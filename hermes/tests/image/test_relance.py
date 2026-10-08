"""« Relancer » une carte arrêtée (étape P7, cahier P7 § 3.4, décision P7-2 ; corrections K4, K5, K25) : refus dans
l'ordre du cahier, carte Hermes (commentaire puis déblocage), carte de l'exécutant (session neuve forcée par
``issue = 'relancee'``, consigne du propriétaire EN TÊTE et consigne d'origine tronquée pour tenir dans la carte), compteur
d'échecs remis à zéro, second blocage de même raison en triage, et la vue de la file Questions."""

from __future__ import annotations

import json

import pytest

from conftest import carte, lancer_sans_depot, lancer_sur_depot, reclamer

MACHINE = "m0000000000a"
SECRET_FACTICE = "AKIA" + "ABCDEFGHIJKLMNOP"  # forme d'une clé AWS, factice (concaténée : hors du balayage du dépôt)


def _bloquer(noyau, tableau: str, identifiant: str, raison: str = "Il manque le jeton de la base de test.",
             kind: str = "capability") -> None:
    with noyau.ka.connexion(tableau) as kc:
        tache = noyau.ka.get_task(kc, identifiant)
        assert noyau.ka.block_task(kc, identifiant, kind=kind, reason=raison,
                                   expected_run_id=tache.current_run_id), identifiant
        assert noyau.ka.get_task(kc, identifiant).status == "blocked"


def _relancer(noyau, conn, projet, identifiant, consigne=None):
    return noyau.questions.relancer_carte(conn, tableau=projet["tableau"], carte=identifiant, consigne=consigne,
                                          auteur="proprietaire:test")


def _refus(noyau, conn, projet, identifiant, consigne=None):
    with pytest.raises(noyau.textes.RefusACP) as exc:
        _relancer(noyau, conn, projet, identifiant, consigne)
    return exc.value


def _demande(noyau, conn, projet, identifiant):
    return noyau.projets.demande_de_la_carte(conn, projet["tableau"], identifiant)


def _exploration_bloquee(noyau, conn, *, issue_precedente=None):
    """Exploration de l'exécutant (poste-claude) réclamée, rendue avec ``issue_precedente`` comme le ferait
    ``reprendre``, puis bloquée — sur le chemin exact du piège K4 n° 1 (dernière issue dans ``ISSUES_REPRISE``)."""
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    reclamer(noyau, projet["tableau"], exploration)
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET machine_id = ?, issue = ? WHERE tableau = ? AND carte = ?",
                     (MACHINE, issue_precedente, projet["tableau"], exploration))
    _bloquer(noyau, projet["tableau"], exploration)
    return projet, exploration


def _servir(noyau, conn, projet, identifiant) -> dict:
    """Carte telle que ``reclamer`` la servirait à l'exécutant MACHINE : réclamée comme lui, construite par
    ``execution.construire_carte`` (contrat ``DemandeCarte`` compris)."""
    fiche = noyau.projets.projet(conn, projet["id"])
    with noyau.ka.connexion(projet["tableau"]) as kc:
        tache = noyau.ka.claim_task(kc, identifiant, ttl_seconds=2700, claimer=noyau.execution.claimer(MACHINE))
        assert tache is not None
        return noyau.execution.construire_carte(conn, kc, fiche, _demande(noyau, conn, projet, identifiant), tache,
                                                MACHINE)


# ------------------------------------------------------------------ refus, dans l'ordre du cahier


