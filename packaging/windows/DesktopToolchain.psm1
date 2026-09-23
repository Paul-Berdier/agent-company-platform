#Requires -Version 5.1

<#
.SYNOPSIS
    Fonctions partagées par les scripts de la station de travail desktop Windows.

.DESCRIPTION
    Ce module ne modifie jamais le poste : il détecte, il résout des chemins, il
    exécute des commandes explicites et il refuse clairement quand un prérequis
    manque. Aucune installation silencieuse, aucun réglage global changé,
    aucun secret écrit sur disque.

    Il est chargé par scripts/setup-desktop.ps1, dev-desktop.ps1,
    build-desktop.ps1, test-desktop.ps1 et package-desktop.ps1.
#>

$script:CodesSortie = [ordered]@{
    Succes             = 0
    ErreurInattendue   = 1
    PrerequisManquant  = 2
    ContratAbsent      = 3
    CompilationEchouee = 4
    TestsEchoues       = 5
    EmpaquetageEchoue  = 6
    SignatureEchouee   = 7
}

function Get-AcpExitCodes {
    <#
    .SYNOPSIS
        Table des codes de sortie communs à tous les scripts desktop.
    #>
    return $script:CodesSortie
}

function Get-AcpRepositoryRoot {
    <#
    .SYNOPSIS
        Racine du dépôt, déduite de l'emplacement de ce module (packaging/windows).
    #>
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}

function Get-AcpToolchain {
    <#
    .SYNOPSIS
        Lit packaging/windows/toolchain.json, la source unique des versions.
    #>
    $racine = Get-AcpRepositoryRoot
    $chemin = Join-Path $racine 'packaging\windows\toolchain.json'
    if (-not (Test-Path -LiteralPath $chemin)) {
        throw "Chaîne d'outils introuvable : $chemin n'existe pas."
    }
    $brut = Get-Content -LiteralPath $chemin -Raw -Encoding UTF8
    try {
        return ($brut | ConvertFrom-Json)
    }
    catch {
        throw "packaging/windows/toolchain.json est illisible : $($_.Exception.Message)"
    }
}

function Get-AcpProductVersion {
    <#
    .SYNOPSIS
        Version du produit, lue dans le fichier VERSION à la racine du dépôt.
    #>
    $chemin = Join-Path (Get-AcpRepositoryRoot) 'VERSION'
    if (-not (Test-Path -LiteralPath $chemin)) {
        throw "Fichier VERSION introuvable à la racine du dépôt."
    }
    $version = (Get-Content -LiteralPath $chemin -Raw -Encoding UTF8).Trim()
    if ($version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+([-+.0-9A-Za-z]*)$') {
        throw "Le fichier VERSION contient une valeur inattendue : '$version'."
    }
    return $version
}

function Write-AcpEtape {
    <#
    .SYNOPSIS
        Titre d'étape, pour que la sortie reste lisible dans un journal de CI.
    #>
    param([Parameter(Mandatory = $true)][string] $Message)
    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Write-AcpRefus {
    <#
    .SYNOPSIS
        Refus explicite en français, écrit sur le flux d'erreur.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $Message,
        [string[]] $Details = @()
    )
    Write-Host ''
    [Console]::Error.WriteLine("REFUS : $Message")
    foreach ($ligne in $Details) {
        [Console]::Error.WriteLine("  - $ligne")
    }
}

function Test-AcpQtDirectory {
    <#
    .SYNOPSIS
        Vrai si le répertoire ressemble à une installation Qt utilisable (windeployqt présent).
    #>
    param([string] $Chemin)
    if ([string]::IsNullOrWhiteSpace($Chemin)) { return $false }
    if (-not (Test-Path -LiteralPath $Chemin)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Chemin 'bin\windeployqt.exe'))
}

