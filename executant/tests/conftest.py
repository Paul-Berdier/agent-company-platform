"""Fixtures des tests de l'image de l'exécutant (outillage : outils_image.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from outils_image import Ressources, exiger  # noqa: E402


@pytest.fixture
def ressources():
    r = Ressources()
    yield r
    r.nettoyer()


@pytest.fixture(scope="session")
def image() -> str:
    return exiger("ACP_IMAGE_EXECUTANT")


@pytest.fixture(scope="session")
def image_factice() -> str:
    return exiger("ACP_IMAGE_EXECUTANT_FACTICE")
