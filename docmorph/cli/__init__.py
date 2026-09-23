"""命令行入口（``docmorph`` / ``python -m docmorph``）。"""

from docmorph.cli.main import build_parser, main

__all__ = ["build_parser", "main"]
