#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import time
import urllib.error
import urllib.request
from typing import Any


REAL_QUERY_TEMPLATES = [
    {
        "name": "plugin_get_all_spaces",
        "space": "llmkg_breaker",
        "ngql": "SHOW SPACES;",
    },
    {
        "name": "plugin_base_catalog_breaker",
        "space": "llmkg_breaker",
        "ngql": "MATCH (l1:entity)-[:rel]->(l2:entity) WHERE l1.entity.lvl == 1 AND l2.entity.lvl == 2 RETURN l1.entity.source_id AS l1_source_id, l1.entity.name AS l1_name, l2.entity.source_id AS l2_source_id, l2.entity.name AS l2_name ORDER BY l1_source_id, l2_source_id;",
    },
    {
        "name": "plugin_base_catalog_transformer",
        "space": "llmkg_transformer",
        "ngql": "MATCH (l1:entity)-[:rel]->(l2:entity) WHERE l1.entity.lvl == 1 AND l2.entity.lvl == 2 RETURN l1.entity.source_id AS l1_source_id, l1.entity.name AS l1_name, l2.entity.source_id AS l2_source_id, l2.entity.name AS l2_name ORDER BY l1_source_id, l2_source_id;",
    },
    {
        "name": "plugin_base_catalog_transmission",
        "space": "llmkg_transmission_line",
        "ngql": "MATCH (l1:entity)-[:rel]->(l2:entity) WHERE l1.entity.lvl == 1 AND l2.entity.lvl == 2 RETURN l1.entity.source_id AS l1_source_id, l1.entity.name AS l1_name, l2.entity.source_id AS l2_source_id, l2.entity.name AS l2_name ORDER BY l1_source_id, l2_source_id;",
    },
    {
        "name": "plugin_downstream_breaker_refuse_trip",
        "space": "llmkg_breaker",
        "ngql": 'MATCH (s:entity)-[:rel*1..5]->(m:entity) WHERE s.entity.lvl == 2 AND s.entity.name == "拒动故障" RETURN DISTINCT m.entity.lvl AS lvl, m.entity.name AS name, m.entity.node_desc AS node_desc ORDER BY lvl, name;',
    },
    {
        "name": "plugin_downstream_transformer_bushing_lead",
        "space": "llmkg_transformer",
        "ngql": 'MATCH (s:entity)-[:rel*1..5]->(m:entity) WHERE s.entity.lvl == 2 AND s.entity.name == "变压器套管引线故障" RETURN DISTINCT m.entity.lvl AS lvl, m.entity.name AS name, m.entity.node_desc AS node_desc ORDER BY lvl, name;',
    },
    {
        "name": "plugin_downstream_transmission_foreign_object",
        "space": "llmkg_transmission_line",
        "ngql": 'MATCH (s:entity)-[:rel*1..5]->(m:entity) WHERE s.entity.lvl == 2 AND s.entity.name == "外力异物短路故障" RETURN DISTINCT m.entity.lvl AS lvl, m.entity.name AS name, m.entity.node_desc AS node_desc ORDER BY lvl, name;',
    },
    {
        "name": "plugin_template_split_query",
        "space": "llmkg_templates",
        "ngql": 'MATCH (t:template)-[:has_version]->(v:template_version)-[:has_section]->(s:template_section) WHERE id(t) == "tpl_default_emergency" AND v.template_version.version_name == t.template.current_version RETURN id(t) AS template_id, t.template.name AS template_name, t.template.current_version AS current_version, id(s) AS section_id, s.template_section.section_no AS section_no, s.template_section.title AS title, s.template_section.level AS level, s.template_section.order_no AS order_no, s.template_section.enabled AS enabled, s.template_section.source_type AS source_type, s.template_section.kg_field AS kg_field, s.template_section.fixed_text AS fixed_text, s.template_section.gen_instruction AS gen_instruction ORDER BY order_no;',
    },
]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    floor_idx = math.floor(k)
    ceil_idx = math.ceil(k)
    if floor_idx == ceil_idx:
        return values[floor_idx]
    return values[floor_idx] + (values[ceil_idx] - values[floor_idx]) * (k - floor_idx)


