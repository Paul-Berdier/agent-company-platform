"""Exécution par l'exécutant (étape P6, cahier P6 § 5, § 14.2) : routes machine servies par un VRAI serveur, derrière
la VRAIE couture par jeton de Hermes, contre de vrais tableaux kanban. Un faux exécutant (requêtes du contrat
partagé) réclame, bat, termine, pose des questions, bloque, rend et s'arrête ; chaque effet est relu dans la base du
tableau (claim_lock, claim_expires, runs, événements) et dans celle du greffon."""

from __future__ import annotations

import json
import time
import uuid

import pytest

from conftest import carte, cartes_du_tableau, en_worker, lancer_sur_depot, outil

from acp_poste_contrat import machine as contrat  # noqa: E402

M = "/api/plugins/acp-poste/machine/v1"
PLAN = {"resume": "Une étape.", "etapes": [
    {"ref": "e1", "titre": "Écrire", "classe": "implementation", "consigne": "Écrire outil.py.", "voie": "poste-codex"}]}


def _poste_actif(pile):
    with pile.noyau.base.connexion() as conn:
        code = pile.noyau.machines.creer_code(conn, "proprietaire:test")["code"]
    corps = {"protocole": "acp-machine/1", "version_poste": "1.0.0", "nom": "Exécutant Railway"}
    reponse = pile.post(f"{M}/enrolement", corps, jeton=code).json()
    with pile.noyau.base.connexion() as conn:
        pile.noyau.machines.confirmer(conn, reponse["machine_id"], reponse["empreinte"], "proprietaire:test")
    return reponse["machine_id"], reponse["jeton"]


class Executant:
    """Faux exécutant : construit ses requêtes à la forme du contrat et valide chaque réponse 200 par lui."""

    def __init__(self, pile, machine: str, jeton: str) -> None:
        self.pile, self.machine, self.jeton = pile, machine, jeton

    def reclamer(self, voies=("poste-claude",), *, en_cours=None, peut_executer=True, attente=5):
        corps = {"protocole": "acp-machine/1", "version_poste": "1.0.0", "peut_executer": peut_executer,
                 "ordres_acquittes": [], "attente_max_s": attente, "politique_valide": True,
                 "voies_disponibles": list(voies) if peut_executer else [], "carte_en_cours": en_cours,
                 "espace_libre_mio": 3120}
        reponse = self.pile.post(f"{M}/reclamer", corps, jeton=self.jeton)
        assert reponse.status_code == 200, reponse.text
        return contrat.ReponseReclamer.model_validate(reponse.json())

    def carte(self, voies=("poste-claude",), **options) -> dict:
        reponse = self.reclamer(voies, **options)
        assert reponse.carte is not None, "aucune carte servie"
        return reponse.carte.model_dump(mode="json")

    def envoyer(self, route: str, carte: dict, *, id_envoi=None, run_id=None, **champs):
        corps = {"id_envoi": id_envoi or str(uuid.uuid4()), "tableau": carte["tableau"], "carte": carte["carte"],
                 "run_id": run_id or carte["run_id"], **champs}
        return self.pile.post(f"{M}/{route}", corps, jeton=self.jeton)

    def terminer(self, carte: dict, resume="Fait : outil.py écrit, 4 tests.", *, verdict=None, corrections=None,
                 pilotage=None, **options):
        meta = metadonnees(carte, pilotage=pilotage)
        return self.envoyer("terminer", carte, issue="termine", resume=resume, verdict=verdict,
                            corrections=corrections, metadonnees=meta, **options)


def metadonnees(carte: dict, *, pilotage=None) -> dict:
    return {"modele_demande": carte["modele"], "modele_servi": "factice-servi-1", "effort": carte["effort"],
            "palier_demande": carte["palier"], "palier_servi": None, "jetons": {"entree": 10, "sortie": 5, "cache": 0},
            "branche": carte["branche"], "base": "1" * 40, "tete": "2" * 40,
            "diffstat": {"fichiers": 1, "ajouts": 12, "retraits": 0},
            "verification": {"etat": "reussie", "code": 0, "duree_s": 3, "tentatives": 1, "raison": None},
            "pilotage": pilotage or {"touche": False, "chemins": []}, "regime": "B", "session_locale": True}


@pytest.fixture
def executant(pile_machine):
    machine, jeton = _poste_actif(pile_machine)
    return Executant(pile_machine, machine, jeton)


@pytest.fixture
def projet(pile_machine):
    with pile_machine.noyau.base.connexion() as conn:
        return lancer_sur_depot(pile_machine.noyau, conn)


def _tache(pile, tableau, identifiant):
    return carte(pile.noyau, tableau, identifiant)


def _demande(pile, tableau, identifiant):
    with pile.noyau.base.connexion() as conn:
        return pile.noyau.projets.demande_de_la_carte(conn, tableau, identifiant)


def _evenements(pile, tableau, identifiant):
    with pile.noyau.ka.connexion(tableau) as kc:
        return [(e.kind, e.payload) for e in pile.noyau.ka.list_events(kc, identifiant)]


