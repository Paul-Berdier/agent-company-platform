"""Émetteur de notifications (cahier P4 § 12.5) : règles exactes, envoi unique, curseur, canaux, secrets,
veille des crochets, passe déclenchée par le tick du répartiteur dans la passerelle seulement."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from conftest import (carte, cartes_du_tableau, en_worker, executer_python, lancer_sans_depot, lancer_sur_depot, outil,
                      reclamer, terminer)
from noyau.notifications import Configuration

PLAN = {"resume": "r", "etapes": [
    {"ref": "e1", "titre": "Chercher A", "classe": "recherche_web", "consigne": "CONSIGNE-TEMOIN-9Q : chercher A."},
    {"ref": "e2", "titre": "Chercher B", "classe": "recherche_web", "consigne": "Chercher B."},
    {"ref": "e3", "titre": "Chercher C", "classe": "recherche_web", "consigne": "Chercher C."},
    {"ref": "e4", "titre": "Chercher D", "classe": "recherche_web", "consigne": "Chercher D."}]}
JETON = "jeton-de-test-acp-p4"
SUJET = "acp_sujet_de_test_0123"


def _projet_planifie(noyau, conn, monkeypatch, plan=PLAN):
    projet = lancer_sans_depot(noyau, conn)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", plan)
    assert tour["ok"], tour
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")  # kanban_complete du worker
    monkeypatch.delenv("HERMES_KANBAN_TASK")
    monkeypatch.delenv("HERMES_KANBAN_BOARD")
    return projet, tour, {c["ref"]: c["carte"] for c in tour["cartes"]}


def _notifs(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre FROM notifications ORDER BY id")]


def test_regles_exactes(noyau, conn, monkeypatch):
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch)
    t = projet["tableau"]
    from hermes_cli.kanban_db_dispatch import _record_task_failure

    with noyau.ka.connexion(t) as kc:
        # bloquee : un blocage typé ordinaire.
        assert noyau.ka.block_task(kc, cartes["e1"], kind="needs_input", reason="Il manque la clé d'accès.")
        # triage : deux blocages du même genre (le propriétaire a débloqué entre les deux).
        assert noyau.ka.block_task(kc, cartes["e2"], kind="capability", reason="x")
        assert noyau.ka.unblock_task(kc, cartes["e2"])
        assert noyau.ka.block_task(kc, cartes["e2"], kind="capability", reason="x")
        # abandon : le disjoncteur du répartiteur.
        _record_task_failure(kc, cartes["e3"], "panne du worker", outcome="crashed", force_trip=True)
    # Aucune notification : réclamation et fin intermédiaire (e4), promotions.
    reclamer(noyau, t, cartes["e4"])
    terminer(noyau, t, cartes["e4"], "fait")
    with noyau.ka.connexion(t) as kc:
        genres = [e[2] for e in noyau.ka.evenements_apres(kc, 0)]
    assert {"blocked", "block_loop_detected", "gave_up", "claimed", "completed"} <= set(genres), genres
    noyau.emetteur.lire_evenements(conn)
    genres_notifies = sorted(g for _c, g in _notifs(conn))
    assert genres_notifies == ["abandon", "bloquee", "bloquee", "triage"], _notifs(conn)
    # (e2 : le premier blocage notifie « bloquee », le second « triage » ; e3 : « gave_up » seul, le
    # disjoncteur ne pose pas d'événement « blocked » : kanban_db_dispatch.py:1418-1455.)
    assert all(c.startswith(("bloquee:", "triage:", "abandon:")) and f":{t}:" in c for c, _g in _notifs(conn))


def test_envoi_unique_par_cle_meme_rejoue(noyau, conn, monkeypatch):
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        noyau.ka.block_task(kc, cartes["e1"], kind="needs_input", reason="manque")
    noyau.emetteur.lire_evenements(conn)
    avant = _notifs(conn)
    with noyau.base.transaction(conn):
        conn.execute("UPDATE curseurs SET evenement = 0")  # rejeu complet des événements
    noyau.emetteur.lire_evenements(conn)
    assert _notifs(conn) == avant and len(avant) == 1


def test_curseur_avance_dans_la_meme_transaction(noyau, conn, monkeypatch):
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        noyau.ka.block_task(kc, cartes["e1"], kind="needs_input", reason="a")
        noyau.ka.block_task(kc, cartes["e2"], kind="needs_input", reason="b")
    curseur = conn.execute("SELECT evenement FROM curseurs").fetchone()[0]
    vraie, appels = noyau.notifications.enfiler_dans, []

    def seconde_leve(*args, **kwargs):
        appels.append(1)
        if len(appels) == 2:
            raise RuntimeError("panne entre deux notifications")
        return vraie(*args, **kwargs)

    monkeypatch.setattr(noyau.notifications, "enfiler_dans", seconde_leve)
    with pytest.raises(RuntimeError):
        noyau.emetteur.lire_evenements(conn)
    assert _notifs(conn) == [] and conn.execute("SELECT evenement FROM curseurs").fetchone()[0] == curseur
    monkeypatch.setattr(noyau.notifications, "enfiler_dans", vraie)
    noyau.emetteur.lire_evenements(conn)
    assert len(_notifs(conn)) == 2 and conn.execute("SELECT evenement FROM curseurs").fetchone()[0] > curseur


def test_projet_termine_une_fois(noyau, conn, monkeypatch):
    plan = {"resume": "r", "etapes": PLAN["etapes"][:1]}
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch, plan)
    assert noyau.emetteur.projets_termines(conn) == []
    terminer(noyau, projet["tableau"], cartes["e1"], "fait")
    assert noyau.emetteur.projets_termines(conn) == []  # synthèse pas encore faite
    terminer(noyau, projet["tableau"], tour["synthese"], "Conclusion.")
    assert noyau.emetteur.projets_termines(conn) == [projet["id"]]
    assert noyau.emetteur.projets_termines(conn) == []
    assert _notifs(conn) == [(f"termine:{projet['id']}", "termine")]
    assert conn.execute("SELECT texte FROM notifications").fetchone()[0] == (
        "ACP — Projet « Veille LLM » terminé : 3 cartes faites.")
    assert noyau.projets.projet(conn, projet["id"])["etat"] == "termine"


def test_pas_termine_tant_qu_une_carte_reste_ouverte(noyau, conn, monkeypatch):
    plan = {"resume": "r", "etapes": PLAN["etapes"][:1]}
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch, plan)
    fiche = noyau.projets.projet(conn, projet["id"])
    noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "témoin")
    terminer(noyau, projet["tableau"], cartes["e1"], "fait")
    terminer(noyau, projet["tableau"], tour["synthese"], "Conclusion.")
    assert noyau.emetteur.projets_termines(conn) == []


def test_canal_absent_desactivee(noyau, conn):
    noyau.notifications.enfiler(conn, cle="test:1", genre="test", texte_notif="ACP — essai")
    appels = []
    bilan = noyau.notifications.envoyer_en_attente(conn, noyau.notifications.Configuration(),
                                                   lambda *a: appels.append(a) or (200, ""))
    assert bilan["desactivees"] == 1 and appels == []
    assert conn.execute("SELECT etat FROM notifications").fetchone()[0] == "desactivee"


def test_textes_sans_consigne_ni_secret(noyau, conn, monkeypatch):
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        noyau.ka.block_task(kc, cartes["e1"], kind="needs_input", reason="CONSIGNE-TEMOIN-9Q")
    noyau.emetteur.lire_evenements(conn)
    textes = [l[0] for l in conn.execute("SELECT texte FROM notifications")]
    assert textes == ["ACP — Projet « Veille LLM » : la carte « Recherche web — e1 : Chercher A » est bloquée."]
    assert all("CONSIGNE-TEMOIN" not in t and len(t) <= 300 for t in textes)
    # Un titre de carte qui porterait un secret est masqué ; il est tronqué à 80 caractères.
    faux = "sk-" + "proj-" + "A" * 40
    texte = noyau.notifications.texte(noyau.textes.NOTIF_BLOQUEE, titre="Essai", carte=faux)
    assert faux not in texte
    long = noyau.notifications.texte(noyau.textes.NOTIF_BLOQUEE, titre="Essai", carte="x" * 200)
    assert "x" * 81 not in long and "x" * 80 in long


def _config(canal):
    if canal == "telegram":
        return Configuration(canal="telegram", jeton="123456:" + JETON, discussion="-1001234")
    return Configuration(canal="ntfy", jeton=JETON, serveur="https://ntfy.acp.test", sujet=SUJET)


def test_telegram_forme_de_la_requete(noyau, conn, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    noyau.notifications.enfiler(conn, cle="test:1", genre="test", projet_id="p_x",
                                texte_notif=noyau.notifications.texte(noyau.textes.NOTIF_TEST))
    requetes = []
    bilan = noyau.notifications.envoyer_en_attente(conn, _config("telegram"),
                                                   lambda *a: requetes.append(a) or (200, "{}"))
    assert bilan["envoyees"] == 1
    methode, url, entetes, corps, delai = requetes[0]
    assert (methode, url, delai) == ("POST", f"https://api.telegram.org/bot123456:{JETON}/sendMessage", 10)
    assert entetes == {"Content-Type": "application/json"}
    assert json.loads(corps) == {"chat_id": "-1001234", "disable_web_page_preview": True, "text": (
        "ACP — Notification de test envoyée depuis la page Projets. https://hermes.acp.test/projets?projet=p_x")}
    assert conn.execute("SELECT etat, tentatives FROM notifications").fetchone()[:] == ("envoyee", 1)


def test_ntfy_forme_et_jeton(noyau, conn, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    noyau.notifications.enfiler(conn, cle="question:q_1", genre="question", projet_id="p_x", texte_notif="ACP — Q")
    noyau.notifications.enfiler(conn, cle="termine:p_x", genre="termine", projet_id="p_x", texte_notif="ACP — T")
    requetes = []
    noyau.notifications.envoyer_en_attente(conn, _config("ntfy"), lambda *a: requetes.append(a) or (200, "{}"))
    (m1, u1, e1, c1, _), (m2, u2, e2, c2, _) = requetes
    assert (m1, u1, c1) == ("POST", f"https://ntfy.acp.test/{SUJET}", "ACP — Q".encode("utf-8"))
    assert e1 == {"Authorization": f"Bearer {JETON}", "Title": "ACP", "Priority": "4",
                  "Content-Type": "text/plain; charset=utf-8", "Click": "https://hermes.acp.test/projets?projet=p_x"}
    assert e2["Priority"] == "3" and c2 == "ACP — T".encode("utf-8")


def test_reprise_puis_echec_apres_5(noyau, conn):
    debut = time.time()
    noyau.base.fixer_horloge(lambda: debut)
    noyau.notifications.enfiler(conn, cle="test:1", genre="test", texte_notif="ACP — essai")
    delais = []
    for tentative in range(1, 6):
        noyau.notifications.envoyer_en_attente(conn, _config("ntfy"), lambda *a: (500, ""))
        ligne = conn.execute("SELECT * FROM notifications").fetchone()
        assert ligne["tentatives"] == tentative and ligne["derniere_erreur"] == "HTTP 500"
        if tentative < 5:
            assert ligne["etat"] == "en_attente"
            delais.append(ligne["prochaine_tentative"] - int(debut))
            # Pas encore échue : rien n'est retenté.
            noyau.notifications.envoyer_en_attente(conn, _config("ntfy"), lambda *a: pytest.fail("trop tôt"))
            noyau.base.fixer_horloge(lambda p=ligne["prochaine_tentative"]: p)
        else:
            assert ligne["etat"] == "echec"
    assert delais == [30, 30 + 60, 30 + 60 + 120, 30 + 60 + 120 + 240]


def test_erreur_d_envoi_sans_url_ni_jeton(noyau, conn):
    noyau.notifications.enfiler(conn, cle="test:1", genre="test", texte_notif="ACP — essai")

    def leve(methode, url, *_):
        raise OSError(f"injoignable : {url}")

    noyau.notifications.envoyer_en_attente(conn, _config("telegram"), leve)
    erreur = conn.execute("SELECT derniere_erreur FROM notifications").fetchone()[0]
    assert erreur == "OSError" and JETON not in erreur


def test_secrets_retires_de_os_environ(noyau):
    """register() retire les variables de notification de os.environ dans TOUT processus ; la passerelle
    seule garde le canal en mémoire."""
    code = r"""
