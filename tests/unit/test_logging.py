"""日志系统：不重复挂载、非阻塞入队、退出刷盘、环形缓冲。"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from docmorph.logging_setup import LOGGER_NAME, get_logger, setup_logging


def test_setup_does_not_stack_handlers(tmp_path):
    first = setup_logging(tmp_path / "logs", console=False)
    second = setup_logging(tmp_path / "logs", console=False)
    try:
        logger = logging.getLogger(LOGGER_NAME)
        # 只保留当前会话的 QueueHandler（异步落盘）+ RingBufferHandler（内存缓冲）；
        # 不再出现旧实现"每 new 一次就多挂一个文件 handler"的问题
        assert len(logger.handlers) == 2
    finally:
        first.shutdown()
        second.shutdown()


def test_writes_reach_file_after_flush(tmp_path):
    session = setup_logging(tmp_path / "logs", console=False)
    try:
        logger = get_logger("test")
        logger.info("hello 中文")
        session.drain()
    finally:
        session.shutdown()
    assert session.log_file is not None
    content = session.log_file.read_text(encoding="utf-8")
    assert "hello 中文" in content


def test_ring_buffer_exposes_recent_entries(tmp_path):
    session = setup_logging(tmp_path / "logs", console=False, ring_capacity=5)
    try:
        logger = get_logger("ring")
        for index in range(8):
            logger.info("line %d", index)
        session.drain()
        entries = session.entries()
        assert len(entries) == 5
        assert "line 7" in entries[-1].message
        # 只保留最近 5 条：line 3 ~ line 7
        assert "line 2" not in session.text()
        lines = session.text().splitlines()
        assert "line 3" in lines[0]
    finally:
        session.shutdown()


def test_concurrent_writes_do_not_deadlock(tmp_path):
    session = setup_logging(tmp_path / "logs", console=False, ring_capacity=50)
    logger = get_logger("stress")

    def worker(seed: int) -> None:
        for index in range(40):
            logger.info("worker-%d-%d", seed, index)

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(worker, seed) for seed in range(6)]
            for future in futures:
                future.result(timeout=20)
        session.drain()
    finally:
        session.shutdown()
    # 进程仍存活即说明没有死锁；文件也已正常写入
    assert session.log_file is not None
    assert "worker-5-39" in session.log_file.read_text(encoding="utf-8")


def test_shutdown_is_idempotent(tmp_path):
    session = setup_logging(tmp_path / "logs", console=False)
    get_logger().warning("bye")
    session.shutdown()
    session.shutdown()
    assert threading.active_count() >= 1