def _jusqu_a_l_implementation(pile, executant, projet, monkeypatch):
    """Exploration servie et terminée par l'exécutant, puis tour 1 planifié (implémentation Codex, relecture
    Claude) : rend le tour."""
    exploration = executant.carte(("poste-claude",))
    assert executant.terminer(exploration, "## Structure\nUn paquet.").json()["etat"] == "done"
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(pile.noyau, "projet_planifier", PLAN)
    assert tour["ok"], tour
    return tour


# ------------------------------------------------------------------ reclamer sert une carte


def test_reclamer_peut_executer_faux_jamais_de_carte(pile_machine, executant, projet):
    """Un poste P5 (peut_executer: false) ne reçoit jamais de carte, même prête et de sa voie ; un poste qui annonce
    une voie SANS pouvoir exécuter est refusé par le contrat (422), rien n'est réclamé."""
    reponse = executant.reclamer(peut_executer=False)
    assert reponse.carte is None
    assert _tache(pile_machine, projet["tableau"], projet["cartes"]["exploration"]).status == "ready"
    # Aucune voie annoncée : rien non plus.
    assert executant.reclamer(voies=()).carte is None
    incoherent = {"protocole": "acp-machine/1", "version_poste": "1.0.0", "peut_executer": False,
                  "ordres_acquittes": [], "attente_max_s": 5, "politique_valide": True,
                  "voies_disponibles": ["poste-claude"]}
    reponse = pile_machine.post(f"{M}/reclamer", incoherent, jeton=executant.jeton)
    assert reponse.status_code == 422, reponse.text
    assert "un poste qui ne peut pas exécuter n'annonce aucune voie" in reponse.json()["detail"]["message"]
    assert _tache(pile_machine, projet["tableau"], projet["cartes"]["exploration"]).status == "ready"


def test_reclamer_sert_seulement_les_cartes_emises(pile_machine, executant, projet):
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        etrangere = pile_machine.noyau.ka.create_task(kc, title="Carte forgée", assignee="poste-claude",
                                                      created_by="hermes", priority=100, board=projet["tableau"])
    servie = executant.carte(("poste-claude",))
    assert servie["carte"] == projet["cartes"]["exploration"] and servie["role"] == "exploration"
    assert _tache(pile_machine, projet["tableau"], etrangere).status == "ready"  # jamais réclamée
    assert _tache(pile_machine, projet["tableau"], etrangere).claim_lock is None


def test_claim_ttl_2700_claimer_stable(pile_machine, executant, projet):
    avant = int(time.time())
    servie = executant.carte()
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.status == "running" and tache.claim_lock == f"acp-poste:{executant.machine}"
    assert avant + 2700 <= tache.claim_expires <= int(time.time()) + 2700
    assert tache.current_run_id == servie["run_id"] and tache.worker_pid is None
    demande = _demande(pile_machine, projet["tableau"], servie["carte"])
    assert demande["machine_id"] == executant.machine and demande["reclamee_le"]


def test_carte_servie_conforme(pile_machine, executant, projet):
    servie = executant.carte()
    contrat.DemandeCarte.model_validate(servie)
    assert servie["branche"] == f"hermes/{servie['carte']}" and servie["branche_base"] is None
    assert (servie["voie"], servie["modele"], servie["effort"], servie["palier"]) == (
        "poste-claude", "factice-claude-1", "low", "default")
    assert servie["reprise"] is False and servie["reponses"] == [] and servie["ttl_s"] == 2700
    assert servie["projet_id"] == projet["id"] and servie["depot_alias"] == "jetable"


def test_une_carte_a_la_fois(pile_machine, executant, projet, monkeypatch):
    """Concurrence 1 : tant que l'exécutant annonce une carte en main, rien d'autre ne lui est servi, même une carte
    prête d'un autre projet."""
    tour = _jusqu_a_l_implementation(pile_machine, executant, projet, monkeypatch)
    impl = executant.carte(("poste-codex", "poste-claude"))
    with pile_machine.noyau.base.connexion() as conn:
        autre = lancer_sur_depot(pile_machine.noyau, conn, titre="Autre projet")
    assert _tache(pile_machine, autre["tableau"], autre["cartes"]["exploration"]).status == "ready"
    en_main = {"tableau": impl["tableau"], "carte": impl["carte"], "run_id": impl["run_id"]}
    assert executant.reclamer(("poste-codex", "poste-claude"), en_cours=en_main).carte is None
    assert _tache(pile_machine, autre["tableau"], autre["cartes"]["exploration"]).status == "ready"
    # Sans carte en main, l'autre projet est servi : la concurrence 1 est bien ce qui l'empêchait.
    assert executant.carte(("poste-claude",))["carte"] == autre["cartes"]["exploration"]
    del tour


# ------------------------------------------------------------------ battement


