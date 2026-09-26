"""Route /api/plugins/acp-poste/v1/meta : contenu, alertes et montage FastAPI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import meta
from conftest import executer_python

GREFFON = Path("/opt/hermes/plugins/acp-poste")
_ETAT_GARDE_REEL = meta.etat_garde_execution
GARDE_PRESENTE = {
    "processus": meta.LIBELLE_PROCESSUS, "decouverte": "reussie", "erreur_decouverte": None, "enregistree": True,
    "presente_dans_le_gestionnaire": True, "outils_admis": [], "outils_retires": [], "alerte": None,
}


CATALOGUE_CONFORME = {"verrou_sha256": "0" * 64, "skills_actives": 16, "skills_attendues": 16, "context7": "connecte",
                      "external_dirs_conforme": True, "desactivations_conformes": True, "ecarts": 0}
INTERFACE = {"greffons": {"acp-interface": "0.11.0", "acp-catalogue": "0.11.0"}, "sdk_attendu": "1.x"}


@pytest.fixture(autouse=True)
def garde_presente_par_defaut(monkeypatch, tmp_path):
    """Hors des tests de la garde, l'état de la garde est simulé présent : le processus pytest
    n'a pas découvert les greffons (et ne doit pas le faire sur /opt/data). Hors des tests du
    catalogue (test_catalogue_route.py), le bloc catalogue est simulé conforme : ce processus n'a pas
    de volume préparé par 05-acp."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(meta, "etat_garde_execution", lambda decouvrir=None: dict(GARDE_PRESENTE))
    monkeypatch.setattr(meta, "bloc_catalogue", lambda: (dict(CATALOGUE_CONFORME), dict(INTERFACE), []))


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
    assert donnees["catalogue"] == CATALOGUE_CONFORME and donnees["interface"] == INTERFACE
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


def _routeur(nom: str, monkeypatch):
    """plugin_api.py chargé par son chemin, comme le fait le tableau de bord ; son meta.py est un
    autre objet module que celui des tests : l'état de la garde y est simulé présent aussi."""
    spec = importlib.util.spec_from_file_location(nom, GREFFON / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module._meta, "etat_garde_execution", lambda decouvrir=None: dict(GARDE_PRESENTE))
    monkeypatch.setattr(module._meta, "bloc_catalogue", lambda: (dict(CATALOGUE_CONFORME), dict(INTERFACE), []))
    return module


def test_le_routeur_du_tableau_de_bord_sert_la_meta(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    module = _routeur("acp_poste_plugin_api_test", monkeypatch)
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


# ======================================================================= étape P2


def test_meta_garde_execution_decouverte_qui_leve(tmp_path, monkeypatch):
    """La découverte des greffons lève dans le processus du tableau de bord : alerte, jamais
    « présente »."""
    monkeypatch.setattr(meta, "etat_garde_execution", _ETAT_GARDE_REEL)

    def decouverte_en_panne():
        raise RuntimeError("panne de découverte")

    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}), decouvrir=decouverte_en_panne)
    garde = donnees["garde_execution"]
    assert garde["processus"] == "processus du tableau de bord (sert /api/ws)"
    assert garde["decouverte"] == "echec" and garde["erreur_decouverte"] == "RuntimeError"
    assert garde["presente_dans_le_gestionnaire"] is not True
    assert meta.ALERTE_GARDE_ABSENTE in donnees["alertes"]


def test_meta_garde_execution_crochet_absent(tmp_path, monkeypatch):
    """Découverte « réussie » mais aucun crochet dans le gestionnaire : alerte."""
    monkeypatch.setattr(meta, "etat_garde_execution", _ETAT_GARDE_REEL)
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}), decouvrir=lambda: None)
    assert donnees["garde_execution"]["decouverte"] == "reussie"
    assert donnees["garde_execution"]["presente_dans_le_gestionnaire"] is False
    assert meta.ALERTE_GARDE_ABSENTE in donnees["alertes"]