import importlib.util, os, sys
os.environ.update({"ACP_NOTIFICATIONS": "ntfy", "ACP_NTFY_SUJET": "acp_sujet_de_test_0123",
                   "ACP_NTFY_JETON": "jeton-de-test-acp-p4", "ACP_NTFY_SERVEUR": "https://ntfy.acp.test"})
sys.argv = ARGV
spec = importlib.util.spec_from_file_location("acp_test_secrets", "/opt/hermes/plugins/acp-poste/__init__.py",
                                              submodule_search_locations=["/opt/hermes/plugins/acp-poste"])
module = importlib.util.module_from_spec(spec)
sys.modules["acp_test_secrets"] = module
spec.loader.exec_module(module)
class Contexte:
    def register_hook(self, *a): pass
    def register_tool(self, **k): pass
    def register_system_prompt_section(self, *a, **k): pass
module.register(Contexte())
from acp_test_secrets.noyau import emetteur
resultat = {"restantes": sorted(k for k in os.environ if k.startswith("ACP_")),
            "canal": emetteur._config.canal, "passerelle": emetteur._dans_la_passerelle,
            "jeton_en_memoire": emetteur._config.jeton is not None}
"""
    import os

    env = dict(os.environ, HERMES_HOME=str(noyau.home))
    passerelle = executer_python(code.replace("ARGV", repr(["hermes", "gateway", "run"])), env=env)
    worker = executer_python(code.replace("ARGV", repr(["hermes", "-p", "default", "chat", "-q", "x"])), env=env)
    assert passerelle == {"restantes": [], "canal": "ntfy", "passerelle": True, "jeton_en_memoire": True}
    assert worker == {"restantes": [], "canal": "aucune", "passerelle": False, "jeton_en_memoire": False}
    with noyau.base.connexion() as conn:
        assert noyau.base.lire_emetteur(conn, "canal") == {"canal": "ntfy", "configure": True,
                                                            "serveur": "https://ntfy.acp.test"}


def test_veille_crochets_engage_la_pause(noyau, conn):
    (noyau.home / "config.yaml").write_text("hooks:\n  on_session_start:\n    - command: id\n", encoding="utf-8")
    try:
        constats = noyau.emetteur.veiller_crochets(conn)
        assert constats == [f"{noyau.home / 'config.yaml'} : hooks"]
        assert noyau.projets.pause_generale()["reason"] == "ACP : crochets shell détectés en cours de route"
        assert [g for _c, g in _notifs(conn)] == ["crochets"]
        noyau.emetteur.veiller_crochets(conn)
        assert len(_notifs(conn)) == 1  # une seule notification pour les mêmes constats
        (noyau.home / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        assert noyau.emetteur.veiller_crochets(conn) == []
        assert noyau.base.lire_emetteur(conn, "crochets") == []
    finally:
        noyau.ka.disengage()


def test_sur_tick_seulement_dans_la_passerelle_et_borne(noyau, conn, monkeypatch):
    monkeypatch.setattr(noyau.emetteur, "demarrer_fil", lambda: None)
    monkeypatch.setattr(noyau.emetteur, "_derniere_passe", 0.0)
    resultat = SimpleNamespace(skipped_nonspawnable=["t_a", "t_b"])
    noyau.emetteur.sur_tick(board="acp-x", result=resultat)
    assert noyau.base.lire_emetteur(conn, "derniere_passe") is None  # hors passerelle : rien
    noyau.emetteur.configurer(noyau.notifications.Configuration(), passerelle=True)
    noyau.emetteur.sur_tick(board="acp-x", result=resultat, dry_run=True)
    assert noyau.base.lire_emetteur(conn, "derniere_passe") is None  # passage à blanc : rien
    noyau.emetteur.sur_tick(board="acp-x", profile_name="default", outcome="ok", result=resultat, inconnu=1)
    premiere = noyau.base.lire_emetteur(conn, "derniere_passe")
    assert premiere is not None and noyau.base.lire_emetteur(conn, "processus") == "passerelle"
    assert noyau.base.lire_emetteur(conn, "derniers_ticks")["acp-x"] == 2
    noyau.base.fixer_horloge(lambda: time.time() + 100)
    noyau.emetteur.sur_tick(board="acp-y", result=SimpleNamespace(skipped_nonspawnable=[]))
    assert noyau.base.lire_emetteur(conn, "derniere_passe") == premiere  # intervalle non écoulé
    assert noyau.emetteur._derniers_ticks["acp-y"] == 0
    # Le crochet ne lève jamais, même sur un résultat aberrant.
    noyau.emetteur.sur_tick(board=object(), result=42)


def test_passe_complete_sans_erreur(noyau, conn, monkeypatch):
    projet, tour, cartes = _projet_planifie(noyau, conn, monkeypatch)
    bilan = noyau.emetteur.passe(conn)
    assert "erreurs" not in bilan, bilan
    assert set(bilan) >= {"reparations", "etrangeres", "pauses", "evenements", "sans_plan", "sans_suite", "questions",
                          "presence", "termines", "crochets"}
    assert carte(noyau, projet["tableau"], cartes["e1"]).status == "ready"


# ============================================================ corrections de la relecture de P4


def _textes(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre, texte FROM notifications ORDER BY id")]


def test_planification_finie_sans_plan_adresse_une_decision(noyau, conn, monkeypatch):
    """Relecture de P4 (haute) : une planification terminée sans projet_planifier laissait le projet arrêté,
    affiché « en cours », sans carte ouverte ni notification. Filet de l'émetteur : UNE carte de décision et
    UNE notification ; l'état dérivé le dit ; « Relancer la planification » permet à Hermes de planifier."""
    projet = lancer_sans_depot(noyau, conn, titre="Sans plan")
    tableau, planif = projet["tableau"], projet["cartes"]["planification"]
    reclamer(noyau, tableau, planif)
    assert terminer(noyau, tableau, planif, "Rien à planifier : projet_planifier a refusé mon plan.")
    fiche = noyau.projets.projet(conn, projet["id"])
    assert noyau.projets.etat(conn, fiche)["etat_derive"] == "a_decider"  # avant même la passe
    for _ in range(3):
        bilan = noyau.emetteur.passe(conn)
        assert "erreurs" not in bilan, bilan
    triage = [t for t in cartes_du_tableau(noyau, tableau).values() if t.status == "triage"]
    assert [t.title for t in triage] == ["Planification sans plan — votre décision est attendue"]
    assert triage[0].assignee == "default" and f"carte {planif} finie sans appel réussi" in triage[0].body
    assert _textes(conn) == [(f"sans_plan:{projet['id']}:1", "triage", "ACP — Projet « Sans plan » : la "
                              "planification s'est terminée sans plan, votre décision est attendue.")]
    liste = [p for p in noyau.projets.lister(conn) if p["id"] == projet["id"]][0]
    assert (liste["etat"], liste["etat_derive"], liste["compteurs"]["triage"]) == ("actif", "a_decider", 1)
    [entree] = noyau.questions.lister(conn)["triage"]
    assert (entree["genre"], entree["actions"]) == ("sans_plan", ["relancer", "conclure"])
    # Avant la décision du propriétaire, la carte de décision ne planifie pas.
    en_worker(monkeypatch, tableau, triage[0].id)
    assert outil(noyau, "projet_planifier", PLAN)["code"] == "contexte"
    # « Relancer la planification » : la carte part, Hermes planifie le tour 1 depuis elle.
    decision = noyau.questions.reprendre_triage(conn, tableau=tableau, carte=triage[0].id,
                                                consigne="Deux recherches suffisent.", auteur="proprietaire:t")
    assert decision == {"carte": triage[0].id, "reprise": True, "action": "relance_planification", "plafond": None}
    tour = outil(noyau, "projet_planifier", PLAN)
    assert tour["ok"] and tour["tour"] == 1, tour
    assert terminer(noyau, tableau, triage[0].id, "Tour 1 planifié.")
    noyau.emetteur.passe(conn)
    assert len(_textes(conn)) == 1  # aucune nouvelle décision : le projet a son tour 1
    assert noyau.projets.etat(conn, noyau.projets.projet(conn, projet["id"]))["etat_derive"] != "a_decider"


