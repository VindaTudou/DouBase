# DouBase MVP 实现计划

> **面向执行者：** 请使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐个实现。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标：** 构建一个 Python CLI 工具，(1) 通过 RAG 检索本地 Markdown/Word/PDF 笔记，结合 LLM 自身知识以混合模式回答用户问题；(2) 分析外部项目源码，生成关键代码与算法的 Markdown 总结，并向量化存入知识库。

**架构：** 基于 Pipeline 的模块化设计 — `解析器 → 分块 → 向量化 → 存储 → 检索 → 生成`。每个阶段是独立模块，背后有抽象接口。CLI 使用 argparse。通过 YAML 配置文件管理，支持环境变量插值。Provider 切换通过工厂函数实现。

**技术栈：** Python >=3.11, ChromaDB, OpenAI SDK（用于 DeepSeek/智谱）, python-docx, PyMuPDF, tiktoken, PyYAML, watchdog, sentence-transformers（可选）, rich

## 全局约束

- Python >=3.11
- chromadb>=0.5.0, openai>=1.0.0, python-docx>=1.0.0, PyMuPDF>=1.23.0, tiktoken>=0.5.0, pyyaml>=6.0, watchdog>=4.0.0, sentence-transformers>=2.0.0（可选）, rich>=13.0.0
- 所有 API 调用使用 `openai` SDK（DeepSeek 和智谱均兼容 OpenAI 接口）
- 默认 LLM: DeepSeek，默认 Embedding: 智谱
- CLI 命令: `doubase`（在 pyproject.toml `[project.scripts]` 中定义）
- 环境变量: config.yaml 中的 `${VAR_NAME}` 在加载时自动解析
- 不使用 LangChain、LlamaIndex — 自研轻量 RAG pipeline
- 测试: LLM/Embedder 层使用 mock，Parser/Chunker/VectorStore 使用真实数据

---

### 任务 1: 项目脚手架

**文件:**
- 创建: `pyproject.toml`
- 创建: `config.yaml`
- 创建: `doubase/__init__.py`
- 创建: `README.md`

**接口:**
- 产出: `doubase` CLI 入口点，通过 `pyproject.toml [project.scripts]` 定义