def test_refus_projet_inconnu_et_carte_non_acp(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    exc = _refus(noyau, conn, {"tableau": "acp-inconnu-0000"}, "t_0000")
    assert exc.code == "projet_inconnu"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        etrangere = noyau.ka.create_task(kc, title="Carte à la main", body="x", assignee="default",
                                         created_by="proprietaire", board=projet["tableau"])
        assert noyau.ka.block_task(kc, etrangere, kind="capability", reason="à la main")
    exc = _refus(noyau, conn, projet, etrangere)
    assert exc.code == "carte_non_acp" and exc.message == (
        f"Refusé par ACP : la carte {etrangere} du tableau « {projet['tableau']} » n'a pas été émise par ACP : ACP ne "
        "la relance pas.")
    [vue] = [b for b in noyau.questions.lister(conn)["bloquees"] if b["carte"] == etrangere]
    assert (vue["relancable"], vue["refus_relance"]) == (False, "Carte non émise par ACP : ACP ne la relance pas.")


def test_refus_projet_en_pause_termine_abandonne(noyau, conn):
    projet, exploration = _exploration_bloquee(noyau, conn)
    noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    exc = _refus(noyau, conn, projet, exploration)
    assert exc.code == "projet_en_pause" and "reprenez d'abord le projet" in exc.message
    [vue] = noyau.questions.lister(conn)["bloquees"]
    assert (vue["relancable"], vue["refus_relance"]) == (False, "Projet en pause : reprenez d'abord le projet.")
    for etat, lisible in (("termine", "terminé"), ("abandonne", "abandonné"), ("creation", "en création")):
        with noyau.base.transaction(conn):
            conn.execute("UPDATE projets SET etat = ? WHERE id = ?", (etat, projet["id"]))
        exc = _refus(noyau, conn, projet, exploration)
        assert exc.code == "projet_fini" and exc.message == (
            f"Refusé par ACP : le projet « Outil jetable » est {lisible} : aucune action possible.")
    assert carte(noyau, projet["tableau"], exploration).status == "blocked"  # rien n'a bougé
    assert _demande(noyau, conn, projet, exploration)["issue"] is None


def test_refus_carte_non_arretee_et_en_revue(noyau, conn):
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    exc = _refus(noyau, conn, projet, exploration)
    assert exc.code == "carte_non_arretee" and "(statut : ready)" in exc.message
    run = reclamer(noyau, projet["tableau"], exploration)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.request_review(kc, exploration, summary="fichiers de pilotage touchés", expected_run_id=run)
    exc = _refus(noyau, conn, projet, exploration)
    assert exc.code == "carte_en_revue" and "Accepter" not in exc.message and "Revues" in exc.message


def _executant_de_la_partie_e(noyau, conn, mesure=True):
    """Exécutant actif dont le dernier inventaire porte (``mesure``) ou non (``None``, forme de P6) la visibilité
    mesurée de ses dépôts."""
    from conftest import inventaire_linux, poste_confirme

    machine, _jeton = poste_confirme(noyau, conn, nom="Exécutant Railway")
    with noyau.base.transaction(conn):
        noyau.inventaire.recevoir_dans(conn, machine, inventaire_linux(mesure=mesure))


def _carte_bloquee_pour_secret(noyau, conn, *, par_issue=True):
    projet = lancer_sur_depot(noyau, conn, titre="Outil secret")
    secret = projet["cartes"]["exploration"]
    reclamer(noyau, projet["tableau"], secret)
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET machine_id = ?, issue = ? WHERE tableau = ? AND carte = ?",
                     (MACHINE, "bloquee:secret" if par_issue else "question", projet["tableau"], secret))
    _bloquer(noyau, projet["tableau"], secret, noyau.textes.RAISON_SECRET_EXECUTANT, kind="needs_input")
    return projet, secret


@pytest.mark.parametrize("mesure", [None, "aucun"], ids=["inventaire_de_p6", "sans_inventaire"])
def test_secret_refuse_tant_que_l_executant_n_est_pas_de_la_partie_e(noyau, conn, mesure):
    """Échec fermé : un exécutant de P6 reprendrait le worktree en quarantaine. Sans inventaire de la partie E (aucune
    visibilité mesurée publiée), la relance d'une carte bloquée pour secret reste refusée, et la file le dit."""
    if mesure != "aucun":
        _executant_de_la_partie_e(noyau, conn, mesure=mesure)
    projet, secret = _carte_bloquee_pour_secret(noyau, conn)
    assert noyau.questions.quarantaine_ecartee_par_l_executant(conn) is False
    exc = _refus(noyau, conn, projet, secret)
    assert exc.code == "carte_secret" and "exécutant à jour (étape P7, partie E)" in exc.message
    [vue] = [b for b in noyau.questions.lister(conn)["bloquees"] if b["carte"] == secret]
    assert (vue["relancable"], vue["quarantaine"]) == (False, True)
    assert vue["refus_relance"].startswith("Bloquée pour un secret : relance possible dès que l'exécutant à jour")
    assert carte(noyau, projet["tableau"], secret).status == "blocked"


