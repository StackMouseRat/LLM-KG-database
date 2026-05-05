from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_DIMENSIONS = {
    "structure": [
        "structure",
        "structure_score",
        "结构",
        "结构规范性",
        "结构完整性",
        "章节结构",
    ],
    "knowledge": [
        "knowledge",
        "knowledge_score",
        "知识",
        "知识相关性",
        "图谱事实",
        "知识准确性",
    ],
    "measure": [
        "measure",
        "measure_score",
        "measures",
        "措施",
        "措施完整性",
        "处置措施",
    ],
    "traceability": [
        "traceability",
        "traceability_score",
        "trace",
        "内容可追溯性",
        "可追溯性",
        "来源追溯",
    ],
}

DEFAULT_MAX_SCORES = {
    "structure": 10.0,
    "knowledge": 10.0,
    "measure": 10.0,
    "traceability": 10.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze LLM-as-a-Judge subscore correlations.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input JSON/JSONL/CSV file, or experiment_evaluation.json.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tmp/subscore_correlation"),
        help="Directory for analysis outputs.",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize subscores by per-dimension max score before correlation analysis.",
    )
    parser.add_argument(
        "--dimension-max",
        nargs="*",
        default=[],
        help="Optional overrides, e.g. structure=2 knowledge=3 measure=3 traceability=2",
    )
    return parser.parse_args()


def parse_dimension_max(overrides: list[str]) -> dict[str, float]:
    values = dict(DEFAULT_MAX_SCORES)
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"invalid dimension-max override: {item}")
        key, raw = item.split("=", 1)
        values[key.strip()] = float(raw)
    return values


