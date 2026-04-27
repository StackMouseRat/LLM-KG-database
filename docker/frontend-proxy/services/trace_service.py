from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import jieba


GRAPH_SPACE_HINTS = [
    {
        "space": "llmkg_breaker",
        "device": "高压断路器",
        "keywords": ["断路器", "高压断路器", "拒动", "拒合", "液压机构", "弹簧机构"],
    },
    {
        "space": "llmkg_transformer",
        "device": "变压器",
        "keywords": ["变压器", "主变", "套管", "瓦斯", "油温", "有载调压", "电抗器"],
    },
    {
        "space": "llmkg_cable",
        "device": "电力电缆",
        "keywords": ["电缆", "电力电缆", "中间接头", "终端头", "电缆沟", "击穿"],
    },
    {
        "space": "llmkg_mutual",
        "device": "互感器",
        "keywords": ["互感器", "电流互感器", "电压互感器", "CT", "TV", "末屏"],
    },
    {
        "space": "llmkg_optical_cable",
        "device": "光缆",
        "keywords": ["光缆", "接续", "接头盒", "通信中断"],
    },
    {
        "space": "llmkg_ring_main_unit",
        "device": "环网柜",
        "keywords": ["环网柜", "开闭器"],
    },
    {
        "space": "llmkg_surge_arrester",
        "device": "避雷器",
        "keywords": ["避雷器", "阀片", "污闪", "侧闪", "闪络"],
    },
    {
        "space": "llmkg_tower",
        "device": "杆塔",
        "keywords": ["杆塔", "塔位", "基础冲刷", "倾斜"],
    },
    {
        "space": "llmkg_transmission_line",
        "device": "输电线路",
        "keywords": [
            "输电线路",
            "导线",
            "雷击跳闸",
            "雷击闪络",
            "感应雷",
            "反击雷",
            "绕击雷",
            "避雷线",
            "覆冰",
            "覆冰过荷载",
            "脱冰跳跃",
            "污闪",
            "积污污闪",
            "风害",
            "风偏闪络",
            "舞动",
            "鸟害",
            "外力破坏",
            "吊车碰线",
            "山火",
            "烟火短路",
        ],
    },
]
TRACE_EDGE_LABELS = {
    "has_fault_category": "发生",
    "contains": "包含",
    "caused_by": "故障原因",
    "has_symptom": "故障现象",
    "handled_by": "应对措施",
    "results_in": "故障后果",
    "has_risk": "安全风险",
    "needs_resource": "应急资源",
}


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


def infer_graph_space_with_context(question: str, fault_scene: str = "", graph_material: str = "") -> dict[str, str] | None:
    text_parts = [question, str(fault_scene or ""), str(graph_material or "")]
    parsed = parse_fault_scene(fault_scene)
    for key in ("故障对象", "故障二级节点", "事件场景", "关键处置要求", "特殊约束"):
        value = parsed.get(key)
        if value:
            text_parts.append(str(value))

    haystack = " ".join(text_parts)
    for item in GRAPH_SPACE_HINTS:
        if any(word in haystack for word in item["keywords"]):
            return {"space": item["space"], "device": item["device"]}
    return None


