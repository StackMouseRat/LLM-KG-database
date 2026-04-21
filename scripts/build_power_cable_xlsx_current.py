from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path

from build_transmission_xlsx import write_workbook


BASE_DIR = Path("xls")
TEXT_DIR = Path("txt") / "电力电缆"
DEVICE_DIR = BASE_DIR / "电力电缆"
WORK_OUTPUT_DIR = DEVICE_DIR / "电力电缆_第一至第八层级图谱数据"
FINAL_OUTPUT_DIR = BASE_DIR / "成品" / "电力电缆" / "电力电缆_第一至第八层级图谱数据"

SECOND_LEVEL_MD = TEXT_DIR / "电力电缆故障层级梳理_第二层级.md"
LAYER_FILES = {
    "故障原因": TEXT_DIR / "电力电缆故障层级梳理_第三层级_故障原因.md",
    "故障现象": TEXT_DIR / "电力电缆故障层级梳理_第四层级_故障现象.md",
    "应对措施": TEXT_DIR / "电力电缆故障层级梳理_第五层级_应对措施.md",
    "故障后果": TEXT_DIR / "电力电缆故障层级梳理_第六层级_故障后果.md",
    "安全风险": TEXT_DIR / "电力电缆故障层级梳理_第七层级_安全风险.md",
    "应急资源": TEXT_DIR / "电力电缆故障层级梳理_第八层级_应急资源.md",
}

TEMPLATE_DIR = BASE_DIR / "示例_带样式完整版"
NODES_TEMPLATE = TEMPLATE_DIR / "节点_nodes.xlsx"
LINKS_TEMPLATE = TEMPLATE_DIR / "关系_links.xlsx"
GROUPS_TEMPLATE = TEMPLATE_DIR / "圈子_groups.xlsx"
MEMBERS_TEMPLATE = TEMPLATE_DIR / "圈子成员_group_members.xlsx"
BLOCKS_TEMPLATE = TEMPLATE_DIR / "区块_blocks.xlsx"
TAGS_TEMPLATE = TEMPLATE_DIR / "标签_tags.xlsx"
TAG_MEMBERS_TEMPLATE = TEMPLATE_DIR / "标签成员_tag_members.xlsx"

ROOT_NAME = "电力电缆"
ROOT_DESC = "依据第一至第八层级梳理结果形成的电力电缆故障知识图谱实体。"
IMAGE_URL = "https://nrdstudio.cn/res/n.jpg"
ROOT_COLOR = "#7C2D12"

DETAIL_LAYERS = [
    "故障原因",
    "故障现象",
    "应对措施",
    "故障后果",
    "安全风险",
    "应急资源",
]

LAYER_COLORS = {
    "故障原因": "#FA8C16",
    "故障现象": "#1890FF",
    "应对措施": "#52C41A",
    "故障后果": "#E8684A",
    "安全风险": "#722ED1",
    "应急资源": "#13C2C2",
}

GROUP_COLORS = {
    "绝缘系统故障": "#2563EB",
    "机械损伤故障": "#D97706",
    "接头与附件故障": "#0F766E",
    "热故障": "#EA580C",
    "火灾事故": "#B91C1C",
}

RELATION_COLORS = {
    "发生": "#5B8FF9",
    "包含": "#5B8FF9",
    "起因于": LAYER_COLORS["故障原因"],
    "表现": LAYER_COLORS["故障现象"],
    "处置": LAYER_COLORS["应对措施"],
    "导致": LAYER_COLORS["故障后果"],
    "存在": LAYER_COLORS["安全风险"],
    "需要": LAYER_COLORS["应急资源"],
}

RELATION_CHAIN = [
    ("起因于", "故障原因"),
    ("表现", "故障现象"),
    ("处置", "应对措施"),
    ("导致", "故障后果"),
    ("存在", "安全风险"),
    ("需要", "应急资源"),
]