- [ ] **步骤 1: 编写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "doubase"
version = "0.1.0"
description = "本地 RAG agent，支持 Markdown/Word/PDF 笔记检索与代码分析"
requires-python = ">=3.11"
dependencies = [
    "chromadb>=0.5.0",
    "openai>=1.0.0",
    "python-docx>=1.0.0",
    "PyMuPDF>=1.23.0",
    "tiktoken>=0.5.0",
    "pyyaml>=6.0",
    "watchdog>=4.0.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
local-embed = ["sentence-transformers>=2.0.0"]

[project.scripts]
doubase = "doubase.cli:main"

[tool.setuptools.packages.find]
include = ["doubase*"]
```

- [ ] **步骤 2: 编写 config.yaml**

```yaml
# LLM 配置
llm:
  provider: deepseek
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    base_url: https://api.deepseek.com/v1
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o
    base_url: https://api.openai.com/v1
  openai_compat:
    api_key: ${CUSTOM_API_KEY}
    model: your-model
    base_url: https://your-api.com/v1

# Embedding 配置
embedding:
  provider: zhipu
  zhipu:
    api_key: ${ZHIPU_API_KEY}
    model: embedding-2
    base_url: https://open.bigmodel.cn/api/paas/v4
  local:
    model_name: BAAI/bge-small-zh-v1.5

# ChromaDB 配置
storage:
  persist_dir: ~/.doubase/vectors
  collection_name: notes

# 分块配置
chunker:
  chunk_size: 512
  chunk_overlap: 64

# 检索配置
retrieval:
  top_k: 5

# 监控目录配置
watch:
  inbox_dir: ~/Documents/inbox

# 解析器配置
parsers:
  enabled:
    - markdown
    - docx
    - pdf

# API 定价（人民币/百万 tokens，用于费用估算）
pricing:
  deepseek:
    input_price: 1.0
    output_price: 2.0
  zhipu:
    embed_price: 0.5
  openai:
    input_price: 2.5
    output_price: 10.0
```

- [ ] **步骤 3: 编写 doubase/__init__.py**

```python
\"""DouBase — 本地 RAG agent，管理你的笔记与代码知识库。\"""

__version__ = "0.1.0"
```

- [ ] **步骤 4: 编写 README.md**

```markdown
# DouBase

本地 RAG CLI 工具，用于个人知识管理与代码分析。

## 快速开始

```bash
pip install -e .
export DEEPSEEK_API_KEY=sk-...
export ZHIPU_API_KEY=...

doubase ingest ~/Documents/notes/
doubase ask "Redis 持久化原理是什么？"
doubase analyze ../some-project/
```
```

- [ ] **步骤 5: 开发模式安装并验证 CLI 入口**

执行: `pip install -e .`
执行: `doubase --help`
预期: 打印用法（cli.py 未编写时会优雅失败，但入口点应能正常解析）

- [ ] **步骤 6: 提交**

```bash
git add pyproject.toml config.yaml doubase/__init__.py README.md
git commit -m "feat: 项目脚手架，包含 pyproject.toml 和配置"
```

---


### 任务 2: 配置模块

**文件:**
- 创建: `doubase/config.py`
- 创建: `tests/test_config.py`

**接口:**
- 产出: `load_config(path: str = None) -> dict` — 加载 YAML、解析 `${VAR}` 环境变量、展开 `~` 路径

- [ ] **步骤 1: 编写失败测试**

创建 `tests/test_config.py`:

```python
import os
import tempfile
from doubase.config import load_config, resolve_env_vars


def test_resolve_env_vars():
    os.environ["TEST_VAR"] = "my-secret"
    config = {
        "llm": {
            "api_key": "${TEST_VAR}",
            "model": "deepseek-chat",
            "count": 42,
        }
    }
    result = resolve_env_vars(config)
    assert result["llm"]["api_key"] == "my-secret"
    assert result["llm"]["model"] == "deepseek-chat"
    assert result["llm"]["count"] == 42


def test_resolve_tilde():
    config = {"storage": {"persist_dir": "~/test"}}
    result = resolve_env_vars(config)
    assert result["storage"]["persist_dir"].startswith("/")
    assert "~" not in result["storage"]["persist_dir"]


def test_missing_env_var_returns_empty():
    config = {"api_key": "${MISSING_VAR_12345}"}
    result = resolve_env_vars(config)
    assert result["api_key"] == ""


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("llm:\n  provider: deepseek\n  deepseek:\n    api_key: test-key\n")
        f.flush()
        config = load_config(f.name)
        assert config["llm"]["provider"] == "deepseek"
        assert config["llm"]["deepseek"]["api_key"] == "test-key"
        os.unlink(f.name)


def test_load_config_defaults_to_project_root():
    config = load_config()
    assert "llm" in config
    assert "embedding" in config
    assert "storage" in config
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_config.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写 config.py 实现**

创建 `doubase/config.py`:

```python
"""配置管理：YAML 加载与环境变量插值。"""

import os
import re
from pathlib import Path

import yaml


def resolve_env_vars(config: dict) -> dict:
    """递归解析字符串值中的 ${VAR_NAME} 和 ~ 路径。"""
    if isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(item) for item in config]
    elif isinstance(config, str):
        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        result = re.sub(r"\$\{(\w+)\}", replacer, config)
        if result.startswith("~"):
            result = os.path.expanduser(result)
        return result
    else:
        return config


def load_config(path: str = None) -> dict:
    """从 YAML 文件加载配置。

    Args:
        path: config.yaml 路径。为 None 时查找项目根目录下的 config.yaml。

    Returns:
        解析并处理后的配置字典。
    """
    if path is None:
        project_root = Path(__file__).resolve().parent.parent
        path = project_root / "config.yaml"
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"配置文件未找到: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    return resolve_env_vars(raw_config)
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_config.py -v`
预期: 5 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/config.py tests/test_config.py
git commit -m "feat: 添加配置模块，支持 YAML 加载与环境变量解析"
```

---

### 任务 3: 解析器接口 + Markdown 解析器

**文件:**
- 创建: `doubase/parsers/__init__.py`
- 创建: `doubase/parsers/base.py`
- 创建: `doubase/parsers/markdown.py`
- 创建: `tests/test_parsers/__init__.py`
- 创建: `tests/test_parsers/test_markdown.py`
- 创建: `tests/test_parsers/fixtures/test.md`

**接口:**
- 消耗: 无（除 Python 标准库外无上游依赖）
- 产出: `BaseParser` 抽象类，包含 `supports(file_path) -> bool` 和 `parse(file_path) -> ParsedDocument`；`ParsedDocument(text, source_path, file_type, metadata)` 数据类；`MarkdownParser` 实现

- [ ] **步骤 1: 编写基础接口**

创建 `doubase/parsers/__init__.py`:

```python
"""文档解析器 — 支持 .md, .docx, .pdf 文件。"""

from doubase.parsers.base import BaseParser, ParsedDocument
from doubase.parsers.markdown import MarkdownParser

__all__ = ["BaseParser", "ParsedDocument", "MarkdownParser"]
```

创建 `doubase/parsers/base.py`:

```python
"""文档解析器抽象接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    """文档解析结果。

    Attributes:
        text: 纯文本内容（可包含 Markdown 格式）。
        source_path: 原始文件的绝对路径。
        file_type: "markdown"、"docx"、"pdf" 之一。
        metadata: 额外信息（frontmatter、页数、作者等）。
    """

    text: str
    source_path: str
    file_type: str
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """文档解析器抽象接口。"""

    @abstractmethod
    def supports(self, file_path: str) -> bool:
        """返回 True 表示此解析器能处理该文件。"""
        ...

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        """解析文件，返回包含纯文本和元数据的 ParsedDocument。"""
        ...
```

- [ ] **步骤 2: 编写 Markdown 解析器**

创建 `doubase/parsers/markdown.py`:

```python
"""Markdown 文件解析器 — 剥离 YAML frontmatter，保留正文。"""

import re
from pathlib import Path

from doubase.parsers.base import BaseParser, ParsedDocument


class MarkdownParser(BaseParser):
    """.md 文件解析器。剥离 YAML frontmatter，保留正文。"""

    FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() == ".md"

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        raw = path.read_text(encoding="utf-8")

        metadata = {}
        m = self.FRONTMATTER_RE.match(raw)
        if m:
            frontmatter_text = m.group(1)
            raw = raw[m.end():]
            try:
                import yaml
                parsed = yaml.safe_load(frontmatter_text)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
            except Exception:
                pass

        return ParsedDocument(
            text=raw.strip(),
            source_path=str(path.resolve()),
            file_type="markdown",
            metadata=metadata,
        )
```

- [ ] **步骤 3: 编写测试夹具与测试**

创建 `tests/test_parsers/fixtures/test.md`:

```markdown
---
title: 测试笔记
tags: [python, rag]
---

# Hello World

这是一篇关于 **RAG** 的测试笔记。

## 第二章

这里有一些内容。
```

创建 `tests/test_parsers/test_markdown.py`:

```python
from pathlib import Path
from doubase.parsers.markdown import MarkdownParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_markdown_supports():
    parser = MarkdownParser()
    assert parser.supports("/path/to/file.md") is True
    assert parser.supports("/path/to/file.txt") is False
    assert parser.supports("/path/to/file.MD") is True


def test_markdown_parse_strips_frontmatter():
    parser = MarkdownParser()
    doc = parser.parse(str(FIXTURES_DIR / "test.md"))
    assert "---" not in doc.text
    assert "# Hello World" in doc.text
    assert "RAG" in doc.text
    assert doc.file_type == "markdown"


def test_markdown_parse_extracts_frontmatter_metadata():
    parser = MarkdownParser()
    doc = parser.parse(str(FIXTURES_DIR / "test.md"))
    assert doc.metadata.get("title") == "测试笔记"
    assert doc.metadata.get("tags") == ["python", "rag"]


def test_markdown_parse_preserves_markdown_formatting():
    parser = MarkdownParser()
    doc = parser.parse(str(FIXTURES_DIR / "test.md"))
    assert "**RAG**" in doc.text
    assert "## 第二章" in doc.text
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_parsers/test_markdown.py -v`
预期: 4 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/parsers/ tests/test_parsers/
git commit -m "feat: 添加解析器接口与 MarkdownParser"
```

---

### 任务 4: DOCX 解析器

**文件:**
- 创建: `doubase/parsers/docx.py`
- 创建: `tests/test_parsers/test_docx.py`

**接口:**
- 消耗: `BaseParser`, `ParsedDocument`（来自 `doubase.parsers.base`）
- 产出: `DocxParser` 类，实现 `BaseParser`

- [ ] **步骤 1: 编写测试**

创建 `tests/test_parsers/test_docx.py`:

```python
import tempfile
from docx import Document as DocxDocument
from doubase.parsers.docx import DocxParser


def _create_test_docx(path: str):
    doc = DocxDocument()
    doc.add_heading("测试文档", level=1)
    doc.add_paragraph("这是一个包含内容的段落。")
    doc.add_paragraph("另一个段落。")
    doc.save(path)


def test_docx_supports():
    parser = DocxParser()
    assert parser.supports("/path/to/file.docx") is True
    assert parser.supports("/path/to/file.doc") is False
    assert parser.supports("/path/to/file.md") is False


def test_docx_parse_extracts_text():
    parser = DocxParser()
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.close()
        _create_test_docx(f.name)
        doc = parser.parse(f.name)

    assert "测试文档" in doc.text
    assert "这是一个包含内容的段落" in doc.text
    assert "另一个段落" in doc.text
    assert doc.file_type == "docx"
    assert doc.source_path.endswith(".docx")
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_parsers/test_docx.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/parsers/docx.py`:

```python
"""DOCX 文件解析器 — 将 .docx 转换为 Markdown 兼容文本。"""

from pathlib import Path

from doubase.parsers.base import BaseParser, ParsedDocument


class DocxParser(BaseParser):
    """.docx 文件解析器。提取文本，将标题转换为 Markdown 格式。"""

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() == ".docx"

    def parse(self, file_path: str) -> ParsedDocument:
        from docx import Document as DocxDocument

        path = Path(file_path)
        doc = DocxDocument(str(path))

        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                lines.append("")
                continue

            if para.style.name.startswith("Heading"):
                level_str = para.style.name.split()[-1]
                level = int(level_str) if level_str.isdigit() else 1
                lines.append("#" * level + " " + text)
            else:
                lines.append(text)

        metadata = {}
        if doc.core_properties.author:
            metadata["author"] = doc.core_properties.author
        if doc.core_properties.title:
            metadata["title"] = doc.core_properties.title

        return ParsedDocument(
            text="\n\n".join(lines),
            source_path=str(path.resolve()),
            file_type="docx",
            metadata=metadata,
        )
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_parsers/test_docx.py -v`
预期: 2 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/parsers/docx.py tests/test_parsers/test_docx.py
git commit -m "feat: 添加 DOCX 解析器"
```

---

### 任务 5: PDF 解析器

**文件:**
- 创建: `doubase/parsers/pdf.py`
- 创建: `tests/test_parsers/test_pdf.py`

**接口:**
- 消耗: `BaseParser`, `ParsedDocument`（来自 `doubase.parsers.base`）
- 产出: `PdfParser` 类，实现 `BaseParser`

- [ ] **步骤 1: 编写测试**

创建 `tests/test_parsers/test_pdf.py`:

```python
import tempfile
from doubase.parsers.pdf import PdfParser


def _create_test_pdf(path: str):
    import fitz  # PyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 72), "你好 PDF", fontsize=14)
    page.insert_text(fitz.Point(72, 100), "这是一个测试 PDF 文档。", fontsize=12)
    doc.save(path)
    doc.close()


def test_pdf_supports():
    parser = PdfParser()
    assert parser.supports("/path/to/file.pdf") is True
    assert parser.supports("/path/to/file.PDF") is True
    assert parser.supports("/path/to/file.md") is False


def test_pdf_parse_extracts_text():
    parser = PdfParser()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.close()
        _create_test_pdf(f.name)
        doc = parser.parse(f.name)

    assert "你好 PDF" in doc.text
    assert "测试 PDF" in doc.text
    assert doc.file_type == "pdf"
    assert doc.source_path.endswith(".pdf")
    assert "pages" in doc.metadata
    assert doc.metadata["pages"] == 1
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_parsers/test_pdf.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/parsers/pdf.py`:

```python
"""PDF 文件解析器 — 使用 PyMuPDF 将 .pdf 转换为纯文本。"""

from pathlib import Path

from doubase.parsers.base import BaseParser, ParsedDocument


class PdfParser(BaseParser):
    """.pdf 文件解析器。使用 PyMuPDF 提取文本。"""

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() == ".pdf"

    def parse(self, file_path: str) -> ParsedDocument:
        import fitz  # PyMuPDF

        path = Path(file_path)
        doc = fitz.open(str(path))

        pages_text = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                pages_text.append(text.strip())

        page_count = len(doc)
        doc.close()

        full_text = "\n\n".join(pages_text)

        return ParsedDocument(
            text=full_text,
            source_path=str(path.resolve()),
            file_type="pdf",
            metadata={"pages": page_count},
        )
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_parsers/test_pdf.py -v`
预期: 2 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/parsers/pdf.py tests/test_parsers/test_pdf.py
git commit -m "feat: 添加基于 PyMuPDF 的 PDF 解析器"
```

---

### 任务 6: 解析器工厂 + 文本分块器

**文件:**
- 修改: `doubase/parsers/__init__.py` — 添加 `get_parser` 工厂函数
- 创建: `doubase/chunker/__init__.py`
- 创建: `doubase/chunker/chunker.py`
- 创建: `tests/test_chunker.py`

**接口:**
- 消耗: `BaseParser`, `MarkdownParser`, `DocxParser`, `PdfParser`, `ParsedDocument`
- 产出: `get_parser(file_path: str) -> BaseParser | None`；`Chunker` 类，包含 `chunk_text(text, source_path, content_hash) -> list[Chunk]`；`Chunk(text, source_path, chunk_index, content_hash)` 数据类

- [ ] **步骤 1: 在 parsers/__init__.py 中添加 get_parser 工厂**

读取当前 `doubase/parsers/__init__.py`，替换为:

```python
"""文档解析器 — 支持 .md, .docx, .pdf 文件。"""

from doubase.parsers.base import BaseParser, ParsedDocument
from doubase.parsers.markdown import MarkdownParser
from doubase.parsers.docx import DocxParser
from doubase.parsers.pdf import PdfParser

__all__ = ["BaseParser", "ParsedDocument", "get_parser", "get_all_parsers"]


def get_all_parsers() -> list[BaseParser]:
    """返回所有可用的解析器实例。"""
    return [MarkdownParser(), DocxParser(), PdfParser()]


def get_parser(file_path: str) -> BaseParser | None:
    """根据文件扩展名返回合适的解析器，不支持则返回 None。"""
    for parser in get_all_parsers():
        if parser.supports(file_path):
            return parser
    return None
```

- [ ] **步骤 2: 编写分块器测试**

创建 `tests/test_chunker.py`:

```python
import hashlib
from doubase.chunker.chunker import Chunker, Chunk


def test_chunker_splits_short_text_into_single_chunk():
    config = {"chunk_size": 100, "chunk_overlap": 20}
    chunker = Chunker(config)
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(b"hello").hexdigest()
    chunks = chunker.chunk_text("hello world", source_path, content_hash)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source_path == source_path
    assert chunks[0].chunk_index == 0
    assert chunks[0].content_hash == content_hash


def test_chunker_splits_long_text():
    config = {"chunk_size": 20, "chunk_overlap": 5}
    chunker = Chunker(config)
    text = " ".join(["word" + str(i) for i in range(80)])
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    chunks = chunker.chunk_text(text, source_path, content_hash)
    assert len(chunks) > 1
    for chunk in chunks:
        token_count = len(chunker._encode(chunk.text))
        assert token_count <= 25


def test_chunker_overlap():
    config = {"chunk_size": 50, "chunk_overlap": 10}
    chunker = Chunker(config)
    text = "unique first sentence. " * 5 + "unique last sentence. " * 5
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    chunks = chunker.chunk_text(text, source_path, content_hash)
    if len(chunks) > 1:
        tokens_0 = chunker._encode(chunks[0].text)
        tokens_1 = chunker._encode(chunks[1].text)
        overlap_found = any(t in tokens_1 for t in tokens_0[-5:])
        assert overlap_found


def test_chunker_handles_empty_text():
    config = {"chunk_size": 100, "chunk_overlap": 20}
    chunker = Chunker(config)
    chunks = chunker.chunk_text("", "/tmp/test.md", "abc123")
    assert len(chunks) == 0
```

- [ ] **步骤 3: 运行测试确认失败**

执行: `pytest tests/test_chunker.py -v`
预期: FAIL

- [ ] **步骤 4: 编写分块器实现**

创建 `doubase/chunker/__init__.py`:

```python
"""文本分块器 — 将文档拆分为可向量化的片段。"""
```

创建 `doubase/chunker/chunker.py`:

```python
"""基于 token 计数的滑动窗口文本分块器。"""

from dataclasses import dataclass


@dataclass
class Chunk:
    """单个文本块及其元数据，可直接用于向量化。

    Attributes:
        text: chunk 文本内容。
        source_path: 原始文件的绝对路径。
        chunk_index: 文档内的从零开始的索引。
        content_hash: 源文件内容的 SHA256 哈希（用于去重）。
    """

    text: str
    source_path: str
    chunk_index: int
    content_hash: str


class Chunker:
    """将文本按 token 数拆分为重叠的 chunk。

    使用 tiktoken cl100k_base 编码进行精确计数。
    如果 tiktoken 不可用，回退到近似字符级分块。
    """

    def __init__(self, config: dict):
        self.chunk_size = config.get("chunk_size", 512)
        self.chunk_overlap = config.get("chunk_overlap", 64)
        self._encoding = None
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass

    def _encode(self, text: str) -> list[int]:
        """将文本编码为 token ID 列表。"""
        if self._encoding is not None:
            return self._encoding.encode(text)
        return list(range(len(text) // 4 + 1))

    def _decode(self, tokens: list[int]) -> str:
        """将 token ID 列表解码为文本字符串。"""
        if self._encoding is not None and hasattr(self._encoding, 'decode'):
            return self._encoding.decode(tokens)
        return ""

    def chunk_text(self, text: str, source_path: str, content_hash: str) -> list[Chunk]:
        """将文本拆分为重叠的 chunk，用于向量化。"""
        if not text.strip():
            return []

        tokens = self._encode(text)
        chunks = []
        step = max(1, self.chunk_size - self.chunk_overlap)

        for i in range(0, len(tokens), step):
            chunk_token_ids = tokens[i:i + self.chunk_size]
            if self._encoding is not None:
                chunk_text = self._decode(chunk_token_ids)
            else:
                char_ratio = len(text) / max(1, len(tokens))
                start_char = int(i * char_ratio)
                end_char = int((i + self.chunk_size) * char_ratio)
                chunk_text = text[start_char:end_char]

            if chunk_text.strip():
                chunks.append(Chunk(
                    text=chunk_text.strip(),
                    source_path=source_path,
                    chunk_index=len(chunks),
                    content_hash=content_hash,
                ))

        return chunks
```

- [ ] **步骤 5: 运行测试确认通过**

执行: `pytest tests/test_chunker.py -v`
预期: 4 PASS

- [ ] **步骤 6: 提交**

```bash
git add doubase/chunker/ doubase/parsers/ tests/test_chunker.py
git commit -m "feat: 添加解析器工厂与基于 token 的分块器"
```

---

### 任务 7: Embedding 接口 + 智谱 Embedding

**文件:**
- 创建: `doubase/embedding/__init__.py`
- 创建: `doubase/embedding/base.py`
- 创建: `doubase/embedding/zhipu.py`
- 创建: `tests/test_embedding.py`

**接口:**
- 消耗: `load_config`（来自 `doubase.config`）
- 产出: `BaseEmbedder` 抽象类，包含 `embed(texts: list[str]) -> list[list[float]]` 和 `embed_query(text: str) -> list[float]`；`ZhipuEmbedder` 实现；`get_embedder(config: dict) -> BaseEmbedder` 工厂函数

- [ ] **步骤 1: 使用 mock 编写测试**

创建 `tests/test_embedding.py`:

```python
from unittest.mock import patch, MagicMock
from doubase.embedding.base import BaseEmbedder
from doubase.embedding.zhipu import ZhipuEmbedder
from doubase.embedding import get_embedder


def test_get_embedder_returns_zhipu_by_default():
    config = {
        "embedding": {
            "provider": "zhipu",
            "zhipu": {
                "api_key": "test-key",
                "model": "embedding-2",
                "base_url": "https://test.com/api",
            },
        }
    }
    embedder = get_embedder(config)
    assert isinstance(embedder, ZhipuEmbedder)


def test_zhipu_embedder_interface():
    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    assert isinstance(embedder, BaseEmbedder)


@patch("doubase.embedding.zhipu.OpenAI")
def test_zhipu_embed_batches(mock_openai_class):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
        MagicMock(embedding=[0.4, 0.5, 0.6]),
    ]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    result = embedder.embed(["hello", "world"])
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    assert result[1] == [0.4, 0.5, 0.6]
    mock_client.embeddings.create.assert_called_once_with(
        model="embedding-2",
        input=["hello", "world"],
    )


@patch("doubase.embedding.zhipu.OpenAI")
def test_zhipu_embed_query(mock_openai_class):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.7, 0.8, 0.9])]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    result = embedder.embed_query("single query")
    assert result == [0.7, 0.8, 0.9]
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_embedding.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/embedding/__init__.py`:

```python
"""Embedding 层 — 将文本转换为向量。"""

from doubase.embedding.base import BaseEmbedder
from doubase.embedding.zhipu import ZhipuEmbedder

__all__ = ["BaseEmbedder", "ZhipuEmbedder", "get_embedder"]


def get_embedder(config: dict) -> BaseEmbedder:
    """工厂函数：返回配置指定的 Embedder 实例。"""
    embedding_config = config["embedding"]
    provider = embedding_config["provider"]

    if provider == "zhipu":
        cfg = embedding_config["zhipu"]
        return ZhipuEmbedder(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg["base_url"],
        )
    elif provider == "local":
        from doubase.embedding.local import LocalEmbedder
        cfg = embedding_config["local"]
        return LocalEmbedder(model_name=cfg["model_name"])
    else:
        raise ValueError(f"未知的 embedding provider: {provider}")
```

创建 `doubase/embedding/base.py`:

```python
"""Embedding 模型抽象接口。"""

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """文本到向量的 embedding 抽象接口。"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化，返回向量列表。"""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条查询文本向量化（某些模型有专门的 query 模式）。"""
        ...
```

创建 `doubase/embedding/zhipu.py`:

```python
"""智谱 AI Embedding API（embedding-2 模型）。智谱 API 兼容 OpenAI 接口。"""

from openai import OpenAI

from doubase.embedding.base import BaseEmbedder


class ZhipuEmbedder(BaseEmbedder):
    """通过智谱 (ZhipuAI) API 进行 Embedding。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        result = self.embed([text])
        return result[0] if result else []
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_embedding.py -v`
预期: 4 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/embedding/ tests/test_embedding.py
git commit -m "feat: 添加 embedding 接口与智谱 Embedder"
```

---

### 任务 8: 本地 Embedder

**文件:**
- 创建: `doubase/embedding/local.py`

**接口:**
- 消耗: `BaseEmbedder`（来自 `doubase.embedding.base`）
- 产出: `LocalEmbedder` — 使用 sentence-transformers 的本地 embedding

- [ ] **步骤 1: 编写实现**

创建 `doubase/embedding/local.py`:

```python
"""本地 embedding 模型 — 通过 sentence-transformers 实现（可选依赖）。"""

from doubase.embedding.base import BaseEmbedder


class LocalEmbedder(BaseEmbedder):
    """本地 embedding 模型（BGE 等），通过 sentence-transformers 运行。

    延迟加载模型，避免导入时即占用内存。
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise ImportError(
                    "本地 embedding 需要 sentence-transformers。"
                    "请执行: pip install doubase[local-embed]"
                )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._ensure_model()
        embedding = self._model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()
```

- [ ] **步骤 2: 在 test_embedding.py 中添加本地 Embedder 测试**

追加到 `tests/test_embedding.py`:

```python
def test_get_embedder_returns_local_when_configured():
    config = {
        "embedding": {
            "provider": "local",
            "local": {
                "model_name": "BAAI/bge-small-zh-v1.5",
            },
        }
    }
    from doubase.embedding.local import LocalEmbedder
    embedder = get_embedder(config)
    assert isinstance(embedder, LocalEmbedder)
    assert embedder._model_name == "BAAI/bge-small-zh-v1.5"


def test_get_embedder_raises_for_unknown_provider():
    config = {
        "embedding": {
            "provider": "unknown",
        }
    }
    try:
        get_embedder(config)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "unknown" in str(e).lower()
```

- [ ] **步骤 3: 运行测试确认通过**

执行: `pytest tests/test_embedding.py -v`
预期: 6 PASS

- [ ] **步骤 4: 提交**

```bash
git add doubase/embedding/local.py tests/test_embedding.py
git commit -m "feat: 添加基于 sentence-transformers 的本地 Embedder"
```

---

### 任务 9: ChromaDB 向量存储

**文件:**
- 创建: `doubase/storage/__init__.py`
- 创建: `doubase/storage/vector_store.py`
- 创建: `tests/test_vector_store.py`

**接口:**
- 消耗: `Chunk`（来自 `doubase.chunker.chunker`），调用方提供的 config
- 产出: `VectorStore` 类，包含 `add_chunks_with_embeddings(chunks, embeddings) -> int`、`search(query_embedding, top_k) -> list[dict]`、`delete_by_source(source_path) -> int`、`get_existing_hash(source_path) -> str | None`、`count() -> int`

- [ ] **步骤 1: 编写测试**

创建 `tests/test_vector_store.py`:

```python
import tempfile
from doubase.storage.vector_store import VectorStore
from doubase.chunker.chunker import Chunk


def _make_chunk(text="test content", source_path="/tmp/test.md", idx=0, hash_val="abc123"):
    return Chunk(text=text, source_path=source_path, chunk_index=idx, content_hash=hash_val)


def test_add_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        chunks = [
            _make_chunk("Redis 持久化使用 RDB 和 AOF", "/notes/redis.md", 0, "h1"),
            _make_chunk("Python 是一门编程语言", "/notes/python.md", 0, "h2"),
        ]
        count = store.add_chunks_with_embeddings(
            chunks,
            [[0.1] * 1536, [0.2] * 1536],
        )
        assert count == 2

        results = store.search([0.1] * 1536, top_k=2)
        assert len(results) == 2


def test_get_existing_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        hash_val = "abcdef1234567890"
        store.add_chunks_with_embeddings(
            [_make_chunk("data", "/notes/file.md", 0, hash_val)],
            [[0.1] * 1536],
        )
        found = store.get_existing_hash("/notes/file.md")
        assert found == hash_val


def test_get_existing_hash_returns_none_for_new_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        found = store.get_existing_hash("/notes/nonexistent.md")
        assert found is None


def test_delete_by_source():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        store.add_chunks_with_embeddings([
            _make_chunk("chunk 1", "/notes/keep.md", 0, "h1"),
            _make_chunk("chunk 2", "/notes/remove.md", 0, "h2"),
        ], [[0.1] * 1536, [0.2] * 1536])
        deleted = store.delete_by_source("/notes/remove.md")
        assert deleted >= 1

        remaining_hash = store.get_existing_hash("/notes/remove.md")
        assert remaining_hash is None

        keep_hash = store.get_existing_hash("/notes/keep.md")
        assert keep_hash == "h1"
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_vector_store.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/storage/__init__.py`:

```python
"""存储层 — ChromaDB 向量存储封装。"""
```

创建 `doubase/storage/vector_store.py`:

```python
"""ChromaDB 向量存储 — 将 ChromaDB collection 封装为我们的 chunk 模型。"""

from pathlib import Path

from doubase.chunker.chunker import Chunk


class VectorStore:
    """基于 ChromaDB 的文档 chunk 向量存储。

    每个 chunk 存储时附带元数据: source_path, content_hash, chunk_index。
    去重逻辑在 ingest 层处理（embedding 前比对哈希），
    但 store 也暴露 get_existing_hash() 方法以支持该检查。
    """

    def __init__(self, persist_dir: str, collection_name: str):
        import chromadb
        persist_path = Path(persist_dir).expanduser().resolve()
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks_with_embeddings(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """添加带预计算 embedding 的 chunks。返回添加数量。"""
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = f"{chunk.source_path}__{chunk.chunk_index}"
            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append({
                "source_path": chunk.source_path,
                "content_hash": chunk.content_hash,
                "chunk_index": chunk.chunk_index,
            })

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        return len(chunks)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """搜索与 query embedding 最相似的 chunks。

        返回 dict 列表，每个 dict 包含: text, source_path, distance。
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                items.append({
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "source_path": results["metadatas"][0][i].get("source_path", "")
                        if results["metadatas"] else "",
                    "distance": results["distances"][0][i]
                        if results["distances"] else 0.0,
                })

        return items

    def delete_by_source(self, source_path: str) -> int:
        """删除指定源文件的所有 chunks。返回删除数量。"""
        existing = self._collection.get(
            where={"source_path": source_path},
        )
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])
            return len(existing["ids"])
        return 0

    def get_existing_hash(self, source_path: str) -> str | None:
        """查询已索引文件的 content_hash，未找到则返回 None。"""
        existing = self._collection.get(
            where={"source_path": source_path},
            limit=1,
        )
        if existing["metadatas"]:
            return existing["metadatas"][0].get("content_hash")
        return None

    def count(self) -> int:
        """返回 collection 中的 chunk 总数。"""
        return self._collection.count()
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_vector_store.py -v`
预期: 4 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/storage/ tests/test_vector_store.py
git commit -m "feat: 添加 ChromaDB 向量存储封装"
```

