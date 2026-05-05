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


FINAL_REFS = [
    "GUAN C, FANG D, LI T, et al. The Research on Current Status of Digital Technology System of Electric Power Emergency Plan[C/OL]//2024 IEEE 14th International Conference on Electronics Information and Emergency Communication (ICEIEC). Beijing, China: IEEE, 2024: 1—4[2026-03-10]. https://ieeexplore.ieee.org/document/10561800/. DOI:10.1109/ICEIEC61773.2024.10561800.",
    "潘志伟．突发事件数字化应急预案智能生成方法研究［D/OL］．沈阳大学，2024［2026-04-23］．https://d.wanfangdata.com.cn/thesis/D03472758．",
    "张建生．火力发电厂设备检修作业危险点控制措施及突发事件应急预案［M］．中国电力出版社，2008．",
    "陈灯．基于大语言模型融合知识图谱的电力领域问答系统研究［D/OL］．2025［2026-04-28］．https://link.cnki.net/doi/10.27139/d.cnki.ghbdu.2025.001689．DOI:10.27139/d.cnki.ghbdu.2025.001689．",
    "宋婧．基于检索增强生成及知识图谱的问答系统研究［D/OL］．大连理工大学，2025［2026-04-28］．https://d.wanfangdata.com.cn/thesis/D04335345．",
    "杨荣正．基于知识图谱和信息抽取的城轨交通应急处置方案生成研究［D/OL］．北京交通大学，2025［2026-03-10］．https://doi.org/10.26944/d.cnki.gbfju.2023.002559．DOI:10.26944/d.cnki.gbfju.2023.002559．",
    "WANG L, LIU X, LIU Y, et al. Knowledge Graph-Based Method for Intelligent Generation of Emergency Plans for Water Conservancy Projects[J/OL]. IEEE Access, 2023, 11: 84414—84429. DOI:10.1109/ACCESS.2023.3302399.",
    "LIU T, ZHANG Q, WANG M, et al. Intelligent generation method of emergency plan based on knowledge graph[C/OL]//2024 4th International Conference on Neural Networks, Information and Communication (NNICE). Guangzhou, China: IEEE, 2024: 1692—1698[2026-03-10]. https://ieeexplore.ieee.org/document/10498620/. DOI:10.1109/NNICE61279.2024.10498620.",
    "姚立伟，任福，王双燕，等．地震灾害应急预案的生成式编制方法［J/OL］．武汉大学学报（信息科学版），2025，50（6）［2026-03-10］．https://doi.org/10.13203/j.whugis20250127．DOI:10.13203/j.whugis20250127．",
    "阎光伟，张云馨，符哲源，等．基于改进集合预测网络的输变电设备故障知识图谱构建方法［J/OL］．电工技术学报，2025，40（15）［2026-03-11］．https://doi.org/10.19595/j.cnki.1000-6753.tces.241362．DOI:10.19595/j.cnki.1000-6753.tces.241362．",
    "林雨辰，张新伟，张思航，等．融合大语言模型的台风场景下电网应急知识图谱构建方法［J/OL］．清华大学学报（自然科学版），2026［2026-03-10］．https://doi.org/10.16511/j.cnki.qhdxxb.2026.26.015．DOI:10.16511/j.cnki.qhdxxb.2026.26.015．",
    "CHEN M, TAO Z, TANG W, et al. Enhancing Emergency Decision-making with Knowledge Graphs and Large Language Models[EB/OL]. arXiv, 2023[2026-03-10]. http://arxiv.org/abs/2311.08732. DOI:10.48550/arXiv.2311.08732.",
    "张晓蕾，高进东，赵开功，等．煤矿事故智能应急预案生成方法研究［J/OL］．矿业安全与环保，2024，51（1）［2026-03-10］．https://doi.org/10.19835/j.issn.1008-4495.20230320．DOI:10.19835/j.issn.1008-4495.20230320．",
    "牛晨璐．基于生成式人工智能技术的公安机关大型活动应急预案编制研究［D/OL］．中国人民公安大学，2025［2026-03-10］．https://doi.org/10.27634/d.cnki.gzrgu.2025.000350．DOI:10.27634/d.cnki.gzrgu.2025.000350．",
    "王成晨．大型活动突发事件交通应急预案快速生成与动态优化方法［D/OL］．东南大学，2022［2026-03-10］．https://doi.org/10.27014/d.cnki.gdnau.2020.002130．DOI:10.27014/d.cnki.gdnau.2020.002130．",
    "贾鹏．基于大语言模型的农业知识问答系统的研究与设计［D/OL］．河北科技师范学院，2024［2026-04-15］．https://d.wanfangdata.com.cn/thesis/D03472322．",
    "郑文军．基于大语言模型的网络安全测评报告内容检查方法研究［D/OL］．2025［2026-04-29］．https://link.cnki.net/doi/10.26969/d.cnki.gbydu.2025.001279．DOI:10.26969/d.cnki.gbydu.2025.001279．",
    "蒋明君．基于知识图谱和大语言模型的智慧教材应用平台的设计与实现［D/OL］．2025［2026-04-15］．https://link.cnki.net/doi/10.26969/d.cnki.gbydu.2025.002859．DOI:10.26969/d.cnki.gbydu.2025.002859．",
    "慕铭．基于大语言模型的智能工作流在中医医学文本汉英翻译中的应用研究［D/OL］．2025［2026-04-29］．https://link.cnki.net/doi/10.26962/d.cnki.gbjwu.2025.000827．DOI:10.26962/d.cnki.gbjwu.2025.000827．",
    "兰天，马梓奥 等．生成式文本质量的自动评估方法综述［C/OL］//The 23rd Chinese National Conference on Computational Linguistics．Taiyuan, China：Chinese Information Processing Society of China，2024：169—196．https://aclanthology.org/2024.ccl-2.10/．",
    "中国三峡新能源有限公司．风力发电工程技术丛书  风电场应急预案编制及范例［M/OL］．中国水利水电出版社，2017［2026-03-16］．http://book.ucdrs.superlib.net/views/specific/2929/bookDetail.jsp?dxNumber=000016826389&d=60131A79C0BF461FE1CA8EF5F8C19511&fenlei=1815080204．",
    "赵全胜，胡伟 等．220kV及以下变电站设备异常和故障典型案例分析［M］．中国电力出版社．",
    "朱远达，洪鹤，曲妍 等．变电设备故障典型案例分析与预防措施［M］．第1版．东北大学出版社，2017．",
    "朱发强，陈佩华 等．电力通信光缆工程［M］．中国电力出版社，2016．",
    "车俊禄，郭飞 等．电网设备故障典型案例［M］．中国电力出版社，2016．",
    "赖敏，张超 等．光缆与光设备维护［M］．人民邮电出版社，2014．",
    "陈平，王鹏．配电网典型故障案例分析［M］．中国电力出版社，2017．",
    "陈平，王鹏．输变电设备典型故障案例分析［M］．中国电力出版社，2018．",
    "张逸群，李海星．输电线路典型故障案例分析及预防［M］．中国电力出版社，2012．",
    "刘勇．新型电力变压器结构原理及常见故障处理［M］．中国电力出版社，2014．",
    "电力人工智能知识图谱组件功能及接口规范［S］．",
    "马玮璐．知识图谱构建管理系统研究［D/OL］．中国农业科学院，2024［2026-04-15］．https://d.wanfangdata.com.cn/thesis/Y4397192．",
    "肖正亮．GraphRAG与智能代理结合的社交平台自动化辩论框架研究［D/OL］．内蒙古大学，2025［2026-04-15］．https://d.wanfangdata.com.cn/thesis/D04195249．",
]

