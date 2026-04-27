from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from services.sse import send_sse


REPO_ROOT = Path(os.getenv("LLM_KG_REPO_ROOT", "/app"))
if not REPO_ROOT.exists():
    REPO_ROOT = Path("/home/ubuntu/LLM-KG-database")
EXPERIMENT_SCRIPT_DIR = Path(os.getenv("EXPERIMENT_SCRIPT_DIR", str(REPO_ROOT / "scripts" / "experiment_page_variants")))

PLAN_GROUP_SCRIPTS = {
    "boundary": [
        {"groupId": "control", "label": "对照组", "script": REPO_ROOT / "scripts" / "run_parallel_generation_pipeline.py", "extraArgs": []},
        {"groupId": "exp-no-boundary", "label": "实验组一", "script": EXPERIMENT_SCRIPT_DIR / "boundary_no_boundary.py", "extraArgs": []},
        {"groupId": "exp-keyword-boundary", "label": "实验组二", "script": EXPERIMENT_SCRIPT_DIR / "boundary_keyword_boundary.py", "extraArgs": []},
    ],
    "disambiguation": [
        {"groupId": "control", "label": "对照组", "script": REPO_ROOT / "scripts" / "run_parallel_generation_pipeline.py", "extraArgs": []},
        {"groupId": "exp-drop-subject-judgement", "label": "实验组一", "script": EXPERIMENT_SCRIPT_DIR / "disambiguation_drop_subject.py", "extraArgs": []},
        {"groupId": "exp-keyword-subject-judgement", "label": "实验组二", "script": EXPERIMENT_SCRIPT_DIR / "disambiguation_keyword_subject.py", "extraArgs": []},
    ],
    "graphTemplate": [
        {"groupId": "control", "label": "对照组", "script": REPO_ROOT / "scripts" / "run_parallel_generation_pipeline.py", "extraArgs": []},
        {"groupId": "exp-no-graph", "label": "实验组一", "script": EXPERIMENT_SCRIPT_DIR / "graph_template_no_graph.py", "extraArgs": []},
        {"groupId": "exp-no-template", "label": "实验组二", "script": EXPERIMENT_SCRIPT_DIR / "graph_template_no_template.py", "extraArgs": []},
    ],
    "multiFault": [
        {"groupId": "control", "label": "对照组", "script": REPO_ROOT / "scripts" / "run_parallel_generation_pipeline.py", "extraArgs": ["--multi-fault"]},
        {"groupId": "exp-single-fault", "label": "实验组一", "script": EXPERIMENT_SCRIPT_DIR / "multi_fault_single_fault.py", "extraArgs": []},
        {"groupId": "exp-detect-no-per-fault-graph", "label": "实验组二", "script": EXPERIMENT_SCRIPT_DIR / "multi_fault_no_per_fault_graph.py", "extraArgs": []},
    ],
}


def find_result_file(base_dir: Path) -> Path | None:
    result_files = sorted(base_dir.glob("**/pipeline_result.json"), key=lambda path: path.stat().st_mtime)
    return result_files[-1] if result_files else None


def combine_output_text(result: dict[str, Any]) -> str:
    chapters = result.get("parallel_generations") or result.get("chapters") or []
    if not isinstance(chapters, list):
        return ""
    parts: list[str] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or "").strip()
        chapter_no = str(chapter.get("chapter_no") or chapter.get("chapterNo") or "").strip()
        text = str(chapter.get("output_text") or chapter.get("outputText") or "").strip()
        if not text:
            continue
        heading = " ".join(item for item in (chapter_no, title) if item)
        parts.append(f"## {heading}\n{text}" if heading else text)
    return "\n\n".join(parts).strip()


