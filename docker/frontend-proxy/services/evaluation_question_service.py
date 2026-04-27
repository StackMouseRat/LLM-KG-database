from __future__ import annotations

import json
import os

from services.template_service import esc_ngql, gql, parse_table


EVALUATION_SPACE = os.getenv("EVALUATION_SPACE", "llmkg_evaluation")


def _vid_list(ids: list[str]) -> str:
    return ",".join(esc_ngql(item) for item in ids)


def _parse_metadata(raw: str) -> dict:
    if not raw:
        return {}
    for text in (raw, raw.replace('\\"', '"')):
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


def get_evaluation_question_suite(suite_id: str) -> dict:
    suite_rows = parse_table(
        gql(
            EVALUATION_SPACE,
            f"FETCH PROP ON eval_suite {esc_ngql(suite_id)} "
            "YIELD properties(vertex).suite_id AS suite_id, "
            "properties(vertex).name AS name, "
            "properties(vertex).description AS description, "
            "properties(vertex).experiment_id AS experiment_id, "
            "properties(vertex).version AS version, "
            "properties(vertex).question_count AS question_count, "
            "properties(vertex).created_at AS created_at, "
            "properties(vertex).metadata AS metadata;",
        )["stdout"]
    )
    if not suite_rows:
        raise RuntimeError(f"evaluation suite not found: {suite_id}")

    group_edge_rows = parse_table(
        gql(
            EVALUATION_SPACE,
            f"GO FROM {esc_ngql(suite_id)} OVER contains_group "
            "YIELD dst(edge) AS group_id, properties(edge).sort_order AS sort_order;",
        )["stdout"]
    )
    group_ids = [row.get("group_id", "") for row in sorted(group_edge_rows, key=lambda item: int(item.get("sort_order") or 0)) if row.get("group_id")]

    group_rows = []
    if group_ids:
        group_rows = parse_table(
            gql(
                EVALUATION_SPACE,
                f"FETCH PROP ON eval_group {_vid_list(group_ids)} "
                "YIELD properties(vertex).group_id AS group_id, "
                "properties(vertex).code AS code, "
                "properties(vertex).name AS name, "
                "properties(vertex).purpose AS purpose, "
                "properties(vertex).expected_behavior AS expected_behavior, "
                "properties(vertex).sort_order AS sort_order;",
            )["stdout"]
        )

    question_ids: list[str] = []
    question_group_by_id: dict[str, str] = {}
    if group_ids:
        question_edge_rows = parse_table(
            gql(
                EVALUATION_SPACE,
                f"GO FROM {_vid_list(group_ids)} OVER contains_question "
                "YIELD src(edge) AS group_id, dst(edge) AS question_id, properties(edge).sort_order AS group_sort_order;",
            )["stdout"]
        )
        question_edge_rows.sort(key=lambda item: (group_ids.index(item.get("group_id", "")) if item.get("group_id", "") in group_ids else 999, int(item.get("group_sort_order") or 0)))
        for row in question_edge_rows:
            question_id = row.get("question_id", "")
            if not question_id:
                continue
            question_ids.append(question_id)
            question_group_by_id[question_id] = row.get("group_id", "")

    question_rows = []
    if question_ids:
        question_rows = parse_table(
            gql(
                EVALUATION_SPACE,
                f"FETCH PROP ON eval_question {_vid_list(question_ids)} "
                "YIELD properties(vertex).question_id AS question_id, "
                "properties(vertex).group_id AS group_id, "
                "properties(vertex).group_code AS group_code, "
                "properties(vertex).question_text AS question_text, "
                "properties(vertex).expected_behavior AS expected_behavior, "
                "properties(vertex).category AS category, "
                "properties(vertex).sort_order AS sort_order, "
                "properties(vertex).enabled AS enabled;",
            )["stdout"]
        )

    questions_by_group: dict[str, list[dict]] = {}
    for row in sorted(question_rows, key=lambda item: int(item.get("sort_order") or 0)):
        group_id = row.get("group_id", "") or question_group_by_id.get(row.get("question_id", ""), "")
        questions_by_group.setdefault(group_id, []).append(
            {
                "questionId": row.get("question_id", ""),
                "groupId": group_id,
                "groupCode": row.get("group_code", ""),
                "questionText": row.get("question_text", ""),
                "expectedBehavior": row.get("expected_behavior", ""),
                "category": row.get("category", ""),
                "sortOrder": int(row.get("sort_order") or 0),
                "enabled": str(row.get("enabled") or "").lower() != "false",
            }
        )

    suite = suite_rows[0]
    metadata = _parse_metadata(suite.get("metadata", ""))
    return {
        "suiteId": suite.get("suite_id", ""),
        "name": suite.get("name", ""),
        "description": suite.get("description", ""),
        "experimentId": suite.get("experiment_id", ""),
        "version": suite.get("version", ""),
        "questionCount": int(suite.get("question_count") or 0),
        "createdAt": suite.get("created_at", ""),
        "evaluationPrompt": str(metadata.get("evaluation_prompt") or ""),
        "groups": [
            {
                "groupId": row.get("group_id", ""),
                "code": row.get("code", ""),
                "name": row.get("name", ""),
                "purpose": row.get("purpose", ""),
                "expectedBehavior": row.get("expected_behavior", ""),
                "sortOrder": int(row.get("sort_order") or 0),
                "questions": questions_by_group.get(row.get("group_id", ""), []),
            }
            for row in sorted(group_rows, key=lambda item: int(item.get("sort_order") or 0))
        ],
    }
