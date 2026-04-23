from __future__ import annotations

from pathlib import Path


DEVICE = "避雷器"
TEXT_DIR = Path("txt") / DEVICE

REFERENCE_DOCS = [
    "docs/project_changes/电力设备图谱建表与导入流程指南.md",
    "txt/输电线路/设备故障图谱通用工作流程.md",
    "txt_rag_cases_kb_imports/llmkg_surge_arrester/*.md",
]

MAJOR_SUBTYPES = {
    "外绝缘与表面放电故障": [
        "避雷器沿面闪络故障",
    ],
    "阀片与本体绝缘故障": [
        "避雷器阀片击穿故障",
    ],
    "防护功能异常故障": [
        "避雷器未有效动作故障",
    ],
    "安装结构与连接故障": [
        "避雷器脱落接地故障",
    ],
}

DETAILS = {
    "避雷器沿面闪络故障": {
        "故障原因": "主要由鸟粪污染、积雪冰棱、污秽潮湿、密封不良、交界面气隙、绝缘树脂厚度不均或外绝缘表面劣化等因素引起，导致避雷器表面或阀片侧面沿面绝缘强度下降并发生闪络、侧闪。",
        "故障现象": "表现为线路跳闸、重合闸成功或失败，避雷器外表存在放电烧蚀、侧闪痕迹、伞裙或护套开裂，现场可见鸟粪、积雪、放电点或沿面通道等外观特征。",
        "应对措施": "应立即开展故障巡视和放电点核查，隔离故障设备，清除污染、冰棱等外部诱因，必要时更换故障避雷器；同时对同厂家同批次设备加强排查，对鸟害、积雪和外绝缘状态实施专项治理。",
        "故障后果": "会造成线路闪络跳闸、重复故障、供电可靠性下降，并可能扩大为引线烧蚀、相邻设备损伤、批量缺陷暴露和恶劣天气下的连续停电风险。",
        "安全风险": "存在雨雪天气高空巡视、带电邻近作业、电弧灼伤、外绝缘反复放电、误判故障点以及夜间和山区环境下处置风险。",
        "应急资源": "需要巡视和检修人员、登塔工器具、绝缘防护用品、防鸟刺或防污治理材料、除冰清雪工具、红外测温与放电痕迹检查工具、备用避雷器和照明通信设备。",
    },
    "避雷器阀片击穿故障": {
        "故障原因": "主要由雷击过电压和较大雷电流冲击、阀片老化劣化、本体绝缘受潮或制造质量缺陷共同作用，导致氧化锌阀片发生贯穿性击穿或本体内部绝缘损坏。",
        "故障现象": "表现为雷雨天气下避雷器故障，阀片出现贯穿性击穿、明显放电通道、烧蚀痕迹或本体开裂，解体后可见内部阀片损伤和绝缘破坏。",
        "应对措施": "应及时停运并更换故障避雷器，复核雷电活动记录、接地状态和运行环境，对同区域同批次产品开展试验检查，并评估是否需要优化防雷配置。",
        "故障后果": "会削弱过电压保护能力，导致线路跳闸、设备损坏、停电范围扩大和后续雷击下重复故障风险增加。",
        "安全风险": "存在雷雨天气再次冲击、故障设备残余电荷、电弧灼伤、户外紧急检修以及误投入缺陷设备的风险。",
        "应急资源": "需要备用避雷器、接地与绝缘测试设备、雷电定位记录、解体检查工具、抢修工器具、防雷作业防护用品和调度协调资源。",
    },
    "避雷器未有效动作故障": {
        "故障原因": "主要由安装不规范、支架尺寸不合理、电极引出过长、计数器引线处理不当、施工验收不到位或防雷配置不匹配等因素引起，导致避雷器在过电压冲击下未能发挥预期保护作用。",
        "故障现象": "表现为故障区存在雷击或过电压冲击，但避雷器未有效动作，支架角铁、引线或电极端部可见烧蚀痕迹，线路仍发生双跳、保护动作或防护失效。",
        "应对措施": "应按厂家手册整改安装方式，优化支架、电极和计数器引线布置，核查同类设备安装一致性，并结合故障记录完善防雷配置和施工验收复核。",
        "故障后果": "会导致避雷器防护能力失效、线路雷击双跳或保护异常，削弱原有防雷措施效果，并可能形成批量安装隐患。",
        "安全风险": "存在安装缺陷长期潜伏、雷雨天气下重复故障、带缺陷运行、误判设备健康状态以及批量外溢风险。",
        "应急资源": "需要厂家安装手册、测量校核工具、整改配件、检测试验设备、施工验收资料、停电窗口和专业检修人员。",
    },
    "避雷器脱落接地故障": {
        "故障原因": "主要由连接结构设计不当、导电杆安装错误、固定螺母防松不足、支架振动后松脱以及施工和验收管理不到位引起，造成避雷器机械脱落并进一步形成接地故障。",
        "故障现象": "表现为避雷器从杆塔或支架上脱落，引线搭接在弓子线或导线上形成接地，现场可见固定部位松脱、导电杆连接异常和机械跌落痕迹。",
        "应对措施": "应立即隔离故障线路并回收脱落部件，按厂家要求重新安装和紧固连接结构，统一排查同批次设备连接方式，并强化施工与验收复核。",
        "故障后果": "会造成线路接地、母线异常、跳闸停电和设备机械损坏，严重时影响同塔或同走廊其他回路的安全运行。",
        "安全风险": "存在导体坠落、接地电位升高、高空坠物、误触带电部件和恶劣天气下抢修的高风险。",
        "应急资源": "需要备用避雷器及连接金具、双螺母防松件、登塔工器具、接地防护用品、巡视抢修人员和厂家安装资料。",
    },
}

