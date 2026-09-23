# 用 PyInstaller 构建 Windows 发行版（onedir，启动快、对 Office COM 与 WebView2 友好）。
#
# 用法（在项目根目录执行）：
#   .\.venv\Scripts\python.exe -m pip install pyinstaller
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# 产物：dist\DocMorph\（绿色目录）与 dist\DocMorphCLI\（命令行版）

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$common = @(
    "--noconfirm", "--clean", "--onedir",
    # 注意：--specpath 会让相对的 --add-data 源路径按 spec 目录解析，因此这里必须用绝对路径
    "--add-data", "$root\docmorph\ui\webapp;docmorph/ui/webapp",
    "--add-data", "$root\docmorph\resources;docmorph/resources",
    "--add-data", "$root\.venv\Lib\site-packages\pypandoc\files;pypandoc/files",
    "--collect-all", "pymupdf",
    "--collect-all", "pdf2docx",
    "--collect-all", "webview",
    "--hidden-import", "win32com.client",
    "--hidden-import", "pythoncom",
    # 与运行时无关的重型模块，排除以缩小发行体积
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
    "--exclude-module", "pytest",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "build"
)

Write-Host "== 构建 GUI 版 ==" -ForegroundColor Cyan
& $python -m PyInstaller @common --windowed --name DocMorph --icon "$root\docmorph\resources\icon.ico" packaging/DocMorph.py

Write-Host "== 构建 CLI 版 ==" -ForegroundColor Cyan
& $python -m PyInstaller @common --console --name DocMorphCLI packaging/DocMorphCLI.py

Write-Host "完成：dist\DocMorph\DocMorph.exe 与 dist\DocMorphCLI\DocMorphCLI.exe" -ForegroundColor Green
