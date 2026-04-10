from __future__ import annotations

import html
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from build_transmission_xlsx import write_workbook


BASE_DIR = Path("xls")
DEVICE_DIR = BASE_DIR / "输电线路"
SOURCE_NODES = DEVICE_DIR / "输电线路_节点_nodes.xlsx"
SOURCE_LINKS = DEVICE_DIR / "输电线路_关系_links.xlsx"

FULL_TEMPLATE_DIR = BASE_DIR / "圈子测试"
FULL_OUTPUT_DIR = DEVICE_DIR / "输电线路_圈子版"

FULL_NODES_TEMPLATE = FULL_TEMPLATE_DIR / "节点_nodes.xlsx"
FULL_LINKS_TEMPLATE = FULL_TEMPLATE_DIR / "关系_links.xlsx"
FULL_GROUPS_TEMPLATE = FULL_TEMPLATE_DIR / "圈子_groups.xlsx"
FULL_MEMBERS_TEMPLATE = FULL_TEMPLATE_DIR / "圈子成员_group_members.xlsx"

FULL_NODES_OUTPUT = FULL_OUTPUT_DIR / "节点_nodes.xlsx"
FULL_LINKS_OUTPUT = FULL_OUTPUT_DIR / "关系_links.xlsx"
FULL_GROUPS_OUTPUT = FULL_OUTPUT_DIR / "圈子_groups.xlsx"
FULL_MEMBERS_OUTPUT = FULL_OUTPUT_DIR / "圈子成员_group_members.xlsx"

SIMPLE_TEMPLATE_DIR = BASE_DIR / "NRD Studio Excel模板文件"
SIMPLE_GROUPS_TEMPLATE = SIMPLE_TEMPLATE_DIR / "圈子_groups.xlsx"
SIMPLE_MEMBERS_TEMPLATE = SIMPLE_TEMPLATE_DIR / "圈子成员_group_members.xlsx"
SIMPLE_GROUPS_OUTPUT = DEVICE_DIR / "输电线路_圈子_groups.xlsx"
SIMPLE_MEMBERS_OUTPUT = DEVICE_DIR / "输电线路_圈子成员_group_members.xlsx"

EXCLUDED_RELATIONS = {"防范"}


def get_sheet_path(path: Path) -> str:
    with zipfile.ZipFile(path) as zin:
        workbook_xml = zin.read("xl/workbook.xml").decode("utf-8", errors="replace")
        rel_id = re.search(r'<sheet[^>]*r:id="([^"]+)"', workbook_xml)
        rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")
        target = re.search(
            rf'<Relationship Id="{re.escape(rel_id.group(1))}"[^>]*Target="([^"]+)"',
            rels_xml,
        )
        return "xl/" + target.group(1).lstrip("/")


def read_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zin:
        shared = []
        if "xl/sharedStrings.xml" in zin.namelist():
            shared_xml = zin.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            for si in re.findall(r"<si\b.*?</si>", shared_xml, flags=re.S):
                texts = re.findall(r"<t[^>]*>(.*?)</t>", si, flags=re.S)
                shared.append(html.unescape("".join(texts)))

        sheet_xml = zin.read(get_sheet_path(path)).decode("utf-8", errors="replace")
        rows = []
        for row_xml in re.findall(r"<row\b.*?</row>", sheet_xml, flags=re.S):
            values = {}
            for attrs, inner in re.findall(r"<c\b([^>]*)>(.*?)</c>", row_xml, flags=re.S):
                ref = re.search(r'r="([A-Z]+)(\d+)"', attrs)
                if not ref:
                    continue
                col = col_to_number(ref.group(1))
                cell_type_match = re.search(r't="([^"]+)"', attrs)
                cell_type = cell_type_match.group(1) if cell_type_match else ""

                if cell_type == "inlineStr":
                    text_match = re.search(r"<t[^>]*>(.*?)</t>", inner, flags=re.S)
                    value = html.unescape(text_match.group(1)) if text_match else ""
                else:
                    value_match = re.search(r"<v>(.*?)</v>", inner, flags=re.S)
                    if not value_match:
                        value = ""
                    elif cell_type == "s":
                        value_index = int(value_match.group(1))
                        value = shared[value_index] if value_index < len(shared) else ""
                    else:
                        value = html.unescape(value_match.group(1))

                values[col] = value

            max_col = max(values) if values else 0
            rows.append([values.get(col, "") for col in range(1, max_col + 1)])
        return rows


def col_to_number(col: str) -> int:
    number = 0
    for char in col:
        number = number * 26 + ord(char) - 64
    return number


def rows_to_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    header = rows[0]
    mapped = []
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        mapped.append(dict(zip(header, padded)))
    return mapped


def find_group_roots(link_rows: list[dict[str, str]]) -> list[str]:
    roots = []
    for row in link_rows:
        if row["源节点"] == "输电线路" and row["关系名称"] == "发生":
            roots.append(row["目标节点"])
    return roots


