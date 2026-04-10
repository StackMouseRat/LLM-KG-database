from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from build_transmission_circles import (
    build_full_group_members,
    build_group_members,
    find_group_roots,
    read_rows,
    rows_to_dicts,
)
from build_transmission_xlsx import write_workbook


BASE_DIR = Path("xls")
DEVICE_DIR = BASE_DIR / "输电线路"

SOURCE_NODES = DEVICE_DIR / "输电线路_节点_nodes.xlsx"
SOURCE_LINKS = DEVICE_DIR / "输电线路_关系_links.xlsx"

STYLE_TEMPLATE_DIR = BASE_DIR / "样式测试"
COLOR_TEMPLATE_DIR = BASE_DIR / "改色测试"
OUTPUT_DIR = DEVICE_DIR / "输电线路_样式完整版"

NODES_TEMPLATE = STYLE_TEMPLATE_DIR / "节点_nodes.xlsx"
LINKS_TEMPLATE = STYLE_TEMPLATE_DIR / "关系_links.xlsx"
GROUPS_TEMPLATE = COLOR_TEMPLATE_DIR / "圈子_groups.xlsx"
MEMBERS_TEMPLATE = STYLE_TEMPLATE_DIR / "圈子成员_group_members.xlsx"
BLOCKS_TEMPLATE = COLOR_TEMPLATE_DIR / "区块_blocks.xlsx"
TAGS_TEMPLATE = COLOR_TEMPLATE_DIR / "标签_tags.xlsx"
TAG_MEMBERS_TEMPLATE = COLOR_TEMPLATE_DIR / "标签成员_tag_members.xlsx"

NODES_OUTPUT = OUTPUT_DIR / "节点_nodes.xlsx"
LINKS_OUTPUT = OUTPUT_DIR / "关系_links.xlsx"
GROUPS_OUTPUT = OUTPUT_DIR / "圈子_groups.xlsx"
MEMBERS_OUTPUT = OUTPUT_DIR / "圈子成员_group_members.xlsx"
BLOCKS_OUTPUT = OUTPUT_DIR / "区块_blocks.xlsx"
TAGS_OUTPUT = OUTPUT_DIR / "标签_tags.xlsx"
TAG_MEMBERS_OUTPUT = OUTPUT_DIR / "标签成员_tag_members.xlsx"

ROOT_NAME = "输电线路"

ROOT_COLOR = "#1F3A5F"
MEASURE_COLOR = "#52C41A"
SHARED_COLOR = "#8C8C8C"
FALLBACK_COLOR = "#BFBFBF"

