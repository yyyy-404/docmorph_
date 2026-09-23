"""配置系统：默认值、分层优先级、旧配置迁移、校验与持久化。"""

from __future__ import annotations

import pytest

from docmorph.settings import ConfigManager
from docmorph.settings.schema import (
    ConfigValueError,
    build_settings,
    coerce_changes,
    render_settings_ini,
)


def test_defaults_without_file(tmp_path):
    manager = ConfigManager(str(tmp_path / "missing.ini"))
    settings = manager.settings()
    assert settings.conflict_policy == "rename"
    assert settings.max_workers == 4
    assert settings.default_target_for("docx").value == "pdf"
    assert settings.log_directory.name == "logs"


def test_file_overrides_defaults(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        "[conversion]\nconflict_policy = skip\nmax_workers = 6\n", encoding="utf-8"
    )
    settings = ConfigManager(str(path)).settings()
    assert settings.conflict_policy == "skip"
    assert settings.max_workers == 6


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "config.ini"
    path.write_text("[conversion]\nmax_workers = 2\n", encoding="utf-8")
    monkeypatch.setenv("DOCMORPH_CONVERSION_MAX_WORKERS", "7")
    assert ConfigManager(str(path)).settings().max_workers == 7


def test_runtime_overrides_win(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.ini"))
    settings = manager.settings({"conversion.max_workers": 3})
    assert settings.max_workers == 3


def test_legacy_config_is_migrated(tmp_path):
    """旧版 [Paths]/[Defaults]/[Conversion] 结构必须可用。"""
    path = tmp_path / "legacy.ini"
    path.write_text(
        "[Paths]\n"
        "input_directory = in\n"
        "output_directory = out\n"
        "log_directory = mylogs\n"
        "\n[Defaults]\n"
        "default_docx_to_format = md\n"
        "default_general_to_format = txt\n"
        "default_pdf_engine = weasyprint\n"
        "\n[Conversion]\n"
        "overwrite = true\n"
        "pdf_chunk_size = 5\n",
        encoding="utf-8",
    )
    manager = ConfigManager(str(path))
    settings = manager.settings()
    assert settings.input_directory.name == "in"
    assert settings.log_directory.name == "mylogs"
    assert settings.default_target_for("docx").value == "md"
    assert settings.default_target == "txt"
    assert settings.conflict_policy == "overwrite"
    assert settings.pdf_backend_preference == "weasyprint"
    assert any("旧版配置" in warning for warning in manager.warnings)


def test_legacy_overwrite_false_becomes_skip(tmp_path):
    path = tmp_path / "legacy.ini"
    path.write_text("[Conversion]\noverwrite = false\n", encoding="utf-8")
    assert ConfigManager(str(path)).settings().conflict_policy == "skip"


def test_invalid_value_falls_back_with_warning(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        "[conversion]\nconflict_policy = destroy\nmax_workers = 999\n", encoding="utf-8"
    )
    manager = ConfigManager(str(path))
    settings = manager.settings()
    assert settings.conflict_policy == "rename"
    assert settings.max_workers == 4
    assert len(manager.warnings) == 2


def test_bom_and_broken_file_are_tolerated(tmp_path):
    good = tmp_path / "good.ini"
    good.write_bytes(b"\xef\xbb\xbf[conversion]\nconflict_policy = skip\n")
    assert ConfigManager(str(good)).settings().conflict_policy == "skip"

    broken = tmp_path / "broken.ini"
    broken.write_text("this is not ini\n[Broken", encoding="utf-8")
    manager = ConfigManager(str(broken))
    assert manager.settings().conflict_policy == "rename"
    assert manager.warnings


def test_coerce_changes_validates_types():
    assert coerce_changes({"max_workers": "8"})["max_workers"] == 8
    assert coerce_changes({"keep_structure": "false"})["keep_structure"] is False
    with pytest.raises(ConfigValueError):
        coerce_changes({"max_workers": "abc"})
    with pytest.raises(ConfigValueError):
        coerce_changes({"unknown_key": "1"})


def test_apply_changes_persists_and_reloads(tmp_path):
    path = tmp_path / "config.ini"
    manager = ConfigManager(str(path))
    manager.apply_changes({"conflict_policy": "overwrite", "max_workers": 6})
    assert path.exists()
    reloaded = ConfigManager(str(path)).settings()
    assert reloaded.conflict_policy == "overwrite"
    assert reloaded.max_workers == 6


def test_render_roundtrip_keeps_targets(tmp_path):
    base = build_settings(
        {
            "paths": {"temp_directory": ""},
            "defaults": {"target_docx": "md", "default_target": "html"},
        },
        [],
    )
    path = tmp_path / "config.ini"
    path.write_text(render_settings_ini(base), encoding="utf-8")
    reloaded = ConfigManager(str(path)).settings()
    assert reloaded.default_target_for("docx").value == "md"
    assert reloaded.default_target == "html"
