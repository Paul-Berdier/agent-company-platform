#Requires -Version 5.1

<#
.SYNOPSIS
    Exécute les tests natifs (Qt Test) et QML (Qt Quick Test) du client desktop.

.DESCRIPTION
    Délègue à CTest, qui est le point d'entrée déclaré par le préréglage de test
    du client. Un test en échec fait échouer ce script : aucun résultat n'est
    ignoré, aucun échec n'est converti en avertissement.

    Codes de sortie :
      0  tous les tests sont passés
      1  erreur inattendue
      2  prérequis manquant (Qt ou CTest)
      3  contrat absent (sources, préréglage, ou répertoire de compilation)
      5  au moins un test a échoué

.PARAMETER Configuration
    Debug ou Release. Détermine le préréglage lu dans packaging/windows/toolchain.json.

.PARAMETER QtDir
    Chemin explicite d'une installation Qt (répertoire contenant bin\windeployqt.exe).

.PARAMETER Filter
    Expression régulière passée à ctest -R pour ne lancer qu'une partie des tests.

.EXAMPLE
    ./scripts/test-desktop.ps1 -Configuration Release
#>

[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Debug',
    [string] $QtDir,
    [string] $Filter
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\packaging\windows\DesktopToolchain.psm1') -Force
$codes = Get-AcpExitCodes
$script:CodeCourant = $codes.ErreurInattendue

try {
    $toolchain = Get-AcpToolchain
    $racine = Get-AcpRepositoryRoot
    $preset = Get-AcpPresetName -Configuration $Configuration -Toolchain $toolchain
    $sources = Join-Path $racine ($toolchain.cmake.sourceDirectory -replace '/', '\')
    $repertoireCompilation = Get-AcpBuildDirectory -Preset $preset -Toolchain $toolchain

    Write-AcpEtape "Tests du client desktop — $Configuration (préréglage $preset)"

    $script:CodeCourant = $codes.ContratAbsent
    if (-not (Test-Path -LiteralPath (Join-Path $repertoireCompilation 'CMakeCache.txt'))) {
        Write-AcpRefus `
            -Message "Rien n'a été compilé pour la configuration $Configuration." `
            -Details @(
                "Attendu : $repertoireCompilation\CMakeCache.txt",
                "Lancez d'abord ./scripts/build-desktop.ps1 -Configuration $Configuration"
            )
        exit $script:CodeCourant
    }

    $script:CodeCourant = $codes.PrerequisManquant
    if (-not (Get-Command -Name 'ctest' -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-AcpRefus `
            -Message "CTest est introuvable dans le PATH." `
            -Details @("CTest est livré avec CMake : winget install --id Kitware.CMake")
        exit $script:CodeCourant
    }

    $qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $toolchain
    if (-not $qt) {
        Write-AcpRefus `
            -Message "Aucune installation Qt $($toolchain.qt.version) utilisable n'a été trouvée." `
            -Details @("Les binaires de test ont besoin des DLL Qt au moment de l'exécution.", "Inventaire : ./scripts/setup-desktop.ps1")
        exit $script:CodeCourant
    }
    $env:PATH = "$(Join-Path $qt 'bin');$env:PATH"

    $arguments = @('--preset', $preset, '--output-on-failure')
    if (-not [string]::IsNullOrWhiteSpace($Filter)) {
        $arguments += @('-R', $Filter)
    }

    $script:CodeCourant = $codes.TestsEchoues
    Invoke-AcpProcess -FilePath 'ctest' -Arguments $arguments `
        -WorkingDirectory $sources `
        -Message "Des tests du client desktop ont échoué"

    Write-Host ''
    Write-Host 'Tous les tests sont passés.' -ForegroundColor Green
    exit $codes.Succes
}
catch {
    Write-AcpRefus -Message $_.Exception.Message
    exit $script:CodeCourant
}
