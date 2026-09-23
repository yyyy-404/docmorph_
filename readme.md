# DocMorph

Windows 优先的**本地**文档格式转换工具：桌面界面 + 命令行，支持 PDF / DOCX / XLSX / MD / HTML / TXT / CSV 互转。文件不会上传到任何服务器，不联网、不需要数据库，也不依赖 Web 服务。

---

## 1. 项目简介

DocMorph 解决的是「手头有各种格式的文档、需要批量转成另一种格式」这类日常问题。它把不同的转换手段（纯 Python 库、Pandoc、Microsoft Office、WPS、LibreOffice）统一到同一个引擎里，并在启动时检测本机到底能用哪些，缺什么就明确告诉用户，而不是点了按钮才报错。

- 运行方式：Windows 桌面应用（WebView2 窗口）与命令行
- 处理范围：单文件、目录批量、拖拽
- 数据边界：全部在本机完成

## 2. 核心功能

- **单文件转换**：选择一个文件 + 目标格式即可转换，输出路径自动推导。
- **批量转换**：可拖入整个目录，递归处理并可选保留目录结构（避免不同子目录的同名文件互相覆盖）。
- **拖拽操作**：把文件或文件夹拖进窗口即可加入待转换列表。
- **转换能力矩阵**：7 种输入格式、31 条转换路由；界面会标明当前机器上哪些可用、哪些缺引擎。
- **后端能力检测与自动降级**：Word / Excel / WPS / LibreOffice / Pandoc / WeasyPrint 逐项检测；输出 PDF 时自动挑选当前可用且保真度最高的引擎。
- **冲突策略**：目标已存在时支持 `rename`（默认，自动改名，绝不覆盖）/ `overwrite` / `skip`。
- **进度与结果**：逐文件进度与状态（成功 / 有提示的成功 / 已跳过 / 不支持 / 引擎缺失 / 失败 / 已取消）、耗时、使用的后端，以及可读的失败原因。
- **取消任务**：批量转换中途可取消；已开始的单个文件会跑完，未开始的不再启动。
- **日志**：写入 `%LOCALAPPDATA%\DocMorph\logs`，界面内置日志面板可实时查看并可直接打开日志文件。
- **配置**：默认值 → 用户配置文件 → `DOCMORPH_*` 环境变量 → 命令行/界面参数，逐层覆盖；旧版 `config.ini` 会自动迁移。
- **CLI 与 GUI 共用同一核心**：两者行为一致，不存在两套转换逻辑。
- **PDF 合并**：`docmorph merge-pdf`（命令行）与引擎 API 均可用。

## 3. 技术栈

| 层次 | 技术 | 说明 |
| --- | --- | --- |
| 桌面外壳 | **pywebview**（Windows 上使用系统 Edge WebView2） | 不打包浏览器内核，安装体积小 |
| 前端 | **Vue 3 + TypeScript + Vite + Pinia** | 纯静态产物，本地加载，不需要服务器 |
| 语言 | Python 3.10 ~ 3.13（开发与验证使用 3.13.15） | 核心业务与转换调度 |
| 结构化文档转换 | **pandoc**（由 `pypandoc-binary` 随包提供，无需单独安装） | docx / md / html / 纯文本 / csv |
| PDF 处理 | **PyMuPDF**、**pdf2docx** | 文本抽取、页面渲染、PDF→DOCX |
| 办公文档 | python-docx、python-pptx、pandas、openpyxl、Pillow | DOCX/PPTX/XLSX 读写与表格处理 |
| Office 渲染 | **pywin32 + COM**（Word / Excel），WPS 同理 | 高保真导出 PDF |
| 测试 | pytest（124 个用例） | 单元 / 集成 / 端到端 |
| 静态检查 | ruff | `ruff check .` |
| 打包 | PyInstaller 6（`--onedir`） | `packaging/build.ps1` |

## 4. 项目结构

