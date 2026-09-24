<# Configure un worker du lanceur local, sans copier d'authentification personnelle. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]{1,36}$')][string]$ProjectId,
    [Parameter(Mandatory)][string]$ProjectPath,
    [Parameter(Mandatory)][string]$CodexProfile,
    [Parameter(Mandatory)][string]$ClaudeProfile,
    [string]$CodexExecutable = '',
    [ValidateSet('doctor', 'register', 'start')][string]$Action = 'doctor',
    [ValidateRange(1024,65533)][int]$ApiPort = 8000
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'DPAPI Windows requis.' }
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'
$claudeExe = Join-Path $repoRoot 'acp-data/tools/claude-2.1.267/claude.exe'
if (-not $CodexExecutable) { $CodexExecutable = (Get-Command codex -ErrorAction Stop).Source }
$projectRoot = (Resolve-Path -LiteralPath $ProjectPath).Path
$codexRoot = (Resolve-Path -LiteralPath $CodexProfile).Path
$claudeRoot = (Resolve-Path -LiteralPath $ClaudeProfile).Path
$secretPath = Join-Path $repoRoot 'acp-data/local-stack/service-secrets.dpapi'
$secure = ConvertTo-SecureString (Get-Content -LiteralPath $secretPath -Raw)
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $secrets = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) | ConvertFrom-Json -AsHashtable }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
$values = @{
    PYTHONUTF8='1'
    ACP_API_URL="http://127.0.0.1:$ApiPort"
    ACP_PROVIDER_GATEWAY_URL="http://127.0.0.1:$($ApiPort+2)"
    ACP_GATEWAY_SERVICE_TOKEN=$secrets.gateway
    ACP_WORKER_REGISTRATION_TOKEN=$secrets.registration
    ACP_WORKER_PROJECT_ID=$ProjectId
    ACP_WORKER_GLOBAL_ACCESS='0'
    ACP_WORKER_SIMULATION='0'
    ACP_ORCHESTRATOR_PROVIDER='hermes'
    ACP_WORKER_STATE_DIR=Join-Path $repoRoot "acp-data/local-stack/workers/$ProjectId"
    ACP_WORKER_CODEX_ENABLED='1'; ACP_WORKER_CODEX_EXECUTABLE=$CodexExecutable; ACP_WORKER_CODEX_HOME=$codexRoot
    ACP_WORKER_CLAUDE_ENABLED='1'; ACP_WORKER_CLAUDE_EXECUTABLE=$claudeExe; ACP_WORKER_CLAUDE_CONFIG_DIR=$claudeRoot
    ACP_WORKER_EXECUTOR_PROJECTS_JSON=(@{$ProjectId=$projectRoot} | ConvertTo-Json -Compress)
    ACP_WORKER_EXECUTOR_PATH=((Split-Path (Get-Command git).Source), "$env:SystemRoot/System32") -join [IO.Path]::PathSeparator
}
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName=$pythonExe; $info.WorkingDirectory=$repoRoot; $info.UseShellExecute=$false
$info.CreateNoWindow=$true; $info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$info.Environment.Clear()
foreach ($key in @('SystemRoot','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE')) {
    $value = [Environment]::GetEnvironmentVariable($key, 'Process')
    if ($value) { $info.Environment[$key]=$value }
}
foreach ($key in $values.Keys) { $info.Environment[$key]=[string]$values[$key] }
foreach ($argument in @('-m','acp_worker.cli',$Action)) { $info.ArgumentList.Add($argument) }
if ($Action -eq 'register') {
    foreach ($argument in @('--real','--project',$ProjectId,'--name',"local-$ProjectId")) { $info.ArgumentList.Add($argument) }
}
$child = [Diagnostics.Process]::Start($info)
try {
    while (-not $child.WaitForExit(500)) { }
    if ($child.ExitCode -ne 0) { throw "Worker terminé avec le code $($child.ExitCode)." }
} finally {
    if (-not $child.HasExited) { $child.Kill($true); $child.WaitForExit(10000) | Out-Null }
    $child.Dispose()
}
