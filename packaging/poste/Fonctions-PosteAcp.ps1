#Requires -Version 5.1
<#
.SYNOPSIS
    Fonctions communes de l'installeur et du désinstalleur du poste ACP (relecture de P5).

.DESCRIPTION
    Chargé par « . (Join-Path $PSScriptRoot 'Fonctions-PosteAcp.ps1') » dans Installer-PosteAcp.ps1 et
    Desinstaller-PosteAcp.ps1. Chaque fonction est éprouvée par packaging/poste/tests/Test-InstallationPoste.ps1 sur des
    clés de registre et des dossiers JETABLES (jamais sur les vrais réglages du PC). Aucune fonction n'écrit hors de
    ce qu'on lui désigne ; aucune ne lit d'identifiant.
#>

Set-StrictMode -Version 3

# Clé des comptes masqués de l'écran d'accueil. Elle porte AUSSI les comptes masqués par d'autres logiciels (Codex y
# masque CodexSandboxOffline et CodexSandboxOnline) : jamais remplacée, jamais supprimée.
$CleComptesMasques = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'

# Claude Code : --restricted exige 2.1.248 (politique.py, VERSION_CLAUDE_MINIMALE) ; en dessous de 2.1.280, le poste
# publie les alias sans résolution ni efforts et la voie poste-claude est refusée au routage (catalogue_claude.py,
# PLAGE_MINIMALE).
$VersionClaudeMinimale = [version]'2.1.248'
$VersionClaudeRoutage = [version]'2.1.280'

# Groupes dont le compte du poste sera membre (Tout le monde, Utilisateurs authentifiés, Utilisateurs, BATCH pour la
# tâche planifiée, INTERACTIF pour la console runas, LOCAL, Compte local) : un droit d'écriture accordé à l'un d'eux
# vaut pour lui.
$SidsDuComptePoste = @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545', 'S-1-5-3', 'S-1-5-4', 'S-1-2-0', 'S-1-5-113')

# Droits par lesquels un compte modifie, remplace ou réautorise un fichier ou un dossier : mêmes droits que
# acp_poste.politique (FILE_ADD_FILE = écriture de données, FILE_ADD_SUBDIRECTORY = ajout de données, DELETE,
# WRITE_DAC, WRITE_OWNER), plus suppression d'enfants et droits génériques.
$MasqueEcriture = [int64](0x2 -bor 0x4 -bor 0x40 -bor 0x10000 -bor 0x40000 -bor 0x80000 -bor 0x10000000 -bor 0x40000000)

function Masquer-CompteAccueil([string] $Cle, [string] $Compte) {
    # « New-Item -Force » sur une clé EXISTANTE la remplace par une clé vide (documentation de New-Item, exemple 9) :
    # les comptes CodexSandbox* réapparaîtraient sur l'écran d'accueil. La clé n'est créée que si elle manque ; seule
    # la valeur du compte du poste est posée.
    if (-not (Test-Path -LiteralPath $Cle)) {
        New-Item -Path $Cle -Force | Out-Null
    }
    New-ItemProperty -LiteralPath $Cle -Name $Compte -Value 0 -PropertyType DWord -Force | Out-Null
}

function Retirer-CompteAccueil([string] $Cle, [string] $Compte) {
    # Seule la valeur du compte du poste est retirée ; la clé reste (elle porte les comptes masqués par d'autres).
    # Rend vrai si une valeur a été retirée.
    if (-not (Test-Path -LiteralPath $Cle)) { return $false }
    if (@((Get-Item -LiteralPath $Cle).GetValueNames()) -notcontains $Compte) { return $false }
    Remove-ItemProperty -LiteralPath $Cle -Name $Compte
    return $true
}

function Lignes-Politique([string] $Texte) {
    # Lignes d'un poste.toml, fins de ligne normalisées, lignes vides finales retirées (le modèle rempli finit par un
    # saut de ligne : ce n'est pas une différence).
    # Rend un tableau (à envelopper par @() chez l'appelant : PowerShell déroule les tableaux rendus).
    $lignes = @(($Texte -replace "`r`n", "`n") -split "`n")
    $fin = $lignes.Count
    while ($fin -gt 0 -and $lignes[$fin - 1] -eq '') { $fin-- }
    if ($fin -eq 0) { return @() }
    return $lignes[0..($fin - 1)]
}

