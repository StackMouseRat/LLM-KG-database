from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from build_transmission_xlsx import write_workbook


BASE_DIR = Path("xls")
DEVICE_DIR = BASE_DIR / "输电线路"
TEXT_DIR = Path("txt") / "输电线路"

MD_PATH = TEXT_DIR / "输电线路故障层级梳理_最新版.md"
if not MD_PATH.exists():
    MD_PATH = TEXT_DIR / "输电线路故障层级梳理_第一至第七层级汇总稿.md"
if not MD_PATH.exists():
    MD_PATH = max(
        (p for p in TEXT_DIR.glob("*.md") if "工作流程" not in p.name),
        key=lambda p: p.stat().st_mtime,
    )
TEMPLATE_DIR = DEVICE_DIR / "输电线路_样式完整版"
OUTPUT_DIR = DEVICE_DIR / "输电线路_改进图谱数据"

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
ROOT_DESC = "依据最新版层级梳理形成的输电线路故障图谱实体。"
ROOT_COLOR = "#1F3A5F"
CAUSE_COLOR = "#FA8C16"
PHENOMENON_COLOR = "#1890FF"

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


def parse_sections(md_text: str) -> tuple[list[str], dict[str, list[str]], dict[str, str], dict[str, str]]:
    majors, subtype_map = parse_hierarchy(md_text)
    cause_map = parse_detail_section(
        md_text,
        "## 第二层级：故障原因（单节点设计）",
        "## 第三层级：故障现象（单节点设计）",
    )
    phenomenon_map = parse_detail_section(
        md_text,
        "## 第三层级：故障现象（单节点设计）",
        "## 下一步建议",
    )
    return majors, subtype_map, cause_map, phenomenon_map


def parse_hierarchy(md_text: str) -> tuple[list[str], dict[str, list[str]]]:
    hierarchy_match = re.search(
        r"## 定稿后的推荐层级结构\s+```text(.*?)```",
        md_text,
        flags=re.S,
    )
    if not hierarchy_match:
        raise ValueError("未找到定稿后的推荐层级结构")

    majors: list[str] = []
    subtype_map: dict[str, list[str]] = defaultdict(list)
    current_major = ""

    for raw_line in hierarchy_match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("├─ ") or line.startswith("└─ "):
            current_major = line[2:].strip("─ ").strip()
            majors.append(current_major)
            continue
        if line.startswith("│  ├─ ") or line.startswith("│  └─ ") or line.startswith("   ├─ ") or line.startswith("   └─ "):
            subtype = line.split("─", 1)[1].strip()
            subtype_map[current_major].append(subtype)

    return majors, subtype_map


def parse_detail_section(md_text: str, start_title: str, end_title: str) -> dict[str, str]:
    start = md_text.index(start_title)
    end = md_text.index(end_title, start)
    section = md_text[start:end]
    lines = section.splitlines()

    details: dict[str, str] = {}
    current_subtype = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#### ") and "示例" not in line:
            current_subtype = line[5:].strip()
        if line.startswith("- 描述/说明：") and current_subtype:
            description = line.split("：", 1)[1].strip()
            i += 1
            while i < len(lines):
                next_line = lines[i]
                stripped = next_line.strip()
                if not stripped:
                    i += 1
                    continue
                if stripped.startswith("#### ") or stripped.startswith("### ") or stripped.startswith("## "):
                    i -= 1
                    break
                if stripped.startswith("- 第二层级节点") or stripped.startswith("- 第三层级节点") or stripped.startswith("- 唯一节点名建议") or stripped.startswith("补充说明："):
                    i -= 1
                    break
                if description:
                    description += " "
                description += stripped
                i += 1
            details[current_subtype] = description
        i += 1

    return details


def build_node_order(majors: list[str], subtype_map: dict[str, list[str]]) -> list[str]:
    ordered = [ROOT_NAME]
    for major in majors:
        ordered.append(major)
    for major in majors:
        for subtype in subtype_map[major]:
            ordered.append(subtype)
            ordered.append(f"{subtype}-故障原因")
            ordered.append(f"{subtype}-故障现象")
    return ordered


def build_links(
    majors: list[str],
    subtype_map: dict[str, list[str]],
) -> list[tuple[str, str, str]]:
    links: list[tuple[str, str, str]] = []
    for major in majors:
        links.append((ROOT_NAME, major, "发生"))
    for major in majors:
        for subtype in subtype_map[major]:
            links.append((major, subtype, "包含"))
            links.append((subtype, f"{subtype}-故障原因", "起因于"))
            links.append((subtype, f"{subtype}-故障现象", "表现为"))
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
    if name.endswith("-故障原因"):
        return {
            "fontFamily": "heiti",
            "fontSize": "16",
            "lineWidth": "2",
            "r": "46",
            "stroke": CAUSE_COLOR,
            "textBorderWidth": "0",
            "weight": "6",
        }
    if name.endswith("-故障现象"):
        return {
            "fontFamily": "heiti",
            "fontSize": "16",
            "lineWidth": "2",
            "r": "46",
            "stroke": PHENOMENON_COLOR,
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


def relation_style(relation: str, major: str) -> dict[str, str]:
    if relation == "发生":
        return {"lineWidth": "4", "stroke": GROUP_COLORS[major], "textBorderWidth": "0"}
    if relation == "包含":
        return {"lineWidth": "3", "stroke": GROUP_COLORS[major], "textBorderWidth": "0"}
    if relation == "起因于":
        return {"lineWidth": "2", "stroke": CAUSE_COLOR, "textBorderWidth": "0"}
    if relation == "表现为":
        return {"lineWidth": "2", "stroke": PHENOMENON_COLOR, "textBorderWidth": "0"}
    raise ValueError(f"未知关系：{relation}")


def copy_empty_templates() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BLOCKS_TEMPLATE, BLOCKS_OUTPUT)
    shutil.copy2(TAGS_TEMPLATE, TAGS_OUTPUT)
    shutil.copy2(TAG_MEMBERS_TEMPLATE, TAG_MEMBERS_OUTPUT)


def main() -> None:
    md_text = MD_PATH.read_text(encoding="utf-8")
    majors, subtype_map, cause_map, phenomenon_map = parse_sections(md_text)

    ordered_names = build_node_order(majors, subtype_map)
    links = build_links(majors, subtype_map)

    major_for_node: dict[str, str] = {}
    for major in majors:
        major_for_node[major] = major
        for subtype in subtype_map[major]:
            major_for_node[subtype] = major
            major_for_node[f"{subtype}-故障原因"] = major
            major_for_node[f"{subtype}-故障现象"] = major

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
        elif name.endswith("-故障原因"):
            subtype = name[:-5]
            desc = cause_map.get(subtype, "")
        elif name.endswith("-故障现象"):
            subtype = name[:-5]
            desc = phenomenon_map.get(subtype, "")
        else:
            desc = f"{major_for_node[name]}下的二级故障类型：{name}。"

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
        major = target if relation == "发生" else major_for_node[source]
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
            members.extend([subtype, f"{subtype}-故障原因", f"{subtype}-故障现象"])

        color = GROUP_COLORS[major]
        group_rows.append([
            str(group_id),
            major,
            f"{major}的改进图谱分组",
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
    copy_empty_templates()

    print(f"output={OUTPUT_DIR}")
    print(f"nodes={len(node_rows) - 1}")
    print(f"links={len(link_rows) - 1}")
    print(f"groups={len(group_rows) - 1}")
    print(f"group_members={len(member_rows) - 1}")


if __name__ == "__main__":
    main()
