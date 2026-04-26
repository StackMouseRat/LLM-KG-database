#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from run_parallel_generation_pipeline import (
    DEFAULT_BASE_URL,
    DEFAULT_BASIC_KEY,
    DEFAULT_PARALLEL_KEY,
    DEFAULT_SPLITTER_KEY,
    call_plugin,
    extract_basic_fields,
    extract_chapters,
    extract_parallel_text,
    extract_plugin_output,
    extract_split_result,
    post_chat_stream,
    read_key,
    sanitize_generated_output,
)


DEFAULT_OUTPUT_DIR = Path("/home/ubuntu/LLM-KG-database/docs/对照试验题库/第四章去图谱实验")
DEFAULT_QUESTIONS = [
    "某110kV断路器故障时保护已发令，但现场未见分闸动作，请生成应急处置方案。",
    "35kV母线TV熔丝反复熔断，二次电压异常，请给出应急处置方案。",
    "雨后某220kV避雷器出现放电痕迹并最终损坏，请生成应急处置方案。",
]


def load_questions(question_file: str | None) -> list[str]:
    if not question_file:
        return DEFAULT_QUESTIONS

    items: list[str] = []
    for line in Path(question_file).read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            items.append(value)
    if not items:
        raise SystemExit("Question file is empty.")
    return items


def select_chapter_four(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    for chapter in chapters:
        if str(chapter.get("chapter_no")) == "4":
            return chapter
    raise RuntimeError("Chapter 4 template not found in template splitter output.")


def generate_chapter_four_no_kg(
    endpoint: str,
    basic_key: str,
    splitter_key: str,
    parallel_key: str,
    timeout: int,
    question: str,
) -> dict[str, Any]:
    basic_response, basic_elapsed = call_plugin(
        endpoint=endpoint,
        api_key=basic_key,
        variables={"用户问题": question},
        timeout=timeout,
    )
    basic_output = extract_plugin_output(basic_response)
    basic_fields = extract_basic_fields(basic_output, question)

    splitter_response, splitter_elapsed = call_plugin(
        endpoint=endpoint,
        api_key=splitter_key,
        variables=None,
        timeout=timeout,
    )
    splitter_output = extract_plugin_output(splitter_response)
    split_result = extract_split_result(splitter_output)
    chapter = select_chapter_four(extract_chapters(split_result))

    variables = {
        "用户问题": basic_fields["用户问题"],
        "故障与场景提取结果": basic_fields["故障与场景提取结果"],
        "图谱检索方案素材": "知识图谱无数据",
        "模板": chapter["template_text"],
    }

    response = post_chat_stream(
        endpoint,
        parallel_key,
        {"stream": True, "detail": True, "variables": variables},
        timeout,
    )

    output_text = sanitize_generated_output(extract_parallel_text(response))
    return {
        "question": question,
        "basic_elapsed_sec": basic_elapsed,
        "splitter_elapsed_sec": splitter_elapsed,
        "basic_fields": basic_fields,
        "template_split": {
            "template_id": str(split_result.get("template_id") or ""),
            "template_name": str(split_result.get("template_name") or ""),
            "current_version": str(split_result.get("current_version") or ""),
        },
        "chapter": {
            "chapter_no": chapter["chapter_no"],
            "title": chapter["title"],
            "section_count": chapter["section_count"],
            "template_text": chapter["template_text"],
        },
        "generation_variables": variables,
        "output_text": output_text,
        "parallel_raw_response": response,
    }


def build_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# 第四章去图谱实验",
        "",
        "说明：本实验复用现有 `基本信息获取 -> 模板切片 -> 并行生成` 链路，",
        "仅在并行生成阶段将 `图谱检索方案素材` 强制改为 `知识图谱无数据`。",
        "",
    ]
    for idx, item in enumerate(results, start=1):
        lines.extend(
            [
                f"## Q{idx:03d}",
                item["question"],
                "",
                "### 章节模板",
                "```text",
                item["chapter"]["template_text"],
                "```",
                "",
                "### 传入并行生成变量",
                "```json",
                json.dumps(item["generation_variables"], ensure_ascii=False, indent=2),
                "```",
                "",
                "### 输出",
                "```text",
                item["output_text"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run chapter 4 generation with graph material disabled.")
    parser.add_argument("--endpoint", default=DEFAULT_BASE_URL)
    parser.add_argument("--basic-key-file", type=Path, default=DEFAULT_BASIC_KEY)
    parser.add_argument("--splitter-key-file", type=Path, default=DEFAULT_SPLITTER_KEY)
    parser.add_argument("--parallel-key-file", type=Path, default=DEFAULT_PARALLEL_KEY)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--question-file", help="Optional UTF-8 file with one question per line.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    basic_key = read_key(args.basic_key_file)
    splitter_key = read_key(args.splitter_key_file)
    parallel_key = read_key(args.parallel_key_file)
    questions = load_questions(args.question_file)

    timestamp_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for question in questions:
        results.append(
            generate_chapter_four_no_kg(
                endpoint=args.endpoint,
                basic_key=basic_key,
                splitter_key=splitter_key,
                parallel_key=parallel_key,
                timeout=args.timeout,
                question=question,
            )
        )

    (timestamp_dir / "chapter4_no_kg_results.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (timestamp_dir / "chapter4_no_kg_results.md").write_text(
        build_markdown(results),
        encoding="utf-8",
    )

    print(f"Saved JSON: {timestamp_dir / 'chapter4_no_kg_results.json'}")
    print(f"Saved Markdown: {timestamp_dir / 'chapter4_no_kg_results.md'}")
    for idx, item in enumerate(results, start=1):
        print(f"[Q{idx:03d}] {item['question']}")
        preview = item["output_text"].splitlines()[0] if item["output_text"] else ""
        print(preview)
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
