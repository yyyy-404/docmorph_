"""与框架无关的通用工具。"""

from __future__ import annotations

import sys


def ensure_console_encoding() -> None:
    """让 stdout/stderr 在非 UTF-8 控制台（如中文 GBK）打印 emoji/symbol 不崩溃。

    仅把无法编码的字符替换为 ``?``，可打印的中文/ASCII 不受影响；
    对已被 pytest/capsys 替换的流自动跳过。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")
        except (OSError, ValueError):
            pass