def read_input(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    if suffix == ".csv":
        with path.open("r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("/10", "").replace("分", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def pick_first(mapping: dict[str, Any], candidates: list[str]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in mapping.items()}
    original = {str(k).strip(): v for k, v in mapping.items()}
    for key in candidates:
        if key in original:
            return original[key]
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def canonical_subscores(raw: dict[str, Any], dimension_max: dict[str, float], normalize: bool) -> dict[str, float] | None:
    result: dict[str, float] = {}
    for canonical, aliases in DEFAULT_DIMENSIONS.items():
        value = maybe_float(pick_first(raw, aliases))
        if value is None:
            return None
        if normalize:
            max_value = float(dimension_max.get(canonical) or 1.0)
            if max_value <= 0:
                raise ValueError(f"invalid max score for {canonical}: {max_value}")
            value = value / max_value
        result[canonical] = value
    return result


def flatten_experiment_evaluation(payload: dict[str, Any], dimension_max: dict[str, float], normalize: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evaluation_state = payload.get("evaluationState") if isinstance(payload.get("evaluationState"), dict) else {}
    scores = evaluation_state.get("scores") if isinstance(evaluation_state.get("scores"), dict) else {}
    plan_id = str(payload.get("planId") or "")
    run_id = str(payload.get("runId") or "")
    for round_id, group_map in scores.items():
        if not isinstance(group_map, dict):
            continue
        for group_id, item in group_map.items():
            if not isinstance(item, dict):
                continue
            subscores = item.get("subscores") if isinstance(item.get("subscores"), dict) else item
            canonical = canonical_subscores(subscores, dimension_max, normalize)
            if canonical is None:
                continue
            row = {
                "plan_id": plan_id,
                "run_id": run_id,
                "round_id": str(round_id),
                "group_id": str(group_id),
                "group_label": str(item.get("groupLabel") or item.get("group_label") or group_id),
                "question_id": str(item.get("questionId") or item.get("question_id") or ""),
                "question_text": str(item.get("questionText") or item.get("question_text") or ""),
                "overall_score": maybe_float(item.get("score") or item.get("overall_score") or item.get("总分")),
                **canonical,
            }
            rows.append(row)
    return rows


def flatten_generic_list(items: list[Any], dimension_max: dict[str, float], normalize: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        subscores = item.get("subscores") if isinstance(item.get("subscores"), dict) else item
        canonical = canonical_subscores(subscores, dimension_max, normalize)
        if canonical is None:
            continue
        row = {
            "plan_id": str(item.get("plan_id") or item.get("planId") or ""),
            "run_id": str(item.get("run_id") or item.get("runId") or ""),
            "round_id": str(item.get("round_id") or item.get("roundId") or idx),
            "group_id": str(item.get("group_id") or item.get("groupId") or ""),
            "group_label": str(item.get("group_label") or item.get("groupLabel") or item.get("label") or ""),
            "question_id": str(item.get("question_id") or item.get("questionId") or ""),
            "question_text": str(item.get("question_text") or item.get("questionText") or ""),
            "overall_score": maybe_float(item.get("overall_score") or item.get("score") or item.get("总分")),
            **canonical,
        }
        rows.append(row)
    return rows


def load_rows(path: Path, dimension_max: dict[str, float], normalize: bool) -> list[dict[str, Any]]:
    payload = read_input(path)
    if isinstance(payload, dict) and "evaluationState" in payload:
        return flatten_experiment_evaluation(payload, dimension_max, normalize)
    if isinstance(payload, list):
        return flatten_generic_list(payload, dimension_max, normalize)
    raise ValueError(f"unsupported input structure: {path}")


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else math.nan


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return math.nan
    return statistics.pvariance(values)


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return math.nan
    return statistics.pstdev(values)


def rankdata(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return math.nan
    mx = mean(x)
    my = mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den_x = sum((a - mx) ** 2 for a in x)
    den_y = sum((b - my) ** 2 for b in y)
    if den_x <= 0 or den_y <= 0:
        return math.nan
    return num / math.sqrt(den_x * den_y)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(rankdata(x), rankdata(y))


def pairwise_correlations(rows: list[dict[str, Any]], dims: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    matrix: dict[str, dict[str, dict[str, float]]] = {}
    for d1 in dims:
        matrix[d1] = {}
        for d2 in dims:
            x = [float(row[d1]) for row in rows]
            y = [float(row[d2]) for row in rows]
            matrix[d1][d2] = {
                "pearson": pearson(x, y),
                "spearman": spearman(x, y),
            }
    return matrix


def write_matrix_csv(path: Path, matrix: dict[str, dict[str, dict[str, float]]], metric: str) -> None:
    dims = list(matrix.keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([metric, *dims])
        for d1 in dims:
            writer.writerow([d1, *[f"{matrix[d1][d2][metric]:.6f}" if not math.isnan(matrix[d1][d2][metric]) else "" for d2 in dims]])


def write_descriptive_stats(path: Path, rows: list[dict[str, Any]], dims: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["dimension", "count", "mean", "stddev", "min", "median", "max"])
        for dim in dims:
            values = [float(row[dim]) for row in rows]
            writer.writerow([
                dim,
                len(values),
                f"{mean(values):.6f}",
                f"{stddev(values):.6f}" if len(values) >= 2 else "",
                f"{min(values):.6f}" if values else "",
                f"{statistics.median(values):.6f}" if values else "",
                f"{max(values):.6f}" if values else "",
            ])


def group_rows(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "")].append(row)
    return dict(grouped)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    dimension_max = parse_dimension_max(args.dimension_max)
    rows = load_rows(args.input, dimension_max, args.normalize)
    if not rows:
        raise SystemExit("No valid rows with complete subscores were found.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    dims = ["structure", "knowledge", "measure", "traceability"]

    write_json(args.out_dir / "normalized_rows.json", rows)
    write_descriptive_stats(args.out_dir / "descriptive_stats.csv", rows, dims)

    overall_matrix = pairwise_correlations(rows, dims)
    write_json(args.out_dir / "overall_correlations.json", overall_matrix)
    write_matrix_csv(args.out_dir / "overall_spearman.csv", overall_matrix, "spearman")
    write_matrix_csv(args.out_dir / "overall_pearson.csv", overall_matrix, "pearson")

    for key in ["plan_id", "group_id", "group_label"]:
        grouped = group_rows(rows, key)
        out = {}
        for group_name, items in grouped.items():
            if len(items) < 2:
                continue
            out[group_name] = pairwise_correlations(items, dims)
        if out:
            write_json(args.out_dir / f"by_{key}_correlations.json", out)

    summary = {
        "input": str(args.input),
        "row_count": len(rows),
        "normalize": args.normalize,
        "dimensions": dims,
        "dimension_max": dimension_max,
        "outputs": {
            "rows": str(args.out_dir / "normalized_rows.json"),
            "descriptive_stats": str(args.out_dir / "descriptive_stats.csv"),
            "overall_correlations": str(args.out_dir / "overall_correlations.json"),
            "overall_spearman": str(args.out_dir / "overall_spearman.csv"),
            "overall_pearson": str(args.out_dir / "overall_pearson.csv"),
        },
    }
    write_json(args.out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
