"""Adaptateur kanban d'acp-poste contre le kanban de Hermes à la version épinglée."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

GREFFON = Path("/opt/hermes/plugins/acp-poste")
TEMOIN = Path("/opt/acp-tests/outils/temoin_compat")


@pytest.fixture
def adaptateur(tmp_path, monkeypatch):
    """HERMES_HOME jetable : le kanban est créé sous tmp_path, jamais sous /opt/data."""
    for nom in ("HERMES_KANBAN_HOME", "HERMES_KANBAN_DB", "HERMES_KANBAN_BOARD"):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    module = importlib.import_module("kanban_adapter")
    return module


def test_chaque_fonction_vient_de_son_module_de_definition(adaptateur):
    for nom, module_attendu in adaptateur.MODULES_DE_DEFINITION.items():
        fonction = getattr(adaptateur, nom)
        assert fonction.__module__ == module_attendu, (nom, fonction.__module__)
    # Les deux pointeurs de compatibilité connus ne sont pas empruntés.
    assert adaptateur.connect.__module__ == "hermes_cli.kanban_db_connect"
    assert adaptateur.heartbeat_worker.__module__ == "hermes_cli.kanban_db_dispatch"


def test_le_scan_de_compatibilite_de_hermes_ne_trouve_rien_dans_le_greffon():
    from hermes_cli.plugin_compat import scan_plugin

    assert scan_plugin(GREFFON) == []


def test_le_scan_de_compatibilite_repere_le_greffon_temoin():
    from hermes_cli.plugin_compat import scan_plugin

    impacts = scan_plugin(TEMOIN)
    assert [h.old for h in impacts] == ["hermes_cli.kanban_db.connect"]
    assert impacts[0].new == "hermes_cli.kanban_db_connect.connect"


def test_une_carte_creee_en_triage_sur_le_tableau_poste(adaptateur, tmp_path):
    adaptateur.assurer_tableau()
    identifiant = adaptateur.creer_carte_triage(
        titre="Lire le README", corps="Consigne de test", cle_idempotence="essai-1")
    carte = adaptateur.lire_carte(identifiant)
    assert carte is not None
    assert carte.status == "triage"
    assert carte.assignee == "poste-windows"
    assert carte.idempotency_key == "essai-1"
    # Idempotence : la même clé rend la même carte.
    assert adaptateur.creer_carte_triage(titre="x", corps="y", cle_idempotence="essai-1") == identifiant
    assert [c.id for c in adaptateur.lister_cartes(statut="triage")] == [identifiant]
    # La base du tableau « poste » est distincte de celle du tableau par défaut.
    from hermes_cli.kanban_db import kanban_db_path

    assert kanban_db_path(board="poste") != kanban_db_path(board="default")
    assert kanban_db_path(board="poste").is_file()
    assert str(kanban_db_path(board="poste")).startswith(str(tmp_path))


def test_la_cle_d_idempotence_est_obligatoire(adaptateur):
    adaptateur.assurer_tableau()
    with pytest.raises(ValueError, match="idempotence"):
        adaptateur.creer_carte_triage(titre="x", corps="y", cle_idempotence="")
