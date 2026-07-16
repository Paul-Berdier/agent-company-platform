#!/usr/bin/env bash
# Installation complète du monorepo (Linux / macOS)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ -d .venv ] || python3 -m venv .venv
PY=".venv/bin/python"

"$PY" -m pip install --upgrade pip
"$PY" -m pip install \
    -e packages/contracts \
    -e packages/database \
    -e packages/provider-sdk \
    -e packages/event-sdk \
    -e packages/agent-sdk \
    -e apps/api \
    -e apps/event-service \
    -e apps/worker \
    -e "services/provider-gateway[test]"

npm install

echo
echo "Installation terminée. Lancez ./scripts/dev.sh"
