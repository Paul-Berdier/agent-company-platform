"""Liens profonds des notifications (étape P7, cahier P7 § 6.2, décision P7-5 ; corrections K2 et K3).

- Chaque genre a sa cible, EN PARAMÈTRES DE REQUÊTE, jamais en fragment : la porte d'authentification de Hermes ne
  garde, pour le retour après la connexion, que le chemin et la requête (``next``).
- La ligne en base garde un CHEMIN RELATIF ; l'URL publique n'est préfixée qu'à l'envoi, dans la passerelle : une ligne
  enfilée par un sous-processus à l'environnement assaini (bilan du cron) n'a pas à la connaître.
- Une ligne antérieure à P7 (lien déjà absolu) part telle quelle ; sans URL publique valide, aucun lien.
- Aucun texte de question ni de consigne dans un lien.
"""

from __future__ import annotations

import json

from conftest import en_worker, lancer_sans_depot, lancer_sur_depot, outil, reclamer, terminer
from noyau.notifications import Configuration

JETON = "jeton-de-test-acp-p7"
SUJET = "acp_sujet_de_test_p7_liens"
NTFY = Configuration(canal="ntfy", jeton=JETON, serveur="https://ntfy.acp.test", sujet=SUJET)
TELEGRAM = Configuration(canal="telegram", jeton="123456:" + JETON, discussion="-1001234")
PLAN = {"resume": "r", "etapes": [
    {"ref": "e1", "titre": "Chercher A", "classe": "recherche_web", "consigne": "Chercher A."}]}


def _liens(conn):
    return {cle: (genre, lien) for cle, genre, lien in conn.execute("SELECT cle, genre, lien FROM notifications")}


def _envoyer(noyau, conn, config=NTFY):
    requetes = []
    noyau.notifications.envoyer_en_attente(conn, config, lambda *a: requetes.append(a) or (200, "{}"))
    return requetes


