from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from services.sse import send_sse


def run_pipeline_process(
    question: str,
    *,
    pipeline_script: str,
    make_run_dir: Callable[[], Path],
    find_result_file: Callable[[Path], Path],
    enable_multi_fault_search: bool = False,
) -> dict[str, Any]:
    base_dir = make_run_dir()
    command = [
        sys.executable,
        pipeline_script,
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


def run_pipeline_sync(
    question: str,
    *,
    pipeline_script: str,
    make_run_dir: Callable[[], Path],
    find_result_file: Callable[[Path], Path],
    infer_dataset_with_context: Callable[..., dict[str, Any] | None],
    infer_dataset: Callable[[str, dict[str, Any] | None], dict[str, Any] | None],
    run_case_search: Callable[[str, dict[str, Any]], dict[str, Any]],
    enable_case_search: bool = False,
    enable_multi_fault_search: bool = False,
) -> dict[str, Any]:
    dataset = infer_dataset_with_context(question) if enable_case_search else None
    if enable_case_search and dataset is not None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            pipeline_future = executor.submit(
                run_pipeline_process,
                question,
                pipeline_script=pipeline_script,
                make_run_dir=make_run_dir,
                find_result_file=find_result_file,
                enable_multi_fault_search=enable_multi_fault_search,
            )
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

    result = run_pipeline_process(
        question,
        pipeline_script=pipeline_script,
        make_run_dir=make_run_dir,
        find_result_file=find_result_file,
        enable_multi_fault_search=enable_multi_fault_search,
    )
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
    *,
    pipeline_script: str,
    make_run_dir: Callable[[], Path],
    infer_dataset_with_context: Callable[..., dict[str, Any] | None],
    infer_dataset: Callable[[str, dict[str, Any] | None], dict[str, Any] | None],
    run_case_search: Callable[[str, dict[str, Any]], dict[str, Any]],
    enable_case_search: bool = False,
    enable_multi_fault_search: bool = False,
) -> None:
    base_dir = make_run_dir()
    command = [
        sys.executable,
        pipeline_script,
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
    final_result: dict[str, Any] | None = None
    pipeline_error_sent = False
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

    def start_case_search(dataset: dict[str, Any]) -> None:
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
        if event == "pipeline_error":
            pipeline_error_sent = True
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
    if return_code != 0 and not pipeline_error_sent:
        message = "\n".join(error_lines).strip() or f"pipeline exited with code {return_code}"
        try:
            send_sse(handler, "pipeline_error", {"message": message})
        except BrokenPipeError:
            return
    elif enable_case_search and not case_started and not pipeline_error_sent:
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
