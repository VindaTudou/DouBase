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