---

### 任务 10: 检索器

**文件:**
- 创建: `doubase/retrieval/__init__.py`
- 创建: `doubase/retrieval/retriever.py`
- 创建: `tests/test_retriever.py`

**接口:**
- 消耗: `VectorStore`, `BaseEmbedder`
- 产出: `Retriever` 类，`retrieve(query: str, top_k: int) -> list[dict]`

- [ ] **步骤 1: 编写测试**

创建 `tests/test_retriever.py`:

```python
from unittest.mock import MagicMock
from doubase.retrieval.retriever import Retriever


def test_retriever_embeds_and_searches():
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_store = MagicMock()
    mock_store.search.return_value = [
        {"text": "Redis 使用 RDB 持久化", "source_path": "/notes/redis.md", "distance": 0.12},
        {"text": "AOF 记录每次写操作", "source_path": "/notes/redis.md", "distance": 0.18},
    ]

    retriever = Retriever(embedder=mock_embedder, vector_store=mock_store)
    results = retriever.retrieve("Redis 如何持久化数据？", top_k=5)

    mock_embedder.embed_query.assert_called_once_with("Redis 如何持久化数据？")
    mock_store.search.assert_called_once_with([0.1, 0.2, 0.3], 5)
    assert len(results) == 2
    assert results[0]["source_path"] == "/notes/redis.md"


def test_retriever_uses_default_top_k():
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2]
    mock_store = MagicMock()
    mock_store.search.return_value = []

    retriever = Retriever(embedder=mock_embedder, vector_store=mock_store)
    retriever.retrieve("test query")

    mock_store.search.assert_called_once_with([0.1, 0.2], 5)
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `pytest tests/test_retriever.py -v`
预期: FAIL

- [ ] **步骤 3: 编写实现**

创建 `doubase/retrieval/__init__.py`:

```python
"""检索层 — 将查询向量化并搜索向量库。"""
```

创建 `doubase/retrieval/retriever.py`:

```python
"""检索 — 将查询 embedding 后从 ChromaDB 中搜索相关 chunks。"""

