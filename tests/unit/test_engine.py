"""引擎：状态映射、冲突策略、链式方案、取消与输入校验（假后端，不依赖外部软件）。"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from docmorph.backends.base import BackendOutcome, ConversionBackend
from docmorph.engine import make_request, unique_path
from docmorph.errors import ConversionFailedError, InvalidInputError
from docmorph.formats import Format
from docmorph.results import ConflictPolicy, ConversionRequest, ConversionStatus


class FakeBackend(ConversionBackend):
    id = "fake"
    label = "假后端"
    capability_id = ""

    def __init__(self, fail: bool = False, warnings=None) -> None:
        self.calls: list[tuple[Format, Format]] = []
        self.fail = fail
        self.warnings = warnings or []

    def available(self, report) -> bool:
        return True

    def handles(self, source: Format, target: Format) -> bool:
        return source is not target

    def convert(self, source, target, source_format, target_format, options, workspace):
        self.calls.append((source_format, target_format))
        if self.fail:
            raise ConversionFailedError("故意失败", self.label)
        target.write_bytes(b"ok")
        return BackendOutcome(outputs=[target], warnings=self.warnings)


@pytest.fixture
def fake_engine(engine, monkeypatch):
    backend = FakeBackend()
    engine.backends = {"fake": backend}

    def fake_select(source, target, backends, report, preference="auto"):
        if (source, target) in {(Format.DOCX, Format.MD), (Format.PDF, Format.TXT)}:
            return (("fake", target),), ""
        return None, "不在支持范围内"

    monkeypatch.setattr("docmorph.engine.select_plan", fake_select)
    monkeypatch.setattr(
        "docmorph.engine.plans",
        lambda source, target: (("fake", target),) if source is not target else (),
    )
    engine.fake_backend = backend  # type: ignore[attr-defined]
    return engine


def make_file(tmp_path: Path, name: str, content: bytes = b"data") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def docx_request(tmp_path: Path, name: str = "b.md", **kwargs) -> ConversionRequest:
    return ConversionRequest(
        input_path=tmp_path / "a.docx",
        output_path=tmp_path / name,
        source_format=Format.DOCX,
        target_format=Format.MD,
        **kwargs,
    )


# ------------------------------------------------------------------ 输入校验
def test_missing_input_is_invalid(fake_engine, tmp_path):
    result = fake_engine.convert(docx_request(tmp_path))
    assert result.status is ConversionStatus.INVALID_INPUT
    assert "不存在" in result.error


def test_directory_input_is_invalid(fake_engine, tmp_path):
    directory = tmp_path / "a.docx"
    directory.mkdir()
    assert fake_engine.convert(docx_request(tmp_path)).status is ConversionStatus.INVALID_INPUT


def test_empty_input_is_invalid(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx", b"")
    assert fake_engine.convert(docx_request(tmp_path)).status is ConversionStatus.INVALID_INPUT


def test_same_format_is_unsupported(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx")
    request = ConversionRequest(
        input_path=tmp_path / "a.docx",
        output_path=tmp_path / "b.docx",
        source_format=Format.DOCX,
        target_format=Format.DOCX,
    )
    result = fake_engine.convert(request)
    assert result.status is ConversionStatus.UNSUPPORTED
    assert "相同" in result.error


# ------------------------------------------------------------------ 方案与状态
def test_unsupported_route_reports_unsupported(fake_engine, tmp_path, monkeypatch):
    monkeypatch.setattr("docmorph.engine.plans", lambda source, target: ())
    make_file(tmp_path, "a.docx")
    request = ConversionRequest(
        input_path=tmp_path / "a.docx",
        output_path=tmp_path / "b.xlsx",
        source_format=Format.DOCX,
        target_format=Format.XLSX,
    )
    assert fake_engine.convert(request).status is ConversionStatus.UNSUPPORTED


def test_unavailable_backend_reports_environment_problem(fake_engine, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "docmorph.engine.select_plan",
        lambda *args, **kwargs: (None, "缺少可用的转换引擎：Microsoft Word"),
    )
    make_file(tmp_path, "a.docx")
    result = fake_engine.convert(docx_request(tmp_path))
    assert result.status is ConversionStatus.BACKEND_UNAVAILABLE
    assert "缺少可用" in result.error


def test_backend_exception_becomes_failed(fake_engine, tmp_path):
    fake_engine.backends["fake"].fail = True
    make_file(tmp_path, "a.docx")
    result = fake_engine.convert(docx_request(tmp_path))
    assert result.status is ConversionStatus.FAILED
    assert "故意失败" in result.error
    assert not (tmp_path / "b.md").exists()


def test_warnings_switch_status(fake_engine, tmp_path):
    fake_engine.backends["fake"].warnings = ["注意：内容有损"]
    make_file(tmp_path, "a.docx")
    result = fake_engine.convert(docx_request(tmp_path))
    assert result.status is ConversionStatus.SUCCESS_WITH_WARNINGS
    assert result.warnings == ["注意：内容有损"]


def test_cancel_event_stops_before_conversion(fake_engine, tmp_path):
    event = threading.Event()
    event.set()
    make_file(tmp_path, "a.docx")
    request = docx_request(tmp_path, options={"cancel_event": event})
    assert fake_engine.convert(request).status is ConversionStatus.CANCELLED


# ------------------------------------------------------------------ 冲突策略
def test_skip_policy_leaves_existing_file(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx")
    target = tmp_path / "b.md"
    target.write_bytes(b"old")
    result = fake_engine.convert(docx_request(tmp_path, conflict=ConflictPolicy.SKIP))
    assert result.status is ConversionStatus.SKIPPED_EXISTS
    assert target.read_bytes() == b"old"


def test_rename_policy_creates_new_file(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx")
    target = tmp_path / "b.md"
    target.write_bytes(b"old")
    result = fake_engine.convert(docx_request(tmp_path, conflict=ConflictPolicy.RENAME))
    assert result.ok
    assert target.read_bytes() == b"old"
    assert result.primary_output is not None
    assert result.primary_output.name == "b (2).md"


def test_overwrite_policy_replaces_file(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx")
    target = tmp_path / "b.md"
    target.write_bytes(b"old")
    assert fake_engine.convert(docx_request(tmp_path, conflict=ConflictPolicy.OVERWRITE)).ok
    assert target.read_bytes() == b"ok"


def test_output_equal_to_input_is_rejected(fake_engine, tmp_path):
    make_file(tmp_path, "a.docx")
    request = ConversionRequest(
        input_path=tmp_path / "a.docx",
        output_path=tmp_path / "a.docx",
        source_format=Format.DOCX,
        target_format=Format.MD,
    )
    result = fake_engine.convert(request)
    assert not result.ok
    assert "相同" in result.error


# ------------------------------------------------------------------ 辅助函数
def test_unique_path_appends_index(tmp_path):
    existing = tmp_path / "a.pdf"
    existing.write_bytes(b"x")
    assert unique_path(existing).name == "a (2).pdf"
    (tmp_path / "a (2).pdf").write_bytes(b"x")
    assert unique_path(existing).name == "a (3).pdf"
    assert unique_path(tmp_path / "fresh.pdf").name == "fresh.pdf"


def test_make_request_infers_format_and_output(settings, tmp_path):
    source = tmp_path / "报告.docx"
    source.write_bytes(b"data")
    request = make_request(source, target_format="md", settings=settings)
    assert request.source_format is Format.DOCX
    assert request.target_format is Format.MD
    assert request.output_path.name == "报告.md"
    assert request.conflict is ConflictPolicy.RENAME


def test_make_request_treats_directory_output_as_dir(settings, tmp_path):
    source = tmp_path / "a.docx"
    source.write_bytes(b"data")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    request = make_request(source, out_dir, "html", settings=settings)
    assert request.output_path == out_dir / "a.html"


def test_make_request_unknown_input_format_raises(tmp_path):
    weird = tmp_path / "a.rar"
    weird.write_bytes(b"data")
    with pytest.raises(InvalidInputError):
        make_request(weird, target_format="pdf")


def test_merge_pdfs_combines_pages(fake_engine, tmp_path):
    from tests.fixtures.builders import make_pdf

    first = make_pdf(tmp_path / "one.pdf", "first document")
    second = make_pdf(tmp_path / "two.pdf", "second document")
    result = fake_engine.merge_pdfs([first, second], tmp_path / "merged.pdf")
    assert result.ok, result.error
    from docmorph.backends.python_backend import import_pymupdf

    with import_pymupdf().open(str(tmp_path / "merged.pdf")) as document:
        assert document.page_count == 2


def test_merge_pdfs_requires_two_files(fake_engine, tmp_path):
    single = make_file(tmp_path, "one.pdf")
    result = fake_engine.merge_pdfs([single], tmp_path / "merged.pdf")
    assert not result.ok
    assert "两个" in result.error
