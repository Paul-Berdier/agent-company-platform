"""Routes de l'étape P7 (cahier P7 § 3.3, § 3.4, § 4.2, § 8.2, § 10 ; correction K19) montées comme le fait le tableau
de bord : session, anti-CSRF (JSON exigé, Origin contrôlé), champs inconnus refusés, et chaque code de refus avec SON
statut HTTP (jamais le 400 par défaut). La porte d'authentification réelle (401 sans session) est prouvée au contrat."""

from __future__ import annotations

from conftest import lancer_sans_depot, lancer_sur_depot
from test_routes_projets import JSON, P, client  # noqa: F401 — fixture des routes (session factice)

ECRITURES = ("/v1/cartes/acp-x/t_x/relancer", "/v1/projets/p_x/reponses", "/v1/projets/p_x/clore")


def test_gardes_d_ecriture(client):  # noqa: F811
    for chemin in ECRITURES:
        assert client.post(f"{P}{chemin}", json={}, headers={"x-test-sans-session": "1"}).status_code == 401
        assert client.post(f"{P}{chemin}", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post(f"{P}{chemin}", json={}, headers={"Origin": "https://intrus.example"}).status_code == 403
        reponse = client.post(f"{P}{chemin}", json={"intrus": 1})
        assert reponse.status_code == 400 and "champ inconnu refusé : intrus" in reponse.json()["detail"]["message"]


def test_relancer_codes_et_reponse(client, noyau):  # noqa: F811
    with noyau.base.connexion() as conn:
        projet = lancer_sans_depot(noyau, conn)
    planif = projet["cartes"]["planification"]
    chemin = f"{P}/v1/cartes/{projet['tableau']}/{planif}/relancer"
    reponse = client.post(chemin, json={})
    assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "carte_non_arretee"
    inconnu = client.post(f"{P}/v1/cartes/acp-inconnu-0000/t_0000/relancer", json={})
    assert inconnu.status_code == 404 and inconnu.json()["detail"]["code"] == "projet_inconnu"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        etrangere = noyau.ka.create_task(kc, title="À la main", body="x", assignee="default", created_by="proprietaire",
                                         board=projet["tableau"])
        assert noyau.ka.block_task(kc, etrangere, kind="capability", reason="à la main")
        assert noyau.ka.block_task(kc, planif, kind="needs_input", reason="Il manque la liste des sources.")
    reponse = client.post(f"{P}/v1/cartes/{projet['tableau']}/{etrangere}/relancer", json={})
    assert reponse.status_code == 403 and reponse.json()["detail"]["code"] == "carte_non_acp"
    reponse = client.post(chemin, json={"consigne": "Sources officielles seulement."})
    assert reponse.status_code == 200 and reponse.json() == {"carte": planif, "relancee": True, "statut_apres": "ready",
                                                             "session_neuve": False, "branche_neuve": False}
    with noyau.base.connexion() as conn:
        auteur = conn.execute("SELECT acteur FROM journal WHERE action = 'relance'").fetchone()[0]
    assert auteur == "proprietaire:proprietaire-test"
    # Projet en pause : 409, pas 400 (correction K19).
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.block_task(kc, planif, kind="capability", reason="encore")
    assert client.post(f"{P}/v1/projets/{projet['id']}/pause", json={}).status_code == 200
    reponse = client.post(chemin, json={})
    assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "projet_en_pause"


def test_reponses_codes(client, noyau):  # noqa: F811
    with noyau.base.connexion() as conn:
        sans_depot = lancer_sans_depot(noyau, conn)
        sur_depot = lancer_sur_depot(noyau, conn)
    reponse = client.post(f"{P}/v1/projets/{sur_depot['id']}/reponses", json={"reponses": "proprietaire"})
    assert reponse.status_code == 200 and reponse.json()["apres"] == "proprietaire"
    assert client.get(f"{P}/v1/projets/{sur_depot['id']}").json()["projet"]["reponses"] == "proprietaire"
    reponse = client.post(f"{P}/v1/projets/{sans_depot['id']}/reponses", json={"reponses": "proprietaire"})
    assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "reponses_sans_objet"
    reponse = client.post(f"{P}/v1/projets/{sur_depot['id']}/reponses", json={"reponses": "personne"})
    assert reponse.status_code == 400 and reponse.json()["detail"]["code"] == "reponses"
    assert client.post(f"{P}/v1/projets/p_inconnu/reponses", json={"reponses": "proprietaire"}).status_code == 404


def test_clore_codes(client, noyau):  # noqa: F811
    with noyau.base.connexion() as conn:
        projet = lancer_sur_depot(noyau, conn)
    chemin = f"{P}/v1/projets/{projet['id']}/clore"
    for corps in ({}, {"confirmation": False}, {"confirmation": "true"}):
        reponse = client.post(chemin, json=corps)
        assert reponse.status_code == 422 and reponse.json()["detail"]["code"] == "confirmation"
    reponse = client.post(chemin, json={"confirmation": True})
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert (corps["clos"], corps["etat"], corps["projet"]["etat"]) == (True, "abandonne", "abandonne")
    reponse = client.post(chemin, json={"confirmation": True})
    assert reponse.status_code == 409 and reponse.json()["detail"]["code"] == "projet_fini"
    assert client.post(f"{P}/v1/projets/p_inconnu/clore", json={"confirmation": True}).status_code == 404


def test_accueil_en_lecture(client):  # noqa: F811
    reponse = client.get(f"{P}/v1/accueil")
    assert reponse.status_code == 200 and reponse.json()["illisibles"] == {}
    assert client.post(f"{P}/v1/accueil", content="{}", headers=JSON).status_code == 405
