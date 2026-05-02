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
from services.provider_balance_service import query_provider_balances


REPO_ROOT = Path(os.getenv("LLM_KG_REPO_ROOT", "/app"))
if not REPO_ROOT.exists():
    REPO_ROOT = Path("/home/ubuntu/LLM-KG-database")
EXPERIMENT_SCRIPT_DIR = Path(os.getenv("EXPERIMENT_SCRIPT_DIR", str(REPO_ROOT / "scripts" / "experiment_page_variants")))
EXPERIMENT_RUN_DIR = Path(os.getenv("EXPERIMENT_RUN_DIR", "/app/data/frontend_experiment_runs"))
EXPERIMENT_PIPELINE_TIMEOUT = int(os.getenv("EXPERIMENT_PIPELINE_TIMEOUT", os.getenv("PIPELINE_TIMEOUT", "480")))
MAX_EXPERIMENT_CONCURRENCY = 15
RUN_CONTROLS: dict[str, dict[str, Any]] = {}
RUN_CONTROLS_LOCK = threading.Lock()

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


def make_run_name(plan_id: str, run_count: int, concurrency: int) -> str:
    return f"{plan_id} · 总次数{run_count} · 并发{concurrency}"


def clamp_concurrency(value: int, run_count: int, group_count: int) -> int:
    return max(1, min(value, max(1, run_count * group_count), MAX_EXPERIMENT_CONCURRENCY))


