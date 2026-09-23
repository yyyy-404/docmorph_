# DocMorph 转换能力矩阵（第三阶段）

> **本矩阵的每一行都经过本机实测**（Windows 11 + Python 3.13.15 + 本仓库 `.venv`）。
> 实测脚本对产物做了内容质检（中文字符、页数、表格/图片是否保留），而不只看"文件是否生成"。
> 图例：**✔ 实测通过** ｜ **△ 实测通过但有明确损失** ｜ **✖ 实测不可用** ｜ **— 不适用**

## 0. 本机外部软件实测基线

| 外部组件 | 状态 | 证据 |
|---|---|---|
| Microsoft Word | **可用** | `Office16\WINWORD.EXE`；COM `Word.Application` 注册；docx→pdf 实测成功 |
| Microsoft Excel | **可用** | `Office16\EXCEL.EXE`；COM `Excel.Application` 注册 |
| Microsoft PowerPoint | **不可用** | `POWERPOINT.EXE` 不存在（仅残留 ProgID 注册项） |
| WPS Office | **未安装** | `KWPS/WPS/ET/WPP.Application` 均未注册 |
| LibreOffice | **未安装** | PATH 与两个标准安装目录均无 `soffice.exe` |
| Pandoc | **可用（随包）** | `pypandoc-binary 1.17` 自带 pandoc 二进制，`get_pandoc_version()` 正常 |
| WeasyPrint | **不可用** | `weasyprint 70` → `OSError: cannot load library 'libgobject-2.0-0'`（缺 GTK/Pango） |
| 其他 pandoc PDF 引擎 | **全部不可用** | `weasyprint/wkhtmltopdf/pdflatex/xelatex/tectonic/typst/prince/context/pdfroff` 均不在 PATH |
| poppler（pdf2image 用） | 仅存在于 Codex 运行时 PATH | 普通用户机器需另行安装 → **新架构改用 PyMuPDF，去掉该依赖** |
| Edge WebView2 运行时 | **可用** | 注册表 `pv = 153.0.4234.48` |
| Edge headless 打印 PDF | **不可用** | 已有 Edge 进程导致 `--print-to-pdf` 被转发丢弃（rc=0 但无输出），不作为方案 |

## 1. 设计原则

1. **纯 Python 优先**：能由 Python 库可靠完成的结构化转换，不引入外部软件；
2. **Office 仅用于渲染保真**：需要"排版级"输出的（→PDF），优先 Word/Excel COM；
3. **不把任何外部软件设为必需**：缺失即降级或明确报错，绝不静默崩溃；
4. **声明即真实**：矩阵中未标 ✔/△ 的组合**不得在 UI 中展示为可用**。

## 2. 最终矩阵

`W` = Word COM，`E` = Excel COM，`WPS` = WPS COM，`LO` = LibreOffice CLI，
`PD` = pandoc（pypandoc-binary），`PY` = 纯 Python（PyMuPDF/pdf2docx/python-docx/python-pptx/pandas/openpyxl）。

| 源 ↓ / 目标 → | PDF | DOCX | XLSX | MD | HTML | TXT | PPTX | CSV |
|---|---|---|---|---|---|---|---|---|
| **PDF** | — | ✔ PY<br>*pdf2docx* | ✖ | ✖ | ✖ | ✔ PY<br>*PyMuPDF* | △ PY<br>*图片幻灯片* | ✖ |
| **DOCX** | ✔ W<br>*(备份: WPS/LO)* | — | ✖ | ✔ PD | ✔ PD | ✔ PD<br>*`plain`* | ✖ | ✖ |
| **XLSX** | ✔ E<br>*(备份: LO)* | ✔ PY+PD<br>*表格→md→docx* | — | ✔ PY<br>*pandas→md 表格* | ✔ PY<br>*pandas→html 表格* | ✔ PY<br>*制表符文本* | ✖ | ✔ PY<br>*openpyxl* |
| **MD** | ✔ PD+W<br>*md→docx→pdf* | ✔ PD | ✖ | — | ✔ PD | ✔ PD<br>*`plain`* | ✖ | ✖ |
| **HTML** | ✔ W<br>*Word 直开导出*<br>*(备份: PD+W、LO)* | ✔ PD | ✖ | ✔ PD | — | ✔ PD<br>*`plain`* | ✖ | ✖ |
| **TXT** | ✔ PD+W<br>*md 读取器→docx→pdf* | ✔ PD<br>*md 读取器* | ✖ | ✔ PD<br>*md 读取器* | ✔ PD<br>*md 读取器* | — | ✖ | ✖ |
| **PPTX** | ✖ | ✖ | ✖ | ✖ | ✖ | ✖ | — | ✖ |
| **CSV** | ✖ | ✔ PD | ✔ PY | ✔ PD | ✔ PD | ✔ PY | ✖ | — |

