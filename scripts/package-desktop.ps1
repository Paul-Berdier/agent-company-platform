#Requires -Version 5.1

<#
.SYNOPSIS
    Déploie les dépendances Qt, fabrique l'installeur, l'archive portable et les
    sommes de contrôle SHA-256 du client desktop Windows.

.DESCRIPTION
    Chaîne complète, dans cet ordre :
      1. localisation du binaire compilé ;
      2. mise en scène dans un répertoire propre ;
      3. windeployqt, avec analyse explicite du répertoire QML source ;
      4. signature de l'exécutable, uniquement si un certificat est fourni ;
      5. archive portable .zip ;
      6. programme d'installation Inno Setup ;
      7. signature du programme d'installation, aux mêmes conditions ;
      8. SHA256SUMS.txt.

    Artefacts produits, avec exactement ces noms :
      AgentCompanyPlatform-Setup-<version>-x64.exe
      AgentCompanyPlatform-Portable-<version>-x64.zip
      SHA256SUMS.txt

    Aucune signature n'est simulée. Si aucun certificat n'est fourni, le script
    l'écrit noir sur blanc et les binaires restent NON SIGNÉS.

    Codes de sortie :
      0  empaquetage réussi
      1  erreur inattendue
      2  prérequis manquant (Qt, windeployqt, Inno Setup)
      3  contrat absent (binaire compilé ou répertoire QML introuvable)
      6  échec d'empaquetage
      7  échec de signature

.PARAMETER Configuration
    Debug ou Release. Release par défaut : c'est la seule configuration distribuable.

.PARAMETER QtDir
    Chemin explicite d'une installation Qt (répertoire contenant bin\windeployqt.exe).

.PARAMETER Version
    Version à graver dans les artefacts. Par défaut, le contenu du fichier VERSION.

.PARAMETER OutputDir
    Répertoire de sortie. Par défaut, dist/desktop à la racine du dépôt.

.PARAMETER DryRun
    Empaquetage à blanc : produit réellement les artefacts pour prouver que la
    chaîne fonctionne, mais ne signe rien et ne publie rien. C'est le mode utilisé
    par l'intégration continue sur une demande de fusion.

.PARAMETER PfxPath
    Chemin d'un certificat PKCS#12. Le mot de passe est lu dans la variable
    d'environnement ACP_SIGNING_PASSWORD, jamais passé en argument de ligne de
    commande. Sans ce paramètre, rien n'est signé.

.PARAMETER SkipInstaller
    Ne fabrique que l'archive portable. Utile quand Inno Setup n'est pas installé.

.EXAMPLE
    ./scripts/package-desktop.ps1 -DryRun

.EXAMPLE
    $env:ACP_SIGNING_PASSWORD = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
    ./scripts/package-desktop.ps1 -PfxPath .\certificat.pfx
#>

[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string] $Configuration = 'Release',
    [string] $QtDir,
    [string] $Version,
    [string] $OutputDir,
    [switch] $DryRun,
    [string] $PfxPath,
    [switch] $SkipInstaller
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\packaging\windows\DesktopToolchain.psm1') -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$codes = Get-AcpExitCodes
$script:CodeCourant = $codes.ErreurInattendue
$script:Empreinte = $null

function Find-Signtool {
    <#
    .SYNOPSIS
        Chemin de signtool.exe : le PATH d'abord, puis le SDK Windows le plus récent.
    #>
    $commande = Get-Command -Name 'signtool.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($commande) { return $commande.Source }

    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if (-not $base) { continue }
        $racineKit = Join-Path $base 'Windows Kits\10\bin'
        if (-not (Test-Path -LiteralPath $racineKit)) { continue }
        $trouve = Get-ChildItem -LiteralPath $racineKit -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'x64\signtool.exe' } |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if ($trouve) { return $trouve }
    }
    return $null
}