@pytest.mark.parametrize("par_issue", [True, False], ids=["issue_bloquee_secret", "raison_fixe_seule"])
def test_carte_bloquee_pour_secret_se_relance_sur_une_branche_neuve(noyau, conn, par_issue):
    """K25 levé par la partie E (cahier P7 § 3.4) : l'exécutant ne reprend jamais le travail en quarantaine
    (apps/poste/tests/test_execution.py::test_relance_apres_secret_branche_neuve_sans_le_commit_fautif) ; avec un
    exécutant de la partie E (visibilité mesurée publiée), la carte bloquée pour un secret se relance donc, la file le
    signale (``quarantaine``) et la réponse dit ``branche_neuve``. La carte est resservie en SESSION NEUVE
    (``reprise: false``)."""
    _executant_de_la_partie_e(noyau, conn)
    assert noyau.questions.quarantaine_ecartee_par_l_executant(conn) is True
    projet = lancer_sur_depot(noyau, conn, titre="Outil secret")
    secret = projet["cartes"]["exploration"]
    reclamer(noyau, projet["tableau"], secret)
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET machine_id = ?, issue = ? WHERE tableau = ? AND carte = ?",
                     (MACHINE, "bloquee:secret" if par_issue else "question", projet["tableau"], secret))
    _bloquer(noyau, projet["tableau"], secret, noyau.textes.RAISON_SECRET_EXECUTANT, kind="needs_input")
    [vue] = [b for b in noyau.questions.lister(conn)["bloquees"] if b["carte"] == secret]
    assert (vue["relancable"], vue["refus_relance"], vue["quarantaine"], vue["executant"]) == (True, None, True, True)
    resultat = _relancer(noyau, conn, projet, secret)
    assert resultat == {"carte": secret, "relancee": True, "statut_apres": resultat["statut_apres"],
                        "session_neuve": True, "branche_neuve": True}
    assert resultat["statut_apres"] in ("ready", "todo")
    assert _demande(noyau, conn, projet, secret)["issue"] == "relancee"
    assert _servir(noyau, conn, projet, secret)["reprise"] is False
    journal = conn.execute("SELECT detail FROM journal WHERE action = 'relance' AND cible = ?", (secret,)).fetchone()
    assert json.loads(journal[0])["quarantaine"] is True


def test_carte_ordinaire_sans_quarantaine_ni_branche_neuve(noyau, conn):
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente="question")
    [vue] = [b for b in noyau.questions.lister(conn)["bloquees"] if b["carte"] == exploration]
    assert vue["quarantaine"] is False and vue["relancable"] is True
    resultat = _relancer(noyau, conn, projet, exploration)
    assert resultat["session_neuve"] is True and resultat["branche_neuve"] is False


def test_refus_consigne_invalide_ou_secrete(noyau, conn):
    projet, exploration = _exploration_bloquee(noyau, conn)
    for consigne in ("", "   ", "x" * 4001, 12):
        assert _refus(noyau, conn, projet, exploration, consigne).code == "arguments"
    exc = _refus(noyau, conn, projet, exploration, "utilise la clé " + SECRET_FACTICE)
    assert exc.code == "secret" and SECRET_FACTICE not in exc.message
    assert carte(noyau, projet["tableau"], exploration).status == "blocked"


# ------------------------------------------------------------------ carte Hermes


