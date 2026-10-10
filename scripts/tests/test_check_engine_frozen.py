"""Fonctions pures de la garde du gel du moteur (sans Git ni étiquette)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_engine_frozen", Path(__file__).resolve().parents[1] / "check_engine_frozen.py"
)
assert _SPEC is not None and _SPEC.loader is not None
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)

ENGINE = "packages/pixel-office-engine"


def lock(**packages: dict) -> dict:
    return {
        "packages": {
            "": {"workspaces": [ENGINE]},
            ENGINE: {
                "name": "@acp/pixel-office-engine",
                "dependencies": {"phaser": "^3"},
                "devDependencies": {"vitest": "^5"},
            },
            **packages,
        }
    }


def entry(version: str, *, integrity: str = "sha512-x", **extra) -> dict:
    return {
        "version": version,
        "resolved": f"https://registry.example/{version}.tgz",
        "integrity": integrity,
        **extra,
    }


def test_node_lookup_skips_nested_node_modules_segments():
    assert guard._lookup_dirs(f"{ENGINE}/node_modules/vitest") == [
        f"{ENGINE}/node_modules/vitest/node_modules",
        f"{ENGINE}/node_modules",
        "packages/node_modules",
        "node_modules",
    ]


def test_the_closure_follows_dependencies_peers_and_engine_dev_dependencies():
    data = lock(
        **{
            "node_modules/phaser": entry("3.90.0", dependencies={"eventemitter3": "^5"}),
            "node_modules/eventemitter3": entry("5.0.4"),
            f"{ENGINE}/node_modules/vitest": entry(
                "5.0.0",
                peerDependencies={"vite": "*", "jsdom": "*"},
                peerDependenciesMeta={"jsdom": {"optional": True}},
            ),
            f"{ENGINE}/node_modules/vite": entry("8.3.0", optionalDependencies={"fsevents": "*"}),
            "node_modules/unrelated": entry("1.0.0"),
        }
    )

    names = {guard._package_name(path) for path in guard.engine_closure(data)}

    assert names == {"phaser", "eventemitter3", "vitest", "vite"}


def test_the_signature_ignores_hoisting_but_not_versions_or_integrity():
    hoisted = lock(
        **{
            "node_modules/phaser": entry("3.90.0"),
            "node_modules/vitest": entry("5.0.0"),
        }
    )
    nested = lock(
        **{
            "node_modules/phaser": entry("3.90.0"),
            f"{ENGINE}/node_modules/vitest": entry("5.0.0"),
            "node_modules/other-workspace-dependency": entry("9.9.9"),
        }
    )
    tampered = lock(
        **{
            "node_modules/phaser": entry("3.90.0", integrity="sha512-autre"),
            "node_modules/vitest": entry("5.0.0"),
        }
    )

    assert guard.closure_signature(hoisted) == guard.closure_signature(nested)
    assert guard.closure_signature(hoisted) != guard.closure_signature(tampered)


def test_a_missing_required_dependency_is_refused():
    with pytest.raises(guard.GelRompu, match="vitest"):
        guard.engine_closure(lock(**{"node_modules/phaser": entry("3.90.0")}))


def test_the_gitignore_block_is_found_and_compared_verbatim():
    archived = "node_modules/\n\n# Third-party licensed pixel-art assets (LimeZu...)\nLimzu/\n*.aseprite\n\n# Autre\n"
    block = guard.gitignore_block(archived)

    assert block == ["# Third-party licensed pixel-art assets (LimeZu...)", "Limzu/", "*.aseprite"]
    assert guard.contains_block("x\r\n" + "\r\n".join(block) + "\r\n", block)
    assert not guard.contains_block(archived.replace("Limzu/", "Limezu/"), block)
