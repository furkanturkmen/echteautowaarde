# One-time local setup: virtual environment, dependencies, database, demo data.
# Nothing here reaches the network except the package installs.
$ErrorActionPreference = "Stop"

$api = Join-Path $PSScriptRoot "..\apps\api"
$web = Join-Path $PSScriptRoot "..\apps\web"

Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location $api
if (-not (Test-Path ".\.venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install --quiet -e ".[dev]"
& ".\.venv\Scripts\alembic.exe" upgrade head
& ".\.venv\Scripts\python.exe" -m echte_auto_waarde.seed --reset

Write-Host "`n== Frontend ==" -ForegroundColor Cyan
Set-Location $web
npm install

Write-Host "`nReady. Start the API with scripts\dev-api.ps1 and the site with scripts\dev-web.ps1." -ForegroundColor Green
Write-Host "The market data is synthetic and unsuitable for real purchase decisions." -ForegroundColor Yellow