def test_carte_hermes_commentee_puis_debloquee(noyau, conn):
    projet = lancer_sans_depot(noyau, conn)
    planif = projet["cartes"]["planification"]
    _bloquer(noyau, projet["tableau"], planif, "Il manque la liste des sources.", kind="needs_input")
    with noyau.ka.connexion(projet["tableau"]) as kc:
        with noyau.ka.write_txn(kc):
            kc.execute("UPDATE tasks SET consecutive_failures = 2 WHERE id = ?", (planif,))
    [vue] = noyau.questions.lister(conn)["bloquees"]
    assert (vue["relancable"], vue["refus_relance"], vue["executant"]) == (True, None, False)
    resultat = _relancer(noyau, conn, projet, planif, "  Prends les sources officielles seulement.  ")
    assert resultat == {"carte": planif, "relancee": True, "statut_apres": "ready", "session_neuve": False,
                        "branche_neuve": False}
    tache = carte(noyau, projet["tableau"], planif)
    assert tache.status == "ready" and tache.consecutive_failures == 0
    with noyau.ka.connexion(projet["tableau"]) as kc:
        commentaires = [(c.author, c.body) for c in noyau.ka.list_comments(kc, planif)]
    assert commentaires == [("proprietaire", "Relance par le propriétaire — consigne :\n"
                                             "Prends les sources officielles seulement.")]
    demande = _demande(noyau, conn, projet, planif)
    assert demande["issue"] is None and demande["consigne_relance"] == "Prends les sources officielles seulement."
    assert demande["consigne_initiale"] is None  # la consigne d'une carte Hermes n'est pas réécrite
    journal = conn.execute("SELECT acteur, action, cible, detail FROM journal WHERE action = 'relance'").fetchall()
    assert [(l[0], l[1], l[2]) for l in journal] == [("proprietaire:test", "relance", planif)]
    assert json.loads(journal[0][3]) == {"avec_consigne": True, "executant": False, "quarantaine": False,
                                         "relancee": True, "statut_apres": "ready"}
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0  # geste du propriétaire


def test_carte_hermes_sans_consigne(noyau, conn):
    projet = lancer_sans_depot(noyau, conn)
    planif = projet["cartes"]["planification"]
    _bloquer(noyau, projet["tableau"], planif)
    assert _relancer(noyau, conn, projet, planif)["relancee"] is True
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.list_comments(kc, planif) == []


# ------------------------------------------------------------------ carte de l'exécutant (K4)


def test_piege_k4_sans_relance_la_carte_repart_en_reprise(noyau, conn):
    """Témoin du piège n° 1 : débloquée SANS passer par « Relancer », une carte dont la dernière issue est ``rendue``
    repart en ``reprise: true`` (l'exécutant n'enverrait à l'agent que SUITE_REPRISE, jamais la consigne)."""
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente="rendue")
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.unblock_task(kc, exploration)
    assert _servir(noyau, conn, projet, exploration)["reprise"] is True


@pytest.mark.parametrize("issue_precedente", ["rendue", "question", "arret", None])
def test_carte_de_l_executant_repart_en_session_neuve_avec_la_consigne(noyau, conn, issue_precedente):
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente=issue_precedente)
    initiale = _demande(noyau, conn, projet, exploration)["consigne"]
    resultat = _relancer(noyau, conn, projet, exploration, "Lis d'abord le README, puis arrête-toi.")
    assert resultat == {"carte": exploration, "relancee": True, "statut_apres": "ready", "session_neuve": True,
                        "branche_neuve": False}
    demande = _demande(noyau, conn, projet, exploration)
    assert (demande["issue"], demande["consigne_initiale"], demande["consigne_relance"]) == (
        "relancee", initiale, "Lis d'abord le README, puis arrête-toi.")
    servie = _servir(noyau, conn, projet, exploration)
    assert servie["reprise"] is False  # session NEUVE : l'agent lit la consigne entière
    assert servie["consigne"].startswith("## Consigne du propriétaire (relance du ")
    assert "\nLis d'abord le README, puis arrête-toi.\n\n## Consigne initiale\n" + initiale in servie["consigne"]
    assert servie["consigne_tronquee"] is False and servie["branche"] == f"hermes/{exploration}"


def test_consigne_longue_tronquee_section_intacte(noyau, conn):
    """Pièges n° 2 et 3 : consigne d'origine de 15 900 caractères + relance de 4 000 → carte VALIDE (contrat
    ``DemandeCarte`` : 16 000 caractères au plus), section du propriétaire intacte en tête, origine tronquée et dite."""
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente="rendue")
    longue = ("Écrire le module et ses tests, sans rien pousser. " * 400)[:15_900]
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET consigne = ? WHERE tableau = ? AND carte = ?",
                     (longue, projet["tableau"], exploration))
    relance = ("Ne touche qu'au dossier outil. " * 200)[:4000]
    assert _relancer(noyau, conn, projet, exploration, relance)["relancee"] is True
    servie = _servir(noyau, conn, projet, exploration)
    from acp_poste_contrat.machine import CONSIGNE_MAX

    assert servie["reprise"] is False and len(servie["consigne"]) <= CONSIGNE_MAX
    assert servie["consigne"].startswith("## Consigne du propriétaire (relance du ")
    assert relance.strip() in servie["consigne"]
    assert servie["consigne"].endswith("[… consigne initiale tronquée par ACP pour tenir, avec la relance, dans les "
                                       "16 000 caractères d'une carte]")
    assert _demande(noyau, conn, projet, exploration)["consigne_initiale"] == longue  # l'origine est gardée


