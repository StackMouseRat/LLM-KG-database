#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

try:
    from nebula3.Config import Config as NebulaConfig
    from nebula3.gclient.net import ConnectionPool as NebulaConnectionPool
except Exception:
    NebulaConfig = None
    NebulaConnectionPool = None


ERROR_PATTERN = re.compile(r"\[ERROR [^\]]+\]:\s*(.+)")
SPACE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


CLIENT_ERROR_TYPES = {
    "validation",
    "ngql_syntax",
    "ngql_semantic",
    "space_not_found",
    "schema_not_found",
    "ngql_client_error",
}

ERROR_HTTP_STATUS = {
    "validation": 400,
    "ngql_syntax": 400,
    "ngql_semantic": 400,
    "space_not_found": 400,
    "schema_not_found": 400,
    "ngql_client_error": 400,
    "queue_timeout": 429,
    "timeout": 504,
    "nebula_unavailable": 503,
    "environment": 503,
    "console_runtime": 502,
}


def normalize_error_message(errors: list[str], stderr: str, stdout: str, return_code: int) -> str:
    if errors:
        return errors[0]
    for value in (stderr.strip(), stdout.strip()):
        if value:
            return value.splitlines()[-1].strip()
    return f"nebula-console exited with code {return_code}"


def classify_nebula_error(message: str, stderr: str, return_code: int) -> str:
    value = f"{message}\n{stderr}".lower()
    if "syntaxerror" in value or "syntax error" in value or "syntaxerror:" in value:
        return "ngql_syntax"
    if "spacenotfound" in value or "space not found" in value or "space `" in value and "not found" in value or "no space" in value:
        return "space_not_found"
    if any(token in value for token in ("tag not found", "edge not found", "schema not found", "unknown tag", "unknown edge")):
        return "schema_not_found"
    if "semanticerror" in value or "semantic error" in value or "semantical error" in value:
        return "ngql_semantic"
    if any(token in value for token in ("connection refused", "transport failure", "failed to connect", "all hosts are invalid")):
        return "nebula_unavailable"
    if return_code == 0:
        return "ngql_client_error"
    return "console_runtime"


