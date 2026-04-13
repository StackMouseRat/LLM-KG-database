from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


BASE_DIR = Path("D:/Graduate_test/dataset")
TXT_ROOT = BASE_DIR / "txt"
XLS_ROOT = BASE_DIR / "xls"
OUT_DIR = XLS_ROOT / "generated_mutual_import_styled"

IMAGE_URL = "https://nrdstudio.cn/res/n.jpg"
ROOT_NODE = "电力互感器"
ROOT_FILL = "#9A3412"
MAJOR_GROUPS = ["电压互感器故障", "电流互感器故障", "互感器分类与预防"]
MAJOR_FILL = {
    "电压互感器故障": "#D97706",
    "电流互感器故障": "#0EA5E9",
    "互感器分类与预防": "#7C3AED",
}
GROUP_DESC = {
    "电压互感器故障": "电压互感器典型故障、谐振、熔断器等运行异常专题。",
    "电流互感器故障": "电流互感器受潮、爆炸、二次回路异常等专题。",
    "互感器分类与预防": "互感器故障分类、原因分析与分场景预防措施。",
}

NODES_FILE = "节点_nodes.xlsx"
LINKS_FILE = "关系_links.xlsx"
GROUPS_FILE = "圈子_groups.xlsx"
GROUP_MEMBERS_FILE = "圈子成员_group_members.xlsx"
BLOCKS_FILE = "区块_blocks.xlsx"
TAGS_FILE = "标签_tags.xlsx"
TAG_MEMBERS_FILE = "标签成员_tag_members.xlsx"


@dataclass
class Section:
    title: str
    text: str
    group: str


def find_input_txt() -> Path:
    # 优先精确命中
    for p in TXT_ROOT.rglob("电力互感器.txt"):
        return p
    # 兜底：名称含“互感器”且不是层级拆分稿
    cands = [
        p
        for p in TXT_ROOT.rglob("*.txt")
        if "互感器" in p.name and "层级梳理" not in p.name and "运行典型故障" not in p.name
    ]
    if not cands:
        raise FileNotFoundError("未找到互感器输入 txt")
    # 取体量最大的一份正文
    return max(cands, key=lambda x: x.stat().st_size)


def find_template_dir() -> Path:
    # 优先使用“已验证可导入”的历史互感器成品壳
    for p in (XLS_ROOT / "成品").rglob("互感器_第一至第八层级图谱数据"):
        if p.is_dir():
            return p
    # 兜底用断路器导入壳
    for p in XLS_ROOT.rglob("high_voltage_breaker_1to8_import4"):
        if p.is_dir():
            return p
    raise FileNotFoundError("未找到可用模板壳目录")


