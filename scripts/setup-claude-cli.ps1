<# Installe le binaire natif officiel épinglé, localement, sans authentification. #>
[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or -not $IsWindows) {
    throw 'Ce lanceur cible Windows x64 ; utiliser la distribution officielle adaptée à votre poste.'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
$version = '2.1.267'
$sha256 = '23dde2a47cf1d7d9c4a2d96d21fa80ea9bfc872dfde0ee06e9982d2908603350'
$size = 220051616
$toolRoot = Join-Path $repoRoot "acp-data/tools/claude-$version"
$exePath = Join-Path $toolRoot 'claude.exe'
if (-not (Test-Path -LiteralPath $exePath)) {
    if ($CheckOnly) { throw 'Claude Code non installé. Exécuter sans -CheckOnly.' }
    New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
    $partPath = Join-Path $toolRoot 'claude.download'
    Invoke-WebRequest "https://downloads.claude.ai/claude-code-releases/$version/win32-x64/claude.exe" -OutFile $partPath
    if ((Get-Item -LiteralPath $partPath).Length -ne $size -or
        (Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha256) {
        throw 'Téléchargement Claude invalide : taille ou SHA256 incorrect. Aucun binaire activé.'
    }
    Move-Item -LiteralPath $partPath -Destination $exePath
}
if ((Get-Item -LiteralPath $exePath).Length -ne $size -or
    (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha256) {
    throw 'Binaire Claude modifié ; remplacement automatique refusé.'
}
$reported = & $exePath --version
if ($LASTEXITCODE -ne 0 -or $reported -notmatch "^$([regex]::Escape($version))\s") {
    throw 'La version exécutée ne correspond pas à la version attendue.'
}
Write-Output "Claude Code $version : SHA256 vérifié, exécutable $exePath"
Write-Output 'Aucun compte connecté, aucun appel de modèle exécuté.'
