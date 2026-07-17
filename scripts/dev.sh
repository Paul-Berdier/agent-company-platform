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
WORKER_STATE_DIR="${ACP_WORKER_STATE_DIR:-$HOME/.agent-company-worker}"
if [[ -f "$WORKER_STATE_DIR/worker.json" ]]; then
  "$PY" -m acp_worker.cli start &
  WORKER_MESSAGE="worker: démarré"
else
  WORKER_MESSAGE="worker: non enregistré (voir docs/workers/windows-worker.md)"
fi

trap 'kill 0' EXIT
echo "api:8000  event-service:8001  provider-gateway:8002  $WORKER_MESSAGE"
echo "Interface : http://localhost:5173"
npm run dev:web
