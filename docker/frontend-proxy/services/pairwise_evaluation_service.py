from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.experiment_service import (
    load_manifest,
    load_pairwise_evaluation_record,
    now_iso,
    run_dir,
    save_pairwise_evaluation_record,
)


PAIRWISE_EVALUATION_ENDPOINT = os.getenv("PAIRWISE_EVALUATION_ENDPOINT", "https://api.deepseek.com/chat/completions")
PAIRWISE_EVALUATION_MODEL = os.getenv("PAIRWISE_EVALUATION_MODEL", "deepseek-v4-flash")
PAIRWISE_EVALUATION_KEY_FILE = Path(os.getenv("PAIRWISE_EVALUATION_KEY_FILE", "/run/fastgpt_keys/deepseek_api_key"))

PAIRWISE_RUNS: dict[str, dict[str, Any]] = {}
PAIRWISE_RUNS_LOCK = threading.Lock()

PLAN_GROUPS: dict[str, dict[str, str]] = {
    "boundary": {
        "A-完整流程": "control",
        "B-移除边界校验": "exp-no-boundary",
        "C-关键词边界校验": "exp-keyword-boundary",
    },
    "disambiguation": {
        "A-完整流程": "control",
        "B-移除主体判定": "exp-drop-subject-judgement",
        "C-关键词主体判定": "exp-keyword-subject-judgement",
    },
    "graphTemplate": {
        "A-完整流程": "control",
        "B-移除图谱": "exp-no-graph",
        "C-移除模板": "exp-no-template",
    },
    "multiFault": {
        "A-完整多故障链路": "control",
        "B-单故障普通链路": "exp-single-fault",
        "C-仅主故障图谱链路": "exp-detect-no-per-fault-graph",
    },
}

PLAN_PURPOSES: dict[str, str] = {
    "boundary": "比较完整流程、移除边界校验、关键词边界校验三组在错误输入阻断、支持设备识别和故障场景放行方面的差异。",
    "disambiguation": "比较完整流程、移除主体判定、关键词主体判定三组在设备主体识别、故障节点匹配、主次关系处理和处置内容聚焦方面的差异。",
    "graphTemplate": "比较完整流程、移除图谱、移除模板三组在图谱事实覆盖、模板章节约束、章节归位和处置闭环方面的差异。",
    "multiFault": "比较完整多故障链路、单故障普通链路、仅主故障图谱链路三组在多故障拆解、逐故障图谱召回、主次优先级和融合处置闭环方面的差异。",
}

PLAN_DIMENSIONS: dict[str, list[str]] = {
    "boundary": [
        "输入边界判定：是否正确阻断无关输入、不支持设备或明显设备故障错配。",
        "链路行为：该放行时是否放行，该终止时是否终止，是否避免错误问题进入预案生成。",
        "提示质量：边界提示是否简洁、准确，能否指导用户修正输入。",
        "抗误判能力：是否避免只按关键词机械放行或机械拦截。",
        "实验组差异识别：能否识别移除边界校验或关键词规则带来的典型缺陷。",
    ],
    "disambiguation": [
        "故障主体识别：是否识别真正故障主体，而不是位置、载体、告警来源或相邻设备。",
        "故障类型与知识库一致性：故障节点、图谱空间和正文主体是否一致。",
        "主次关系与因果链处理：是否正确区分主故障、伴随故障、受影响对象和处置优先级。",
        "处置内容聚焦度：检查、隔离、抢修和恢复验证是否围绕真实故障主体展开。",
        "实验组差异识别：能否识别主体漂移、关键词误判、图谱错查等缺陷。",
    ],
    "graphTemplate": [
        "图谱事实覆盖与准确性：是否给出与故障主体匹配的原因、现象、措施、后果、风险和资源。",
        "模板结构完整性与顺序：是否保持正式预案结构，章节顺序是否合理。",
        "章节边界与内容归位：检查确认、故障定位、抢修措施、恢复验证是否分开归位，是否存在串章和重复堆叠。",
        "处置闭环与可执行性：是否形成检查确认、隔离抢修、风险控制、响应终止和恢复验证闭环。",
        "实验组差异识别：能否识别移除图谱导致事实泛化、移除模板导致结构失控等缺陷。",
    ],
    "multiFault": [
        "多故障识别与拆解：是否识别主故障、伴随故障和次生风险。",
        "逐故障图谱事实覆盖：是否分别召回各故障的原因、现象、措施、风险和资源。",
        "主次因果链与处置优先级：是否说明主次关系、诱发关系和先后处置顺序。",
        "融合处置闭环与可执行性：是否把多故障素材融合为完整、可执行的预案，而不是简单堆叠。",
        "实验组差异识别：能否识别单故障链路或仅主故障图谱链路造成的覆盖不足。",
    ],
}


