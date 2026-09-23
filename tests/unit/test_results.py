"""结果模型的状态语义。"""

from __future__ import annotations

from pathlib import Path

from docmorph.formats import Format
from docmorph.results import (
    BatchSummary,
    ConflictPolicy,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
)


def build_result(status: ConversionStatus, **kwargs) -> ConversionResult:
    request = ConversionRequest(
        input_path=Path("in.docx"),
        output_path=Path("out.pdf"),
        source_format=Format.DOCX,
        target_format=Format.PDF,
    )
    return ConversionResult(request=request, status=status, **kwargs)


def test_only_success_states_are_ok():
    assert build_result(ConversionStatus.SUCCESS).ok
    assert build_result(ConversionStatus.SUCCESS_WITH_WARNINGS).ok
    for status in (
        ConversionStatus.SKIPPED_EXISTS,
        ConversionStatus.UNSUPPORTED,
        ConversionStatus.BACKEND_UNAVAILABLE,
        ConversionStatus.INVALID_INPUT,
        ConversionStatus.FAILED,
        ConversionStatus.CANCELLED,
    ):
        assert not build_result(status).ok, status


def test_summary_contains_status_label():
    result = build_result(ConversionStatus.FAILED, error="缺少依赖")
    text = result.summary()
    assert "失败" in text
    assert "缺少依赖" in text


def test_summary_mentions_output_name():
    result = build_result(ConversionStatus.SUCCESS, outputs=[Path("a/b/out.pdf")], backend="pandoc")
    assert "out.pdf" in result.summary()
    assert "pandoc" in result.summary()


def test_batch_summary_serialization():
    summary = BatchSummary(total=3, succeeded=2, failed=1, duration_ms=1500)
    payload = summary.as_dict()
    assert payload["total"] == 3
    assert payload["duration_s"] == 1.5


def test_conflict_policy_values():
    assert {item.value for item in ConflictPolicy} == {"rename", "overwrite", "skip"}
