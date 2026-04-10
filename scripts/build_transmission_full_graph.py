from __future__ import annotations

import shutil
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_transmission_xlsx import write_workbook


BASE_DIR = Path("xls")
DEVICE_DIR = BASE_DIR / "输电线路"
TEXT_DIR = Path("txt") / "输电线路"

SUMMARY_MD = TEXT_DIR / "输电线路故障层级梳理_第一至第七层级汇总稿.md"
if not SUMMARY_MD.exists():
    SUMMARY_MD = max(
        (p for p in TEXT_DIR.glob("*.md") if "工作流程" not in p.name),
        key=lambda p: p.stat().st_mtime,
    )

TEMPLATE_DIR = DEVICE_DIR / "输电线路_样式完整版"
OUTPUT_DIR = DEVICE_DIR / "成品" / "输电线路_第一至第七层级图谱数据"

NODES_TEMPLATE = TEMPLATE_DIR / "节点_nodes.xlsx"
LINKS_TEMPLATE = TEMPLATE_DIR / "关系_links.xlsx"
GROUPS_TEMPLATE = TEMPLATE_DIR / "圈子_groups.xlsx"
MEMBERS_TEMPLATE = TEMPLATE_DIR / "圈子成员_group_members.xlsx"
BLOCKS_TEMPLATE = TEMPLATE_DIR / "区块_blocks.xlsx"
TAGS_TEMPLATE = TEMPLATE_DIR / "标签_tags.xlsx"
TAG_MEMBERS_TEMPLATE = TEMPLATE_DIR / "标签成员_tag_members.xlsx"

NODES_OUTPUT = OUTPUT_DIR / "节点_nodes.xlsx"
LINKS_OUTPUT = OUTPUT_DIR / "关系_links.xlsx"
GROUPS_OUTPUT = OUTPUT_DIR / "圈子_groups.xlsx"
MEMBERS_OUTPUT = OUTPUT_DIR / "圈子成员_group_members.xlsx"
BLOCKS_OUTPUT = OUTPUT_DIR / "区块_blocks.xlsx"
TAGS_OUTPUT = OUTPUT_DIR / "标签_tags.xlsx"
TAG_MEMBERS_OUTPUT = OUTPUT_DIR / "标签成员_tag_members.xlsx"

ROOT_NAME = "输电线路"
ROOT_DESC = "依据第一至第七层级汇总稿形成的输电线路故障知识图谱实体。"
ROOT_COLOR = "#1F3A5F"

DETAIL_LAYERS = [
    "故障原因",
    "故障现象",
    "应对措施",
    "故障后果",
    "安全风险",
    "应急资源",
]

LAYER_TITLES = {
    "故障原因": "## 第二层级：故障原因（单节点设计）",
    "故障现象": "## 第三层级：故障现象（单节点设计）",
    "应对措施": "## 第四层级：应对措施（单节点设计）",
    "故障后果": "## 第五层级：故障后果（单节点设计）",
    "安全风险": "## 第六层级：安全风险（单节点设计）",
    "应急资源": "## 第七层级：应急资源（单节点设计）",
}

LAYER_COLORS = {
    "故障原因": "#FA8C16",
    "故障现象": "#1890FF",
    "应对措施": "#52C41A",
    "故障后果": "#E8684A",
    "安全风险": "#722ED1",
    "应急资源": "#13C2C2",
}

RELATION_COLORS = {
    "发生": "#5B8FF9",
    "包含": "#5B8FF9",
    "起因于": LAYER_COLORS["故障原因"],
    "表现": LAYER_COLORS["故障现象"],
    "导致": LAYER_COLORS["故障后果"],
    "处置": LAYER_COLORS["应对措施"],
    "针对性": LAYER_COLORS["应对措施"],
    "存在": LAYER_COLORS["安全风险"],
    "需要": LAYER_COLORS["应急资源"],
}

GROUP_COLORS = {
    "覆冰故障": "#6DC8EC",
    "舞动故障": "#5AD8A6",
    "雷击闪络故障": "#F6BD16",
    "外力破坏故障": "#E8684A",
    "风害故障": "#5B8FF9",
    "鸟害故障": "#9270CA",
    "污闪故障": "#FF9D4D",
}

MAJOR_DESCRIPTIONS = {
    "覆冰故障": "输电线路因覆冰导致机械性能和电气性能下降的一级故障大类。",
    "舞动故障": "输电线路导线舞动引发的机械和电气故障大类。",
    "雷击闪络故障": "输电线路受雷电过电压冲击引发闪络的一级故障大类。",
    "外力破坏故障": "输电线路受外部人为或环境作用破坏形成的一级故障大类。",
    "风害故障": "输电线路受强风及其伴生效应影响形成的一级故障大类。",
    "鸟害故障": "输电线路受鸟类活动及相关诱发因素影响形成的一级故障大类。",
    "污闪故障": "输电线路绝缘表面污秽受潮后发生放电闪络的一级故障大类。",
}


