#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(os.getenv("LLM_KG_REPO_ROOT", "/home/ubuntu/LLM-KG-database"))
DEFAULT_BASE_URL = os.getenv("PIPELINE_BASE_URL", "http://127.0.0.1:3000/api/v1/chat/completions")


def pick_key_path(*candidates: str) -> Path:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return Path(candidates[0])


DEFAULT_BASIC_KEY = Path(
    os.getenv("PIPELINE_BASIC_KEY_FILE", "/home/ubuntu/.fastgpt_keys/basic_info_api_key")
)
DEFAULT_MULTI_FAULT_BASIC_KEY = Path(
    os.getenv(
        "PIPELINE_MULTI_FAULT_BASIC_KEY_FILE",
        str(
            pick_key_path(
                "/run/fastgpt_keys/multi_fault_device_analysis_plugin_api_key",
                "/home/ubuntu/.fastgpt_keys/multi_fault_device_analysis_plugin_api_key",
            )
        ),
    )
)
DEFAULT_MULTI_FAULT_GRAPH_QUERY_KEY = Path(
    os.getenv(
        "PIPELINE_MULTI_FAULT_GRAPH_QUERY_KEY_FILE",
        str(
            pick_key_path(
                "/run/fastgpt_keys/parallel_database_query_plugin_api_key",
                "/home/ubuntu/.fastgpt_keys/parallel_database_query_plugin_api_key",
            )
        ),
    )
)
DEFAULT_SPLITTER_KEY = Path(
    os.getenv("PIPELINE_SPLITTER_KEY_FILE", "/home/ubuntu/.fastgpt_keys/template_publish_test_api_key")
)
DEFAULT_PARALLEL_KEY = Path(
    os.getenv("PIPELINE_PARALLEL_KEY_FILE", "/home/ubuntu/.fastgpt_keys/parallel_gen_api_key")
)
DEFAULT_OUTPUT_DIR = Path(
    os.getenv(
        "PIPELINE_DEFAULT_OUTPUT_DIR",
        str(REPO_ROOT / "docs" / "project_changes" / "parallel_generation_pipeline_runs"),
    )
)
EVENT_LOCK = threading.Lock()


def read_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"API key file is empty: {path}")
    return key


def emit_event(stream_events: bool, event: str, data: dict[str, Any] | None = None) -> None:
    if not stream_events:
        return
    payload: dict[str, Any] = {"event": event}
    if data is not None:
        payload["data"] = data
    with EVENT_LOCK:
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def log_progress(stream_events: bool, message: str) -> None:
    if not stream_events:
        print(message, flush=True)


def post_chat(endpoint: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def post_chat_stream(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: int,
    on_chunk: callable | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    answer = ""
    flow_responses: list[Any] = []
    event_name = ""
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal answer, flow_responses, event_name, data_lines
        if not event_name and not data_lines:
            return

        payload_text = "\n".join(data_lines).strip()
        if not payload_text:
            event_name = ""
            data_lines = []
            return

        try:
            payload_obj = json.loads(payload_text)
        except Exception:
            payload_obj = payload_text

        if event_name == "answer" and isinstance(payload_obj, dict):
            text = (
                payload_obj.get("text")
                or payload_obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                or payload_obj.get("choices", [{}])[0].get("message", {}).get("content", "")
                or ""
            )
            if isinstance(text, str) and text:
                answer += text
                if on_chunk:
                    on_chunk(text)
        elif event_name == "flowResponses" and isinstance(payload_obj, list):
            flow_responses = payload_obj

        event_name = ""
        data_lines = []

    with urlopen(req, timeout=timeout) as resp:
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

    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": answer
                }
            }
        ],
        "responseData": flow_responses,
    }


def call_plugin(
    endpoint: str,
    api_key: str,
    variables: dict[str, Any] | None,
    timeout: int
) -> tuple[dict[str, Any], float]:
    payload: dict[str, Any] = {"stream": False, "detail": True}
    if variables:
        payload["variables"] = variables

    start = time.time()
    response = post_chat(endpoint, api_key, payload, timeout)
    return response, round(time.time() - start, 3)


