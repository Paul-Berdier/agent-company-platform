"""Routes P4 du greffon (cahier P4 § 11) montées comme le fait le tableau de bord : session, anti-CSRF (JSON
exigé, Origin contrôlé), codes et refus en français. La porte d'authentification réelle de Hermes (401 sans
session) est prouvée au contrat, sur le vrai tableau de bord ; ici une session factice est posée par un
intergiciel de test."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import carte, lancer_sur_depot, releve_factice

GREFFON = Path("/opt/hermes/plugins/acp-poste")
P = "/api/plugins/acp-poste"
JSON = {"Content-Type": "application/json"}


@pytest.fixture
def client(noyau, monkeypatch):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("acp_poste_plugin_api_p4", GREFFON / "dashboard" / "plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    application = FastAPI()

    @application.middleware("http")
    async def session_factice(request: Request, suivant):
        if request.headers.get("x-test-sans-session") is None:
            request.state.session = SimpleNamespace(user_id="proprietaire-test")
        return await suivant(request)

    application.include_router(module.router, prefix=P)
    return TestClient(application)


def _lancer(client, **corps):
    return client.post(f"{P}/v1/projets", json=dict({"titre": "Veille", "objectif": "Recenser."}, **corps))


def test_liste_vide_et_etats_inconnus(client):
    reponse = client.get(f"{P}/v1/projets")
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["projets"] == [] and donnees["pause_generale"] is None and donnees["questions_ouvertes"] == 0
    assert donnees["poste"]["etat"] == "non_configure"
    assert donnees["notifications"] == {"canal": None, "configure": False, "connu": False,
                                        "message": "Notifications non configurées."}


def test_ecriture_sans_session_json_ou_origine(client):
    reponse = client.post(f"{P}/v1/projets", json={"titre": "t", "objectif": "o"}, headers={"x-test-sans-session": "1"})
    assert reponse.status_code == 401 and reponse.json()["detail"]["message"] == "Session du tableau de bord requise."
    reponse = client.post(f"{P}/v1/projets", content="titre=t", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert reponse.status_code == 415 and reponse.json()["detail"] == {"code": "json", "message": "Requête refusée : "
                                                                                                 "corps JSON attendu."}
    reponse = client.post(f"{P}/v1/projets", json={"titre": "t", "objectif": "o"},
                          headers={"Origin": "https://intrus.example"})
    assert reponse.status_code == 403 and reponse.json()["detail"]["message"] == (
        "Requête refusée : origine « https://intrus.example » non autorisée.")
    reponse = client.post(f"{P}/v1/projets", content="[1]", headers=JSON)
    assert reponse.status_code == 400
    # L'origine publique est admise.
    reponse = client.post(f"{P}/v1/projets", json={"titre": "t", "objectif": "o"},
                          headers={"Origin": "https://hermes.acp.test"})
    assert reponse.status_code == 201
    for chemin in ("/v1/projets/p_x/pause", "/v1/projets/p_x/reprise", "/v1/questions/q_x/reponse",
                   "/v1/triage/acp-x/t_x/reprendre", "/v1/pause", "/v1/notifications/test"):
        assert client.post(f"{P}{chemin}", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post(f"{P}{chemin}", json={}, headers={"Origin": "https://intrus.example"}).status_code == 403


def test_lancement_201_idempotent_et_refus(client, noyau):
    premier = client.post(f"{P}/v1/projets", json={"titre": "Idem", "objectif": "o"}, headers={"Idempotency-Key": "k1"})
    second = client.post(f"{P}/v1/projets", json={"titre": "Idem", "objectif": "o"}, headers={"Idempotency-Key": "k1"})
    assert (premier.status_code, second.status_code) == (201, 200)
    assert premier.json()["projet"]["id"] == second.json()["projet"]["id"] and second.json()["deja_lance"] is True
    with noyau.base.connexion() as conn:
        fiche = noyau.projets.projet(conn, premier.json()["projet"]["id"])
    assert (fiche["origine"], fiche["auteur"]) == ("tableau_de_bord", "proprietaire:proprietaire-test")
    reponse = _lancer(client, depot="jetable")
    assert reponse.status_code == 400 and reponse.json()["detail"]["code"] == "aucun_inventaire"
    assert _lancer(client, intrus=1).status_code == 400
    with noyau.base.connexion() as conn:
        noyau.base.poser_reglage(conn, "projets_actifs_max", 1, "test")
    reponse = _lancer(client)
    assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "projets_actifs"


def test_detail_pause_reprise(client):
    projet = _lancer(client).json()["projet"]
    detail = client.get(f"{P}/v1/projets/{projet['id']}")
    assert detail.status_code == 200
    corps = detail.json()["projet"]
    assert corps["etat_derive"] == "planification" and corps["journal"][0]["action"] == "lancement"
    assert corps["cartes"][0]["modele_servi"] == "Non observé"
    assert client.get(f"{P}/v1/projets/{projet['tableau']}").json()["projet"]["id"] == projet["id"]
    inconnu = client.get(f"{P}/v1/projets/p_inconnu")
    assert inconnu.status_code == 404 and inconnu.json()["detail"]["message"] == "Refusé par ACP : projet « p_inconnu » inconnu."
    assert client.post(f"{P}/v1/projets/{projet['id']}/pause", json={}).json()["projet"]["etat"] == "en_pause"
    assert client.post(f"{P}/v1/projets/{projet['id']}/pause", json={}).status_code == 409
    assert client.post(f"{P}/v1/projets/{projet['id']}/reprise", json={}).json()["projet"]["etat"] == "actif"
    assert client.post(f"{P}/v1/projets/{projet['id']}/reprise", json={}).status_code == 409


def test_questions_triage_et_poste(client, noyau):
    assert client.get(f"{P}/v1/questions").json() == {"questions": [], "triage": [], "bloquees": [],
                                                       "tableaux_illisibles": []}
    reponse = client.post(f"{P}/v1/questions/q_inconnue/reponse", json={"reponse": "oui"})
    assert reponse.status_code == 404
    projet = _lancer(client).json()["projet"]
    reponse = client.post(f"{P}/v1/triage/{projet['tableau']}/t_inconnue/reprendre", json={})
    assert reponse.status_code == 404 and reponse.json()["detail"]["code"] == "triage_inconnu"
    poste = client.get(f"{P}/v1/poste").json()
    assert poste["poste"]["etat"] == "non_configure" and poste["catalogue"]["etat"] == "inconnu"
    with noyau.base.connexion() as conn:
        noyau.routage.enregistrer_releve(conn, releve_factice("poste-codex"))
    assert client.get(f"{P}/v1/poste").json()["catalogue"]["releve_factice"] is True


def test_reprise_d_un_triage_par_la_route(client, noyau):
    """Bouton « Reprendre » de la page Projets (seconde partie de P4) : 200, la carte quitte le triage avec la
    consigne du propriétaire ; rejouée, la route répond 404 (plus de carte en triage)."""
    with noyau.base.connexion() as conn:
        projet = lancer_sur_depot(noyau, conn)
        fiche = noyau.projets.projet(conn, projet["id"])
        triage = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "3 tours planifiés")
    chemin = f"{P}/v1/triage/{projet['tableau']}/{triage}/reprendre"
    reponse = client.post(chemin, json={"consigne": "Conclure avec ce qui est fait."})
    assert reponse.status_code == 200 and reponse.json() == {"carte": triage, "reprise": True}
    tache = carte(noyau, projet["tableau"], triage)
    assert tache.status in ("todo", "ready") and "Conclure avec ce qui est fait." in tache.body
    assert client.get(f"{P}/v1/questions").json()["triage"] == []
    rejouee = client.post(chemin, json={})
    assert rejouee.status_code == 404 and rejouee.json()["detail"]["code"] == "triage_inconnu"


def test_pause_generale(client, noyau):
    try:
        reponse = client.post(f"{P}/v1/pause", json={"generale": True, "raison": "vacances"})
        assert reponse.status_code == 200
        assert reponse.json()["pause_generale"]["reason"] == "ACP : pause du propriétaire — vacances"
        assert client.get(f"{P}/v1/projets").json()["pause_generale"] is not None
        assert _lancer(client).status_code == 409
        with noyau.base.connexion() as conn:
            assert noyau.base.reglage(conn, "pause_reclamations") == 1
        assert client.post(f"{P}/v1/pause", json={"generale": "oui"}).status_code == 400
    finally:
        assert client.post(f"{P}/v1/pause", json={"generale": False}).json()["pause_generale"] is None
    with noyau.base.connexion() as conn:
        assert noyau.base.reglage(conn, "pause_reclamations") == 0


def test_notification_de_test(client, noyau):
    reponse = client.post(f"{P}/v1/notifications/test", json={})
    assert reponse.status_code == 409 and reponse.json()["detail"]["message"] == "Notifications non configurées."
    with noyau.base.connexion() as conn:
        with noyau.base.transaction(conn):
            noyau.base.ecrire_emetteur(conn, "canal", {"canal": "ntfy", "configure": True, "serveur": "https://x.test"})
    reponse = client.post(f"{P}/v1/notifications/test", json={})
    assert reponse.status_code == 202 and reponse.json()["etat"] == "en_attente"
    with noyau.base.connexion() as conn:
        assert [tuple(l) for l in conn.execute("SELECT genre, etat FROM notifications")] == [("test", "en_attente")]