class NebulaGateway:
    def __init__(
        self,
        docker_network: str,
        console_image: str,
        nebula_host: str,
        nebula_port: int,
        nebula_user: str,
        nebula_password: str,
        timeout_sec: int,
        max_concurrency: int,
        queue_timeout_sec: float,
        driver_mode: str,
        client_pool_size: int,
    ) -> None:
        self.docker_network = docker_network
        self.console_image = console_image
        self.nebula_host = nebula_host
        self.nebula_port = nebula_port
        self.nebula_user = nebula_user
        self.nebula_password = nebula_password
        self.timeout_sec = timeout_sec
        self.max_concurrency = max_concurrency
        self.queue_timeout_sec = queue_timeout_sec
        self.driver_mode = driver_mode
        self.client_pool_size = client_pool_size
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._client_pool = None
        self._client_pool_error = ""
        if self.driver_mode in {"auto", "client"}:
            self._init_client_pool()

    def _init_client_pool(self) -> None:
        if NebulaConfig is None or NebulaConnectionPool is None:
            self._client_pool_error = "nebula3-python not installed"
            return
        try:
            config = NebulaConfig()
            config.max_connection_pool_size = self.client_pool_size
            config.min_connection_pool_size = 1
            config.timeout = self.timeout_sec * 1000
            pool = NebulaConnectionPool()
            ok = pool.init([(self.nebula_host, self.nebula_port)], config)
            if not ok:
                self._client_pool_error = "failed to initialize Nebula connection pool"
                return
            self._client_pool = pool
        except Exception as exc:
            self._client_pool_error = f"client pool init failed: {exc}"

    def _execute_with_client(self, query: str, space: str | None, queue_wait_ms: int, started: float) -> dict[str, Any]:
        if self._client_pool is None:
            raise RuntimeError(self._client_pool_error or "client pool unavailable")
        session = None
        try:
            session = self._client_pool.get_session(self.nebula_user, self.nebula_password)
            if space:
                use_result = session.execute(f"USE {space};")
                if not use_result.is_succeeded():
                    message = str(use_result.error_msg() or "failed to select space")
                    return self._build_error_result(
                        error_type=classify_nebula_error(message, "", 0),
                        message=message,
                        duration_ms=int((time.time() - started) * 1000),
                        queue_wait_ms=queue_wait_ms,
                        stdout=self._render_result_stdout(use_result),
                        stderr="",
                        return_code=0,
                        driver_mode="client",
                    )
            result = session.execute(query)
            duration_ms = int((time.time() - started) * 1000)
            stdout = self._render_result_stdout(result)
            if result.is_succeeded():
                return {
                    "ok": True,
                    "duration_ms": duration_ms,
                    "queue_wait_ms": queue_wait_ms,
                    "return_code": 0,
                    "errors": [],
                    "stdout": stdout,
                    "stderr": "",
                    "meta": {
                        "driver_mode": "client",
                        "nebula_host": self.nebula_host,
                        "nebula_port": self.nebula_port,
                        "max_concurrency": self.max_concurrency,
                    },
                }
            message = str(result.error_msg() or "nebula query failed")
            return self._build_error_result(
                error_type=classify_nebula_error(message, "", 0),
                message=message,
                duration_ms=duration_ms,
                queue_wait_ms=queue_wait_ms,
                stdout=stdout,
                stderr="",
                return_code=0,
                driver_mode="client",
            )
        finally:
            if session is not None:
                try:
                    session.release()
                except Exception:
                    pass

    def _execute_with_console(self, query: str, space: str | None, queue_wait_ms: int, started: float) -> dict[str, Any]:
        script = query + "\n"
        if space:
            script = f"USE {space};\n" + script
        try:
            script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
            shell_cmd = (
                f"echo '{script_b64}' | base64 -d | "
                f"nebula-console -addr {self.nebula_host} -port {self.nebula_port} "
                f"-u {self.nebula_user} -p {self.nebula_password}"
            )

            cmd = [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                "--network",
                self.docker_network,
                self.console_image,
                "-lc",
                shell_cmd,
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout_sec,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - started) * 1000)
            return self._build_error_result(
                error_type="timeout",
                message=f"query timed out after {self.timeout_sec}s",
                duration_ms=duration_ms,
                queue_wait_ms=queue_wait_ms,
                stdout="",
                stderr="",
                return_code=124,
                driver_mode="console",
            )
        except FileNotFoundError:
            duration_ms = int((time.time() - started) * 1000)
            return self._build_error_result(
                error_type="environment",
                message="docker command not found",
                duration_ms=duration_ms,
                queue_wait_ms=queue_wait_ms,
                stdout="",
                stderr="",
                return_code=127,
                driver_mode="console",
            )

        duration_ms = int((time.time() - started) * 1000)
        stdout = self._decode_output(proc.stdout or b"")
        stderr = self._decode_output(proc.stderr or b"")
        errors = [m.group(1).strip() for m in ERROR_PATTERN.finditer(stdout)]
        ok = proc.returncode == 0 and not errors
        if ok:
            return {
                "ok": True,
                "duration_ms": duration_ms,
                "queue_wait_ms": queue_wait_ms,
                "return_code": proc.returncode,
                "errors": [],
                "stdout": stdout,
                "stderr": stderr,
                "meta": {
                    "driver_mode": "console",
                    "docker_network": self.docker_network,
                    "nebula_host": self.nebula_host,
                    "nebula_port": self.nebula_port,
                    "max_concurrency": self.max_concurrency,
                },
            }
        message = normalize_error_message(errors, stderr, stdout, proc.returncode)
        return self._build_error_result(
            error_type=classify_nebula_error(message, stderr, proc.returncode),
            message=message,
            duration_ms=duration_ms,
            queue_wait_ms=queue_wait_ms,
            stdout=stdout,
            stderr=stderr,
            return_code=proc.returncode,
            driver_mode="console",
            errors=errors,
        )

    @staticmethod
    def _build_error_result(
        *,
        error_type: str,
        message: str,
        duration_ms: int,
        queue_wait_ms: int,
        stdout: str,
        stderr: str,
        return_code: int,
        driver_mode: str,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "error_type": error_type,
            "duration_ms": duration_ms,
            "queue_wait_ms": queue_wait_ms,
            "return_code": return_code,
            "errors": errors or ([message] if message else []),
            "message": message,
            "stdout": stdout,
            "stderr": stderr,
            "meta": {
                "driver_mode": driver_mode,
            },
        }

    @staticmethod
    def _render_result_stdout(result: Any) -> str:
        try:
            keys = list(result.keys())
            rows: list[list[str]] = []
            for row_index in range(result.row_size()):
                values = []
                for value in result.row_values(row_index):
                    rendered = value.cast()
                    if isinstance(rendered, str):
                        values.append(f'"{rendered}"')
                    else:
                        values.append(str(rendered))
                rows.append(values)
            return render_table(keys, rows)
        except Exception:
            return str(result)

    def run_ngql(self, ngql: str, space: str | None = None) -> dict[str, Any]:
        query = ngql.strip()
        if not query:
            return {
                "ok": False,
                "error_type": "validation",
                "message": "ngql cannot be empty",
            }

        script = query + "\n"
        if space:
            script = f"USE {space};\n" + script

        started = time.time()
        acquired = self._semaphore.acquire(timeout=self.queue_timeout_sec)
        queue_wait_ms = int((time.time() - started) * 1000)
        if not acquired:
            return {
                "ok": False,
                "error_type": "queue_timeout",
                "duration_ms": queue_wait_ms,
                "queue_wait_ms": queue_wait_ms,
                "message": f"gateway query queue timed out after {self.queue_timeout_sec}s",
                "meta": {
                    "max_concurrency": self.max_concurrency,
                    "queue_timeout_sec": self.queue_timeout_sec,
                },
            }

        try:
            if self.driver_mode == "client":
                try:
                    return self._execute_with_client(query, space, queue_wait_ms, started)
                except Exception as exc:
                    duration_ms = int((time.time() - started) * 1000)
                    return self._build_error_result(
                        error_type="environment",
                        message=f"nebula client unavailable: {exc}",
                        duration_ms=duration_ms,
                        queue_wait_ms=queue_wait_ms,
                        stdout="",
                        stderr="",
                        return_code=1,
                        driver_mode="client",
                    )
            if self.driver_mode == "console":
                return self._execute_with_console(query, space, queue_wait_ms, started)

            if self._client_pool is not None:
                try:
                    return self._execute_with_client(query, space, queue_wait_ms, started)
                except Exception as exc:
                    self._client_pool_error = str(exc)

            return self._execute_with_console(query, space, queue_wait_ms, started)
        finally:
            self._semaphore.release()

    @staticmethod
    def _decode_output(data: bytes) -> str:
        if not data:
            return ""
        for enc in ("utf-8", "gb18030"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    string_headers = [str(item) for item in headers]
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(header) for header in string_headers]
    for row in string_rows:
        for idx, cell in enumerate(row):
            if idx < len(widths):
                widths[idx] = max(widths[idx], len(cell))
    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    header_line = "| " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(string_headers)) + " |"
    body_lines = ["| " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(widths))) + " |" for row in string_rows]
    lines = [border, header_line, border, *body_lines, border]
    return "\n" + "\n".join(lines) + (f"\nGot {len(string_rows)} rows\n" if rows else "\n")


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "NebulaHTTPGateway/0.1"

    @property
    def gateway(self) -> NebulaGateway:
        return self.server.gateway  # type: ignore[attr-defined]

    def _json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _status_for_result(result: dict[str, Any]) -> int:
        if result.get("ok"):
            return 200
        error_type = str(result.get("error_type") or "")
        return ERROR_HTTP_STATUS.get(error_type, 502)

    def _read_json_body(self) -> tuple[dict[str, Any] | None, str | None]:
        content_length = self.headers.get("Content-Length")
        if not content_length:
            return None, "missing Content-Length"
        try:
            length = int(content_length)
        except ValueError:
            return None, "invalid Content-Length"
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")), None
        except json.JSONDecodeError:
            return None, "invalid JSON body"

    def do_OPTIONS(self) -> None:
        self._json(204, {})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._json(
                200,
                {
                    "name": "nebula-http-gateway",
                    "endpoints": ["/graph/health", "/graph/query"],
                },
            )
            return

        if path == "/graph/health":
            result = self.gateway.run_ngql("SHOW HOSTS;")
            self._json(self._status_for_result(result), result)
            return

        self._json(404, {"ok": False, "message": "not found"})

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path != "/graph/query":
                self._json(404, {"ok": False, "message": "not found"})
                return

            payload, error = self._read_json_body()
            if error:
                self._json(400, {"ok": False, "message": error})
                return
            if not isinstance(payload, dict):
                self._json(400, {"ok": False, "message": "JSON body must be an object"})
                return

            ngql = payload.get("ngql")
            if not isinstance(ngql, str):
                self._json(400, {"ok": False, "message": "field 'ngql' must be string"})
                return

            space = payload.get("space")
            if space is not None:
                if not isinstance(space, str):
                    self._json(400, {"ok": False, "message": "field 'space' must be string"})
                    return
                if not SPACE_PATTERN.fullmatch(space):
                    self._json(400, {"ok": False, "message": "invalid space name"})
                    return

            result = self.gateway.run_ngql(ngql=ngql, space=space)
            self._json(self._status_for_result(result), result)
        except Exception as exc:
            self._json(
                500,
                {
                    "ok": False,
                    "message": f"gateway internal error: {exc.__class__.__name__}",
                },
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nebula Graph HTTP gateway")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--docker-network",
        default="nebula-docker-compose_nebula-net",
        help="Docker network where Nebula services are reachable",
    )
    parser.add_argument(
        "--console-image",
        default="docker.io/vesoft/nebula-console:v3.6.0",
        help="Nebula console image used to execute nGQL",
    )
    parser.add_argument("--nebula-host", default="graphd")
    parser.add_argument("--nebula-port", type=int, default=9669)
    parser.add_argument("--nebula-user", default="root")
    parser.add_argument("--nebula-password", default="nebula")
    parser.add_argument("--timeout-sec", type=int, default=20)
    parser.add_argument(
        "--driver-mode",
        choices=("auto", "client", "console"),
        default=os.getenv("NEBULA_GATEWAY_DRIVER_MODE", "auto"),
        help="Query execution mode: direct client pool, nebula-console, or auto fallback.",
    )
    parser.add_argument(
        "--client-pool-size",
        type=int,
        default=int(os.getenv("NEBULA_GATEWAY_CLIENT_POOL_SIZE", "16")),
        help="Connection pool size for nebula3-python direct mode.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=int(os.getenv("NEBULA_GATEWAY_MAX_CONCURRENCY", "8")),
        help="Maximum number of nebula-console queries allowed to run concurrently.",
    )
    parser.add_argument(
        "--queue-timeout-sec",
        type=float,
        default=float(os.getenv("NEBULA_GATEWAY_QUEUE_TIMEOUT_SEC", "5")),
        help="Maximum seconds a request may wait for an available query slot.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    max_concurrency = max(1, args.max_concurrency)
    queue_timeout_sec = max(0.1, args.queue_timeout_sec)
    client_pool_size = max(1, args.client_pool_size)
    gateway = NebulaGateway(
        docker_network=args.docker_network,
        console_image=args.console_image,
        nebula_host=args.nebula_host,
        nebula_port=args.nebula_port,
        nebula_user=args.nebula_user,
        nebula_password=args.nebula_password,
        timeout_sec=args.timeout_sec,
        max_concurrency=max_concurrency,
        queue_timeout_sec=queue_timeout_sec,
        driver_mode=args.driver_mode,
        client_pool_size=client_pool_size,
    )
    server = ThreadingHTTPServer((args.host, args.port), GatewayHandler)
    server.gateway = gateway  # type: ignore[attr-defined]
    print(
        f"nebula-http-gateway listening on http://{args.host}:{args.port} "
        f"(network={args.docker_network}, nebula={args.nebula_host}:{args.nebula_port}, "
        f"driver_mode={args.driver_mode}, client_pool_size={client_pool_size}, "
        f"max_concurrency={max_concurrency}, queue_timeout_sec={queue_timeout_sec})"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