def test_conclure_une_planification_sans_plan_abandonne_le_projet(noyau, conn):
    """« Conclure » une planification sans plan : le projet n'a rien fait, il est « abandonné » (pas
    « terminé »), sa carte de décision archivée, et aucune notification (c'est le geste du propriétaire)."""
    projet = lancer_sans_depot(noyau, conn, titre="Conclu sans plan")
    reclamer(noyau, projet["tableau"], projet["cartes"]["planification"])
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Rien.")
    noyau.emetteur.passe(conn)
    [triage] = [t.id for t in cartes_du_tableau(noyau, projet["tableau"]).values() if t.status == "triage"]
    resultat = noyau.questions.conclure_triage(conn, tableau=projet["tableau"], carte=triage, auteur="proprietaire:t")
    assert resultat["conclu"] is True and resultat["projet"]["etat"] == "abandonne"
    assert carte(noyau, projet["tableau"], triage).status == "archived"
    noyau.emetteur.passe(conn)
    assert [g for _c, g, _t in _textes(conn)] == ["triage"]  # celle de la décision seulement
    assert noyau.questions.lister(conn)["triage"] == []


def test_question_sans_suite_escaladee(noyau, conn, monkeypatch):
    """Relecture de P4 (moyenne) : la carte « répondre » finie sans question_repondre ni question_escalader
    laissait la question « ouverte » et la carte du poste planifiée, en silence. Filet de l'émetteur : la
    question est escaladée, avec UNE notification « question »."""
    projet = lancer_sur_depot(noyau, conn, titre="Question muette")
    tableau, explo = projet["tableau"], projet["cartes"]["exploration"]
    run = reclamer(noyau, tableau, explo)
    q = noyau.questions.poser(conn, tableau=tableau, carte=explo, run_id=run, texte="Quel nom de module ?")
    reclamer(noyau, tableau, q["carte_repondre"])
    assert terminer(noyau, tableau, q["carte_repondre"], "Je ne peux pas trancher.")
    for _ in range(3):
        assert "erreurs" not in noyau.emetteur.passe(conn)
    question = noyau.questions.question(conn, q["question"])
    assert question["etat"] == "escaladee" and question["motif_escalade"] == (
        "Hermes n'a ni répondu ni escaladé : sa carte « répondre » s'est terminée sans suite (done) ; votre "
        "réponse est attendue.")
    assert [(c, g) for c, g, _t in _textes(conn)] == [(f"question:{q['question']}", "question")]
    assert carte(noyau, tableau, explo).status == "scheduled"
    # Le propriétaire répond depuis la page : la carte du poste reprend.
    reponse = noyau.questions.repondre_par_proprietaire(conn, q["question"], reponse="outil", auteur="proprietaire:t")
    assert reponse["carte_debloquee"] is True and carte(noyau, tableau, explo).status == "ready"


