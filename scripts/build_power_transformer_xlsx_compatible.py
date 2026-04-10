from __future__ import annotations

import html
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path


BASE_DIR = Path("D:/Graduate_test/dataset")
TXT_DIR = BASE_DIR / "txt" / "变压器"
TEMPLATE_DIR = (
    BASE_DIR
    / "xls"
    / "成品"
    / "高压断路器"
    / "高压断路器_第一至第七层级图谱数据"
)

WORK_OUTPUT_DIR = BASE_DIR / "xls" / "变压器" / "变压器_第一至第八层级图谱数据"
FINAL_OUTPUT_DIR = BASE_DIR / "xls" / "成品" / "变压器" / "变压器_第一至第八层级图谱数据"

ROOT_NAME = "变压器"
ROOT_DESC = "依据原始故障资料梳理形成的变压器第一至第八层级图谱实体。"
IMAGE_URL = "https://nrdstudio.cn/res/n.jpg"
ROOT_COLOR = "#9A3412"

DETAIL_LAYERS = ["故障原因", "故障现象", "应对措施", "故障后果", "安全风险", "应急资源"]

MAJOR_TO_SUBTYPES = {
    "保护与监测故障": [
        "变压器运行状态异常故障",
        "变压器瓦斯保护动作异常故障",
    ],
    "本体绝缘与铁心绕组故障": [
        "变压器进水受潮故障",
        "变压器铁心多点接地故障",
        "变压器绕组短路与断线故障",
        "变压器绕组变形故障",
        "变压器铁心故障",
        "大型电力变压器围屏爬电故障",
    ],
    "套管与调压及油箱附件故障": [
        "有载调压分接开关箱渗油故障",
        "变压器套管引线故障",
        "小型配电变压器喷油与油箱炸裂故障",
    ],
}

MAJOR_DESCRIPTIONS = {
    "保护与监测故障": "覆盖运行监测、保护动作和状态诊断相关故障。",
    "本体绝缘与铁心绕组故障": "覆盖绝缘系统、铁心和绕组本体相关故障。",
    "套管与调压及油箱附件故障": "覆盖套管、调压开关和油箱附件相关故障。",
}

