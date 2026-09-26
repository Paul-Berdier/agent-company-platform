"""Lancement d'un projet (cahier P4 § 6.1 et § 8.1) : tableau, cartes, idempotence, chaque refus, réparation."""

from __future__ import annotations

import pytest

import time

from conftest import (carte, cartes_du_tableau, en_discussion, en_worker, lancer_sans_depot, lancer_sur_depot, outil,
                      releve_factice)


def test_sans_depot_cree_tableau_et_planification_ready(noyau, conn):
    projet = lancer_sans_depot(noyau, conn)
    assert projet["etat"] == "actif" and projet["tableau"].startswith("acp-veille-llm-")
    assert projet["cartes"]["exploration"] is None
    tableaux = {b["slug"]: b for b in noyau.ka.list_boards()}
    assert projet["tableau"] in tableaux
    assert "n'en créez pas à la main" in tableaux[projet["tableau"]]["description"]
    planif = carte(noyau, projet["tableau"], projet["cartes"]["planification"])
    assert planif.status == "ready" and planif.assignee == "default" and planif.created_by == "acp-poste"
    assert planif.skills == ["acp-orchestration", "acp-routage", "acp-exploration"]
    assert planif.priority == 10 and planif.max_runtime_seconds == 1800
    assert planif.model_override is None and planif.provider_override is None
    assert planif.idempotency_key == f"acp:{projet['id']}:t0:planification"
    demande = noyau.projets.demande_de_la_carte(conn, projet["tableau"], planif.id)
    assert demande["role"] == "planification" and demande["voie"] == "hermes" and demande["source_routage"] == "profil"
    fiche = noyau.projets.projet(conn, projet["id"])
    assert (fiche["plafond_tours"], fiche["plafond_cartes"], fiche["plafond_corrections"]) == (3, 30, 2)
    assert fiche["cartes_creees"] == 1 and fiche["origine"] == "tableau_de_bord"
    curseur = conn.execute("SELECT evenement FROM curseurs WHERE tableau = ?", (projet["tableau"],)).fetchone()[0]
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert curseur == noyau.ka.dernier_evenement(kc) > 0


