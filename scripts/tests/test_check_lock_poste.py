"""Verrou d'exécution du poste Windows (``requirements/poste-3.12.lock.txt``, étape P5, décision D53) : hachés, mêmes
versions que le verrou du dépôt, dépendances directes du poste présentes, aucun outil de test ni de construction."""

from __future__ import annotations

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _module():
    spec = importlib.util.spec_from_file_location("check_lock", RACINE / "scripts" / "check_lock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _module()
PROJETS = {chemin: (RACINE / chemin).read_text(encoding="utf-8") for chemin in CHECK.POSTE_PROJECTS}
PINS = CHECK.parse_pins((RACINE / "requirements" / "python-3.12.lock.txt").read_text(encoding="utf-8"))


def _verrou(**pins: str) -> str:
    return "".join(f"{nom}=={version} \\\n    --hash=sha256:{'0' * 64}\n" for nom, version in pins.items())


def test_le_verrou_livre_est_coherent():
    texte = CHECK.POSTE_LOCK_PATH.read_text(encoding="utf-8")
    assert CHECK.check_poste(texte, PINS, PROJETS) == []
    assert set(CHECK.parse_pins(texte)) == {"pydantic", "pydantic-core", "annotated-types", "typing-extensions",
                                             "typing-inspection"}


def test_outil_de_test_refuse():
    texte = _verrou(pydantic=PINS["pydantic"], pytest=PINS["pytest"])
    assert any("pytest n'a rien à faire sur le poste" in e for e in CHECK.check_poste(texte, PINS, PROJETS))


def test_version_differente_refusee():
    texte = _verrou(pydantic="2.0.0")
    assert any("diffère du verrou du dépôt" in e for e in CHECK.check_poste(texte, PINS, PROJETS))


def test_hache_absent_refuse():
    texte = f"pydantic=={PINS['pydantic']}\n"
    assert any("sans haché" in e for e in CHECK.check_poste(texte, PINS, PROJETS))


def test_dependance_du_poste_absente():
    texte = _verrou(**{"annotated-types": PINS["annotated-types"]})
    assert any("pydantic (dépendance de apps/poste/pyproject.toml) absent" in e
               for e in CHECK.check_poste(texte, PINS, PROJETS))
