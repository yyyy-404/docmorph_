"""运行环境能力检测。

回答一个问题：**这台机器上，哪些转换后端现在就能用？**

* 不硬编码任何外部软件为必需；
* 检测结果缓存（进程内一次），GUI 的"系统能力"面板与引擎选路共用同一份；
* 检测过程绝不启动 Office（只查注册表/文件路径），避免拖慢启动。
"""

from __future__ import annotations

import contextlib
import ctypes.util
import importlib
import io
import os
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

KIND_PACKAGE = "python-package"
KIND_APP = "external-app"
KIND_RUNTIME = "system-runtime"


@dataclass(frozen=True)
class Capability:
    """单个能力项。"""

    id: str
    label: str
    kind: str
    available: bool
    detail: str = ""
    hint: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "available": self.available,
            "detail": self.detail,
            "hint": self.hint,
        }


@dataclass
class CapabilityReport:
    """一次检测的完整结果。"""

    capabilities: dict[str, Capability] = field(default_factory=dict)

    def add(self, capability: Capability) -> None:
        self.capabilities[capability.id] = capability

    def get(self, capability_id: str) -> Capability:
        return self.capabilities.get(
            capability_id,
            Capability(capability_id, capability_id, KIND_PACKAGE, False, "未检测", ""),
        )

    def available(self, capability_id: str) -> bool:
        return self.get(capability_id).available

    def as_dict(self) -> dict[str, object]:
        return {
            "capabilities": [cap.as_dict() for cap in self.capabilities.values()],
            "available": sorted(k for k, v in self.capabilities.items() if v.available),
            "missing": sorted(k for k, v in self.capabilities.items() if not v.available),
        }

    def summary_lines(self) -> list[str]:
        lines = []
        for cap in self.capabilities.values():
            mark = "✔" if cap.available else "✘"
            detail = f" — {cap.detail}" if cap.detail else ""
            lines.append(f"{mark} {cap.label}{detail}")
        return lines


# ---------------------------------------------------------------------- 探测工具

def _module_available(module_name: str) -> str | None:
    """尝试导入模块，返回版本号字符串；失败返回 ``None``。"""
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    version = getattr(module, "__version__", None)
    if version is None and module_name == "weasyprint":
        version = getattr(module, "VERSION", "")
    return str(version) if version else "已安装"


def _registry_app_path(exe_name: str) -> str | None:
    """从 ``App Paths`` 读取可执行文件完整路径（Windows）。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - 非 Windows
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in ("", r"\WOW6432Node"):
            key_path = rf"SOFTWARE{view}\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
            try:
                with winreg.OpenKey(root, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value and os.path.exists(value):
                        return value
            except OSError:
                continue
    return None


def _com_progid_registered(prog_id: str) -> bool:
    """检查 COM ProgID 是否注册（不代表可执行文件真的存在）。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return False
    for root in (winreg.HKEY_CLASSES_ROOT,):
        try:
            with winreg.OpenKey(root, rf"{prog_id}\CLSID"):
                return True
        except OSError:
            continue
    return False