def test_meta_garde_execution_apres_vraie_decouverte(tmp_path):
    """Processus neuf : la route découvre elle-même les greffons (idempotent), puis lit l'état de
    la garde dans CE processus ; aucune alerte de garde."""
    home = tmp_path / "home-neuf"
    home.mkdir()
    code = ("import sys; sys.path.insert(0, '/opt/hermes/plugins/acp-poste'); import meta; "
            "resultat = meta.etat_garde_execution()")
    garde = executer_python(code, env={"HERMES_HOME": str(home), "PATH": "/usr/bin:/bin", "HOME": str(home)})
    assert garde["decouverte"] == "reussie"
    assert garde["presente_dans_le_gestionnaire"] is True and garde["enregistree"] is True
    assert garde["alerte"] is None
    assert len(garde["outils_admis"]) == 34 and garde["outils_retires"] == ["kanban_attach_url", "kanban_create"]


def test_meta_reseau(tmp_path):
    https = {"pair": "100.64.0.3", "schema_vu": "https", "hote": "hermes.up.railway.app",
             "entetes_transmis": {"x-forwarded-for": True, "x-forwarded-proto": True, "inconnu": True},
             "x_forwarded_proto": "https" * 10}
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}), reseau=https)
    assert donnees["reseau"] == {
        "pair": "100.64.0.3", "schema_vu": "https", "hote": "hermes.up.railway.app",
        "entetes_transmis": {"x-forwarded-for": True, "x-forwarded-proto": True, "x-forwarded-host": False,
                             "x-real-ip": False, "x-railway-edge": False},
        "x_forwarded_proto": ("https" * 10)[:16]}
    assert not any("Secure" in a for a in donnees["alertes"])
    http = dict(https, schema_vu="http")
    alertes = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}), reseau=http)["alertes"]
    assert any("en « http » et non en https" in a and "Secure" in a for a in alertes)
    assert meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}))["reseau"] is None


def test_meta_reseau_par_la_route_sans_la_valeur_de_x_forwarded_for(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    module = _routeur("acp_poste_plugin_api_reseau", monkeypatch)
    application = FastAPI()
    application.include_router(module.router, prefix="/api/plugins/acp-poste")
    reponse = TestClient(application).get("/api/plugins/acp-poste/v1/meta", headers={
        "X-Forwarded-For": "203.0.113.77", "X-Forwarded-Proto": "https", "X-Railway-Edge": "railway/eu"})
    assert reponse.status_code == 200
    reseau = reponse.json()["reseau"]
    assert reseau["entetes_transmis"]["x-forwarded-for"] is True
    assert reseau["entetes_transmis"]["x-railway-edge"] is True
    assert reseau["x_forwarded_proto"] == "https"
    assert "203.0.113.77" not in reponse.text


def test_meta_lazy_packages(tmp_path):
    etat = {"soul": {"etat": "a_jour"}, "lazy_packages": {"entrees": ["edge_tts"]}}
    alertes = meta.construire_meta(_sources(tmp_path, etat))["alertes"]
    assert any("/opt/data/lazy-packages" in a and "edge_tts" in a for a in alertes)
    etat["lazy_packages"]["entrees"] = []
    assert not any("lazy-packages" in a for a in meta.construire_meta(_sources(tmp_path, etat))["alertes"])


def test_meta_commit_deploye(tmp_path):
    sha = "0123456789abcdef0123456789abcdef01234567"
    donnees = meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}, "deploiement": {"commit": sha}}))
    assert donnees["deploiement"] == {"commit": sha}
    # Hors Railway (ou état de schéma 1) : null, jamais une valeur inventée.
    assert meta.construire_meta(_sources(tmp_path, {"soul": {"etat": "a_jour"}}))["deploiement"] == {"commit": None}
    assert meta.construire_meta(_sources(tmp_path))["deploiement"] == {"commit": None}