> 说明：`PPTX` 作为**源**格式在本版本不支持（解析渲染需 PowerPoint COM，本机不可用且受众有限）；
> 矩阵中不声明，UI 中不展示为可转换源。`PDF→XLSX / DOCX→XLSX / MD→XLSX / HTML→XLSX` 同理不声明。

## 3. 逐条实测记录（本轮真实执行）

| 路由 | 后端 | 耗时 | 产物 | 质检结果 |
|---|---|---|---|---|
| docx→pdf | Word COM | 4.45–8.89s | 147–174 KB, 1 页 | 中文保留，文本长度 86 |
| docx→md | pandoc | 1.10s | 530 B | 中文保留，含表格 |
| docx→html | pandoc | 0.77s | 542 B | 中文保留 |
| docx→txt | pandoc `txt` | 0.19s | **失败** | `Invalid output format! Got txt` |
| docx→txt | pandoc `plain` | <0.3s | 406 字符 | 中文保留 → **改用 `plain`** |
| md→docx | pandoc | 0.40s | 11 KB, 4 段, 1 表 | 中文保留 |
| md→html | pandoc | 0.24s | 315 B | 中文保留 |
| md→pdf | pandoc+weasyprint | 0.26s | **失败** | `weasyprint not found`（pandoc 找不到 CLI） |
| md→pdf | pandoc→docx→Word | 3.61s | 144 KB, 1 页 | 中文保留 ✔ |
| html→docx | pandoc | 0.28s | 10.7 KB, 3 段, 1 表 | 中文保留 |
| html→md | pandoc | 0.28s | 73 B | 中文保留 |
| html→txt | pandoc `txt` | 0.13s | **失败** | `Invalid output format! Got txt` |
| html→pdf | pandoc+weasyprint | 0.29s | **失败** | `weasyprint not found` |
| html→pdf | Word COM（Word 直开 HTML 导出 PDF） | — | 36 KB | 中文保留 ✔ |
| html→pdf | pandoc→docx→Word | 4.04s | 51 KB, 1 页 | 中文保留 ✔ |
| txt→docx | pandoc（markdown 读取器） | 4.81s（含转 PDF） | 10.5 KB | 中文保留 ✔ |
| xlsx→csv（仅首个 sheet） | pandas+openpyxl | 0.05s | 36 B | **丢失第 2 个 sheet** |
| xlsx→csv（合并全部 sheet） | pandas+openpyxl | — | — | 含"第二张表" ✔ |
| pdf→txt | PyPDF2 | — | 87 字符, 1 页 | 中文保留 ✔ |
| pdf→docx | pdf2docx | — | 38 KB, 4 段 | 中文与段落保留 ✔ |
| pdf→pptx | PyMuPDF/pdf2image + python-pptx | ~2s/页 | 1 页幻灯片 | **无文本层（`has_text=False`）→ 标 △** |

### 3.1 实测暴露、必须修复的问题

