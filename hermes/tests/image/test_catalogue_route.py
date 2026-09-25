"""Étape P3 : ``GET /api/plugins/acp-poste/v1/catalogue`` et blocs ``catalogue`` et ``interface`` de
``/v1/meta`` (greffon acp-poste, catalogue.py), contre le code de Hermes à la version épinglée.

États calculés sur des volumes préparés comme 05-acp le fait (skills livrées synchronisées, réglages
appliqués), puis altérés : une skill désactivée par ACP réactivée par le propriétaire, le dossier du
catalogue retiré de skills.external_dirs, une skill locale homonyme d'une skill d'ACP, une skill
locale hors catalogue. La lecture se fait dans un PROCESSUS NEUF (HERMES_HOME jetable), comme le
tableau de bord qui sert la route.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import acp_demarrage as ad
from conftest import env_processus, executer_python, installer_home_de_test

GREFFON = Path("/opt/hermes/plugins/acp-poste")
VERROU = json.loads(Path("/opt/acp/catalogue/catalogue.lock.json").read_text(encoding="utf-8"))
NOMS_ACP = sorted(s["nom"] for s in VERROU["skills"] if s["cible"] == "hermes")
CATALOGUE = ad.charger_catalogue(ad.Chemins())

LIRE = """
import sys
sys.path.insert(0, "/opt/hermes/plugins/acp-poste")
import catalogue, meta
complet = catalogue.construire_catalogue()
resultat = {"catalogue": complet, "resume": catalogue.resume_pour_meta(complet), "interface": catalogue.bloc_interface(),
            "meta": meta.bloc_catalogue()}
