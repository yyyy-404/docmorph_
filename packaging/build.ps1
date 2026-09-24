# Build Windows distribution with PyInstaller (onedir).
#
# Usage (from project root, clean venv recommended):
#   python -m venv .venv-build
#   .\.venv-build\Scripts\activate
#   pip install -r requirements-full.txt
#   pip install pyinstaller
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# Optional: -PythonPath <path\to\python.exe>
# Default probe order: .venv-build, .venv, then PATH python.
#
# Output: dist\DocMorph\ and dist\DocMorphCLI\

param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $PythonPath) {
    foreach ($candidate in @(".venv-build\Scripts\python.exe", ".venv\Scripts\python.exe")) {
        $full = Join-Path $root $candidate
        if (Test-Path $full) { $PythonPath = $full; break }
    }
}
if (-not $PythonPath) { $PythonPath = "python" }

Write-Host "Python: $PythonPath" -ForegroundColor Cyan

$pypandocFiles = & $PythonPath -c "import pypandoc, pathlib; print(pathlib.Path(pypandoc.__file__).resolve().parent / 'files')"
if ($LASTEXITCODE -ne 0 -or -not $pypandocFiles -or -not (Test-Path $pypandocFiles)) {
    throw "Cannot locate pypandoc/files (pip install -r requirements-full.txt first)"
}

$common = @(
    "--noconfirm", "--clean", "--onedir",
    # --specpath makes relative --add-data sources resolve against spec dir; use absolute paths
    "--add-data", "$root\docmorph\ui\webapp;docmorph/ui/webapp",
    "--add-data", "$root\docmorph\resources;docmorph/resources",
    "--add-data", "$pypandocFiles;pypandoc/files",
    "--collect-all", "pymupdf",
    "--collect-all", "pdf2docx",
    "--collect-all", "webview",
    "--hidden-import", "win32com.client",
    "--hidden-import", "pythoncom",
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
    "--exclude-module", "pytest",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "build"
)

Write-Host "== Build GUI ==" -ForegroundColor Cyan
& $PythonPath -m PyInstaller @common --windowed --name DocMorph --icon "$root\docmorph\resources\icon.ico" packaging/DocMorph.py
if ($LASTEXITCODE -ne 0) { throw "GUI build failed" }

Write-Host "== Build CLI ==" -ForegroundColor Cyan
& $PythonPath -m PyInstaller @common --console --name DocMorphCLI packaging/DocMorphCLI.py
if ($LASTEXITCODE -ne 0) { throw "CLI build failed" }

$gui = Join-Path $root "dist\DocMorph\DocMorph.exe"
$cli = Join-Path $root "dist\DocMorphCLI\DocMorphCLI.exe"
if (-not (Test-Path $gui)) { throw "Missing $gui" }
if (-not (Test-Path $cli)) { throw "Missing $cli" }
Write-Host "Done: dist\DocMorph\DocMorph.exe and dist\DocMorphCLI\DocMorphCLI.exe" -ForegroundColor Green
