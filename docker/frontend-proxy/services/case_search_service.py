from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


KB_PLUGIN_URL = os.getenv("KB_PLUGIN_URL", "http://host.docker.internal:3000/api/v1/chat/completions")
KB_PLUGIN_KEY_FILE = os.getenv(
    "KB_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/knowledge_base_query_plugin_api_key",
)

DATASET_MAP = {
    "breaker": {
        "kb_name": "llmkg_breaker",
        "display_name": "高压断路器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a88f",
        "space": "llmkg_breaker",
    },
    "cable": {
        "kb_name": "llmkg_cable",
        "display_name": "电力电缆知识库",
        "dataset_id": "69e8b07a796863b2e4d3a890",
        "space": "llmkg_cable",
    },
    "transformer": {
        "kb_name": "llmkg_transformer",
        "display_name": "变压器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a897",
        "space": "llmkg_transformer",
    },
    "surge_arrester": {
        "kb_name": "llmkg_surge_arrester",
        "display_name": "避雷器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a894",
        "space": "llmkg_surge_arrester",
    },
    "mutual": {
        "kb_name": "llmkg_mutual",
        "display_name": "互感器知识库",
        "dataset_id": "69e8b07a796863b2e4d3a891",
        "space": "llmkg_mutual",
    },
    "optical_cable": {
        "kb_name": "llmkg_optical_cable",
        "display_name": "光缆知识库",
        "dataset_id": "69e8b07a796863b2e4d3a892",
        "space": "llmkg_optical_cable",
    },
    "ring_main_unit": {
        "kb_name": "llmkg_ring_main_unit",
        "display_name": "环网柜知识库",
        "dataset_id": "69e8b07a796863b2e4d3a893",
        "space": "llmkg_ring_main_unit",
    },
}
DEVICE_TO_DATASET_KEY = {
    "高压断路器": "breaker",
    "断路器": "breaker",
    "开关柜": "breaker",
    "变压器": "transformer",
    "主变": "transformer",
    "电力电缆": "cable",
    "电缆": "cable",
    "避雷器": "surge_arrester",
    "互感器": "mutual",
    "电流互感器": "mutual",
    "电压互感器": "mutual",
    "光缆": "optical_cable",
    "环网柜": "ring_main_unit",
}
KB_NAME_TO_DATASET = {v["kb_name"]: v for v in DATASET_MAP.values()}


def parse_fault_scene(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def infer_dataset_with_context(question: str, fault_scene: str = "", graph_material: str = "", kb_name: str = "") -> dict[str, Any] | None:
    if kb_name and kb_name in KB_NAME_TO_DATASET:
        return KB_NAME_TO_DATASET[kb_name]

    parsed = parse_fault_scene(fault_scene)
    device_name = str(parsed.get("故障对象") or "").strip()
    if device_name and device_name != "未明确":
        dataset_key = DEVICE_TO_DATASET_KEY.get(device_name)
        if dataset_key and dataset_key in DATASET_MAP:
            return DATASET_MAP[dataset_key]

    text_parts = [question, str(fault_scene or ""), str(graph_material or "")]
    for key in ("故障二级节点", "事件场景", "关键处置要求"):
        value = parsed.get(key)
        if value:
            text_parts.append(str(value))
    haystack = " ".join(text_parts)
    for dataset_key, keywords in [
        ("breaker", ["断路器", "开关柜", "拒合", "拒动", "跳闸线圈", "液压机构", "弹簧机构"]),
        ("cable", ["电缆", "电缆沟", "中间接头", "终端头", "绝缘劣化", "击穿"]),
        ("transformer", ["变压器", "主变", "瓦斯", "有载调压", "套管", "油温", "电抗器"]),
        ("surge_arrester", ["避雷器", "阀片", "侧闪", "闪络", "脱落接地", "未有效动作"]),
        ("mutual", ["互感器", "CT", "TV", "末屏"]),
        ("optical_cable", ["光缆", "接续", "接头盒", "通信中断"]),
        ("ring_main_unit", ["环网柜", "开闭器"]),
    ]:
        if any(word in haystack for word in keywords):
            return DATASET_MAP[dataset_key]
    return None


def infer_dataset(question: str, pipeline_result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not pipeline_result:
        return infer_dataset_with_context(question)

    basic_info = pipeline_result.get("basic_info", {}) or {}
    fields = basic_info.get("fields", {}) or {}
    return infer_dataset_with_context(
        question,
        str(fields.get("故障与场景提取结果") or ""),
        str(fields.get("图谱检索方案素材") or ""),
        str(fields.get("知识库名") or ""),
    )


def read_plugin_key() -> str:
    path = Path(KB_PLUGIN_KEY_FILE)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"plugin key file is empty: {path}")
    return key


def run_case_search(question: str, dataset: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "stream": False,
        "detail": True,
        "variables": {
            "当前识别设备": [{"datasetId": dataset["dataset_id"]}],
            "用户问题": question,
        },
    }
    req = Request(
        KB_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_plugin_key()}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"case search HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"case search URL error: {exc}")

    plugin_output = None
    for node in body.get("responseData", []):
        if node.get("moduleType") == "pluginOutput":
            plugin_output = node.get("pluginOutput", {})
    cards: list[dict[str, Any]] = []
    if isinstance(plugin_output, dict):
        raw_cards = plugin_output.get("ICBM")
        if isinstance(raw_cards, list):
            for item in raw_cards[:6]:
                if not isinstance(item, dict):
                    continue
                score_parts = []
                score_values: dict[str, float] = {}
                for score in item.get("score", []):
                    if isinstance(score, dict) and isinstance(score.get("value"), (int, float)):
                        score_parts.append(f"{score.get('type', 'score')}={score['value']:.3f}")
                        score_values[str(score.get("type", ""))] = float(score["value"])
                cards.append(
                    {
                        "id": item.get("id"),
                        "title": str(item.get("sourceName") or "未命名案例"),
                        "kbId": str(item.get("datasetId") or ""),
                        "docId": str(item.get("collectionId") or ""),
                        "relevance": " / ".join(score_parts),
                        "excerpt": str(item.get("q") or item.get("a") or ""),
                        "_sort_score": score_values.get("reRank") or score_values.get("embedding") or score_values.get("rrf") or 0,
                    }
                )

    cards.sort(key=lambda c: c.pop("_sort_score", 0), reverse=True)

    if not cards:
        raise RuntimeError("case search returned no cards")

    return {
        "enabled": True,
        "status": "done",
        "kb_name": dataset["kb_name"],
        "display_name": dataset.get("display_name", dataset["kb_name"]),
        "dataset_id": dataset["dataset_id"],
        "query_question": question,
        "cards": cards,
    }
