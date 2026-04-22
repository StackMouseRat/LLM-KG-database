from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


SOURCE_DIR = Path("txt_rag_cases")
OUTPUT_DIR = Path("txt_rag_cases_case_corpus")
INDEX_FILE = OUTPUT_DIR / "index.tsv"
README_FILE = OUTPUT_DIR / "README.md"


@dataclass(frozen=True)
class SourceRule:
    include: bool = True
    exclude_reason: str = ""
    start_after_heading: str | None = None
    start_after_line: str | None = None
    heading_levels: tuple[int, ...] = ()
    heading_patterns: tuple[str, ...] = ()
    plain_patterns: tuple[str, ...] = ()


RULES: dict[str, SourceRule] = {
    "README.md": SourceRule(
        include=False,
        exclude_reason="索引说明文档，不属于案例正文。",
    ),
    "项目3_光缆线路故障处理与维护_完整提取.md": SourceRule(
        include=False,
        exclude_reason="教程/手册型内容，排除出案例语料。",
    ),
    "输变电设备典型故障_第二章.md": SourceRule(
        include=False,
        exclude_reason="原文结构损坏严重，当前版本不适合稳定抽取单案例。",
    ),
    "220kV及以下变电站设备异常和故障典型案例分析_第一章_变压器.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^[一二三四五六七八九十]+、.+$",),
    ),
    "220kV及以下变电站设备异常和故障典型案例分析_第二章_电流互感器.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^[一二三四五六七八九十]+、.+$",),
    ),
    "220kV及以下变电站设备异常和故障典型案例分析_第三章_电压互感器.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^[一二三四五六七八九十]+、.+$",),
    ),
    "220kV及以下变电站设备异常和故障典型案例分析_第四章_断路器.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^[一二三四五六七八九十]+、.+$",),
    ),
    "光缆与光设备维护_5_3_典型案例分析_完整提取.md": SourceRule(
        start_after_heading=r"^5\.3 典型案例分析$",
        heading_levels=(3, 4),
        heading_patterns=(r"^\d+[.．]\s+.*(业务中断|故障|异常)$",),
    ),
    "变电设备故障典型案例分析与预防措施_第二章_变压器运行异常及事故处理.md": SourceRule(
        start_after_heading=r"^第四节.*实例$",
        heading_levels=(3,),
        heading_patterns=(r"^[一二三四五六七八九十]+、.+(故障|异常)$",),
    ),
    "变电设备故障典型案例分析与预防措施_第三章_高压断路器.md": SourceRule(
        include=False,
        exclude_reason="页序错位且手册内容混入案例段，当前版本保守排除。",
    ),
    "电网设备故障典型案例_第1章_变压器（高压电抗器）故障典型案例.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^\d+\.\d+\s+.+$",),
    ),
    "电网设备故障典型案例_第2章_断路器（不含开关柜）故障典型案例.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^\d+\.\d+\s+.+$",),
    ),
    "电网设备故障典型案例_第4章_互感器故障典型案例.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^\d+\.\d+\s+.+$",),
    ),
    "输变电设备典型故障_第一章.md": SourceRule(
        start_after_heading=r"^第二节 .*典型案例$",
        heading_levels=(3,),
        heading_patterns=(r"^案例[一二三四五六七八九十]+.+$",),
    ),
    "输电线路典型故障案例分析及预防_第一章_杆塔及基础.md": SourceRule(
        start_after_heading=r"^第一节 .*故障$",
        heading_levels=(3, 4),
        heading_patterns=(
            r"^【?[一二三四五六七八九十]+[、，].*故障】?$",
            r"^[（(][一二三四五六七八九十]+[)）].*故障$",
        ),
    ),
    "输电线路典型故障案例分析及预防_第二章_导线及地线.md": SourceRule(
        heading_levels=(3, 4),
        heading_patterns=(
            r"^[一二三四五六七八九十]+、.*故障$",
            r"^[（(][一二三四五六七八九十]+[)）].*故障$",
        ),
    ),
    "配电网典型故障案例分析_第一章_配电网架空线路设备故障分析典型案例.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^案例[一二三四五六七八九十]+.+$",),
    ),
    "配电网典型故障案例分析_第二章_配电电缆线路设备故障分析典型案例.md": SourceRule(
        heading_levels=(3,),
        heading_patterns=(r"^案例[一二三四五六七八九十]+.+$",),
    ),
}