def test_battement_prolonge(pile_machine, executant, projet):
    servie = executant.carte()
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        kc.execute("UPDATE tasks SET claim_expires = ? WHERE id = ?", (int(time.time()) + 60, servie["carte"]))
    reponse = executant.envoyer("battement", servie, note="Tests : 41 réussis ; correction en cours.")
    assert reponse.status_code == 200
    assert contrat.ReponseBattement.model_validate(reponse.json()).model_dump() == {
        "valide": True, "pause": False, "annuler": False}
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.claim_expires >= int(time.time()) + 2690 and tache.last_heartbeat_at
    notes = [p for k, p in _evenements(pile_machine, projet["tableau"], servie["carte"]) if k == "heartbeat"]
    assert notes == [{"note": "Tests : 41 réussis ; correction en cours."}]
    with pile_machine.noyau.base.connexion() as conn:
        source = conn.execute("SELECT source FROM presence WHERE machine_id = ?", (executant.machine,)).fetchone()[0]
    assert source == "battement"


def test_battement_invalide_apres_reprise(pile_machine, executant, projet):
    servie = executant.carte()
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        assert pile_machine.noyau.ka.reclaim_task(kc, servie["carte"], reason="test")
    reponse = executant.envoyer("battement", servie, note="Toujours là.")
    assert reponse.status_code == 200 and reponse.json()["valide"] is False
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "ready"


def test_battement_annule_si_projet_en_pause(pile_machine, executant, projet):
    servie = executant.carte()
    with pile_machine.noyau.base.connexion() as conn:
        pile_machine.noyau.projets.mettre_en_pause(conn, projet["id"], auteur="proprietaire:test")
    reponse = executant.envoyer("battement", servie, note="Étape 2.")
    assert reponse.json() == {"valide": True, "pause": False, "annuler": True}


# ------------------------------------------------------------------ terminer


def test_terminer_complete(pile_machine, executant, projet):
    servie = executant.carte()
    reponse = executant.terminer(servie, "## Structure\nUn paquet Python.")
    assert reponse.status_code == 200 and reponse.json() == {"etat": "done", "deja_recu": False}
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.status == "done" and tache.claim_lock is None
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        assert pile_machine.noyau.ka.latest_summaries(kc, [servie["carte"]])[servie["carte"]].startswith("## Structure")
    demande = _demande(pile_machine, projet["tableau"], servie["carte"])
    assert (demande["modele_servi"], demande["issue"], demande["tete"]) == ("factice-servi-1", "termine", "2" * 40)
    assert json.loads(demande["verification"])["etat"] == "reussie"
    # Résolution observée (D59) : visible sur la page Routage, jamais supposée.
    resolutions = pile_machine.get("/api/plugins/acp-poste/v1/routage").json()["resolutions_observees"]
    assert [(r["voie"], r["alias"], r["modele_servi"]) for r in resolutions] == [
        ("poste-claude", "factice-claude-1", "factice-servi-1")]
    # La planification (Hermes) est désormais prête : la fin de l'exploration l'a libérée.
    assert _tache(pile_machine, projet["tableau"], projet["cartes"]["planification"]).status == "ready"


def test_terminer_idempotent(pile_machine, executant, projet):
    servie = executant.carte()
    identifiant = str(uuid.uuid4())
    premiere = executant.terminer(servie, id_envoi=identifiant)
    seconde = executant.terminer(servie, id_envoi=identifiant)
    assert premiere.json() == {"etat": "done", "deja_recu": False}
    assert seconde.status_code == 200 and seconde.json() == {"etat": "done", "deja_recu": True}
    fins = [k for k, _p in _evenements(pile_machine, projet["tableau"], servie["carte"]) if k == "completed"]
    assert fins == ["completed"]
    # Le même identifiant pour un AUTRE corps est refusé, sans effet.
    autre = executant.terminer(servie, "Autre résumé.", id_envoi=identifiant)
    assert autre.status_code == 422 and autre.json()["detail"]["code"] == "requete_refusee"
    assert "identifiant d'envoi déjà employé" in autre.json()["detail"]["message"]


def test_reclamation_perdue_409_sans_effet(pile_machine, executant, projet):
    servie = executant.carte()
    reponse = executant.terminer(servie, run_id=servie["run_id"] + 7)
    assert reponse.status_code == 409 and reponse.json()["detail"] == {"code": "reclamation_perdue", "message": (
        f"La carte {servie['carte']} (run {servie['run_id'] + 7}) n'est plus réclamée par cet exécutant : rien n'a été "
        "écrit dans ACP ; le travail reste sur la branche locale.")}
    contrat.ErreurMachine.model_validate(reponse.json())
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "running"
    with pile_machine.noyau.base.connexion() as conn:
        assert conn.execute("SELECT COUNT(*) FROM envois").fetchone()[0] == 0


def test_secret_detecte_422_rien_ecrit(pile_machine, executant, projet):
    servie = executant.carte()
    faux = "sk-ant-" + "x" * 32
    reponse = executant.terminer(servie, f"J'ai trouvé {faux} dans le dépôt.")
    assert reponse.status_code == 422 and reponse.json()["detail"] == {"code": "secret_detecte", "message": (
        "Envoi refusé : la requête contient un secret (motif clé d'API Anthropic) ; rien n'a été enregistré.")}
    assert faux not in reponse.text
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "running"
    assert _demande(pile_machine, projet["tableau"], servie["carte"])["issue"] is None


