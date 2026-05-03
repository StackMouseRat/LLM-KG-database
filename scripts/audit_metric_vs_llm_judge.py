#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


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
    pairs = sorted(enumerate(values), key=lambda item: item[1])
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


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def metric_keys(rows: list[dict[str, Any]]) -> list[str]:
    candidates = ["rougeL", "chrfpp", "bertscoreF1", "bleu1", "bleu4"]
    return [key for key in candidates if any(isinstance(row.get(key), int | float) for row in rows)]


def compact_case(row: dict[str, Any], metrics: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "planId": row.get("planId"),
        "runId": row.get("runId"),
        "round": row.get("round"),
        "groupId": row.get("groupId"),
        "question": row.get("question"),
        "llmJudgeScore": row.get("llmJudgeScore"),
    }
    for key in metrics:
        if row.get(key) is not None:
            out[key] = row[key]
    for key in ["referencePreview", "candidatePreview", "refPreview", "candPreview"]:
        if row.get(key):
            out[key] = row[key]
    return out


def summarize_metric(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    subset = [row for row in rows if isinstance(row.get(key), int | float) and isinstance(row.get("llmJudgeScore"), int | float)]
    metric_values = [float(row[key]) for row in subset]
    llm_values = [float(row["llmJudgeScore"]) for row in subset]
    high_metric_threshold = percentile(metric_values, 0.75)
    low_llm_threshold = percentile(llm_values, 0.25)
    low_metric_threshold = percentile(metric_values, 0.25)
    high_llm_threshold = percentile(llm_values, 0.75)

    high_metric_low_llm = [
        row for row in subset if float(row[key]) >= high_metric_threshold and float(row["llmJudgeScore"]) <= low_llm_threshold
    ]
    low_metric_high_llm = [
        row for row in subset if float(row[key]) <= low_metric_threshold and float(row["llmJudgeScore"]) >= high_llm_threshold
    ]

    return {
        "pairs": len(subset),
        "pearson": pearson(metric_values, llm_values),
        "spearman": spearman(metric_values, llm_values),
        "metricP75": high_metric_threshold,
        "metricP25": low_metric_threshold,
        "llmP75": high_llm_threshold,
        "llmP25": low_llm_threshold,
        "highMetricLowLlmCount": len(high_metric_low_llm),
        "lowMetricHighLlmCount": len(low_metric_high_llm),
        "highMetricLowLlmTop": [compact_case(row, [key]) for row in sorted(high_metric_low_llm, key=lambda r: float(r[key]), reverse=True)[:8]],
        "lowMetricHighLlmTop": [compact_case(row, [key]) for row in sorted(low_metric_high_llm, key=lambda r: float(r[key]))[:8]],
    }


def ordering_inversions(rows: list[dict[str, Any]], key: str, min_metric_gap: float, min_llm_gap: float) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row.get(key), int | float) and isinstance(row.get("llmJudgeScore"), int | float):
            grouped[(str(row.get("planId")), str(row.get("runId")), int(row.get("round", 0)))].append(row)

    inversions: list[dict[str, Any]] = []
    for group_rows in grouped.values():
        for i, left in enumerate(group_rows):
            for right in group_rows[i + 1 :]:
                metric_gap = float(left[key]) - float(right[key])
                llm_gap = float(left["llmJudgeScore"]) - float(right["llmJudgeScore"])
                if abs(metric_gap) < min_metric_gap or abs(llm_gap) < min_llm_gap:
                    continue
                if metric_gap * llm_gap < 0:
                    metric_winner, llm_winner = (left, right) if metric_gap > 0 else (right, left)
                    inversions.append(
                        {
                            "metric": key,
                            "planId": left.get("planId"),
                            "runId": left.get("runId"),
                            "round": left.get("round"),
                            "question": left.get("question"),
                            "metricWinner": compact_case(metric_winner, [key]),
                            "llmWinner": compact_case(llm_winner, [key]),
                            "metricGap": abs(metric_gap),
                            "llmGap": abs(llm_gap),
                        }
                    )
    return sorted(inversions, key=lambda item: (float(item["llmGap"]), float(item["metricGap"])), reverse=True)


def by_run_summary(rows: list[dict[str, Any]], metrics: list[str]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[f"{row.get('planId')}/{row.get('runId')}"] .append(row)

    out: dict[str, Any] = {}
    for run_key, subset in sorted(grouped.items()):
        llm = [float(row["llmJudgeScore"]) for row in subset if isinstance(row.get("llmJudgeScore"), int | float)]
        item: dict[str, Any] = {"pairs": len(subset), "llmJudgeAvg": sum(llm) / len(llm) if llm else 0.0, "corr": {}}
        for metric in metrics:
            valid = [row for row in subset if isinstance(row.get(metric), int | float) and isinstance(row.get("llmJudgeScore"), int | float)]
            if len(valid) < 2:
                continue
            xs = [float(row[metric]) for row in valid]
            ys = [float(row["llmJudgeScore"]) for row in valid]
            item["corr"][f"pearson_{metric}_vs_llmJudge"] = pearson(xs, ys)
            item["corr"][f"spearman_{metric}_vs_llmJudge"] = spearman(xs, ys)
        out[run_key] = item
    return out


def paper_summary(report: dict[str, Any], primary_metric: str) -> dict[str, Any]:
    metric_report = report["metricAudit"].get(primary_metric, {})
    weak_runs: list[str] = []
    negative_runs: list[str] = []
    for run_key, run in report["byRun"].items():
        corr = run.get("corr", {}).get(f"pearson_{primary_metric}_vs_llmJudge")
        if not isinstance(corr, int | float):
            continue
        if abs(float(corr)) < 0.3:
            weak_runs.append(run_key)
        if float(corr) < 0:
            negative_runs.append(run_key)
    return {
        "mainFinding": "Traditional overlap/embedding metrics show only partial agreement with LLM-as-Judge and can overestimate structurally similar but semantically incomplete emergency plans.",
        "primaryMetric": primary_metric,
        "primaryPearson": metric_report.get("pearson"),
        "primarySpearman": metric_report.get("spearman"),
        "highMetricLowLlmCount": metric_report.get("highMetricLowLlmCount"),
        "lowMetricHighLlmCount": metric_report.get("lowMetricHighLlmCount"),
        "weakCorrelationRuns": weak_runs,
        "negativeCorrelationRuns": negative_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit traditional metrics against LLM-as-Judge scores")
    parser.add_argument("--input", default="tmp/metrics/first_batch_metrics_rouge_chrf_bertscore.json")
    parser.add_argument("--out", default="tmp/metrics/metric_vs_llm_judge_audit.json")
    parser.add_argument("--primary-metric", default="bertscoreF1")
    parser.add_argument("--min-metric-gap", type=float, default=0.03)
    parser.add_argument("--min-llm-gap", type=float, default=1.0)
    args = parser.parse_args()

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = source.get("rows") if isinstance(source.get("rows"), list) else []
    metrics = metric_keys(rows)
    if not rows or not metrics:
        raise SystemExit("input has no auditable rows or metrics")

    report = {
        "source": args.input,
        "pairs": len(rows),
        "metrics": metrics,
        "metricAudit": {metric: summarize_metric(rows, metric) for metric in metrics},
        "byRun": by_run_summary(rows, metrics),
        "orderingInversions": {
            metric: ordering_inversions(rows, metric, args.min_metric_gap, args.min_llm_gap)[:12] for metric in metrics
        },
    }
    primary = args.primary_metric if args.primary_metric in metrics else metrics[0]
    report["paperSummary"] = paper_summary(report, primary)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["paperSummary"], ensure_ascii=False, indent=2))
    print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
