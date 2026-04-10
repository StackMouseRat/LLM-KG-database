from __future__ import annotations

import html
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


BASE_DIR = Path("D:/Graduate_test/dataset")
TXT_DIR = BASE_DIR / "txt" / "互感器"

TEMPLATE_DIR = (
    BASE_DIR
    / "xls"
    / "成品"
    / "高压断路器"
    / "高压断路器_第一至第七层级图谱数据"
)

WORK_OUTPUT_DIR = BASE_DIR / "xls" / "互感器" / "互感器_第一至第八层级图谱数据"
FINAL_OUTPUT_DIR = BASE_DIR / "xls" / "成品" / "互感器" / "互感器_第一至第八层级图谱数据"

ROOT_NAME = "互感器"
ROOT_DESC = "依据第一至第八层级梳理形成的互感器故障图谱实体。"
IMAGE_URL = "https://nrdstudio.cn/res/n.jpg"
ROOT_COLOR = "#9A3412"

DETAIL_LAYERS = ["故障原因", "故障现象", "应对措施", "故障后果", "安全风险", "应急资源"]
LAYER_TO_FILE_KEY = {
    "故障原因": "第三层级_故障原因",
    "故障现象": "第四层级_故障现象",
    "应对措施": "第五层级_应对措施",
    "故障后果": "第六层级_故障后果",
    "安全风险": "第七层级_安全风险",
    "应急资源": "第八层级_应急资源",
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
    "表现为": LAYER_COLORS["故障现象"],
    "处置": LAYER_COLORS["应对措施"],
    "导致": LAYER_COLORS["故障后果"],
    "存在": LAYER_COLORS["安全风险"],
    "需要": LAYER_COLORS["应急资源"],
}

MAJOR_COLORS = {
    "电压互感器故障": "#D97706",
    "电流互感器故障": "#0EA5E9",
}

MAJOR_DESCRIPTIONS = {
    "电压互感器故障": "收录电磁式、串级式、电容式电压互感器及其熔断器相关故障。",
    "电流互感器故障": "收录常规电流互感器和电容型电流互感器的二次回路、受潮、爆炸等故障。",
}

NODES_FILE = "节点_nodes.xlsx"
LINKS_FILE = "关系_links.xlsx"
GROUPS_FILE = "圈子_groups.xlsx"
GROUP_MEMBERS_FILE = "圈子成员_group_members.xlsx"
BLOCKS_FILE = "区块_blocks.xlsx"
TAGS_FILE = "标签_tags.xlsx"
TAG_MEMBERS_FILE = "标签成员_tag_members.xlsx"


def section_between(md_text: str, start_title: str, end_title: str | None) -> str:
    start = md_text.index(start_title)
    end = len(md_text) if end_title is None else md_text.index(end_title, start)
    return md_text[start:end]


def parse_majors_and_subtypes() -> tuple[list[str], dict[str, list[str]]]:
    second_level_file = next(p for p in TXT_DIR.glob("*.md") if "第二层级" in p.name)
    text = second_level_file.read_text(encoding="utf-8")
    section = section_between(text, "## 3. 第二层级推荐结果", "## 4. 推荐层级结构")

    subtype_map: dict[str, list[str]] = defaultdict(list)
    current_major = ""
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("### 3."):
            current_major = re.sub(r"^###\s+3\.\d+\s+", "", stripped).strip()
            continue
        if re.match(r"^\d+\.\s+", stripped) and current_major:
            _, name = stripped.split(".", 1)
            subtype_map[current_major].append(name.strip())

    majors = list(subtype_map.keys())
    return majors, subtype_map