def test_terminer_hors_contrat_issue_invalide(pile_machine, executant, projet):
    servie = executant.carte()
    reponse = executant.terminer(servie, "   ")
    assert reponse.status_code == 422 and reponse.json()["detail"]["code"] == "issue_invalide"
    assert reponse.json()["detail"]["message"] == ("Issue refusée par le contrat : champ « resume » (« resume » ne peut "
                                                    "pas être vide).")
    verdict = executant.terminer(servie, verdict="accepte")
    assert verdict.status_code == 422 and "un verdict ne se rend que pour une carte de relecture" in verdict.text


def test_carte_inconnue_404_et_non_emise_403(pile_machine, executant, projet):
    servie = executant.carte()
    inconnue = dict(servie, carte="t_00000000")
    reponse = executant.envoyer("battement", inconnue, note="x")
    assert reponse.status_code == 404 and reponse.json()["detail"]["code"] == "carte_inconnue"
    planif = dict(servie, carte=projet["cartes"]["planification"])  # carte Hermes : jamais servie au poste
    reponse = executant.envoyer("battement", planif, note="x")
    assert reponse.status_code == 403 and reponse.json()["detail"] == {"code": "carte_non_emise", "message": (
        f"Carte {projet['cartes']['planification']} refusée : elle n'a pas été émise par ACP.")}


# ------------------------------------------------------------------ revue des fichiers de pilotage


def _vers_la_revue(pile, executant, projet):
    servie = executant.carte()
    pilotage = {"touche": True, "chemins": [".github/workflows/ci.yml", "CLAUDE.md"]}
    reponse = executant.terminer(servie, "Ajout d'un contrôle de CI.", pilotage=pilotage)
    assert reponse.json() == {"etat": "review", "deja_recu": False}
    return servie


def test_terminer_pilotage_en_revue(pile_machine, executant, projet):
    servie = _vers_la_revue(pile_machine, executant, projet)
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "review"
    revues = pile_machine.get("/api/plugins/acp-poste/v1/questions").json()["revues"]
    assert [(r["carte"], r["chemins"]) for r in revues] == [(servie["carte"], [".github/workflows/ci.yml", "CLAUDE.md"])]
    assert revues[0]["diff"].startswith("Le diff reste sur l'exécutant")
    with pile_machine.noyau.base.connexion() as conn:
        pile_machine.noyau.emetteur.passe(conn)
        genres = [l[0] for l in conn.execute("SELECT genre FROM notifications")]
    assert "revue" in genres


def test_revue_accepter(pile_machine, executant, projet):
    servie = _vers_la_revue(pile_machine, executant, projet)
    url = f"/api/plugins/acp-poste/v1/revues/{projet['tableau']}/{servie['carte']}/accepter"
    reponse = pile_machine.post(url, {})
    assert reponse.status_code == 200 and reponse.json() == {"carte": servie["carte"], "etat": "done"}
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        resume = pile_machine.noyau.ka.latest_summaries(kc, [servie["carte"]])[servie["carte"]]
    assert resume.startswith("Ajout d'un contrôle de CI.") and "acceptée par le propriétaire" in resume
    # Une seconde fois : la carte n'est plus en revue.
    assert pile_machine.post(url, {}).status_code == 404


def test_revue_refuser_rouvre_avec_le_motif(pile_machine, executant, projet):
    servie = _vers_la_revue(pile_machine, executant, projet)
    url = f"/api/plugins/acp-poste/v1/revues/{projet['tableau']}/{servie['carte']}/refuser"
    assert pile_machine.post(url, {}).status_code == 422  # motif exigé
    reponse = pile_machine.post(url, {"motif": "Ne touche pas au workflow de CI."})
    assert reponse.status_code == 200 and reponse.json()["etat"] == "ready"
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.status == "ready" and tache.assignee == "poste-claude"
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        commentaires = [c.body for c in pile_machine.noyau.ka.list_comments(kc, servie["carte"])]
    assert commentaires == ["Revue des fichiers de pilotage refusée par le propriétaire : Ne touche pas au workflow de CI."]
    resservie = executant.carte()
    assert resservie["carte"] == servie["carte"] and resservie["reprise"] is True
    assert [(r["genre"], r["repondu_par"]) for r in resservie["reponses"]] == [("refus_revue", "proprietaire")]
    assert resservie["reponses"][0]["texte"] == ("Le propriétaire a refusé la modification des fichiers de pilotage : "
                                                  "Ne touche pas au workflow de CI. Retire-la.")
    # Livré au premier battement : il n'est plus resservi ensuite.
    executant.envoyer("battement", resservie, note="Reprise.")
    assert _demande(pile_machine, projet["tableau"], servie["carte"])["refus_livre_le"]


def test_block_task_sur_revue_sans_effet(pile_machine, executant, projet):
    """Témoin de la raison du choix (cahier P6 § 5.4) : block_task est SANS EFFET sur une carte en revue (son UPDATE
    exige running ou ready) ; « Refuser » qui l'appellerait serait un bouton qui fait semblant."""
    servie = _vers_la_revue(pile_machine, executant, projet)
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        assert pile_machine.noyau.ka.block_task(kc, servie["carte"], kind="needs_input", reason="refus") is False
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "review"


