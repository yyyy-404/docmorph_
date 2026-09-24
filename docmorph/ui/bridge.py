"""桌面壳与界面之间的桥接层。

前端通过 ``window.pywebview.api`` 调用这里的方法，全部返回 JSON 可序列化的字典。
转换任务在后台线程执行，界面以固定间隔调用 :meth:`Api.get_state` 拉取进度
（比注入 JS 更稳，且不依赖具体 shell 实现——将来换 Tauri 时只需替换这一层）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docmorph import __version__
from docmorph.formats import parse_format
from docmorph.jobs import JobOutcome
from docmorph.logging_setup import get_logger
from docmorph.results import ConflictPolicy, ConversionResult
from docmorph.services import ApplicationService

logger = get_logger("ui")

THEME_COLORS = ["#FFF9D2", "#FFEBCC", "#BFDDF0", "#8CC0EB"]
MAX_TASKS_IN_STATE = 400


@dataclass
class UiSelection:
    """界面当前选择的输入。"""

    files: list[Path]
    directory: Path | None = None
    notes: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


class Api:
    """暴露给前端的接口集合。"""

    def __init__(self, service: ApplicationService) -> None:
        self.service = service
        self.window: Any = None
        self.selection = UiSelection(files=[], directory=None)
        self.tasks: list[dict[str, Any]] = []
        self.summary: dict[str, Any] | None = None
        self.running = False
        self.progress = 0
        self.progress_text = "就绪"
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def attach(self, window: Any) -> None:
        self.window = window

    # ------------------------------------------------------------------ 状态
    def get_state(self) -> dict[str, Any]:
        settings = self.service.settings
        with self._lock:
            tasks = list(self.tasks[-MAX_TASKS_IN_STATE:])
            summary = self.summary
            running = self.running
            progress = self.progress
            progress_text = self.progress_text
        return {
            "version": __version__,
            "platform": sys.version.split()[0],
            "running": running,
            "cancel_requested": self._cancel.is_set(),
            "progress": progress,
            "progress_text": progress_text,
            "summary": summary,
            "tasks": tasks,
            "output_directory": str(settings.output_directory),
            "input_directory": str(settings.input_directory),
            "keep_structure": settings.keep_structure,
            "conflict_policy": settings.conflict_policy,
            "max_workers": settings.max_workers,
            "xlsx_csv_mode": settings.xlsx_csv_mode,
            "extract_media": settings.extract_media,
            "pdf_backend_preference": settings.pdf_backend_preference,
            "theme_colors": THEME_COLORS,
            "log_tail": [entry.format() for entry in self.service.log_entries(300)],
            "log_file": str(self.service.log_file or ""),
            "config_path": str(self.service.config.path),
            "config_warnings": list(self.service.config.warnings),
            "webview_available": True,
            "safe_mode": self.service.safe_mode,
            "capability_pending": not self.service.capability_provider.loaded,
            "temp_retention_hours": settings.temp_retention_hours,
        }

    def get_catalog(self) -> list[dict[str, Any]]:
        return self.service.catalog()

    def get_capabilities(self) -> dict[str, Any]:
        """能力快照：**不阻塞界面**。

        未完成完整检测时先返回启动轻量结果（``pending=True``），同时后台开始预热；
        前端会轮询直到 ``pending`` 变假。
        """
        payload = self.service.capabilities_snapshot(wait=False)
        if payload.get("pending"):
            self.service.start_capability_warmup()
        return payload

    def recheck_capabilities(self) -> dict[str, Any]:
        """手动重新检测（系统能力页的"重新检测"按钮）：真实导入依赖做权威自检。"""
        return self.service.deep_recheck_capabilities()

    def get_logs(self, limit: int = 300) -> list[str]:
        return [entry.format() for entry in self.service.log_entries(int(limit))]

    # ------------------------------------------------------------------ 选择
    def select_files(self) -> dict[str, Any]:
        paths = self._open_dialog(mode="open", multiple=True)
        return self._apply_paths([Path(item) for item in paths], directory=None)

    def select_folder(self) -> dict[str, Any]:
        paths = self._open_dialog(mode="folder")
        if not paths:
            return self._selection_payload()
        directory = Path(paths[0])
        return self._apply_paths([], directory=directory)

    def select_output_directory(self) -> dict[str, Any]:
        paths = self._open_dialog(mode="folder")
        if not paths:
            return {"directory": "", "files": [], "count": 0, "notes": []}
        return {"directory": paths[0], "files": [], "count": 0, "notes": []}

    def set_selection(self, payload: dict[str, Any]) -> dict[str, Any]:
        """接收界面传来的路径（拖拽或外部调用）。"""
        files = [Path(item) for item in (payload or {}).get("files", []) if item]
        directory = (payload or {}).get("directory")
        return self._apply_paths(files, directory=Path(directory) if directory else None)

    def selection_snapshot(self) -> dict[str, Any]:
        """当前选择的只读快照。"""
        return self._selection_payload()

    # ------------------------------------------------------------------ 转换
    def start_conversion(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.running:
            return {"ok": False, "message": "已有转换任务正在进行"}
        payload = payload or {}
        target = parse_format(payload.get("target"))
        if target is None:
            return {"ok": False, "message": "请选择目标格式"}

        inputs = list(self.selection.files)
        if not inputs and self.selection.directory is not None:
            inputs = self.service.directory_inputs(self.selection.directory)
        if not inputs:
            return {"ok": False, "message": "请先选择要转换的文件或目录"}

        output_directory = payload.get("output_directory") or str(
            self.service.settings.output_directory
        )
        conflict = _conflict(payload.get("conflict_policy"))
        keep_structure = bool(payload.get("keep_structure", self.service.settings.keep_structure))
        workers = int(payload.get("workers") or self.service.settings.max_workers)
        input_root = self.selection.directory if self.selection.directory else None
        if input_root is None and len(inputs) > 1:
            try:
                input_root = Path(os.path.commonpath([str(item.parent) for item in inputs]))
            except ValueError:
                input_root = None

        requests = self.service.build_requests(
            inputs,
            output_directory,
            target,
            input_root=input_root,
            keep_structure=keep_structure,
            conflict=conflict,
            options={"progress": self._on_page_progress},
        )
        if not requests:
            return {"ok": False, "message": "没有可转换的文件"}

        self._cancel = threading.Event()
        with self._lock:
            self.tasks = []
            self.summary = None
            self.running = True
            self.progress = 0
            self.progress_text = f"开始转换 {len(requests)} 个文件…"

        self._worker = threading.Thread(
            target=self._run_job, args=(requests, workers), name="docmorph-ui-job", daemon=True
        )
        self._worker.start()
        return {"ok": True, "message": f"已开始转换 {len(requests)} 个文件"}

    def _on_page_progress(self, done: int, total: int, label: str = "") -> None:
        """后端报告的页级进度（PDF 抽取/渲染等支持页进度的能力）。"""
        with self._lock:
            if not self.running:
                return
            prefix = f"{label} " if label else ""
            self.progress_text = f"{prefix}第 {done}/{total} 页"

    # ------------------------------------------------------------------ PDF 工具
    def merge_pdfs(self, payload: dict[str, Any]) -> dict[str, Any]:
        """合并 PDF：``{"inputs": [...], "output": "merged.pdf"}``。"""
        payload = payload or {}
        inputs = [Path(item) for item in payload.get("inputs", []) if item]
        output = payload.get("output") or str(
            Path(self.service.settings.output_directory) / "merged.pdf"
        )
        if len(inputs) < 2:
            return {"ok": False, "message": "请至少选择两个 PDF 文件"}
        result = self.service.merge_pdfs(inputs, output)
        return {
            "ok": result.ok,
            "message": result.summary() if result.ok else (result.error or result.status.label),
            "outputs": [str(path) for path in result.outputs],
        }

    def split_pdf(self, payload: dict[str, Any]) -> dict[str, Any]:
        """拆分 PDF：``{"input": "a.pdf", "pages": "1-3,5", "output_directory": "..."}``。"""
        payload = payload or {}
        source = payload.get("input")
        if not source:
            return {"ok": False, "message": "请选择要拆分的 PDF"}
        output_dir = payload.get("output_directory") or str(self.service.settings.output_directory)
        result = self.service.split_pdf(
            source, output_dir, ranges=payload.get("pages") or None, conflict=payload.get("conflict_policy")
        )
        return {
            "ok": result.ok,
            "message": result.summary() if result.ok else (result.error or result.status.label),
            "outputs": [str(path) for path in result.outputs],
        }

    def cancel_conversion(self) -> dict[str, Any]:
        if not self.running:
            return {"ok": False, "message": "当前没有正在进行的任务"}
        self._cancel.set()
        with self._lock:
            self.progress_text = "正在取消（当前文件完成后停止）…"
        return {"ok": True, "message": "已请求取消"}

    # ------------------------------------------------------------------ 其它
    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = payload or {}
        aliases = {"input_directory": "input_directory", "output_directory": "output_directory"}
        changes: dict[str, Any] = {}
        for key, value in payload.items():
            if key in aliases or key in {
                "conflict_policy",
                "max_workers",
                "keep_structure",
                "xlsx_csv_mode",
                "extract_media",
                "pdf_backend_preference",
                "temp_retention_hours",
            }:
                changes[aliases.get(key, key)] = value
        if not changes:
            return {"ok": False, "message": "没有可保存的设置项"}
        try:
            self.service.update_settings(**changes)
        except ValueError as exc:  # 取值非法时给出人话提示
            return {"ok": False, "message": f"设置未生效：{exc}"}
        return {"ok": True, "message": "设置已保存"}

    def open_path(self, path: str) -> dict[str, Any]:
        target = Path(path)
        if not target.exists():
            return {"ok": False, "message": f"路径不存在：{path}"}
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]  # Windows 专用
        except Exception as exc:
            return {"ok": False, "message": f"无法打开：{exc}"}
        return {"ok": True, "message": "已打开"}

    def reveal_output(self) -> dict[str, Any]:
        directory = Path(self.service.settings.output_directory)
        if not directory.exists():
            return {"ok": False, "message": "输出目录尚不存在"}
        try:
            subprocess.Popen(["explorer", str(directory)])
        except Exception as exc:
            return {"ok": False, "message": f"无法打开资源管理器：{exc}"}
        return {"ok": True, "message": "已打开输出目录"}

    def quit(self) -> dict[str, Any]:
        if self.window is not None:
            self.window.destroy()
        return {"ok": True, "message": "正在退出"}

    # ------------------------------------------------------------------ 内部
    def _run_job(self, requests, workers: int) -> None:
        def _progress(result: ConversionResult, done: int, total: int) -> None:
            with self._lock:
                self.tasks.append(_task_payload(result))
                self.progress = int(done / max(1, total) * 100)
                self.progress_text = result.summary()

        try:
            self._run_requests(requests, workers, _progress)
        except Exception as exc:
            logger.exception("界面任务执行失败")
            with self._lock:
                self.progress_text = f"任务异常：{exc}"
        finally:
            with self._lock:
                self.running = False
                if self.summary:
                    self.progress_text = (
                        f"完成：成功 {self.summary['succeeded']} / {self.summary['total']}"
                    )

    def _run_requests(self, requests, workers: int, progress) -> JobOutcome:
        from docmorph.jobs import JobRunner

        runner = JobRunner(self.service.engine, max_workers=workers)
        outcome = runner.run(requests, on_progress=progress, cancel_event=self._cancel)
        with self._lock:
            self.summary = outcome.summary.as_dict()
        return outcome

    def _apply_paths(
        self, files: Sequence[Path], directory: Path | None
    ) -> dict[str, Any]:
        if directory is not None:
            expanded = self.service.directory_inputs(directory)
            notes = [] if expanded else [f"目录中没有可转换的文件：{directory}"]
            self.selection = UiSelection(files=expanded, directory=directory, notes=notes)
        else:
            expanded, notes = self.service.expand_inputs(files)
            self.selection = UiSelection(files=expanded, directory=None, notes=notes)
        return self._selection_payload()

    def _selection_payload(self) -> dict[str, Any]:
        return {
            "files": [str(item) for item in self.selection.files],
            "directory": str(self.selection.directory) if self.selection.directory else "",
            "count": len(self.selection.files),
            "notes": list(self.selection.notes or []),
        }

    def _open_dialog(self, mode: str, multiple: bool = False) -> list[str]:
        """调用系统文件对话框（由 pywebview 实现）。"""
        try:
            import webview
        except ImportError:
            return []
        if self.window is None:
            return []
        if mode == "folder":
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        else:
            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=multiple, file_types=_file_types()
            )
        if not result:
            return []
        if isinstance(result, (str, os.PathLike)):
            return [os.fspath(result)]
        return [os.fspath(item) for item in result]


def _file_types() -> tuple:
    """文件对话框的过滤器（pywebview 语法）。"""
    return (
        "所有支持的文档 (*.pdf;*.docx;*.xlsx;*.pptx;*.md;*.html;*.htm;*.txt;*.csv)",
        "PDF (*.pdf)",
        "Word (*.docx)",
        "Excel (*.xlsx)",
        "Markdown (*.md)",
        "网页 (*.html;*.htm)",
        "文本 (*.txt)",
        "CSV (*.csv)",
        "所有文件 (*.*)",
    )


def _task_payload(result: ConversionResult) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:12],
        "input": str(result.input_path),
        "file_name": result.input_path.name,
        "status": result.status.value,
        "status_label": result.status.label,
        "backend": result.backend,
        "outputs": [str(path) for path in result.outputs],
        "warnings": list(result.warnings),
        "error": result.error,
        "duration_s": result.duration_s,
    }


def _conflict(value: Any) -> ConflictPolicy | None:
    if not value:
        return None
    try:
        return ConflictPolicy(str(value))
    except ValueError:
        return None
