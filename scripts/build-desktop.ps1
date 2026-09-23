#Requires -Version 5.1

<#
.SYNOPSIS
    Configure et compile le client desktop Windows avec le préréglage CMake MSVC.

.DESCRIPTION
    Refuse explicitement, plutôt que de deviner, quand Qt, MSVC, CMake ou les
    sources du client sont absents. N'installe rien et ne modifie aucun réglage
    durable du poste : l'environnement MSVC n'est chargé que dans la session de
    ce script.

    Codes de sortie :
      0  compilation réussie
      1  erreur inattendue
      2  prérequis manquant (Qt, MSVC ou CMake)
      3  contrat absent (apps/desktop, préréglage ou répertoire de compilation)
      4  échec de configuration ou de compilation

.PARAMETER Configuration
    Debug ou Release. Détermine le préréglage lu dans packaging/windows/toolchain.json.

.PARAMETER QtDir
    Chemin explicite d'une installation Qt (répertoire contenant bin\windeployqt.exe).

.PARAMETER Clean
    Supprime le répertoire de compilation avant de configurer.

.EXAMPLE
    ./scripts/build-desktop.ps1 -Configuration Release -QtDir "C:\Qt\6.8.3\msvc2022_64"
#>

[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Debug',
    [string] $QtDir,
    [switch] $Clean
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

    Write-AcpEtape "Compilation du client desktop — $Configuration (préréglage $preset)"

    # --- Contrat : les sources et les préréglages doivent exister ------------------
    $script:CodeCourant = $codes.ContratAbsent
    $fichierPresets = Join-Path $sources 'CMakePresets.json'
    if (-not (Test-Path -LiteralPath $fichierPresets)) {
        Write-AcpRefus `
            -Message "Les sources du client desktop sont absentes : $fichierPresets n'existe pas." `
            -Details @(
                "Ce répertoire est produit par le lot fondation desktop, pas par cette chaîne d'outils.",
                "Tant qu'il n'est pas fusionné, rien ne peut être compilé, et rien ne doit prétendre l'avoir été."
            )
        exit $script:CodeCourant
    }

    # --- Prérequis ----------------------------------------------------------------
    $script:CodeCourant = $codes.PrerequisManquant
    $qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $toolchain
    if (-not $qt) {
        Write-AcpRefus `
            -Message "Aucune installation Qt $($toolchain.qt.version) utilisable n'a été trouvée." `
            -Details @(
                "Chemins examinés : -QtDir, ACP_QT_DIR, QT_ROOT_DIR, Qt6_DIR, C:\Qt\$($toolchain.qt.version)\*.",
                "Un répertoire Qt est réputé valide s'il contient bin\windeployqt.exe.",
                "Inventaire détaillé : ./scripts/setup-desktop.ps1"
            )
        exit $script:CodeCourant
    }
    Write-Host "Qt : $qt"

    if (-not (Get-Command -Name 'cmake' -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-AcpRefus `
            -Message "CMake est introuvable dans le PATH." `
            -Details @("À lancer vous-même : winget install --id Kitware.CMake")
        exit $script:CodeCourant
    }

    if (-not (Enter-AcpMsvcEnvironment)) {
        Write-AcpRefus `
            -Message "L'environnement de compilation MSVC x64 n'a pas pu être chargé." `
            -Details @(
                "Visual Studio 2022 avec la charge « Développement Desktop en C++ » (composant Microsoft.VisualStudio.Component.VC.Tools.x86.x64) est requis.",
                "Inventaire détaillé : ./scripts/setup-desktop.ps1"
            )
        exit $script:CodeCourant
    }
    Write-Host "MSVC : $((Get-Command cl.exe -CommandType Application | Select-Object -First 1).Source)"

    # Qt est exposé à CMake par CMAKE_PREFIX_PATH, et ses DLL au PATH de cette session
    # seulement : aucun réglage durable du poste n'est touché.
    $env:CMAKE_PREFIX_PATH = $qt
    $env:PATH = "$(Join-Path $qt 'bin');$env:PATH"

    # --- Configuration ------------------------------------------------------------
    $repertoireCompilation = Get-AcpBuildDirectory -Preset $preset -Toolchain $toolchain
    if ($Clean -and (Test-Path -LiteralPath $repertoireCompilation)) {
        Write-Host "Suppression de $repertoireCompilation"
        Remove-Item -LiteralPath $repertoireCompilation -Recurse -Force
    }

    $script:CodeCourant = $codes.CompilationEchouee
    Write-AcpEtape "Configuration CMake"
    Invoke-AcpProcess -FilePath 'cmake' -Arguments @('--preset', $preset) `
        -WorkingDirectory $sources `
        -Message "La configuration CMake avec le préréglage « $preset » a échoué"

    # --- Contrat : emplacement du répertoire de compilation ------------------------
    $script:CodeCourant = $codes.ContratAbsent
    if (-not (Test-Path -LiteralPath (Join-Path $repertoireCompilation 'CMakeCache.txt'))) {
        Write-AcpRefus `
            -Message "CMake a configuré ailleurs que là où cette chaîne d'outils l'attend." `
            -Details @(
                "Attendu : $repertoireCompilation\CMakeCache.txt",
                "Le préréglage « $preset » doit poser binaryDir à `${sourceDir}/build/`${presetName}.",
                "Contrat documenté dans packaging/windows/toolchain.json et docs/desktop-build.md."
            )
        exit $script:CodeCourant
    }

    # --- Compilation --------------------------------------------------------------
    $script:CodeCourant = $codes.CompilationEchouee
    Write-AcpEtape "Compilation"
    Invoke-AcpProcess -FilePath 'cmake' -Arguments @('--build', '--preset', $preset) `
        -WorkingDirectory $sources `
        -Message "La compilation avec le préréglage « $preset » a échoué"

    Write-Host ''
    Write-Host "Compilation terminée. Binaires sous $repertoireCompilation" -ForegroundColor Green
    exit $codes.Succes
}
catch {
    Write-AcpRefus -Message $_.Exception.Message
    exit $script:CodeCourant
}
