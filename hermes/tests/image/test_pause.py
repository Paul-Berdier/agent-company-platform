"""Pause d'un projet et pause générale (cahier P4 § 12.2 ; décision D31)."""

from __future__ import annotations

import pytest

from conftest import carte, en_discussion, en_worker, lancer_sans_depot, lancer_sur_depot, outil, reclamer

PLAN = {"resume": "r", "etapes": [
    {"ref": "e1", "titre": "Écrire", "classe": "implementation", "consigne": "c", "voie": "poste-codex"},
    {"ref": "e2", "titre": "Veille", "classe": "recherche_web", "consigne": "c"}]}


def _tour(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    with noyau.ka.connexion(projet["tableau"]) as kc:
        run = noyau.ka.get_task(kc, projet["cartes"]["exploration"]).current_run_id
        noyau.ka.complete_task(kc, projet["cartes"]["exploration"], summary="ok", expected_run_id=run)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", PLAN)
    with noyau.ka.connexion(projet["tableau"]) as kc:  # kanban_complete du worker de planification
        noyau.ka.complete_task(kc, projet["cartes"]["planification"], summary="Plan posé.")
    par_role = {c["role"]: c["carte"] for c in tour["cartes"]}
    return projet, tour, par_role


def test_pause_projet_planifie_todo_et_ready_pas_running(noyau, conn, monkeypatch):
    projet, tour, par_role = _tour(noyau, conn, monkeypatch)
    reclamer(noyau, projet["tableau"], par_role["implementation"])  # running, sous le poste simulé
    resultat = noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    assert resultat["projet"]["etat"] == "en_pause"
    assert carte(noyau, projet["tableau"], par_role["implementation"]).status == "running"
    for identifiant in (par_role["relecture"], par_role["hermes"], tour["synthese"]):
        assert carte(noyau, projet["tableau"], identifiant).status == "scheduled", identifiant
    assert set(resultat["cartes_planifiees"]) == {par_role["relecture"], par_role["hermes"], tour["synthese"]}
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.mettre_en_pause(conn, projet["id"], auteur="p")
    assert exc.value.code == "deja_en_pause"


def test_reprise_ne_reveille_que_les_cartes_de_la_pause(noyau, conn, monkeypatch):
    projet, tour, par_role = _tour(noyau, conn, monkeypatch)
    run = reclamer(noyau, projet["tableau"], par_role["implementation"])
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=par_role["implementation"], run_id=run,
                              texte="Question ?")
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="p")
    resultat = noyau.projets.reprendre(conn, projet["id"], auteur="p")
    assert resultat["projet"]["etat"] == "actif"
    # La carte planifiée pour une question attend toujours sa réponse ; les autres reprennent.
    assert carte(noyau, projet["tableau"], par_role["implementation"]).status == "scheduled"
    assert carte(noyau, projet["tableau"], par_role["hermes"]).status == "ready"
    assert carte(noyau, projet["tableau"], par_role["relecture"]).status == "todo"
    assert carte(noyau, projet["tableau"], q["carte_repondre"]).status == "ready"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.reprendre(conn, projet["id"], auteur="p")
    assert exc.value.code == "pas_en_pause"


def test_enfant_d_une_carte_finie_pendant_la_pause_replanifie(noyau, conn, monkeypatch):
    """Une carte remise en ``ready`` pendant la pause (ici par un geste direct sur le tableau) repasse en
    ``scheduled`` à la passe suivante de l'émetteur ; règle idempotente."""
    projet, tour, par_role = _tour(noyau, conn, monkeypatch)
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="p")
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.unblock_task(kc, par_role["hermes"])
    assert carte(noyau, projet["tableau"], par_role["hermes"]).status == "ready"
    assert noyau.projets.replanifier_les_projets_en_pause(conn) == [par_role["hermes"]]
    assert carte(noyau, projet["tableau"], par_role["hermes"]).status == "scheduled"
    assert noyau.projets.replanifier_les_projets_en_pause(conn) == []


def test_planifier_pendant_la_pause_cree_puis_planifie(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="p")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", {"resume": "r", "etapes": [
        {"ref": "e1", "titre": "t", "classe": "recherche_web", "consigne": "c"}]})
    assert tour["ok"]
    for c in tour["cartes"]:
        assert carte(noyau, projet["tableau"], c["carte"]).status == "scheduled"


