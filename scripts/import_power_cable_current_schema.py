#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests


TYPE_FIELDS = "name string, node_desc string, lvl int, source_id int, degree int, weight int, stroke string"
TYPED_TAGS = [
    "root_node",
    "fault_l1",
    "fault_l2",
    "fault_cause",
    "fault_symptom",
    "response_measure",
    "fault_consequence",
    "safety_risk",
    "emergency_resource",
]
ENTITY_BATCH = 1
EDGE_BATCH = 16


def esc(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def chunked(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def gql(endpoint: str, ngql: str, space: str) -> dict:
    last_exc: Exception | None = None
    payload = {"space": space, "ngql": ngql}
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


def ensure_schema(endpoint: str, space: str) -> None:
    gql(endpoint, f"CREATE TAG IF NOT EXISTS entity({TYPE_FIELDS});", space)
    for tag in TYPED_TAGS:
        gql(endpoint, f"CREATE TAG IF NOT EXISTS {tag}({TYPE_FIELDS});", space)
    gql(endpoint, 'CREATE EDGE IF NOT EXISTS rel(relation string);', space)
    gql(endpoint, 'CREATE TAG INDEX IF NOT EXISTS entity_lvl_idx ON entity(lvl);', space)


def delete_known_vertices(endpoint: str, space: str, nodes: list[dict]) -> None:
    for batch in chunked(nodes, 32):
        vids = ", ".join(f'"{esc(node["vid"])}"' for node in batch)
        gql(endpoint, f"DELETE VERTEX {vids} WITH EDGE;", space)


def insert_entity_vertices(endpoint: str, space: str, nodes: list[dict]) -> None:
    for batch in chunked(nodes, ENTITY_BATCH):
        values = []
        for node in batch:
            values.append(
                f'"{esc(node["vid"])}":('
                f'"{esc(node["name"])}",'
                f'"{esc(node["node_desc"])}",'
                f'{int(node["lvl"])},'
                f'{int(node["source_id"])},'
                f'{int(node["degree"])},'
                f'{int(node["weight"])},'
                f'"{esc(node["stroke"])}")'
            )
        ngql = (
            "INSERT VERTEX entity(name, node_desc, lvl, source_id, degree, weight, stroke) "
            f"VALUES {', '.join(values)};"
        )
        gql(endpoint, ngql, space)


def insert_typed_vertices(endpoint: str, space: str, nodes: list[dict]) -> None:
    by_tag: dict[str, list[dict]] = {}
    for node in nodes:
        by_tag.setdefault(node["typed_tag"], []).append(node)

    for tag_name, tag_nodes in by_tag.items():
        for batch in chunked(tag_nodes, ENTITY_BATCH):
            values = []
            for node in batch:
                values.append(
                    f'"{esc(node["vid"])}":('
                    f'"{esc(node["name"])}",'
                    f'"{esc(node["node_desc"])}",'
                    f'{int(node["lvl"])},'
                    f'{int(node["source_id"])},'
                    f'{int(node["degree"])},'
                    f'{int(node["weight"])},'
                    f'"{esc(node["stroke"])}")'
                )
            ngql = (
                f"INSERT VERTEX {tag_name}(name, node_desc, lvl, source_id, degree, weight, stroke) "
                f"VALUES {', '.join(values)};"
            )
            gql(endpoint, ngql, space)


def insert_edges(endpoint: str, space: str, links: list[dict]) -> None:
    for batch in chunked(links, EDGE_BATCH):
        values = []
        for link in batch:
            values.append(
                f'"{esc(link["src"])}"->"{esc(link["dst"])}":("{esc(link["relation"])}")'
            )
        gql(endpoint, f"INSERT EDGE rel(relation) VALUES {', '.join(values)};", space)


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
    result: list[dict[str, str]] = []
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


def count_tag(endpoint: str, space: str, tag_name: str) -> int:
    rows = parse_table(gql(endpoint, f"MATCH (v:{tag_name}) RETURN count(v) AS c;", space)["stdout"])
    return int(rows[0]["c"]) if rows else 0


def count_edge(endpoint: str, space: str) -> int:
    rows = parse_table(gql(endpoint, "MATCH ()-[e:rel]->() RETURN count(e) AS c;", space)["stdout"])
    return int(rows[0]["c"]) if rows else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Import power cable graph into current Nebula schema.")
    parser.add_argument(
        "--manifest",
        default="/home/ubuntu/LLM-KG-database/xls/成品/电力电缆/电力电缆_第一至第八层级图谱数据/graph_manifest.json",
    )
    parser.add_argument("--endpoint", default="http://127.0.0.1:8787/graph/query")
    parser.add_argument("--space", default="llmkg_cable")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    nodes = manifest["nodes"]
    links = manifest["links"]

    ensure_schema(args.endpoint, args.space)
    delete_known_vertices(args.endpoint, args.space, nodes)
    insert_entity_vertices(args.endpoint, args.space, nodes)
    insert_typed_vertices(args.endpoint, args.space, nodes)
    insert_edges(args.endpoint, args.space, links)

    print(f"space={args.space}")
    print(f"entity={count_tag(args.endpoint, args.space, 'entity')}")
    for tag in TYPED_TAGS:
        print(f"{tag}={count_tag(args.endpoint, args.space, tag)}")
    print(f"rel={count_edge(args.endpoint, args.space)}")


if __name__ == "__main__":
    main()
