#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '../DesktopToolchain.psm1') -Force
$repository = Get-AcpRepositoryRoot
$build = Get-AcpBuildDirectory -Preset (Get-AcpPresetName -Configuration Release)
$qt = Resolve-AcpQtDirectory
if (-not $qt) { throw 'Qt requis pour le test réel du CRT.' }
$fixture = Join-Path $repository ('.test-tmp/crt-package-' + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $fixture 'stage'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $build 'AgentCompanyPlatform.exe') -Destination $stage
Copy-Item -LiteralPath (Join-Path $qt 'bin/Qt6Core.dll') -Destination $stage
$runtime = Copy-AcpMsvcRuntime -BuildDirectory $build -Destination $stage
if (-not (Test-Path -LiteralPath (Join-Path $stage 'vcruntime140.dll'))) {
    throw 'Le CRT annoncé déployé est absent du résultat.'
}

# Les refus utilisent uniquement une copie jetable des fichiers redistribuables.
$fakeVc = Join-Path $fixture 'VC'
$fakeCrt = Join-Path $fakeVc 'Redist/MSVC/14.44.1/x64/Microsoft.VC143.CRT'
$fakeBuild = Join-Path $fixture 'build'
New-Item -ItemType Directory -Path $fakeCrt -Force | Out-Null
New-Item -ItemType Directory -Path $fakeBuild -Force | Out-Null
Get-ChildItem -LiteralPath $runtime.Directory -File -Filter '*.dll' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $fakeCrt
}
$encoding = New-Object System.Text.UTF8Encoding($false)
function Set-TestCompiler([string] $Version) {
    $path = Join-Path $fakeVc "Tools/MSVC/$Version/bin/Hostx64/x64/cl.exe"
    [System.IO.File]::WriteAllText((Join-Path $fakeBuild 'CMakeCache.txt'),
        "CMAKE_CXX_COMPILER:FILEPATH=$path`n", $encoding)
}
function Assert-Refused([string] $Reason, [string] $Pattern) {
    $caught = $null
    try { Copy-AcpMsvcRuntime -BuildDirectory $fakeBuild -Destination $stage | Out-Null }
    catch { $caught = $_.Exception.Message }
    if (-not $caught -or $caught -notmatch $Pattern) {
        throw "Refus attendu ($Reason), reçu : $caught"
    }
}
Set-TestCompiler '14.99.99999'
Assert-Refused 'runtime plus ancien que le toolset' 'introuvable ou trop ancien'
Set-TestCompiler '14.30.0'
$missing = Join-Path $fakeCrt 'msvcp140_2.dll'
Move-Item -LiteralPath $missing -Destination ($missing + '.held')
Assert-Refused 'DLL redistribuable manquante' 'incomplet'
Move-Item -LiteralPath ($missing + '.held') -Destination $missing

$wrongArchitecture = Join-Path $fakeCrt 'vcruntime140_1.dll'
$bytes = [System.IO.File]::ReadAllBytes($wrongArchitecture)
$pe = [BitConverter]::ToInt32($bytes, 0x3c)
$bytes[$pe + 4] = 0x4c
$bytes[$pe + 5] = 0x01
[System.IO.File]::WriteAllBytes($wrongArchitecture, $bytes)
Assert-Refused 'DLL x86 dans une distribution x64' 'pas un binaire PE x64'

$result = [pscustomobject]@{
    status = 'passed'
    runtimeVersion = $runtime.Version
    requiredToolsetVersion = $runtime.RequiredVersion
    qtLinkerVersion = $runtime.QtLinkerVersion
    deployedDlls = $runtime.FileCount
    checks = @('real-runtime-deployed', 'old-runtime-rejected', 'missing-dll-rejected', 'x86-dll-rejected')
}
[System.IO.File]::WriteAllText((Join-Path $fixture 'result.json'),
    ($result | ConvertTo-Json -Depth 4), $encoding)
$result | ConvertTo-Json -Depth 4