def test_deuxieme_relance_repart_de_la_consigne_d_origine(noyau, conn):
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente="rendue")
    initiale = _demande(noyau, conn, projet, exploration)["consigne"]
    _relancer(noyau, conn, projet, exploration, "Première consigne.")
    reclamer(noyau, projet["tableau"], exploration)
    _bloquer(noyau, projet["tableau"], exploration, "Autre manque.", kind="needs_input")
    _relancer(noyau, conn, projet, exploration, "Seconde consigne.")
    consigne = _demande(noyau, conn, projet, exploration)["consigne"]
    assert "Seconde consigne." in consigne and "Première consigne." not in consigne
    assert consigne.endswith("## Consigne initiale\n" + initiale)


def test_second_blocage_de_meme_raison_en_triage(noyau, conn):
    """``block_recurrences`` survit au déblocage : une carte relancée qui rebloque pour la même raison part en
    triage (autonomie § 2, point 7), comme un déblocage à la main."""
    projet, exploration = _exploration_bloquee(noyau, conn)
    assert _relancer(noyau, conn, projet, exploration)["relancee"] is True
    reclamer(noyau, projet["tableau"], exploration)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        run = noyau.ka.get_task(kc, exploration).current_run_id
        noyau.ka.block_task(kc, exploration, kind="capability", reason="Il manque encore le jeton.",
                            expected_run_id=run)
        assert noyau.ka.get_task(kc, exploration).status == "triage"
    [vue] = noyau.questions.lister(conn)["triage"]
    assert vue["carte"] == exploration and vue["actions"] == ["reprendre"]


def test_echec_du_deblocage_restaure_la_demande(noyau, conn, monkeypatch):
    """Aucun faux succès : si ``unblock_task`` refuse (la carte a changé entre-temps), la réponse le dit et la demande
    de l'exécutant retrouve son état d'avant (issue, consigne)."""
    projet, exploration = _exploration_bloquee(noyau, conn, issue_precedente="rendue")
    avant = _demande(noyau, conn, projet, exploration)
    monkeypatch.setattr(noyau.ka, "unblock_task", lambda kc, carte_id: False)
    resultat = _relancer(noyau, conn, projet, exploration, "Consigne perdue ?")
    assert resultat == {"carte": exploration, "relancee": False, "statut_apres": "blocked", "session_neuve": False,
                        "branche_neuve": False}
    apres = _demande(noyau, conn, projet, exploration)
    assert {c: apres[c] for c in ("issue", "consigne", "consigne_relance", "relancee_le", "consigne_initiale")} == {
        c: avant[c] for c in ("issue", "consigne", "consigne_relance", "relancee_le", "consigne_initiale")}


def test_relance_ne_cree_aucune_carte(noyau, conn):
    projet, exploration = _exploration_bloquee(noyau, conn)
    avant = (noyau.projets.projet(conn, projet["id"])["cartes_creees"],
             conn.execute("SELECT COUNT(*) FROM demandes").fetchone()[0])
    _relancer(noyau, conn, projet, exploration, "Recommence.")
    assert (noyau.projets.projet(conn, projet["id"])["cartes_creees"],
            conn.execute("SELECT COUNT(*) FROM demandes").fetchone()[0]) == avant


# ------------------------------------------------------------------ bout en bout par les vraies routes (pile machine)


