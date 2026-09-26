"""Contrat de l'étape P4, piloté depuis l'hôte (voir conftest.py) : projets autonomes sur Hermes, testés
SANS le PC, sur la pile complète (s6, passerelle, tableau de bord, workers kanban réels).

Pile : faux fournisseur d'identité, modèle factice à scénarios (hermes/tests/outils/modele_factice.py),
faux serveur ntfy en HTTPS (``ntfy.acp.test``, outils/notif_factice.py), volume jetable avec
``kanban.dispatch_interval_seconds: 5``, canal ``ntfy`` configuré par les variables ``ACP_NTFY_*`` (valeurs de
TEST, forme hors des motifs du balayage des secrets), et un POSTE SIMULÉ (outils/poste_simule.py) qui joue le
rôle du poste Windows par l'API kanban et les fonctions du greffon (routes machine : P5-P6).

Ce qui est prouvé ici, sur l'image réellement construite :
- routes derrière la VRAIE porte d'authentification du tableau de bord (401), anti-CSRF (415, 403) ;
- émetteur de notifications DANS la passerelle (passe datée, lue par /v1/meta), envoi réel en HTTPS au faux
  ntfy, une seule notification par événement ;
- projet sans dépôt de bout en bout : planification, cartes Hermes, synthèse gardée par ses parents,
  projet terminé, notification « terminé » unique ;
- projet sur dépôt avec le poste simulé : exploration, planification relancée, relecture croisée, synthèse
  gardée, trois tours puis plafond (triage et notification uniques) ;
- outils réellement offerts au worker (différés derrière tool_search, appelés par tool_call), refus de
  kanban_create, mémoire mise en attente, carte poste-* étrangère bloquée, pauses, présence, questions,
  lancement depuis la discussion, refus de démarrer sur des crochets shell.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

import pytest

from conftest import (ENV_VALIDE, Conteneur, afficher, attendre_modele_factice, demarrer_jusqu_a_l_arret, docker,
                      lancer)

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
SCENARIOS = "/tmp/acp-scenarios.json"
JOURNAL_NTFY = "/tmp/ntfy.jsonl"
# Valeurs de TEST (jamais de vrais secrets), formes hors des motifs de scripts/balayer_secrets.py.
SUJET = "acp_sujet_de_test_0123"
JETON = "jeton-de-test-acp-p4"
ENV_P4 = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test", ACP_NTFY_SUJET=SUJET,
              ACP_NTFY_JETON=JETON)
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
MARQUEUR_EXPLORATION = "EXPLORATION-TEMOIN-7F3A"
INTERDITS = {"terminal", "read_file", "write_file", "patch", "search_files", "execute_code", "cronjob_manage",
             "delegate_task", "manage_connections", "process_manage", "computer_use"}


# =========================================================================== pile et utilitaires


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
    hermes = lancer(ressources, image_tests, ENV_P4, volume=volume, reseau=reseau)
    hermes.sh("mkdir -p /tmp/acp-temoins && chmod 1777 /tmp/acp-temoins", verifier=True)
    hermes.executer(["sh", "-c", f"echo '{{}}' > {SCENARIOS}"], utilisateur="hermes", verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", "10"), ("projets_actifs_max", "30"),
                        ("lancements_discussion_par_jour", "30")):
        simule(hermes, "reglage", cle, valeur)
    hermes.ntfy = ntfy  # type: ignore[attr-defined]
    return hermes


def jeton(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def api(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None, *, avec_jeton: bool = True,
        entetes: Optional[Dict[str, str]] = None, brut: Optional[str] = None):
    """(code, JSON) d'une requête au VRAI tableau de bord, en bouclage local, avec la session OIDC."""
    commande = ["curl", "-s", "-o", "/tmp/acp-reponse-p4", "-w", "%{http_code}", "-X", methode,
                f"http://127.0.0.1:9119{P}{chemin}"]
    if avec_jeton:
        commande += ["-H", f"Authorization: Bearer {jeton(hermes)}"]
    for cle, valeur in (entetes or {}).items():
        commande += ["-H", f"{cle}: {valeur}"]
    if corps is not None or brut is not None:
        if not any(k.lower() == "content-type" for k in (entetes or {})):
            commande += ["-H", "Content-Type: application/json"]
        commande += ["--data-binary", brut if brut is not None else json.dumps(corps, ensure_ascii=False)]
    code = int(hermes.executer(commande, verifier=True).stdout.strip())
    contenu = hermes.executer(["cat", "/tmp/acp-reponse-p4"], verifier=True).stdout
    try:
        return code, json.loads(contenu)
    except ValueError:
        return code, contenu


