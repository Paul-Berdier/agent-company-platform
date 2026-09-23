<#
.SYNOPSIS
Installe Hermes épinglé dans le projet, sans modèle ni compte configuré.
.DESCRIPTION
Requiert Git, uv et Python 3.11 à 3.13. Aucun service ou appel de modèle
n'est lancé. Le code tiers, le profil et les notes restent sous acp-data/.
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repoRoot 'acp-data/tools/hermes-v2026.9.7'
$profileRoot = Join-Path $repoRoot 'acp-data/hermes-profile'
$vaultRoot = Join-Path $repoRoot 'acp-data/obsidian'
$expectedCommit = '2237be355906fbe6065ce1815711eee52b2d646e'
$expectedVersion = '0.21.1'
$gitExe = (Get-Command git -ErrorAction Stop).Source
$uvExe = (Get-Command uv -ErrorAction Stop).Source
$pythonExe = (Get-Command $Python -ErrorAction Stop).Source
& $pythonExe -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "Python 3.11 a 3.13 requis"; assert "WindowsApps" not in sys.base_prefix, "Utiliser Python hors Microsoft Store"'
if ($LASTEXITCODE -ne 0) { throw 'Python incompatible.' }

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    if ($CheckOnly) { throw 'Hermes non installé. Exécuter sans -CheckOnly.' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sourceRoot) | Out-Null
    & $gitExe -c core.longpaths=true clone --depth 1 --branch v2026.9.7 https://github.com/NousResearch/hermes-agent.git $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw 'Le téléchargement Hermes a échoué ; aucun profil modifié.' }
}
$head = & $gitExe -c "safe.directory=$sourceRoot" -c core.longpaths=true -C $sourceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head.Trim() -ne $expectedCommit) {
    throw 'Le dossier Hermes ne correspond pas au commit validé ; remplacement automatique refusé.'
}
$changes = & $gitExe -c "safe.directory=$sourceRoot" -c core.longpaths=true -C $sourceRoot status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Sources Hermes modifiées ; installation automatique refusée.' }

if (-not $CheckOnly) {
    Push-Location $sourceRoot
    try {
        # L'API Runs de cette version importe aiohttp depuis l'extra messaging.
        & $uvExe sync --locked --no-dev --extra mcp --extra messaging --python $pythonExe
        if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances Hermes interrompue.' }
    } finally { Pop-Location }
    New-Item -ItemType Directory -Force -Path $profileRoot, $vaultRoot | Out-Null
    $notePath = Join-Path $vaultRoot 'Accueil.md'
    if (-not (Test-Path -LiteralPath $notePath)) {
        @'
# Notes ACP

Ce dossier est un coffre Markdown local, ouvrable comme coffre dans Obsidian.
Hermes peut y accéder avec sa compétence Obsidian et ses outils de fichiers,
après configuration et autorisation. Aucun compte ni synchronisation n'est requis.

Les notes ne remplacent pas les preuves, budgets ou décisions persistés dans ACP.
'@ | Set-Content -LiteralPath $notePath -Encoding utf8
    }
}
$hermesPython = Join-Path $sourceRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $hermesPython)) { throw 'Environnement Hermes absent.' }
$installed = & $hermesPython -c 'from importlib.metadata import version; print(version("hermes-agent"))'
if ($LASTEXITCODE -ne 0 -or $installed.Trim() -ne $expectedVersion) { throw 'Version Hermes installée incompatible.' }
Write-Output "Hermes $expectedVersion installé et sources vérifiées ($expectedCommit)."
Write-Output "Profil isolé : $profileRoot"
Write-Output "Coffre de notes : $vaultRoot"
Write-Output 'Modèle/authentification : à configurer avec ./scripts/hermes-local.ps1 -Action setup.'
Write-Output 'Aucun Run Hermes ni appel de modèle exécuté.'
