"""程序目录与运行时数据目录解析。

原则：**运行时数据全部落在程序目录下的 ``runtime/`` 里**（便携、自包含），
不写入 ``%LOCALAPPDATA%`` / ``%APPDATA%`` 下的 DocMorph 专用目录：

* 配置：``<程序目录>/config.ini``
* 日志：``<程序目录>/runtime/logs``
* 缓存：``<程序目录>/runtime/cache``
* 临时文件：``<程序目录>/runtime/temp``
* WebView：``<程序目录>/runtime/webview``
* 默认输入输出：``<用户文档>/DocMorph/input|output``（用户文档，不是运行时数据）

“程序目录”（:func:`project_root`）的判定：

* PyInstaller 打包版（Full）：``sys.executable`` 所在目录（EXE 旁）。
  **不是** ``sys._MEIPASS``——那是指向 ``_internal/`` 的临时解压目录，
  运行数据写进去既会随打包结构变化，也无法随 EXE 目录整体拷贝；
* 源码版（Slim）：项目根目录（``run.py`` / ``pyproject.toml`` 所在处，
  即本文件 ``docmorph/settings/paths.py`` 向上两级）；
* 其它安装形态（如 pip 非可编辑安装进 site-packages）：退回到当前工作目录，
  避免把运行数据写进 Python 安装目录。

所有目录**按需创建**：调用方在真正写入时 ``mkdir``，不预先生成空目录
（因此没有实际用途的 ``runtime/cache`` 不会被凭空创建）。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

APP_NAME = "DocMorph"


def project_root() -> Path:
    """“应用程序目录”：Full 取 EXE 所在目录，Slim 取项目根目录。"""
    if getattr(sys, "frozen", False):
        # PyInstaller：sys.executable 即 DocMorph.exe / DocMorphCLI.exe 的完整路径
        return Path(sys.executable).resolve().parent
    root = Path(__file__).resolve().parents[2]  # docmorph/settings/paths.py -> 项目根
    if (root / "pyproject.toml").is_file() or (root / "run.py").is_file():
        return root
    # 非源码布局（pip 安装到 site-packages 等）：退回 cwd，绝不写 site-packages
    return Path.cwd()


def runtime_dir() -> Path:
    """运行时数据根目录 ``<程序目录>/runtime``（logs/cache/temp/webview 的父目录）。"""
    return project_root() / "runtime"


def log_dir() -> Path:
    """日志目录 ``<程序目录>/runtime/logs``（按需创建）。"""
    return runtime_dir() / "logs"


def cache_dir() -> Path:
    """缓存目录 ``<程序目录>/runtime/cache``（按需创建；当前版本无独立磁盘缓存消费者）。"""
    return runtime_dir() / "cache"


def webview_dir() -> Path:
    """WebView（Edge WebView2 / Chromium）用户数据目录 ``<程序目录>/runtime/webview``。"""
    return runtime_dir() / "webview"


def app_config_dir() -> Path:
    """用户配置文件所在目录（即程序目录，``config.ini`` 与 EXE/``run.py`` 同级）。"""
    return project_root()


def app_data_dir() -> Path:
    """运行时数据目录（兼容旧名，等价于 :func:`runtime_dir`）。"""
    return runtime_dir()


def user_documents_dir() -> Path:
    """用户"文档"目录（不存在时退回家目录）。"""
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def default_input_dir() -> Path:
    return user_documents_dir() / APP_NAME / "input"


def default_output_dir() -> Path:
    return user_documents_dir() / APP_NAME / "output"


def default_log_dir() -> Path:
    return log_dir()


def default_config_path() -> Path:
    return app_config_dir() / "config.ini"


class TempWorkspace:
    """一次会话共用的临时目录，退出时整体清理。

    所有后端产生的中间文件（分块 PDF、页面图片、pandoc 媒体等）都必须写到这里
    （默认 ``<程序目录>/runtime/temp``），不允许散落在源码目录、当前工作目录
    或用户的输出目录里。
    """

    def __init__(self, root: Path | None = None, prefix: str = "session") -> None:
        if root is None or str(root) in {"", "."}:
            base = runtime_dir() / "temp"
        else:
            base = Path(root).expanduser()
            if not base.is_absolute():
                base = base.resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.path = (base / f"{prefix}-{uuid.uuid4().hex[:8]}").resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self._closed = False

    def file(self, name: str) -> Path:
        """在会话目录下取一个安全的临时文件路径。"""
        safe = os.path.basename(name) or "tmp"
        return self.path / safe

    def subdir(self, name: str) -> Path:
        safe = os.path.basename(name) or "tmp"
        target = self.path / safe
        target.mkdir(parents=True, exist_ok=True)
        return target

    def cleanup(self) -> None:
        """尽力删除会话目录；失败不影响主流程。"""
        if self._closed:
            return
        self._closed = True
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> TempWorkspace:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.cleanup()


def system_temp_dir() -> Path:
    """系统临时目录 ``%TEMP%``。

    **仅供第三方库/系统场景使用**（无法安全改写其内部行为时）；
    DocMorph 自己可控的临时文件一律走 ``runtime/temp``。
    """
    return Path(tempfile.gettempdir())


def temp_root(custom: Path | None = None) -> Path:
    """临时工作区根目录（默认 ``<程序目录>\\runtime\\temp``）。

    空值 / ``Path(".")`` 一律视为“未指定”，返回默认绝对路径，
    避免相对路径被 Word 等 COM 组件按 system32 解析。
    """
    if custom is None or str(custom) in {"", "."}:
        return runtime_dir() / "temp"
    path = Path(custom).expanduser()
    return path if path.is_absolute() else path.resolve()


def cleanup_stale_temp(root: Path | None = None, max_age_hours: float = 24.0) -> int:
    """清理过期的遗留临时目录（崩溃/强杀留下的 ``session-*`` / ``convert-*``）。

    只删除"看起来是本程序创建、且超过保留时长"的目录；任何失败都被忽略。
    返回删除的目录数。
    """
    base = temp_root(root)
    if not base.is_dir():
        return 0
    deadline = time.time() - max(0.0, max_age_hours) * 3600
    removed = 0
    try:
        entries = list(base.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.is_dir():
            continue
        if not any(entry.name.startswith(prefix) for prefix in ("session-", "convert-", "job-")):
            continue
        try:
            if entry.stat().st_mtime >= deadline:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        if not entry.exists():
            removed += 1
    return removed
