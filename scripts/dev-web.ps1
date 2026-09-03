# Start the Echte Auto Waarde frontend locally (Windows PowerShell).
$ErrorActionPreference = "Stop"
$web = Join-Path $PSScriptRoot "..\apps\web"
Set-Location $web
npm run dev
