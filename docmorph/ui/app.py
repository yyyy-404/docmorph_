"""桌面应用外壳（pywebview + Edge WebView2）。

启动顺序按"先让窗口起来，再去做重活"设计：

1. :func:`docmorph.startup.bootstrap` 建立最小环境（编码 / 日志目录 / 异常钩子 / 诊断）；
2. 只做**零重型导入**的启动检查（前端产物是否存在、WebView2 是否可用、pywebview 能否导入）；
3. 创建窗口并显示；
4. 窗口起来之后，才在后台线程做完整能力检测（不阻塞首屏）。

任何一步失败都会写入 ``startup-crash.log``，并在无控制台环境下弹出原生对话框说明原因，
而不是静默退出。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from docmorph import __version__
from docmorph.logging_setup import get_logger
from docmorph.services import ApplicationService
from docmorph.settings import ConfigManager
from docmorph.startup import (
    StartupContext,
    bootstrap,
    log_startup_error,
    resource_dir,
    safe_mode_requested,
    show_fatal_message,
    write_startup_log,
)
from docmorph.ui.bridge import Api

logger = get_logger("ui.app")

WEBAPP_DIR = resource_dir()
INDEX_FILE = WEBAPP_DIR / "index.html"
WINDOW_TITLE = "DocMorph - 文档格式转换器"

EXIT_OK = 0
EXIT_BAD_ENVIRONMENT = 3


def assets_available() -> bool:
    return INDEX_FILE.exists()


def _fallback_page(message: str) -> str:
    """前端产物缺失时显示的说明页（同样是本地 HTML，不依赖网络）。"""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{WINDOW_TITLE}</title>
<style>
 body {{ font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif; background:#f2f3f5; color:#333;
        margin:0; height:100vh; display:flex; align-items:center; justify-content:center; }}
 .box {{ background:rgba(255,255,255,.7); border:1px solid #e3e6ea; border-radius:12px;
         padding:28px 32px; max-width:560px; box-shadow:0 2px 8px rgba(31,34,38,.08); }}
 h1 {{ font-size:18px; margin:0 0 12px; }}
 p {{ line-height:1.7; font-size:13px; margin:6px 0; }}
 code {{ background:#fff9d2; padding:2px 6px; border-radius:5px; }}
</style></head><body><div class="box">
<h1>DocMorph {__version__}</h1>
<p>{message}</p>
<p>命令行功能不受影响，例如：<code>docmorph doctor</code>、<code>docmorph convert 文件.docx --to pdf</code>。</p>
</div></body></html>"""


def build_service(
    config_path: str | None = None,
    safe_mode: bool = False,
    warmup: bool = True,
) -> ApplicationService:
    """构造服务（不触发完整能力检测；需要时后台预热）。"""
    config = ConfigManager.load_or_create(config_path)
    service = ApplicationService(config=config, safe_mode=safe_mode)
    logger.info(
        "DocMorph %s 启动 | 配置=%s | 日志=%s | 安全模式=%s",
        __version__,
        config.path,
        service.log_file,
        safe_mode,
    )
    if warmup:
        service.start_capability_warmup()
    return service


def _webview2_blocking_problem() -> str:
    """返回"必须阻止启动"的 WebView2 问题说明；没问题返回空串。"""
    from docmorph.capability import startup_report

    report = startup_report()
    if report.available("webview2"):
        return ""
    return (
        "未检测到 Microsoft Edge WebView2 运行时，桌面界面无法显示。\n\n"
        "解决办法（任选其一）：\n"
        "1. 安装 WebView2 运行时：https://developer.microsoft.com/microsoft-edge/webview2/\n"
        "2. 安装或更新 Microsoft Edge（Windows 10/11 通常已自带）\n\n"
        "命令行功能不受影响，可先用：docmorph doctor / docmorph convert 文件.docx --to pdf"
    )


def _register_drop_handler(window, api: Api) -> None:
    """把 WebView2 的文件拖拽事件接到服务层。

    WebView2 出于安全考虑不向普通 HTML5 拖拽暴露真实路径，pywebview 的 DOM 事件
    接口可以拿到完整路径，因此在这里注册。

    注册到多个元素上，使**窗口主要区域**都可以接收拖拽（不只是那块虚线区域）。
    """

    def on_drop(event) -> None:
        try:
            files = (event.get("dataTransfer") or {}).get("files") or []
            paths = [item.get("pywebviewFullPath") for item in files]
            paths = [path for path in paths if path]
            if not paths:
                return
            payload = api.set_selection({"files": paths})
            _push_selection(window, payload)
        except Exception:
            logger.exception("处理拖拽文件失败")

    def register() -> None:
        registered = 0
        for selector in ("#app", "#drop-zone", "body"):
            try:
                element = window.dom.get_element(selector)
            except Exception:
                logger.debug("拖拽注册失败：%s", selector, exc_info=True)
                continue
            if element is None:
                continue
            try:
                element.on("drop", on_drop)
                registered += 1
            except Exception:
                logger.debug("拖拽监听失败：%s", selector, exc_info=True)
        if registered:
            logger.info("已启用全窗口拖拽（注册 %d 个区域）", registered)
        else:
            logger.warning("未能注册拖拽处理器，可改用「选择文件」按钮")

    try:
        window.events.loaded += register
    except Exception:
        # 拖拽只是增强功能：注册失败不能让整个窗口启动失败
        logger.warning("注册拖拽回调失败，可改用「选择文件」按钮", exc_info=True)


