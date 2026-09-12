"""Vérifie que tous les composants publiables portent la version du produit."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

PYPROJECTS = (
    "apps/api/pyproject.toml",
    "apps/cli/pyproject.toml",
    "apps/event-service/pyproject.toml",
    "apps/worker/pyproject.toml",
    "packages/agent-sdk/pyproject.toml",
    "packages/contracts/pyproject.toml",
    "packages/database/pyproject.toml",
    "packages/event-sdk/pyproject.toml",
    "packages/provider-sdk/pyproject.toml",
    "services/provider-gateway/pyproject.toml",
)

PACKAGE_JSONS = (
    "package.json",
    "apps/web/package.json",
    "packages/contracts/package.json",
    "packages/pixel-office-engine/package.json",
    "packages/ui/package.json",
)

FASTAPI_APPS = (
    "apps/api/src/acp_api/main.py",
    "apps/event-service/src/acp_event_service/main.py",
    "services/provider-gateway/src/acp_provider_gateway/main.py",
)

PYTHON_VERSION_MODULES = ("apps/cli/src/acp_cli/__init__.py",)

LOCK_PACKAGES = ("", "apps/web", "packages/contracts", "packages/pixel-office-engine", "packages/ui")


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

    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    report(errors, "package-lock.json", lock.get("version"))
    for package in LOCK_PACKAGES:
        report(
            errors,
            f"package-lock.json#packages/{package or '<root>'}",
            lock.get("packages", {}).get(package, {}).get("version"),
        )

    version_pattern = re.compile(r'\bversion\s*=\s*"([^"]+)"')
    for relative in FASTAPI_APPS:
        match = version_pattern.search((ROOT / relative).read_text(encoding="utf-8"))
        report(errors, relative, match.group(1) if match else None)

    module_version_pattern = re.compile(r'\b__version__\s*=\s*"([^"]+)"')
    for relative in PYTHON_VERSION_MODULES:
        match = module_version_pattern.search((ROOT / relative).read_text(encoding="utf-8"))
        report(errors, relative, match.group(1) if match else None)

    if errors:
        print("Dérive de version détectée :", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Toutes les versions publiables sont synchronisées sur {EXPECTED}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
