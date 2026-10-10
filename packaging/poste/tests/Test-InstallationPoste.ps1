#Requires -Version 5.1
<#
.SYNOPSIS
    Éprouve l'installeur et le désinstalleur du poste EN SIMULATION SEULEMENT (cahier P5 § 8.1, § 14.1), et leurs
    fonctions communes sur des clés et des dossiers JETABLES (relecture de P5).

.DESCRIPTION
    Aucun compte, aucune tâche, aucun dossier ni réglage du PC n'est créé : chaque cas lance
    Installer-PosteAcp.ps1 -Simulation (ou Desinstaller-PosteAcp.ps1 -Simulation) et vérifie
      - le plan imprimé (les neuf étapes, les refus en français, le code de sortie) ;
      - que l'état du PC est IDENTIQUE avant et après : C:\Program Files\ACP, C:\ProgramData\ACP, C:\ACP, le compte
        local acp-poste, les tâches planifiées sous \ACP\, les comptes masqués de l'écran d'accueil.
    Les sources de Codex et de Claude sont de FAUSSES CLI compilées ici (csc du .NET Framework) : elles ne font que
    répondre à « --version » avec la version demandée par le cas (et écrire un avertissement sur leur sortie d'erreur).

    Fonctions-PosteAcp.ps1 est éprouvé directement : clé UserList JETABLE sous HKCU:\Software\ACP-test-<guid> (une
    valeur déjà présente doit survivre), poste.toml jetable (aucune fausse différence sous Windows PowerShell 5.1),
    droits d'un dossier jetable, forme exécutable des commandes.

    Le cas « installation acceptée » exige un Python 3.12 installé « pour tous les utilisateurs » (hors de tout profil,
    hors WindowsApps) et non modifiable par le compte du poste : celui de -Python, sinon celui du PATH. Faute d'en
    trouver un, le cas est déclaré IGNORÉ (jamais compté réussi) ; en CI (windows-2022), une copie du Python de
    setup-python sous Program Files convient.

    -ExigerInstallationAcceptee (CI) : le cas « installation acceptée » ignoré compte comme un échec.

    Code de sortie : 0 si aucun échec, 1 sinon.
#>
[CmdletBinding()]
param(
    [string] $Python = '',
    [switch] $ExigerInstallationAcceptee
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false

$Ici = Split-Path -Parent $MyInvocation.MyCommand.Path
$Depot = (Resolve-Path (Join-Path $Ici '..\..\..')).Path
$Installeur = Join-Path $Depot 'packaging\poste\Installer-PosteAcp.ps1'
$Desinstalleur = Join-Path $Depot 'packaging\poste\Desinstaller-PosteAcp.ps1'
. (Join-Path $Depot 'packaging\poste\Fonctions-PosteAcp.ps1')
$Hote = (Get-Process -Id $PID).Path
Write-Host "Hôte : $Hote ($($PSVersionTable.PSVersion))"
$script:Reussis = 0
$script:Ignores = 0
$script:Echecs = New-Object System.Collections.Generic.List[string]

function Etat-Du-PC {
    $programFiles = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'ACP'
    $programData = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'ACP'
    $racine = Join-Path $env:SystemDrive 'ACP'
    $compte = Get-CimInstance -ClassName Win32_UserAccount -Filter "LocalAccount=True AND Name='acp-poste'" -ErrorAction SilentlyContinue
    $taches = @(Get-ScheduledTask -TaskPath '\ACP\' -ErrorAction SilentlyContinue | ForEach-Object { $_.TaskName })
    $comptes = @(Get-CimInstance -ClassName Win32_UserAccount -Filter 'LocalAccount=True' | ForEach-Object { $_.Name }) | Sort-Object
    $masques = ''
    if (Test-Path -LiteralPath $CleComptesMasques) {
        $cle = Get-Item -LiteralPath $CleComptesMasques
        $masques = (@($cle.GetValueNames() | Sort-Object | ForEach-Object { "$_=$($cle.GetValue($_))" }) -join ',')
    }
    return ('pf={0};pd={1};acp={2};compte={3};taches={4};comptes={5};masques={6}' -f (Test-Path $programFiles),
            (Test-Path $programData), (Test-Path $racine), [bool]$compte, ($taches -join ','), ($comptes -join ','), $masques)
}

function Verifier([string] $Nom, [bool] $Condition, [string] $Detail = '') {
    if ($Condition) {
        $script:Reussis++
        Write-Host "  OK      $Nom"
    } else {
        $script:Echecs.Add("$Nom $Detail")
        Write-Host "  ÉCHEC   $Nom $Detail"
    }
}

function Lancer([string] $Script, [string[]] $Arguments) {
    $sortie = & $Hote -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Script @Arguments 2>&1 | Out-String
    return @{ Code = $LASTEXITCODE; Sortie = $sortie }
}

function Sans-Erreur-D-Analyse([string] $Code) {
    $erreurs = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($Code, [ref]$null, [ref]$erreurs)
    return (@($erreurs).Count -eq 0)
}

$temporaire = Join-Path ([IO.Path]::GetTempPath()) ('acp-test-installation-' + [Guid]::NewGuid().ToString('N'))
$codex = Join-Path $temporaire 'codex'
$claude = Join-Path $temporaire 'claude'
$cleJetable = 'HKCU:\Software\ACP-test-' + [Guid]::NewGuid().ToString('N')
$pythonModifiable = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) ('acp-test-python-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path (Join-Path $codex 'bin'), (Join-Path $codex 'codex-resources'), $claude | Out-Null
[IO.File]::WriteAllBytes((Join-Path $codex 'codex-resources\codex-windows-sandbox-setup.exe'), [byte[]]@())

# Fausse CLI : répond à « --version » (version lue dans version.txt à côté d'elle) et écrit un avertissement sur sa
# sortie d'erreur, comme Codex sous un dossier temporaire. Compilée par csc du .NET Framework (présent sur Windows 10,
# 11 et windows-2022).
$sourceFausse = Join-Path $temporaire 'FausseCli.cs'
[IO.File]::WriteAllText($sourceFausse, @'
using System;
using System.IO;
class FausseCli {
    static int Main(string[] args) {
        if (args.Length != 1 || args[0] != "--version") { Console.Error.WriteLine("fausse CLI : seul --version"); return 3; }
        string dossier = AppDomain.CurrentDomain.BaseDirectory;
        string version = File.ReadAllText(Path.Combine(dossier, "version.txt")).Trim();
        Console.Error.WriteLine("WARNING: avertissement de test sur la sortie d'erreur");
        string nom = Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]).ToLowerInvariant();
        if (nom == "codex") { Console.WriteLine("codex-cli " + version); } else { Console.WriteLine(version + " (Claude Code)"); }
        return 0;
    }
}
'@)
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$fausseCli = Join-Path $temporaire 'FausseCli.exe'
& $csc /nologo /target:exe "/out:$fausseCli" $sourceFausse | Out-Null
if ($LASTEXITCODE -ne 0) { throw "csc n'a pas compilé la fausse CLI (code $LASTEXITCODE)." }

function Fausses-Cli([string] $VersionCodex, [string] $VersionClaude) {
    # $VersionCodex vide : codex.exe est un fichier vide, qui ne démarre pas.
    if ($VersionCodex) {
        Copy-Item -LiteralPath $fausseCli -Destination (Join-Path $codex 'bin\codex.exe') -Force
        [IO.File]::WriteAllText((Join-Path $codex 'bin\version.txt'), $VersionCodex)
    } else {
        [IO.File]::WriteAllBytes((Join-Path $codex 'bin\codex.exe'), [byte[]]@())
    }
    Copy-Item -LiteralPath $fausseCli -Destination (Join-Path $claude 'claude.exe') -Force
    [IO.File]::WriteAllText((Join-Path $claude 'version.txt'), $VersionClaude)
}

$profils = [Environment]::ExpandEnvironmentVariables(
    (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList').ProfilesDirectory)

function Arguments([string] $PythonDuCas, [string] $Origine = 'https://hermes-acp.test') {
    return @('-Origine', $Origine, '-Python', $PythonDuCas, '-Depot', $Depot, '-CodexSource', $codex,
             '-ClaudeSource', (Join-Path $claude 'claude.exe'), '-ProfilProprietaire', $temporaire, '-Simulation')
}

function Neuf-Etapes([string] $Sortie) {
    foreach ($n in 1..9) { if ($Sortie -notmatch "tape $n/9 :") { return $false } }
    return $true
}

try {
    $avant = Etat-Du-PC
    Write-Host "État du PC avant : $avant"
    if (-not $Python) {
        $trouve = Get-Command python -ErrorAction SilentlyContinue
        if ($trouve) { $Python = $trouve.Source }
    }
    $admissible = $false
    $raison = "aucun Python 3.12 « tous utilisateurs » sur ce PC (celui du PATH est sous un profil, dans WindowsApps ou d'une autre version)"
    if ($Python -and (Test-Path -LiteralPath $Python) -and $Python -notmatch '\\WindowsApps\\' -and
        -not ([IO.Path]::GetFullPath($Python).StartsWith($profils.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) {
        if (@(Interpreteur-Modifiable $Python $SidsDuComptePoste).Count -gt 0) {
            $raison = "le Python désigné ($Python) est modifiable par les groupes du compte du poste"
        } else {
            $admissible = ((& $Python -I -c "import sys; print('%d.%d' % sys.version_info[:2])") -eq '3.12')
        }
    }
    $pythonDesCas = $(if ($admissible) { $Python } else { 'C:\Absent\python.exe' })

    # ------------------------------------------------------------------ cas 1 : installation acceptée
    Write-Host ''
    Write-Host 'Cas 1 : installation acceptée (Python 3.12 « tous utilisateurs », Codex 0.156.1, Claude Code 2.1.280)'
    Fausses-Cli '0.156.1' '2.1.280'
    if ($admissible) {
        $r = Lancer $Installeur (Arguments $Python)
        Verifier 'code de sortie 0' ($r.Code -eq 0) "(code $($r.Code))"
        Verifier 'neuf étapes imprimées' (Neuf-Etapes $r.Sortie)
        Verifier 'aucun refus' ($r.Sortie -match 'Simulation terminée : aucun refus')
        Verifier 'versions lues sur les sources' ($r.Sortie -match 'Codex \(source\) : 0\.156\.1' -and $r.Sortie -match 'Claude Code \(source\) : 2\.1\.280')
        Verifier 'sortie d''erreur des CLI jetée (aucun avertissement anglais)' ($r.Sortie -notmatch 'avertissement de test')
        Verifier 'aucun avertissement de version' ($r.Sortie -notmatch 'ATTENTION : Claude Code')
        Verifier 'tâche planifiée décrite' ($r.Sortie -match 'garde toutes les 15 min')
        Verifier 'groupes désignés par SID' ($r.Sortie -match '\*S-1-5-32-544:\(OI\)\(CI\)F')
        $commandes = @([regex]::Matches($r.Sortie, "& '[^'\r\n]+acp-poste\.cmd' [a-z][a-z -]*[a-z]") | ForEach-Object { $_.Value })
        Verifier 'cinq commandes du compte imprimées sous la forme « & ''…\acp-poste.cmd'' … »' ($commandes.Count -eq 5) "($($commandes.Count))"
        Verifier 'chaque commande imprimée s''analyse sans erreur' (@($commandes | Where-Object { -not (Sans-Erreur-D-Analyse $_) }).Count -eq 0)
        Verifier 'aucune commande entre guillemets sans &' ($r.Sortie -notmatch '"[^"\r\n]*acp-poste\.cmd" ')
        Verifier 'libellés de la page Poste' ($r.Sortie -match "« Générer un code d'enrôlement »" -and $r.Sortie -match '« Confirmer le poste »')
        Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)
        if ($script:Echecs.Count -gt 0) { Write-Host $r.Sortie }
    } elseif ($ExigerInstallationAcceptee) {
        Verifier 'cas « installation acceptée » exigé' $false "($raison)"
    } else {
        $script:Ignores++
        Write-Host "  IGNORÉ  $raison : le cas est prouvé sur windows-2022."
    }

    # ------------------------------------------------------------------ cas 2 : Python du Microsoft Store
    Write-Host ''
    Write-Host 'Cas 2 : Python de WindowsApps refusé'
    $r = Lancer $Installeur (Arguments (Join-Path $profils 'quelquun\AppData\Local\Microsoft\WindowsApps\python.exe'))
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus WindowsApps en français' ($r.Sortie -match 'Python du Microsoft Store \(WindowsApps\) refusé')
    Verifier 'neuf étapes imprimées malgré le refus' (Neuf-Etapes $r.Sortie)
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 3 : Python sous un profil
    Write-Host ''
    Write-Host 'Cas 3 : Python « pour moi seul » (sous un profil) refusé'
    $r = Lancer $Installeur (Arguments (Join-Path $profils 'quelquun\AppData\Local\Programs\Python\Python312\python.exe'))
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus « pour tous les utilisateurs »' ($r.Sortie -match 'Installez Python 3\.12 de python\.org pour tous les utilisateurs')
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 4 : origine HTTP
    Write-Host ''
    Write-Host 'Cas 4 : origine sans HTTPS refusée'
    $r = Lancer $Installeur (Arguments $pythonDesCas 'http://hermes-acp.test')
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus de l''origine en français' ($r.Sortie -match 'Origine doit être une origine HTTPS')
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 5 : désinstallation à blanc
    Write-Host ''
    Write-Host 'Cas 5 : désinstallation en simulation'
    $r = Lancer $Desinstalleur @('-Simulation')
    Verifier 'code de sortie 0' ($r.Code -eq 0) "(code $($r.Code))"
    Verifier 'rappel de la révocation' ($r.Sortie -match 'révoquez le poste sur la page Poste')
    Verifier 'rappel de la ligne d''état (statusLine)' ($r.Sortie -match 'statusLine')
    Verifier 'espaces de travail et écran d''accueil traités' ($r.Sortie -match 'espaces' -and $r.Sortie -match "Écran d'accueil")
    Verifier 'rien supprimé' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 6 : Claude Code trop ancien
    Write-Host ''
    Write-Host 'Cas 6 : Claude Code 2.1.239 refusé dès la simulation (--restricted exige 2.1.248)'
    Fausses-Cli '0.156.1' '2.1.239'
    $r = Lancer $Installeur (Arguments $pythonDesCas)
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus de version en français' ($r.Sortie -match 'REFUS : Claude Code 2\.1\.239 est antérieur à 2\.1\.248')
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 7 : Claude Code sous 2.1.280
    Write-Host ''
    Write-Host 'Cas 7 : Claude Code 2.1.250 admis avec un avertissement (voie refusée au routage sous 2.1.280)'
    Fausses-Cli '0.156.1' '2.1.250'
    $r = Lancer $Installeur (Arguments $pythonDesCas)
    Verifier 'avertissement du routage' ($r.Sortie -match 'ATTENTION : Claude Code 2\.1\.250 est antérieur à 2\.1\.280.*refusée au routage')
    Verifier 'aucun refus de version' ($r.Sortie -notmatch 'REFUS : Claude Code')
    if ($admissible) { Verifier 'code de sortie 0' ($r.Code -eq 0) "(code $($r.Code))" }
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 8 : Codex qui ne démarre pas
    Write-Host ''
    Write-Host 'Cas 8 : codex.exe illisible refusé dès la simulation'
    Fausses-Cli '' '2.1.280'
    $r = Lancer $Installeur (Arguments $pythonDesCas)
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus en français' ($r.Sortie -match 'REFUS : codex\.exe --version illisible')
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 9 : Python modifiable par les Utilisateurs
    Write-Host ''
    Write-Host 'Cas 9 : Python dans un dossier où les Utilisateurs peuvent écrire refusé (décision D67)'
    New-Item -ItemType Directory -Path $pythonModifiable | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $pythonModifiable 'python.exe'), [byte[]]@())
    Fausses-Cli '0.156.1' '2.1.280'
    $r = Lancer $Installeur (Arguments (Join-Path $pythonModifiable 'python.exe'))
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus « Python modifiable » en français' ($r.Sortie -match 'REFUS : Python modifiable par le compte acp-poste ou l''un de ses groupes')
    Remove-Item -LiteralPath $pythonModifiable -Recurse -Force
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 10 : fonctions communes, objets jetables
    Write-Host ''
    Write-Host "Cas 10 : comptes masqués de l'écran d'accueil (clé jetable $cleJetable)"
    $cle = Join-Path $cleJetable 'SpecialAccounts\UserList'
    Masquer-CompteAccueil $cle 'acp-poste'
    Verifier 'clé absente : créée (parents compris) avec la seule valeur du poste' (
        (Test-Path -LiteralPath $cle) -and ((@((Get-Item -LiteralPath $cle).GetValueNames()) -join ',') -eq 'acp-poste'))
    Remove-Item -LiteralPath $cle -Recurse -Force
    New-Item -Path $cle -Force | Out-Null
    foreach ($nom in @('CodexSandboxOffline', 'CodexSandboxOnline')) {
        New-ItemProperty -LiteralPath $cle -Name $nom -Value 0 -PropertyType DWord | Out-Null
    }
    Masquer-CompteAccueil $cle 'acp-poste'
    Masquer-CompteAccueil $cle 'acp-poste'
    $valeurs = (@((Get-Item -LiteralPath $cle).GetValueNames() | Sort-Object) -join ',')
    Verifier 'clé existante : les valeurs de Codex survivent (deux passages)' ($valeurs -eq 'acp-poste,CodexSandboxOffline,CodexSandboxOnline') "($valeurs)"
    Verifier 'désinstallation : retire la valeur du poste' (Retirer-CompteAccueil $cle 'acp-poste')
    $valeurs = (@((Get-Item -LiteralPath $cle).GetValueNames() | Sort-Object) -join ',')
    Verifier 'désinstallation : la clé et les valeurs de Codex restent' ($valeurs -eq 'CodexSandboxOffline,CodexSandboxOnline') "($valeurs)"
    Verifier 'désinstallation : rien à retirer la seconde fois' (-not (Retirer-CompteAccueil $cle 'acp-poste'))

    Write-Host ''
    Write-Host 'Cas 11 : poste.toml existant comparé au modèle rempli (UTF-8 sans BOM, LF, comme l''installeur l''écrit)'
    $modele = [IO.File]::ReadAllText((Join-Path $Depot 'packaging\poste\poste.toml.modele'), (New-Object Text.UTF8Encoding $false))
    $rempli = $modele.Replace('__ORIGINE__', 'https://hermes-acp.test').Replace('__PROGRAMFILES_ACP__', 'C:\Program Files\ACP').
        Replace('__PROGRAMDATA_ACP__', 'C:\ProgramData\ACP').Replace('__VERSION_CODEX__', '0.156.1').
        Replace('__VERSION_CLAUDE__', '2.1.280').Replace('__PROFIL_PROPRIETAIRE__', 'C:\Users\Proprietaire')
    $politique = Join-Path $temporaire 'poste.toml'
    [IO.File]::WriteAllText($politique, ($rempli -replace "`r`n", "`n"), (New-Object Text.UTF8Encoding $false))
    $differences = @(Differences-Politique $politique $rempli)
    Verifier "fichier identique : aucune différence (accents et ligne vide finale compris)" ($differences.Count -eq 0) "($($differences.Count))"
    Verifier 'versions identiques : aucun écart signalé' (@(Ecarts-VersionTestee $politique @{ codex = '0.156.1'; claude = '2.1.280' }).Count -eq 0)
    [IO.File]::WriteAllText($politique, (($rempli -replace "`r`n", "`n").Replace('version_testee = "2.1.280"', 'version_testee = "2.1.239"')),
                            (New-Object Text.UTF8Encoding $false))
    $differences = @(Differences-Politique $politique $rempli)
    Verifier 'une ligne changée : exactement deux lignes signalées' ($differences.Count -eq 2) "($($differences.Count))"
    $ecarts = @(Ecarts-VersionTestee $politique @{ codex = '0.156.1'; claude = '2.1.280' })
    Verifier 'écart de version_testee de Claude signalé, celui de Codex non' (
        $ecarts.Count -eq 1 -and $ecarts[0] -match '^\[claude\] version_testee vaut « 2\.1\.239 » ; la copie installée est en 2\.1\.280') "($($ecarts -join ' | '))"

    Write-Host ''
    Write-Host 'Cas 12 : droits du compte du poste sur un dossier jetable (décision D67)'
    $dossierDroits = Join-Path $temporaire 'droits'
    New-Item -ItemType Directory -Path $dossierDroits | Out-Null
    Verifier 'dossier du profil : aucun droit pour les groupes du poste' (@(Droits-Ecriture-Pour $dossierDroits $SidsDuComptePoste).Count -eq 0)
    $acl = Get-Acl -LiteralPath $dossierDroits
    $utilisateurs = New-Object Security.Principal.SecurityIdentifier 'S-1-5-32-545'
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($utilisateurs, 'Modify', 'ContainerInherit, ObjectInherit', 'InheritOnly', 'Allow')))
    Set-Acl -LiteralPath $dossierDroits -AclObject $acl
    Verifier 'ACE « héritage seulement » : sans effet sur le dossier lui-même' (@(Droits-Ecriture-Pour $dossierDroits $SidsDuComptePoste).Count -eq 0)
    $acl = Get-Acl -LiteralPath $dossierDroits
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($utilisateurs, 'CreateFiles', 'Allow')))
    Set-Acl -LiteralPath $dossierDroits -AclObject $acl
    $droits = @(Droits-Ecriture-Pour $dossierDroits $SidsDuComptePoste)
    Verifier 'Utilisateurs : création de fichiers détectée' ($droits.Count -eq 1 -and $droits[0] -match '^S-1-5-32-545 : ') "($($droits -join ' | '))"

    Write-Host ''
    Write-Host 'Cas 13 : forme des commandes du compte'
    $forme = Commande-Poste 'C:\Program Files\ACP\poste\acp-poste.cmd' 'connexion codex'
    Verifier 'forme « & ''…'' … »' ($forme -eq "& 'C:\Program Files\ACP\poste\acp-poste.cmd' connexion codex") "($forme)"
    Verifier 's''analyse sans erreur' (Sans-Erreur-D-Analyse $forme)
    Verifier 'témoin : l''ancienne forme entre guillemets sans & ne s''analyse pas' (-not (Sans-Erreur-D-Analyse '"C:\Program Files\ACP\poste\acp-poste.cmd" connexion codex'))
} finally {
    Remove-Item -LiteralPath $temporaire -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $cleJetable -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pythonModifiable -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host ("Bilan : {0} vérifications réussies, {1} cas ignoré(s), {2} échec(s)." -f $script:Reussis, $script:Ignores, $script:Echecs.Count)
if ($script:Echecs.Count -gt 0) {
    $script:Echecs | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
exit 0
