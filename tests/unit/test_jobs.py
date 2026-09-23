"""批量执行器：并发、取消、统计、失败继续。"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from docmorph.formats import Format
from docmorph.jobs import JobRunner, summarize, tally
from docmorph.results import BatchSummary, ConversionRequest, ConversionResult, ConversionStatus
from docmorph.settings.paths import TempWorkspace


def request_for(index: int) -> ConversionRequest:
    return ConversionRequest(
        input_path=Path(f"file{index}.docx"),
        output_path=Path(f"file{index}.md"),
        source_format=Format.DOCX,
        target_format=Format.MD,
    )


class StubEngine:
    """按索引决定成功 / 失败 / 异常，并记录并发峰值。"""

    def __init__(self, failures=(), crashes=(), delay: float = 0.01) -> None:
        self.failures = set(failures)
        self.crashes = set(crashes)
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def convert(self, request: ConversionRequest) -> ConversionResult:
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        index = int(request.input_path.stem.removeprefix("file"))
        try:
            time.sleep(self.delay)
            if index in self.crashes:
                raise RuntimeError("boom")
            if index in self.failures:
                return ConversionResult(
                    request=request, status=ConversionStatus.FAILED, error="失败"
                )
            return ConversionResult(
                request=request, status=ConversionStatus.SUCCESS, outputs=[request.output_path]
            )
        finally:
            with self.lock:
                self.active -= 1


def test_runs_all_requests_and_tallies():
    runner = JobRunner(StubEngine(failures=[1]), max_workers=3)
    outcome = runner.run([request_for(i) for i in range(5)])
    assert outcome.summary.total == 5
    assert outcome.summary.succeeded == 4
    assert outcome.summary.failed == 1
    assert len(outcome.failures) == 1


def test_engine_exception_is_captured_as_failure():
    runner = JobRunner(StubEngine(crashes=[2]), max_workers=2)
    outcome = runner.run([request_for(2)])
    assert outcome.summary.failed == 1
    assert "boom" in outcome.results[0].error


def test_progress_callback_reports_monotonic_counts():
    seen: list[tuple[int, int]] = []
    runner = JobRunner(StubEngine(), max_workers=2)
    outcome = runner.run(
        [request_for(i) for i in range(4)],
        on_progress=lambda result, done, total: seen.append((done, total)),
    )
    assert len(seen) == 4
    assert [item[0] for item in seen] == [1, 2, 3, 4]
    assert all(item[1] == 4 for item in seen)
    assert outcome.summary.succeeded == 4


def test_cancel_event_skips_pending_work():
    event = threading.Event()
    event.set()
    runner = JobRunner(StubEngine(), max_workers=2)
    outcome = runner.run([request_for(i) for i in range(3)], cancel_event=event)
    assert outcome.summary.cancelled == 3
    assert outcome.summary.succeeded == 0


def test_workers_are_capped_by_request_count():
    engine = StubEngine(delay=0.05)
    runner = JobRunner(engine, max_workers=8)
    runner.run([request_for(i) for i in range(2)])
    assert engine.peak <= 2


def test_empty_input_returns_empty_outcome():
    outcome = JobRunner(StubEngine()).run([])
    assert outcome.summary.total == 0


def test_tally_and_summarize_helpers():
    results = [
        ConversionResult(request=request_for(0), status=ConversionStatus.SUCCESS),
        ConversionResult(request=request_for(1), status=ConversionStatus.SKIPPED_EXISTS),
        ConversionResult(request=request_for(2), status=ConversionStatus.FAILED),
        ConversionResult(request=request_for(3), status=ConversionStatus.CANCELLED),
    ]
    summary = summarize(results)
    assert (summary.succeeded, summary.skipped, summary.failed, summary.cancelled) == (1, 1, 1, 1)
    assert tally(BatchSummary(total=4), results).total == 4


def test_temp_workspace_is_cleaned(tmp_path):
    workspace = TempWorkspace(root=tmp_path, prefix="unit")
    target = workspace.file("x.txt")
    target.write_text("data", encoding="utf-8")
    assert target.exists()
    workspace.cleanup()
    assert not workspace.path.exists()