def run_one_group(
    handler: BaseHTTPRequestHandler,
    send_lock: threading.Lock,
    *,
    plan_id: str,
    group: dict[str, Any],
    round_index: int,
    run_count: int,
    question: str,
    output_dir: Path,
) -> dict[str, Any]:
    group_id = str(group["groupId"])
    script = Path(group["script"])
    group_output_dir = output_dir / f"round_{round_index:03d}" / group_id
    group_output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(script),
        "--question",
        question,
        "--output-dir",
        str(group_output_dir),
        "--stream-events",
        *list(group.get("extraArgs") or []),
    ]

    def safe_send(event: str, data: object) -> None:
        with send_lock:
            send_sse(handler, event, data)

    safe_send("experiment_group_started", {"planId": plan_id, "round": round_index, "runCount": run_count, "groupId": group_id, "groupLabel": group.get("label"), "question": question})
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=os.environ.copy())
    assert process.stdout is not None
    logs: list[str] = []
    terminal_message = ""
    terminated = False
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logs.append(line)
            safe_send("experiment_group_log", {"planId": plan_id, "round": round_index, "groupId": group_id, "text": line})
            continue
        event = payload.get("event")
        data = payload.get("data", {})
        if isinstance(event, str):
            safe_send("experiment_group_stream", {"planId": plan_id, "round": round_index, "groupId": group_id, "event": event, "data": data})
            if event == "pipeline_error" and isinstance(data, dict):
                terminated = True
                terminal_message = str(data.get("message") or data.get("boundaryMessage") or "流水线终止，未生成预案正文。")
            if event == "chapter_chunk" and isinstance(data, dict):
                safe_send("experiment_group_chunk", {"planId": plan_id, "round": round_index, "groupId": group_id, "text": str(data.get("chunk") or "")})

    return_code = process.wait()
    if return_code != 0:
        message = "\n".join(logs).strip() or f"experiment group exited with code {return_code}"
        safe_send("experiment_group_error", {"planId": plan_id, "round": round_index, "groupId": group_id, "message": message})
        return {"groupId": group_id, "status": "error", "message": message}

    result_file = find_result_file(group_output_dir)
    result = json.loads(result_file.read_text(encoding="utf-8")) if result_file else {}
    output_text = combine_output_text(result)
    status = "done"
    if not output_text and terminal_message:
        output_text = f"【流程终止】{terminal_message}"
        status = "terminated"
    elif not output_text and not result_file:
        output_text = "【无生成结果】脚本未产出 pipeline_result.json。"
        status = "terminated"
    payload = {"planId": plan_id, "round": round_index, "runCount": run_count, "groupId": group_id, "groupLabel": group.get("label"), "question": question, "outputText": output_text, "resultFile": str(result_file) if result_file else "", "status": status}
    safe_send("experiment_group_done", payload)
    return {"groupId": group_id, "status": "done", **payload}


def stream_experiment_run(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
    plan_id = str(body.get("planId") or "").strip()
    stage = str(body.get("stage") or "generation").strip()
    if stage != "generation":
        send_sse(handler, "experiment_stage_started", {"planId": plan_id, "stage": stage})
        send_sse(handler, "experiment_stage_done", {"planId": plan_id, "stage": stage, "message": "评估接口待接入质量评估批处理。"})
        return

    groups = PLAN_GROUP_SCRIPTS.get(plan_id)
    if not groups:
        send_sse(handler, "experiment_error", {"message": f"unknown experiment plan: {plan_id}"})
        return

    questions = [str(item).strip() for item in body.get("questions", []) if str(item).strip()]
    if not questions:
        send_sse(handler, "experiment_error", {"message": "questions is required"})
        return

    run_count = max(1, int(body.get("runCount") or 1))
    concurrency = max(1, min(int(body.get("concurrency") or 1), run_count * len(groups)))
    output_dir = Path(os.getenv("EXPERIMENT_RUN_DIR", "/app/data/frontend_experiment_runs")) / plan_id
    output_dir.mkdir(parents=True, exist_ok=True)
    send_lock = threading.Lock()
    total = run_count * len(groups)
    completed = 0

    send_sse(handler, "experiment_stage_started", {"planId": plan_id, "stage": stage, "runCount": run_count, "concurrency": concurrency, "total": total})
    tasks = []
    for round_index in range(1, run_count + 1):
        question = questions[(round_index - 1) % len(questions)]
        send_sse(handler, "experiment_round_started", {"planId": plan_id, "stage": stage, "round": round_index, "runCount": run_count, "question": question})
        for group in groups:
            tasks.append((round_index, question, group))

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(run_one_group, handler, send_lock, plan_id=plan_id, group=group, round_index=round_index, run_count=run_count, question=question, output_dir=output_dir): (round_index, group)
            for round_index, question, group in tasks
        }
        for future in as_completed(future_map):
            completed += 1
            try:
                future.result()
            except Exception as exc:
                round_index, group = future_map[future]
                send_sse(handler, "experiment_group_error", {"planId": plan_id, "round": round_index, "groupId": group.get("groupId"), "message": str(exc)})
            send_sse(handler, "experiment_progress", {"planId": plan_id, "stage": stage, "completed": completed, "total": total, "progress": round(completed / total * 100)})

    send_sse(handler, "experiment_stage_done", {"planId": plan_id, "stage": stage, "completed": completed, "total": total, "progress": 100})
