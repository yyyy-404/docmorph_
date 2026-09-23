"""Pandoc 后端：结构化文档之间的转换（docx/md/html/plain/csv）。

关键格式映射（实测驱动）：

* pandoc **没有** ``txt`` 目标格式，纯文本输出必须用 ``plain``；
* pandoc 也没有 ``txt`` 读取器，纯文本输入按 ``markdown`` 读取；
* 转 Markdown 且需要图片时使用 ``--extract-media``，把图片落到输出目录下的
  ``<stem>_media`` 子目录，并在结果里提示用户（不静默丢图，也不污染工作目录）。
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docmorph.backends.base import BackendOutcome, ConversionBackend, ensure_parent, verify_output
from docmorph.capability import CapabilityReport
from docmorph.errors import BackendUnavailableError, ConversionFailedError, DependencyMissingError
from docmorph.formats import PANDOC_READER, PANDOC_WRITER, Format
from docmorph.settings.paths import TempWorkspace


class PandocBackend(ConversionBackend):
    """基于 pandoc（随 ``pypandoc-binary`` 一起分发的二进制）的后端。"""

    id = "pandoc"
    label = "Pandoc"
    serial = False
    capability_id = "pandoc"

    def __init__(self) -> None:
        self._module: Any = None

    # ------------------------------------------------------------------ 能力
    def available(self, report: CapabilityReport) -> bool:
        return report.available("pandoc")

    def handles(self, source: Format, target: Format) -> bool:
        return source in PANDOC_READER and target in PANDOC_WRITER

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
        pypandoc = self._pypandoc()
        writer = PANDOC_WRITER[target_format]
        reader = PANDOC_READER[source_format]
        ensure_parent(target)

        extra_args = list(options.get("pandoc_args", ()))  # type: ignore[arg-type]
        if target_format is Format.HTML:
            extra_args.append("--standalone")
            extra_args.append("--metadata=charset=utf-8")

        warnings: list[str] = []
        outputs: list[Path] = []
        if target_format is Format.MD:
            media_dir = target.parent / f"{target.stem}_media"
            if options.get("extract_media", True):
                media_dir.mkdir(parents=True, exist_ok=True)
                extra_args.append(f"--extract-media={media_dir}")

        try:
            pypandoc.convert_file(
                str(source),
                writer,
                outputfile=str(target),
                extra_args=extra_args,
                format=reader,
            )
        except RuntimeError as exc:
            raise ConversionFailedError(f"Pandoc 转换失败：{exc}", self.label) from exc

        verify_output(target, self.label)
        outputs.append(target)

        if target_format is Format.MD:
            media_dir = target.parent / f"{target.stem}_media"
            if media_dir.is_dir() and any(media_dir.iterdir()):
                warnings.append(f"文档中的图片已抽取到 {media_dir.name}/ 目录")
        return BackendOutcome(outputs=outputs, warnings=warnings)

    # ------------------------------------------------------------------ 内部
    def _pypandoc(self):
        if self._module is None:
            try:
                self._module = importlib.import_module("pypandoc")
            except ImportError as exc:  # pragma: no cover - 由 capability 提前拦截
                raise DependencyMissingError("pypandoc-binary", self.id) from exc
            try:
                self._module.get_pandoc_version()
            except Exception as exc:
                raise BackendUnavailableError(
                    self.id,
                    f"pandoc 二进制不可用（{type(exc).__name__}）",
                    "请执行 pip install pypandoc-binary",
                ) from exc
        return self._module
