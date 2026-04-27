from __future__ import annotations

import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from services.auth_service import (
    AUTH_SESSION_TTL,
    build_session_cookie,
    create_session,
    destroy_session,
    get_cookie_value,
    get_user_group,
    resolve_session,
    resolve_session_info,
    validate_credentials,
)
from services.case_search_service import infer_dataset, infer_dataset_with_context, run_case_search
from services.experiment_service import stream_experiment_run
from services.pipeline_service import run_pipeline_sync, stream_pipeline
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
PIPELINE_SCRIPT = os.getenv("PIPELINE_SCRIPT", "/app/scripts/run_parallel_generation_pipeline.py")
PIPELINE_RUN_DIR = Path(os.getenv("PIPELINE_RUN_DIR", "/app/data/frontend_pipeline_runs"))


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

    def _get_cookie(self, name: str = "") -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        return get_cookie_value(raw_cookie, name) if name else get_cookie_value(raw_cookie)

    def _build_session_cookie(self, token: str, max_age: int) -> str:
        return build_session_cookie(token, max_age)

    def _authenticated_username(self) -> str | None:
        return resolve_session(self._get_cookie())

    def _authenticated_session(self) -> dict[str, object] | None:
        return resolve_session_info(self._get_cookie())

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

    def _write_bad_request(self, message: str) -> None:
        self._write_json(400, {"message": message})

    def _send_event_stream_headers(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_stream_headers()
        self.end_headers()

    def _handle_auth_me(self) -> None:
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

    def _handle_template_prompts(self) -> None:
        try:
            prompts = list_template_prompts()
            self._write_json(200, {"prompts": prompts})
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_template_sections(self) -> None:
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

    def _handle_auth_login(self) -> None:
        try:
            body = self._read_json_body()
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "")
            if not validate_credentials(username, password):
                self._write_json(401, {"message": "用户名或密码错误", "code": "INVALID_CREDENTIALS"})
                return
            token, _ = create_session(username)
            self._write_json(
                200,
                {"ok": True, "username": username, "group": get_user_group(username)},
                extra_headers=[("Set-Cookie", self._build_session_cookie(token, AUTH_SESSION_TTL))],
            )
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_auth_logout(self) -> None:
        destroy_session(self._get_cookie())
        self._write_json(
            200,
            {"ok": True},
            extra_headers=[("Set-Cookie", self._build_session_cookie("", 0))],
        )

    def _handle_trace_subgraph(self) -> None:
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
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_quality_review(self) -> None:
        try:
            body = self._read_json_body()
            prompt = str(body.get("prompt") or "").strip()
            content = str(body.get("content") or "").strip()
            mode = str(body.get("mode") or "optimize").strip() or "optimize"
            fault_scene = str(body.get("faultScene") or "")
            graph_material = str(body.get("graphMaterial") or "")
            if not prompt:
                self._write_bad_request("prompt is required")
                return
            if not content:
                self._write_bad_request("content is required")
                return

            if not body.get("stream"):
                result = run_format_review_sync(prompt, content, fault_scene, graph_material)
                self._write_json(200, {"mode": mode, **result})
                return

            self._send_event_stream_headers()
            try:
                stream_format_review(self, prompt, content, mode, fault_scene, graph_material)
            except Exception as exc:
                send_sse(self, "quality_error", {"mode": mode, "message": str(exc)})
            finally:
                send_sse(self, "close", {})
                self.wfile.flush()
                self.wfile.close()
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_template_prompt_save(self) -> None:
        try:
            if self._require_admin() is None:
                return
            body = self._read_json_body()
            prompt_key = str(body.get("prompt_key") or "").strip()
            prompt_text = str(body.get("prompt_text") or "")
            if not prompt_key:
                self._write_bad_request("prompt_key is required")
                return

            update_template_prompt(prompt_key, prompt_text)
            prompts = list_template_prompts()
            matched = next((item for item in prompts if item["prompt_key"] == prompt_key), None)
            self._write_json(200, {"ok": True, "prompt": matched})
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_template_section_mutation(self) -> None:
        try:
            if self._require_admin() is None:
                return
            body = self._read_json_body()
            section_id = str(body.get("section_id") or "").strip()
            if not section_id:
                self._write_bad_request("section_id is required")
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
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def _handle_pipeline_run(self) -> None:
        try:
            body = self._read_json_body()
            question = str(body.get("question") or "").strip()
            enable_case_search = bool(body.get("enableCaseSearch"))
            enable_multi_fault_search = bool(body.get("enableMultiFaultSearch"))
            if not question:
                self._write_bad_request("question is required")
                return

            if not body.get("stream"):
                result = run_pipeline_sync(
                    question,
                    pipeline_script=PIPELINE_SCRIPT,
                    make_run_dir=make_run_dir,
                    find_result_file=find_result_file,
                    infer_dataset_with_context=infer_dataset_with_context,
                    infer_dataset=infer_dataset,
                    run_case_search=run_case_search,
                    enable_case_search=enable_case_search,
                    enable_multi_fault_search=enable_multi_fault_search,
                )
                self._write_json(200, result)
                return

            self._send_event_stream_headers()
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

    def _handle_experiment_run(self) -> None:
        try:
            body = self._read_json_body()
            if not body.get("stream"):
                self._write_bad_request("stream is required")
                return
            self._send_event_stream_headers()
            try:
                stream_experiment_run(self, body)
            except Exception as exc:
                send_sse(self, "experiment_error", {"message": str(exc)})
            finally:
                send_sse(self, "close", {})
                self.wfile.flush()
                self.wfile.close()
        except Exception as exc:
            self._write_json(500, {"message": str(exc)})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/auth/me":
            self._handle_auth_me()
            return

        if self.path.startswith("/api/") and self._require_auth() is None:
            return

        if self.path == "/api/template/prompts":
            self._handle_template_prompts()
            return

        if self.path == "/api/template/sections":
            self._handle_template_sections()
            return

        self._write_json(404, {"message": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/auth/login":
            self._handle_auth_login()
            return

        if self.path == "/api/auth/logout":
            self._handle_auth_logout()
            return

        if self.path.startswith("/api/") and self._require_auth() is None:
            return

        if self.path == "/api/trace/subgraph":
            self._handle_trace_subgraph()
            return

        if self.path == "/api/quality/review":
            self._handle_quality_review()
            return

        if self.path == "/api/template/prompt/save":
            self._handle_template_prompt_save()
            return

        if self.path in ("/api/template/section/save", "/api/template/section/reset"):
            self._handle_template_section_mutation()
            return

        if self.path == "/api/experiment/run":
            self._handle_experiment_run()
            return

        if self.path not in ("/api/plan/generate", "/api/pipeline/run"):
            self._write_json(404, {"message": "not found"})
            return

        self._handle_pipeline_run()


def main() -> None:
    PIPELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"frontend proxy listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
