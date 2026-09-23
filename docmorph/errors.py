"""DocMorph 异常层次。

所有面向用户的失败都必须落到这里的某一个类型上，便于：

- UI 用统一方式把错误翻译成人话；
- CLI 用退出码区分「用法错误 / 环境缺失 / 转换失败」；
- 日志记录可分类的结构化字段。

约定：抛出的异常消息是**给用户看的中文说明**，技术细节放在 ``cause`` 与
``traceback`` 中（由引擎记录）。
"""

from __future__ import annotations


class DocMorphError(Exception):
    """DocMorph 所有业务异常的基类。"""


class ConfigurationError(DocMorphError):
    """配置文件无法解析或取值非法。"""


class UnsupportedConversionError(DocMorphError):
    """请求的 (源格式 → 目标格式) 组合不在支持范围内。"""

    def __init__(self, source: str, target: str, reason: str = "") -> None:
        self.source = source
        self.target = target
        message = f"不支持从 {source} 转换为 {target}"
        if reason:
            message += f"（{reason}）"
        super().__init__(message)


class BackendUnavailableError(DocMorphError):
    """所需转换后端在当前环境不可用（缺少软件或库）。"""

    def __init__(self, backend_id: str, reason: str, hint: str = "") -> None:
        self.backend_id = backend_id
        self.reason = reason
        self.hint = hint
        prefix = f"转换后端「{backend_id}」不可用：" if backend_id else "当前环境缺少可用的转换引擎："
        message = f"{prefix}{reason}"
        if hint:
            message += f"。{hint}"
        super().__init__(message)


class DependencyMissingError(BackendUnavailableError):
    """缺少必需的 Python 包。"""

    def __init__(self, package: str, backend_id: str = "python") -> None:
        super().__init__(
            backend_id,
            f"缺少 Python 依赖 {package}",
            f"请执行 pip install {package}",
        )
        self.package = package


class InvalidInputError(DocMorphError):
    """输入文件不存在、是目录、为空或格式无法识别。"""


class OutputError(DocMorphError):
    """输出路径不可写、无权限或与输入冲突。"""


class ConversionFailedError(DocMorphError):
    """转换过程本身失败（后端返回错误或产物缺失）。"""

    def __init__(self, message: str, backend_id: str = "") -> None:
        self.backend_id = backend_id
        super().__init__(message)


class ConversionTimeoutError(ConversionFailedError):
    """转换超时（外部软件或子进程无响应）。"""

    def __init__(self, seconds: float, backend_id: str = "") -> None:
        super().__init__(f"转换超过 {seconds:.0f} 秒未完成，已中止", backend_id)


class ConversionCancelledError(DocMorphError):
    """用户取消了任务。"""
