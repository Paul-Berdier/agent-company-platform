# Lance tous les services de développement (Windows PowerShell)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = "$root\.venv\Scripts\python.exe"

# Base + seed de démonstration
& $py -m acp_api.seed

Start-Process -WorkingDirectory $root $py -ArgumentList "-m","uvicorn","acp_api.main:app","--port","8000"
Start-Process -WorkingDirectory $root $py -ArgumentList "-m","uvicorn","acp_event_service.main:app","--port","8001"
Start-Process -WorkingDirectory $root $py -ArgumentList "-m","uvicorn","acp_provider_gateway.main:app","--port","8002"
$workerStateDir = if ($env:ACP_WORKER_STATE_DIR) { $env:ACP_WORKER_STATE_DIR } else { Join-Path $HOME ".agent-company-worker" }
$workerState = Join-Path $workerStateDir "worker.json"
if (Test-Path -LiteralPath $workerState) {
    Start-Process -WorkingDirectory $root $py -ArgumentList "-m","acp_worker.cli","start" -WindowStyle Hidden
    $workerMessage = "worker: démarré"
} else {
    $workerMessage = "worker: non enregistré (voir docs/workers/windows-worker.md)"
}

Write-Host "api:8000  event-service:8001  provider-gateway:8002  $workerMessage" -ForegroundColor Green
Write-Host "Interface : http://localhost:5173" -ForegroundColor Green
npm run dev:web
