"""启动引导层：让应用"无论如何都能安全地起来，并且失败时留下可诊断的记录"。

职责边界（**不做**业务逻辑，也不重复 capability 的检测逻辑）：

1. 建立最小可用的运行环境（控制台编码、配置目录、日志目录），并对"目录不可写"这类
   环境问题降级而不是崩溃；
2. 安装进程级异常钩子，把启动/运行期异常写入 ``startup-crash.log``（含诊断信息）；
3. 记录启动各阶段耗时到 ``startup.log``（带轮转，不会无限增长）；
4. 提供安全模式判定与启动上下文，供 GUI/CLI 复用。

日志里**只记录环境与异常信息**，不记录用户文档内容、路径以外的隐私数据。
"""

from __future__ import annotations

import contextlib
import faulthandler
import importlib.util
import logging
import os
import platform
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from docmorph.settings.paths import app_data_dir, default_log_dir

MAX_LOG_BYTES = 1 * 1024 * 1024
BACKUP_COUNT = 3

STARTUP_LOG_NAME = "startup.log"
CRASH_LOG_NAME = "startup-crash.log"
FAULT_LOG_NAME = "startup-fault.log"

SAFE_MODE_FLAGS = ("--safe-mode", "--safe", "/safe-mode")

#: 保持 faulthandler 输出文件对象的引用（被回收会关闭 fd）
_FAULT_HANDLE: Any = None
#: 测试可以通过它强制安装 faulthandler
_FAULT_FORCE = bool(os.environ.get("DOCMORPH_FORCE_FAULTHANDLER"))


@dataclass
class Phase:
    """一个启动阶段及其耗时（毫秒）。"""

    name: str
    duration_ms: int
    ok: bool = True
    detail: str = ""


@dataclass
class StartupContext:
    """一次启动的上下文与诊断信息。"""

    log_dir: Path
    config_path: str = ""
    safe_mode: bool = False
    phases: list[Phase] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    degraded: list[str] = field(default_factory=list)
    _started: float = field(default_factory=time.perf_counter)

    # ------------------------------------------------------------------ 记录
    def phase_ok(self, name: str, duration_s: float, detail: str = "") -> None:
        self.phases.append(Phase(name, int(duration_s * 1000), True, detail))

    def phase_failed(self, name: str, duration_s: float, detail: str) -> None:
        self.phases.append(Phase(name, int(duration_s * 1000), False, detail))
        self.degraded.append(f"{name}: {detail}")

    @property
    def elapsed_s(self) -> float:
        return round(time.perf_counter() - self._started, 3)

    def summary(self) -> str:
        parts = [f"{phase.name}={phase.duration_ms}ms{'!' if not phase.ok else ''}" for phase in self.phases]
        return " ".join(parts)


# ---------------------------------------------------------------------- 诊断信息

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """前端产物所在目录（打包后位于 ``_internal``，因此不能用 ``__file__`` 直接推断）。"""
    if _is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "docmorph" / "ui" / "webapp"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / "ui" / "webapp"


def diagnostics() -> dict[str, Any]:
    """收集启动诊断信息（**不含**任何用户文档内容）。"""
    from docmorph import __version__

    # 只查模块是否存在，不真的导入（省掉约 0.2s；真正需要时 app.run 会导入）
    webview_ok: Any = bool(importlib.util.find_spec("webview"))

    webapp = resource_dir()
    index = webapp / "index.html"
    info: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "frozen": _is_frozen(),
        "cwd": os.getcwd(),
        "app_data_dir": str(app_data_dir()),
        "resource_dir": str(webapp),
        "webapp_index": str(index),
        "webapp_ok": index.exists(),
        "pywebview": webview_ok,
    }
    try:
        from docmorph.capability import startup_report

        report = startup_report()
        info["webview2"] = report.get("webview2").available
        info["webview2_detail"] = report.get("webview2").detail
    except Exception as exc:
        info["webview2"] = f"检测失败：{type(exc).__name__}: {exc}"
    return info


# ---------------------------------------------------------------------- 日志