def parse_layer_details() -> dict[str, dict[str, str]]:
    files = {p.name: p for p in TXT_DIR.glob("*.md")}
    layer_details: dict[str, dict[str, str]] = {}

    for layer, key in LAYER_TO_FILE_KEY.items():
        path = next(v for k, v in files.items() if key in k)
        text = path.read_text(encoding="utf-8")
        details: dict[str, str] = {}
        current_subtype = ""

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#### "):
                current_subtype = stripped[5:].strip()
                continue
            if current_subtype and stripped.startswith("- 描述/说明："):
                details[current_subtype] = stripped.split("：", 1)[1].strip()

        layer_details[layer] = details

    return layer_details


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
            links.append((cause, phenomenon, "表现为"))
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
    if name in MAJOR_COLORS:
        return {
            "fontFamily": "heiti",
            "fontSize": "22",
            "lineWidth": "4",
            "r": "72",
            "stroke": MAJOR_COLORS[name],
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
    major = major_for_node or "电压互感器故障"
    return {
        "fontFamily": "heiti",
        "fontSize": "18",
        "lineWidth": "3",
        "r": "58",
        "stroke": MAJOR_COLORS[major],
        "textBorderWidth": "0",
        "weight": "8",
    }


def relation_style(relation: str, major: str | None) -> dict[str, str]:
    if relation in {"发生", "包含"}:
        width = "4" if relation == "发生" else "3"
        stroke = MAJOR_COLORS.get(major or "", RELATION_COLORS[relation])
    else:
        width = "2"
        stroke = RELATION_COLORS[relation]
    return {"lineWidth": width, "stroke": stroke, "textBorderWidth": "0"}


def col_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_sheet_path(template_zip: zipfile.ZipFile) -> str:
    wb_xml = template_zip.read("xl/workbook.xml").decode("utf-8", errors="replace")
    rel_id_match = re.search(r'<sheet[^>]*r:id="([^"]+)"', wb_xml)
    if not rel_id_match:
        raise ValueError("未找到 sheet r:id")
    rel_id = rel_id_match.group(1)
    rels_xml = template_zip.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")
    target_match = re.search(
        rf'<Relationship Id="{re.escape(rel_id)}"[^>]*Target="([^"]+)"', rels_xml
    )
    if not target_match:
        raise ValueError("未找到 workbook 对应 sheet Target")
    target = target_match.group(1).lstrip("/")
    return "xl/" + target


def parse_dimension_cols(template_xml: str) -> tuple[str, str]:
    m = re.search(r'<dimension ref="([A-Z]+)\d+:([A-Z]+)\d+"', template_xml)
    if m:
        return m.group(1), m.group(2)
    return "A", "A"


def xml_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def build_shared_strings(rows: list[list[object]]) -> tuple[list[list[int]], str]:
    index_map: dict[str, int] = {}
    unique: list[str] = []
    matrix: list[list[int]] = []
    total_count = 0

    for row in rows:
        row_idx: list[int] = []
        for value in row:
            text = "" if value is None else str(value)
            if text not in index_map:
                index_map[text] = len(unique)
                unique.append(text)
            row_idx.append(index_map[text])
            total_count += 1
        matrix.append(row_idx)

    si_parts = [f'<si><t xml:space="preserve">{xml_escape(text)}</t></si>' for text in unique]
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{total_count}" uniqueCount="{len(unique)}">'
        + "".join(si_parts)
        + "</sst>"
    )
    return matrix, shared_xml


def build_sheet_data_xml(
    rows: list[list[object]],
    mode: str,
    keep_end_col: str,
    template_xml: str,
) -> tuple[str, str | None]:
    if not rows:
        raise ValueError("rows 不能为空")

    row_extra = ' x14ac:dyDescent="0.2"' if "x14ac:dyDescent" in template_xml else ""
    row_count = len(rows)
    col_count = len(rows[0])
    sheet_rows: list[str] = []

    shared_matrix: list[list[int]] | None = None
    shared_xml: str | None = None
    if mode == "shared":
        shared_matrix, shared_xml = build_shared_strings(rows)

    for r_i, row in enumerate(rows, start=1):
        cells: list[str] = []
        for c_i, value in enumerate(row, start=1):
            ref = f"{col_name(c_i)}{r_i}"
            style_attr = ' s="1"' if r_i == 1 else ""
            if mode == "shared":
                v = shared_matrix[r_i - 1][c_i - 1]  # type: ignore[index]
                cell_xml = f'<c r="{ref}"{style_attr} t="s"><v>{v}</v></c>'
            else:
                text = xml_escape(value)
                cell_xml = (
                    f'<c r="{ref}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}'
                    "</t></is></c>"
                )
            cells.append(cell_xml)
        row_xml = f'<row r="{r_i}" spans="1:{col_count}"{row_extra}>{"".join(cells)}</row>'
        sheet_rows.append(row_xml)

    sheet_data_xml = f"<sheetData>{''.join(sheet_rows)}</sheetData>"
    dimension_xml = f'<dimension ref="A1:{keep_end_col}{row_count}"/>'
    return dimension_xml + "\n" + sheet_data_xml, shared_xml