function Differences-Politique([string] $Chemin, [string] $Contenu) {
    # poste.toml existant comparé au modèle rempli. Lu en UTF-8 EXPLICITE : sous Windows PowerShell 5.1,
    # Get-Content sans -Encoding lit un fichier UTF-8 sans BOM en ANSI et signalait chaque ligne accentuée.
    $existant = @(Lignes-Politique ([IO.File]::ReadAllText($Chemin, (New-Object Text.UTF8Encoding $false))))
    $attendu = @(Lignes-Politique $Contenu)
    if ($existant.Count -eq 0 -or $attendu.Count -eq 0) {
        # Compare-Object refuse une collection vide : chaque ligne de l'autre côté est une différence.
        return @(@($existant | ForEach-Object { [pscustomobject]@{ SideIndicator = '<='; InputObject = $_ } }) +
                 @($attendu | ForEach-Object { [pscustomobject]@{ SideIndicator = '=>'; InputObject = $_ } }))
    }
    return @(Compare-Object -ReferenceObject $existant -DifferenceObject $attendu -SyncWindow ([Math]::Max($existant.Count, $attendu.Count)))
}

function Version-Testee([string] $Chemin, [string] $Section) {
    # Valeur de version_testee dans la section [codex] ou [claude] de poste.toml (lecture simple, sans évaluer le
    # TOML : seule une ligne « version_testee = "X.Y.Z" » est reconnue) ; $null si absente.
    $courante = ''
    foreach ($ligne in [IO.File]::ReadAllLines($Chemin, (New-Object Text.UTF8Encoding $false))) {
        if ($ligne -match '^\s*\[([^\]]+)\]') { $courante = $Matches[1].Trim(); continue }
        if ($courante -eq $Section -and $ligne -match '^\s*version_testee\s*=\s*"([^"]*)"') { return $Matches[1] }
    }
    return $null
}

function Ecarts-VersionTestee([string] $Chemin, [hashtable] $Versions) {
    # Messages en français pour chaque CLI dont la version installée diffère de version_testee : poste.toml n'est
    # jamais remplacé, c'est au propriétaire de l'éditer (éditeur élevé).
    $messages = @()
    foreach ($section in @('codex', 'claude')) {
        $lue = $Versions[$section]
        if (-not $lue -or $lue -notmatch '^\d+\.\d+\.\d+$') { continue }
        $testee = Version-Testee $Chemin $section
        if ($testee -ne $lue) {
            $messages += ("[{0}] version_testee vaut « {1} » ; la copie installée est en {2} : mettez version_testee à jour " +
                          'dans poste.toml (éditeur lancé en administrateur), sinon le poste la déclare hors version.') -f
                         $section, $testee, $lue
        }
    }
    return $messages
}

