# DocMorph 项目全貌报告（跨会话上下文）

> 用途：供任意模型、任意新对话快速建立对本项目的**准确、完整**认知，用于优化与可持续开发。
> 事实以**当前代码**为准；与本文件冲突时以代码为准，并请更新本文件。
> 最近核对：清理后基线 — Python 3.13 / 版本 0.3.0 / pytest **124 passed** / ruff 通过。

---

## 1. 一句话定位

**DocMorph** 是 Windows 优先的**本地**文档格式转换工具：桌面 GUI（pywebview + Vue 3）+ CLI，把 PDF/DOCX/XLSX/MD/HTML/TXT/CSV 等互转；**不联网、无数据库、无 Web 服务、文件不出本机**。

---

## 2. 绝对约束（改需求前必须遵守）

| 约束 | 说明 |
| --- | --- |
| 本地桌面 | 禁止 Web 化 / 云 / 账号 / 数据库 / Redis / Docker / K8s / 微服务 |
| 不换栈 | Python 3.10–3.13 + Vue 3 + TS + Vite + Pinia + pywebview(WebView2) |
| 双端同核 | GUI 与 CLI **必须**共用 `ApplicationService`，禁止两套转换逻辑 |
| 外部软件可选 | Word/Excel/WPS/LibreOffice 一律可选；缺失 = 降级或明确报错，**禁止静默崩溃** |
| 声明即真实 | UI/CLI 只展示 `registry` 中声明且当前环境可用的路由 |
| 依赖惰性 | 重依赖不在 import 时加载；缺失时抛 `DependencyMissingError` |
| 默认不覆盖 | 冲突策略默认 `rename`，绝不悄悄覆盖用户文件 |
| 中文 UX | 异常 message 面向用户中文；技术细节放 cause/traceback |

**非目标**：为了“高级”堆技术栈；重构整个项目；修改与任务无关的业务逻辑。

---

## 3. 技术栈与依赖

| 层 | 技术 |
| --- | --- |
| 桌面壳 | pywebview（Windows = 系统 Edge WebView2） |
| 前端 | Vue 3 + TypeScript + Vite + Pinia（无 Router，单页面板切换） |
| 后端 | Python 包 `docmorph`（setuptools / pyproject） |
| 结构化转换 | pandoc（由 `pypandoc-binary` 自带，无需用户另装） |
| PDF | PyMuPDF、pdf2docx（**不用** poppler/pdf2image） |
| Office | python-docx、python-pptx、pandas、openpyxl、Pillow |
| 高保真 →PDF | pywin32 COM（Word/Excel/WPS）；可选 LibreOffice / WeasyPrint |
| 测试/检查 | pytest、ruff（line-length 100） |
| 打包 | PyInstaller 6 `--onedir`，脚本 `packaging/build.ps1` |

核心运行依赖清单：`requirements.txt`（与 `pyproject.toml` dependencies 一致）。  
开发依赖：`requirements-dev.txt`（pytest、pytest-cov、ruff）。

---

## 4. 架构（依赖方向严格单向）

```
run.py / docmorph-gui / python -m docmorph.ui     docmorph / python -m docmorph
        │ ui/ (pywebview + bridge)                        │ cli/
        └──────────────────┬───────────────────────────────┘
                           ▼
              services.ApplicationService          ← 唯一业务门面
                    │            │
                    ▼            ▼
             jobs.JobRunner   capability.detect
                    │
                    ▼
             engine.ConversionEngine               ← 校验 / 选路 / 执行 / 计时
                    │
                    ▼
             registry.ROUTES                       ← (src,dst) → 有序 Plan 列表
                    │
                    ▼
             backends/*  (pandoc | python | word/excel/wps | libreoffice | weasyprint)

横切：settings/（配置） · logging_setup/（日志） · errors.py · results.py · formats.py
```

**规则**：UI/CLI → services → engine → registry → backends；backends 不依赖 UI/CLI；不在 engine 里写死具体后端分支链。

---

## 5. 模块地图（文件 → 职责 → 改哪里）

### 5.1 核心领域

