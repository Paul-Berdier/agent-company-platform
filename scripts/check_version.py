"""Vérifie que tous les composants publiables portent la version du produit.

Refonte « Hermes au centre » : seuls les composants conservés sont vérifiés. Le
client desktop lit directement le fichier ``VERSION`` (``apps/desktop/cmake/
AcpVersion.cmake``) et n'en garde aucune copie.

``packages/pixel-office-engine`` est volontairement ABSENT de cette liste : le moteur
est gelé octet pour octet sur l'étiquette ``archive/acp-0.10.0-avant-hermes``
(``scripts/check_engine_frozen.py``). S'il y figurait, chaque hausse de version
obligerait à modifier son ``package.json``, donc à rompre le gel. Son entrée dans
``package-lock.json`` garde de même la version que déclare son ``package.json``.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

PYPROJECTS = (
    "apps/poste/pyproject.toml",
    "hermes/plugins/acp-poste/contrat/pyproject.toml",
)

PACKAGE_JSONS = ("package.json", "hermes/plugins/acp-poste/dashboard/manifest.json")

# Manifestes YAML des greffons groupés de l'image Hermes (champ ``version`` de premier
# niveau, lu sans PyYAML : ce script ne dépend que de la bibliothèque standard).
PLUGIN_YAMLS = ("hermes/plugins/acp-poste/plugin.yaml",)
_VERSION_YAML = re.compile(r'^version:\s*"?([^"\s#]+)"?\s*(?:#.*)?$', re.MULTILINE)

# Seul le paquet racine est versionné par le produit dans le verrou npm.
LOCK_PACKAGES = ("",)


def report(errors: list[str], path: str, actual: object) -> None:
    if actual != EXPECTED:
        errors.append(f"{path}: version {actual!r}, attendu {EXPECTED!r}")


def main() -> int:
    errors: list[str] = []

    for relative in PYPROJECTS:
        data = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))
        report(errors, relative, data.get("project", {}).get("version"))

    for relative in PACKAGE_JSONS:
        data = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        report(errors, relative, data.get("version"))

    for relative in PLUGIN_YAMLS:
        found = _VERSION_YAML.findall((ROOT / relative).read_text(encoding="utf-8"))
        report(errors, relative, found[0] if len(found) == 1 else None)

    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    report(errors, "package-lock.json", lock.get("version"))
    for package in LOCK_PACKAGES:
        report(
            errors,
            f"package-lock.json#packages/{package or '<root>'}",
            lock.get("packages", {}).get(package, {}).get("version"),
        )

    if errors:
        print("Dérive de version détectée :", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Toutes les versions publiables sont synchronisées sur {EXPECTED}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
