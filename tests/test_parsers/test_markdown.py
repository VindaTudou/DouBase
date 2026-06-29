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
