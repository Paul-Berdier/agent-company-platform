"""« Clore le projet » (étape P7, cahier P7 § 10, décision P7-9 ; correction K11) : cartes ouvertes archivées (dont une
carte de l'exécutant réclamée, qui perd sa réclamation), questions annulées, attentes supprimées, ``termine`` seulement
si la synthèse du tour est faite (sinon ``abandonne``), mise à jour d'état conditionnelle face à la passe de
l'émetteur, aucune notification, refus."""

from __future__ import annotations

import json

import pytest

from conftest import cartes_du_tableau, lancer_sans_depot, lancer_sur_depot, reclamer, terminer
from test_emetteur import PLAN, _projet_planifie


def _clore(noyau, conn, projet, confirmation=True):
    return noyau.projets.clore(conn, projet["id"], confirmation=confirmation, auteur="proprietaire:test")


def test_clore_en_pleine_execution_abandonne(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    tableau, exploration = projet["tableau"], projet["cartes"]["exploration"]
    run = reclamer(noyau, tableau, exploration)  # réclamée par l'exécutant (simulé), en cours
    q = noyau.questions.poser(conn, tableau=tableau, carte=exploration, run_id=run, texte="Faut-il tout réécrire ?")
    with noyau.base.transaction(conn):
        conn.execute("INSERT INTO attentes (tableau, carte, motif, reprise_le, cree_le) VALUES (?, ?, 'quota', 1, 1)",
                     (tableau, exploration))
    ouvertes = {i for i, t in cartes_du_tableau(noyau, tableau).items() if t.status not in ("done", "archived")}
    assert {exploration, projet["cartes"]["planification"], q["carte_repondre"]} <= ouvertes
    notifs_avant = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    resultat = _clore(noyau, conn, projet)
    assert (resultat["clos"], resultat["etat"], resultat["projet"]["etat"]) == (True, "abandonne", "abandonne")
    assert set(resultat["cartes_archivees"]) == ouvertes and resultat["cartes_non_archivees"] == []
    assert resultat["questions_annulees"] == 1 and resultat["branches_rapportees"] == []
    toutes = cartes_du_tableau(noyau, tableau)
    assert {toutes[c].status for c in ouvertes} == {"archived"}
    assert toutes[exploration].claim_lock is None  # la réclamation de l'exécutant est perdue
    assert noyau.questions.question(conn, q["question"])["etat"] == "annulee"
    assert conn.execute("SELECT COUNT(*) FROM attentes").fetchone()[0] == 0
    fiche = noyau.projets.projet(conn, projet["id"])
    assert fiche["termine_le"] is not None
    # Aucune notification, même après une passe de l'émetteur (événements « archived » lus).
    noyau.emetteur.passe(conn)
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == notifs_avant
    [journal] = conn.execute("SELECT acteur, detail FROM journal WHERE action = 'cloture'").fetchall()
    assert journal[0] == "proprietaire:test"
    assert json.loads(journal[1]) == {"etat": "abandonne", "cartes_archivees": len(ouvertes),
                                      "cartes_non_archivees": [], "questions_annulees": 1}
    # L'exécutant voit la carte perdue : son battement suivant n'est plus valide (``_a_nous`` faux).
    tache = cartes_du_tableau(noyau, tableau)[exploration]
    assert not noyau.execution._a_nous(tache, "simule", run)


def test_clore_arrete_le_worker_d_une_carte_hermes_en_cours(noyau, conn):
    """Relecture finale de P7 (constat tests-4 a, cahier P7 § 13.1 « dont une running Hermes ») : une carte de Hermes
    en cours, réclamée comme le fait le répartiteur et dont le worker est un processus vivant de cet hôte, est archivée
    par « Clore le projet » ; Hermes (``archive_task``) arrête son worker et le dit (``archive_worker_termination``)."""
    import subprocess
    import sys
    import threading

    from hermes_cli import kanban_db as kb
    from hermes_cli.kanban_db_dispatch import _set_worker_pid

    projet = lancer_sans_depot(noyau, conn)
    tableau, planif = projet["tableau"], projet["cartes"]["planification"]
    worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    threading.Thread(target=worker.wait, daemon=True).start()  # récolté dès sa fin (jamais un zombie « vivant »)
    try:
        with noyau.ka.connexion(tableau) as kc:
            tache = noyau.ka.claim_task(kc, planif, ttl_seconds=900, claimer=kb._claimer_id())  # comme le répartiteur
            assert tache is not None and tache.status == "running"
            _set_worker_pid(kc, planif, worker.pid)
        resultat = _clore(noyau, conn, projet)
        assert planif in resultat["cartes_archivees"] and resultat["cartes_non_archivees"] == []
        with noyau.ka.connexion(tableau) as kc:
            assert noyau.ka.get_task(kc, planif).status == "archived"
            [fin] = [e for e in noyau.ka.list_events(kc, planif) if e.kind == "archive_worker_termination"]
        assert fin.payload["prev_pid"] == worker.pid and fin.payload["terminated"] is True, fin.payload
        assert worker.wait(timeout=15) is not None  # le processus du worker est bien arrêté
    finally:
        if worker.poll() is None:
            worker.kill()


def test_clore_apres_la_synthese_termine(noyau, conn, monkeypatch):
    plan = {"resume": "r", "etapes": PLAN["etapes"][:1]}
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch, plan)
    fiche = noyau.projets.projet(conn, projet["id"])
    decision = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "témoin")  # une carte reste ouverte
    terminer(noyau, projet["tableau"], cartes["e1"], "fait")
    terminer(noyau, projet["tableau"], tour["synthese"], "Conclusion.")
    assert noyau.emetteur.projets_termines(conn) == []  # la carte de décision ouverte retient le projet
    avant = [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications ORDER BY id")]
    assert [g for _c, g in avant] == ["plafond"]  # celle de la carte de décision, émise à sa création
    resultat = _clore(noyau, conn, projet)
    assert (resultat["clos"], resultat["etat"]) == (True, "termine")
    assert resultat["cartes_archivees"] == [decision]
    assert noyau.emetteur.projets_termines(conn) == []  # plus actif : aucune notification « terminé »
    noyau.emetteur.passe(conn)
    assert [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications ORDER BY id")] == avant


def test_clore_un_projet_en_pause(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    assert _clore(noyau, conn, projet)["etat"] == "abandonne"


def test_refus(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    for confirmation in (None, False, "oui", 1):
        with pytest.raises(noyau.textes.RefusACP) as exc:
            _clore(noyau, conn, projet, confirmation)
        assert exc.value.code == "confirmation"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.clore(conn, "p_inconnu", confirmation=True, auteur="p")
    assert exc.value.code == "projet_inconnu"
    _clore(noyau, conn, projet)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _clore(noyau, conn, projet)
    assert exc.value.code == "projet_fini" and "est abandonné" in exc.value.message
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'cloture'").fetchone()[0] == 1


def test_course_avec_la_passe_de_l_emetteur(noyau, conn, monkeypatch):
    """La passe de l'émetteur termine le projet entre la lecture et la mise à jour conditionnelle : une seule des deux
    gagne ; la clôture le dit et ne fait RIEN (ni archive, ni annulation)."""
    projet = lancer_sur_depot(noyau, conn)
    reel = noyau.projets.synthese_du_tour_faite

    def pendant_la_lecture(conn_, fiche):
        with noyau.base.transaction(conn_):
            conn_.execute("UPDATE projets SET etat = 'termine' WHERE id = ?", (fiche["id"],))
        return reel(conn_, fiche)
    monkeypatch.setattr(noyau.projets, "synthese_du_tour_faite", pendant_la_lecture)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _clore(noyau, conn, projet)
    assert exc.value.code == "projet_fini" and "a changé d'état pendant la clôture (terminé)" in exc.value.message
    ouvertes = [t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status != "archived"]
    assert len(ouvertes) == 2
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'cloture'").fetchone()[0] == 0
