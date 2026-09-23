"""LibreOffice 后端：没有 Office 时的通用文档转换兜底。

通过 ``soffice --headless --convert-to`` 驱动，属于**可选**能力：
用户没装 LibreOffice 时该后端直接不可用，不影响其它转换。
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docmorph.backends.base import BackendOutcome, ConversionBackend, ensure_parent, verify_output
from docmorph.capability import CapabilityReport
from docmorph.errors import ConversionFailedError, ConversionTimeoutError
from docmorph.formats import Format
from docmorph.settings.paths import TempWorkspace

# LibreOffice 的导出格式名与扩展名不完全一致
_LO_TARGETS = {
    Format.PDF: "pdf",
    Format.DOCX: "docx",
    Format.XLSX: "xlsx",
    Format.HTML: "html",
    Format.TXT: "txt",
    Format.CSV: "csv",
    Format.PPTX: "pptx",
}

_LO_SOURCES = {
    Format.DOCX,
    Format.XLSX,
    Format.PPTX,
    Format.HTML,
    Format.TXT,
    Format.CSV,
    Format.MD,
}


class LibreOfficeBackend(ConversionBackend):
    """基于 ``soffice`` 命令行的转换后端。"""

    id = "libreoffice"
    label = "LibreOffice"
    serial = True
    capability_id = "libreoffice"

    def __init__(self, executable: str = "", timeout_seconds: int = 300) -> None:
        self._executable = executable
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------ 能力
    def available(self, report: CapabilityReport) -> bool:
        return bool(self.executable(report))

    def executable(self, report: CapabilityReport | None = None) -> str:
        if self._executable and Path(self._executable).exists():
            return self._executable
        found = shutil.which("soffice") or shutil.which("soffice.exe")
        if found:
            return found
        if report is not None:
            capability = report.get("libreoffice")
            if capability.available and capability.detail:
                return capability.detail
        return ""

    def handles(self, source: Format, target: Format) -> bool:
        return source in _LO_SOURCES and target in _LO_TARGETS

    # ------------------------------------------------------------------ 执行
    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        executable = self.executable()
        if not executable:
            raise ConversionFailedError("未找到 soffice 可执行文件", self.label)
        ensure_parent(target)
        out_dir = workspace.subdir(f"libreoffice-{target.stem}")
        timeout = float(options.get("office_timeout_seconds", self.timeout_seconds))
        command = [
            executable,
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={workspace.path.as_uri()}",
            "--convert-to",
            _LO_TARGETS[target_format],
            "--outdir",
            str(out_dir),
            str(source),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ConversionTimeoutError(timeout, self.label) from exc
        produced = out_dir / f"{source.stem}.{target_format.value}"
        if not produced.exists():
            raw = completed.stderr or completed.stdout or b""
            message = raw.decode("utf-8", "replace").strip()
            raise ConversionFailedError(
                f"LibreOffice 转换失败（退出码 {completed.returncode}）：{message[:200]}",
                self.label,
            )
        shutil.move(str(produced), str(target))
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])
