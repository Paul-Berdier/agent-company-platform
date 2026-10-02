"""Preuve « redéploiement pendant une question » de l'étape P7 (cahier P7 § 13.2 ; corrections K1, K2, K3, K12), pilotée
depuis l'hôte (voir conftest.py), sur la pile complète, avec le FAUX EXÉCUTANT de P6 (outils/faux_executant.py) et le
modèle factice à scénarios.

Parcours, sur UN projet sur le dépôt jetable (« qui répond » : le propriétaire) :

1. l'exécutant réclame l'exploration et pose une question → carte ``scheduled``, question ``escaladee`` ; le faux ntfy
   reçoit UNE notification « question » dont l'en-tête ``Click`` est le lien profond
   ``https://hermes.acp.test/projets?vue=questions&q=<id>`` (requête, jamais fragment : K2 ; chemin relatif en base,
   URL publique préfixée à l'envoi : K3) ;
2. REDÉPLOIEMENT : le conteneur Hermes est SUPPRIMÉ puis RECRÉÉ sur le MÊME volume, comme Railway (le volume porte
   alors ``scripts/acp-bilan.py`` déposé au premier démarrage : le second démarrage doit passer les gardes, K1) ;
   l'exécutant garde son jeton (son propre stockage, recopié ici d'un conteneur à l'autre : jamais affiché) ;
3. après le redémarrage : même question (identifiant, texte, état), carte toujours ``scheduled``, AUCUNE notification
   en double (clé unique), l'exécutant reprend son long-poll (rien à servir) ;
4. réponse du propriétaire par la route → la carte repart : servie avec ``reprise: true`` et la réponse ; fin de
   l'exploration → planification (modèle factice : une implémentation sur poste-claude) → implémentation servie et
   terminée (branche rapportée) → synthèse → carte d'INTÉGRATION servie sur ``poste-integration`` → projet
   ``termine`` et notification ``integration`` (K12 : ``termine`` n'est envoyée que sans branche à intégrer).
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from conftest import ENV_VALIDE, Conteneur, afficher, attendre_modele_factice, docker, lancer

MODELE = """\
kanban:
  dispatch_interval_seconds: 5
model:
  provider: custom
  base_url: http://127.0.0.1:18080/v1
  default: acp-factice
  api_key: factice
