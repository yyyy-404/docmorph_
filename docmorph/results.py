"""转换请求 / 结果的数据模型。

取代旧实现里"返回 bool + 打日志"的模糊表达：调用方必须能区分
「成功 / 有警告的成功 / 已存在被跳过 / 不支持 / 后端缺失 / 输入非法 / 失败 / 取消」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from docmorph.formats import Format


class ConflictPolicy(str, Enum):
    """目标文件已存在时的处理方式。"""

    RENAME = "rename"      # 自动改名（默认，绝不覆盖用户数据）
    OVERWRITE = "overwrite"
    SKIP = "skip"


class ConversionStatus(str, Enum):
    """一次转换的最终状态。"""

    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    SKIPPED_EXISTS = "skipped_exists"
    UNSUPPORTED = "unsupported"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    INVALID_INPUT = "invalid_input"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_success(self) -> bool:
        return self in (ConversionStatus.SUCCESS, ConversionStatus.SUCCESS_WITH_WARNINGS)

    @property
    def label(self) -> str:
        """中文展示名（UI/CLI 共用）。"""
        return _STATUS_LABELS[self]


_STATUS_LABELS: dict[ConversionStatus, str] = {
    ConversionStatus.SUCCESS: "成功",
    ConversionStatus.SUCCESS_WITH_WARNINGS: "成功（有提示）",
    ConversionStatus.SKIPPED_EXISTS: "已跳过（目标已存在）",
    ConversionStatus.UNSUPPORTED: "不支持",
    ConversionStatus.BACKEND_UNAVAILABLE: "缺少转换引擎",
    ConversionStatus.INVALID_INPUT: "输入无效",
    ConversionStatus.FAILED: "失败",
    ConversionStatus.CANCELLED: "已取消",
}


@dataclass
class ConversionRequest:
    """一次转换所需的最小信息集合。"""

    input_path: Path
    output_path: Path
    source_format: Format
    target_format: Format
    conflict: ConflictPolicy = ConflictPolicy.RENAME
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)


@dataclass
class ConversionResult:
    """一次转换的结果。"""

    request: ConversionRequest
    status: ConversionStatus
    backend: str = ""
    duration_ms: int = 0
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    traceback: str = ""

    @property
    def ok(self) -> bool:
        return self.status.is_success

    @property
    def input_path(self) -> Path:
        return self.request.input_path

    @property
    def primary_output(self) -> Path | None:
        return self.outputs[0] if self.outputs else None

    @property
    def duration_s(self) -> float:
        return round(self.duration_ms / 1000, 2)

    def summary(self) -> str:
        """一行中文摘要，CLI 与 UI 共用。"""
        name = self.request.input_path.name
        head = f"{name}: {self.status.label}"
        if self.backend:
            head += f" [{self.backend}]"
        if self.status.is_success and self.outputs:
            head += f" → {self.outputs[0].name}"
        if self.duration_ms:
            head += f" ({self.duration_s}s)"
        if self.error and not self.status.is_success:
            head += f" — {self.error}"
        return head


@dataclass
class BatchSummary:
    """一批转换的汇总统计。"""

    total: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: int = 0
    duration_ms: int = 0

    @property
    def duration_s(self) -> float:
        return round(self.duration_ms / 1000, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "skipped": self.skipped,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "duration_s": self.duration_s,
        }