| 模块 | 职责 | 扩展时改这里 |
| --- | --- | --- |
| `formats.py` | `Format` 枚举、别名归一（txt→plain 等）、`detect_format` | 新格式 / 新别名 |
| `results.py` | `ConversionRequest/Result`、`ConversionStatus`、`ConflictPolicy` | 新状态字段、结果结构 |
| `errors.py` | `DocMorphError` 层次（配置/不支持/后端缺失/输入/输出/超时/取消…） | 新失败类别 |
| `registry.py` | **路由表** `ROUTES[(src,dst)] = (Plan, …)`；Plan = 多步 `((backend_id, 中间格式), …)` | **新增一条转换** |
| `capability.py` | 检测 Word/WPS/LibreOffice/Pandoc/WeasyPrint/WebView2/库版本 | 新外部能力 |
| `engine.py` | `ConversionEngine.convert`：校验 → `select_plan` → 执行 → 状态翻译 | 选路策略、公共前置逻辑 |
| `jobs.py` | `JobRunner`：并发、每后端串行闸门、取消、进度、汇总 | 批量并发/取消粒度 |
| `services.py` | `ApplicationService`：展开输入、输出路径、批量编排、catalog/doctor/logs | **给 GUI/CLI 加用户能力** |
| `logging_setup.py` | 队列化日志 + 内存环形缓冲（UI 日志面板） | 日志格式/保留策略 |
| `utils.py` | `ensure_console_encoding`（GBK 控制台防崩） | 一般不动 |

### 5.2 配置 `settings/`

优先级（低→高）：

```
代码默认值  <  用户配置文件  <  DOCMORPH_<SECTION>_<KEY> 环境变量  <  CLI/UI 传入
```

| 文件 | 职责 |
| --- | --- |
| `schema.py` | 默认值、校验、INI 模板渲染 — **唯一事实来源** |
| `paths.py` | 配置/日志/临时目录（`%APPDATA%` / `%LOCALAPPDATA%`） |
| `manager.py` | 分层合并、旧键迁移（如 `overwrite`→`conflict_policy`）、持久化 |

配置文件默认在用户目录（见 `doctor` 输出）；`config.example.ini` 为字段模板。  
新增配置项：**schema 默认值 + 校验 + example + 测试** 同步改。

### 5.3 后端 `backends/`

| 文件 | 覆盖 |
| --- | --- |
| `base.py` | 抽象基类、`verify_output` 产物校验 |
| `pandoc_backend.py` | docx/md/html/plain/csv 结构化互转（txt 用 `plain`） |
| `python_backend.py` | pdf→txt/docx/pptx、xlsx↔csv/md/html/txt、表格等 |
| `office.py` | Word/Excel/WPS COM（**串行闸门 + 超时**） |
| `libreoffice_backend.py` | `soffice --headless` 兜底 |
| `weasyprint_backend.py` | HTML→PDF 兜底（Windows 需 GTK） |

新增后端：新文件 + 在 `registry.ROUTES` 注册步骤 + `capability` 若需检测则补检测 + 测试。

### 5.4 CLI `cli/main.py`

子命令：`convert` · `batch` · `formats` · `doctor` · `config` · `merge-pdf`（`legacy` 为隐藏旧语法适配，仍走新服务层）。

退出码约定（README）：`0` 成功（含跳过）｜`1` 转换失败｜`2` 用法错误｜`3` 缺引擎。

### 5.5 桌面 UI

| 位置 | 职责 |
| --- | --- |
| `ui/app.py` | pywebview 窗口、WebView2 拖拽事件、启动/退出 |
| `ui/bridge.py` | `Api`：暴露给前端的 JSON 契约；后台线程跑任务；`get_state` 轮询进度 |
| `ui/webapp/` | **前端构建产物**（随包发布，用户无需 Node）；缺失时降级 HTML 提示 |
| `frontend/src/api.ts` | 调 `window.pywebview.api.*`；浏览器 dev 模式模拟降级 |
| `frontend/src/stores/app.ts` | Pinia 状态 |
| `frontend/src/App.vue` + `components/*` | 四面板：转换 / 日志 / 系统能力 / 设置 |
| `frontend/src/styles/theme.css` | 视觉基线（浅灰玻璃拟态 + 调色板） |

