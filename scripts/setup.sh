#!/usr/bin/env bash
# Installation du dépôt pour le développement (Linux / macOS)
#
# Les versions tierces sont bornées par requirements/constraints.txt, dérivé du verrou
# haché Python 3.12 (scripts/check_lock.py --write-constraints) : le poste local
# installe les mêmes versions que l'intégration continue.
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
    pytest pytest-asyncio \
    -e packages/contracts \
    -e apps/worker

"$PY" scripts/check_lock.py

npm install

echo
echo "Installation terminée. Tests : $PY -m pytest -q ; npm run test:engine"
