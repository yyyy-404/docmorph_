"""转换路由注册表：``(源格式, 目标格式) → 有序候选方案``。

一个"方案"(Plan) 是若干"步骤"(Step) 的序列，每步 = ``(后端 id, 该步产出的格式)``。
这样"md → pdf"可以自然表达为「先 pandoc 转 docx，再 Word 导出 pdf」，
而无需在引擎里写死链式逻辑。

**新增一种转换能力 = 在这里加一行**（并确保对应后端实现了该步骤）。
"""

from __future__ import annotations

from collections.abc import Sequence

from docmorph.capability import CapabilityReport
from docmorph.formats import Format

Step = tuple[str, Format]
Plan = tuple[Step, ...]

_W = Format.PDF

ROUTES: dict[tuple[Format, Format], tuple[Plan, ...]] = {
    # ---------------------------------------------------------------- PDF 输入
    (Format.PDF, Format.TXT): ((("python", Format.TXT),),),
    (Format.PDF, Format.DOCX): ((("python", Format.DOCX),),),
    (Format.PDF, Format.PPTX): ((("python", Format.PPTX),),),
    # ---------------------------------------------------------------- DOCX 输入
    (Format.DOCX, Format.PDF): (
        (("word", _W),),
        (("wps", _W),),
        (("libreoffice", _W),),
    ),
    (Format.DOCX, Format.MD): ((("pandoc", Format.MD),),),
    (Format.DOCX, Format.HTML): ((("pandoc", Format.HTML),),),
    (Format.DOCX, Format.TXT): (
        (("pandoc", Format.TXT),),
        (("python", Format.TXT),),
    ),
    # ---------------------------------------------------------------- XLSX 输入
    (Format.XLSX, Format.CSV): ((("python", Format.CSV),),),
    (Format.XLSX, Format.MD): ((("python", Format.MD),),),
    (Format.XLSX, Format.HTML): ((("python", Format.HTML),),),
    (Format.XLSX, Format.TXT): ((("python", Format.TXT),),),
    (Format.XLSX, Format.DOCX): (
        (("python", Format.MD), ("pandoc", Format.DOCX)),
        (("libreoffice", Format.DOCX),),
    ),
    (Format.XLSX, Format.PDF): (
        (("excel", _W),),
        (("wps", _W),),
        (("libreoffice", _W),),
    ),
    # ---------------------------------------------------------------- MD 输入
    (Format.MD, Format.DOCX): ((("pandoc", Format.DOCX),),),
    (Format.MD, Format.HTML): ((("pandoc", Format.HTML),),),
    (Format.MD, Format.TXT): ((("pandoc", Format.TXT),),),
    (Format.MD, Format.PDF): (
        (("pandoc", Format.DOCX), ("word", _W)),
        (("pandoc", Format.DOCX), ("wps", _W)),
        (("pandoc", Format.HTML), ("weasyprint", _W)),
        (("pandoc", Format.DOCX), ("libreoffice", _W)),
    ),
    # ---------------------------------------------------------------- HTML 输入
    (Format.HTML, Format.DOCX): ((("pandoc", Format.DOCX),),),
    (Format.HTML, Format.MD): ((("pandoc", Format.MD),),),
    (Format.HTML, Format.TXT): ((("pandoc", Format.TXT),),),
    (Format.HTML, Format.PDF): (
        (("word", _W),),
        (("wps", _W),),
        (("pandoc", Format.DOCX), ("word", _W)),
        (("weasyprint", _W),),
        (("libreoffice", _W),),
    ),
    # ---------------------------------------------------------------- TXT 输入
    (Format.TXT, Format.DOCX): ((("pandoc", Format.DOCX),),),
    (Format.TXT, Format.HTML): ((("pandoc", Format.HTML),),),
    (Format.TXT, Format.MD): ((("pandoc", Format.MD),),),
    (Format.TXT, Format.PDF): (
        (("pandoc", Format.DOCX), ("word", _W)),
        (("pandoc", Format.DOCX), ("wps", _W)),
        (("word", _W),),
        (("pandoc", Format.DOCX), ("libreoffice", _W)),
    ),
    # ---------------------------------------------------------------- CSV 输入
    (Format.CSV, Format.XLSX): ((("python", Format.XLSX),),),
    (Format.CSV, Format.DOCX): ((("pandoc", Format.DOCX),),),
    (Format.CSV, Format.MD): ((("pandoc", Format.MD),),),
    (Format.CSV, Format.HTML): ((("pandoc", Format.HTML),),),
    (Format.CSV, Format.TXT): ((("pandoc", Format.TXT),),),
    (Format.CSV, Format.PDF): (
        (("pandoc", Format.DOCX), ("word", _W)),
        (("pandoc", Format.DOCX), ("wps", _W)),
        (("pandoc", Format.DOCX), ("libreoffice", _W)),
    ),
}