def test_carte_abandonnee_relancee_par_la_route_puis_servie_en_session_neuve(pile_machine):
    """Par les VRAIES routes : l'exécutant réclame l'exploration puis la rend (``reprendre`` : issue ``rendue``) ; le
    disjoncteur de Hermes l'abandonne (``gave_up``) ; le propriétaire la relance avec une consigne
    (``POST /v1/cartes/{t}/{c}/relancer``) ; le ``reclamer`` suivant la sert avec ``reprise: false``, la consigne du
    propriétaire en tête, et le compteur d'échecs à zéro."""
    from hermes_cli.kanban_db_dispatch import _record_task_failure

    from test_execution_p6 import Executant, _poste_actif

    noyau = pile_machine.noyau
    machine, jeton = _poste_actif(pile_machine)
    executant = Executant(pile_machine, machine, jeton)
    with noyau.base.connexion() as conn:
        projet = lancer_sur_depot(noyau, conn)
    servie = executant.carte(("poste-claude",))
    assert executant.envoyer("reprendre", servie, motif="redemarrage").json()["etat"] == "rendue"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        _record_task_failure(kc, servie["carte"], "panne du lanceur", outcome="crashed", force_trip=True)
        tache = noyau.ka.get_task(kc, servie["carte"])
        assert tache.status == "blocked" and tache.consecutive_failures >= 1
    file = pile_machine.get("/api/plugins/acp-poste/v1/questions").json()
    [arretee] = file["bloquees"]
    assert (arretee["carte"], arretee["abandonnee"], arretee["relancable"]) == (servie["carte"], True, True)
    reponse = pile_machine.post(f"/api/plugins/acp-poste/v1/cartes/{projet['tableau']}/{servie['carte']}/relancer",
                                {"consigne": "Repars de zéro : le lanceur est réparé."})
    assert reponse.status_code == 200 and reponse.json() == {
        "carte": servie["carte"], "relancee": True, "statut_apres": "ready", "session_neuve": True,
        "branche_neuve": False}
    assert carte(noyau, projet["tableau"], servie["carte"]).consecutive_failures == 0
    resservie = executant.carte(("poste-claude",), en_cours={"tableau": servie["tableau"], "carte": servie["carte"],
                                                             "run_id": servie["run_id"]})
    assert resservie["carte"] == servie["carte"] and resservie["reprise"] is False
    assert resservie["consigne"].startswith("## Consigne du propriétaire (relance du ")
    assert "Repars de zéro : le lanceur est réparé." in resservie["consigne"]
    assert resservie["consigne"].endswith(servie["consigne"])  # la consigne d'origine suit, entière


def _integration_bloquee_par_un_conflit(pile, monkeypatch):
    """Carte d'intégration (voie ``poste-integration``, SANS agent) bloquée par un conflit, comme l'exécutant la bloque
    (``Execution._integrer`` : ``CarteRefusee("capacite", "Conflit d'intégration : …")``)."""
    from test_execution_p6 import Executant, _finir_la_synthese, _jusqu_a_l_implementation, _poste_actif

    noyau = pile.noyau
    machine, jeton = _poste_actif(pile)
    executant = Executant(pile, machine, jeton)
    with noyau.base.connexion() as conn:
        projet = lancer_sur_depot(noyau, conn)
    tour = _jusqu_a_l_implementation(pile, executant, projet, monkeypatch)
    executant.terminer(executant.carte(("poste-codex",)), "Implémenté.")
    executant.terminer(executant.carte(("poste-claude",)), "Conforme.", verdict="accepte")
    _finir_la_synthese(pile, projet, tour["synthese"])
    with noyau.base.connexion() as conn:
        noyau.emetteur.passe(conn)
    servie = executant.carte(("poste-integration",))
    assert servie["role"] == "integration"
    reponse = executant.envoyer("bloquer", servie, genre="capacite",
                                raison="Conflit d'intégration : README.md : aucune résolution automatique.")
    assert reponse.status_code == 200, reponse.text
    assert carte(noyau, projet["tableau"], servie["carte"]).status == "blocked"
    return projet, servie


