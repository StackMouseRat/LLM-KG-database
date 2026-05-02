#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

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
GRAPH_QUERY_URL_CANDIDATES = [
    os.getenv("EXPERIMENT_GRAPH_QUERY_URL", "").strip(),
    "http://host.docker.internal:8787/graph/query",
    "http://127.0.0.1:8787/graph/query",
]
BARE_LLM_URL = os.getenv("EXPERIMENT_BARE_LLM_URL", "https://api.deepseek.com/chat/completions")
BARE_LLM_MODEL = os.getenv("EXPERIMENT_BARE_LLM_MODEL", "deepseek-chat")
BARE_LLM_KEY_FILE = Path(os.getenv(
    "EXPERIMENT_BARE_LLM_KEY_FILE",
    str(pipeline.pick_key_path("/run/fastgpt_keys/deepseek_api_key", "/home/ubuntu/.fastgpt_keys/deepseek_api_key")),
))


def parse_args(variant_id: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run experiment page variant: {variant_id}")
    parser.add_argument("--question", required=True, help="User question for this experiment variant.")
    parser.add_argument("--endpoint", default=pipeline.DEFAULT_BASE_URL)
    parser.add_argument("--basic-key-file", type=Path, default=pipeline.DEFAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-basic-key-file", type=Path, default=pipeline.DEFAULT_MULTI_FAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-graph-query-key-file", type=Path, default=pipeline.DEFAULT_MULTI_FAULT_GRAPH_QUERY_KEY)
    parser.add_argument("--splitter-key-file", type=Path, default=pipeline.DEFAULT_SPLITTER_KEY)
    parser.add_argument("--parallel-key-file", type=Path, default=pipeline.DEFAULT_PARALLEL_KEY)
    parser.add_argument("--timeout", type=int, default=pipeline.DEFAULT_TIMEOUT)
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


def update_fault_scene_subject_and_fault(fault_scene: str, device_name: str | None, fault_name: str) -> str:
    try:
        parsed = json.loads(fault_scene or "{}")
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    parsed["故障对象"] = device_name or "未明确"
    parsed["故障二级节点"] = fault_name or "未明确"
    parsed["主故障二级节点"] = fault_name or "未明确"
    return json.dumps(parsed, ensure_ascii=False)


def post_json(url: str, payload: dict[str, Any], timeout: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def query_graph_gateway(space: str, ngql: str, timeout: int) -> dict[str, Any]:
    last_error = ""
    for url in [item for item in GRAPH_QUERY_URL_CANDIDATES if item]:
        try:
            result = post_json(url, {"space": space, "ngql": ngql}, timeout)
            if result.get("ok"):
                return result
            last_error = str(result.get("message") or result.get("errors") or "graph query failed")
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "graph query failed")


def parse_nebula_table_column(stdout: str, column_index: int) -> list[str]:
    values: list[str] = []
    for line in stdout.splitlines():
        if not line.strip().startswith("|") or '"' not in line:
            continue
        cells = [cell.strip().strip('"') for cell in line.strip().strip("|").split("|")]
        if len(cells) > column_index and cells[column_index] and cells[column_index] not in values:
            values.append(cells[column_index])
    return values


def query_fault_l2_candidates(device_space: str, timeout: int) -> list[str]:
    if not device_space:
        return []
    ngql = (
        "MATCH (l1:entity)-[:rel]->(l2:entity) "
        "WHERE l1.entity.lvl == 1 AND l2.entity.lvl == 2 "
        "RETURN l1.entity.name AS l1_name, l2.entity.name AS l2_name LIMIT 200;"
    )
    result = query_graph_gateway(device_space, ngql, timeout)
    return parse_nebula_table_column(str(result.get("stdout") or ""), 1)


def score_candidate(question: str, original_fault: str, candidate: str) -> int:
    text = f"{question} {original_fault}"
    score = 0
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", candidate):
        if token in text:
            score += len(token) * 3
    for keyword in ("拒动", "跳闸", "放电", "接地", "短路", "断路", "过热", "发热", "控制", "保护", "机构", "触头", "绝缘", "泄漏"):
        if keyword in text and keyword in candidate:
            score += 12
    return score


def choose_fault_l2_fallback(question: str, original_fault: str, candidates: list[str]) -> str:
    if not candidates:
        return original_fault or question
    return max(candidates, key=lambda item: (score_candidate(question, original_fault, item), -candidates.index(item)))


def choose_fault_l2_with_llm(question: str, device_name: str | None, original_fault: str, candidates: list[str], timeout: int) -> str:
    if not candidates:
        return original_fault or question
    if not BARE_LLM_KEY_FILE.exists():
        return choose_fault_l2_fallback(question, original_fault, candidates)

    prompt = (
        "你是电力设备故障分类助手。现在实验组已经被强行判定为某个设备，"
        "即使这个判定很牵强，也必须从候选二级故障中选择一个最能勉强解释用户问题的故障。"
        "只允许输出候选二级故障的原文，不要解释。\n\n"
        f"强行判定设备：{device_name or '未明确'}\n"
        f"用户问题：{question}\n"
        f"原完整流程故障节点：{original_fault or '未明确'}\n"
        "候选二级故障：\n" + "\n".join(f"- {item}" for item in candidates)
    )
    payload = {
        "model": BARE_LLM_MODEL,
        "messages": [
            {"role": "system", "content": "只从候选列表中选择并输出一个二级故障名称。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 80,
    }
    try:
        response = post_json(
            BARE_LLM_URL,
            payload,
            timeout,
            headers={"Authorization": f"Bearer {pipeline.read_key(BARE_LLM_KEY_FILE)}"},
        )
        content = str(response.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        for candidate in candidates:
            if candidate == content or candidate in content:
                return candidate
    except Exception:
        pass
    return choose_fault_l2_fallback(question, original_fault, candidates)


def fault_scene_main_fault(fault_scene: str, question: str) -> str:
    try:
        parsed = json.loads(fault_scene or "{}")
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    main_fault = str(parsed.get("主故障二级节点") or "").strip()
    if main_fault and main_fault != "未明确":
        return main_fault
    fault_nodes_raw = parsed.get("故障二级节点")
    if isinstance(fault_nodes_raw, list):
        for item in fault_nodes_raw:
            value = str(item).strip()
            if value and value != "未明确":
                return value
    elif isinstance(fault_nodes_raw, str) and fault_nodes_raw.strip() and fault_nodes_raw.strip() != "未明确":
        return fault_nodes_raw.strip()
    return question


def requery_graph_material(args: argparse.Namespace, device_space: str, fault_name: str) -> str:
    device_space = str(device_space or "").strip()
    fault_name = str(fault_name or "").strip()
    if not device_space or not fault_name:
        return "本实验组保留图谱检索步骤，但弱主体策略未得到可用设备表或故障节点，图谱检索无命中。"

    graph_key = pipeline.read_key(args.multi_fault_graph_query_key_file)
    graph_response, _ = pipeline.call_plugin(
        args.endpoint,
        graph_key,
        {"设备表": device_space, "当前查询的二级故障": fault_name},
        args.timeout,
    )
    graph_text = str(pipeline.extract_plugin_output(graph_response).get("图谱检索") or "").strip()
    return graph_text or f"本实验组按弱主体策略查询设备表 {device_space}、故障节点 {fault_name}，但图谱检索无命中。"


def apply_weak_subject_graph(args: argparse.Namespace, basic_fields: dict[str, str], question: str, *, device_name: str | None, kb_name: str | None) -> None:
    if kb_name:
        basic_fields["知识库名"] = kb_name
    original_fault = fault_scene_main_fault(basic_fields["故障与场景提取结果"], question)
    candidates = query_fault_l2_candidates(basic_fields.get("知识库名", ""), args.timeout)
    fault_name = choose_fault_l2_with_llm(question, device_name, original_fault, candidates, args.timeout)
    basic_fields["故障与场景提取结果"] = update_fault_scene_subject_and_fault(
        basic_fields["故障与场景提取结果"],
        device_name,
        fault_name,
    )
    basic_fields["图谱检索方案素材"] = requery_graph_material(args, basic_fields.get("知识库名", ""), fault_name)


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


def build_main_fault_graph_material(args: argparse.Namespace, basic_fields: dict[str, str], basic_output: dict[str, Any], question: str) -> tuple[str, str]:
    try:
        parsed_fault_scene = json.loads(basic_fields["故障与场景提取结果"] or "{}")
    except Exception:
        parsed_fault_scene = {}
    if not isinstance(parsed_fault_scene, dict):
        parsed_fault_scene = {}

    fault_nodes_raw = parsed_fault_scene.get("故障二级节点")
    if isinstance(fault_nodes_raw, list):
        fault_nodes = [str(item).strip() for item in fault_nodes_raw if str(item).strip()]
    elif isinstance(fault_nodes_raw, str) and fault_nodes_raw.strip():
        fault_nodes = [fault_nodes_raw.strip()]
    else:
        fault_nodes = []

    main_fault = str(parsed_fault_scene.get("主故障二级节点") or (fault_nodes[0] if fault_nodes else question)).strip()
    device_space = str(basic_output.get("设备表") or basic_fields.get("知识库名") or "").strip()
    graph_text = ""
    if device_space and main_fault:
        graph_key = pipeline.read_key(args.multi_fault_graph_query_key_file)
        graph_response, _ = pipeline.call_plugin(
            args.endpoint,
            graph_key,
            {"设备表": device_space, "当前查询的二级故障": main_fault},
            args.timeout,
        )
        graph_text = str(pipeline.extract_plugin_output(graph_response).get("图谱检索") or "")

    material = {
        "设备表": device_space,
        "故障二级节点": fault_nodes,
        "主故障二级节点": main_fault,
        "主故障图谱检索": {main_fault: graph_text} if main_fault else {},
        "未检索说明": "本实验组保留多故障识别结果，但只检索主故障图谱；伴随故障和次生故障不提供图谱素材。",
    }
    return json.dumps(material, ensure_ascii=False), device_space


def blank_chapter_templates(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    instruction = (
        "本实验组移除正式应急预案章节模板。请不要依赖固定六章结构、章节编号、章节标题或小节约束，"
        "仅根据用户问题、故障与场景提取结果、图谱检索素材自由组织内容，直接生成完整处置建议。"
        "输出应体现缺少模板约束时的自然组织方式，不要因为缺少模板而拒绝生成。"
    )
    return [{**chapter, "template_text": instruction} for chapter in chapters]


def main(variant_id: str) -> None:
    args = parse_args(variant_id)
    question = args.question
    started = time.time()

    try:
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
            matched = keyword_subject(question)
            apply_weak_subject_graph(
                args,
                basic_fields,
                question,
                device_name=None,
                kb_name=matched[1] if matched else basic_fields.get("知识库名", ""),
            )
        elif variant_id == "disambiguation_keyword_subject":
            basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
            matched = keyword_subject(question)
            if matched:
                device_name, kb_name = matched
                apply_weak_subject_graph(args, basic_fields, question, device_name=device_name, kb_name=kb_name)
        elif variant_id == "graph_template_no_graph":
            basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
            basic_fields["图谱检索方案素材"] = ""
        elif variant_id == "graph_template_no_template":
            basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question)
        elif variant_id == "multi_fault_single_fault":
            basic_response, basic_elapsed, basic_fields, _ = call_basic(args, question, use_multi_fault=False)
        elif variant_id == "multi_fault_no_per_fault_graph":
            basic_response, basic_elapsed, basic_fields, basic_output = call_basic(args, question, use_multi_fault=True)
            main_fault_material, device_space = build_main_fault_graph_material(args, basic_fields, basic_output, question)
            basic_fields["图谱检索方案素材"] = main_fault_material
            basic_fields["知识库名"] = device_space or basic_fields["知识库名"]
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
    except Exception as exc:
        pipeline.emit_event(args.stream_events, "pipeline_error", {"message": str(exc)})
        if not args.stream_events:
            print(json.dumps({"variant": variant_id, "error": str(exc)}, ensure_ascii=False))
