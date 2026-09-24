"""Route /api/plugins/acp-poste/v1/meta : contenu, alertes et montage FastAPI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import meta

GREFFON = Path("/opt/hermes/plugins/acp-poste")


def _sources(tmp_path: Path, etat: object = None) -> "meta.SourcesMeta":
    fichier_etat = tmp_path / "etat-demarrage.json"
    if etat is not None:
        fichier_etat.write_text(json.dumps(etat), encoding="utf-8")
    return meta.SourcesMeta(etat_demarrage=fichier_etat)


def test_la_meta_decrit_le_contrat_et_les_versions(tmp_path):
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}, "greffons_utilisateur": {}}))
    assert donnees["contrat"] == "acp-poste/1"
    assert donnees["greffon"] == {"nom": "acp-poste", "version": "0.11.0"}
    assert donnees["hermes"]["version"] == "0.21.5"
    assert donnees["hermes"]["version_testee"] == "0.21.5"
    assert donnees["hermes"]["conforme"] is True
    assert donnees["hermes"]["commit"] == "f97608f178d1ffeca59860195ab7da295f7c8e5f"
    assert donnees["image"]["condensat_index"] == (
        "sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7")
    assert donnees["openrpc"]["info_version"] == "1"
    assert donnees["openrpc"]["methodes"] == 237
    assert donnees["openrpc"]["identique"] is True
    assert donnees["alertes"] == []


def test_sans_etat_de_demarrage_la_meta_dit_inconnu(tmp_path):
    donnees = meta.construire_meta(_sources(tmp_path))
    assert donnees["demarrage"] is None
    assert any("État du démarrage inconnu" in a for a in donnees["alertes"])


def test_un_soul_divergent_et_des_greffons_utilisateur_sont_signales(tmp_path):
    etat = {"soul": {"etat": "divergent"}, "greffons_utilisateur": {"dossiers": ["outil"]}}
    alertes = meta.construire_meta(_sources(tmp_path, etat))["alertes"]
    assert any("SOUL.md a été modifié" in a for a in alertes)
    assert any("outil" in a for a in alertes)


def test_la_meta_expose_l_etat_de_la_portee_geree(tmp_path):
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}, "greffons_utilisateur": {}}))
    # Sous pytest, get_managed_dir() renvoie None sans détournement : aucune alerte de portée.
    assert donnees["environnement"]["managed_dir_attendu"] == "/etc/hermes"
    assert donnees["environnement"]["hermes_managed_dir_present"] is False
    assert not any("Portée gérée détournée" in a for a in donnees["alertes"])


def test_hermes_managed_dir_dans_l_environnement_declenche_une_alerte(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED_DIR", "/opt/data/faux-gere")
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}, "greffons_utilisateur": {}}))
    assert donnees["environnement"]["hermes_managed_dir_present"] is True
    assert donnees["environnement"]["managed_dir_conforme"] is False
    assert any("Portée gérée détournée" in a for a in donnees["alertes"])


def test_un_contrat_openrpc_different_est_signale(tmp_path):
    autre = tmp_path / "openrpc.json"
    autre.write_text(json.dumps({"info": {"version": "2"}, "methods": []}), encoding="utf-8")
    sources = meta.SourcesMeta(openrpc_installe=autre, etat_demarrage=tmp_path / "absent.json")
    donnees = meta.construire_meta(sources)
    assert donnees["openrpc"]["identique"] is False
    assert donnees["openrpc"]["info_version"] == "2"
    assert any("diffère de la copie épinglée" in a for a in donnees["alertes"])


def test_le_routeur_du_tableau_de_bord_sert_la_meta():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("acp_poste_plugin_api_test", GREFFON / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    application = FastAPI()
    application.include_router(module.router, prefix="/api/plugins/acp-poste")
    reponse = TestClient(application).get("/api/plugins/acp-poste/v1/meta")
    assert reponse.status_code == 200
    assert reponse.json()["contrat"] == "acp-poste/1"


def test_le_manifeste_du_tableau_de_bord_monte_l_api_sans_onglet():
    manifeste = json.loads((GREFFON / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    assert manifeste["name"] == "acp-poste"
    assert manifeste["api"] == "plugin_api.py"
    assert manifeste["tab"]["hidden"] is True
    assert (GREFFON / "dashboard" / manifeste["entry"]).is_file()