from doubase.embedding.base import BaseEmbedder
from doubase.storage.vector_store import VectorStore


class Retriever:
    """将用户查询向量化，从向量库中检索 top-K 相关 chunks。"""

    def __init__(self, embedder: BaseEmbedder, vector_store: VectorStore):
        self._embedder = embedder
        self._store = vector_store

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed 查询文本并返回 top-K 最相关 chunks。

        Args:
            query: 用户自然语言问题。
            top_k: 检索数量。

        Returns:
            dict 列表，每个包含: text, source_path, distance。
        """
        query_vector = self._embedder.embed_query(query)
        return self._store.search(query_vector, top_k=top_k)
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_retriever.py -v`
预期: 2 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/retrieval/ tests/test_retriever.py
git commit -m "feat: 添加检索器（embed 查询 + 搜索向量库）"
```

---

### 任务 11: LLM 接口 + DeepSeek LLM

**文件:**
- 创建: `doubase/generation/__init__.py`
- 创建: `doubase/generation/base.py`
- 创建: `doubase/generation/deepseek.py`
- 创建: `tests/test_generation.py`

**接口:**
- 消耗: 无
- 产出: `BaseLLM` 抽象类，包含 `chat(messages, **kwargs) -> str` 和 `chat_stream(messages, **kwargs) -> Iterator[str]`；`DeepSeekLLM` 实现；`get_llm(config, override_provider=None) -> BaseLLM` 工厂函数

- [ ] **步骤 1: 编写基础接口和实现**

创建 `doubase/generation/__init__.py`:

```python
"""LLM 生成层 — 模型无关的对话接口。"""

from doubase.generation.base import BaseLLM
from doubase.generation.deepseek import DeepSeekLLM

__all__ = ["BaseLLM", "DeepSeekLLM", "get_llm"]


def get_llm(config: dict, override_provider: str = None) -> BaseLLM:
    """工厂函数：返回配置指定的 LLM 实例。

    Args:
        config: 完整配置字典。
        override_provider: 不为 None 时，使用此 provider 而非配置中的默认值。
    """
    llm_config = config["llm"]
    provider = override_provider or llm_config["provider"]

    if provider == "deepseek":
        cfg = llm_config["deepseek"]
        return DeepSeekLLM(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg["base_url"],
        )
    elif provider in ("openai", "openai_compat"):
        from doubase.generation.openai_compat import OpenAICompatLLM
        cfg = llm_config[provider]
        return OpenAICompatLLM(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        )
    else:
        raise ValueError(f"未知的 LLM provider: {provider}")
```

创建 `doubase/generation/base.py`:

```python
"""LLM 对话模型抽象接口。"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class BaseLLM(ABC):
    """大语言模型对话抽象接口。"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送消息，返回完整文本回复。"""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """发送消息，逐 token 流式返回文本。"""
        ...
```

创建 `doubase/generation/deepseek.py`:

```python
"""DeepSeek Chat API — 兼容 OpenAI 接口。"""

from collections.abc import Iterator

from openai import OpenAI

from doubase.generation.base import BaseLLM


class DeepSeekLLM(BaseLLM):
    """DeepSeek API 的 LLM 客户端（兼容 OpenAI 接口）。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

- [ ] **步骤 2: 编写测试**

创建 `tests/test_generation.py`:

```python
from unittest.mock import patch, MagicMock
from doubase.generation.base import BaseLLM
from doubase.generation.deepseek import DeepSeekLLM
from doubase.generation import get_llm


def test_get_llm_returns_deepseek_by_default():
    config = {
        "llm": {
            "provider": "deepseek",
            "deepseek": {
                "api_key": "test-key",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
            },
        }
    }
    llm = get_llm(config)
    assert isinstance(llm, DeepSeekLLM)


def test_get_llm_override_provider():
    config = {
        "llm": {
            "provider": "deepseek",
            "deepseek": {"api_key": "sk-ds", "model": "deepseek-chat", "base_url": "https://x.com"},
            "openai": {"api_key": "sk-oai", "model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
        }
    }
    from doubase.generation.openai_compat import OpenAICompatLLM
    llm = get_llm(config, override_provider="openai")
    assert isinstance(llm, OpenAICompatLLM)


@patch("doubase.generation.deepseek.OpenAI")
def test_deepseek_chat(mock_openai_class):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Redis 持久化使用 RDB 和 AOF。"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    llm = DeepSeekLLM(api_key="test", model="deepseek-chat", base_url="https://api.test.com")
    result = llm.chat([{"role": "user", "content": "你好"}])
    assert "Redis 持久化" in result


@patch("doubase.generation.deepseek.OpenAI")
def test_deepseek_chat_stream(mock_openai_class):
    mock_client = MagicMock()
    mock_chunk1 = MagicMock()
    mock_chunk1.choices = [MagicMock(delta=MagicMock(content="你好 "))]
    mock_chunk2 = MagicMock()
    mock_chunk2.choices = [MagicMock(delta=MagicMock(content="世界"))]
    mock_chunk3 = MagicMock()
    mock_chunk3.choices = [MagicMock(delta=MagicMock(content=None))]
    mock_client.chat.completions.create.return_value = [mock_chunk1, mock_chunk2, mock_chunk3]
    mock_openai_class.return_value = mock_client

    llm = DeepSeekLLM(api_key="test", model="deepseek-chat", base_url="https://api.test.com")
    tokens = list(llm.chat_stream([{"role": "user", "content": "你好"}]))
    assert tokens == ["你好 ", "世界"]
```

- [ ] **步骤 3: 运行测试确认通过**

执行: `pytest tests/test_generation.py -v`
预期: 4 PASS

- [ ] **步骤 4: 提交**

```bash
git add doubase/generation/ tests/test_generation.py
git commit -m "feat: 添加 LLM 接口与 DeepSeek 对话客户端"
```

---

### 任务 12: OpenAI 兼容 LLM

**文件:**
- 创建: `doubase/generation/openai_compat.py`

**接口:**
- 消耗: `BaseLLM`（来自 `doubase.generation.base`）
- 产出: `OpenAICompatLLM` — 适用于 OpenAI 及任何兼容 API

- [ ] **步骤 1: 编写实现**

创建 `doubase/generation/openai_compat.py`:

```python
"""OpenAI / OpenAI 兼容 LLM 客户端。"""

from collections.abc import Iterator

from openai import OpenAI

from doubase.generation.base import BaseLLM


class OpenAICompatLLM(BaseLLM):
    """适用于 OpenAI 及任何兼容 API 的 LLM 客户端（Ollama、vLLM 等）。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

- [ ] **步骤 2: 添加测试**

追加到 `tests/test_generation.py`:

```python
def test_get_llm_returns_openai_compat():
    config = {
        "llm": {
            "provider": "openai_compat",
            "openai_compat": {
                "api_key": "test-key",
                "model": "custom-model",
                "base_url": "https://custom.api.com/v1",
            },
        }
    }
    from doubase.generation.openai_compat import OpenAICompatLLM
    llm = get_llm(config)
    assert isinstance(llm, OpenAICompatLLM)
```

- [ ] **步骤 3: 运行测试确认通过**

执行: `pytest tests/test_generation.py -v`
预期: 5 PASS

- [ ] **步骤 4: 提交**

```bash
git add doubase/generation/openai_compat.py tests/test_generation.py
git commit -m "feat: 添加 OpenAI 兼容 LLM 客户端"
```

---

### 任务 13: Ingest Pipeline（核心流水线组装）

**文件:**
- 创建: `doubase/pipeline.py`
- 创建: `tests/test_pipeline.py`

**接口:**
- 消耗: 所有前述模块（parsers, chunker, embedder, vector store, config）
- 产出: `estimate_ingest(paths, config) -> dict`；`display_ingest_estimate(estimate)`；`run_ingest(paths, config, skip_confirm=False) -> dict`

- [ ] **步骤 1: 编写 pipeline**

创建 `doubase/pipeline.py`:

