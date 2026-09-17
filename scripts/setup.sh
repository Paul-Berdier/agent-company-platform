#!/usr/bin/env bash
# Installation complète du monorepo (Linux / macOS)
#
# Les versions tierces sont bornées par requirements/constraints.txt, dérivé du verrou
# haché de l'image Python 3.12 (scripts/check_lock.py --write-constraints) : le poste
# local installe les mêmes versions que l'image de production.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if grep -qi microsoft /proc/version 2>/dev/null; then
    VENV=".venv-wsl"
else
    VENV=".venv"
fi
[ -d "$VENV" ] || python3 -m venv "$VENV"
PY="$VENV/bin/python"

"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install \
    -c requirements/constraints.txt \
    -e packages/contracts \
    -e "packages/database[postgresql]" \
    -e packages/provider-sdk \
    -e packages/event-sdk \
    -e packages/agent-sdk \
    -e apps/api \
    -e apps/cli \
    -e apps/event-service \
    -e apps/worker \
    -e "services/provider-gateway[test]"

"$PY" scripts/check_lock.py

npm install

echo
echo "Installation terminée. Lancez bash scripts/dev.sh"
