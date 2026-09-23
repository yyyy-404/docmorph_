"""文档格式定义、别名归一化与扩展名识别。

集中处理"用户写的格式名"与"库要求的格式名"之间的差异，例如：

* 用户会说 ``txt``，而 pandoc 的输出格式名是 ``plain``（输入侧用 ``markdown``）；
* 用户会说 ``htm`` / ``markdown`` / ``jpeg`` 这类别名。

把这类映射收在这里，避免散落到各个后端。
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path


class Format(str, Enum):
    """支持的文档格式（值即规范扩展名）。"""

    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    MD = "md"
    HTML = "html"
    TXT = "txt"
    CSV = "csv"

    def __str__(self) -> str:  # 便于日志与 UI 直接拼接
        return self.value


# 用户/系统可能给出的别名 → 规范格式
ALIASES: dict[str, Format] = {
    "markdown": Format.MD,
    "mdown": Format.MD,
    "mkd": Format.MD,
    "htm": Format.HTML,
    "xhtml": Format.HTML,
    "text": Format.TXT,
    "log": Format.TXT,
    "word": Format.DOCX,
    "doc": Format.DOCX,
    "excel": Format.XLSX,
    "xlsm": Format.XLSX,
    "xls": Format.XLSX,
    "powerpoint": Format.PPTX,
    "ppt": Format.PPTX,
}

# 目标格式 → pandoc writer 名称（None 表示 pandoc 无法直接输出该格式）
PANDOC_WRITER: dict[Format, str] = {
    Format.MD: "markdown",
    Format.HTML: "html",
    Format.TXT: "plain",
    Format.DOCX: "docx",
    Format.PPTX: "pptx",
    Format.CSV: "csv",
}

# 源格式 → pandoc reader 名称（None 表示 pandoc 无法直接读取该格式）
# 注意：pandoc 没有 txt reader，纯文本按 markdown 读取最稳妥。
PANDOC_READER: dict[Format, str] = {
    Format.MD: "markdown",
    Format.HTML: "html",
    Format.TXT: "markdown",
    Format.DOCX: "docx",
    Format.PPTX: "pptx",
    Format.CSV: "csv",
}


def parse_format(value: object) -> Format | None:
    """把任意书写形式（``"PDF"`` / ``".docx"`` / ``Format.MD``）解析为 :class:`Format`。"""
    if isinstance(value, Format):
        return value
    if value is None:
        return None
    text = str(value).strip().lower().lstrip(".")
    if not text:
        return None
    if text in ALIASES:
        return ALIASES[text]
    try:
        return Format(text)
    except ValueError:
        return None


def detect_format(path: object) -> Format | None:
    """按扩展名识别文件格式；也接受 ``Path``。"""
    extension = Path(os.fspath(path)).suffix
    return parse_format(extension)

