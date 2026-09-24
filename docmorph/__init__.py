"""DocMorph —— Windows 优先的本地文档格式转换工具（GUI + CLI）。

公共入口：

* :class:`~docmorph.services.ApplicationService`：GUI 与 CLI 共用的编排层；
* :class:`~docmorph.engine.ConversionEngine`：转换引擎（路由与执行）；
* :class:`~docmorph.formats.Format`、:class:`~docmorph.results.ConversionStatus` 等数据模型。

安装与使用说明见 README.md。
"""

from docmorph.engine import ConversionEngine, make_request
from docmorph.formats import Format
from docmorph.results import (
    BatchSummary,
    ConflictPolicy,
    ConversionRequest,
    ConversionResult,
    ConversionStatus,
)
from docmorph.services import ApplicationService
from docmorph.settings import ConfigManager, Settings

__version__ = "0.3.1"

__all__ = [
    "ApplicationService",
    "BatchSummary",
    "ConfigManager",
    "ConflictPolicy",
    "ConversionEngine",
    "ConversionRequest",
    "ConversionResult",
    "ConversionStatus",
    "Format",
    "Settings",
    "__version__",
    "make_request",
]