def compile_patterns(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
    return [re.compile(pattern) for pattern in patterns]


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def parse_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        headings.append((idx, len(match.group(1)), match.group(2).strip()))
    return headings


def first_heading_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return fallback


def find_start_offset(
    lines: list[str],
    headings: list[tuple[int, int, str]],
    rule: SourceRule,
) -> int:
    if rule.start_after_heading:
        matcher = re.compile(rule.start_after_heading)
        for idx, _, text in headings:
            if matcher.search(text):
                return idx + 1
    if rule.start_after_line:
        matcher = re.compile(rule.start_after_line)
        for idx, line in enumerate(lines):
            if matcher.search(line.strip()):
                return idx + 1
    return 0


def collect_case_starts(
    lines: list[str],
    headings: list[tuple[int, int, str]],
    start_offset: int,
    rule: SourceRule,
) -> list[tuple[int, str, bool]]:
    candidates: dict[int, tuple[int, str, bool]] = {}
    heading_patterns = compile_patterns(rule.heading_patterns)
    plain_patterns = compile_patterns(rule.plain_patterns)

    for idx, level, text in headings:
        if idx < start_offset:
            continue
        if rule.heading_levels and level not in rule.heading_levels:
            continue
        if not any(pattern.search(text) for pattern in heading_patterns):
            continue
        candidates[idx] = (idx, text, True)

    for idx, raw_line in enumerate(lines[start_offset:], start=start_offset):
        text = raw_line.strip()
        if not text:
            continue
        if HEADING_RE.match(text):
            continue
        if not any(pattern.search(text) for pattern in plain_patterns):
            continue
        candidates.setdefault(idx, (idx, text, False))

    return [candidates[idx] for idx in sorted(candidates)]


def clean_title(text: str) -> str:
    text = text.strip()
    text = text.strip("【】")
    return re.sub(r"\s+", " ", text)


def nearest_section_heading(
    headings: list[tuple[int, int, str]],
    case_start: int,
) -> str:
    for idx, level, text in reversed(headings):
        if idx >= case_start:
            continue
        if level != 2:
            continue
        return text
    return ""


def strip_outer_blank_lines(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def build_document(
    case_id: str,
    case_title: str,
    source_file: str,
    source_title: str,
    section_title: str,
    body_lines: list[str],
) -> str:
    body = "\n".join(strip_outer_blank_lines(body_lines)).strip()
    if body:
        body += "\n"
    frontmatter = [
        "---",
        f"case_id: {case_id}",
        f"doc_kind: case",
        f"source_file: {source_file}",
        f"source_title: {source_title}",
    ]
    if section_title:
        frontmatter.append(f"source_section: {section_title}")
    frontmatter.extend(["---", "", f"# {case_title}", ""])
    text = "\n".join(frontmatter)
    if body:
        return text + "\n" + body
    return text + "\n"


def write_readme(
    generated_count: int,
    included_sources: dict[str, int],
    excluded_sources: dict[str, str],
) -> None:
    lines = [
        "# 案例专用语料",
        "",
        "本目录由 `scripts/build_case_only_rag_corpus.py` 自动生成。",
        "",
        f"- 案例文件数：{generated_count}",
        f"- 纳入源文件数：{len(included_sources)}",
        f"- 排除源文件数：{len(excluded_sources)}",
        "",
        "## 纳入源文件",
        "",
    ]
    for source_file, case_count in sorted(included_sources.items()):
        lines.append(f"- `{source_file}`: {case_count} 个案例")
    lines.extend(["", "## 排除源文件", ""])
    for source_file, reason in sorted(excluded_sources.items()):
        lines.append(f"- `{source_file}`: {reason}")
    README_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    rows = ["case_id\toutput_file\tsource_file\tsource_section\tcase_title"]
    included_sources: dict[str, int] = {}
    excluded_sources: dict[str, str] = {}

    case_counter = 0
    for path in sorted(SOURCE_DIR.glob("*.md")):
        rule = RULES.get(
            path.name,
            SourceRule(include=False, exclude_reason="未配置抽取规则，默认排除。"),
        )
        if not rule.include:
            excluded_sources[path.name] = rule.exclude_reason
            continue

        lines = path.read_text(encoding="utf-8").splitlines()
        headings = parse_headings(lines)
        source_title = first_heading_title(lines, path.stem)
        start_offset = find_start_offset(lines, headings, rule)
        starts = collect_case_starts(lines, headings, start_offset, rule)
        if not starts:
            excluded_sources[path.name] = "未识别到稳定案例边界，已保守排除。"
            continue

        case_count = 0
        for index, (line_idx, raw_title, is_heading) in enumerate(starts):
            end_idx = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
            body_start = line_idx + 1
            if not is_heading:
                body_start = line_idx + 1
            case_body = lines[body_start:end_idx]
            if not "".join(case_body).strip():
                continue

            case_counter += 1
            case_count += 1
            case_id = f"case_{case_counter:04d}"
            case_title = clean_title(raw_title)
            section_title = nearest_section_heading(headings, line_idx)
            output_name = f"{case_id}.md"
            document = build_document(
                case_id=case_id,
                case_title=case_title,
                source_file=path.name,
                source_title=source_title,
                section_title=section_title,
                body_lines=case_body,
            )
            (OUTPUT_DIR / output_name).write_text(document, encoding="utf-8")
            rows.append(
                "\t".join(
                    [
                        case_id,
                        output_name,
                        path.name,
                        section_title,
                        case_title,
                    ]
                )
            )

        if case_count:
            included_sources[path.name] = case_count
        else:
            excluded_sources[path.name] = "未识别到可用案例内容。"

    INDEX_FILE.write_text("\n".join(rows) + "\n", encoding="utf-8")
    write_readme(
        generated_count=case_counter,
        included_sources=included_sources,
        excluded_sources=excluded_sources,
    )
    print(f"generated {case_counter} case files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
