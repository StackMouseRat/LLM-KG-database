from __future__ import annotations

import html
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple


BASE_DIR = Path("D:/Graduate_test/dataset")
TXT_DIR = BASE_DIR / "txt"
XLS_DIR = BASE_DIR / "xls"

ROOT_NAME = "电力互感器"
ROOT_DESC = "依据互感器新稿（第一至第八层级）梳理结果形成的故障知识图谱实体。"
IMAGE_URL = "https://nrdstudio.cn/res/n.jpg"

DETAIL_LAYERS = ["故障原因", "故障现象", "应对措施", "故障后果", "安全风险", "应急资源"]
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
MAJOR_PALETTE = ["#D97706", "#0EA5E9", "#7C3AED", "#10B981", "#EF4444", "#14B8A6"]
ROOT_COLOR = "#9A3412"

NODES_FILE = "节点_nodes.xlsx"
LINKS_FILE = "关系_links.xlsx"
GROUPS_FILE = "圈子_groups.xlsx"
GROUP_MEMBERS_FILE = "圈子成员_group_members.xlsx"
BLOCKS_FILE = "区块_blocks.xlsx"
TAGS_FILE = "标签_tags.xlsx"
TAG_MEMBERS_FILE = "标签成员_tag_members.xlsx"


def find_new_hierarchy_md() -> Path:
    key = "互感器故障层级梳理_第一至第八层级汇总稿_新稿"
    for p in TXT_DIR.rglob("*.md"):
        if key in p.name:
            return p
    raise FileNotFoundError(f"未找到新稿层级 md: {key}")


def find_template_dir() -> Path:
    # 优先使用“已验证可导入”的互感器成品壳
    for p in (XLS_DIR / "成品").rglob("互感器_第一至第八层级图谱数据"):
        if p.is_dir() and (p / NODES_FILE).exists() and (p / LINKS_FILE).exists():
            return p
    # 兜底
    for p in XLS_DIR.rglob("high_voltage_breaker_1to8_import4"):
        if p.is_dir():
            return p
    raise FileNotFoundError("未找到可用模板壳目录")


def col_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def xml_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def get_sheet_path(zin: zipfile.ZipFile) -> str:
    wb_xml = zin.read("xl/workbook.xml").decode("utf-8", errors="replace")
    rel_id = re.search(r'<sheet[^>]*r:id="([^"]+)"', wb_xml).group(1)
    rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")
    target = re.search(
        rf'<Relationship Id="{re.escape(rel_id)}"[^>]*Target="([^"]+)"', rels
    ).group(1)
    return "xl/" + target.lstrip("/")


def parse_dimension_end_col(sheet_xml: str) -> str:
    m = re.search(r'<dimension ref="[A-Z]+\d+:([A-Z]+)\d+"', sheet_xml)
    return m.group(1) if m else "A"


def build_shared_strings(rows: List[List[object]]) -> Tuple[List[List[int]], str]:
    index_map: Dict[str, int] = {}
    unique: List[str] = []
    matrix: List[List[int]] = []
    total = 0
    for row in rows:
        idx_row: List[int] = []
        for v in row:
            s = "" if v is None else str(v)
            if s not in index_map:
                index_map[s] = len(unique)
                unique.append(s)
            idx_row.append(index_map[s])
            total += 1
        matrix.append(idx_row)
    sis = "".join(f'<si><t xml:space="preserve">{xml_escape(t)}</t></si>' for t in unique)
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{total}" uniqueCount="{len(unique)}">{sis}</sst>'
    )
    return matrix, shared_xml


def build_sheet_data(rows: List[List[object]], mode: str, template_xml: str) -> Tuple[str, str | None]:
    if not rows:
        raise ValueError("rows 不能为空")
    extra = ' x14ac:dyDescent="0.2"' if "x14ac:dyDescent" in template_xml else ""
    row_xml: List[str] = []
    col_count = len(rows[0])
    shared_matrix: List[List[int]] | None = None
    shared_xml: str | None = None
    if mode == "shared":
        shared_matrix, shared_xml = build_shared_strings(rows)

    for r, row in enumerate(rows, start=1):
        cells: List[str] = []
        for c, val in enumerate(row, start=1):
            ref = f"{col_name(c)}{r}"
            style = ' s="1"' if r == 1 else ""
            if mode == "shared":
                idx = shared_matrix[r - 1][c - 1]  # type: ignore[index]
                cells.append(f'<c r="{ref}"{style} t="s"><v>{idx}</v></c>')
            else:
                t = xml_escape(val)
                cells.append(
                    f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{t}</t></is></c>'
                )
        row_xml.append(f'<row r="{r}" spans="1:{col_count}"{extra}>{"".join(cells)}</row>')
    return "<sheetData>" + "".join(row_xml) + "</sheetData>", shared_xml


