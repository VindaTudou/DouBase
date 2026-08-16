import pytest
from doubase.chunker.heading_splitter import split_by_headings, HeadingSection


FIXTURE = """---
title: 测试
---

# 智能体

智能体是一个能够自主感知环境的系统。

它的核心循环是 观察-思考-行动。

## 核心组件

### 感知模块

感知模块负责接收环境信息。包括传感器数据、用户输入等。

### 规划模块

规划模块是智能体的决策中心。主要有 ReAct 和 Plan-and-Solve 两种范式。

## 常见框架

- LangChain
- AutoGPT
"""


def test_split_by_headings_count():
    sections = split_by_headings(FIXTURE)
    assert len(sections) >= 5


def test_split_by_headings_levels():
    sections = split_by_headings(FIXTURE)
    headings = [(s.heading_level, s.heading_text) for s in sections if s.heading_level > 0]
    assert (1, "智能体") in headings
    assert (2, "核心组件") in headings
    assert (3, "感知模块") in headings
    assert (3, "规划模块") in headings
    assert (2, "常见框架") in headings


def test_heading_path_tracks_hierarchy():
    sections = split_by_headings(FIXTURE)
    for s in sections:
        if s.heading_text == "感知模块":
            assert "智能体" in s.heading_path
            assert "核心组件" in s.heading_path
        if s.heading_text == "规划模块":
            assert "智能体" in s.heading_path
            assert "核心组件" in s.heading_path


def test_body_text_not_empty():
    sections = split_by_headings(FIXTURE)
    for s in sections:
        if s.heading_text == "智能体":
            assert "自主感知环境" in s.body_text
        if s.heading_text == "常见框架":
            assert "LangChain" in s.body_text


def test_no_headings_returns_single_section():
    text = "这是一段没有标题的纯文本。\n包含多行内容。"
    sections = split_by_headings(text)
    assert len(sections) == 1
    assert sections[0].heading_level == 0
    assert sections[0].heading_path == []
    assert "纯文本" in sections[0].body_text


def test_start_line_tracking():
    text = "preamble\n# Title\nbody line 1\nbody line 2\n## Sub\nmore body"
    sections = split_by_headings(text)
    titles = {s.heading_text: s.start_line for s in sections if s.heading_text}
    assert titles.get("Title") == 1


from doubase.chunker.chunker import Chunker, chunk_by_headings


def test_chunk_by_headings_short_sections():
    """短段落 -> 每个标题一个 chunk"""
    chunker = Chunker({"chunk_size": 512, "chunk_overlap": 64})
    text = "# Title\nShort body.\n\n## Sub\nAlso short."
    chunks = chunk_by_headings(text, "/tmp/test.md", "hash123", chunker)
    assert len(chunks) == 2
    assert chunks[0].metadata["strategy"] == "heading"
    assert chunks[0].metadata["heading_text"] == "Title"
    assert chunks[0].metadata["heading_path"] == ["Title"]
    assert chunks[1].metadata["heading_text"] == "Sub"
    assert chunks[1].metadata["heading_path"] == ["Title", "Sub"]


def test_chunk_by_headings_long_section_falls_back_to_sliding_window():
    """长段落 -> 滑动窗口兜底"""
    chunker = Chunker({"chunk_size": 20, "chunk_overlap": 5})
    text = "# Test\n" + "word " * 100
    chunks = chunk_by_headings(text, "/tmp/test.md", "hash456", chunker)
    assert len(chunks) > 1
    for c in chunks:
        assert c.metadata["strategy"] in ("heading", "sliding_window")
        assert c.metadata["heading_text"] == "Test"


def test_chunk_by_headings_global_index():
    """全局 chunk_index 连续编号"""
    chunker = Chunker({"chunk_size": 20, "chunk_overlap": 5})
    text = "# A\nshort\n\n# B\n" + "word " * 100
    chunks = chunk_by_headings(text, "/tmp/test.md", "hash789", chunker)
    assert chunks[0].chunk_index == 0
    assert chunks[-1].chunk_index == len(chunks) - 1


def test_chunk_text_includes_heading_path():
    """短段落：chunk 文本前置完整标题路径（标题词可被检索到）"""
    chunker = Chunker({"chunk_size": 512, "chunk_overlap": 64})
    text = "# 智能体\n\n正文内容A\n\n## 感知模块\n\n正文内容B"
    chunks = chunk_by_headings(text, "/tmp/test.md", "h1", chunker)
    assert chunks[0].text.startswith("# 智能体\n正文内容A")
    # 子标题 chunk 要带完整路径（大标题 + 小标题）
    assert chunks[1].text.startswith("# 智能体\n## 感知模块\n正文内容B")


def test_sliding_window_subchunks_each_carry_heading():
    """长段落滑动窗口：每个子 chunk 都带同一标题前缀，而非只有第一个"""
    chunker = Chunker({"chunk_size": 20, "chunk_overlap": 5})
    text = "# 长标题\n" + "word " * 100
    chunks = chunk_by_headings(text, "/tmp/test.md", "h2", chunker)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith("# 长标题\n")
        assert c.metadata["strategy"] in ("heading", "sliding_window")


def test_preamble_chunk_has_no_heading_prefix():
    """无标题 preamble：chunk 文本不带标题前缀"""
    chunker = Chunker({"chunk_size": 512, "chunk_overlap": 64})
    text = "开头没标题的段落\n\n# 之后才有标题\n正文"
    chunks = chunk_by_headings(text, "/tmp/test.md", "h3", chunker)
    assert chunks[0].text == "开头没标题的段落"
