"""Outillage commun des tests navigateur (hermes/tests/e2e), pilotés depuis l'hôte par Playwright.

ACP_E2E_OBLIGATOIRE=1 (la CI) change toute absence de Playwright ou de Chromium en ÉCHEC ; sans elle
(poste local), les tests sont IGNORÉS avec la raison exacte. Aucun navigateur n'est téléchargé ici.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contrat"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pile_identite import Pile  # noqa: E402

OBLIGATOIRE = os.environ.get("ACP_E2E_OBLIGATOIRE", "").strip() == "1"
CAPTURES = os.environ.get("ACP_E2E_CAPTURES", "").strip()


def afficher(titre: str, texte: str) -> None:
    print(f"\n===== {titre} =====\n{texte.rstrip()}\n", flush=True)


def manque(raison: str) -> None:
    if OBLIGATOIRE:
        pytest.fail(f"{raison} (ACP_E2E_OBLIGATOIRE=1 : l'absence est un échec, jamais un test ignoré)", pytrace=False)
    pytest.skip(raison)


def image(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        pytest.fail(f"{nom} n'est pas défini : ce test exige les images construites.", pytrace=False)
    return valeur


@pytest.fixture(scope="module")
def playwright_sync():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        manque(f"Playwright n'est pas installé ({exc}) : pip install --require-hashes -r "
               f"hermes/tests/requirements-e2e.txt")
    with sync_playwright() as p:
        executable = Path(p.chromium.executable_path)
        if not executable.exists():
            manque(f"Chromium de Playwright absent ({executable}) : rien n'est téléchargé par ce test")
        yield p


@pytest.fixture(scope="module")
def pile():
    p = Pile()
    yield p
    p.nettoyer()