def _push_selection(window, payload: dict) -> None:
    """把 Python 侧解析出的拖拽结果推给界面（界面订阅 ``window.docmorphDrop``）。"""
    try:
        import json

        data = json.dumps(payload, ensure_ascii=False)
        window.evaluate_js(
            f"window.docmorphDrop && window.docmorphDrop({data});"
        )
    except Exception:
        logger.debug("推送拖拽结果失败", exc_info=True)


def run(
    config_path: str | None = None,
    debug: bool = False,
    safe_mode: bool | None = None,
    context: StartupContext | None = None,
) -> int:
    """启动桌面窗口，返回进程退出码。**本函数不会因任何单点失败而静默退出。**"""
    if context is None:
        context = bootstrap(safe_mode=safe_mode)
    if safe_mode is None:
        safe_mode = context.safe_mode

    # ---- 启动必需检查（全部为零重型导入的检查） ----
    step = time.perf_counter()
    try:
        import webview
    except ImportError as exc:
        context.phase_failed("pywebview", time.perf_counter() - step, str(exc))
        write_startup_log(context)
        log_startup_error(exc, context, stage="import-pywebview")
        show_fatal_message(
            f"DocMorph {__version__} 无法启动",
            "缺少图形界面组件 pywebview。\n\n请在命令行执行：pip install pywebview\n\n"
            "（命令行功能不受影响：docmorph doctor）",
        )
        return EXIT_BAD_ENVIRONMENT
    context.phase_ok("pywebview", time.perf_counter() - step)

    step = time.perf_counter()
    problem = _webview2_blocking_problem()
    if problem:
        context.phase_failed("webview2", time.perf_counter() - step, "运行时缺失")
        write_startup_log(context)
        log_startup_error(RuntimeError(problem), context, stage="webview2-check")
        show_fatal_message(f"DocMorph {__version__} 无法显示界面", problem)
        return EXIT_BAD_ENVIRONMENT
    context.phase_ok("webview2", time.perf_counter() - step)

    # ---- 服务与界面 ----
    step = time.perf_counter()
    try:
        service = build_service(config_path, safe_mode=bool(safe_mode))
    except Exception as exc:
        context.phase_failed("service", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")
        write_startup_log(context)
        log_startup_error(exc, context, stage="build-service")
        show_fatal_message(
            f"DocMorph {__version__} 初始化失败",
            f"{type(exc).__name__}: {exc}\n\n"
            "可以尝试安全模式（只加载内置转换能力）：\n"
            "    python run.py --safe-mode\n\n"
            f"详细日志：{context.log_dir}",
        )
        return EXIT_BAD_ENVIRONMENT
    context.phase_ok("service", time.perf_counter() - step)

    api = Api(service)
    if assets_available():
        url = INDEX_FILE.as_uri()
    else:
        logger.warning("未找到前端构建产物：%s", INDEX_FILE)
        url = "data:text/html;charset=utf-8," + _fallback_page(
            "界面资源尚未构建（docmorph/ui/webapp/index.html 缺失）。"
        )

    step = time.perf_counter()
    try:
        window = webview.create_window(
            WINDOW_TITLE,
            url=url,
            js_api=api,
            width=1040,
            height=760,
            min_size=(780, 560),
            background_color="#F2F3F5",
        )
        api.attach(window)
        if assets_available():
            _register_drop_handler(window, api)
        context.phase_ok("window", time.perf_counter() - step)
    except Exception as exc:
        context.phase_failed("window", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")
        write_startup_log(context)
        log_startup_error(exc, context, stage="create-window")
        show_fatal_message(
            f"DocMorph {__version__} 无法创建窗口",
            f"{type(exc).__name__}: {exc}\n\n"
            "界面依赖 Microsoft Edge WebView2 运行时；若刚安装完成，请重启后再试。\n"
            f"详细日志：{context.log_dir}",
        )
        service.shutdown()
        return EXIT_BAD_ENVIRONMENT

    storage = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DocMorph" / "webview"
    try:
        storage.mkdir(parents=True, exist_ok=True)
    except OSError:
        storage = Path(context.log_dir)

    write_startup_log(context)
    step = time.perf_counter()
    try:
        webview.start(debug=debug, private_mode=False, storage_path=str(storage))
        context.phase_ok("mainloop", time.perf_counter() - step)
    except Exception as exc:
        context.phase_failed("mainloop", time.perf_counter() - step, f"{type(exc).__name__}: {exc}")
        write_startup_log(context)
        log_startup_error(exc, context, stage="webview-start")
        show_fatal_message(
            f"DocMorph {__version__} 界面启动失败",
            f"{type(exc).__name__}: {exc}\n\n"
            "常见原因：WebView2 运行时未安装/损坏、显卡驱动异常。\n"
            f"详细日志：{context.log_dir}",
        )
        return EXIT_BAD_ENVIRONMENT
    finally:
        service.shutdown()
        logger.info("DocMorph 已退出（用时 %.1fs）", context.elapsed_s)
    return EXIT_OK


def main() -> None:
    """``docmorph-gui`` / ``python run.py`` 入口。"""
    debug = bool(os.environ.get("DOCMORPH_DEBUG"))
    safe = safe_mode_requested()
    # 启动最早期就装好异常钩子：之后任何未捕获异常都会落到 startup-crash.log
    context = bootstrap(safe_mode=safe)
    try:
        code = run(debug=debug, safe_mode=safe, context=context)
    except Exception as exc:
        log_startup_error(exc, context, stage="gui-main")
        show_fatal_message(
            f"DocMorph {__version__} 发生未预期错误",
            f"{type(exc).__name__}: {exc}\n\n详细日志：{context.log_dir}",
        )
        code = 1
    sys.exit(code)


if __name__ == "__main__":  # pragma: no cover
    main()
