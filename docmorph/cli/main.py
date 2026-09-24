"""DocMorph 命令行界面。

子命令::

    docmorph convert <输入> [-o 输出] [--to 格式] [--overwrite|--skip|--rename]
    docmorph batch <目录> [-o 输出目录] [--to 格式] [--flat] [--workers N]
    docmorph formats [--json]         # 转换能力矩阵（含当前环境可用性）
    docmorph doctor [--json]          # 环境体检（Word/WPS/Pandoc/LibreOffice…）
    docmorph config [--init|--path|--json]
    docmorph merge-pdf 输出.pdf 输入1.pdf 输入2.pdf ...

兼容旧用法：``docmorph <输入> <输出> --from docx --to pdf [--batch]``
（未给出子命令时自动按旧语法解析）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from docmorph import __version__
from docmorph.formats import parse_format
from docmorph.results import ConflictPolicy
from docmorph.services import ApplicationService
from docmorph.settings import ConfigManager
from docmorph.startup import safe_mode_requested, strip_safe_mode_flags
from docmorph.utils import ensure_console_encoding

_PROG = "docmorph"
_SUBCOMMANDS = ("convert", "batch", "formats", "doctor", "config", "merge-pdf")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3

_CONFLICT_FLAGS: dict[str, ConflictPolicy] = {
    "overwrite": ConflictPolicy.OVERWRITE,
    "skip": ConflictPolicy.SKIP,
    "rename": ConflictPolicy.RENAME,
}


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None, help="配置文件路径（默认程序目录下的 config.ini）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于脚本消费）")
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出结果，不输出进度细节")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="DocMorph —— 本地文档格式转换工具（不上传、不联网）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  docmorph convert 报告.docx --to pdf\n"
            "  docmorph batch ./docs -o ./out --to md\n"
            "  docmorph doctor\n"
            "  docmorph formats\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"DocMorph {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # convert
    convert = subparsers.add_parser("convert", help="转换单个文件")
    convert.add_argument("input", help="输入文件")
    convert.add_argument("-o", "--output", default=None, help="输出文件或输出目录")
    convert.add_argument("--to", dest="to_format", default=None, help="目标格式")
    convert.add_argument("--from", dest="from_format", default=None, help="源格式（默认按扩展名）")
    _add_conflict(convert)
    _add_common(convert)

    # batch
    batch = subparsers.add_parser("batch", help="批量转换目录或文件")
    batch.add_argument("inputs", nargs="+", help="输入目录或文件（可多个）")
    batch.add_argument("-o", "--output", default=None, help="输出目录（默认取配置）")
    batch.add_argument("--to", dest="to_format", default=None, help="目标格式（默认按各源格式的默认值）")
    batch.add_argument("--flat", action="store_true", help="不保留目录结构（默认保留）")
    batch.add_argument("--workers", type=int, default=None, help="并发线程数（Office 转换始终串行）")
    _add_conflict(batch)
    _add_common(batch)

    # formats
    formats = subparsers.add_parser("formats", help="查看转换能力矩阵")
    _add_common(formats)

    # doctor
    doctor = subparsers.add_parser("doctor", help="检测运行环境与可用转换引擎")
    doctor.add_argument(
        "--deep",
        action="store_true",
        help="真实导入依赖做权威自检（较慢，可能触发第三方库输出）",
    )
    _add_common(doctor)

    # config
    config = subparsers.add_parser("config", help="查看或初始化配置")
    config.add_argument("--init", action="store_true", help="生成默认配置文件")
    config.add_argument("--path", action="store_true", help="只打印配置文件路径")
    _add_common(config)

    # merge-pdf
    merge = subparsers.add_parser("merge-pdf", help="合并多个 PDF")
    merge.add_argument("output", help="输出的 PDF 路径")
    merge.add_argument("inputs", nargs="+", help="待合并的 PDF 文件")
    _add_common(merge)

    # split-pdf
    split = subparsers.add_parser("split-pdf", help="按页范围拆分 PDF")
    split.add_argument("input", help="输入 PDF")
    split.add_argument("-o", "--output", default=None, help="输出目录（默认取配置的输出目录）")
    split.add_argument("--pages", default=None, help="页范围，如 1-3,5,7-9；留空表示每页一个文件")
    _add_conflict(split)
    _add_common(split)

    # 兼容旧语法：docmorph <输入> [输出] [--from X] [--to Y] [--batch]
    legacy = subparsers.add_parser("legacy", help=argparse.SUPPRESS)
    legacy.add_argument("input", nargs="?")
    legacy.add_argument("output", nargs="?")
    legacy.add_argument("--from", dest="from_format")
    legacy.add_argument("--to", dest="to_format")
    legacy.add_argument("--batch", action="store_true")
    legacy.add_argument("--keep-structure", action="store_true")
    legacy.add_argument("--workers", type=int, default=None)
    legacy.add_argument("--overwrite", action="store_true")
    _add_common(legacy)
    return parser


def _add_conflict(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--overwrite", action="store_true", help="覆盖已存在的输出文件")
    group.add_argument("--skip", action="store_true", help="已存在则跳过")
    group.add_argument("--rename", action="store_true", help="已存在则自动改名（默认）")


def _conflict_from_args(args: argparse.Namespace) -> ConflictPolicy | None:
    for flag, policy in _CONFLICT_FLAGS.items():
        if getattr(args, flag, False):
            return policy
    return None


def _service(args: argparse.Namespace, enable_file_log: bool = True) -> ApplicationService:
    config = ConfigManager.load(args.config)
    return ApplicationService(
        config=config,
        enable_file_log=enable_file_log,
        safe_mode=safe_mode_requested(),
    )


def _print(text: str = "") -> None:
    print(text, flush=True)


def _resolve_output_directory(service: ApplicationService, output: str | None, inputs: Sequence[Path]) -> Path:
    if output:
        candidate = Path(output)
        if len(inputs) == 1 and candidate.suffix and not candidate.is_dir():
            return candidate.parent
        return candidate
    return Path(service.settings.output_directory)


# ---------------------------------------------------------------------- 子命令实现
def cmd_convert(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        source = Path(args.input)
        if not source.exists():
            _print(f"❌ 输入文件不存在：{source}")
            return EXIT_USAGE
        target_format = parse_format(args.to_format) if args.to_format else None
        explicit = Path(args.output) if args.output else None
        output_dir: Path | None = None
        output_file: Path | None = None
        if explicit is not None:
            if explicit.is_dir() or not explicit.suffix:
                output_dir = explicit
            else:
                output_file = explicit
                if target_format is None:
                    target_format = parse_format(explicit.suffix)
        if output_dir is None and output_file is None:
            output_dir = Path(service.settings.output_directory)

        if output_file is not None and target_format is not None:
            from docmorph.engine import make_request

            request = make_request(
                source,
                output_file,
                target_format,
                settings=service.settings,
                conflict=_conflict_from_args(args),
            )
            result = service.engine.convert(request)
        else:
            result = service.convert_one(
                source,
                output_dir,
                target_format,
                conflict=_conflict_from_args(args),
            )
        return _report_results([result], args)
    finally:
        service.shutdown()


def cmd_batch(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        inputs, notes = service.expand_inputs([Path(item) for item in args.inputs])
        for note in notes:
            _print(f"⚠️ {note}")
        if not inputs:
            _print("❌ 没有找到可转换的文件")
            return EXIT_USAGE
        output_dir = Path(args.output) if args.output else Path(service.settings.output_directory)
        input_root = Path(args.inputs[0]) if len(args.inputs) == 1 and Path(args.inputs[0]).is_dir() else None
        target_format = parse_format(args.to_format) if args.to_format else None
        if not args.json:
            _print(f"🚀 开始批量转换 {len(inputs)} 个文件 → {output_dir}")

        def _progress(result, done, total):
            if not (args.quiet or args.json):
                _print(f"  [{done}/{total}] {result.summary()}")

        outcome = service.convert_many(
            inputs,
            output_dir,
            target_format,
            input_root=input_root,
            keep_structure=not args.flat,
            conflict=_conflict_from_args(args),
            on_progress=_progress,
            workers=args.workers,
        )
        return _report_batch(outcome, args)
    finally:
        service.shutdown()


def cmd_formats(args: argparse.Namespace) -> int:
    service = _service(args, enable_file_log=False)
    try:
        catalog = service.catalog()
        if args.json:
            _print(json.dumps({"catalog": catalog}, ensure_ascii=False, indent=2))
            return EXIT_OK
        _print("源格式 → 目标格式（✔ 当前环境可用 / ✘ 缺少引擎）")
        for entry in catalog:
            _print(f"\n{entry['source']}（默认 → {entry['default_target']}）")
            for target in entry["targets"]:
                mark = "✔" if target["available"] else "✘"
                detail = f"  [{', '.join(target['backends'])}]" if target["available"] else f"  {target['reason']}"
                _print(f"  {mark} {target['target']}{detail}")
        return EXIT_OK
    finally:
        service.shutdown()


def cmd_doctor(args: argparse.Namespace) -> int:
    service = _service(args, enable_file_log=False)
    try:
        if getattr(args, "deep", False):
            if not args.json:
                _print("🔍 正在做深度自检（会真实导入各依赖，可能需要几秒）…")
            service.deep_recheck_capabilities()
        payload = service.doctor()
        if args.json:
            _print(json.dumps(payload, ensure_ascii=False, indent=2))
            return EXIT_OK
        _print(f"DocMorph {__version__} 环境体检")
        _print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
        _print(f"配置文件: {payload['settings']['config_path']}")
        _print(f"日志文件: {payload['log_file'] or '（未启用）'}")
        _print("\n转换引擎：")
        for capability in payload["capabilities"]["capabilities"]:
            mark = "✔" if capability["available"] else "✘"
            detail = f" — {capability['detail']}" if capability["detail"] else ""
            _print(f"  {mark} {capability['label']}{detail}")
            if not capability["available"] and capability["hint"]:
                _print(f"      提示：{capability['hint']}")
        routes = payload["routes"]
        _print(f"\n转换路由：{routes['available']}/{routes['total']} 条当前可用")
        if service.config.warnings:
            _print("\n配置提示：")
            for warning in service.config.warnings:
                _print(f"  ⚠️ {warning}")
        return EXIT_OK
    finally:
        service.shutdown()


def cmd_config(args: argparse.Namespace) -> int:
    config = ConfigManager.load(args.config)
    if args.path:
        _print(str(config.path))
        return EXIT_OK
    if args.init:
        created = config.ensure_file(overwrite=False)
        if created:
            _print(f"✅ 已生成配置文件：{config.path}")
        else:
            _print(f"ℹ️ 配置文件已存在：{config.path}")
        return EXIT_OK
    payload = config.describe()
    if args.json:
        _print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    _print(f"配置文件：{payload['config_path']}（{'存在' if payload['config_exists'] else '不存在，使用默认值'}）")
    for section, values in payload["settings"].items():
        if isinstance(values, dict):
            for key, value in values.items():
                _print(f"  {section}.{key} = {value}")
        else:
            _print(f"  {section} = {values}")
    for warning in payload["warnings"]:
        _print(f"  ⚠️ {warning}")
    return EXIT_OK


def cmd_merge_pdf(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        result = service.merge_pdfs(args.inputs, args.output)
        return _report_results([result], args)
    finally:
        service.shutdown()


def cmd_split_pdf(args: argparse.Namespace) -> int:
    service = _service(args)
    try:
        source = Path(args.input)
        if not source.exists():
            _print(f"❌ 输入文件不存在：{source}")
            return EXIT_USAGE
        output_dir = Path(args.output) if args.output else Path(service.settings.output_directory)
        if not args.json:
            _print(f"✂️ 拆分 {source.name} → {output_dir}（页范围：{args.pages or '每页一个文件'}）")
        result = service.split_pdf(
            source, output_dir, ranges=args.pages, conflict=_conflict_from_args(args)
        )
        if result.ok and not args.json:
            _print(f"✅ 已生成 {len(result.outputs)} 个文件：")
            for path in result.outputs[:20]:
                _print(f"   {path.name}")
            if len(result.outputs) > 20:
                _print(f"   …另有 {len(result.outputs) - 20} 个文件")
        return _report_results([result], args)
    finally:
        service.shutdown()


def cmd_legacy(args: argparse.Namespace) -> int:
    """旧语法：input [output] [--from] [--to] [--batch]。"""
    if args.batch:
        batch_args = argparse.Namespace(
            inputs=[args.input] if args.input else [],
            output=args.output,
            to_format=args.to_format,
            flat=not args.keep_structure,
            workers=args.workers,
            overwrite=args.overwrite,
            skip=False,
            rename=False,
            config=args.config,
            json=args.json,
            quiet=args.quiet,
        )
        if not batch_args.inputs:
            _print("❌ 批量模式需要输入目录")
            return EXIT_USAGE
        return cmd_batch(batch_args)
    convert_args = argparse.Namespace(
        input=args.input,
        output=args.output,
        to_format=args.to_format,
        from_format=args.from_format,
        overwrite=args.overwrite,
        skip=False,
        rename=False,
        config=args.config,
        json=args.json,
        quiet=args.quiet,
    )
    if not convert_args.input:
        _print("❌ 缺少输入文件。使用 docmorph --help 查看用法")
        return EXIT_USAGE
    return cmd_convert(convert_args)


# ---------------------------------------------------------------------- 输出
def _report_results(results: Sequence[Any], args: argparse.Namespace) -> int:
    if args.json:
        _print(
            json.dumps(
                [
                    {
                        "input": str(item.input_path),
                        "status": item.status.value,
                        "backend": item.backend,
                        "outputs": [str(path) for path in item.outputs],
                        "warnings": item.warnings,
                        "error": item.error,
                        "duration_s": item.duration_s,
                    }
                    for item in results
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in results:
            mark = _result_mark(item.status.value)
            _print(f"{mark} {item.summary()}")
            for warning in item.warnings:
                _print(f"    提示：{warning}")
    # "已跳过（目标已存在）"不是错误，不应让脚本误判失败
    failed = [item for item in results if item.status.value in _FAILURE_STATUSES]
    if not failed:
        return EXIT_OK
    if any(item.status.value == "backend_unavailable" for item in failed):
        _print("提示：运行 `docmorph doctor` 查看缺失的转换引擎与安装建议。")
        return EXIT_ENVIRONMENT
    return EXIT_FAILED


_FAILURE_STATUSES = {"unsupported", "backend_unavailable", "invalid_input", "failed", "cancelled"}


def _result_mark(status: str) -> str:
    if status.startswith("success"):
        return "✅"
    if status == "skipped_exists":
        return "⏭"
    if status == "cancelled":
        return "⏹"
    return "❌"


def _report_batch(outcome, args: argparse.Namespace) -> int:
    summary = outcome.summary
    if args.json:
        _print(
            json.dumps(
                {
                    "summary": summary.as_dict(),
                    "results": [
                        {
                            "input": str(item.input_path),
                            "status": item.status.value,
                            "backend": item.backend,
                            "outputs": [str(path) for path in item.outputs],
                            "warnings": item.warnings,
                            "error": item.error,
                        }
                        for item in outcome.results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print(
            f"\n📊 完成：共 {summary.total} 个，成功 {summary.succeeded}，"
            f"跳过 {summary.skipped}，失败 {summary.failed}，取消 {summary.cancelled}"
            f"（{summary.duration_s}s）"
        )
        for failure in outcome.failures:
            _print(f"  ❌ {failure.input_path.name}：{failure.error or failure.status.label}")
    return EXIT_OK if summary.failed == 0 else EXIT_FAILED


# ---------------------------------------------------------------------- 入口
def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    """未给出子命令时，按旧语法解析（保持向后兼容）。"""
    items = list(sys.argv[1:] if argv is None else argv)
    known = set(_SUBCOMMANDS) | {"legacy", "split-pdf", "-h", "--help", "--version"}
    for item in items:
        if item == "--":
            break
        if item.startswith("-"):
            continue
        if item in known:
            return items
        return ["legacy", *items]
    return items


def main(argv: Sequence[str] | None = None) -> int:
    ensure_console_encoding()
    # 安全模式：在参数解析之前摘掉标记，并通过环境变量传给服务层
    raw = list(sys.argv[1:] if argv is None else argv)
    if safe_mode_requested(raw):
        os.environ["DOCMORPH_SAFE_MODE"] = "1"
    raw = strip_safe_mode_flags(raw)
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(raw))
    if args.command is None:
        parser.print_help()
        return EXIT_USAGE
    handler = {
        "convert": cmd_convert,
        "batch": cmd_batch,
        "formats": cmd_formats,
        "doctor": cmd_doctor,
        "config": cmd_config,
        "merge-pdf": cmd_merge_pdf,
        "split-pdf": cmd_split_pdf,
        "legacy": cmd_legacy,
    }.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return handler(args)
    except KeyboardInterrupt:
        _print("\n已中断")
        return EXIT_FAILED
    except Exception as exc:
        _print(f"❌ 发生错误：{type(exc).__name__}: {exc}")
        if os.environ.get("DOCMORPH_DEBUG"):
            raise
        return EXIT_FAILED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