#: 可作为输入格式的集合（UI 下拉框与 CLI 校验共用）
SOURCE_FORMATS: tuple[Format, ...] = (
    Format.PDF,
    Format.DOCX,
    Format.XLSX,
    Format.MD,
    Format.HTML,
    Format.TXT,
    Format.CSV,
)


def plans(source: Format, target: Format) -> tuple[Plan, ...]:
    """返回该组合的所有候选方案（可能为空 = 不支持）。"""
    return ROUTES.get((source, target), ())


def declared_targets(source: Format) -> list[Format]:
    """该源格式"声明支持"的目标格式（不判断后端是否可用）。"""
    return [target for (src, target) in ROUTES if src is source]


def plan_backends(plan: Plan) -> tuple[str, ...]:
    return tuple(backend_id for backend_id, _ in plan)


def plan_available(plan: Plan, backends: dict[str, object], report: CapabilityReport) -> bool:
    for backend_id in plan_backends(plan):
        backend = backends.get(backend_id)
        if backend is None or not backend.available(report):  # type: ignore[attr-defined]
            return False
    return True


def select_plan(
    source: Format,
    target: Format,
    backends: dict[str, object],
    report: CapabilityReport,
    pdf_preference: str = "auto",
) -> tuple[Plan | None, str]:
    """挑选第一个"所有步骤都可用"的方案。

    :return: ``(方案 或 None, 不可用原因)``
    """
    candidates = list(plans(source, target))
    if not candidates:
        return None, f"{source} → {target} 不在支持范围内"

    if pdf_preference and pdf_preference != "auto" and target is Format.PDF:
        preferred = [plan for plan in candidates if pdf_preference in plan_backends(plan)]
        others = [plan for plan in candidates if pdf_preference not in plan_backends(plan)]
        candidates = preferred + others

    reasons: list[str] = []
    for plan in candidates:
        missing = [
            backend_id
            for backend_id in plan_backends(plan)
            if backend_id not in backends or not backends[backend_id].available(report)  # type: ignore[attr-defined]
        ]
        if not missing:
            return plan, ""
        labels = "、".join(backends[b].label if b in backends else b for b in missing)  # type: ignore[attr-defined]
        reasons.append(labels)
    unique = list(dict.fromkeys(reasons))
    return None, "缺少可用的转换引擎：" + "；或 ".join(unique)


def routes_snapshot() -> list[dict[str, object]]:
    """给 ``docmorph formats`` 命令用的路由快照。"""
    rows: list[dict[str, object]] = []
    for (source, target), plan_list in ROUTES.items():
        rows.append(
            {
                "source": source.value,
                "target": target.value,
                "plans": [" → ".join(f"{backend}:{fmt.value}" for backend, fmt in plan) for plan in plan_list],
            }
        )
    return sorted(rows, key=lambda row: (str(row["source"]), str(row["target"])))


def sources() -> Sequence[Format]:
    return SOURCE_FORMATS


#: 能产出 PDF 的后端 → 对应的能力项（用于缺引擎时的说明）
PDF_BACKEND_CAPABILITIES: dict[str, str] = {
    "word": "word",
    "excel": "excel",
    "wps": "wps",
    "libreoffice": "libreoffice",
    "weasyprint": "weasyprint",
}

PDF_BACKEND_LABELS: dict[str, str] = {
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "wps": "WPS Office",
    "libreoffice": "LibreOffice",
    "weasyprint": "WeasyPrint（需 GTK）",
}


def pdf_output_advice(report, reason: str = "", disabled: Sequence[str] = ()) -> str:
    """生成"为什么不能输出 PDF + 怎么办"的说明（不改变任何路由行为）。"""
    available: list[str] = []
    missing: list[str] = []
    for backend_id, label in PDF_BACKEND_LABELS.items():
        capability = report.get(PDF_BACKEND_CAPABILITIES[backend_id])
        if backend_id in disabled:
            continue
        (available if capability.available else missing).append(label)

    parts = ["当前环境没有可用的 PDF 输出引擎。"]
    parts.append("已检测到：" + ("、".join(available) if available else "无"))
    if missing:
        parts.append("未检测到：" + "、".join(missing))
    if disabled:
        parts.append("安全模式下已禁用：" + "、".join(disabled))
    parts.append(
        "可选做法：① 安装 Microsoft Office 或 WPS Office 之一；"
        "② 安装免费的 LibreOffice（https://www.libreoffice.org/）后重试；"
        "③ 或先转换为 md / html / docx / txt 等无需 Office 的格式。"
    )
    if available:
        parts.append(f"（当前可用引擎：{ '、'.join(available) }，可能不支持该源格式）")
    if reason:
        parts.append(f"路由信息：{reason}")
    return " ".join(parts)