def simule(hermes: Conteneur, *arguments: str, attendu: int = 0) -> Dict[str, Any]:
    """Poste SIMULÉ (outils/poste_simule.py), sous l'uid hermes, avec le HERMES_HOME du conteneur."""
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments], utilisateur="hermes",
                             delai=120)
    assert sortie.returncode == attendu, (arguments, sortie.returncode, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def cartes(hermes: Conteneur, tableau: str) -> Dict[str, Dict[str, Any]]:
    return {c["id"]: c for c in simule(hermes, "cartes", tableau)["cartes"]}


def ajouter_scenarios(hermes: Conteneur, nouveaux: Dict[str, Any]) -> None:
    actuels = json.loads(hermes.sh(f"cat {SCENARIOS}", verifier=True).stdout or "{}")
    marqueurs = sorted(set(actuels.get("_marqueurs", [])) | set(nouveaux.pop("_marqueurs", [])))
    actuels.update(nouveaux)
    if marqueurs:
        actuels["_marqueurs"] = marqueurs
    hermes.executer(["sh", "-c", f"cat > {SCENARIOS}"], utilisateur="hermes", entree=json.dumps(actuels,
                    ensure_ascii=False), verifier=True)


def requetes(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = hermes.sh(f"cat {JOURNAL_FACTICE} 2>/dev/null", verifier=True).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def requetes_du_role(hermes: Conteneur, role: str, titre: str) -> List[Dict[str, Any]]:
    cle = f"rôle « {role} » — projet « {titre} »"
    return [r for r in requetes(hermes) if r.get("methode") == "POST" and cle in (r.get("section_acp") or "")]


def notifications_ntfy(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = docker("exec", hermes.ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def attendre(predicat: Callable[[], Any], delai: float, message: str, pas: float = 2.0) -> Any:
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def scenario(etapes: List[Dict[str, Any]], resume: str) -> Dict[str, Any]:
    return {"dans": "systeme", "etapes": etapes, "resume_final": resume}


def appel(nom: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Étape de scénario : un outil du greffon, DIFFÉRÉ par Hermes, appelé par le pont tool_call."""
    return {"outil": "tool_call", "arguments": {"calls": [{"name": nom, "arguments": arguments or {}}]}}


def lancer_projet(hermes: Conteneur, **corps) -> Dict[str, Any]:
    code, reponse = api(hermes, "POST", "/v1/projets", corps)
    assert code == 201, (code, reponse)
    return reponse["projet"]


def _projet_du_titre(hermes: Conteneur, titre: str) -> str:
    code, liste = api(hermes, "GET", "/v1/projets")
    assert code == 200
    [projet] = [p["id"] for p in liste["projets"] if p["titre"] == titre]
    return projet


def detail(hermes: Conteneur, projet: str) -> Dict[str, Any]:
    code, reponse = api(hermes, "GET", f"/v1/projets/{projet}")
    assert code == 200, reponse
    return reponse["projet"]


def meta_projets(hermes: Conteneur) -> Dict[str, Any]:
    code, meta = api(hermes, "GET", "/v1/meta")
    assert code == 200
    return meta


# =========================================================================== 1. routes


ROUTES = [("GET", "/v1/projets"), ("POST", "/v1/projets"), ("GET", "/v1/questions"), ("POST", "/v1/pause"),
          ("GET", "/v1/poste"), ("POST", "/v1/notifications/test"), ("GET", "/v1/projets/p_x"),
          ("POST", "/v1/questions/q_x/reponse")]


def test_routes_sans_session_401(pile):
    codes = {f"{m} {c}": api(pile, m, c, {} if m == "POST" else None, avec_jeton=False)[0] for m, c in ROUTES}
    afficher("routes P4 sans session", json.dumps(codes, indent=1))
    assert set(codes.values()) == {401}


def test_ecriture_sans_json_415_et_origine_403(pile):
    code, reponse = api(pile, "POST", "/v1/projets", brut="titre=x", entetes={"Content-Type": "text/plain"})
    assert code == 415 and reponse["detail"]["message"] == "Requête refusée : corps JSON attendu."
    code, reponse = api(pile, "POST", "/v1/pause", {"generale": True}, entetes={"Origin": "https://intrus.example"})
    assert code == 403 and reponse["detail"]["message"] == "Requête refusée : origine « https://intrus.example » non autorisée."
    code, lecture = api(pile, "GET", "/v1/projets")
    assert code == 200 and lecture["pause_generale"] is None  # la pause refusée n'a rien engagé


def test_emetteur_tourne_dans_la_passerelle(pile):
    def passe_recente():
        projets = meta_projets(pile)["projets"]
        emetteur = projets.get("emetteur") or {}
        return projets if emetteur.get("processus") == "passerelle" and emetteur.get("derniere_passe") else None

    projets = attendre(passe_recente, 90, "aucune passe de l'émetteur dans la passerelle")
    afficher("/v1/meta : bloc projets", json.dumps(projets, ensure_ascii=False, indent=1))
    emetteur = projets["emetteur"]
    assert time.time() - emetteur["derniere_passe"] < 60
    assert emetteur["canal"] == "ntfy" and emetteur["configure"] is True
    assert projets["base"] == "ok" and projets["schema"] == "1" and projets["pause_generale"] is None
    assert JETON not in json.dumps(projets)  # jamais le jeton (ni le sujet) dans une réponse


def test_notification_de_test_envoyee_par_la_passerelle(pile):
    """Bouton « Envoyer une notification de test » de la page Projets (seconde partie de P4) : la route la met
    en file (202), la passerelle l'envoie au faux ntfy à sa passe suivante, une seule fois."""
    avant = len(notifications_ntfy(pile))
    code, reponse = api(pile, "POST", "/v1/notifications/test", {})
    assert code == 202 and reponse["etat"] == "en_attente", (code, reponse)
    envoyees = attendre(lambda: [n for n in notifications_ntfy(pile)[avant:] if "Notification de test" in n["corps"]],
                        60, "la notification de test n'est pas parvenue au faux ntfy")
    afficher("faux ntfy : notification de test", json.dumps(envoyees, ensure_ascii=False, indent=1))
    assert [n["corps"] for n in envoyees] == ["ACP — Notification de test envoyée depuis la page Projets."]
    assert envoyees[0]["autorisation_presente"] and envoyees[0]["title"] == "ACP"
    time.sleep(11)  # deux passes de plus : toujours une seule
    assert len([n for n in notifications_ntfy(pile)[avant:] if "Notification de test" in n["corps"]]) == 1


# =========================================================================== 2. projet sans dépôt


PLAN_SANS_DEPOT = {"resume": "Deux recherches puis synthèse.", "decisions": ["Sources de moins d'un an"],
                   "etapes": [
                       {"ref": "e1", "titre": "Chercher les modèles", "classe": "recherche_web",
                        "consigne": "Recenser les modèles publiés ce mois."},
                       {"ref": "e2", "titre": "Chercher les prix", "classe": "recherche_web",
                        "consigne": "Relever leurs prix publics."}]}


def test_projet_sans_depot_de_bout_en_bout(pile):
    titre = "Veille contrat"
    ajouter_scenarios(pile, {
        f"rôle « planification » — projet « {titre} »": scenario(
            [{"outil": "kanban_show", "arguments": {}}, appel("poste_catalogue"), appel("projet_planifier", PLAN_SANS_DEPOT)],
            "Plan posé : deux recherches."),
        f"rôle « hermes » — projet « {titre} »": scenario(
            [{"outil": "memory"}, {"outil": "kanban_create"}, {"outil": "kanban_show", "arguments": {}}],
            "Recherche faite (témoin)."),
        f"rôle « synthese » — projet « {titre} »": scenario([appel("projet_etat")], "Conclusion : deux recherches faites."),
    })
    avant_ntfy = len(notifications_ntfy(pile))
    projet = lancer_projet(pile, titre=titre, objectif="Veille des modèles de langage.", profil="recherche",
                           depot=None, reponses="hermes_d_abord")
    fini = attendre(lambda: detail(pile, projet["id"])["etat"] == "termine" and detail(pile, projet["id"]), 360,
                    "le projet sans dépôt n'est pas arrivé au bout")
    toutes = cartes(pile, projet["tableau"])
    par_role = {}
    for c in fini["cartes"]:
        par_role.setdefault(c["role"], []).append(toutes[c["carte"]])
    afficher("projet sans dépôt : cartes", json.dumps(fini["cartes"], ensure_ascii=False, indent=1))
    assert [c["statut"] for c in fini["cartes"]] == ["done"] * 4
    assert {c["assigne"] for c in toutes.values()} == {"default"} and len(toutes) == 4
    # La synthèse n'est partie qu'APRÈS ses deux parents.
    synthese = requetes_du_role(pile, "synthese", titre)
    assert synthese, "la synthèse n'a jamais interrogé le modèle"
    fins = [c["fini_le"] for c in par_role["hermes"]]
    assert min(r["t"] for r in synthese) >= max(fins), (synthese[0]["t"], fins)
    # Notifications : UNE « terminé », aucune pour les fins intermédiaires.
    nouvelles = [n for n in notifications_ntfy(pile)[avant_ntfy:] if titre in n["corps"]]
    afficher("faux ntfy : notifications du projet", json.dumps(nouvelles, ensure_ascii=False, indent=1))
    assert [n["corps"] for n in nouvelles] == [f"ACP — Projet « {titre} » terminé : 4 cartes faites."]
    n = nouvelles[0]
    assert n["chemin"] == f"/{SUJET}" and n["autorisation_presente"] and n["title"] == "ACP" and n["priority"] == "3"
    assert n["click"] == f"https://hermes.acp.test/projets?projet={projet['id']}"
    time.sleep(12)  # deux passes de plus : toujours une seule
    assert len([x for x in notifications_ntfy(pile) if titre in x["corps"]]) == 1


def test_outils_offerts_au_worker_de_planification(pile):
    """Liste imprimée des outils du worker de planification (projet du test précédent) : les outils du greffon
    sont DIFFÉRÉS par Hermes derrière tool_search (tools/tool_search.py:150-162) et appelés par tool_call."""
    premiere = requetes_du_role(pile, "planification", "Veille contrat")
    assert premiere, "aucune requête du worker de planification"
    offerts, catalogue = premiere[0]["outils_offerts"], premiere[0]["catalogue_differe"] or ""
    afficher("worker de planification : outils offerts", json.dumps(offerts) + "\n--- catalogue différé ---\n" + catalogue)
    assert {"kanban_show", "kanban_complete", "tool_call", "tool_describe", "tool_search"} <= set(offerts)
    assert not (set(offerts) & INTERDITS) and not any(o.startswith("browser_") for o in offerts)
    for nom in ("projet_planifier", "projet_etat", "poste_catalogue", "poste_etat", "question_repondre",
                "question_escalader"):
        assert nom in catalogue, nom
    for nom in ("projet_lancer", "routage_surcharger", "terminal"):
        assert nom not in catalogue and nom not in offerts, nom
    # kanban_create et kanban_attach_url restent OFFERTS par Hermes au worker (jeu kanban), et refusés par la
    # garde à l'appel (P2 ; test suivant).
    assert {"kanban_create", "kanban_attach_url"} <= set(offerts) and "kanban_create" not in catalogue
    resultats = [r["contenu"] for q in premiere for r in q.get("resultats_outils") or []]
    assert any('"ok": true, "tour": 1' in r for r in resultats), resultats


def test_kanban_create_et_memoire_refuses_dans_un_worker(pile):
    """kanban_create reste refusé par la garde. Mesuré au premier passage de ce contrat : dans un worker
    « chat -q », une écriture en mémoire ouvrait l'invite d'approbation en ligne du CLI, qui attendait 300 s
    sans personne (la carte restait bloquée cinq minutes) avant de mettre l'écriture en attente. Depuis, la
    garde refuse memory dans un worker kanban, tout de suite ; rien n'est écrit ni mis en attente."""
    hermes_requetes = requetes_du_role(pile, "hermes", "Veille contrat")
    resultats = [r["contenu"] for q in hermes_requetes for r in q.get("resultats_outils") or []]
    afficher("worker Hermes : résultats d'outils", json.dumps(resultats, ensure_ascii=False, indent=1)[:4000])
    assert any("Refusé par ACP : l'agent ne crée pas de carte kanban lui-même" in r for r in resultats)
    assert any("Refusé par ACP : une carte kanban n'écrit pas en mémoire" in r for r in resultats), resultats
    en_attente = pile.sh("ls /opt/data/pending/memory/ 2>/dev/null | wc -l", verifier=True).stdout.strip()
    memoire = pile.sh("cat /opt/data/memories/MEMORY.md 2>/dev/null; cat /opt/data/MEMORY.md 2>/dev/null",
                      verifier=False).stdout
    assert int(en_attente) == 0 and "témoin ACP P4" not in memoire
    # Les cartes Hermes n'ont pas attendu : chacune a fini en moins d'une minute après sa première requête.
    for carte in [c for c in cartes(pile, detail(pile, _projet_du_titre(pile, "Veille contrat"))["tableau"]).values()
                  if c["titre"].startswith("Recherche web")]:
        assert carte["fini_le"] - carte["debut"] < 60, carte


# =========================================================================== 3. projet sur dépôt, poste simulé


def _releves(pile):
    for voie in ("poste-codex", "poste-claude"):
        releve = {"voie": voie, "source": "releve_factice", "version_cli": "0.0.0-factice",
                  "releve_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                  "modeles": [{"id": f"factice-{voie[6:]}-1", "isDefault": True,
                               "supportedReasoningEfforts": ["low", "medium", "extreme"],
                               "defaultReasoningEffort": "medium", "serviceTiers": ["default"]}],
                  "depots": [{"alias": "jetable"}]}
        simule(pile, "releve-factice", json.dumps(releve))


def _plan_impl(effort: str = "extreme") -> Dict[str, Any]:
    return {"resume": "Écrire l'outil.", "decisions": ["Python 3.12"], "etapes": [
        {"ref": "e1", "titre": "Écrire outil.py", "classe": "implementation", "consigne": "Écrire outil.py.",
         "voie": "poste-codex", "effort": effort}]}


def _finir_cartes_du_poste(pile, tableau: str, identifiants: List[str]) -> None:
    for identifiant in identifiants:
        simule(pile, "reclamer", tableau, identifiant)
        simule(pile, "terminer", tableau, identifiant, f"Fait par le poste simulé ({identifiant}).")


def test_projet_sur_depot_exploration_par_le_poste_simule(pile):
    titre = "Outil sur depot"
    _releves(pile)
    ajouter_scenarios(pile, {
        "_marqueurs": [MARQUEUR_EXPLORATION],
        f"rôle « planification » — projet « {titre} »": scenario(
            [{"outil": "kanban_show", "arguments": {}}, appel("projet_planifier", _plan_impl())], "Plan posé."),
        f"rôle « synthese » — projet « {titre} »": scenario([appel("projet_etat")], "Conclusion."),
    })
    projet = lancer_projet(pile, titre=titre, objectif="Écrire un outil dans le dépôt jetable.", profil="base",
                           depot="jetable", exploration={"voie": "poste-claude", "modele": "factice-claude-1",
                                                         "effort": "low"})
    exploration = projet["cartes"]["exploration"]
    # La carte du poste reste prête (jamais lancée par Hermes) ; la planification attend.
    attendre(lambda: (meta_projets(pile)["projets"]["emetteur"]["derniers_ticks"] or {}).get(projet["tableau"]), 60,
             "le répartiteur n'a pas vu la carte du poste (skipped_nonspawnable)")
    etat = cartes(pile, projet["tableau"])
    assert etat[exploration]["statut"] == "ready" and etat[exploration]["assigne"] == "poste-claude"
    assert etat[exploration]["reclamation"] is None
    assert etat[projet["cartes"]["planification"]]["statut"] == "todo"
    simule(pile, "reclamer", projet["tableau"], exploration)
    simule(pile, "terminer", projet["tableau"], exploration, f"Carte du dépôt : {MARQUEUR_EXPLORATION}.")
    planif = projet["cartes"]["planification"]
    lancee = attendre(lambda: cartes(pile, projet["tableau"])[planif]["debut"], 40,
                      "la planification n'a pas été lancée après l'exploration")
    premiere = attendre(lambda: requetes_du_role(pile, "planification", titre), 90,
                        "le worker de planification n'a pas interrogé le modèle")
    # Fin et lancement lus sur la MÊME horloge, celle des conteneurs (completed_at et started_at de Hermes, en
    # secondes entières) : l'heure de l'hôte, prise après le retour de « docker exec », a déjà donné un délai
    # négatif (-0,6 s en CI) sans que l'ordre soit en cause.
    fin_exploration = cartes(pile, projet["tableau"])[exploration]["fini_le"]
    delai = lancee - fin_exploration
    afficher("délai fin d'exploration → planification lancée",
             f"réclamée par le répartiteur {delai} s après la fin de l'exploration (horloge des conteneurs, à la "
             f"seconde près ; passage toutes les 5 s) ; première requête du worker au modèle "
             f"{premiere[0]['t'] - fin_exploration:.1f} s après")
    # Jamais avant la fin de l'exploration ; deux passages du répartiteur au plus (5 s chacun), plus une marge.
    assert 0 <= delai <= 12, delai
    attendre(lambda: any(MARQUEUR_EXPLORATION in (r.get("marqueurs_trouves") or [])
                         for r in requetes_du_role(pile, "planification", titre)), 60,
             "le résumé de l'exploration n'est pas parvenu à la planification (kanban_show)")
    tour = attendre(lambda: detail(pile, projet["id"])["tour"] == 1 and detail(pile, projet["id"]), 90,
                    "le tour 1 n'a pas été planifié")
    impl = next(c for c in tour["cartes"] if c["role"] == "implementation")
    # Effort hors de l'énumération de Hermes : exact dans la demande, jamais posé sur la carte.
    assert (impl["effort"], impl["effort_carte"]) == ("extreme", None)
    montre = json.loads(pile.executer(["sh", "-c", f"cd /opt/data && hermes kanban --board {projet['tableau']} show "
                                                  f"{impl['carte']} --json"], utilisateur="hermes", verifier=True).stdout)
    tache = montre.get("task", montre)
    # « hermes kanban show --json » ne publie pas reasoning_effort (hermes_cli/kanban_output.py:18-24) : lu
    # par kanban_db.get_task, le module de Hermes lui-même, sans passer par le greffon.
    effort = pile.python(
        "import json, sys\nfrom hermes_cli.kanban_db import get_task\nfrom hermes_cli.kanban_db_connect import connect\n"
        f"c = connect(board={projet['tableau']!r})\nt = get_task(c, {impl['carte']!r})\n"
        "print(json.dumps({'reasoning_effort': t.reasoning_effort, 'model_override': t.model_override}))",
        utilisateur="hermes", env={"HERMES_HOME": "/opt/data"}, verifier=True).stdout.strip().splitlines()[-1]
    afficher("hermes kanban show --json (implémentation) et kanban_db.get_task", json.dumps({k: tache.get(k) for k in (
        "assignee", "model_override", "created_by", "status")}, ensure_ascii=False) + "\n" + effort)
    assert tache["model_override"] == "factice-codex-1" and tache["assignee"] == "poste-codex"
    assert json.loads(effort) == {"reasoning_effort": None, "model_override": "factice-codex-1"}


def test_graphe_complet_relecture_et_synthese_gardee(pile):
    titre = "Graphe complet"
    _releves(pile)
    ajouter_scenarios(pile, {
        f"rôle « planification » — projet « {titre} »": scenario([appel("projet_planifier", _plan_impl("low"))],
                                                                 "Plan posé."),
        f"rôle « synthese » — projet « {titre} »": scenario([appel("projet_planifier", _plan_impl("low"))],
                                                            "Tour suivant planifié."),
    })
    avant_ntfy = len(notifications_ntfy(pile))
    projet = lancer_projet(pile, titre=titre, objectif="Trois tours puis plafond.", profil="base", depot="jetable",
                           exploration={"voie": "poste-codex"})
    _finir_cartes_du_poste(pile, projet["tableau"], [projet["cartes"]["exploration"]])
    for tour in (1, 2, 3):
        fiche = attendre(lambda: detail(pile, projet["id"])["tour"] == tour and detail(pile, projet["id"]), 120,
                         f"le tour {tour} n'a pas été planifié")
        du_tour = [c for c in fiche["cartes"] if c["tour"] == tour]
        impl = next(c for c in du_tour if c["role"] == "implementation")
        rel = next(c for c in du_tour if c["role"] == "relecture")
        synth = next(c for c in du_tour if c["role"] == "synthese")
        assert (impl["voie"], rel["voie"], rel["relue"]) == ("poste-codex", "poste-claude", f"acp:{projet['id']}:t{tour}:e1:implementation")
        _finir_cartes_du_poste(pile, projet["tableau"], [impl["carte"]])
        time.sleep(11)  # deux passages du répartiteur : la synthèse reste gardée par la relecture
        assert cartes(pile, projet["tableau"])[synth["carte"]]["statut"] == "todo"
        _finir_cartes_du_poste(pile, projet["tableau"], [rel["carte"]])
    # La synthèse du tour 3 demande un 4e tour : refus, UNE carte de triage, UNE notification « plafond ».
    triage = attendre(lambda: [c for c in cartes(pile, projet["tableau"]).values() if c["statut"] == "triage"], 120,
                      "aucune carte de triage au plafond des tours")
    time.sleep(12)
    triage = [c for c in cartes(pile, projet["tableau"]).values() if c["statut"] == "triage"]
    notifs = [n for n in notifications_ntfy(pile)[avant_ntfy:] if titre in n["corps"]]
    afficher("plafond des tours", json.dumps({"triage": triage, "notifications": notifs}, ensure_ascii=False, indent=1))
    assert [c["titre"] for c in triage] == ["Plafond atteint : tours — votre décision est attendue"]
    assert [n["corps"] for n in notifs] == [f"ACP — Projet « {titre} » : plafond de tours atteint, votre décision est attendue."]
    resultats = [r["contenu"] for q in requetes_du_role(pile, "synthese", titre) for r in q.get("resultats_outils") or []]
    assert any('"code": "plafond_tours"' in r for r in resultats)
    assert detail(pile, projet["id"])["etat_derive"] == "plafond_atteint"


def test_deux_reclamations_distantes_n_empechent_pas_un_autre_projet(pile):
    titre_a, titre_b = "Reclamations A", "Reclamations B"
    plan_a = {"resume": "Deux étapes.", "etapes": [
        {"ref": "e1", "titre": "Un", "classe": "implementation", "consigne": "Un.", "voie": "poste-codex"},
        {"ref": "e2", "titre": "Deux", "classe": "implementation", "consigne": "Deux.", "voie": "poste-claude"}]}
    ajouter_scenarios(pile, {
        f"rôle « planification » — projet « {titre_a} »": scenario([appel("projet_planifier", plan_a)], "Plan posé."),
        f"rôle « planification » — projet « {titre_b} »": scenario([appel("projet_etat")], "Rien à faire."),
    })
    _releves(pile)
    a = lancer_projet(pile, titre=titre_a, objectif="Occuper le poste.", depot="jetable",
                      exploration={"voie": "poste-claude"})
    _finir_cartes_du_poste(pile, a["tableau"], [a["cartes"]["exploration"]])
    fiche = attendre(lambda: detail(pile, a["id"])["tour"] == 1 and detail(pile, a["id"]), 120, "tour 1 de A")
    impls = [c["carte"] for c in fiche["cartes"] if c["role"] == "implementation"]
    for identifiant in impls:
        simule(pile, "reclamer", a["tableau"], identifiant)
    assert {cartes(pile, a["tableau"])[i]["statut"] for i in impls} == {"running"}
    b = lancer_projet(pile, titre=titre_b, objectif="Passer malgré le poste occupé.", depot=None)
    attendre(lambda: requetes_du_role(pile, "planification", titre_b), 60,
             "la planification du projet B n'a pas été lancée alors que deux cartes du poste sont réclamées")
    etat = cartes(pile, a["tableau"])
    afficher("réclamations distantes", json.dumps({i: etat[i] for i in impls}, ensure_ascii=False, indent=1))
    assert {etat[i]["statut"] for i in impls} == {"running"}  # ni orphelines ni « worker mort »
    assert {etat[i]["reclamation"] for i in impls} == {"acp-poste:simule"}
    assert b["id"]


# =========================================================================== 4. cartes étrangères, pauses


def test_carte_poste_etrangere_refusee(pile):
    # Sans scénario, le worker de planification répondrait sans kanban_complete : trois échecs, puis abandon
    # (constaté au contrat complet : notification « abandonnée » en fin de module). Il conclut ici.
    ajouter_scenarios(pile, {"rôle « planification » — projet « Etrangere »": scenario([appel("projet_etat")], "Vu.")})
    projet = lancer_projet(pile, titre="Etrangere", objectif="Témoin.", depot=None)
    avant_ntfy = len(notifications_ntfy(pile))
    sortie = pile.executer(["sh", "-c", f"cd /opt/data && hermes kanban --board {projet['tableau']} create "
                                        "'Carte à la main' --assignee poste-codex --json"], utilisateur="hermes",
                           verifier=True).stdout
    identifiant = json.loads(sortie)["id"]
    bloquee = attendre(lambda: cartes(pile, projet["tableau"])[identifiant]["statut"] == "blocked", 60,
                       "la carte poste-* étrangère n'a pas été bloquée")
    evenements = pile.executer(["sh", "-c", f"cd /opt/data && hermes kanban --board {projet['tableau']} show "
                                            f"{identifiant} --json"], utilisateur="hermes", verifier=True).stdout
    assert "Refusé par ACP : carte poste-* non émise par le greffon acp-poste ; seul le greffon crée les cartes du " \
           "poste." in evenements
    notif = attendre(lambda: [n for n in notifications_ntfy(pile)[avant_ntfy:] if "Etrangere" in n["corps"]], 60,
                     "aucune notification « bloquée »")
    afficher("carte poste-* étrangère", json.dumps({"bloquee": bloquee, "notification": notif}, ensure_ascii=False))
    assert notif[0]["corps"] == "ACP — Projet « Etrangere » : la carte « Carte à la main » est bloquée."


def test_pause_d_un_projet(pile):
    """Projet sur dépôt : la planification attend l'exploration du poste simulé, rien ne part tout seul."""
    titre = "Pause projet"
    ajouter_scenarios(pile, {f"rôle « planification » — projet « {titre} »": scenario([appel("projet_etat")], "Vu.")})
    _releves(pile)
    projet = lancer_projet(pile, titre=titre, objectif="Mise en pause.", depot="jetable",
                           exploration={"voie": "poste-claude"})
    exploration, planif = projet["cartes"]["exploration"], projet["cartes"]["planification"]
    code, pause = api(pile, "POST", f"/v1/projets/{projet['id']}/pause", {})
    assert code == 200 and pause["cartes_planifiees"] == [exploration, planif]
    etat = cartes(pile, projet["tableau"])
    assert (etat[exploration]["statut"], etat[planif]["statut"]) == ("scheduled", "scheduled")
    assert simule(pile, "reclamer", projet["tableau"], exploration, attendu=3) == {"reclamee": False}
    assert api(pile, "POST", f"/v1/projets/{projet['id']}/pause", {})[0] == 409
    code, reprise = api(pile, "POST", f"/v1/projets/{projet['id']}/reprise", {})
    assert code == 200 and sorted(reprise["cartes_reveillees"]) == sorted([exploration, planif])
    etat = cartes(pile, projet["tableau"])
    assert (etat[exploration]["statut"], etat[planif]["statut"]) == ("ready", "todo")
    _finir_cartes_du_poste(pile, projet["tableau"], [exploration])
    attendre(lambda: requetes_du_role(pile, "planification", titre), 60, "aucun worker après la reprise")


def test_pause_generale_aucun_worker(pile):
    titre = "Pause generale"
    ajouter_scenarios(pile, {f"rôle « planification » — projet « {titre} »": scenario([appel("projet_etat")], "Vu.")})
    _releves(pile)
    projet = lancer_projet(pile, titre=titre, objectif="Pause générale.", depot="jetable",
                           exploration={"voie": "poste-claude"})
    code, generale = api(pile, "POST", "/v1/pause", {"generale": True, "raison": "contrat"})
    assert code == 200 and generale["pause_generale"]["reason"] == "ACP : pause du propriétaire — contrat"
    try:
        assert api(pile, "POST", "/v1/projets", {"titre": "Refusé", "objectif": "o"})[0] == 409
        _finir_cartes_du_poste(pile, projet["tableau"], [projet["cartes"]["exploration"]])
        assert cartes(pile, projet["tableau"])[projet["cartes"]["planification"]]["statut"] == "ready"
        time.sleep(17)  # trois passages du répartiteur : aucun worker
        assert requetes_du_role(pile, "planification", titre) == []
        assert cartes(pile, projet["tableau"])[projet["cartes"]["planification"]]["statut"] == "ready"
        assert pile.sh("test -f /opt/data/ESTOP", verifier=False).returncode == 0
    finally:
        assert api(pile, "POST", "/v1/pause", {"generale": False})[1]["pause_generale"] is None
    attendre(lambda: requetes_du_role(pile, "planification", titre), 60, "aucun worker après la reprise générale")


# =========================================================================== 5. présence, questions, discussion


def test_poste_hors_ligne_une_notification(pile):
    avant = len(notifications_ntfy(pile))
    simule(pile, "presence", "poste-contrat")
    code, poste = api(pile, "GET", "/v1/poste")
    assert code == 200 and poste["poste"]["etat"] == "en_ligne"
    premiere = attendre(lambda: [n for n in notifications_ntfy(pile)[avant:] if "Poste hors ligne" in n["corps"]], 60,
                        "aucune notification « poste hors ligne »")
    time.sleep(12)
    assert len([n for n in notifications_ntfy(pile)[avant:] if "Poste hors ligne" in n["corps"]]) == 1
    assert premiere[0]["priority"] == "4"
    simule(pile, "presence", "poste-contrat")  # retour en ligne : nouveau passage
    attendre(lambda: len([n for n in notifications_ntfy(pile)[avant:] if "Poste hors ligne" in n["corps"]]) == 2, 60,
             "pas de seconde notification après un retour puis un nouveau silence")
    afficher("présence du poste simulé", json.dumps(notifications_ntfy(pile)[avant:], ensure_ascii=False, indent=1))


def test_question_repondue_par_hermes(pile):
    titre = "Question contrat"
    ajouter_scenarios(pile, {
        f"rôle « repondre » — projet « {titre} »": scenario(
            [appel("question_repondre", {"reponse": "Oui, garder Python 3.11.",
                                         "fondement": "Décision du projet : compatibilité 3.11."})], "Répondu."),
    })
    _releves(pile)
    projet = lancer_projet(pile, titre=titre, objectif="Question témoin.", depot="jetable",
                           exploration={"voie": "poste-claude"})
    exploration = projet["cartes"]["exploration"]
    simule(pile, "reclamer", projet["tableau"], exploration)
    question = simule(pile, "question", projet["tableau"], exploration, "Faut-il garder Python 3.11 ?")
    assert question["etat"] == "ouverte" and question["carte_repondre"]
    assert cartes(pile, projet["tableau"])[exploration]["statut"] == "scheduled"
    attendre(lambda: cartes(pile, projet["tableau"])[exploration]["statut"] == "ready", 120,
             "la carte du poste n'a pas été débloquée par la réponse de Hermes")
    code, liste = api(pile, "GET", "/v1/questions")
    assert code == 200 and not [q for q in liste["questions"] if q["id"] == question["question"]]
    commentaires = pile.executer(["sh", "-c", f"cd /opt/data && hermes kanban --board {projet['tableau']} show "
                                              f"{exploration} --json"], utilisateur="hermes", verifier=True).stdout
    assert "hermes (acp-questions)" in commentaires and "Fondement : Décision du projet" in commentaires


def test_discussion_lance_un_projet(pile):
    ajouter_scenarios(pile, {"rôle « planification » — projet « Projet témoin ACP »": scenario([appel("projet_etat")],
                                                                                              "Vu.")})
    sortie = pile.executer([PYTHON, "/opt/acp-tests/outils/client_ws.py", "prompt", jeton(pile), "/tmp/acp-ws-p4.json",
                            "OUTIL:tool_call>projet_lancer"], delai=400)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    code, liste = api(pile, "GET", "/v1/projets")
    temoins = [p for p in liste["projets"] if p["titre"] == "Projet témoin ACP"]
    afficher("discussion → projet_lancer", json.dumps(temoins, ensure_ascii=False, indent=1))
    assert len(temoins) == 1 and temoins[0]["origine"] == "discussion"
    # projet_planifier n'est pas offert à la discussion ; forcé par le pont, il est refusé.
    sortie = pile.executer([PYTHON, "/opt/acp-tests/outils/client_ws.py", "prompt", jeton(pile), "/tmp/acp-ws-p4b.json",
                            "OUTIL:tool_call>projet_planifier"], delai=400)
    assert sortie.returncode == 0, sortie.stderr[-3000:]
    derniere = [r for r in requetes(pile) if r.get("outil_demande") == "tool_call>projet_planifier"]
    assert derniere and "projet_planifier" not in (derniere[-1].get("catalogue_differe") or "")
    resultats = [r["contenu"] for r in requetes(pile) for r in r.get("resultats_outils") or []]
    assert any("'projet_planifier' is not available in this session" in r or "Refusé par ACP" in r
               for r in resultats), resultats[-5:]


# =========================================================================== 6. crochets, mémoire


def test_aucun_crochet_et_refus_des_hooks(pile, ressources, image):
    liste = pile.executer(["sh", "-c", "cd /opt/data && hermes hooks list"], utilisateur="hermes")
    afficher("hermes hooks list", liste.stdout + liste.stderr)
    assert liste.returncode == 0 and "pre_tool_call" not in liste.stdout
    for fichiers, motif in (
            ({"config.yaml": "hooks:\n  pre_tool_call:\n    - command: id\n"}, "déclare des crochets shell (hooks : "
                                                                              "pre_tool_call)"),
            ({"shell-hooks-allowlist.json": "{}\n"}, "shell-hooks-allowlist.json existe : il autoriserait des "
                                                    "crochets shell")):
        volume = ressources.volume(image, fichiers)
        code, journal = demarrer_jusqu_a_l_arret(ressources, image, ENV_VALIDE, volume)
        lignes = "\n".join(l for l in journal.splitlines() if "[acp]" in l)
        afficher(f"démarrage refusé : {list(fichiers)[0]}", lignes[-1500:])
        assert code == 1 and "[acp] REFUS : " in journal and motif in journal


def test_memoire_mesuree(pile):
    """Mesure indicative (pas un seuil) de la mémoire du conteneur pendant que deux workers tournent."""
    titre = "Memoire"
    lent = {"outil": "kanban_show", "arguments": {}}
    ajouter_scenarios(pile, {f"rôle « hermes » — projet « {titre} »": scenario([lent, lent, lent], "Fait.")})
    ajouter_scenarios(pile, {f"rôle « planification » — projet « {titre} »": scenario(
        [appel("projet_planifier", {"resume": "Deux recherches.", "etapes": [
            {"ref": "a", "titre": "A", "classe": "recherche_web", "consigne": "A."},
            {"ref": "b", "titre": "B", "classe": "recherche_web", "consigne": "B."}]})], "Plan.")})
    # La synthèse conclut (sans scénario, elle échouerait trois fois puis serait abandonnée).
    ajouter_scenarios(pile, {f"rôle « synthese » — projet « {titre} »": scenario([appel("projet_etat")], "Conclusion.")})
    projet = lancer_projet(pile, titre=titre, objectif="Mesurer.", depot=None)
    mesures, environnements, erreurs_lecture = [], [], []
    limite = time.monotonic() + 120
    while time.monotonic() < limite:
        pids = pile.sh("pgrep -u hermes -f 'work kanban task'", verifier=False).stdout.split()
        stats = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", pile.nom, verifier=False).stdout.strip()
        mesures.append((len(pids), stats))
        for pid in pids[:1]:
            # Environnement INITIAL d'un worker lancé par la passerelle : aucune variable de notification
            # (register() les a retirées de l'environnement de la passerelle avant tout lancement). Lu sous
            # l'uid hermes : root, sans CAP_SYS_PTRACE dans le conteneur, ne lit pas /proc/<pid>/environ d'un
            # autre uid (mesuré : lecture vide au passage précédent de ce contrat).
            lecture = pile.sh(f"tr '\\0' '\\n' < /proc/{pid}/environ | cut -d= -f1", utilisateur="hermes",
                              verifier=False)
            noms = lecture.stdout.split()
            if "HERMES_KANBAN_TASK" in noms:  # lecture réussie de l'environnement d'un vrai worker
                environnements.append(sorted(n for n in noms if n.startswith("ACP_")))
            elif lecture.stderr.strip():
                erreurs_lecture.append(lecture.stderr.strip()[:200])
        if detail(pile, projet["id"])["etat"] == "termine":
            break
        time.sleep(2)
    afficher("mémoire mesurée (docker stats) et workers kanban",
             "\n".join(f"{w} worker(s) : {m}" for w, m in mesures) + f"\nvariables ACP_* des workers : {environnements}"
             + (f"\nlectures en échec : {erreurs_lecture[:3]}" if erreurs_lecture else ""))
    assert environnements and all(e == [] for e in environnements), (environnements, erreurs_lecture[:3])
    assert mesures and any(w >= 1 for w, _ in mesures)