function Invoke-Signature {
    <#
    .SYNOPSIS
        Signe un fichier avec le certificat déjà importé dans le magasin de l'utilisateur.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $Fichier,
        [Parameter(Mandatory = $true)][string] $Signtool,
        [Parameter(Mandatory = $true)][object] $Signature
    )
    Invoke-AcpProcess -FilePath $Signtool -Arguments @(
        'sign',
        '/sha1', $script:Empreinte,
        '/fd', $Signature.fileDigestAlgorithm,
        '/tr', $Signature.timestampUrl,
        '/td', $Signature.fileDigestAlgorithm,
        '/v',
        $Fichier
    ) -Message "La signature de $(Split-Path -Leaf $Fichier) a échoué"
}

try {
    $toolchain = Get-AcpToolchain
    $racine = Get-AcpRepositoryRoot
    $preset = Get-AcpPresetName -Configuration $Configuration -Toolchain $toolchain
    $repertoireCompilation = Get-AcpBuildDirectory -Preset $preset -Toolchain $toolchain

    if ([string]::IsNullOrWhiteSpace($Version)) { $Version = Get-AcpProductVersion }
    if ([string]::IsNullOrWhiteSpace($OutputDir)) { $OutputDir = Join-Path $racine 'dist\desktop' }
    $OutputDir = [System.IO.Path]::GetFullPath($OutputDir).TrimEnd('\')

    $prefixe = $toolchain.product.artifactPrefix
    $suffixe = $toolchain.product.architectureSuffix
    $nomExecutable = $toolchain.product.executable
    $nomInstalleurBase = "$prefixe-Setup-$Version-$suffixe"
    $nomInstalleur = "$nomInstalleurBase.exe"
    $nomArchive = "$prefixe-Portable-$Version-$suffixe.zip"

    Write-AcpEtape "Empaquetage du client desktop $Version — $Configuration"
    if ($DryRun) {
        Write-Host "Mode à blanc : les artefacts sont produits, rien n'est signé, rien n'est publié." -ForegroundColor Yellow
    }

    # --- 1. Binaire compilé -------------------------------------------------------
    $script:CodeCourant = $codes.ContratAbsent
    if (-not (Test-Path -LiteralPath $repertoireCompilation)) {
        Write-AcpRefus `
            -Message "Rien n'a été compilé pour la configuration $Configuration." `
            -Details @(
                "Attendu : $repertoireCompilation",
                "Lancez d'abord ./scripts/build-desktop.ps1 -Configuration $Configuration"
            )
        exit $script:CodeCourant
    }

    $candidats = @(Get-ChildItem -LiteralPath $repertoireCompilation -Recurse -File -Filter $nomExecutable -ErrorAction SilentlyContinue)
    if ($candidats.Count -eq 0) {
        Write-AcpRefus `
            -Message "Le binaire $nomExecutable est introuvable sous $repertoireCompilation." `
            -Details @("Le nom de l'exécutable est fixé dans packaging/windows/toolchain.json et repris tel quel par l'installeur.")
        exit $script:CodeCourant
    }
    $prefere = @($candidats | Where-Object { $_.DirectoryName -like "*\$Configuration" })
    if ($prefere.Count -gt 0) { $candidats = $prefere }
    $executableSource = ($candidats | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
    Write-Host "Binaire : $executableSource"

    $repertoireQml = Join-Path $racine ($toolchain.cmake.qmlDirectory -replace '/', '\')
    if (-not (Test-Path -LiteralPath $repertoireQml)) {
        Write-AcpRefus `
            -Message "Le répertoire QML à analyser est introuvable : $repertoireQml" `
            -Details @(
                "windeployqt doit analyser les sources QML pour embarquer les bons modules ; sans elles, l'application se lancerait en produisant une fenêtre vide.",
                "Corrigez cmake.qmlDirectory dans packaging/windows/toolchain.json si le lot desktop range ses QML ailleurs."
            )
        exit $script:CodeCourant
    }

    # --- 2. Mise en scène ---------------------------------------------------------
    $script:CodeCourant = $codes.EmpaquetageEchoue
    $scene = Join-Path $OutputDir 'stage'
    if (Test-Path -LiteralPath $scene) { Remove-Item -LiteralPath $scene -Recurse -Force }
    New-Item -ItemType Directory -Path $scene -Force | Out-Null
    Copy-Item -LiteralPath $executableSource -Destination (Join-Path $scene $nomExecutable) -Force
    $executableScene = Join-Path $scene $nomExecutable

    # --- 3. windeployqt -----------------------------------------------------------
    $script:CodeCourant = $codes.PrerequisManquant
    $qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $toolchain
    if (-not $qt) {
        Write-AcpRefus `
            -Message "Aucune installation Qt $($toolchain.qt.version) utilisable n'a été trouvée." `
            -Details @("Inventaire : ./scripts/setup-desktop.ps1")
        exit $script:CodeCourant
    }
    $windeployqt = Join-Path $qt 'bin\windeployqt.exe'

    $script:CodeCourant = $codes.EmpaquetageEchoue
    Write-AcpEtape "Déploiement des dépendances Qt (windeployqt)"
    # --qmldir force l'analyse des imports QML ; --compiler-runtime embarque le
    # runtime MSVC pour que l'archive portable fonctionne sur un poste nu. Les
    # traductions Qt sont volontairement conservées : elles portent le français
    # des boîtes de dialogue standard.
    Invoke-AcpProcess -FilePath $windeployqt -Arguments @(
        "--$($Configuration.ToLowerInvariant())",
        '--qmldir', $repertoireQml,
        '--compiler-runtime',
        '--verbose', '1',
        $executableScene
    ) -Message "windeployqt a échoué"

    # --- 4. Certificat ------------------------------------------------------------
    $signatureDemandee = (-not $DryRun) -and (-not [string]::IsNullOrWhiteSpace($PfxPath))
    $signtool = $null
    if ($signatureDemandee) {
        $script:CodeCourant = $codes.SignatureEchouee
        if (-not (Test-Path -LiteralPath $PfxPath)) {
            Write-AcpRefus -Message "Le certificat indiqué est introuvable : $PfxPath"
            exit $script:CodeCourant
        }
        if ([string]::IsNullOrWhiteSpace($env:ACP_SIGNING_PASSWORD)) {
            Write-AcpRefus `
                -Message "Le mot de passe du certificat est absent." `
                -Details @("Renseignez la variable d'environnement ACP_SIGNING_PASSWORD. Elle n'est jamais passée en argument de ligne de commande.")
            exit $script:CodeCourant
        }
        $signtool = Find-Signtool
        if (-not $signtool) {
            Write-AcpRefus `
                -Message "signtool.exe est introuvable." `
                -Details @("Il est livré par le SDK Windows 10/11 : winget install --id Microsoft.WindowsSDK.10.0.22621")
            exit $script:CodeCourant
        }

        Write-AcpEtape "Import du certificat de signature"
        $motDePasse = ConvertTo-SecureString -String $env:ACP_SIGNING_PASSWORD -AsPlainText -Force
        $certificat = Import-PfxCertificate -FilePath $PfxPath `
            -CertStoreLocation $toolchain.signing.certificateStore -Password $motDePasse
        $script:Empreinte = $certificat.Thumbprint
        Write-Host "Certificat importé (empreinte $($script:Empreinte))."

        Write-AcpEtape "Signature de l'exécutable"
        Invoke-Signature -Fichier $executableScene -Signtool $signtool -Signature $toolchain.signing
    }
    else {
        Write-Host ''
        Write-Host 'AUCUNE SIGNATURE : les binaires produits ne sont pas signés.' -ForegroundColor Yellow
        if ($DryRun) {
            Write-Host "Raison : empaquetage à blanc." -ForegroundColor Yellow
        }
        else {
            Write-Host "Raison : aucun certificat fourni (-PfxPath absent)." -ForegroundColor Yellow
        }
    }

    # --- 5. Archive portable ------------------------------------------------------
    $script:CodeCourant = $codes.EmpaquetageEchoue
    Write-AcpEtape "Archive portable"
    $cheminArchive = Join-Path $OutputDir $nomArchive
    if (Test-Path -LiteralPath $cheminArchive) { Remove-Item -LiteralPath $cheminArchive -Force }
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $scene, $cheminArchive, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    Write-Host "Produit : $cheminArchive"
    $artefacts = @($cheminArchive)

    # --- 6. Programme d'installation ---------------------------------------------
    if (-not $SkipInstaller) {
        $script:CodeCourant = $codes.PrerequisManquant
        $iscc = Find-AcpInnoSetupCompiler
        if (-not $iscc) {
            Write-AcpRefus `
                -Message "Le compilateur Inno Setup (ISCC.exe) est introuvable." `
                -Details @(
                    "À lancer vous-même : winget install --id JRSoftware.InnoSetup",
                    "Pour ne produire que l'archive portable : ./scripts/package-desktop.ps1 -SkipInstaller"
                )
            exit $script:CodeCourant
        }

        $script:CodeCourant = $codes.EmpaquetageEchoue
        Write-AcpEtape "Programme d'installation (Inno Setup)"
        $scriptIss = Join-Path $racine ($toolchain.innoSetup.script -replace '/', '\')
        Invoke-AcpProcess -FilePath $iscc -Arguments @(
            "/DAcpVersion=$Version",
            "/DAcpSourceDir=$($scene.TrimEnd('\'))",
            "/DAcpOutputDir=$OutputDir",
            "/DAcpOutputBaseFilename=$nomInstalleurBase",
            $scriptIss
        ) -Message "La compilation du programme d'installation a échoué"

        $cheminInstalleur = Join-Path $OutputDir $nomInstalleur
        if (-not (Test-Path -LiteralPath $cheminInstalleur)) {
            Write-AcpRefus -Message "Inno Setup n'a pas produit $cheminInstalleur."
            exit $script:CodeCourant
        }
        Write-Host "Produit : $cheminInstalleur"

        if ($signatureDemandee) {
            $script:CodeCourant = $codes.SignatureEchouee
            Write-AcpEtape "Signature du programme d'installation"
            Invoke-Signature -Fichier $cheminInstalleur -Signtool $signtool -Signature $toolchain.signing
        }
        $artefacts = @($cheminInstalleur) + $artefacts
    }
    else {
        Write-Host "Programme d'installation ignoré (-SkipInstaller)." -ForegroundColor Yellow
    }

    # --- 7. Sommes de contrôle ----------------------------------------------------
    $script:CodeCourant = $codes.EmpaquetageEchoue
    Write-AcpEtape "Sommes de contrôle SHA-256"
    $cheminSommes = Write-AcpChecksumFile -Files $artefacts -Destination (Join-Path $OutputDir 'SHA256SUMS.txt')
    Get-Content -LiteralPath $cheminSommes | ForEach-Object { Write-Host "  $_" }

    Write-Host ''
    Write-Host "Empaquetage terminé dans $OutputDir" -ForegroundColor Green
    if ($signatureDemandee) {
        Write-Host 'Les artefacts sont signés et horodatés.' -ForegroundColor Green
    }
    else {
        Write-Host 'Les artefacts NE SONT PAS signés : Windows SmartScreen avertira les utilisateurs.' -ForegroundColor Yellow
    }
    exit $codes.Succes
}
catch {
    Write-AcpRefus -Message $_.Exception.Message
    exit $script:CodeCourant
}
finally {
    # Le certificat ne reste jamais dans le magasin de l'utilisateur après coup.
    if ($script:Empreinte) {
        $chemin = Join-Path $toolchain.signing.certificateStore $script:Empreinte
        if (Test-Path -LiteralPath $chemin) {
            Remove-Item -LiteralPath $chemin -Force -ErrorAction SilentlyContinue
        }
    }
}