**改界面**：改 `frontend/src` → `cd frontend && pnpm/npm install && npm run build` → 产物进 `docmorph/ui/webapp`。  
**改桥**：先动 `bridge.py`，同步 `api.ts` 的 `PywebviewApi` 与 `types.ts`（契约两端一起改）。

### 5.6 打包

- 入口：`packaging/DocMorph.py`（GUI）、`DocMorphCLI.py`（CLI）
- 脚本：`packaging/build.ps1`（依赖 `.venv`、icon、webapp、pypandoc files）

---

## 6. 关键数据流（一次转换）

```
用户输入（文件/目录/拖拽）
  → ApplicationService 展开输入、推导输出路径（keep_structure、冲突策略）
  → JobRunner 建任务（并发；Office 类串行）
  → ConversionEngine.convert(request)
       1) 输入/格式校验
       2) registry.select_plan（能力 + 用户偏好过滤）
       3) 逐步调用 backend.convert
       4) 计时、写 ConversionResult(status, backend, outputs, warnings, error…)
  → 状态不是 bool：SUCCESS / SUCCESS_WITH_WARNINGS / SKIPPED_EXISTS /
     UNSUPPORTED / BACKEND_UNAVAILABLE / INVALID_INPUT / FAILED / CANCELLED
  → CLI 映射退出码；GUI bridge 轮询 get_state 刷新进度/结果
```

---

## 7. 入口一览

| 方式 | 命令 |
| --- | --- |
| 总入口（推荐开发用） | `python run.py`（GUI）／`python run.py doctor`（CLI 子命令透传） |
| GUI | `python -m docmorph.ui` 或安装后 `docmorph-gui` |
| CLI | `python -m docmorph …` 或安装后 `docmorph …` |
| 包安装 | `pip install -e .` / `pip install -r requirements.txt` |
| 测试 | `.venv\Scripts\python.exe -m pytest -q` |
| Lint | `.venv\Scripts\python.exe -m ruff check .` |
| 前端 | `frontend/` 下 install + `npm run build`（或 pnpm） |
| 打包 | 见 README §12 / `packaging/build.ps1` |

公共 API（`docmorph/__init__.py`）：`ApplicationService`、`ConversionEngine`、`make_request`、`Format`、`ConversionRequest/Result/Status`、`ConflictPolicy`、`BatchSummary`、`ConfigManager`、`Settings`、`__version__`。

---

## 8. 转换能力（产品事实）

- **7 个源格式**：pdf / docx / xlsx / md / html / txt / csv → **约 31 条** `(src→dst)` 路由；**pptx 仅作输出**。
- 详细矩阵与实测：**`CONVERSION_MATRIX.md`**（权威）；运行时：`docmorph formats`。
- →PDF 引擎优先级：`word/excel（对应源）→ wps → libreoffice → weasyprint(有GTK) → 明确失败`；可用 `pdf_backend_preference` 手工指定。
- 无 Office 时：非 PDF 目标全部可用；PDF 输出按路由降级或提示安装。

---

## 9. 测试与验收（改完必跑）

```powershell
# 后端
.\.venv\Scripts\python.exe -m pytest -q          # 期望 124 passed（缺 Office 的用例自动 skip）
.\.venv\Scripts\python.exe -m ruff check .

# 冒烟
.\.venv\Scripts\python.exe -m docmorph doctor
.\.venv\Scripts\python.exe -m docmorph formats

# 前端（改了 frontend 才需要）
cd frontend
# npm install / pnpm install
npm run build          # vue-tsc --noEmit && vite build → ../docmorph/ui/webapp
```

测试布局：`tests/unit`（纯逻辑）· `tests/integration`（真实转换，缺环境 skip）· `tests/e2e`（CLI）· `tests/fixtures`（代码生成样本，**不提交二进制**）。

Markers：`needs_office` / `needs_pandoc` / `slow`。  
**禁止**：缺环境的用例改成硬失败；伪造“测试通过”。

---

## 10. 扩展配方（vibe coding 常用任务）

### 10.1 新增一条转换路由

1. 确认步骤能用现有后端完成（或先实现后端）。
2. `registry.ROUTES` 加 `(Format.X, Format.Y): ((("backend", Format.STEP), …),)`；多步用链式 Plan。
3. 若需新外部软件：`capability.py` 检测 + `backends/` 实现 + `errors` 提示。
4. 单测：路由存在、select_plan 在能力缺失时降级正确。
5. 有真实环境则补 integration；更新 `CONVERSION_MATRIX.md`。
6. UI 的 catalog 来自 services，一般**无需改前端**即可出现新项。