```python
"""核心流水线：ingest 和 ask。"""

import hashlib
from pathlib import Path

from doubase.parsers import get_parser
from doubase.chunker.chunker import Chunker
from doubase.embedding import get_embedder
from doubase.storage.vector_store import VectorStore
from doubase.retrieval.retriever import Retriever
from doubase.generation import get_llm

from rich.console import Console
from rich.table import Table

console = Console()


def _hash_file(file_path: str) -> str:
    """计算文件内容的 SHA256 哈希。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files(paths: list[str]) -> list[str]:
    """展开目录为文件列表。"""
    all_files = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    all_files.append(str(f))
        elif path.is_file():
            all_files.append(str(path))
        else:
            console.print(f"[yellow]⚠️  路径不存在: {p}[/yellow]")
    return sorted(all_files)


def estimate_ingest(paths: list[str], config: dict) -> dict:
    """预扫描文件，估算 embedding 费用（不调用任何 API）。

    Returns:
        包含 files（各文件统计）、total_chunks、total_tokens、total_cost 的字典。
    """
    files = _collect_files(paths)
    chunker = Chunker(config.get("chunker", {}))
    pricing = config.get("pricing", {}).get("zhipu", {})
    embed_price = pricing.get("embed_price", 0.5)

    file_stats = []
    total_tokens = 0
    total_chunks = 0
    skipped_unsupported = []

    for file_path in files:
        parser = get_parser(file_path)
        if parser is None:
            skipped_unsupported.append(file_path)
            continue

        try:
            doc = parser.parse(file_path)
        except Exception:
            skipped_unsupported.append(file_path)
            continue

        content_hash = _hash_file(file_path)
        chunks = chunker.chunk_text(doc.text, file_path, content_hash)

        token_count = sum(len(chunker._encode(c.text)) for c in chunks)

        file_stats.append({
            "path": file_path,
            "size_kb": round(Path(file_path).stat().st_size / 1024, 1),
            "chunks": len(chunks),
            "tokens": token_count,
        })
        total_tokens += token_count
        total_chunks += len(chunks)

    total_cost = total_tokens / 1_000_000 * embed_price

    return {
        "files": file_stats,
        "skipped": skipped_unsupported,
        "total_chunks": total_chunks,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "embedding_provider": config["embedding"]["provider"],
        "embedding_model": config["embedding"].get(
            config["embedding"]["provider"], {}
        ).get("model", "unknown"),
    }


def display_ingest_estimate(estimate: dict):
    """展示 ingest 费用估算表格。"""
    console.print()
    console.print("[bold]═══ Ingest 预算估算 ═══[/bold]")
    console.print(
        f"Embedding 提供商: {estimate['embedding_provider']} "
        f"({estimate['embedding_model']})"
    )

    if estimate["files"]:
        table = Table(show_header=True, header_style="bold")
        table.add_column("文件", style="dim")
        table.add_column("大小", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("费用", justify="right")

        avg_cost_per_token = (
            estimate["total_cost"] / max(1, estimate["total_tokens"])
        )
        for f in estimate["files"]:
            file_cost = f["tokens"] * avg_cost_per_token
            table.add_row(
                f["path"],
                f"{f['size_kb']} KB",
                str(f["chunks"]),
                f"{f['tokens']:,}",
                f"¥{file_cost:.4f}",
            )

        table.add_section()
        table.add_row(
            "[bold]合计[/bold]",
            "",
            f"[bold]{estimate['total_chunks']}[/bold]",
            f"[bold]{estimate['total_tokens']:,}[/bold]",
            f"[bold]¥{estimate['total_cost']:.4f}[/bold]",
        )
        console.print(table)

    if estimate["skipped"]:
        console.print(
            f"\n[yellow]⚠️  跳过不支持的文件: "
            f"{len(estimate['skipped'])} 个[/yellow]"
        )


def run_ingest(paths: list[str], config: dict, skip_confirm: bool = False):
    """运行完整的 ingest 流水线：解析 → 哈希去重 → 分块 → embedding → 存储。

    Args:
        paths: 待导入的文件或目录列表。
        config: 完整配置字典。
        skip_confirm: True 时跳过确认提示。
    """
    # 阶段 1: 估算
    estimate = estimate_ingest(paths, config)
    display_ingest_estimate(estimate)

    # 阶段 2: 确认
    if not skip_confirm:
        try:
            answer = input("\n是否继续? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消[/yellow]")
            return
        if answer and answer not in ("y", "yes"):
            console.print("[yellow]已取消[/yellow]")
            return

    # 阶段 3: 执行
    results = {
        "success": [],
        "skipped_unchanged": [],
        "skipped_unsupported": [],
        "failed": [],
    }

    files = _collect_files(paths)
    chunker = Chunker(config.get("chunker", {}))
    embedder = get_embedder(config)
    store = VectorStore(
        persist_dir=config["storage"]["persist_dir"],
        collection_name=config["storage"]["collection_name"],
    )

    for file_path in files:
        parser = get_parser(file_path)
        if parser is None:
            results["skipped_unsupported"].append(file_path)
            console.print(f"  ⚠️  跳过 (不支持): {file_path}")
            continue

        # 去重检查
        content_hash = _hash_file(file_path)
        existing_hash = store.get_existing_hash(file_path)
        if existing_hash == content_hash:
            results["skipped_unchanged"].append(file_path)
            console.print(f"  ⏭️  跳过 (未变更): {file_path}")
            continue

        # 如果文件已变更，先删除旧 chunks
        if existing_hash is not None:
            store.delete_by_source(file_path)

        # 解析
        try:
            doc = parser.parse(file_path)
        except Exception as e:
            results["failed"].append({"path": file_path, "error": str(e)})
            console.print(f"  ❌ 解析失败: {file_path} ({e})")
            continue

        # 分块
        chunks = chunker.chunk_text(doc.text, file_path, content_hash)
        if not chunks:
            results["skipped_unchanged"].append(file_path)
            console.print(f"  ⏭️  跳过 (空文件): {file_path}")
            continue

        # Embedding
        try:
            embeddings = embedder.embed([c.text for c in chunks])
        except Exception as e:
            results["failed"].append(
                {"path": file_path, "error": f"embedding: {e}"}
            )
            console.print(f"  ❌ Embedding 失败: {file_path} ({e})")
            continue

        # 存储
        try:
            store.add_chunks_with_embeddings(chunks, embeddings)
        except Exception as e:
            results["failed"].append(
                {"path": file_path, "error": f"storage: {e}"}
            )
            console.print(f"  ❌ 存储失败: {file_path} ({e})")
            continue

        results["success"].append({"path": file_path, "chunks": len(chunks)})
        console.print(f"  ✅ 成功导入: {file_path} ({len(chunks)} chunks)")

    # 汇总
    console.print()
    console.print("[bold]doubase ingest 结果:[/bold]")
    console.print(
        f"  总计: {len(results['success'])} 成功, "
        f"{len(results['skipped_unchanged'])} 未变更, "
        f"{len(results['skipped_unsupported'])} 跳过, "
        f"{len(results['failed'])} 失败"
    )

    return results
```

- [ ] **步骤 2: 编写 pipeline 测试**

创建 `tests/test_pipeline.py`:

```python
import tempfile
import os
from pathlib import Path
from doubase.pipeline import _hash_file, _collect_files, estimate_ingest


def test_hash_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("hello world")
        f.flush()
        result = _hash_file(f.name)
        assert len(result) == 64
        os.unlink(f.name)


def test_collect_files_expands_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "a.md").write_text("a")
        Path(tmpdir, "b.docx").write_text("b")
        Path(tmpdir, "c.txt").write_text("c")
        files = _collect_files([tmpdir])
        assert len(files) == 3
        assert any("a.md" in f for f in files)


def test_estimate_ingest_with_markdown():
    config = {
        "chunker": {"chunk_size": 512, "chunk_overlap": 64},
        "embedding": {
            "provider": "zhipu",
            "zhipu": {
                "api_key": "test",
                "model": "embedding-2",
                "base_url": "https://test.com",
            },
        },
        "pricing": {"zhipu": {"embed_price": 0.5}},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        md_file = Path(tmpdir, "test.md")
        md_file.write_text("# Hello\n\n" + "This is a test. " * 20)
        est = estimate_ingest([str(md_file)], config)
        assert est["total_chunks"] >= 1
        assert est["total_tokens"] > 0
        assert est["total_cost"] >= 0
```

- [ ] **步骤 3: 运行测试确认通过**

执行: `pytest tests/test_pipeline.py -v`
预期: 3 PASS

- [ ] **步骤 4: 提交**

```bash
git add doubase/pipeline.py tests/test_pipeline.py
git commit -m "feat: 添加 ingest 流水线，包含哈希去重与确认流程"
```

---

### 任务 14: Ask Pipeline（RAG 提示词 + 生成）

**文件:**
- 修改: `doubase/pipeline.py` — 添加 ask 流水线函数
- 修改: `tests/test_pipeline.py` — 添加 ask 测试

**接口:**
- 消耗: Retriever, BaseLLM, config
- 产出: `_build_ask_prompt(question, chunks) -> list[dict]`；`run_ask(question, config, llm_override=None, embedding_override=None)` — 检索 chunks、构建混合提示词、流式输出 LLM 回答

- [ ] **步骤 1: 在 pipeline.py 中添加 ask 函数**

追加到 `doubase/pipeline.py`:

```python
def _build_ask_prompt(question: str, chunks: list[dict]) -> list[dict]:
    """构建混合 RAG 提示词：本地知识 + LLM 知识。"""
    system_prompt = """你是一个知识助手。请综合以下两个来源来回答用户问题:
1. 用户本地笔记中的相关内容 (见下文)
2. 你自己的通用知识

规则:
- 如果本地笔记有相关信息，优先引用，并注明来源文件路径
- 如果本地笔记没有覆盖的部分，用你自己的知识补充，并标注"[通用知识]"
- 不要编造本地笔记中不存在的内容
- 用中文回答"""

    user_parts = [question]
    if chunks:
        user_parts.append("\n---\n本地检索结果:")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source_path", "unknown")
            user_parts.append(f"\n[来源 {i}: {source}]\n{chunk['text']}")
    else:
        user_parts.append(
            "\n(本地笔记中未找到相关内容，请使用你的通用知识回答)"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def run_ask(
    question: str,
    config: dict,
    llm_override: str = None,
    embedding_override: str = None,
):
    """运行 RAG 问答流水线：检索 + 生成回答。

    Args:
        question: 用户问题。
        config: 完整配置字典。
        llm_override: 覆盖 LLM provider（如 "openai"）。
        embedding_override: 覆盖 embedding provider（如 "local"）。
    """
    top_k = config.get("retrieval", {}).get("top_k", 5)

    # 设置组件
    if embedding_override:
        embed_config = config.copy()
        embed_config["embedding"] = embed_config["embedding"].copy()
        embed_config["embedding"]["provider"] = embedding_override
        embedder = get_embedder(embed_config)
    else:
        embedder = get_embedder(config)

    store = VectorStore(
        persist_dir=config["storage"]["persist_dir"],
        collection_name=config["storage"]["collection_name"],
    )

    llm = get_llm(config, override_provider=llm_override)

    # 检查知识库是否为空
    if store.count() == 0:
        console.print(
            "[yellow]知识库为空。请先执行 doubase ingest 导入笔记。[/yellow]"
        )
        console.print("[dim]将仅使用 LLM 自身知识回答...[/dim]")
        chunks = []
    else:
        # 检索
        retriever = Retriever(embedder=embedder, vector_store=store)
        chunks = retriever.retrieve(question, top_k=top_k)

        if not chunks:
            console.print(
                "[dim]本地笔记中未找到相关内容，将仅使用通用知识回答。[/dim]"
            )
        else:
            console.print(f"[dim]检索到 {len(chunks)} 个相关片段[/dim]")

    # 构建提示词
    messages = _build_ask_prompt(question, chunks)

    # 流式输出回答
    console.print()
    try:
        for token in llm.chat_stream(messages):
            console.print(token, end="", highlight=False)
        console.print()
    except Exception as e:
        console.print(f"\n[red]❌ LLM 调用失败: {e}[/red]")
        console.print("[dim]请检查网络连接和 API Key 配置。[/dim]")
```

