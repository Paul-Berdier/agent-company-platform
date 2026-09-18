# Recompile le verrou Python 3.12 (requirements/python-3.12.lock.txt) et le fichier
# de contraintes local (requirements/constraints.txt).
#
# La compilation a lieu DANS un conteneur python:3.12-slim, jamais sur le poste :
# les hachés et les marqueurs de plateforme doivent être ceux de l'image de
# production (Linux, CPython 3.12), pas ceux d'un Windows en 3.13. pip-tools n'est
# donc jamais installé localement.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$image = "python:3.12-slim"
$compile = "pip install --quiet pip-tools && pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/python-3.12.lock.txt requirements/python-3.12.in"

docker run --rm -v "${root}:/w" -w /w $image sh -c $compile
if ($LASTEXITCODE -ne 0) {
    throw "pip-compile a échoué dans le conteneur (code $LASTEXITCODE) ; le verrou n'est pas à jour."
}

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $root "scripts\check_lock.py") --write-constraints
if ($LASTEXITCODE -ne 0) {
    throw "check_lock.py a refusé le verrou (code $LASTEXITCODE)."
}
Write-Host "Verrou et contraintes régénérés ; relancez scripts/check_lock.py avant de commiter." -ForegroundColor Green
