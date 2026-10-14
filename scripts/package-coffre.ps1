#Requires -Version 5.1
<# Empaquette le bridge coffre autonome sans compte administrateur ni installation personnelle. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Python,
    [Parameter(Mandatory = $true)][string] $OutputDir
)
$ErrorActionPreference = 'Stop'
$repoCoffre = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (Test-Path -LiteralPath $Python -PathType Leaf) {
    $interpreteurCoffre = (Resolve-Path -LiteralPath $Python).ProviderPath
} else {
    $commandePythonCoffre = Get-Command -Name $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $interpreteurCoffre = $commandePythonCoffre.Source
}
$sortieCoffre = [IO.Path]::GetFullPath($OutputDir)
& $interpreteurCoffre -I (Join-Path $PSScriptRoot 'package_coffre.py') --repo $repoCoffre --output $sortieCoffre
if ($LASTEXITCODE -ne 0) { throw "L'empaquetage autonome du coffre a échoué (code $LASTEXITCODE)." }
Write-Output "Bridge coffre autonome vérifié : $sortieCoffre"