```
docmorph_/
├── docmorph/                     # Python 包
│   ├── __init__.py               # 公共 API 与版本号
│   ├── __main__.py               # python -m docmorph（CLI）
│   ├── errors.py                 # 异常层次（配置/后端/输入/输出/超时/取消…）
│   ├── formats.py                # 格式定义与别名归一化（txt→plain 等）
│   ├── results.py                # ConversionRequest / Result / Status / ConflictPolicy
│   ├── capability.py             # 运行环境能力检测（Word/WPS/Pandoc/LibreOffice/WebView2…）
│   ├── registry.py               # 路由表：(源格式,目标格式) → 有序候选方案（支持链式）
│   ├── engine.py                 # 转换引擎：校验、选路、执行、计时、状态翻译
│   ├── jobs.py                   # 批量执行器：并发、取消、进度、统计
│   ├── services.py               # 应用服务层（GUI 与 CLI 共用）
│   ├── logging_setup.py          # 队列化日志（文件 + 内存环形缓冲）
│   ├── settings/                 # 配置系统
│   │   ├── paths.py              # %APPDATA% / %LOCALAPPDATA% / 临时工作区
│   │   ├── schema.py             # 默认值、校验、模板渲染（唯一事实来源）
│   │   └── manager.py            # 分层合并、旧配置迁移、持久化
│   ├── backends/                 # 具体转换手段
│   │   ├── base.py               # 后端抽象与产物校验
│   │   ├── pandoc_backend.py     # pandoc（docx/md/html/plain/csv）
│   │   ├── python_backend.py     # PyMuPDF / pdf2docx / 表格 / DOCX 文本
│   │   ├── office.py             # Word / Excel / WPS（COM，串行 + 超时保护）
│   │   ├── libreoffice_backend.py# soffice 命令行（可选）
│   │   └── weasyprint_backend.py # HTML→PDF（可选，需 GTK）
│   ├── cli/                      # 命令行（convert/batch/formats/doctor/config/merge-pdf）
│   ├── ui/                       # 桌面界面
│   │   ├── app.py                # pywebview 外壳、窗口、拖拽事件接入
│   │   ├── bridge.py             # 暴露给前端的 API（JSON 契约）
│   │   └── webapp/               # 前端构建产物（随包发布，用户无需 Node）
│   └── resources/                # 图标等静态资源
├── frontend/                     # 界面源码（Vue 3 + TS + Vite）
│   ├── src/components/           # 拖拽区/文件列表/格式选择/队列/日志/设置/能力面板
│   ├── src/stores/app.ts         # Pinia 状态
│   └── src/api.ts                # 与 Python 桥接（浏览器预览模式自动降级）
├── packaging/                    # PyInstaller 入口与构建脚本
├── tests/
│   ├── fixtures/                 # 用代码生成测试文档（不提交二进制）
│   ├── unit/                     # 格式/结果/路由/配置/日志/能力/引擎/任务/服务
│   ├── integration/              # 真实转换（pandoc / PDF / Office，缺依赖自动跳过）
│   └── e2e/                      # 命令行端到端
├── config.example.ini            # 配置字段说明
├── requirements.txt              # 运行依赖（仅 Python 包）
├── requirements-dev.txt          # 开发与测试依赖
├── CONVERSION_MATRIX.md          # 转换能力矩阵（逐条实测记录）
└── pyproject.toml                # 打包元数据、入口点、pytest/ruff 配置
```

## 5. 支持格式

| 源格式 | 可转换到 | 说明 |
| --- | --- | --- |
| `pdf` | `txt`、`docx`、`pptx` | 文本抽取 / 版面近似还原 / 每页图片幻灯片 |
| `docx` | `pdf`、`md`、`html`、`txt` | 输出 PDF 需要 Office 或 LibreOffice |
| `xlsx` | `csv`、`md`、`html`、`txt`、`docx`、`pdf` | 输出 PDF 需要 Excel 或 LibreOffice |
| `md` | `docx`、`html`、`txt`、`pdf` | 输出 PDF = md→docx→PDF（保排版） |
| `html` | `docx`、`md`、`txt`、`pdf` | 输出 PDF 优先由 Word 直接渲染 |
| `txt` | `docx`、`html`、`md`、`pdf` | 纯文本按 Markdown 语义解析 |
| `csv` | `xlsx`、`docx`、`md`、`html`、`txt`、`pdf` | 表格按行列还原 |

