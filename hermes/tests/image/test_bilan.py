"""Bilan quotidien (étape P7, cahier P7 § 7, décision P7-6) : noyau (``noyau/bilan.py``) et script de l'image
(``/opt/acp/scripts/acp-bilan.py``) que lance une tâche cron ``no_agent`` créée par le propriétaire.

- UNE notification ``bilan:<AAAA-MM-JJ>`` par jour de PARIS (deux exécutions le même jour n'en font qu'une) ;
- compteurs seulement : aucun titre de carte, aucune question ; 300 caractères au plus ; ce qui ne se lit pas est dit
  « inconnu », jamais compté zéro ; envoyé même quand rien n'a bougé ;
- canal absent : la ligne passe ``desactivee`` (rien n'est envoyé) ;
- le script ignore ses arguments, son entrée et l'environnement hors ``HERMES_HOME`` (exigé).
"""

from __future__ import annotations

import calendar
import os
import subprocess
from pathlib import Path

from conftest import PYTHON_HERMES, lancer_sur_depot, reclamer

SCRIPT = Path("/opt/acp/scripts/acp-bilan.py")
TITRE_TEMOIN = "TITRE-DE-CARTE-TEMOIN"
QUESTION_TEMOIN = "QUESTION-TEMOIN-7Q"


def _epoch(annee, mois, jour, heure, minute=0) -> int:
    return calendar.timegm((annee, mois, jour, heure, minute, 0))


def _bilans(conn):
    return [tuple(l) for l in conn.execute("SELECT cle, genre, texte, lien, etat FROM notifications WHERE genre = "
                                           "'bilan' ORDER BY id")]


def test_base_vide_texte_exact_et_une_ligne_par_jour_de_paris(noyau, conn):
    # 2026-10-01 22:30 UTC = 2 octobre 00:30 à Paris : le jour est celui de Paris, jamais celui d'UTC.
    noyau.base.fixer_horloge(lambda: _epoch(2026, 10, 1, 22, 30))
    premier = noyau.bilan.enfiler(conn)
    assert premier == {"cle": "bilan:2026-10-02", "nouveau": True, "texte": (
        "ACP — Bilan du 02/10 : aucun projet en cours, rien n'attend votre décision, exécutant non configuré.")}
    noyau.base.fixer_horloge(lambda: _epoch(2026, 10, 2, 21, 59))  # 23:59 à Paris : même jour
    assert noyau.bilan.enfiler(conn)["nouveau"] is False
    noyau.base.fixer_horloge(lambda: _epoch(2026, 10, 2, 22, 0))  # minuit à Paris : jour suivant
    assert noyau.bilan.enfiler(conn)["cle"] == "bilan:2026-10-03"
    assert [(c, g, l, e) for c, g, _t, l, e in _bilans(conn)] == [
        ("bilan:2026-10-02", "bilan", "/", "en_attente"), ("bilan:2026-10-03", "bilan", "/", "en_attente")]
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE action = 'bilan'").fetchone()[0] == 2


def test_compteurs_seulement_jamais_un_titre_ni_une_question(noyau, conn):
    projet = lancer_sur_depot(noyau, conn, titre=f"Projet {TITRE_TEMOIN}", reponses="proprietaire")
    run = reclamer(noyau, projet["tableau"], projet["cartes"]["exploration"])
    noyau.questions.poser(conn, tableau=projet["tableau"], carte=projet["cartes"]["exploration"], run_id=run,
                          texte=f"{QUESTION_TEMOIN} : quel nom ?")
    resultat = noyau.bilan.enfiler(conn)
    texte = resultat["texte"]
    assert TITRE_TEMOIN not in texte and QUESTION_TEMOIN not in texte and len(texte) <= 300
    assert "1 projet en cours (0 carte faite sur 2)" in texte, texte
    assert "1 question pour vous" in texte and "exécutant non configuré" in texte, texte


