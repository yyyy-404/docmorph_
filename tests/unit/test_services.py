"""应用服务层：输入展开、输出路径、格式目录、诊断。"""

from __future__ import annotations

from pathlib import Path

from docmorph.formats import Format
from docmorph.results import ConflictPolicy


def test_expand_inputs_walks_directories_and_dedupes(service, tmp_path):
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.docx").write_bytes(b"x")
    (root / "sub" / "b.md").write_text("# b", encoding="utf-8")
    (root / "note.rar").write_bytes(b"x")
    files, notes = service.expand_inputs([root, root / "a.docx"])
    names = sorted(item.name for item in files)
    assert names == ["a.docx", "b.md"]
    # 目录扫描静默忽略不支持的扩展名；直接指定不支持的文件时才提示
    assert notes == []
    _, explicit_notes = service.expand_inputs([root / "note.rar"])
    assert any("不支持" in note for note in explicit_notes)


def test_expand_inputs_reports_missing_paths(service, tmp_path):
    files, notes = service.expand_inputs([tmp_path / "nope"])
    assert files == []
    assert any("不存在" in note for note in notes)


def test_build_requests_flat_and_nested(service, tmp_path):
    root = tmp_path / "in"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "a.docx").write_bytes(b"x")
    inputs = service.directory_inputs(root)

    flat = service.build_requests(inputs, tmp_path / "flat", Format.MD, keep_structure=False)
    assert flat[0].output_path == tmp_path / "flat" / "a.md"

    nested = service.build_requests(
        inputs, tmp_path / "nested", Format.MD, input_root=root, keep_structure=True
    )
    assert nested[0].output_path == tmp_path / "nested" / "sub" / "a.md"


def test_build_requests_uses_settings_conflict_policy(service, tmp_path):
    file = tmp_path / "a.docx"
    file.write_bytes(b"x")
    request = service.build_requests([file], tmp_path / "out", Format.MD)[0]
    assert request.conflict is ConflictPolicy(service.settings.conflict_policy)


def test_build_requests_uses_default_target_per_format(service, tmp_path):
    docx = tmp_path / "a.docx"
    xlsx = tmp_path / "b.xlsx"
    docx.write_bytes(b"x")
    xlsx.write_bytes(b"x")
    requests = service.build_requests([docx, xlsx], tmp_path / "out", None)
    assert requests[0].target_format is Format.PDF
    assert requests[1].target_format is Format.CSV


def test_catalog_marks_unavailable_targets_with_reason(service):
    catalog = {entry["source"]: entry for entry in service.catalog()}
    assert "pdf" in catalog and catalog["pdf"]["default_target"] == "docx"
    for entry in catalog.values():
        for target in entry["targets"]:
            if target["available"]:
                assert target["backends"]
            else:
                assert target["reason"]


def test_doctor_payload_has_routes_and_capabilities(service):
    payload = service.doctor()
    assert payload["routes"]["total"] > 0
    assert payload["routes"]["available"] <= payload["routes"]["total"]
    assert "capabilities" in payload["capabilities"]
    assert payload["settings"]["config_path"]


def test_update_settings_rebuilds_engine_and_persists(service):
    service.update_settings(conflict_policy="overwrite", max_workers=3)
    assert service.settings.conflict_policy == "overwrite"
    assert service.settings.max_workers == 3
    assert service.engine.settings.max_workers == 3
    assert "overwrite" in Path(service.config.path).read_text(encoding="utf-8")


def test_update_settings_rejects_invalid_value(service):
    import pytest

    with pytest.raises(ValueError):
        service.update_settings(conflict_policy="destroy-everything")


def test_log_text_is_available(service):
    from docmorph.logging_setup import get_logger

    get_logger("test.services").info("服务层日志测试")
    text = service.log_text(50)
    assert "服务层日志测试" in text


def test_formats_for_returns_declared_targets():
    from docmorph.services import formats_for

    targets = {item.value for item in formats_for("md")}
    assert targets == {"docx", "html", "txt", "pdf"}
