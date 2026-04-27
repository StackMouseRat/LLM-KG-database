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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.case_search_service import infer_dataset, infer_dataset_with_context, run_case_search
from services.pipeline_service import stream_pipeline
from services.sse import send_sse
from services.trace_service import build_trace_subgraph, extract_trace_focus_fields


PORT = int(os.getenv("FRONTEND_PROXY_PORT", "8788"))
AUTH_USERS_RAW = os.getenv("APP_LOGIN_USERS", "")
AUTH_USERNAME = os.getenv("APP_LOGIN_USERNAME", "")
AUTH_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")
AUTH_COOKIE_NAME = os.getenv("APP_LOGIN_COOKIE_NAME", "llmkg_session")
AUTH_SESSION_TTL = int(os.getenv("APP_LOGIN_SESSION_TTL", "86400"))
PIPELINE_SCRIPT = os.getenv("PIPELINE_SCRIPT", "/app/scripts/run_parallel_generation_pipeline.py")
PIPELINE_RUN_DIR = Path(os.getenv("PIPELINE_RUN_DIR", "/app/data/frontend_pipeline_runs"))
FORMAT_REVIEW_PLUGIN_URL = os.getenv(
    "FORMAT_REVIEW_PLUGIN_URL",
    "http://host.docker.internal:3000/api/v1/chat/completions",
)
FORMAT_REVIEW_PLUGIN_KEY_FILE = os.getenv(
    "FORMAT_REVIEW_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/format_review_plugin_api_key",
)
TEMPLATE_GRAPH_URL = os.getenv("TEMPLATE_GRAPH_URL", "http://host.docker.internal:8787/graph/query")
TEMPLATE_SPACE = os.getenv("TEMPLATE_SPACE", "llmkg_templates")
TEMPLATE_ID = os.getenv("TEMPLATE_ID", "tpl_default_emergency")
TEMPLATE_DEFAULTS_FILE = Path(
    os.getenv("TEMPLATE_DEFAULTS_FILE", "/app/data/template_defaults_snapshot.json")
)
PROMPT_TAG = "template_prompt_config"
PROMPT_DEFAULTS = {
    "optimize_prompt": {
        "id": "tpl_prompt_optimize",
        "prompt_key": "optimize_prompt",
        "title": "优化提示词",
        "prompt_text": "请对预案正文进行格式优化：\n1. 保留原始章节编号和标题层级\n2. 修复换行、标题粘连、列表错位\n3. 删除无意义的元信息噪声\n4. 不改变业务含义和处置步骤\n5. 输出适合正式预案阅读的规范文本\n\n若提供了\"故障与场景背景\"和\"图谱检索背景\"，优化时应参考这些背景信息：\n- 故障场景背景含设备名称和故障类型，正文中设备指代应与之一致\n- 图谱检索背景含故障原因、现象、措施等，优化时不应删减或扭曲这些图谱来源内容",
        "order_no": 10,
    },
    "evaluate_prompt": {
        "id": "tpl_prompt_evaluate",
        "prompt_key": "evaluate_prompt",
        "title": "评估提示词",
        "prompt_text": "请对预案正文进行质量评估：\n1. 检查结构是否完整\n2. 检查章节编号是否连续\n3. 检查是否存在重复、缺项、逻辑跳跃\n4. 检查应急动作是否可执行\n5. 输出简短的质量结论与修改建议\n\n关于来源标记[KG]/[GEN]/[FIX]的检查：\n- 不要建议去除这些标记，它们有专门的后处理环节\n- 检查[KG]标记的内容是否与图谱检索背景中的故障原因、现象、措施、后果、风险、资源对应\n- 检查[GEN]标记的内容是否是模型根据场景推导生成的\n- 检查[FIX]标记的内容是否确实是模板中的固定文本\n- 如发现标记与内容来源不符，在修改建议中指出\n\n若提供了\"故障与场景背景\"和\"图谱检索背景\"，评估时应参考这些背景信息：\n- 对照故障场景背景，检查正文中设备名称、故障类型、响应等级是否一致\n- 对照图谱检索背景，检查正文是否遗漏了关键的故障原因、应对措施或安全风险\n- 如发现遗漏应在修改建议中指出具体缺项",
        "order_no": 20,
    },
}
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


def parse_table(stdout: str) -> list[dict[str, str]]:
    rows = []
    for line in stdout.splitlines():
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if not parts:
            continue
        if set("".join(parts)) <= {"+", "-"}:
            continue
        rows.append(parts)
    if len(rows) < 2:
        return []
    header = rows[0]
    data_rows = rows[1:]
    result: list[dict[str, str]] = []
    for row in data_rows:
        if len(row) != len(header):
            continue
        item = {}
        for key, value in zip(header, row):
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            item[key] = value
        result.append(item)
    return result


def count_rows(space: str, ngql: str) -> int:
    rows = parse_table(gql(space, ngql)["stdout"])
    if not rows:
        return 0
    value = next(iter(rows[0].values()))
    try:
        return int(str(value))
    except Exception:
        return 0