DETAILS = {
    "变压器运行状态异常故障": {
        "故障原因": "负荷冲击、过电压、内部接触不良、局部放电和冷却或接地异常会引发运行状态异常。",
        "故障现象": "出现异常声响、振动和温升，伴随油色油位变化、异味或套管电晕等现象。",
        "应对措施": "加强巡视并核对负荷电压，检查冷却、接地和套管状态，必要时停运试验处置。",
        "故障后果": "若未及时处置，易发展为绝缘劣化和部件损伤，触发保护动作甚至停电。",
        "安全风险": "带缺陷运行可能导致电弧放电、喷油和火灾风险，危及现场人员与设备安全。",
        "应急资源": "需要红外测温、听音棒、油样取样器、局放检测工具和运行巡视记录。",
    },
    "变压器瓦斯保护动作异常故障": {
        "故障原因": "内部短路放电、冷却系统异常、空气侵入、潜油泵故障或二次回路问题会引发瓦斯异常动作。",
        "故障现象": "可出现轻瓦斯报警或重瓦斯跳闸，气体继电器积气和油流异常等现象。",
        "应对措施": "按规程开展取气与色谱分析，检查油路与冷却系统并核查二次回路，确认后停运检修。",
        "故障后果": "误判或延误处置会扩大内部故障，严重时导致绕组烧损和主变停运。",
        "安全风险": "故障条件下强送电可能引发严重电弧和爆炸事故。",
        "应急资源": "需要气体继电器试验工具、色谱检测资源、油样瓶、备用继电器和检修队伍。",
    },
    "变压器进水受潮故障": {
        "故障原因": "密封老化渗漏、呼吸器失效、检修进水和潮湿环境共同导致绝缘受潮。",
        "故障现象": "绝缘电阻和吸收比下降，油中含水升高，tanδ与色谱指标异常。",
        "应对措施": "排查渗漏并恢复密封，更换干燥剂，实施真空滤油和干燥处理后复测确认。",
        "故障后果": "绝缘强度下降后易形成局部放电并进一步发展为击穿故障。",
        "安全风险": "受潮状态继续运行存在突发短路和人身触电风险。",
        "应急资源": "需要含水测试仪、真空滤油装置、干燥空气源、密封备件和备用绝缘油。",
    },
    "变压器铁心多点接地故障": {
        "故障原因": "夹件位移、金属异物、绝缘垫老化和运输振动可导致铁心形成多点接地。",
        "故障现象": "接地电流异常、局部温升和气体继电器告警，伴随色谱气体增长。",
        "应对措施": "通过接地电流法定位并实施临时单点接地，停运后吊芯处理绝缘缺陷。",
        "故障后果": "长期多点接地会造成局部过热和绝缘炭化，进而诱发更严重故障。",
        "安全风险": "吊芯检修和临时处理过程存在触电、吊装和误操作风险。",
        "应急资源": "需要接地电流检测工具、绝缘垫片、吊装工装、检修票和隔离接地器材。",
    },
    "变压器绕组短路与断线故障": {
        "故障原因": "外部短路冲击、绝缘老化受潮、焊接缺陷和机械应力会导致绕组短路或断线。",
        "故障现象": "可见差动或瓦斯动作，直流电阻和短路阻抗异常，伴随温升和异响。",
        "应对措施": "开展电测定位并停运检查，修复引线焊点或更换受损绕组后复测投运。",
        "故障后果": "若保护拒动或处置不及时，可能造成绕组烧毁和长时间停电。",
        "安全风险": "故障电流和电弧会引发喷油着火并危及站内设备安全。",
        "应急资源": "需要直阻与阻抗测试设备、吊罩工具、绕组备件、消防器材和检修人员。",
    },
    "变压器绕组变形故障": {
        "故障原因": "短路电动力冲击、运输碰撞和装配夹紧不足会导致绕组机械变形。",
        "故障现象": "频响曲线偏移、短路阻抗变化，局放增大并出现运行噪声异常。",
        "应对措施": "执行频响与阻抗复测，评估变形程度并制定返厂修复或更换方案。",
        "故障后果": "变形会改变绝缘间隙，累积后可能演化为匝间短路和绝缘击穿。",
        "安全风险": "缺陷积累后可能发生突发性事故，存在设备损毁和运行中断风险。",
        "应急资源": "需要频响测试仪、阻抗测试仪、历史基线数据、吊装装备和专家支持。",
    },
    "变压器铁心故障": {
        "故障原因": "硅钢片绝缘损坏、接地片异常、夹件松动或局部短接可引发铁心故障。",
        "故障现象": "空载损耗增大、局部过热、噪声升高，油色和相关试验数据异常。",
        "应对措施": "结合空载试验和温升排查，停运后吊芯修复绝缘并完成紧固处理。",
        "故障后果": "持续过热会加速油纸绝缘老化并缩短主变寿命。",
        "安全风险": "局部过热升级时存在火灾及次生电气事故风险。",
        "应急资源": "需要空载损耗测试资源、红外测温设备、绝缘材料、紧固件和消防器材。",
    },
    "大型电力变压器围屏爬电故障": {
        "故障原因": "围屏受潮污染、场强集中、绝缘老化及油中杂质会导致围屏爬电。",
        "故障现象": "出现局放增强、爬电痕迹和色谱异常，绝缘试验边缘化。",
        "应对措施": "清洁干燥围屏并优化场强分布，更换受损绝缘件并加强油处理。",
        "故障后果": "爬电持续发展将导致绝缘击穿和主变被迫停运。",
        "安全风险": "突发放电会威胁人员安全并扩大设备损坏范围。",
        "应急资源": "需要局放检测设备、油处理装置、围屏绝缘件、防护用品和检修方案。",
    },
    "有载调压分接开关箱渗油故障": {
        "故障原因": "密封圈老化、焊缝缺陷、机械振动和温度循环会造成分接开关箱渗油。",
        "故障现象": "可见油位下降和箱体油迹，并伴随调压切换异常或报警。",
        "应对措施": "停电隔离后定位渗漏点，更换密封件或补焊并补油试验后恢复运行。",
        "故障后果": "油位过低会引起触头过热，导致调压功能失效甚至内部故障。",
        "安全风险": "带缺陷切换存在弧光、喷油和火灾风险。",
        "应急资源": "需要密封件套件、补焊工装、补油设备、切换试验工具和检修人员。",
    },
    "变压器套管引线故障": {
        "故障原因": "连接松动、接触电阻增大、振动疲劳及密封老化受潮会导致套管引线故障。",
        "故障现象": "套管发热变色并伴随放电声、渗油和接头温度异常。",
        "应对措施": "通过测温和停电检查紧固接头，清污补涂并更换老化密封与受损引线。",
        "故障后果": "接头烧蚀可进一步发展为套管击穿和主变停运故障。",
        "安全风险": "涉及高处与高压部位作业，存在触电和坠落风险。",
        "应急资源": "需要测温设备、力矩工具、引线与密封备件、绝缘涂料和登高防护。",
    },
    "小型配电变压器喷油与油箱炸裂故障": {
        "故障原因": "内部短路、保护拒动、密封薄弱和过热产气会导致喷油及油箱炸裂。",
        "故障现象": "表现为油箱鼓胀、喷油、压力异常、异响异味和保护动作。",
        "应对措施": "立即停运隔离并泄压排险，查明故障点后修复或更换设备。",
        "故障后果": "可造成设备报废并扩大停电影响范围，影响配网供电可靠性。",
        "安全风险": "喷油起火和爆炸具有较高人身伤害和设备毁损风险。",
        "应急资源": "需要泄压围油器材、消防装备、备用配电变压器、吊装车辆和抢修班组。",
    },
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

GROUP_COLORS = {
    "保护与监测故障": "#D97706",
    "本体绝缘与铁心绕组故障": "#0EA5E9",
    "套管与调压及油箱附件故障": "#8B5CF6",
}

NODES_FILE = "节点_nodes.xlsx"
LINKS_FILE = "关系_links.xlsx"
GROUPS_FILE = "圈子_groups.xlsx"
GROUP_MEMBERS_FILE = "圈子成员_group_members.xlsx"
BLOCKS_FILE = "区块_blocks.xlsx"
TAGS_FILE = "标签_tags.xlsx"
TAG_MEMBERS_FILE = "标签成员_tag_members.xlsx"


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


def build_shared_strings(rows: list[list[object]]) -> tuple[list[list[int]], str]:
    idx_map: dict[str, int] = {}
    unique: list[str] = []
    matrix: list[list[int]] = []
    total = 0
    for row in rows:
        idx_row: list[int] = []
        for v in row:
            s = "" if v is None else str(v)
            if s not in idx_map:
                idx_map[s] = len(unique)
                unique.append(s)
            idx_row.append(idx_map[s])
            total += 1
        matrix.append(idx_row)
    sis = "".join(f'<si><t xml:space="preserve">{xml_escape(t)}</t></si>' for t in unique)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{total}" uniqueCount="{len(unique)}">{sis}</sst>'
    )
    return matrix, xml


