<# Lance le Hermes local préparé par setup-hermes.ps1, dans son profil isolé. #>
[CmdletBinding()]
param(
    [ValidateSet('setup', 'gateway', 'status', 'version')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$hermesExe = Join-Path $repoRoot 'acp-data/tools/hermes-v2026.9.7/.venv/Scripts/hermes.exe'
if (-not (Test-Path -LiteralPath $hermesExe)) { throw 'Exécuter ./scripts/setup-hermes.ps1 auparavant.' }
$profileRoot = Join-Path $repoRoot 'acp-data/hermes-profile'
$vaultRoot = Join-Path $repoRoot 'acp-data/obsidian'
if (-not (Test-Path -LiteralPath $profileRoot)) { throw 'Profil absent ; terminer setup-hermes.ps1.' }
& (Join-Path (Split-Path -Parent $hermesExe) 'python.exe') (Join-Path $PSScriptRoot 'check_hermes_profile.py') --source (Join-Path $repoRoot 'acp-data/tools/hermes-v2026.9.7') --profile $profileRoot
if ($LASTEXITCODE -ne 0) { throw 'Configuration Hermes incompatible avec les bornes du lanceur local.' }
$saved = @{}
$overrides = @{
    HERMES_HOME = $profileRoot
    OBSIDIAN_VAULT_PATH = $vaultRoot
    PYTHONUTF8 = '1'
    HERMES_DISABLE_LAZY_INSTALLS = '1'
}
if ($Action -eq 'gateway') {
    if (-not $env:API_SERVER_KEY) { throw 'Définir API_SERVER_KEY dans cette session (même secret que HERMES_API_KEY du provider-gateway).' }
    $overrides.API_SERVER_ENABLED = 'true'
    $overrides.API_SERVER_HOST = '127.0.0.1'
    $overrides.API_SERVER_PORT = '8642'
}
try {
    foreach ($key in $overrides.Keys) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $overrides[$key], 'Process')
    }
    if ($Action -eq 'version') { & $hermesExe --version }
    elseif ($Action -eq 'gateway') { & $hermesExe gateway run }
    else { & $hermesExe $Action }
    if ($LASTEXITCODE -ne 0) { throw "Hermes a terminé avec le code $LASTEXITCODE." }
} finally {
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
}