def _rotating_logger(name: str, path: Path, level: int = logging.INFO) -> logging.Logger:
    """独立的轮转文件 logger（不接入业务日志体系，避免相互影响）。

    注意：logger 是进程级单例。若目标路径发生变化（例如切换配置目录、测试指向 tmp），
    必须替换掉旧的 handler，否则会继续写旧路径（甚至写进已被删除的文件）。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    wanted = str(path)
    existing = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]
    if any(handler.baseFilename == wanted for handler in existing):
        return logger
    for handler in existing:
        logger.removeHandler(handler)
        with contextlib.suppress(OSError):
            handler.close()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    except OSError:
        if not any(isinstance(item, logging.NullHandler) for item in logger.handlers):
            logger.addHandler(logging.NullHandler())
    return logger


def _write_report(logger: logging.Logger, title: str, text: str, info: dict[str, Any] | None = None) -> None:
    lines = [f"===== {title} ====="]
    for key, value in (info or {}).items():
        lines.append(f"{key}: {value}")
    if text:
        lines.append(text.rstrip())
    logger.error("\n".join(lines))


# ---------------------------------------------------------------------- 引导

def safe_mode_requested(argv: Iterable[str] | None = None) -> bool:
    """是否请求安全模式（命令行参数或环境变量）。"""
    if os.environ.get("DOCMORPH_SAFE_MODE"):
        return True
    args = list(sys.argv[1:] if argv is None else argv)
    return any(arg in SAFE_MODE_FLAGS for arg in args)


def strip_safe_mode_flags(argv: Iterable[str]) -> list[str]:
    """把安全模式参数从 argv 中摘掉（避免传给 argparse 报错）。"""
    return [arg for arg in argv if arg not in SAFE_MODE_FLAGS]


def bootstrap(
    log_dir: Path | None = None,
    safe_mode: bool | None = None,
    install_hooks: bool = True,
) -> StartupContext:
    """建立最小运行环境。**任何失败都降级处理，不抛异常。**"""
    started = time.perf_counter()
    target_dir = Path(log_dir) if log_dir else default_log_dir()
    context = StartupContext(log_dir=target_dir)

    # 1) 控制台编码（GBK 控制台下打印符号不崩）
    step = time.perf_counter()
    try:
        from docmorph.utils import ensure_console_encoding

        ensure_console_encoding()
        context.phase_ok("console", time.perf_counter() - step)
    except Exception as exc:
        context.phase_failed("console", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")

    # 2) 日志目录（不可写时退回到临时目录）
    step = time.perf_counter()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        probe = target_dir / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        context.phase_ok("log_dir", time.perf_counter() - step, str(target_dir))
    except OSError as exc:
        fallback = Path(os.environ.get("TEMP", ".")) / "DocMorph" / "logs"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            context.log_dir = fallback
            context.phase_failed("log_dir", time.perf_counter() - step, f"{exc}（已回退到 {fallback}）")
        except OSError as exc2:
            context.log_dir = Path(".")
            context.phase_failed("log_dir", time.perf_counter() - step, f"{exc}；回退失败 {exc2}")

    # 3) 安全模式标记
    if safe_mode is None:
        safe_mode = safe_mode_requested()
    context.safe_mode = bool(safe_mode)

    # 4) 诊断信息
    step = time.perf_counter()
    try:
        context.diagnostics = diagnostics()
        context.phase_ok("diagnostics", time.perf_counter() - step)
    except Exception as exc:
        context.phase_failed("diagnostics", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")

    # 5) 异常钩子 + faulthandler（原生崩溃也能留下记录）
    if install_hooks:
        step = time.perf_counter()
        try:
            install_exception_hooks(context)
            _install_faulthandler(context)
            context.phase_ok("hooks", time.perf_counter() - step)
        except Exception as exc:
            context.phase_failed("hooks", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")

    write_startup_log(context, started)
    return context


def write_startup_log(context: StartupContext, started: float | None = None) -> None:
    """把本次启动的诊断信息与阶段耗时写入 ``startup.log``。"""
    logger = _rotating_logger("docmorph.startup", context.log_dir / STARTUP_LOG_NAME)
    total = int((time.perf_counter() - (started or context._started)) * 1000)
    lines = [
        "===== DocMorph 启动 =====",
        f"safe_mode: {context.safe_mode}",
        f"phases: {context.summary() or '(无)'}",
        f"elapsed_ms: {total}",
    ]
    for key, value in context.diagnostics.items():
        lines.append(f"{key}: {value}")
    if context.degraded:
        lines.append("degraded:")
        lines.extend(f"  - {item}" for item in context.degraded)
    logger.info("\n".join(lines))


def crash_logger(log_dir: Path | None = None) -> logging.Logger:
    """启动异常日志器（轮转，1MB × 3）。"""
    directory = Path(log_dir) if log_dir else default_log_dir()
    return _rotating_logger("docmorph.startup.crash", directory / CRASH_LOG_NAME, logging.ERROR)


def log_startup_error(
    exc: BaseException,
    context: StartupContext | None = None,
    stage: str = "",
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """记录一次启动/运行期异常，返回崩溃日志路径（失败则 None）。"""
    log_dir = context.log_dir if context else default_log_dir()
    logger = crash_logger(log_dir)
    info: dict[str, Any] = {"stage": stage or "(未标注)"}
    if context is not None:
        info["safe_mode"] = context.safe_mode
        info["phases"] = context.summary()
        info["degraded"] = "; ".join(context.degraded)
        info.update({k: v for k, v in context.diagnostics.items() if k not in info})
    else:
        with contextlib.suppress(Exception):
            info.update(diagnostics())
    if extra:
        info.update(extra)
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    _write_report(logger, f"异常：{type(exc).__name__}", text, info)
    path = log_dir / CRASH_LOG_NAME
    return path if path.exists() else None


def install_exception_hooks(context: StartupContext | None = None) -> None:
    """安装 ``sys.excepthook`` / ``threading.excepthook``：任何未捕获异常都留下诊断记录。"""
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb) -> None:
        with contextlib.suppress(Exception):
            log_startup_error(exc_value, context, stage="main-thread")
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook

    def _thread_hook(args) -> None:
        if args.exc_type is SystemExit:
            return
        with contextlib.suppress(Exception):
            log_startup_error(args.exc_value, context, stage=f"thread:{args.thread.name}")

    threading.excepthook = _thread_hook


def _install_faulthandler(context: StartupContext) -> None:
    """原生崩溃（访问违例等）时把栈写入文件。

    注意：**必须持有文件对象引用**——文件对象一旦被回收就会关闭 fd，
    而 faulthandler 仍会往该 fd 写，反而可能导致二次崩溃。
    另外在 pytest 进程里不接管 faulthandler，避免干扰 pytest 自身的崩溃诊断。
    """
    global _FAULT_HANDLE
    if "pytest" in sys.modules and not _FAULT_FORCE:
        return
    path = context.log_dir / FAULT_LOG_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8")
    except OSError:
        return
    try:
        faulthandler.enable(file=handle, all_threads=True)
    except (RuntimeError, ValueError):
        handle.close()
        return
    _FAULT_HANDLE = handle


def guard(stage: str, context: StartupContext | None, default: Callable[[], Any] | None = None) -> Callable:
    """装饰器/上下文辅助：把某阶段的异常记录到崩溃日志并降级继续。"""

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            step = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                if context is not None:
                    context.phase_failed(stage, time.perf_counter() - step, f"{type(exc).__name__}: {exc}")
                log_startup_error(exc, context, stage=stage)
                if default is not None:
                    return default()
                return None
            if context is not None:
                context.phase_ok(stage, time.perf_counter() - step)
            return result

        return wrapper

    return decorator


def show_fatal_message(title: str, message: str) -> None:
    """在无控制台（``--windowed``）的情况下也能让用户看到错误：优先弹原生对话框。

    自动化环境（pytest / 显式设置 ``DOCMORPH_NO_DIALOG``）里跳过模态对话框——
    否则会一直等待用户点击，表现为"卡住"。这种情况改为输出到 stderr。
    """
    if os.environ.get("DOCMORPH_NO_DIALOG") or "pytest" in sys.modules:
        with contextlib.suppress(Exception):
            print(f"{title}\n{message}", file=sys.stderr, flush=True)
        return
    with contextlib.suppress(Exception):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
        return
    with contextlib.suppress(Exception):
        print(f"{title}\n{message}", file=sys.stderr, flush=True)
