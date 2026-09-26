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
