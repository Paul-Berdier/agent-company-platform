#Requires -Version 5.1
<#
.SYNOPSIS
    Installe le poste Windows d'ACP sous un compte Windows dédié et une tâche planifiée (étape P5, cahier § 8).

.DESCRIPTION
    À lancer PAR LE PROPRIÉTAIRE, dans un PowerShell ÉLEVÉ (UAC). Rien ne se fait sans lui : le mot de passe du compte
    « acp-poste » est saisi par lui (jamais écrit nulle part), chaque réglage système optionnel demande sa
    confirmation. Neuf étapes, chacune refusée en français si sa condition manque :

      1. contrôles (administrateur, Windows 10/11, Python 3.12 de python.org « pour tous les utilisateurs » et non
         modifiable par le compte du poste, dépôt, origine HTTPS, sources de Codex et de Claude Code avec leur
         version : Claude Code 2.1.248 au moins, avertissement sous 2.1.280) ;
      2. compte local « acp-poste » (membre du seul groupe Utilisateurs, désigné par SID) ;
      3. dossiers et ACL (héritage coupé, groupes désignés par SID : le PC est en français, les runners en anglais) ;
      4. poste installé SANS venv (décision D53) : dépendances d'exécution hachées (requirements/poste-3.12.lock.txt)
         et sources du poste copiées sous Program Files\ACP\poste\lib, lanceur python -I ;
      5. binaires de Codex et de Claude Code copiés depuis vos installations (décision D54), SHA-256 consignés,
         --version relancé sur la copie ;
      6. poste.toml écrit depuis le modèle s'il n'existe pas (jamais remplacé : différence affichée, écarts de
         version_testee signalés) ;
      7. tâche planifiée \ACP\Poste ACP (au démarrage + garde toutes les 15 min, mot de passe enregistré) ;
      8. options système, chacune sur confirmation explicite (décision D57) ;
      9. vérifications finales et liste des gestes manuels restants.

    -Simulation n'écrit RIEN (ni fichier, ni compte, ni tâche, ni réglage) et ne demande aucun mot de passe : il
    imprime le plan des neuf étapes et TOUS les refus (code 2 s'il y en a, 0 sinon). Seul « --version » est lancé sur
    les sources de Codex et de Claude Code, dans un profil jetable sous %TEMP% supprimé aussitôt. C'est ce que vérifie
    packaging/poste/tests/Test-InstallationPoste.ps1. Les fonctions communes sont dans Fonctions-PosteAcp.ps1, à côté.

.EXAMPLE
    # PowerShell élevé, depuis la racine du dépôt :
    .\packaging\poste\Installer-PosteAcp.ps1 -Origine https://hermes-xxxx.up.railway.app `
        -Python 'C:\Program Files\Python312\python.exe' -Depot (Get-Location) `
        -CodexSource "$env:APPDATA\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc" `
        -ClaudeSource "$env:USERPROFILE\.local\bin\claude.exe" -Simulation
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Origine,
    [Parameter(Mandatory = $true)][string] $Python,
    [Parameter(Mandatory = $true)][string] $Depot,
    [Parameter(Mandatory = $true)][string] $CodexSource,
    [Parameter(Mandatory = $true)][string] $ClaudeSource,
    [string] $ProfilProprietaire = $env:USERPROFILE,
    [string] $Compte = 'acp-poste',
    [switch] $Simulation
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
if ([Console]::IsOutputRedirected) {
    # Sortie capturée (test à blanc, journal) : UTF-8, sans toucher à la page de code d'une console interactive.
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
}
$Fonctions = Join-Path $PSScriptRoot 'Fonctions-PosteAcp.ps1'
if (-not (Test-Path -LiteralPath $Fonctions -PathType Leaf)) {
    Write-Host "Refusé : Fonctions-PosteAcp.ps1 est introuvable à côté de l'installeur ; lancez-le depuis le dépôt." -ForegroundColor Red
    exit 2
}
. $Fonctions

# Groupes et comptes désignés par SID, jamais par leur nom localisé.
$SID_ADMINISTRATEURS = 'S-1-5-32-544'
$SID_UTILISATEURS = 'S-1-5-32-545'
$SID_BUREAU_A_DISTANCE = 'S-1-5-32-555'
$SID_SYSTEME = 'S-1-5-18'

$ProgramFiles = [Environment]::GetFolderPath('ProgramFiles')
$ProgramData = [Environment]::GetFolderPath('CommonApplicationData')
$AcpProgramFiles = Join-Path $ProgramFiles 'ACP'
$DossierPoste = Join-Path $AcpProgramFiles 'poste'
$DossierLib = Join-Path $DossierPoste 'lib'
$DossierOutils = Join-Path $AcpProgramFiles 'outils'
$AcpProgramData = Join-Path $ProgramData 'ACP'
$DossierQuotas = Join-Path $AcpProgramData 'quotas'
$Politique = Join-Path $AcpProgramData 'poste.toml'
$JournalInstallation = Join-Path $AcpProgramData 'installation.jsonl'
$RacineAcp = Join-Path $env:SystemDrive 'ACP'
$DossierDepots = Join-Path $RacineAcp 'depots'
$DossierEspaces = Join-Path $RacineAcp 'espaces'
$Lanceur = Join-Path $DossierPoste 'lancer.py'
$CommandePoste = Join-Path $DossierPoste 'acp-poste.cmd'
$Tache = 'Poste ACP'
$CheminTache = '\ACP\'

$script:Refus = New-Object System.Collections.Generic.List[string]

function Refuser([string] $Message) {
    if ($Simulation) {
        $script:Refus.Add($Message)
        Write-Host "  REFUS : $Message"
        return
    }
    Write-Host "Refusé : $Message" -ForegroundColor Red
    exit 2
}

function Etape([int] $Numero, [string] $Titre) {
    Write-Host ''
    Write-Host ('Étape {0}/9 : {1}' -f $Numero, $Titre)
}

function Faire([string] $Description, [scriptblock] $Action) {
    if ($Simulation) {
        Write-Host "  [simulation, rien n'est fait] $Description"
        return
    }
    Write-Host "  $Description"
    & $Action
}

function Consigner([hashtable] $Entree) {
    if ($Simulation) { return }
    $Entree['quand'] = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $ligne = ($Entree | ConvertTo-Json -Compress) + "`n"
    [IO.File]::AppendAllText($JournalInstallation, $ligne, (New-Object Text.UTF8Encoding $false))
}

function Empreinte([string] $Chemin) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Chemin).Hash.ToLowerInvariant()
}