def read_key(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"API key file is empty: {path}")
    return value


def pairwise_run_key(plan_id: str, run_id: str) -> str:
    return f"{plan_id}:{run_id}"


def is_pairwise_running(plan_id: str, run_id: str) -> bool:
    with PAIRWISE_RUNS_LOCK:
        return pairwise_run_key(plan_id, run_id) in PAIRWISE_RUNS


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
        parts.append(f"{heading}\n{text}" if heading else text)
    return "\n\n".join(parts).strip()


def find_pipeline_result(group_dir: Path) -> Path | None:
    files = sorted(group_dir.glob("*/pipeline_result.json"), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


def load_round_candidates(run_base_dir: Path, plan_id: str, round_no: int) -> tuple[str, dict[str, str]]:
    groups = PLAN_GROUPS.get(plan_id)
    if not groups:
        raise RuntimeError(f"unsupported planId: {plan_id}")
    round_dir = run_base_dir / f"round_{round_no:03d}"
    if not round_dir.exists():
        raise RuntimeError(f"round directory not found: {round_dir}")

    question = ""
    candidates: dict[str, str] = {}
    missing: list[str] = []
    for label, group_id in groups.items():
        result_path = find_pipeline_result(round_dir / group_id)
        if not result_path:
            missing.append(label)
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        question = question or str(result.get("question") or "")
        text = combine_output_text(result)
        if text:
            candidates[label] = text
        else:
            missing.append(label)
    if missing:
        raise RuntimeError(f"round {round_no} missing candidate output: {', '.join(missing)}")
    return question, candidates


def build_messages(plan_id: str, question: str, candidates: dict[str, str]) -> list[dict[str, str]]:
    system_prompt = (
        "你是电气设备应急预案质量评审专家。你必须输出合法 JSON 对象，不要输出 Markdown，"
        "不要使用 ```json 代码块。请进行相对比较，而不是孤立地做绝对评分。JSON 输出必须符合用户给出的格式样例。"
    )
    dimensions = "\n".join(f"{idx}. {item}" for idx, item in enumerate(PLAN_DIMENSIONS[plan_id], start=1))
    candidate_text = "\n\n".join(f"【候选预案{label}】\n{text}" for label, text in candidates.items())
    labels = list(candidates.keys())
    user_prompt = f"""请比较同一故障场景下三份候选预案。注意：本请求要求 JSON 输出。

【故障场景】
{question}

【实验目的】
{PLAN_PURPOSES[plan_id]}

【分项评价维度】
{dimensions}

【评审要求】
- 先比较三份候选预案在各维度上的相对优劣，再给总体排序。
- 不要因为文本更长、语气正式或标签更多就判为更好。
- 可以给 1-10 分辅助分数，但分数必须服从前面的相对排序，只表示相对差距。
- margin 字段只能使用：明显、中等、轻微、基本相当。
- 必须输出合法 JSON 对象本身。

{candidate_text}

EXAMPLE JSON OUTPUT:
{{
  "dimension_comparison": [
    {{"dimension": "图谱事实覆盖与准确性", "ranking": {json.dumps(labels, ensure_ascii=False)}, "reason": "简要说明相对排序依据。"}}
  ],
  "overall_ranking": {json.dumps(labels, ensure_ascii=False)},
  "pairwise_preferences": [
    {{"better": "{labels[0]}", "worse": "{labels[1]}", "margin": "明显", "reason": "简要说明胜出原因。"}}
  ],
  "relative_scores": {{{', '.join(json.dumps(label, ensure_ascii=False) + ': 0.0' for label in labels)}}},
  "main_findings": ["主要发现。"],
  "summary": "总体结论。"
}}"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def request_pairwise_json(messages: list[dict[str, str]], timeout: int) -> dict[str, Any]:
    payload = {
        "model": PAIRWISE_EVALUATION_MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        PAIRWISE_EVALUATION_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_key(PAIRWISE_EVALUATION_KEY_FILE)}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek URL error: {exc}") from exc
    content = str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "")
    if not content.strip():
        raise RuntimeError("DeepSeek returned empty content")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DeepSeek returned invalid JSON: {content[:300]}") from exc
    return {
        "elapsedSec": round(time.perf_counter() - started, 3),
        "contentChars": len(content),
        "evaluation": parsed,
        "raw": body,
    }


def normalize_pairwise_evaluation(plan_id: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    label_to_group = PLAN_GROUPS.get(plan_id, {})

    def map_label(value: str) -> str:
        return label_to_group.get(str(value), str(value))

    normalized = dict(evaluation)
    ranking = evaluation.get("overall_ranking")
    if isinstance(ranking, list):
        normalized["overall_ranking_group_ids"] = [map_label(str(item)) for item in ranking]
    relative_scores = evaluation.get("relative_scores")
    if isinstance(relative_scores, dict):
        normalized["relative_scores_group_ids"] = {
            map_label(str(label)): score for label, score in relative_scores.items()
        }
    pairwise_preferences = evaluation.get("pairwise_preferences")
    if isinstance(pairwise_preferences, list):
        normalized["pairwise_preferences_group_ids"] = [
            {
                **item,
                "better_group_id": map_label(str(item.get("better") or "")),
                "worse_group_id": map_label(str(item.get("worse") or "")),
            }
            for item in pairwise_preferences
            if isinstance(item, dict)
        ]
    dimension_comparison = evaluation.get("dimension_comparison")
    if isinstance(dimension_comparison, list):
        normalized["dimension_comparison_group_ids"] = [
            {
                **item,
                "ranking_group_ids": [map_label(str(label)) for label in item.get("ranking", [])] if isinstance(item, dict) and isinstance(item.get("ranking"), list) else [],
            }
            for item in dimension_comparison
            if isinstance(item, dict)
        ]
    return normalized


def compute_summary_stats(results: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {}
    completed_items = [item for item in results.values() if isinstance(item, dict) and item.get("status") == "done"]
    total = len(completed_items)
    for item in completed_items:
        ranking = item.get("overallRanking")
        if not isinstance(ranking, list):
            continue
        for index, group_id in enumerate(ranking[:3], start=1):
            group_key = str(group_id)
            stat = counts.setdefault(group_key, {"rank1": 0, "rank2": 0, "rank3": 0})
            stat[f"rank{index}"] += 1
    summary: dict[str, Any] = {}
    for group_id, stat in counts.items():
        summary[group_id] = {
            **stat,
            "rank1Pct": round(stat["rank1"] / total * 100, 1) if total else 0.0,
            "rank2Pct": round(stat["rank2"] / total * 100, 1) if total else 0.0,
            "rank3Pct": round(stat["rank3"] / total * 100, 1) if total else 0.0,
        }
    return summary


def build_round_result(plan_id: str, round_no: int, question: str, candidates: dict[str, str], result: dict[str, Any]) -> dict[str, Any]:
    normalized_eval = normalize_pairwise_evaluation(plan_id, result["evaluation"] if isinstance(result.get("evaluation"), dict) else {})
    overall_ranking = normalized_eval.get("overall_ranking_group_ids")
    relative_scores = normalized_eval.get("relative_scores_group_ids")
    return {
        "status": "done",
        "round": round_no,
        "question": question,
        "candidateChars": {PLAN_GROUPS[plan_id].get(label, label): len(text) for label, text in candidates.items()},
        "inputChars": sum(len(message["content"]) for message in build_messages(plan_id, question, candidates)),
        "elapsedSec": result["elapsedSec"],
        "contentChars": result["contentChars"],
        "overallRanking": overall_ranking if isinstance(overall_ranking, list) else [],
        "relativeScores": relative_scores if isinstance(relative_scores, dict) else {},
        "mainFindings": normalized_eval.get("main_findings") if isinstance(normalized_eval.get("main_findings"), list) else [],
        "summary": str(normalized_eval.get("summary") or ""),
        "evaluation": normalized_eval,
        "evaluatedAt": now_iso(),
    }


def pending_rounds(manifest: dict[str, Any], pairwise_state: dict[str, Any], *, resume: bool) -> list[int]:
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    eligible: list[int] = []
    for round_key, round_data in rounds.items():
        if not str(round_key).isdigit() or not isinstance(round_data, dict):
            continue
        groups = round_data.get("groups") if isinstance(round_data.get("groups"), dict) else {}
        if groups and all(isinstance(item, dict) and item.get("status") in {"done", "terminated"} and str(item.get("outputText") or "").strip() for item in groups.values()):
            eligible.append(int(round_key))
    eligible.sort()
    if not resume:
        return eligible
    results = pairwise_state.get("results") if isinstance(pairwise_state.get("results"), dict) else {}
    errors = pairwise_state.get("errors") if isinstance(pairwise_state.get("errors"), dict) else {}
    retry_rounds = [round_no for round_no in eligible if str(round_no) in errors]
    fresh_rounds = [round_no for round_no in eligible if str(round_no) not in results and str(round_no) not in errors]
    return retry_rounds + fresh_rounds


def run_pairwise_round(plan_id: str, run_id: str, round_no: int, timeout: int) -> dict[str, Any]:
    run_base_dir = run_dir(plan_id, run_id)
    question, candidates = load_round_candidates(run_base_dir, plan_id, round_no)
    messages = build_messages(plan_id, question, candidates)
    result = request_pairwise_json(messages, timeout)
    return build_round_result(plan_id, round_no, question, candidates, result)


def _update_state(plan_id: str, run_id: str, mutate: callable) -> dict[str, Any]:
    record = load_pairwise_evaluation_record(plan_id, run_id)
    state = record.get("pairwiseEvaluationState") if isinstance(record.get("pairwiseEvaluationState"), dict) else {}
    if not state:
        state = {
            "status": "idle",
            "progress": 0,
            "concurrency": 3,
            "activeTasks": [],
            "results": {},
            "errors": {},
            "summaryStats": {},
        }
    mutate(state)
    saved = save_pairwise_evaluation_record(plan_id, run_id, state)
    return saved.get("pairwiseEvaluationState") if isinstance(saved.get("pairwiseEvaluationState"), dict) else state


def start_pairwise_evaluation_run(plan_id: str, run_id: str, *, concurrency: int = 3, resume: bool = True, timeout: int = 300) -> dict[str, Any]:
    load_manifest(plan_id, run_id)
    with PAIRWISE_RUNS_LOCK:
        if pairwise_run_key(plan_id, run_id) in PAIRWISE_RUNS:
            return load_pairwise_evaluation_record(plan_id, run_id)
        PAIRWISE_RUNS[pairwise_run_key(plan_id, run_id)] = {
            "startedAt": now_iso(),
            "concurrency": max(1, int(concurrency or 1)),
            "resume": bool(resume),
            "timeout": max(30, int(timeout or 300)),
        }

    manifest = load_manifest(plan_id, run_id)
    initial_state = _update_state(
        plan_id,
        run_id,
        lambda state: state.update({
            "status": "running",
            "progress": 0,
            "concurrency": max(1, int(concurrency or 1)),
            "activeTasks": [],
            "results": state.get("results") if resume and isinstance(state.get("results"), dict) else {},
            "errors": state.get("errors") if resume and isinstance(state.get("errors"), dict) else {},
            "summaryStats": state.get("summaryStats") if resume and isinstance(state.get("summaryStats"), dict) else {},
        }),
    )

    def worker() -> None:
        try:
            pairwise_state = load_pairwise_evaluation_record(plan_id, run_id).get("pairwiseEvaluationState") or {}
            rounds = pending_rounds(manifest, pairwise_state if isinstance(pairwise_state, dict) else {}, resume=resume)
            total = len(rounds)
            _update_state(plan_id, run_id, lambda state: state.update({"progress": 100 if total == 0 else 0}))
            if total == 0:
                _update_state(plan_id, run_id, lambda state: state.update({"status": "done", "activeTasks": []}))
                return

            completed = 0
            active_rounds: set[int] = set()
            timeout_value = max(30, int(timeout or 300))

            def set_active_tasks(state: dict[str, Any]) -> None:
                state["activeTasks"] = [
                    {"round": round_no, "status": "running", "startedAt": now_iso()}
                    for round_no in sorted(active_rounds)
                ]

            with ThreadPoolExecutor(max_workers=max(1, int(concurrency or 1))) as executor:
                pending_iter = iter(rounds)
                future_map: dict[Any, int] = {}

                def submit_next() -> bool:
                    try:
                        round_no = next(pending_iter)
                    except StopIteration:
                        return False
                    active_rounds.add(round_no)
                    _update_state(plan_id, run_id, set_active_tasks)
                    future = executor.submit(run_pairwise_round, plan_id, run_id, round_no, timeout_value)
                    future_map[future] = round_no
                    return True

                for _ in range(max(1, int(concurrency or 1))):
                    if not submit_next():
                        break

                while future_map:
                    for future in as_completed(list(future_map.keys())):
                        round_no = future_map.pop(future)
                        active_rounds.discard(round_no)
                        try:
                            payload = future.result()
                            def apply_done(state: dict[str, Any]) -> None:
                                results = state.setdefault("results", {})
                                if isinstance(results, dict):
                                    results[str(round_no)] = payload
                                errors = state.setdefault("errors", {})
                                if isinstance(errors, dict):
                                    errors.pop(str(round_no), None)
                                state["summaryStats"] = compute_summary_stats(results if isinstance(results, dict) else {})
                            _update_state(plan_id, run_id, apply_done)
                        except Exception as exc:
                            def apply_error(state: dict[str, Any]) -> None:
                                errors = state.setdefault("errors", {})
                                if isinstance(errors, dict):
                                    errors[str(round_no)] = {"message": str(exc), "updatedAt": now_iso()}
                            _update_state(plan_id, run_id, apply_error)
                        completed += 1
                        progress = round(completed / total * 100)
                        _update_state(
                            plan_id,
                            run_id,
                            lambda state: (
                                state.update({"progress": progress}),
                                set_active_tasks(state),
                            ),
                        )
                        submit_next()
                        break

            final_state = load_pairwise_evaluation_record(plan_id, run_id).get("pairwiseEvaluationState") or {}
            final_errors = final_state.get("errors") if isinstance(final_state, dict) and isinstance(final_state.get("errors"), dict) else {}
            _update_state(
                plan_id,
                run_id,
                lambda state: state.update({
                    "status": "done" if not final_errors else "partial",
                    "progress": 100,
                    "activeTasks": [],
                }),
            )
        finally:
            with PAIRWISE_RUNS_LOCK:
                PAIRWISE_RUNS.pop(pairwise_run_key(plan_id, run_id), None)

    thread = threading.Thread(target=worker, name=f"pairwise-eval-{plan_id}-{run_id}", daemon=True)
    thread.start()
    return {"planId": plan_id, "runId": run_id, "pairwiseEvaluationState": initial_state}
