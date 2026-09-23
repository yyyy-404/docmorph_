# 项目清理报告

## 1. 清理目标

在不改变 DocMorph 现有功能、业务逻辑、API、数据与界面行为的前提下，删除项目中已无实际价值的 AI 过程文档、历史报告、临时实验文件、构建缓存、废弃旧实现及其回归用例，使仓库只保留运行、构建、部署、测试与维护所需内容。

## 2. 删除内容

### AI / 历史文档

| 文件 | 原因 |
| --- | --- |
| `AI_PROJECT_REPORT.md` | AI 交接用项目分析报告，内容已过时（描述旧版 PySide6 架构） |
| `PROJECT_ANALYSIS.md` | 第一阶段摸底报告，描述的根目录旧文件已删除 |
| `PHASE2_REPORT.md` | 第二阶段变更记录，属 AI 工作过程文档 |
| `CURRENT_ARCHITECTURE.md` | 过时架构分析，与当前 pywebview + Vue 3 实现不符 |
| `REFACTOR_PLAN.md` | 已完成的重构方案，属阶段性过程文档 |

### 临时文件 / 实验产物 / 缓存

| 路径 | 原因 |
| --- | --- |
| `.lab/` | 本地实验工作区：探测脚本、smoke 转换产物、截图、实验日志 |
| `.idea/` | IDE 本地配置（已在 `.gitignore`，不应作为源码保留） |
| `build/`、`dist/`、`docmorph.egg-info/` | 构建产物（已在 `.gitignore`） |
| `.pytest_cache/`、`.ruff_cache/`、`__pycache__/` | 测试与 lint 缓存 |
| `preparatory.md` | 临时配色笔记（仅 1 行外部链接；调色板已固化在 `frontend/src/styles/theme.css`） |

### 废弃代码（旧实现，新架构测试全绿后删除）

新架构（`engine` / `backends` / `services` / `settings` / `ui` / `cli`）在删除前已通过 **174 passed** 基线验证；`REFACTOR_PLAN.md` 与 `README.md` 均标注旧实现「确认无用后可删除」。引用关系已逐文件核实：

| 删除项 | 说明 |
| --- | --- |
| `docmorph/converter.py` | 旧转换核心，已被 `engine.py` + `backends/` 取代 |
| `docmorph/logger.py` | 旧日志，已被 `logging_setup.py` 取代 |
| `docmorph/config.py` | 旧配置，已被 `settings/` 取代 |
| `docmorph/resources.py` | 旧资源加载（仅旧 GUI 使用） |
| `docmorph/_legacy_cli.py` | 旧 CLI，已被 `cli/main.py` 取代 |
| `docmorph/gui/` | 旧 PySide6 GUI，已被 `ui/` + `frontend/` 取代 |
| `docmorph/resources/style.css` | 旧 QSS，仅旧 GUI 使用；`icon.ico` 保留（打包仍引用） |
| `tests/test_converter.py`、`test_logger.py`、`test_config.py`、`test_cli.py`、`test_gui_smoke.py`、`test_utils.py` | 旧实现回归用例 |
| `tests/conftest.py` 中 `config` / `converter` fixtures | 仅供旧用例使用 |
| `docmorph/utils.py` 中 `make_output_path` | 仅旧 GUI 调用；新逻辑在 `services.make_output_path`。`ensure_console_encoding` 仍被 CLI/UI 使用，已保留 |

### 其他

- 前端组件均已核对 import / 使用关系，**无未引用组件，未删除任何前端文件**。
- 无 CI 配置（`.github/`）可删；`.gitattributes`、`config.example.ini`、依赖与锁文件均保留。

## 3. 保留的重要文档

| 文件 | 保留原因 |
| --- | --- |
| `README.md` | 正式使用说明：安装、配置、数据库/配置初始化、启动、构建、打包、测试、能力检测、已知限制 |
| `CONVERSION_MATRIX.md` | 正式技术文档：31 条转换路由的实测矩阵与后端说明，README 直接引用 |
| `config.example.ini` | 配置字段模板，运行/排障必需 |
| `requirements.txt` / `requirements-dev.txt` / `pyproject.toml` | 依赖与打包、pytest/ruff 配置 |
| `.gitignore` / `.gitattributes` | 仓库与文本处理配置 |

## 4. 代码修改

仅包含删除冗余内容所必需的最小修改：

- `tests/conftest.py`：移除仅服务旧用例的 `config` / `converter` fixtures 及注释。
- `docmorph/utils.py`：移除无调用方的 `make_output_path`，保留 `ensure_console_encoding`。
- `pyproject.toml`：移除 ruff exclude 中的旧实现条目与失效注释。
- `frontend/src/styles/theme.css`：注释中去掉已删除的 `preparatory.md` 文件名引用（色值不变）。
- `README.md`：移除「仍保留旧版实现」的过时说明；测试数量 174 → 124。

**未修改业务逻辑。**

## 5. 验证结果

以下均为本次清理后**实际执行**的命令结果：

| 项目 | 结果 |
| --- | --- |
| 依赖解析 | `pip install -r requirements-dev.txt --dry-run` 成功（无冲突） |
| 后端 import | `import docmorph` 及 `cli` / `ui` / `engine` / `services` / `backends` / `settings` / `capability` 正常 |
| CLI 启动 | `python -m docmorph --help`、`formats`、`doctor` 正常 |
| GUI 资源 | `assets_available()` 为 True（`docmorph/ui/webapp` 构建产物存在） |
| 测试 | `python -m pytest -q` → **124 passed**（清理前基线 174 passed，差值为已删除的旧实现用例） |
| 静态检查 | `ruff check .` → All checks passed |
| 前端类型检查 | `vue-tsc --noEmit` → 通过 |
| 前端构建 | `vite build` → 成功，产物写入 `docmorph/ui/webapp/`（hash 与清理前一致） |
| 打包脚本 | `packaging/build.ps1` 仍引用存在的 `docmorph/resources/icon.ico` 与 `ui/webapp`，未改 |

未执行：PyInstaller 完整打包（耗时且依赖本机 Office 环境，与本次文件清理无直接关系）；无伪造结果。

## 6. 待确认文件

- `.venv/` — 本地 Python 虚拟环境，已被 `.gitignore` 忽略，**不作为项目源码**；可由 `requirements.txt` / `requirements-dev.txt` 重建。本次验证在其中完成，故保留在磁盘上，未纳入仓库。
- `frontend/node_modules/` — 前端本地依赖，已被 `.gitignore` 忽略，保留供本地构建。

除此之外：无。

## 7. 清理后根目录结构（项目本体）

```
docmorph_/
├── docmorph/            # Python 包（engine/backends/services/settings/ui/cli）
├── frontend/            # Vue 3 界面源码
├── packaging/           # PyInstaller 入口与构建脚本
├── tests/               # unit / integration / e2e
├── README.md            # 正式使用文档
├── CONVERSION_MATRIX.md # 转换能力实测矩阵
├── config.example.ini
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── .gitattributes
```