def normalize_question_items(body: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw_items = body.get("questionItems")
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            question_text = str(raw_item.get("questionText") or raw_item.get("question") or "").strip()
            if not question_text:
                continue
            items.append({
                "questionId": str(raw_item.get("questionId") or ""),
                "questionText": question_text,
                "groupId": str(raw_item.get("groupId") or ""),
                "groupCode": str(raw_item.get("groupCode") or ""),
                "groupName": str(raw_item.get("groupName") or raw_item.get("category") or ""),
                "expectedBehavior": str(raw_item.get("expectedBehavior") or ""),
                "category": str(raw_item.get("category") or raw_item.get("groupName") or ""),
            })
    if items:
        return items

    return [
        {"questionId": "", "questionText": str(item).strip(), "groupId": "", "groupCode": "", "groupName": "", "expectedBehavior": "", "category": ""}
        for item in body.get("questions", [])
        if str(item).strip()
    ]


def sample_run_questions(question_items: list[dict[str, str]], run_count: int) -> list[dict[str, str]]:
    pool = [item for item in question_items if str(item.get("questionText") or "").strip()]
    if not pool:
        return []
    selected: list[dict[str, str]] = []
    while len(selected) < run_count:
        batch = pool[:]
        random.shuffle(batch)
        selected.extend(batch[: run_count - len(selected)])
    return selected[:run_count]


def run_dir(plan_id: str, run_id: str) -> Path:
    return EXPERIMENT_RUN_DIR / plan_id / run_id


def manifest_path(plan_id: str, run_id: str) -> Path:
    return run_dir(plan_id, run_id) / "experiment_run.json"


def evaluation_path(plan_id: str, run_id: str) -> Path:
    return run_dir(plan_id, run_id) / "experiment_evaluation.json"


def run_control_key(plan_id: str, run_id: str) -> str:
    return f"{plan_id}:{run_id}"


def register_run_control(plan_id: str, run_id: str) -> dict[str, Any]:
    key = run_control_key(plan_id, run_id)
    with RUN_CONTROLS_LOCK:
        control = {"mode": "running", "processes": set(), "updatedAt": now_iso()}
        RUN_CONTROLS[key] = control
        return control


def get_run_control(plan_id: str, run_id: str) -> dict[str, Any] | None:
    with RUN_CONTROLS_LOCK:
        return RUN_CONTROLS.get(run_control_key(plan_id, run_id))


def unregister_run_control(plan_id: str, run_id: str) -> None:
    with RUN_CONTROLS_LOCK:
        RUN_CONTROLS.pop(run_control_key(plan_id, run_id), None)


def interrupt_experiment_run(plan_id: str, run_id: str, mode: str) -> dict[str, Any]:
    if mode not in {"safe", "force"}:
        raise RuntimeError("interrupt mode must be safe or force")
    manifest = load_manifest(plan_id, run_id)
    manifest["interruptRequested"] = mode
    manifest["status"] = "stopping" if mode == "safe" else "interrupted"
    save_manifest(manifest)

    terminated = 0
    control = get_run_control(plan_id, run_id)
    if control is not None:
        with RUN_CONTROLS_LOCK:
            control["mode"] = mode
            control["updatedAt"] = now_iso()
            processes = list(control.get("processes") or [])
        if mode == "force":
            for process in processes:
                try:
                    if process.poll() is None:
                        process.terminate()
                        terminated += 1
                except Exception:
                    continue
    return {"ok": True, "planId": plan_id, "runId": run_id, "mode": mode, "terminated": terminated}


def save_manifest(manifest: dict[str, Any]) -> None:
    plan_id = str(manifest.get("planId") or "")
    run_id = str(manifest.get("runId") or "")
    path = manifest_path(plan_id, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["updatedAt"] = now_iso()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def capture_balance_snapshot(stage: str, round_index: int, timing: str) -> dict[str, Any]:
    try:
        payload = query_provider_balances(force=True)
        return {
            "stage": stage,
            "round": round_index,
            "timing": timing,
            "capturedAt": now_iso(),
            "updatedAt": payload.get("updatedAt"),
            "providers": payload.get("providers") if isinstance(payload.get("providers"), list) else [],
        }
    except Exception as exc:
        return {
            "stage": stage,
            "round": round_index,
            "timing": timing,
            "capturedAt": now_iso(),
            "error": str(exc),
            "providers": [],
        }


def append_balance_snapshot(manifest: dict[str, Any], snapshot: dict[str, Any]) -> None:
    snapshots = manifest.setdefault("balanceSnapshots", [])
    if isinstance(snapshots, list):
        snapshots.append(snapshot)


def all_groups_completed(manifest: dict[str, Any]) -> bool:
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    for round_data in rounds.values():
        groups = round_data.get("groups") if isinstance(round_data, dict) and isinstance(round_data.get("groups"), dict) else {}
        for group_output in groups.values():
            if not isinstance(group_output, dict) or group_output.get("status") not in {"done", "terminated"}:
                return False
    return True


def load_manifest(plan_id: str, run_id: str) -> dict[str, Any]:
    path = manifest_path(plan_id, run_id)
    if not path.exists():
        raise RuntimeError(f"experiment run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def default_evaluation_state() -> dict[str, Any]:
    return {"status": "idle", "progress": 0, "scores": {}}


def load_evaluation_record(plan_id: str, run_id: str) -> dict[str, Any]:
    path = evaluation_path(plan_id, run_id)
    if not path.exists():
        return {
            "planId": plan_id,
            "runId": run_id,
            "createdAt": "",
            "updatedAt": "",
            "evaluationState": default_evaluation_state(),
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_evaluation_record(plan_id: str, run_id: str, evaluation_state: dict[str, Any]) -> dict[str, Any]:
    load_manifest(plan_id, run_id)
    existing = load_evaluation_record(plan_id, run_id)
    now = now_iso()
    record = {
        "planId": plan_id,
        "runId": run_id,
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
        "evaluationState": evaluation_state if isinstance(evaluation_state, dict) else default_evaluation_state(),
    }
    path = evaluation_path(plan_id, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return record


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    total_groups = 0
    completed_groups = 0
    for round_data in rounds.values():
        groups = round_data.get("groups") if isinstance(round_data, dict) and isinstance(round_data.get("groups"), dict) else {}
        total_groups += len(groups)
        completed_groups += sum(1 for item in groups.values() if isinstance(item, dict) and item.get("status") in {"done", "terminated"})
    summary = {
        "runId": manifest.get("runId", ""),
        "name": manifest.get("name", ""),
        "planId": manifest.get("planId", ""),
        "status": manifest.get("status", ""),
        "createdAt": manifest.get("createdAt", ""),
        "updatedAt": manifest.get("updatedAt", ""),
        "runCount": int(manifest.get("runCount") or 0),
        "concurrency": int(manifest.get("concurrency") or 0),
        "completedGroups": completed_groups,
        "totalGroups": total_groups,
        "completedRounds": sum(1 for round_data in rounds.values() if isinstance(round_data, dict) and all(isinstance(item, dict) and item.get("status") in {"done", "terminated"} for item in (round_data.get("groups") or {}).values())),
        "targetRounds": int(manifest.get("runCount") or 0),
        "interruptRequested": str(manifest.get("interruptRequested") or ""),
        "balanceSnapshots": manifest.get("balanceSnapshots") if isinstance(manifest.get("balanceSnapshots"), list) else [],
        "questions": manifest.get("questions") if isinstance(manifest.get("questions"), list) else [],
        "questionItems": manifest.get("questionItems") if isinstance(manifest.get("questionItems"), list) else [],
    }
    try:
        evaluation = load_evaluation_record(str(summary["planId"]), str(summary["runId"]))
        evaluation_state = evaluation.get("evaluationState") if isinstance(evaluation.get("evaluationState"), dict) else {}
        scores = evaluation_state.get("scores") if isinstance(evaluation_state.get("scores"), dict) else {}
        score_items = [item for group_map in scores.values() if isinstance(group_map, dict) for item in group_map.values() if isinstance(item, dict)]
        summary["evaluationStatus"] = str(evaluation_state.get("status") or "idle")
        summary["evaluatedGroups"] = sum(1 for item in score_items if item.get("status") in {"done", "error"})
        summary["totalEvaluations"] = len(score_items)
        summary["evaluationUpdatedAt"] = str(evaluation.get("updatedAt") or "")
    except Exception:
        summary["evaluationStatus"] = "idle"
        summary["evaluatedGroups"] = 0
        summary["totalEvaluations"] = 0
        summary["evaluationUpdatedAt"] = ""
    return summary


def output_state_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    round_questions: dict[str, str] = {}
    output_rounds: dict[str, dict[str, Any]] = {}
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    for round_key, round_data in rounds.items():
        if not isinstance(round_data, dict):
            continue
        question = str(round_data.get("question") or "")
        question_item = round_data.get("questionItem") if isinstance(round_data.get("questionItem"), dict) else {}
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
                "questionItem": group_output.get("questionItem") if isinstance(group_output.get("questionItem"), dict) else question_item,
                "outputText": str(group_output.get("outputText") or group_output.get("message") or ""),
                "streamingText": "",
                "status": str(group_output.get("status") or "error"),
            }
    round_question_items = {
        str(round_key): round_data.get("questionItem")
        for round_key, round_data in rounds.items()
        if isinstance(round_data, dict) and isinstance(round_data.get("questionItem"), dict)
    }
    return {"roundQuestions": round_questions, "roundQuestionItems": round_question_items, "rounds": output_rounds}


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
    evaluation = load_evaluation_record(plan_id, run_id)
    return {
        "run": summarize_manifest(manifest),
        "outputState": output_state_from_manifest(manifest),
        "evaluationState": evaluation.get("evaluationState") or default_evaluation_state(),
        "evaluationRecord": evaluation,
        "manifest": manifest,
    }


def create_manifest(plan_id: str, run_id: str, run_count: int, concurrency: int, question_items: list[dict[str, str]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    created_at = now_iso()
    selected_questions = sample_run_questions(question_items, run_count)
    rounds: dict[str, Any] = {}
    for round_index in range(1, run_count + 1):
        question_item = selected_questions[round_index - 1]
        question = str(question_item.get("questionText") or "")
        rounds[str(round_index)] = {
            "question": question,
            "questionItem": question_item,
            "groups": {
                str(group["groupId"]): {
                    "groupId": str(group["groupId"]),
                    "groupLabel": str(group.get("label") or ""),
                    "question": question,
                    "questionItem": question_item,
                    "status": "pending",
                    "outputText": "",
                    "resultFile": "",
                }
                for group in groups
            },
        }
    return {
        "runId": run_id,
        "name": make_run_name(plan_id, run_count, concurrency),
        "planId": plan_id,
        "status": "running",
        "createdAt": created_at,
        "updatedAt": created_at,
        "runCount": run_count,
        "concurrency": concurrency,
        "questions": [str(item.get("questionText") or "") for item in selected_questions],
        "questionItems": selected_questions,
        "questionPoolSize": len(question_items),
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
    question_item: dict[str, Any],
    output_dir: Path,
    manifest: dict[str, Any],
    manifest_lock: threading.Lock,
    run_control: dict[str, Any] | None = None,
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
        "--timeout",
        str(EXPERIMENT_PIPELINE_TIMEOUT),
        "--stream-events",
        *list(group.get("extraArgs") or []),
    ]

    def safe_send(event: str, data: object) -> None:
        try:
            with send_lock:
                send_sse(handler, event, data)
        except Exception:
            return

    def update_manifest_group(patch: dict[str, Any]) -> None:
        round_key = str(round_index)
        with manifest_lock:
            round_data = manifest.setdefault("rounds", {}).setdefault(round_key, {"question": question, "questionItem": question_item, "groups": {}})
            round_data.setdefault("questionItem", question_item)
            group_data = round_data.setdefault("groups", {}).setdefault(group_id, {})
            group_data.update(patch)
            manifest["status"] = "done" if all_groups_completed(manifest) else "running"
            save_manifest(manifest)

    update_manifest_group({"status": "running", "startedAt": now_iso(), "question": question, "questionItem": question_item, "groupLabel": group.get("label")})
    safe_send("experiment_group_started", {"planId": plan_id, "round": round_index, "runCount": run_count, "groupId": group_id, "groupLabel": group.get("label"), "question": question, "questionItem": question_item})
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=os.environ.copy())
    if run_control is not None:
        with RUN_CONTROLS_LOCK:
            processes = run_control.setdefault("processes", set())
            processes.add(process)
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
    if run_control is not None:
        with RUN_CONTROLS_LOCK:
            processes = run_control.setdefault("processes", set())
            processes.discard(process)
    if run_control is not None and run_control.get("mode") == "force" and return_code != 0:
        message = "实验已强制中断，当前断点已保存。"
        update_manifest_group({"status": "terminated", "message": message, "finishedAt": now_iso()})
        safe_send("experiment_group_done", {"planId": plan_id, "round": round_index, "runCount": run_count, "groupId": group_id, "groupLabel": group.get("label"), "question": question, "questionItem": question_item, "outputText": f"【强制中断】{message}", "resultFile": "", "status": "terminated"})
        return {"groupId": group_id, "status": "terminated", "message": message}
    if return_code != 0:
        message = "\n".join(logs).strip() or f"experiment group exited with code {return_code}"
        update_manifest_group({"status": "error", "message": message, "finishedAt": now_iso()})
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
    payload = {"planId": plan_id, "round": round_index, "runCount": run_count, "groupId": group_id, "groupLabel": group.get("label"), "question": question, "questionItem": question_item, "outputText": output_text, "resultFile": str(result_file) if result_file else "", "status": status}
    update_manifest_group({"status": status, "questionItem": question_item, "outputText": output_text, "resultFile": str(result_file) if result_file else "", "finishedAt": now_iso()})
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

    question_items = normalize_question_items(body)
    if not question_items:
        send_sse(handler, "experiment_error", {"message": "questions is required"})
        return

    requested_run_count = max(1, int(body.get("runCount") or 1))
    run_id = str(body.get("runId") or "").strip()
    if run_id:
        manifest = load_manifest(plan_id, run_id)
        run_count = int(manifest.get("runCount") or requested_run_count)
        saved_items = manifest.get("questionItems") if isinstance(manifest.get("questionItems"), list) else []
        question_items = [item for item in saved_items if isinstance(item, dict) and str(item.get("questionText") or "").strip()] or question_items
    else:
        run_id = make_run_id(plan_id)
        run_count = requested_run_count
        manifest = create_manifest(plan_id, run_id, run_count, clamp_concurrency(int(body.get("concurrency") or 1), run_count, len(groups)), question_items, groups)
        save_manifest(manifest)

    concurrency = clamp_concurrency(int(body.get("concurrency") or manifest.get("concurrency") or 1), run_count, len(groups))
    manifest["concurrency"] = concurrency
    manifest["name"] = make_run_name(plan_id, run_count, concurrency)
    manifest["status"] = "running"
    manifest["interruptRequested"] = ""
    save_manifest(manifest)
    run_control = register_run_control(plan_id, run_id)
    output_dir = run_dir(plan_id, run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    send_lock = threading.Lock()
    manifest_lock = threading.Lock()
    all_total = run_count * len(groups)
    completed = 0

    def safe_send(event: str, data: object) -> None:
        try:
            with send_lock:
                send_sse(handler, event, data)
        except Exception:
            return

    safe_send("experiment_stage_started", {"planId": plan_id, "runId": run_id, "stage": stage, "runCount": run_count, "concurrency": concurrency, "total": all_total, "run": summarize_manifest(manifest), "outputState": output_state_from_manifest(manifest)})
    tasks = []
    for round_index in range(1, run_count + 1):
        round_key = str(round_index)
        fallback_question_item = question_items[(round_index - 1) % len(question_items)]
        round_data = manifest.setdefault("rounds", {}).setdefault(round_key, {"question": fallback_question_item.get("questionText", ""), "questionItem": fallback_question_item, "groups": {}})
        saved_question_item = round_data.get("questionItem") if isinstance(round_data.get("questionItem"), dict) else None
        question = str(round_data.get("question") or (saved_question_item or fallback_question_item).get("questionText") or "")
        question_item = saved_question_item or {"questionId": "", "questionText": question, "groupId": "", "groupCode": "", "groupName": "", "expectedBehavior": "", "category": ""}
        round_data["question"] = question
        round_data["questionItem"] = question_item
        safe_send("experiment_round_started", {"planId": plan_id, "runId": run_id, "stage": stage, "round": round_index, "runCount": run_count, "question": question, "questionItem": question_item})
        for group in groups:
            group_id = str(group["groupId"])
            group_data = round_data.setdefault("groups", {}).setdefault(group_id, {"groupId": group_id, "groupLabel": group.get("label"), "question": question, "questionItem": question_item, "status": "pending", "outputText": ""})
            group_data.setdefault("questionItem", question_item)
            if group_data.get("status") in {"done", "terminated"} and str(group_data.get("outputText") or ""):
                continue
            tasks.append((round_index, question, question_item, group))

    total = len(tasks)
    if total == 0:
        manifest["status"] = "done"
        save_manifest(manifest)
        safe_send("experiment_progress", {"planId": plan_id, "runId": run_id, "stage": stage, "completed": 0, "total": 0, "progress": 100})
        safe_send("experiment_stage_done", {"planId": plan_id, "runId": run_id, "stage": stage, "completed": 0, "total": 0, "progress": 100, "outputState": output_state_from_manifest(manifest)})
        return

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            pending_iter = iter(tasks)
            future_map: dict[Any, tuple[int, dict[str, Any]]] = {}

            def submit_next() -> bool:
                if run_control.get("mode") in {"safe", "force"}:
                    return False
                try:
                    round_index, question, question_item, group = next(pending_iter)
                except StopIteration:
                    return False
                future = executor.submit(run_one_group, handler, send_lock, plan_id=plan_id, group=group, round_index=round_index, run_count=run_count, question=question, question_item=question_item, output_dir=output_dir, manifest=manifest, manifest_lock=manifest_lock, run_control=run_control)
                future_map[future] = (round_index, group)
                return True

            for _ in range(concurrency):
                if not submit_next():
                    break

            while future_map:
                for future in as_completed(list(future_map.keys()), timeout=None):
                    completed += 1
                    round_index, group = future_map.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        safe_send("experiment_group_error", {"planId": plan_id, "round": round_index, "groupId": group.get("groupId"), "message": str(exc)})
                    safe_send("experiment_progress", {"planId": plan_id, "runId": run_id, "stage": stage, "completed": completed, "total": total, "progress": round(completed / total * 100), "run": summarize_manifest(manifest)})
                    round_key = str(round_index)
                    round_data = manifest.get("rounds", {}).get(round_key) if isinstance(manifest.get("rounds"), dict) else None
                    groups_done = False
                    if isinstance(round_data, dict):
                        groups = round_data.get("groups") if isinstance(round_data.get("groups"), dict) else {}
                        groups_done = bool(groups) and all(isinstance(item, dict) and item.get("status") in {"done", "terminated"} for item in groups.values())
                    if groups_done:
                        with manifest_lock:
                            captured = manifest.setdefault("balanceRoundFinished", [])
                            if isinstance(captured, list) and round_index not in captured:
                                append_balance_snapshot(manifest, capture_balance_snapshot(stage, round_index, "round_finished"))
                                captured.append(round_index)
                                save_manifest(manifest)
                    submit_next()
                    break

        final_status = "done" if all_groups_completed(manifest) else "partial"
        if run_control.get("mode") == "safe":
            final_status = "interrupted"
        elif run_control.get("mode") == "force":
            final_status = "interrupted"
        manifest["status"] = final_status
        save_manifest(manifest)
        safe_send("experiment_stage_done", {"planId": plan_id, "runId": run_id, "stage": stage, "completed": completed, "total": total, "progress": round(completed / total * 100), "run": summarize_manifest(manifest), "outputState": output_state_from_manifest(manifest)})
    finally:
        unregister_run_control(plan_id, run_id)
