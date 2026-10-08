"""File Questions commune (étape P7, cahier P7 § 3.1, § 3.2, § 3.5 ; correction K6) : les cinq sections de
``GET /v1/questions``, la règle unique ``chez`` (dont une question ouverte SANS carte « répondre », comptée « à vous »,
jamais cachée), le statut de la carte « répondre », les compteurs « À traiter par vous » et « Chez Hermes », la section
des discussions en attente en lecture seule (inconnue → ``null`` et le message, jamais zéro)."""

from __future__ import annotations

from conftest import lancer_sur_depot, reclamer


def _question(noyau, conn, **options):
    projet = lancer_sur_depot(noyau, conn, **options)
    exploration = projet["cartes"]["exploration"]
    run = reclamer(noyau, projet["tableau"], exploration)
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=exploration, run_id=run, texte="Quel nom ?")
    return projet, q


def test_cinq_sections_et_compteurs(noyau, conn):
    projet_h, q_h = _question(noyau, conn, titre="Chez Hermes")
    projet_p, q_p = _question(noyau, conn, titre="Chez moi", reponses="proprietaire")
    # Une décision (triage) et une carte arrêtée, sur un troisième projet.
    projet_d = lancer_sur_depot(noyau, conn, titre="Décisions")
    fiche = noyau.projets.projet(conn, projet_d["id"])
    noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "témoin")
    with noyau.ka.connexion(projet_d["tableau"]) as kc:
        assert noyau.ka.block_task(kc, projet_d["cartes"]["exploration"], kind="needs_input", reason="manque x")
    file = noyau.questions.file_questions(conn)
    assert set(file) == {"questions", "triage", "revues", "bloquees", "tableaux_illisibles", "discussions",
                         "compteurs"}
    chez = {q["id"]: (q["chez"], q["carte_repondre_statut"]) for q in file["questions"]}
    assert chez == {q_h["question"]: ("hermes", "ready"), q_p["question"]: ("proprietaire", None)}
    [arretee] = file["bloquees"]
    assert (arretee["relancable"], arretee["refus_relance"], arretee["executant"]) == (True, None, True)
    assert file["compteurs"] == {"questions": 1, "decisions": 1, "revues": 0, "arretees": 1, "chez_hermes": 1,
                                 "a_traiter": 3}
    assert file["discussions"]["suivies"] is True and file["discussions"]["requetes_ouvertes"] == 0


def test_question_ouverte_sans_carte_repondre_est_a_vous(noyau, conn):
    """K6 : une question ``ouverte`` dont la carte « répondre » n'a jamais été créée n'est pas rattrapée par le filet
    (il ne lit que ``carte_repondre IS NOT NULL``) : elle est comptée « à vous », jamais cachée. Et une question
    escaladée est « à vous » même si sa carte « répondre » existe."""
    projet, q = _question(noyau, conn)
    with noyau.base.transaction(conn):
        conn.execute("UPDATE questions SET carte_repondre = NULL WHERE id = ?", (q["question"],))
    [ligne] = noyau.questions.file_questions(conn)["questions"]
    assert (ligne["etat"], ligne["chez"]) == ("ouverte", "proprietaire")
    assert noyau.questions.questions_sans_suite(conn) == []  # le filet ne la voit pas : la file la montre
    with noyau.base.transaction(conn):
        conn.execute("UPDATE questions SET carte_repondre = ?, etat = 'escaladee' WHERE id = ?",
                     (q["carte_repondre"], q["question"]))
    file = noyau.questions.file_questions(conn)
    assert file["questions"][0]["chez"] == "proprietaire" and file["compteurs"]["questions"] == 1
    assert file["compteurs"]["chez_hermes"] == 0


def test_chez_ne_depend_pas_du_reglage_courant(noyau, conn):
    projet, q = _question(noyau, conn)
    noyau.projets.changer_reponses(conn, projet["id"], reponses="proprietaire", auteur="proprietaire:test")
    [ligne] = noyau.questions.file_questions(conn)["questions"]
    assert ligne["chez"] == "hermes"  # la question ouverte garde son traitement


def test_discussions_inconnues_jamais_zero(noyau, conn, monkeypatch):
    monkeypatch.setattr(noyau.ka, "open_request_count", None)
    assert noyau.questions.discussions_en_attente() == {
        "suivies": False, "requetes_ouvertes": None,
        "message": "Discussions : état inconnu (le tableau de bord ne publie pas le nombre de requêtes ouvertes dans "
                   "cette version de Hermes).",
        "limite": "Les questions posées dans la discussion en terminal (/chat) ne sont visibles que dans cette "
                  "discussion."}

    def en_panne():
        raise RuntimeError("panne")
    monkeypatch.setattr(noyau.ka, "open_request_count", en_panne)
    assert noyau.questions.discussions_en_attente()["requetes_ouvertes"] is None


def test_discussions_comptent_les_requetes_ouvertes_du_processus(noyau):
    """Le compteur est celui de Hermes (``tui_gateway.server_requests``), lu sans rien rattacher : une requête ouverte
    par une session de CE processus est comptée, puis plus du tout quand elle est retirée."""
    from tui_gateway import server_requests

    requete = server_requests.ServerRequest("session-test", "clarify", {"question": "?"})
    with server_requests._lock:  # inscrite comme send() le ferait, sans écrire de trame (aucun client ici)
        server_requests._open[requete.id] = requete
    try:
        assert noyau.questions.discussions_en_attente()["requetes_ouvertes"] == 1
    finally:
        server_requests.cancel("session-test")
    assert noyau.questions.discussions_en_attente()["requetes_ouvertes"] == 0


def test_decision_lue_avant_son_rattachement(noyau, conn):
    """Relecture finale de P7 (constat tests-1, cause réelle de l'échec de ``test_prolonger_au_plafond_puis_conclure``
    en CI 37027816283) : ``cartes.creer`` valide la carte kanban PUIS rattache la demande, dans une autre base ; entre
    les deux, la file lisait la carte de décision sans son genre (``["reprendre"]`` au lieu de « Prolonger » et
    « Conclure »), et le rattachement ne changeait aucune empreinte suivie par la page. La demande est retrouvée par sa
    CLÉ (cartes.py : « reconnue à sa clé même avant le rattachement »), et le rattachement change « projets »."""
    from noyau import flux

    projet = lancer_sur_depot(noyau, conn, titre="Décisions")
    fiche = noyau.projets.projet(conn, projet["id"])
    carte = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "3 tours planifiés")
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET carte = NULL WHERE tableau = ? AND carte = ?", (projet["tableau"], carte))
    fenetre = flux.calculer().valeurs
    [decision] = noyau.questions.lister(conn)["triage"]
    assert (decision["carte"], decision["genre"], decision["actions"]) == (carte, "tours", ["prolonger", "conclure"])
    lu = noyau.questions._carte_en_triage(conn, projet["tableau"], carte)
    assert lu["demande"] is not None and lu["demande"]["ref"] == "plafond-tours"
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET carte = ? WHERE tableau = ? AND ref = 'plafond-tours'",
                     (carte, projet["tableau"]))
    assert flux.calculer().valeurs["projets"] != fenetre["projets"]