`pptx` 目前**只能作为输出**，不能作为输入（解析 PPT 版面需要 PowerPoint，本版本不支持）。完整矩阵、每条路由使用的后端与实测结果见 `CONVERSION_MATRIX.md`。

## 6. 转换后端

| 后端 | 依赖类型 | 覆盖能力 |
| --- | --- | --- |
| `pandoc` | Python 包（自带 pandoc 二进制） | docx/md/html/纯文本/csv 之间的结构化转换 |
| `python` | Python 包 | PDF→文本/DOCX/PPTX、XLSX↔CSV、XLSX→MD/HTML/TXT、DOCX→TXT |
| `word` | **外部软件**：Microsoft Word | docx / html / txt → PDF（排版保真最好） |
| `excel` | **外部软件**：Microsoft Excel | xlsx → PDF |
| `wps` | **外部软件**：WPS Office（可选） | Word/Excel 缺失时的等价替代 |
| `libreoffice` | **外部软件**：LibreOffice（可选） | 无 Office 时的 PDF 渲染兜底 |
| `weasyprint` | 可选 Python 包 + **GTK/Pango** | HTML→PDF 的纯 Python 兜底（Windows 默认不可用） |

## 7. Word / WPS 依赖说明

**只有「输出 PDF 且需要排版保真」时才需要 Office 类软件。**

| 转换 | 需要 Word/Excel？ | 没有 Office 时 |
| --- | --- | --- |
| DOCX → PDF | 需要 Word（或 WPS / LibreOffice） | 该转换不可用，界面会说明原因 |
| HTML → PDF | 需要 Word（或 WPS / LibreOffice） | 同上（WeasyPrint 需额外安装 GTK） |
| MD / TXT → PDF | 需要 Word（或 WPS / LibreOffice） | 同上 |
| XLSX → PDF | 需要 Excel（或 WPS / LibreOffice） | 同上 |
| PDF → TXT / DOCX / PPTX | **不需要** | 始终可用 |
| DOCX ↔ MD / HTML / TXT | **不需要** | 始终可用 |
| MD ↔ HTML / 纯文本 | **不需要** | 始终可用 |
| XLSX → CSV / MD / HTML / TXT | **不需要** | 始终可用 |
| CSV → XLSX / MD / HTML / TXT | **不需要** | 始终可用 |

- **WPS 完全可选**：检测到 WPS 时才作为 Word/Excel 的替代参与路由，不会要求用户安装。
- 引擎优先级固定为 `Word/Excel → WPS → LibreOffice → WeasyPrint`，可在设置中用 `pdf_backend_preference` 手工指定（例如强制使用 LibreOffice）。
- 一台 Office 都装不了的机器：改用非 PDF 目标格式（md/html/docx/txt 全部可用），或安装免费的 LibreOffice。

## 8. 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（其他平台可用 CLI，但本项目以 Windows 为主） |
| Python | 3.10 ~ 3.13 |
| 图形界面 | Microsoft Edge WebView2 运行时（Windows 11 与新版 Windows 10 已内置） |
| 可选（仅影响输出 PDF） | Microsoft Word / Excel、WPS Office、LibreOffice 之一 |
| 可选（仅开发前端） | Node.js 18+ |

## 9. 安装

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

或作为包安装（会注册 `docmorph` 与 `docmorph-gui` 两个命令）：

```powershell
pip install -e .
```

## 10. 开发运行

根目录 `run.py` 是总入口（默认开图形界面，带参数则走 CLI）：

```powershell
python run.py                     # 桌面界面
python run.py doctor              # 环境体检
python run.py formats             # 转换能力矩阵
python run.py --cli --help        # 全部 CLI 子命令
```

