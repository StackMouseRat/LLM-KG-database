#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_parallel_generation_pipeline as pipeline


DEVICE_KEYWORDS = [
    ("断路器", "高压断路器", "llmkg_breaker"),
    ("开关", "高压断路器", "llmkg_breaker"),
    ("电缆", "电力电缆", "llmkg_cable"),
    ("变压器", "变压器", "llmkg_transformer"),
    ("主变", "变压器", "llmkg_transformer"),
    ("避雷器", "避雷器", "llmkg_surge_arrester"),
    ("互感器", "互感器", "llmkg_mutual"),
    ("光缆", "光缆", "llmkg_optical_cable"),
    ("环网柜", "环网柜", "llmkg_ring_main_unit"),
]

FAULT_KEYWORDS = ["故障", "告警", "异常", "拒动", "跳闸", "放电", "开路", "击穿", "起火", "处置", "预案", "应急"]


def parse_args(variant_id: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run experiment page variant: {variant_id}")
    parser.add_argument("--question", required=True, help="User question for this experiment variant.")
    parser.add_argument("--endpoint", default=pipeline.DEFAULT_BASE_URL)
    parser.add_argument("--basic-key-file", type=Path, default=pipeline.DEFAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-basic-key-file", type=Path, default=pipeline.DEFAULT_MULTI_FAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-graph-query-key-file", type=Path, default=pipeline.DEFAULT_MULTI_FAULT_GRAPH_QUERY_KEY)
    parser.add_argument("--splitter-key-file", type=Path, default=pipeline.DEFAULT_SPLITTER_KEY)
    parser.add_argument("--parallel-key-file", type=Path, default=pipeline.DEFAULT_PARALLEL_KEY)
    parser.add_argument("--timeout", type=int, default=210)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=pipeline.DEFAULT_OUTPUT_DIR / "experiment_page_variants" / variant_id)
    parser.add_argument("--stream-events", action="store_true")
    return parser.parse_args()


def keyword_boundary(question: str) -> dict[str, str] | None:
    has_device = any(keyword in question for keyword, _, _ in DEVICE_KEYWORDS)
    has_fault = any(keyword in question for keyword in FAULT_KEYWORDS)
    if not has_device and not has_fault:
        return {
            "reason": "irrelevant",
            "message": "关键词规则未命中电力设备故障或应急处置问题。",
            "boundaryResult": "irrelevant",
            "boundaryMessage": "关键词规则未命中电力设备故障或应急处置问题。",
            "userQuestion": question,
        }
    if has_fault and not has_device:
        return {
            "reason": "unsupported_device",
            "message": "关键词规则未识别到当前系统支持的设备主体。",
            "boundaryResult": "unsupported_device",
            "boundaryMessage": "关键词规则未识别到当前系统支持的设备主体。",
            "userQuestion": question,
        }
    return None


def keyword_subject(question: str) -> tuple[str, str] | None:
    for keyword, device_name, kb_name in DEVICE_KEYWORDS:
        if keyword in question:
            return device_name, kb_name
    return None


def update_fault_scene_device(fault_scene: str, device_name: str | None) -> str:
    try:
        parsed = json.loads(fault_scene or "{}")
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    parsed["故障对象"] = device_name or "未明确"
    return json.dumps(parsed, ensure_ascii=False)


def call_basic(args: argparse.Namespace, question: str, *, use_multi_fault: bool = False, ignore_boundary: bool = False) -> tuple[dict[str, Any], float, dict[str, str], dict[str, Any]]:
    key = pipeline.read_key(args.multi_fault_basic_key_file if use_multi_fault else args.basic_key_file)
    response, elapsed = pipeline.call_plugin(args.endpoint, key, {"用户问题": question}, args.timeout)
    output = pipeline.extract_plugin_output(response)
    boundary_failure = pipeline.extract_boundary_failure(output)
    if boundary_failure is not None and not ignore_boundary:
        raise RuntimeError(json.dumps(boundary_failure, ensure_ascii=False))
    return response, elapsed, pipeline.extract_basic_fields(output, question), output


