"""桌面应用外壳（pywebview + Edge WebView2）。

* 界面是本地静态页面（Vite 构建产物），**不启动任何服务器**，也不联网；
* 业务逻辑全部通过 :class:`docmorph.ui.bridge.Api` 调用服务层；
* 缺少 WebView2 运行时或前端产物时给出可执行的提示，而不是崩溃。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from docmorph import __version__
from docmorph.capability import detect
from docmorph.logging_setup import get_logger
from docmorph.services import ApplicationService
from docmorph.settings import ConfigManager
from docmorph.ui.bridge import Api

logger = get_logger("ui.app")

WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"
INDEX_FILE = WEBAPP_DIR / "index.html"
WINDOW_TITLE = "DocMorph - 文档格式转换器"


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


def build_service(config_path: str | None = None) -> ApplicationService:
    config = ConfigManager.load_or_create(config_path)
    service = ApplicationService(config=config)
    logger.info("DocMorph %s 启动 | 配置=%s | 日志=%s", __version__, config.path, service.log_file)
    return service


def _register_drop_handler(window, api: Api) -> None:
    """把 WebView2 的文件拖拽事件接到服务层。

    WebView2 出于安全考虑不向普通 HTML5 拖拽暴露真实路径，pywebview 的 DOM 事件
    接口可以拿到完整路径，因此在这里注册一次。
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
        try:
            element = window.dom.get_element("#drop-zone")
            if element is None:
                logger.warning("未找到拖拽区域元素，拖拽功能不可用")
                return
            element.on("drop", on_drop)
        except Exception:
            logger.warning("注册拖拽处理器失败，可改用「选择文件」按钮", exc_info=True)

    window.events.loaded += register


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


def run(config_path: str | None = None, debug: bool = False) -> int:
    """启动桌面窗口，返回进程退出码。"""
    from docmorph.utils import ensure_console_encoding

    ensure_console_encoding()
    capabilities = detect()
    if not capabilities.available("webview2"):
        print(
            "⚠️ 未检测到 Edge WebView2 运行时，图形界面可能无法显示。\n"
            "   可安装：https://developer.microsoft.com/microsoft-edge/webview2/\n"
            "   命令行功能仍可正常使用（docmorph doctor / docmorph convert）。"
        )
    try:
        import webview
    except ImportError:
        print("❌ 缺少 pywebview，请执行：pip install pywebview")
        return 1

    service = build_service(config_path)
    api = Api(service)

    if assets_available():
        url = INDEX_FILE.as_uri()
    else:
        print(
            "⚠️ 未找到前端构建产物（docmorph/ui/webapp/index.html）。\n"
            "   开发者可执行：cd frontend && npm install && npm run build"
        )
        url = "data:text/html;charset=utf-8," + _fallback_page(
            "界面资源尚未构建。"
        )

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

    storage = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DocMorph" / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(debug=debug, private_mode=False, storage_path=str(storage))
    finally:
        service.shutdown()
        logger.info("DocMorph 已退出")
    return 0


def main() -> None:
    """``docmorph-gui`` 入口。"""
    debug = bool(os.environ.get("DOCMORPH_DEBUG"))
    sys.exit(run(debug=debug))


if __name__ == "__main__":  # pragma: no cover
    main()
