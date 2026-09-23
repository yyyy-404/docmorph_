"""应用服务层：GUI 与 CLI 共用的**唯一**编排入口。

这一层回答"用户想做什么"，而不关心"怎么点"或"怎么敲命令"：

* 展开输入（文件 / 目录 / 拖拽结果）；
* 生成输出路径（保留目录结构、同名不覆盖）；
* 组织批量任务、进度与取消；
* 提供格式目录、能力报告、诊断信息给界面展示。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from docmorph.capability import CapabilityReport, detect
from docmorph.engine import ConversionEngine, make_request
from docmorph.formats import Format, detect_format, parse_format
from docmorph.jobs import JobOutcome, JobRunner, ProgressCallback
from docmorph.logging_setup import LoggingSession, get_logger, setup_logging
from docmorph.registry import (
    SOURCE_FORMATS,
    declared_targets,
    plan_backends,
    routes_snapshot,
    select_plan,
)
from docmorph.results import ConflictPolicy, ConversionRequest, ConversionResult
from docmorph.settings import ConfigManager, Settings

logger = get_logger("services")


class ApplicationService:
    """DocMorph 的业务门面。"""

    def __init__(
        self,
        config: ConfigManager | None = None,
        settings: Settings | None = None,
        logging_session: LoggingSession | None = None,
        enable_file_log: bool = True,
    ) -> None:
        self.config = config or ConfigManager.load()
        self.settings = settings or self.config.settings()
        self._logging_session = logging_session or setup_logging(
            self.settings.log_directory, to_file=enable_file_log
        )
        self.capabilities: CapabilityReport = detect()
        self.engine = ConversionEngine(
            settings=self.settings, capabilities=self.capabilities
        )

    # ------------------------------------------------------------------ 生命周期
    @property
    def log_file(self) -> Path | None:
        return self._logging_session.log_file

    def log_text(self, limit: int = 300) -> str:
        """返回最近的日志文本（GUI 日志面板使用）。"""
        return self._logging_session.text(limit)

    def log_entries(self, limit: int | None = None):
        return self._logging_session.entries(limit)

    def shutdown(self) -> None:
        self._logging_session.shutdown()

    def __enter__(self) -> ApplicationService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()

    # ------------------------------------------------------------------ 信息
    def catalog(self) -> list[dict[str, Any]]:
        """格式目录：每个源格式支持哪些目标格式、当前是否可用、为什么不可用。"""
        entries: list[dict[str, Any]] = []
        for source in SOURCE_FORMATS:
            targets: list[dict[str, Any]] = []
            for target in self.engine.declared_targets(source):
                plan, reason = select_plan(
                    source,
                    target,
                    self.engine.backends,
                    self.capabilities,
                    self.settings.pdf_backend_preference,
                )
                targets.append(
                    {
                        "target": target.value,
                        "available": plan is not None,
                        "backends": list(plan_backends(plan)) if plan else [],
                        "reason": reason,
                    }
                )
            entries.append(
                {
                    "source": source.value,
                    "default_target": self.settings.default_target_for(source).value,
                    "targets": targets,
                }
            )
        return entries

    def capabilities_payload(self) -> dict[str, Any]:
        return self.capabilities.as_dict()

    def settings_payload(self) -> dict[str, Any]:
        payload = self.settings.as_dict()
        payload["config_path"] = str(self.config.path)
        payload["warnings"] = list(self.config.warnings)
        return payload

    def doctor(self) -> dict[str, Any]:
        """环境体检：能力 + 关键配置 + 可执行的路由数量。"""
        available_routes = 0
        total_routes = 0
        for entry in self.catalog():
            for target in entry["targets"]:
                total_routes += 1
                available_routes += 1 if target["available"] else 0
        return {
            "capabilities": self.capabilities.as_dict(),
            "settings": self.settings_payload(),
            "routes": {
                "total": total_routes,
                "available": available_routes,
                "detail": routes_snapshot(),
            },
            "log_file": str(self.log_file) if self.log_file else "",
        }

    # ------------------------------------------------------------------ 输入展开
    def expand_inputs(
        self, paths: Iterable[os.PathLike | str], recursive: bool = True
    ) -> tuple[list[Path], list[str]]:
        """把"用户给的东西"展开成待转换文件列表。

        :return: ``(文件列表, 提示信息)``
        """
        files: list[Path] = []
        notes: list[str] = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                pattern = "**/*" if recursive else "*"
                found = [
                    item
                    for item in sorted(path.glob(pattern))
                    if item.is_file() and detect_format(item) in SOURCE_FORMATS
                ]
                if not found:
                    notes.append(f"目录中没有可转换的文件：{path}")
                files.extend(found)
            elif path.is_file():
                if detect_format(path) is None:
                    notes.append(f"跳过不支持的文件类型：{path.name}")
                    continue
                files.append(path)
            else:
                notes.append(f"路径不存在：{path}")
        # 去重且保持顺序
        unique: list[Path] = []
        seen = set()
        for item in files:
            resolved = item.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(item)
        return unique, notes

    def directory_inputs(self, directory: os.PathLike | str) -> list[Path]:
        files, _ = self.expand_inputs([directory], recursive=True)
        return files

    # ------------------------------------------------------------------ 请求构造
    def build_requests(
        self,
        inputs: Sequence[Path],
        output_dir: os.PathLike | str,
        target: Format | str | None = None,
        input_root: os.PathLike | str | None = None,
        keep_structure: bool | None = None,
        conflict: ConflictPolicy | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> list[ConversionRequest]:
        """按批量规则生成请求列表。"""
        root = Path(input_root) if input_root else None
        keep = self.settings.keep_structure if keep_structure is None else keep_structure
        policy = _conflict_policy(conflict) if conflict is not None else ConflictPolicy(
            self.settings.conflict_policy
        )
        requests: list[ConversionRequest] = []
        for item in inputs:
            source_format = detect_format(item)
            if source_format is None:
                continue
            target_format = parse_format(target) or self.settings.default_target_for(source_format)
            destination = make_output_path(
                item,
                Path(output_dir),
                target_format,
                keep_structure=keep,
                input_root=root,
            )
            requests.append(
                ConversionRequest(
                    input_path=item,
                    output_path=destination,
                    source_format=source_format,
                    target_format=target_format,
                    conflict=policy,
                    options=dict(options or {}),
                )
            )
        return requests

    # ------------------------------------------------------------------ 转换
    def convert_one(
        self,
        input_path: os.PathLike | str,
        output_dir: os.PathLike | str | None = None,
        target: Format | str | None = None,
        conflict: ConflictPolicy | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> ConversionResult:
        """单文件转换（GUI 的单文件按钮、CLI 的默认模式都走这里）。"""
        source = Path(input_path)
        policy = _conflict_policy(conflict) if conflict is not None else None
        output_hint = Path(output_dir) if output_dir else None
        request = make_request(
            source,
            output_hint,
            target,
            settings=self.settings,
            conflict=policy,
            options=options,
        )
        return self.engine.convert(request)

    def convert_many(
        self,
        inputs: Sequence[Path],
        output_dir: os.PathLike | str,
        target: Format | str | None = None,
        input_root: os.PathLike | str | None = None,
        keep_structure: bool | None = None,
        conflict: ConflictPolicy | str | None = None,
        options: Mapping[str, Any] | None = None,
        on_progress: ProgressCallback | None = None,
        cancel_event: Any = None,
        workers: int | None = None,
    ) -> JobOutcome:
        """批量转换。"""
        requests = self.build_requests(
            inputs, output_dir, target, input_root, keep_structure, conflict, options
        )
        runner = JobRunner(self.engine, max_workers=workers or self.settings.max_workers)
        return runner.run(requests, on_progress=on_progress, cancel_event=cancel_event)

    def merge_pdfs(
        self, inputs: Sequence[os.PathLike | str], output_path: os.PathLike | str
    ) -> ConversionResult:
        return self.engine.merge_pdfs([Path(item) for item in inputs], Path(output_path))

    # ------------------------------------------------------------------ 设置
    def update_settings(self, **changes: Any) -> Settings:
        """就地更新设置并重建引擎（GUI 设置面板使用）。"""
        self.settings = self.config.apply_changes(changes)
        self.engine = ConversionEngine(settings=self.settings, capabilities=self.capabilities)
        return self.settings


def _conflict_policy(value: ConflictPolicy | str) -> ConflictPolicy:
    if isinstance(value, ConflictPolicy):
        return value
    return ConflictPolicy(str(value).strip().lower())


def make_output_path(
    file_path: Path,
    output_dir: Path,
    target_format: Format,
    keep_structure: bool = False,
    input_root: Path | None = None,
) -> Path:
    """计算输出路径：可选保留相对目录结构；同名由引擎按冲突策略处理。"""
    if keep_structure and input_root is not None:
        try:
            relative = file_path.resolve().relative_to(Path(input_root).resolve())
            directory = output_dir / relative.parent
        except ValueError:
            directory = output_dir
    else:
        directory = output_dir
    return directory / f"{file_path.stem}.{target_format.value}"


def supported_sources() -> Sequence[Format]:
    return SOURCE_FORMATS


def formats_for(source: Format | str) -> list[Format]:
    """某源格式声明的目标格式（离线，不依赖环境）。"""
    fmt = parse_format(source)
    if fmt is None:
        return []
    return list(declared_targets(fmt))