def build_sheet_data(rows: list[list[object]], mode: str, template_xml: str) -> tuple[str, str | None]:
    if not rows:
        raise ValueError("rows 不能为空")
    extra = ' x14ac:dyDescent="0.2"' if "x14ac:dyDescent" in template_xml else ""
    col_count = len(rows[0])
    row_count = len(rows)

    shared_matrix: list[list[int]] | None = None
    shared_xml: str | None = None
    if mode == "shared":
        shared_matrix, shared_xml = build_shared_strings(rows)

    row_xml: list[str] = []
    for r in range(1, row_count + 1):
        cells: list[str] = []
        for c in range(1, col_count + 1):
            ref = f"{col_name(c)}{r}"
            style = ' s="1"' if r == 1 else ""
            if mode == "shared":
                idx = shared_matrix[r - 1][c - 1]  # type: ignore[index]
                cells.append(f'<c r="{ref}"{style} t="s"><v>{idx}</v></c>')
            else:
                t = xml_escape(rows[r - 1][c - 1])
                cells.append(f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{t}</t></is></c>')
        row_xml.append(f'<row r="{r}" spans="1:{col_count}"{extra}>{"".join(cells)}</row>')
    return "<sheetData>" + "".join(row_xml) + "</sheetData>", shared_xml


def replace_sheet_xml(template_xml: str, sheet_data_xml: str, end_col: str, row_count: int) -> str:
    dim = f'<dimension ref="A1:{end_col}{row_count}"/>'
    out = re.sub(r"<dimension ref=\"[^\"]*\"/>", dim, template_xml, count=1)
    out = re.sub(r"<sheetData>.*?</sheetData>", sheet_data_xml, out, count=1, flags=re.S)
    out = re.sub(
        r'<selection [^>]*activeCell="[^"]+"[^>]*sqref="[^"]+"[^>]*/>',
        '<selection activeCell="A1" sqref="A1"/>',
        out,
        count=1,
    )
    return out


def write_workbook(template_path: Path, output_path: Path, rows: list[list[object]], mode: str) -> None:
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


def build_links() -> list[tuple[str, str, str]]:
    links: list[tuple[str, str, str]] = []
    for major, subs in MAJOR_TO_SUBTYPES.items():
        links.append((ROOT_NAME, major, "发生"))
        for s in subs:
            cause = f"{s}-故障原因"
            ph = f"{s}-故障现象"
            ms = f"{s}-应对措施"
            rs = f"{s}-故障后果"
            sk = f"{s}-安全风险"
            er = f"{s}-应急资源"
            links.extend(
                [
                    (major, s, "包含"),
                    (s, cause, "起因于"),
                    (cause, ph, "表现为"),
                    (s, ms, "处置"),
                    (cause, rs, "导致"),
                    (ms, sk, "存在"),
                    (ms, er, "需要"),
                ]
            )
    return links


def node_style(name: str, major: str | None) -> dict[str, str]:
    if name == ROOT_NAME:
        return {"fontFamily": "heiti", "fontSize": "30", "lineWidth": "5", "r": "100", "stroke": ROOT_COLOR, "textBorderWidth": "0", "weight": "10"}
    if name in GROUP_COLORS:
        return {"fontFamily": "heiti", "fontSize": "22", "lineWidth": "4", "r": "72", "stroke": GROUP_COLORS[name], "textBorderWidth": "0", "weight": "9"}
    for layer in DETAIL_LAYERS:
        if name.endswith(f"-{layer}"):
            return {"fontFamily": "heiti", "fontSize": "16", "lineWidth": "2", "r": "46", "stroke": LAYER_COLORS[layer], "textBorderWidth": "0", "weight": "6"}
    c = GROUP_COLORS.get(major or "", "#0EA5E9")
    return {"fontFamily": "heiti", "fontSize": "18", "lineWidth": "3", "r": "58", "stroke": c, "textBorderWidth": "0", "weight": "8"}


def relation_style(relation: str, major: str | None) -> dict[str, str]:
    if relation in {"发生", "包含"}:
        return {"lineWidth": "4" if relation == "发生" else "3", "stroke": GROUP_COLORS.get(major or "", RELATION_COLORS[relation]), "textBorderWidth": "0"}
    return {"lineWidth": "2", "stroke": RELATION_COLORS[relation], "textBorderWidth": "0"}


def build_rows() -> tuple[list[list[object]], list[list[object]], list[list[object]], list[list[object]]]:
    links = build_links()
    degree = Counter()
    for s, t, _ in links:
        degree[s] += 1
        degree[t] += 1

    major_of: dict[str, str] = {}
    ordered = [ROOT_NAME]
    for major, subs in MAJOR_TO_SUBTYPES.items():
        ordered.append(major)
        major_of[major] = major
        for s in subs:
            ordered.append(s)
            major_of[s] = major
            for layer in DETAIL_LAYERS:
                n = f"{s}-{layer}"
                ordered.append(n)
                major_of[n] = major

    node_rows: list[list[object]] = [[
        "id", "name", "degree", "desc", "fontFamily", "fontSize", "image", "lineWidth", "r", "stroke", "textBorderWidth", "weight"
    ]]
    node_id: dict[str, str] = {}
    for i, name in enumerate(ordered):
        node_id[name] = str(i)
        if name == ROOT_NAME:
            desc = ROOT_DESC
        elif name in MAJOR_DESCRIPTIONS:
            desc = MAJOR_DESCRIPTIONS[name]
        elif any(name.endswith(f"-{l}") for l in DETAIL_LAYERS):
            sub, layer = name.rsplit("-", 1)
            desc = DETAILS[sub][layer]
        else:
            desc = DETAILS[name]["故障原因"]
        st = node_style(name, major_of.get(name))
        node_rows.append([node_id[name], name, str(degree[name]), desc, st["fontFamily"], st["fontSize"], IMAGE_URL, st["lineWidth"], st["r"], st["stroke"], st["textBorderWidth"], st["weight"]])

    link_rows: list[list[object]] = [[
        "id", "from", "fromNodeName", "lineWidth", "relation", "stroke", "textBorderWidth", "to", "toNodeName"
    ]]
    for i, (s, t, r) in enumerate(links):
        major = t if s == ROOT_NAME else (s if s in GROUP_COLORS else major_of.get(s))
        st = relation_style(r, major)
        link_rows.append([str(i), node_id[s], s, st["lineWidth"], r, st["stroke"], st["textBorderWidth"], node_id[t], t])

    group_rows: list[list[object]] = [[
        "id", "name", "desc", "member_count", "order", "show", "type", "itemStyle.fill", "itemStyle.markColor", "itemStyle.stroke"
    ]]
    member_rows: list[list[object]] = [["id", "name", "member_id", "member_name"]]

    for gid, (major, subs) in enumerate(MAJOR_TO_SUBTYPES.items()):
        members: list[str] = [major]
        for s in subs:
            members.append(s)
            for layer in DETAIL_LAYERS:
                members.append(f"{s}-{layer}")
        color = GROUP_COLORS[major]
        group_rows.append([str(gid), major, f"{major}的第一至第八层级图谱分组。", str(len(members)), str(gid), "0", "1", color, color, color])
        for m in members:
            member_rows.append([str(gid), major, node_id[m], m])

    return node_rows, link_rows, group_rows, member_rows


def validate(node_rows: list[list[object]], link_rows: list[list[object]], group_rows: list[list[object]], member_rows: list[list[object]]) -> None:
    nids = {r[0] for r in node_rows[1:]}
    if len(nids) != len(node_rows) - 1:
        raise ValueError("节点ID重复")
    for r in link_rows[1:]:
        if r[1] not in nids or r[7] not in nids:
            raise ValueError(f"关系引用非法: {r}")
    gids = {r[0] for r in group_rows[1:]}
    for r in member_rows[1:]:
        if r[0] not in gids or r[2] not in nids:
            raise ValueError(f"圈子成员引用非法: {r}")


def copy_static_files(output_dir: Path) -> None:
    for name in [BLOCKS_FILE, TAGS_FILE, TAG_MEMBERS_FILE]:
        shutil.copy2(TEMPLATE_DIR / name, output_dir / name)


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    node_rows, link_rows, group_rows, member_rows = build_rows()
    validate(node_rows, link_rows, group_rows, member_rows)
    write_workbook(TEMPLATE_DIR / NODES_FILE, output_dir / NODES_FILE, node_rows, mode="shared")
    write_workbook(TEMPLATE_DIR / LINKS_FILE, output_dir / LINKS_FILE, link_rows, mode="shared")
    write_workbook(TEMPLATE_DIR / GROUPS_FILE, output_dir / GROUPS_FILE, group_rows, mode="inline")
    write_workbook(TEMPLATE_DIR / GROUP_MEMBERS_FILE, output_dir / GROUP_MEMBERS_FILE, member_rows, mode="inline")
    copy_static_files(output_dir)
    print(f"生成完成: {output_dir}")
    print(f"nodes={len(node_rows)-1} links={len(link_rows)-1} groups={len(group_rows)-1} members={len(member_rows)-1}")


def write_markdowns() -> None:
    TXT_DIR.mkdir(parents=True, exist_ok=True)

    first_level = TXT_DIR / "变压器故障层级梳理_第一层级.md"
    second_level = TXT_DIR / "变压器故障层级梳理_第二层级.md"
    layer_files = {
        "故障原因": TXT_DIR / "变压器故障层级梳理_第三层级_故障原因.md",
        "故障现象": TXT_DIR / "变压器故障层级梳理_第四层级_故障现象.md",
        "应对措施": TXT_DIR / "变压器故障层级梳理_第五层级_应对措施.md",
        "故障后果": TXT_DIR / "变压器故障层级梳理_第六层级_故障后果.md",
        "安全风险": TXT_DIR / "变压器故障层级梳理_第七层级_安全风险.md",
        "应急资源": TXT_DIR / "变压器故障层级梳理_第八层级_应急资源.md",
    }
    summary = TXT_DIR / "变压器故障层级梳理_第一至第八层级汇总稿.md"

    majors = list(MAJOR_TO_SUBTYPES.keys())

    first_level_text = """# 变压器故障层级梳理（第一层级）

## 1. 目标
确定变压器故障图谱根节点下的一级故障大类，作为后续层级扩展基准。

## 2. 根节点
- 根节点名称：`变压器`

## 3. 一级故障大类
1. 保护与监测故障
2. 本体绝缘与铁心绕组故障
3. 套管与调压及油箱附件故障
"""
    first_level.write_text(first_level_text.strip() + "\n", encoding="utf-8")

    second_lines = [
        "# 变压器故障层级梳理（第二层级）",
        "",
        "## 1. 目标",
        "确定 `变压器 -> 一级故障大类 -> 二级故障小类` 的结构清单。",
        "",
        "## 2. 第二层级推荐结果",
    ]
    for i, major in enumerate(majors, start=1):
        second_lines.append(f"### 2.{i} {major}")
        for j, subtype in enumerate(MAJOR_TO_SUBTYPES[major], start=1):
            second_lines.append(f"{j}. {subtype}")
        second_lines.append("")
    second_level.write_text("\n".join(second_lines).strip() + "\n", encoding="utf-8")

    for layer, path in layer_files.items():
        title_num = {
            "故障原因": "第三",
            "故障现象": "第四",
            "应对措施": "第五",
            "故障后果": "第六",
            "安全风险": "第七",
            "应急资源": "第八",
        }[layer]
        lines = [f"# 变压器故障层级梳理（{title_num}层级：{layer}）", ""]
        for i, major in enumerate(majors, start=1):
            lines.append(f"### 3.{i} {major}")
            lines.append("")
            for subtype in MAJOR_TO_SUBTYPES[major]:
                lines.append(f"#### {subtype}")
                lines.append(f"- 唯一节点名建议：`{subtype}-{layer}`")
                lines.append(f"- 描述/说明：{DETAILS[subtype][layer]}")
                lines.append("")
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    summary_lines = [
        "# 变压器故障层级梳理（第一至第八层级汇总稿）",
        "",
        "## 1. 建模范围",
        "本稿用于变压器故障知识图谱第一至第八层级建模与 Excel 生成。",
        "",
        "## 2. 层级结构",
        "```text",
        "变压器",
    ]
    for major in majors:
        summary_lines.append(f"├── {major}" if major != majors[-1] else f"└── {major}")
        subs = MAJOR_TO_SUBTYPES[major]
        for idx, subtype in enumerate(subs):
            prefix = "│   " if major != majors[-1] else "    "
            branch = "├── " if idx != len(subs) - 1 else "└── "
            summary_lines.append(f"{prefix}{branch}{subtype}")
    summary_lines.extend(["```", "", "## 3. 二级故障小类明细", ""])

    cnt = 1
    for major in majors:
        for subtype in MAJOR_TO_SUBTYPES[major]:
            summary_lines.append(f"### 3.{cnt} {subtype}")
            summary_lines.append(f"- 所属一级大类：{major}")
            for layer in DETAIL_LAYERS:
                summary_lines.append(f"- {layer}：{DETAILS[subtype][layer]}")
            summary_lines.append("")
            cnt += 1
    summary.write_text("\n".join(summary_lines).strip() + "\n", encoding="utf-8")
    print("层级文档生成完成: txt/变压器")


def main() -> None:
    write_markdowns()
    generate(WORK_OUTPUT_DIR)
    generate(FINAL_OUTPUT_DIR)


if __name__ == "__main__":
    main()
