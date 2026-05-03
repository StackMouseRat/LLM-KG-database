#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return 0x4E00 <= code <= 0x9FFF


def tokenize(text: str) -> list[str]:
    text = text or ""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if is_cjk(ch):
            if buf:
                part = "".join(buf).strip().lower()
                if part:
                    tokens.extend(re.findall(r"[a-z0-9]+", part))
                buf = []
            tokens.append(ch)
        else:
            buf.append(ch)
    if buf:
        part = "".join(buf).strip().lower()
        if part:
            tokens.extend(re.findall(r"[a-z0-9]+", part))
    return tokens


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text or "")


def ngrams(items: list[str], n: int) -> Counter[tuple[str, ...]]:
    if len(items) < n:
        return Counter()
    return Counter(tuple(items[i : i + n]) for i in range(len(items) - n + 1))


def rouge_l_f1_fast(reference: str, candidate: str) -> float:
    ref = tokenize(reference)
    cand = tokenize(candidate)
    if not ref or not cand:
        return 0.0
    # SequenceMatcher is much faster than exact DP LCS on long Chinese plans.
    matcher = SequenceMatcher(None, ref, cand, autojunk=False)
    lcs_like = sum(block.size for block in matcher.get_matching_blocks())
    p = lcs_like / len(cand)
    r = lcs_like / len(ref)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def chrf_pp(reference: str, candidate: str, char_order: int = 6, word_order: int = 2, beta: float = 2.0) -> float:
    ref_chars = list(reference or "")
    cand_chars = list(candidate or "")
    ref_words = words(reference)
    cand_words = words(candidate)

    precisions: list[float] = []
    recalls: list[float] = []

    def add_orders(ref_items: list[str], cand_items: list[str], max_order: int) -> None:
        for n in range(1, max_order + 1):
            ref_ng = ngrams(ref_items, n)
            cand_ng = ngrams(cand_items, n)
            overlap = sum(min(count, ref_ng.get(ng, 0)) for ng, count in cand_ng.items())
            precisions.append(overlap / sum(cand_ng.values()) if cand_ng else 0.0)
            recalls.append(overlap / sum(ref_ng.values()) if ref_ng else 0.0)

    add_orders(ref_chars, cand_chars, char_order)
    add_orders(ref_words, cand_words, word_order)

    precision = sum(precisions) / len(precisions) if precisions else 0.0
    recall = sum(recalls) / len(recalls) if recalls else 0.0
    if precision == 0.0 and recall == 0.0:
        return 0.0
    beta2 = beta * beta
    return (1 + beta2) * precision * recall / (beta2 * precision + recall)


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def rank(values: list[float]) -> list[float]:
    pairs = sorted(enumerate(values), key=lambda x: x[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][1] == pairs[i][1]:
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            out[pairs[k][0]] = avg
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    return pearson(rank(xs), rank(ys))


def extract_output_text(manifest: dict[str, Any], round_id: str, group_id: str) -> str:
    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    round_data = rounds.get(round_id) if isinstance(rounds.get(round_id), dict) else {}
    groups = round_data.get("groups") if isinstance(round_data.get("groups"), dict) else {}
    group = groups.get(group_id) if isinstance(groups.get(group_id), dict) else {}
    return str(group.get("outputText") or "")


def extract_llm_score(evaluation: dict[str, Any], round_id: str, group_id: str) -> float | None:
    st = evaluation.get("evaluationState") if isinstance(evaluation.get("evaluationState"), dict) else {}
    scores = st.get("scores") if isinstance(st.get("scores"), dict) else {}
    round_map = scores.get(round_id) if isinstance(scores.get(round_id), dict) else {}
    rec = round_map.get(group_id) if isinstance(round_map.get(group_id), dict) else {}
    structured = rec.get("structuredEvaluation") if isinstance(rec.get("structuredEvaluation"), dict) else {}
    value = structured.get("score", rec.get("score"))
    try:
        if value is None:
            return None
        f = float(value)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def iter_rows(runs_root: Path, reference_group: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(runs_root.glob("*/*")):
        manifest_path = run_dir / "experiment_run.json"
        eval_path = run_dir / "experiment_evaluation.json"
        if not manifest_path.exists() or not eval_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
        rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
        for round_id in sorted(rounds.keys(), key=lambda x: int(x)):
            ref_text = extract_output_text(manifest, round_id, reference_group)
            if not ref_text.strip():
                continue
            groups = rounds[round_id].get("groups") if isinstance(rounds[round_id].get("groups"), dict) else {}
            for group_id, group_data in groups.items():
                if group_id == reference_group:
                    continue
                cand = str(group_data.get("outputText") or "")
                if not cand.strip():
                    continue
                score = extract_llm_score(evaluation, round_id, group_id)
                if score is None:
                    continue
                rows.append(
                    {
                        "planId": manifest.get("planId"),
                        "runId": manifest.get("runId"),
                        "round": int(round_id),
                        "groupId": group_id,
                        "question": str(rounds[round_id].get("question") or ""),
                        "reference": ref_text,
                        "candidate": cand,
                        "llmJudgeScore": score,
                    }
                )
    return rows


def add_bertscore(rows: list[dict[str, Any]], model_type: str, batch_size: int) -> str:
    try:
        from bert_score import score as bert_score
    except Exception as exc:
        return f"BERTScore skipped: bert_score is not available ({type(exc).__name__})."

    candidates = [row["candidate"] for row in rows]
    references = [row["reference"] for row in rows]
    _, _, f1 = bert_score(candidates, references, lang="zh", model_type=model_type, batch_size=batch_size, verbose=True)
    for row, value in zip(rows, f1.tolist()):
        row["bertscoreF1"] = float(value)
    return "BERTScore completed."


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_keys = ["rougeL", "chrfpp"]
    if any("bertscoreF1" in row for row in rows):
        metric_keys.append("bertscoreF1")

    def avg(key: str, subset: list[dict[str, Any]]) -> float:
        vals = [float(row[key]) for row in subset if row.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    by_run: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["planId"]), str(row["runId"]))].append(row)
    for (plan_id, run_id), subset in grouped.items():
        llm = [float(row["llmJudgeScore"]) for row in subset]
        by_run[f"{plan_id}/{run_id}"] = {
            "pairs": len(subset),
            "llmJudgeAvg": avg("llmJudgeScore", subset),
            **{key: avg(key, subset) for key in metric_keys},
            "corr": {
                f"pearson_{key}_vs_llmJudge": pearson([float(row[key]) for row in subset], llm)
                for key in metric_keys
            }
            | {
                f"spearman_{key}_vs_llmJudge": spearman([float(row[key]) for row in subset], llm)
                for key in metric_keys
            },
        }

    llm_all = [float(row["llmJudgeScore"]) for row in rows]
    return {
        "pairs": len(rows),
        "overall": {
            "llmJudgeAvg": avg("llmJudgeScore", rows),
            **{key: avg(key, rows) for key in metric_keys},
            "corr": {
                f"pearson_{key}_vs_llmJudge": pearson([float(row[key]) for row in rows], llm_all)
                for key in metric_keys
            }
            | {
                f"spearman_{key}_vs_llmJudge": spearman([float(row[key]) for row in rows], llm_all)
                for key in metric_keys
            },
        },
        "byRun": by_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="First-batch ROUGE-L / chrF++ / optional BERTScore comparator")
    parser.add_argument("--runs-root", default="docs/project_changes/frontend_experiment_runs")
    parser.add_argument("--reference-group", default="control")
    parser.add_argument("--out", default="tmp/metrics/first_batch_metrics.json")
    parser.add_argument("--with-bertscore", action="store_true")
    parser.add_argument("--bertscore-model", default="bert-base-chinese")
    parser.add_argument("--bertscore-batch-size", type=int, default=2)
    args = parser.parse_args()

    rows = iter_rows(Path(args.runs_root), args.reference_group)
    for row in rows:
        row["rougeL"] = rouge_l_f1_fast(row["reference"], row["candidate"])
        row["chrfpp"] = chrf_pp(row["reference"], row["candidate"])
        row["referencePreview"] = row.pop("reference")[:500]
        row["candidatePreview"] = row.pop("candidate")[:500]

    bertscore_status = "BERTScore not requested."
    if args.with_bertscore:
        # Restore full texts for BERTScore from source files to keep default JSON compact.
        full_rows = iter_rows(Path(args.runs_root), args.reference_group)
        for compact, full in zip(rows, full_rows):
            compact["reference"] = full["reference"]
            compact["candidate"] = full["candidate"]
        bertscore_status = add_bertscore(rows, args.bertscore_model, args.bertscore_batch_size)
        for row in rows:
            row.pop("reference", None)
            row.pop("candidate", None)

    report = {
        "referenceGroup": args.reference_group,
        "metrics": ["rougeL", "chrfpp"] + (["bertscoreF1"] if any("bertscoreF1" in r for r in rows) else []),
        "bertscoreStatus": bertscore_status,
        **summarize(rows),
        "rows": rows,
        "notes": [
            "ROUGE-L uses a SequenceMatcher LCS-like approximation for long Chinese plans.",
            "chrF++ is computed as character n-gram order 1-6 plus word n-gram order 1-2 with beta=2.",
            "BERTScore is optional and requires installing bert_score/transformers/torch.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")
    print(json.dumps({"pairs": report["pairs"], "metrics": report["metrics"], "bertscoreStatus": bertscore_status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