def first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_fault_names(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                result.append(candidate)
        elif isinstance(value, list):
            for item in value:
                candidate = str(item or "").strip()
                if candidate:
                    result.append(candidate)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in result:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def wrap_fault_l2_label(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value

    words = [str(item).strip() for item in jieba.lcut(value) if str(item).strip()]
    if len(words) <= 1:
        return value

    total_length = 0
    split_index = -1
    for index, word in enumerate(words):
        total_length += len(word)
        if total_length > 3:
            split_index = index
            break

    if split_index < 0 or split_index >= len(words) - 1:
        return value

    left = "".join(words[: split_index + 1])
    right = "".join(words[split_index + 1:])
    if len(right) > 5:
        right = wrap_fault_l2_label(right)
    return left + "\n" + right


def extract_trace_focus_fields(
    question: str,
    fault_scene: str = "",
    graph_material: str = "",
    device_hint: str = "",
    fault_hint: str = "",
) -> dict[str, Any]:
    parsed = parse_fault_scene(fault_scene)
    graph_material_parsed = parse_fault_scene(graph_material)
    explicit_space = first_non_empty(
        graph_material_parsed.get("设备表"),
        parsed.get("设备表"),
        graph_material_parsed.get("space"),
        parsed.get("space"),
    )

    device_name = first_non_empty(
        device_hint,
        parsed.get("故障对象"),
        parsed.get("设备"),
        parsed.get("设备名称"),
    )
    fault_names = normalize_fault_names(
        parsed.get("主故障二级节点"),
        parsed.get("故障二级节点"),
        graph_material_parsed.get("主故障二级节点"),
        graph_material_parsed.get("故障二级节点"),
    )
    fault_name = first_non_empty(
        fault_hint,
        parsed.get("主故障二级节点"),
        parsed.get("当前故障分析"),
        parsed.get("二级故障名称"),
        graph_material_parsed.get("主故障二级节点"),
    )
    if not fault_name and fault_names:
        fault_name = fault_names[0]

    if not fault_name:
        for text in (fault_scene, graph_material, question):
            if not isinstance(text, str) or not text.strip():
                continue
            for pattern in (
                r"(?:故障二级节点|当前二级故障|当前故障分析)[：:\"]+\s*\"?([^\"，,\n]+?故障)\"?",
                r"(?:匹配故障|当前故障)[：:\"]+\s*\"?([^\"，,\n]+?故障)\"?",
            ):
                matched = re.search(pattern, text)
                if matched:
                    fault_name = matched.group(1).strip()
                    break
            if fault_name:
                break

    graph_space = {"space": explicit_space, "device": ""} if explicit_space else infer_graph_space_with_context(question, fault_scene, graph_material)
    return {
        "space": graph_space.get("space") if graph_space else "",
        "device": device_name or (graph_space.get("device") if graph_space else ""),
        "fault": fault_name,
        "faults": fault_names or ([fault_name] if fault_name else []),
    }


def query_rows(graph_query: Callable[[str, str], dict[str, Any]], space: str, ngql: str) -> list[dict[str, str]]:
    return parse_table(str(graph_query(space, ngql).get("stdout") or ""))


def get_trace_candidate_spaces(preferred_space: str = "") -> list[str]:
    spaces: list[str] = []
    if preferred_space:
        spaces.append(preferred_space)
    for item in GRAPH_SPACE_HINTS:
        space = str(item.get("space") or "").strip()
        if space and space not in spaces:
            spaces.append(space)
    return spaces


def add_trace_node(
    nodes: dict[str, dict[str, Any]],
    node_id: str,
    label: str,
    node_type: str,
    desc: str = "",
    is_focus: bool = False,
    is_hit: bool = False,
) -> None:
    if not node_id:
        return
    existing = nodes.get(node_id)
    wrapped_label = wrap_fault_l2_label(label) if node_type in {"fault_l1", "fault_l2"} else ""
    payload: dict[str, Any] = {
        "id": node_id,
        "label": label or node_id,
        "type": node_type,
        "desc": desc,
    }
    if is_focus:
        payload["isFocus"] = True
    if is_hit:
        payload["isHit"] = True
    if wrapped_label:
        payload["wrappedLabel"] = wrapped_label
    if existing:
        if is_focus:
            existing["isFocus"] = True
        if is_hit:
            existing["isHit"] = True
        if wrapped_label and not existing.get("wrappedLabel"):
            existing["wrappedLabel"] = wrapped_label
        if desc and not existing.get("desc"):
            existing["desc"] = desc
        return
    nodes[node_id] = payload


def add_trace_edge(edges: dict[str, dict[str, Any]], source: str, target: str, label: str, is_hit: bool = False) -> None:
    if not source or not target:
        return
    edge_id = f"{source}->{label}->{target}"
    display_label = TRACE_EDGE_LABELS.get(label, label)
    edge = edges.setdefault(
        edge_id,
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": display_label,
        },
    )
    if is_hit:
        edge["isHit"] = True


def build_trace_subgraph(
    space: str,
    fault_name: str,
    *,
    graph_query: Callable[[str, str], dict[str, Any]],
    device_name: str = "",
    hit_fault_names: list[str] | None = None,
) -> dict[str, Any]:
    if not fault_name:
        raise RuntimeError("trace fault name is empty")

    upstream_ngql = (
        "MATCH (r:root_node)-[:has_fault_category]->(l1:fault_l1)-[:contains]->(l2:fault_l2) "
        "RETURN id(r) AS root_id, r.root_node.name AS root_name, r.root_node.node_desc AS root_desc, "
        "id(l1) AS l1_id, l1.fault_l1.name AS l1_name, l1.fault_l1.node_desc AS l1_desc, "
        "id(l2) AS l2_id, l2.fault_l2.name AS l2_name, l2.fault_l2.node_desc AS l2_desc;"
    )
    normalized_fault = fault_name.strip()
    normalized_hit_faults = normalize_fault_names(hit_fault_names or [], normalized_fault)
    normalized_hit_fault_set = set(normalized_hit_faults)

    effective_space = ""
    upstream_rows: list[dict[str, str]] = []
    filtered_rows: list[dict[str, str]] = []
    last_error = ""

    for candidate_space in get_trace_candidate_spaces(space):
        try:
            candidate_rows = query_rows(graph_query, candidate_space, upstream_ngql)
        except Exception as exc:
            last_error = str(exc)
            continue
        if not candidate_rows:
            continue

        candidate_filtered_rows = [
            item for item in candidate_rows
            if str(item.get("l2_name") or "").strip() == normalized_fault
        ]
        if device_name:
            candidate_filtered_rows = [
                item for item in candidate_filtered_rows
                if device_name in str(item.get("root_name") or "")
            ] or candidate_filtered_rows
        if not candidate_filtered_rows:
            candidate_filtered_rows = [
                item for item in candidate_rows
                if normalized_fault in str(item.get("l2_name") or "")
            ]
            if device_name:
                candidate_filtered_rows = [
                    item for item in candidate_filtered_rows
                    if device_name in str(item.get("root_name") or "")
                ] or candidate_filtered_rows

        if candidate_filtered_rows:
            effective_space = candidate_space
            upstream_rows = candidate_rows
            filtered_rows = candidate_filtered_rows
            break

    if not filtered_rows:
        if last_error:
            raise RuntimeError(f"trace root path not found for fault: {fault_name}; last error: {last_error}")
        raise RuntimeError(f"trace root path not found for fault: {fault_name}")

    row = filtered_rows[0]
    root_id = str(row.get("root_id") or "")
    l1_id = str(row.get("l1_id") or "")
    l2_id = str(row.get("l2_id") or "")

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    root_name = str(row.get("root_name") or device_name or "设备根节点")

    root_filter_rows = [item for item in upstream_rows if str(item.get("root_id") or "") == root_id]
    hit_rows = [
        item
        for item in root_filter_rows
        if str(item.get("l2_name") or "").strip() in normalized_hit_fault_set
    ]
    if not hit_rows:
        hit_rows = [row]
    hit_root_ids = {str(item.get("root_id") or "") for item in hit_rows}
    hit_l1_ids = {str(item.get("l1_id") or "") for item in hit_rows}
    hit_l2_ids = {str(item.get("l2_id") or "") for item in hit_rows}
    hit_node_ids = {root_id, *hit_root_ids, *hit_l1_ids, *hit_l2_ids}
    hit_edge_keys = {
        f"{str(item.get('root_id') or '')}->has_fault_category->{str(item.get('l1_id') or '')}"
        for item in hit_rows
    }
    hit_edge_keys.update(
        f"{str(item.get('l1_id') or '')}->contains->{str(item.get('l2_id') or '')}"
        for item in hit_rows
    )
    for item in root_filter_rows:
        item_root_id = str(item.get("root_id") or "")
        item_l1_id = str(item.get("l1_id") or "")
        item_l2_id = str(item.get("l2_id") or "")
        add_trace_node(nodes, item_root_id, str(item.get("root_name") or root_name), "root_node", str(item.get("root_desc") or ""), is_hit=item_root_id in hit_node_ids)
        add_trace_node(nodes, item_l1_id, str(item.get("l1_name") or "一级故障"), "fault_l1", str(item.get("l1_desc") or ""), is_hit=item_l1_id in hit_node_ids)
        add_trace_node(nodes, item_l2_id, str(item.get("l2_name") or "二级故障"), "fault_l2", str(item.get("l2_desc") or ""), is_focus=item_l2_id == l2_id, is_hit=item_l2_id in hit_node_ids)
        add_trace_edge(edges, item_root_id, item_l1_id, "has_fault_category", is_hit=f"{item_root_id}->has_fault_category->{item_l1_id}" in hit_edge_keys)
        add_trace_edge(edges, item_l1_id, item_l2_id, "contains", is_hit=f"{item_l1_id}->contains->{item_l2_id}" in hit_edge_keys)

    cause_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, "
            "c.fault_cause.name AS cause_name, c.fault_cause.node_desc AS cause_desc;"
        ),
    )
    for cause in cause_rows:
        current_l2_id = str(cause.get("l2_id") or "")
        cause_id = str(cause.get("cause_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(cause_id)
            hit_edge_keys.add(f"{current_l2_id}->caused_by->{cause_id}")
        add_trace_node(nodes, cause_id, str(cause.get("cause_name") or "故障原因"), "fault_cause", str(cause.get("cause_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, current_l2_id, cause_id, "caused_by", is_hit=is_hit)

    symptom_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause)-[:has_symptom]->(s:fault_symptom) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, id(s) AS symptom_id, "
            "s.fault_symptom.name AS symptom_name, s.fault_symptom.node_desc AS symptom_desc;"
        ),
    )
    for symptom in symptom_rows:
        current_l2_id = str(symptom.get("l2_id") or "")
        cause_id = str(symptom.get("cause_id") or "")
        symptom_id = str(symptom.get("symptom_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(symptom_id)
            hit_edge_keys.add(f"{cause_id}->has_symptom->{symptom_id}")
        add_trace_node(nodes, symptom_id, str(symptom.get("symptom_name") or "故障现象"), "fault_symptom", str(symptom.get("symptom_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, cause_id, symptom_id, "has_symptom", is_hit=is_hit)

    consequence_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:caused_by]->(c:fault_cause)-[:results_in]->(co:fault_consequence) "
            "RETURN id(l2) AS l2_id, id(c) AS cause_id, id(co) AS consequence_id, "
            "co.fault_consequence.name AS consequence_name, co.fault_consequence.node_desc AS consequence_desc;"
        ),
    )
    for consequence in consequence_rows:
        current_l2_id = str(consequence.get("l2_id") or "")
        cause_id = str(consequence.get("cause_id") or "")
        consequence_id = str(consequence.get("consequence_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(consequence_id)
            hit_edge_keys.add(f"{cause_id}->results_in->{consequence_id}")
        add_trace_node(nodes, consequence_id, str(consequence.get("consequence_name") or "故障后果"), "fault_consequence", str(consequence.get("consequence_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, cause_id, consequence_id, "results_in", is_hit=is_hit)

    measure_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, "
            "m.response_measure.name AS measure_name, m.response_measure.node_desc AS measure_desc;"
        ),
    )
    for measure in measure_rows:
        current_l2_id = str(measure.get("l2_id") or "")
        measure_id = str(measure.get("measure_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(measure_id)
            hit_edge_keys.add(f"{current_l2_id}->handled_by->{measure_id}")
        add_trace_node(nodes, measure_id, str(measure.get("measure_name") or "应对措施"), "response_measure", str(measure.get("measure_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, current_l2_id, measure_id, "handled_by", is_hit=is_hit)

    risk_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure)-[:has_risk]->(r:safety_risk) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, id(r) AS risk_id, "
            "r.safety_risk.name AS risk_name, r.safety_risk.node_desc AS risk_desc;"
        ),
    )
    for risk in risk_rows:
        current_l2_id = str(risk.get("l2_id") or "")
        measure_id = str(risk.get("measure_id") or "")
        risk_id = str(risk.get("risk_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(risk_id)
            hit_edge_keys.add(f"{measure_id}->has_risk->{risk_id}")
        add_trace_node(nodes, risk_id, str(risk.get("risk_name") or "安全风险"), "safety_risk", str(risk.get("risk_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, measure_id, risk_id, "has_risk", is_hit=is_hit)

    resource_rows = query_rows(
        graph_query,
        effective_space,
        (
            "MATCH (l2:fault_l2)-[:handled_by]->(m:response_measure)-[:needs_resource]->(er:emergency_resource) "
            "RETURN id(l2) AS l2_id, id(m) AS measure_id, id(er) AS resource_id, "
            "er.emergency_resource.name AS resource_name, er.emergency_resource.node_desc AS resource_desc;"
        ),
    )
    for resource in resource_rows:
        current_l2_id = str(resource.get("l2_id") or "")
        measure_id = str(resource.get("measure_id") or "")
        resource_id = str(resource.get("resource_id") or "")
        is_hit = current_l2_id in hit_l2_ids
        if is_hit:
            hit_node_ids.add(resource_id)
            hit_edge_keys.add(f"{measure_id}->needs_resource->{resource_id}")
        add_trace_node(nodes, resource_id, str(resource.get("resource_name") or "应急资源"), "emergency_resource", str(resource.get("resource_desc") or ""), is_hit=is_hit)
        add_trace_edge(edges, measure_id, resource_id, "needs_resource", is_hit=is_hit)

    for node_id in hit_node_ids:
        if node_id in nodes:
            nodes[node_id]["isHit"] = True

    return {
        "device": str(row.get("root_name") or device_name or ""),
        "fault": str(row.get("l2_name") or fault_name),
        "graph": {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        },
        "rawDetail": {
            "space": effective_space,
            "deviceHint": device_name,
            "faultHint": fault_name,
            "faultHints": normalized_hit_faults,
            "focusPath": [root_id, l1_id, l2_id],
        },
    }
