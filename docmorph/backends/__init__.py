"""转换后端集合。"""

from __future__ import annotations

from docmorph.backends.base import BackendOutcome, ConversionBackend
from docmorph.backends.libreoffice_backend import LibreOfficeBackend
from docmorph.backends.office import ExcelBackend, WordBackend, WpsBackend
from docmorph.backends.pandoc_backend import PandocBackend
from docmorph.backends.python_backend import PythonBackend
from docmorph.backends.weasyprint_backend import WeasyPrintBackend

__all__ = [
    "BackendOutcome",
    "ConversionBackend",
    "ExcelBackend",
    "LibreOfficeBackend",
    "PandocBackend",
    "PythonBackend",
    "WeasyPrintBackend",
    "WordBackend",
    "WpsBackend",
    "build_default_backends",
]


def build_default_backends(office_timeout_seconds: int = 300) -> dict[str, ConversionBackend]:
    """构造默认后端表（顺序无关，路由由 registry 决定）。"""
    return {
        backend.id: backend
        for backend in (
            PandocBackend(),
            PythonBackend(),
            WordBackend(office_timeout_seconds),
            ExcelBackend(office_timeout_seconds),
            WpsBackend(office_timeout_seconds),
            LibreOfficeBackend(timeout_seconds=office_timeout_seconds),
            WeasyPrintBackend(),
        )
    }
