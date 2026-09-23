"""日志系统：非阻塞队列 + 文件/控制台/内存环形缓冲。

取代旧实现的问题（每次实例化都往全局 logger 追加 handler 且从不移除）：

* 业务线程只做 ``QueueHandler`` 入队，**绝不因磁盘 IO 阻塞转换线程**；
* ``QueueListener`` 独占一个后台线程负责格式化与落盘；
* 每次会话只挂一次 handler，重复调用会先清理自身旧 handler；
* 内存环形缓冲供 GUI 日志面板实时拉取；
* 关闭时 ``listener.stop()`` 并 flush，保证退出不丢日志。
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import os
import queue
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "docmorph"
LOG_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


@dataclass(frozen=True)
class LogEntry:
    """一条日志（供 UI 直接消费）。"""

    time: str
    level: str
    logger: str
    message: str

    def format(self) -> str:
        return f"[{self.time}] {self.level:<7} {self.message}"


class RingBufferHandler(logging.Handler):
    """把最近 N 条日志保存在内存中，供 UI 拉取。"""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._entries: deque[LogEntry] = deque(maxlen=max(1, capacity))
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogEntry(
            time=datetime.fromtimestamp(record.created).strftime(DATE_FORMAT),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
        )
        with self._lock:
            self._entries.append(entry)

    def entries(self, limit: int | None = None) -> list[LogEntry]:
        with self._lock:
            items = list(self._entries)
        return items[-limit:] if limit else items

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class LoggingSession:
    """一次运行期间的日志会话句柄。"""

    def __init__(
        self,
        logger: logging.Logger,
        listener: logging.handlers.QueueListener | None,
        handlers: Sequence[logging.Handler],
        ring: RingBufferHandler,
        log_file: Path | None,
    ) -> None:
        self.logger = logger
        self._listener = listener
        self._handlers = list(handlers)
        self._ring = ring
        self.log_file = log_file
        self._closed = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 读取
    def entries(self, limit: int | None = None) -> list[LogEntry]:
        return self._ring.entries(limit)

    def text(self, limit: int = 300) -> str:
        return "\n".join(entry.format() for entry in self.entries(limit))

    # ------------------------------------------------------------------ 关闭
    def flush(self) -> None:
        for handler in self._handlers:
            with contextlib.suppress(OSError, ValueError):
                handler.flush()

    def drain(self) -> None:
        """等待后台线程处理完队列（``stop`` 会排入哨兵，保证先前记录已落盘）。"""
        if self._listener is None:
            return
        self._listener.stop()
        self._listener.start()

    def shutdown(self) -> None:
        """停止监听线程并刷盘；可重复调用。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self._listener is not None:
            self._listener.stop()
        for handler in self._handlers:
            with contextlib.suppress(Exception):
                handler.close()
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)

    def __enter__(self) -> LoggingSession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()


def _session_log_path(log_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(log_dir) / f"docmorph_{stamp}.log"


def setup_logging(
    log_dir: os.PathLike | str,
    level: str = "INFO",
    console: bool = True,
    to_file: bool = True,
    ring_capacity: int = 500,
) -> LoggingSession:
    """装配日志系统并返回会话句柄。

    :param console: 是否同时输出到控制台（打包后的 GUI 通常关掉）
    :param to_file: 是否写日志文件
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(LEVELS.get(level.upper(), logging.INFO))
    logger.propagate = False

    # 清理上一次会话遗留的 handler，避免重复写入（旧实现的核心缺陷）
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        if isinstance(handler, logging.handlers.QueueHandler):
            continue
        with contextlib.suppress(Exception):
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    downstream: list[logging.Handler] = []

    log_file: Path | None = None
    if to_file:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        log_file = _session_log_path(directory)
        file_handler = logging.FileHandler(log_file, encoding="utf-8", delay=True)
        file_handler.setFormatter(formatter)
        downstream.append(file_handler)
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        downstream.append(stream)

    log_queue: queue.Queue[logging.LogRecord | None] = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # 环形缓冲直接挂在 logger 上（纯内存写入，几乎零成本），界面轮询日志时
    # 能立即看到最新记录，无需等待后台线程处理队列。
    ring = RingBufferHandler(capacity=ring_capacity)
    ring.setFormatter(formatter)
    logger.addHandler(ring)

    listener = logging.handlers.QueueListener(log_queue, *downstream, respect_handler_level=True)
    listener.start()

    return LoggingSession(logger, listener, downstream, ring, log_file)


def setup_null_logging(level: str = "CRITICAL") -> LoggingSession:
    """测试用：不写文件、不输出控制台。"""
    return setup_logging(log_dir=Path(os.devnull).parent, level=level, console=False, to_file=False)


def get_logger(name: str = "") -> logging.Logger:
    """获取 ``docmorph`` 命名空间下的子 logger。"""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def status_log(logger: logging.Logger, status: str, entity: str, message: str = "") -> None:
    """按业务状态写一条结构化日志（兼容旧的 status 语义）。"""
    level = {
        "SUCCESS": logging.INFO,
        "INFO": logging.INFO,
        "SKIPPED": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "FAILED": logging.ERROR,
    }.get(status.upper(), logging.INFO)
    label = os.path.basename(entity) if entity else "-"
    logger.log(level, "%s | %s | %s", status.upper(), label, message)


def describe_handlers() -> dict[str, int]:
    """返回当前已挂载的 handler 数量（供测试断言"不重复挂载"）。"""
    logger = logging.getLogger(LOGGER_NAME)
    return {"handlers": len(logger.handlers)}
