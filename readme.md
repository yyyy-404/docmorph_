# 📄 文档格式转换器（Document Format Converter）

一个基于 Python 开发的多格式文档批量转换工具，支持图形界面（GUI）和命令行（CLI）操作，支持配置文件自定义默认参数，支持线程池加速处理、日志记录、PDF 引擎切换等特性。

## ✅ 功能特点

- 支持多种文件格式转换：
  - PDF ↔ DOCX、TXT
  - DOCX → PDF、Markdown、HTML
  - HTML ↔ PDF、DOCX、Markdown
  - Excel（.xlsx）→ CSV
  - Markdown ↔ DOCX、PDF
- 支持批量转换和单文件转换
- 图形界面（Tkinter）与命令行接口共存
- 支持默认配置文件 `config.ini`
- 自动生成转换日志 `logs/conversion_log_*.txt`
- 使用线程池进行并发加速
- 可选择是否覆盖已有文件
- 可选 PDF 引擎（默认使用 WeasyPrint，支持切换为 pdflatex）

------

## 📦 安装依赖

**需要python环境**



项目使用以下主要依赖库，请使用 `pip` 安装：

```
bash


复制编辑
pip install -r requirements.txt
```

如果你没有 `requirements.txt` 文件，可使用以下命令手动安装：

```
bash复制编辑pip install pdf2docx docx2pdf pypandoc pandas PyPDF2 ttkthemes
pip install weasyprint  # 用于 PDF 生成（默认）
```

> ⚠️ 若使用 `weasyprint` 出错，也可在 config.ini 中切换为 `pdflatex`（需本地安装）。

------

## 🛠 如何使用

### 方式一：图形界面（推荐）

```
bash


复制编辑
python converter_gui.py
```

运行后可选择文件或目录，设置目标格式，一键执行转换，支持进度条和失败提示。

------

### 方式二：命令行使用

```
bash


复制编辑
python converter.py input_path output_path --from docx --to pdf [--batch] [--overwrite]
```

#### 参数说明：

| 参数          | 说明                     |
| ------------- | ------------------------ |
| `input_path`  | 输入文件或文件夹路径     |
| `output_path` | 输出文件或文件夹路径     |
| `--from`      | 源格式，如 docx、pdf     |
| `--to`        | 目标格式，如 pdf、docx   |
| `--batch`     | 启用批量转换（用于目录） |
| `--overwrite` | 覆盖已存在的文件         |



示例：将 input 文件夹中的 DOCX 批量转换为 PDF：

```
bash


复制编辑
python converter.py ./input ./output --from docx --to pdf --batch
```

------

## ⚙️ 配置文件说明（config.ini）

首次运行会自动生成 `config.ini` 文件，格式如下：

```
ini复制编辑[Paths]
input_directory = ./input
output_directory = ./output

[Defaults]
default_docx_to_format = pdf
default_pdf_to_format = docx
default_xlsx_to_format = csv
default_md_to_format = docx
default_html_to_format = md

[Conversion]
default_format = pdf
overwrite = false
pdf_engine = weasyprint

[Log]
log_dir = ./logs
```

你可以修改此配置文件来自定义：

- 默认输入输出目录
- 各文件类型的默认转换目标格式
- 是否允许覆盖（true/false）
- PDF 引擎选择（`weasyprint` 或 `pdflatex`）

## ✅ 支持的格式转换一览（默认转换方向）

| 源格式（from） | 默认目标格式（to） | 其他支持格式        |
| -------------- | ------------------ | ------------------- |
| `docx`         | `pdf`              | `md`, `html`, `txt` |
| `pdf`          | `docx`             | `txt`, `html`       |
| `md`           | `docx`             | `pdf`, `html`       |
| `html`         | `md`               | `docx`, `pdf`       |
| `xlsx`         | `csv`              | -                   |



> ✅ 默认转换方向可在 `config.ini` 中自定义。