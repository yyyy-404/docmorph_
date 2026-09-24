# DocMorph

Windows 优先的**本地**文档格式转换工具：桌面界面 + 命令行，支持 PDF / DOCX / XLSX / MD / HTML / TXT / CSV 互转。文件不上传服务器，不联网、不需要数据库。

当前版本：**0.3.0**

---

## 1. DocMorph 是什么

把多种转换手段（纯 Python 库、Pandoc、Microsoft Office、WPS、LibreOffice）统一到一个引擎里：按需检测本机能力，缺什么明确告知，而不是点击后才失败。

| 项 | 说明 |
| --- | --- |
| 运行方式 | Windows 桌面应用（WebView2）与命令行 |
| 处理范围 | 单文件、目录批量、拖拽 |
| 数据边界 | 全部在本机完成 |
| 设计取向 | 启动轻、按需加载、出错可解释、功能够用 |

### 核心功能

- 单文件 / 批量 / 拖拽转换；可保留目录结构
- 7 种输入格式、31 条转换路由；界面标明当前机器哪些可用
- 后端能力检测与自动降级（Word / Excel / WPS / LibreOffice / Pandoc / WeasyPrint）
- PDF 工具：合并；按页范围拆分/提取（`1-3,5,7-9`，留空 = 每页一个）
- 冲突策略：`rename`（默认）/ `overwrite` / `skip`；任务可取消
- 日志：`%LOCALAPPDATA%\DocMorph\logs`，界面可查看
- 配置：默认值 → 用户配置 → `DOCMORPH_*` 环境变量 → 命令行/界面参数
- 启动保护与 `--safe-mode`（启动异常时仍可用内置能力诊断）

## 2. 支持格式

| 源格式 | 可转换到 | 说明 |
| --- | --- | --- |
| `pdf` | `txt`、`docx`、`pptx` | 文本抽取 / 版面近似 / 每页图片幻灯片 |
| `docx` | `pdf`、`md`、`html`、`txt` | →PDF 需要 Office 或 LibreOffice |
| `xlsx` | `csv`、`md`、`html`、`txt`、`docx`、`pdf` | →PDF 需要 Excel 或 LibreOffice |
| `md` | `docx`、`html`、`txt`、`pdf` | →PDF = md→docx→PDF |
| `html` | `docx`、`md`、`txt`、`pdf` | →PDF 优先 Word 直接渲染 |
| `txt` | `docx`、`html`、`md`、`pdf` | 按 Markdown 语义解析 |
| `csv` | `xlsx`、`docx`、`md`、`html`、`txt`、`pdf` | 表格按行列还原 |

`pptx` **仅作输出**，不能作输入。逐条路由、后端分工与实测说明见 [CONVERSION_MATRIX.md](CONVERSION_MATRIX.md)。

## 3. 两种使用方式

### 3.1 Slim 源码版（GitHub 主仓库）

主仓库即 Slim：含完整源码、前端源码，以及已构建的 `docmorph/ui/webapp` 产物（**无需 Node** 即可开 GUI）。

```powershell
git clone https://github.com/yyyy-404/docmorph_.git
cd docmorph_
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python run.py              # 桌面界面
python run.py doctor       # 环境体检
```

或安装为命令（注册 `docmorph` / `docmorph-gui`）：

```powershell
pip install -e .
```

**可选完整功能依赖**（见 §4）：

```powershell
pip install -r requirements-full.txt
```

### 3.2 Full 可直接运行版（GitHub Release）

适合不想配置 Python 的 Windows 用户：

1. 打开本仓库 **Releases**
2. 下载 `DocMorph-Full-Windows-x64.zip`
3. 解压 → 双击 `DocMorph.exe`

| 项 | 要求 |
| --- | --- |
| 系统 | **Windows 10/11 x64** |
| Python / pip / Node | **不需要** |
| 运行时 | Microsoft Edge **WebView2**（Win11 / 新版 Win10 通常已内置） |
| →PDF 高保真 | 见 §5（Word / Excel / WPS / LibreOffice） |

## 4. requirements.txt 与 requirements-full.txt

| 文件 | 用途 | 内容 |
| --- | --- | --- |
| `requirements.txt` | **Slim 运行依赖** | 项目正常运行所需的直接第三方包（传递依赖由 pip 解析） |
| `requirements-full.txt` | **Full 功能环境** | `-r requirements.txt` + 可选能力（当前：`weasyprint>=60`） |

说明：

- 两者**都不含** pytest / ruff / pyinstaller 等开发或打包工具。
- WeasyPrint 在 Windows 上仍需系统 **GTK/Pango** 才能真正渲染；未装 GTK 时程序会标为不可用并自动降级，不影响其它转换。
- PyInstaller **不是**运行时依赖；仅维护者构建 Full 时单独安装（见 §9）。

## 5. 对 Office / WPS / LibreOffice 的依赖

**只有「输出 PDF 且需要排版保真」时才需要 Office 类软件。**

| 转换 | 需要 Office 类？ | 没有时 |
| --- | --- | --- |
| DOCX / HTML / MD / TXT → PDF | Word（或 WPS / LibreOffice） | 该路由不可用，界面说明原因 |
| XLSX → PDF | Excel（或 WPS / LibreOffice） | 同上 |
| PDF → TXT / DOCX / PPTX | 否 | 可用 |
| DOCX ↔ MD / HTML / TXT | 否 | 可用 |
| MD ↔ HTML / 纯文本 | 否 | 可用 |
| XLSX ↔ CSV 及 XLSX→MD/HTML/TXT | 否 | 可用 |

