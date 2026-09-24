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
import importlib.util
import io
import logging
import os
import shutil
import sys
import threading
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

KIND_PACKAGE = "python-package"
KIND_APP = "external-app"
KIND_RUNTIME = "system-runtime"

LOGGER_NAME = "docmorph.capability"


@contextlib.contextmanager
def _quiet_output():
    """静音第三方库的导入期提示。

    只允许在**主线程**做全局重定向：``contextlib.redirect_*`` 改的是进程级 ``sys.stdout/stderr``，
    若在后台预热线程里使用，会把同一时刻其它线程（例如 CLI 输出、日志控制台 handler）的输出一起吞掉。
    """
    if threading.current_thread() is threading.main_thread():
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield
    else:
        yield


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

#: 模块名 → 发行包名（用于不导入模块就取版本号）
_DISTRIBUTIONS: dict[str, str] = {
    "pymupdf": "PyMuPDF",
    "fitz": "PyMuPDF",
    "pdf2docx": "pdf2docx",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "PIL": "Pillow",
    "win32com": "pywin32",
    "webview": "pywebview",
    "pypandoc": "pypandoc-binary",
    "weasyprint": "weasyprint",
}


def _module_present(module_name: str) -> bool:
    """只判断模块是否可导入，**不真的导入**（零重型依赖、零第三方输出）。"""
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        # 探测本身失败一律视为"不可用"，绝不向外抛（单项失败不能影响其它能力）
        return False


def _distribution_version(*candidates: str) -> str | None:
    """通过包元数据取版本（不导入模块）。"""
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover
        return None
    for name in candidates:
        if not name:
            continue
        try:
            return metadata.version(name)
        except Exception:
            continue
    return None


def _module_available(module_name: str, *, deep: bool = False) -> str | None:
    """探测模块。

    ``deep=False``（默认）：只用 ``find_spec`` + 包元数据判断是否存在并取版本，
    **不导入模块**——这是启动/选路快且安静的关键（也避免第三方库往 stdout 打印提示）。

    ``deep=True``：真正导入模块以确认可用（可获得最准确的版本），代价是慢且有第三方输出，
    仅用于用户显式要求的"重新检测 / doctor --deep"。
    """
    if not deep:
        if not _module_present(module_name):
            return None
        version = _distribution_version(_DISTRIBUTIONS.get(module_name, ""), module_name)
        return version or "已安装"
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


def _gtk_libraries_present() -> bool:
    """粗查 GTK/Pango 原生库是否存在（不导入 weasyprint）。"""
    return any(
        ctypes.util.find_library(library) for library in ("gobject-2.0-0", "libgobject-2.0-0", "pango-1.0-0")
    )


def _weasyprint_usable(*, deep: bool = False) -> tuple[bool, str]:
    """WeasyPrint 需要 GTK/Pango 原生库，仅"装了包"并不代表可用。

    默认（``deep=False``）：**不导入 weasyprint**，只用 ``find_spec`` + 原生库探测判断，
    这样既快又不会让 WeasyPrint 往 stdout 打印安装指引（会污染 CLI 的 --json 输出）。
    ``deep=True``：真正导入并做一次渲染自检（更权威，但慢且有第三方输出）。
    """
    if not _module_present("weasyprint"):
        return False, "未安装"
    if not _gtk_libraries_present():
        return False, "已安装，但未检测到 GTK/Pango 运行时"
    if not deep:
        return True, "GTK 可用（未做渲染自检）"
    # 深度模式：真实渲染一次，确认端到端可用
    try:
        with _quiet_output():
            importlib.import_module("weasyprint")
    except ImportError:
        return False, "未安装"
    except Exception as exc:
        return False, f"已安装但导入失败：{type(exc).__name__}"
    try:
        with _quiet_output():
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


def _pymupdf_version(*, deep: bool = False) -> str | None:
    """PyMuPDF 的历史导入名是 ``fitz``，新版也提供 ``pymupdf``。"""
    for module_name in ("pymupdf", "fitz"):
        version = _module_available(module_name, deep=deep)
        if version is not None:
            return version
    return None


def _pandoc_binary_present() -> bool:
    """pypandoc 随包提供 pandoc 二进制，检查它是否就位（不导入 pypandoc）。"""
    spec = None
    try:
        spec = importlib.util.find_spec("pypandoc")
    except (ImportError, ValueError):
        return False
    if spec is None or not spec.origin:
        return False
    binary = Path(spec.origin).parent / "files" / "pandoc.exe"
    return binary.is_file() or (Path(spec.origin).parent / "files").is_dir()


