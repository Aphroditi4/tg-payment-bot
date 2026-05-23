if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Host "Virtual environment not found. Run:"
    Write-Host "python -m venv .venv"
    Write-Host ".\.venv\Scripts\Activate.ps1"
    Write-Host "pip install -r requirements.txt"
    exit 1
}

.\.venv\Scripts\python.exe -m app.main