"""
JOURNAL_FACTICE = "/tmp/modele-factice.jsonl"
JOURNAL_NTFY = "/tmp/ntfy-parcours.jsonl"
SCENARIOS = "/tmp/acp-scenarios.json"
SUJET = "acp_sujet_de_test_parcours"
JETON_NTFY = "jeton-de-test-acp-parcours"
ENV_PARCOURS = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test",
                    ACP_NTFY_SUJET=SUJET, ACP_NTFY_JETON=JETON_NTFY)
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
FAUX_POSTE = "/opt/acp-tests/outils/faux_poste.py"
FAUX = "/opt/acp-tests/outils/faux_executant.py"
TITRE = "Parcours P7"
QUESTION = "Quel nom donner au module principal ?"
REPONSE = "outil.py, sans dépendance externe."
PLAN = {"resume": "Une implémentation, puis la synthèse.", "decisions": ["Module unique outil.py"],
        "etapes": [{"ref": "e1", "titre": "Écrire outil.py", "classe": "implementation", "voie": "poste-claude",
                    "modele": "opus", "effort": "low",
                    "relecture": False, "consigne": "Écrire outil.py selon la réponse du propriétaire."}]}


def _appel(nom: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"outil": "tool_call", "arguments": {"calls": [{"name": nom, "arguments": arguments or {}}]}}


SCENARIOS_PARCOURS = {
    f"rôle « planification » — projet « {TITRE} »": {
        "dans": "systeme", "etapes": [{"outil": "kanban_show", "arguments": {}}, _appel("projet_planifier", PLAN)],
        "resume_final": "Plan posé : une implémentation."},
    f"rôle « synthese » — projet « {TITRE} »": {
        "dans": "systeme", "etapes": [_appel("projet_etat")], "resume_final": "Conclusion : outil.py écrit."},
}


def _demarrer_modele(hermes: Conteneur) -> None:
    hermes.executer(["sh", "-c", f"cat > {SCENARIOS}"], utilisateur="hermes",
                    entree=json.dumps(SCENARIOS_PARCOURS, ensure_ascii=False), verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", "reglage", "emetteur_intervalle_s", "5"],
                             utilisateur="hermes", delai=120)
    assert sortie.returncode == 0, sortie.stderr[-2000:]


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/idp_factice.py", "--emetteur",
           "https://idp.acp.test:8443", "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem",
           "--cle", "/opt/acp-tests/ac/idp.key")
    ntfy = ressources.nom("ntfy")
    ressources.conteneurs.append(ntfy)
    docker("run", "-d", "--name", ntfy, "--network", reseau, "--network-alias", "ntfy.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/notif_factice.py", "--port", "443",
           "--certificat", "/opt/acp-tests/ac/ntfy.pem", "--cle", "/opt/acp-tests/ac/ntfy.key",
           "--journal", JOURNAL_NTFY)
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, ENV_PARCOURS, volume=volume, reseau=reseau)
    _demarrer_modele(hermes)
    return {"hermes": hermes, "ntfy": ntfy, "volume": volume, "reseau": reseau}


def jeton_oidc(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def api(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None):
    commande = ["curl", "-s", "-o", "/tmp/acp-reponse-parcours", "-w", "%{http_code}", "-X", methode,
                f"http://127.0.0.1:9119{P}{chemin}", "-H", f"Authorization: Bearer {jeton_oidc(hermes)}"]
    if corps is not None:
        commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
    code = int(hermes.executer(commande, verifier=True).stdout.strip())
    contenu = hermes.executer(["cat", "/tmp/acp-reponse-parcours"], verifier=True).stdout
    try:
        return code, json.loads(contenu)
    except ValueError:
        return code, contenu


def outil(hermes: Conteneur, script: str, *arguments: str) -> Dict[str, Any]:
    sortie = hermes.executer([PYTHON, script, *arguments], utilisateur="hermes", delai=120)
    assert sortie.returncode == 0, (arguments, sortie.returncode, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def reclamer(hermes: Conteneur, voies: str = "poste-claude", en_cours: Optional[str] = None) -> Dict[str, Any]:
    arguments = ["reclamer", "--voies", voies, "--attente", "5"]
    if en_cours:
        arguments += ["--en-cours", en_cours]
    reponse = outil(hermes, FAUX, *arguments)
    assert reponse["statut"] == 200, reponse
    return reponse["corps"]


def envoyer(hermes: Conteneur, route: str, **champs) -> Dict[str, Any]:
    return outil(hermes, FAUX, "envoyer", route, "--champs", json.dumps(champs, ensure_ascii=False))


def lire_tache(hermes: Conteneur, tableau: str, carte: str) -> Dict[str, Any]:
    code = ("import json\n"
            "from hermes_cli.kanban_db_connect import connect\n"
            f"c = connect(board={tableau!r})\n"
            f"r = c.execute('SELECT status FROM tasks WHERE id = ?', ({carte!r},)).fetchone()\n"
            "print(json.dumps({'status': r[0] if r else None}))\n")
    sortie = hermes.executer([PYTHON, "-c", code], utilisateur="hermes", verifier=True,
                             env={"HERMES_HOME": "/opt/data"}).stdout
    return json.loads(sortie.strip().splitlines()[-1])


def notifications(ntfy: str) -> List[Dict[str, Any]]:
    brut = docker("exec", ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def du_projet(ntfy: str) -> List[Dict[str, Any]]:
    return [n for n in notifications(ntfy) if f"« {TITRE} »" in n.get("corps", "")]


def attendre(predicat, delai: float, message: str, pas: float = 2.0):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def _recopier_l_executant(ancien: str, nouveau: str) -> None:
    """L'exécutant garde son jeton et sa dernière carte dans SON stockage : ici /tmp du conteneur de test, recopié
    d'un conteneur à l'autre (rien n'est affiché ; le jeton ne quitte pas les fichiers)."""
    with tempfile.TemporaryDirectory(prefix="acp-parcours-") as dossier:
        for chemin in ("/tmp/faux-poste", "/tmp/faux-executant"):
            docker("cp", f"{ancien}:{chemin}", str(Path(dossier) / Path(chemin).name))
            docker("cp", str(Path(dossier) / Path(chemin).name), f"{nouveau}:/tmp/")
    docker("exec", nouveau, "chown", "-R", "hermes:hermes", "/tmp/faux-poste", "/tmp/faux-executant")


def test_redeploiement_pendant_une_question_puis_projet_termine(pile, ressources, image_tests):
    hermes, ntfy = pile["hermes"], pile["ntfy"]
    preuves: Dict[str, Any] = {}
    # ------------------------------------------------------------ exécutant enrôlé, projet, question
    code, cree = api(hermes, "POST", "/v1/poste/enrolement", {})
    assert code == 201, cree
    enrole = outil(hermes, FAUX_POSTE, "enroler", cree["code"], "--nom", "Exécutant Railway")
    code, confirme = api(hermes, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                     "empreinte": enrole["empreinte"]})
    assert code == 200, confirme
    assert outil(hermes, FAUX, "inventaire", "--regime", "B")["statut"] == 200
    code, lance = api(hermes, "POST", "/v1/projets", {
        "titre": TITRE, "objectif": "Écrire outil.py dans le dépôt jetable.", "depot": "jetable",
        "reponses": "proprietaire", "exploration": {"voie": "poste-claude", "modele": "opus", "effort": "low"}})
    assert code == 201, lance
    projet = lance["projet"]
    exploration = reclamer(hermes)["carte"]
    assert exploration and exploration["role"] == "exploration" and exploration["tableau"] == projet["tableau"]
    posee = envoyer(hermes, "question", texte=QUESTION, contexte="Le dépôt ne contient encore aucun module.")
    assert posee["statut"] == 200 and posee["corps"]["etat"] == "escaladee", posee
    question = posee["corps"]["question"]
    assert lire_tache(hermes, exploration["tableau"], exploration["carte"])["status"] == "scheduled"
    recue = attendre(lambda: [n for n in du_projet(ntfy) if "une question attend votre réponse" in n["corps"]], 90,
                     "notification « question » non reçue")
    assert [n["click"] for n in recue] == [f"https://hermes.acp.test/projets?vue=questions&q={question}"]
    code, file = api(hermes, "GET", "/v1/questions")
    [avant] = [q for q in file["questions"] if q["id"] == question]
    preuves["avant_redeploiement"] = {"question": avant, "notification": recue[0]}

    # ------------------------------------------------------------ redéploiement : même volume, nouveau conteneur
    ancien = hermes.nom
    # Le conteneur est recréé AVEC le même volume ; l'ancien est d'abord arrêté (un seul Hermes sur le volume).
    docker("stop", "-t", "30", ancien, delai=180)
    hermes = lancer(ressources, image_tests, ENV_PARCOURS, volume=pile["volume"], reseau=pile["reseau"])
    _recopier_l_executant(ancien, hermes.nom)
    docker("rm", "-f", "-v", ancien, delai=180)
    pile["hermes"] = hermes
    _demarrer_modele(hermes)
    journal = hermes.journaux()
    lignes = [l for l in journal.splitlines() if l.startswith("[acp]") and ("scripts" in l or "bilan" in l)]
    afficher("redéploiement : gardes du second démarrage (même volume)", "\n".join(lignes))
    assert "inspectés : vides (hors acp-bilan.py, admis par son empreinte)" in journal
    assert "[acp] REFUS" not in journal
    code, file = api(hermes, "GET", "/v1/questions")
    assert code == 200
    [apres] = [q for q in file["questions"] if q["id"] == question]
    assert {k: apres[k] for k in ("id", "texte", "etat", "carte", "chez")} == \
        {k: avant[k] for k in ("id", "texte", "etat", "carte", "chez")}
    assert apres["etat"] == "escaladee" and apres["chez"] == "proprietaire"
    assert lire_tache(hermes, exploration["tableau"], exploration["carte"])["status"] == "scheduled"
    rien = reclamer(hermes)
    assert rien["carte"] is None, rien  # long-poll repris : la carte attend la réponse
    time.sleep(12)  # deux passes de l'émetteur après le redémarrage : aucune notification en double
    assert len([n for n in du_projet(ntfy) if "une question attend votre réponse" in n["corps"]]) == 1
    preuves["apres_redeploiement"] = {"question": apres, "reclamer": rien}

    # ------------------------------------------------------------ réponse, reprise du fil, fin du projet
    code, repondue = api(hermes, "POST", f"/v1/questions/{question}/reponse", {"reponse": REPONSE})
    assert code == 200 and repondue["carte_debloquee"] is True, repondue
    reprise = attendre(lambda: reclamer(hermes)["carte"], 60, "carte non resservie après la réponse")
    assert reprise["carte"] == exploration["carte"] and reprise["reprise"] is True
    assert [r["texte"] for r in reprise["reponses"]] == [REPONSE]
    fin = envoyer(hermes, "terminer", resume="## Structure\nUn module à écrire : outil.py.")
    assert fin["statut"] == 200 and fin["corps"]["etat"] == "done", fin
    implementation = attendre(lambda: reclamer(hermes)["carte"], 240,
                              "implémentation jamais servie (planification par le modèle factice)", pas=3)
    assert implementation["role"] == "implementation" and implementation["voie"] == "poste-claude"
    fin = envoyer(hermes, "terminer", resume="outil.py écrit et vérifié.")
    assert fin["statut"] == 200 and fin["corps"]["etat"] == "done", fin
    integration = attendre(lambda: reclamer(hermes, voies="poste-claude,poste-integration")["carte"], 240,
                           "intégration jamais servie (synthèse par le modèle factice)", pas=3)
    assert integration["role"] == "integration" and integration["voie"] == "poste-integration"
    assert integration["branches_a_integrer"] == [implementation["branche"]]
    fin = envoyer(hermes, "terminer", resume="Branche intégrée, vérification réussie.")
    assert fin["statut"] == 200 and fin["corps"]["etat"] == "done", fin

    def termine():
        code, detail = api(hermes, "GET", f"/v1/projets/{projet['id']}")
        return detail["projet"] if code == 200 and detail["projet"]["etat"] == "termine" else None

    fini = attendre(termine, 120, "le projet n'est pas arrivé à « terminé »")
    finales = attendre(lambda: (lambda n: n if any("prête sur l'exécutant" in x["corps"] for x in n) else None)(
        du_projet(ntfy)), 90, "notification « integration » non reçue")
    preuves["fin"] = {"etat": fini["etat"], "cartes": [(c["role"], c["statut"]) for c in fini["cartes"]],
                      "notifications": [(n["corps"], n["click"]) for n in finales]}
    afficher("parcours P7 : redéploiement pendant une question, puis projet terminé",
             json.dumps(preuves, ensure_ascii=False, indent=1, default=str))
    integrations = [n for n in finales if "prête sur l'exécutant" in n["corps"]]
    assert len(integrations) == 1 and integrations[0]["click"] == f"https://hermes.acp.test/projets?projet={projet['id']}"
    assert not any(" terminé : " in n["corps"] and "cartes faites" in n["corps"] for n in finales)  # K12
    questions = [n for n in finales if "une question attend votre réponse" in n["corps"]]
    assert len(questions) == 1