function Resolve-AcpQtDirectory {
    <#
    .SYNOPSIS
        Résout le répertoire Qt sans jamais rien installer.

    .DESCRIPTION
        Ordre de recherche, du plus explicite au plus deviné :
          1. le paramètre -QtDir ;
          2. la variable d'environnement ACP_QT_DIR ;
          3. QT_ROOT_DIR (posée par jurplel/install-qt-action) ;
          4. Qt6_DIR (pointe sur lib/cmake/Qt6, on remonte de trois niveaux) ;
          5. C:\Qt\<version épinglée>\msvc2022_64.
        Renvoie $null si rien de valide n'est trouvé : c'est à l'appelant de refuser.
    #>
    param(
        [string] $QtDir,
        [object] $Toolchain
    )

    if (-not $Toolchain) { $Toolchain = Get-AcpToolchain }

    $candidats = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($QtDir)) { $candidats.Add($QtDir) }
    if (-not [string]::IsNullOrWhiteSpace($env:ACP_QT_DIR)) { $candidats.Add($env:ACP_QT_DIR) }
    if (-not [string]::IsNullOrWhiteSpace($env:QT_ROOT_DIR)) { $candidats.Add($env:QT_ROOT_DIR) }
    if (-not [string]::IsNullOrWhiteSpace($env:Qt6_DIR)) {
        $candidats.Add((Join-Path $env:Qt6_DIR '..\..\..'))
    }
    $architecture = $Toolchain.qt.architecture -replace '^win64_', ''
    $candidats.Add("C:\Qt\$($Toolchain.qt.version)\$architecture")

    foreach ($candidat in $candidats) {
        try {
            $resolu = (Resolve-Path -LiteralPath $candidat -ErrorAction Stop).Path
        }
        catch {
            continue
        }
        if (Test-AcpQtDirectory -Chemin $resolu) { return $resolu }
    }
    return $null
}

function Get-AcpCommandVersion {
    <#
    .SYNOPSIS
        Première ligne de la version d'un exécutable, ou $null s'il est absent ou muet.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $Nom,
        [string[]] $Arguments = @('--version')
    )
    $commande = Get-Command -Name $Nom -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $commande) { return $null }
    try {
        $sortie = & $commande.Source @Arguments 2>&1
    }
    catch {
        return $commande.Source
    }
    $premiere = ($sortie | Select-Object -First 1)
    if ($null -eq $premiere) { return $commande.Source }
    return ([string]$premiere).Trim()
}

function Find-AcpVisualStudio {
    <#
    .SYNOPSIS
        Chemin d'installation d'un Visual Studio portant les outils C++ x64, via vswhere.
    #>
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { return $null }
    $chemin = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $chemin = ($chemin | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($chemin)) { return $null }
    return ([string]$chemin).Trim()
}

function Set-AcpMsvcOutputEncoding {
    # Préférer l'anglais lorsqu'il est installé. Sinon MSVC garde sa langue :
    # la page UTF-8 doit donc être la même pour sa sortie et sa détection CMake.
    $env:VSLANG = '1033'
    $chcp = Join-Path $env:SystemRoot 'System32\chcp.com'
    & $chcp 65001 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Impossible d'initialiser la page de codes UTF-8 de la console MSVC."
    }
}

