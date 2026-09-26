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
    # Tant que la passerelle n'a pas publié l'état du canal, il est INCONNU, et le message le dit (relecture de P4).
    assert donnees["notifications"] == {"canal": None, "configure": False, "connu": False,
                                        "message": "État du canal de notification inconnu : la passerelle ne l'a "
                                                   "pas encore publié."}


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
    assert reponse.status_code == 200 and reponse.json() == {"carte": triage, "reprise": True, "action": "prolongation",
                                                             "plafond": {"genre": "tours", "avant": 3, "apres": 4}}
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
    assert reponse.status_code == 409 and reponse.json()["detail"]["message"] == (
        "État du canal de notification inconnu : la passerelle ne l'a pas encore publié.")
    with noyau.base.connexion() as conn:
        with noyau.base.transaction(conn):
            noyau.base.ecrire_emetteur(conn, "canal", {"canal": "aucune", "configure": False, "serveur": None})
    reponse = client.post(f"{P}/v1/notifications/test", json={})
    assert reponse.status_code == 409 and reponse.json()["detail"]["message"] == "Notifications non configurées."
    with noyau.base.connexion() as conn:
        with noyau.base.transaction(conn):
            noyau.base.ecrire_emetteur(conn, "canal", {"canal": "ntfy", "configure": True, "serveur": "https://x.test"})
    reponse = client.post(f"{P}/v1/notifications/test", json={})
    assert reponse.status_code == 202 and reponse.json()["etat"] == "en_attente"
    with noyau.base.connexion() as conn:
        assert [tuple(l) for l in conn.execute("SELECT genre, etat FROM notifications")] == [("test", "en_attente")]


# ============================================================ corrections de la relecture de P4


def test_reprise_generale_refusee_tant_que_des_crochets_existent(client, noyau):
    """Relecture de P4 (basse) : la veille des crochets shell (D34) engage l'arrêt d'urgence ; POST /v1/pause
    {"generale": false} le levait sans vérifier que les crochets avaient disparu, et le premier tour du
    répartiteur pouvait lancer des workers avec --accept-hooks. Refus 409 tant qu'ils existent."""
    (noyau.home / "config.yaml").write_text("hooks:\n  pre_tool_call:\n    - command: 'true'\n", encoding="utf-8")
    try:
        with noyau.base.connexion() as conn:
            assert noyau.emetteur.veiller_crochets(conn)
        assert noyau.projets.pause_generale()["reason"] == "ACP : crochets shell détectés en cours de route"
        reponse = client.post(f"{P}/v1/pause", json={"generale": False})
        assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "crochets"
        assert reponse.json()["detail"]["message"].startswith(
            "Refusé par ACP : des crochets shell sont toujours déclarés (")
        assert noyau.projets.pause_generale() is not None
        # Crochets retirés : la reprise passe.
        (noyau.home / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        reponse = client.post(f"{P}/v1/pause", json={"generale": False})
        assert reponse.status_code == 200 and reponse.json()["pause_generale"] is None
    finally:
        noyau.ka.disengage()


def test_resume_coupe_le_dit_et_se_lit_en_entier(client, noyau):
    """Relecture de P4 (haute) : le détail coupait chaque résumé à 500 caractères et la liste la dernière note à
    200, au milieu d'un mot, sans le dire, sans moyen de lire le reste. Pour un projet sans dépôt, ce texte
    EST le livrable. Désormais : longueur et « tronqué » rendus, résumé entier par une route, et le résultat du
    projet (synthèse faite du dernier tour) en entier dans le détail."""
    from conftest import lancer_sans_depot, reclamer, terminer

    rapport = "".join(f"Paragraphe {i} du rapport de recherche, avec ses sources. " for i in range(60))
    with noyau.base.connexion() as conn:
        projet = lancer_sans_depot(noyau, conn, titre="Rapport long")
    tableau, planif = projet["tableau"], projet["cartes"]["planification"]
    reclamer(noyau, tableau, planif)
    assert terminer(noyau, tableau, planif, resume=rapport)
    detail = client.get(f"{P}/v1/projets/{projet['id']}").json()["projet"]
    [carte_planif] = [c for c in detail["cartes"] if c["carte"] == planif]
    assert len(carte_planif["resume"]) == 500 and carte_planif["resume"] == rapport[:500]
    assert (carte_planif["resume_tronque"], carte_planif["resume_longueur"]) == (True, len(rapport))
    liste = client.get(f"{P}/v1/projets").json()["projets"][0]
    assert liste["derniere_note"] == rapport[:200] and liste["derniere_note_tronquee"] is True
    lue = client.get(f"{P}/v1/projets/{projet['id']}/cartes/{planif}")
    assert lue.status_code == 200 and lue.json()["carte"] == {
        "carte": planif, "titre": "Planification — Rapport long", "role": "planification", "statut": "done",
        "resume": rapport, "longueur": len(rapport), "tronque": False}
    inconnue = client.get(f"{P}/v1/projets/{projet['id']}/cartes/t_inconnue")
    assert inconnue.status_code == 404 and inconnue.json()["detail"]["code"] == "carte_inconnue"
    assert detail["resultat"] is None  # aucune synthèse faite : pas de résultat du projet, rien d'inventé


def test_resultat_du_projet_en_entier(client, noyau, monkeypatch):
    """Le détail rend la synthèse FAITE du dernier tour en entier (« Résultat du projet »), pas 500 caractères."""
    from conftest import en_worker, lancer_sans_depot, outil, terminer

    with noyau.base.connexion() as conn:
        projet = lancer_sans_depot(noyau, conn, titre="Résultat entier")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", {"resume": "Une recherche.", "etapes": [
        {"ref": "e1", "titre": "Chercher", "classe": "recherche_web", "consigne": "Chercher."}]})
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")
    terminer(noyau, projet["tableau"], tour["cartes"][0]["carte"], "Recherche faite.")
    conclusion = ("Conclusion. " + "Détail vérifié. " * 300).rstrip()
    terminer(noyau, projet["tableau"], tour["synthese"], conclusion)
    resultat = client.get(f"{P}/v1/projets/{projet['id']}").json()["projet"]["resultat"]
    assert resultat == {"tour": 1, "carte": tour["synthese"], "texte": conclusion, "longueur": len(conclusion),
                        "tronque": False}
    assert len(conclusion) > 4000


def test_conclure_par_la_route(client, noyau, monkeypatch):
    """Bouton « Conclure » d'une carte de décision (décision D41) : 200 ; une carte qui n'est pas une décision du
    greffon est refusée (409), une carte inconnue aussi (404)."""
    from conftest import lancer_sans_depot, reclamer, terminer

    with noyau.base.connexion() as conn:
        projet = lancer_sans_depot(noyau, conn, titre="Conclure route")
    reclamer(noyau, projet["tableau"], projet["cartes"]["planification"])
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Rien.")
    with noyau.base.connexion() as conn:
        noyau.emetteur.passe(conn)
    [triage] = client.get(f"{P}/v1/questions").json()["triage"]
    assert triage["actions"] == ["relancer", "conclure"] and triage["raison"]
    chemin = f"{P}/v1/triage/{projet['tableau']}/{triage['carte']}/conclure"
    assert client.post(chemin, content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    reponse = client.post(chemin, json={})
    assert reponse.status_code == 200 and reponse.json()["projet"]["etat"] == "abandonne"
    assert client.post(chemin, json={}).status_code == 404
