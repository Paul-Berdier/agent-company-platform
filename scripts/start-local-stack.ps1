<#
.SYNOPSIS
Démarre la pile ACP locale persistante sur loopback, jusqu'à Ctrl+C.
.DESCRIPTION
PowerShell 7 / Windows. Aucun seed de démonstration ni worker automatique.
Les secrets techniques sont chiffrés par DPAPI pour l'utilisateur Windows.
-CheckStartup vérifie le démarrage puis arrête les processus créés.
-BootstrapOwner demande localement le premier compte et son mot de passe.
#>
[CmdletBinding()]
param(
    [string]$Python = '',
    [ValidateRange(1024,65533)][int]$ApiPort = 8000,
    [switch]$CheckStartup,
    [switch]$BootstrapOwner,
    [switch]$WithHermes,
    [ValidatePattern('^[A-Za-z0-9_-]{1,36}$')][string]$WorkerProjectId = ''
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Ce lanceur utilise DPAPI Windows ; utiliser le déploiement documenté pour Linux.' }
if ($CheckStartup -and $BootstrapOwner) { throw '-CheckStartup ne crée aucun compte.' }
$servicePorts = @($ApiPort, ($ApiPort + 1), ($ApiPort + 2)) + $(if ($WithHermes) { @(8642) } else { @() })
if (@($servicePorts | Select-Object -Unique).Count -ne $servicePorts.Count) {
    throw 'Ports de services en conflit : avec Hermes, choisir un -ApiPort dont les trois ports ne comprennent pas 8642.'
}
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $repoRoot '.venv/Scripts/python.exe' }
$pythonExe = (Get-Command $Python -ErrorAction Stop).Source
if ($WithHermes) {
    & $pythonExe (Join-Path $PSScriptRoot 'check_hermes_profile.py') --source (Join-Path $repoRoot 'acp-data/tools/hermes-v2026.9.7') --profile (Join-Path $repoRoot 'acp-data/hermes-profile')
    if ($LASTEXITCODE -ne 0) { throw 'Configuration Hermes incompatible avec les bornes du lanceur local.' }
}
$runtimeRoot = Join-Path $repoRoot 'acp-data/local-stack'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$secretPath = Join-Path $runtimeRoot 'service-secrets.dpapi'