# ------------------------------------------------------------------ relecture et corrections


def test_terminer_corrections_dans_l_ordre(pile_machine, executant, projet, monkeypatch):
    """Preuve P6 du plan d'autonomie : la synthèse n'est jamais prête entre la fin de la relecture et la correction."""
    tour = _jusqu_a_l_implementation(pile_machine, executant, projet, monkeypatch)
    impl = executant.carte(("poste-codex",))
    assert impl["role"] == "implementation" and impl["voie"] == "poste-codex"
    assert executant.terminer(impl, "Implémenté.").json()["etat"] == "done"
    relecture = executant.carte(("poste-claude",))
    assert relecture["role"] == "relecture" and relecture["carte_relue"] == impl["carte"]
    assert relecture["branche_depart"] is None and relecture["parents"][0]["branche"] == f"hermes/{impl['carte']}"
    reponse = executant.terminer(relecture, "Il manque la gestion des erreurs.", verdict="corrections",
                                 corrections="Gérer les fichiers absents.")
    assert reponse.json() == {"etat": "correction_creee", "deja_recu": False}
    toutes = cartes_du_tableau(pile_machine.noyau, projet["tableau"])
    assert toutes[relecture["carte"]].status == "done"
    assert toutes[tour["synthese"]].status == "todo"
    correction = executant.carte(("poste-codex",))
    assert correction["role"] == "correction" and correction["correction_n"] == 1
    assert correction["branche_depart"] == f"hermes/{impl['carte']}"
    assert "Gérer les fichiers absents." in correction["consigne"]


def test_relecture_acceptee(pile_machine, executant, projet, monkeypatch):
    tour = _jusqu_a_l_implementation(pile_machine, executant, projet, monkeypatch)
    impl = executant.carte(("poste-codex",))
    executant.terminer(impl, "Implémenté.")
    relecture = executant.carte(("poste-claude",))
    assert executant.terminer(relecture, "Conforme.", verdict="accepte").json()["etat"] == "done"
    assert _tache(pile_machine, projet["tableau"], tour["synthese"]).status == "ready"
    relue = executant.terminer(relecture, "Encore.", verdict="accepte")
    assert relue.status_code == 409  # la relecture n'est plus à l'exécutant


# ------------------------------------------------------------------ questions


def test_deux_questions_sans_triage(pile_machine, executant, projet):
    servie = executant.carte()
    premiere = executant.envoyer("question", servie, texte="Garder Python 3.10 ?", contexte="requires-python >= 3.10")
    assert premiere.status_code == 200
    corps = contrat.ReponseQuestion.model_validate(premiere.json())
    assert corps.etat == "ouverte" and corps.carte_repondre
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "scheduled"
    reponse = pile_machine.post(f"/api/plugins/acp-poste/v1/questions/{corps.question}/reponse", {"reponse": "Oui."})
    assert reponse.status_code == 200
    resservie = executant.carte()
    assert resservie["carte"] == servie["carte"] and resservie["reprise"] is True
    assert [(r["question"], r["texte"]) for r in resservie["reponses"]] == [(corps.question, "Oui.")]
    executant.envoyer("battement", resservie, note="Reprise.")
    seconde = executant.envoyer("question", resservie, texte="Et la 3.9 ?")
    assert seconde.status_code == 200 and seconde.json()["question"] != corps.question
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.status == "scheduled"  # jamais en triage : schedule_task n'est pas un blocage
    with pile_machine.noyau.base.connexion() as conn:
        livree = conn.execute("SELECT livree_le FROM questions WHERE id = ?", (corps.question,)).fetchone()[0]
    assert livree  # la première réponse est livrée une seule fois


# ------------------------------------------------------------------ blocages


def test_bloquer_capacite_deux_fois_triage(pile_machine, executant, projet):
    servie = executant.carte()
    premiere = executant.envoyer("bloquer", servie, genre="capacite", raison="Modèle servi différent de l'alias.")
    assert premiere.json() == {"etat": "bloquee", "deja_recu": False}
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        assert pile_machine.noyau.ka.unblock_task(kc, servie["carte"])
    resservie = executant.carte()
    seconde = executant.envoyer("bloquer", resservie, genre="memoire", raison="Deux arrêts OOM (code 137).")
    assert seconde.json() == {"etat": "triage", "deja_recu": False}  # même kind (capability) : triage


def test_bloquer_quota_debloque_a_l_heure(pile_machine, executant, projet):
    servie = executant.carte()
    reprise = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 120))
    reponse = executant.envoyer("bloquer", servie, genre="quota", raison="Limite atteinte.", reprise_le=reprise)
    assert reponse.json() == {"etat": "planifiee", "deja_recu": False}
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "scheduled"
    noyau = pile_machine.noyau
    with noyau.base.connexion() as conn:
        assert noyau.attentes.debloquer(conn) == []  # pas encore l'heure
        debut = noyau.base.maintenant()
        noyau.base.fixer_horloge(lambda: debut + 121)
        try:
            assert noyau.attentes.debloquer(conn) == [f"{projet['tableau']}/{servie['carte']}"]
        finally:
            noyau.base.fixer_horloge(None)
        assert conn.execute("SELECT COUNT(*) FROM attentes").fetchone()[0] == 0
    assert _tache(pile_machine, projet["tableau"], servie["carte"]).status == "ready"
    assert executant.carte()["reprise"] is True