function Sous-Un-Profil([string] $Chemin) {
    $profils = [Environment]::ExpandEnvironmentVariables(
        (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList').ProfilesDirectory)
    $plein = [IO.Path]::GetFullPath($Chemin)
    return $plein.StartsWith($profils.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Ecrire-Sans-BOM([string] $Chemin, [string] $Contenu) {
    [IO.File]::WriteAllText($Chemin, $Contenu, (New-Object Text.UTF8Encoding $false))
}

function Acl-Dossier([string] $Dossier, [string[]] $Droits) {
    # Héritage coupé, puis droits explicites (SID préfixés d'un astérisque pour icacls).
    & icacls.exe $Dossier /inheritance:r /grant:r @Droits | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls a refusé les droits de $Dossier (code $LASTEXITCODE)." }
}

Write-Host "Installation du poste Windows d'ACP (étape P5)" -NoNewline
if ($Simulation) { Write-Host " : SIMULATION, rien ne sera écrit." } else { Write-Host '.' }

# ============================================================ 1. contrôles
Etape 1 'contrôles'
# Compte déjà présent (réinstallation) : son SID compte aussi pour les droits sur l'interpréteur.
$existant = Get-CimInstance -ClassName Win32_UserAccount -Filter "LocalAccount=True AND Name='$Compte'" -ErrorAction SilentlyContinue
$sidsDuPoste = @($SidsDuComptePoste)
if ($existant) { $sidsDuPoste += $existant.SID }
$identite = [Security.Principal.WindowsIdentity]::GetCurrent()
$administrateur = ([Security.Principal.WindowsPrincipal] $identite).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($administrateur) {
    Write-Host '  administrateur : oui'
} elseif ($Simulation) {
    Write-Host "  administrateur : non (la simulation n'écrit rien ; l'installation réelle l'exigera)"
} else {
    Refuser "lancez l'installeur dans un PowerShell élevé (UAC)."
}
$version = [Environment]::OSVersion.Version
if ($version.Major -lt 10) { Refuser "Windows 10 ou 11 exigé (version lue : $version)." }
else { Write-Host "  Windows : $version" }

if (-not $Origine.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase) -or $Origine.TrimEnd('/') -match '^https://[^/]+/.+') {
    Refuser "-Origine doit être une origine HTTPS sans chemin (https://<domaine de Hermes>)."
}

$pythonAdmis = $false
if ($Python -match '[^\x20-\x7E]') {
    Refuser "le chemin de Python doit être en caractères ASCII (il est écrit dans acp-poste.cmd, lu par cmd.exe)."
} elseif ($Python -match '\\WindowsApps\\') {
    Refuser "Python du Microsoft Store (WindowsApps) refusé : son interpréteur réel sort du Job Object. Installez Python 3.12 de python.org pour tous les utilisateurs."
} elseif (Sous-Un-Profil $Python) {
    Refuser "Python installé « pour moi seul » (sous un profil) : le compte $Compte ne pourra pas l'exécuter. Installez Python 3.12 de python.org pour tous les utilisateurs."
} elseif (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Refuser "-Python ne désigne aucun fichier."
} elseif (($modifiables = @(Interpreteur-Modifiable $Python $sidsDuPoste)).Count -gt 0) {
    # Décision D67 : le service détient les jetons déchiffrés ; « python -I » exécute encore les .pth de site-packages.
    Refuser ("Python modifiable par le compte $Compte ou l'un de ses groupes ({0}) : un exécutant pourrait injecter du code dans le service, qui détient les jetons déchiffrés. Installez Python 3.12 de python.org pour tous les utilisateurs, sous Program Files (décision D67)." -f $modifiables[0])
} else {
    $versionPython = (& $Python -I -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
    if ($versionPython -ne '3.12') {
        Refuser "Python 3.12 exigé (le verrou du poste est compilé pour CPython 3.12) ; version lue : $versionPython."
    } else {
        Write-Host '  Python : 3.12, « tous utilisateurs », hors WindowsApps, non modifiable par le compte du poste'
        $pythonAdmis = $true
    }
}

foreach ($attendu in @('apps\poste\src\acp_poste\cli.py', 'hermes\plugins\acp-poste\contrat\acp_poste_contrat\machine.py',
                       'requirements\poste-3.12.lock.txt', 'packaging\poste\poste.toml.modele',
                       'packaging\poste\tache-poste.xml.modele', 'packaging\poste\lancer.py',
                       'packaging\poste\acp-poste.cmd.modele', 'packaging\poste\ligne_etat.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Depot $attendu))) {
        Refuser "-Depot n'est pas un checkout du dépôt ACP ($attendu absent)."
        break
    }
}

$codexExe = Join-Path $CodexSource 'bin\codex.exe'
$codexAide = Join-Path $CodexSource 'codex-resources\codex-windows-sandbox-setup.exe'
$versionCodex = '<lue sur la source>'
$versionClaude = '<lue sur la source>'
if (-not (Test-Path -LiteralPath $codexExe -PathType Leaf) -or -not (Test-Path -LiteralPath $codexAide -PathType Leaf)) {
    Refuser "-CodexSource doit désigner le dossier vendor\x86_64-pc-windows-msvc du paquet npm @openai/codex (bin\codex.exe et codex-resources\codex-windows-sandbox-setup.exe)."
} else {
    $lue = Lire-VersionCli $codexExe 'codex'
    if (-not $lue) {
        Refuser "codex.exe --version illisible : l'exécutable désigné par -CodexSource ne démarre pas."
    } else {
        $versionCodex = $lue
        Write-Host "  Codex (source) : $versionCodex, codex.exe SHA-256 $(Empreinte $codexExe)"
    }
}
if (-not (Test-Path -LiteralPath $ClaudeSource -PathType Leaf) -or [IO.Path]::GetFileName($ClaudeSource) -ne 'claude.exe') {
    Refuser '-ClaudeSource doit désigner le binaire natif claude.exe de votre installation de Claude Code.'
} else {
    $lue = Lire-VersionCli $ClaudeSource 'claude'
    $verdict = Verdict-VersionClaude $lue
    if ($verdict.ContainsKey('Refus')) {
        Refuser $verdict.Refus
    } else {
        $versionClaude = $lue
        Write-Host "  Claude Code (source) : $versionClaude, claude.exe SHA-256 $(Empreinte $ClaudeSource)"
        if ($verdict.ContainsKey('Avertissement')) { Write-Host "  ATTENTION : $($verdict.Avertissement)" }
    }
}
if (-not (Test-Path -LiteralPath $ProfilProprietaire -PathType Container)) {
    Refuser '-ProfilProprietaire ne désigne aucun dossier.'
}

# ============================================================ 2. compte dédié
Etape 2 "compte local « $Compte »"
# Détection par CIM à l'étape 1 (Windows PowerShell 5.1 et PowerShell 7) ; création par New-LocalUser en installation réelle.
$sidCompte = if ($existant) { $existant.SID } else { '<SID du compte créé>' }
$motDePasse = $null
if ($existant) {
    Write-Host "  Compte existant conservé (SID $sidCompte) : appartenances revérifiées ; son mot de passe sera demandé pour la tâche."
} else {
    Write-Host "  Compte à créer : mot de passe choisi par vous (deux saisies masquées), jamais écrit ; il n'expire pas, le compte ne peut pas le changer (tout changement ultérieur par un administrateur rend illisibles ses secrets DPAPI)."
}
if (-not $Simulation) {
    $motDePasse = Read-Host -AsSecureString "Mot de passe du compte $Compte"
    if (-not $existant) {
        $confirmation = Read-Host -AsSecureString 'Confirmez le mot de passe'
        $a = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($motDePasse)
        $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirmation)
        try {
            $identiques = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($a) -ceq [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($a)
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
        }
        if (-not $identiques) { Refuser 'les deux saisies du mot de passe diffèrent.' }
    }
}
Faire "New-LocalUser $Compte (-PasswordNeverExpires, -UserMayNotChangePassword, -AccountNeverExpires), membre du groupe $SID_UTILISATEURS seulement" {
    if (-not $existant) {
        New-LocalUser -Name $Compte -Password $motDePasse -PasswordNeverExpires -UserMayNotChangePassword `
            -AccountNeverExpires -Description 'ACP - poste Windows (compte dédié)' | Out-Null
    }
    $utilisateur = Get-LocalUser -Name $Compte
    $script:sidCompte = $utilisateur.SID.Value
    $utilisateurs = Get-LocalGroup -SID $SID_UTILISATEURS
    if (-not (Get-LocalGroupMember -Group $utilisateurs | Where-Object { $_.SID -eq $utilisateur.SID })) {
        Add-LocalGroupMember -Group $utilisateurs -Member $utilisateur
    }
    foreach ($interdit in @($SID_ADMINISTRATEURS, $SID_BUREAU_A_DISTANCE)) {
        $groupe = Get-LocalGroup -SID $interdit
        if (Get-LocalGroupMember -Group $groupe | Where-Object { $_.SID -eq $utilisateur.SID }) {
            Refuser "le compte $Compte est membre du groupe $interdit : retirez-le puis relancez l'installeur."
        }
    }
}
$sidProprietaire = $identite.User.Value

# ============================================================ 3. dossiers et ACL
Etape 3 'dossiers et ACL (héritage coupé, groupes désignés par SID)'
$plan = @(
    @{ Dossier = $DossierPoste; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)RX', "*${sidProprietaire}:(OI)(CI)RX") },
    @{ Dossier = $DossierOutils; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)RX', "*${sidProprietaire}:(OI)(CI)RX") },
    @{ Dossier = $AcpProgramData; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)R') },
    @{ Dossier = $DossierQuotas; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)R', "*${sidProprietaire}:(OI)(CI)M") },
    @{ Dossier = $DossierDepots; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)M') },
    @{ Dossier = $DossierEspaces; Droits = @("*${SID_ADMINISTRATEURS}:(OI)(CI)F", "*${SID_SYSTEME}:(OI)(CI)F", 'COMPTE:(OI)(CI)M') }
)
foreach ($entree in $plan) {
    $droits = $entree.Droits | ForEach-Object { $_ -replace '^COMPTE:', "*${sidCompte}:" }
    Faire "$($entree.Dossier) : $($droits -join ' ')" {
        New-Item -ItemType Directory -Force -Path $entree.Dossier | Out-Null
        Acl-Dossier $entree.Dossier $droits
    }
}

# ============================================================ 4. poste sans venv
Etape 4 'poste installé sans venv (python -I, bibliothèques sous Program Files)'
$verrou = Join-Path $Depot 'requirements\poste-3.12.lock.txt'
Faire "pip install --no-deps --require-hashes --only-binary=:all: -r requirements\poste-3.12.lock.txt --target $DossierLib" {
    & $Python -I -m pip install --no-deps --require-hashes --only-binary=:all: --no-input --disable-pip-version-check `
        -r $verrou --target $DossierLib
    if ($LASTEXITCODE -ne 0) { throw "pip a refusé le verrou d'exécution du poste (code $LASTEXITCODE)." }
}
Faire "copie des sources acp_poste et acp_poste_contrat (sans __pycache__) dans $DossierLib, puis lancer.py, ligne_etat.py et acp-poste.cmd" {
    foreach ($source in @((Join-Path $Depot 'apps\poste\src\acp_poste'),
                          (Join-Path $Depot 'hermes\plugins\acp-poste\contrat\acp_poste_contrat'))) {
        $cible = Join-Path $DossierLib (Split-Path $source -Leaf)
        if (Test-Path -LiteralPath $cible) { Remove-Item -LiteralPath $cible -Recurse -Force }
        Copy-Item -LiteralPath $source -Destination $cible -Recurse
        Get-ChildItem -LiteralPath $cible -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $Depot 'packaging\poste\lancer.py') -Destination $Lanceur -Force
    Copy-Item -LiteralPath (Join-Path $Depot 'packaging\poste\ligne_etat.py') -Destination (Join-Path $DossierPoste 'ligne_etat.py') -Force
    $cmd = (Get-Content -LiteralPath (Join-Path $Depot 'packaging\poste\acp-poste.cmd.modele') -Raw).
        Replace('__PYTHON__', $Python).Replace('__LANCEUR__', $Lanceur)
    [IO.File]::WriteAllText($CommandePoste, ($cmd -replace "`r?`n", "`r`n"), (New-Object Text.ASCIIEncoding))
    $commit = (& git -C $Depot rev-parse HEAD 2>$null)
    Consigner @{ etape = 4; poste = 'sources copiées'; commit = "$commit"; lanceur = (Empreinte $Lanceur) }
}

# ============================================================ 5. binaires des CLI
Etape 5 'binaires de Codex et de Claude Code copiés depuis vos installations (décision D54)'
Faire "copie de $CodexSource vers $DossierOutils\codex et de claude.exe vers $DossierOutils\claude, SHA-256 consignés, --version relancé sur chaque copie" {
    $cibleCodex = Join-Path $DossierOutils 'codex'
    $cibleClaude = Join-Path $DossierOutils 'claude'
    if (Test-Path -LiteralPath $cibleCodex) { Remove-Item -LiteralPath $cibleCodex -Recurse -Force }
    Copy-Item -LiteralPath $CodexSource -Destination $cibleCodex -Recurse
    New-Item -ItemType Directory -Force -Path $cibleClaude | Out-Null
    Copy-Item -LiteralPath $ClaudeSource -Destination (Join-Path $cibleClaude 'claude.exe') -Force
    $copieCodex = Lire-VersionCli (Join-Path $cibleCodex 'bin\codex.exe') 'codex'
    $copieClaude = Lire-VersionCli (Join-Path $cibleClaude 'claude.exe') 'claude'
    if (-not $copieCodex) { throw "codex --version illisible sur la copie : l'exécutable ne démarre pas hors de son dossier d'installation." }
    if (-not $copieClaude) { throw "claude --version illisible sur la copie." }
    if ($copieCodex -ne $script:versionCodex -or $copieClaude -ne $script:versionClaude) {
        throw "la version d'une copie diffère de sa source (Codex $copieCodex, Claude Code $copieClaude) : une CLI a été mise à jour pendant l'installation ; relancez l'installeur."
    }
    Consigner @{ etape = 5; codex = (Empreinte (Join-Path $cibleCodex 'bin\codex.exe')); codex_version = $script:versionCodex;
                 aide_bac_a_sable = (Empreinte (Join-Path $cibleCodex 'codex-resources\codex-windows-sandbox-setup.exe'));
                 claude = (Empreinte (Join-Path $cibleClaude 'claude.exe')); claude_version = $script:versionClaude }
    Write-Host "  Codex $($script:versionCodex), Claude Code $($script:versionClaude) : à confirmer par vous dans poste.toml (version_testee)."
}

# ============================================================ 6. poste.toml
Etape 6 "poste.toml ($Politique), jamais remplacé s'il existe"
$modele = Get-Content -LiteralPath (Join-Path $Depot 'packaging\poste\poste.toml.modele') -Raw -Encoding UTF8
$contenu = $modele.Replace('__ORIGINE__', $Origine.TrimEnd('/')).Replace('__PROGRAMFILES_ACP__', $AcpProgramFiles).
    Replace('__PROGRAMDATA_ACP__', $AcpProgramData).Replace('__VERSION_CODEX__', $versionCodex).
    Replace('__VERSION_CLAUDE__', $versionClaude).Replace('__PROFIL_PROPRIETAIRE__', $ProfilProprietaire)
if (Test-Path -LiteralPath $Politique) {
    $differences = @(Differences-Politique $Politique $contenu)
    if ($differences.Count -eq 0) {
        Write-Host '  poste.toml existe déjà : rien n''est écrit ; il est identique au modèle rempli.'
    } else {
        Write-Host ("  poste.toml existe déjà : rien n'est écrit. {0} ligne(s) diffèrent du modèle rempli (<= votre fichier, => le modèle) :" -f $differences.Count)
        $differences | ForEach-Object { Write-Host ("    {0} {1}" -f $_.SideIndicator, $_.InputObject) }
    }
    foreach ($ecart in @(Ecarts-VersionTestee $Politique @{ codex = $versionCodex; claude = $versionClaude })) {
        Write-Host "  ATTENTION : $ecart"
    }
} else {
    $lignes = ($contenu -split "`n").Count
    Faire "écriture de poste.toml ($lignes lignes, UTF-8 sans BOM, droits hérités : Administrateurs et SYSTEM en écriture, $Compte en lecture)" {
        Ecrire-Sans-BOM $Politique ($contenu -replace "`r`n", "`n")
    }
}

# ============================================================ 7. tâche planifiée
Etape 7 "tâche planifiée $CheminTache$Tache"
$xml = (Get-Content -LiteralPath (Join-Path $Depot 'packaging\poste\tache-poste.xml.modele') -Raw -Encoding UTF8).
    Replace('__PYTHON__', [Security.SecurityElement]::Escape($Python)).
    Replace('__LANCEUR__', [Security.SecurityElement]::Escape($Lanceur)).
    Replace('__DOSSIER_TRAVAIL__', [Security.SecurityElement]::Escape($AcpProgramData)).
    Replace('__SID_COMPTE__', $sidCompte)
Write-Host "  Action : `"$Python`" -I `"$Lanceur`" servir ; au démarrage (retard 1 min) et garde toutes les 15 min sans fin ; « ignorer la nouvelle » ; durée illimitée ; niveau limité ; mot de passe enregistré."
Faire "Register-ScheduledTask -TaskPath '$CheminTache' -TaskName '$Tache' -User $Compte (mot de passe converti le temps de l'appel)" {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($motDePasse)
    try {
        Register-ScheduledTask -TaskPath $CheminTache -TaskName $Tache -Xml $xml -User $Compte `
            -Password ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)) -Force | Out-Null
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

# ============================================================ 8. options système (sur confirmation)
Etape 8 'options système, chacune sur confirmation explicite (décision D57)'
$options = @(
    @{ Question = 'Couper le démarrage rapide (HiberbootEnabled = 0) ? Sans cela, un « arrêt » peut ne pas relancer la tâche au démarrage.';
       Action = { Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -Value 0 -Type DWord } },
    @{ Question = 'Veille jamais sur secteur (powercfg /change standby-timeout-ac 0) ? Sinon chaque veille de plus de 3 min notifie « Poste hors ligne ».';
       Action = { & powercfg.exe /change standby-timeout-ac 0 } },
    @{ Question = "Masquer $Compte de l'écran d'accueil ?";
       Action = {
           # Clé créée seulement si elle manque ; les valeurs déjà présentes (comptes CodexSandbox*) restent.
           Masquer-CompteAccueil $CleComptesMasques $Compte } }
)
foreach ($option in $options) {
    if ($Simulation) {
        Write-Host "  [simulation, aucune question posée] $($option.Question)"
        continue
    }
    $reponse = Read-Host "$($option.Question) [o/N]"
    if ($reponse -match '^(o|oui)$') { & $option.Action; Write-Host '    appliqué.' } else { Write-Host '    laissé tel quel.' }
}

# ============================================================ 9. vérifications finales
Etape 9 'vérifications finales et gestes manuels restants'
Faire "schtasks /Query /TN `"$CheminTache$Tache`" /V /FO LIST, droits d'ouverture de session du compte (secedit /export /areas USER_RIGHTS)" {
    & schtasks.exe /Query /TN "$CheminTache$Tache" /V /FO LIST | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "la tâche planifiée est illisible après son enregistrement." }
    $export = Join-Path ([IO.Path]::GetTempPath()) ('acp-droits-' + [Guid]::NewGuid().ToString('N') + '.inf')
    try {
        & secedit.exe /export /areas USER_RIGHTS /cfg $export | Out-Null
        $droits = Get-Content -LiteralPath $export -Encoding Unicode
    } finally {
        Remove-Item -LiteralPath $export -Force -ErrorAction SilentlyContinue
    }
    $ligne = { param($nom) ($droits | Where-Object { $_ -match "^$nom\s*=" }) -join '' }
    if ((& $ligne 'SeBatchLogonRight') -notmatch [Regex]::Escape("*$sidCompte")) {
        Write-Host "  ATTENTION : $Compte n'a pas le droit « Ouvrir une session en tant que tâche » : la tâche ne démarrera pas."
    }
    foreach ($refus in @('SeDenyBatchLogonRight', 'SeDenyInteractiveLogonRight')) {
        if ((& $ligne $refus) -match [Regex]::Escape("*$sidCompte")) {
            Write-Host "  ATTENTION : $Compte figure dans $refus (runas ou la tâche échoueront)."
        }
    }
    Consigner @{ etape = 9; tache = "$CheminTache$Tache"; verifie = $true }
}
Write-Host ''
Write-Host 'Gestes manuels restants (vous seul, apps/poste/README.md) :'
Write-Host "  c. console du compte : runas /user:$Compte `"powershell -NoProfile`""
Write-Host '  d0. activer la « connexion par code d''appareil » dans les réglages de sécurité de votre compte ChatGPT'
Write-Host "  d. $(Commande-Poste $CommandePoste 'connexion codex')   (codex login --device-auth, dans la console du compte)"
Write-Host "  e. claude setup-token (dans VOTRE session), puis $(Commande-Poste $CommandePoste 'connexion claude') (collage masqué)"
Write-Host "  f. $(Commande-Poste $CommandePoste 'connexion bac-a-sable')   (UAC : identifiants administrateur)"
Write-Host "  g0. $(Commande-Poste $CommandePoste 'diagnostic --reseau')"
Write-Host "  g. page Poste, section « Enrôler un poste » : « Générer un code d'enrôlement » ; $(Commande-Poste $CommandePoste 'enroler') ; comparer l'empreinte ; « Confirmer le poste »"
Write-Host "  h. Start-ScheduledTask -TaskPath '$CheminTache' -TaskName '$Tache' (ou redémarrer)"
Write-Host "  i. facultatif : ligne d'état de vos sessions Claude Code vers $DossierQuotas\claude-code.json"

if ($Simulation) {
    Write-Host ''
    if ($script:Refus.Count -gt 0) {
        Write-Host ("Simulation terminée : {0} refus ; rien n'a été écrit." -f $script:Refus.Count)
        exit 2
    }
    Write-Host "Simulation terminée : aucun refus ; rien n'a été écrit."
    exit 0
}
Write-Host ''
Write-Host 'Installation terminée.'
exit 0
