"""Insertion d'une correction (cahier P4 § 6.4) : préparée et testée en P4 avec le poste simulé, câblée en P6."""

from __future__ import annotations

from conftest import carte, cartes_du_tableau, en_worker, lancer_sur_depot, outil, reclamer, terminer

PLAN = {"resume": "Une étape.", "etapes": [
    {"ref": "e1", "titre": "Écrire", "classe": "implementation", "consigne": "Écrire outil.py.", "voie": "poste-codex"}]}


def _tour_1(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    terminer(noyau, projet["tableau"], projet["cartes"]["exploration"], "Carte du dépôt.")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", PLAN)
    assert tour["ok"], tour
    impl = next(c["carte"] for c in tour["cartes"] if c["role"] == "implementation")
    rel = next(c["carte"] for c in tour["cartes"] if c["role"] == "relecture")
    reclamer(noyau, projet["tableau"], impl)
    terminer(noyau, projet["tableau"], impl, "Implémenté.")
    run = reclamer(noyau, projet["tableau"], rel)
    return projet, tour, impl, rel, run


def test_ordre_correction_liaison_puis_fin(noyau, conn, monkeypatch):
    projet, tour, impl, rel, run = _tour_1(noyau, conn, monkeypatch)
    synthese = tour["synthese"]
    vues = []

    def sonde(etape):
        vues.append((etape, carte(noyau, projet["tableau"], synthese).status))

    resultat = noyau.graphe.inserer_correction(conn, tableau=projet["tableau"], carte_relecture=rel,
                                               run_id_relecture=run, consigne="Corriger la gestion des erreurs.",
                                               sonde=sonde)
    assert [e for e, _ in vues] == ["controle", "cartes", "liaison_correction", "liaison_relecture", "fin"]
    assert all(statut == "todo" for _, statut in vues), vues  # la synthèse n'est JAMAIS prête entre les étapes
    assert resultat["relecture_terminee"] is True and resultat["n"] == 1
    toutes = cartes_du_tableau(noyau, projet["tableau"])
    correction, relecture2 = toutes[resultat["correction"]], toutes[resultat["relecture"]]
    assert toutes[rel].status == "done" and correction.status == "ready" and relecture2.status == "todo"
    assert (correction.assignee, relecture2.assignee) == ("poste-codex", "poste-claude")
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.parent_ids(kc, correction.id) == [rel]
        assert noyau.ka.parent_ids(kc, relecture2.id) == [correction.id]
        assert {correction.id, relecture2.id} <= set(noyau.ka.parent_ids(kc, synthese))
    # La synthèse ne part qu'après la correction ET sa relecture.
    reclamer(noyau, projet["tableau"], correction.id)
    terminer(noyau, projet["tableau"], correction.id, "Corrigé.")
    assert carte(noyau, projet["tableau"], synthese).status == "todo"
    reclamer(noyau, projet["tableau"], relecture2.id)
    terminer(noyau, projet["tableau"], relecture2.id, "Relu : conforme.")
    assert carte(noyau, projet["tableau"], synthese).status == "ready"
    assert noyau.projets.projet(conn, projet["id"])["cartes_creees"] == 2 + 3 + 2


def test_temoin_sans_liaison_la_synthese_partirait(noyau, conn, monkeypatch):
    """Témoin négatif : si la correction n'était pas liée à la synthèse, la fin de la relecture rendrait la
    synthèse prête alors qu'une correction reste à faire."""
    projet, tour, impl, rel, run = _tour_1(noyau, conn, monkeypatch)
    monkeypatch.setattr(noyau.ka, "link_tasks", lambda *a, **k: False)
    noyau.graphe.inserer_correction(conn, tableau=projet["tableau"], carte_relecture=rel, run_id_relecture=run,
                                    consigne="Corriger.")
    assert carte(noyau, projet["tableau"], tour["synthese"]).status == "ready"


def test_plafond_corrections_triage(noyau, conn, monkeypatch):
    noyau.base.poser_reglage(conn, "plafond_corrections", 1, "test")
    projet, tour, impl, rel, run = _tour_1(noyau, conn, monkeypatch)
    premiere = noyau.graphe.inserer_correction(conn, tableau=projet["tableau"], carte_relecture=rel,
                                               run_id_relecture=run, consigne="Corriger.")
    reclamer(noyau, projet["tableau"], premiere["correction"])
    terminer(noyau, projet["tableau"], premiere["correction"], "Corrigé.")
    run2 = reclamer(noyau, projet["tableau"], premiere["relecture"])
    try:
        noyau.graphe.inserer_correction(conn, tableau=projet["tableau"], carte_relecture=premiere["relecture"],
                                        run_id_relecture=run2, consigne="Encore.")
        raise AssertionError("la seconde correction aurait dû être refusée")
    except noyau.textes.RefusACP as exc:
        assert (exc.code, exc.message) == ("plafond_corrections", "Refusé par ACP : plafond de 1 corrections atteint "
                                           "pour l'étape « e1 » ; une carte de triage vous est adressée.")
    triage = [t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    assert [t.title for t in triage] == ["Plafond atteint : corrections — votre décision est attendue"]
    # La relecture en cours n'a pas été terminée par le refus.
    assert carte(noyau, projet["tableau"], premiere["relecture"]).status == "running"
