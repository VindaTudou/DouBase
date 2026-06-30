"""按 Markdown # 标题切分文档。"""

import re
from dataclasses import dataclass


# 匹配行首的 # 标题（1-6 级）
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class HeadingSection:
    """一个标题及其正文段落。

    Attributes:
        heading_level: 标题级别 0-6（0 表示无标题的 preamble）。
        heading_text: 标题文本（不含 # 号）。
        heading_path: 从根到当前标题的完整路径。
        body_text: 段落正文（不含标题行本身）。
        start_line: 在原文件中的起始行号（0-indexed）。
    """

    heading_level: int
    heading_text: str
    heading_path: list[str]
    body_text: str
    start_line: int


def split_by_headings(text: str) -> list[HeadingSection]:
    """按 Markdown # 标题将文本切分为段落。

    第一个 # 标题之前的内容视为 preamble（heading_level=0）。

    Args:
        text: Markdown 文档全文。

    Returns:
        按文档顺序排列的段落列表。
    """
    matches = list(HEADING_RE.finditer(text))

    if not matches:
        return [HeadingSection(
            heading_level=0,
            heading_text="",
            heading_path=[],
            body_text=text.strip(),
            start_line=0,
        )]

    sections = []
    heading_stack = []

    # 第一个标题出现之前的 preamble
    first_match = matches[0]
    if first_match.start() > 0:
        preamble = text[:first_match.start()].strip()
        if preamble:
            sections.append(HeadingSection(
                heading_level=0,
                heading_text="",
                heading_path=[],
                body_text=preamble,
                start_line=0,
            ))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading_text = m.group(2).strip()

        # 维护标题路径栈
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading_text))
        heading_path = [h[1] for h in heading_stack]

        # 正文范围: 当前标题之后 → 下一个标题之前（或文末）
        body_start = m.end()
        if i + 1 < len(matches):
            body_end = matches[i + 1].start()
        else:
            body_end = len(text)

        body_text = text[body_start:body_end].strip()
        start_line = text[:m.start()].count("\n")

        sections.append(HeadingSection(
            heading_level=level,
            heading_text=heading_text,
            heading_path=heading_path,
            body_text=body_text,
            start_line=start_line,
        ))

    return sections
