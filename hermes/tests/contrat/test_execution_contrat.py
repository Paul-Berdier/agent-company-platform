"""Contrat de l'étape P6, piloté depuis l'hôte (voir conftest.py) : l'exécution des cartes par l'exécutant Railway sur
la pile complète (s6, passerelle, tableau de bord), avec un FAUX EXÉCUTANT (hermes/tests/outils/faux_executant.py) qui
parle ``acp-machine/1`` au vrai tableau de bord à travers la vraie couture par jeton de Hermes et valide chaque réponse
par les modèles du contrat partagé. Il n'exécute RIEN : il rapporte ce que le test lui dicte. Le vrai exécutant
(apps/poste, image executant/) est prouvé par ses propres tests.

Pile : faux fournisseur d'identité (session OIDC du propriétaire), faux serveur ntfy en HTTPS, volume jetable,
répartiteur et émetteur à 5 s.

Ce qui est prouvé ici, sur l'image réellement construite :
- neuf chemins à jeton exacts, vus par /v1/meta dans le tableau de bord ; les six routes P6 refusent la session OIDC du
  propriétaire et tout porteur inconnu (401 de la couture) ;
- inventaire Linux reçu (régime B, voie Codex fermée) et vu par /v1/poste ;
- une carte n'est servie qu'à ``peut_executer`` et sur une voie annoncée ; réclamée ``acp-poste:<machine>``, TTL 2 700 s ;
- battement, fin, idempotence, réclamation perdue (409, sans effet), secret (422, rien d'écrit) ;
- question → réponse du propriétaire → carte resservie avec ``reprise`` et la réponse ; deux questions sans triage ;
- revue des fichiers de pilotage refusée par le propriétaire → carte resservie avec le motif ; reprendre, arrêt propre ;
- notifications « revue » et « secret » réellement envoyées au faux ntfy ; aucun jeton ni secret factice dans les
  journaux de Hermes ni dans la base du greffon.
"""

from __future__ import annotations

import json
import time
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
JOURNAL_NTFY = "/tmp/ntfy-p6.jsonl"
SCENARIOS = "/tmp/acp-scenarios.json"
SUJET = "acp_sujet_de_test_p6"
JETON_NTFY = "jeton-de-test-acp-p6"
ENV_P6 = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test", ACP_NTFY_SUJET=SUJET,
              ACP_NTFY_JETON=JETON_NTFY)
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
FAUX_POSTE = "/opt/acp-tests/outils/faux_poste.py"
FAUX = "/opt/acp-tests/outils/faux_executant.py"
ROUTES_P6 = ("battement", "terminer", "question", "bloquer", "reprendre", "arret")
SECRET_FACTICE = "sk-ant-" + "faux" * 8  # assemblé à l'exécution : le balayage du dépôt ne le voit pas


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
    hermes = lancer(ressources, image_tests, ENV_P6, volume=volume, reseau=reseau)
    hermes.executer(["sh", "-c", f"echo '{{}}' > {SCENARIOS}"], utilisateur="hermes", verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", "reglage", "emetteur_intervalle_s", "5"],
                             utilisateur="hermes", delai=120)
    assert sortie.returncode == 0, sortie.stderr[-2000:]
    hermes.ntfy = ntfy  # type: ignore[attr-defined]
    return hermes


