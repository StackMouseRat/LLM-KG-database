#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import time
from typing import Dict, Iterable, List

import requests


TYPE_FIELDS = "name string, node_desc string, lvl int, source_id int, degree int, weight int, stroke string"
LLMKG_PREFIX = "llmkg_"
INSERT_BATCH_SIZE = 8

TAG_RULES = {
    "root_node": "v.entity.lvl == 0",
    "fault_l1": "v.entity.lvl == 1",
    "fault_l2": "v.entity.lvl == 2",
    "fault_cause": 'v.entity.name ENDS WITH "-故障原因"',
    "fault_symptom": 'v.entity.name ENDS WITH "-故障现象"',
    "response_measure": 'v.entity.name ENDS WITH "-应对措施"',
    "fault_consequence": 'v.entity.name ENDS WITH "-故障后果"',
    "safety_risk": 'v.entity.name ENDS WITH "-安全风险"',
    "emergency_resource": 'v.entity.name ENDS WITH "-应急资源"',
}


def gql(endpoint: str, ngql: str, space: str | None = None) -> dict:
    payload = {"ngql": ngql}
    if space:
        payload["space"] = space
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            r = requests.post(
                endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
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


def parse_table(stdout: str) -> List[Dict[str, str]]:
    rows: List[List[str]] = []
    for line in stdout.splitlines():
        line = line.rstrip()
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
    result: List[Dict[str, str]] = []
    for row in data_rows:
        if len(row) != len(header):
            continue
        item = {}
        for k, v in zip(header, row):
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            item[k] = v
        result.append(item)
    return result


def esc(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def list_spaces(endpoint: str) -> List[str]:
    rows = parse_table(gql(endpoint, "SHOW SPACES;")["stdout"])
    return [row["Name"] for row in rows if row["Name"].startswith(LLMKG_PREFIX)]


def count_entity(endpoint: str, space: str) -> int:
    rows = parse_table(gql(endpoint, "MATCH (v:entity) RETURN count(v) AS c;", space)["stdout"])
    return int(rows[0]["c"]) if rows else 0


def ensure_tag(endpoint: str, space: str, tag_name: str) -> None:
    gql(endpoint, f"CREATE TAG IF NOT EXISTS {tag_name}({TYPE_FIELDS});", space)
    for _ in range(10):
        rows = parse_table(gql(endpoint, "SHOW TAGS;", space)["stdout"])
        names = {row["Name"] for row in rows}
        if tag_name in names:
            return
        time.sleep(1)
    raise RuntimeError(f"Tag {tag_name} not visible in {space} after creation")


def fetch_vertices(endpoint: str, space: str, where_clause: str) -> List[Dict[str, str]]:
    query = (
        "MATCH (v:entity) "
        f"WHERE {where_clause} "
        "RETURN id(v) AS vid, "
        "v.entity.name AS name, "
        "v.entity.node_desc AS node_desc, "
        "v.entity.lvl AS lvl, "
        "v.entity.source_id AS source_id, "
        "v.entity.degree AS degree, "
        "v.entity.weight AS weight, "
        "v.entity.stroke AS stroke "
        "ORDER BY source_id;"
    )
    return parse_table(gql(endpoint, query, space)["stdout"])


def chunked(items: List[Dict[str, str]], size: int) -> Iterable[List[Dict[str, str]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def insert_tagged_vertices(endpoint: str, space: str, tag_name: str, items: List[Dict[str, str]]) -> None:
    for chunk in chunked(items, INSERT_BATCH_SIZE):
        values = []
        for item in chunk:
            values.append(
                f"\"{esc(item['vid'])}\":("
                f"\"{esc(item['name'])}\","
                f"\"{esc(item['node_desc'])}\","
                f"{int(item['lvl'])},"
                f"{int(item['source_id'])},"
                f"{int(item['degree'])},"
                f"{int(item['weight'])},"
                f"\"{esc(item['stroke'])}\")"
            )
        ngql = (
            f"INSERT VERTEX {tag_name}(name, node_desc, lvl, source_id, degree, weight, stroke) "
            f"VALUES {', '.join(values)};"
        )
        gql(endpoint, ngql, space)


def count_tag(endpoint: str, space: str, tag_name: str) -> int:
    rows = parse_table(gql(endpoint, f"MATCH (v:{tag_name}) RETURN count(v) AS c;", space)["stdout"])
    return int(rows[0]["c"]) if rows else 0


def count_unclassified(endpoint: str, space: str) -> int:
    where = " OR ".join(f"({clause})" for clause in TAG_RULES.values())
    rows = parse_table(
        gql(
            endpoint,
            f"MATCH (v:entity) WHERE NOT ({where}) RETURN count(v) AS c;",
            space,
        )["stdout"]
    )
    return int(rows[0]["c"]) if rows else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate entity vertices into typed Nebula tags.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8787/graph/query")
    args = parser.parse_args()

    spaces = list_spaces(args.endpoint)
    for space in spaces:
        entity_count = count_entity(args.endpoint, space)
        if entity_count == 0:
            print(f"=== {space} ===")
            print("skip: entity_count=0")
            continue
        print(f"=== {space} ===")
        for tag_name, where_clause in TAG_RULES.items():
            ensure_tag(args.endpoint, space, tag_name)
            items = fetch_vertices(args.endpoint, space, where_clause)
            if items:
                insert_tagged_vertices(args.endpoint, space, tag_name, items)
            print(f"{tag_name}: migrated={len(items)} current_count={count_tag(args.endpoint, space, tag_name)}")
        print(f"unclassified_entity={count_unclassified(args.endpoint, space)}")


if __name__ == "__main__":
    main()