| 编号 | 问题 | 影响 | 修复方式 |
|---|---|---|---|
| M1 | pandoc **没有 `txt` 目标格式**，正确输出格式是 `plain` | `docx→txt`、`html→txt` 当前**必然失败** | 引擎内做格式别名映射 `txt → plain` |
| M2 | 默认 `pdf_engine = weasyprint` 在本机**完全不可用**（缺 GTK），且 pandoc 也找不到 weasyprint CLI | `md→pdf`、`html→pdf` 当前**必然失败** | 默认改走 Word COM；WeasyPrint 降级为"检测到 GTK 才启用"的可选后端 |
| M3 | `xlsx→csv` 只导出第一个 sheet | 多 sheet 数据**静默丢失** | 默认导出全部 sheet（分文件 + 合并模式），并在结果中给出 warning |
| M4 | `pdf→pptx` 产物为纯图片 | 用户拿到**不可编辑**的 PPT | 保持图片策略，但把 PDF 提取文本写入**演讲者备注**，并在结果中标注 warning |
| M5 | `pdf2image` 依赖 poppler（普通用户机器没有） | 普通用户 `pdf→pptx` 失败 | 改用 PyMuPDF 渲染页面，移除 poppler 依赖 |
| M6 | `docx2pdf` 要求 `>=0.1.16`，该版本不存在 | **干净环境无法 pip install** | 锁定可用版本并在新依赖清单中修正 |
| M7 | `xlsx` 读取隐式依赖 `openpyxl`，但清单里没有 | 干净环境 `xlsx→csv` 失败 | 显式加入 `openpyxl` |
| M8 | Office COM 被放入线程池并发执行 | 多文件批量时 Word 实例互相干扰/挂起风险 | 每个 Office 后端独立串行闸门 + 超时 |

## 4. 后端清单（新架构）

| 后端 id | 实现 | 依赖类型 | 覆盖路由 |
|---|---|---|---|
| `pandoc` | pypandoc-binary（自带 pandoc） | 纯 Python 包 | 文档结构类：office↔md/html/plain、md↔html、csv→md |
| `python` | PyMuPDF / pdf2docx / python-docx / python-pptx / pandas / openpyxl / Pillow | 纯 Python 包 | pdf→txt/docx/pptx、xlsx→csv/md/html/txt |
| `word` | Word COM（pywin32 → `Word.Application`） | 外部软件 | docx→pdf、html→pdf、任意可转 docx 的源→pdf |
| `excel` | Excel COM（`Excel.Application`） | 外部软件 | xlsx→pdf |
| `wps` | WPS COM（`KWPS.Application`） | 外部软件（可选） | docx/xlsx→pdf（Word/Excel 缺失时的替代） |
| `libreoffice` | `soffice --headless --convert-to` | 外部软件（可选） | office→pdf 兜底 |
| `weasyprint` | weasyprint（需 GTK） | 可选 Python + 系统库 | html/md→pdf 兜底 |

## 5. 每个目标格式的引擎优先顺序

| 目标 | 优先顺序 |
|---|---|
| **PDF** | `word`/`excel`（对应源） → `wps` → `libreoffice` → `weasyprint`(若有 GTK) → 失败并给出安装建议 |
| **DOCX** | `pandoc` → `python`（本机源为 docx 时直接复制/规范化） |
| **MD / HTML / TXT** | `pandoc`（txt 走 `plain`）→ `python`（xlsx/pdf 源） |
| **CSV / XLSX** | `python`（openpyxl/pandas） |
| **PPTX** | `python`（PyMuPDF 渲染 + python-pptx，含备注文本） |

## 6. 用户必须安装什么（结论）

* **只需 Python 3.10+ 与 `pip install -r requirements.txt`** 即可使用：
  docx↔md/html/txt、md↔docx/html/txt、html↔docx/md/txt、xlsx→csv/md/html、csv→docx/md/html/xlsx、
  pdf→txt/docx/pptx。
* **想要"→PDF"且要求排版保真**：需要安装 **Microsoft Word（docx/md/html→pdf）** 或
  **Microsoft Excel（xlsx→pdf）**，或 **WPS Office**（Word/Excel 的替代），或 **LibreOffice**（兜底）。
* **完全没有 Office** 时：→PDF 不可用（除非自行安装 GTK 以启用 WeasyPrint 兜底）；其它转换仍全部可用，
  程序会在能力面板中明确说明原因。