- [ ] **步骤 2: 在 test_pipeline.py 中添加 ask 测试**

追加到 `tests/test_pipeline.py`:

```python
from doubase.pipeline import _build_ask_prompt


def test_build_ask_prompt_with_chunks():
    chunks = [
        {
            "text": "Redis 使用 RDB 快照",
            "source_path": "/notes/redis.md",
            "distance": 0.1,
        },
        {
            "text": "AOF 记录每次写操作",
            "source_path": "/notes/db.md",
            "distance": 0.2,
        },
    ]
    messages = _build_ask_prompt("Redis 如何持久化数据？", chunks)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "本地笔记" in messages[0]["content"]
    assert "/notes/redis.md" in messages[1]["content"]
    assert "/notes/db.md" in messages[1]["content"]
    assert "Redis 使用 RDB" in messages[1]["content"]


def test_build_ask_prompt_empty_chunks():
    messages = _build_ask_prompt("某个问题", [])
    assert len(messages) == 2
    assert "未找到相关内容" in messages[1]["content"]
    assert "通用知识" in messages[0]["content"]
```

- [ ] **步骤 3: 运行测试确认通过**

执行: `pytest tests/test_pipeline.py -v`
预期: 5 PASS（之前的 3 + 新增 2）

- [ ] **步骤 4: 提交**

```bash
git add doubase/pipeline.py tests/test_pipeline.py
git commit -m "feat: 添加 ask 流水线，支持混合 RAG 提示词与流式输出"
```

---

### 任务 15: Analyzer — 项目扫描器

**文件:**
- 创建: `doubase/analyzer/__init__.py`
- 创建: `doubase/analyzer/scanner.py`
- 创建: `tests/test_analyzer/__init__.py`
- 创建: `tests/test_analyzer/test_scanner.py`
- 创建: `tests/test_analyzer/fixtures/mini_project/__init__.py`
- 创建: `tests/test_analyzer/fixtures/mini_project/core/engine.py`
- 创建: `tests/test_analyzer/fixtures/mini_project/utils/helper.py`

**接口:**
- 消耗: 无（除 Python 标准库外）
- 产出: `scan_project(project_dir: str, focus: str = None) -> list[dict]` — 返回按重要性排序的文件列表，每个元素包含 `{"path", "content", "language", "score"}`

- [ ] **步骤 1: 编写扫描器**

创建 `doubase/analyzer/__init__.py`:

```python
"""代码分析器 — 扫描、分析并总结外部项目。"""
```

创建 `doubase/analyzer/scanner.py`:

```python
"""项目扫描器 — 发现源码文件并按重要性排序。"""

import os
from pathlib import Path

EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", "vendor",
    ".venv", "venv", "env", ".tox", ".eggs",
    "__MACOSX", ".DS_Store",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cc", ".cs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".clj",
    ".ex", ".exs", ".erl", ".hrl",
}

NAME_KEYWORDS = {
    "algorithm": 1.0, "algo": 1.0,
    "core": 0.9, "engine": 0.9,
    "main": 0.8,
    "init": 0.5,
    "utils": 0.3, "helper": 0.3, "helpers": 0.3,
}

PATH_KEYWORDS = {
    "src": 0.8, "lib": 0.8, "core": 0.85,
    "include": 0.7,
    "tests": 0.2, "test": 0.2, "spec": 0.2,
    "vendor": 0.1, "node_modules": 0.0,
}

DEFAULT_NAME_SCORE = 0.5
DEFAULT_PATH_SCORE = 0.5
MAX_FILES = 50
LARGE_PROJECT_THRESHOLD = 500


def _score_name(file_path: str) -> float:
    stem = Path(file_path).stem.lower()
    for keyword, score in NAME_KEYWORDS.items():
        if keyword in stem:
            return score
    return DEFAULT_NAME_SCORE


def _score_path(file_path: str, project_root: str, focus_dir: str = None) -> float:
    rel = Path(file_path).relative_to(project_root)
    parts = rel.parts[:-1]

    if focus_dir:
        focus_parts = Path(focus_dir).parts
        if all(p in parts for p in focus_parts):
            return 1.0

    if not parts:
        return 0.6

    scores = [PATH_KEYWORDS.get(p.lower(), DEFAULT_PATH_SCORE) for p in parts]
    return sum(scores) / len(scores) if scores else DEFAULT_PATH_SCORE


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx",
        ".go": "go", ".rs": "rust", ".java": "java",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".cs": "csharp", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".kt": "kotlin",
    }
    return lang_map.get(ext, "unknown")


def scan_project(project_dir: str, focus: str = None) -> list[dict]:
    """扫描项目目录，返回按重要性排序的重要源文件列表。

    Args:
        project_dir: 项目根目录路径。
        focus: 可选的优先子目录。

    Returns:
        包含 path, content, language, score 的 dict 列表，按 score 降序排列。
    """
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"项目目录未找到: {project_dir}")

    if focus:
        focus_path = (root / focus).resolve()
        if not focus_path.exists():
            raise FileNotFoundError(f"Focus 目录未找到: {focus_path}")

    file_entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in SOURCE_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, fname)
            file_entries.append(full_path)

    raw_entries = []
    max_len = 0
    for fpath in file_entries:
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            raw_entries.append((fpath, content))
            max_len = max(max_len, len(content))
        except Exception:
            continue

    scored_files = []
    for fpath, content in raw_entries:
        length_score = len(content) / max(1, max_len)
        name_score = _score_name(fpath)
        path_score = _score_path(fpath, str(root), focus)
        total = 0.3 * length_score + 0.4 * name_score + 0.3 * path_score

        scored_files.append({
            "path": fpath,
            "content": content,
            "language": _detect_language(fpath),
            "score": round(total, 4),
        })

    scored_files.sort(key=lambda x: x["score"], reverse=True)

    if len(scored_files) > MAX_FILES and len(file_entries) > LARGE_PROJECT_THRESHOLD:
        scored_files = scored_files[:MAX_FILES]

    return scored_files
```

- [ ] **步骤 2: 编写测试夹具**

创建 `tests/test_analyzer/fixtures/mini_project/__init__.py`（空文件）

创建 `tests/test_analyzer/fixtures/mini_project/core/engine.py`:

```python
"""核心引擎模块。"""

class Engine:
    def __init__(self):
        self._queue = []

    def process(self, data):
        result = self._transform(data)
        return self._validate(result)

    def _transform(self, data):
        return [item * 2 for item in data]

    def _validate(self, data):
        return all(isinstance(item, int) for item in data)
```

创建 `tests/test_analyzer/fixtures/mini_project/utils/helper.py`:

```python
"""工具辅助函数。"""

def format_output(data):
    return str(data).strip()

def parse_input(raw):
    return raw.split(",")
```

- [ ] **步骤 3: 编写扫描器测试**

创建 `tests/test_analyzer/test_scanner.py`:

```python
from pathlib import Path
from doubase.analyzer.scanner import scan_project, _score_name

FIXTURES = Path(__file__).parent / "fixtures"


def test_score_name_core():
    assert _score_name("src/core/engine.py") >= 0.9


def test_score_name_utils():
    assert _score_name("/path/to/utils.py") == 0.3


def test_score_name_default():
    assert _score_name("unknown_file.py") == 0.5


def test_scan_project_finds_files():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project)
    assert len(results) >= 2
    paths = [r["path"] for r in results]
    assert any("engine.py" in p for p in paths)
    assert any("helper.py" in p for p in paths)


def test_scan_project_sorts_by_score():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_scan_project_with_focus():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project, focus="core")
    assert len(results) >= 2
    if len(results) >= 2:
        top_paths = [r["path"] for r in results[:2]]
        assert any("core" in p for p in top_paths)
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `pytest tests/test_analyzer/test_scanner.py -v`
预期: 6 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/analyzer/ tests/test_analyzer/
git commit -m "feat: 添加项目扫描器，支持重要性排序"
```

---

### 任务 16: Analyzer — 代码分析器 + 写入器 + Analyze Pipeline

**文件:**
- 创建: `doubase/analyzer/analyzer.py`
- 创建: `doubase/analyzer/writer.py`
- 修改: `doubase/pipeline.py` — 添加 analyze 流水线

**接口:**
- 消耗: scanner, LLM, embedder, vector store, config
- 产出: `estimate_analyze(project_dir, config, focus=None) -> dict`；`run_analyze(project_dir, config, focus=None, skip_confirm=False)` — 扫描 → LLM 逐文件分析 → 写入 .md → 入库

- [ ] **步骤 1: 编写 analyzer.py**

创建 `doubase/analyzer/analyzer.py`:

```python
"""代码分析器 — 使用 LLM 分析源码文件。"""

from doubase.generation.base import BaseLLM

ANALYSIS_PROMPT_TEMPLATE = """分析以下代码文件，识别并总结:

1. 核心算法 — 描述算法思路、时间/空间复杂度
2. 关键数据结构 — 重要的类、结构体、接口及其用途
3. 设计模式 — 使用了哪些设计模式
4. 对外接口 — 公开的函数/方法及其签名和用途
5. 依赖关系 — 模块间依赖

用简洁的中文回答，使用 Markdown 格式。

文件路径: {file_path}
语言: {language}

代码:
```
{code}
```"""

SYNTHESIS_PROMPT_TEMPLATE = """以下是对项目 "{project_name}" 各文件的逐一分析:

{file_analyses}

请撰写一份项目整体综述，包含:
1. 项目架构概述 — 整体结构、分层设计
2. 核心算法一览 — 列出所有核心算法及其所在文件
3. 模块间调用关系 — 描述主要模块之间的依赖和调用关系

用简洁的中文回答，使用 Markdown 格式。"""


def build_analysis_prompt(file_path: str, code: str, language: str) -> list[dict]:
    """构建单文件分析提示词。"""
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        file_path=file_path,
        language=language,
        code=code[:8000],
    )
    return [{"role": "user", "content": prompt}]


def analyze_file(llm: BaseLLM, file_path: str, code: str, language: str) -> str:
    """分析单个文件，返回 Markdown 总结。"""
    messages = build_analysis_prompt(file_path, code, language)
    return llm.chat(messages)


def synthesize_overview(
    llm: BaseLLM,
    project_name: str,
    file_analyses: list[dict],
) -> str:
    """将各文件分析结果合成为项目综述。

    Args:
        project_name: 项目名称。
        file_analyses: {"file": str, "analysis": str} 列表。

    Returns:
        Markdown 格式的综述文本。
    """
    combined = "\n\n---\n\n".join(
        f"### {fa['file']}\n{fa['analysis']}" for fa in file_analyses
    )
    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        project_name=project_name,
        file_analyses=combined,
    )
    messages = [{"role": "user", "content": prompt}]
    return llm.chat(messages)
```

