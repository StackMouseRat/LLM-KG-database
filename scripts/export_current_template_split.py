from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ENDPOINT = "http://127.0.0.1:3000/api/v1/chat/completions"
KEY_FILE = Path("/home/ubuntu/.fastgpt_keys/template_publish_test_api_key")
OUTPUT_DIR = Path("/home/ubuntu/LLM-KG-database/docs/对照试验题库/当前模板导出")


def fetch_template_split() -> dict:
    api_key = KEY_FILE.read_text(encoding="utf-8").strip()
    payload = {"stream": False, "detail": True}
    request = Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def extract_split_result(response: dict) -> dict:
    for node in response.get("responseData", []):
        if not isinstance(node, dict):
            continue
        if node.get("moduleType") != "pluginOutput":
            continue
        plugin_output = node.get("pluginOutput", {})
        if not isinstance(plugin_output, dict):
            continue
        for key in ("切分结果", "章节模板对象", "result"):
            value = plugin_output.get(key)
            if isinstance(value, dict):
                return value
    return {}


def main() -> int:
    response = fetch_template_split()
    split_result = extract_split_result(response)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUTPUT_DIR / "template_split_raw_response.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "template_split_result.json").write_text(
        json.dumps(split_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    chapters = split_result.get("chapters", [])
    if isinstance(chapters, list):
        index_lines = [
            "# 当前模板章节索引",
            "",
            f"- template_id: {split_result.get('template_id', '')}",
            f"- template_name: {split_result.get('template_name', '')}",
            f"- current_version: {split_result.get('current_version', '')}",
            f"- chapter_count: {split_result.get('chapter_count', 0)}",
            "",
        ]
        for i, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            chapter_no = str(chapter.get("chapter_no", i))
            title = str(chapter.get("title", ""))
            text = str(chapter.get("text", ""))
            file_name = f"chapter_{i:02d}_{chapter_no}_{title}.txt".replace("/", "_")
            (OUTPUT_DIR / file_name).write_text(text, encoding="utf-8")
            index_lines.append(f"- {file_name}")
        (OUTPUT_DIR / "README.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    print(f"Saved template split to: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