def replace_sheet_xml(template_xml: str, sheet_data_xml: str, end_col: str, row_count: int) -> str:
    dim = f'<dimension ref="A1:{end_col}{row_count}"/>'
    out = re.sub(r'<dimension ref="[^"]*"/>', dim, template_xml, count=1)
    out = re.sub(r"<sheetData>.*?</sheetData>", sheet_data_xml, out, count=1, flags=re.S)
    out = re.sub(
        r'<selection [^>]*activeCell="[^"]+"[^>]*sqref="[^"]+"[^>]*/>',
        '<selection activeCell="A1" sqref="A1"/>',
        out,
        count=1,
    )
    return out


def write_workbook(template_path: Path, output_path: Path, rows: List[List[object]], mode: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path) as zin:
        sheet_path = get_sheet_path(zin)
        template_xml = zin.read(sheet_path).decode("utf-8", errors="replace")
        end_col = parse_dimension_end_col(template_xml)
        sheet_data_xml, shared_xml = build_sheet_data(rows, mode, template_xml)
        new_sheet = replace_sheet_xml(template_xml, sheet_data_xml, end_col, len(rows)).encode("utf-8")
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == sheet_path:
                    data = new_sheet
                elif mode == "shared" and info.filename == "xl/sharedStrings.xml" and shared_xml is not None:
                    data = shared_xml.encode("utf-8")
                zout.writestr(info, data)


def parse_new_hierarchy(md_path: Path) -> Tuple[List[str], Dict[str, List[str]], Dict[str, Dict[str, str]]]:
    text = md_path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()]

    major_order: List[str] = []
    subtype_map: Dict[str, List[str]] = {}
    details: Dict[str, Dict[str, str]] = {}

    current_subtype = ""
    for ln in lines:
        if ln.startswith("### "):
            current_subtype = re.sub(r"^###\s+\d+\.\d+\s+", "", ln).strip()
            details[current_subtype] = {}
            continue
        if not current_subtype or not ln.startswith("- "):
            continue

        m_major = re.match(r"^- 一级大类：(.+)$", ln)
        if m_major:
            major = m_major.group(1).strip()
            if major not in major_order:
                major_order.append(major)
                subtype_map[major] = []
            subtype_map[major].append(current_subtype)
            continue

        for layer in DETAIL_LAYERS:
            prefix = f"- {layer}："
            if ln.startswith(prefix):
                details[current_subtype][layer] = ln[len(prefix) :].strip()
                break

    # 校验
    if not major_order:
        raise ValueError("未解析到一级大类")
    for major in major_order:
        if not subtype_map.get(major):
            raise ValueError(f"一级大类缺少二级小类: {major}")
    for subtype, d in details.items():
        missing = [k for k in DETAIL_LAYERS if k not in d]
        if missing:
            raise ValueError(f"{subtype} 缺少层级字段: {missing}")

    return major_order, subtype_map, details


def node_style(name: str, major: str | None, major_colors: Dict[str, str]) -> Dict[str, str]:
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
    if major and name == major:
        return {
            "fontFamily": "heiti",
            "fontSize": "22",
            "lineWidth": "4",
            "r": "72",
            "stroke": major_colors[major],
            "textBorderWidth": "0",
            "weight": "9",
        }
    if any(name.endswith(f"-{layer}") for layer in DETAIL_LAYERS):
        layer = name.rsplit("-", 1)[1]
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
        "stroke": major_colors.get(major or "", "#6B7280"),
        "textBorderWidth": "0",
        "weight": "8",
    }


def relation_style(relation: str, major: str | None, major_colors: Dict[str, str]) -> Dict[str, str]:
    if relation in {"发生", "包含"}:
        width = "4" if relation == "发生" else "3"
        stroke = major_colors.get(major or "", RELATION_COLORS[relation])
    else:
        width = "2"
        stroke = RELATION_COLORS[relation]
    return {"lineWidth": width, "stroke": stroke, "textBorderWidth": "0"}