function Lire-VersionCli([string] $Executable, [string] $Cli) {
    # « --version » d'une CLI dans un profil jetable vide (CODEX_HOME ou CLAUDE_CONFIG_DIR, mises à jour coupées),
    # sortie d'erreur jetée : Codex y avertit en anglais qu'il ne crée pas d'assistants dans un dossier temporaire.
    # Rend « X.Y.Z » ou $null (exécutable qui ne démarre pas, sortie illisible).
    $vide = Join-Path ([IO.Path]::GetTempPath()) ('acp-version-' + [Guid]::NewGuid().ToString('N'))
    $noms = @('CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'DISABLE_UPDATES', 'DISABLE_AUTOUPDATER')
    $sauves = @{}
    foreach ($nom in $noms) { $sauves[$nom] = [Environment]::GetEnvironmentVariable($nom, 'Process') }
    $sortie = ''
    try {
        New-Item -ItemType Directory -Path $vide | Out-Null
        if ($Cli -eq 'codex') {
            [Environment]::SetEnvironmentVariable('CODEX_HOME', $vide, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable('CLAUDE_CONFIG_DIR', $vide, 'Process')
            [Environment]::SetEnvironmentVariable('DISABLE_UPDATES', '1', 'Process')
            [Environment]::SetEnvironmentVariable('DISABLE_AUTOUPDATER', '1', 'Process')
        }
        # Portée locale : sous Windows PowerShell 5.1, une sortie d'erreur redirigée devient une erreur terminante
        # quand $ErrorActionPreference vaut Stop.
        $ErrorActionPreference = 'Continue'
        $sortie = "$(& $Executable --version 2>$null | Select-Object -First 1)"
    } catch {
        $sortie = ''
    } finally {
        foreach ($nom in $noms) { [Environment]::SetEnvironmentVariable($nom, $sauves[$nom], 'Process') }
        Remove-Item -LiteralPath $vide -Recurse -Force -ErrorAction SilentlyContinue
    }
    $version = ($sortie -replace '^codex-cli\s+', '' -replace '\s*\(Claude Code\)\s*$', '').Trim()
    if ($version -match '^\d+\.\d+\.\d+$') { return $version }
    return $null
}

function Verdict-VersionClaude([string] $Version) {
    # @{ Refus = '…' }, @{ Avertissement = '…' } ou @{} : refus sous 2.1.248, avertissement sous 2.1.280.
    if (-not $Version) {
        return @{ Refus = "claude.exe --version illisible : l'exécutable désigné par -ClaudeSource ne démarre pas." }
    }
    $lue = [version]$Version
    if ($lue -lt $VersionClaudeMinimale) {
        return @{ Refus = ("Claude Code {0} est antérieur à {1} (option --restricted exigée par le poste) : mettez-le à jour " +
                           '(« claude update » dans votre session), puis relancez l''installeur.') -f $Version, $VersionClaudeMinimale }
    }
    if ($lue -lt $VersionClaudeRoutage) {
        return @{ Avertissement = ("Claude Code {0} est antérieur à {1} : le poste publiera ses alias sans modèle ni " +
                                   'efforts, et la voie poste-claude sera refusée au routage. Mettez-le à jour.') -f
                                  $Version, $VersionClaudeRoutage }
    }
    return @{}
}

function Droits-Ecriture-Pour([string] $Chemin, [string[]] $Sids) {
    # Droits d'écriture (masque ci-dessus) accordés sur $Chemin LUI-MÊME à l'un des $Sids : ACE d'autorisation
    # effectives (explicites ou héritées), hors ACE « héritage seulement ». Rend la liste « SID : droits ». Une ACE de
    # refus n'est pas déduite (prudence : un refus éventuel ne fait pas accepter).
    $obtenus = @()
    $acl = Get-Acl -LiteralPath $Chemin
    foreach ($ace in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($ace.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
        if ($ace.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) { continue }
        $sid = $ace.IdentityReference.Value
        if ($Sids -notcontains $sid) { continue }
        if (([int64]$ace.FileSystemRights -band $MasqueEcriture) -ne 0) {
            $obtenus += "${sid} : $($ace.FileSystemRights)"
        }
    }
    return $obtenus
}

function Cibles-Interpreteur([string] $Python) {
    # python.exe, son dossier, Lib, Lib\site-packages et DLLs (disposition de python.org) : ce que « python -I »
    # exécute ou importe, fichiers .pth de site-packages compris.
    $dossier = Split-Path -Parent $Python
    $cibles = @($Python, $dossier)
    foreach ($relatif in @('Lib', 'Lib\site-packages', 'DLLs')) {
        $chemin = Join-Path $dossier $relatif
        if (Test-Path -LiteralPath $chemin) { $cibles += $chemin }
    }
    return $cibles
}

function Interpreteur-Modifiable([string] $Python, [string[]] $Sids) {
    # Liste « chemin (SID : droits) » des cibles de l'interpréteur que le compte du poste pourrait modifier (décision
    # D67) ; vide si aucune.
    $obtenus = @()
    foreach ($cible in (Cibles-Interpreteur $Python)) {
        foreach ($droit in (Droits-Ecriture-Pour $cible $Sids)) { $obtenus += "$cible ($droit)" }
    }
    return $obtenus
}

function Commande-Poste([string] $CommandePoste, [string] $Arguments) {
    # Forme EXÉCUTABLE dans la console du compte (runas … "powershell -NoProfile") : le dossier du poste n'est dans
    # aucun PATH, et un chemin entre guillemets sans l'opérateur & est une erreur d'analyse (décision D68).
    return "& '$CommandePoste' $Arguments"
}