def replace_sheet_parts(template_xml: str, dimension_and_data_xml: str) -> str:
    dim_part, data_part = dimension_and_data_xml.split("\n", 1)
    updated = re.sub(r"<dimension ref=\"[^\"]*\"/>", dim_part, template_xml, count=1)
    updated = re.sub(r"<sheetData>.*?</sheetData>", data_part, updated, count=1, flags=re.S)
    updated = re.sub(
        r'<selection [^>]*activeCell="[^"]+"[^>]*sqref="[^"]+"[^>]*/>',
        '<selection activeCell="A1" sqref="A1"/>',
        updated,
        count=1,
    )
    return updated


def write_workbook_from_template(
    template_path: Path,
    output_path: Path,
    rows: list[list[object]],
    mode: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path) as zin:
        sheet_path = get_sheet_path(zin)
        template_sheet_xml = zin.read(sheet_path).decode("utf-8", errors="replace")
        _, end_col = parse_dimension_cols(template_sheet_xml)
        dimension_and_data_xml, shared_xml = build_sheet_data_xml(
            rows=rows,
            mode=mode,
            keep_end_col=end_col,
            template_xml=template_sheet_xml,
        )
        new_sheet_xml = replace_sheet_parts(template_sheet_xml, dimension_and_data_xml).encode("utf-8")

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == sheet_path:
                    data = new_sheet_xml
                elif mode == "shared" and info.filename == "xl/sharedStrings.xml" and shared_xml is not None:
                    data = shared_xml.encode("utf-8")
                zout.writestr(info, data)


