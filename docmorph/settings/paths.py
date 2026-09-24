"""应用目录与临时工作区解析。

原则：**运行时数据不落在项目目录里**。

* 配置：``%APPDATA%\\DocMorph``
* 日志 / 缓存 / 临时文件：``%LOCALAPPDATA%\\DocMorph``
* 默认输入输出：``<用户文档>\\DocMorph\\input|output``
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

APP_NAME = "DocMorph"


def _env_dir(variable: str, fallback: Path) -> Path:
    raw = os.environ.get(variable)
    return Path(raw) if raw else fallback


def app_config_dir() -> Path:
    """用户配置文件目录。"""
    base = _env_dir("APPDATA", Path.home() / "AppData" / "Roaming")
    return base / APP_NAME


def app_data_dir() -> Path:
    """日志、缓存等本地数据目录。"""
    base = _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    return base / APP_NAME


def user_documents_dir() -> Path:
    """用户"文档"目录（不存在时退回家目录）。"""
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def default_input_dir() -> Path:
    return user_documents_dir() / APP_NAME / "input"


def default_output_dir() -> Path:
    return user_documents_dir() / APP_NAME / "output"


def default_log_dir() -> Path:
    return app_data_dir() / "logs"


def default_config_path() -> Path:
    return app_config_dir() / "config.ini"


class TempWorkspace:
    """一次会话共用的临时目录，退出时整体清理。

    所有后端产生的中间文件（分块 PDF、页面图片、pandoc 媒体等）都必须写到这里，
    不允许写进项目目录、当前工作目录或用户的输出目录。
    """

    def __init__(self, root: Path | None = None, prefix: str = "session") -> None:
        if root is None or str(root) in {"", "."}:
            base = app_data_dir() / "temp"
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
    """系统临时目录（供不需要会话隔离的场景使用）。"""
    return Path(tempfile.gettempdir())


def temp_root(custom: Path | None = None) -> Path:
    """临时工作区根目录（默认 ``%LOCALAPPDATA%\\DocMorph\\temp``）。

    空值 / ``Path(".")`` 一律视为“未指定”，返回默认绝对路径，
    避免相对路径被 Word 等 COM 组件按 system32 解析。
    """
    if custom is None or str(custom) in {"", "."}:
        return app_data_dir() / "temp"
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
