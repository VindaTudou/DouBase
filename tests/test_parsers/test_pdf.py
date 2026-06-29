import tempfile
from doubase.parsers.pdf import PdfParser


def _create_test_pdf(path: str):
    import fitz  # PyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 72), "你好 PDF", fontsize=14, fontname="china-s")
    page.insert_text(fitz.Point(72, 100), "这是一个测试 PDF 文档。", fontsize=12, fontname="china-s")
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