def jeton_oidc(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def api(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None):
    """(code, JSON) d'une route du PROPRIÉTAIRE, avec sa session OIDC, en bouclage local."""
    commande = ["curl", "-s", "-o", "/tmp/acp-reponse-p6", "-w", "%{http_code}", "-X", methode,
                f"http://127.0.0.1:9119{P}{chemin}", "-H", f"Authorization: Bearer {jeton_oidc(hermes)}"]
    if corps is not None:
        commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
    code = int(hermes.executer(commande, verifier=True).stdout.strip())
    contenu = hermes.executer(["cat", "/tmp/acp-reponse-p6"], verifier=True).stdout
    try:
        return code, json.loads(contenu)
    except ValueError:
        return code, contenu


def _outil(hermes: Conteneur, script: str, *arguments: str, attendu: Optional[int] = 0) -> Dict[str, Any]:
    sortie = hermes.executer([PYTHON, script, *arguments], utilisateur="hermes", delai=120)
    if attendu is not None:
        assert sortie.returncode == attendu, (arguments, sortie.returncode, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def executant(hermes: Conteneur, *arguments: str, attendu: Optional[int] = 0) -> Dict[str, Any]:
    return _outil(hermes, FAUX, *arguments, attendu=attendu)


def envoyer(hermes: Conteneur, route: str, **champs) -> Dict[str, Any]:
    options = []
    for cle in ("id_envoi", "run"):
        if cle in champs:
            options += [f"--{cle.replace('_', '-')}", str(champs.pop(cle))]
    return executant(hermes, "envoyer", route, "--champs", json.dumps(champs, ensure_ascii=False), *options)


def carte_servie(hermes: Conteneur, voies: str = "poste-claude", en_cours: Optional[str] = None) -> Dict[str, Any]:
    arguments = ["reclamer", "--voies", voies, "--attente", "5"]
    if en_cours:
        arguments += ["--en-cours", en_cours]
    reponse = executant(hermes, *arguments)
    assert reponse["statut"] == 200 and reponse["corps"]["carte"], reponse
    return reponse["corps"]["carte"]


def lire_tache(hermes: Conteneur, tableau: str, carte: str) -> Dict[str, Any]:
    """Ligne de la carte dans la base du tableau (lecture seule, uid hermes)."""
    code = ("import json, sys\n"
            "from hermes_cli.kanban_db_connect import connect\n"
            f"c = connect(board={tableau!r})\n"
            f"r = c.execute('SELECT status, claim_lock, claim_expires, current_run_id, consecutive_failures, "
            f"worker_pid FROM tasks WHERE id = ?', ({carte!r},)).fetchone()\n"
            "print(json.dumps(dict(zip(['status', 'claim_lock', 'claim_expires', 'current_run_id', "
            "'consecutive_failures', 'worker_pid'], list(r)))))\n")
    sortie = hermes.executer([PYTHON, "-c", code], utilisateur="hermes", verifier=True,
                             env={"HERMES_HOME": "/opt/data"}).stdout
    return json.loads(sortie.strip().splitlines()[-1])


def notifications(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = docker("exec", hermes.ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def attendre(predicat, delai: float, message: str, pas: float = 1.0):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def lancer_projet(hermes: Conteneur, titre: str) -> Dict[str, Any]:
    code, projet = api(hermes, "POST", "/v1/projets", {
        "titre": titre, "objectif": "Écrire un outil dans le dépôt jetable.", "depot": "jetable",
        "exploration": {"voie": "poste-claude", "modele": "opus", "effort": "low"}})
    assert code == 201, projet
    return projet["projet"]


# =========================================================================== 1. couture et méta


def test_neuf_chemins_a_jeton(pile):
    code, meta = api(pile, "GET", "/v1/meta")
    assert code == 200
    chemins = meta["machine"]["chemins_a_jeton"]
    assert list(chemins) == [f"{P}/machine/v1/{r}" for r in ("enrolement", "reclamer", "inventaire", *ROUTES_P6)]
    assert all(chemins.values())
    oidc = jeton_oidc(pile)
    constats = {}
    for route in ROUTES_P6:
        for nom, entete in (("aucun", []), ("session OIDC", ["-H", f"Authorization: Bearer {oidc}"]),
                            ("jeton inconnu", ["-H", "Authorization: Bearer acpm_" + "A" * 43])):
            sortie = pile.executer(["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", "-H",
                                    "Content-Type: application/json", *entete, "--data", "{}",
                                    f"http://127.0.0.1:9119{P}/machine/v1/{route}"], verifier=True).stdout
            corps, statut = sortie.rsplit("\n", 1)
            constats[f"{route} {nom}"] = statut
            assert statut == "401" and json.loads(corps) == {"error": "unauthenticated", "detail": "Unauthorized"}
    afficher("six routes P6 sans jeton machine", json.dumps(constats, ensure_ascii=False, indent=1))


# =========================================================================== 2. enrôlement, inventaire Linux


def test_enrolement_et_inventaire_linux(pile):
    code, cree = api(pile, "POST", "/v1/poste/enrolement", {})
    assert code == 201
    enrole = _outil(pile, FAUX_POSTE, "enroler", cree["code"], "--nom", "Exécutant Railway")
    code, confirme = api(pile, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                   "empreinte": enrole["empreinte"]})
    assert code == 200 and confirme["machine"]["etat"] == "actif"
    reponse = executant(pile, "inventaire", "--regime", "B")
    assert reponse["statut"] == 200, reponse
    code, vue = api(pile, "GET", "/v1/poste")
    afficher("exécutant vu par /v1/poste", json.dumps(vue["executant"], ensure_ascii=False, indent=1)[:3000])
    assert vue["executant"]["plateforme"] == "linux" and vue["executant"]["hote"] == "railway"
    assert vue["executant"]["isolement"]["regime"] == "B"
    assert list(vue["executant"]["voies_fermees"]) == ["poste-codex"]


# =========================================================================== 3. carte servie, battement, fin


def test_carte_servie_seulement_a_peut_executer(pile):
    projet = lancer_projet(pile, "Projet A")
    rien = executant(pile, "reclamer", "--sans-execution", "--attente", "5")
    assert rien["statut"] == 200 and rien["corps"]["carte"] is None
    carte = carte_servie(pile)
    assert carte["tableau"] == projet["tableau"] and carte["role"] == "exploration"
    tache = lire_tache(pile, carte["tableau"], carte["carte"])
    machine = api(pile, "GET", "/v1/poste")[1]["machine"]["machine"]["id"]
    assert tache["status"] == "running" and tache["claim_lock"] == f"acp-poste:{machine}"
    assert 2600 <= tache["claim_expires"] - int(time.time()) <= 2700 and tache["worker_pid"] is None
    afficher("carte servie à l'exécutant", json.dumps({"carte": carte, "tache": tache}, ensure_ascii=False, indent=1))


def test_battement_fin_idempotence_et_refus(pile):
    battement = envoyer(pile, "battement", note="Étape 1 : lecture du dépôt.")
    assert battement["statut"] == 200 and battement["corps"] == {"valide": True, "pause": False, "annuler": False}
    perdue = envoyer(pile, "terminer", resume="Mauvais run.", run=999)
    assert perdue["statut"] == 409 and perdue["corps"]["detail"]["code"] == "reclamation_perdue"
    secret = envoyer(pile, "terminer", resume=f"Trouvé {SECRET_FACTICE} dans le dépôt.")
    assert secret["statut"] == 422 and secret["corps"]["detail"]["code"] == "secret_detecte"
    assert SECRET_FACTICE not in json.dumps(secret["corps"])
    fin = envoyer(pile, "terminer", resume="## Structure\nUn paquet.", id_envoi="3f2a8c1e-5b6d-4e7f-8a9b-0c1d2e3f4a5b")
    assert fin["statut"] == 200 and fin["corps"] == {"etat": "done", "deja_recu": False}
    rejeu = envoyer(pile, "terminer", resume="## Structure\nUn paquet.", id_envoi="3f2a8c1e-5b6d-4e7f-8a9b-0c1d2e3f4a5b")
    assert rejeu["statut"] == 200 and rejeu["corps"] == {"etat": "done", "deja_recu": True}
    afficher("fin d'une carte", json.dumps({"409": perdue["corps"], "422": secret["corps"], "rejeu": rejeu["corps"]},
                                           ensure_ascii=False, indent=1))


# =========================================================================== 4. questions, revue, reprise


def test_deux_questions_sans_triage(pile):
    projet = lancer_projet(pile, "Projet B")
    carte = carte_servie(pile)
    assert carte["tableau"] == projet["tableau"]
    question = envoyer(pile, "question", texte="Garder Python 3.10 ?", contexte="requires-python >= 3.10")
    assert question["statut"] == 200 and question["corps"]["etat"] == "ouverte"
    code, repondue = api(pile, "POST", f"/v1/questions/{question['corps']['question']}/reponse", {"reponse": "Oui."})
    assert code == 200 and repondue["carte_debloquee"] is True
    resservie = carte_servie(pile)
    assert resservie["carte"] == carte["carte"] and resservie["reprise"] is True
    assert [r["texte"] for r in resservie["reponses"]] == ["Oui."]
    envoyer(pile, "battement", note="Reprise après la réponse.")
    seconde = envoyer(pile, "question", texte="Et Python 3.9 ?")
    assert seconde["statut"] == 200
    assert lire_tache(pile, carte["tableau"], carte["carte"])["status"] == "scheduled"  # jamais en triage


def test_revue_refusee_puis_reprise_et_arret(pile):
    projet = lancer_projet(pile, "Projet C")
    carte = carte_servie(pile)
    assert carte["tableau"] == projet["tableau"]
    revue = envoyer(pile, "terminer", resume="Ajout d'un contrôle de CI.",
                    metadonnees=dict(_metadonnees(carte), pilotage={"touche": True,
                                                                     "chemins": [".github/workflows/ci.yml"]}))
    assert revue["statut"] == 200 and revue["corps"]["etat"] == "review"
    code, questions = api(pile, "GET", "/v1/questions")
    assert [r["carte"] for r in questions["revues"]] == [carte["carte"]]
    code, refus = api(pile, "POST", f"/v1/revues/{carte['tableau']}/{carte['carte']}/refuser",
                      {"motif": "Ne touche pas au workflow de CI."})
    assert code == 200 and refus["etat"] == "ready", refus
    resservie = carte_servie(pile)
    assert resservie["carte"] == carte["carte"] and resservie["reprise"] is True
    assert [r["genre"] for r in resservie["reponses"]] == ["refus_revue"]
    rendue = envoyer(pile, "reprendre", motif="redemarrage")
    assert rendue["corps"] == {"etat": "rendue", "deja_recu": False}
    en_cours = f"{resservie['tableau']}:{resservie['carte']}:{resservie['run_id']}"
    encore = carte_servie(pile, en_cours=en_cours)
    assert encore["carte"] == carte["carte"] and encore["run_id"] != resservie["run_id"]
    arret = envoyer(pile, "arret", motif="sigterm")
    assert arret["corps"] == {"etat": "rendue", "deja_recu": False}
    tache = lire_tache(pile, carte["tableau"], carte["carte"])
    assert tache["status"] == "ready" and tache["consecutive_failures"] == 0


def _metadonnees(carte: Dict[str, Any]) -> Dict[str, Any]:
    return {"modele_demande": carte["modele"], "modele_servi": "factice-servi-1", "effort": carte["effort"],
            "palier_demande": carte["palier"], "palier_servi": None, "jetons": None, "branche": carte["branche"],
            "base": "1" * 40, "tete": "2" * 40, "diffstat": {"fichiers": 1, "ajouts": 3, "retraits": 0},
            "verification": {"etat": "reussie", "code": 0, "duree_s": 1, "tentatives": 1, "raison": None},
            "pilotage": {"touche": False, "chemins": []}, "regime": "B", "session_locale": True}


def test_secret_bloque_et_notifications(pile):
    carte = carte_servie(pile)
    bloquee = envoyer(pile, "bloquer", genre="secret", raison="Motif trouvé dans le diff.")
    assert bloquee["statut"] == 200 and bloquee["corps"]["etat"] == "bloquee"
    recues = attendre(lambda: (lambda n: n if {"revue", "secret"} <= {x.get("genre") for x in n} else None)(
        [dict(x, genre=_genre(x)) for x in notifications(pile)]), 90, "notifications revue et secret non reçues")
    afficher("notifications P6 reçues par le faux ntfy", json.dumps([x["corps"] for x in recues], ensure_ascii=False,
                                                                     indent=1))
    del carte


def _genre(notification: Dict[str, Any]) -> Optional[str]:
    corps = notification.get("corps", "")
    if "attend votre revue" in corps:
        return "revue"
    if "secret détecté" in corps:
        return "secret"
    return None


# =========================================================================== 4 bis. étape P7 : relancer, clore


def _mettre_les_autres_en_pause(pile: Conteneur) -> None:
    """Isole le projet du test : le faux exécutant sert la carte prête la plus prioritaire de TOUS les projets actifs ;
    les projets des tests précédents passent en pause (``_candidates`` ne sert que les projets actifs)."""
    code, liste = api(pile, "GET", "/v1/projets")
    assert code == 200
    for projet in liste["projets"]:
        if projet["etat"] == "actif":
            assert api(pile, "POST", f"/v1/projets/{projet['id']}/pause", {})[0] == 200


def _du_projet(pile: Conteneur, titre: str) -> List[str]:
    """Notifications reçues par le faux ntfy pour CE projet (la pile est partagée : un autre projet peut notifier)."""
    return [n["corps"] for n in notifications(pile) if f"« {titre} »" in n.get("corps", "")]


def _politique(pile: Conteneur, efforts: List[str]) -> None:
    code, vue = api(pile, "POST", "/v1/routage/politique", {"efforts_interdits": efforts, "paliers_admis": ["default"],
                                                             "motif": "contrat P7"})
    assert code == 200, vue


def test_p7_relance_apres_un_ecart_session_neuve(pile):
    """Cahier P7 § 3.4, correction K4, sur le chemin réel : la carte rendue (``reprendre`` : issue ``rendue``) est
    BLOQUÉE à la réclamation suivante par le double contrôle du greffon (effort interdit entre-temps) ; le propriétaire
    rétablit la politique puis la relance avec une consigne (``POST /v1/cartes/{t}/{c}/relancer``) ; le ``reclamer``
    suivant la sert en SESSION NEUVE (``reprise: false``), consigne du propriétaire en tête ; aucune notification de la
    relance."""
    _mettre_les_autres_en_pause(pile)
    projet = lancer_projet(pile, "Projet P7 relance")
    carte = carte_servie(pile)
    assert carte["tableau"] == projet["tableau"] and carte["effort"] == "low"
    assert envoyer(pile, "reprendre", motif="redemarrage")["corps"]["etat"] == "rendue"
    en_cours = f"{carte['tableau']}:{carte['carte']}:{carte['run_id']}"
    _politique(pile, ["max", "ultra", "ultracode", "low"])
    try:
        refusee = executant(pile, "reclamer", "--voies", "poste-claude", "--attente", "5", "--en-cours", en_cours)
        assert refusee["statut"] == 200 and refusee["corps"]["carte"] is None, refusee
    finally:
        _politique(pile, ["max", "ultra", "ultracode"])
    assert lire_tache(pile, carte["tableau"], carte["carte"])["status"] == "blocked"
    code, file = api(pile, "GET", "/v1/questions")
    [arretee] = [b for b in file["bloquees"] if b["carte"] == carte["carte"]]
    assert (arretee["relancable"], arretee["executant"]) == (True, True)
    assert arretee["raison"].startswith("Refusé par ACP au moment de la réclamation")
    assert file["discussions"]["suivies"] is True  # le compteur de Hermes est lu dans le tableau de bord
    # Le blocage à la réclamation est notifié par la passe de l'émetteur (P6, événement « blocked ») : l'attendre
    # d'abord, sinon il arriverait pendant la relance et serait pris pour une notification de la relance.
    avant = attendre(lambda: (lambda c: c if any("est bloquée" in x for x in c) else None)(
        _du_projet(pile, "Projet P7 relance")), 60, "le blocage à la réclamation n'a pas été notifié")
    code, relance = api(pile, "POST", f"/v1/cartes/{carte['tableau']}/{carte['carte']}/relancer",
                        {"consigne": "La politique est rétablie : reprends l'exploration depuis le début."})
    assert code == 200 and relance == {"carte": carte["carte"], "relancee": True, "statut_apres": "ready",
                                       "session_neuve": True, "branche_neuve": False}, relance
    resservie = carte_servie(pile, en_cours=en_cours)
    extrait = {k: resservie[k] for k in ("carte", "run_id", "reprise")}
    afficher("P7 : carte relancée servie", json.dumps(extrait, ensure_ascii=False) + " ; " + resservie["consigne"][:400])
    assert resservie["carte"] == carte["carte"] and resservie["reprise"] is False
    assert resservie["consigne"].startswith("## Consigne du propriétaire (relance du ")
    assert "La politique est rétablie : reprends l'exploration depuis le début." in resservie["consigne"]
    assert resservie["consigne"].endswith(carte["consigne"])
    time.sleep(11)  # deux passes de l'émetteur : la relance (geste du propriétaire) ne notifie rien
    assert _du_projet(pile, "Projet P7 relance") == avant


def test_p7_clore_pendant_la_reclamation(pile):
    """Cahier P7 § 10, correction K11 : clore le projet pendant que l'exécutant tient sa carte ; la carte est archivée,
    le battement suivant rend ``valide: false`` (pas un 409), l'exécutant la rend et reçoit ``deja_libre`` ; le projet
    est ``abandonne`` (aucune synthèse) ; aucune notification."""
    _mettre_les_autres_en_pause(pile)
    projet = lancer_projet(pile, "Projet P7 clore")
    carte = carte_servie(pile)
    assert carte["tableau"] == projet["tableau"]
    assert envoyer(pile, "battement", note="Au travail.")["corps"]["valide"] is True
    avant = _du_projet(pile, "Projet P7 clore")
    code, clos = api(pile, "POST", f"/v1/projets/{projet['id']}/clore", {"confirmation": True})
    assert code == 200 and (clos["clos"], clos["etat"]) == (True, "abandonne"), clos
    assert carte["carte"] in clos["cartes_archivees"] and clos["cartes_non_archivees"] == []
    tache = lire_tache(pile, carte["tableau"], carte["carte"])
    assert tache["status"] == "archived" and tache["claim_lock"] is None
    battement = envoyer(pile, "battement", note="Toujours au travail ?")
    assert battement["statut"] == 200 and battement["corps"]["valide"] is False, battement
    rendue = envoyer(pile, "reprendre", motif="reclamation_perdue")
    assert rendue["statut"] == 200 and rendue["corps"] == {"etat": "deja_libre", "deja_recu": False}
    code, encore = api(pile, "POST", f"/v1/projets/{projet['id']}/clore", {"confirmation": True})
    assert code == 409 and encore["detail"]["code"] == "projet_fini"
    time.sleep(11)  # deux passes de l'émetteur : la clôture ne notifie rien pour ce projet
    assert _du_projet(pile, "Projet P7 clore") == avant


# =========================================================================== 5. secrets


def test_aucun_jeton_ni_secret_dans_les_journaux(pile):
    journaux = pile.journaux()
    base = pile.executer([PYTHON, "-c", (
        "import sqlite3, json\n"
        "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
        "t = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
        "print(json.dumps({x: [list(map(str, l)) for l in c.execute(f'SELECT * FROM {x}')] for x in t}))\n")],
        utilisateur="hermes", verifier=True).stdout
    for nom, texte in (("docker logs", journaux), ("base du greffon", base)):
        assert "acpm_" not in texte and "acpe_" not in texte, nom
        assert SECRET_FACTICE not in texte, nom
    envois = json.loads(base)["envois"]
    assert envois and all(len(l[0]) == 36 for l in envois)
    afficher("secrets", f"{len(journaux)} caractères de journaux, {len(base)} de base : ni jeton, ni secret factice ; "
                        f"{len(envois)} envois gardés")