def test_cible_de_chaque_genre_en_requete_jamais_en_fragment(noyau):
    lien = noyau.notifications.lien
    attendus = {
        ("question", "p_1", "q_0123456789ab"): "/projets?vue=questions&q=q_0123456789ab",
        ("question", "p_1", None): "/projets?vue=questions",
        ("bloquee", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("triage", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("abandon", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("revue", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("secret", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("conflit", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("plafond", "p_1", "acp-p-1/t_ab12"): "/projets?vue=questions&carte=acp-p-1/t_ab12",
        ("plafond", "p_1", None): "/projets?vue=questions",
        ("bloquee", None, None): "/projets",  # carte hors tableau de projet : aucune cible inventée
        ("termine", "p_1", None): "/projets?projet=p_1",
        ("integration", "p_1", None): "/projets?projet=p_1",
        ("hors_ligne", None, None): "/poste",
        ("isolement", None, None): "/poste",
        ("bilan", None, None): "/",
        ("test", None, None): "/projets",
        ("crochets", None, None): "/projets",
    }
    for (genre, projet, cible), attendu in attendus.items():
        obtenu = lien(genre, projet, cible)
        assert obtenu == attendu, (genre, projet, cible, obtenu)
        assert "#" not in obtenu and obtenu.startswith("/")
    # Une cible qui porterait un caractère spécial est encodée, jamais recopiée telle quelle.
    assert lien("question", "p_1", "q&x=1#y") == "/projets?vue=questions&q=q%26x%3D1%23y"


def test_question_escaladee_lien_relatif_en_base_puis_absolu_a_l_envoi(noyau, conn, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    projet = lancer_sur_depot(noyau, conn, reponses="proprietaire")
    run = reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=projet["cartes"]["exploration"], run_id=run,
                              texte="TEXTE-DE-QUESTION-TEMOIN : quel nom donner au module ?")
    assert q["etat"] == "escaladee"
    assert _liens(conn) == {f"question:{q['question']}": ("question", f"/projets?vue=questions&q={q['question']}")}
    [(_methode, _url, entetes, corps, _delai)] = _envoyer(noyau, conn)
    assert entetes["Click"] == f"https://hermes.acp.test/projets?vue=questions&q={q['question']}"
    assert "TEXTE-DE-QUESTION-TEMOIN" not in entetes["Click"] and b"TEXTE-DE-QUESTION-TEMOIN" not in corps
    # La ligne garde son chemin relatif après l'envoi (rien n'est réécrit en base).
    assert conn.execute("SELECT lien, etat FROM notifications").fetchone()[:] == (
        f"/projets?vue=questions&q={q['question']}", "envoyee")


def test_escalade_par_hermes_puis_passe_meme_cible(noyau, conn, monkeypatch):
    projet = lancer_sur_depot(noyau, conn)
    run = reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    q = noyau.questions.poser(conn, tableau=projet["tableau"], carte=projet["cartes"]["exploration"], run_id=run,
                              texte="Budget ?")
    en_worker(monkeypatch, projet["tableau"], q["carte_repondre"])
    assert outil(noyau, "question_escalader", {"motif": "Dépense : le propriétaire tranche."})["etat"] == "escaladee"
    noyau.emetteur.questions_escaladees(conn)
    assert _liens(conn) == {f"question:{q['question']}": ("question", f"/projets?vue=questions&q={q['question']}")}


def _projet_planifie(noyau, conn, monkeypatch):
    projet = lancer_sans_depot(noyau, conn)
    en_worker(monkeypatch, projet["tableau"], projet["cartes"]["planification"])
    tour = outil(noyau, "projet_planifier", PLAN)
    assert tour["ok"], tour
    terminer(noyau, projet["tableau"], projet["cartes"]["planification"], "Plan posé.")
    monkeypatch.delenv("HERMES_KANBAN_TASK")
    monkeypatch.delenv("HERMES_KANBAN_BOARD")
    return projet, tour, {c["ref"]: c["carte"] for c in tour["cartes"]}["e1"]


def test_carte_bloquee_et_decision_ciblent_leur_carte(noyau, conn, monkeypatch):
    projet, _tour, e1 = _projet_planifie(noyau, conn, monkeypatch)
    with noyau.ka.connexion(projet["tableau"]) as kc:
        assert noyau.ka.block_task(kc, e1, kind="needs_input", reason="Il manque la clé.")
    noyau.emetteur.lire_evenements(conn)
    fiche = noyau.projets.projet(conn, projet["id"])
    decision = noyau.graphe.creer_triage_plafond(conn, fiche, "tours", "témoin")
    liens = _liens(conn)
    [bloquee] = [v for c, v in liens.items() if c.startswith("bloquee:")]
    [plafond] = [v for c, v in liens.items() if c.startswith("plafond:")]
    assert bloquee == ("bloquee", f"/projets?vue=questions&carte={projet['tableau']}/{e1}")
    assert decision and plafond == ("plafond", f"/projets?vue=questions&carte={projet['tableau']}/{decision}")


def test_projet_termine_mene_au_detail(noyau, conn, monkeypatch):
    projet, tour, e1 = _projet_planifie(noyau, conn, monkeypatch)
    terminer(noyau, projet["tableau"], e1, "fait")
    terminer(noyau, projet["tableau"], tour["synthese"], "Conclusion.")
    assert noyau.emetteur.projets_termines(conn) == [projet["id"]]
    assert _liens(conn) == {f"termine:{projet['id']}": ("termine", f"/projets?projet={projet['id']}")}


def test_ligne_anterieure_absolue_gardee_et_sans_url_publique_aucun_lien(noyau, conn, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    with noyau.base.transaction(conn):
        conn.execute("INSERT INTO notifications (cle, genre, projet_id, texte, lien, etat, tentatives, "
                     "prochaine_tentative, cree_le) VALUES ('termine:p_ancien', 'termine', 'p_ancien', 'ACP — ancien', "
                     "'https://ancienne.acp.test/projets?projet=p_ancien', 'en_attente', 0, 0, 0)")
    noyau.notifications.enfiler(conn, cle="bilan:2026-10-02", genre="bilan", texte_notif="ACP — Bilan.")
    [(_m, _u, ancien, _c, _d), (_m2, _u2, bilan, _c2, _d2)] = _envoyer(noyau, conn)
    assert ancien["Click"] == "https://ancienne.acp.test/projets?projet=p_ancien"
    assert bilan["Click"] == "https://hermes.acp.test/"
    # Sans URL publique valide (absente, ou http) : aucun lien, jamais une adresse inventée.
    for valeur in (None, "http://hermes.acp.test"):
        if valeur is None:
            monkeypatch.delenv("HERMES_DASHBOARD_PUBLIC_URL", raising=False)
        else:
            monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", valeur)
        noyau.notifications.enfiler(conn, cle=f"test:{valeur}", genre="test", texte_notif="ACP — essai")
        [(_m, _u, entetes, _c, _d)] = _envoyer(noyau, conn)
        assert "Click" not in entetes


def test_telegram_ajoute_le_lien_absolu_au_texte(noyau, conn, monkeypatch):
    monkeypatch.setenv("HERMES_DASHBOARD_PUBLIC_URL", "https://hermes.acp.test")
    noyau.notifications.enfiler(conn, cle="hors_ligne:m:1", genre="hors_ligne", texte_notif="ACP — Hors ligne.")
    [(_m, _u, _e, corps, _d)] = _envoyer(noyau, conn, TELEGRAM)
    assert json.loads(corps)["text"] == "ACP — Hors ligne. https://hermes.acp.test/poste"