def extract_plugin_output(response: dict[str, Any]) -> dict[str, Any]:
    response_data = response.get("responseData", [])
    if not isinstance(response_data, list):
        return {}

    for node in response_data:
        if not isinstance(node, dict):
            continue
        if node.get("moduleType") == "pluginOutput":
            plugin_output = node.get("pluginOutput", {})
            return plugin_output if isinstance(plugin_output, dict) else {}
    return {}


BOUNDARY_FAILURE_MESSAGES = {
    "irrelevant": "请输入电力设备故障、告警、检修或应急处置相关问题。",
    "unsupported_device": "当前系统暂不支持该设备类型，请改为断路器、电缆、变压器、避雷器、互感器、光缆或环网柜相关问题。",
    "incompatible_device_fault": "输入中的设备与故障描述可能不匹配，请确认故障主体或故障现象后重新输入。",
}


def extract_boundary_failure(plugin_output: dict[str, Any]) -> dict[str, str] | None:
    result = str(
        plugin_output.get("边界判定结果")
        or plugin_output.get("reason")
        or plugin_output.get("result")
        or ""
    ).strip()
    if not result or result == "ok":
        return None

    message = str(plugin_output.get("边界判定信息") or plugin_output.get("message") or "").strip()
    if not message:
        message = BOUNDARY_FAILURE_MESSAGES.get(result, "当前输入无法进入预案生成链路，请补充电力设备故障相关信息后重试。")

    return {
        "reason": result,
        "message": message,
        "userQuestion": str(plugin_output.get("用户问题") or ""),
        "boundaryResult": result,
        "boundaryMessage": message,
    }


KB_NAME_TO_DEVICE = {
    "llmkg_breaker": "高压断路器",
    "llmkg_cable": "电力电缆",
    "llmkg_transformer": "变压器",
    "llmkg_surge_arrester": "避雷器",
    "llmkg_mutual": "互感器",
    "llmkg_optical_cable": "光缆",
    "llmkg_ring_main_unit": "环网柜",
}


def extract_basic_fields(plugin_output: dict[str, Any], question: str) -> dict[str, str]:
    fault_scene = str(plugin_output.get("故障类型分析") or "")
    kb_name = str(plugin_output.get("知识库名") or "")
    if fault_scene:
        try:
            parsed = json.loads(fault_scene)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            fault_nodes = parsed.get("故障二级节点")
            if isinstance(fault_nodes, list):
                normalized_fault_nodes = [str(item).strip() for item in fault_nodes if str(item).strip()]
                parsed["故障二级节点"] = normalized_fault_nodes
                if normalized_fault_nodes and not parsed.get("主故障二级节点"):
                    parsed["主故障二级节点"] = normalized_fault_nodes[0]
            elif isinstance(fault_nodes, str) and fault_nodes.strip():
                parsed.setdefault("主故障二级节点", fault_nodes.strip())

            device_name = str(parsed.get("故障对象") or "").strip()
            if not device_name or device_name == "未明确" or "kV设备" in device_name or re.search(r"(该|本|某)设备", device_name):
                resolved = KB_NAME_TO_DEVICE.get(kb_name)
                if resolved:
                    parsed["故障对象"] = resolved
            fault_scene = json.dumps(parsed, ensure_ascii=False)

    return {
        "用户问题": str(plugin_output.get("用户问题") or question),
        "故障与场景提取结果": fault_scene,
        "图谱检索方案素材": str(plugin_output.get("图谱检索") or ""),
        "模板文本": str(plugin_output.get("模板文本") or ""),
        "知识库名": kb_name,
        "边界判定结果": str(plugin_output.get("边界判定结果") or plugin_output.get("reason") or plugin_output.get("result") or "ok"),
        "边界判定信息": str(plugin_output.get("边界判定信息") or plugin_output.get("message") or ""),
    }