- 引擎优先级：`Word/Excel → WPS → LibreOffice → WeasyPrint`，可用 `pdf_backend_preference` 手工指定。
- 这些均为**环境条件**，不是所有用户机器上都一定可用；运行 `doctor` 可查看本机结果。

## 6. GUI / CLI 入口

根目录 `run.py` 为总入口（默认 GUI，带参数走 CLI）：

```powershell
python run.py                     # 桌面界面
python run.py --safe-mode         # 安全模式（仅内置能力）
python run.py doctor              # 环境体检
python run.py doctor --deep       # 深度自检（真实导入依赖）
python run.py formats             # 转换能力矩阵
python run.py --cli --help        # 全部 CLI 子命令
```

等价模块方式：

```powershell
python -m docmorph.ui             # 桌面界面
python -m docmorph doctor
python -m docmorph formats
```

安装为包后亦可使用 `docmorph` / `docmorph-gui` 命令。

### CLI 示例

```powershell
docmorph convert 报告.docx --to pdf
docmorph batch .\docs -o .\out --to md
docmorph formats
docmorph doctor
docmorph merge-pdf 合并.pdf a.pdf b.pdf
docmorph split-pdf 报告.pdf --pages 1-3,5
```

常用参数：`--overwrite` / `--skip` / `--rename`（默认）、`--workers N`、`--json`、`--quiet`、`--config PATH`。  
退出码：`0` 成功（含已跳过）｜`1` 转换失败｜`2` 用法错误｜`3` 缺少转换引擎。

## 7. PDF 工具

```powershell
docmorph merge-pdf 输出.pdf 输入1.pdf 输入2.pdf
docmorph split-pdf 文档.pdf --pages 1-3,5   # 留空 --pages = 每页一个文件
```

默认不覆盖同名文件。

## 8. 项目结构

```
docmorph_/
├── docmorph/                 # Python 包（引擎 / 后端 / 配置 / CLI / UI）
│   ├── ui/webapp/            # 前端构建产物（随仓库发布，用户无需 Node）
│   └── resources/            # 图标等静态资源
├── frontend/                 # Vue 3 + TypeScript 界面源码
├── packaging/                # PyInstaller 构建脚本
├── run.py                    # 总启动入口
├── config.example.ini        # 配置字段说明
├── pyproject.toml            # 打包元数据与入口点
├── requirements.txt          # Slim 运行依赖
├── requirements-full.txt     # Full 功能依赖
├── README.md
└── CONVERSION_MATRIX.md      # 转换能力矩阵
```

## 9. 维护者：构建 Full（PyInstaller）

在**干净虚拟环境**中执行（勿直接压缩历史 `.venv`）：

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\activate
pip install -r requirements-full.txt
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

产物：

- `dist\DocMorph\DocMorph.exe`（桌面版）
- `dist\DocMorphCLI\DocMorphCLI.exe`（命令行版）

将 `dist\DocMorph` 整目录压缩为 `DocMorph-Full-Windows-x64.zip`，作为 **GitHub Release 资产**上传。  
**不要**把该 zip 或 `dist/`、`.venv*` 提交进主分支。

目标机器仍需 WebView2；→PDF 高保真仍需 Office/WPS/LibreOffice 之一。

### 修改前端源码时（可选，需 Node 18+）

```powershell
cd frontend
npm install          # 或 pnpm install
npm run build        # 产物输出到 docmorph/ui/webapp
```

普通用户克隆仓库后**不必**执行此步。

## 10. 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（x64 为验证目标） |
| Python（Slim 源码版） | 3.10 ~ 3.13 |
| 图形界面 | Edge WebView2 运行时 |
| 可选（仅 →PDF） | Word / Excel、WPS、LibreOffice 之一 |
| 可选（仅改前端） | Node.js 18+ |

## 11. 已知限制

- `PDF → PPTX`：每页一张图片幻灯片（文本进备注），不能直接编辑排版。
- `PDF → DOCX`：版面近似还原，复杂排版会有偏差。
- 无文本层 PDF（扫描件）→ TXT 会失败；本版本不含 OCR。
- `XLSX → CSV` 默认按工作表拆分；可在设置改为合并或仅第一个表。
- 无 Office/WPS/LibreOffice 且无 GTK 时，所有 →PDF 不可用（其它转换不受影响）。
- 浅检测可能把「装坏了的依赖」标为可用；用 `doctor --deep` 或界面「重新检测」取权威结论。
- 安全模式禁用 Office 类后端，仅保留 Pandoc 与纯 Python（该模式下 →PDF 不可用）。
- Full（PyInstaller）发行体积约数百 MB，主要来自 pandoc / opencv / PyMuPDF 等功能依赖，详见构建产物说明。

## 12. 发布前验证说明

发布前已在构建机完成真实功能验证（非模拟），包括：

- 环境体检与转换能力矩阵检查
- 关键转换冒烟（md/docx/pdf/xlsx/csv 等）
- 默认配置下 `md → pdf` 多步转换
- 桌面界面启动
- Full（PyInstaller）构建与启动

具体路由语义与后端分工以 [CONVERSION_MATRIX.md](CONVERSION_MATRIX.md) 为准；矩阵中「本机实测」仅描述文档编写时的验证环境，**不代表**所有用户机器都具备相同外部软件。
