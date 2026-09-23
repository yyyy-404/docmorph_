"""Office COM 后端（Word / Excel / WPS）。

设计要点：

* **串行**：Office COM 不是线程安全的，每个应用持有一把进程内锁，
  批量转换时同类任务自动排队，避免多个 Word 实例互相干扰（旧实现把它们丢进线程池并发跑）；
* **超时**：子线程看门狗到点强制 ``Quit()``，避免 Word 弹窗导致任务永久挂起；
* **不改动用户文件**：一律以只读方式打开输入；
* **不启动 Office 做检测**：是否可用由 :mod:`docmorph.capability` 通过文件与注册表判断。
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from docmorph.backends.base import BackendOutcome, ConversionBackend, ensure_parent, verify_output
from docmorph.capability import CapabilityReport
from docmorph.errors import (
    BackendUnavailableError,
    ConversionFailedError,
    ConversionTimeoutError,
    DependencyMissingError,
)
from docmorph.formats import Format
from docmorph.settings.paths import TempWorkspace

WD_FORMAT_PDF = 17
EXCEL_FORMAT_PDF = 0  # xlTypePDF

_LOCKS: dict[str, threading.Lock] = {
    "word": threading.Lock(),
    "excel": threading.Lock(),
    "wps": threading.Lock(),
}


def _dispatch(prog_id: str) -> Any:
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:  # pragma: no cover - 由 capability 提前拦截
        raise DependencyMissingError("pywin32", "office") from exc

    pythoncom.CoInitialize()
    try:
        return win32com.client.Dispatch(prog_id)
    except Exception as exc:
        pythoncom.CoUninitialize()
        raise BackendUnavailableError(
            prog_id,
            f"无法启动 {prog_id}（{type(exc).__name__}）",
            "请确认已正确安装并激活该办公软件",
        ) from exc


@contextlib.contextmanager
def com_application(prog_id: str, lock_name: str, timeout_seconds: float) -> Iterator[Any]:
    """以「串行 + 超时」保护的方式使用一个 COM 应用实例。"""
    import pythoncom

    lock = _LOCKS.setdefault(lock_name, threading.Lock())
    lock.acquire()
    app = _dispatch(prog_id)
    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        with contextlib.suppress(Exception):
            app.Quit()

    timer = threading.Timer(timeout_seconds, _kill)
    timer.daemon = True
    timer.start()
    try:
        yield app
        if timed_out.is_set():
            raise ConversionTimeoutError(timeout_seconds, lock_name)
    finally:
        timer.cancel()
        with contextlib.suppress(Exception):
            app.Quit()
        with contextlib.suppress(Exception):
            pythoncom.CoUninitialize()
        lock.release()


class OfficeBackendBase(ConversionBackend):
    """Office 类后端的公共实现。"""

    serial = True
    lock_name = "word"
    prog_id = "Word.Application"

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds

    def available(self, report: CapabilityReport) -> bool:
        return report.available(self.capability_id) and report.available("win32com")

    def _desktop_file(self, source: Path, workspace: TempWorkspace) -> Path:
        """Office 对超长/非 ASCII 路径不友好，必要时先复制到工作区。"""
        if len(str(source)) < 200 and str(source).isascii():
            return source
        staged = workspace.file(f"input{source.suffix}")
        staged.write_bytes(source.read_bytes())
        return staged


class WordBackend(OfficeBackendBase):
    """用 Microsoft Word 把 docx/html/txt 渲染为 PDF（排版保真最好）。"""

    id = "word"
    label = "Microsoft Word"
    lock_name = "word"
    prog_id = "Word.Application"
    capability_id = "word"

    def handles(self, source: Format, target: Format) -> bool:
        return target is Format.PDF and source in {Format.DOCX, Format.HTML, Format.TXT}

    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        ensure_parent(target)
        staged = self._desktop_file(source, workspace)
        timeout = float(options.get("office_timeout_seconds", self.timeout_seconds))
        with com_application(self.prog_id, self.lock_name, timeout) as word:
            word.Visible = False
            with contextlib.suppress(Exception):
                word.DisplayAlerts = 0
            document = None
            try:
                document = word.Documents.Open(
                    str(staged), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False
                )
                document.SaveAs2(str(target), FileFormat=WD_FORMAT_PDF)
            except Exception as exc:
                raise ConversionFailedError(f"Word 导出 PDF 失败：{exc}", self.label) from exc
            finally:
                if document is not None:
                    with contextlib.suppress(Exception):
                        document.Close(SaveChanges=0)
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])


class ExcelBackend(OfficeBackendBase):
    """用 Microsoft Excel 把 xlsx 导出为 PDF。"""

    id = "excel"
    label = "Microsoft Excel"
    lock_name = "excel"
    prog_id = "Excel.Application"
    capability_id = "excel"

    def handles(self, source: Format, target: Format) -> bool:
        return target is Format.PDF and source is Format.XLSX

    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        ensure_parent(target)
        staged = self._desktop_file(source, workspace)
        timeout = float(options.get("office_timeout_seconds", self.timeout_seconds))
        with com_application(self.prog_id, self.lock_name, timeout) as excel:
            with contextlib.suppress(Exception):
                excel.Visible = False
                excel.DisplayAlerts = False
            workbook = None
            try:
                workbook = excel.Workbooks.Open(str(staged), ReadOnly=True, UpdateLinks=0)
                workbook.ExportAsFixedFormat(EXCEL_FORMAT_PDF, str(target))
            except Exception as exc:
                raise ConversionFailedError(f"Excel 导出 PDF 失败：{exc}", self.label) from exc
            finally:
                if workbook is not None:
                    with contextlib.suppress(Exception):
                        workbook.Close(SaveChanges=False)
        verify_output(target, self.label)
        warnings: list[str] = ["PDF 由 Excel 按工作表打印区域导出，可能分页与屏幕视图不同"]
        return BackendOutcome(outputs=[target], warnings=warnings)


class WpsBackend(OfficeBackendBase):
    """WPS Office 后端：Word/Excel 缺失时的等价替代（完全可选）。"""

    id = "wps"
    label = "WPS Office"
    lock_name = "wps"
    prog_id = "KWPS.Application"
    capability_id = "wps"

    def handles(self, source: Format, target: Format) -> bool:
        return target is Format.PDF and source in {
            Format.DOCX,
            Format.HTML,
            Format.TXT,
            Format.XLSX,
        }

    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        ensure_parent(target)
        staged = self._desktop_file(source, workspace)
        timeout = float(options.get("office_timeout_seconds", self.timeout_seconds))
        spreadsheet = source_format is Format.XLSX
        prog_id = "KET.Application" if spreadsheet else "KWPS.Application"

        with com_application(prog_id, self.lock_name, timeout) as app:
            with contextlib.suppress(Exception):
                app.Visible = False
                app.DisplayAlerts = 0 if not spreadsheet else False
            document = None
            try:
                if spreadsheet:
                    document = app.Workbooks.Open(str(staged), ReadOnly=True, UpdateLinks=0)
                    document.ExportAsFixedFormat(EXCEL_FORMAT_PDF, str(target))
                else:
                    document = app.Documents.Open(
                        str(staged), ConfirmConversions=False, ReadOnly=True
                    )
                    document.SaveAs2(str(target), FileFormat=WD_FORMAT_PDF)
            except Exception as exc:
                raise ConversionFailedError(f"WPS 导出 PDF 失败：{exc}", self.label) from exc
            finally:
                if document is not None:
                    with contextlib.suppress(Exception):
                        document.Close(0 if not spreadsheet else False)
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])
