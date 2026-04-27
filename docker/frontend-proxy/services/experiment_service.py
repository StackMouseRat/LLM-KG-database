from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from services.sse import send_sse


REPO_ROOT = Path(os.getenv("LLM_KG_REPO_ROOT", "/app"))
if not REPO_ROOT.exists():
    REPO_ROOT = Path("/home/ubuntu/LLM-KG-database")
EXPERIMENT_SCRIPT_DIR = Path(os.getenv("EXPERIMENT_SCRIPT_DIR", str(REPO_ROOT / "scripts" / "experiment_page_variants")))
EXPERIMENT_RUN_DIR = Path(os.getenv("EXPERIMENT_RUN_DIR", "/app/data/frontend_experiment_runs"))

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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_run_id(plan_id: str) -> str:
    return f"{plan_id}_{int(time.time() * 1000)}_{random.randrange(0, 0xFFFFFF):06x}"


def run_dir(plan_id: str, run_id: str) -> Path:
    return EXPERIMENT_RUN_DIR / plan_id / run_id


def manifest_path(plan_id: str, run_id: str) -> Path:
    return run_dir(plan_id, run_id) / "experiment_run.json"


def save_manifest(manifest: dict[str, Any]) -> None:
    plan_id = str(manifest.get("planId") or "")
    run_id = str(manifest.get("runId") or "")
    path = manifest_path(plan_id, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["updatedAt"] = now_iso()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def load_manifest(plan_id: str, run_id: str) -> dict[str, Any]:
    path = manifest_path(plan_id, run_id)
    if not path.exists():
        raise RuntimeError(f"experiment run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    total_groups = 0
    completed_groups = 0
    for round_data in rounds.values():
        groups = round_data.get("groups") if isinstance(round_data, dict) and isinstance(round_data.get("groups"), dict) else {}
        total_groups += len(groups)
        completed_groups += sum(1 for item in groups.values() if isinstance(item, dict) and item.get("status") in {"done", "terminated"})
    return {
        "runId": manifest.get("runId", ""),
        "planId": manifest.get("planId", ""),
        "status": manifest.get("status", ""),
        "createdAt": manifest.get("createdAt", ""),
        "updatedAt": manifest.get("updatedAt", ""),
        "runCount": int(manifest.get("runCount") or 0),
        "concurrency": int(manifest.get("concurrency") or 0),
        "completedGroups": completed_groups,
        "totalGroups": total_groups,
        "questions": manifest.get("questions") if isinstance(manifest.get("questions"), list) else [],
    }


def output_state_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    round_questions: dict[str, str] = {}
    output_rounds: dict[str, dict[str, Any]] = {}
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    for round_key, round_data in rounds.items():
        if not isinstance(round_data, dict):
            continue
        question = str(round_data.get("question") or "")
        round_questions[str(round_key)] = question
        output_rounds[str(round_key)] = {}
        groups = round_data.get("groups") if isinstance(round_data.get("groups"), dict) else {}
        for group_id, group_output in groups.items():
            if not isinstance(group_output, dict):
                continue
            output_rounds[str(round_key)][str(group_id)] = {
                "groupId": str(group_id),
                "groupLabel": str(group_output.get("groupLabel") or ""),
                "question": str(group_output.get("question") or question),
                "outputText": str(group_output.get("outputText") or group_output.get("message") or ""),
                "streamingText": "",
                "status": str(group_output.get("status") or "error"),
            }
    return {"roundQuestions": round_questions, "rounds": output_rounds}


def list_experiment_runs(plan_id: str) -> list[dict[str, Any]]:
    base_dir = EXPERIMENT_RUN_DIR / plan_id
    if not base_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in base_dir.glob("*/experiment_run.json"):
        try:
            items.append(summarize_manifest(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return sorted(items, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)


def get_experiment_run(plan_id: str, run_id: str) -> dict[str, Any]:
    manifest = load_manifest(plan_id, run_id)
    return {"run": summarize_manifest(manifest), "outputState": output_state_from_manifest(manifest), "manifest": manifest}


def create_manifest(plan_id: str, run_id: str, run_count: int, concurrency: int, questions: list[str], groups: list[dict[str, Any]]) -> dict[str, Any]:
    created_at = now_iso()
    rounds: dict[str, Any] = {}
    for round_index in range(1, run_count + 1):
        question = questions[(round_index - 1) % len(questions)]
        rounds[str(round_index)] = {
            "question": question,
            "groups": {
                str(group["groupId"]): {
                    "groupId": str(group["groupId"]),
                    "groupLabel": str(group.get("label") or ""),
                    "question": question,
                    "status": "pending",
                    "outputText": "",
                    "resultFile": "",
                }
                for group in groups
            },
        }
    return {
        "runId": run_id,
        "planId": plan_id,
        "status": "running",
        "createdAt": created_at,
        "updatedAt": created_at,
        "runCount": run_count,
        "concurrency": concurrency,
        "questions": questions,
        "groups": [{"groupId": str(group["groupId"]), "label": str(group.get("label") or "")} for group in groups],
        "rounds": rounds,
    }


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
