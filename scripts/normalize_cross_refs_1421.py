from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(w("t")))


def find_paragraph(root: ET.Element, startswith: str) -> ET.Element:
    for p in root.iter(w("p")):
        if paragraph_text(p).strip().startswith(startswith):
            return p
    raise RuntimeError(f"paragraph not found: {startswith}")


def clear_paragraph_content(p: ET.Element) -> None:
    ppr = None
    for child in list(p):
        if child.tag == w("pPr"):
            ppr = child
        else:
            p.remove(child)
    if ppr is None:
        ppr = ET.Element(w("pPr"))
        p.insert(0, ppr)


def add_text_run(p: ET.Element, text: str, superscript: bool = False) -> None:
    r = ET.SubElement(p, w("r"))
    if superscript:
        rpr = ET.SubElement(r, w("rPr"))
        ET.SubElement(rpr, w("vertAlign"), {w("val"): "superscript"})
    t = ET.SubElement(r, w("t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = text


def add_field_run(p: ET.Element, bookmark: str, displayed: str, number_format: str | None = None) -> None:
    def make_r() -> ET.Element:
        r = ET.SubElement(p, w("r"))
        rpr = ET.SubElement(r, w("rPr"))
        ET.SubElement(rpr, w("vertAlign"), {w("val"): "superscript"})
        return r

    r_begin = make_r()
    ET.SubElement(r_begin, w("fldChar"), {w("fldCharType"): "begin"})

    r_instr = make_r()
    instr = f" REF {bookmark} \\r \\h"
    if number_format:
        instr += f' \\# "{number_format}"'
    instr += " \\* MERGEFORMAT "
    instr_text = ET.SubElement(r_instr, w("instrText"))
    instr_text.set(f"{{{XML_NS}}}space", "preserve")
    instr_text.text = instr

    r_sep = make_r()
    ET.SubElement(r_sep, w("fldChar"), {w("fldCharType"): "separate"})

    r_text = make_r()
    t = ET.SubElement(r_text, w("t"))
    t.text = displayed

    r_end = make_r()
    ET.SubElement(r_end, w("fldChar"), {w("fldCharType"): "end"})


def add_citation_group(p: ET.Element, nums: list[int], bookmark_by_num: dict[int, str]) -> None:
    nums = sorted(dict.fromkeys(nums))
    if len(nums) == 1:
        n = nums[0]
        add_field_run(p, bookmark_by_num[n], f"[{n}]")
        return

    consecutive = nums == list(range(nums[0], nums[-1] + 1))
    if consecutive:
        start, end = nums[0], nums[-1]
        add_field_run(p, bookmark_by_num[start], f"[{start}", "[0")
        add_text_run(p, "-", superscript=True)
        add_field_run(p, bookmark_by_num[end], f"{end}]", "0]")
        return

    first, last = nums[0], nums[-1]
    add_field_run(p, bookmark_by_num[first], f"[{first}", "[0")
    for n in nums[1:-1]:
        add_text_run(p, ",", superscript=True)
        add_field_run(p, bookmark_by_num[n], f"{n}", "0")
    add_text_run(p, ",", superscript=True)
    add_field_run(p, bookmark_by_num[last], f"{last}]", "0]")


def rebuild_paragraph(p: ET.Element, parts: list[tuple[str, str | list[int]]], bookmark_by_num: dict[int, str]) -> None:
    clear_paragraph_content(p)
    for kind, value in parts:
        if kind == "text":
            add_text_run(p, value)  # type: ignore[arg-type]
        elif kind == "cite":
            add_citation_group(p, value, bookmark_by_num)  # type: ignore[arg-type]
        else:
            raise RuntimeError(f"unknown part kind: {kind}")


def extract_bookmark_mapping(root: ET.Element) -> dict[int, str]:
    mapping: dict[int, str] = {}
    inside_refs = False
    ref_no = 0
    for p in root.iter(w("p")):
        text = paragraph_text(p).strip()
        if text == "参考文献":
            inside_refs = True
            continue
        if not inside_refs:
            continue
        if text == "致谢":
            break
        if not text:
            continue
        names = [
            el.attrib.get(w("name"))
            for el in p.iter(w("bookmarkStart"))
            if el.attrib.get(w("name")) and not el.attrib.get(w("name")).startswith("_GoBack")
        ]
        if names:
            ref_no += 1
            mapping[ref_no] = names[0]
    return mapping


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python normalize_cross_refs_1421.py <src.docx> <dst.docx>")

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    with ZipFile(src) as zin:
        info_map = {info.filename: info for info in zin.infolist()}
        file_map = {name: zin.read(name) for name in info_map}

    root = ET.fromstring(file_map["word/document.xml"])
    bookmark_by_num = extract_bookmark_mapping(root)

    targets = {
        "生成式大语言模型通常采用 Transformer 解码器结构": [
            ("text", "生成式大语言模型通常采用 Transformer 解码器结构。预训练阶段负责学习语言规律和常见知识表达，指令微调阶段再把模型调整到问答、抽取和写作等任务。对电气设备故障场景而言，输入经常包含简称、位置修饰和省略式描述，规则模板难以穷尽所有写法，大模型在语义理解和连续文本组织上更具优势。电力领域已有研究将大模型与知识图谱结合用于问答和应急知识组织，说明外部知识结构确实有助于改善专业文本的一致性"),
            ("cite", [4, 11]),
            ("text", "；其他垂直领域的知识问答、内容检查和知识图谱平台实践也表明，大模型与结构化知识结合能够提高专业任务适配性"),
            ("cite", [16, 17, 18]),
            ("text", "。"),
        ],
        "知识图谱把对象、属性及其关系组织为图结构": [
            ("text", "知识图谱把对象、属性及其关系组织为图结构，适合表示电气设备故障中的因果链条。以断路器控制回路异常为例，故障可能对应拒分、拒合等现象，后续处置又会涉及隔离、检查、抢修和恢复验证。将这些内容整理为节点和关系后，系统就可以从故障节点出发检索原因、现象和措施，为预案章节提供可追溯依据"),
            ("cite", [8, 9]),
            ("text", "。"),
        ],
        "图谱构建资料来自设备原理说明、典型故障案例、运维规程和历史预案文本": [
            ("text", "图谱构建资料来自设备原理说明、典型故障案例、运维规程和历史预案文本，文件格式包括 Word、PDF 和 Markdown。不同资料对同一设备或故障的表述并不完全一致，缩写、同义词和上下文省略较常见。若直接从原文抽取实体和关系，容易形成重复节点和方向不一致的关系，这也是模式层需要先行确定的现实原因"),
            ("cite", [22, 23, 24, 25, 26, 27, 28, 29, 30]),
            ("text", "。"),
        ],
        "本文采用先定模式层、再整理数据的构建路线": [
            ("text", "本文采用先定模式层、再整理数据的构建路线。模式层由人工依据领域经验和现行规程确定，原始资料的拆分、归类和同义归并由大语言模型辅助完成，结果再经人工复核后导入图数据库。模型只在预定义节点类型和关系范围内识别内容，这样既保留了整理效率，也避免了图谱结构随着原始资料写法波动"),
            ("cite", [10, 11]),
            ("text", "。图3-1展示了两种构建方式的差异。"),
        ],
        "电气设备应急预案智能生成涉及知识组织、流程调度、接口聚合和前端展示等多个环节": [
            ("text", "电气设备应急预案智能生成涉及知识组织、流程调度、接口聚合和前端展示等多个环节。为避免将全部逻辑耦合在单一工作流或单一服务中，本文按照职责边界将系统划分为数据与知识层、运行时编排层、接口封装层和前端交互层四个层次，各层之间通过标准化接口通信"),
            ("cite", [1, 19, 31, 32]),
            ("text", "。"),
        ],
    }

    for startswith, parts in targets.items():
        p = find_paragraph(root, startswith)
        rebuild_paragraph(p, parts, bookmark_by_num)

    new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with ZipFile(src) as zin, ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = new_xml if info.filename == "word/document.xml" else zin.read(info.filename)
            zout.writestr(info, data)


if __name__ == "__main__":
    main()