def test_carte_d_integration_relancee_sans_consigne_ni_session(pile_machine, monkeypatch):
    """Relecture finale de P7 (constat scenario-2) : une carte d'intégration n'a pas d'agent ; l'exécutant rejoue la
    même fusion déterministe sans jamais lire de consigne. La file le dit (``integration``) ; une consigne est
    refusée (``consigne_sans_objet`` : rien n'est écrit, la carte reste bloquée) ; la relance sans consigne rejoue la
    fusion, et la réponse ne promet aucune « session neuve »."""
    noyau = pile_machine.noyau
    projet, servie = _integration_bloquee_par_un_conflit(pile_machine, monkeypatch)
    url = f"/api/plugins/acp-poste/v1/cartes/{projet['tableau']}/{servie['carte']}/relancer"
    file = pile_machine.get("/api/plugins/acp-poste/v1/questions").json()
    [arretee] = [b for b in file["bloquees"] if b["carte"] == servie["carte"]]
    assert (arretee["relancable"], arretee["executant"], arretee["integration"]) == (True, True, True)
    with noyau.base.connexion() as conn:
        avant = noyau.projets.demande_de_la_carte(conn, projet["tableau"], servie["carte"])
    refus = pile_machine.post(url, {"consigne": "Garde la version de la branche de l'implémentation."})
    assert refus.status_code == 400, refus.text
    assert refus.json()["detail"]["code"] == "consigne_sans_objet"
    assert "rejoue la même fusion" in refus.json()["detail"]["message"]
    with noyau.base.connexion() as conn:
        assert noyau.projets.demande_de_la_carte(conn, projet["tableau"], servie["carte"]) == avant
    assert carte(noyau, projet["tableau"], servie["carte"]).status == "blocked"
    reponse = pile_machine.post(url, {"consigne": None})
    assert reponse.status_code == 200 and reponse.json() == {
        "carte": servie["carte"], "relancee": True, "statut_apres": "ready", "session_neuve": False,
        "branche_neuve": False}, reponse.text
    file = pile_machine.get("/api/plugins/acp-poste/v1/questions").json()
    assert servie["carte"] not in [b["carte"] for b in file["bloquees"]]  # repartie : elle a quitté la liste


def test_carte_repondre_d_une_question_adressee_ne_se_relance_pas(noyau, conn):
    """Relecture finale de P7 (constat scenario-6) : une carte « répondre » de Hermes bloquée fait escalader sa question
    par le filet de l'émetteur ; relancée, elle ne pouvait plus rien (question_repondre et question_escalader exigent
    une question « ouverte ») : un bouton qui faisait semblant, un tour de modèle perdu, et la même demande comptée deux
    fois dans « À traiter par vous ». Elle est désormais NON relançable, avec la raison, et n'est pas comptée."""
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, projet["tableau"], exploration)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run, texte="Quel nom ?")
    repondre = q["carte_repondre"]
    reclamer(noyau, projet["tableau"], repondre)
    _bloquer(noyau, projet["tableau"], repondre, raison="Hermes n'a pas pu conclure.")
    assert noyau.questions.questions_sans_suite(conn) == [q["question"]]
    file = noyau.questions.file_questions(conn)
    assert [x["etat"] for x in file["questions"]] == ["escaladee"]
    [arretee] = [b for b in file["bloquees"] if b["carte"] == repondre]
    assert arretee["relancable"] is False and arretee["question_adressee"] is True
    assert arretee["refus_relance"] == noyau.textes.REFUS_RELANCE_QUESTION_ADRESSEE
    assert file["compteurs"]["arretees"] == 0 and file["compteurs"]["questions"] == 1
    assert file["compteurs"]["a_traiter"] == 1  # la question, une seule fois
    refus = _refus(noyau, conn, projet, repondre)
    assert refus.code == "question_adressee"
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.get_task(kc, repondre).status == "blocked"  # rien n'a bougé


def test_carte_repondre_d_une_question_encore_ouverte_se_relance(noyau, conn):
    """Témoin : tant que sa question est encore « ouverte » (le filet n'est pas encore passé), la carte « répondre »
    bloquée se relance comme toute carte de Hermes."""
    projet = lancer_sur_depot(noyau, conn)
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, projet["tableau"], exploration)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run, texte="Quel nom ?")
    reclamer(noyau, projet["tableau"], q["carte_repondre"])
    _bloquer(noyau, projet["tableau"], q["carte_repondre"])
    [arretee] = [b for b in noyau.questions.file_questions(conn)["bloquees"] if b["carte"] == q["carte_repondre"]]
    assert arretee["relancable"] is True and arretee["question_adressee"] is False
    assert _relancer(noyau, conn, projet, q["carte_repondre"])["relancee"] is True
