#Requires -Version 5.1
<#
.SYNOPSIS
    Bout en bout LOCAL du poste Windows d'ACP contre l'image Hermes locale (cahier P5 § 14.5). Jamais en CI.

.DESCRIPTION
    Monte la pile de test (image ACP_IMAGE_TESTS, faux fournisseur d'identité, faux ntfy, modèle factice, bord TLS
    factice publié sur 127.0.0.1:<Port>) puis lance le VRAI poste (apps/poste) sous VOTRE compte (compte =
    "proprietaire", aucun compte dédié, aucune tâche planifiée, aucun réglage système), sur une racine temporaire, avec
    le vrai Codex sur un CODEX_HOME jetable et vide (liste de secours, aucun compte) et le vrai Claude Code sur un
    CLAUDE_CONFIG_DIR jetable, sans jeton. Détail : apps/poste/tests/e2e/e2e_poste_windows.py.

    Prérequis : Docker Desktop (conteneurs Linux), l'image de test construite, un Python 3.12 python.org avec le
    verrou du dépôt installé (venv), Codex CLI (npm) et Claude Code installés.

.EXAMPLE
    $env:ACP_IMAGE_TESTS = 'acp-hermes-tests:p5o'
    ./scripts/e2e-poste-windows.ps1 -Python .\.venv\Scripts\python.exe -Preuves "$env:TEMP\e2e-poste.json"
#>
[CmdletBinding()]
param(
    [string] $Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'),
    [string] $ImageTests = $env:ACP_IMAGE_TESTS,
    [string] $Codex = (Join-Path $env:APPDATA 'npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe'),
    [string] $Claude = (Join-Path $env:USERPROFILE '.local\bin\claude.exe'),
    [int] $Port = 18443,
    [string] $Preuves = (Join-Path ([IO.Path]::GetTempPath()) 'acp-e2e-poste.json'),
    [switch] $Garder
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
$Racine = Split-Path -Parent $PSScriptRoot

foreach ($exige in @(@{ Chemin = $Python; Nom = 'Python (-Python)' }, @{ Chemin = $Codex; Nom = 'Codex (-Codex)' },
                     @{ Chemin = $Claude; Nom = 'Claude Code (-Claude)' })) {
    if (-not (Test-Path -LiteralPath $exige.Chemin -PathType Leaf)) {
        Write-Host "Refusé : $($exige.Nom) introuvable." -ForegroundColor Red
        exit 2
    }
}
if (-not $ImageTests) {
    Write-Host "Refusé : image de test absente (ACP_IMAGE_TESTS ou -ImageTests)." -ForegroundColor Red
    exit 2
}
& docker image inspect $ImageTests *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Refusé : image $ImageTests introuvable (docker build -f hermes/tests/Dockerfile …)." -ForegroundColor Red
    exit 2
}

$env:PYTHONUTF8 = '1'
$arguments = @((Join-Path $Racine 'apps\poste\tests\e2e\e2e_poste_windows.py'), '--image-tests', $ImageTests,
               '--codex', $Codex, '--claude', $Claude, '--port', $Port, '--preuves', $Preuves)
if ($Garder) { $arguments += '--garder' }
& $Python @arguments
$code = $LASTEXITCODE
Write-Host ''
Write-Host "Rapport : $Preuves (code $code)"
exit $code
