#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_MANIFEST = "/home/ubuntu/LLM-KG-database/docs/evaluation_question_sets/boundary_input_boundary_v1.json"
DEFAULT_ENDPOINT = "http://127.0.0.1:8787/graph/query"
DEFAULT_SPACE = "llmkg_evaluation"


def esc(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def gql(endpoint: str, ngql: str, space: str | None = None, retries: int = 5) -> dict[str, Any]:
    payload: dict[str, Any] = {"ngql": ngql}
    if space:
        payload["space"] = space
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(endpoint, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(str(data.get("errors") or data.get("message") or data))
            return data
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    raise RuntimeError(f"nGQL failed after retries: {last_exc}")


def create_space(endpoint: str, space: str) -> None:
    gql(
        endpoint,
        f"CREATE SPACE IF NOT EXISTS {space}(partition_num=10, replica_factor=1, vid_type=FIXED_STRING(128));",
        None,
    )
    time.sleep(2)


def ensure_schema(endpoint: str, space: str) -> None:
    gql(
        endpoint,
        "CREATE TAG IF NOT EXISTS eval_suite("
        "suite_id string, name string, description string, experiment_id string, version string, "
        "question_count int, created_at string, metadata string);",
        space,
    )
    gql(
        endpoint,
        "CREATE TAG IF NOT EXISTS eval_group("
        "group_id string, suite_id string, code string, name string, purpose string, "
        "expected_behavior string, sort_order int, metadata string);",
        space,
    )
    gql(
        endpoint,
        "CREATE TAG IF NOT EXISTS eval_question("
        "question_id string, suite_id string, group_id string, group_code string, question_text string, "
        "expected_behavior string, category string, sort_order int, enabled bool, source string, metadata string);",
        space,
    )
    gql(endpoint, "CREATE EDGE IF NOT EXISTS contains_group(relation string, sort_order int);", space)
    gql(endpoint, "CREATE EDGE IF NOT EXISTS contains_question(relation string, sort_order int);", space)
    gql(endpoint, "CREATE TAG INDEX IF NOT EXISTS eval_question_suite_idx ON eval_question(suite_id(64));", space)
    gql(endpoint, "CREATE TAG INDEX IF NOT EXISTS eval_question_group_idx ON eval_question(group_id(64));", space)


def build_records(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    suite_id = str(manifest["suite_id"])
    groups: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    question_index = 1
    for group_order, group in enumerate(manifest.get("groups", []), start=1):
        code = str(group["code"])
        group_id = f"{suite_id}__group_{code}"
        groups.append({
            "group_id": group_id,
            "suite_id": suite_id,
            "code": code,
            "name": str(group.get("name") or ""),
            "purpose": str(group.get("purpose") or ""),
            "expected_behavior": str(group.get("expected_behavior") or ""),
            "sort_order": group_order,
            "metadata": json.dumps({k: v for k, v in group.items() if k != "questions"}, ensure_ascii=False),
        })
        for item_order, question_text in enumerate(group.get("questions", []), start=1):
            questions.append({
                "question_id": f"{suite_id}__q_{question_index:03d}",
                "suite_id": suite_id,
                "group_id": group_id,
                "group_code": code,
                "question_text": str(question_text),
                "expected_behavior": str(group.get("expected_behavior") or ""),
                "category": str(group.get("name") or code),
                "sort_order": question_index,
                "group_sort_order": item_order,
                "enabled": True,
                "source": "manual_boundary_experiment_design",
                "metadata": json.dumps({"group_order": group_order, "item_order": item_order}, ensure_ascii=False),
            })
            question_index += 1
    suite = {
        "suite_id": suite_id,
        "name": str(manifest.get("name") or suite_id),
        "description": str(manifest.get("description") or ""),
        "experiment_id": str(manifest.get("experiment_id") or ""),
        "version": str(manifest.get("version") or ""),
        "question_count": len(questions),
        "created_at": str(manifest.get("created_at") or ""),
        "metadata": json.dumps({k: v for k, v in manifest.items() if k != "groups"}, ensure_ascii=False),
    }
    return suite, groups, questions


def insert_suite(endpoint: str, space: str, suite: dict[str, Any]) -> None:
    values = (
        f'"{esc(suite["suite_id"])}":('
        f'"{esc(suite["suite_id"])}","{esc(suite["name"])}","{esc(suite["description"])}",'
        f'"{esc(suite["experiment_id"])}","{esc(suite["version"])}",{int(suite["question_count"])},'
        f'"{esc(suite["created_at"])}","{esc(suite["metadata"])}")'
    )
    gql(endpoint, "INSERT VERTEX eval_suite(suite_id, name, description, experiment_id, version, question_count, created_at, metadata) VALUES " + values + ";", space)


def insert_groups(endpoint: str, space: str, suite_id: str, groups: list[dict[str, Any]]) -> None:
    for group in groups:
        values = (
            f'"{esc(group["group_id"])}":('
            f'"{esc(group["group_id"])}","{esc(group["suite_id"])}","{esc(group["code"])}",'
            f'"{esc(group["name"])}","{esc(group["purpose"])}","{esc(group["expected_behavior"])}",'
            f'{int(group["sort_order"])},"{esc(group["metadata"])}")'
        )
        gql(endpoint, "INSERT VERTEX eval_group(group_id, suite_id, code, name, purpose, expected_behavior, sort_order, metadata) VALUES " + values + ";", space)
        edge = f'"{esc(suite_id)}"->"{esc(group["group_id"])}":("contains_group",{int(group["sort_order"])})'
        gql(endpoint, "INSERT EDGE contains_group(relation, sort_order) VALUES " + edge + ";", space)


def insert_questions(endpoint: str, space: str, questions: list[dict[str, Any]]) -> None:
    for question in questions:
        values = (
            f'"{esc(question["question_id"])}":('
            f'"{esc(question["question_id"])}","{esc(question["suite_id"])}","{esc(question["group_id"])}",'
            f'"{esc(question["group_code"])}","{esc(question["question_text"])}",'
            f'"{esc(question["expected_behavior"])}","{esc(question["category"])}",'
            f'{int(question["sort_order"])},{str(bool(question["enabled"])).lower()},'
            f'"{esc(question["source"])}","{esc(question["metadata"])}")'
        )
        gql(endpoint, "INSERT VERTEX eval_question(question_id, suite_id, group_id, group_code, question_text, expected_behavior, category, sort_order, enabled, source, metadata) VALUES " + values + ";", space)
        edge = f'"{esc(question["group_id"])}"->"{esc(question["question_id"])}":("contains_question",{int(question["group_sort_order"])})'
        gql(endpoint, "INSERT EDGE contains_question(relation, sort_order) VALUES " + edge + ";", space)


def delete_existing_suite(endpoint: str, space: str, suite_id: str) -> None:
    group_rows = gql(
        endpoint,
        f'GO FROM "{esc(suite_id)}" OVER contains_group YIELD dst(edge) AS group_id;',
        space,
    ).get("data", {}).get("rows", [])
    group_ids = [str(row[0]) for row in group_rows if row]

    question_ids: list[str] = []
    if group_ids:
        group_vids = ",".join(f'"{esc(group_id)}"' for group_id in group_ids)
        question_rows = gql(
            endpoint,
            f"GO FROM {group_vids} OVER contains_question YIELD dst(edge) AS question_id;",
            space,
        ).get("data", {}).get("rows", [])
        question_ids = [str(row[0]) for row in question_rows if row]

    vids = [suite_id, *group_ids, *question_ids]
    if vids:
        gql(endpoint, "DELETE VERTEX " + ",".join(f'\"{esc(vid)}\"' for vid in vids) + " WITH EDGE;", space)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import evaluation question set into a dedicated Nebula space.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--space", default=DEFAULT_SPACE)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    suite, groups, questions = build_records(manifest)
    create_space(args.endpoint, args.space)
    ensure_schema(args.endpoint, args.space)
    delete_existing_suite(args.endpoint, args.space, suite["suite_id"])
    insert_suite(args.endpoint, args.space, suite)
    insert_groups(args.endpoint, args.space, suite["suite_id"], groups)
    insert_questions(args.endpoint, args.space, questions)
    print(json.dumps({"space": args.space, "suite_id": suite["suite_id"], "groups": len(groups), "questions": len(questions)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
