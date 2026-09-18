#Requires -Version 5.1

<#
.SYNOPSIS
    Inventorie les prérequis du client desktop Windows. N'installe rien.

.DESCRIPTION
    Ce script est conçu pour tourner sur un poste où rien n'est installé. Son rôle
    est de dire, outil par outil, ce qui manque et quelle commande lancer soi-même
    pour l'obtenir. Il ne télécharge rien, n'installe rien, ne modifie ni le PATH,
    ni le registre, ni un fichier du dépôt.

    Codes de sortie :
      0  tous les prérequis obligatoires sont présents
      1  erreur inattendue
      2  au moins un prérequis obligatoire manque

.PARAMETER QtDir
    Chemin explicite d'une installation Qt (le répertoire qui contient bin\windeployqt.exe).
    À défaut, ACP_QT_DIR, QT_ROOT_DIR, Qt6_DIR puis C:\Qt\<version épinglée> sont examinés.

.PARAMETER Json
    Écrit l'inventaire en JSON sur la sortie standard, pour un usage automatisé.

.EXAMPLE
    ./scripts/setup-desktop.ps1

.EXAMPLE
    ./scripts/setup-desktop.ps1 -QtDir "C:\Qt\6.8.3\msvc2022_64" -Json
#>

[CmdletBinding()]
param(
    [string] $QtDir,
    [switch] $Json
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\packaging\windows\DesktopToolchain.psm1') -Force
$codes = Get-AcpExitCodes

try {
    $toolchain = Get-AcpToolchain
    $prerequis = Get-AcpPrerequisites -QtDir $QtDir -Toolchain $toolchain
    $manquants = @($prerequis | Where-Object { $_.Requis -and -not $_.Present })

    if ($Json) {
        $prerequis | ConvertTo-Json -Depth 4
        if ($manquants.Count -gt 0) { exit $codes.PrerequisManquant }
        exit $codes.Succes
    }

    Write-AcpEtape "Prérequis du client desktop — Agent Company Platform $(Get-AcpProductVersion)"
    Write-Host "Ce script n'installe rien. Il constate, et il vous dit quoi lancer." -ForegroundColor Yellow

    foreach ($item in $prerequis) {
        if ($item.Present) {
            $marque = '[present]'
            $couleur = 'Green'
        }
        elseif ($item.Requis) {
            $marque = '[MANQUANT]'
            $couleur = 'Red'
        }
        else {
            $marque = '[absent]  '
            $couleur = 'Yellow'
        }
        Write-Host ''
        Write-Host "$marque $($item.Nom)" -ForegroundColor $couleur
        Write-Host "           $($item.Detail)"
        if (-not $item.Present) {
            Write-Host "           À lancer vous-même : $($item.Installation)" -ForegroundColor DarkYellow
        }
    }

    Write-Host ''
    Write-Host "Qt épinglé pour ce produit : $($toolchain.qt.version) / $($toolchain.qt.architecture)."
    Write-Host "Source unique de ces valeurs : packaging/windows/toolchain.json."

    if ($manquants.Count -gt 0) {
        Write-AcpRefus `
            -Message "$($manquants.Count) prérequis obligatoire(s) manquant(s) : la compilation du client desktop est impossible en l'état." `
            -Details ($manquants | ForEach-Object { $_.Nom })
        exit $codes.PrerequisManquant
    }

    Write-Host ''
    Write-Host 'Tous les prérequis obligatoires sont présents.' -ForegroundColor Green
    Write-Host 'Étape suivante : ./scripts/build-desktop.ps1 -Configuration Debug'
    exit $codes.Succes
}
catch {
    Write-AcpRefus -Message $_.Exception.Message
    exit $codes.ErreurInattendue
}
