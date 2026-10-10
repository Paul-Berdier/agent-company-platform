#!/usr/bin/env bash
# Recompile le verrou Python 3.12 (requirements/python-3.12.lock.txt) et le fichier
# de contraintes local (requirements/constraints.txt).
#
# La compilation a lieu DANS un conteneur python:3.12-slim, jamais sur le poste :
# les hachés et les marqueurs de plateforme doivent être ceux de l'image de
# production (Linux, CPython 3.12). pip-tools n'est donc jamais installé localement.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="python:3.12-slim"
COMPILE="pip install --quiet pip-tools && pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/python-3.12.lock.txt requirements/python-3.12.in"

docker run --rm -v "${ROOT}:/w" -w /w "$IMAGE" sh -c "$COMPILE"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/.venv-wsl/bin/python" ]; then
    PY="$ROOT/.venv-wsl/bin/python"
else
    PY="python3"
fi
"$PY" "$ROOT/scripts/check_lock.py" --write-constraints

# Étape P5 : verrou d'EXÉCUTION du poste Windows (pydantic seul), aux mêmes versions que le verrou du dépôt
# (requirements/poste-3.12.in contraint par constraints.txt, régénéré juste au-dessus).
COMPILE_POSTE="pip install --quiet pip-tools && pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/poste-3.12.lock.txt requirements/poste-3.12.in"
docker run --rm -v "${ROOT}:/w" -w /w "$IMAGE" sh -c "$COMPILE_POSTE"
"$PY" "$ROOT/scripts/check_lock.py"
echo "Verrous et contraintes régénérés ; relancez scripts/check_lock.py avant de commiter."
