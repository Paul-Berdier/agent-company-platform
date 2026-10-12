#Requires -Version 5.1
# Menu lancé volontairement dans la session du propriétaire. Aucun service ni tâche créée.
param([switch] $VerifierLanceur)
$ErrorActionPreference = 'Stop'
$pythonCoffre = Join-Path $PSScriptRoot 'runtime\python.exe'
if (-not (Test-Path -LiteralPath $pythonCoffre -PathType Leaf)) { throw 'Le runtime du coffre est absent du paquet.' }
function Invoke-Coffre([string[]] $ArgumentsCoffre) {
    & $pythonCoffre -I -B -m acp_poste.cli obsidian @ArgumentsCoffre
    $script:CodeCoffre = $LASTEXITCODE
    if ($script:CodeCoffre -ne 0) { Write-Host 'Le geste a été refusé ; relisez le message avant de continuer.' -ForegroundColor Yellow }
}
if ($VerifierLanceur) {
    Invoke-Coffre -ArgumentsCoffre @('creer', '--help')
    exit $script:CodeCoffre
}
Write-Host 'Coffre ACP — notes Markdown pour Obsidian' -ForegroundColor Cyan
Write-Host 'Ce bridge est indépendant des assistants et ne remplace aucune machine ACP.'
Write-Host 'Il reste actif dans cette fenêtre. Aucun démarrage automatique n''est installé.'
while ($true) {
    Write-Host ''
    Write-Host '1  Créer mon nouveau coffre ACP'
    Write-Host '2  Associer ce coffre à Hermes'
    Write-Host '3  Démarrer le bridge (laisser cette fenêtre ouverte)'
    Write-Host '4  Voir le diagnostic local'
    Write-Host '5  Oublier une ancienne association locale'
    Write-Host '0  Quitter'
    $choixCoffre = Read-Host 'Votre choix'
    switch ($choixCoffre) {
        '1' {
            $defautCoffre = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ACP-notes'
            Write-Host 'Le dossier doit être neuf ; aucun coffre existant ne sera repris.'
            $cheminCoffre = Read-Host "Dossier du nouveau coffre [$defautCoffre]"
            if ([string]::IsNullOrWhiteSpace($cheminCoffre)) { $cheminCoffre = $defautCoffre }
            Invoke-Coffre -ArgumentsCoffre @('creer', '--dossier', $cheminCoffre)
            if ($script:CodeCoffre -eq 0) { Write-Host 'Dans Obsidian, vous pouvez ensuite choisir « Ouvrir un dossier comme coffre » et ce même dossier.' }
        }
        '2' {
            Write-Host 'Dans ACP → Coffre ACP, générez un code d''association.'
            $origineCoffre = Read-Host 'Origine HTTPS de Hermes (la même que dans ACP)'
            Invoke-Coffre -ArgumentsCoffre @('associer', '--origine', $origineCoffre)
            if ($script:CodeCoffre -eq 0) { Write-Host 'Comparez l''empreinte affichée puis confirmez l''association dans ACP.' }
        }
        '3' { Invoke-Coffre -ArgumentsCoffre @('servir') }
        '4' { Invoke-Coffre -ArgumentsCoffre @('diagnostic') }
        '5' {
            Write-Host 'Arrêtez le bridge et révoquez son ancienne association dans ACP avant de continuer.'
            Write-Host 'Les notes et leur dossier sont conservés. Seule cette identité locale sera effacée.'
            $oubliCoffre = Read-Host 'Tapez OUBLIER pour confirmer'
            if ($oubliCoffre -ceq 'OUBLIER') { Invoke-Coffre -ArgumentsCoffre @('oublier') }
        }
        '0' { return }
        default { Write-Host 'Choisissez un nombre affiché dans le menu.' }
    }
}
