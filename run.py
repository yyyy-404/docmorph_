"""DocMorph 总启动入口。

用法（项目根目录）::

    python run.py                    # 启动桌面界面
    python run.py --safe-mode        # 安全模式启动（只加载内置转换能力）
    python run.py doctor             # 等价于 docmorph doctor（其余 CLI 子命令同理）
    python run.py --gui              # 强制启动桌面界面

``--safe-mode`` 会被提前摘出并写入环境变量，因此 GUI 与 CLI 两条路径都能生效；
正常模式启动失败时，安全模式仍应能打开界面用于诊断。
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    from docmorph.startup import bootstrap, safe_mode_requested, strip_safe_mode_flags

    args = list(sys.argv[1:] if argv is None else argv)
    safe_mode = safe_mode_requested(args)
    if safe_mode:
        os.environ["DOCMORPH_SAFE_MODE"] = "1"
    args = strip_safe_mode_flags(args)

    # 启动最早阶段就装好异常钩子与诊断日志（GUI/CLI 共用）
    context = bootstrap(safe_mode=safe_mode)

    if not args or args[0] in {"--gui", "-g"}:
        from docmorph.ui.app import run as gui_run

        return gui_run(safe_mode=safe_mode, context=context)

    if args[0] in {"--help", "-h"}:
        print(__doc__.strip())
        print("\nCLI 完整用法：python run.py --cli --help\n")
        return 0

    if args[0] == "--cli":
        args = args[1:]

    from docmorph.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
