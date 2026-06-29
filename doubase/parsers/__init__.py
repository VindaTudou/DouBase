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
