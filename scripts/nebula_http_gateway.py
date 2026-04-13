#!/usr/bin/env python3
import argparse
import base64
import json
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


ERROR_PATTERN = re.compile(r"\[ERROR [^\]]+\]:\s*(.+)")
SPACE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    ) -> None:
        self.docker_network = docker_network
        self.console_image = console_image
        self.nebula_host = nebula_host
        self.nebula_port = nebula_port
        self.nebula_user = nebula_user
        self.nebula_password = nebula_password
        self.timeout_sec = timeout_sec

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
            return {
                "ok": False,
                "error_type": "timeout",
                "duration_ms": duration_ms,
                "message": f"query timed out after {self.timeout_sec}s",
            }
        except FileNotFoundError:
            duration_ms = int((time.time() - started) * 1000)
            return {
                "ok": False,
                "error_type": "environment",
                "duration_ms": duration_ms,
                "message": "docker command not found",
            }

        duration_ms = int((time.time() - started) * 1000)
        stdout = self._decode_output(proc.stdout or b"")
        stderr = self._decode_output(proc.stderr or b"")
        errors = [m.group(1).strip() for m in ERROR_PATTERN.finditer(stdout)]
        ok = proc.returncode == 0 and not errors

        return {
            "ok": ok,
            "duration_ms": duration_ms,
            "return_code": proc.returncode,
            "errors": errors,
            "stdout": stdout,
            "stderr": stderr,
            "meta": {
                "docker_network": self.docker_network,
                "nebula_host": self.nebula_host,
                "nebula_port": self.nebula_port,
            },
        }

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
            status_code = 200 if result.get("ok") else 502
            self._json(status_code, result)
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
            if result.get("ok"):
                self._json(200, result)
                return
            if result.get("error_type") == "validation":
                self._json(400, result)
                return
            self._json(502, result)
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    gateway = NebulaGateway(
        docker_network=args.docker_network,
        console_image=args.console_image,
        nebula_host=args.nebula_host,
        nebula_port=args.nebula_port,
        nebula_user=args.nebula_user,
        nebula_password=args.nebula_password,
        timeout_sec=args.timeout_sec,
    )
    server = ThreadingHTTPServer((args.host, args.port), GatewayHandler)
    server.gateway = gateway  # type: ignore[attr-defined]
    print(
        f"nebula-http-gateway listening on http://{args.host}:{args.port} "
        f"(network={args.docker_network}, nebula={args.nebula_host}:{args.nebula_port})"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
