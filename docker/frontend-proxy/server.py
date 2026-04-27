from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
import json
import os
import random
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from services.case_search_service import infer_dataset, infer_dataset_with_context, run_case_search
from services.pipeline_service import stream_pipeline
from services.quality_service import run_format_review_sync, stream_format_review
from services.sse import send_sse
from services.template_service import (
    TEMPLATE_ID,
    ensure_template_defaults_snapshot,
    gql,
    list_template_prompts,
    list_template_sections,
    update_template_prompt,
    update_template_section,
)
from services.trace_service import build_trace_subgraph, extract_trace_focus_fields


PORT = int(os.getenv("FRONTEND_PROXY_PORT", "8788"))
AUTH_USERS_RAW = os.getenv("APP_LOGIN_USERS", "")
AUTH_USERNAME = os.getenv("APP_LOGIN_USERNAME", "")
AUTH_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")
AUTH_COOKIE_NAME = os.getenv("APP_LOGIN_COOKIE_NAME", "llmkg_session")
AUTH_SESSION_TTL = int(os.getenv("APP_LOGIN_SESSION_TTL", "86400"))
PIPELINE_SCRIPT = os.getenv("PIPELINE_SCRIPT", "/app/scripts/run_parallel_generation_pipeline.py")
PIPELINE_RUN_DIR = Path(os.getenv("PIPELINE_RUN_DIR", "/app/data/frontend_pipeline_runs"))
ACTIVE_SESSIONS: dict[str, dict[str, object]] = {}
SESSION_LOCK = threading.Lock()

def load_auth_users() -> dict[str, str]:
    users: dict[str, str] = {}

    for item in str(AUTH_USERS_RAW or "").split(","):
        pair = item.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        if username:
            users[username] = password

    if AUTH_USERNAME:
        users.setdefault(AUTH_USERNAME, AUTH_PASSWORD)

    return users


AUTH_USERS = load_auth_users()


def get_user_group(username: str) -> str:
    return "admin" if username == "admin" else "user"


def create_session(username: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + AUTH_SESSION_TTL
    with SESSION_LOCK:
        ACTIVE_SESSIONS[token] = {
            "username": username,
            "group": get_user_group(username),
            "expires_at": expires_at,
        }
    return token, expires_at


def resolve_session_info(token: str | None) -> dict[str, object] | None:
    if not token:
        return None
    now = int(time.time())
    with SESSION_LOCK:
        session = ACTIVE_SESSIONS.get(token)
        if not session:
            return None
        expires_at = int(session.get("expires_at") or 0)
        if expires_at <= now:
            ACTIVE_SESSIONS.pop(token, None)
            return None
        return {
            "username": str(session.get("username") or ""),
            "group": str(session.get("group") or get_user_group(str(session.get("username") or ""))),
        }


def resolve_session(token: str | None) -> str | None:
    session = resolve_session_info(token)
    if not session:
        return None
    return str(session.get("username") or "")


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with SESSION_LOCK:
        ACTIVE_SESSIONS.pop(token, None)


def make_run_dir() -> Path:
    base_dir = PIPELINE_RUN_DIR / f"run_{int(time.time() * 1000)}_{random.randrange(0, 0xFFFFFF):06x}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def find_result_file(base_dir: Path) -> Path:
    result_dirs = sorted(path for path in base_dir.iterdir() if path.is_dir())
    if not result_dirs:
        raise RuntimeError(f"pipeline result directory not found: {base_dir}")
    result_file = result_dirs[-1] / "pipeline_result.json"
    if not result_file.exists():
        raise RuntimeError(f"pipeline result file not found: {result_file}")
    return result_file


def run_pipeline_process(question: str, enable_multi_fault_search: bool = False) -> dict:
    base_dir = make_run_dir()
    command = [
        sys.executable,
        PIPELINE_SCRIPT,
        "--question",
        question,
        "--output-dir",
        str(base_dir),
    ]
    if enable_multi_fault_search:
        command.append("--multi-fault")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"pipeline exited with code {completed.returncode}"
        )
    result_file = find_result_file(base_dir)
    return json.loads(result_file.read_text(encoding="utf-8"))