def _pandoc_version(*, deep: bool = False) -> str | None:
    if not deep:
        return "已随 pypandoc 提供" if _pandoc_binary_present() else None
    try:
        import pypandoc

        return str(pypandoc.get_pandoc_version())
    except Exception:
        return None


# ---------------------------------------------------------------------- 检测

_CACHE: CapabilityReport | None = None
_DEEP_CACHE: CapabilityReport | None = None


def detect(force: bool = False, *, full: bool = True, deep: bool = False) -> CapabilityReport:
    """检测并缓存当前环境能力。

    :param full: ``True`` 检测全部能力项；``False`` 只做启动所需的轻量检查（WebView2 / Python）。
    :param deep: ``True`` 时**真正导入**各依赖做权威自检（慢、会产生第三方输出），
        仅用于用户显式要求（系统能力页的"重新检测"、``doctor --deep``）；
        默认 ``False`` 时只用模块存在性 + 包元数据判断，**零重型导入**：
        这样启动与选路都快，也不会把库的提示信息打到 stdout 上（避免污染 CLI 的 --json）。
    """
    if not full:
        return startup_report(force=force)
    global _CACHE, _DEEP_CACHE
    cached = _DEEP_CACHE if deep else _CACHE
    if cached is not None and not force:
        return cached

    report = CapabilityReport()
    # 深度检测会真实导入第三方库，它们可能往 stdout/stderr 写提示，这里静音处理
    with warnings.catch_warnings(), _quiet_output():
        warnings.simplefilter("ignore")
        try:
            _detect_into(report, deep=deep)
        except Exception as exc:
            logging.getLogger(LOGGER_NAME).warning("能力检测整体失败", exc_info=True)
            report = startup_report(force=True)
            report.add(
                Capability(
                    "diagnostics",
                    "能力检测异常",
                    KIND_RUNTIME,
                    False,
                    f"{type(exc).__name__}: {exc}",
                    "可在“系统能力”页重新检测；单项检测失败不会影响其它转换能力",
                )
            )
    if deep:
        _DEEP_CACHE = report
        _CACHE = report  # 深度结果更权威，直接作为默认缓存
    else:
        _CACHE = report
    return report


def _detect_into(report: CapabilityReport, *, deep: bool = False) -> None:
    """执行实际检测并写入 ``report``。"""

    pymupdf_version = _pymupdf_version(deep=deep)
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
        version = _module_available(module, deep=deep)
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

    pandoc_version = _pandoc_version(deep=deep)
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

    usable, detail = _weasyprint_usable(deep=deep)
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


# ---------------------------------------------------------------------- 启动轻量检测
# 启动阶段只回答一个问题："窗口能不能起来？"
# 因此这里只做**零重型导入**的检查（读注册表 / 查文件），完整检测推迟到按需或后台预热。


@dataclass(frozen=True)
class StartupProbe:
    """启动阶段的一项轻量检查。"""

    id: str
    label: str
    kind: str
    run: Callable[[], tuple[bool, str]]
    hint: str = ""


def _probe_python_runtime() -> tuple[bool, str]:
    frozen = "（打包运行）" if getattr(sys, "frozen", False) else ""
    return True, f"Python {sys.version.split()[0]}{frozen}"


def _probe_webview2_runtime() -> tuple[bool, str]:
    version = _webview2_version()
    return bool(version), f"版本 {version}" if version else "未检测到"


STARTUP_PROBES: tuple[StartupProbe, ...] = (
    StartupProbe(
        "webview2",
        "Edge WebView2 运行时",
        KIND_RUNTIME,
        _probe_webview2_runtime,
        "图形界面需要它；可安装 Microsoft Edge WebView2 Runtime，命令行不受影响",
    ),
    StartupProbe("python", "Python 运行时", KIND_RUNTIME, _probe_python_runtime),
)

_STARTUP_CACHE: CapabilityReport | None = None


def startup_report(force: bool = False) -> CapabilityReport:
    """启动阶段使用的轻量报告：**不导入任何重型依赖**。

    单项检查异常只会把该项标记为不可用，不会向外抛。
    """
    global _STARTUP_CACHE
    if _STARTUP_CACHE is not None and not force:
        return _STARTUP_CACHE
    report = CapabilityReport()
    for probe in STARTUP_PROBES:
        try:
            available, detail = probe.run()
        except Exception as exc:
            available, detail = False, f"检测失败：{type(exc).__name__}: {exc}"
        report.add(
            Capability(
                probe.id,
                probe.label,
                probe.kind,
                bool(available),
                str(detail),
                "" if available else probe.hint,
            )
        )
    _STARTUP_CACHE = report
    return report