def do_request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.time()
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            return {
                "ok": bool(data.get("ok")),
                "status": response.status,
                "elapsed_ms": round((time.time() - started) * 1000, 2),
                "queue_wait_ms": data.get("queue_wait_ms"),
                "driver_mode": data.get("meta", {}).get("driver_mode"),
                "error_type": data.get("error_type"),
                "message": data.get("message"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        error_type = None
        message = body
        try:
            parsed = json.loads(body)
            error_type = parsed.get("error_type")
            message = parsed.get("message")
        except Exception:
            pass
        return {
            "ok": False,
            "status": exc.code,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "queue_wait_ms": None,
            "driver_mode": None,
            "error_type": error_type,
            "message": message,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "EXC",
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "queue_wait_ms": None,
            "driver_mode": None,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }


def run_level(url: str, concurrency: int, timeout: float) -> dict[str, Any]:
    payloads = [
        {
            "space": REAL_QUERY_TEMPLATES[index % len(REAL_QUERY_TEMPLATES)]["space"],
            "ngql": REAL_QUERY_TEMPLATES[index % len(REAL_QUERY_TEMPLATES)]["ngql"],
        }
        for index in range(concurrency)
    ]
    template_names = [REAL_QUERY_TEMPLATES[index % len(REAL_QUERY_TEMPLATES)]["name"] for index in range(concurrency)]
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda args: do_request(url, args[0], timeout) | {"template": args[1]}, zip(payloads, template_names)))
    wall_ms = round((time.time() - started) * 1000, 2)

    latencies = [item["elapsed_ms"] for item in results]
    queue_waits = [item["queue_wait_ms"] for item in results if isinstance(item.get("queue_wait_ms"), (int, float))]
    success = [item for item in results if item["ok"] and item["status"] == 200]
    failures = [item for item in results if not (item["ok"] and item["status"] == 200)]

    failure_statuses: dict[str, int] = {}
    failure_errors: dict[str, int] = {}
    template_usage: dict[str, int] = {}
    for item in results:
        template_usage[item["template"]] = template_usage.get(item["template"], 0) + 1
    for item in failures:
        failure_statuses[str(item["status"])] = failure_statuses.get(str(item["status"]), 0) + 1
        failure_errors[str(item.get("error_type") or "unknown")] = failure_errors.get(str(item.get("error_type") or "unknown"), 0) + 1

    return {
        "concurrency": concurrency,
        "template_mix": template_usage,
        "success_count": len(success),
        "failure_count": len(failures),
        "success_rate": round(len(success) / len(results) * 100, 2),
        "wall_ms": wall_ms,
        "latency_p50_ms": round(percentile(latencies, 0.5) or 0, 2),
        "latency_p95_ms": round(percentile(latencies, 0.95) or 0, 2),
        "latency_max_ms": round(max(latencies), 2),
        "queue_wait_p50_ms": round(percentile(queue_waits, 0.5) or 0, 2) if queue_waits else None,
        "queue_wait_p95_ms": round(percentile(queue_waits, 0.95) or 0, 2) if queue_waits else None,
        "driver_mode": success[0].get("driver_mode") if success else None,
        "failure_statuses": failure_statuses,
        "failure_errors": failure_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Nebula HTTP gateway with real plugin query templates.")
    parser.add_argument("--url", default="http://127.0.0.1:8787/graph/query")
    parser.add_argument("--start", type=int, default=50)
    parser.add_argument("--step", type=int, default=50)
    parser.add_argument("--max", type=int, default=550)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--good-p95-ms", type=float, default=3000)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    stop_reason = None
    for concurrency in range(args.start, args.max + 1, args.step):
        result = run_level(args.url, concurrency, args.timeout)
        results.append(result)
        if result["failure_count"] > 0:
            stop_reason = f"failures at concurrency={concurrency}"
            break
        if result["latency_p95_ms"] > args.good_p95_ms * 2:
            stop_reason = f"p95 latency too high at concurrency={concurrency}"
            break

    best_good = None
    for result in results:
        if result["failure_count"] == 0 and result["latency_p95_ms"] <= args.good_p95_ms:
            best_good = result

    print(json.dumps({
        "templates": REAL_QUERY_TEMPLATES,
        "tested_levels": results,
        "best_good_concurrency": best_good["concurrency"] if best_good else None,
        "criterion": f"100% success and p95 <= {args.good_p95_ms}ms",
        "stop_reason": stop_reason,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
