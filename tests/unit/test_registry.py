"""路由注册表与方案选择。"""

from __future__ import annotations

from docmorph.capability import Capability, CapabilityReport
from docmorph.formats import Format
from docmorph.registry import (
    declared_targets,
    plan_backends,
    plans,
    routes_snapshot,
    select_plan,
)


class FakeBackend:
    def __init__(self, backend_id: str, available: bool) -> None:
        self.id = backend_id
        self.label = backend_id
        self.available = lambda report: available


def report_with(*available: str) -> CapabilityReport:
    report = CapabilityReport()
    for backend_id in ("word", "excel", "wps", "libreoffice", "pandoc", "python", "weasyprint"):
        report.add(
            Capability(backend_id, backend_id, "external-app", backend_id in available, "", "")
        )
    return report


def backends(word=True, pandoc=True, python=True, weasyprint=False) -> dict:
    return {
        "word": FakeBackend("word", word),
        "excel": FakeBackend("excel", True),
        "wps": FakeBackend("wps", False),
        "libreoffice": FakeBackend("libreoffice", False),
        "pandoc": FakeBackend("pandoc", pandoc),
        "python": FakeBackend("python", python),
        "weasyprint": FakeBackend("weasyprint", weasyprint),
    }


def test_every_declared_route_has_at_least_one_plan():
    for row in routes_snapshot():
        source, target = Format(str(row["source"])), Format(str(row["target"]))
        assert plans(source, target), f"{source}->{target} 缺少方案"


def test_declared_targets_matches_routes():
    targets = {item.value for item in declared_targets(Format.DOCX)}
    assert targets == {"pdf", "md", "html", "txt"}


def test_unknown_combination_returns_reason():
    plan, reason = select_plan(Format.PPTX, Format.PDF, backends(), report_with())
    assert plan is None
    assert "不在支持范围内" in reason


def test_select_plan_skips_unavailable_backends():
    plan, reason = select_plan(
        Format.DOCX, Format.PDF, backends(word=False), report_with("word")
    )
    assert plan is None
    assert "Microsoft" in reason or "word" in reason


def test_select_plan_uses_chain_for_markdown_to_pdf():
    plan, _ = select_plan(Format.MD, Format.PDF, backends(), report_with("word", "pandoc"))
    assert plan is not None
    assert plan_backends(plan) == ("pandoc", "word")
    assert plan[-1][1] is Format.PDF


def test_pdf_preference_reorders_candidates():
    fake = backends()
    fake["libreoffice"] = FakeBackend("libreoffice", True)
    report = report_with("word", "pandoc", "libreoffice")
    default_plan, _ = select_plan(Format.DOCX, Format.PDF, fake, report, "auto")
    assert plan_backends(default_plan) == ("word",)
    preferred, _ = select_plan(Format.DOCX, Format.PDF, fake, report, "libreoffice")
    assert plan_backends(preferred)[-1] == "libreoffice"


def test_html_to_pdf_prefers_word_over_weasyprint():
    fake = backends(weasyprint=True)
    plan, _ = select_plan(Format.HTML, Format.PDF, fake, report_with("word", "weasyprint"))
    assert plan_backends(plan) == ("word",)
