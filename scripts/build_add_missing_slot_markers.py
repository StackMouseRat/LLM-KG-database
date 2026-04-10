from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple


MARKER = "[[MISSING_FROM_GRAPH]]"
COMMON = "通用"
REQUIRED_SLOTS = [
    "fault_object",
    "fault_consequence",
    "fault_level",
    "precursor",
    "action_steps",
    "safety_risk",
]
SEP = "<<<CHUNK>>>"


def read_rows(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[dict], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def write_txt(path: Path, rows: List[dict]) -> None:
    with path.open("w", encoding="utf-8-sig") as f:
        for i, r in enumerate(rows):
            if i:
                f.write("\n")
            lines = [
                f"chunk_id: {r.get('chunk_id', '')}",
                f"doc_id: {r.get('doc_id', '')}",
                f"chunk_type: {r.get('chunk_type', '')}",
                f"asset_type: {r.get('asset_type', '')}",
                f"fault_type: {r.get('fault_type', '')}",
                f"slot_key: {r.get('slot_key', '')}",
                f"keywords: {r.get('keywords', '')}",
                f"source_ref: {r.get('source_ref', '')}",
                f"priority: {r.get('priority', '')}",
                f"version: {r.get('version', '')}",
                "content:",
                (r.get("content", "") or "").strip(),
                SEP,
            ]
            f.write("\n".join(lines))


def max_chunk_id(rows: List[dict]) -> int:
    m = 0
    for r in rows:
        cid = (r.get("chunk_id", "") or "").strip()
        if cid.startswith("C") and cid[1:].isdigit():
            m = max(m, int(cid[1:]))
    return m


def add_markers(rows: List[dict]) -> Tuple[List[dict], int]:
    by_fault_slots: Dict[str, set] = {}
    for r in rows:
        ft = (r.get("fault_type") or "").strip()
        sk = (r.get("slot_key") or "").strip()
        if not ft or ft == COMMON or not sk:
            continue
        by_fault_slots.setdefault(ft, set()).add(sk)

    if not rows:
        return rows, 0

    doc_id = rows[0].get("doc_id", "")
    asset = rows[0].get("asset_type", "")
    version = rows[0].get("version", "")

    added = 0
    cid = max_chunk_id(rows)
    out = list(rows)

    for ft in sorted(by_fault_slots.keys()):
        present = by_fault_slots.get(ft, set())
        missing = [s for s in REQUIRED_SLOTS if s not in present]
        for slot in missing:
            cid += 1
            out.append(
                {
                    "chunk_id": f"C{cid:06d}",
                    "doc_id": doc_id,
                    "chunk_type": "slot_missing_marker",
                    "asset_type": asset,
                    "fault_type": ft,
                    "slot_key": slot,
                    "content": (
                        f"{MARKER} fault_type={ft}; slot_key={slot}; "
                        "reason=图谱缺少该槽位显式事实，请在生成阶段基于已有事实谨慎推理补全。"
                    ),
                    "keywords": f"{asset}|{ft}|{slot}|MISSING_FROM_GRAPH",
                    "source_ref": "generated_missing_marker",
                    "priority": "1",
                    "version": f"{version}_missing_marked",
                }
            )
            added += 1

    return out, added


def process_one(input_csv: Path, output_csv: Path, output_txt: Path) -> Tuple[int, int]:
    rows = read_rows(input_csv)
    merged, added = add_markers(rows)
    fields = [
        "chunk_id",
        "doc_id",
        "chunk_type",
        "asset_type",
        "fault_type",
        "slot_key",
        "content",
        "keywords",
        "source_ref",
        "priority",
        "version",
    ]
    write_csv(output_csv, merged, fields)
    retrieval_rows = [r for r in merged if r.get("chunk_type") != "template_clause"]
    write_txt(output_txt, retrieval_rows)
    return len(merged), added


def main() -> None:
    root = Path(r"D:\Graduate_test\dataset")

    breaker_in = next(root.glob("**/断路器/csv/kb_chunks_corrected_v5_name_desc.csv"))
    breaker_out_csv = breaker_in.parent / "kb_chunks_corrected_v6_missing_marked.csv"
    breaker_out_txt = (
        breaker_in.parent / "kb_chunks_fastgpt_upload_retrieval_only_corrected_v6_missing_marked.txt"
    )

    trans_in = next(root.glob("**/输电线/10_csv_structured/kb_chunks_transmission_v3.csv"))
    trans_out_csv = trans_in.parent / "kb_chunks_transmission_v4_missing_marked.csv"
    trans_out_txt = (
        trans_in.parent.parent
        / "20_upload_chunks"
        / "kb_chunks_transmission_retrieval_only_v4_missing_marked.txt"
    )

    b_total, b_added = process_one(breaker_in, breaker_out_csv, breaker_out_txt)
    t_total, t_added = process_one(trans_in, trans_out_csv, trans_out_txt)

    print("breaker_in:", breaker_in)
    print("breaker_out_csv:", breaker_out_csv)
    print("breaker_out_txt:", breaker_out_txt)
    print("breaker_total_rows:", b_total, "added_markers:", b_added)
    print("trans_in:", trans_in)
    print("trans_out_csv:", trans_out_csv)
    print("trans_out_txt:", trans_out_txt)
    print("trans_total_rows:", t_total, "added_markers:", t_added)


if __name__ == "__main__":
    main()
