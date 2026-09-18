# Installation complète du monorepo (Windows PowerShell)
#
# Les versions tierces sont bornées par requirements/constraints.txt, dérivé du verrou
# haché de l'image Python 3.12 (scripts/check_lock.py --write-constraints) : le poste
# local, même en Python 3.13, installe les mêmes versions que l'image de production.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "$root\.venv")) {
    python -m venv "$root\.venv"
}
$py = "$root\.venv\Scripts\python.exe"

& $py -m pip install --upgrade pip setuptools wheel
& $py -m pip install `
    -c "$root\requirements\constraints.txt" `
    -e "$root\packages\contracts" `
    -e "$root\packages\database[postgresql]" `
    -e "$root\packages\provider-sdk" `
    -e "$root\packages\event-sdk" `
    -e "$root\packages\agent-sdk" `
    -e "$root\apps\api" `
    -e "$root\apps\cli" `
    -e "$root\apps\event-service" `
    -e "$root\apps\worker" `
    -e "$root\services\provider-gateway[test]"

& $py "$root\scripts\check_lock.py"
if ($LASTEXITCODE -ne 0) {
    throw "requirements/constraints.txt diverge du verrou : relancez scripts/lock_python.ps1."
}

npm install

Write-Host "`nInstallation terminée. Lancez ./scripts/dev.ps1" -ForegroundColor Green