Z_MAP = {
    1: 8,
    2: 1,
    6: 9,
    8: 10,
    9: 13,
    10: 11,
    11: 12,
    16: 4,
    17: 5,
    18: 14,
    23: 15,
    25: 2,
    26: 21,
}


def paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(w("t")))


def set_paragraph_text(p: ET.Element, text: str) -> None:
    ppr = None
    for child in list(p):
        if child.tag == w("pPr"):
            ppr = child
        else:
            p.remove(child)
    if ppr is None:
        ppr = ET.Element(w("pPr"))
        p.insert(0, ppr)
    r = ET.Element(w("r"))
    t = ET.SubElement(r, w("t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = text
    p.append(r)


def find_paragraph(root: ET.Element, startswith: str) -> ET.Element:
    for p in root.iter(w("p")):
        if paragraph_text(p).strip().startswith(startswith):
            return p
    raise RuntimeError(f"paragraph not found: {startswith}")


def replace_z_citations(text: str) -> str:
    def repl_ascii(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"[{Z_MAP.get(old, old)}]"

    def repl_full(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"［{Z_MAP.get(old, old)}］"

    text = re.sub(r"\[Z(\d+)\]", repl_ascii, text)
    text = re.sub(r"［Z(\d+)］", repl_full, text)
    return text


def replace_numeric_citations(text: str, mapping: dict[int, int]) -> str:
    def repl_ascii(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"[{mapping.get(old, old)}]"

    def repl_full(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"［{mapping.get(old, old)}］"

    text = re.sub(r"\[(\d+)\]", repl_ascii, text)
    text = re.sub(r"［(\d+)］", repl_full, text)
    return text


def make_paragraph_like(template: ET.Element, text: str) -> ET.Element:
    p = copy.deepcopy(template)
    set_paragraph_text(p, text)
    return p


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python rebuild_0505_from_0107_xml.py <src.docx> <dst.docx>")

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    with ZipFile(src) as zin:
        info_map = {info.filename: info for info in zin.infolist()}
        file_map = {name: zin.read(name) for name in info_map}

    root = ET.fromstring(file_map["word/document.xml"])
    body = root.find(w("body"))
    assert body is not None

    paragraph_replacements = {
        "电力设备发生故障后，现场处置需要在较短时间内完成故障判断": "电力设备发生故障后，现场处置需要在较短时间内完成故障判断、风险识别和资源调度，预案文本能否快速给出处置依据会直接影响后续行动。已有研究指出，电力应急预案管理正在从文档归档转向数字化应用[1]，突发事件数字化预案生成也要求把知识组织、场景匹配和内容结构化放入同一流程[2]。问题在于，故障机理、事故案例和操作规程仍分散在不同资料中，预案章节所需知识缺少统一索引[3]。",
        "大语言模型能够处理故障描述中的非规范表达": "大语言模型能够处理故障描述中的非规范表达，知识图谱则把设备、故障及处置知识固定为可查询结构。电力领域已有研究将两者用于专业问答和知识组织，说明外部知识确实有助于改善模型回答中的事实一致性[4][5]。但本文面对的不是单次问答，而是整篇预案生成，因此模型之外还必须增加章节模板和流程控制，使故障事实、章节边界和来源记录都能被检查[6][7]。",
        "大语言模型与检索增强生成的结合，已经被用于缓解专业问答中的知识盲区": "大语言模型与检索增强生成的结合，已经被用于缓解专业问答中的知识盲区。相关研究显示，图谱约束和外部检索能够改善回答准确性[4][5]，应急决策研究中也开始使用大模型与知识结构进行辅助判断[12]。但电气设备预案生成对模型提出了更强约束：输入主体要判准，故障知识要能追溯，章节内容还要与模板保持一致。若只把检索结果拼入提示词，模型仍可能在章节边界和处置依据上产生不稳定输出[6]。",
        "现有研究已经证明，知识图谱适合承担应急知识的结构化组织任务": "现有研究已经证明，知识图谱适合承担应急知识的结构化组织任务。相关工作将图谱用于应急预案生成[8]，水利工程等场景也验证了图谱对预案知识整理的支撑作用[9]。在电力领域，输变电设备故障图谱研究主要解决故障文本抽取、实体识别和图谱构建问题[10]，而电网应急知识图谱与大模型结合的研究则进一步说明领域图谱能够参与电力应急知识组织[11]。不过，多数工作仍停留在检索、问答或知识管理层面，对预案章节结构和处置流程的约束相对不足。",
        "智能预案生成已经覆盖煤矿事故": "智能预案生成已经覆盖煤矿事故[13]、水利工程[9]、大型活动[14]、大型活动交通应急[15]和突发事件数字化预案[2]等场景。这些工作说明自动化预案生成具有可行性，但电气设备故障处置还要面对设备主体消歧、二级故障匹配、图谱空间选择和多故障融合等更细的运行问题。本文据此把设备故障知识图谱、结构化预案模板、大语言模型和工作流编排结合起来，研究面向电力设备故障场景的可控生成方法。",
        "生成式大语言模型通常采用 Transformer 解码器结构": "生成式大语言模型通常采用 Transformer 解码器结构。预训练阶段负责学习语言规律和常见知识表达，指令微调阶段再把模型调整到问答、抽取和写作等任务。对电气设备故障场景而言，输入经常包含简称、位置修饰和省略式描述，规则模板难以穷尽所有写法，大模型在语义理解和连续文本组织上更具优势。电力领域已有研究将大模型与知识图谱结合用于问答和应急知识组织，说明外部知识结构确实有助于改善专业文本的一致性[11][4]；其他垂直领域的知识问答、内容检查和知识图谱平台实践也表明，大模型与结构化知识结合能够提高专业任务适配性[16][17][18]。",
        "知识图谱把对象、属性及其关系组织为图结构": "知识图谱把对象、属性及其关系组织为图结构，适合表示电气设备故障中的因果链条。以断路器控制回路异常为例，故障可能对应拒分、拒合等现象，后续处置又会涉及隔离、检查、抢修和恢复验证。将这些内容整理为节点和关系后，系统就可以从故障节点出发检索原因、现象和措施，为预案章节提供可追溯依据[8][9]。",
        "检索增强生成（Retrieval-Augmented Generation，RAG）的基本思路": "检索增强生成（Retrieval-Augmented Generation，RAG）的基本思路，是在模型生成之前先从外部知识库中检索相关内容，再将检索结果与用户输入共同送入模型。这样做的目的，一方面是补充模型在专业领域中的知识覆盖，另一方面也是为了降低事实幻觉和答非所问的风险[5]。在本文的任务场景下，RAG 主要承担案例类知识的召回功能，而预案生成所依赖的主知识来源仍然是结构化图谱查询。",
        "本文采用 LLM-as-a-Judge 作为主要自动评价方式": "本文采用 LLM-as-a-Judge 作为主要自动评价方式，评分维度和实验设计将在后文详述。ROUGE-L、chrF++ 和 BERTScore F1 等指标作为辅助参照，用以观察生成文本与参考文本的表层接近程度[20]。最终预案质量仍需结合人工审查判断。",
        "参考风电场应急预案编制及范例中对应急预案结构和编制内容的说明": "参考风电场应急预案编制及范例中对应急预案结构和编制内容的说明[21]，并结合项目收集的历史预案文本，本文将预案组织为事件特征、应急组织与职责、处置程序、处置措施、应急保障和附件六个一级章节，并逐级细化至二级和三级子项。每个章节条目通过三个字段配置其内容生成方式，以下以第六章附件为例展示模板结构，完整模板见附录C。",
        "图谱构建资料来自设备原理说明、典型故障案例、运维规程和历史预案文本": "图谱构建资料来自设备原理说明、典型故障案例、运维规程和历史预案文本，文件格式包括 Word、PDF 和 Markdown。不同资料对同一设备或故障的表述并不完全一致，缩写、同义词和上下文省略较常见。若直接从原文抽取实体和关系，容易形成重复节点和方向不一致的关系，这也是模式层需要先行确定的现实原因[22][23][24][25][26][27][28][29][30]。",
        "本文采用先定模式层、再整理数据的构建路线": "本文采用先定模式层、再整理数据的构建路线。模式层由人工依据领域经验和现行规程确定，原始资料的拆分、归类和同义归并由大语言模型辅助完成，结果再经人工复核后导入图数据库。模型只在预定义节点类型和关系范围内识别内容，这样既保留了整理效率，也避免了图谱结构随着原始资料写法波动[10][11]。图3-1展示了两种构建方式的差异。",
        "电气设备应急预案智能生成涉及知识组织、流程调度、接口聚合和前端展示等多个环节": "电气设备应急预案智能生成涉及知识组织、流程调度、接口聚合和前端展示等多个环节。为避免将全部逻辑耦合在单一工作流或单一服务中，本文按照职责边界将系统划分为数据与知识层、运行时编排层、接口封装层和前端交互层四个层次，各层之间通过标准化接口通信[31][19][32][1]。",
        "复杂生成任务既可以采用编程式框架，也可以采用可视化工作流平台": "复杂生成任务既可以采用编程式框架，也可以采用可视化工作流平台。LangChain、LangGraph 等框架允许开发者用代码定义节点、状态和执行逻辑，适合复杂控制，但开发调试成本较高。可视化平台便于快速配置模型调用和接口节点，而复杂分支、并发控制和结果持久化通常仍需外部脚本补充。本文选择 FastGPT 作为工作流平台，主要因为其支持结构化输出抽取和外部 HTTP 接口调用，能够较快把设备识别、故障匹配和章节生成配置为独立插件；章节并发控制和结果持久化则由外部 Python 流水线承担[19]。",
        "工程落地还需要补充模板版本管理、多人协同审查和知识回流机制": "工程落地还需要补充模板版本管理、多人协同审查和知识回流机制。这里的知识回流不仅包括实验结果整理，也包括把人工修订后的预案内容回写到模板或知识库。系统若与运维检修和应急指挥平台对接，生成结果才能进入可修订、可复用的业务流程；若进一步结合 GraphRAG 与智能代理等机制，后续还可以把知识召回、结果审查和修订反馈组织为更稳定的闭环流程[33]。",
    }

    for startswith, new_text in paragraph_replacements.items():
        set_paragraph_text(find_paragraph(root, startswith), new_text)

    # Convert any remaining Z-style citations before the reference section.
    ref_heading = find_paragraph(root, "参考文献")
    for p in body.iter(w("p")):
        if p is ref_heading:
            break
        text = paragraph_text(p)
        if "[Z" in text or "［Z" in text:
            set_paragraph_text(p, replace_z_citations(text))

    # Rebuild reference block from original body children.
    body_children = list(body)
    ref_idx = next(i for i, el in enumerate(body_children) if el.tag == w("p") and paragraph_text(el).strip() == "参考文献")
    ack_idx = next(i for i, el in enumerate(body_children) if i > ref_idx and el.tag == w("p") and paragraph_text(el).strip() == "致谢")
    template = next(el for el in body_children[ref_idx + 1 : ack_idx] if el.tag == w("p") and paragraph_text(el).strip())
    for el in list(body)[ref_idx + 1 : ack_idx]:
        body.remove(el)
    insert_at = ref_idx + 1
    for idx, ref_text in enumerate(FINAL_REFS, start=1):
        body.insert(insert_at, make_paragraph_like(template, f"[{idx}] {ref_text}"))
        insert_at += 1
    body.insert(insert_at, make_paragraph_like(template, ""))

    new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with ZipFile(src) as zin, ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = new_xml if info.filename == "word/document.xml" else zin.read(info.filename)
            zout.writestr(info, data)


if __name__ == "__main__":
    main()
