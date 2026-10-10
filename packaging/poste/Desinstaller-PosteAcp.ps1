#Requires -Version 5.1
<#
.SYNOPSIS
    Désinstalle le poste Windows d'ACP (étape P5, cahier § 8.5).

.DESCRIPTION
    À lancer PAR LE PROPRIÉTAIRE dans un PowerShell élevé. Retire la tâche planifiée \ACP\Poste ACP ; puis, chacun sur
    confirmation : C:\Program Files\ACP, C:\ProgramData\ACP (poste.toml compris), C:\ACP\espaces (puis C:\ACP s'il
    est vide), la valeur « acp-poste » des comptes masqués de l'écran d'accueil (la clé UserList et ses autres valeurs
    restent), et le compte « acp-poste » avec son profil (donc son coffre DPAPI et ses jetons). C:\ACP\depots n'est
    jamais supprimé sans une seconde confirmation NOMINATIVE (retaper le chemin exact).

    Rappels imprimés : révoquer le poste sur la page Poste (la révocation est un geste côté Hermes) ; retirer la ligne
    d'état (statusLine) de ~/.claude/settings.json, qui appelait ligne_etat.py ; les comptes locaux CodexSandboxOffline
    et CodexSandboxOnline appartiennent à Codex et restent.

    -Simulation n'écrit ni ne supprime rien et ne pose aucune question : il imprime ce qui serait fait.
#>
[CmdletBinding()]
param(
    [string] $Compte = 'acp-poste',
    [switch] $Simulation
)

Set-StrictMode -Version 3
$ErrorActionPreference = 'Stop'
if ([Console]::IsOutputRedirected) {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
}
$Fonctions = Join-Path $PSScriptRoot 'Fonctions-PosteAcp.ps1'
if (-not (Test-Path -LiteralPath $Fonctions -PathType Leaf)) {
    Write-Host "Refusé : Fonctions-PosteAcp.ps1 est introuvable à côté du désinstalleur ; lancez-le depuis le dépôt." -ForegroundColor Red
    exit 2
}
. $Fonctions

$ProgramFiles = [Environment]::GetFolderPath('ProgramFiles')
$ProgramData = [Environment]::GetFolderPath('CommonApplicationData')
$AcpProgramFiles = Join-Path $ProgramFiles 'ACP'
$AcpProgramData = Join-Path $ProgramData 'ACP'
$RacineAcp = Join-Path $env:SystemDrive 'ACP'
$DossierDepots = Join-Path $RacineAcp 'depots'
$DossierEspaces = Join-Path $RacineAcp 'espaces'

function Confirmer([string] $Question) {
    if ($Simulation) {
        Write-Host "  [simulation, aucune question posée] $Question"
        return $false
    }
    return (Read-Host "$Question [o/N]") -match '^(o|oui)$'
}

Write-Host "Désinstallation du poste Windows d'ACP" -NoNewline
if ($Simulation) { Write-Host ' : SIMULATION, rien ne sera supprimé.' } else { Write-Host '.' }
$identite = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $Simulation -and -not ([Security.Principal.WindowsPrincipal] $identite).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Refusé : lancez la désinstallation dans un PowerShell élevé (UAC).' -ForegroundColor Red
    exit 2
}

Write-Host ''
Write-Host '1. Tâche planifiée \ACP\Poste ACP'
$tache = Get-ScheduledTask -TaskPath '\ACP\' -TaskName 'Poste ACP' -ErrorAction SilentlyContinue
if (-not $tache) {
    Write-Host '  absente.'
} elseif ($Simulation) {
    Write-Host '  [simulation] Stop-ScheduledTask puis Unregister-ScheduledTask.'
} else {
    Stop-ScheduledTask -InputObject $tache -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -InputObject $tache -Confirm:$false
    Write-Host '  retirée.'
}

