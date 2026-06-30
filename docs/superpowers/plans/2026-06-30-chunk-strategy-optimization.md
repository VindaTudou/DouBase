# Chunk 策略优化 — 实现计划

> **面向执行者：** 请使用 superpowers:subagent-driven-development（推荐）按任务逐个实现。步骤使用复选框跟踪。

**目标：** 将现有滑动窗口分块替换为三级分块策略（按 `#` 标题切分 → 滑动窗口兜底 → LLM 保守合并），提升 RAG 检索的语义完整性。

**架构：** `doubase/chunker/` 下新增 `heading_splitter.py` 和 `semantic_merger.py`，`pipeline.py` 中替换 `chunk_text()` 调用为新的三级流程。`Chunk` 数据类新增 `metadata: dict` 字段。Ask 流程无变更。

**技术栈：** Python >=3.11, tiktoken, rich

## 全局约束

- Python >=3.11（`/opt/homebrew/bin/python3.11`）
- 现有 53 个测试不能破坏
- `.md` 文件走标题切分；`.docx`、`.pdf` 保持原有滑动窗口
- LLM 合并默认执行，仅同标题下 chunk 数 > 1 时调 LLM
- LLM 合并 prompt 必须简短（单 token 回复 MERGE / KEEP_SEPARATE）

---

### 任务 1: Chunk 数据结构更新

**文件:**
- 修改: `doubase/chunker/chunker.py` — Chunk 数据类添加 metadata 字段

**接口:**
- 消耗: 无
- 产出: `Chunk(text, source_path, chunk_index, content_hash, metadata)` — metadata 默认 `{}`

- [ ] **步骤 1: 修改 Chunk 数据类**

读取 `doubase/chunker/chunker.py`，替换 Chunk 定义为：

```python
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """单个文本块及其元数据，可直接用于向量化。

    Attributes:
        text: chunk 文本内容。
        source_path: 原始文件的绝对路径。
        chunk_index: 文档内的从零开始的索引。
        content_hash: 源文件内容的 SHA256 哈希（用于去重）。
        metadata: 分块元数据（heading_path, heading_text, strategy 等）。
    """

    text: str
    source_path: str
    chunk_index: int
    content_hash: str
    metadata: dict = field(default_factory=dict)
```

- [ ] **步骤 2: 运行现有测试确认无回归**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 53 passed（metadata 默认值 `{}` 不影响现有调用）

- [ ] **步骤 3: 提交**

```bash
git add doubase/chunker/chunker.py
git commit -m "feat: add metadata field to Chunk dataclass"
```

---

### 任务 2: 标题切分器 (HeadingSplitter)

**文件:**
- 创建: `doubase/chunker/heading_splitter.py`
- 修改: `doubase/chunker/__init__.py` — 导出新函数
- 创建: `tests/test_heading_splitter.py`

**接口:**
- 消耗: 纯文本字符串
- 产出: `split_by_headings(text: str) -> list[HeadingSection]`；`HeadingSection(heading_level, heading_text, heading_path, body_text, start_line)` 数据类

- [ ] **步骤 1: 编写测试**

创建 `tests/test_heading_splitter.py`:

```python
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
    # Preamble (frontmatter removed outside)+ 智能体 + 核心组件 + 感知模块 + 规划模块 + 常见框架
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
    # "Title" should start at line 1 (0-indexed)
    assert titles.get("Title") == 1
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_heading_splitter.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/chunker/heading_splitter.py`:

```python
"""按 Markdown # 标题切分文档。"""

import re
from dataclasses import dataclass, field


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
    # 找到所有标题行位置
    matches = list(HEADING_RE.finditer(text))

    if not matches:
        # 没有任何标题 → 全文作为一个段落
        return [HeadingSection(
            heading_level=0,
            heading_text="",
            heading_path=[],
            body_text=text.strip(),
            start_line=0,
        )]

    sections = []
    heading_stack = []  # 维护标题层级路径

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
        level = len(m.group(1))  # # 的数量 = 标题级别
        heading_text = m.group(2).strip()

        # 维护标题路径栈
        # 弹出所有级别 >= 当前级别的标题
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

        # 计算起始行号
        start_line = text[:m.start()].count("\n")

        sections.append(HeadingSection(
            heading_level=level,
            heading_text=heading_text,
            heading_path=heading_path,
            body_text=body_text,
            start_line=start_line,
        ))

    return sections
```

