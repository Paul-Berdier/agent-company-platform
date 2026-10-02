#Requires -Version 5.1
<#
.SYNOPSIS
    Bout en bout LOCAL de la station Qt (apps/desktop) contre la pile de test (cahier P8 § 10). Jamais en CI.

.DESCRIPTION
    Monte la pile de test (vrai Authelia, Hermes de test avec le modèle factice, bord TLS factice publié sur
    127.0.0.1), puis pilote la VRAIE station (exécutable de test acp_desktop_e2e, jamais installé) : connexion
    native RFC 8252 par Chromium (passkey virtuelle), rotation du jeton, discussion JSON-RPC, projet lancé,
    question posée par le poste simulé et RÉPONDUE depuis la station, veille du kanban, sauvegarde chiffrée,
    reprise de session au redémarrage, déconnexion, hygiène (préférences, coffre, journaux).

    Le coffre et la portée de préférences sont DE TEST (AcpDesktopE2E-<uuid>, « ACP E2E <uuid> ») et supprimés à
    la fin ; la station ne joint la pile que par un mandataire CONNECT local qui refuse tout autre nom.
    Détail : apps/desktop/tests/e2e/e2e_desktop_windows.py.

    Prérequis : Docker Desktop (conteneurs Linux), les images de test et d'identité construites depuis ce dépôt,
    la station compilée en Release (scripts/build-desktop.ps1), un Python 3.12 python.org avec le verrou
    hermes/tests/requirements-e2e.txt installé et Chromium de Playwright (python -m playwright install chromium).

    Codes de sortie : 0 parcours réussi ; 1 écart constaté (voir le rapport) ; 2 prérequis manquant.

.EXAMPLE
    ./scripts/e2e-desktop-windows.ps1 -Python .\.venv-e2e\Scripts\python.exe `
        -ImageTests acp-hermes-tests:p8 -ImageIdentite acp-identite:p8 -Preuves "$env:TEMP\e2e-desktop.json"
#>
[CmdletBinding()]
param(
    [string] $Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'),
    [string] $ImageTests = $env:ACP_IMAGE_TESTS,
    [string] $ImageIdentite = $env:ACP_IMAGE_IDENTITE,
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',
    [string] $QtDir,
    [string] $Preuves = (Join-Path ([IO.Path]::GetTempPath()) 'acp-e2e-desktop.json'),
    [string] $Captures = (Join-Path ([IO.Path]::GetTempPath()) 'acp-e2e-desktop-captures'),
    [switch] $Garder
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
$Racine = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $Racine 'packaging\windows\DesktopToolchain.psm1') -Force

function Refuser([string] $Message) {
    Write-Host "Refusé : $Message" -ForegroundColor Red
    exit 2
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { Refuser "Python introuvable (-Python)." }
foreach ($image in @(@{ Nom = 'ImageTests'; Valeur = $ImageTests }, @{ Nom = 'ImageIdentite'; Valeur = $ImageIdentite })) {
    if (-not $image.Valeur) { Refuser "image absente (-$($image.Nom))." }
    & docker image inspect $image.Valeur *> $null
    if ($LASTEXITCODE -ne 0) { Refuser "image $($image.Valeur) introuvable (voir docs/refonte/image.md)." }
}

$toolchain = Get-AcpToolchain
$preset = Get-AcpPresetName -Configuration $Configuration -Toolchain $toolchain
$repertoire = Get-AcpBuildDirectory -Preset $preset -Toolchain $toolchain
$executable = Join-Path $repertoire 'acp_desktop_e2e.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    Refuser "pilote $executable introuvable : compilez d'abord (scripts/build-desktop.ps1 -Configuration $Configuration)."
}
$qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $toolchain
if (-not $qt) { Refuser "Qt introuvable (-QtDir ou ACP_QT_DIR)." }
$qtBin = Join-Path $qt 'bin'

& $Python -c "import playwright" 2>$null
if ($LASTEXITCODE -ne 0) { Refuser "Playwright absent de $Python (pip install --require-hashes -r hermes/tests/requirements-e2e.txt)." }

$env:PYTHONUTF8 = '1'
$arguments = @((Join-Path $Racine 'apps\desktop\tests\e2e\e2e_desktop_windows.py'),
               '--image-tests', $ImageTests, '--image-identite', $ImageIdentite,
               '--executable', $executable, '--qt-bin', $qtBin, '--preuves', $Preuves, '--captures', $Captures)
if ($Garder) { $arguments += '--garder' }
& $Python @arguments
$code = $LASTEXITCODE
Write-Host ''
Write-Host "Rapport : $Preuves ; captures : $Captures (code $code)"
exit $code