def startup_probe_ids() -> list[str]:
    """启动阶段会执行的检查项 id。"""
    return [probe.id for probe in STARTUP_PROBES]


class CapabilityProvider:
    """惰性能力提供者（GUI/CLI/引擎共用）。

    * 启动阶段只调用 :meth:`startup`（零重型导入），窗口先起来；
    * 完整检测由 :meth:`report` 按需触发，或由 :meth:`warmup` 在后台线程预热；
    * 内部缓存 + 锁，保证多线程只检测一次。
    """

    def __init__(self) -> None:
        self._full: CapabilityReport | None = None
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._warmup_error: str = ""
        self._deep_done = False

    # ------------------------------------------------------------------ 查询
    @property
    def loaded(self) -> bool:
        with self._lock:
            return self._full is not None

    @property
    def warmup_error(self) -> str:
        with self._lock:
            return self._warmup_error

    def startup(self) -> CapabilityReport:
        with self._lock:
            if self._full is not None:
                return self._full
        return startup_report()

    @property
    def deep_done(self) -> bool:
        """是否已经做过一次深度（真实导入）自检。"""
        with self._lock:
            return self._deep_done

    def report(self, force: bool = False) -> CapabilityReport:
        """完整报告（首次调用会执行完整检测）。"""
        with self._lock:
            if self._full is not None and not force:
                return self._full
        return self.refresh()

    def refresh(self, deep: bool = False) -> CapabilityReport:
        """重新检测。``deep=True`` 会真实导入依赖做权威自检（较慢、有第三方输出）。"""
        report = detect(force=True, deep=deep)
        with self._lock:
            self._full = report
            if deep:
                self._deep_done = True
        return report

    # ------------------------------------------------------------------ 预热
    def warmup(self, on_ready: Callable[[CapabilityReport], None] | None = None) -> bool:
        """后台线程执行完整检测；返回是否新启动了线程（已在跑则返回 False）。"""
        with self._lock:
            if self._full is not None:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            thread = threading.Thread(
                target=self._warmup_worker,
                args=(on_ready,),
                name="docmorph-capability",
                daemon=True,
            )
            self._thread = thread
        thread.start()
        return True

    def _warmup_worker(self, on_ready: Callable[[CapabilityReport], None] | None) -> None:
        try:
            report = self.refresh()
        except Exception as exc:
            with self._lock:
                self._warmup_error = f"{type(exc).__name__}: {exc}"
            logging.getLogger(LOGGER_NAME).warning("后台能力检测失败", exc_info=True)
            return
        if on_ready is not None:
            try:
                on_ready(report)
            except Exception:
                logging.getLogger(LOGGER_NAME).warning("能力检测回调失败", exc_info=True)


def iter_capability_ids() -> Iterable[str]:
    """已知的能力项 id（含外部软件与 Python 包），供 UI/测试遍历。"""
    return (
        "webview2",
        "python",
        "pymupdf",
        "pdf2docx",
        "docx",
        "pptx",
        "pandas",
        "openpyxl",
        "PIL",
        "pandoc",
        "win32com",
        "weasyprint",
        "word",
        "excel",
        "powerpoint",
        "wps",
        "libreoffice",
        "webview",
    )


class FrozenProvider:
    """把一个既有报告包装成 provider（测试、CLI 单次运行、指定环境时使用）。"""

    def __init__(self, report: CapabilityReport) -> None:
        self._report = report

    @property
    def loaded(self) -> bool:
        return True

    @property
    def warmup_error(self) -> str:
        return ""

    def startup(self) -> CapabilityReport:
        return self._report

    def report(self, force: bool = False) -> CapabilityReport:
        return self._report

    def refresh(self) -> CapabilityReport:
        return self._report

    def warmup(self, on_ready: Callable[[CapabilityReport], None] | None = None) -> bool:
        return False


def as_provider(source: object | None) -> CapabilityProvider | FrozenProvider:
    """把 ``None`` / ``CapabilityReport`` / provider 统一成 provider。"""
    if source is None:
        return CapabilityProvider()
    if isinstance(source, (CapabilityProvider, FrozenProvider)):
        return source
    if isinstance(source, CapabilityReport):
        return FrozenProvider(source)
    raise TypeError(f"不支持的能力来源类型：{type(source).__name__}")
