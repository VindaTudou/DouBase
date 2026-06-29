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
