from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import random
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PORT = int(os.getenv("FRONTEND_PROXY_PORT", "8788"))
PIPELINE_SCRIPT = os.getenv("PIPELINE_SCRIPT", "/app/scripts/run_parallel_generation_pipeline.py")
PIPELINE_RUN_DIR = Path(os.getenv("PIPELINE_RUN_DIR", "/app/data/frontend_pipeline_runs"))
KB_PLUGIN_URL = os.getenv("KB_PLUGIN_URL", "http://host.docker.internal:3000/api/v1/chat/completions")
KB_PLUGIN_KEY_FILE = os.getenv(
    "KB_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/knowledge_base_query_plugin_api_key",
)
TEMPLATE_GRAPH_URL = os.getenv("TEMPLATE_GRAPH_URL", "http://host.docker.internal:8787/graph/query")
TEMPLATE_SPACE = os.getenv("TEMPLATE_SPACE", "llmkg_templates")
TEMPLATE_ID = os.getenv("TEMPLATE_ID", "tpl_default_emergency")
TEMPLATE_DEFAULTS_FILE = Path(
    os.getenv("TEMPLATE_DEFAULTS_FILE", "/app/data/template_defaults_snapshot.json")
)
DATASET_MAP = {
    "breaker": {
        "kb_name": "llmkg_breaker",
        "dataset_id": "69e8b07a796863b2e4d3a88f",
    },
    "cable": {
        "kb_name": "llmkg_cable",
        "dataset_id": "69e8b07a796863b2e4d3a890",
    },
    "transformer": {
        "kb_name": "llmkg_transformer",
        "dataset_id": "69e8b07a796863b2e4d3a897",
    },
    "surge_arrester": {
        "kb_name": "llmkg_surge_arrester",
        "dataset_id": "69e8b07a796863b2e4d3a894",
    },
}


def send_sse(handler: BaseHTTPRequestHandler, event: str, data: object) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    handler.wfile.write(f"event: {event}\n".encode("utf-8"))
    handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
    handler.wfile.flush()


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


def parse_fault_scene(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def infer_dataset_with_context(question: str, fault_scene: str = "", graph_material: str = "") -> dict | None:
    text_parts = [question]
    text_parts.append(str(fault_scene or ""))
    text_parts.append(str(graph_material or ""))
    parsed = parse_fault_scene(fault_scene)
    for key in ("故障对象", "故障二级节点", "事件场景", "关键处置要求"):
        value = parsed.get(key)
        if value:
            text_parts.append(str(value))

    haystack = " ".join(text_parts)
    if any(word in haystack for word in ["断路器", "开关柜", "拒合", "拒动", "跳闸线圈", "液压机构", "弹簧机构"]):
        return DATASET_MAP["breaker"]
    if any(word in haystack for word in ["电缆", "电缆沟", "中间接头", "终端头", "绝缘劣化", "击穿"]):
        return DATASET_MAP["cable"]
    if any(word in haystack for word in ["变压器", "主变", "瓦斯", "有载调压", "套管", "油温", "电抗器"]):
        return DATASET_MAP["transformer"]
    if any(word in haystack for word in ["避雷器", "阀片", "侧闪", "闪络", "雷击", "脱落接地", "未有效动作"]):
        return DATASET_MAP["surge_arrester"]
    return None


def infer_dataset(question: str, pipeline_result: dict | None = None) -> dict | None:
    if not pipeline_result:
        return infer_dataset_with_context(question)

    basic_info = pipeline_result.get("basic_info", {}) or {}
    fields = basic_info.get("fields", {}) or {}
    return infer_dataset_with_context(
        question,
        str(fields.get("故障与场景提取结果") or ""),
        str(fields.get("图谱检索方案素材") or ""),
    )


def read_plugin_key() -> str:
    path = Path(KB_PLUGIN_KEY_FILE)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"plugin key file is empty: {path}")
    return key


def run_case_search(question: str, dataset: dict) -> dict:
    payload = {
        "stream": False,
        "detail": True,
        "variables": {
            "当前识别设备": [{"datasetId": dataset["dataset_id"]}],
            "用户问题": question,
        },
    }
    req = Request(
        KB_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_plugin_key()}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"case search HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"case search URL error: {exc}")

    plugin_output = None
    for node in body.get("responseData", []):
        if node.get("moduleType") == "pluginOutput":
            plugin_output = node.get("pluginOutput", {})
    cards: list[dict] = []
    if isinstance(plugin_output, dict):
        raw_cards = plugin_output.get("ICBM")
        if isinstance(raw_cards, list):
            for item in raw_cards[:6]:
                if not isinstance(item, dict):
                    continue
                score_parts = []
                for score in item.get("score", []):
                    if isinstance(score, dict) and isinstance(score.get("value"), (int, float)):
                        score_parts.append(f"{score.get('type', 'score')}={score['value']:.3f}")
                cards.append(
                    {
                        "id": item.get("id"),
                        "title": str(item.get("sourceName") or "未命名案例"),
                        "kbId": str(item.get("datasetId") or ""),
                        "docId": str(item.get("collectionId") or ""),
                        "relevance": " / ".join(score_parts),
                        "excerpt": str(item.get("q") or item.get("a") or ""),
                    }
                )

    if not cards:
        raise RuntimeError("case search returned no cards")

    return {
        "enabled": True,
        "status": "done",
        "kb_name": dataset["kb_name"],
        "dataset_id": dataset["dataset_id"],
        "query_question": question,
        "cards": cards,
    }