LVL_MAP = {
    "root_node": 0,
    "fault_l1": 1,
    "fault_l2": 2,
    "fault_cause": 3,
    "response_measure": 3,
    "fault_symptom": 4,
    "fault_consequence": 4,
    "safety_risk": 4,
    "emergency_resource": 4,
}


def section_between(md_text: str, start_title: str, end_title: str | None) -> str:
    start = md_text.index(start_title)
    end = len(md_text) if end_title is None else md_text.index(end_title, start)
    return md_text[start:end]


def parse_majors_and_subtypes(md_text: str) -> tuple[list[str], dict[str, list[str]]]:
    section = section_between(md_text, "## 3. 第二层级推荐结果", "## 4. 推荐层级结构")
    subtype_map: dict[str, list[str]] = {}
    current_major = ""

    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("### 3."):
            current_major = re.sub(r"^###\s+3\.\d+\s+", "", stripped).strip()
            subtype_map[current_major] = []
            continue
        if current_major and re.match(r"^\d+\.\s+", stripped):
            _, name = stripped.split(".", 1)
            subtype_map[current_major].append(name.strip())

    return list(subtype_map.keys()), subtype_map


def parse_layer_file(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    details: dict[str, str] = {}
    current_subtype = ""
    capture_desc = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#### "):
            current_subtype = stripped[5:].strip()
            capture_desc = False
            continue
        if not current_subtype:
            continue
        if stripped.startswith("- 描述/说明："):
            inline = stripped.split("：", 1)[1].strip()
            if inline:
                details[current_subtype] = inline
                capture_desc = False
            else:
                capture_desc = True
            continue
        if capture_desc and stripped:
            details[current_subtype] = stripped
            capture_desc = False

    return details


def build_node_order(majors: list[str], subtype_map: dict[str, list[str]]) -> list[str]:
    ordered = [ROOT_NAME]
    ordered.extend(majors)
    for major in majors:
        for subtype in subtype_map[major]:
            ordered.append(subtype)
            for layer in DETAIL_LAYERS:
                ordered.append(f"{subtype}-{layer}")
    return ordered


def build_links(majors: list[str], subtype_map: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    links: list[tuple[str, str, str]] = []
    for major in majors:
        links.append((ROOT_NAME, major, "发生"))
        for subtype in subtype_map[major]:
            links.append((major, subtype, "包含"))
            cause = f"{subtype}-故障原因"
            symptom = f"{subtype}-故障现象"
            measure = f"{subtype}-应对措施"
            consequence = f"{subtype}-故障后果"
            risk = f"{subtype}-安全风险"
            resource = f"{subtype}-应急资源"
            links.append((subtype, cause, "起因于"))
            links.append((cause, symptom, "表现"))
            links.append((subtype, measure, "处置"))
            links.append((cause, consequence, "导致"))
            links.append((measure, risk, "存在"))
            links.append((measure, resource, "需要"))
    return links


def node_style(name: str, major_for_node: str | None) -> dict[str, str]:
    if name == ROOT_NAME:
        return {
            "fontFamily": "heiti",
            "fontSize": "30",
            "lineWidth": "5",
            "r": "100",
            "stroke": ROOT_COLOR,
            "textBorderWidth": "0",
            "weight": "10",
        }
    if name in GROUP_COLORS:
        return {
            "fontFamily": "heiti",
            "fontSize": "22",
            "lineWidth": "4",
            "r": "72",
            "stroke": GROUP_COLORS[name],
            "textBorderWidth": "0",
            "weight": "9",
        }
    for layer in DETAIL_LAYERS:
        if name.endswith(f"-{layer}"):
            return {
                "fontFamily": "heiti",
                "fontSize": "16",
                "lineWidth": "2",
                "r": "46",
                "stroke": LAYER_COLORS[layer],
                "textBorderWidth": "0",
                "weight": "6",
            }
    return {
        "fontFamily": "heiti",
        "fontSize": "18",
        "lineWidth": "3",
        "r": "58",
        "stroke": GROUP_COLORS[major_for_node],
        "textBorderWidth": "0",
        "weight": "8",
    }


def relation_style(relation: str, major: str | None) -> dict[str, str]:
    if relation in {"发生", "包含"}:
        stroke = GROUP_COLORS[major] if major else RELATION_COLORS[relation]
        width = "4" if relation == "发生" else "3"
    else:
        stroke = RELATION_COLORS[relation]
        width = "2"
    return {"lineWidth": width, "stroke": stroke, "textBorderWidth": "0"}


def write_output_set(
    output_dir: Path,
    node_rows: list[list[str]],
    link_rows: list[list[str]],
    group_rows: list[list[str]],
    member_rows: list[list[str]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_workbook(NODES_TEMPLATE, output_dir / "节点_nodes.xlsx", node_rows)
    write_workbook(LINKS_TEMPLATE, output_dir / "关系_links.xlsx", link_rows)
    write_workbook(GROUPS_TEMPLATE, output_dir / "圈子_groups.xlsx", group_rows)
    write_workbook(MEMBERS_TEMPLATE, output_dir / "圈子成员_group_members.xlsx", member_rows)
    shutil.copy2(BLOCKS_TEMPLATE, output_dir / "区块_blocks.xlsx")
    shutil.copy2(TAGS_TEMPLATE, output_dir / "标签_tags.xlsx")
    shutil.copy2(TAG_MEMBERS_TEMPLATE, output_dir / "标签成员_tag_members.xlsx")


def typed_tag_for_name(name: str, majors: set[str], subtypes: set[str]) -> str:
    if name == ROOT_NAME:
        return "root_node"
    if name in majors:
        return "fault_l1"
    if name in subtypes:
        return "fault_l2"
    if name.endswith("-故障原因"):
        return "fault_cause"
    if name.endswith("-故障现象"):
        return "fault_symptom"
    if name.endswith("-应对措施"):
        return "response_measure"
    if name.endswith("-故障后果"):
        return "fault_consequence"
    if name.endswith("-安全风险"):
        return "safety_risk"
    if name.endswith("-应急资源"):
        return "emergency_resource"
    raise ValueError(f"无法识别节点类型: {name}")


def main() -> None:
    second_level_text = SECOND_LEVEL_MD.read_text(encoding="utf-8")
    majors, subtype_map = parse_majors_and_subtypes(second_level_text)
    layer_details = {layer: parse_layer_file(path) for layer, path in LAYER_FILES.items()}

    ordered_subtypes = [subtype for major in majors for subtype in subtype_map[major]]
    for layer in DETAIL_LAYERS:
        missing = [subtype for subtype in ordered_subtypes if subtype not in layer_details[layer]]
        if missing:
            raise ValueError(f"{layer} 缺少描述: {missing}")

    ordered_names = build_node_order(majors, subtype_map)
    links = build_links(majors, subtype_map)

    major_for_node: dict[str, str] = {}
    for major in majors:
        major_for_node[major] = major
        for subtype in subtype_map[major]:
            major_for_node[subtype] = major
            for layer in DETAIL_LAYERS:
                major_for_node[f"{subtype}-{layer}"] = major

    degree = Counter()
    for source, target, _ in links:
        degree[source] += 1
        degree[target] += 1

    node_rows = [[
        "id",
        "name",
        "degree",
        "desc",
        "fontFamily",
        "fontSize",
        "image",
        "lineWidth",
        "r",
        "stroke",
        "textBorderWidth",
        "weight",
    ]]

    node_id_map: dict[str, int] = {}
    subtypes_set = set(ordered_subtypes)
    majors_set = set(majors)
    manifest_nodes: list[dict[str, object]] = []

    for index, name in enumerate(ordered_names):
        node_id_map[name] = index
        style = node_style(name, major_for_node.get(name))
        typed_tag = typed_tag_for_name(name, majors_set, subtypes_set)
        lvl = LVL_MAP[typed_tag]

        if name == ROOT_NAME:
            desc = ROOT_DESC
        elif name in majors:
            desc = f"电力电缆故障一级大类：{name}。"
        elif name in ordered_subtypes:
            desc = f"{major_for_node[name]}下的二级故障小类：{name}。"
        else:
            subtype, layer = name.rsplit("-", 1)
            desc = layer_details[layer][subtype]

        node_rows.append([
            str(index),
            name,
            str(degree[name]),
            desc,
            style["fontFamily"],
            style["fontSize"],
            IMAGE_URL,
            style["lineWidth"],
            style["r"],
            style["stroke"],
            style["textBorderWidth"],
            style["weight"],
        ])

        manifest_nodes.append({
            "vid": f"n_{index}",
            "name": name,
            "node_desc": desc,
            "lvl": lvl,
            "source_id": index,
            "degree": degree[name],
            "weight": int(style["weight"]),
            "stroke": style["stroke"],
            "typed_tag": typed_tag,
            "major": major_for_node.get(name, ""),
        })

    link_rows = [[
        "id",
        "from",
        "fromNodeName",
        "lineWidth",
        "relation",
        "stroke",
        "textBorderWidth",
        "to",
        "toNodeName",
    ]]

    manifest_links: list[dict[str, str]] = []
    for index, (source, target, relation) in enumerate(links):
        major = target if relation == "发生" else major_for_node.get(source)
        style = relation_style(relation, major)
        link_rows.append([
            str(index),
            str(node_id_map[source]),
            source,
            style["lineWidth"],
            relation,
            style["stroke"],
            style["textBorderWidth"],
            str(node_id_map[target]),
            target,
        ])
        manifest_links.append({
            "src": f"n_{node_id_map[source]}",
            "dst": f"n_{node_id_map[target]}",
            "relation": relation,
        })

    group_rows = [[
        "id",
        "name",
        "desc",
        "member_count",
        "order",
        "show",
        "type",
        "itemStyle.fill",
        "itemStyle.markColor",
        "itemStyle.stroke",
    ]]

    member_rows = [[
        "id",
        "name",
        "member_id",
        "member_name",
    ]]

    for group_id, major in enumerate(majors):
        members = [major]
        for subtype in subtype_map[major]:
            members.append(subtype)
            for layer in DETAIL_LAYERS:
                members.append(f"{subtype}-{layer}")

        color = GROUP_COLORS[major]
        group_rows.append([
            str(group_id),
            major,
            f"{major}的第一至第八层级图谱分组。",
            str(len(members)),
            str(group_id),
            "0",
            "1",
            color,
            color,
            color,
        ])

        for member in members:
            member_rows.append([
                str(group_id),
                major,
                str(node_id_map[member]),
                member,
            ])

    write_output_set(WORK_OUTPUT_DIR, node_rows, link_rows, group_rows, member_rows)
    write_output_set(FINAL_OUTPUT_DIR, node_rows, link_rows, group_rows, member_rows)

    manifest = {
        "space": "llmkg_cable",
        "root": ROOT_NAME,
        "majors": majors,
        "subtypes": ordered_subtypes,
        "detail_layers": DETAIL_LAYERS,
        "nodes": manifest_nodes,
        "links": manifest_links,
        "counts": {
            "nodes": len(manifest_nodes),
            "links": len(manifest_links),
            "groups": len(group_rows) - 1,
            "group_members": len(member_rows) - 1,
        },
    }
    for output_dir in (WORK_OUTPUT_DIR, FINAL_OUTPUT_DIR):
        (output_dir / "graph_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"work_output={WORK_OUTPUT_DIR}")
    print(f"final_output={FINAL_OUTPUT_DIR}")
    print(f"nodes={len(manifest_nodes)}")
    print(f"links={len(manifest_links)}")
    print(f"groups={len(group_rows) - 1}")
    print(f"group_members={len(member_rows) - 1}")


if __name__ == "__main__":
    main()