def test_pluriels_et_liste_des_demandes(noyau):
    a_traiter = noyau.bilan._a_traiter
    assert a_traiter({"questions": 0, "decisions": 0, "revues": 0, "arretees": 0}) == "rien n'attend votre décision"
    assert a_traiter({"questions": 1, "decisions": 1, "revues": 0, "arretees": 0}) == (
        "1 question et 1 décision pour vous")
    assert a_traiter({"questions": 2, "decisions": 0, "revues": 1, "arretees": 3}) == (
        "2 questions, 1 revue et 3 cartes arrêtées pour vous")
    projets = noyau.bilan._projets
    assert projets({"en_cours": 2, "en_pause": 1, "faites": 5, "total": 12}) == (
        "2 projets en cours (5 cartes faites sur 12), 1 en pause")
    assert projets({"en_cours": 1, "en_pause": 0, "faites": None, "total": None}) == "1 projet en cours"
    assert projets({"en_cours": 0, "en_pause": 0, "faites": 0, "total": 0}) == "aucun projet en cours"


def test_bloc_illisible_dit_inconnu_jamais_zero(noyau, conn, monkeypatch):
    def panne(*_a, **_k):
        raise RuntimeError("base illisible")

    monkeypatch.setattr(noyau.projets, "lister", panne)
    monkeypatch.setattr(noyau.questions, "file_questions", panne)
    monkeypatch.setattr(noyau.presence, "etat_poste", panne)
    texte = noyau.bilan.enfiler(conn)["texte"]
    assert texte.endswith("projets : état inconnu, demandes en attente : état inconnu, état de l'exécutant "
                          "inconnu."), texte
    assert " 0 " not in texte


def test_canal_absent_la_ligne_passe_desactivee(noyau, conn):
    noyau.bilan.enfiler(conn)
    appels = []
    bilan = noyau.notifications.envoyer_en_attente(conn, noyau.notifications.Configuration(),
                                                   lambda *a: appels.append(a) or (200, ""))
    assert bilan["desactivees"] == 1 and appels == []
    assert _bilans(conn)[0][4] == "desactivee"


def _script(*arguments, env=None, entree=None):
    return subprocess.run([PYTHON_HERMES, str(SCRIPT), *arguments], env=env, input=entree, capture_output=True,
                          text=True, timeout=120)


def test_le_script_enfile_une_fois_et_ignore_arguments_entree_et_variables(noyau, conn, tmp_path):
    autre = tmp_path / "autre-home"
    autre.mkdir()
    env = {"PATH": "/usr/bin:/bin", "HERMES_HOME": str(noyau.home),
           # Ignorées : rien ne redirige la base ni le tableau, aucune variable d'ACP n'est lue.
           "HERMES_KANBAN_DB": str(autre / "kanban.db"), "HERMES_KANBAN_HOME": str(autre),
           "ACP_NOTIFICATIONS": "ntfy", "HERMES_DASHBOARD_PUBLIC_URL": "https://intrus.example"}
    premier = _script("--supprimer", "/opt/data", env=env, entree="rm -rf /\n")
    assert (premier.returncode, premier.stdout, premier.stderr) == (0, "bilan enfilé\n", ""), premier
    second = _script(env=env)
    assert (second.returncode, second.stdout) == (0, "bilan déjà enfilé aujourd'hui\n"), second
    [(cle, genre, texte, lien, etat)] = _bilans(conn)
    assert cle.startswith("bilan:") and (genre, lien, etat) == ("bilan", "/", "en_attente")
    assert texte.startswith("ACP — Bilan du ") and len(texte) <= 300
    assert sorted(os.listdir(autre)) == []  # rien n'a été écrit ailleurs


def test_le_script_sans_hermes_home_refuse_sans_rien_ecrire(tmp_path):
    for env in ({"PATH": "/usr/bin:/bin"}, {"PATH": "/usr/bin:/bin", "HERMES_HOME": "relatif"},
                {"PATH": "/usr/bin:/bin", "HERMES_HOME": str(tmp_path / "absent")}):
        resultat = _script(env=env)
        assert (resultat.returncode, resultat.stdout) == (1, ""), resultat
        assert resultat.stderr == "HERMES_HOME absent ou invalide : bilan non enfilé.\n", resultat.stderr
    assert not (tmp_path / "absent").exists()