def section_between(md_text: str, start_title: str, end_title: str | None) -> str:
    start = md_text.index(start_title)
    if end_title is None:
        end = len(md_text)
    else:
        end = md_text.index(end_title, start)
    return md_text[start:end]


def normalize_heading_name(text: str) -> str:
    return re.sub(r"^\d+\.\s*", "", text).strip()


def parse_majors(md_text: str) -> list[str]:
    section = section_between(md_text, "## 定稿后的一级大类", "## 定稿后的二级小类")
    majors: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit():
            continue
        _, name = stripped.split(".", 1)
        majors.append(name.strip())
    return majors


def parse_subtypes(md_text: str) -> dict[str, list[str]]:
    section = section_between(md_text, "## 定稿后的二级小类", "## 定稿后的推荐层级结构")
    subtype_map: dict[str, list[str]] = defaultdict(list)
    current_major = ""
    collecting = False
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            current_major = normalize_heading_name(stripped.split(" ", 1)[1])
            collecting = True
            continue
        if stripped == "说明：":
            collecting = False
            continue
        if stripped.startswith("- ") and current_major and collecting:
            subtype_map[current_major].append(stripped[2:].strip())
    return subtype_map


def parse_layer_details(md_text: str, layer_name: str, next_title: str | None) -> dict[str, str]:
    section = section_between(md_text, LAYER_TITLES[layer_name], next_title)
    lines = section.splitlines()

    details: dict[str, str] = {}
    current_subtype = ""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith("#### ") and not stripped.startswith("#### 示例："):
            current_subtype = stripped[5:].strip()
            i += 1
            continue

        if stripped.startswith("- 描述/说明：") and current_subtype:
            fragments = []
            tail = stripped.split("：", 1)[1].strip()
            if tail:
                fragments.append(tail)

            i += 1
            while i < len(lines):
                next_line = lines[i]
                next_stripped = next_line.strip()
                if not next_stripped:
                    i += 1
                    continue
                if next_stripped.startswith("## ") or next_stripped.startswith("### ") or next_stripped.startswith("#### "):
                    break
                if next_stripped.startswith("- ") and not next_line.startswith("  "):
                    break
                fragments.append(next_stripped)
                i += 1

            details[current_subtype] = " ".join(fragments).strip()
            continue

        i += 1

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
    for major in majors:
        for subtype in subtype_map[major]:
            cause = f"{subtype}-故障原因"
            phenomenon = f"{subtype}-故障现象"
            measure = f"{subtype}-应对措施"
            consequence = f"{subtype}-故障后果"
            risk = f"{subtype}-安全风险"
            resource = f"{subtype}-应急资源"

            links.append((major, subtype, "包含"))
            links.append((subtype, cause, "起因于"))
            links.append((cause, phenomenon, "表现"))
            links.append((cause, consequence, "导致"))
            links.append((subtype, measure, "处置"))
            links.append((cause, measure, "针对性"))
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


def copy_optional_templates() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BLOCKS_TEMPLATE, BLOCKS_OUTPUT)
    shutil.copy2(TAGS_TEMPLATE, TAGS_OUTPUT)
    shutil.copy2(TAG_MEMBERS_TEMPLATE, TAG_MEMBERS_OUTPUT)


def main() -> None:
    md_text = SUMMARY_MD.read_text(encoding="utf-8")

    majors = parse_majors(md_text)
    subtype_map = parse_subtypes(md_text)

    layer_details: dict[str, dict[str, str]] = {}
    layer_order = DETAIL_LAYERS
    for index, layer in enumerate(layer_order):
        next_title = LAYER_TITLES[layer_order[index + 1]] if index + 1 < len(layer_order) else None
        layer_details[layer] = parse_layer_details(md_text, layer, next_title)

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
    for index, name in enumerate(ordered_names):
        node_id_map[name] = index
        style = node_style(name, major_for_node.get(name))

        if name == ROOT_NAME:
            desc = ROOT_DESC
        elif name in majors:
            desc = MAJOR_DESCRIPTIONS[name]
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
            "https://nrdstudio.cn/res/n.jpg",
            style["lineWidth"],
            style["r"],
            style["stroke"],
            style["textBorderWidth"],
            style["weight"],
        ])

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
            f"{major}的第一至第七层级图谱分组。",
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

    write_workbook(NODES_TEMPLATE, NODES_OUTPUT, node_rows)
    write_workbook(LINKS_TEMPLATE, LINKS_OUTPUT, link_rows)
    write_workbook(GROUPS_TEMPLATE, GROUPS_OUTPUT, group_rows)
    write_workbook(MEMBERS_TEMPLATE, MEMBERS_OUTPUT, member_rows)
    copy_optional_templates()

    print(f"source={SUMMARY_MD}")
    print(f"output={OUTPUT_DIR}")
    print(f"nodes={len(node_rows) - 1}")
    print(f"links={len(link_rows) - 1}")
    print(f"groups={len(group_rows) - 1}")
    print(f"group_members={len(member_rows) - 1}")


if __name__ == "__main__":
    main()
