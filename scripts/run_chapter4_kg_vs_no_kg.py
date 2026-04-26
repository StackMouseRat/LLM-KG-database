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
    build_generation_graph_material,
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


DEFAULT_OUTPUT_DIR = Path("/home/ubuntu/LLM-KG-database/docs/对照试验题库/第四章有无图谱对照")
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


def generate_one_variant(
    endpoint: str,
    parallel_key: str,
    timeout: int,
    user_question: str,
    fault_scene: str,
    graph_material: str,
    chapter: dict[str, Any],
) -> dict[str, Any]:
    variables = {
        "用户问题": user_question,
        "故障与场景提取结果": fault_scene,
        "图谱检索方案素材": graph_material,
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
        "generation_variables": variables,
        "output_text": output_text,
        "parallel_raw_response": response,
        "kg_tag_count": output_text.count("[KG]"),
        "gen_tag_count": output_text.count("[GEN]"),
        "fix_tag_count": output_text.count("[FIX]"),
    }


def run_one_question(
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

    with_kg_material = build_generation_graph_material(basic_fields["图谱检索方案素材"])
    no_kg_material = "知识图谱无数据"

    with_kg = generate_one_variant(
        endpoint=endpoint,
        parallel_key=parallel_key,
        timeout=timeout,
        user_question=basic_fields["用户问题"],
        fault_scene=basic_fields["故障与场景提取结果"],
        graph_material=with_kg_material,
        chapter=chapter,
    )
    no_kg = generate_one_variant(
        endpoint=endpoint,
        parallel_key=parallel_key,
        timeout=timeout,
        user_question=basic_fields["用户问题"],
        fault_scene=basic_fields["故障与场景提取结果"],
        graph_material=no_kg_material,
        chapter=chapter,
    )

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
        "with_kg": with_kg,
        "no_kg": no_kg,
    }


def build_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# 第四章有无图谱并排对照",
        "",
        "说明：复用现有 `基本信息获取 -> 模板切片 -> 并行生成` 链路，只比较第四章。",
        "两组差别仅在并行生成阶段：",
        "- 有图谱：传入真实 `图谱检索方案素材`",
        "- 无图谱：传入 `知识图谱无数据`",
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
                "### 有图谱输入摘要",
                "```text",
                item["with_kg"]["generation_variables"]["图谱检索方案素材"],
                "```",
                f"- 标签统计：KG={item['with_kg']['kg_tag_count']} GEN={item['with_kg']['gen_tag_count']} FIX={item['with_kg']['fix_tag_count']}",
                "",
                "### 有图谱输出",
                "```text",
                item["with_kg"]["output_text"],
                "```",
                "",
                "### 无图谱输入摘要",
                "```text",
                item["no_kg"]["generation_variables"]["图谱检索方案素材"],
                "```",
                f"- 标签统计：KG={item['no_kg']['kg_tag_count']} GEN={item['no_kg']['gen_tag_count']} FIX={item['no_kg']['fix_tag_count']}",
                "",
                "### 无图谱输出",
                "```text",
                item["no_kg"]["output_text"],
                "```",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare chapter 4 generation with vs without graph material.")
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

    output_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for question in questions:
        results.append(
            run_one_question(
                endpoint=args.endpoint,
                basic_key=basic_key,
                splitter_key=splitter_key,
                parallel_key=parallel_key,
                timeout=args.timeout,
                question=question,
            )
        )

    (output_dir / "chapter4_kg_vs_no_kg.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "chapter4_kg_vs_no_kg.md").write_text(
        build_markdown(results),
        encoding="utf-8",
    )

    print(f"Saved JSON: {output_dir / 'chapter4_kg_vs_no_kg.json'}")
    print(f"Saved Markdown: {output_dir / 'chapter4_kg_vs_no_kg.md'}")
    for idx, item in enumerate(results, start=1):
        print(f"[Q{idx:03d}] {item['question']}")
        print(
            f"with_kg tags=KG:{item['with_kg']['kg_tag_count']} GEN:{item['with_kg']['gen_tag_count']} FIX:{item['with_kg']['fix_tag_count']}"
        )
        print(
            f"no_kg  tags=KG:{item['no_kg']['kg_tag_count']} GEN:{item['no_kg']['gen_tag_count']} FIX:{item['no_kg']['fix_tag_count']}"
        )
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