- [ ] **步骤 2: 编写 writer.py**

创建 `doubase/analyzer/writer.py`:

```python
"""写入器 — 从分析结果生成 Markdown 总结文件。"""

from datetime import datetime, timezone
from pathlib import Path


def write_summary(
    output_dir: str,
    project_name: str,
    project_source: str,
    file_path: str,
    language: str,
    analysis_text: str,
) -> str:
    """将单文件分析结果写入 Markdown 文件。"""
    out = Path(output_dir) / project_name
    out.mkdir(parents=True, exist_ok=True)

    rel = Path(file_path).relative_to(project_source)
    safe_name = str(rel).replace("/", "_").replace("\\", "_").replace(".", "_")
    md_file = out / f"{safe_name}.md"

    frontmatter = f"""---
project: {project_name}
source_path: {file_path}
analyzed_at: {datetime.now(timezone.utc).isoformat()}
language: {language}
---"""

    content = f"{frontmatter}\n\n{analysis_text}"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file.resolve())


def write_overview(
    output_dir: str,
    project_name: str,
    project_source: str,
    overview_text: str,
) -> str:
    """将项目综述写入 overview.md。"""
    out = Path(output_dir) / project_name
    out.mkdir(parents=True, exist_ok=True)

    md_file = out / "overview.md"
    frontmatter = f"""---
project: {project_name}
source_path: {project_source}
analyzed_at: {datetime.now(timezone.utc).isoformat()}
type: overview
---"""

    content = f"{frontmatter}\n\n{overview_text}"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file.resolve())
```

- [ ] **步骤 3: 在 pipeline.py 中添加 analyze 流水线**

在 `doubase/pipeline.py` 顶部添加导入:

```python
from doubase.analyzer.scanner import scan_project
```

追加到 `doubase/pipeline.py`:

```python
def estimate_analyze(project_dir: str, config: dict, focus: str = None) -> dict:
    """估算项目分析的费用（不调用任何付费 API）。"""
    files = scan_project(project_dir, focus=focus)
    llm_provider = config["llm"]["provider"]
    pricing = config.get("pricing", {}).get(llm_provider, {})
    input_price = pricing.get("input_price", 1.0)
    output_price = pricing.get("output_price", 2.0)
    embed_price = (
        config.get("pricing", {}).get("zhipu", {}).get("embed_price", 0.5)
    )

    chunker = Chunker(config.get("chunker", {}))
    total_llm_input = 0
    total_llm_output = 0
    file_estimates = []

    for f in files:
        code_tokens = len(chunker._encode(f["content"]))
        input_tokens = 200 + code_tokens
        output_tokens = int(input_tokens * 0.3)
        total_llm_input += input_tokens
        total_llm_output += output_tokens
        file_estimates.append({
            "path": f["path"],
            "size_kb": round(len(f["content"]) / 1024, 1),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    synthesis_input = total_llm_output + 2000
    synthesis_output = 2000
    total_llm_input += synthesis_input
    total_llm_output += synthesis_output

    llm_cost = (
        total_llm_input * input_price + total_llm_output * output_price
    ) / 1_000_000

    total_embed_tokens = total_llm_output
    embed_cost = total_embed_tokens / 1_000_000 * embed_price

    return {
        "project_dir": project_dir,
        "project_name": Path(project_dir).name,
        "total_files": len(file_estimates),
        "scanned_total": len(files),
        "file_estimates": file_estimates,
        "total_llm_input": total_llm_input,
        "total_llm_output": total_llm_output,
        "llm_cost": llm_cost,
        "total_embed_tokens": total_embed_tokens,
        "embed_cost": embed_cost,
        "total_cost": llm_cost + embed_cost,
        "llm_provider": llm_provider,
        "llm_model": config["llm"][llm_provider]["model"],
        "embedding_provider": config["embedding"]["provider"],
    }


def display_analyze_estimate(estimate: dict):
    """展示 analyze 费用估算表格。"""
    console.print()
    console.print("[bold]═══ Analyze 预算估算 ═══[/bold]")
    console.print(f"项目: {estimate['project_name']}")
    console.print(
        f"源码文件: {estimate['scanned_total']} 个 -> "
        f"重要性排序后选取 {estimate['total_files']} 个"
    )
    console.print(
        f"LLM: {estimate['llm_provider']} ({estimate['llm_model']}) | "
        f"Embedding: {estimate['embedding_provider']}"
    )

    console.print("\n[bold]—— LLM 分析花费 ——[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("文件", style="dim")
    table.add_column("代码量", justify="right")
    table.add_column("预估输入", justify="right")
    table.add_column("预估输出", justify="right")
    table.add_column("费用", justify="right")

    total_file_tokens = sum(
        fe["input_tokens"] + fe["output_tokens"]
        for fe in estimate["file_estimates"]
    )
    for fe in estimate["file_estimates"][:20]:
        proportion = (fe["input_tokens"] + fe["output_tokens"]) / max(1, total_file_tokens)
        file_cost = estimate["llm_cost"] * proportion * 0.85
        table.add_row(
            fe["path"][-50:],
            f"{fe['size_kb']} KB",
            f"{fe['input_tokens']:,} tk",
            f"{fe['output_tokens']:,} tk",
            f"¥{file_cost:.4f}",
        )

    if len(estimate["file_estimates"]) > 20:
        table.add_row("...", "...", "...", "...", "...")

    table.add_section()
    table.add_row(
        "[bold]LLM 小计[/bold]",
        "-",
        f"[bold]{estimate['total_llm_input']:,} tk[/bold]",
        f"[bold]{estimate['total_llm_output']:,} tk[/bold]",
        f"[bold]¥{estimate['llm_cost']:.4f}[/bold]",
    )
    console.print(table)

    console.print(f"\n[bold]—— Embedding 入库花费 ——[/bold]")
    console.print(
        f"生成 .md 总结 -> 约 {estimate['total_embed_tokens']:,} tokens -> "
        f"¥{estimate['embed_cost']:.4f}"
    )

    total = estimate['total_cost']
    console.print(
        f"\n[bold green]💰 总花费预估: ¥{total:.4f} "
        f"(LLM ¥{estimate['llm_cost']:.4f} + Embedding ¥{estimate['embed_cost']:.4f})"
        f"[/bold green]"
    )


def run_analyze(
    project_dir: str,
    config: dict,
    focus: str = None,
    skip_confirm: bool = False,
):
    """运行完整的 analyze 流水线：扫描 -> 分析 -> 写入 -> 入库。

    Args:
        project_dir: 待分析项目路径。
        config: 完整配置字典。
        focus: 可选的优先子目录。
        skip_confirm: True 时跳过确认提示。
    """
    from doubase.analyzer.analyzer import analyze_file, synthesize_overview
    from doubase.analyzer.writer import write_summary, write_overview

    # 阶段 1: 估算
    estimate = estimate_analyze(project_dir, config, focus)
    display_analyze_estimate(estimate)

    # 阶段 2: 确认
    if not skip_confirm:
        try:
            answer = input("\n是否继续? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消[/yellow]")
            return
        if answer and answer not in ("y", "yes"):
            console.print("[yellow]已取消[/yellow]")
            return

    # 阶段 3: 执行
    project_name = Path(project_dir).expanduser().resolve().name
    output_dir = str(
        Path(project_dir).expanduser().resolve().parent / "doubase_summaries"
    )
    project_source = str(Path(project_dir).expanduser().resolve())

    files = scan_project(project_dir, focus=focus)
    llm = get_llm(config)

    console.print(f"\n[bold]分析 {len(files)} 个文件...[/bold]")

    file_analyses = []
    success_count = 0
    fail_count = 0

    for i, f in enumerate(files, 1):
        console.print(f"  [{i}/{len(files)}] {f['path'][-60:]}")
        try:
            analysis = analyze_file(
                llm, f["path"], f["content"], f["language"]
            )
            write_summary(
                output_dir, project_name, project_source,
                f["path"], f["language"], analysis,
            )
            file_analyses.append({"file": f["path"], "analysis": analysis})
            success_count += 1
        except Exception as e:
            console.print(f"    [red]❌ 失败: {e}[/red]")
            fail_count += 1
            continue

    # 综述
    console.print(f"\n[bold]生成项目综述...[/bold]")
    try:
        overview = synthesize_overview(llm, project_name, file_analyses)
        overview_path = write_overview(
            output_dir, project_name, project_source, overview
        )
        console.print(f"  ✅ 综述已保存: {overview_path}")
    except Exception as e:
        console.print(f"  [red]❌ 综述生成失败: {e}[/red]")

    # 将分析结果入库
    console.print(f"\n[bold]将分析结果导入知识库...[/bold]")
    summary_dir = Path(output_dir) / project_name
    if summary_dir.exists():
        summary_files = list(summary_dir.glob("*.md"))
        if summary_files:
            try:
                run_ingest(
                    [str(s) for s in summary_files], config, skip_confirm=True
                )
            except Exception as e:
                console.print(f"  [red]❌ 导入失败: {e}[/red]")

    console.print(f"\n[bold]doubase analyze 结果:[/bold]")
    console.print(f"  ✅ 分析成功: {success_count} 个文件")
    if fail_count:
        console.print(f"  ❌ 分析失败: {fail_count} 个文件")
    console.print(f"  📁 总结文件: {output_dir}/{project_name}/")
```

- [ ] **步骤 4: 添加 estimate_analyze 测试**

追加到 `tests/test_pipeline.py`:

```python
from doubase.pipeline import estimate_analyze


def test_estimate_analyze():
    config = {
        "llm": {
            "provider": "deepseek",
            "deepseek": {
                "api_key": "test",
                "model": "deepseek-chat",
                "base_url": "https://test.com",
            },
        },
        "embedding": {
            "provider": "zhipu",
            "zhipu": {
                "api_key": "test",
                "model": "embedding-2",
                "base_url": "https://test.com",
            },
        },
        "pricing": {
            "deepseek": {"input_price": 1.0, "output_price": 2.0},
            "zhipu": {"embed_price": 0.5},
        },
        "chunker": {"chunk_size": 512, "chunk_overlap": 64},
    }
    est = estimate_analyze(
        "tests/test_analyzer/fixtures/mini_project", config
    )
    assert est["total_files"] >= 2
    assert est["total_llm_input"] > 0
    assert est["total_llm_output"] > 0
    assert est["total_cost"] > 0
```

- [ ] **步骤 5: 运行测试**

执行: `pytest tests/test_pipeline.py -v`
预期: 6 PASS（之前的 5 + 新增）

- [ ] **步骤 6: 提交**

```bash
git add doubase/analyzer/analyzer.py doubase/analyzer/writer.py doubase/pipeline.py tests/test_pipeline.py
git commit -m "feat: 添加代码分析器、写入器与 analyze 流水线"
```

