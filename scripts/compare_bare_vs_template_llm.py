from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from probe_fastgpt_plugin import extract_text, post_json, read_api_key


DEFAULT_ENDPOINT = "http://127.0.0.1:3000/api/v1/chat/completions"
DEFAULT_OUTPUT_DIR = Path("/home/ubuntu/LLM-KG-database/docs/对照试验题库/轻量实验结果")


def load_questions(question: str | None, question_file: str | None) -> list[str]:
    items: list[str] = []
    if question:
        value = question.strip()
        if value:
            items.append(value)
    if question_file:
        for line in Path(question_file).read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                items.append(value)
    deduped: list[str] = []
    seen = set()
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    if not deduped:
        raise SystemExit("No questions provided. Use --question or --question-file.")
    return deduped


def load_template(template: str | None, template_file: str | None) -> str:
    if template_file:
        raw = Path(template_file).read_text(encoding="utf-8")
    else:
        raw = template or ""

    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("内容来源："):
            continue
        if stripped.startswith("图谱字段："):
            continue
        cleaned_lines.append(line.rstrip())

    return "\n".join(cleaned_lines).strip()


def call_plugin(endpoint: str, api_key: str, prompt: str, template: str, timeout: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stream": False,
        "detail": True,
        "variables": {"提示词": prompt},
    }
    if template:
        payload["variables"]["模板"] = template
    response = post_json(endpoint, api_key, payload, timeout)
    answer_text, reasoning_text, plugin_output = extract_text(response)
    return {
        "payload": payload,
        "answer_text": answer_text,
        "reasoning_text": reasoning_text,
        "plugin_output": plugin_output,
        "raw": response,
    }


def summarize_result(text: str) -> dict[str, Any]:
    stripped = text.strip()
    return {
        "char_count": len(stripped),
        "line_count": len([line for line in stripped.splitlines() if line.strip()]),
        "has_numbered_steps": any(token in stripped for token in ("1.", "2.", "3.", "1、", "2、", "3、")),
        "has_section_judgment": "故障判断" in stripped,
        "has_section_action": any(token in stripped for token in ("处理建议", "处置建议", "应急处置")),
    }


def build_markdown(results: list[dict[str, Any]], template_text: str) -> str:
    lines = [
        "# 轻量实验：裸 LLM vs 带模板 LLM",
        "",
        "## 模板提示词",
        "```text",
        template_text,
        "```",
        "",
    ]

    for item in results:
        lines.extend(
            [
                f"## 题目 {item['index']}",
                item["question"],
                "",
                "### 裸 LLM",
                "```text",
                item["bare"]["answer_text"],
                "```",
                f"- 摘要：{json.dumps(item['bare']['summary'], ensure_ascii=False)}",
                "",
                "### 带模板 LLM",
                "```text",
                item["templated"]["answer_text"],
                "```",
                f"- 摘要：{json.dumps(item['templated']['summary'], ensure_ascii=False)}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight comparison: bare LLM vs templated LLM.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--api-key", help="FastGPT plugin key.")
    parser.add_argument("--api-key-file", help="Path to a file containing the FastGPT plugin key.")
    parser.add_argument("--question", help="Single question to run.")
    parser.add_argument("--question-file", help="UTF-8 text file with one question per line.")
    parser.add_argument("--template", help="Inline template prompt.")
    parser.add_argument("--template-file", help="Template prompt file.")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    api_key = read_api_key(args.api_key, args.api_key_file)
    questions = load_questions(args.question, args.question_file)
    template_text = load_template(args.template, args.template_file)
    if not template_text:
        raise SystemExit("Template is required. Use --template or --template-file.")

    output_root = Path(args.output_dir)
    output_dir = output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        bare = call_plugin(args.endpoint, api_key, question, "", args.timeout)
        bare["summary"] = summarize_result(bare["answer_text"])

        templated = call_plugin(args.endpoint, api_key, question, template_text, args.timeout)
        templated["summary"] = summarize_result(templated["answer_text"])

        results.append(
            {
                "index": index,
                "question": question,
                "bare": bare,
                "templated": templated,
            }
        )

    json_path = output_dir / "comparison_results.json"
    md_path = output_dir / "comparison_results.md"
    json_path.write_text(json.dumps({"template": template_text, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(results, template_text), encoding="utf-8")

    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    for item in results:
        print(f"[Q{item['index']:03d}]")
        print(f"question={item['question']}")
        print(f"bare={item['bare']['answer_text']}")
        print(f"templated={item['templated']['answer_text']}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
