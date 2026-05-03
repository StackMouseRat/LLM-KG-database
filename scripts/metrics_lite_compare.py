#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
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


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def bleu_n(reference: str, candidate: str, n: int) -> float:
    ref = tokenize(reference)
    cand = tokenize(candidate)
    if not cand:
        return 0.0
    c_ngrams = ngrams(cand, n)
    if not c_ngrams:
        return 0.0
    r_ngrams = Counter(ngrams(ref, n))
    c_counts = Counter(c_ngrams)
    hit = 0
    total = sum(c_counts.values())
    for gram, cnt in c_counts.items():
        hit += min(cnt, r_ngrams.get(gram, 0))
    precision = hit / max(total, 1)
    bp = 1.0 if len(cand) > len(ref) else math.exp(1 - (len(ref) / max(len(cand), 1)))
    return bp * precision


def lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
            else:
                cur[j] = max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def rouge_l_f1(reference: str, candidate: str) -> float:
    ref = tokenize(reference)
    cand = tokenize(candidate)
    if not ref or not cand:
        return 0.0
    lcs = lcs_len(ref, cand)
    p = lcs / len(cand)
    r = lcs / len(ref)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


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


def safe_read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
        if math.isfinite(f):
            return f
    except Exception:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Light BLEU/ROUGE vs LLM-as-Judge comparator")
    parser.add_argument("--plan-id", required=True, help="experiment plan id, e.g. disambiguation")
    parser.add_argument("--run-id", required=True, help="experiment run id")
    parser.add_argument("--reference-group", default="control", help="group id used as reference text")
    parser.add_argument("--target-groups", default="", help="comma-separated target groups; default: all non-reference")
    parser.add_argument(
        "--runs-root",
        default="/app/data/frontend_experiment_runs",
        help="experiment runs root dir",
    )
    parser.add_argument("--out", default="", help="optional output json path")
    args = parser.parse_args()

    run_dir = Path(args.runs_root) / args.plan_id / args.run_id
    manifest_path = run_dir / "experiment_run.json"
    eval_path = run_dir / "experiment_evaluation.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    manifest = safe_read_json(manifest_path)
    evaluation = safe_read_json(eval_path) if eval_path.exists() else {}

    rounds = manifest.get("rounds") if isinstance(manifest.get("rounds"), dict) else {}
    any_round = next(iter(rounds.values()), {})
    group_ids = []
    if isinstance(any_round, dict):
        gmap = any_round.get("groups") if isinstance(any_round.get("groups"), dict) else {}
        group_ids = list(gmap.keys())

    if args.target_groups.strip():
        targets = [item.strip() for item in args.target_groups.split(",") if item.strip()]
    else:
        targets = [gid for gid in group_ids if gid != args.reference_group]

    rows: list[dict[str, Any]] = []
    for round_id in sorted(rounds.keys(), key=lambda x: int(x)):
        ref_text = extract_output_text(manifest, round_id, args.reference_group)
        if not ref_text.strip():
            continue
        for gid in targets:
            cand = extract_output_text(manifest, round_id, gid)
            if not cand.strip():
                continue
            row = {
                "round": int(round_id),
                "groupId": gid,
                "bleu1": bleu_n(ref_text, cand, 1),
                "bleu2": bleu_n(ref_text, cand, 2),
                "bleu3": bleu_n(ref_text, cand, 3),
                "bleu4": bleu_n(ref_text, cand, 4),
                "rougeL": rouge_l_f1(ref_text, cand),
                "llmJudgeScore": extract_llm_score(evaluation, round_id, gid),
            }
            rows.append(row)

    def avg(key: str) -> float:
        vals = [float(item[key]) for item in rows if item.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    valid_for_corr = [item for item in rows if item.get("llmJudgeScore") is not None]
    llm = [float(item["llmJudgeScore"]) for item in valid_for_corr]
    rouge = [float(item["rougeL"]) for item in valid_for_corr]
    bleu1s = [float(item["bleu1"]) for item in valid_for_corr]
    bleu4s = [float(item["bleu4"]) for item in valid_for_corr]

    by_group: dict[str, dict[str, float]] = {}
    for gid in targets:
        subset = [r for r in rows if r["groupId"] == gid]
        if not subset:
            continue
        by_group[gid] = {
            "count": float(len(subset)),
            "bleu1": sum(float(r["bleu1"]) for r in subset) / len(subset),
            "bleu4": sum(float(r["bleu4"]) for r in subset) / len(subset),
            "rougeL": sum(float(r["rougeL"]) for r in subset) / len(subset),
            "llmJudgeScore": sum(float(r["llmJudgeScore"]) for r in subset if r.get("llmJudgeScore") is not None)
            / max(sum(1 for r in subset if r.get("llmJudgeScore") is not None), 1),
        }

    report = {
        "planId": args.plan_id,
        "runId": args.run_id,
        "referenceGroup": args.reference_group,
        "targetGroups": targets,
        "pairs": len(rows),
        "rows": rows,
        "overall": {
            "bleu1": avg("bleu1"),
            "bleu2": avg("bleu2"),
            "bleu3": avg("bleu3"),
            "bleu4": avg("bleu4"),
            "rougeL": avg("rougeL"),
            "llmJudgeAvg": sum(llm) / len(llm) if llm else 0.0,
            "corr": {
                "pearson_rougeL_vs_llmJudge": pearson(rouge, llm) if llm else 0.0,
                "spearman_rougeL_vs_llmJudge": spearman(rouge, llm) if llm else 0.0,
                "pearson_bleu1_vs_llmJudge": pearson(bleu1s, llm) if llm else 0.0,
                "spearman_bleu1_vs_llmJudge": spearman(bleu1s, llm) if llm else 0.0,
                "pearson_bleu4_vs_llmJudge": pearson(bleu4s, llm) if llm else 0.0,
                "spearman_bleu4_vs_llmJudge": spearman(bleu4s, llm) if llm else 0.0,
            },
        },
        "byGroup": by_group,
        "notes": [
            "This lightweight baseline uses control-group output as pseudo-reference.",
            "BLEU/ROUGE are lexical overlap metrics and may undervalue factual correctness paraphrases.",
            "LLM-as-Judge scores are read from experiment_evaluation.json structuredEvaluation.score.",
        ],
    }

    out_text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text, encoding="utf-8")
        print(f"saved: {out_path}")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
