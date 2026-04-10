from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from build_transmission_circles import (
    build_full_group_members,
    build_full_links,
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

COLOR_TEMPLATE_DIR = BASE_DIR / "改色测试"
OUTPUT_DIR = DEVICE_DIR / "输电线路_改色版"

NODES_TEMPLATE = COLOR_TEMPLATE_DIR / "节点_nodes.xlsx"
LINKS_TEMPLATE = COLOR_TEMPLATE_DIR / "关系_links.xlsx"
GROUPS_TEMPLATE = COLOR_TEMPLATE_DIR / "圈子_groups.xlsx"
MEMBERS_TEMPLATE = COLOR_TEMPLATE_DIR / "圈子成员_group_members.xlsx"
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

GROUP_COLORS = {
    "覆冰故障": "#6DC8EC",
    "舞动故障": "#5AD8A6",
    "雷击闪络故障": "#F6BD16",
    "外力破坏故障": "#E8684A",
    "风害故障": "#5B8FF9",
    "鸟害故障": "#9270CA",
    "污闪故障": "#FF9D4D",
}

EQUIPMENT_COLOR = "#D0021B"
MEASURE_COLOR = "#52C41A"
SHARED_COLOR = "#8C8C8C"
FALLBACK_COLOR = "#BFBFBF"


def build_membership_map(group_members: dict[str, list[str]]) -> dict[str, set[str]]:
    membership = defaultdict(set)
    for group_name, members in group_members.items():
        for member_name in members:
            membership[member_name].add(group_name)
    return membership


def build_measure_set(link_rows: list[dict[str, str]]) -> set[str]:
    return {row["目标节点"] for row in link_rows if row["关系名称"] == "防范"}


def node_radius(name: str, roots: list[str]) -> str:
    if name == "输电线路":
        return "100"
    if name in roots:
        return "72"
    return "46"


def node_stroke(
    name: str,
    membership_map: dict[str, set[str]],
    measure_set: set[str],
) -> str:
    if name == "输电线路":
        return EQUIPMENT_COLOR
    if name in membership_map:
        groups = membership_map[name]
        if len(groups) == 1:
            return GROUP_COLORS[next(iter(groups))]
        return SHARED_COLOR
    if name in measure_set:
        return MEASURE_COLOR
    return FALLBACK_COLOR


def build_colored_nodes(
    node_rows: list[dict[str, str]],
    roots: list[str],
    membership_map: dict[str, set[str]],
    measure_set: set[str],
) -> tuple[list[list[str]], dict[str, int]]:
    node_id_map = {row["节点名称"]: index for index, row in enumerate(node_rows)}

    rows = [[
        "id",
        "name",
        "degree",
        "desc",
        "image",
        "r",
        "stroke",
        "weight",
    ]]

    for index, row in enumerate(node_rows):
        name = row["节点名称"]
        rows.append([
            str(index),
            name,
            row["度"],
            row["描述"],
            row["图像"],
            node_radius(name, roots),
            node_stroke(name, membership_map, measure_set),
            row["权重"],
        ])

    return rows, node_id_map


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

    colored_nodes_rows, node_id_map = build_colored_nodes(
        node_rows,
        roots,
        membership_map,
        measure_set,
    )
    colored_links_rows = build_full_links(link_rows, node_id_map)
    colored_groups_rows = build_colored_groups(roots, group_members)
    colored_members_rows = build_full_group_members(roots, group_members, node_id_map)

    write_workbook(NODES_TEMPLATE, NODES_OUTPUT, colored_nodes_rows)
    write_workbook(LINKS_TEMPLATE, LINKS_OUTPUT, colored_links_rows)
    write_workbook(GROUPS_TEMPLATE, GROUPS_OUTPUT, colored_groups_rows)
    write_workbook(MEMBERS_TEMPLATE, MEMBERS_OUTPUT, colored_members_rows)
    copy_optional_templates()

    print(f"output={OUTPUT_DIR}")
    print(f"groups={len(roots)}")
    print(f"shared_nodes={sum(1 for groups in membership_map.values() if len(groups) > 1)}")
    print(f"measure_nodes={len(measure_set)}")


if __name__ == "__main__":
    main()
