import json
import os
from pathlib import Path

from .definitions import ModuleManifest

# Module "core" intégré : thème de bureau générique, aucun rôle métier.
CORE_MANIFEST = ModuleManifest(
    module="core",
    description="Module de base : bureau générique, rôle polyvalent.",
    departments=[
        {
            "department_type": "general",
            "name": "General Office",
            "office_theme": "default",
            "stations": [
                {"id": "desk-1", "name": "Desk 1", "kind": "desk", "x": 2, "y": 2},
                {"id": "desk-2", "name": "Desk 2", "kind": "desk", "x": 5, "y": 2},
                {"id": "desk-3", "name": "Desk 3", "kind": "desk", "x": 2, "y": 5},
                {"id": "desk-4", "name": "Desk 4", "kind": "desk", "x": 5, "y": 5},
            ],
            "available_animations": ["sit", "type", "walk", "coffee", "think"],
            "status_mapping": {
                "idle": "coffee",
                "thinking": "think",
                "working": "type",
                "reviewing": "think",
                "blocked": "sit",
                "offline": "away",
            },
            "roles": [
                {
                    "id": "generalist",
                    "name": "Generalist",
                    "capabilities": ["plan", "execute"],
                }
            ],
        }
    ],
)


def load_module_manifest(path: Path) -> ModuleManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ModuleManifest.model_validate(data)


def load_modules(plugins_dir: str | os.PathLike | None = None) -> dict[str, ModuleManifest]:
    """Charge le module core + tous les plugins présents sur disque.

    Un plugin manquant ou invalide est ignoré : le cœur fonctionne sans
    aucun module métier.
    """
    modules: dict[str, ModuleManifest] = {"core": CORE_MANIFEST}
    root = Path(plugins_dir or os.environ.get("ACP_PLUGINS_DIR", "./plugins"))
    if not root.is_dir():
        return modules
    for manifest_path in sorted(root.glob("*/plugin.json")):
        try:
            manifest = load_module_manifest(manifest_path)
            modules[manifest.module] = manifest
        except Exception:  # noqa: BLE001 — un plugin cassé ne bloque pas la plateforme
            continue
    return modules
