"""纯 Python 后端：PDF / 表格 / DOCX 的读写。

覆盖能力（全部无外部程序依赖）：

* ``pdf → txt``：PyMuPDF 逐页抽取文本（比 PyPDF2 保真更好，支持中文）；
* ``pdf → docx``：pdf2docx 保留段落与表格；
* ``pdf → pptx``：PyMuPDF 渲染每页为图片后铺满幻灯片，并把抽取到的文本写入
  **演讲者备注**（明确告知用户幻灯片是图片、不可编辑）；
* ``xlsx → csv / md / html / txt``：pandas + openpyxl；
* ``csv → xlsx``：pandas + openpyxl；
* ``docx → txt``：python-docx（pandoc 不可用时的兜底）。
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from docmorph.backends.base import BackendOutcome, ConversionBackend, ensure_parent, verify_output
from docmorph.capability import CapabilityReport
from docmorph.errors import ConversionFailedError, DependencyMissingError
from docmorph.formats import Format
from docmorph.settings.paths import TempWorkspace

RENDER_DPI = 150


def import_pymupdf():
    """导入 PyMuPDF（历史名 ``fitz``，新名 ``pymupdf``）。"""
    for module_name in ("pymupdf", "fitz"):
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    raise DependencyMissingError("PyMuPDF", "python")


def import_module_or_raise(module_name: str, package_hint: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise DependencyMissingError(package_hint, "python") from exc


class PythonBackend(ConversionBackend):
    """不依赖任何外部办公软件的本地后端。"""

    id = "python"
    label = "Python 原生引擎"
    serial = False
    capability_id = ""

    # ------------------------------------------------------------------ 能力
    def available(self, report: CapabilityReport) -> bool:
        return True  # 具体路由在 handles() 中按能力细分

    def handles(self, source: Format, target: Format) -> bool:
        pair = (source, target)
        return pair in {
            (Format.PDF, Format.TXT),
            (Format.PDF, Format.DOCX),
            (Format.PDF, Format.PPTX),
            (Format.DOCX, Format.TXT),
            (Format.XLSX, Format.CSV),
            (Format.XLSX, Format.MD),
            (Format.XLSX, Format.HTML),
            (Format.XLSX, Format.TXT),
            (Format.CSV, Format.XLSX),
        }

    # ------------------------------------------------------------------ 执行
    def convert(
        self,
        source: Path,
        target: Path,
        source_format: Format,
        target_format: Format,
        options: Mapping[str, Any],
        workspace: TempWorkspace,
    ) -> BackendOutcome:
        ensure_parent(target)
        pair = (source_format, target_format)
        if pair == (Format.PDF, Format.TXT):
            return self._pdf_to_text(source, target, options)
        if pair == (Format.PDF, Format.DOCX):
            return self._pdf_to_docx(source, target)
        if pair == (Format.PDF, Format.PPTX):
            return self._pdf_to_pptx(source, target, workspace, options)
        if pair == (Format.DOCX, Format.TXT):
            return self._docx_to_text(source, target)
        if pair == (Format.XLSX, Format.CSV):
            return self._xlsx_to_csv(source, target, options)
        if pair in {(Format.XLSX, Format.MD), (Format.XLSX, Format.HTML), (Format.XLSX, Format.TXT)}:
            return self._xlsx_to_text_like(source, target, target_format)
        if pair == (Format.CSV, Format.XLSX):
            return self._csv_to_xlsx(source, target)
        raise ConversionFailedError(f"{self.label} 不支持 {source_format} → {target_format}", self.label)

    # ------------------------------------------------------------------ PDF
    def _pdf_to_text(self, source: Path, target: Path, options: Mapping[str, Any]) -> BackendOutcome:
        pymupdf = import_pymupdf()
        pages: list[str] = []
        with pymupdf.open(str(source)) as document:
            for index, page in enumerate(document, start=1):
                text = page.get_text().strip()
                if options.get("page_markers"):
                    pages.append(f"--- 第 {index} 页 ---\n{text}")
                else:
                    pages.append(text)
        content = "\n\n".join(pages)
        if not content.strip():
            raise ConversionFailedError("PDF 中没有可提取的文本（可能是扫描件，需要 OCR）", self.label)
        target.write_text(content, encoding="utf-8")
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])

    def _pdf_to_docx(self, source: Path, target: Path) -> BackendOutcome:
        pdf2docx = import_module_or_raise("pdf2docx", "pdf2docx")
        converter = pdf2docx.Converter(str(source))
        try:
            converter.convert(str(target))
        except Exception as exc:
            raise ConversionFailedError(f"PDF→DOCX 失败：{exc}", self.label) from exc
        finally:
            converter.close()
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])

    def _pdf_to_pptx(
        self, source: Path, target: Path, workspace: TempWorkspace, options: Mapping[str, Any]
    ) -> BackendOutcome:
        pymupdf = import_pymupdf()
        pptx = import_module_or_raise("pptx", "python-pptx")
        images_dir = workspace.subdir(f"slides-{target.stem}")
        presentation = pptx.Presentation()
        blank_layout = presentation.slide_layouts[6]
        notes_available = False
        page_count = 0
        dpi = int(options.get("render_dpi", RENDER_DPI))

        with pymupdf.open(str(source)) as document:
            for index, page in enumerate(document):
                image_path = images_dir / f"page-{index + 1:04d}.png"
                page.get_pixmap(dpi=dpi).save(str(image_path))
                slide = presentation.slides.add_slide(blank_layout)
                slide.shapes.add_picture(
                    str(image_path), 0, 0,
                    width=presentation.slide_width, height=presentation.slide_height,
                )
                text = page.get_text().strip()
                if text:
                    notes_frame = slide.notes_slide.notes_text_frame
                    notes_frame.text = text
                    notes_available = True
                page_count += 1

        if page_count == 0:
            raise ConversionFailedError("PDF 没有可渲染的页面", self.label)
        presentation.save(str(target))
        verify_output(target, self.label)

        warnings = [f"已生成 {page_count} 张幻灯片，每页为图片（不含可编辑文本）"]
        if notes_available:
            warnings.append("每页提取到的文本已放入幻灯片备注，便于复制")
        return BackendOutcome(outputs=[target], warnings=warnings)

    # ------------------------------------------------------------------ DOCX
    def _docx_to_text(self, source: Path, target: Path) -> BackendOutcome:
        docx = import_module_or_raise("docx", "python-docx")
        document = docx.Document(str(source))
        lines: list[str] = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            lines.append("")
            for row in table.rows:
                lines.append("\t".join(cell.text.strip() for cell in row.cells))
        target.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])

    # ------------------------------------------------------------------ 表格
    def _read_workbook(self, source: Path) -> dict[str, Any]:
        pandas = import_module_or_raise("pandas", "pandas")
        import_module_or_raise("openpyxl", "openpyxl")  # pandas 读 xlsx 需要它
        try:
            sheets = pandas.read_excel(str(source), sheet_name=None)
        except Exception as exc:
            raise ConversionFailedError(f"无法读取 Excel 文件：{exc}", self.label) from exc
        if not sheets:
            raise ConversionFailedError("Excel 文件中没有工作表", self.label)
        return sheets

    def _xlsx_to_csv(
        self, source: Path, target: Path, options: Mapping[str, Any]
    ) -> BackendOutcome:
        sheets = self._read_workbook(source)
        mode = str(options.get("xlsx_csv_mode", "sheets"))
        names = list(sheets)
        warnings: list[str] = []
        outputs: list[Path] = []
        pandas = import_module_or_raise("pandas", "pandas")

        if mode == "merged" or len(names) == 1:
            if len(names) > 1 and mode == "merged":
                frames = []
                for name in names:
                    frame = sheets[name].copy()
                    frame.insert(0, "sheet", name)
                    frames.append(frame)
                pandas.concat(frames, ignore_index=True).to_csv(target, index=False, encoding="utf-8-sig")
                warnings.append(f"已把 {len(names)} 个工作表合并为一个 CSV（新增 sheet 列）")
            else:
                sheets[names[0]].to_csv(target, index=False, encoding="utf-8-sig")
            outputs.append(target)
        elif mode == "first":
            sheets[names[0]].to_csv(target, index=False, encoding="utf-8-sig")
            outputs.append(target)
            if len(names) > 1:
                warnings.append(
                    f"仅导出了第 1 个工作表「{names[0]}」；其余 {len(names) - 1} 个未导出"
                    "（可在设置中改为 sheets 或 merged 模式）"
                )
        else:  # sheets：每个工作表一个文件
            for index, name in enumerate(names):
                if index == 0:
                    destination = target
                else:
                    safe = _safe_filename(str(name))
                    destination = target.with_name(f"{target.stem}__{safe}{target.suffix}")
                sheets[name].to_csv(destination, index=False, encoding="utf-8-sig")
                outputs.append(destination)
            if len(names) > 1:
                warnings.append(f"已按工作表拆分导出 {len(names)} 个 CSV 文件")

        for path in outputs:
            verify_output(path, self.label)
        return BackendOutcome(outputs=outputs, warnings=warnings)

    def _xlsx_to_text_like(
        self, source: Path, target: Path, target_format: Format
    ) -> BackendOutcome:
        sheets = self._read_workbook(source)
        chunks: list[str] = []
        for name, frame in sheets.items():
            if target_format is Format.MD:
                chunks.append(f"## {name}\n\n{_to_markdown_table(frame)}")
            elif target_format is Format.HTML:
                chunks.append(f"<h2>{name}</h2>\n{frame.to_html(index=False, border=0)}")
            else:
                # 反斜杠不能直接出现在 f-string 的表达式内（Python < 3.12 会报语法错误）
                table = frame.to_csv(index=False, sep="\t")
                chunks.append(f"=== {name} ===\n{table}")
        content = "\n\n".join(chunks)
        target.write_text(content, encoding="utf-8")
        verify_output(target, self.label)
        warning = [f"已导出 {len(sheets)} 个工作表"] if len(sheets) > 1 else []
        return BackendOutcome(outputs=[target], warnings=warning)

    def _csv_to_xlsx(self, source: Path, target: Path) -> BackendOutcome:
        pandas = import_module_or_raise("pandas", "pandas")
        import_module_or_raise("openpyxl", "openpyxl")
        try:
            # utf-8-sig：兼容 Excel 导出的带 BOM 文件，避免首列名混入 BOM
            frame = pandas.read_csv(source, sep=None, engine="python", encoding="utf-8-sig")
        except Exception as exc:
            raise ConversionFailedError(f"无法读取 CSV：{exc}", self.label) from exc
        with pandas.ExcelWriter(target, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name=_safe_filename(source.stem)[:31] or "Sheet1")
        verify_output(target, self.label)
        return BackendOutcome(outputs=[target])


def _safe_filename(name: str) -> str:
    """把工作表名转成安全文件名（Windows 非法字符）。"""
    cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip()
    return cleaned[:60] or "sheet"


def _to_markdown_table(frame, max_rows: int = 500) -> str:
    """把 DataFrame 渲染成 Markdown 表格（不依赖 tabulate）。"""
    columns = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for _, row in frame.head(max_rows).iterrows():
        cells = [str(value).replace("|", "\\|").replace("\n", " ") for value in row.tolist()]
        lines.append("| " + " | ".join(cells) + " |")
    if len(frame) > max_rows:
        lines.append(f"| …（共 {len(frame)} 行，仅显示前 {max_rows} 行） |" + " |" * (len(columns) - 1))
    return "\n".join(lines)


def sheet_names(path: Path) -> Sequence[str]:
    """列出 Excel 工作表名（供 UI 预览）。"""
    pandas = import_module_or_raise("pandas", "pandas")
    return list(pandas.read_excel(path, sheet_name=None).keys())
