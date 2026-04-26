from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
import json
import os
import random
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import jieba


PORT = int(os.getenv("FRONTEND_PROXY_PORT", "8788"))
AUTH_USERS_RAW = os.getenv("APP_LOGIN_USERS", "")
AUTH_USERNAME = os.getenv("APP_LOGIN_USERNAME", "")
AUTH_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")
AUTH_COOKIE_NAME = os.getenv("APP_LOGIN_COOKIE_NAME", "llmkg_session")
AUTH_SESSION_TTL = int(os.getenv("APP_LOGIN_SESSION_TTL", "86400"))
PIPELINE_SCRIPT = os.getenv("PIPELINE_SCRIPT", "/app/scripts/run_parallel_generation_pipeline.py")
PIPELINE_RUN_DIR = Path(os.getenv("PIPELINE_RUN_DIR", "/app/data/frontend_pipeline_runs"))
KB_PLUGIN_URL = os.getenv("KB_PLUGIN_URL", "http://host.docker.internal:3000/api/v1/chat/completions")
KB_PLUGIN_KEY_FILE = os.getenv(
    "KB_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/knowledge_base_query_plugin_api_key",
)
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
DATASET_MAP = {
    "breaker": {
        "kb_name": "llmkg_breaker",
        "display_name": "高压断路器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a88f",
        "space": "llmkg_breaker",
    },
    "cable": {
        "kb_name": "llmkg_cable",
        "display_name": "电力电缆知识库",
        "dataset_id": "69e8b07a796863b2e4d3a890",
        "space": "llmkg_cable",
    },
    "transformer": {
        "kb_name": "llmkg_transformer",
        "display_name": "变压器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a897",
        "space": "llmkg_transformer",
    },
    "surge_arrester": {
        "kb_name": "llmkg_surge_arrester",
        "display_name": "避雷器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a894",
        "space": "llmkg_surge_arrester",
    },
    "mutual": {
        "kb_name": "llmkg_mutual",
        "display_name": "互感器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a891",
        "space": "llmkg_mutual",
    },
    "optical_cable": {
        "kb_name": "llmkg_optical_cable",
        "display_name": "光缆知识库",
        "dataset_id": "69e8b07a796863b2e4d3a892",
        "space": "llmkg_optical_cable",
    },
    "ring_main_unit": {
        "kb_name": "llmkg_ring_main_unit",
        "display_name": "环网柜知识库",
        "dataset_id": "69e8b07a796863b2e4d3a893",
        "space": "llmkg_ring_main_unit",
    },
}
DEVICE_TO_DATASET_KEY = {
    "高压断路器": "breaker",
    "断路器": "breaker",
    "开关柜": "breaker",
    "变压器": "transformer",
    "主变": "transformer",
    "电力电缆": "cable",
    "电缆": "cable",
    "避雷器": "surge_arrester",
    "互感器": "mutual",
    "电流互感器": "mutual",
    "电压互感器": "mutual",
    "光缆": "optical_cable",
    "环网柜": "ring_main_unit",
}
KB_NAME_TO_DATASET = {v["kb_name"]: v for v in DATASET_MAP.values()}
GRAPH_SPACE_HINTS = [
    {
        "space": "llmkg_breaker",
        "device": "高压断路器",
        "keywords": ["断路器", "高压断路器", "拒动", "拒合", "液压机构", "弹簧机构"],
    },
    {
        "space": "llmkg_transformer",
        "device": "变压器",
        "keywords": ["变压器", "主变", "套管", "瓦斯", "油温", "有载调压", "电抗器"],
    },
    {
        "space": "llmkg_cable",
        "device": "电力电缆",
        "keywords": ["电缆", "电力电缆", "中间接头", "终端头", "电缆沟", "击穿"],
    },
    {
        "space": "llmkg_mutual",
        "device": "互感器",
        "keywords": ["互感器", "电流互感器", "电压互感器", "CT", "TV", "末屏"],
    },
    {
        "space": "llmkg_optical_cable",
        "device": "光缆",
        "keywords": ["光缆", "接续", "接头盒", "通信中断"],
    },
    {
        "space": "llmkg_ring_main_unit",
        "device": "环网柜",
        "keywords": ["环网柜", "开闭器"],
    },
    {
        "space": "llmkg_surge_arrester",
        "device": "避雷器",
        "keywords": ["避雷器", "阀片", "污闪", "侧闪", "闪络"],
    },
    {
        "space": "llmkg_tower",
        "device": "杆塔",
        "keywords": ["杆塔", "塔位", "基础冲刷", "倾斜"],
    },
    {
        "space": "llmkg_transmission_line",
        "device": "输电线路",
        "keywords": [
            "输电线路",
            "导线",
            "雷击跳闸",
            "雷击闪络",
            "感应雷",
            "反击雷",
            "绕击雷",
            "避雷线",
            "覆冰",
            "覆冰过荷载",
            "脱冰跳跃",
            "污闪",
            "积污污闪",
            "风害",
            "风偏闪络",
            "舞动",
            "鸟害",
            "外力破坏",
            "吊车碰线",
            "山火",
            "烟火短路",
        ],
    },
]
TRACE_EDGE_LABELS = {
    "has_fault_category": "发生",
    "contains": "包含",
    "caused_by": "故障原因",
    "has_symptom": "故障现象",
    "handled_by": "应对措施",
    "results_in": "故障后果",
    "has_risk": "安全风险",
    "needs_resource": "应急资源",
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


def parse_fault_scene(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def infer_dataset_with_context(question: str, fault_scene: str = "", graph_material: str = "", kb_name: str = "") -> dict | None:
    if kb_name and kb_name in KB_NAME_TO_DATASET:
        return KB_NAME_TO_DATASET[kb_name]

    parsed = parse_fault_scene(fault_scene)
    device_name = str(parsed.get("故障对象") or "").strip()
    if device_name and device_name != "未明确":
        dataset_key = DEVICE_TO_DATASET_KEY.get(device_name)
        if dataset_key and dataset_key in DATASET_MAP:
            return DATASET_MAP[dataset_key]

    text_parts = [question]
    text_parts.append(str(fault_scene or ""))
    text_parts.append(str(graph_material or ""))
    for key in ("故障二级节点", "事件场景", "关键处置要求"):
        value = parsed.get(key)
        if value:
            text_parts.append(str(value))
    haystack = " ".join(text_parts)
    for dataset_key, keywords in [
        ("breaker", ["断路器", "开关柜", "拒合", "拒动", "跳闸线圈", "液压机构", "弹簧机构"]),
        ("cable", ["电缆", "电缆沟", "中间接头", "终端头", "绝缘劣化", "击穿"]),
        ("transformer", ["变压器", "主变", "瓦斯", "有载调压", "套管", "油温", "电抗器"]),
        ("surge_arrester", ["避雷器", "阀片", "侧闪", "闪络", "脱落接地", "未有效动作"]),
        ("mutual", ["互感器", "CT", "TV", "末屏"]),
        ("optical_cable", ["光缆", "接续", "接头盒", "通信中断"]),
        ("ring_main_unit", ["环网柜", "开闭器"]),
    ]:
        if any(word in haystack for word in keywords):
            return DATASET_MAP[dataset_key]
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
        str(fields.get("知识库名") or ""),
    )


def infer_graph_space_with_context(question: str, fault_scene: str = "", graph_material: str = "") -> dict | None:
    text_parts = [question, str(fault_scene or ""), str(graph_material or "")]
    parsed = parse_fault_scene(fault_scene)
    for key in ("故障对象", "故障二级节点", "事件场景", "关键处置要求", "特殊约束"):
        value = parsed.get(key)
        if value:
            text_parts.append(str(value))

    haystack = " ".join(text_parts)
    for item in GRAPH_SPACE_HINTS:
        if any(word in haystack for word in item["keywords"]):
            return {"space": item["space"], "device": item["device"]}
    return None


def first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_fault_names(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                result.append(candidate)
        elif isinstance(value, list):
            for item in value:
                candidate = str(item or "").strip()
                if candidate:
                    result.append(candidate)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in result:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def wrap_fault_l2_label(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value

    words = [str(item).strip() for item in jieba.lcut(value) if str(item).strip()]
    if len(words) <= 1:
        return value

    total_length = 0
    split_index = -1
    for index, word in enumerate(words):
        total_length += len(word)
        if total_length > 3:
            split_index = index
            break

    if split_index < 0 or split_index >= len(words) - 1:
        return value

    left = "".join(words[: split_index + 1])
    right = "".join(words[split_index + 1 :])
    if len(right) > 5:
        right = wrap_fault_l2_label(right)
    return left + "\n" + right


def extract_trace_focus_fields(
    question: str,
    fault_scene: str = "",
    graph_material: str = "",
    device_hint: str = "",
    fault_hint: str = "",
) -> dict:
    parsed = parse_fault_scene(fault_scene)
    graph_material_parsed = parse_fault_scene(graph_material)
    explicit_space = first_non_empty(
        graph_material_parsed.get("设备表"),
        parsed.get("设备表"),
        graph_material_parsed.get("space"),
        parsed.get("space"),
    )

    device_name = first_non_empty(
        device_hint,
        parsed.get("故障对象"),
        parsed.get("设备"),
        parsed.get("设备名称"),
    )
    fault_names = normalize_fault_names(
        parsed.get("主故障二级节点"),
        parsed.get("故障二级节点"),
        graph_material_parsed.get("主故障二级节点"),
        graph_material_parsed.get("故障二级节点"),
    )
    fault_name = first_non_empty(
        fault_hint,
        parsed.get("主故障二级节点"),
        parsed.get("当前故障分析"),
        parsed.get("二级故障名称"),
        graph_material_parsed.get("主故障二级节点"),
    )
    if not fault_name and fault_names:
        fault_name = fault_names[0]

    if not fault_name:
        for text in (fault_scene, graph_material, question):
            if not isinstance(text, str) or not text.strip():
                continue
            for pattern in (
                r"(?:故障二级节点|当前二级故障|当前故障分析)[：:\"]+\s*\"?([^\"，,\n]+?故障)\"?",
                r"(?:匹配故障|当前故障)[：:\"]+\s*\"?([^\"，,\n]+?故障)\"?",
            ):
                matched = re.search(pattern, text)
                if matched:
                    fault_name = matched.group(1).strip()
                    break
            if fault_name:
                break

    graph_space = {"space": explicit_space, "device": ""} if explicit_space else infer_graph_space_with_context(question, fault_scene, graph_material)
    return {
        "space": graph_space.get("space") if graph_space else "",
        "device": device_name or (graph_space.get("device") if graph_space else ""),
        "fault": fault_name,
        "faults": fault_names or ([fault_name] if fault_name else []),
    }


def query_rows(space: str, ngql: str) -> list[dict[str, str]]:
    return parse_table(gql(space, ngql)["stdout"])


def get_trace_candidate_spaces(preferred_space: str = "") -> list[str]:
    spaces: list[str] = []
    if preferred_space:
        spaces.append(preferred_space)
    for item in GRAPH_SPACE_HINTS:
        space = str(item.get("space") or "").strip()
        if space and space not in spaces:
            spaces.append(space)
    return spaces


def add_trace_node(
    nodes: dict[str, dict],
    node_id: str,
    label: str,
    node_type: str,
    desc: str = "",
    is_focus: bool = False,
    is_hit: bool = False,
) -> None:
    if not node_id:
        return
    existing = nodes.get(node_id)
    wrapped_label = wrap_fault_l2_label(label) if node_type in {"fault_l1", "fault_l2"} else ""
    payload = {
        "id": node_id,
        "label": label or node_id,
        "type": node_type,
        "desc": desc,
    }
    if is_focus:
        payload["isFocus"] = True
    if is_hit:
        payload["isHit"] = True
    if wrapped_label:
        payload["wrappedLabel"] = wrapped_label
    if existing:
        if is_focus:
            existing["isFocus"] = True
        if is_hit:
            existing["isHit"] = True
        if wrapped_label and not existing.get("wrappedLabel"):
            existing["wrappedLabel"] = wrapped_label
        if desc and not existing.get("desc"):
            existing["desc"] = desc
        return
    nodes[node_id] = payload


def add_trace_edge(edges: dict[str, dict], source: str, target: str, label: str, is_hit: bool = False) -> None:
    if not source or not target:
        return
    edge_id = f"{source}->{label}->{target}"
    display_label = TRACE_EDGE_LABELS.get(label, label)
    edge = edges.setdefault(
        edge_id,
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": display_label,
        },
    )
    if is_hit:
        edge["isHit"] = True


def build_trace_subgraph(
    space: str,
    fault_name: str,
    device_name: str = "",
    hit_fault_names: list[str] | None = None,
) -> dict:
    if not fault_name:
        raise RuntimeError("trace fault name is empty")

    upstream_ngql = (
        "MATCH (r:root_node)-[:has_fault_category]->(l1:fault_l1)-[:contains]->(l2:fault_l2) "
        "RETURN id(r) AS root_id, r.root_node.name AS root_name, r.root_node.node_desc AS root_desc, "
        "id(l1) AS l1_id, l1.fault_l1.name AS l1_name, l1.fault_l1.node_desc AS l1_desc, "
        "id(l2) AS l2_id, l2.fault_l2.name AS l2_name, l2.fault_l2.node_desc AS l2_desc;"
    )
    normalized_fault = fault_name.strip()
    normalized_hit_faults = normalize_fault_names(hit_fault_names or [], normalized_fault)
    normalized_hit_fault_set = set(normalized_hit_faults)

    effective_space = ""
    upstream_rows: list[dict[str, str]] = []
    filtered_rows: list[dict[str, str]] = []
    last_error = ""

    for candidate_space in get_trace_candidate_spaces(space):
        try:
            candidate_rows = query_rows(candidate_space, upstream_ngql)
        except Exception as exc:
            last_error = str(exc)
            continue
        if not candidate_rows:
            continue

        candidate_filtered_rows = [
            item for item in candidate_rows
            if str(item.get("l2_name") or "").strip() == normalized_fault
        ]
        if device_name:
            candidate_filtered_rows = [
                item for item in candidate_filtered_rows
                if device_name in str(item.get("root_name") or "")
            ] or candidate_filtered_rows
        if not candidate_filtered_rows:
            candidate_filtered_rows = [
                item for item in candidate_rows
                if normalized_fault in str(item.get("l2_name") or "")
            ]
            if device_name:
                candidate_filtered_rows = [
                    item for item in candidate_filtered_rows
                    if device_name in str(item.get("root_name") or "")
                ] or candidate_filtered_rows

        if candidate_filtered_rows:
            effective_space = candidate_space
            upstream_rows = candidate_rows
            filtered_rows = candidate_filtered_rows
            break

    if not filtered_rows:
        if last_error:
            raise RuntimeError(f"trace root path not found for fault: {fault_name}; last error: {last_error}")
        raise RuntimeError(f"trace root path not found for fault: {fault_name}")

    row = filtered_rows[0]
    root_id = str(row.get("root_id") or "")
    l1_id = str(row.get("l1_id") or "")
    l2_id = str(row.get("l2_id") or "")

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    root_name = str(row.get("root_name") or device_name or "设备根节点")

    root_filter_rows = [item for item in upstream_rows if str(item.get("root_id") or "") == root_id]
    hit_rows = [
        item
        for item in root_filter_rows
        if str(item.get("l2_name") or "").strip() in normalized_hit_fault_set
    ]
    if not hit_rows:
        hit_rows = [row]
    hit_root_ids = {str(item.get("root_id") or "") for item in hit_rows}
    hit_l1_ids = {str(item.get("l1_id") or "") for item in hit_rows}
    hit_l2_ids = {str(item.get("l2_id") or "") for item in hit_rows}
    hit_node_ids = {root_id, *hit_root_ids, *hit_l1_ids, *hit_l2_ids}
    hit_edge_keys = {
        f"{str(item.get('root_id') or '')}->has_fault_category->{str(item.get('l1_id') or '')}"
        for item in hit_rows
    }
    hit_edge_keys.update(
        f"{str(item.get('l1_id') or '')}->contains->{str(item.get('l2_id') or '')}"
        for item in hit_rows
    )
    for item in root_filter_rows:
        item_root_id = str(item.get("root_id") or "")
        item_l1_id = str(item.get("l1_id") or "")
        item_l2_id = str(item.get("l2_id") or "")
        add_trace_node(
            nodes,
            item_root_id,
            str(item.get("root_name") or root_name),
            "root_node",
            str(item.get("root_desc") or ""),
            is_hit=item_root_id in hit_node_ids,
        )
        add_trace_node(
            nodes,
            item_l1_id,
            str(item.get("l1_name") or "一级故障"),
            "fault_l1",
            str(item.get("l1_desc") or ""),
            is_hit=item_l1_id in hit_node_ids,
        )
        add_trace_node(
            nodes,
            item_l2_id,
            str(item.get("l2_name") or "二级故障"),
            "fault_l2",
            str(item.get("l2_desc") or ""),
            is_focus=item_l2_id == l2_id,
            is_hit=item_l2_id in hit_node_ids,
        )
        add_trace_edge(
            edges,
            item_root_id,
            item_l1_id,
            "has_fault_category",
            is_hit=f"{item_root_id}->has_fault_category->{item_l1_id}" in hit_edge_keys,
        )
        add_trace_edge(
            edges,
            item_l1_id,
            item_l2_id,
            "contains",
            is_hit=f"{item_l1_id}->contains->{item_l2_id}" in hit_edge_keys,
        )

    cause_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, "
            "c.fault_cause.name AS cause_name, c.fault_cause.node_desc AS cause_desc;"
        ),
    )
    for cause in cause_rows:
        current_l2_id = str(cause.get("l2_id") or "")
        cause_id = str(cause.get("cause_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(cause_id)
          hit_edge_keys.add(f"{current_l2_id}->caused_by->{cause_id}")
        add_trace_node(
            nodes,
            cause_id,
            str(cause.get("cause_name") or "故障原因"),
            "fault_cause",
            str(cause.get("cause_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, current_l2_id, cause_id, "caused_by", is_hit=is_hit)

    symptom_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause)-[:has_symptom]->(s:fault_symptom) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, id(s) AS symptom_id, "
            "s.fault_symptom.name AS symptom_name, s.fault_symptom.node_desc AS symptom_desc;"
        ),
    )
    for symptom in symptom_rows:
        current_l2_id = str(symptom.get("l2_id") or "")
        cause_id = str(symptom.get("cause_id") or "")
        symptom_id = str(symptom.get("symptom_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(symptom_id)
          hit_edge_keys.add(f"{cause_id}->has_symptom->{symptom_id}")
        add_trace_node(
            nodes,
            symptom_id,
            str(symptom.get("symptom_name") or "故障现象"),
            "fault_symptom",
            str(symptom.get("symptom_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, cause_id, symptom_id, "has_symptom", is_hit=is_hit)

    consequence_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause)-[:results_in]->(co:fault_consequence) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, id(co) AS consequence_id, "
            "co.fault_consequence.name AS consequence_name, co.fault_consequence.node_desc AS consequence_desc;"
        ),
    )
    for consequence in consequence_rows:
        current_l2_id = str(consequence.get("l2_id") or "")
        cause_id = str(consequence.get("cause_id") or "")
        consequence_id = str(consequence.get("consequence_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(consequence_id)
          hit_edge_keys.add(f"{cause_id}->results_in->{consequence_id}")
        add_trace_node(
            nodes,
            consequence_id,
            str(consequence.get("consequence_name") or "故障后果"),
            "fault_consequence",
            str(consequence.get("consequence_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, cause_id, consequence_id, "results_in", is_hit=is_hit)

    measure_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, "
            "m.response_measure.name AS measure_name, m.response_measure.node_desc AS measure_desc;"
        ),
    )
    for measure in measure_rows:
        current_l2_id = str(measure.get("l2_id") or "")
        measure_id = str(measure.get("measure_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(measure_id)
          hit_edge_keys.add(f"{current_l2_id}->handled_by->{measure_id}")
        add_trace_node(
            nodes,
            measure_id,
            str(measure.get("measure_name") or "应对措施"),
            "response_measure",
            str(measure.get("measure_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, current_l2_id, measure_id, "handled_by", is_hit=is_hit)

    risk_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure)-[:has_risk]->(r:safety_risk) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, id(r) AS risk_id, "
            "r.safety_risk.name AS risk_name, r.safety_risk.node_desc AS risk_desc;"
        ),
    )
    for risk in risk_rows:
        current_l2_id = str(risk.get("l2_id") or "")
        measure_id = str(risk.get("measure_id") or "")
        risk_id = str(risk.get("risk_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(risk_id)
          hit_edge_keys.add(f"{measure_id}->has_risk->{risk_id}")
        add_trace_node(
            nodes,
            risk_id,
            str(risk.get("risk_name") or "安全风险"),
            "safety_risk",
            str(risk.get("risk_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, measure_id, risk_id, "has_risk", is_hit=is_hit)

    resource_rows = query_rows(
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure)-[:needs_resource]->(er:emergency_resource) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, id(er) AS resource_id, "
            "er.emergency_resource.name AS resource_name, er.emergency_resource.node_desc AS resource_desc;"
        ),
    )
    for resource in resource_rows:
        current_l2_id = str(resource.get("l2_id") or "")
        measure_id = str(resource.get("measure_id") or "")
        resource_id = str(resource.get("resource_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
          hit_node_ids.add(resource_id)
          hit_edge_keys.add(f"{measure_id}->needs_resource->{resource_id}")
        add_trace_node(
            nodes,
            resource_id,
            str(resource.get("resource_name") or "应急资源"),
            "emergency_resource",
            str(resource.get("resource_desc") or ""),
            is_hit=is_hit,
        )
        add_trace_edge(edges, measure_id, resource_id, "needs_resource", is_hit=is_hit)

    for node_id in hit_node_ids:
        if node_id in nodes:
            nodes[node_id]["isHit"] = True

    return {
        "device": str(row.get("root_name") or device_name or ""),
        "fault": str(row.get("l2_name") or fault_name),
        "graph": {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        },
        "rawDetail": {
            "space": effective_space,
            "deviceHint": device_name,
            "faultHint": fault_name,
            "faultHints": normalized_hit_faults,
            "focusPath": [root_id, l1_id, l2_id],
        },
    }


def read_plugin_key() -> str:
    path = Path(KB_PLUGIN_KEY_FILE)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"plugin key file is empty: {path}")
    return key


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
                score_values: dict[str, float] = {}
                for score in item.get("score", []):
                    if isinstance(score, dict) and isinstance(score.get("value"), (int, float)):
                        score_parts.append(f"{score.get('type', 'score')}={score['value']:.3f}")
                        score_values[str(score.get("type", ""))] = float(score["value"])
                cards.append(
                    {
                        "id": item.get("id"),
                        "title": str(item.get("sourceName") or "未命名案例"),
                        "kbId": str(item.get("datasetId") or ""),
                        "docId": str(item.get("collectionId") or ""),
                        "relevance": " / ".join(score_parts),
                        "excerpt": str(item.get("q") or item.get("a") or ""),
                        "_sort_score": score_values.get("reRank") or score_values.get("embedding") or score_values.get("rrf") or 0,
                    }
                )

    cards.sort(key=lambda c: c.pop("_sort_score", 0), reverse=True)

    if not cards:
        raise RuntimeError("case search returned no cards")

    return {
        "enabled": True,
        "status": "done",
        "kb_name": dataset["kb_name"],
        "display_name": dataset.get("display_name", dataset["kb_name"]),
        "dataset_id": dataset["dataset_id"],
        "query_question": question,
        "cards": cards,
    }


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


def stream_pipeline(
    question: str,
    handler: BaseHTTPRequestHandler,
    enable_case_search: bool = False,
    enable_multi_fault_search: bool = False,
) -> None:
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
    if enable_multi_fault_search:
        command.append("--multi-fault")
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
                str(basic_info.get("kbName") or ""),
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
