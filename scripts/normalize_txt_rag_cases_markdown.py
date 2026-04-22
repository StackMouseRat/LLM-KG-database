from __future__ import annotations

import re
from pathlib import Path


ROOT = Path("txt_rag_cases")

TITLE_OVERRIDES = {
    "220kV及以下变电站设备异常和故障典型案例分析_第一章_变压器.md": "220kV及以下变电站设备异常和故障典型案例分析 第一章 变压器",
    "220kV及以下变电站设备异常和故障典型案例分析_第二章_电流互感器.md": "220kV及以下变电站设备异常和故障典型案例分析 第二章 电流互感器",
    "220kV及以下变电站设备异常和故障典型案例分析_第三章_电压互感器.md": "220kV及以下变电站设备异常和故障典型案例分析 第三章 电压互感器",
    "220kV及以下变电站设备异常和故障典型案例分析_第四章_断路器.md": "220kV及以下变电站设备异常和故障典型案例分析 第四章 断路器",
    "光缆与光设备维护_5_3_典型案例分析_完整提取.md": "光缆与光设备维护 5.3 典型案例分析",
    "变电设备故障典型案例分析与预防措施_第二章_变压器运行异常及事故处理.md": "变电设备故障典型案例分析与预防措施 第二章 变压器运行异常及事故处理",
    "变电设备故障典型案例分析与预防措施_第三章_高压断路器.md": "变电设备故障典型案例分析与预防措施 第三章 高压断路器",
    "电网设备故障典型案例_第1章_变压器（高压电抗器）故障典型案例.md": "电网设备故障典型案例 第1章 变压器（高压电抗器）故障典型案例",
    "电网设备故障典型案例_第2章_断路器（不含开关柜）故障典型案例.md": "电网设备故障典型案例 第2章 断路器（不含开关柜）故障典型案例",
    "电网设备故障典型案例_第4章_互感器故障典型案例.md": "电网设备故障典型案例 第4章 互感器故障典型案例",
    "输变电设备典型故障_第一章.md": "输变电设备典型故障 第一章",
    "输变电设备典型故障_第二章.md": "输变电设备典型故障 第二章",
    "输电线路典型故障案例分析及预防_第一章_杆塔及基础.md": "输电线路典型故障案例分析及预防 第一章 杆塔及基础",
    "输电线路典型故障案例分析及预防_第二章_导线及地线.md": "输电线路典型故障案例分析及预防 第二章 导线及地线",
    "配电网典型故障案例分析_第一章_配电网架空线路设备故障分析典型案例.md": "配电网典型故障案例分析 第一章 配电网架空线路设备故障分析典型案例",
    "配电网典型故障案例分析_第二章_配电电缆线路设备故障分析典型案例.md": "配电网典型故障案例分析 第二章 配电电缆线路设备故障分析典型案例",
    "项目3_光缆线路故障处理与维护_完整提取.md": "项目3 光缆线路故障处理与维护",
}

HEADING_KEYWORDS = (
    "故障",
    "异常",
    "分析",
    "处理",
    "结论",
    "建议",
    "概况",
    "现场",
    "原因",
    "试验",
    "解体",
    "过程",
    "基本情况",
    "天气",
    "环境",
    "线路",
    "概述",
    "情况",
    "措施",
    "检查",
    "预防",
    "简介",
    "运行工况",
    "设备信息",
    "设备情况",
    "故障现象",
    "小结",
    "操作步骤",
    "教学目标",
    "实训环境",
    "学习总结题",
    "填空题",
    "简答题",
    "任务",
    "实践",
    "案例",
    "巡视",
    "检修",
    "监督",
)

EXACT_H2 = {"小结", "习题", "数据来源", "更新记录"}


def normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.strip())


def build_title(path: Path) -> str:
    return TITLE_OVERRIDES.get(path.name, path.stem.replace("_", " "))


def build_skip_set(path: Path, title: str) -> set[str]:
    skip = {title}
    stem_parts = [part for part in path.stem.split("_") if part and part != "完整提取"]
    skip.update(stem_parts)
    joined = " ".join(stem_parts)
    if joined:
        skip.add(joined)
    for size in (2, 3):
        for idx in range(len(stem_parts) - size + 1):
            skip.add(" ".join(stem_parts[idx : idx + size]))
    return {normalize_spaces(item) for item in skip if item.strip()}