def call_template_split(args: argparse.Namespace) -> tuple[dict[str, Any], float, dict[str, Any], list[dict[str, Any]]]:
    splitter_key = pipeline.read_key(args.splitter_key_file)
    response, elapsed = pipeline.call_plugin(args.endpoint, splitter_key, None, args.timeout)
    split_result = pipeline.extract_split_result(pipeline.extract_plugin_output(response))
    chapters = pipeline.extract_chapters(split_result)
    if not chapters:
        raise RuntimeError("No chapters found in template splitter output.")
    return response, elapsed, split_result, chapters


def generate_chapters(args: argparse.Namespace, basic_fields: dict[str, str], chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parallel_key = pipeline.read_key(args.parallel_key_file)
    generations: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(chapters))) as executor:
        future_map = {
            executor.submit(
                pipeline.generate_one_chapter,
                args.endpoint,
                parallel_key,
                args.timeout,
                basic_fields,
                chapter,
                args.stream_events,
            ): chapter
            for chapter in chapters
        }
        for future in as_completed(future_map):
            generations.append(future.result())
    generations.sort(key=lambda item: pipeline.chapter_sort_key(item["chapter_no"]))
    return generations


def blank_chapter_templates(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**chapter, "template_text": ""} for chapter in chapters]


def main(variant_id: str) -> None:
    args = parse_args(variant_id)
    question = args.question
    started = time.time()

    if variant_id == "boundary_no_boundary":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question, ignore_boundary=True)
    elif variant_id == "boundary_keyword_boundary":
        keyword_failure = keyword_boundary(question)
        if keyword_failure is not None:
            pipeline.emit_event(args.stream_events, "pipeline_error", keyword_failure)
            print(json.dumps(keyword_failure, ensure_ascii=False, indent=2))
            return
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question, ignore_boundary=True)
        basic_fields["边界判定结果"] = "ok"
        basic_fields["边界判定信息"] = ""
    elif variant_id == "disambiguation_drop_subject":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
        basic_fields["故障与场景提取结果"] = update_fault_scene_device(basic_fields["故障与场景提取结果"], None)
    elif variant_id == "disambiguation_keyword_subject":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
        matched = keyword_subject(question)
        if matched:
            device_name, kb_name = matched
            basic_fields["故障与场景提取结果"] = update_fault_scene_device(basic_fields["故障与场景提取结果"], device_name)
            basic_fields["知识库名"] = kb_name
    elif variant_id == "graph_template_no_graph":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
        basic_fields["图谱检索方案素材"] = ""
    elif variant_id == "graph_template_no_template":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
    elif variant_id == "multi_fault_single_fault":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question, use_multi_fault=False)
    elif variant_id == "multi_fault_no_per_fault_graph":
        basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question, use_multi_fault=True)
        try:
            parsed_fault_scene = json.loads(basic_fields["故障与场景提取结果"] or "{}")
        except Exception:
            parsed_fault_scene = {}
        main_fault = str(parsed_fault_scene.get("主故障二级节点") or question) if isinstance(parsed_fault_scene, dict) else question
        _, _, main_fault_fields, _ = call_basic(args, main_fault, use_multi_fault=False, ignore_boundary=True)
        basic_fields["图谱检索方案素材"] = main_fault_fields["图谱检索方案素材"]
        basic_fields["知识库名"] = main_fault_fields["知识库名"] or basic_fields["知识库名"]
    else:
        raise ValueError(f"Unknown variant: {variant_id}")

    splitter_response, splitter_elapsed, split_result, chapters = call_template_split(args)
    if variant_id == "graph_template_no_template":
        chapters = blank_chapter_templates(chapters)

    generations = generate_chapters(args, basic_fields, chapters)
    out_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    pipeline.write_outputs(out_dir, question, basic_response, basic_elapsed, basic_fields, splitter_response, splitter_elapsed, split_result, generations)
    result = {"variant": variant_id, "elapsed_sec": round(time.time() - started, 3), "output_dir": str(out_dir)}
    pipeline.emit_event(args.stream_events, "variant_done", result)
    if not args.stream_events:
        print(json.dumps(result, ensure_ascii=False))
