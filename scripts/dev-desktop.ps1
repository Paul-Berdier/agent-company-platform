#Requires -Version 5.1

<#
.SYNOPSIS
    Boucle de développement du client desktop : compile, puis lance l'application.

.DESCRIPTION
    Enchaîne scripts/build-desktop.ps1 puis l'exécution du binaire produit, avec
    les DLL Qt exposées au seul processus lancé. Ne déploie rien, n'installe rien
    et ne touche à aucun réglage durable du poste.

    L'URL du serveur n'est jamais codée ici : elle se saisit dans l'application.
    -ServerUrl ne fait que pré-renseigner la variable d'environnement ACP_API_URL
    pour cette exécution, si le client la lit.

    Codes de sortie :
      0  l'application s'est terminée normalement
      1  erreur inattendue
      2  prérequis manquant
      3  contrat absent (sources ou binaire attendu introuvable)
      4  échec de compilation
      autre : code de sortie de l'application elle-même

.PARAMETER Configuration
    Debug (par défaut) ou Release.

.PARAMETER QtDir
    Chemin explicite d'une installation Qt.

.PARAMETER SkipBuild
    Lance le binaire déjà compilé sans recompiler.

.PARAMETER ServerUrl
    URL du serveur à proposer à l'application pour cette exécution (ACP_API_URL).

.EXAMPLE
    ./scripts/dev-desktop.ps1

.EXAMPLE
    ./scripts/dev-desktop.ps1 -SkipBuild -ServerUrl "https://exemple.up.railway.app"
#>

[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Debug',
    [string] $QtDir,
    [switch] $SkipBuild,
    [string] $ServerUrl
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\packaging\windows\DesktopToolchain.psm1') -Force
$codes = Get-AcpExitCodes
$script:CodeCourant = $codes.ErreurInattendue

try {
    $toolchain = Get-AcpToolchain
    $preset = Get-AcpPresetName -Configuration $Configuration -Toolchain $toolchain
    $repertoireCompilation = Get-AcpBuildDirectory -Preset $preset -Toolchain $toolchain

    if (-not $SkipBuild) {
        $script:CodeCourant = $codes.CompilationEchouee
        # Table de hachage et non tableau : un tableau serait transmis en arguments
        # positionnels, et « -Configuration » deviendrait la valeur du paramètre.
        $parametres = @{ Configuration = $Configuration }
        if (-not [string]::IsNullOrWhiteSpace($QtDir)) { $parametres['QtDir'] = $QtDir }
        & (Join-Path $PSScriptRoot 'build-desktop.ps1') @parametres
        if ($LASTEXITCODE -ne 0) {
            Write-AcpRefus -Message "La compilation a échoué : l'application ne sera pas lancée."
            exit $LASTEXITCODE
        }
    }

    Write-AcpEtape "Lancement du client desktop — $Configuration"

    $script:CodeCourant = $codes.ContratAbsent
    $nomExecutable = $toolchain.product.executable
    $candidats = @()
    if (Test-Path -LiteralPath $repertoireCompilation) {
        $candidats = @(Get-ChildItem -LiteralPath $repertoireCompilation -Recurse -File -Filter $nomExecutable -ErrorAction SilentlyContinue)
    }
    if ($candidats.Count -eq 0) {
        Write-AcpRefus `
            -Message "Le binaire $nomExecutable est introuvable sous $repertoireCompilation." `
            -Details @(
                "Le préréglage « $preset » doit produire un exécutable nommé exactement $nomExecutable.",
                "Ce nom est fixé dans packaging/windows/toolchain.json et repris par l'installeur."
            )
        exit $script:CodeCourant
    }
    $executable = ($candidats | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

    $script:CodeCourant = $codes.PrerequisManquant
    $qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $toolchain
    if (-not $qt) {
        Write-AcpRefus `
            -Message "Aucune installation Qt $($toolchain.qt.version) utilisable n'a été trouvée." `
            -Details @("L'application a besoin des DLL Qt au moment de l'exécution.", "Inventaire : ./scripts/setup-desktop.ps1")
        exit $script:CodeCourant
    }
    $env:PATH = "$(Join-Path $qt 'bin');$env:PATH"

    if (-not [string]::IsNullOrWhiteSpace($ServerUrl)) {
        if ($ServerUrl -notmatch '^https://') {
            Write-Host "Attention : $ServerUrl n'est pas en HTTPS. Le client peut refuser cette URL." -ForegroundColor Yellow
        }
        $env:ACP_API_URL = $ServerUrl
        Write-Host "ACP_API_URL = $ServerUrl (pour cette exécution seulement)"
    }

    Write-Host "Exécutable : $executable"
    & $executable
    exit $LASTEXITCODE
}
catch {
    Write-AcpRefus -Message $_.Exception.Message
    exit $script:CodeCourant
}