def read_text_auto(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("decode", b"", 0, 1, f"无法解码: {path}")


def normalize_lines(text: str) -> List[str]:
    out: List[str] = []
    for raw in text.splitlines():
        line = raw.replace("\u3000", " ").strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        out.append(line)
    return out


def heading_level(line: str) -> int:
    if re.match(r"^第\s*\d+章", line):
        return 1
    if re.match(r"^\d+\.\d+", line):
        return 2
    if re.match(r"^第\s*\d+节", line):
        return 2
    if re.match(r"^[一二三四五六七八九十]+、", line):
        return 3
    if re.match(r"^\d+[、.]", line):
        return 4
    return 0


def classify_group(title: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)", title)
    if m:
        idx = int(m.group(2))
        if idx <= 5:
            return "电压互感器故障"
        return "电流互感器故障"
    if "电压互感器" in title:
        return "电压互感器故障"
    if "电流互感器" in title or "SF₆" in title or "SF6" in title:
        return "电流互感器故障"
    return "互感器分类与预防"


def parse_sections(lines: List[str]) -> List[Section]:
    sections: List[Section] = []
    current_title = "概述"
    buf: List[str] = []

    for line in lines:
        lvl = heading_level(line)
        if lvl in (2, 3):
            if buf:
                body = " ".join(buf)
                sections.append(Section(current_title, body, classify_group(current_title)))
            current_title = line
            buf = [line]
        else:
            buf.append(line)

    if buf:
        body = " ".join(buf)
        sections.append(Section(current_title, body, classify_group(current_title)))

    # 去重、过滤噪声
    out: List[Section] = []
    seen = set()
    for s in sections:
        text = s.text.strip()
        if len(text) < 20:
            continue
        key = (s.title, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def make_desc(text: str, max_len: int = 180) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_rows(
    sections: List[Section],
) -> Tuple[List[List[object]], List[List[object]], List[List[object]], List[List[object]]]:
    node_id: Dict[str, str] = {}
    node_desc: Dict[str, str] = {}
    node_style: Dict[str, Dict[str, str]] = {}
    links_raw: List[Tuple[str, str, str, str, str]] = []  # src,dst,relation,color,width

    def add_node(name: str, desc: str, style: Dict[str, str]) -> None:
        if name in node_id:
            return
        node_id[name] = str(len(node_id))
        node_desc[name] = desc
        node_style[name] = style

    add_node(
        ROOT_NODE,
        "依据新版本《电力互感器》文本抽取得到的互感器故障知识图谱根节点。",
        {
            "fontFamily": "heiti",
            "fontSize": "30",
            "lineWidth": "5",
            "r": "100",
            "stroke": ROOT_FILL,
            "textBorderWidth": "0",
            "weight": "10",
        },
    )

    for g in MAJOR_GROUPS:
        add_node(
            g,
            GROUP_DESC[g],
            {
                "fontFamily": "heiti",
                "fontSize": "22",
                "lineWidth": "4",
                "r": "72",
                "stroke": MAJOR_FILL[g],
                "textBorderWidth": "0",
                "weight": "9",
            },
        )
        links_raw.append((ROOT_NODE, g, "发生", MAJOR_FILL[g], "4"))

    seen_titles = set()
    for s in sections:
        title = s.title.strip()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        add_node(
            title,
            make_desc(s.text),
            {
                "fontFamily": "heiti",
                "fontSize": "16",
                "lineWidth": "2",
                "r": "46",
                "stroke": MAJOR_FILL[s.group],
                "textBorderWidth": "0",
                "weight": "6",
            },
        )
        links_raw.append((s.group, title, "包含", MAJOR_FILL[s.group], "3"))

    degree = {k: 0 for k in node_id}
    for s, t, _, _, _ in links_raw:
        degree[s] += 1
        degree[t] += 1

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
    for name, nid in sorted(node_id.items(), key=lambda x: int(x[1])):
        st = node_style[name]
        node_rows.append(
            [
                nid,
                name,
                str(degree[name]),
                node_desc[name],
                st["fontFamily"],
                st["fontSize"],
                IMAGE_URL,
                st["lineWidth"],
                st["r"],
                st["stroke"],
                st["textBorderWidth"],
                st["weight"],
            ]
        )

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
    for i, (src, dst, rel, color, width) in enumerate(links_raw):
        link_rows.append([str(i), node_id[src], src, width, rel, color, "0", node_id[dst], dst])

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

    group_nodes: Dict[str, List[str]] = {g: [g] for g in MAJOR_GROUPS}
    for s in sections:
        if s.title in node_id:
            group_nodes[s.group].append(s.title)

    for i, g in enumerate(MAJOR_GROUPS):
        gid = str(i)
        uniq = []
        seen = set()
        for n in group_nodes[g]:
            if n in seen:
                continue
            seen.add(n)
            uniq.append(n)
        group_rows.append(
            [
                gid,
                g,
                f"{g} 的新稿图谱分组（壳兼容导入版）。",
                str(len(uniq)),
                str(i),
                "0",
                "1",
                MAJOR_FILL[g],
                MAJOR_FILL[g],
                MAJOR_FILL[g],
            ]
        )
        for n in uniq:
            member_rows.append([gid, g, node_id[n], n])

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
    if len(group_ids) != len(group_rows) - 1:
        raise ValueError("圈子 id 重复")

    for r in member_rows[1:]:
        if r[0] not in group_ids:
            raise ValueError(f"圈子成员 group id 不存在: {r}")
        if r[2] not in node_ids:
            raise ValueError(f"圈子成员 member_id 不存在: {r}")


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
    rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")
    target = re.search(rf'<Relationship Id="{re.escape(rel_id)}"[^>]*Target="([^"]+)"', rels_xml).group(1)
    return "xl/" + target.lstrip("/")


def parse_dimension_end_col(template_xml: str) -> str:
    m = re.search(r'<dimension ref="[A-Z]+\d+:([A-Z]+)\d+"', template_xml)
    return m.group(1) if m else "A"


def build_shared_strings(rows: List[List[object]]) -> Tuple[List[List[int]], str]:
    index_map: Dict[str, int] = {}
    unique: List[str] = []
    matrix: List[List[int]] = []
    total = 0

    for row in rows:
        ridx: List[int] = []
        for val in row:
            s = "" if val is None else str(val)
            if s not in index_map:
                index_map[s] = len(unique)
                unique.append(s)
            ridx.append(index_map[s])
            total += 1
        matrix.append(ridx)

    sis = "".join(f'<si><t xml:space="preserve">{xml_escape(s)}</t></si>' for s in unique)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{total}" uniqueCount="{len(unique)}">{sis}</sst>'
    )
    return matrix, xml


def build_sheet_data(rows: List[List[object]], mode: str, template_xml: str) -> Tuple[str, str | None]:
    if not rows:
        raise ValueError("rows 不能为空")
    extra = ' x14ac:dyDescent="0.2"' if "x14ac:dyDescent" in template_xml else ""
    col_count = len(rows[0])
    row_xml: List[str] = []

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
                cells.append(f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{t}</t></is></c>')
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


def copy_optional_shell_files(template_dir: Path, output_dir: Path) -> None:
    for name in (BLOCKS_FILE, TAGS_FILE, TAG_MEMBERS_FILE):
        p = template_dir / name
        if p.exists():
            (output_dir / name).write_bytes(p.read_bytes())


def check_shell_compat(template_file: Path, out_file: Path, expected_mode: str) -> None:
    with zipfile.ZipFile(template_file) as zt, zipfile.ZipFile(out_file) as zo:
        t_styles = zt.read("xl/styles.xml").decode("utf-8", errors="replace")
        o_styles = zo.read("xl/styles.xml").decode("utf-8", errors="replace")
        t_xfs = re.search(r"<cellXfs[^>]*count=\"(\d+)\"", t_styles)
        o_xfs = re.search(r"<cellXfs[^>]*count=\"(\d+)\"", o_styles)
        if (t_xfs.group(1) if t_xfs else "") != (o_xfs.group(1) if o_xfs else ""):
            raise ValueError(f"styles cellXfs 不一致: {template_file.name}")

        out_sheet = zo.read(get_sheet_path(zo)).decode("utf-8", errors="replace")
        if expected_mode == "shared":
            if 't="inlineStr"' in out_sheet:
                raise ValueError(f"{out_file.name} 发现 inlineStr（应为 shared）")
            if "xl/sharedStrings.xml" not in zo.namelist():
                raise ValueError(f"{out_file.name} 缺少 sharedStrings.xml")


def generate() -> None:
    txt_path = find_input_txt()
    template_dir = find_template_dir()

    text = read_text_auto(txt_path)
    sections = parse_sections(normalize_lines(text))
    node_rows, link_rows, group_rows, member_rows = build_rows(sections)
    validate_rows(node_rows, link_rows, group_rows, member_rows)

    node_tpl = next(template_dir.glob("*_nodes.xlsx"))
    link_tpl = next(template_dir.glob("*_links.xlsx"))
    group_tpl = next(template_dir.glob("*_groups.xlsx"))
    member_tpl = next(template_dir.glob("*_group_members.xlsx"))

    node_out = OUT_DIR / node_tpl.name
    link_out = OUT_DIR / link_tpl.name
    group_out = OUT_DIR / group_tpl.name
    member_out = OUT_DIR / member_tpl.name

    write_workbook(node_tpl, node_out, node_rows, mode="shared")
    write_workbook(link_tpl, link_out, link_rows, mode="shared")
    write_workbook(group_tpl, group_out, group_rows, mode="inline")
    write_workbook(member_tpl, member_out, member_rows, mode="inline")
    copy_optional_shell_files(template_dir, OUT_DIR)

    # 壳一致性检查（重点四表）
    check_shell_compat(node_tpl, node_out, expected_mode="shared")
    check_shell_compat(link_tpl, link_out, expected_mode="shared")
    check_shell_compat(group_tpl, group_out, expected_mode="inline")
    check_shell_compat(member_tpl, member_out, expected_mode="inline")

    print("input_txt:", txt_path)
    print("template_dir:", template_dir)
    print("output_dir:", OUT_DIR)
    print("sections:", len(sections))
    print("nodes:", len(node_rows) - 1)
    print("links:", len(link_rows) - 1)
    print("groups:", len(group_rows) - 1)
    print("group_members:", len(member_rows) - 1)
    print("node_file:", node_out)
    print("link_file:", link_out)
    print("group_file:", group_out)
    print("member_file:", member_out)


if __name__ == "__main__":
    generate()