---

### 任务 17: CLI（全部命令）

**文件:**
- 创建: `doubase/cli.py`

**接口:**
- 消耗: 所有流水线函数、config
- 产出: `main()` — 基于 argparse 的 CLI，包含 `ask`、`ingest`、`analyze` 子命令

- [ ] **步骤 1: 编写 CLI**

创建 `doubase/cli.py`:

```python
"""CLI 入口 — 基于 argparse 的命令路由。"""

import argparse
import sys

from doubase.config import load_config
from doubase.pipeline import run_ingest, run_ask, run_analyze


def main():
    parser = argparse.ArgumentParser(
        prog="doubase",
        description="本地 RAG agent，支持笔记检索与代码分析",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # --- ask ---
    ask_parser = subparsers.add_parser("ask", help="提问（RAG + LLM）")
    ask_parser.add_argument("question", help="你的问题")
    ask_parser.add_argument(
        "--llm", help="覆盖 LLM provider（deepseek, openai, openai_compat）"
    )
    ask_parser.add_argument(
        "--embedding", help="覆盖 embedding provider（zhipu, local）"
    )

    # --- ingest ---
    ingest_parser = subparsers.add_parser("ingest", help="导入文档到知识库")
    ingest_parser.add_argument("paths", nargs="+", help="待导入的文件或目录")
    ingest_parser.add_argument(
        "--yes", "-y", action="store_true", help="跳过确认提示"
    )
    ingest_parser.add_argument(
        "--watch", "-w", action="store_true", help="监控目录，自动导入新文件"
    )

    # --- analyze ---
    analyze_parser = subparsers.add_parser(
        "analyze", help="分析代码项目并将结果入库"
    )
    analyze_parser.add_argument("project", help="项目目录路径")
    analyze_parser.add_argument(
        "--focus", "-f", help="优先分析的子目录"
    )
    analyze_parser.add_argument(
        "--yes", "-y", action="store_true", help="跳过确认提示"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # 加载配置
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    # 路由命令
    if args.command == "ask":
        run_ask(
            question=args.question,
            config=config,
            llm_override=args.llm,
            embedding_override=args.embedding,
        )

    elif args.command == "ingest":
        if args.watch:
            from doubase.watch import run_watch
            run_watch(config)
        else:
            run_ingest(
                paths=args.paths,
                config=config,
                skip_confirm=args.yes,
            )

    elif args.command == "analyze":
        run_analyze(
            project_dir=args.project,
            config=config,
            focus=args.focus,
            skip_confirm=args.yes,
        )


if __name__ == "__main__":
    main()
```

- [ ] **步骤 2: 验证 CLI 入口**

执行: `doubase --help`
预期: 打印帮助信息，包含 ask、ingest、analyze 子命令

- [ ] **步骤 3: 提交**

```bash
git add doubase/cli.py
git commit -m "feat: 添加 CLI，包含 ask、ingest、analyze 子命令"
```

---

### 任务 18: Watch 监控模式

**文件:**
- 创建: `doubase/watch.py`

**接口:**
- 消耗: config, pipeline 中的 run_ingest
- 产出: `run_watch(config: dict)` — 启动 watchdog 观察者，自动处理新文件

- [ ] **步骤 1: 编写 watch.py**

创建 `doubase/watch.py`:

```python
"""监控模式 — 监控目录中的新文件并自动导入。"""

import time
from pathlib import Path

from rich.console import Console

console = Console()


def run_watch(config: dict):
    """启动监控目录，自动导入新增的 .md/.docx/.pdf 文件。"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        console.print(
            "[red]watchdog 库未安装。请执行: pip install watchdog[/red]"
        )
        return

    watch_dir = config.get("watch", {}).get("inbox_dir", "~/Documents/inbox")
    watch_path = Path(watch_dir).expanduser().resolve()
    watch_path.mkdir(parents=True, exist_ok=True)

    processed = set()

    class IngestHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            file_path = event.src_path
            ext = Path(file_path).suffix.lower()
            if ext not in (".md", ".docx", ".pdf"):
                return

            if file_path in processed:
                return
            processed.add(file_path)

            time.sleep(1)

            console.print(f"\n[bold]📥 检测到新文件: {file_path}[/bold]")
            from doubase.pipeline import run_ingest
            try:
                run_ingest([file_path], config, skip_confirm=True)
            except Exception as e:
                console.print(f"[red]❌ 导入失败: {e}[/red]")

    observer = Observer()
    observer.schedule(IngestHandler(), str(watch_path), recursive=True)
    observer.start()

    console.print(f"[bold]👀 正在监控目录: {watch_path}[/bold]")
    console.print("[dim]支持: .md / .docx / .pdf  按 Ctrl+C 停止[/dim]")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]监控已停止[/yellow]")

    observer.join()
```

- [ ] **步骤 2: 提交**

```bash
git add doubase/watch.py
git commit -m "feat: 添加 watch 模式，监控目录自动导入新文件"
```

---

### 任务 19: 集成测试 + 冒烟测试

**文件:**
- 创建: `tests/test_cli.py`
- 创建: `tests/conftest.py`

**接口:**
- 使用真实 parser/chunker/ChromaDB 和 mock LLM/Embedder 进行 CLI 端到端测试

- [ ] **步骤 1: 编写 conftest.py**

创建 `tests/conftest.py`:

```python
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def temp_config():
    """创建包含测试配置的临时目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        vectors_dir = Path(tmpdir) / "vectors"
        vectors_dir.mkdir()

        config_content = f"""
llm:
  provider: deepseek
  deepseek:
    api_key: test-key
    model: deepseek-chat
    base_url: https://api.deepseek.com/v1

embedding:
  provider: zhipu
  zhipu:
    api_key: test-key
    model: embedding-2
    base_url: https://open.bigmodel.cn/api/paas/v4

storage:
  persist_dir: {vectors_dir}
  collection_name: test_notes

chunker:
  chunk_size: 100
  chunk_overlap: 20

retrieval:
  top_k: 3

pricing:
  deepseek:
    input_price: 1.0
    output_price: 2.0
  zhipu:
    embed_price: 0.5
"""
        config_path.write_text(config_content)
        yield str(config_path)
```

- [ ] **步骤 2: 编写 CLI 测试**

创建 `tests/test_cli.py`:

```python
import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "ask" in result.stdout
    assert "ingest" in result.stdout
    assert "analyze" in result.stdout


def test_cli_ask_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "ask", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_ingest_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "ingest", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_analyze_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "analyze", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_no_command_shows_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
```

- [ ] **步骤 3: 运行集成测试**

执行: `pytest tests/test_cli.py -v`
预期: 5 PASS

- [ ] **步骤 4: 运行全部测试**

执行: `pytest tests/ -v`
预期: 所有测试通过

- [ ] **步骤 5: 提交**

```bash
git add tests/conftest.py tests/test_cli.py
git commit -m "test: 添加 CLI 集成测试与 conftest 夹具"
```

---

### 任务 20: README 完善 + 最终集成验证

**文件:**
- 修改: `README.md`

**接口:**
- 无（仅文档）

- [ ] **步骤 1: 更新 README.md**

替换 `README.md` 为:

```markdown
# DouBase 🧠

本地 RAG CLI 工具，用于个人知识管理与代码分析。

## 功能

- **RAG 问答** — 提问，结合本地笔记 + LLM 知识给出混合回答
- **文档导入** — 导入 `.md`、`.docx`、`.pdf` 文件到 ChromaDB 向量库
- **代码分析** — 分析外部项目，自动生成 Markdown 总结并入库
- **费用估算** — 在调用任何付费 API 前展示花费预估，确认后执行
- **监控模式** — 自动导入放入监控目录的新文件
- **提供商切换** — LLM 可切换 DeepSeek/OpenAI，Embedding 可切换智谱/本地

## 快速开始

### 1. 安装

```bash
cd DouBase
pip install -e .

# 可选：本地 embedding 模型
pip install -e ".[local-embed]"
```

### 2. 设置 API Key

```bash
export DEEPSEEK_API_KEY=sk-你的-deepseek-key
export ZHIPU_API_KEY=你的-智谱-key
```

### 3. 导入你的笔记

```bash
# 导入整个目录
doubase ingest ~/Documents/Obsidian/

# 导入特定文件
doubase ingest notes.md report.docx paper.pdf

# 跳过确认
doubase ingest ~/notes/ --yes

# 监控目录，自动导入新文件
doubase ingest --watch ~/Documents/inbox/
```

### 4. 提问

```bash
doubase ask "Redis 持久化原理是什么？"
doubase ask "什么是梯度下降？"
doubase ask "解释 Transformer 注意力机制" --llm openai
```

### 5. 分析代码项目

```bash
doubase analyze ~/projects/some-repo/
doubase analyze ~/projects/some-repo/ --focus src/core/
doubase analyze ~/projects/some-repo/ --yes
```

## 配置

编辑 `config.yaml` 切换提供商、模型、分块大小等。

```yaml
llm:
  provider: deepseek  # 可改为 openai 或 openai_compat

embedding:
  provider: zhipu     # 可改为 local 使用离线 embedding

retrieval:
  top_k: 5            # 检索返回的 chunk 数量

pricing:
  deepseek:
    input_price: 1.0   # 人民币/百万 tokens
    output_price: 2.0
```

## 架构

```
Ingest 流水线:   解析器 → 哈希去重 → 分块器 → Embedder → ChromaDB
Ask 流水线:      查询 → Embed → 检索 top-K → 混合提示词 → LLM → 回答
Analyze 流水线:  扫描器 → LLM 分析 → 写入器 (.md) → Ingest 流水线
```

## 技术栈

- Python 3.11+、ChromaDB、OpenAI SDK
- python-docx（Word）、PyMuPDF（PDF）、tiktoken（token 计数）
- rich（终端美化输出）、watchdog（文件监控）

## 许可证

MIT
```

- [ ] **步骤 2: 最终验证**

执行完整测试套件:
```bash
pip install -e .
pytest tests/ -v
```

预期: 所有测试通过（20+ 个测试，覆盖所有模块）

- [ ] **步骤 3: 快速冒烟测试**

```bash
# 无需 API key 即可运行（会展示估算，然后在实际 API 调用时优雅失败）
doubase --help
doubase ask --help
doubase ingest --help
doubase analyze --help
```

- [ ] **步骤 4: 最终提交**

```bash
git add README.md
git commit -m "docs: 完善 README，添加完整使用指南"
```

---

## 实现注意事项

1. **任务间依赖:** 严格按顺序执行。任务 13 之前不得编写 pipeline.py，因为它依赖所有上游模块。
2. **测试优先:** 每个任务先编写失败测试，验证失败后再编写实现。
3. **ChromaDB 注意:** 测试中使用 `TemporaryDirectory` 确保每次测试数据隔离。
4. **API Key 安全:** 测试使用 mock，config 中的 API key 是占位符，不会发起真正的网络请求。
5. **pipeline.py 导入:** 任务 16 完成后，确保 `pipeline.py` 顶部有正确的导入顺序（特别是 `from doubase.analyzer.scanner import scan_project`）。
