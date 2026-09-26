"""Questions d'une carte du poste (cahier P4 § 8.6, 8.7 ; décision D28) : carte « répondre », escalade,
réponses de Hermes et du propriétaire, reprise d'un triage."""

from __future__ import annotations

import pytest

from conftest import carte, cartes_du_tableau, en_worker, lancer_sur_depot, outil, reclamer


def _carte_du_poste_en_cours(noyau, conn, monkeypatch, **options):
    projet = lancer_sur_depot(noyau, conn, **options)
    run = reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    return projet, projet["cartes"]["exploration"], run


def test_poser_planifie_la_carte_et_cree_repondre(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch)
    reponse = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run,
                                    texte="Faut-il garder Python 3.11 ?")
    assert reponse["etat"] == "ouverte" and reponse["question"].startswith("q_")
    assert carte(noyau, projet["tableau"], poste).status == "scheduled"
    repondre = carte(noyau, projet["tableau"], reponse["carte_repondre"])
    assert (repondre.status, repondre.assignee, repondre.priority, repondre.skills) == (
        "ready", "default", 10, ["acp-questions"])
    assert "Faut-il garder Python 3.11 ?" in repondre.body
    # Idempotente : la même question sur le même run ne crée rien de plus.
    again = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="autre")
    assert again["deja_posee"] is True and again["question"] == reponse["question"]
    assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 1


def test_politique_proprietaire_escalade_directe(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch, reponses="proprietaire")
    reponse = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="Quel nom ?")
    assert reponse["etat"] == "escaladee" and reponse["carte_repondre"] is None
    notifs = [tuple(l) for l in conn.execute("SELECT cle, genre, etat FROM notifications")]
    assert notifs == [(f"question:{reponse['question']}", "question", "en_attente")]
    texte = conn.execute("SELECT texte FROM notifications").fetchone()[0]
    assert texte == "ACP — Projet « Outil jetable » : une question attend votre réponse." and "Quel nom" not in texte


def test_repondre_commente_et_debloque(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="Python 3.11 ?")
    en_worker(monkeypatch, projet["tableau"], q["carte_repondre"])
    reponse = outil(noyau, "question_repondre", {"reponse": "Oui, garder 3.11.",
                                                  "fondement": "Décision : compatibilité 3.11."})
    assert reponse == {"ok": True, "question": q["question"], "etat": "repondue", "carte_debloquee": True}
    assert carte(noyau, projet["tableau"], poste).status == "ready"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        commentaires = noyau.ka.list_comments(kc, poste)
    assert [(c.author, c.body) for c in commentaires] == [
        ("hermes (acp-questions)", "Oui, garder 3.11.\n\nFondement : Décision : compatibilité 3.11.")]
    ligne = noyau.questions.question(conn, q["question"])
    assert (ligne["etat"], ligne["repondu_par"]) == ("repondue", "hermes")
    # Une question fermée ne se rouvre pas ; hors de sa carte « répondre », refus de contexte.
    assert outil(noyau, "question_repondre", {"reponse": "x", "fondement": "y"})["message"] == (
        f"Refusé par ACP : la question {q['question']} n'est plus ouverte (repondue).")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    assert outil(noyau, "question_repondre", {"reponse": "x", "fondement": "y"})["message"] == (
        "Refusé par ACP : question_repondre ne s'appelle que depuis la carte « répondre » de cette question.")


def test_escalader_notifie_une_fois(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="Budget ?")
    en_worker(monkeypatch, projet["tableau"], q["carte_repondre"])
    reponse = outil(noyau, "question_escalader", {"motif": "Question de dépense : le propriétaire tranche."})
    assert reponse == {"ok": True, "question": q["question"], "etat": "escaladee"}
    noyau.emetteur.questions_escaladees(conn)
    noyau.emetteur.questions_escaladees(conn)
    assert conn.execute("SELECT COUNT(*) FROM notifications WHERE genre = 'question'").fetchone()[0] == 1
    assert carte(noyau, projet["tableau"], poste).status == "scheduled"  # attend le propriétaire


def test_deux_questions_successives_sans_triage(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch, reponses="proprietaire")
    for tour in range(2):
        q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte=f"Question {tour} ?")
        noyau.questions.repondre_par_proprietaire(conn, q["question"], reponse="Oui.", auteur="proprietaire:test")
        assert carte(noyau, projet["tableau"], poste).status == "ready"
        run = reclamer(noyau, projet["tableau"], poste)
    tache = carte(noyau, projet["tableau"], poste)
    assert tache.status == "running" and tache.block_recurrences == 0 and tache.block_kind is None


def test_reponse_du_proprietaire(noyau, conn, monkeypatch):
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="Nom du module ?")
    resultat = noyau.questions.repondre_par_proprietaire(conn, q["question"], reponse="outil_jetable",
                                                         auteur="proprietaire:test")
    assert resultat["carte_debloquee"] is True
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert [(c.author, c.body) for c in noyau.ka.list_comments(kc, poste)] == [("proprietaire", "outil_jetable")]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.repondre_par_proprietaire(conn, q["question"], reponse="encore", auteur="p")
    assert exc.value.code == "question_fermee"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.repondre_par_proprietaire(conn, "q_inconnue", reponse="x", auteur="p")
    assert exc.value.code == "question_inconnue"
    listes = noyau.questions.lister(conn)
    assert listes["questions"] == []


def test_poser_refuse_hors_d_une_carte_du_poste_en_cours(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.poser(conn, tableau=projet["tableau"], carte=projet["cartes"]["planification"], run_id=None,
                              texte="?")
    assert exc.value.code == "question_carte"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.poser(conn, tableau=projet["tableau"], carte=projet["cartes"]["exploration"], run_id=None,
                              texte="?")
    assert exc.value.code == "question_carte_etat"


def test_reprendre_un_triage(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    fiche = noyau.projets.projet(conn, projet["id"])
    carte_triage = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "3 tours planifiés")
    assert carte(noyau, projet["tableau"], carte_triage).status == "triage"
    listes = noyau.questions.lister(conn)
    assert [t["carte"] for t in listes["triage"]] == [carte_triage]
    resultat = noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=carte_triage,
                                                consigne="Conclure avec ce qui est fait.", auteur="proprietaire:t")
    assert resultat == {"carte": carte_triage, "reprise": True}
    tache = carte(noyau, projet["tableau"], carte_triage)
    assert tache.status in ("todo", "ready") and "Conclure avec ce qui est fait." in tache.body
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=carte_triage, consigne=None, auteur="p")
    assert exc.value.code == "triage_inconnu"
    assert len([t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]) == 0