def run_pipeline_sync(question: str, enable_case_search: bool = False, enable_multi_fault_search: bool = False) -> dict:
    dataset = infer_dataset_with_context(question) if enable_case_search else None
    if enable_case_search and dataset is not None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            pipeline_future = executor.submit(run_pipeline_process, question, enable_multi_fault_search)
            case_future = executor.submit(run_case_search, question, dataset)
            result = pipeline_future.result()
            try:
                result["case_search"] = case_future.result()
            except Exception as exc:
                result["case_search"] = {
                    "enabled": True,
                    "status": "error",
                    "kb_name": dataset["kb_name"],
                    "dataset_id": dataset["dataset_id"],
                    "query_question": question,
                    "error": str(exc),
                }
            return result

    result = run_pipeline_process(question, enable_multi_fault_search)
    if enable_case_search:
        dataset = infer_dataset(question, result)
        if dataset is None:
            result["case_search"] = {
                "enabled": True,
                "status": "skipped",
                "query_question": question,
                "error": "未命中已建立知识库对应设备",
            }
        else:
            result["case_search"] = run_case_search(question, dataset)
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "FrontendProxy/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_common_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_stream_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _write_json(self, status: int, payload: dict, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _get_cookie(self, name: str) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    def _build_session_cookie(self, token: str, max_age: int) -> str:
        return (
            f"{AUTH_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
        )

    def _authenticated_username(self) -> str | None:
        return resolve_session(self._get_cookie(AUTH_COOKIE_NAME))

    def _authenticated_session(self) -> dict[str, object] | None:
        return resolve_session_info(self._get_cookie(AUTH_COOKIE_NAME))

    def _require_auth(self) -> str | None:
        username = self._authenticated_username()
        if username:
            return username
        self._write_json(401, {"message": "请先登录", "code": "UNAUTHORIZED"})
        return None

    def _require_admin(self) -> dict[str, object] | None:
        session = self._authenticated_session()
        if not session:
            self._write_json(401, {"message": "请先登录", "code": "UNAUTHORIZED"})
            return None
        if str(session.get("group") or "") != "admin":
            self._write_json(403, {"message": "无权限执行该操作", "code": "FORBIDDEN"})
            return None
        return session

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/auth/me":
            session = self._authenticated_session()
            if not session:
                self._write_json(401, {"message": "未登录", "code": "UNAUTHORIZED"})
                return
            self._write_json(
                200,
                {
                    "ok": True,
                    "username": str(session.get("username") or ""),
                    "group": str(session.get("group") or ""),
                },
            )
            return

        if self.path.startswith("/api/") and self._require_auth() is None:
            return

        if self.path == "/api/template/prompts":
            try:
                prompts = list_template_prompts()
                self._write_json(200, {"prompts": prompts})
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path != "/api/template/sections":
            self._write_json(404, {"message": "not found"})
            return

        try:
            sections = list_template_sections()
            defaults = ensure_template_defaults_snapshot(sections)
            payload = {
                "template_id": TEMPLATE_ID,
                "sections": [
                    {
                        **section,
                        "default": defaults.get(section["section_id"], {}),
                    }
                    for section in sections
                ],
            }
            self._write_json(200, payload)
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def do_POST(self) -> None:
        if self.path == "/api/auth/login":
            try:
                body = self._read_json_body()
                username = str(body.get("username") or "").strip()
                password = str(body.get("password") or "")
                if not username or AUTH_USERS.get(username) != password:
                    self._write_json(401, {"message": "用户名或密码错误", "code": "INVALID_CREDENTIALS"})
                    return
                token, _ = create_session(username)
                self._write_json(
                    200,
                    {"ok": True, "username": username, "group": get_user_group(username)},
                    extra_headers=[("Set-Cookie", self._build_session_cookie(token, AUTH_SESSION_TTL))],
                )
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path == "/api/auth/logout":
            destroy_session(self._get_cookie(AUTH_COOKIE_NAME))
            self._write_json(
                200,
                {"ok": True},
                extra_headers=[("Set-Cookie", self._build_session_cookie("", 0))],
            )
            return

        if self.path.startswith("/api/") and self._require_auth() is None:
            return

        if self.path == "/api/trace/subgraph":
            try:
                body = self._read_json_body()
                question = str(body.get("question") or "").strip()
                fault_scene = str(body.get("faultScene") or "")
                graph_material = str(body.get("graphMaterial") or "")
                focus = extract_trace_focus_fields(question, fault_scene, graph_material)
                trace = build_trace_subgraph(
                    space=str(focus.get("space") or ""),
                    fault_name=str(focus.get("fault") or ""),
                    graph_query=gql,
                    device_name=str(focus.get("device") or ""),
                    hit_fault_names=focus.get("faults") if isinstance(focus.get("faults"), list) else None,
                )
                self._write_json(200, trace)
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path == "/api/quality/review":
            try:
                body = self._read_json_body()
                prompt = str(body.get("prompt") or "").strip()
                content = str(body.get("content") or "").strip()
                mode = str(body.get("mode") or "optimize").strip() or "optimize"
                fault_scene = str(body.get("faultScene") or "")
                graph_material = str(body.get("graphMaterial") or "")
                if not prompt:
                    self.send_response(400)
                    self._send_common_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": "prompt is required"}).encode("utf-8"))
                    return
                if not content:
                    self.send_response(400)
                    self._send_common_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": "content is required"}).encode("utf-8"))
                    return

                if not body.get("stream"):
                    result = run_format_review_sync(prompt, content, fault_scene, graph_material)
                    payload = json.dumps({"mode": mode, **result}, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self._send_common_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._send_stream_headers()
                self.end_headers()
                try:
                    stream_format_review(self, prompt, content, mode, fault_scene, graph_material)
                except Exception as exc:
                    send_sse(self, "quality_error", {"mode": mode, "message": str(exc)})
                finally:
                    send_sse(self, "close", {})
                    self.wfile.flush()
                    self.wfile.close()
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path == "/api/template/prompt/save":
            try:
                if self._require_admin() is None:
                    return
                body = self._read_json_body()
                prompt_key = str(body.get("prompt_key") or "").strip()
                prompt_text = str(body.get("prompt_text") or "")
                if not prompt_key:
                    self.send_response(400)
                    self._send_common_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": "prompt_key is required"}).encode("utf-8"))
                    return

                update_template_prompt(prompt_key, prompt_text)
                prompts = list_template_prompts()
                matched = next((item for item in prompts if item["prompt_key"] == prompt_key), None)
                self._write_json(200, {"ok": True, "prompt": matched})
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path in ("/api/template/section/save", "/api/template/section/reset"):
            try:
                if self._require_admin() is None:
                    return
                body = self._read_json_body()
                section_id = str(body.get("section_id") or "").strip()
                if not section_id:
                    self.send_response(400)
                    self._send_common_headers()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": "section_id is required"}).encode("utf-8"))
                    return

                if self.path == "/api/template/section/reset":
                    sections = list_template_sections()
                    defaults = ensure_template_defaults_snapshot(sections)
                    default = defaults.get(section_id)
                    if not default:
                        raise RuntimeError(f"default template section not found: {section_id}")
                    update_template_section(
                        section_id,
                        str(default.get("source_type") or ""),
                        str(default.get("fixed_text") or ""),
                        str(default.get("gen_instruction") or ""),
                    )
                else:
                    update_template_section(
                        section_id,
                        str(body.get("source_type") or ""),
                        str(body.get("fixed_text") or ""),
                        str(body.get("gen_instruction") or ""),
                    )

                sections = list_template_sections()
                defaults = ensure_template_defaults_snapshot(sections)
                matched = next((item for item in sections if item["section_id"] == section_id), None)
                payload = {
                    "ok": True,
                    "section": {
                        **matched,
                        "default": defaults.get(section_id, {}),
                    }
                    if matched
                    else None,
                }
                self._write_json(200, payload)
                return
            except Exception as exc:
                self._write_json(500, {"message": str(exc)})
                return

        if self.path not in ("/api/plan/generate", "/api/pipeline/run"):
            self._write_json(404, {"message": "not found"})
            return

        try:
            body = self._read_json_body()
            question = str(body.get("question") or "").strip()
            enable_case_search = bool(body.get("enableCaseSearch"))
            enable_multi_fault_search = bool(body.get("enableMultiFaultSearch"))
            if not question:
                self.send_response(400)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"message": "question is required"}).encode("utf-8"))
                return

            if not body.get("stream"):
                result = run_pipeline_sync(
                    question,
                    enable_case_search=enable_case_search,
                    enable_multi_fault_search=enable_multi_fault_search,
                )
                self._write_json(200, result)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._send_stream_headers()
            self.end_headers()
            stream_pipeline(
                question,
                self,
                pipeline_script=PIPELINE_SCRIPT,
                make_run_dir=make_run_dir,
                infer_dataset_with_context=infer_dataset_with_context,
                infer_dataset=infer_dataset,
                run_case_search=run_case_search,
                enable_case_search=enable_case_search,
                enable_multi_fault_search=enable_multi_fault_search,
            )
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})


def main() -> None:
    PIPELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"frontend proxy listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
