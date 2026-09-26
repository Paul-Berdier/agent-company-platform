#Requires -Version 5.1
<#
.SYNOPSIS
    Éprouve l'installeur et le désinstalleur du poste EN SIMULATION SEULEMENT (cahier P5 § 8.1, § 14.1).

.DESCRIPTION
    Aucun compte, aucune tâche, aucun dossier ni réglage n'est créé : chaque cas lance
    Installer-PosteAcp.ps1 -Simulation (ou Desinstaller-PosteAcp.ps1 -Simulation) et vérifie
      - le plan imprimé (les neuf étapes, les refus en français, le code de sortie) ;
      - que l'état du PC est IDENTIQUE avant et après : C:\Program Files\ACP, C:\ProgramData\ACP, C:\ACP, le compte
        local acp-poste, les tâches planifiées sous \ACP\.
    Les sources de Codex et de Claude sont de faux fichiers vides dans un dossier temporaire (jamais exécutés en
    simulation).

    Le cas « installation acceptée » exige un Python 3.12 installé « pour tous les utilisateurs » (hors de tout profil,
    hors WindowsApps) : celui de -Python, sinon celui du PATH. Faute d'en trouver un, le cas est déclaré IGNORÉ (jamais
    compté réussi) ; sur windows-2022 (CI), le Python de setup-python convient.

    Code de sortie : 0 si aucun échec, 1 sinon.
#>
[CmdletBinding()]
param(
    [string] $Python = ''
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false

$Ici = Split-Path -Parent $MyInvocation.MyCommand.Path
$Depot = (Resolve-Path (Join-Path $Ici '..\..\..')).Path
$Installeur = Join-Path $Depot 'packaging\poste\Installer-PosteAcp.ps1'
$Desinstalleur = Join-Path $Depot 'packaging\poste\Desinstaller-PosteAcp.ps1'
$Hote = (Get-Process -Id $PID).Path
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
    return ('pf={0};pd={1};acp={2};compte={3};taches={4};comptes={5}' -f (Test-Path $programFiles), (Test-Path $programData),
            (Test-Path $racine), [bool]$compte, ($taches -join ','), ($comptes -join ','))
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

$temporaire = Join-Path ([IO.Path]::GetTempPath()) ('acp-test-installation-' + [Guid]::NewGuid().ToString('N'))
$codex = Join-Path $temporaire 'codex'
New-Item -ItemType Directory -Force -Path (Join-Path $codex 'bin'), (Join-Path $codex 'codex-resources'), (Join-Path $temporaire 'claude') | Out-Null
foreach ($faux in @((Join-Path $codex 'bin\codex.exe'), (Join-Path $codex 'codex-resources\codex-windows-sandbox-setup.exe'),
                    (Join-Path $temporaire 'claude\claude.exe'))) {
    [IO.File]::WriteAllBytes($faux, [byte[]]@())
}
$profils = [Environment]::ExpandEnvironmentVariables(
    (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList').ProfilesDirectory)

function Arguments([string] $PythonDuCas, [string] $Origine = 'https://hermes-acp.test') {
    return @('-Origine', $Origine, '-Python', $PythonDuCas, '-Depot', $Depot, '-CodexSource', $codex,
             '-ClaudeSource', (Join-Path $temporaire 'claude\claude.exe'), '-ProfilProprietaire', $temporaire, '-Simulation')
}

function Neuf-Etapes([string] $Sortie) {
    foreach ($n in 1..9) { if ($Sortie -notmatch "tape $n/9 :") { return $false } }
    return $true
}

try {
    $avant = Etat-Du-PC
    Write-Host "État du PC avant : $avant"

    # ------------------------------------------------------------------ cas 1 : installation acceptée
    Write-Host ''
    Write-Host 'Cas 1 : installation acceptée (Python 3.12 « tous utilisateurs »)'
    if (-not $Python) {
        $trouve = Get-Command python -ErrorAction SilentlyContinue
        if ($trouve) { $Python = $trouve.Source }
    }
    $admissible = $false
    if ($Python -and (Test-Path -LiteralPath $Python) -and $Python -notmatch '\\WindowsApps\\' -and
        -not ([IO.Path]::GetFullPath($Python).StartsWith($profils.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) {
        $admissible = ((& $Python -I -c "import sys; print('%d.%d' % sys.version_info[:2])") -eq '3.12')
    }
    if ($admissible) {
        $r = Lancer $Installeur (Arguments $Python)
        Verifier 'code de sortie 0' ($r.Code -eq 0) "(code $($r.Code))"
        Verifier 'neuf étapes imprimées' (Neuf-Etapes $r.Sortie)
        Verifier 'aucun refus' ($r.Sortie -match 'Simulation terminée : aucun refus')
        Verifier 'tâche planifiée décrite' ($r.Sortie -match 'garde toutes les 15 min')
        Verifier 'groupes désignés par SID' ($r.Sortie -match '\*S-1-5-32-544:\(OI\)\(CI\)F')
        Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)
        if ($script:Echecs.Count -gt 0) { Write-Host $r.Sortie }
    } else {
        $script:Ignores++
        Write-Host "  IGNORÉ  aucun Python 3.12 « tous utilisateurs » sur ce PC (celui du PATH est sous un profil, dans WindowsApps ou d'une autre version) : le cas est prouvé sur windows-2022."
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
    $r = Lancer $Installeur (Arguments ($(if ($admissible) { $Python } else { 'C:\Absent\python.exe' })) 'http://hermes-acp.test')
    Verifier 'code de sortie 2' ($r.Code -eq 2) "(code $($r.Code))"
    Verifier 'refus de l''origine en français' ($r.Sortie -match 'Origine doit être une origine HTTPS')
    Verifier 'rien écrit' ((Etat-Du-PC) -eq $avant)

    # ------------------------------------------------------------------ cas 5 : désinstallation à blanc
    Write-Host ''
    Write-Host 'Cas 5 : désinstallation en simulation'
    $r = Lancer $Desinstalleur @('-Simulation')
    Verifier 'code de sortie 0' ($r.Code -eq 0) "(code $($r.Code))"
    Verifier 'rappel de la révocation' ($r.Sortie -match 'révoquez le poste sur la page Poste')
    Verifier 'rien supprimé' ((Etat-Du-PC) -eq $avant)
} finally {
    Remove-Item -LiteralPath $temporaire -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host ("Bilan : {0} vérifications réussies, {1} cas ignoré(s), {2} échec(s)." -f $script:Reussis, $script:Ignores, $script:Echecs.Count)
if ($script:Echecs.Count -gt 0) {
    $script:Echecs | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
exit 0