- [ ] **步骤 4: 更新 __init__.py**

修改 `doubase/chunker/__init__.py`:

```python
"""文本分块器 — 将文档拆分为可向量化的片段。"""

from doubase.chunker.heading_splitter import split_by_headings, HeadingSection
```

- [ ] **步骤 5: 运行测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_heading_splitter.py -v`
预期: 6 PASS

- [ ] **步骤 6: 提交**

```bash
git add doubase/chunker/heading_splitter.py doubase/chunker/__init__.py tests/test_heading_splitter.py
git commit -m "feat: add heading-based markdown splitter"
```

---

### 任务 3: Stage 2 集成 — 标题切分 + 滑动窗口兜底

**文件:**
- 修改: `doubase/chunker/chunker.py` — 新增 `chunk_by_headings()` 方法
- 修改: `doubase/chunker/__init__.py` — 导出新方法

**接口:**
- 消耗: `split_by_headings()`, 现有 `Chunker`
- 产出: `chunk_by_headings(text, source_path, content_hash, chunker) -> list[Chunk]` — 标题切分 + 滑动窗口兜底

- [ ] **步骤 1: 在 Chunker 类中添加 chunk_by_headings 静态方法**

在 `doubase/chunker/chunker.py` 中 `Chunker` 类定义之后添加：

```python
def chunk_by_headings(
    text: str,
    source_path: str,
    content_hash: str,
    chunker: "Chunker",
) -> list[Chunk]:
    """Stage 1+2: 按 # 标题切分 → 长段落滑动窗口兜底。

    仅对 .md 文件调用此函数。.docx/.pdf 继续使用 chunker.chunk_text()。
    """
    from doubase.chunker.heading_splitter import split_by_headings

    sections = split_by_headings(text)
    all_chunks = []

    for section in sections:
        tokens = chunker._encode(section.body_text)
        if len(tokens) <= chunker.chunk_size:
            # 短段落 → 单个 chunk
            all_chunks.append(Chunk(
                text=section.body_text,
                source_path=source_path,
                chunk_index=0,  # 后续全局编号修正
                content_hash=content_hash,
                metadata={
                    "heading_path": section.heading_path,
                    "heading_text": section.heading_text,
                    "strategy": "heading",
                },
            ))
        else:
            # 长段落 → 滑动窗口切分
            sub_text = section.body_text
            sub_tokens = chunker._encode(sub_text)
            step = max(1, chunker.chunk_size - chunker.chunk_overlap)

            for i in range(0, len(sub_tokens), step):
                chunk_token_ids = sub_tokens[i:i + chunker.chunk_size]
                if chunker._encoding is not None:
                    chunk_text = chunker._decode(chunk_token_ids)
                else:
                    char_ratio = len(sub_text) / max(1, len(sub_tokens))
                    start_char = int(i * char_ratio)
                    end_char = int((i + chunker.chunk_size) * char_ratio)
                    chunk_text = sub_text[start_char:end_char]

                if chunk_text.strip():
                    all_chunks.append(Chunk(
                        text=chunk_text.strip(),
                        source_path=source_path,
                        chunk_index=0,  # 后续全局编号修正
                        content_hash=content_hash,
                        metadata={
                            "heading_path": section.heading_path,
                            "heading_text": section.heading_text,
                            "strategy": "sliding_window",
                        },
                    ))

    # 全局编号
    for i, c in enumerate(all_chunks):
        c.chunk_index = i

    return all_chunks
```

- [ ] **步骤 2: 更新 __init__.py**

修改 `doubase/chunker/__init__.py` 追加导出：

```python
from doubase.chunker.chunker import Chunk, Chunker, chunk_by_headings
```

- [ ] **步骤 3: 编写 Stage 2 集成测试**

追加到 `tests/test_heading_splitter.py`:

```python
from doubase.chunker.chunker import Chunker, chunk_by_headings