function Enter-AcpMsvcEnvironment {
    <#
    .SYNOPSIS
        Charge l'environnement de développement MSVC x64 dans la session courante.

    .DESCRIPTION
        Préfère l'anglais (VSLANG=1033) et fixe la page de codes UTF-8 de la console
        pour la configuration CMake et la compilation, y compris si cl.exe est
        déjà joignable. MSVC reste utilisable avec son seul pack de langue installé.
        Sinon, localise Visual Studio par
        vswhere puis invoque Launch-VsDevShell.ps1, qui est la méthode documentée par
        Microsoft pour initialiser un environnement de compilation depuis un script
        (https://learn.microsoft.com/en-us/visualstudio/ide/reference/command-prompt-powershell,
        consultée le 18 septembre 2026). Renvoie $true si cl.exe est joignable ensuite.
    #>
    # /showIncludes est un protocole de dépendances pour Ninja. La console
    # UTF-8 évite un préfixe mal décodé, y compris sans pack anglais installé.
    Set-AcpMsvcOutputEncoding
    $compilateur = Get-Command -Name 'cl.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($compilateur) {
        return $true
    }

    $vs = Find-AcpVisualStudio
    if (-not $vs) { return $false }

    $lanceur = Join-Path $vs 'Common7\Tools\Launch-VsDevShell.ps1'
    if (-not (Test-Path -LiteralPath $lanceur)) { return $false }

    # Les scripts d'initialisation de Visual Studio appellent vswhere.exe par son nom :
    # sans le répertoire de l'installeur dans le PATH de la session, ils affichent
    # « 'vswhere.exe' n'est pas reconnu », sans effet mais trompeur.
    $installeur = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer'
    if ((Test-Path -LiteralPath $installeur) -and (($env:PATH -split ';') -notcontains $installeur)) {
        $env:PATH = "$installeur;$env:PATH"
    }

    & $lanceur -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Null
    # Réaffirmer après le lanceur, qui peut importer une préférence de langue.
    Set-AcpMsvcOutputEncoding
    $compilateur = Get-Command -Name 'cl.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $compilateur) { return $false }
    return $true
}

