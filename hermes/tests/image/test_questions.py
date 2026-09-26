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
    assert reponse == {"ok": True, "question": q["question"], "etat": "repondue", "carte_debloquee": True,
                       "reprise_differee": False}
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
    # Carte de décision au plafond de tours : « Reprendre » la PROLONGE (décision D41 ; tests dédiés plus bas).
    assert resultat == {"carte": carte_triage, "reprise": True, "action": "prolongation",
                        "plafond": {"genre": "tours", "avant": 3, "apres": 4}}
    tache = carte(noyau, projet["tableau"], carte_triage)
    assert tache.status in ("todo", "ready") and "Conclure avec ce qui est fait." in tache.body
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=carte_triage, consigne=None, auteur="p")
    assert exc.value.code == "triage_inconnu"
    assert len([t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]) == 0


# ============================================================ corrections de la relecture de P4

RAISON_ETRANGERE = ("Refusé par ACP : carte poste-* non émise par le greffon acp-poste ; seul le greffon crée les "
                    "cartes du poste.")


def test_raison_connue_des_cartes_bloquees_et_en_triage(noyau, conn):
    """Relecture de P4 (haute) : /v1/questions rendait « raison : None » (« Inconnu » à la page) pour une carte
    bloquée avec une raison : ``block_task`` de Hermes la range dans l'événement, pas dans
    ``last_failure_error``. Sans dépôt, bloquer avec sa raison est le SEUL moyen pour Hermes de signaler un
    manque : la raison doit arriver jusqu'au propriétaire. Idem pour une carte passée en triage par Hermes."""
    projet = lancer_sur_depot(noyau, conn)
    tableau = projet["tableau"]
    with noyau.ka.connexion(tableau) as kc:
        etrangere = noyau.ka.create_task(kc, title="Carte à la main", body="x", assignee="poste-codex",
                                         created_by="proprietaire", board=tableau)
    assert noyau.etrangeres.balayer(conn) == [(tableau, etrangere)]
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, tableau, exploration)
    with noyau.ka.connexion(tableau) as kc:
        assert noyau.ka.block_task(kc, exploration, reason="Il manque le jeton de la base de test.",
                                   kind="needs_input", expected_run_id=run)
    vues = {b["carte"]: b["raison"] for b in noyau.questions.lister(conn)["bloquees"]}
    assert vues == {etrangere: RAISON_ETRANGERE, exploration: "Il manque le jeton de la base de test."}
    # Carte passée en triage par le disjoncteur de blocages de Hermes : sa raison, et « Reprendre » seulement.
    with noyau.ka.connexion(tableau) as kc:
        assert noyau.ka.unblock_task(kc, exploration)  # le propriétaire débloque ; le même manque revient
        assert noyau.ka.block_task(kc, exploration, reason="Encore et toujours pas de jeton.", kind="needs_input")
        assert noyau.ka.get_task(kc, exploration).status == "triage"
    [triage] = noyau.questions.lister(conn)["triage"]
    assert (triage["carte"], triage["raison"], triage["genre"], triage["actions"]) == (
        exploration, "Encore et toujours pas de jeton.", None, ["reprendre"])


def test_question_listee_avec_le_titre_de_sa_carte_et_son_contexte(noyau, conn, monkeypatch):
    """Relecture de P4 (produit) : une question n'était rattachée qu'à l'identifiant de sa carte, et son contexte
    (fourni par le poste, enregistré) n'était jamais rendu : le propriétaire répondait sans lui."""
    projet, poste, run = _carte_du_poste_en_cours(noyau, conn, monkeypatch, reponses="proprietaire")
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=poste, run_id=run, texte="Quelle version ?",
                              contexte="Le dépôt cible Python 3.11 et 3.12 dans sa CI.")
    [ligne] = noyau.questions.lister(conn)["questions"]
    assert ligne["id"] == q["question"]
    assert ligne["carte_titre"] == "Exploration du dépôt « jetable »"
    assert ligne["contexte"] == "Le dépôt cible Python 3.11 et 3.12 dans sa CI."
