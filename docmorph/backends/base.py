"""转换后端抽象。

一个"后端"= 一种把 ``源格式`` 变成 ``目标格式`` 的具体手段（库、外部程序或 COM）。
后端只关心"我能不能做"和"怎么做"，**不做**路由决策、冲突处理、日志落盘
（那些是 registry / engine 的职责）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docmorph.capability import CapabilityReport
from docmorph.formats import Format
from docmorph.settings.paths import TempWorkspace


@dataclass
class BackendOutcome:
    """后端执行结果：产物路径 + 需要提示用户的信息。"""

    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ConversionBackend(ABC):
    """所有后端的基类。"""

    id: str = "backend"
    label: str = "转换后端"
    #: 是否需要独占执行（Office COM 不支持并发），引擎会据此串行化
    serial: bool = False
    #: 该后端依赖的环境能力 id（用于报告"缺什么"）
    capability_id: str = ""

    @abstractmethod
    def available(self, report: CapabilityReport) -> bool:
        """当前环境是否可用。"""

    @abstractmethod
    def handles(self, source: Format, target: Format) -> bool:
        """是否直接支持这一对格式（不含链式中间步骤）。"""

    @abstractmethod
    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        """执行转换。

        :raises DocMorphError: 任一失败情形（由引擎翻译成 :class:`ConversionStatus`）。
        """

    def unavailable_reason(self, report: CapabilityReport) -> str:
        """不可用原因（用于提示用户）。"""
        capability = report.get(self.capability_id)
        return capability.hint or capability.detail or f"{self.label} 不可用"

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<{type(self).__name__} id={self.id}>"


def ensure_parent(path: Path) -> None:
    """确保输出文件的父目录存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)


def verify_output(path: Path, backend_label: str) -> Path:
    """确认后端真的产出了文件（"生成文件"≠"转换正确"，但至少要有文件）。"""
    from docmorph.errors import ConversionFailedError

    if not path.exists() or path.stat().st_size == 0:
        raise ConversionFailedError(
            f"{backend_label} 未产生有效输出文件：{path.name}", backend_label
        )
    return path


def human_size(path: Path) -> str:
    """人类可读的文件大小（日志/提示用）。"""
    size = path.stat().st_size if path.exists() else 0
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}GB"
