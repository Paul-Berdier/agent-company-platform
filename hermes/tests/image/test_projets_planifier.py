"""Planification d'un tour (cahier P4 § 6.2 et § 8.2) : graphe, atomicité, idempotence, plafonds, chaque refus."""

from __future__ import annotations

import pytest

from conftest import (carte, cartes_du_tableau, en_worker, lancer_sans_depot, lancer_sur_depot, outil, reclamer,
                      releve_factice, terminer)

PLAN_DEPOT = {
    "resume": "Écrire puis documenter.",
    "decisions": ["Python 3.12", "Tests avec pytest"],
    "etapes": [
        {"ref": "e1", "titre": "Écrire le module", "classe": "implementation", "consigne": "Écrire outil.py.",
         "voie": "poste-codex", "modele": "factice-codex-1", "effort": "high"},
        {"ref": "e2", "titre": "Veille", "classe": "recherche_web", "consigne": "Chercher l'état de l'art.",
         "depend_de": ["e1"]},
    ],
}
PLAN_HERMES = {"resume": "Deux recherches.", "etapes": [
    {"ref": "e1", "titre": "Chercher A", "classe": "recherche_web", "consigne": "Chercher A."},
    {"ref": "e2", "titre": "Chercher B", "classe": "recherche_web", "consigne": "Chercher B.", "depend_de": ["e1"]}]}


def _terminer_exploration(noyau, projet):
    reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    assert terminer(noyau, projet["tableau"], projet["cartes"]["exploration"], "Carte du dépôt.")


def _planifier(noyau, monkeypatch, projet, plan, carte_id=None):
    en_worker(monkeypatch, projet["tableau"], carte_id or projet["cartes"]["planification"])
    return outil(noyau, "projet_planifier", plan)


