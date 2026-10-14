"""Simulateurs d’inventaire : aucun Docker, processus agent ou compte réel."""
import importlib.util
from pathlib import Path
import sys

import pytest
from acp_poste_contrat.inventaire import InventairePoste

RACINE = Path(__file__).resolve().parents[2]


def _module(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def simulateur(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    fp = _module("_faux_poste_test_distant", RACINE / "hermes/tests/outils/faux_poste.py")
    monkeypatch.setattr(fp, "FIXTURES", RACINE / "hermes/tests/outils/fixtures_machine")
    return fp


def test_inventaire_windows_reste_un_temoin_refuse(simulateur):
    distant = _module("_garde_fixture_distante", RACINE / "hermes/plugins/acp-poste/noyau/distant.py")
    inventaire = simulateur.inventaire_de_l_exemple()
    valide = InventairePoste.model_validate(inventaire)
    assert valide.poste.plateforme == "windows"
    assert distant.raison_inventaire(inventaire) is not None
    assert inventaire["bac_a_sable_codex"] is not None


def test_inventaire_linux_simule_admis_garde_catalogues_historiques(simulateur):
    distant = _module("_garde_fixture_distante", RACINE / "hermes/plugins/acp-poste/noyau/distant.py")
    ancien = simulateur.inventaire_de_l_exemple()
    inventaire = simulateur.inventaire_de_l_exemple(linux_distant=True)
    InventairePoste.model_validate(inventaire)
    assert distant.raison_inventaire(inventaire) is None
    assert (inventaire["poste"]["plateforme"], inventaire["poste"]["hote"]) == ("linux", "railway")
    assert inventaire["bac_a_sable_codex"] is None
    assert inventaire["isolement_linux"]["ecriture_admise"] == {"codex": True, "claude": True}
    assert inventaire["isolement_linux"]["sonde_le"] == inventaire["releve_le"]
    assert set(inventaire["politique"]["conditions"]) == {"codex", "claude"}
    for nouveau, avant in zip(inventaire["releves"], ancien["releves"], strict=True):
        assert nouveau["modeles"] == avant["modeles"]
        assert nouveau["origine_liste"] == avant["origine_liste"]
