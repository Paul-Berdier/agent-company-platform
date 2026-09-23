#Requires -Version 5.1

<#
.SYNOPSIS
    Vérifie que Ninja recompile après modification d'un en-tête sous MSVC.
.DESCRIPTION
    Régression réelle et indépendante de Qt/Pester. Chaque exécution crée son
    mini-projet sous .test-tmp ; aucun cache desktop existant n'est ouvert.
    Exiger MSVC, CMake et Ninja déjà installés. Aucune installation automatique.
#>
[CmdletBinding()]
param([string] $NinjaPath = '')

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\DesktopToolchain.psm1') -Force
$languePrecedente = $env:VSLANG
$pagePrecedente = [Console]::InputEncoding.CodePage
$racineTest = Join-Path (Get-AcpRepositoryRoot) ('.test-tmp\msvc-header-deps-' + [guid]::NewGuid().ToString('N'))
$utf8 = New-Object System.Text.UTF8Encoding($false)

try {
    if (-not (Enter-AcpMsvcEnvironment)) { throw 'MSVC x64 est requis pour ce test.' }
    # Le cas important est aussi un Developer Shell déjà chargé en français :
    # le retour anticipé du module ne doit pas conserver une sortie localisée.
    $env:VSLANG = '1036'
    if (-not (Enter-AcpMsvcEnvironment)) { throw 'Le Developer Shell a perdu cl.exe.' }
    if ($env:VSLANG -ne '1033') { throw 'La langue MSVC reste localisée dans un environnement déjà initialisé.' }
    foreach ($outil in 'cmake', 'ninja') {
        if (-not (Get-Command -Name $outil -CommandType Application -ErrorAction SilentlyContinue)) {
            throw "Prérequis absent : $outil."
        }
    }
    $null = New-Item -ItemType Directory -Path $racineTest -Force
    $build = Join-Path $racineTest 'build'
    $header = Join-Path $racineTest 'value.h'
    [IO.File]::WriteAllText((Join-Path $racineTest 'CMakeLists.txt'), @'
cmake_minimum_required(VERSION 3.28)
project(AcpHeaderDependencyRegression LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
add_executable(header_probe main.cpp)
'@ + "`n", $utf8)
    [IO.File]::WriteAllText((Join-Path $racineTest 'main.cpp'), "#include `"value.h`"`nint main() { return kHeaderValue; }`n", $utf8)
    [IO.File]::WriteAllText($header, "inline constexpr int kHeaderValue = 42;`n", $utf8)
    $configuration = @('-S', $racineTest, '-B', $build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release')
    if ($NinjaPath) {
        $ninjaResolu = (Resolve-Path -LiteralPath $NinjaPath -ErrorAction Stop).Path
        $configuration += '-DCMAKE_MAKE_PROGRAM=' + $ninjaResolu
    }
    Invoke-AcpProcess -FilePath 'cmake' -Arguments $configuration
    Invoke-AcpProcess -FilePath 'cmake' -Arguments @('--build', $build)
    $programme = Join-Path $build 'header_probe.exe'
    & $programme
    if ($LASTEXITCODE -ne 42) { throw 'Le premier binaire ne reflète pas la valeur initiale de son en-tête.' }

    [IO.File]::WriteAllText($header, "inline constexpr int kHeaderValue = 43;`n", $utf8)
    Invoke-AcpProcess -FilePath 'cmake' -Arguments @('--build', $build, '--', '-d', 'explain')
    & $programme
    if ($LASTEXITCODE -ne 43) { throw "Ninja n'a pas recompilé après modification de l'en-tête." }
    $preuve = [ordered]@{ status = 'passed'; languagePreference = $env:VSLANG; consoleCodePage = 65001; initialValue = 42; rebuiltValue = 43 }
    [IO.File]::WriteAllText((Join-Path $racineTest 'result.json'), ($preuve | ConvertTo-Json) + "`n", $utf8)
    Write-Host "Régression MSVC/Ninja vérifiée : $racineTest"
}
finally {
    & (Join-Path $env:SystemRoot 'System32\chcp.com') $pagePrecedente | Out-Null
    if ($null -eq $languePrecedente) { Remove-Item Env:VSLANG -ErrorAction SilentlyContinue }
    else { $env:VSLANG = $languePrecedente }
}
