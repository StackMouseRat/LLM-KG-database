#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from typing import Iterable

import requests


EDGE_MAP = {
    "发生": "has_fault_category",
    "包含": "contains",
    "起因于": "caused_by",
    "表现": "has_symptom",
    "表现为": "has_symptom",
    "处置": "handled_by",
    "导致": "results_in",
    "存在": "has_risk",
    "需要": "needs_resource",
}

EDGE_BATCH = 16


def gql(endpoint: str, ngql: str, space: str) -> dict:
    payload = {"space": space, "ngql": ngql}
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            r = requests.post(endpoint, json=payload, timeout=60)
            if r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:240]}")
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(f"Query failed: {j.get('errors') or j.get('message')}")
            return j
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt == 5:
                break
            time.sleep(attempt)
    raise RuntimeError(f"gql failed after retries: {last_exc}")


def parse_table(stdout: str) -> list[dict[str, str]]:
    rows = []
    for line in stdout.splitlines():
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if not parts:
            continue
        if set("".join(parts)) <= {"+", "-"}:
            continue
        rows.append(parts)
    if len(rows) < 2:
        return []
    header = rows[0]
    data_rows = rows[1:]
    result = []
    for row in data_rows:
        if len(row) != len(header):
            continue
        item = {}
        for key, value in zip(header, row):
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            item[key] = value
        result.append(item)
    return result


def chunked(items: list[dict[str, str]], size: int) -> Iterable[list[dict[str, str]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def ensure_edge_schema(endpoint: str, space: str) -> None:
    for edge_name in EDGE_MAP.values():
        gql(endpoint, f"CREATE EDGE IF NOT EXISTS {edge_name}();", space)


def fetch_all_rel_edges(endpoint: str, space: str) -> list[dict[str, str]]:
    rows = parse_table(
        gql(
            endpoint,
            'MATCH ()-[e:rel]->() RETURN src(e) AS src, dst(e) AS dst, e.relation AS relation;',
            space,
        )["stdout"]
    )
    return rows


def insert_semantic_edges(endpoint: str, space: str, edge_name: str, rows: list[dict[str, str]]) -> None:
    for batch in chunked(rows, EDGE_BATCH):
        values = [f'"{row["src"]}"->"{row["dst"]}":()' for row in batch]
        gql(endpoint, f"INSERT EDGE {edge_name}() VALUES {', '.join(values)};", space)


def count_edge(endpoint: str, space: str, edge_name: str) -> int:
    rows = parse_table(gql(endpoint, f"MATCH ()-[e:{edge_name}]->() RETURN count(e) AS c;", space)["stdout"])
    return int(rows[0]["c"]) if rows else 0


def fetch_root_l1_edges(endpoint: str, space: str) -> list[dict[str, str]]:
    rows = parse_table(
        gql(
            endpoint,
            (
                "MATCH (root:root_node), (major:fault_l1) "
                "RETURN id(root) AS src, id(major) AS dst;"
            ),
            space,
        )["stdout"]
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade formal spaces from rel edges to semantic edges.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8787/graph/query")
    parser.add_argument(
        "--spaces",
        nargs="+",
        default=["llmkg_breaker", "llmkg_mutual", "llmkg_transformer", "llmkg_transmission_line"],
    )
    args = parser.parse_args()

    for space in args.spaces:
        print(f"=== {space} ===")
        ensure_edge_schema(args.endpoint, space)
        all_rows = fetch_all_rel_edges(args.endpoint, space)
        for rel_name, semantic_edge in EDGE_MAP.items():
            rows = [row for row in all_rows if row.get("relation") == rel_name]
            if rows:
                insert_semantic_edges(args.endpoint, space, semantic_edge, rows)
            print(
                f"{semantic_edge}: migrated={len(rows)} current_count={count_edge(args.endpoint, space, semantic_edge)}"
            )
        if count_edge(args.endpoint, space, "has_fault_category") == 0:
            root_l1_rows = fetch_root_l1_edges(args.endpoint, space)
            if root_l1_rows:
                insert_semantic_edges(args.endpoint, space, "has_fault_category", root_l1_rows)
            print(
                "has_fault_category_backfill: "
                f"migrated={len(root_l1_rows)} current_count={count_edge(args.endpoint, space, 'has_fault_category')}"
            )


if __name__ == "__main__":
    main()
