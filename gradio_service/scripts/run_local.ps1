param(
    [int]$Port = 8000,
    [ValidateSet("mock", "real")]
    [string]$Mode = "mock"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $ProjectRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Error "Virtual environment not found. Follow README_WINDOWS.md first."
    exit 1
}

$env:APP_MODE = $Mode
$env:APP_HOST = "127.0.0.1"
$env:APP_PORT = "$Port"
$env:PYTHONPATH = "$RepoRoot;$ProjectRoot"

Write-Host "Gradio: http://127.0.0.1:$Port/gradio"
Write-Host "API docs: http://127.0.0.1:$Port/docs"
& $PythonExe -m uvicorn gradio_debug.app:app --host 127.0.0.1 --port $Port --workers 1 --app-dir $ProjectRoot
