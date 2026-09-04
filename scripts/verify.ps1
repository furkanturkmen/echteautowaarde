# Everything that has to pass before a commit. No network, no services needed.
$ErrorActionPreference = "Stop"

$api = Join-Path $PSScriptRoot "..\apps\api"
$web = Join-Path $PSScriptRoot "..\apps\web"

Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location $api
& ".\.venv\Scripts\ruff.exe" check .
& ".\.venv\Scripts\ruff.exe" format --check .
& ".\.venv\Scripts\python.exe" -m mypy echte_auto_waarde
& ".\.venv\Scripts\python.exe" -m pytest -q

Write-Host "`n== Frontend ==" -ForegroundColor Cyan
Set-Location $web
npm run lint
npx tsc --noEmit
npm run build

Write-Host "`nAll checks passed." -ForegroundColor Green