LAYER_TO_NUM = {
    "故障原因": "第三",
    "故障现象": "第四",
    "应对措施": "第五",
    "故障后果": "第六",
    "安全风险": "第七",
    "应急资源": "第八",
}


def ensure_dir() -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)


def write_file(name: str, content: str) -> None:
    (TEXT_DIR / name).write_text(content.rstrip() + "\n", encoding="utf-8")


def build_first_level() -> str:
    majors = "\n".join(f"{idx}. {name}" for idx, name in enumerate(MAJOR_SUBTYPES, start=1))
    return f"""# {DEVICE}故障层级梳理（第一层级）

## 1. 目标
确定{DEVICE}故障图谱根节点下的一级故障大类，作为后续层级扩展基准。

## 2. 参考文档
{chr(10).join(f"- `{item}`" for item in REFERENCE_DOCS)}

## 3. 一级故障大类
{majors}
"""


def build_second_level() -> str:
    lines = [
        f"# {DEVICE}故障层级梳理（第二层级）",
        "",
        "## 1. 目标",
        f"确定 `{DEVICE} -> 一级故障大类 -> 二级故障小类` 的结构清单。",
        "",
        "## 2. 第二层级推荐结果",
    ]
    for major_idx, (major, subtypes) in enumerate(MAJOR_SUBTYPES.items(), start=1):
        lines.append(f"### 2.{major_idx} {major}")
        for subtype_idx, subtype in enumerate(subtypes, start=1):
            lines.append(f"{subtype_idx}. {subtype}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_detail_layer(layer_name: str) -> str:
    title_num = LAYER_TO_NUM[layer_name]
    lines = [
        f"# {DEVICE}故障层级梳理（{title_num}层级：{layer_name}）",
        "",
        "## 1. 目标",
        f"在第二层级基础上，为每个二级故障小类统一补充{title_num}层级 `{layer_name}` 节点。",
        "",
        "## 2. 命名规则",
        f"- 层级名称统一：`{layer_name}`",
        f"- 唯一节点名建议：`<二级故障小类>-{layer_name}`",
        "",
        f"## 3. 各二级小类的{layer_name}",
        "",
    ]
    section_idx = 1
    for major, subtypes in MAJOR_SUBTYPES.items():
        lines.append(f"### 3.{section_idx} {major}")
        lines.append("")
        for subtype in subtypes:
            lines.extend(
                [
                    f"#### {subtype}",
                    "",
                    f"- {title_num}层级节点：`{layer_name}`",
                    f"- 唯一节点名建议：`{subtype}-{layer_name}`",
                    f"- 描述/说明：{DETAILS[subtype][layer_name]}",
                    "",
                ]
            )
        section_idx += 1
    return "\n".join(lines).rstrip()


def build_summary() -> str:
    lines = [
        f"# {DEVICE}故障层级梳理（第一至第八层级汇总稿）",
        "",
        "## 1. 文档说明",
        "",
        f"本稿依据项目内现有避雷器案例资料，按《电力设备图谱建表与导入流程指南》和《设备故障图谱通用工作流程》整理出{DEVICE}故障图谱的第一至第八层级结构。",
        "",
        "当前已合并层级包括：",
        "",
        "1. 第一层级：一级故障大类",
        "2. 第二层级：二级故障小类",
        "3. 第三层级：故障原因",
        "4. 第四层级：故障现象",
        "5. 第五层级：应对措施",
        "6. 第六层级：故障后果",
        "7. 第七层级：安全风险",
        "8. 第八层级：应急资源",
        "",
        "## 2. 层级关系口径",
        "",
        f"- `{DEVICE} --发生--> 一级故障大类`",
        "- `一级故障大类 --包含--> 二级故障小类`",
        "- `二级故障小类 --起因于--> 故障原因`",
        "- `故障原因 --表现--> 故障现象`",
        "- `二级故障小类 --处置--> 应对措施`",
        "- `故障原因 --导致--> 故障后果`",
        "- `应对措施 --存在--> 安全风险`",
        "- `应对措施 --需要--> 应急资源`",
        "",
        "## 3. 第二层级结构",
        "",
        "```text",
        DEVICE,
    ]
    for major, subtypes in MAJOR_SUBTYPES.items():
        lines.append(f"├─ {major}")
        for subtype in subtypes:
            lines.append(f"│  └─ {subtype}")
    lines.extend(["```", "", "## 4. 二级故障小类明细", ""])

    for major, subtypes in MAJOR_SUBTYPES.items():
        lines.append(f"### {major}")
        lines.append("")
        for subtype in subtypes:
            lines.append(f"#### {subtype}")
            for layer_name in ["故障原因", "故障现象", "应对措施", "故障后果", "安全风险", "应急资源"]:
                lines.append(f"- {layer_name}：{DETAILS[subtype][layer_name]}")
            lines.append("")
    return "\n".join(lines).rstrip()


def main() -> None:
    ensure_dir()
    write_file(f"{DEVICE}故障层级梳理_第一层级.md", build_first_level())
    write_file(f"{DEVICE}故障层级梳理_第二层级.md", build_second_level())
    for layer_name in ["故障原因", "故障现象", "应对措施", "故障后果", "安全风险", "应急资源"]:
        write_file(
            f"{DEVICE}故障层级梳理_{LAYER_TO_NUM[layer_name]}层级_{layer_name}.md",
            build_detail_layer(layer_name),
        )
    write_file(f"{DEVICE}故障层级梳理_第一至第八层级汇总稿.md", build_summary())

    print(f"已生成 {DEVICE} 层级文件目录：{TEXT_DIR}")
    print("二级故障分类如下：")
    for major, subtypes in MAJOR_SUBTYPES.items():
        print(f"[{major}]")
        for subtype in subtypes:
            print(f"- {subtype}")


if __name__ == "__main__":
    main()
