"""能力检测。"""

from __future__ import annotations

from docmorph.capability import Capability, CapabilityReport, detect


def test_detect_reports_expected_keys():
    report = detect(force=True)
    for key in ("pymupdf", "pandoc", "word", "excel", "wps", "libreoffice", "webview2", "win32com"):
        assert key in report.capabilities, key


def test_detect_is_cached():
    first = detect()
    second = detect()
    assert first is second
    assert detect(force=True) is not first


def test_missing_capability_has_hint():
    report = detect()
    for capability in report.capabilities.values():
        if not capability.available and capability.kind != "external-app":
            assert capability.hint or capability.detail


def test_report_payload_shape():
    payload = CapabilityReport().as_dict()
    assert payload == {"capabilities": [], "available": [], "missing": []}


def test_unknown_capability_is_unavailable():
    report = CapabilityReport()
    assert report.available("nope") is False
    assert report.get("nope").available is False
    report.add(Capability("ok", "OK", "python-package", True, "1.0"))
    assert report.available("ok")
    assert "✔ OK" in "\n".join(report.summary_lines())
    report.add(Capability("bad", "BAD", "external-app", False, "未安装", "请安装"))
    assert "✘ BAD" in "\n".join(report.summary_lines())
