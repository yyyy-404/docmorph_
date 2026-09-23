"""Office COM 真实转换（缺 Word/Excel 时自动跳过）。

这些用例会启动 Word/Excel，比较慢，因此只覆盖最关键的 PDF 导出路径。
"""

from __future__ import annotations

import pytest

from docmorph.results import ConflictPolicy
from tests.conftest import OFFICE_SKIP

pytestmark = [OFFICE_SKIP, pytest.mark.slow]


def convert(engine, source, target_format, tmp_path, name: str):
    from docmorph.engine import make_request

    destination = tmp_path / f"{name}.{target_format}"
    request = make_request(
        source,
        destination,
        target_format,
        settings=engine.settings,
        conflict=ConflictPolicy.OVERWRITE,
    )
    return engine.convert(request)


def pdf_pages(path) -> int:
    from docmorph.backends.python_backend import import_pymupdf

    with import_pymupdf().open(str(path)) as document:
        return document.page_count


def test_docx_to_pdf_via_word(engine, samples, tmp_path):
    result = convert(engine, samples["docx"], "pdf", tmp_path, "word_out")
    assert result.ok, result.error
    assert result.backend == "word"
    assert result.primary_output.stat().st_size > 1000
    assert pdf_pages(result.primary_output) >= 1


def test_markdown_to_pdf_uses_chain(engine, samples, tmp_path):
    result = convert(engine, samples["md"], "pdf", tmp_path, "md_pdf")
    assert result.ok, result.error
    assert result.backend == "pandoc + word"
    assert pdf_pages(result.primary_output) >= 1


def test_html_to_pdf_via_word(engine, samples, tmp_path):
    result = convert(engine, samples["html"], "pdf", tmp_path, "html_pdf")
    assert result.ok, result.error
    assert pdf_pages(result.primary_output) >= 1


def test_pdf_roundtrip_keeps_text(engine, samples, tmp_path):
    """docx → pdf → txt：验证 Word 渲染出来的 PDF 也能被回读。"""
    pdf = convert(engine, samples["docx"], "pdf", tmp_path, "roundtrip")
    assert pdf.ok, pdf.error
    text = convert(engine, pdf.primary_output, "txt", tmp_path, "roundtrip_txt")
    assert text.ok, text.error
    content = text.primary_output.read_text(encoding="utf-8")
    assert content.strip()