def test_chunk_by_headings_short_sections():
    """短段落 → 每个标题一个 chunk"""
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
    """长段落 → 滑动窗口兜底"""
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
```

- [ ] **步骤 4: 运行测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_heading_splitter.py -v`
预期: 9 PASS

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 62 passed

- [ ] **步骤 5: 提交**

```bash
git add doubase/chunker/chunker.py doubase/chunker/__init__.py tests/test_heading_splitter.py
git commit -m "feat: integrate heading split + sliding window fallback (Stage 1+2)"
```

---

### 任务 4: LLM 语义合并器 (SemanticMerger)

**文件:**
- 创建: `doubase/chunker/semantic_merger.py`
- 创建: `tests/test_semantic_merger.py`

**接口:**
- 消耗: `list[Chunk]`, `BaseLLM`
- 产出: `merge_semantically(chunks: list[Chunk], llm: BaseLLM) -> list[Chunk]` — 合并同标题下语义相关的相邻 chunk

- [ ] **步骤 1: 编写测试**

创建 `tests/test_semantic_merger.py`:

```python
from unittest.mock import MagicMock
from doubase.chunker.chunker import Chunk
from doubase.chunker.semantic_merger import merge_semantically


def _make_chunk(text, heading_text, strategy, chunk_idx):
    return Chunk(
        text=text,
        source_path="/tmp/test.md",
        chunk_index=chunk_idx,
        content_hash="abc",
        metadata={"heading_text": heading_text, "strategy": strategy},
    )


def test_single_chunk_per_heading_skips_llm():
    """同标题下只有 1 个 chunk → 不调 LLM，直接返回"""
    chunks = [
        _make_chunk("段落 A", "标题1", "heading", 0),
        _make_chunk("段落 B", "标题2", "heading", 1),
    ]
    mock_llm = MagicMock()
    result = merge_semantically(chunks, mock_llm)
    mock_llm.chat.assert_not_called()
    assert len(result) == 2


def test_multiple_chunks_same_heading_calls_llm():
    """同标题下 > 1 chunk → 调 LLM"""
    chunks = [
        _make_chunk("RDB 简介第一部分...", "RDB", "sliding_window", 0),
        _make_chunk("RDB 简介第二部分...", "RDB", "sliding_window", 1),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "MERGE"
    result = merge_semantically(chunks, mock_llm)
    mock_llm.chat.assert_called_once()
    assert len(result) == 1
    assert "RDB 简介第一部分" in result[0].text
    assert "RDB 简介第二部分" in result[0].text
    assert result[0].metadata["strategy"] == "merged"


def test_llm_says_keep_separate():
    """LLM 判断不相关 → 保持独立"""
    chunks = [
        _make_chunk("完全不相关的内容 A", "标题", "sliding_window", 0),
        _make_chunk("完全不相关的内容 B", "标题", "sliding_window", 1),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "KEEP_SEPARATE"
    result = merge_semantically(chunks, mock_llm)
    assert len(result) == 2


def test_three_chunks_merge_chain():
    """三个 chunk: A+B 合并, B+C 不合并 → 返回 2 个"""
    chunks = [
        _make_chunk("相关 A", "标题", "sliding_window", 0),
        _make_chunk("相关 B", "标题", "sliding_window", 1),
        _make_chunk("无关 C", "标题", "sliding_window", 2),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ["MERGE", "KEEP_SEPARATE"]
    result = merge_semantically(chunks, mock_llm)
    assert mock_llm.chat.call_count == 2
    assert len(result) == 2
    assert "相关 A" in result[0].text and "相关 B" in result[0].text
    assert "无关 C" in result[1].text


def test_mixed_headings():
    """混合多标题: 仅同标题下的才考虑合并"""
    chunks = [
        _make_chunk("A1", "标题A", "sliding_window", 0),
        _make_chunk("A2", "标题A", "sliding_window", 1),
        _make_chunk("B1", "标题B", "heading", 2),
        _make_chunk("C1", "标题C", "sliding_window", 3),
        _make_chunk("C2", "标题C", "sliding_window", 4),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ["MERGE", "MERGE"]
    result = merge_semantically(chunks, mock_llm)
    # A1+A2 合并, B1 独立, C1+C2 合并 → 3 个
    assert len(result) == 3
    # B1 保持独立
    b_chunks = [c for c in result if c.metadata["heading_text"] == "标题B"]
    assert len(b_chunks) == 1
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_semantic_merger.py -v`
预期: FAIL