def test_bloquer_secret_reste_bloquee(pile_machine, executant, projet):
    servie = executant.carte()
    reponse = executant.envoyer("bloquer", servie, genre="secret", raison="Motif trouvé dans le diff.")
    assert reponse.json() == {"etat": "bloquee", "deja_recu": False}
    bloques = [p for k, p in _evenements(pile_machine, projet["tableau"], servie["carte"]) if k == "blocked"]
    assert bloques[-1]["kind"] == "needs_input" and bloques[-1]["reason"] == (
        "Secret détecté dans la production de l'exécutant : rien n'a été envoyé ; la branche locale est gardée pour "
        "examen.")
    with pile_machine.noyau.base.connexion() as conn:
        pile_machine.noyau.emetteur.passe(conn)
        assert [l[0] for l in conn.execute("SELECT genre FROM notifications WHERE genre IN ('secret', 'bloquee')")] == [
            "secret"]


def test_bloquer_secret_deux_fois_triage(pile_machine, executant, projet):
    """Correction de la contre-vérification : needs_input compte les récurrences ; le second blocage après votre
    déblocage envoie la carte en triage. Les deux issues demandent votre geste."""
    servie = executant.carte()
    executant.envoyer("bloquer", servie, genre="secret", raison="Premier.")
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        assert pile_machine.noyau.ka.unblock_task(kc, servie["carte"])
    resservie = executant.carte()
    assert executant.envoyer("bloquer", resservie, genre="secret", raison="Second.").json()["etat"] == "triage"


# ------------------------------------------------------------------ reprendre et arret


def test_reprendre_avant_ttl_compteur_zero(pile_machine, executant, projet):
    servie = executant.carte()
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        kc.execute("UPDATE tasks SET consecutive_failures = 2 WHERE id = ?", (servie["carte"],))
    reponse = executant.envoyer("reprendre", servie, motif="redemarrage")
    assert reponse.json() == {"etat": "rendue", "deja_recu": False}
    tache = _tache(pile_machine, projet["tableau"], servie["carte"])
    assert tache.status == "ready" and tache.consecutive_failures == 0 and tache.claim_lock is None
    en_main = {"tableau": servie["tableau"], "carte": servie["carte"], "run_id": servie["run_id"]}
    resservie = executant.carte(en_cours=en_main)
    assert resservie["carte"] == servie["carte"] and resservie["reprise"] is True
    assert resservie["run_id"] != servie["run_id"]


def test_reprendre_apres_ttl_deja_libre(pile_machine, executant, projet):
    servie = executant.carte()
    with pile_machine.noyau.ka.connexion(projet["tableau"]) as kc:
        kc.execute("UPDATE tasks SET claim_expires = ? WHERE id = ?", (int(time.time()) - 5, servie["carte"]))
        from hermes_cli.kanban_db import release_stale_claims

        assert release_stale_claims(kc) == 1  # le TTL expiré : Hermes reprend la carte et compte un échec
    for route, motif in (("reprendre", "reclamation_perdue"), ("arret", "sigterm")):
        reponse = executant.envoyer(route, servie, motif=motif)
        assert reponse.status_code == 200 and reponse.json() == {"etat": "deja_libre", "deja_recu": False}


def test_reprendre_sans_pid_ne_tue_rien(pile_machine, executant, projet):
    """Réclamation distante : worker_pid nul et verrou hors du préfixe d'hôte de Hermes ; reclaim_task ne vise
    aucun processus (kanban_db_dispatch.py:463-466)."""
    servie = executant.carte()
    executant.envoyer("reprendre", servie, motif="redemarrage")
    repris = [p for k, p in _evenements(pile_machine, projet["tableau"], servie["carte"]) if k == "reclaimed"]
    assert repris and repris[-1]["host_local"] is False and repris[-1]["termination_attempted"] is False
    assert repris[-1]["prev_pid"] is None and repris[-1]["prev_lock"] == f"acp-poste:{executant.machine}"


def test_arret_grace_hors_ligne(pile_machine, executant, projet):
    servie = executant.carte()
    assert executant.envoyer("arret", servie, motif="sigterm").json() == {"etat": "rendue", "deja_recu": False}
    noyau = pile_machine.noyau
    with noyau.base.connexion() as conn:
        conn.execute("UPDATE machines SET hote = 'railway', plateforme = 'linux' WHERE id = ?", (executant.machine,))
        debut = noyau.base.maintenant()
        noyau.presence.DEMARRAGE_DU_PROCESSUS = 0
        noyau.base.ecrire_emetteur(conn, "demarrage_tableau_de_bord", 0)
        noyau.base.fixer_horloge(lambda: debut + 300)  # au-delà du seuil de 180 s, dans la grâce de 600 s
        try:
            assert noyau.presence.evaluer(conn) == []
            assert noyau.presence.etat_poste(conn)["etat"] == "redeploiement"
            noyau.base.fixer_horloge(lambda: debut + 700)
            assert noyau.presence.evaluer(conn) == [executant.machine]
        finally:
            noyau.base.fixer_horloge(None)
        texte = conn.execute("SELECT texte FROM notifications WHERE genre = 'hors_ligne'").fetchone()[0]
    assert texte.startswith("ACP — Exécutant Railway hors ligne depuis")


