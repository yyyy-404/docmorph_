"""批量任务执行器：并发、取消、进度、失败继续。

设计要点：

* 并发由线程池提供，但 **Office 后端内部自带串行闸门**，所以多文件批量不会
  同时驱动多个 Word/Excel 实例；
* 取消是"协作式"的：已开始的文件会跑完（无法安全中断 Word COM），未开始的不再启动；
* 单个文件失败不影响其它文件，最终返回完整统计。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from docmorph.engine import ConversionEngine
from docmorph.logging_setup import get_logger
from docmorph.results import BatchSummary, ConversionRequest, ConversionResult, ConversionStatus

logger = get_logger("jobs")

#: 进度回调：(本次结果, 已完成数, 总数)
ProgressCallback = Callable[[ConversionResult, int, int], None]


@dataclass
class JobOutcome:
    """一批任务的执行结果。"""

    results: list[ConversionResult] = field(default_factory=list)
    summary: BatchSummary = field(default_factory=BatchSummary)

    @property
    def failures(self) -> list[ConversionResult]:
        return [item for item in self.results if not item.ok]


class JobRunner:
    """把一串 :class:`ConversionRequest` 跑成一批结果。"""

    def __init__(self, engine: ConversionEngine, max_workers: int = 4) -> None:
        self.engine = engine
        self.max_workers = max(1, int(max_workers))

    def run(
        self,
        requests: Sequence[ConversionRequest],
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        workers: int | None = None,
    ) -> JobOutcome:
        """执行全部请求；``cancel_event`` 置位后不再启动新任务。"""
        started = time.perf_counter()
        total = len(requests)
        outcome = JobOutcome(summary=BatchSummary(total=total))
        if total == 0:
            return outcome

        worker_count = max(1, min(workers or self.max_workers, total))
        counter = {"done": 0}
        lock = threading.Lock()

        def _run_one(request: ConversionRequest) -> ConversionResult:
            if cancel_event is not None and cancel_event.is_set():
                return ConversionResult(
                    request=request, status=ConversionStatus.CANCELLED, error="任务已取消"
                )
            if cancel_event is not None:
                request.options = {**request.options, "cancel_event": cancel_event}
            return self.engine.convert(request)

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="docmorph") as pool:
            future_map = {pool.submit(_run_one, request): request for request in requests}
            for future in as_completed(future_map):
                request = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = ConversionResult(
                        request=request,
                        status=ConversionStatus.FAILED,
                        error=f"任务执行异常：{type(exc).__name__}: {exc}",
                    )
                outcome.results.append(result)
                with lock:
                    counter["done"] += 1
                    done = counter["done"]
                if on_progress is not None:
                    on_progress(result, done, total)

        outcome.summary.duration_ms = int((time.perf_counter() - started) * 1000)
        tally(outcome.summary, outcome.results)
        logger.info(
            "批量完成 | 共 %d，成功 %d，跳过 %d，失败 %d，取消 %d | %.2fs",
            outcome.summary.total,
            outcome.summary.succeeded,
            outcome.summary.skipped,
            outcome.summary.failed,
            outcome.summary.cancelled,
            outcome.summary.duration_s,
        )
        return outcome


def tally(summary: BatchSummary, results: Iterable[ConversionResult]) -> BatchSummary:
    """把结果序列累计进统计对象。"""
    for result in results:
        if result.status.is_success:
            summary.succeeded += 1
        elif result.status is ConversionStatus.SKIPPED_EXISTS:
            summary.skipped += 1
        elif result.status is ConversionStatus.CANCELLED:
            summary.cancelled += 1
        else:
            summary.failed += 1
    return summary


def summarize(results: Iterable[ConversionResult]) -> BatchSummary:
    """对任意结果序列做统计（供 UI 局部刷新使用）。"""
    items = list(results)
    summary = BatchSummary(total=len(items))
    return tally(summary, items)