- [ ] **步骤 3: 编写实现**

创建 `doubase/chunker/semantic_merger.py`:

```python
"""LLM 语义合并 — 合并同标题下语义相关的相邻 chunk。"""

from doubase.chunker.chunker import Chunk
from doubase.generation.base import BaseLLM

MERGE_PROMPT = """以下两段文本来自同一篇文档的相邻段落。判断它们是否应该合并为一个语义单元。

合并标准：两段文本讨论同一主题的连续内容，合并后阅读流畅、逻辑连贯。
不合并标准：两段文本讨论不同方面、不同案例，各自独立存在更有意义。

文本 1:
{text1}

文本 2:
{text2}

请仅回复一个词：MERGE 或 KEEP_SEPARATE。"""


def merge_semantically(chunks: list[Chunk], llm: BaseLLM) -> list[Chunk]:
    """LLM 保守合并：仅合并同标题下语义相关的相邻 chunk。

    Args:
        chunks: Stage 1+2 产出的全部 chunk（已按 chunk_index 排序）。
        llm: LLM 实例（用于判断语义相关性）。

    Returns:
        合并后的 chunk 列表。
    """
    if not chunks:
        return []

    # 按 heading_text 分组（保持组内原有顺序）
    groups: dict[str, list[int]] = {}  # heading_text -> chunk indices
    for i, c in enumerate(chunks):
        heading = c.metadata.get("heading_text", "")
        if heading not in groups:
            groups[heading] = []
        groups[heading].append(i)

    # 标记哪些 index 需要移除（被合并到前一个）
    to_remove: set[int] = set()

    for heading, indices in groups.items():
        if len(indices) <= 1:
            continue  # 同标题下只有 1 个 chunk → 无需合并

        # 逐个判断相邻 pair
        for j in range(len(indices) - 1):
            idx_a = indices[j]
            idx_b = indices[j + 1]

            if idx_a in to_remove:
                # 上一个已经被合并了 → 跳过
                continue

            # 调 LLM 判断
            prompt = MERGE_PROMPT.format(
                text1=chunks[idx_a].text,
                text2=chunks[idx_b].text,
            )
            try:
                reply = llm.chat([{"role": "user", "content": prompt}]).strip().upper()
            except Exception:
                # LLM 调用失败 → 保守行为：不合并
                continue

            if "MERGE" in reply:
                # 合并: 将 idx_b 的内容追加到 idx_a, 标记 idx_b 待移除
                chunks[idx_a].text = chunks[idx_a].text + "\n\n" + chunks[idx_b].text
                chunks[idx_a].metadata["strategy"] = "merged"
                to_remove.add(idx_b)

    # 移除被合并的 chunk
    result = [c for i, c in enumerate(chunks) if i not in to_remove]

    # 重新编号
    for i, c in enumerate(result):
        c.chunk_index = i

    return result
```

- [ ] **步骤 4: 更新 __init__.py**

修改 `doubase/chunker/__init__.py` 追加：

```python
from doubase.chunker.semantic_merger import merge_semantically
```

- [ ] **步骤 5: 运行测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_semantic_merger.py -v`
预期: 6 PASS

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 68 passed

- [ ] **步骤 6: 提交**

```bash
git add doubase/chunker/semantic_merger.py doubase/chunker/__init__.py tests/test_semantic_merger.py
git commit -m "feat: add LLM semantic merger for same-heading chunks"
```

---

### 任务 5: Pipeline 集成

**文件:**
- 修改: `doubase/pipeline.py` — `run_ingest()`, `estimate_ingest()` 使用新分块流程
- 创建: `tests/test_heading_splitter.py` 追加集成测试

**接口:**
- 消耗: `chunk_by_headings()`, `merge_semantically()`, 现有 pipeline
- 产出: 更新后的 ingest 流程

- [ ] **步骤 1: 更新 run_ingest() 中的分块逻辑**

读取 `doubase/pipeline.py`，找到 `run_ingest()` 中分块部分（约第 230-240 行），替换为：

```python
        # 分块 — 根据文件类型选择策略
        if doc.file_type == "markdown":
            raw_chunks = chunk_by_headings(doc.text, file_path, content_hash, chunker)
        else:
            # .docx / .pdf 保持原有滑动窗口
            raw_chunks = chunker.chunk_text(doc.text, file_path, content_hash)

        # LLM 语义合并（Stage 3）
        if config.get("chunker", {}).get("semantic_merge", True):
            llm = get_llm(config)
            chunks = merge_semantically(raw_chunks, llm)
        else:
            chunks = raw_chunks

        if not chunks:
            results["skipped_unchanged"].append(file_path)
            console.print(f"  ⏭️  跳过 (空文件): {file_path}")
            continue