RELATION_STYLES = {
    "起因于": {"lineWidth": "2", "stroke": "#FA8C16", "textBorderWidth": "0"},
    "表现为": {"lineWidth": "2", "stroke": "#1890FF", "textBorderWidth": "0"},
    "导致": {"lineWidth": "2", "stroke": "#F5222D", "textBorderWidth": "0"},
    "防范": {"lineWidth": "2", "stroke": MEASURE_COLOR, "textBorderWidth": "0"},
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


def build_membership_map(group_members: dict[str, list[str]]) -> dict[str, set[str]]:
    membership = defaultdict(set)
    for group_name, members in group_members.items():
        for member_name in members:
            membership[member_name].add(group_name)
    return membership


def build_measure_set(link_rows: list[dict[str, str]]) -> set[str]:
    return {row["目标节点"] for row in link_rows if row["关系名称"] == "防范"}


def build_subtype_set(link_rows: list[dict[str, str]]) -> set[str]:
    return {row["目标节点"] for row in link_rows if row["关系名称"] == "包含"}


def node_color(name: str, membership_map: dict[str, set[str]], measure_set: set[str]) -> str:
    if name == ROOT_NAME:
        return ROOT_COLOR
    if name in measure_set:
        return MEASURE_COLOR
    if name in membership_map:
        groups = membership_map[name]
        if len(groups) == 1:
            return GROUP_COLORS[next(iter(groups))]
        return SHARED_COLOR
    return FALLBACK_COLOR


def node_style(
    name: str,
    roots: list[str],
    subtype_set: set[str],
    membership_map: dict[str, set[str]],
    measure_set: set[str],
) -> dict[str, str]:
    if name == ROOT_NAME:
        return {
            "fontFamily": "heiti",
            "fontSize": "30",
            "lineWidth": "5",
            "r": "100",
            "stroke": ROOT_COLOR,
            "textBorderWidth": "0",
        }
    if name in roots:
        return {
            "fontFamily": "heiti",
            "fontSize": "22",
            "lineWidth": "4",
            "r": "72",
            "stroke": GROUP_COLORS[name],
            "textBorderWidth": "0",
        }
    if name in subtype_set:
        return {
            "fontFamily": "heiti",
            "fontSize": "18",
            "lineWidth": "3",
            "r": "58",
            "stroke": node_color(name, membership_map, measure_set),
            "textBorderWidth": "0",
        }
    return {
        "fontFamily": "heiti",
        "fontSize": "16",
        "lineWidth": "2",
        "r": "46",
        "stroke": node_color(name, membership_map, measure_set),
        "textBorderWidth": "0",
    }


def group_color_for_node(name: str, membership_map: dict[str, set[str]]) -> str:
    if name in GROUP_COLORS:
        return GROUP_COLORS[name]
    if name in membership_map and len(membership_map[name]) == 1:
        return GROUP_COLORS[next(iter(membership_map[name]))]
    return SHARED_COLOR


def relation_style(
    relation: str,
    source_name: str,
    target_name: str,
    membership_map: dict[str, set[str]],
) -> dict[str, str]:
    if relation == "发生":
        return {
            "lineWidth": "4",
            "stroke": GROUP_COLORS.get(target_name, ROOT_COLOR),
            "textBorderWidth": "0",
        }
    if relation == "包含":
        return {
            "lineWidth": "3",
            "stroke": group_color_for_node(source_name, membership_map)
            if source_name != ROOT_NAME
            else group_color_for_node(target_name, membership_map),
            "textBorderWidth": "0",
        }
    return RELATION_STYLES.get(
        relation,
        {"lineWidth": "2", "stroke": FALLBACK_COLOR, "textBorderWidth": "0"},
    )


def build_styled_nodes(
    node_rows: list[dict[str, str]],
    roots: list[str],
    subtype_set: set[str],
    membership_map: dict[str, set[str]],
    measure_set: set[str],
) -> tuple[list[list[str]], dict[str, int]]:
    node_id_map = {row["节点名称"]: index for index, row in enumerate(node_rows)}

    rows = [[
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

    for index, row in enumerate(node_rows):
        style = node_style(
            row["节点名称"],
            roots,
            subtype_set,
            membership_map,
            measure_set,
        )
        rows.append([
            str(index),
            row["节点名称"],
            row["度"],
            row["描述"],
            style["fontFamily"],
            style["fontSize"],
            row["图像"],
            style["lineWidth"],
            style["r"],
            style["stroke"],
            style["textBorderWidth"],
            row["权重"],
        ])

    return rows, node_id_map


def build_styled_links(
    link_rows: list[dict[str, str]],
    node_id_map: dict[str, int],
    membership_map: dict[str, set[str]],
) -> list[list[str]]:
    rows = [[
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

    for index, row in enumerate(link_rows):
        style = relation_style(
            row["关系名称"],
            row["源节点"],
            row["目标节点"],
            membership_map,
        )
        rows.append([
            str(index),
            str(node_id_map[row["源节点"]]),
            row["源节点"],
            style["lineWidth"],
            row["关系名称"],
            style["stroke"],
            style["textBorderWidth"],
            str(node_id_map[row["目标节点"]]),
            row["目标节点"],
        ])

    return rows


def build_colored_groups(
    roots: list[str],
    group_members: dict[str, list[str]],
) -> list[list[str]]:
    rows = [[
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

    for index, name in enumerate(roots):
        color = GROUP_COLORS[name]
        rows.append([
            str(index),
            name,
            f"{name}的有关信息",
            str(len(group_members[name])),
            str(index),
            "0",
            "1",
            color,
            color,
            color,
        ])

    return rows


def copy_optional_templates() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BLOCKS_TEMPLATE, BLOCKS_OUTPUT)
    shutil.copy2(TAGS_TEMPLATE, TAGS_OUTPUT)
    shutil.copy2(TAG_MEMBERS_TEMPLATE, TAG_MEMBERS_OUTPUT)


def main() -> None:
    node_rows = rows_to_dicts(read_rows(SOURCE_NODES))
    link_rows = rows_to_dicts(read_rows(SOURCE_LINKS))

    roots = find_group_roots(link_rows)
    group_members = build_group_members(roots, link_rows)
    membership_map = build_membership_map(group_members)
    measure_set = build_measure_set(link_rows)
    subtype_set = build_subtype_set(link_rows)

    styled_nodes_rows, node_id_map = build_styled_nodes(
        node_rows,
        roots,
        subtype_set,
        membership_map,
        measure_set,
    )
    styled_links_rows = build_styled_links(link_rows, node_id_map, membership_map)
    groups_rows = build_colored_groups(roots, group_members)
    members_rows = build_full_group_members(roots, group_members, node_id_map)

    write_workbook(NODES_TEMPLATE, NODES_OUTPUT, styled_nodes_rows)
    write_workbook(LINKS_TEMPLATE, LINKS_OUTPUT, styled_links_rows)
    write_workbook(GROUPS_TEMPLATE, GROUPS_OUTPUT, groups_rows)
    write_workbook(MEMBERS_TEMPLATE, MEMBERS_OUTPUT, members_rows)
    copy_optional_templates()

    shared_nodes = sum(1 for groups in membership_map.values() if len(groups) > 1)
    print(f"output={OUTPUT_DIR}")
    print(f"groups={len(roots)}")
    print(f"subtypes={len(subtype_set)}")
    print(f"measures={len(measure_set)}")
    print(f"shared_nodes={shared_nodes}")


if __name__ == "__main__":
    main()