def build_rows() -> tuple[list[list[object]], list[list[object]], list[list[object]], list[list[object]]]:
    majors, subtype_map = parse_majors_and_subtypes()
    layer_details = parse_layer_details()

    ordered_subtypes = [s for m in majors for s in subtype_map[m]]
    for layer in DETAIL_LAYERS:
        missing = [s for s in ordered_subtypes if s not in layer_details[layer]]
        if missing:
            raise ValueError(f"{layer} 缺少描述：{missing}")

    links = build_links(majors, subtype_map)
    degree = Counter()
    for source, target, _ in links:
        degree[source] += 1
        degree[target] += 1

    major_for_node: dict[str, str] = {}
    for major in majors:
        major_for_node[major] = major
        for subtype in subtype_map[major]:
            major_for_node[subtype] = major
            for layer in DETAIL_LAYERS:
                major_for_node[f"{subtype}-{layer}"] = major

    node_rows: list[list[object]] = [[
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
    node_id: dict[str, str] = {}
    index = 0

    ordered_names: list[str] = [ROOT_NAME]
    ordered_names.extend(majors)
    for major in majors:
        for subtype in subtype_map[major]:
            ordered_names.append(subtype)
            for layer in DETAIL_LAYERS:
                ordered_names.append(f"{subtype}-{layer}")

    for name in ordered_names:
        node_id[name] = str(index)
        index += 1
        if name == ROOT_NAME:
            desc = ROOT_DESC
        elif name in MAJOR_DESCRIPTIONS:
            desc = MAJOR_DESCRIPTIONS[name]
        elif any(name.endswith(f"-{layer}") for layer in DETAIL_LAYERS):
            subtype, layer = name.rsplit("-", 1)
            desc = layer_details[layer][subtype]
        else:
            desc = layer_details["故障原因"][name]

        style = node_style(name, major_for_node.get(name))
        node_rows.append([
            node_id[name],
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

    link_rows: list[list[object]] = [[
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
    for i, (source, target, relation) in enumerate(links):
        if source == ROOT_NAME:
            major = target
        elif source in MAJOR_COLORS:
            major = source
        else:
            major = major_for_node.get(source)
        style = relation_style(relation, major)
        link_rows.append([
            str(i),
            node_id[source],
            source,
            style["lineWidth"],
            relation,
            style["stroke"],
            style["textBorderWidth"],
            node_id[target],
            target,
        ])

    group_rows: list[list[object]] = [[
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
    group_members_rows: list[list[object]] = [["id", "name", "member_id", "member_name"]]

    for g_idx, major in enumerate(majors):
        members = [major]
        for subtype in subtype_map[major]:
            members.append(subtype)
            for layer in DETAIL_LAYERS:
                members.append(f"{subtype}-{layer}")

        group_rows.append([
            str(g_idx),
            major,
            f"{major}的第一至第八层级图谱分组。",
            str(len(members)),
            str(g_idx),
            "0",
            "1",
            MAJOR_COLORS[major],
            MAJOR_COLORS[major],
            MAJOR_COLORS[major],
        ])

        for member in members:
            group_members_rows.append([str(g_idx), major, node_id[member], member])

    return node_rows, link_rows, group_rows, group_members_rows


def validate_rows(
    node_rows: list[list[object]],
    link_rows: list[list[object]],
    group_rows: list[list[object]],
    group_members_rows: list[list[object]],
) -> None:
    node_ids = {row[0] for row in node_rows[1:]}
    if len(node_ids) != len(node_rows) - 1:
        raise ValueError("节点 id 存在重复")

    for row in link_rows[1:]:
        if row[1] not in node_ids or row[7] not in node_ids:
            raise ValueError(f"关系引用不存在节点: {row}")

    group_ids = {row[0] for row in group_rows[1:]}
    if len(group_ids) != len(group_rows) - 1:
        raise ValueError("圈子 id 存在重复")

    for row in group_members_rows[1:]:
        if row[0] not in group_ids:
            raise ValueError(f"圈子成员 group id 不存在: {row}")
        if row[2] not in node_ids:
            raise ValueError(f"圈子成员 member_id 不存在: {row}")


def copy_static_files(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in [BLOCKS_FILE, TAGS_FILE, TAG_MEMBERS_FILE]:
        shutil.copy2(TEMPLATE_DIR / name, output_dir / name)


def generate_once(output_dir: Path) -> None:
    node_rows, link_rows, group_rows, member_rows = build_rows()
    validate_rows(node_rows, link_rows, group_rows, member_rows)

    write_workbook_from_template(TEMPLATE_DIR / NODES_FILE, output_dir / NODES_FILE, node_rows, mode="shared")
    write_workbook_from_template(TEMPLATE_DIR / LINKS_FILE, output_dir / LINKS_FILE, link_rows, mode="shared")
    write_workbook_from_template(TEMPLATE_DIR / GROUPS_FILE, output_dir / GROUPS_FILE, group_rows, mode="inline")
    write_workbook_from_template(
        TEMPLATE_DIR / GROUP_MEMBERS_FILE,
        output_dir / GROUP_MEMBERS_FILE,
        member_rows,
        mode="inline",
    )
    copy_static_files(output_dir)

    print(f"生成完成: {output_dir}")
    print(f"nodes={len(node_rows)-1} links={len(link_rows)-1} groups={len(group_rows)-1} members={len(member_rows)-1}")


def main() -> None:
    generate_once(WORK_OUTPUT_DIR)
    generate_once(FINAL_OUTPUT_DIR)


if __name__ == "__main__":
    main()