Write-Host ''
Write-Host '2. Dossiers du poste'
foreach ($dossier in @($AcpProgramFiles, $AcpProgramData)) {
    if (-not (Test-Path -LiteralPath $dossier)) { Write-Host "  $dossier : absent."; continue }
    if (Confirmer "Supprimer $dossier ?") {
        Remove-Item -LiteralPath $dossier -Recurse -Force
        Write-Host "  $dossier supprimé."
    } else {
        Write-Host "  $dossier conservé."
    }
}
if (Test-Path -LiteralPath $DossierDepots) {
    if ($Simulation) {
        Write-Host "  [simulation] $DossierDepots : suppression seulement après confirmation nominative (chemin retapé)."
    } elseif ((Read-Host "Pour supprimer les dépôts du poste, retapez exactement $DossierDepots (sinon Entrée)") -ceq $DossierDepots) {
        Remove-Item -LiteralPath $DossierDepots -Recurse -Force
        Write-Host "  $DossierDepots supprimé."
    } else {
        Write-Host "  $DossierDepots conservé."
    }
}
# Espaces de travail des cartes (P6) : créés par l'installeur, avec une ACE pour le compte du poste.
if (Test-Path -LiteralPath $DossierEspaces) {
    if (Confirmer "Supprimer $DossierEspaces (espaces de travail des cartes) ?") {
        Remove-Item -LiteralPath $DossierEspaces -Recurse -Force
        Write-Host "  $DossierEspaces supprimé."
    } else {
        Write-Host "  $DossierEspaces conservé."
    }
} else {
    Write-Host "  $DossierEspaces : absent."
}
if ((Test-Path -LiteralPath $RacineAcp) -and -not (Get-ChildItem -LiteralPath $RacineAcp -Force | Select-Object -First 1)) {
    if ($Simulation) {
        Write-Host "  [simulation] $RacineAcp, vide, serait retiré."
    } else {
        Remove-Item -LiteralPath $RacineAcp -Force
        Write-Host "  $RacineAcp, vide, retiré."
    }
}

Write-Host ''
Write-Host "3. Écran d'accueil (comptes masqués)"
$masque = (Test-Path -LiteralPath $CleComptesMasques) -and
          (@((Get-Item -LiteralPath $CleComptesMasques).GetValueNames()) -contains $Compte)
if (-not $masque) {
    Write-Host "  $Compte n'y est pas masqué."
} elseif (Confirmer "Retirer la seule valeur « $Compte » des comptes masqués (les autres valeurs, dont celles de Codex, restent) ?") {
    if (Retirer-CompteAccueil $CleComptesMasques $Compte) { Write-Host '  valeur retirée ; la clé et ses autres valeurs restent.' }
} else {
    Write-Host '  valeur conservée.'
}

Write-Host ''
Write-Host "4. Compte « $Compte »"
$utilisateur = Get-LocalUser -Name $Compte -ErrorAction SilentlyContinue
if (-not $utilisateur) {
    Write-Host '  absent.'
} elseif (Confirmer "Supprimer le compte $Compte et son profil (coffre DPAPI, jetons, profil Codex) ?") {
    $profil = Get-CimInstance -ClassName Win32_UserProfile | Where-Object { $_.SID -eq $utilisateur.SID.Value }
    Remove-LocalUser -InputObject $utilisateur
    if ($profil) { $profil | Remove-CimInstance }
    Write-Host '  compte et profil supprimés.'
} else {
    Write-Host '  compte conservé.'
}

Write-Host ''
Write-Host 'Rappels :'
Write-Host "  - révoquez le poste sur la page Poste d'ACP (la désinstallation ne touche pas Hermes) ;"
Write-Host '  - retirez la ligne d''état (clé statusLine) de votre ~/.claude/settings.json : elle appelait ligne_etat.py, supprimé avec le poste ;'
Write-Host '  - les comptes locaux CodexSandboxOffline et CodexSandboxOnline appartiennent à Codex et restent.'
exit 0