def gql(space: str, ngql: str) -> dict:
    req = Request(
        TEMPLATE_GRAPH_URL,
        data=json.dumps({"space": space, "ngql": ngql}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"template graph HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"template graph URL error: {exc}")
    if not body.get("ok"):
        raise RuntimeError(str(body.get("errors") or body.get("message") or body))
    return body


def esc_ngql(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def encode_prompt_text(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("\n", "\\n")


def decode_prompt_text(text: str) -> str:
    return str(text or "").replace("\\n", "\n").replace("\\\\", "\\")


def ensure_prompt_schema() -> None:
    gql(
        TEMPLATE_SPACE,
        f"CREATE TAG IF NOT EXISTS {PROMPT_TAG}(prompt_key string, title string, prompt_text string, order_no int64);",
    )


def ensure_prompt_defaults() -> None:
    ensure_prompt_schema()
    for item in PROMPT_DEFAULTS.values():
        exists = count_rows(
            TEMPLATE_SPACE,
            f"MATCH (p:{PROMPT_TAG}) WHERE id(p) == {esc_ngql(item['id'])} RETURN count(p) AS c;",
        )
        if exists:
            continue
        ngql = (
            f"INSERT VERTEX {PROMPT_TAG}(prompt_key, title, prompt_text, order_no) VALUES "
            f"{esc_ngql(item['id'])}:("
            f"{esc_ngql(item['prompt_key'])},"
            f"{esc_ngql(item['title'])},"
            f"{esc_ngql(encode_prompt_text(item['prompt_text']))},"
            f"{int(item['order_no'])}"
            ");"
        )
        gql(TEMPLATE_SPACE, ngql)


def get_prompt_record(prompt_key: str) -> dict:
    ensure_prompt_defaults()
    default = PROMPT_DEFAULTS[prompt_key]
    ngql = (
        f"MATCH (p:{PROMPT_TAG}) WHERE id(p) == {esc_ngql(default['id'])} "
        "RETURN id(p) AS prompt_id, "
        f"p.{PROMPT_TAG}.prompt_key AS prompt_key, "
        f"p.{PROMPT_TAG}.title AS title, "
        f"p.{PROMPT_TAG}.prompt_text AS prompt_text, "
        f"p.{PROMPT_TAG}.order_no AS order_no;"
    )
    rows = parse_table(gql(TEMPLATE_SPACE, ngql)["stdout"])
    if not rows:
        return {
            "prompt_id": default["id"],
            "prompt_key": default["prompt_key"],
            "title": default["title"],
            "prompt_text": default["prompt_text"],
            "order_no": default["order_no"],
            "default": default,
        }
    row = rows[0]
    return {
        "prompt_id": row.get("prompt_id", ""),
        "prompt_key": row.get("prompt_key", ""),
        "title": row.get("title", ""),
        "prompt_text": decode_prompt_text(row.get("prompt_text", "")),
        "order_no": int(row.get("order_no") or 0),
        "default": default,
    }


def list_template_prompts() -> list[dict]:
    return sorted(
        [get_prompt_record(key) for key in PROMPT_DEFAULTS.keys()],
        key=lambda item: int(item.get("order_no") or 0),
    )


def update_template_prompt(prompt_key: str, prompt_text: str) -> None:
    ensure_prompt_defaults()
    default = PROMPT_DEFAULTS.get(prompt_key)
    if not default:
        raise RuntimeError(f"unknown prompt_key: {prompt_key}")
    ngql = (
        f"UPDATE VERTEX ON {PROMPT_TAG} {esc_ngql(default['id'])} "
        f"SET {PROMPT_TAG}.prompt_text={esc_ngql(encode_prompt_text(prompt_text))};"
    )
    gql(TEMPLATE_SPACE, ngql)


def list_template_sections() -> list[dict]:
    ngql = (
        "MATCH (t:template)-[:has_version]->(v:template_version)-[:has_section]->(s:template_section) "
        f"WHERE id(t) == {esc_ngql(TEMPLATE_ID)} "
        "RETURN id(s) AS section_id, "
        "s.template_section.section_no AS section_no, "
        "s.template_section.title AS title, "
        "s.template_section.level AS level, "
        "s.template_section.order_no AS order_no, "
        "s.template_section.source_type AS source_type, "
        "s.template_section.kg_field AS kg_field, "
        "s.template_section.fixed_text AS fixed_text, "
        "s.template_section.gen_instruction AS gen_instruction "
        "ORDER BY order_no;"
    )
    rows = parse_table(gql(TEMPLATE_SPACE, ngql)["stdout"])
    sections = [
        {
            "section_id": row.get("section_id", ""),
            "section_no": row.get("section_no", ""),
            "title": row.get("title", ""),
            "level": int(row.get("level") or 0),
            "order_no": int(row.get("order_no") or 0),
            "source_type": row.get("source_type", ""),
            "kg_field": row.get("kg_field", ""),
            "fixed_text": row.get("fixed_text", ""),
            "gen_instruction": row.get("gen_instruction", ""),
        }
        for row in rows
    ]
    return sections


def ensure_template_defaults_snapshot(sections: list[dict]) -> dict[str, dict]:
    if TEMPLATE_DEFAULTS_FILE.exists():
        try:
            saved = json.loads(TEMPLATE_DEFAULTS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                return saved
        except Exception:
            pass

    snapshot = {
        item["section_id"]: {
            "source_type": item["source_type"],
            "fixed_text": item["fixed_text"],
            "gen_instruction": item["gen_instruction"],
        }
        for item in sections
    }
    TEMPLATE_DEFAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DEFAULTS_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def update_template_section(section_id: str, source_type: str, fixed_text: str, gen_instruction: str) -> None:
    ngql = (
        "UPDATE VERTEX ON template_section "
        f"{esc_ngql(section_id)} SET "
        f"template_section.source_type={esc_ngql(source_type)}, "
        f"template_section.fixed_text={esc_ngql(fixed_text)}, "
        f"template_section.gen_instruction={esc_ngql(gen_instruction)};"
    )
    gql(TEMPLATE_SPACE, ngql)


def read_format_review_key() -> str:
    path = Path(FORMAT_REVIEW_PLUGIN_KEY_FILE)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"format review plugin key file is empty: {path}")
    return key


def extract_plugin_text(response: dict) -> tuple[str, str]:
    reasoning = ""
    output = ""
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    output = content
                elif isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "reasoning":
                            reasoning += str(item.get("reasoning", {}).get("content") or "")
                        if item.get("type") == "text":
                            output += str(item.get("text", {}).get("content") or "")
    for node in response.get("responseData", []):
        if node.get("moduleType") == "chatNode":
            if not reasoning:
                reasoning = str(node.get("reasoningText") or "")
    return output.strip(), reasoning.strip()


def run_format_review_sync(prompt: str, content: str, fault_scene: str = "", graph_material: str = "") -> dict:
    background_parts: list[str] = []
    if fault_scene:
        background_parts.append(f"【故障与场景背景】\n{fault_scene}")
    if graph_material:
        background_parts.append(f"【图谱检索背景】\n{graph_material}")
    if background_parts:
        prompt = prompt + "\n\n" + "\n\n".join(background_parts)

    payload = {
        "stream": False,
        "detail": True,
        "variables": {
            "提示词": prompt,
            "当前需求": content,
        },
    }
    req = Request(
        FORMAT_REVIEW_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_format_review_key()}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"format review HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"format review URL error: {exc}")
    output_text, reasoning_text = extract_plugin_text(body)
    return {
        "output_text": output_text,
        "reasoning_text": reasoning_text,
        "raw": body,
    }


def stream_format_review(handler: BaseHTTPRequestHandler, prompt: str, content: str, mode: str, fault_scene: str = "", graph_material: str = "") -> None:
    background_parts: list[str] = []
    if fault_scene:
        background_parts.append(f"【故障与场景背景】\n{fault_scene}")
    if graph_material:
        background_parts.append(f"【图谱检索背景】\n{graph_material}")
    if background_parts:
        prompt = prompt + "\n\n" + "\n\n".join(background_parts)

    payload = {
        "stream": True,
        "detail": True,
        "variables": {
            "提示词": prompt,
            "当前需求": content,
        },
    }
    req = Request(
        FORMAT_REVIEW_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_format_review_key()}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
        },
    )

    send_sse(handler, "quality_status", {"mode": mode, "status": "started"})

    reasoning_text = ""
    output_text = ""
    event_name = ""
    data_lines: list[str] = []
    seen_reasoning = False
    seen_output = False

    def flush_event() -> None:
        nonlocal event_name, data_lines, reasoning_text, output_text, seen_reasoning, seen_output
        if not event_name and not data_lines:
            return
        payload_text = "\n".join(data_lines).strip()
        if event_name == "answer" and payload_text and payload_text != "[DONE]":
            try:
                payload_obj = json.loads(payload_text)
            except Exception:
                payload_obj = {}
            if isinstance(payload_obj, dict):
                choices = payload_obj.get("choices", [])
                if isinstance(choices, list) and choices:
                    delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
                    reasoning_chunk = str(delta.get("reasoning_content") or "")
                    text_chunk = str(delta.get("content") or "")
                    if reasoning_chunk:
                        reasoning_text += reasoning_chunk
                        if not seen_reasoning:
                            seen_reasoning = True
                            send_sse(handler, "quality_status", {"mode": mode, "status": "thinking"})
                        send_sse(handler, "quality_reasoning_chunk", {"mode": mode, "chunk": reasoning_chunk})
                    if text_chunk:
                        output_text += text_chunk
                        if not seen_output:
                            seen_output = True
                            send_sse(handler, "quality_status", {"mode": mode, "status": "generating"})
                        send_sse(handler, "quality_output_chunk", {"mode": mode, "chunk": text_chunk})
        event_name = ""
        data_lines = []

    try:
        with urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if not line.strip():
                    flush_event()
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            flush_event()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"format review HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"format review URL error: {exc}")

    send_sse(
        handler,
        "quality_done",
        {
            "mode": mode,
            "status": "done",
            "output_text": output_text,
            "reasoning_text": reasoning_text,
        },
    )


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
