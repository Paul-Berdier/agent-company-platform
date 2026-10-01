"""Faux Hermes HTTPS pour les tests de contrat du poste (cahier P5 § 14.2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent


def _module():
    spec = importlib.util.spec_from_file_location("faux_hermes", ICI / "faux_hermes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FAUX_HERMES = _module()


@pytest.fixture(scope="session")
def autorite(tmp_path_factory):
    return FAUX_HERMES.AutoriteDeTest(tmp_path_factory.mktemp("autorite-de-test"))


@pytest.fixture
def hermes(autorite):
    faux = FAUX_HERMES.FauxHermes(autorite).demarrer()
    try:
        yield faux
    finally:
        faux.arreter()


@pytest.fixture
def module_faux_hermes():
    return FAUX_HERMES