def test_avec_depot_cree_exploration_puis_planification_todo(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    toutes = cartes_du_tableau(noyau, projet["tableau"])
    exploration = toutes[projet["cartes"]["exploration"]]
    planif = toutes[projet["cartes"]["planification"]]
    assert exploration.assignee == "poste-claude" and exploration.status == "ready"
    assert exploration.model_override == "factice-claude-1" and exploration.reasoning_effort == "low"
    assert exploration.max_runtime_seconds is None  # le poste impose le sien (P6)
    assert "LECTURE SEULE" in exploration.body and "## Risques" in exploration.body
    assert planif.status == "todo"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.parent_ids(kc, planif.id) == [exploration.id]
    demande = noyau.projets.demande_de_la_carte(conn, projet["tableau"], exploration.id)
    assert demande["source_routage"] == "choix_explicite" and demande["mention"] == "quota inconnu"


def test_idempotence_meme_cle(noyau, conn):
    premier = noyau.projets.lancer(conn, titre="Idem", objectif="x", origine="tableau_de_bord", auteur="p",
                                   cle_idempotence="tableau_de_bord:cle-1")
    second = noyau.projets.lancer(conn, titre="Idem", objectif="x", origine="tableau_de_bord", auteur="p",
                                  cle_idempotence="tableau_de_bord:cle-1")
    assert premier["deja_lance"] is False and second["deja_lance"] is True
    assert premier["projet"]["id"] == second["projet"]["id"]
    assert conn.execute("SELECT COUNT(*) FROM projets").fetchone()[0] == 1


def test_idempotence_depuis_la_discussion(noyau, monkeypatch):
    en_discussion(monkeypatch)
    args = {"titre": "Depuis la discussion", "objectif": "Tester.", "profil": "recherche", "depot": None}
    premier = outil(noyau, "projet_lancer", args, "s-1")
    second = outil(noyau, "projet_lancer", args, "s-1")
    autre_session = outil(noyau, "projet_lancer", args, "s-2")
    assert premier["ok"] and second["deja_lance"] and second["projet"]["id"] == premier["projet"]["id"]
    assert autre_session["projet"]["id"] != premier["projet"]["id"]
    with noyau.base.connexion() as conn:
        fiche = noyau.projets.projet(conn, premier["projet"]["id"])
    assert fiche["origine"] == "discussion" and fiche["auteur"] == "discussion:s-1"


def _refus(noyau, conn, **options):
    valeurs = dict(titre="Refus", objectif="Objectif.", origine="tableau_de_bord", auteur="p")
    valeurs.update(options)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.lancer(conn, **valeurs)
    assert conn.execute("SELECT COUNT(*) FROM projets WHERE titre = ?", (valeurs["titre"],)).fetchone()[0] == 0
    return exc.value


def test_refus_contexte(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    reponse = outil(noyau, "projet_lancer", {"titre": "x", "objectif": "y"})
    assert reponse == {"ok": False, "code": "contexte", "message": "Refusé par ACP : projet_lancer ne s'appelle que "
                                                                   "depuis la discussion, jamais depuis une carte."}


def test_refus_pause_generale(noyau, conn):
    noyau.ka.engage("ACP : essai")
    try:
        exc = _refus(noyau, conn)
    finally:
        noyau.ka.disengage()
    assert exc.code == "pause_generale" and exc.message == (
        "Refusé par ACP : Hermes est en pause générale ; reprenez-la depuis la page Projets avant de lancer un projet.")


@pytest.mark.parametrize("options, code, message", [
    ({"titre": ""}, "titre", "Refusé par ACP : le titre doit compter de 1 à 120 caractères."),
    ({"titre": "x" * 121}, "titre", "Refusé par ACP : le titre doit compter de 1 à 120 caractères."),
    ({"objectif": " "}, "objectif", "Refusé par ACP : l'objectif doit compter de 1 à 4000 caractères."),
    ({"profil": "jeux"}, "profil", "Refusé par ACP : type de projet « jeux » inconnu (base, web, recherche ou donnees)."),
    ({"depot": "jetable"}, "aucun_inventaire",
     "Refusé par ACP : aucun dépôt autorisé n'est connu : le poste n'a encore publié aucun inventaire (étape P5). "
     "Lancez le projet sans dépôt, ou connectez le poste."),
    # Faux secret assemblé à l'exécution : le balayage des secrets du dépôt ne doit rien trouver ici.
    ({"objectif": "clé " + "sk-" + "proj-" + "ABCDEFGHIJKLMNOPQRSTUVWX"}, "secret",
     "Refusé par ACP : l'objectif contient ce qui ressemble à un secret (clé d'API OpenAI) ; retirez-le."),
])
def test_refus_simples(noyau, conn, options, code, message):
    exc = _refus(noyau, conn, **options)
    assert (exc.code, exc.message) == (code, message)


def test_refus_depot_inconnu(noyau, conn):
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-claude", depots=("jetable", "autre")))
    exc = _refus(noyau, conn, depot="secret-du-voisin")
    assert exc.code == "depot_inconnu" and exc.message == (
        "Refusé par ACP : le dépôt « secret-du-voisin » ne figure pas parmi les dépôts autorisés du poste "
        "(autre, jetable).")


def test_refus_exploration(noyau, conn):
    noyau.routage.enregistrer_releve(conn, releve_factice("poste-claude"))
    exc = _refus(noyau, conn, depot="jetable")
    assert exc.code == "exploration" and exc.message == (
        "Refusé par ACP : aucun exécutant disponible pour l'exploration : Aucun modèle disponible pour la classe "
        "« exploration » : table de routage non validée et aucun choix explicite.")
    exc = _refus(noyau, conn, depot="jetable", exploration={"voie": "poste-codex"})
    assert exc.code == "exploration" and "catalogue du poste inconnu (aucun relevé)" in exc.message
    exc = _refus(noyau, conn, exploration={"voie": "poste-claude"})
    assert exc.code == "exploration" and "ce projet n'en a pas" in exc.message


def test_refus_projets_actifs(noyau, conn):
    noyau.base.poser_reglage(conn, "projets_actifs_max", 1, "test")
    lancer_sans_depot(noyau, conn, "Premier")
    exc = _refus(noyau, conn)
    assert exc.code == "projets_actifs" and exc.message == (
        "Refusé par ACP : 1 projets sont déjà en cours (plafond 1) ; terminez-en un ou mettez-le en pause.")
    # Un projet en pause ne compte plus.
    premier = conn.execute("SELECT id FROM projets").fetchone()[0]
    noyau.projets.mettre_en_pause(conn, premier, auteur="test")
    assert lancer_sans_depot(noyau, conn, "Deuxième")["etat"] == "actif"


def test_refus_lancements_jour(noyau, conn):
    noyau.base.poser_reglage(conn, "lancements_discussion_par_jour", 1, "test")
    noyau.projets.lancer(conn, titre="Un", objectif="x", origine="discussion", auteur="discussion:s")
    exc = _refus(noyau, conn, origine="discussion", auteur="discussion:s")
    assert exc.code == "lancements_jour" and exc.message == (
        "Refusé par ACP : 1 projets ont déjà été lancés depuis la discussion aujourd'hui (plafond) ; lancez celui-ci "
        "depuis la page Projets.")
    # La page Projets reste possible.
    assert noyau.projets.lancer(conn, titre="Page", objectif="x", origine="tableau_de_bord", auteur="p")["projet"]


def test_reparation_d_une_creation_interrompue(noyau, conn, monkeypatch):
    """Coupure entre la réservation et la création kanban : la passe de l'émetteur répare après 60 s."""
    vraie = noyau.cartes.creer
    monkeypatch.setattr(noyau.cartes, "creer", lambda *a, **k: (_ for _ in ()).throw(OSError("coupure")))
    with pytest.raises(OSError):
        lancer_sans_depot(noyau, conn, "Interrompu")
    monkeypatch.setattr(noyau.cartes, "creer", vraie)
    fiche = conn.execute("SELECT * FROM projets WHERE titre = 'Interrompu'").fetchone()
    assert fiche["etat"] == "creation"
    assert conn.execute("SELECT COUNT(*) FROM demandes WHERE carte IS NULL").fetchone()[0] == 1
    assert noyau.cartes.reparer(conn) == []  # moins de 60 s : rien
    noyau.base.fixer_horloge(lambda: time.time() + 61)
    assert noyau.cartes.reparer(conn) == [fiche["id"]]
    assert noyau.projets.projet(conn, fiche["id"])["etat"] == "actif"
    demande = conn.execute("SELECT * FROM demandes WHERE projet_id = ?", (fiche["id"],)).fetchone()
    assert demande["carte"] and carte(noyau, fiche["tableau"], demande["carte"]).status == "ready"
    # Rejouée, la réparation ne crée rien de plus (clé d'idempotence).
    assert noyau.cartes.reparer(conn) == [] and len(cartes_du_tableau(noyau, fiche["tableau"])) == 1