function New-Token {
    return [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).Replace('+','-').Replace('/','_')
}
function Reveal-LocalSecret([Security.SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if (-not (Test-Path -LiteralPath $secretPath)) {
    $initial = @{}
    foreach ($key in @('gateway', 'events', 'bootstrap', 'vault', 'artifacts', 'hermes', 'registration')) {
        $initial[$key] = New-Token
    }
    $secured = ConvertTo-SecureString ($initial | ConvertTo-Json -Compress) -AsPlainText -Force
    $ciphertext = ConvertFrom-SecureString $secured
    # CreateNew refuse un remplacement en cas de deux lanceurs simultanés.
    $stream = [IO.File]::Open($secretPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($ciphertext)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}
$secrets = Reveal-LocalSecret (ConvertTo-SecureString (Get-Content -LiteralPath $secretPath -Raw)) | ConvertFrom-Json -AsHashtable
foreach ($key in @('gateway', 'events', 'bootstrap', 'vault', 'artifacts', 'hermes', 'registration')) {
    if (-not $secrets[$key]) { throw "Secret technique absent : $key. Aucun remplacement automatique." }
}
$apiUrl = "http://127.0.0.1:$ApiPort"
$eventPort = $ApiPort + 1
$gatewayPort = $ApiPort + 2
foreach ($port in $servicePorts) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
    try { $listener.Start() }
    catch { throw "Le port $port est déjà occupé. Choisir -ApiPort ou arrêter son service explicitement." }
    finally { $listener.Stop() }
}
$sourcePaths = @('packages/contracts', 'packages/database', 'packages/provider-sdk',
    'packages/event-sdk', 'packages/agent-sdk', 'apps/api', 'apps/event-service',
    'apps/worker', 'services/provider-gateway') | ForEach-Object { Join-Path $repoRoot "$_/src" }
$common = @{
    PYTHONPATH = $sourcePaths -join [IO.Path]::PathSeparator
    PYTHONUTF8 = '1'
    ACP_DATABASE_URL = 'sqlite:///' + (Join-Path $runtimeRoot 'platform.db').Replace('\','/')
    ACP_API_URL = $apiUrl
    ACP_EVENT_SERVICE_URL = "http://127.0.0.1:$eventPort"
    ACP_PROVIDER_GATEWAY_URL = "http://127.0.0.1:$gatewayPort"
    ACP_PLUGINS_DIR = Join-Path $repoRoot 'plugins'
}
function Start-ServiceProcess([string]$Name, [string]$Executable, [string[]]$Arguments, [hashtable]$Values) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.WorkingDirectory = $repoRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.Environment.Clear()
    foreach ($key in @('SystemRoot', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'USERPROFILE')) {
        $value = [Environment]::GetEnvironmentVariable($key, 'Process')
        if ($value) { $info.Environment[$key] = $value }
    }
    foreach ($key in $Values.Keys) { $info.Environment[$key] = [string]$Values[$key] }
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $child = [Diagnostics.Process]::Start($info)
    if (-not $child) { throw "Impossible de démarrer $Name." }
    return @{Name=$Name; Process=$child}
}
function Wait-Health([string]$Url, $Child) {
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        if ($Child.Process.HasExited) { throw "$($Child.Name) s'est arrêté (code $($Child.Process.ExitCode))." }
        try { $response = Invoke-WebRequest $Url -TimeoutSec 2; if ($response.StatusCode -eq 200) { return } }
        catch { Start-Sleep -Milliseconds 250 }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$($Child.Name) n'est pas prêt après 45 secondes."
}
function Wait-HermesHealth($Child, [string]$Token) {
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        if ($Child.Process.HasExited) { throw "Hermes s'est arrêté (code $($Child.Process.ExitCode))." }
        $response = $null
        try {
            $response = Invoke-WebRequest 'http://127.0.0.1:8642/health/detailed' -TimeoutSec 2 -SkipHttpErrorCheck -Headers @{Authorization="Bearer $Token"}
        } catch { }
        if ($response -and $response.StatusCode -in @(401,403)) {
            throw 'Hermes refuse le secret technique local ; aucun démarrage validé.'
        }
        if ($response -and $response.StatusCode -in @(200,503)) {
            $health = $null
            try { $health = $response.Content | ConvertFrom-Json -AsHashtable } catch { }
            if ($health -and $health.platform -eq 'hermes-agent' -and $health.readiness.status) {
                if ($Child.Process.HasExited) { throw "Hermes s'est arrêté pendant son diagnostic." }
                return @{StatusCode=$response.StatusCode; Readiness=$health.readiness.status}
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'API Hermes non joignable avec le secret local après 45 secondes.'
}
$children = [Collections.Generic.List[object]]::new()
try {
    $apiEnv = $common.Clone()
    $apiEnv.ACP_GATEWAY_SERVICE_TOKEN = $secrets.gateway
    $apiEnv.ACP_EVENT_SERVICE_TOKEN = $secrets.events
    $apiEnv.ACP_BOOTSTRAP_TOKEN = $secrets.bootstrap
    $apiEnv.ACP_SESSION_COOKIE_SECURE = '0'
    $apiEnv.ACP_SECRETS_KEYS = $secrets.vault
    $apiEnv.ACP_ARTIFACT_SIGNING_KEYS = $secrets.artifacts
    $apiEnv.ACP_ARTIFACT_STORAGE_DIR = Join-Path $runtimeRoot 'artifacts'
    $apiEnv.ACP_SKILLS_STORAGE_DIR = Join-Path $runtimeRoot 'skills'
    $apiEnv.ACP_WORKER_REGISTRATION_TOKEN = $secrets.registration
    # Aucune portée d'enrôlement implicite : l'opérateur choisit son projet.
    if ($WorkerProjectId) { $apiEnv.ACP_WORKER_REGISTRATION_PROJECT_ID = $WorkerProjectId }
    $children.Add((Start-ServiceProcess 'API' $pythonExe @('-m','uvicorn','acp_api.main:app','--host','127.0.0.1','--port',"$ApiPort",'--no-access-log') $apiEnv))
    $eventEnv = $common.Clone()
    $eventEnv.ACP_EVENT_SERVICE_TOKEN = $secrets.events
    $children.Add((Start-ServiceProcess 'Événements' $pythonExe @('-m','uvicorn','acp_event_service.main:app','--host','127.0.0.1','--port',"$eventPort",'--no-access-log') $eventEnv))
    $gatewayEnv = $common.Clone()
    $gatewayEnv.ACP_GATEWAY_SERVICE_TOKEN = $secrets.gateway
    if ($WithHermes) {
        $gatewayEnv.HERMES_BASE_URL = 'http://127.0.0.1:8642'
        $gatewayEnv.HERMES_API_KEY = $secrets.hermes
        $hermesExe = Join-Path $repoRoot 'acp-data/tools/hermes-v2026.9.7/.venv/Scripts/hermes.exe'
        $hermesEnv = @{
            HERMES_HOME = Join-Path $repoRoot 'acp-data/hermes-profile'
            OBSIDIAN_VAULT_PATH = Join-Path $repoRoot 'acp-data/obsidian'
            API_SERVER_ENABLED='true'; API_SERVER_HOST='127.0.0.1'; API_SERVER_PORT='8642'
            API_SERVER_KEY=$secrets.hermes; HERMES_DISABLE_LAZY_INSTALLS='1'; PYTHONUTF8='1'
        }
        $hermesChild = Start-ServiceProcess 'Hermes' $hermesExe @('gateway','run','--no-supervise') $hermesEnv
        $children.Add($hermesChild)
    }
    $children.Add((Start-ServiceProcess 'Fournisseurs' $pythonExe @('-m','uvicorn','acp_provider_gateway.main:app','--host','127.0.0.1','--port',"$gatewayPort",'--no-access-log') $gatewayEnv))
    Wait-Health "$apiUrl/ready" $children[0]
    Wait-Health "http://127.0.0.1:$eventPort/health" $children[1]
    Wait-Health "http://127.0.0.1:$gatewayPort/health" $children[$children.Count - 1]
    if ($WithHermes) {
        $hermesHealth = Wait-HermesHealth $hermesChild $secrets.hermes
        if ($hermesHealth.StatusCode -eq 503 -or $hermesHealth.Readiness -ne 'ok') {
            Write-Output 'API Hermes joignable, mais diagnostic dégradé : disponibilité du modèle non confirmée. Aucun Run lancé.'
        } else {
            Write-Output 'API Hermes joignable ; diagnostic déclaré sain. Génération de modèle non vérifiée, aucun Run lancé.'
        }
    }
    if ($BootstrapOwner) {
        $login = Read-Host 'Identifiant du premier propriétaire'
        $password = Read-Host 'Mot de passe du premier propriétaire' -AsSecureString
        $payload = @{login=$login; display_name=$login; password=(Reveal-LocalSecret $password)} | ConvertTo-Json
        $null = Invoke-RestMethod "$apiUrl/auth/bootstrap" -Method Post -ContentType 'application/json' -Headers @{'X-ACP-Bootstrap-Token'=$secrets.bootstrap} -Body $payload
        $payload = $null
        Write-Output 'Premier compte créé. Connectez-vous depuis le desktop avec ces identifiants.'
    }
    Write-Output "Pile locale prête : API $apiUrl ; base dédiée dans $runtimeRoot."
    Write-Output 'Hermes/modèles et workers restent soumis à leur diagnostic et à leur configuration explicite.'
    if (-not $CheckStartup) {
        Write-Output 'Laisser ce terminal ouvert. Ctrl+C arrête uniquement les processus créés ici.'
        while ($true) {
            foreach ($child in $children) { if ($child.Process.HasExited) { throw "$($child.Name) s'est arrêté." } }
            Start-Sleep -Seconds 1
        }
    }
} finally {
    foreach ($child in $children) {
        if (-not $child.Process.HasExited) { $child.Process.Kill($true); $child.Process.WaitForExit(10000) | Out-Null }
        $child.Process.Dispose()
    }
}