def looks_like_page_number(text: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", text))


def is_false_code_fence(text: str) -> bool:
    return text in {"```", "```markdown"}


def strip_heading_markup(text: str) -> tuple[str, int]:
    stripped = text.lstrip()
    match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
    if match:
        return normalize_spaces(match.group(2)), len(match.group(1))
    stripped = re.sub(r"^>+\s*", "", stripped)
    return normalize_spaces(stripped), 0


def is_non_heading_caption(text: str) -> bool:
    return text.startswith("图") or text.startswith("表") or text.startswith("附图")


def classify_heading(text: str, original_level: int) -> int | None:
    if not text or is_non_heading_caption(text):
        return None

    if re.match(r"^（[0-9]+）.+$", text):
        return 0

    if re.match(r"^\d+[)）].+$", text):
        return 0

    if re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩].+$", text):
        return 0

    if text in EXACT_H2:
        return 2

    if re.match(r"^第[一二三四五六七八九十0-9]+章(?:\s+.+)?$", text):
        return 2

    if re.match(r"^第[一二三四五六七八九十0-9]+节(?:\s+.+)?$", text):
        return 2

    if re.match(r"^项目\s*\d+", text):
        return 2

    if re.match(r"^\d+(?:\.\d+){2,5}[ \u3000]+.+$", text):
        dots = text.split()[0].split(".")
        return min(len([item for item in dots if item]) + 1, 6)

    if re.match(r"^\d+\.\d+[ \u3000]+.+$", text):
        return 3

    if text.startswith("任务"):
        return 3

    if text.startswith("案例"):
        return 3

    if re.match(r"^[一二三四五六七八九十百千]+、.+$", text):
        return 3

    if re.match(r"^（[一二三四五六七八九十]+）.+$", text):
        return 4

    if re.match(r"^\d+[.．]?\s*[^0-9].*$", text):
        if len(text) <= 40 and any(keyword in text for keyword in HEADING_KEYWORDS):
            return 4

    if re.match(r"^[A-Za-z0-9一二三四五六七八九十]+[ \u3000]*[、.．][ \u3000]*.+$", text):
        if len(text) <= 40 and any(keyword in text for keyword in HEADING_KEYWORDS):
            return 4

    if original_level > 0 and not is_non_heading_caption(text):
        return original_level

    return None


def normalize_file(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    title = build_title(path)
    skip_set = build_skip_set(path, title)

    output: list[str] = [f"# {title}", ""]
    prev_blank = True

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = normalize_spaces(line)
        stripped = stripped.replace("```markdown", "").replace("```", "").strip()

        if not stripped:
            if not prev_blank:
                output.append("")
            prev_blank = True
            continue

        if is_false_code_fence(stripped):
            continue

        if looks_like_page_number(stripped):
            continue

        if stripped.startswith("<!--") and stripped.endswith("-->"):
            if not prev_blank:
                output.append("")
            output.append(stripped)
            output.append("")
            prev_blank = True
            continue

        text, original_level = strip_heading_markup(stripped)

        if text in skip_set:
            continue

        heading_level = classify_heading(text, original_level)
        if heading_level is not None:
            if heading_level > 0:
                if not prev_blank:
                    output.append("")
                output.append(f"{'#' * heading_level} {text}")
                output.append("")
                prev_blank = True
            else:
                output.append(text)
                prev_blank = False
            continue

        if stripped == "---":
            if not prev_blank:
                output.append("")
            output.append("---")
            output.append("")
            prev_blank = True
            continue

        output.append(line.strip())
        prev_blank = False

    normalized: list[str] = []
    last_blank = False
    for line in output:
        if line == "":
            if not last_blank:
                normalized.append(line)
            last_blank = True
        else:
            normalized.append(line)
            last_blank = False

    final_text = "\n".join(normalized).strip() + "\n"
    path.write_text(final_text, encoding="utf-8")


def main() -> None:
    for path in sorted(ROOT.glob("*.md")):
        if path.name == "README.md":
            continue
        normalize_file(path)
        print(f"normalized {path}")


if __name__ == "__main__":
    main()
