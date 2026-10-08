"""« Qui répond » modifiable (étape P7, cahier P7 § 4.2, décision P7-3 ; correction K6) : changement en cours de
projet, question SUIVANTE escaladée directement, question ouverte gardant son traitement (« Hermes y répond »), refus
sans dépôt (D42), sur un projet fini et pour une valeur inconnue ; journal ``reglage_reponses``."""

from __future__ import annotations

import json

import pytest

from conftest import carte, lancer_sans_depot, lancer_sur_depot, reclamer


def _changer(noyau, conn, projet, reponses):
    return noyau.projets.changer_reponses(conn, projet["id"], reponses=reponses, auteur="proprietaire:test")


def test_changement_en_cours_de_projet_vaut_pour_les_questions_suivantes(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, projet["tableau"], exploration)
    premiere = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run,
                                     texte="Faut-il garder Python 3.11 ?")
    assert premiere["etat"] == "ouverte" and premiere["carte_repondre"]
    resultat = _changer(noyau, conn, projet, "proprietaire")
    assert (resultat["avant"], resultat["apres"], resultat["questions_ouvertes_inchangees"]) == (
        "hermes_d_abord", "proprietaire", 1)
    assert resultat["projet"]["reponses"] == "proprietaire"
    # La question ouverte garde son traitement : Hermes y répond toujours (règle unique « chez », K6).
    [q] = noyau.questions.lister(conn)["questions"]
    assert (q["id"], q["etat"], q["chez"], q["carte_repondre"]) == (
        premiere["question"], "ouverte", "hermes", premiere["carte_repondre"])
    assert carte(noyau, projet["tableau"], premiere["carte_repondre"]).status == "ready"
    # Réponse du propriétaire à la première, puis question SUIVANTE : escaladée directement, sans carte « répondre ».
    noyau.questions.repondre_par_proprietaire(conn, premiere["question"], reponse="Oui.", auteur="proprietaire:test")
    run = reclamer(noyau, projet["tableau"], exploration)
    suivante = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run,
                                     texte="Et la 3.12 ?")
    assert (suivante["etat"], suivante["carte_repondre"]) == ("escaladee", None)
    assert [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications")] == [
        (f"question:{suivante['question']}", "question")]
    journal = conn.execute("SELECT acteur, detail FROM journal WHERE action = 'reglage_reponses'").fetchall()
    assert [l[0] for l in journal] == ["proprietaire:test"]
    assert json.loads(journal[0][1]) == {"avant": "hermes_d_abord", "apres": "proprietaire", "questions_ouvertes": 1}


def test_retour_a_hermes_d_abord(noyau, conn):
    projet = lancer_sur_depot(noyau, conn, reponses="proprietaire")
    assert _changer(noyau, conn, projet, "hermes_d_abord")["apres"] == "hermes_d_abord"
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, projet["tableau"], exploration)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run, texte="Quel nom ?")
    assert q["etat"] == "ouverte" and q["carte_repondre"]


def test_refus_sans_depot_projet_fini_valeur_inconnue(noyau, conn):
    sans_depot = lancer_sans_depot(noyau, conn)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _changer(noyau, conn, sans_depot, "proprietaire")
    assert exc.value.code == "reponses_sans_objet" and exc.value.message == (
        "Refusé par ACP : Sans dépôt, aucune question ne peut naître : ce réglage est sans objet.")
    projet = lancer_sur_depot(noyau, conn)
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _changer(noyau, conn, projet, "personne")
    assert exc.value.code == "reponses"
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.changer_reponses(conn, "p_inconnu", reponses="proprietaire", auteur="p")
    assert exc.value.code == "projet_inconnu"
    for etat in ("termine", "abandonne"):
        with noyau.base.transaction(conn):
            conn.execute("UPDATE projets SET etat = ? WHERE id = ?", (etat, projet["id"]))
        with pytest.raises(noyau.textes.RefusACP) as exc:
            _changer(noyau, conn, projet, "proprietaire")
        assert exc.value.code == "projet_fini"
    assert noyau.projets.projet(conn, projet["id"])["reponses"] == "hermes_d_abord"
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'reglage_reponses'").fetchone()[0] == 0


def test_projet_en_pause_modifiable(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    assert _changer(noyau, conn, projet, "proprietaire")["projet"]["etat"] == "en_pause"