def build_group_members(
    roots: list[str],
    link_rows: list[dict[str, str]],
) -> dict[str, list[str]]:
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in link_rows:
        adjacency[row["源节点"]].append((row["关系名称"], row["目标节点"]))

    groups = {}
    for root in roots:
        seen = {root}
        ordered = [root]
        queue = [root]
        while queue:
            current = queue.pop(0)
            for relation, target in adjacency.get(current, []):
                if relation in EXCLUDED_RELATIONS:
                    continue
                if target in seen:
                    continue
                seen.add(target)
                ordered.append(target)
                queue.append(target)
        groups[root] = ordered
    return groups


def build_full_nodes(
    node_rows: list[dict[str, str]],
    roots: list[str],
) -> tuple[list[list[str]], dict[str, int]]:
    root_to_group_id = {name: index for index, name in enumerate(roots)}
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
        "group.show",
    ]]

    for index, row in enumerate(node_rows):
        name = row["节点名称"]
        if name == "输电线路":
            radius = "100"
            stroke = "#4a90e2"
            group_show = ""
        elif name in root_to_group_id:
            radius = "72"
            stroke = ""
            group_show = str(root_to_group_id[name])
        else:
            radius = "46"
            stroke = ""
            group_show = ""

        rows.append([
            str(index),
            name,
            row["度"],
            row["描述"],
            row["图像"],
            radius,
            stroke,
            row["权重"],
            group_show,
        ])

    return rows, node_id_map


def build_full_links(
    link_rows: list[dict[str, str]],
    node_id_map: dict[str, int],
) -> list[list[str]]:
    rows = [[
        "id",
        "from",
        "fromNodeName",
        "relation",
        "to",
        "toNodeName",
    ]]

    for index, row in enumerate(link_rows):
        rows.append([
            str(index),
            str(node_id_map[row["源节点"]]),
            row["源节点"],
            row["关系名称"],
            str(node_id_map[row["目标节点"]]),
            row["目标节点"],
        ])

    return rows


def build_full_groups(
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
    ]]

    for index, name in enumerate(roots):
        rows.append([
            str(index),
            name,
            f"{name}的有关信息",
            str(len(group_members[name])),
            str(index),
            "0",
            "1",
        ])

    return rows


def build_full_group_members(
    roots: list[str],
    group_members: dict[str, list[str]],
    node_id_map: dict[str, int],
) -> list[list[str]]:
    rows = [[
        "id",
        "name",
        "member_id",
        "member_name",
    ]]

    for index, name in enumerate(roots):
        for member_name in group_members[name]:
            rows.append([
                str(index),
                name,
                str(node_id_map[member_name]),
                member_name,
            ])

    return rows


def build_simple_groups(
    roots: list[str],
    group_members: dict[str, list[str]],
) -> tuple[list[list[str]], list[list[str]]]:
    group_rows = [["圈子名称", "描述"]]
    member_rows = [["圈子名称", "成员名称"]]

    for name in roots:
        group_rows.append([name, f"{name}的有关信息"])
        for member_name in group_members[name]:
            member_rows.append([name, member_name])

    return group_rows, member_rows


def main() -> None:
    node_rows = rows_to_dicts(read_rows(SOURCE_NODES))
    link_rows = rows_to_dicts(read_rows(SOURCE_LINKS))

    roots = find_group_roots(link_rows)
    group_members = build_group_members(roots, link_rows)

    full_nodes_rows, node_id_map = build_full_nodes(node_rows, roots)
    full_links_rows = build_full_links(link_rows, node_id_map)
    full_groups_rows = build_full_groups(roots, group_members)
    full_group_members_rows = build_full_group_members(roots, group_members, node_id_map)

    simple_groups_rows, simple_group_members_rows = build_simple_groups(roots, group_members)

    write_workbook(FULL_NODES_TEMPLATE, FULL_NODES_OUTPUT, full_nodes_rows)
    write_workbook(FULL_LINKS_TEMPLATE, FULL_LINKS_OUTPUT, full_links_rows)
    write_workbook(FULL_GROUPS_TEMPLATE, FULL_GROUPS_OUTPUT, full_groups_rows)
    write_workbook(FULL_MEMBERS_TEMPLATE, FULL_MEMBERS_OUTPUT, full_group_members_rows)

    write_workbook(SIMPLE_GROUPS_TEMPLATE, SIMPLE_GROUPS_OUTPUT, simple_groups_rows)
    write_workbook(SIMPLE_MEMBERS_TEMPLATE, SIMPLE_MEMBERS_OUTPUT, simple_group_members_rows)

    print(f"groups={len(roots)}")
    print(f"full_nodes={FULL_NODES_OUTPUT}")
    print(f"full_links={FULL_LINKS_OUTPUT}")
    print(f"full_groups={FULL_GROUPS_OUTPUT}")
    print(f"full_group_members={FULL_MEMBERS_OUTPUT}")
    print(f"simple_groups={SIMPLE_GROUPS_OUTPUT}")
    print(f"simple_group_members={SIMPLE_MEMBERS_OUTPUT}")


if __name__ == "__main__":
    main()