def _install_roots() -> list[Path]:
    """常见的办公软件安装根目录。"""
    roots: list[Path] = []
    for env_name, default in (
        ("ProgramFiles", r"C:\Program Files"),
        ("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        base = Path(os.environ.get(env_name, default))
        roots.extend(
            [
                base / "Microsoft Office" / "Root" / "Office16",
                base / "Microsoft Office" / "Root" / "Office15",
                base / "Microsoft Office" / "Office16",
                base / "Kingsoft" / "WPS Office",
                base / "WPS Office",
                base / "LibreOffice" / "program",
            ]
        )
    return roots


def _find_office_executable(exe_names: list[str], prog_id: str) -> str | None:
    """定位办公软件可执行文件：App Paths 注册表 → PATH → 常见安装目录。

    只查文件系统与注册表，**不启动**任何 Office 进程。
    """
    roots = _install_roots()
    for exe in exe_names:
        found = _registry_app_path(exe)
        if found:
            return found
        located = shutil.which(exe)
        if located:
            return located
        for root in roots:
            candidate = root / exe
            if candidate.is_file():
                return str(candidate)
    return None


def _weasyprint_usable() -> tuple[bool, str]:
    """WeasyPrint 需要 GTK/Pango 原生库，仅 import 成功并不代表可用。"""
    # WeasyPrint 在缺少原生库时会直接往 stderr 打印安装指引，检测时静音处理
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            importlib.import_module("weasyprint")
    except ImportError:
        return False, "未安装"
    except Exception as exc:
        return False, f"已安装但导入失败：{type(exc).__name__}"
    for library in ("gobject-2.0-0", "libgobject-2.0-0", "pango-1.0-0"):
        if ctypes.util.find_library(library):
            return True, "GTK 可用"
    # find_library 在 Windows 上常查不到，做一次真实渲染验证
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML

            pdf = HTML(string="<p>ok</p>").write_pdf()
        if pdf:
            return True, "已通过渲染自检"
    except Exception as exc:
        return False, f"已安装但缺少原生库 GTK/Pango（{type(exc).__name__}）"
    return False, "自检未通过"


def _webview2_version() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return None
    client = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (r"\WOW6432Node", ""):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE{view}\Microsoft\EdgeUpdate\Clients\{client}") as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    return str(version)
            except OSError:
                continue
    return None


def _pymupdf_version() -> str | None:
    """PyMuPDF 的历史导入名是 ``fitz``，新版也提供 ``pymupdf``。"""
    for module_name in ("pymupdf", "fitz"):
        version = _module_available(module_name)
        if version is not None:
            return version
    return None


def _pandoc_version() -> str | None:
    try:
        import pypandoc

        return str(pypandoc.get_pandoc_version())
    except Exception:
        return None


# ---------------------------------------------------------------------- 检测

_CACHE: CapabilityReport | None = None


def detect(force: bool = False) -> CapabilityReport:
    """检测并缓存当前环境能力。"""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    report = CapabilityReport()
    # 部分第三方库在导入期就往 stderr 写弃用/安装提示（PyMuPDF 的 fitz 别名、
    # WeasyPrint 的 GTK 指引），检测过程对用户无意义，这里静音处理。
    with warnings.catch_warnings(), contextlib.redirect_stdout(
        io.StringIO()
    ), contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore")
        _detect_into(report)
    _CACHE = report
    return report


def _detect_into(report: CapabilityReport) -> None:
    """执行实际检测并写入 ``report``。"""

    pymupdf_version = _pymupdf_version()
    report.add(
        Capability(
            "pymupdf",
            "PyMuPDF（PDF 解析/渲染）",
            KIND_PACKAGE,
            pymupdf_version is not None,
            pymupdf_version or "未安装",
            "" if pymupdf_version else "请执行 pip install PyMuPDF",
        )
    )

    for module, label in (
        ("pdf2docx", "pdf2docx（PDF→DOCX）"),
        ("docx", "python-docx（DOCX 读写）"),
        ("pptx", "python-pptx（PPTX 读写）"),
        ("pandas", "pandas（表格处理）"),
        ("openpyxl", "openpyxl（XLSX 读写）"),
        ("PIL", "Pillow（图像处理）"),
        ("win32com", "pywin32（Office 自动化）"),
        ("webview", "pywebview（桌面窗口）"),
    ):
        version = _module_available(module)
        report.add(
            Capability(
                module,
                label,
                KIND_PACKAGE,
                version is not None,
                version or "未安装",
                "" if version else f"请执行 pip install {'pywin32' if module == 'win32com' else module}",
            )
        )

    pandoc_version = _pandoc_version()
    report.add(
        Capability(
            "pandoc",
            "Pandoc（结构化文档转换）",
            KIND_PACKAGE,
            pandoc_version is not None,
            f"pandoc {pandoc_version}" if pandoc_version else "不可用",
            "" if pandoc_version else "请执行 pip install pypandoc-binary",
        )
    )

    usable, detail = _weasyprint_usable()
    report.add(
        Capability(
            "weasyprint",
            "WeasyPrint（HTML→PDF 纯 Python 引擎）",
            KIND_PACKAGE,
            usable,
            detail,
            "" if usable else "需额外安装 GTK/Pango 运行时；建议改用 Word/LibreOffice",
        )
    )

    for cap_id, label, exe_names, prog_id in (
        ("word", "Microsoft Word", ["WINWORD.EXE"], "Word.Application"),
        ("excel", "Microsoft Excel", ["EXCEL.EXE"], "Excel.Application"),
        ("powerpoint", "Microsoft PowerPoint", ["POWERPOINT.EXE"], "PowerPoint.Application"),
    ):
        found = _find_office_executable(exe_names, prog_id)
        registered = _com_progid_registered(prog_id)
        available = bool(found)
        if found:
            detail = found
        elif registered:
            detail = "已注册 COM 但未找到程序文件"
        else:
            detail = "未安装"
        report.add(
            Capability(
                cap_id,
                label,
                KIND_APP,
                available,
                detail,
                "" if available else "安装 Microsoft Office 后可启用高保真 PDF 导出",
            )
        )

    wps_found = _find_office_executable(["wps.exe", "et.exe", "wpp.exe"], "KWPS.Application")
    wps_registered = _com_progid_registered("KWPS.Application") or _com_progid_registered("WPS.Application")
    report.add(
        Capability(
            "wps",
            "WPS Office",
            KIND_APP,
            bool(wps_found),
            wps_found or ("已注册 COM 但未找到程序文件" if wps_registered else "未安装"),
            "可选：作为 Word/Excel 的替代渲染后端",
        )
    )

    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if not soffice:
        for candidate in (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ):
            if os.path.exists(candidate):
                soffice = candidate
                break
    report.add(
        Capability(
            "libreoffice",
            "LibreOffice",
            KIND_APP,
            bool(soffice),
            soffice or "未安装",
            "可选：无 Office 时的 PDF 渲染兜底方案",
        )
    )

    webview_version = _webview2_version()
    report.add(
        Capability(
            "webview2",
            "Edge WebView2 运行时",
            KIND_RUNTIME,
            bool(webview_version),
            f"版本 {webview_version}" if webview_version else "未检测到",
            "图形界面需要它；缺失时可安装 Microsoft Edge WebView2 Runtime，命令行不受影响",
        )
    )
