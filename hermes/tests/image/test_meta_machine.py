"""Bloc « machine » de /v1/meta (étape P5, cahier P5 § 12.6) : fournisseur et chemins à jeton DANS ce processus,
fournisseurs de session, postes par état, dernier inventaire, alertes en français (fournisseur absent, deux processus
sur le même jeton, nom d'hôte « acp-poste », aucune connexion interactive)."""

from __future__ import annotations

import time

import pytest

import meta
from conftest import inventaire_factice, poste_confirme


@pytest.fixture
def fournisseur(noyau):
    from hermes_cli.dashboard_auth.registry import register_global_provider, unregister_global_provider
    from hermes_cli.dashboard_auth.token_auth import register_token_route

    from acp_poste_contrat.machine import ROUTES

    jeton_machine = meta.sous_module_noyau("jeton_machine")
    instance = jeton_machine.FournisseurJetonMachine()
    register_global_provider(instance)
    for chemin in ROUTES:
        register_token_route(chemin)
    yield instance
    unregister_global_provider(instance.name, instance)


def test_bloc_machine_conforme(fournisseur, noyau, conn, monkeypatch):
    jeton_machine = meta.sous_module_noyau("jeton_machine")
    monkeypatch.setattr(jeton_machine.aa, "list_session_providers",
                        lambda: [type("S", (), {"name": "self-hosted"})()])
    bloc, alertes = meta.bloc_machine()
    assert bloc["fournisseur"] == "enregistre" and all(bloc["chemins_a_jeton"].values())
    assert list(bloc["chemins_a_jeton"]) == ["/api/plugins/acp-poste/machine/v1/enrolement",
                                             "/api/plugins/acp-poste/machine/v1/reclamer",
                                             "/api/plugins/acp-poste/machine/v1/inventaire"]
    assert bloc["base"] == "ok" and bloc["machines"] == {"a_confirmer": 0, "actif": 0, "revoque": 0}
    assert bloc["dernier_inventaire"] is None and alertes == []
    machine, _jeton = poste_confirme(noyau, conn)
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_factice())
    bloc, alertes = meta.bloc_machine()
    assert bloc["machines"]["actif"] == 1 and isinstance(bloc["dernier_inventaire"], int) and alertes == []


def test_fournisseur_absent_et_aucune_session(noyau, monkeypatch):
    jeton_machine = meta.sous_module_noyau("jeton_machine")
    monkeypatch.setattr(jeton_machine.aa, "list_session_providers", lambda: [])
    monkeypatch.setattr(jeton_machine.aa, "list_token_providers", lambda: [])
    bloc, alertes = meta.bloc_machine()
    assert bloc["fournisseur"] == "absent"
    assert "Le fournisseur de jeton machine n'est pas enregistré dans le tableau de bord." in alertes
    assert "Aucun fournisseur de connexion interactive : personne ne peut se connecter." in alertes


def test_deux_processus_sur_le_meme_jeton(fournisseur, noyau, conn):
    machine, _jeton = poste_confirme(noyau, conn)
    conn.execute("UPDATE machines SET remplacements_minute = 6, remplacements_depuis = ? WHERE id = ?",
                 (int(time.time()), machine))
    _bloc, alertes = meta.bloc_machine()
    assert "Deux processus semblent utiliser le même jeton machine." in alertes


def test_nom_d_hote_acp_poste(fournisseur, noyau, monkeypatch):
    import socket

    monkeypatch.setattr(socket, "gethostname", lambda: "acp-poste")
    _bloc, alertes = meta.bloc_machine()
    assert ("Le nom d'hôte du conteneur vaut « acp-poste » : un réclamant du poste serait pris pour un worker "
            "local.") in alertes


def test_la_meta_porte_le_bloc_machine(noyau, tmp_path, monkeypatch):
    monkeypatch.setattr(meta, "etat_garde_execution", lambda decouvrir=None: {"alerte": None})
    monkeypatch.setattr(meta, "bloc_catalogue", lambda: ({}, {}, []))
    donnees = meta.construire_meta(meta.SourcesMeta(etat_demarrage=tmp_path / "absent.json"))
    assert "machine" in donnees and donnees["machine"]["base"] == "ok"
