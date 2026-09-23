"""格式解析与识别。"""

from __future__ import annotations

import pytest

from docmorph.formats import Format, detect_format, parse_format


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pdf", Format.PDF),
        ("PDF", Format.PDF),
        (".docx", Format.DOCX),
        (" markdown ", Format.MD),
        ("htm", Format.HTML),
        ("text", Format.TXT),
        ("ppt", Format.PPTX),
        (Format.CSV, Format.CSV),
    ],
)
def test_parse_format_accepts_aliases(value, expected):
    assert parse_format(value) is expected


@pytest.mark.parametrize("value", [None, "", "   ", "rar", "unknown"])
def test_parse_format_rejects_unknown(value):
    assert parse_format(value) is None


def test_detect_format_from_suffix(tmp_path):
    assert detect_format(tmp_path / "a.PDF") is Format.PDF
    assert detect_format(tmp_path / "b.tar.gz") is None


def test_txt_maps_to_pandoc_plain_writer():
    """回归：pandoc 没有 txt 目标格式，必须映射为 plain。"""
    from docmorph.formats import PANDOC_READER, PANDOC_WRITER

    assert PANDOC_WRITER[Format.TXT] == "plain"
    assert "txt" not in PANDOC_WRITER.values()
    assert PANDOC_READER[Format.TXT] == "markdown"