def build_multi_fault_graph_material(
    endpoint: str,
    api_key: str,
    timeout: int,
    device_space: str,
    fault_scene_text: str,
    max_workers: int,
) -> str:
    try:
        parsed = json.loads(fault_scene_text or "{}")
    except Exception:
        parsed = {}

    if not isinstance(parsed, dict):
        return ""

    fault_nodes_raw = parsed.get("故障二级节点")
    if isinstance(fault_nodes_raw, list):
        fault_nodes = [str(item).strip() for item in fault_nodes_raw if str(item).strip()]
    elif isinstance(fault_nodes_raw, str) and fault_nodes_raw.strip():
        fault_nodes = [fault_nodes_raw.strip()]
    else:
        fault_nodes = []

    if not device_space or not fault_nodes:
        return ""

    per_fault: dict[str, str] = {}
    errors: dict[str, str] = {}

    def query_one_fault(fault_name: str) -> tuple[str, str]:
        response, _ = call_plugin(
            endpoint=endpoint,
            api_key=api_key,
            variables={"设备表": device_space, "当前查询的二级故障": fault_name},
            timeout=timeout,
        )
        plugin_output = extract_plugin_output(response)
        return fault_name, str(plugin_output.get("图谱检索") or "")

    with ThreadPoolExecutor(max_workers=min(max_workers, len(fault_nodes))) as executor:
        future_map = {executor.submit(query_one_fault, fault_name): fault_name for fault_name in fault_nodes}
        for future in as_completed(future_map):
            fault_name = future_map[future]
            try:
                name, text = future.result()
                per_fault[name] = text
            except Exception as exc:
                errors[fault_name] = str(exc)

    material = {
        "设备表": device_space,
        "故障二级节点": fault_nodes,
        "主故障二级节点": str(parsed.get("主故障二级节点") or (fault_nodes[0] if fault_nodes else "")),
        "逐故障图谱检索": per_fault,
    }
    if errors:
        material["查询错误"] = errors
    return json.dumps(material, ensure_ascii=False)


def extract_split_result(plugin_output: dict[str, Any]) -> dict[str, Any]:
    for key in ("切分结果", "章节模板对象", "result"):
        value = plugin_output.get(key)
        if isinstance(value, dict):
            return value
    return {}