"""


def _preparer(chemins, valeurs, config: str = "") -> None:
    installer_home_de_test(chemins, valeurs, config=config)
    executer_python("from tools.skills_sync import sync_skills; sync_skills(quiet=True); resultat = True",
                    env=env_processus(chemins))
    ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=10000, gid=10000)


def _lire(chemins) -> dict:
    return executer_python(LIRE, env=env_processus(chemins))


def test_catalogue_conforme(chemins, valeurs):
    _preparer(chemins, valeurs)
    lu = _lire(chemins)
    complet = lu["catalogue"]
    print(json.dumps({k: v for k, v in complet.items() if k not in ("skills", "profils", "exclus", "livrees")},
                     ensure_ascii=False, indent=1))
    etats = {s["nom"]: s["etat"] for s in complet["skills"]}
    assert all(etats[n] == "active" for n in NOMS_ACP), etats
    assert all(e == "reportee-p8" for n, e in etats.items() if n not in NOMS_ACP)
    assert complet["external_dirs_conforme"] is True and complet["desactivations_conformes"] is True
    assert complet["collisions"] == [] and complet["hors_catalogue"] == [] and complet["desactivations_non_appliquees"] == []
    assert complet["verrou"]["sha256"] == ad.empreinte(Path("/opt/acp/catalogue/catalogue.lock.json").read_bytes())
    assert set(complet["sources"]) == {"acp", "emilkowalski/skills", "leonxlnx/taste-skill", "affaan-m/ECC"}
    assert set(complet["profils"]) == {"base", "web", "recherche", "donnees"}
    [c7] = [m for m in complet["mcp"] if m["nom"] == "context7"]
    # Processus neuf, aucune découverte MCP : état « inconnu », jamais « connecté » inventé.
    assert c7["connexion"] == "inconnu" and c7["statut_hermes"] == "configured"
    assert complet["alertes"] == []
    assert lu["resume"] == {"verrou_sha256": complet["verrou"]["sha256"], "skills_actives": len(NOMS_ACP),
                            "skills_attendues": len(NOMS_ACP), "context7": "inconnu", "external_dirs_conforme": True,
                            "desactivations_conformes": True, "ecarts": 0}
    assert lu["interface"] == {"greffons": {"acp-interface": "0.11.0", "acp-catalogue": "0.11.0"}, "sdk_attendu": "1.x"}
    assert lu["meta"] == [lu["resume"], lu["interface"], []]


def test_context7_connecte_puis_hors_ligne(chemins, valeurs, faux_context7):
    _preparer(chemins, valeurs)
    code = "from tools.mcp_tool_discovery import discover_mcp_tools; discover_mcp_tools()\n" + LIRE
    lu = executer_python(code, env=env_processus(chemins))
    [c7] = [m for m in lu["catalogue"]["mcp"] if m["nom"] == "context7"]
    assert c7["connexion"] == "connecte" and c7["outils_exposes"] == 2
    assert lu["resume"]["context7"] == "connecte"
    faux_context7.arreter()
    lu = executer_python(code, env=env_processus(chemins))
    [c7] = [m for m in lu["catalogue"]["mcp"] if m["nom"] == "context7"]
    assert c7["connexion"] == "hors_ligne" and c7["statut_hermes"] == "failed"


def _reecrire_config(chemins, modification) -> None:
    fichier = chemins.config_volume
    donnees = ad.charger_yaml(fichier.read_text(encoding="utf-8"))
    modification(donnees)
    import yaml

    fichier.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")


def test_skill_reactivee_par_le_proprietaire(chemins, valeurs):
    _preparer(chemins, valeurs)
    _reecrire_config(chemins, lambda d: d["skills"]["disabled"].remove("codex"))
    complet = _lire(chemins)["catalogue"]
    assert complet["desactivations_non_appliquees"] == ["codex"]
    assert complet["desactivations_conformes"] is False
    assert any("codex" in a and "rétablies au prochain démarrage" in a for a in complet["alertes"])
    # Le démarrage suivant (05-acp) la désactive de nouveau.
    etat = ad.appliquer_reglages_skills(chemins, CATALOGUE, uid=10000, gid=10000)
    assert etat["etat"] == "applique" and etat["desactivations_ajoutees"] == ["codex"]


def test_external_dirs_retire(chemins, valeurs):
    _preparer(chemins, valeurs)
    _reecrire_config(chemins, lambda d: d["skills"].pop("external_dirs"))
    lu = _lire(chemins)
    complet = lu["catalogue"]
    assert complet["external_dirs_conforme"] is False
    assert {s["etat"] for s in complet["skills"] if s["cible"] == "hermes"} == {"absente"}
    assert any("skills.external_dirs ne contient pas /opt/acp/skills" in a for a in complet["alertes"])
    assert lu["resume"]["skills_actives"] == 0 and lu["resume"]["ecarts"] == len(NOMS_ACP) + 1


def test_collision_et_skill_hors_catalogue(chemins, valeurs):
    _preparer(chemins, valeurs)
    for nom in ("acp-redaction", "ma-skill"):
        dossier = chemins.hermes_home / "skills" / "locales" / nom
        dossier.mkdir(parents=True)
        (dossier / "SKILL.md").write_text(f"---\nname: {nom}\ndescription: x\n---\n# {nom}\n", encoding="utf-8")
    complet = _lire(chemins)["catalogue"]
    etats = {s["nom"]: s["etat"] for s in complet["skills"]}
    assert etats["acp-redaction"] == "ambigue"
    assert [c["nom"] for c in complet["collisions"]] == ["acp-redaction"]
    assert complet["hors_catalogue"] == ["ma-skill"]
    assert any("Skills en collision" in a and "acp-redaction" in a for a in complet["alertes"])


def test_serveur_mcp_hors_catalogue_signale(chemins, valeurs):
    _preparer(chemins, valeurs, config="mcp_servers:\n  deepwiki:\n    url: https://mcp.deepwiki.com/mcp\n")
    complet = _lire(chemins)["catalogue"]
    assert any("Serveur MCP hors catalogue configuré dans Hermes : deepwiki" in a for a in complet["alertes"])


def _charger_catalogue(nom: str):
    """catalogue.py chargé par son chemin, comme le fait plugin_api.py (module inscrit dans
    sys.modules avant son exécution : ses dataclasses l'exigent)."""
    import sys

    spec = importlib.util.spec_from_file_location(nom, GREFFON / "catalogue.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def test_verrou_illisible(tmp_path):
    module = _charger_catalogue("acp_catalogue_test")
    faux = tmp_path / "verrou.json"
    faux.write_text("{", encoding="utf-8")
    complet = module.construire_catalogue(module.SourcesCatalogue(verrou=faux), vue={}, mcp={})
    assert complet["verrou"]["sha256"] is None and complet["skills"] == []
    assert complet["alertes"] == [f"Verrou du catalogue illisible : {faux}. Le catalogue d'ACP est inconnu."]
    resume = module.resume_pour_meta(complet)
    assert resume["skills_actives"] is None and resume["skills_attendues"] is None and resume["context7"] == "inconnu"


def test_etat_du_chargeur_illisible_dit_inconnu():
    module = _charger_catalogue("acp_catalogue_test2")

    def panne():
        raise RuntimeError("panne")

    module.vue_du_chargeur = panne
    module.etat_mcp = panne
    complet = module.construire_catalogue()
    assert {s["etat"] for s in complet["skills"] if s["cible"] == "hermes"} == {"inconnu"}
    assert any("État du chargeur de skills de Hermes illisible (RuntimeError)" in a for a in complet["alertes"])
    assert all(m.get("connexion") == "inconnu" for m in complet["mcp"] if m["cible"] == "hermes")
    assert module.resume_pour_meta(complet)["skills_actives"] is None


def test_la_route_catalogue_est_montee(monkeypatch, chemins, valeurs):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("acp_poste_plugin_api_catalogue", GREFFON / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module._catalogue, "vue_du_chargeur", lambda: {
        "external_dirs": ["/opt/acp/skills"], "desactivees": [e["nom"] for e in VERROU["livrees"]["desactivees_par_acp"]],
        "emplacements": {s["nom"]: [f"/opt/acp/skills/{s['chemin']}"] for s in VERROU["skills"] if s["cible"] == "hermes"}})
    monkeypatch.setattr(module._catalogue, "etat_mcp", lambda: {"context7": {
        "connexion": "hors_ligne", "statut_hermes": "failed", "outils": 0, "url": "https://mcp.context7.com/mcp"}})
    application = FastAPI()
    application.include_router(module.router, prefix="/api/plugins/acp-poste")
    reponse = TestClient(application).get("/api/plugins/acp-poste/v1/catalogue")
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert {s["nom"]: s["etat"] for s in donnees["skills"] if s["cible"] == "hermes"} == {n: "active" for n in NOMS_ACP}
    assert [m["connexion"] for m in donnees["mcp"] if m["nom"] == "context7"] == ["hors_ligne"]