### 10.2 新增 CLI 子命令

`cli/main.py` 注册 parser + `cmd_*` → **只调** `ApplicationService` → 补 e2e 测试。

### 10.3 新增 GUI 功能

1. `bridge.Api` 增加方法（返回可 JSON 序列化 dict）。
2. `frontend/src/api.ts` 扩展 `PywebviewApi` + `types.ts`。
3. store/组件接线；浏览器 dev 用 mock 分支可降级提示。
4. 改完必须 `npm run build`。

### 10.4 新增配置项

`settings/schema.py` 默认值与校验 → `config.example.ini` → 如需环境变量确认 `DOCMORPH_*` 映射 → 单测默认值与覆盖优先级。

---

## 11. 已知限制与技术债（勿当 bug 乱修，除非任务就是修它）

| 项 | 说明 |
| --- | --- |
| PDF→PPTX | 每页一张图 + 文本进备注（△），非可编辑版式 |
| PDF→DOCX | 版面近似；复杂排版有偏差 |
| 无 OCR | 扫描件 PDF→TXT 会失败并提示 |
| PDF 输出 | 无 Office/WPS/LO 且无 GTK 时不可用（其余格式不受影响） |
| PPTX 输入 | 不支持（需 PowerPoint 解析） |
| 发行体积 | PyInstaller 约 500MB（numpy/opencv/PyMuPDF 等） |
| 无 CI | 目前仅本机 pytest/ruff |
| `legacy` 子命令 | 保留旧 CLI 参数语法，**实现已走新服务层**，不是旧代码 |

---

## 12. 仓库结构（清理后）

```
docmorph_/
├── run.py                 # 总启动入口（GUI 默认，参数透传 CLI）
├── docmorph/              # Python 包（见 §5）
├── frontend/              # Vue 源码（构建产物在 docmorph/ui/webapp）
├── packaging/             # PyInstaller
├── tests/                 # unit / integration / e2e / fixtures
├── README.md              # 用户与开发者主文档
├── CONVERSION_MATRIX.md   # 转换矩阵（实测权威）
├── PROJECT_CLEANUP_REPORT.md
├── config.example.ini
├── pyproject.toml
├── requirements.txt / requirements-dev.txt
└── .gitignore / .gitattributes
```

**不要**在根目录堆 AI 报告/实验目录；本地用 `.venv`、`frontend/node_modules`（均 gitignore）。

---

## 13. 协作纪律（给后续模型的硬规则）

1. **先读再改**：本文件 + `README.md` + 相关模块 docstring；改路由必读 `registry.py`。
2. **最小 diff**：不顺手重构、不换框架、不升级依赖、不改 API/状态语义 unless 任务明确要求。
3. **双端共用**：业务进 `services`/`engine`，禁止在 `cli/` 或 `ui/` 复制一份转换逻辑。
4. **可选外部软件**：任何 Office/LO 依赖必须可 skip/降级。
5. **契约同步**：改 `bridge.py` 必同步 `api.ts` / `types.ts`。
6. **验证**：至少 `pytest` + `ruff`；动了前端加 `vue-tsc`/`vite build`。
7. **文档同步**：改能力矩阵、配置项、启动方式时更新 `README.md` / `CONVERSION_MATRIX.md` / `config.example.ini`。
8. **不确定就保留**：拿不准的文件/代码不删，先查引用，再记入待确认。

---

## 14. 推荐阅读顺序（新对话 5 分钟上手）

1. 本文件 §2 约束 + §4 架构  
2. `README.md`（功能与命令）  
3. `docmorph/services.py`（门面）→ `engine.py` → `registry.py`  
4. `docmorph/cli/main.py` 或 `ui/bridge.py`（按你要改的端）  
5. `CONVERSION_MATRIX.md`（能力边界）  
6. `tests/` 对应目录（现有测试风格与夹具）

---

*维护约定：架构、入口、版本、测试数量发生实质变化时，更新本文件对应章节。*
