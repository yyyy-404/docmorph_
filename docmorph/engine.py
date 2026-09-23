"""转换引擎：把 :class:`ConversionRequest` 变成 :class:`ConversionResult`。

职责边界：

* 校验输入、解析冲突策略、挑选方案（registry）、按步骤执行、计时、记录日志；
* **不**决定 UI 长什么样，**不**关心任务队列（那是 services / jobs 的事）；
* 所有异常在这里被翻译成明确的状态，绝不向调用方抛"裸异常"。
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docmorph.backends import build_default_backends
from docmorph.backends.base import ConversionBackend
from docmorph.capability import CapabilityReport, detect
from docmorph.errors import (
    BackendUnavailableError,
    ConversionCancelledError,
    DocMorphError,
    InvalidInputError,
    OutputError,
    UnsupportedConversionError,
)
from docmorph.formats import Format, detect_format
from docmorph.logging_setup import get_logger
from docmorph.registry import (
    Plan,
    declared_targets,
    plan_backends,
    plans,
    select_plan,
)
from docmorph.results import (
    ConflictPolicy,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
)
from docmorph.settings import Settings
from docmorph.settings.paths import TempWorkspace

logger = get_logger("engine")


class ConversionEngine:
    """本地文档转换引擎。"""

    def __init__(
        self,
        settings: Settings | None = None,
        capabilities: CapabilityReport | None = None,
        backends: dict[str, ConversionBackend] | None = None,
    ) -> None:
        from docmorph.settings.schema import DEFAULTS, build_settings

        self.settings = settings or build_settings(
            {section: dict(values) for section, values in DEFAULTS.items()}, []
        )
        self.capabilities = capabilities or detect()
        self.backends = backends or build_default_backends(self.settings.office_timeout_seconds)

    # ------------------------------------------------------------------ 能力查询
    def declared_targets(self, source: Format) -> list[Format]:
        """声明支持的目标格式（不判断环境）。"""
        return declared_targets(source)

    def available_targets(self, source: Format) -> list[Format]:
        """当前环境**真的能跑**的目标格式。"""
        result = []
        for target in declared_targets(source):
            plan, _ = select_plan(
                source, target, self.backends, self.capabilities, self.settings.pdf_backend_preference
            )
            if plan:
                result.append(target)
        return result

    def unavailable_reason(self, source: Format, target: Format) -> str:
        _, reason = select_plan(
            source, target, self.backends, self.capabilities, self.settings.pdf_backend_preference
        )
        return reason

    # ------------------------------------------------------------------ 主流程
    def convert(self, request: ConversionRequest) -> ConversionResult:
        """执行一次转换（含链式方案）。"""
        started = time.perf_counter()
        try:
            return self._convert(request, started)
        except ConversionCancelledError as exc:
            return self._fail(request, ConversionStatus.CANCELLED, str(exc), started)
        except UnsupportedConversionError as exc:
            return self._fail(request, ConversionStatus.UNSUPPORTED, str(exc), started)
        except InvalidInputError as exc:
            return self._fail(request, ConversionStatus.INVALID_INPUT, str(exc), started)
        except (BackendUnavailableError, OutputError) as exc:
            status = (
                ConversionStatus.BACKEND_UNAVAILABLE
                if isinstance(exc, BackendUnavailableError)
                else ConversionStatus.FAILED
            )
            return self._fail(request, status, str(exc), started)
        except DocMorphError as exc:
            return self._fail(request, ConversionStatus.FAILED, str(exc), started, traceback_text=traceback.format_exc())
        except Exception as exc:
            logger.exception("未预期的转换错误")
            return self._fail(
                request,
                ConversionStatus.FAILED,
                f"未预期的错误：{type(exc).__name__}: {exc}",
                started,
                traceback_text=traceback.format_exc(),
            )

    def _convert(self, request: ConversionRequest, started: float) -> ConversionResult:
        source_path = Path(request.input_path)
        self._validate_input(source_path)
        source_format = request.source_format
        target_format = request.target_format

        if source_format is target_format:
            raise UnsupportedConversionError(
                source_format.value, target_format.value, "源格式与目标格式相同"
            )

        plan, reason = select_plan(
            source_format,
            target_format,
            self.backends,
            self.capabilities,
            self.settings.pdf_backend_preference,
        )
        if plan is None:
            if plans(source_format, target_format):
                raise BackendUnavailableError("", reason, "")
            raise UnsupportedConversionError(source_format.value, target_format.value, reason)

        target_path, status = self._resolve_target(request)
        if status is ConversionStatus.SKIPPED_EXISTS:
            return ConversionResult(
                request=request,
                status=status,
                warnings=[f"目标文件已存在，按设置跳过：{target_path.name}"],
                duration_ms=self._elapsed_ms(started),
            )
        if request.conflict is ConflictPolicy.OVERWRITE and target_path.exists():
            with_suppress = self._remove_quietly(target_path)
            if not with_suppress:
                raise OutputError(f"无法覆盖已存在的文件：{target_path.name}")

        outputs, warnings = self._execute_plan(request, plan, target_path)
        status = ConversionStatus.SUCCESS_WITH_WARNINGS if warnings else ConversionStatus.SUCCESS
        result = ConversionResult(
            request=request,
            status=status,
            backend=" + ".join(plan_backends(plan)),
            duration_ms=self._elapsed_ms(started),
            outputs=outputs,
            warnings=warnings,
        )
        logger.info(
            "转换成功 | %s | %s → %s | 后端=%s | %.2fs",
            source_path.name,
            source_format.value,
            target_format.value,
            result.backend,
            result.duration_s,
        )
        return result

    # ------------------------------------------------------------------ 步骤执行
    def _execute_plan(
        self, request: ConversionRequest, plan: Plan, target_path: Path
    ) -> tuple[list[Path], list[str]]:
        options: dict[str, Any] = {
            "office_timeout_seconds": self.settings.office_timeout_seconds,
            "xlsx_csv_mode": self.settings.xlsx_csv_mode,
            "extract_media": self.settings.extract_media,
        }
        options.update(request.options)
        cancel_event = options.get("cancel_event")
        workspace = TempWorkspace(
            root=self.settings.temp_directory or None,
            prefix=f"convert-{Path(request.input_path).stem[:24]}",
        )
        warnings: list[str] = []
        try:
            current = Path(request.input_path)
            current_format = request.source_format
            outputs: list[Path] = []
            for index, (backend_id, step_format) in enumerate(plan):
                if cancel_event is not None and cancel_event.is_set():
                    raise ConversionCancelledError("任务已取消")
                backend = self.backends[backend_id]
                is_last = index == len(plan) - 1
                destination = target_path if is_last else workspace.file(
                    f"step{index + 1}-{Path(request.input_path).stem}.{step_format.value}"
                )
                logger.debug(
                    "步骤 %d/%d：%s 将 %s 转为 %s",
                    index + 1,
                    len(plan),
                    backend.label,
                    current_format.value,
                    step_format.value,
                )
                outcome = backend.convert(
                    current, destination, current_format, step_format, options, workspace
                )
                warnings.extend(outcome.warnings)
                outputs = outcome.outputs
                current = destination
                current_format = step_format
            return outputs, warnings
        finally:
            workspace.cleanup()

    # ------------------------------------------------------------------ 校验/路径
    @staticmethod
    def _validate_input(source_path: Path) -> None:
        if not source_path.exists():
            raise InvalidInputError(f"输入文件不存在：{source_path}")
        if source_path.is_dir():
            raise InvalidInputError(f"输入是目录而不是文件：{source_path}")
        if source_path.stat().st_size == 0:
            raise InvalidInputError(f"输入文件为空：{source_path.name}")

    def _resolve_target(self, request: ConversionRequest) -> tuple[Path, ConversionStatus]:
        target = Path(request.output_path)
        if target.resolve() == Path(request.input_path).resolve():
            raise OutputError("输出路径与输入路径相同，拒绝执行以避免覆盖原始文件")
        if not target.exists():
            return target, ConversionStatus.SUCCESS
        if request.conflict is ConflictPolicy.SKIP:
            return target, ConversionStatus.SKIPPED_EXISTS
        if request.conflict is ConflictPolicy.OVERWRITE:
            return target, ConversionStatus.SUCCESS
        return unique_path(target), ConversionStatus.SUCCESS

    @staticmethod
    def _remove_quietly(path: Path) -> bool:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except OSError:
            return False

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _fail(
        self,
        request: ConversionRequest,
        status: ConversionStatus,
        message: str,
        started: float,
        traceback_text: str = "",
    ) -> ConversionResult:
        level = logging.WARNING if status is ConversionStatus.SKIPPED_EXISTS else logging.ERROR
        logger.log(
            level,
            "%s | %s → %s | %s",
            status.label,
            request.source_format.value,
            request.target_format.value,
            message,
        )
        return ConversionResult(
            request=request,
            status=status,
            duration_ms=self._elapsed_ms(started),
            error=message,
            traceback=traceback_text,
        )

    # ------------------------------------------------------------------ 其它能力
    def merge_pdfs(self, inputs: list[Path], target: Path) -> ConversionResult:
        """合并多个 PDF（旧版核心已有能力，这里正式暴露）。"""
        request = ConversionRequest(
            input_path=inputs[0] if inputs else Path("."),
            output_path=target,
            source_format=Format.PDF,
            target_format=Format.PDF,
        )
        started = time.perf_counter()
        try:
            if len(inputs) < 2:
                raise InvalidInputError("至少需要两个 PDF 文件才能合并")
            for item in inputs:
                if not item.exists():
                    raise InvalidInputError(f"待合并文件不存在：{item}")
            from docmorph.backends.python_backend import import_pymupdf

            pymupdf = import_pymupdf()
            target.parent.mkdir(parents=True, exist_ok=True)
            with pymupdf.open() as merged:
                for item in inputs:
                    with pymupdf.open(str(item)) as document:
                        merged.insert_pdf(document)
                merged.save(str(target))
            return ConversionResult(
                request=request,
                status=ConversionStatus.SUCCESS,
                backend="python",
                duration_ms=self._elapsed_ms(started),
                outputs=[target],
            )
        except DocMorphError as exc:
            return self._fail(request, ConversionStatus.FAILED, str(exc), started)
        except Exception as exc:
            return self._fail(
                request,
                ConversionStatus.FAILED,
                f"合并失败：{type(exc).__name__}: {exc}",
                started,
                traceback.format_exc(),
            )

    def capability_snapshot(self) -> dict[str, Any]:
        return self.capabilities.as_dict()


def unique_path(path: Path) -> Path:
    """在目标已存在时生成 ``name (2).ext`` 形式的新路径。"""
    if not path.exists():
        return path
    directory = path.parent
    stem, suffix = path.stem, path.suffix
    for index in range(2, 1000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem} ({os.getpid()}){suffix}"


def make_request(
    input_path: os.PathLike | str,
    output_path: os.PathLike | str | None = None,
    target_format: Format | str | None = None,
    settings: Settings | None = None,
    conflict: ConflictPolicy | None = None,
    options: Mapping[str, Any] | None = None,
) -> ConversionRequest:
    """构造请求的便捷函数（自动识别源格式与默认输出路径）。"""
    source = Path(input_path)
    source_format = detect_format(source)
    if source_format is None:
        raise InvalidInputError(f"无法识别输入文件格式：{source.name}")
    resolved_target = target_format
    if resolved_target is None and output_path is not None:
        resolved_target = detect_format(output_path)
    if resolved_target is None:
        if settings is None:
            from docmorph.settings.schema import DEFAULTS, build_settings

            settings = build_settings({section: dict(v) for section, v in DEFAULTS.items()}, [])
        resolved_target = settings.default_target_for(source_format)
    target_format_value = (
        resolved_target if isinstance(resolved_target, Format) else Format(str(resolved_target))
    )
    if output_path is None:
        destination = source.with_name(f"{source.stem}.{target_format_value.value}")
    else:
        candidate = Path(output_path)
        if candidate.is_dir() or not candidate.suffix:
            destination = candidate / f"{source.stem}.{target_format_value.value}"
        else:
            destination = candidate
    policy = conflict
    if policy is None:
        policy = ConflictPolicy(settings.conflict_policy) if settings else ConflictPolicy.RENAME
    return ConversionRequest(
        input_path=source,
        output_path=destination,
        source_format=source_format,
        target_format=target_format_value,
        conflict=policy,
        options=dict(options or {}),
    )


def cancel_event() -> threading.Event:
    """便捷构造取消信号。"""
    return threading.Event()
