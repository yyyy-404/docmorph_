"""WeasyPrint 后端（可选）：纯 Python 的 HTML → PDF。

注意：Windows 上 WeasyPrint 需要额外的 GTK/Pango 原生库，**默认不可用**。
能力检测会做一次真实渲染自检，通过后才参与路由；否则由 Word / LibreOffice 兜底。
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docmorph.backends.base import BackendOutcome, ConversionBackend, ensure_parent, verify_output
from docmorph.capability import CapabilityReport
from docmorph.errors import ConversionFailedError, DependencyMissingError
from docmorph.formats import Format
from docmorph.settings.paths import TempWorkspace


class WeasyPrintBackend(ConversionBackend):
    """HTML → PDF。"""

    id = "weasyprint"
    label = "WeasyPrint"
    serial = False
    capability_id = "weasyprint"

    def available(self, report: CapabilityReport) -> bool:
        return report.available("weasyprint")

    def handles(self, source: Format, target: Format) -> bool:
        return source is Format.HTML and target is Format.PDF

    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        try:
            weasyprint = importlib.import_module("weasyprint")
        except ImportError as exc:  # pragma: no cover - 由能力检测提前拦截
            raise DependencyMissingError("weasyprint", self.id) from exc
        ensure_parent(target)
        try:
            weasyprint.HTML(filename=str(source)).write_pdf(str(target))
        except Exception as exc:
            raise ConversionFailedError(
                f"WeasyPrint 渲染失败：{exc}（Windows 需额外安装 GTK/Pango）", self.label
            ) from exc
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])
