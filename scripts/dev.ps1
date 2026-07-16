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
Start-Process -WorkingDirectory $root $py -ArgumentList "-m","acp_worker.main"

Write-Host "api:8000  event-service:8001  provider-gateway:8002  worker: démarré" -ForegroundColor Green
Write-Host "Interface : http://localhost:5173" -ForegroundColor Green
npm run dev:web
