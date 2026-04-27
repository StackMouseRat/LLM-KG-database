from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def count_rows(space: str, ngql: str) -> int:
    rows = parse_table(gql(space, ngql)["stdout"])
    if not rows:
        return 0
    value = next(iter(rows[0].values()))
    try:
        return int(str(value))
    except Exception:
        return 0


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
    return [
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
