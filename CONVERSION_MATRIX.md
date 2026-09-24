# DocMorph 转换能力矩阵

> **矩阵与路由定义**以 `docmorph/registry.py` 为准；本文件描述产品支持的转换能力、后端分工，以及文档编写时在**构建机**上的实测结论。
>
> **产品理论支持** ≠ **每台用户机器都可用**：Word / Excel / WPS / LibreOffice / GTK 属于环境条件，请以本机 `docmorph doctor` 为准。
>
> 图例：**✔ 已验证可用** ｜ **△ 可用但有明确损失** ｜ **✖ 不支持** ｜ **— 不适用**
>
> 下方「本机基线」记录的是**验证环境快照**，不是对所有用户的承诺。

## 0. 验证环境基线（构建机快照，非普适）

| 外部组件 | 该验证机状态 | 说明 |
|---|---|---|
| Microsoft Word | 可用 | `Office16\WINWORD.EXE`；用户机器未装则该路由不可用 |
| Microsoft Excel | 可用 | `Office16\EXCEL.EXE`；用户机器未装则该路由不可用 |
| Microsoft PowerPoint | 不可用 | 仅残留 ProgID；与 PPTX 不作输入一致 |
| WPS Office | 未安装 | 可选替代，装了才会参与路由 |
| LibreOffice | 未安装 | 可选兜底，装了才会参与路由 |
| Pandoc | 可用（随包） | `pypandoc-binary` 自带，Slim/Full 均具备 |
| WeasyPrint | 不可用 | 缺 GTK/Pango；Full 已含 Python 包，仍需系统 GTK |
| Edge WebView2 | 可用 | GUI 必需；Win11/新版 Win10 通常已内置 |

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

## 3. 构建机验证记录（示例，非所有用户环境保证）

> 下表为文档编写时在**验证机**上的抽样结果；其它机器因 Office/GTK 是否安装而异。

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
| pdf→txt | PyMuPDF | — | 中文保留 ✔ |
| pdf→docx | pdf2docx | — | 38 KB, 4 段 | 中文与段落保留 ✔ |
| pdf→pptx | PyMuPDF + python-pptx | ~2s/页 | 1 页幻灯片 | **无文本层（`has_text=False`）→ 标 △** |

## 4. 后端清单

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

* **Slim（`pip install -r requirements.txt`）+ Python 3.10+** 即可使用：  
  docx↔md/html/txt、md↔docx/html/txt、html↔docx/md/txt、xlsx→csv/md/html、csv→docx/md/html/xlsx、  
  pdf→txt/docx/pptx。
* **想要「→PDF」且要求排版保真**：需安装 **Microsoft Word**（docx/md/html→pdf）或 **Microsoft Excel**（xlsx→pdf），或 **WPS Office**，或 **LibreOffice** 之一。  
  以上均为**可选环境**，缺失时对应路由会明确不可用，不会静默失败。
* **完全没有 Office 类软件** 时：→PDF 不可用（除非安装 GTK 以启用 WeasyPrint 兜底，且 WeasyPrint 包已随 `requirements-full.txt` 安装）；其它转换仍可用。  
  请运行 `docmorph doctor` 查看**本机**能力，勿假设与验证机相同。
