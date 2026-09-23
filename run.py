"""DocMorph 总启动入口。

用法（项目根目录）::

    python run.py                 # 启动桌面界面
    python run.py doctor          # 等价于 docmorph doctor（其余 CLI 子命令同理）
    python run.py --gui           # 强制启动桌面界面
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in {"--gui", "-g"}:
        from docmorph.ui import main as gui_main

        gui_main()
        return 0

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
