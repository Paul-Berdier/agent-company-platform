#!/usr/bin/env bash
# Lance tous les services de développement (Linux / macOS)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY=".venv/bin/python"

"$PY" -m acp_api.seed

"$PY" -m uvicorn acp_api.main:app --port 8000 &
"$PY" -m uvicorn acp_event_service.main:app --port 8001 &
"$PY" -m uvicorn acp_provider_gateway.main:app --port 8002 &
"$PY" -m acp_worker.main &

trap 'kill 0' EXIT
echo "api:8000  event-service:8001  provider-gateway:8002  worker: démarré"
echo "Interface : http://localhost:5173"
npm run dev:web
