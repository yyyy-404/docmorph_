"""CLI 端到端：命令、退出码、JSON 输出、批量与目录结构。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docmorph.cli.main import main
from docmorph.settings import ConfigManager
from docmorph.settings.schema import build_settings, render_settings_ini


@pytest.fixture
def config_file(tmp_path, raw_settings) -> Path:
    path = tmp_path / "config.ini"
    path.write_text(render_settings_ini(build_settings(raw_settings, [])), encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path, config_file, raw_settings) -> Path:
    """带配置的临时工作目录。"""
    for key in ("input_directory", "output_directory", "temp_directory"):
        Path(raw_settings["paths"][key]).mkdir(parents=True, exist_ok=True)
    return tmp_path


def run(argv, capsys):
    code = main(argv)
    return code, capsys.readouterr().out


# ------------------------------------------------------------------ 信息类命令
def test_formats_json_lists_every_source(config_file, capsys):
    code, out = run(["formats", "--json", "--config", str(config_file)], capsys)
    assert code == 0
    payload = json.loads(out)
    sources = [entry["source"] for entry in payload["catalog"]]
    assert sources == ["pdf", "docx", "xlsx", "md", "html", "txt", "csv"]
    docx_entry = next(item for item in payload["catalog"] if item["source"] == "docx")
    assert {item["target"] for item in docx_entry["targets"]} == {"pdf", "md", "html", "txt"}


def test_formats_human_output_marks_availability(config_file, capsys):
    code, out = run(["formats", "--config", str(config_file)], capsys)
    assert code == 0
    assert "✔" in out


def test_doctor_json_reports_capabilities(config_file, capsys):
    code, out = run(["doctor", "--json", "--config", str(config_file)], capsys)
    assert code == 0
    payload = json.loads(out)
    ids = {item["id"] for item in payload["capabilities"]["capabilities"]}
    assert {"word", "pandoc", "libreoffice", "webview2"} <= ids
    assert payload["routes"]["total"] > 0


def test_config_path_and_json(config_file, capsys):
    code, out = run(["config", "--path", "--config", str(config_file)], capsys)
    assert code == 0
    assert out.strip() == str(config_file)

    code, out = run(["config", "--json", "--config", str(config_file)], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["config_path"] == str(config_file)


def test_config_init_creates_file(tmp_path, capsys):
    target = tmp_path / "fresh.ini"
    code, _ = run(["config", "--init", "--config", str(target)], capsys)
    assert code == 0
    assert target.exists()
    assert ConfigManager(str(target)).settings().max_workers == 4


def test_version_flag_exits(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "DocMorph" in capsys.readouterr().out


# ------------------------------------------------------------------ 单文件转换
def test_convert_markdown_to_docx(workspace, config_file, samples, capsys):
    output = workspace / "single"
    code, out = run(
        ["convert", str(samples["md"]), "-o", str(output), "--to", "docx", "--config", str(config_file)],
        capsys,
    )
    assert code == 0, out
    assert (output / "sample.docx").exists()


def test_convert_json_output_shape(workspace, config_file, samples, capsys):
    output = workspace / "single_json"
    code, out = run(
        [
            "convert",
            str(samples["md"]),
            "-o",
            str(output),
            "--to",
            "html",
            "--json",
            "--config",
            str(config_file),
        ],
        capsys,
    )
    assert code == 0, out
    payload = json.loads(out)
    assert payload[0]["status"] == "success"
    assert payload[0]["backend"] == "pandoc"
    assert payload[0]["outputs"]


def test_convert_missing_input_is_usage_error(workspace, config_file, capsys):
    code, out = run(["convert", str(workspace / "nope.docx"), "--config", str(config_file)], capsys)
    assert code == 2
    assert "不存在" in out


def test_convert_unsupported_combination(workspace, config_file, samples, capsys):
    code, out = run(
        ["convert", str(samples["md"]), "--to", "xlsx", "--config", str(config_file)], capsys
    )
    assert code == 1
    assert "不支持" in out


def test_legacy_syntax_still_works(workspace, config_file, samples, capsys):
    """旧用法 docmorph <输入> --to <格式> 必须继续可用。"""
    code, out = run([str(samples["md"]), "--to", "docx", "--config", str(config_file)], capsys)
    assert code == 0, out


def test_conflict_flags(workspace, config_file, samples, capsys):
    output = workspace / "conflict"
    args = ["convert", str(samples["md"]), "-o", str(output), "--to", "html", "--config", str(config_file)]
    assert run(args, capsys)[0] == 0
    first = sorted(path.name for path in output.iterdir())
    # 默认 rename：不覆盖，生成 "sample (2).html"
    assert run(args, capsys)[0] == 0
    assert sorted(path.name for path in output.iterdir()) != first

    skip_args = [*args, "--skip"]
    code, _ = run(skip_args, capsys)
    assert code == 0


# ------------------------------------------------------------------ 批量
def test_batch_keeps_directory_structure(workspace, config_file, samples, capsys):
    source_root = workspace / "tree"
    (source_root / "sub").mkdir(parents=True)
    (source_root / "a.md").write_text("# a", encoding="utf-8")
    (source_root / "sub" / "b.md").write_text("# b", encoding="utf-8")
    output = workspace / "batch_out"
    code, out = run(
        ["batch", str(source_root), "-o", str(output), "--to", "docx", "--config", str(config_file)],
        capsys,
    )
    assert code == 0, out
    assert (output / "a.docx").exists()
    assert (output / "sub" / "b.docx").exists()


def test_batch_flat_mode_collapses_structure(workspace, config_file, capsys):
    source_root = workspace / "tree2"
    (source_root / "sub").mkdir(parents=True)
    (source_root / "a.md").write_text("# a", encoding="utf-8")
    (source_root / "sub" / "b.md").write_text("# b", encoding="utf-8")
    output = workspace / "batch_flat"
    code, out = run(
        [
            "batch",
            str(source_root),
            "-o",
            str(output),
            "--to",
            "docx",
            "--flat",
            "--config",
            str(config_file),
        ],
        capsys,
    )
    assert code == 0, out
    assert (output / "a.docx").exists()
    assert (output / "b.docx").exists()


def test_batch_json_reports_summary(workspace, config_file, samples, capsys):
    source_root = workspace / "tree3"
    source_root.mkdir()
    (source_root / "a.md").write_text("# a", encoding="utf-8")
    code, out = run(
        [
            "batch",
            str(source_root),
            "-o",
            str(workspace / "batch_json"),
            "--to",
            "html",
            "--json",
            "--config",
            str(config_file),
        ],
        capsys,
    )
    assert code == 0, out
    payload = json.loads(out)
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["succeeded"] == 1


def test_batch_empty_directory_is_usage_error(workspace, config_file, capsys):
    empty = workspace / "empty"
    empty.mkdir()
    code, out = run(["batch", str(empty), "--to", "docx", "--config", str(config_file)], capsys)
    assert code == 2
    assert "没有找到" in out


# ------------------------------------------------------------------ 其它
def test_merge_pdf_command(workspace, config_file, tmp_path, capsys):
    from tests.fixtures.builders import make_pdf

    first = make_pdf(tmp_path / "m1.pdf", "first")
    second = make_pdf(tmp_path / "m2.pdf", "second")
    target = workspace / "merged.pdf"
    code, out = run(
        ["merge-pdf", str(target), str(first), str(second), "--config", str(config_file)], capsys
    )
    assert code == 0, out
    assert target.exists()
