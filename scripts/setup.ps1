# Installation complète du monorepo (Windows PowerShell)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "$root\.venv")) {
    python -m venv "$root\.venv"
}
$py = "$root\.venv\Scripts\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install `
    -e "$root\packages\contracts" `
    -e "$root\packages\database" `
    -e "$root\packages\provider-sdk" `
    -e "$root\packages\event-sdk" `
    -e "$root\packages\agent-sdk" `
    -e "$root\apps\api" `
    -e "$root\apps\event-service" `
    -e "$root\apps\worker" `
    -e "$root\services\provider-gateway[test]"

npm install

Write-Host "`nInstallation terminée. Lancez ./scripts/dev.ps1" -ForegroundColor Green