def test_pause_generale_estop_et_refus_des_outils(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    noyau.ka.engage("ACP : pause du propriétaire")
    try:
        assert noyau.projets.pause_generale()["reason"] == "ACP : pause du propriétaire"
        assert (noyau.home / "ESTOP").is_file()
        en_discussion(monkeypatch)
        assert outil(noyau, "projet_lancer", {"titre": "t", "objectif": "o"})["code"] == "pause_generale"
        assert outil(noyau, "routage_surcharger", {"portee": "projet", "cible": projet["id"], "classe": "recherche_web",
                                                   "voie": "hermes", "motif": "m"})["code"] == "pause_generale"
        # Les lectures restent possibles ; une carte déjà lancée finit son travail (pas de NOUVEAU travail :
        # le répartiteur ne lance rien tant que la pause dure).
        assert outil(noyau, "projet_etat", {})["pause_generale"] is True
        en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
        assert outil(noyau, "projet_planifier", {"resume": "r", "etapes": [
            {"ref": "e1", "titre": "t", "classe": "recherche_web", "consigne": "c"}]})["ok"]
    finally:
        noyau.ka.disengage()
    assert noyau.projets.pause_generale() is None


# ============================================================ corrections de la relecture de P4


def test_reprise_respecte_le_plafond_de_projets_actifs(noyau, conn):
    """Relecture de P4 (basse) : le plafond ``projets_actifs_max`` n'était vérifié qu'au lancement ; mettre A en
    pause, lancer B puis reprendre A faisait deux projets actifs pour un plafond de 1."""
    noyau.base.poser_reglage(conn, "projets_actifs_max", 1, "test")
    a = lancer_sans_depot(noyau, conn, titre="Projet A")
    noyau.projets.mettre_en_pause(conn, a["id"], auteur="proprietaire:test")
    lancer_sans_depot(noyau, conn, titre="Projet B")
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.reprendre(conn, a["id"], auteur="proprietaire:test")
    assert (exc.value.code, exc.value.message) == ("projets_actifs", (
        "Refusé par ACP : 1 projets sont déjà en cours (plafond 1) ; terminez-en un ou mettez-en un en pause avant "
        "de reprendre « Projet A »."))
    assert noyau.projets.projet(conn, a["id"])["etat"] == "en_pause"
    actifs = conn.execute("SELECT COUNT(*) FROM projets WHERE etat IN ('creation', 'actif')").fetchone()[0]
    assert actifs == 1


def test_reponse_pendant_la_pause_reprend_a_la_reprise_du_projet(noyau, conn, monkeypatch):
    """Relecture de P4 (produit) : sur un projet en pause, la réponse débloquait la carte (« prête ») que la passe
    suivante replanifiait, et la page annonçait « la carte reprend ». Désormais la réponse est enregistrée et
    commentée, la carte reste planifiée (reprise différée, dite) et reprend à la reprise du projet."""
    projet = lancer_sur_depot(noyau, conn, reponses="proprietaire")
    tableau, poste = projet["tableau"], projet["cartes"]["exploration"]
    run = reclamer(noyau, tableau, poste)
    q = noyau.questions.poser(conn, tableau=tableau, carte=poste, run_id=run, texte="Quelle version ?")
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    reponse = noyau.questions.repondre_par_proprietaire(conn, q["question"], reponse="3.12", auteur="proprietaire:t")
    assert reponse == {"question": q["question"], "etat": "repondue", "carte_debloquee": False,
                       "reprise_differee": True}
    assert carte(noyau, tableau, poste).status == "scheduled"
    noyau.projets.replanifier_les_projets_en_pause(conn)
    assert carte(noyau, tableau, poste).status == "scheduled"
    with noyau.ka.connexion(tableau) as kc:
        assert [c.body for c in noyau.ka.list_comments(kc, poste)] == ["3.12"]
    reprise = noyau.projets.reprendre(conn, projet["id"], auteur="proprietaire:test")
    assert poste in reprise["cartes_reveillees"] and carte(noyau, tableau, poste).status == "ready"


def test_decision_de_triage_refusee_sur_un_projet_en_pause(noyau, conn):
    """Une décision (« Prolonger », « Conclure ») sur un projet en pause ferait partir la carte avant la reprise :
    refusée, avec le moyen d'en sortir."""
    projet = lancer_sans_depot(noyau, conn, titre="Décision en pause")
    fiche = noyau.projets.projet(conn, projet["id"])
    triage = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "3 tours planifiés")
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    for decider in (lambda: noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=triage,
                                                             consigne=None, auteur="p"),
                    lambda: noyau.questions.conclure_triage(conn, tableau=projet["tableau"], carte=triage, auteur="p")):
        with pytest.raises(noyau.textes.RefusACP) as exc:
            decider()
        assert (exc.value.code, exc.value.message) == ("projet_en_pause", (
            "Refusé par ACP : le projet « Décision en pause » est en pause : reprenez-le avant de décider de cette "
            "carte."))
    assert carte(noyau, projet["tableau"], triage).status == "triage"
    assert noyau.projets.projet(conn, projet["id"])["plafond_tours"] == 3