def extract_chapters(split_result: dict[str, Any]) -> list[dict[str, Any]]:
    chapters = split_result.get("chapters")
    if not isinstance(chapters, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        normalized.append({
            "index": index,
            "chapter_no": str(chapter.get("chapter_no") or index),
            "title": str(chapter.get("title") or ""),
            "section_count": int(chapter.get("section_count") or 0),
            "template_text": str(chapter.get("text") or ""),
        })
    return normalized


def chapter_sort_key(chapter_no: str) -> tuple[int, list[int | str]]:
    parts = str(chapter_no).split(".")
    normalized: list[int | str] = []
    for part in parts:
        part = part.strip()
        if part.isdigit():
            normalized.append(int(part))
        else:
            normalized.append(part)
    return (0, normalized)


def extract_parallel_text(response: dict[str, Any]) -> str:
    plugin_output = extract_plugin_output(response)
    for key in ("template", "正文", "结果"):
        value = plugin_output.get(key)
        if isinstance(value, str) and value.strip():
            return value

    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
    return ""


def sanitize_generated_output(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    sanitized_lines: list[str] = []
    for line in value.split("\n"):
        sanitized_lines.append(re.sub(r"^(\s*)-\s+", r"\1", line))
    return "\n".join(sanitized_lines)


def build_generation_graph_material(graph_material_text: str) -> str:
    value = str(graph_material_text or "").strip()
    if not value:
        return ""

    try:
        parsed = json.loads(value)
    except Exception:
        return value

    if not isinstance(parsed, dict):
        return value

    per_fault = parsed.get("逐故障图谱检索")
    if not isinstance(per_fault, dict) or not per_fault:
        return value

    fault_names = parsed.get("故障二级节点")
    if isinstance(fault_names, list):
        normalized_faults = [str(item).strip() for item in fault_names if str(item).strip()]
    elif isinstance(fault_names, str) and fault_names.strip():
        normalized_faults = [fault_names.strip()]
    else:
        normalized_faults = []

    lines = [
        f"设备表：{str(parsed.get('设备表') or '未明确')}",
        f"主故障二级节点：{str(parsed.get('主故障二级节点') or (normalized_faults[0] if normalized_faults else '未明确'))}",
    ]
    if normalized_faults:
        lines.append(f"命中故障二级节点：{'、'.join(normalized_faults)}")

    for fault_name in normalized_faults or list(per_fault.keys()):
        fault_text = str(per_fault.get(fault_name) or "").strip()
        if not fault_text:
            continue
        lines.extend([
            "",
            f"【{fault_name}】",
            fault_text,
        ])

    extra_errors = parsed.get("查询错误")
    if isinstance(extra_errors, dict) and extra_errors:
        lines.append("")
        lines.append("【查询错误】")
        for fault_name, error_text in extra_errors.items():
            lines.append(f"{fault_name}：{error_text}")

    return "\n".join(lines).strip()


def generate_one_chapter(
    endpoint: str,
    api_key: str,
    timeout: int,
    shared_fields: dict[str, str],
    chapter: dict[str, Any],
    stream_events: bool,
) -> dict[str, Any]:
    variables = {
        "用户问题": shared_fields["用户问题"],
        "故障与场景提取结果": shared_fields["故障与场景提取结果"],
        "图谱检索方案素材": build_generation_graph_material(shared_fields["图谱检索方案素材"]),
        "模板": chapter["template_text"],
    }

    start = time.time()
    response = post_chat_stream(
        endpoint,
        api_key,
        {"stream": True, "detail": True, "variables": variables},
        timeout,
        on_chunk=(
            lambda chunk: emit_event(
                stream_events,
                "chapter_chunk",
                {
                    "chapterNo": chapter["chapter_no"],
                    "title": chapter["title"],
                    "chunk": chunk,
                },
            )
        ),
    )
    elapsed = round(time.time() - start, 3)

    return {
        "chapter_no": chapter["chapter_no"],
        "title": chapter["title"],
        "section_count": chapter["section_count"],
        "template_text": chapter["template_text"],
        "elapsed_sec": elapsed,
        "response": response,
        "output_text": sanitize_generated_output(extract_parallel_text(response)),
    }


def write_outputs(
    out_dir: Path,
    question: str,
    basic_response: dict[str, Any],
    basic_elapsed: float,
    basic_fields: dict[str, str],
    splitter_response: dict[str, Any],
    splitter_elapsed: float,
    split_result: dict[str, Any],
    generations: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    result_json = {
        "question": question,
        "basic_info": {
            "elapsed_sec": basic_elapsed,
            "fields": basic_fields,
            "response": basic_response,
        },
        "template_splitter": {
            "elapsed_sec": splitter_elapsed,
            "split_result": split_result,
            "response": splitter_response,
        },
        "parallel_generations": generations,
    }
    (out_dir / "pipeline_result.json").write_text(
        json.dumps(result_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 并行生成流水线结果",
        "",
        f"问题：{question}",
        "",
        "## 基本信息",
        f"- 用户问题：{basic_fields['用户问题']}",
        "- 故障与场景提取结果：",
        "```json",
        basic_fields["故障与场景提取结果"],
        "```",
        "- 图谱检索方案素材：",
        "```text",
        basic_fields["图谱检索方案素材"],
        "```",
        "",
        "## 模板切片结果",
        "```json",
        json.dumps(split_result, ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    for item in generations:
        lines.extend([
            f"## Chapter {item['chapter_no']} {item['title']}",
            f"- elapsed_sec: {item['elapsed_sec']}",
            f"- section_count: {item['section_count']}",
            "- template_text:",
            "```text",
            item["template_text"],
            "```",
            "- output_text:",
            "```text",
            item["output_text"],
            "```",
            "",
        ])

    (out_dir / "pipeline_result.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run basic-info -> template-splitter -> parallel-generation pipeline.")
    parser.add_argument("--question", required=True, help="User question passed to the basic-info plugin.")
    parser.add_argument("--endpoint", default=DEFAULT_BASE_URL)
    parser.add_argument("--basic-key-file", type=Path, default=DEFAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-basic-key-file", type=Path, default=DEFAULT_MULTI_FAULT_BASIC_KEY)
    parser.add_argument("--multi-fault-graph-query-key-file", type=Path, default=DEFAULT_MULTI_FAULT_GRAPH_QUERY_KEY)
    parser.add_argument("--splitter-key-file", type=Path, default=DEFAULT_SPLITTER_KEY)
    parser.add_argument("--parallel-key-file", type=Path, default=DEFAULT_PARALLEL_KEY)
    parser.add_argument("--timeout", type=int, default=210)
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stream-events", action="store_true")
    parser.add_argument("--multi-fault", action="store_true")
    args = parser.parse_args()

    basic_key = read_key(args.multi_fault_basic_key_file if args.multi_fault else args.basic_key_file)
    multi_fault_graph_query_key = (
        read_key(args.multi_fault_graph_query_key_file) if args.multi_fault else ""
    )
    splitter_key = read_key(args.splitter_key_file)
    parallel_key = read_key(args.parallel_key_file)

    try:
        emit_event(args.stream_events, "basic_info_started", {"question": args.question})
        log_progress(
            args.stream_events,
            "[1/3] Calling 多故障基本信息获取 plugin..." if args.multi_fault else "[1/3] Calling 基本信息获取 plugin..."
        )
        basic_response, basic_elapsed = call_plugin(
            endpoint=args.endpoint,
            api_key=basic_key,
            variables={"用户问题": args.question},
            timeout=args.timeout,
        )
        basic_output = extract_plugin_output(basic_response)
        boundary_failure = extract_boundary_failure(basic_output)
        if boundary_failure is not None:
            emit_event(args.stream_events, "pipeline_error", boundary_failure)
            log_progress(args.stream_events, boundary_failure["message"])
            return

        basic_fields = extract_basic_fields(basic_output, args.question)
        if args.multi_fault:
            graph_material = build_multi_fault_graph_material(
                endpoint=args.endpoint,
                api_key=multi_fault_graph_query_key,
                timeout=args.timeout,
                device_space=str(basic_output.get("设备表") or ""),
                fault_scene_text=basic_fields["故障与场景提取结果"],
                max_workers=args.max_workers,
            )
            if graph_material:
                basic_fields["图谱检索方案素材"] = graph_material
        emit_event(
            args.stream_events,
            "basic_info_done",
            {
                "elapsed_sec": basic_elapsed,
                "basicInfo": {
                    "userQuestion": basic_fields["用户问题"],
                    "faultScene": basic_fields["故障与场景提取结果"],
                    "graphMaterial": basic_fields["图谱检索方案素材"],
                    "kbName": basic_fields["知识库名"],
                    "boundaryResult": basic_fields["边界判定结果"],
                    "boundaryMessage": basic_fields["边界判定信息"],
                },
            },
        )

        emit_event(args.stream_events, "template_split_started", {})
        log_progress(args.stream_events, "[2/3] Calling 模板切片 plugin...")
        splitter_response, splitter_elapsed = call_plugin(
            endpoint=args.endpoint,
            api_key=splitter_key,
            variables=None,
            timeout=args.timeout,
        )
        splitter_output = extract_plugin_output(splitter_response)
        split_result = extract_split_result(splitter_output)
        chapters = extract_chapters(split_result)
        if not chapters:
            raise RuntimeError("No chapters found in template splitter output.")
        emit_event(
            args.stream_events,
            "template_split_done",
            {
                "elapsed_sec": splitter_elapsed,
                "templateSplit": {
                    "templateId": str(split_result.get("template_id") or ""),
                    "templateName": str(split_result.get("template_name") or ""),
                    "currentVersion": str(split_result.get("current_version") or ""),
                    "chapterCount": len(chapters),
                },
                "chapters": [
                    {
                        "chapterNo": chapter["chapter_no"],
                        "title": chapter["title"],
                        "sectionCount": chapter["section_count"],
                        "templateText": chapter["template_text"],
                        "status": "pending",
                    }
                    for chapter in chapters
                ],
            },
        )

        emit_event(args.stream_events, "parallel_generating_started", {"chapterCount": len(chapters)})
        log_progress(args.stream_events, f"[3/3] Calling 并行生成 plugin for {len(chapters)} chapters...")
        generations: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(args.max_workers, len(chapters))) as executor:
            future_map = {}
            for chapter in chapters:
                emit_event(
                    args.stream_events,
                    "chapter_started",
                    {
                        "chapterNo": chapter["chapter_no"],
                        "title": chapter["title"],
                        "sectionCount": chapter["section_count"],
                    },
                )
                future = executor.submit(
                    generate_one_chapter,
                    args.endpoint,
                    parallel_key,
                    args.timeout,
                    basic_fields,
                    chapter,
                    args.stream_events,
                )
                future_map[future] = chapter

            for future in as_completed(future_map):
                chapter = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    emit_event(
                        args.stream_events,
                        "chapter_error",
                        {
                            "chapterNo": chapter["chapter_no"],
                            "title": chapter["title"],
                            "error": str(exc),
                        },
                    )
                    raise
                generations.append(result)
                emit_event(
                    args.stream_events,
                    "chapter_done",
                    {
                        "chapterNo": result["chapter_no"],
                        "title": result["title"],
                        "sectionCount": result["section_count"],
                        "elapsedSec": result["elapsed_sec"],
                        "templateText": result["template_text"],
                        "outputText": result["output_text"],
                        "status": "done" if result["output_text"] else "error",
                    },
                )
                log_progress(
                    args.stream_events,
                    f"  - chapter={chapter['chapter_no']} title={chapter['title']} elapsed={result['elapsed_sec']}s",
                )

        generations.sort(key=lambda x: chapter_sort_key(x["chapter_no"]))

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = args.output_dir / ts
        write_outputs(
            out_dir=out_dir,
            question=args.question,
            basic_response=basic_response,
            basic_elapsed=basic_elapsed,
            basic_fields=basic_fields,
            splitter_response=splitter_response,
            splitter_elapsed=splitter_elapsed,
            split_result=split_result,
            generations=generations,
        )

        final_result = {
            "question": args.question,
            "basicInfo": {
                "userQuestion": basic_fields["用户问题"],
                "faultScene": basic_fields["故障与场景提取结果"],
                "graphMaterial": basic_fields["图谱检索方案素材"],
                "boundaryResult": basic_fields["边界判定结果"],
                "boundaryMessage": basic_fields["边界判定信息"],
            },
            "templateSplit": {
                "templateId": str(split_result.get("template_id") or ""),
                "templateName": str(split_result.get("template_name") or ""),
                "currentVersion": str(split_result.get("current_version") or ""),
                "chapterCount": len(chapters),
            },
            "chapters": [
                {
                    "chapterNo": result["chapter_no"],
                    "title": result["title"],
                    "sectionCount": result["section_count"],
                    "templateText": result["template_text"],
                    "outputText": result["output_text"],
                    "elapsedSec": result["elapsed_sec"],
                    "status": "done" if result["output_text"] else "error",
                }
                for result in generations
            ],
        }
        emit_event(args.stream_events, "pipeline_done", final_result)
        log_progress(args.stream_events, f"Saved results to: {out_dir}")
    except Exception as exc:
        emit_event(args.stream_events, "pipeline_error", {"message": str(exc)})
        raise


if __name__ == "__main__":
    main()