def test_carte_tient_dans_64_kio(pile_machine, executant, projet, monkeypatch):
    """Résumés des parents ÉNORMES : la carte servie est réduite (résumés tronqués, et dit) et tient dans 60 Kio."""
    exploration = executant.carte(("poste-claude",))
    executant.terminer(exploration, "é" * 4000)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    plan = {"resume": "Une étape.", "etapes": [{"ref": "e1", "titre": "Écrire", "classe": "implementation",
                                                "consigne": "ü" * 8000, "voie": "poste-codex"}]}
    assert outil(pile_machine.noyau, "projet_planifier", plan)["ok"]
    reponse = executant.reclamer(("poste-codex",))
    assert reponse.carte is not None
    corps = json.dumps(reponse.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    assert len(corps) <= contrat.TAILLE_MAX_REPONSE


GRAND = "\U0001d54f"  # 4 octets en UTF-8 : le pire cas pour la taille du JSON servi


def _implementation_planifiee(pile, executant, projet, monkeypatch, consigne="Écrire outil.py."):
    exploration = executant.carte(("poste-claude",))
    executant.terminer(exploration, "Exploré.")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    plan = {"resume": "Une étape.", "etapes": [{"ref": "e1", "titre": "Écrire", "classe": "implementation",
                                                "consigne": consigne, "voie": "poste-codex"}]}
    assert outil(pile.noyau, "projet_planifier", plan)["ok"]
    with pile.noyau.base.connexion() as conn:
        return conn.execute("SELECT carte FROM demandes WHERE tableau = ? AND role = 'implementation'",
                            (projet["tableau"],)).fetchone()["carte"]


def test_carte_resumes_des_parents_reduits_sous_60_kio(pile_machine, executant, projet, monkeypatch):
    """Douze parents aux résumés de 2 000 caractères de 4 octets (96 Kio) : la carte est SERVIE (jamais bloquée),
    résumés réduits et marqués tronqués, et tient dans 60 Kio ; la consigne, elle, reste entière."""
    import meta

    servie_par_les_routes = meta.sous_module_noyau("execution")  # la copie du noyau que les routes appellent
    _implementation_planifiee(pile_machine, executant, projet, monkeypatch, consigne="ü" * 8000)

    def gonfles(conn, kc, fiche, carte_id):
        return [{"carte": f"t_{rang + 1:04x}abcd", "role": "exploration", "resume": GRAND * contrat.RESUME_PARENT_MAX,
                 "tronque": False, "branche": None, "_cree_le": rang} for rang in range(contrat.PARENTS_MAX)]

    monkeypatch.setattr(servie_par_les_routes, "_parents", gonfles)
    servie = executant.reclamer(("poste-codex",)).carte
    assert servie is not None, "carte bloquée au lieu d'être réduite"
    assert contrat.taille_json(servie.model_dump(mode="json")) <= contrat.TAILLE_MAX_CARTE
    assert len(servie.parents) == contrat.PARENTS_MAX
    assert all(p.tronque and (p.resume is None or len(p.resume) <= 1000) for p in servie.parents)
    assert servie.consigne == "ü" * 8000 and servie.consigne_tronquee is False


def test_carte_consigne_tronquee_et_dite_sous_60_kio(pile_machine, executant, projet, monkeypatch):
    """Consigne de 16 000 caractères de 4 octets (64 Kio, une correction démesurée) : servie tronquée AVEC la mention,
    jamais en silence, et la carte tient dans 60 Kio."""
    noyau = pile_machine.noyau
    impl = _implementation_planifiee(pile_machine, executant, projet, monkeypatch)
    with noyau.base.connexion() as conn:
        conn.execute("UPDATE demandes SET consigne = ? WHERE tableau = ? AND carte = ?",
                     (GRAND * contrat.CONSIGNE_MAX, projet["tableau"], impl))
    servie = executant.reclamer(("poste-codex",)).carte
    assert servie is not None and servie.carte == impl, "carte bloquée au lieu d'être tronquée"
    assert contrat.taille_json(servie.model_dump(mode="json")) <= contrat.TAILLE_MAX_CARTE
    assert servie.consigne_tronquee is True
    assert servie.consigne.startswith(GRAND * 200) and servie.consigne.endswith(noyau.textes.MENTION_TRONQUE)


# ------------------------------------------------------------------ intégration (cahier P6 § 6.7)


def _finir_la_synthese(pile, projet, synthese):
    """La planification puis la synthèse (cartes Hermes) terminées comme le ferait le worker de Hermes."""
    with pile.noyau.ka.connexion(projet["tableau"]) as kc:
        for identifiant in (projet["cartes"]["planification"], synthese):
            tache = pile.noyau.ka.claim_task(kc, identifiant, ttl_seconds=600, claimer="test:hermes")
            assert tache is not None, identifiant
            assert pile.noyau.ka.complete_task(kc, identifiant, summary="Fait.", expected_run_id=tache.current_run_id)


def test_integration_servie_sur_poste_integration(pile_machine, executant, projet, monkeypatch):
    noyau = pile_machine.noyau
    tour = _jusqu_a_l_implementation(pile_machine, executant, projet, monkeypatch)
    impl = executant.carte(("poste-codex",))
    executant.terminer(impl, "Implémenté.")
    relecture = executant.carte(("poste-claude",))
    executant.terminer(relecture, "Conforme.", verdict="accepte")
    _finir_la_synthese(pile_machine, projet, tour["synthese"])
    with noyau.base.connexion() as conn:
        noyau.emetteur.passe(conn)
        assert noyau.projets.projet(conn, projet["id"])["etat"] == "actif"  # attend l'intégration
        integration = conn.execute("SELECT * FROM demandes WHERE projet_id = ? AND role = 'integration'",
                                   (projet["id"],)).fetchone()
    assert integration is not None and integration["voie"] == "poste-integration" and integration["modele"] is None
    assert executant.reclamer(("poste-codex", "poste-claude")).carte is None  # jamais servie hors de sa voie
    servie = executant.carte(("poste-integration",))
    assert servie["role"] == "integration" and servie["voie"] == "poste-integration"
    assert (servie["modele"], servie["effort"], servie["palier"]) == (None, None, None)
    assert servie["branches_a_integrer"] == [f"hermes/{impl['carte']}"]
    assert servie["branche"] == "hermes/projet-" + projet["tableau"].removeprefix("acp-")
    assert executant.terminer(servie, "Branche intégrée, vérification réussie.").json()["etat"] == "done"
    with noyau.base.connexion() as conn:
        noyau.emetteur.passe(conn)
        assert noyau.projets.projet(conn, projet["id"])["etat"] == "termine"
        texte = conn.execute("SELECT texte FROM notifications WHERE genre = 'integration'").fetchone()[0]
    assert f"branche {servie['branche']} prête sur l'exécutant" in texte
    poste = pile_machine.get("/api/plugins/acp-poste/v1/poste").json()["executant"]
    assert [(b["branche"], b["tete"]) for b in poste["branches_pretes"]] == [(servie["branche"], "2" * 40)]
    assert poste["branches_pretes"][0]["commande"] == (
        f"railway ssh -i <clé dédiée> --service executant -- acp-poste bundle jetable {servie['branche']}")


def test_projet_simule_sans_branche_rapportee_termine_sans_integration(pile_machine, projet, monkeypatch):
    """Non-régression P4 : des cartes du poste terminées hors de l'exécutant (aucune branche rapportée) ne font
    émettre aucune intégration ; le projet se termine comme en P4."""
    from conftest import reclamer, terminer

    noyau = pile_machine.noyau
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    terminer(noyau, projet["tableau"], projet["cartes"]["exploration"], "Carte du dépôt.")
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", PLAN)
    for c in tour["cartes"]:
        reclamer(noyau, projet["tableau"], c["carte"])
        terminer(noyau, projet["tableau"], c["carte"], "Fait.")
    _finir_la_synthese(pile_machine, projet, tour["synthese"])
    with noyau.base.connexion() as conn:
        noyau.emetteur.passe(conn)
        assert noyau.projets.projet(conn, projet["id"])["etat"] == "termine"
        assert conn.execute("SELECT COUNT(*) FROM demandes WHERE role = 'integration'").fetchone()[0] == 0


# ------------------------------------------------------------------ page Poste et /v1/meta


def test_vue_poste_carte_en_cours(pile_machine, executant, projet):
    servie = executant.carte()
    en_main = {"tableau": servie["tableau"], "carte": servie["carte"], "run_id": servie["run_id"]}
    executant.envoyer("battement", servie, note="Étape 1.")
    executant.reclamer(en_cours=en_main, attente=5)
    vue = pile_machine.get("/api/plugins/acp-poste/v1/poste").json()["executant"]
    assert vue["peut_executer"] is True and vue["voies_disponibles"] == ["poste-claude"]
    assert vue["espace_libre_mio"] == 3120
    en_cours = vue["carte_en_cours"]
    assert (en_cours["carte"], en_cours["role"], en_cours["modele_demande"], en_cours["statut"]) == (
        servie["carte"], "exploration", "factice-claude-1", "running")
    assert en_cours["a_nous"] is True and en_cours["dernier_battement"]


def test_meta_resume_l_executant(pile_machine, executant, projet):
    import meta

    executant.reclamer(attente=5)
    bloc, _alertes = meta.bloc_machine()
    assert bloc["executant"]["peut_executer"] is True and bloc["executant"]["voies_disponibles"] == ["poste-claude"]
    assert bloc["executant"]["plateforme"] == "windows"  # aucun inventaire encore : la valeur par défaut de P5
    assert all(bloc["chemins_a_jeton"].values()) and len(bloc["chemins_a_jeton"]) == 9
