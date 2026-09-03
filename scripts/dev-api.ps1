# Start the Echte Auto Waarde API locally (Windows PowerShell).
$ErrorActionPreference = "Stop"
$api = Join-Path $PSScriptRoot "..\apps\api"
Set-Location $api
& ".\.venv\Scripts\python.exe" -m uvicorn echte_auto_waarde.main:app --reload --port 8000