def build_rows(
    major_order: List[str],
    subtype_map: Dict[str, List[str]],
    details: Dict[str, Dict[str, str]],
) -> Tuple[List[List[object]], List[List[object]], List[List[object]], List[List[object]]]:
    major_colors = {m: MAJOR_PALETTE[i % len(MAJOR_PALETTE)] for i, m in enumerate(major_order)}

    links: List[Tuple[str, str, str]] = []
    for major in major_order:
        links.append((ROOT_NAME, major, "发生"))
        for subtype in subtype_map[major]:
            cause = f"{subtype}-故障原因"
            phen = f"{subtype}-故障现象"
            action = f"{subtype}-应对措施"
            cons = f"{subtype}-故障后果"
            risk = f"{subtype}-安全风险"
            res = f"{subtype}-应急资源"
            links.append((major, subtype, "包含"))
            links.append((subtype, cause, "起因于"))
            links.append((cause, phen, "表现为"))
            links.append((subtype, action, "处置"))
            links.append((cause, cons, "导致"))
            links.append((action, risk, "存在"))
            links.append((action, res, "需要"))

    degree: Dict[str, int] = {}
    for s, t, _ in links:
        degree[s] = degree.get(s, 0) + 1
        degree[t] = degree.get(t, 0) + 1

    node_id: Dict[str, str] = {}
    node_major: Dict[str, str] = {}
    ordered_names: List[str] = [ROOT_NAME]
    for major in major_order:
        ordered_names.append(major)
        node_major[major] = major
        for subtype in subtype_map[major]:
            ordered_names.append(subtype)
            node_major[subtype] = major
            for layer in DETAIL_LAYERS:
                n = f"{subtype}-{layer}"
                ordered_names.append(n)
                node_major[n] = major

    for i, name in enumerate(ordered_names):
        node_id[name] = str(i)

    node_rows: List[List[object]] = [[
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

    for name in ordered_names:
        if name == ROOT_NAME:
            desc = ROOT_DESC
            major = None
        elif name in major_order:
            desc = f"{name} 一级故障大类。"
            major = name
        elif any(name.endswith(f"-{layer}") for layer in DETAIL_LAYERS):
            subtype, layer = name.rsplit("-", 1)
            desc = details[subtype][layer]
            major = node_major[name]
        else:
            major = node_major[name]
            desc = f"{major} 下的二级故障小类：{name}。"

        style = node_style(name, major, major_colors)
        node_rows.append([
            node_id[name],
            name,
            str(degree.get(name, 0)),
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

    link_rows: List[List[object]] = [[
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
    for i, (s, t, r) in enumerate(links):
        if s == ROOT_NAME:
            major = t
        elif s in major_order:
            major = s
        else:
            major = node_major[s]
        style = relation_style(r, major, major_colors)
        link_rows.append([
            str(i),
            node_id[s],
            s,
            style["lineWidth"],
            r,
            style["stroke"],
            style["textBorderWidth"],
            node_id[t],
            t,
        ])

    group_rows: List[List[object]] = [[
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
    member_rows: List[List[object]] = [["id", "name", "member_id", "member_name"]]

    for gi, major in enumerate(major_order):
        members = [major]
        for subtype in subtype_map[major]:
            members.append(subtype)
            for layer in DETAIL_LAYERS:
                members.append(f"{subtype}-{layer}")
        group_rows.append([
            str(gi),
            major,
            f"{major} 的第一至第八层级图谱分组（新稿）。",
            str(len(members)),
            str(gi),
            "0",
            "1",
            major_colors[major],
            major_colors[major],
            major_colors[major],
        ])
        for m in members:
            member_rows.append([str(gi), major, node_id[m], m])

    return node_rows, link_rows, group_rows, member_rows


def validate_rows(
    node_rows: List[List[object]],
    link_rows: List[List[object]],
    group_rows: List[List[object]],
    member_rows: List[List[object]],
) -> None:
    node_ids = {r[0] for r in node_rows[1:]}
    if len(node_ids) != len(node_rows) - 1:
        raise ValueError("节点 id 重复")
    for r in link_rows[1:]:
        if r[1] not in node_ids or r[7] not in node_ids:
            raise ValueError(f"关系引用断裂: {r}")
    group_ids = {r[0] for r in group_rows[1:]}
    for r in member_rows[1:]:
        if r[0] not in group_ids or r[2] not in node_ids:
            raise ValueError(f"圈子成员引用断裂: {r}")


def copy_static_shell_files(template_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in [BLOCKS_FILE, TAGS_FILE, TAG_MEMBERS_FILE]:
        src = template_dir / name
        if src.exists():
            shutil.copy2(src, output_dir / name)


def generate_once(template_dir: Path, output_dir: Path, rows: Tuple[List[List[object]], ...]) -> None:
    node_rows, link_rows, group_rows, member_rows = rows
    write_workbook(template_dir / NODES_FILE, output_dir / NODES_FILE, node_rows, mode="shared")
    write_workbook(template_dir / LINKS_FILE, output_dir / LINKS_FILE, link_rows, mode="shared")
    write_workbook(template_dir / GROUPS_FILE, output_dir / GROUPS_FILE, group_rows, mode="inline")
    write_workbook(
        template_dir / GROUP_MEMBERS_FILE,
        output_dir / GROUP_MEMBERS_FILE,
        member_rows,
        mode="inline",
    )
    copy_static_shell_files(template_dir, output_dir)


def main() -> None:
    md_path = find_new_hierarchy_md()
    template_dir = find_template_dir()

    major_order, subtype_map, details = parse_new_hierarchy(md_path)
    rows = build_rows(major_order, subtype_map, details)
    validate_rows(*rows)

    out_work = XLS_DIR / "互感器" / "互感器_电力互感器新稿_第一至第八层级图谱数据"
    out_prod = XLS_DIR / "成品" / "互感器" / "互感器_电力互感器新稿_第一至第八层级图谱数据"

    generate_once(template_dir, out_work, rows)
    generate_once(template_dir, out_prod, rows)

    node_rows, link_rows, group_rows, member_rows = rows
    print("hierarchy_md:", md_path)
    print("template_dir:", template_dir)
    print("out_work:", out_work)
    print("out_prod:", out_prod)
    print(f"majors={len(major_order)} subtypes={sum(len(v) for v in subtype_map.values())}")
    print(f"nodes={len(node_rows)-1} links={len(link_rows)-1} groups={len(group_rows)-1} members={len(member_rows)-1}")


if __name__ == "__main__":
    main()