def test_transport_ne_suit_aucune_redirection(noyau):
    """Relecture de P4 (basse) : l'ouvreur par défaut de urllib suivait un 302 d'un POST en gardant
    Authorization (jeton ntfy) vers un autre hôte. Désormais un 3xx est un échec « HTTP 3xx », rien ne part
    vers la cible de la redirection."""
    import http.server
    import threading

    recu = []

    class Cible(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            recu.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET  # noqa: N815

        def log_message(self, *_):
            pass

    cible = http.server.HTTPServer(("127.0.0.1", 0), Cible)

    class Redirige(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{cible.server_address[1]}/ailleurs")
            self.end_headers()

        def log_message(self, *_):
            pass

    source = http.server.HTTPServer(("127.0.0.1", 0), Redirige)
    for serveur in (cible, source):
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        config = Configuration(canal="ntfy", jeton=JETON, serveur=f"http://127.0.0.1:{source.server_address[1]}",
                               sujet=SUJET)
        methode, url, entetes, corps = noyau.notifications.requete(config, {"texte": "t", "genre": "test", "lien": None})
        assert entetes["Authorization"] == f"Bearer {JETON}"
        code, _ = noyau.notifications.transport_urllib(methode, url, entetes, corps, 5)
        assert code == 302 and recu == []
        # Dans la file : un échec « HTTP 302 », réessayé plus tard vers la MÊME URL, jamais vers la redirection.
        with noyau.base.connexion() as conn:
            noyau.notifications.enfiler(conn, cle="test:redirection", genre="test", texte_notif="ACP — essai")
            bilan = noyau.notifications.envoyer_en_attente(conn, config)
            ligne = conn.execute("SELECT etat, derniere_erreur FROM notifications").fetchone()
        assert bilan["reportees"] == 1 and tuple(ligne) == ("en_attente", "HTTP 302") and recu == []
    finally:
        for serveur in (cible, source):
            serveur.shutdown()