```

在 `pipeline.py` 顶部添加导入：

```python
from doubase.chunker.chunker import chunk_by_headings
from doubase.chunker.semantic_merger import merge_semantically
```

- [ ] **步骤 2: 更新 estimate_ingest()**

在 `estimate_ingest()` 中，`chunker.chunk_text()` 调用替换为：

```python
        content_hash = _hash_file(file_path)
        if doc.file_type == "markdown":
            raw_chunks = chunk_by_headings(doc.text, file_path, content_hash, chunker)
        else:
            raw_chunks = chunker.chunk_text(doc.text, file_path, content_hash)

        # 估算 LLM 合并费用（仅统计需要 LLM 判断的 pair 数）
        merge_pairs = 0
        from collections import Counter
        heading_counts = Counter(c.metadata.get("heading_text", "") for c in raw_chunks)
        for count in heading_counts.values():
            if count > 1:
                merge_pairs += count - 1

        chunks = raw_chunks
        merge_cost_estimate = merge_pairs * 500 / 1_000_000 * pricing.get("input_price", 1.0)
```

在 `estimate_ingest()` 返回的 dict 中增加 `merge_pairs` 和 `merge_cost_estimate` 字段。

- [ ] **步骤 3: 运行全量测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 68 passed（无回归）

- [ ] **步骤 4: 提交**

```bash
git add doubase/pipeline.py
git commit -m "feat: integrate 3-stage chunking into ingest pipeline"
```

---

### 任务 6: Config 更新 + 端到端验证

**文件:**
- 修改: `config.yaml` — 添加 heading_split / semantic_merge 配置项

- [ ] **步骤 1: 更新 config.yaml**

在 `chunker` 段追加：

```yaml
chunker:
  chunk_size: 512
  chunk_overlap: 64
  heading_split: true           # 启用 # 标题切分（仅 .md）
  semantic_merge: true          # 启用 LLM 保守合并
```

- [ ] **步骤 2: 端到端测试**

创建临时 markdown 文件并执行 ingest：

```bash
cat > /tmp/test_chunk_strategy.md << 'EOF'
---
title: 测试
---

# 智能体

智能体是一个能够自主感知环境、做出决策并采取行动的系统。

## 核心组件

### 感知模块
感知模块负责接收环境信息。包括传感器数据、用户输入、API 返回值等。

### 规划模块
规划模块是智能体的决策中心。主要有两种范式：ReAct 和 Plan-and-Solve。

## 常见框架

- LangChain
- AutoGPT
- MetaGPT
EOF

doubase ingest /tmp/test_chunk_strategy.md --yes
```

预期：每个标题段落作为一个独立 chunk 入库，strategy 标记为 "heading"。

- [ ] **步骤 3: 运行全量测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 68 passed

- [ ] **步骤 4: 提交**

```bash
git add config.yaml
git commit -m "feat: add heading_split and semantic_merge config options"
```

---

## 实现注意事项

1. **任务顺序**: 1 → 2 → 3 → 4 → 5 → 6，严格按依赖顺序
2. **TDD**: 每个任务先写失败测试，再写实现
3. **Python 版本**: 始终使用 `/opt/homebrew/bin/python3.11`
4. **向后兼容**: `.docx` 和 `.pdf` 文件不受影响，继续走原有滑动窗口
5. **现有 53 个测试**: 不能破坏任何已有测试