def run_pipeline_process(question: str) -> dict:
    base_dir = make_run_dir()
    command = [
        sys.executable,
        PIPELINE_SCRIPT,
        "--question",
        question,
        "--output-dir",
        str(base_dir),
    ]
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


def run_pipeline_sync(question: str, enable_case_search: bool = False) -> dict:
    dataset = infer_dataset_with_context(question) if enable_case_search else None
    if enable_case_search and dataset is not None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            pipeline_future = executor.submit(run_pipeline_process, question)
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

    result = run_pipeline_process(question)
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


def stream_pipeline(question: str, handler: BaseHTTPRequestHandler, enable_case_search: bool = False) -> None:
    base_dir = make_run_dir()
    command = [
        sys.executable,
        PIPELINE_SCRIPT,
        "--question",
        question,
        "--output-dir",
        str(base_dir),
        "--stream-events",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )

    error_lines: list[str] = []
    final_result: dict | None = None
    send_lock = threading.Lock()
    case_thread: threading.Thread | None = None
    case_started = False
    case_finished = not enable_case_search

    def safe_send(event: str, data: object) -> bool:
        try:
            with send_lock:
                send_sse(handler, event, data)
            return True
        except BrokenPipeError:
            return False

    def start_case_search(dataset: dict) -> None:
        nonlocal case_thread, case_started, case_finished
        case_started = True
        case_finished = False

        def worker() -> None:
            nonlocal case_finished
            if not safe_send(
                "case_search_started",
                {
                    "enabled": True,
                    "status": "running",
                    "kb_name": dataset["kb_name"],
                    "dataset_id": dataset["dataset_id"],
                    "query_question": question,
                },
            ):
                return
            try:
                case_result = run_case_search(question, dataset)
                safe_send("case_search_done", case_result)
            except Exception as exc:
                safe_send(
                    "case_search_error",
                    {
                        "enabled": True,
                        "status": "error",
                        "kb_name": dataset["kb_name"],
                        "dataset_id": dataset["dataset_id"],
                        "query_question": question,
                        "error": str(exc),
                    },
                )
            finally:
                case_finished = True

        case_thread = threading.Thread(target=worker, daemon=True)
        case_thread.start()

    initial_dataset = infer_dataset_with_context(question) if enable_case_search else None
    if enable_case_search and initial_dataset is not None:
        start_case_search(initial_dataset)

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            error_lines.append(line)
            try:
                send_sse(handler, "pipeline_log", {"text": line})
            except BrokenPipeError:
                process.kill()
                return
            continue

        event = payload.get("event")
        if not isinstance(event, str):
            continue
        data = payload.get("data", {})
        if event == "pipeline_done" and isinstance(data, dict):
            final_result = data
        if event == "basic_info_done" and enable_case_search and not case_started and isinstance(data, dict):
            basic_info = data.get("basicInfo", {}) if isinstance(data, dict) else {}
            dataset = infer_dataset_with_context(
                question,
                str(basic_info.get("faultScene") or ""),
                str(basic_info.get("graphMaterial") or ""),
            )
            if dataset is not None:
                start_case_search(dataset)
        if not safe_send(event, data):
            process.kill()
            return

    return_code = process.wait()
    if return_code != 0:
        message = "\n".join(error_lines).strip() or f"pipeline exited with code {return_code}"
        try:
            send_sse(handler, "pipeline_error", {"message": message})
        except BrokenPipeError:
            return
    elif enable_case_search and not case_started:
        dataset = infer_dataset(question, final_result)
        if dataset is None:
            if not safe_send(
                "case_search_error",
                {
                    "enabled": True,
                    "status": "skipped",
                    "query_question": question,
                    "error": "未命中已建立知识库对应设备",
                },
            ):
                return
        else:
            start_case_search(dataset)

    if case_thread is not None:
        case_thread.join(timeout=120)

    try:
        with send_lock:
            send_sse(handler, "close", {})
    except BrokenPipeError:
        return


class Handler(BaseHTTPRequestHandler):
    server_version = "FrontendProxy/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path != "/api/template/sections":
            self.send_response(404)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "not found"}).encode("utf-8"))
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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"message": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path in ("/api/template/section/save", "/api/template/section/reset"):
            try:
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
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as exc:
                payload = json.dumps({"message": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

        if self.path not in ("/api/plan/generate", "/api/pipeline/run"):
            self.send_response(404)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"message": "not found"}).encode("utf-8"))
            return

        try:
            body = self._read_json_body()
            question = str(body.get("question") or "").strip()
            enable_case_search = bool(body.get("enableCaseSearch"))
            if not question:
                self.send_response(400)
                self._send_common_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"message": "question is required"}).encode("utf-8"))
                return

            if not body.get("stream"):
                result = run_pipeline_sync(question, enable_case_search=enable_case_search)
                payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            stream_pipeline(question, self, enable_case_search=enable_case_search)
        except Exception as exc:
            payload = json.dumps({"message": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self._send_common_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


def main() -> None:
    PIPELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"frontend proxy listening on {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
