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
