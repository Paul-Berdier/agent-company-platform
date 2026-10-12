"""Résultats d'exécution lus depuis les vrais runs Hermes de l'image épinglée."""
from __future__ import annotations

import json

import pytest

from conftest import lancer_sur_depot

MACHINE = "m0123456789a"


def _vues(noyau, conn, projet, carte):
    fiche = noyau.projets.exiger_projet(conn, projet["id"])
    detail = noyau.projets.etat(conn, fiche)
    ligne = next(c for c in detail["cartes"] if c["carte"] == carte)
    entiere = noyau.projets.lire_carte(conn, fiche, carte)
    assert ligne["execution"] == entiere["execution"]
    return ligne["execution"]


def _reclamer(noyau, projet, carte, machine=MACHINE):
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.claim_task(kc, carte, claimer="acp-poste:" + machine)
        assert tache is not None
        return tache.current_run_id


def _meta(carte):
    return {"branche": "hermes/" + carte, "base": "1" * 40, "tete": "2" * 40,
            "diffstat": {"fichiers": 2, "ajouts": 8, "retraits": 0},
            "verification": {"etat": "reussie", "code": 0, "tentatives": 1},
            "jetons": {"entree": 12, "sortie": 4, "cache": 0}, "modele_servi": None}


def test_aucune_execution_et_observation_courante(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    assert _vues(noyau, conn, projet, carte)["etat"] == "aucune"
    identifiant = _reclamer(noyau, projet, carte)
    vue = _vues(noyau, conn, projet, carte)
    assert (vue["etat"], vue["portee"], vue["run_id"], vue["machine_id"], vue["statut"]) == (
        "observe", "courante", identifiant, MACHINE, "running")
    assert vue["metadonnees"] is None


def test_resultat_termine_appartient_au_run_et_ne_transmet_pas_metadata_libre(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    identifiant = _reclamer(noyau, projet, carte)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.complete_task(kc, carte, summary="Exploration terminée.", expected_run_id=identifiant,
                                      metadata=dict(_meta(carte), sortie_brute="NE_PAS_EXPORTER"))
        assert noyau.ka.get_task(kc, carte).current_run_id is None
    vue = _vues(noyau, conn, projet, carte)
    assert vue["run_id"] == identifiant and vue["portee"] == "derniere"
    assert vue["provenance"] == "hermes.task_runs" and vue["machine_id"] == MACHINE
    assert vue["metadonnees"] == _meta(carte)
    assert "NE_PAS_EXPORTER" not in json.dumps(vue)
    assert vue["fin"] >= vue["debut"]


def test_reprise_ne_recycle_pas_resultat_ni_machine_du_run_en_revue(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    premier = _reclamer(noyau, projet, carte)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.request_review(kc, carte, summary="À relire.", expected_run_id=premier, metadata=_meta(carte))
        assert noyau.ka.reopen_review_task(kc, carte)
    # Colonnes historiques de demandes conservées par une relance : elles ne sont pas une preuve du nouveau run.
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET machine_id = ?, tete = ?, verification = ? WHERE carte = ?",
                     (MACHINE, "2" * 40, '{"etat":"reussie"}', carte))
    second = _reclamer(noyau, projet, carte, "m11111111111")
    assert second != premier
    vue = _vues(noyau, conn, projet, carte)
    assert vue["run_id"] == second and vue["machine_id"] == "m11111111111"
    assert vue["portee"] == "courante" and vue["metadonnees"] is None


def test_run_illisible_ne_supprime_pas_le_detail_projet(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    _reclamer(noyau, projet, carte)
    def panne(*args, **kwargs):
        raise RuntimeError("table de runs illisible")
    monkeypatch.setattr(noyau.ka, "get_run", panne)
    assert _vues(noyau, conn, projet, carte)["etat"] == "indisponible"


def test_carte_autre_projet_ne_divulgue_pas_execution(noyau, conn):
    premier = lancer_sur_depot(noyau, conn, titre="Premier")
    second = lancer_sur_depot(noyau, conn, titre="Second")
    carte = second["cartes"]["exploration"]
    _reclamer(noyau, second, carte)
    fiche = noyau.projets.exiger_projet(conn, premier["id"])
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.projets.lire_carte(conn, fiche, carte)
    assert exc.value.code == "carte_inconnue"


def test_question_ouverte_conserve_l_attente_du_vrai_run(noyau, conn):
    projet = lancer_sur_depot(noyau, conn, reponses="proprietaire")
    carte = projet["cartes"]["exploration"]
    identifiant = _reclamer(noyau, projet, carte)
    question = noyau.questions.poser(conn, tableau=projet["tableau"], carte=carte,
                                    run_id=identifiant, texte="Quelle version faut-il conserver ?")
    assert question["etat"] == "escaladee"
    vue = _vues(noyau, conn, projet, carte)
    assert (vue["run_id"], vue["portee"], vue["statut"], vue["issue"]) == (
        identifiant, "derniere", "scheduled", "scheduled")
    assert vue["machine_id"] == MACHINE and vue["metadonnees"] is None


def test_projection_lit_un_run_par_carte_et_ne_se_replie_pas(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    identifiant = _reclamer(noyau, projet, carte)
    fiche = noyau.projets.exiger_projet(conn, projet["id"])
    get_run, latest_run = noyau.ka.get_run, noyau.ka.latest_run
    appels = []

    def courante(kc, run_id):
        appels.append(("courante", run_id))
        return get_run(kc, run_id)

    def derniere(kc, task_id):
        appels.append(("derniere", task_id))
        return latest_run(kc, task_id)

    monkeypatch.setattr(noyau.ka, "get_run", courante)
    monkeypatch.setattr(noyau.ka, "latest_run", derniere)
    assert noyau.projets.lire_carte(conn, fiche, carte)["execution"]["run_id"] == identifiant
    assert appels == [("courante", identifiant)]
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.complete_task(kc, carte, summary="Terminé.", expected_run_id=identifiant,
                                      metadata=_meta(carte))
    appels.clear()
    assert noyau.projets.lire_carte(conn, fiche, carte)["execution"]["run_id"] == identifiant
    assert appels == [("derniere", carte)]
    appels.clear()
    monkeypatch.setattr(noyau.ka, "latest_run", lambda kc, task_id: None)
    assert noyau.projets.lire_carte(conn, fiche, carte)["execution"]["etat"] == "aucune"
    assert appels == []


def test_run_courant_absent_ne_reprend_pas_une_ancienne_tentative(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    carte = projet["cartes"]["exploration"]
    premier = _reclamer(noyau, projet, carte)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.request_review(kc, carte, summary="À vérifier.", expected_run_id=premier,
                                      metadata=_meta(carte))
        assert noyau.ka.reopen_review_task(kc, carte)
    _reclamer(noyau, projet, carte)
    appels_derniere = []
    monkeypatch.setattr(noyau.ka, "get_run", lambda kc, run_id: None)
    monkeypatch.setattr(noyau.ka, "latest_run", lambda kc, task_id: appels_derniere.append(task_id))
    assert _vues(noyau, conn, projet, carte)["etat"] == "indisponible"
    assert appels_derniere == []