等价的模块方式：

```powershell
python -m docmorph.ui            # 桌面界面
python -m docmorph doctor        # 环境体检
python -m docmorph formats       # 查看转换能力矩阵
```

修改界面（需要 Node.js）：

```powershell
cd frontend
npm install
npm run build                    # 产物输出到 docmorph/ui/webapp
```

## 11. CLI

```powershell
docmorph convert 报告.docx --to pdf            # 单文件
docmorph convert 报告.docx -o D:\out --to md    # 指定输出目录
docmorph batch .\docs -o .\out --to md          # 批量（默认保留目录结构）
docmorph batch .\docs -o .\out --to md --flat   # 批量（平铺到输出目录）
docmorph formats                                # 能力矩阵（含当前环境可用性）
docmorph doctor                                 # 环境体检
docmorph config --path                          # 配置文件位置
docmorph merge-pdf 合并.pdf a.pdf b.pdf         # 合并 PDF
```

参数：`--overwrite` / `--skip` / `--rename`（默认）、`--workers N`、`--json`、`--quiet`、`--config PATH`。

退出码：`0` 成功（含「已跳过」）｜`1` 转换失败｜`2` 用法错误｜`3` 缺少转换引擎。

旧写法 `docmorph <输入> --to <格式>` 仍然可用。

## 12. 构建与打包

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

产物：`dist\DocMorph\DocMorph.exe`（桌面版）与 `dist\DocMorphCLI\DocMorphCLI.exe`（命令行版）。两个目录都是绿色免安装的，可以整体拷贝到其他 Windows 机器；目标机器仍需具备 WebView2 运行时，若要用 Office 渲染则同样需要装好 Office/WPS/LibreOffice。

## 13. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # 124 passed
.\.venv\Scripts\python.exe -m ruff check .       # All checks passed
```

需要外部软件的用例（Word / Excel）在检测不到时会**自动跳过**，不会因为开发机没装 Office 而失败。

## 14. 系统能力检测

```powershell
docmorph doctor          # 文本报告
docmorph doctor --json   # 机器可读
```

界面里对应「系统能力」页，逐项显示 Word / Excel / WPS / LibreOffice / Pandoc / WeasyPrint / WebView2 / PyMuPDF / pywin32 是否可用、检测到的路径，以及缺失时的安装建议。

## 15. 已知限制

- `PDF → PPTX` 生成的是**每页一张图片**的幻灯片（从 PDF 抽取到的文本会放进演讲者备注），不能直接编辑排版。
- `PDF → DOCX` 是版面近似还原，复杂排版（多栏、浮动图、公式）会有偏差。
- PDF 若无文本层（扫描件），`PDF → TXT` 会失败并提示需要 OCR，本版本不含 OCR。
- `XLSX → CSV` 默认按工作表拆分导出（`sample.csv`、`sample__第二页.csv`），可在设置中改为合并或仅导出第一个工作表。
- `XLSX → MD/HTML/TXT` 导出的是表格数据，不含原表样式与图表。
- 没有 Office / WPS / LibreOffice 且未安装 GTK 时，所有输出 PDF 的转换不可用（其余转换不受影响）。
- 拖拽依赖 WebView2 的 DOM 事件；若某些环境取不到真实路径，请改用「选择文件 / 选择文件夹」。
- PyInstaller 发行目录约 500 MB，主要来自 numpy / opencv / PyMuPDF；如需瘦身可进一步裁剪 `pdf2docx` 的图像处理依赖。

## 16. 开发状态

当前版本 **0.3.0**：核心引擎、后端抽象、能力检测、任务系统、配置与日志分层、CLI、桌面界面（Vue 3）、打包脚本与测试体系均已完成，并在本机对全部 31 条转换路由做了真实转换验证（结果记录在 `CONVERSION_MATRIX.md`）。

后续可扩展方向：PDF 合并/拆分/加密解密、OCR、图片格式互转、EPUB/ODT、转换预设与历史记录、批量重命名规则、更多界面主题。
