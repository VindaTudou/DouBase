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