function Get-AcpPrerequisites {
    <#
    .SYNOPSIS
        Inventaire des prérequis de compilation du client desktop.

    .DESCRIPTION
        Ne modifie rien. Renvoie une liste d'objets décrivant, pour chaque outil,
        s'il est présent, ce qui a été détecté, et la commande exacte à lancer
        soi-même pour l'installer.
    #>
    param(
        [string] $QtDir,
        [object] $Toolchain
    )

    if (-not $Toolchain) { $Toolchain = Get-AcpToolchain }
    $racine = Get-AcpRepositoryRoot
    $resultats = New-Object System.Collections.Generic.List[object]

    function New-Verdict {
        param($Nom, $Requis, $Present, $Detail, $Installation)
        return [pscustomobject]@{
            Nom          = $Nom
            Requis       = $Requis
            Present      = $Present
            Detail       = $Detail
            Installation = $Installation
        }
    }

    # Visual Studio / MSVC
    $vs = Find-AcpVisualStudio
    $resultats.Add((New-Verdict `
        -Nom 'Compilateur MSVC (Visual Studio 2022, charge C++ x64)' `
        -Requis $true `
        -Present ([bool]$vs) `
        -Detail $(if ($vs) { $vs } else { 'Aucune installation Visual Studio portant Microsoft.VisualStudio.Component.VC.Tools.x86.x64' }) `
        -Installation 'winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.22621"'))

    # CMake
    $cmake = Get-AcpCommandVersion -Nom 'cmake' -Arguments @('--version')
    $resultats.Add((New-Verdict `
        -Nom 'CMake (>= 3.28 recommandé pour les préréglages v8)' `
        -Requis $true `
        -Present ([bool]$cmake) `
        -Detail $(if ($cmake) { $cmake } else { 'cmake introuvable dans le PATH' }) `
        -Installation 'winget install --id Kitware.CMake'))

    # Ninja
    $ninja = Get-AcpCommandVersion -Nom 'ninja' -Arguments @('--version')
    $resultats.Add((New-Verdict `
        -Nom 'Ninja (nécessaire si le préréglage MSVC utilise le générateur Ninja)' `
        -Requis $false `
        -Present ([bool]$ninja) `
        -Detail $(if ($ninja) { "ninja $ninja" } else { 'ninja introuvable dans le PATH' }) `
        -Installation 'winget install --id Ninja-build.Ninja'))

    # Qt
    $qt = Resolve-AcpQtDirectory -QtDir $QtDir -Toolchain $Toolchain
    $architecture = $Toolchain.qt.architecture -replace '^win64_', ''
    $resultats.Add((New-Verdict `
        -Nom "Qt $($Toolchain.qt.version) $architecture" `
        -Requis $true `
        -Present ([bool]$qt) `
        -Detail $(if ($qt) { $qt } else { "Aucun répertoire Qt valide (bin\windeployqt.exe absent) parmi -QtDir, ACP_QT_DIR, QT_ROOT_DIR, Qt6_DIR et C:\Qt\$($Toolchain.qt.version)\$architecture" }) `
        -Installation "Installeur officiel Qt (https://www.qt.io/download-qt-installer) : cocher Qt $($Toolchain.qt.version) / MSVC 2022 64-bit. Sinon, en ligne de commande : pip install aqtinstall puis aqt install-qt $($Toolchain.qt.host) $($Toolchain.qt.target) $($Toolchain.qt.version) $($Toolchain.qt.architecture) --outputdir C:\Qt"))

    # Inno Setup (empaquetage seulement)
    $iscc = Find-AcpInnoSetupCompiler
    $resultats.Add((New-Verdict `
        -Nom "Inno Setup $($Toolchain.innoSetup.minimumVersion) ou plus récent (empaquetage seulement)" `
        -Requis $false `
        -Present ([bool]$iscc) `
        -Detail $(if ($iscc) { $iscc } else { 'ISCC.exe introuvable' }) `
        -Installation "winget install --id JRSoftware.InnoSetup"))

    # Sources du client desktop
    $sources = Join-Path $racine ($Toolchain.cmake.sourceDirectory -replace '/', '\')
    $presets = Join-Path $sources 'CMakePresets.json'
    $resultats.Add((New-Verdict `
        -Nom "Sources du client desktop ($($Toolchain.cmake.sourceDirectory)/CMakePresets.json)" `
        -Requis $true `
        -Present (Test-Path -LiteralPath $presets) `
        -Detail $(if (Test-Path -LiteralPath $presets) { $presets } else { "$presets est absent : le lot qui écrit apps/desktop n'a pas encore été fusionné" }) `
        -Installation "Aucune commande : ce répertoire est produit par le lot fondation desktop, pas par cette chaîne d'outils."))

    # Contrat des préréglages : chaque nom de toolchain.json (cmake.presets) doit exister
    # comme préréglage de configuration, de compilation ET de test. Sans le préréglage de
    # test, test-desktop.ps1 échouerait après une compilation complète.
    if (Test-Path -LiteralPath $presets) {
        $declares = Get-Content -LiteralPath $presets -Raw -Encoding UTF8 | ConvertFrom-Json
        $manquants = New-Object System.Collections.Generic.List[string]
        foreach ($nom in $Toolchain.cmake.presets.PSObject.Properties.Value) {
            foreach ($famille in 'configurePresets', 'buildPresets', 'testPresets') {
                if (-not (@($declares.$famille) | Where-Object { $_.name -eq $nom })) {
                    $manquants.Add("$famille/$nom")
                }
            }
        }
        $resultats.Add((New-Verdict `
            -Nom 'Préréglages CMake exigés par packaging/windows/toolchain.json' `
            -Requis $true `
            -Present ($manquants.Count -eq 0) `
            -Detail $(if ($manquants.Count -eq 0) { 'configuration, compilation et test présents pour chaque préréglage' } else { 'absents de CMakePresets.json : ' + ($manquants -join ', ') }) `
            -Installation "Aucune commande : déclarer les préréglages manquants dans $($Toolchain.cmake.sourceDirectory)/CMakePresets.json."))
    }

    return $resultats
}

function Find-AcpInnoSetupCompiler {
    <#
    .SYNOPSIS
        Chemin de ISCC.exe, le compilateur Inno Setup, ou $null.
    #>
    $commande = Get-Command -Name 'iscc.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($commande) { return $commande.Source }

    # winget installe Inno Setup par utilisateur sous LOCALAPPDATA quand on lui
    # demande --scope user : c'est l'installation recommandée par ce dépôt, qui
    # évite une élévation inutile. Les deux emplacements machine restent examinés.
    $candidats = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($candidat in $candidats) {
        if ($candidat -and (Test-Path -LiteralPath $candidat)) { return $candidat }
    }
    return $null
}

function Get-AcpPresetName {
    <#
    .SYNOPSIS
        Nom du préréglage CMake pour une configuration donnée.
    #>
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Debug', 'Release')][string] $Configuration,
        [object] $Toolchain
    )
    if (-not $Toolchain) { $Toolchain = Get-AcpToolchain }
    return $Toolchain.cmake.presets.$Configuration
}

function Get-AcpBuildDirectory {
    <#
    .SYNOPSIS
        Répertoire de compilation attendu pour un préréglage, selon le contrat documenté.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $Preset,
        [object] $Toolchain
    )
    if (-not $Toolchain) { $Toolchain = Get-AcpToolchain }
    $racine = Get-AcpRepositoryRoot
    $source = Join-Path $racine ($Toolchain.cmake.sourceDirectory -replace '/', '\')
    return (Join-Path $source "build\$Preset")
}

function Copy-AcpMsvcRuntime {
    <#
    .SYNOPSIS
        Déploie le CRT MSVC x64 redistribuable à côté de l'exécutable Release.
    .DESCRIPTION
        Utilise l'installation Visual Studio du compilateur enregistré par CMake,
        jamais une DLL trouvée dans System32 ou dans le PATH. La version des DLL
        doit couvrir le toolset utilisé et le linker du Qt effectivement déployé.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $BuildDirectory,
        [Parameter(Mandatory = $true)][string] $Destination
    )

    $cache = Get-Content -LiteralPath (Join-Path $BuildDirectory 'CMakeCache.txt')
    $compiler = @($cache | Where-Object { $_ -match '^CMAKE_CXX_COMPILER:FILEPATH=' })
    if ($compiler.Count -ne 1 -or $compiler[0] -notmatch
        '^CMAKE_CXX_COMPILER:FILEPATH=(.+[\\/]VC)[\\/]Tools[\\/]MSVC[\\/](14\.\d+\.\d+)[\\/]bin[\\/]Host(?:x64|x86)[\\/]x64[\\/]cl\.exe$') {
        throw 'Le cache CMake ne désigne pas un toolset MSVC x64 redistribuable connu.'
    }
    $vcRoot = $Matches[1]
    $minimumVersion = [version]($Matches[2] + '.0')
    if ($minimumVersion.Minor -lt 30) {
        throw 'Le client Qt MSVC 2022 exige le CRT VC143 (toolset 14.30 ou plus récent).'
    }

    function Read-AcpPeRuntimeContract([string] $Path) {
        $reader = New-Object System.IO.BinaryReader([System.IO.File]::OpenRead($Path))
        try {
            if ($reader.ReadUInt16() -ne 0x5a4d) { throw "Fichier PE invalide : $Path" }
            $reader.BaseStream.Position = 0x3c
            $offset = $reader.ReadUInt32()
            $reader.BaseStream.Position = $offset
            if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) {
                throw "Le fichier n'est pas un binaire PE x64 : $Path"
            }
            $reader.BaseStream.Position = $offset + 24
            if ($reader.ReadUInt16() -ne 0x20b) { throw "En-tête PE32+ attendu : $Path" }
            return [version](('{0}.{1}' -f $reader.ReadByte(), $reader.ReadByte()))
        }
        finally { $reader.Dispose() }
    }

    $qtLinker = Read-AcpPeRuntimeContract (Join-Path $Destination 'Qt6Core.dll')
    $appLinker = Read-AcpPeRuntimeContract (Join-Path $Destination 'AgentCompanyPlatform.exe')
    $redistRoot = Join-Path $vcRoot 'Redist/MSVC'
    $candidates = @(Get-ChildItem -LiteralPath $redistRoot -Directory | Where-Object {
        $_.Name -match '^14\.\d+\.\d+$'
    } | ForEach-Object {
        $directory = Join-Path $_.FullName 'x64/Microsoft.VC143.CRT'
        $runtime = Join-Path $directory 'vcruntime140.dll'
        if (Test-Path -LiteralPath $runtime) {
            $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($runtime)
            $version = [version]('{0}.{1}.{2}.{3}' -f $info.FileMajorPart,
                $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart)
            if ($version -ge $minimumVersion -and $version -ge $qtLinker -and $version -ge $appLinker) {
                [pscustomobject]@{ Directory = $directory; Version = $version }
            }
        }
    } | Sort-Object Version -Descending)
    if ($candidates.Count -eq 0) {
        throw "CRT VC143 x64 redistribuable introuvable ou trop ancien (minimum $minimumVersion ; Qt linker $qtLinker)."
    }
    $selected = $candidates[0]
    $required = @('concrt140.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll',
        'msvcp140_atomic_wait.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
    foreach ($name in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $selected.Directory $name))) {
            throw "CRT redistribuable incomplet : $name absent."
        }
    }
    $files = @(Get-ChildItem -LiteralPath $selected.Directory -File -Filter '*.dll')
    foreach ($file in $files) {
        $null = Read-AcpPeRuntimeContract $file.FullName
        $info = $file.VersionInfo
        $version = [version]('{0}.{1}.{2}.{3}' -f $info.FileMajorPart,
            $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart)
        if ($version -ne $selected.Version) { throw "Versions CRT incohérentes : $($file.Name)." }
    }
    foreach ($file in $files) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $Destination $file.Name)
    }
    return [pscustomobject]@{
        Version = $selected.Version.ToString()
        RequiredVersion = $minimumVersion.ToString()
        QtLinkerVersion = $qtLinker.ToString()
        Directory = $selected.Directory
        FileCount = $files.Count
    }
}

function Invoke-AcpProcess {
    <#
    .SYNOPSIS
        Exécute un programme externe et lève une exception française s'il échoue.
    #>
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [string[]] $Arguments = @(),
        [string] $Message = '',
        [string] $WorkingDirectory = ''
    )

    $precedent = $null
    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        $precedent = (Get-Location).Path
        Set-Location -LiteralPath $WorkingDirectory
    }
    try {
        Write-Host "> $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
        & $FilePath @Arguments
        $code = $LASTEXITCODE
    }
    finally {
        if ($precedent) { Set-Location -LiteralPath $precedent }
    }

    if ($code -ne 0) {
        $texte = $Message
        if ([string]::IsNullOrWhiteSpace($texte)) {
            $texte = "La commande a échoué : $FilePath"
        }
        throw "$texte (code de sortie $code)."
    }
}

function Get-AcpSha256 {
    <#
    .SYNOPSIS
        Empreinte SHA-256 minuscule d'un fichier.
    #>
    param([Parameter(Mandatory = $true)][string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-AcpChecksumFile {
    <#
    .SYNOPSIS
        Écrit un SHA256SUMS.txt au format « empreinte deux-espaces nom », lisible par sha256sum -c.
    #>
    param(
        [Parameter(Mandatory = $true)][string[]] $Files,
        [Parameter(Mandatory = $true)][string] $Destination
    )
    $lignes = foreach ($fichier in $Files) {
        '{0}  {1}' -f (Get-AcpSha256 -Path $fichier), (Split-Path -Leaf $fichier)
    }
    $contenu = ($lignes -join "`n") + "`n"
    [System.IO.File]::WriteAllText($Destination, $contenu, (New-Object System.Text.UTF8Encoding($false)))
    return $Destination
}

Export-ModuleMember -Function `
    Get-AcpExitCodes, `
    Get-AcpRepositoryRoot, `
    Get-AcpToolchain, `
    Get-AcpProductVersion, `
    Write-AcpEtape, `
    Write-AcpRefus, `
    Test-AcpQtDirectory, `
    Resolve-AcpQtDirectory, `
    Get-AcpCommandVersion, `
    Find-AcpVisualStudio, `
    Enter-AcpMsvcEnvironment, `
    Get-AcpPrerequisites, `
    Find-AcpInnoSetupCompiler, `
    Get-AcpPresetName, `
    Get-AcpBuildDirectory, `
    Copy-AcpMsvcRuntime, `
    Invoke-AcpProcess, `
    Get-AcpSha256, `
    Write-AcpChecksumFile