def test_graphe_complet_tour_1(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    _terminer_exploration(noyau, projet)
    reponse = _planifier(noyau, monkeypatch, projet, PLAN_DEPOT)
    assert reponse["ok"] and reponse["tour"] == 1 and reponse["deja_planifie"] is False
    par_role = {(c["ref"], c["role"]): c for c in reponse["cartes"]}
    impl, rel, e2 = par_role[("e1", "implementation")], par_role[("e1", "relecture")], par_role[("e2", "hermes")]
    toutes = cartes_du_tableau(noyau, projet["tableau"])
    ti, tr, te2, ts = (toutes[impl["carte"]], toutes[rel["carte"]], toutes[e2["carte"]], toutes[reponse["synthese"]])
    # Implémentation : voie, modèle et effort choisis, sans compétences (le poste n'en charge pas).
    assert (ti.assignee, ti.model_override, ti.reasoning_effort, ti.status) == ("poste-codex", "factice-codex-1", "high",
                                                                                 "ready")
    assert ti.skills is None and ti.max_runtime_seconds is None and ti.created_by == "acp-poste"
    assert "Exécutant : poste-codex · Modèle : factice-codex-1 · Effort : high · Palier : default" in ti.body
    assert "- Python 3.12" in ti.body and "la demande enregistrée par le greffon fait foi" in ti.body
    # Relecture croisée : l'AUTRE voie, modèle et effort par défaut du relevé de poste-claude.
    assert (tr.assignee, tr.model_override, tr.reasoning_effort, tr.status) == ("poste-claude", "factice-claude-1",
                                                                                 "medium", "todo")
    assert rel["relit"] == impl["carte"] and impl["relue_par"] == rel["carte"]
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.parent_ids(kc, tr.id) == [ti.id]
        assert sorted(noyau.ka.parent_ids(kc, te2.id)) == sorted([ti.id, tr.id])
        assert sorted(noyau.ka.parent_ids(kc, ts.id)) == sorted([ti.id, tr.id, te2.id])
    # Carte Hermes : profil default, skills du profil (verrou) et acp-redaction, 3 600 s.
    assert te2.assignee == "default" and te2.max_runtime_seconds == 3600 and "acp-redaction" in te2.skills
    assert {"acp-profils", "hermes-agent"} <= set(te2.skills)
    # Synthèse : parents = tout le tour, priorité 10, 1 800 s.
    assert ts.assignee == "default" and ts.priority == 10 and ts.max_runtime_seconds == 1800
    assert ts.skills == ["acp-synthese", "acp-routage"] and ts.status == "todo"
    assert ts.idempotency_key == f"acp:{projet['id']}:t1:synthese"
    fiche = noyau.projets.projet(conn, projet["id"])
    assert fiche["tour"] == 1 and fiche["cartes_creees"] == 2 + 4
    assert reponse["plafonds_restants"] == {"tours": 2, "cartes": 30 - 6}


def test_atomique_rien_si_une_creation_leve(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    avant = set(cartes_du_tableau(noyau, projet["tableau"]))
    vraie, appels = noyau.ka.create_task, []

    def troisieme_leve(*args, **kwargs):
        appels.append(kwargs.get("idempotency_key"))
        if len(appels) == 3:
            raise RuntimeError("panne au milieu du tour")
        return vraie(*args, **kwargs)

    monkeypatch.setattr(noyau.ka, "create_task", troisieme_leve)
    reponse = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    assert reponse == {"ok": False, "code": "echec_creation", "message": "Échec d'ACP : aucune carte n'a été créée "
                       "(RuntimeError) ; le plan peut être rappelé tel quel."}
    assert set(cartes_du_tableau(noyau, projet["tableau"])) == avant
    assert conn.execute("SELECT COUNT(*) FROM demandes WHERE projet_id = ? AND tour = 1", (projet["id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM tours").fetchone()[0] == 0
    fiche = noyau.projets.projet(conn, projet["id"])
    assert fiche["tour"] == 0 and fiche["cartes_creees"] == 1
    # Témoin : sans la panne, le même plan passe.
    monkeypatch.setattr(noyau.ka, "create_task", vraie)
    assert _planifier(noyau, monkeypatch, projet, PLAN_HERMES)["ok"]


def test_idempotence_meme_plan(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    premier = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    second = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    assert second["deja_planifie"] is True and second["synthese"] == premier["synthese"]
    assert [c["carte"] for c in second["cartes"]] == [c["carte"] for c in premier["cartes"]]
    assert len(cartes_du_tableau(noyau, projet["tableau"])) == 1 + 3


def test_refus_meme_tour_autre_plan(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    autre = dict(PLAN_HERMES, resume="Autre plan.")
    reponse = _planifier(noyau, monkeypatch, projet, autre)
    assert reponse == {"ok": False, "code": "deja_planifie_autrement", "message": "Refusé par ACP : le tour 1 est déjà "
                       "planifié par cette carte avec un autre plan ; terminez-la par kanban_complete."}


def test_plafond_cartes_sans_creation_partielle(noyau, conn, monkeypatch):
    noyau.base.poser_reglage(conn, "plafond_cartes", 3, "test")
    projet = lancer_sans_depot(noyau, conn)
    reponse = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    assert reponse == {"ok": False, "code": "plafond_cartes", "message": "Refusé par ACP : ce plan créerait 3 cartes, "
                       "et le projet en compte déjà 1 sur 3 (plafond). Réduisez le plan."}
    assert len(cartes_du_tableau(noyau, projet["tableau"])) == 1
    un_seul = {"resume": "Une étape.", "etapes": PLAN_HERMES["etapes"][:1]}
    assert _planifier(noyau, monkeypatch, projet, un_seul)["ok"]


def test_plafond_tours_carte_de_triage_unique(noyau, conn, monkeypatch):
    noyau.base.poser_reglage(conn, "plafond_tours", 1, "test")
    projet = lancer_sans_depot(noyau, conn)
    tour1 = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    for c in tour1["cartes"]:
        assert terminer(noyau, projet["tableau"], c["carte"])
    for _ in range(2):
        reponse = _planifier(noyau, monkeypatch, projet, PLAN_HERMES, carte_id=tour1["synthese"])
        assert reponse == {"ok": False, "code": "plafond_tours", "message": "Refusé par ACP : plafond de 1 tours "
                           "atteint pour le projet « Veille LLM » ; une carte de triage vous est adressée."}
    triage = [t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    assert len(triage) == 1 and triage[0].assignee == "default"
    assert triage[0].title == "Plafond atteint : tours — votre décision est attendue"
    notifs = conn.execute("SELECT cle, genre FROM notifications").fetchall()
    # Clé de la notification par VALEUR du plafond : après une prolongation, le nouveau plafond en redemande une.
    assert [tuple(n) for n in notifs] == [(f"plafond:{projet['id']}:tours:1", "plafond")]


def test_effort_hors_enumeration_sans_reasoning_effort(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    _terminer_exploration(noyau, projet)
    plan = {"resume": "r", "etapes": [{"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c",
                                       "voie": "poste-codex", "effort": "extreme", "relecture": False}]}
    reponse = _planifier(noyau, monkeypatch, projet, plan)
    impl = reponse["cartes"][0]
    assert (impl["effort"], impl["effort_carte"]) == ("extreme", None)
    assert carte(noyau, projet["tableau"], impl["carte"]).reasoning_effort is None
    demande = noyau.projets.demande_de_la_carte(conn, projet["tableau"], impl["carte"])
    assert demande["effort"] == "extreme" and demande["effort_carte"] is None


@pytest.mark.parametrize("etape, code, message", [
    ({"voie": "poste-codex", "effort": "max"}, "effort_interdit",
     "Refusé par ACP : l'effort « max » est interdit par défaut ; seul le propriétaire peut le lever (page Routage, "
     "étape P5)."),
    ({"voie": "poste-codex", "modele": "factice-codex-2", "effort": "high"}, "effort_non_pris_en_charge",
     "Refusé par ACP : l'effort « high » n'est pas pris en charge par « factice-codex-2 » (efforts relevés : low)."),
    ({"voie": "poste-codex", "modele": "gpt-imaginaire"}, "modele_absent", "Refusé par ACP : le modèle "
     "« gpt-imaginaire » ne figure pas dans le relevé de la voie poste-codex (relevé du "),
    ({"classe": "recherche_web", "voie": "hermes", "modele": "gpt-imaginaire"}, "modele_absent",
     "Refusé par ACP : le modèle « gpt-imaginaire » ne figure pas dans le dernier relevé poste-codex ("),
    ({"classe": "recherche_web", "voie": "poste-codex"}, "classe_voie",
     "Refusé par ACP : la classe « recherche_web » n'admet pas la voie « poste-codex » (voies admises : hermes)."),
    ({"classe": "integration"}, "integration_p6",
     "Refusé par ACP : la classe « integration » (fusion locale des branches) est prévue à l'étape P6."),
    # Faux jeton assemblé à l'exécution (le balayage des secrets du dépôt ne doit rien trouver ici).
    ({"voie": "poste-codex", "consigne": "jeton " + "gh" + "p_" + "A" * 36}, "secret",
     "Refusé par ACP : la consigne de l'étape « e1 » contient ce qui ressemble à un secret (jeton GitHub)."),
])
def test_refus_du_routage(noyau, conn, monkeypatch, etape, code, message):
    projet = lancer_sur_depot(noyau, conn)
    _terminer_exploration(noyau, projet)
    plan = {"resume": "r", "etapes": [dict({"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c"},
                                           **etape)]}
    reponse = _planifier(noyau, monkeypatch, projet, plan)
    assert reponse["ok"] is False and reponse["code"] == code and reponse["message"].startswith(message), reponse
    assert noyau.projets.projet(conn, projet["id"])["tour"] == 0
    assert len(cartes_du_tableau(noyau, projet["tableau"])) == 2


def test_palier_interdit_refuse(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    _terminer_exploration(noyau, projet)
    noyau.routage.enregistrer_routage(conn, "implementation", [
        {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "low", "palier": "priority"}],
        source="releve_factice", valide_par="test")
    plan = {"resume": "r", "etapes": [{"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c"}]}
    reponse = _planifier(noyau, monkeypatch, projet, plan)
    assert (reponse["code"], reponse["message"]) == ("palier_interdit", "Refusé par ACP : le palier « priority » est "
                                                     "interdit par défaut (dépense hors enveloppe).")


def test_sans_depot_etape_poste_refusee(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    plan = {"resume": "r", "etapes": [{"ref": "code", "titre": "t", "classe": "implementation", "consigne": "c"}]}
    reponse = _planifier(noyau, monkeypatch, projet, plan)
    assert (reponse["code"], reponse["message"]) == ("sans_depot", "Refusé par ACP : le projet « Veille LLM » n'a pas "
                                                     "de dépôt ; l'étape « code » exige le poste et un dépôt autorisé.")


def test_aucun_modele_et_relecture_impossible(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn, voies=("poste-codex",),
                              exploration={"voie": "poste-codex", "modele": "factice-codex-1"})
    _terminer_exploration(noyau, projet)
    sans_choix = {"resume": "r", "etapes": [{"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c"}]}
    reponse = _planifier(noyau, monkeypatch, projet, sans_choix)
    assert (reponse["code"], reponse["message"]) == ("aucun_modele", "Aucun modèle disponible pour la classe "
                                                     "« implementation » : table de routage non validée et aucun choix "
                                                     "explicite.")
    avec_choix = {"resume": "r", "etapes": [{"ref": "e1", "titre": "t", "classe": "implementation", "consigne": "c",
                                             "voie": "poste-codex"}]}
    reponse = _planifier(noyau, monkeypatch, projet, avec_choix)
    assert (reponse["code"], reponse["message"]) == ("relecture_impossible", "Refusé par ACP : la relecture croisée de "
                                                     "l'étape « e1 » exige l'autre exécutant : aucun relevé pour "
                                                     "poste-claude.")


@pytest.mark.parametrize("etapes, detail", [
    ([{"ref": "e1", "titre": "t", "classe": "recherche_web", "consigne": "c", "depend_de": ["e9"]}],
     "étape e1 : dépend de « e9 », inconnue"),
    ([{"ref": "e1", "titre": "t", "classe": "recherche_web", "consigne": "c", "depend_de": ["e2"]},
      {"ref": "e2", "titre": "t", "classe": "recherche_web", "consigne": "c", "depend_de": ["e1"]}],
     "cycle entre e1 et e2"),
    ([{"ref": "e1", "titre": "t", "classe": "recherche_web", "consigne": "c"}] * 2, "références en double : e1"),
    ([{"ref": f"e{i}", "titre": "t", "classe": "recherche_web", "consigne": "c"} for i in range(13)],
     "plus de 12 étapes"),
    ([{"ref": "E1", "titre": "t", "classe": "recherche_web", "consigne": "c"}], "étape 1 : référence « E1 » invalide"),
    ([{"ref": "e1", "titre": "t", "classe": "cuisine", "consigne": "c"}], "étape e1 : classe « cuisine » inconnue"),
])
def test_plan_invalide(noyau, conn, monkeypatch, etapes, detail):
    projet = lancer_sans_depot(noyau, conn)
    reponse = _planifier(noyau, monkeypatch, projet, {"resume": "r", "etapes": etapes})
    assert reponse["code"] == "plan_invalide" and reponse["message"].startswith(f"Refusé par ACP : {detail}"), reponse


def test_refus_contexte_et_carte_non_courante(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    tour1 = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    # Une carte Hermes ordinaire n'est ni une planification ni une synthèse.
    reponse = _planifier(noyau, monkeypatch, projet, PLAN_HERMES, carte_id=tour1["cartes"][0]["carte"])
    assert reponse["code"] == "contexte" and reponse["message"] == (
        "Refusé par ACP : projet_planifier ne s'appelle que depuis la carte de planification ou de synthèse d'un "
        "projet ACP.")
    # Depuis la discussion : jamais.
    monkeypatch.delenv("HERMES_KANBAN_TASK")
    assert outil(noyau, "projet_planifier", PLAN_HERMES)["code"] == "contexte"
    # Une synthèse d'un tour qui n'est pas le tour courant.
    with noyau.base.transaction(conn):
        conn.execute("UPDATE demandes SET tour = 5 WHERE carte = ?", (tour1["synthese"],))
    reponse = _planifier(noyau, monkeypatch, projet, PLAN_HERMES, carte_id=tour1["synthese"])
    assert reponse["code"] == "carte_non_courante" and reponse["message"] == (
        "Refusé par ACP : cette carte n'est pas la planification ou la synthèse en cours du projet « Veille LLM ».")


def test_tableau_et_carte_pris_dans_l_environnement(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    for intrus in ({"tableau": "autre"}, {"carte": "t_autre"}):
        reponse = _planifier(noyau, monkeypatch, projet, dict(PLAN_HERMES, **intrus))
        assert reponse["code"] == "arguments" and "champ inconnu refusé" in reponse["message"]
    schema = noyau.outils.SCHEMAS["projet_planifier"]["parameters"]
    assert schema["additionalProperties"] is False and not {"tableau", "carte"} & set(schema["properties"])


def test_synthese_relance_un_tour_dans_les_plafonds(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    tour1 = _planifier(noyau, monkeypatch, projet, PLAN_HERMES)
    assert carte(noyau, projet["tableau"], tour1["synthese"]).status == "todo"
    for c in tour1["cartes"]:
        assert carte(noyau, projet["tableau"], tour1["synthese"]).status == "todo"
        terminer(noyau, projet["tableau"], c["carte"])
    assert carte(noyau, projet["tableau"], tour1["synthese"]).status == "ready"
    tour2 = _planifier(noyau, monkeypatch, projet, {"resume": "Reprise.", "etapes": PLAN_HERMES["etapes"][:1]},
                       carte_id=tour1["synthese"])
    assert tour2["ok"] and tour2["tour"] == 2 and tour2["plafonds_restants"]["tours"] == 1
    assert tour2["synthese"] != tour1["synthese"]


# ============================================================ corrections de la relecture de P4 (décision D41)

UNE_ETAPE = {"resume": "Une recherche.", "etapes": PLAN_HERMES["etapes"][:1]}


def _tour_fini(noyau, projet, tour):
    for c in tour["cartes"]:
        assert terminer(noyau, projet["tableau"], c["carte"])


def _notifs(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre, texte FROM notifications ORDER BY id")]


def test_prolonger_au_plafond_de_tours_planifie_un_tour_de_plus(noyau, conn, monkeypatch):
    """Relecture de P4 (haute) : « Reprendre » une carte de triage au plafond la faisait exécuter par Hermes, qui
    ne pouvait pas planifier (refus « contexte ») : le projet passait « terminé », notification comprise, alors
    que le propriétaire demandait de continuer. « Prolonger » relève le plafond de tours de 1 (journalisé) et la
    carte de décision planifie le tour suivant ; le nouveau plafond atteint adresse une NOUVELLE décision."""
    noyau.base.poser_reglage(conn, "plafond_tours", 1, "test")
    projet = lancer_sans_depot(noyau, conn, titre="Plafond prolongé")
    tour1 = _planifier(noyau, monkeypatch, projet, UNE_ETAPE)
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")
    _tour_fini(noyau, projet, tour1)
    assert _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=tour1["synthese"])["code"] == "plafond_tours"
    terminer(noyau, projet["tableau"], tour1["synthese"], "Plafond atteint, décision attendue.")
    noyau.emetteur.passe(conn)
    [triage] = [t.id for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    fiche = noyau.projets.projet(conn, projet["id"])
    assert (fiche["etat"], noyau.projets.etat(conn, fiche)["etat_derive"]) == ("actif", "plafond_atteint")
    assert "« Prolonger » accorde un tour de plus" in carte(noyau, projet["tableau"], triage).body
    [entree] = noyau.questions.lister(conn)["triage"]
    assert (entree["genre"], entree["actions"]) == ("tours", ["prolonger", "conclure"])
    decision = noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=triage,
                                                consigne="Faites un tour de plus pour vérifier.", auteur="proprietaire:t")
    assert decision == {"carte": triage, "reprise": True, "action": "prolongation",
                        "plafond": {"genre": "tours", "avant": 1, "apres": 2}}
    tour2 = _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=triage)
    assert tour2["ok"] and tour2["tour"] == 2, tour2
    assert terminer(noyau, projet["tableau"], triage, "Tour 2 planifié.")
    noyau.emetteur.passe(conn)
    fiche = noyau.projets.projet(conn, projet["id"])
    assert fiche["etat"] == "actif" and not [n for n in _notifs(conn) if n[1] == "termine"]
    journal = [tuple(l) for l in conn.execute("SELECT action, cible FROM journal WHERE action = 'prolongation'")]
    assert journal == [("prolongation", triage)]
    # Tour 2 fini : un 3e tour est refusé au nouveau plafond, avec UNE nouvelle décision et sa notification.
    _tour_fini(noyau, projet, tour2)
    assert _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=tour2["synthese"])["code"] == "plafond_tours"
    assert [(c, g) for c, g, _t in _notifs(conn)] == [(f"plafond:{projet['id']}:tours:1", "plafond"),
                                                       (f"plafond:{projet['id']}:tours:2", "plafond")]
    assert len([t for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]) == 1


def test_plafond_de_cartes_sans_plan_possible_adresse_une_decision(noyau, conn, monkeypatch):
    """Relecture de P4 (moyenne) : plafond de cartes atteint quand la synthèse veut un tour de plus : refus sans
    triage ni notification, puis « terminé ». Quand plus aucun plan ne tient (moins de deux cartes), c'est un
    plafond : carte de décision et notification ; « Prolonger » relève le plafond de ``prolongation_cartes``."""
    noyau.base.poser_reglage(conn, "plafond_cartes", 3, "test")
    projet = lancer_sans_depot(noyau, conn, titre="Plafond de cartes")
    tour1 = _planifier(noyau, monkeypatch, projet, UNE_ETAPE)
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")
    _tour_fini(noyau, projet, tour1)
    refus = _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=tour1["synthese"])
    assert refus == {"ok": False, "code": "plafond_cartes", "message": (
        "Refusé par ACP : le projet « Plafond de cartes » compte déjà 3 cartes sur 3 (plafond) : aucun plan ne tient "
        "plus (une étape et sa synthèse en demandent deux) ; une carte de triage vous est adressée.")}
    terminer(noyau, projet["tableau"], tour1["synthese"], "Il reste la moitié.")
    noyau.emetteur.passe(conn)
    fiche = noyau.projets.projet(conn, projet["id"])
    assert (fiche["etat"], noyau.projets.etat(conn, fiche)["etat_derive"]) == ("actif", "plafond_atteint")
    assert [t for _c, g, t in _notifs(conn)] == [
        "ACP — Projet « Plafond de cartes » : plafond de cartes atteint, votre décision est attendue."]
    [triage] = [t.id for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    decision = noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=triage, consigne=None,
                                                auteur="proprietaire:t")
    assert decision["plafond"] == {"genre": "cartes", "avant": 3, "apres": 13}
    assert _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=triage)["tour"] == 2
    # Il reste des cartes, mais pas assez pour CE plan : refus ordinaire (« Réduisez le plan »), aucune décision.
    noyau.base.poser_reglage(conn, "plafond_cartes", 3, "test")
    autre = lancer_sans_depot(noyau, conn, titre="Plan trop grand")
    assert _planifier(noyau, monkeypatch, autre, PLAN_HERMES)["message"].endswith("Réduisez le plan.")
    assert [t.status for t in cartes_du_tableau(noyau, autre["tableau"]).values()] == ["ready"]


def test_conclure_au_plafond_termine_sans_notification(noyau, conn, monkeypatch):
    """« Conclure » au plafond : refusé tant qu'une autre carte est ouverte (la synthèse qui vient de demander le
    tour), puis carte de décision archivée, projet « terminé », aucune notification « terminé » (geste du
    propriétaire). « Prolonger » au plafond de corrections : étape P6, refusé."""
    noyau.base.poser_reglage(conn, "plafond_tours", 1, "test")
    projet = lancer_sans_depot(noyau, conn, titre="Conclu au plafond")
    tour1 = _planifier(noyau, monkeypatch, projet, UNE_ETAPE)
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")
    _tour_fini(noyau, projet, tour1)
    _planifier(noyau, monkeypatch, projet, UNE_ETAPE, carte_id=tour1["synthese"])
    [triage] = [t.id for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.conclure_triage(conn, tableau=projet["tableau"], carte=triage, auteur="proprietaire:t")
    assert exc.value.code == "cartes_ouvertes"
    terminer(noyau, projet["tableau"], tour1["synthese"], "Conclusion.")
    resultat = noyau.questions.conclure_triage(conn, tableau=projet["tableau"], carte=triage, auteur="proprietaire:t")
    assert resultat["projet"]["etat"] == "termine" and carte(noyau, projet["tableau"], triage).status == "archived"
    noyau.emetteur.passe(conn)
    assert [g for _c, g, _t in _notifs(conn)] == ["plafond"]
    fiche = noyau.projets.projet(conn, projet["id"])
    corrections = noyau.graphe.creer_triage_plafond(conn, dict(fiche, etat="actif"), "corrections", "2 corrections")
    with noyau.base.transaction(conn):
        conn.execute("UPDATE projets SET etat = 'actif' WHERE id = ?", (projet["id"],))
    with pytest.raises(noyau.textes.RefusACP) as exc:
        noyau.questions.reprendre_triage(conn, tableau=projet["tableau"], carte=corrections, consigne=None, auteur="p")
    assert exc.value.code == "prolongation_p6"
    assert carte(noyau, projet["tableau"], corrections).status == "triage"
