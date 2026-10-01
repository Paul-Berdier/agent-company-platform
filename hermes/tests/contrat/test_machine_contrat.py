"""Contrat de l'étape P5, piloté depuis l'hôte (voir conftest.py) : le poste connecté (protocole acp-machine/1) sur
la pile complète (s6, passerelle, tableau de bord), avec un FAUX POSTE (hermes/tests/outils/faux_poste.py) qui parle
au vrai tableau de bord à travers la vraie couture d'authentification par jeton de Hermes, et valide chaque réponse
par les modèles du contrat partagé. Le vrai poste Windows (apps/poste) est prouvé par ses propres tests.

Pile : faux fournisseur d'identité (session OIDC du propriétaire), faux serveur ntfy en HTTPS (notifications
« Poste hors ligne »), volume jetable, répartiteur à 5 s, émetteur à 5 s, seuil hors ligne à 10 s.

Ce qui est prouvé ici, sur l'image réellement construite :
- les trois chemins machine ne répondent qu'au jeton machine (401 de la couture sans porteur, avec la session OIDC
  du propriétaire, avec un jeton d'une autre forme) ; une route P6 non enregistrée reste fermée ;
- /v1/meta voit, dans le tableau de bord, le fournisseur enregistré et les trois chemins à jeton ;
- enrôlement par code à usage unique, empreinte recalculée identique, confirmation par la page, présence ;
- inventaire visible dans le poste, le routage et les quotas ; un projet sur dépôt n'est plus refusé ;
- ordre « Relever maintenant » servi en moins de 3 s ; révocation pendant l'attente : 401 poste_revoque aussitôt,
  jeton effacé par le poste, appel suivant refusé par la couture ;
- poste arrêté : UNE notification « Poste hors ligne » par passage ; redémarrage de Hermes : aucune ;
- aucun jeton ni code dans les journaux de Hermes, la base du greffon ou le journal du faux poste.
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
JOURNAL_NTFY = "/tmp/ntfy-p5.jsonl"
SCENARIOS = "/tmp/acp-scenarios.json"
SUJET = "acp_sujet_de_test_p5"
JETON_NTFY = "jeton-de-test-acp-p5"
ENV_P5 = dict(ENV_VALIDE, ACP_NOTIFICATIONS="ntfy", ACP_NTFY_SERVEUR="https://ntfy.acp.test", ACP_NTFY_SUJET=SUJET,
              ACP_NTFY_JETON=JETON_NTFY)
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
FAUX = "/opt/acp-tests/outils/faux_poste.py"
SEUIL_S = 10


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
    hermes = lancer(ressources, image_tests, ENV_P5, volume=volume, reseau=reseau)
    _modele(hermes)
    for cle, valeur in (("emetteur_intervalle_s", "5"), ("seuil_hors_ligne_s", str(SEUIL_S))):
        reglage(hermes, cle, valeur)
    hermes.ntfy = ntfy  # type: ignore[attr-defined]
    return hermes


def _modele(hermes: Conteneur) -> None:
    hermes.executer(["sh", "-c", f"echo '{{}}' > {SCENARIOS}"], utilisateur="hermes", verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)


def reglage(hermes: Conteneur, cle: str, valeur: str) -> None:
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", "reglage", cle, valeur],
                             utilisateur="hermes", delai=120)
    assert sortie.returncode == 0, sortie.stderr[-2000:]


def jeton_oidc(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def api(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None):
    """(code, JSON) d'une route du PROPRIÉTAIRE, avec sa session OIDC, en bouclage local."""
    commande = ["curl", "-s", "-o", "/tmp/acp-reponse-p5", "-w", "%{http_code}", "-X", methode,
                f"http://127.0.0.1:9119{P}{chemin}", "-H", f"Authorization: Bearer {jeton_oidc(hermes)}"]
    if corps is not None:
        commande += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(corps, ensure_ascii=False)]
    code = int(hermes.executer(commande, verifier=True).stdout.strip())
    contenu = hermes.executer(["cat", "/tmp/acp-reponse-p5"], verifier=True).stdout
    try:
        return code, json.loads(contenu)
    except ValueError:
        return code, contenu


def faux(hermes: Conteneur, *arguments: str, attendu: Optional[int] = 0, delai: int = 120) -> Dict[str, Any]:
    """Faux poste, sous l'uid hermes, dans le conteneur ; rend sa dernière ligne JSON."""
    sortie = hermes.executer([PYTHON, FAUX, *arguments], utilisateur="hermes", delai=delai)
    if attendu is not None:
        assert sortie.returncode == attendu, (arguments, sortie.returncode, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def servir_en_fond(hermes: Conteneur, attente: int = 25, duree: int = 900) -> None:
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, FAUX, "servir", "--attente", str(attente), "--duree",
           str(duree))


def arreter_le_faux(hermes: Conteneur) -> None:
    hermes.executer(["pkill", "-f", "faux_poste.py servir"], verifier=False)


def journal_du_faux(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = hermes.sh("cat /tmp/faux-poste/journal.jsonl 2>/dev/null", verifier=True).stdout
    return [json.loads(l) for l in brut.splitlines() if l.strip()]


def notifications_hors_ligne(hermes: Conteneur) -> List[Dict[str, Any]]:
    brut = docker("exec", hermes.ntfy, "sh", "-c", f"cat {JOURNAL_NTFY} 2>/dev/null", verifier=False).stdout
    return [n for n in (json.loads(l) for l in brut.splitlines() if l.strip()) if "Poste hors ligne" in n.get("corps", "")]


def attendre(predicat, delai: float, message: str, pas: float = 1.0):
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = predicat()
        if dernier:
            return dernier
        time.sleep(pas)
    raise AssertionError(f"{message} (après {delai:.0f} s) ; dernier état : {str(dernier)[:1500]}")


def enroler_et_confirmer(hermes: Conteneur, nom: str = "Poste de contrat") -> Dict[str, Any]:
    code, cree = api(hermes, "POST", "/v1/poste/enrolement", {})
    assert code == 201, cree
    enrole = faux(hermes, "enroler", cree["code"], "--nom", nom)
    code, confirme = api(hermes, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                     "empreinte": enrole["empreinte"]})
    assert code == 200 and confirme["machine"]["etat"] == "actif", confirme
    return enrole


# =========================================================================== 1. couture et méta


def test_chemins_machine_sans_jeton_401(pile):
    oidc = jeton_oidc(pile)
    constats = {}
    for route in ("enrolement", "reclamer", "inventaire"):
        for porteur in ("aucun", f"brut:{oidc}", "brut:acpm_" + "A" * 43, "brut:acpe_" + "B" * 43):
            reponse = faux(pile, "appel", route, "--porteur", porteur)
            constats[f"{route} {porteur[:12]}"] = (reponse["statut"], reponse["corps"])
            assert reponse["statut"] == 401 and reponse["corps"] == {"error": "unauthenticated",
                                                                     "detail": "Unauthorized"}, (route, reponse)
    afficher("routes machine sans jeton reconnu", json.dumps(constats, ensure_ascii=False, indent=1))


def test_meta_bloc_machine(pile):
    code, meta = api(pile, "GET", "/v1/meta")
    assert code == 200
    machine = meta["machine"]
    afficher("/v1/meta : bloc machine", json.dumps(machine, ensure_ascii=False, indent=1))
    assert machine["fournisseur"] == "enregistre" and all(machine["chemins_a_jeton"].values())
    assert len(machine["chemins_a_jeton"]) == 3 and machine["base"] == "ok"
    assert "self-hosted" in machine["fournisseurs_de_session"]
    assert not any("jeton machine" in a or "chemins machine" in a.lower() or "connexion interactive" in a
                   for a in meta["alertes"]), meta["alertes"]


# =========================================================================== 2. enrôlement et inventaire


def test_enrolement_confirmation_bout_en_bout(pile):
    code, vue = api(pile, "GET", "/v1/poste")
    assert code == 200 and vue["poste"]["etat"] == "non_configure"
    code, cree = api(pile, "POST", "/v1/poste/enrolement", {})
    assert code == 201 and cree["code"].startswith("acpe_")
    assert cree["commande"] == '& "$env:ProgramFiles\\ACP\\poste\\acp-poste.cmd" enroler'  # décision D68
    enrole = faux(pile, "enroler", cree["code"], "--nom", "Poste de contrat")
    assert enrole["statut"] == 201 and enrole["etat"] == "a_confirmer" and enrole["cache_control"] == "no-store"
    assert enrole["empreinte"] == enrole["empreinte_recalculee"]  # le poste recalcule la même empreinte
    # Usage unique : le même code est refusé par la couture.
    second = faux(pile, "enroler", cree["code"], attendu=3)
    assert second["statut"] == 401
    code, vue = api(pile, "GET", "/v1/poste")
    assert vue["poste"]["etat"] == "a_confirmer" and vue["machine"]["machine"]["empreinte"] == enrole["empreinte"]
    attente = faux(pile, "reclamer", "--attente", "5")
    assert attente["statut"] == 200 and attente["corps"]["etat_machine"] == "a_confirmer"
    assert attente["corps"]["prochaine_attente_s"] == 15 and attente["duree"] < 3
    refuse = faux(pile, "inventaire")
    assert refuse["statut"] == 403 and refuse["corps"]["detail"]["code"] == "poste_a_confirmer"
    code, confirme = api(pile, "POST", "/v1/poste/confirmation", {"machine_id": enrole["machine_id"],
                                                                   "empreinte": enrole["empreinte"].lower()})
    assert code == 200 and confirme["machine"]["etat"] == "actif"
    presence = faux(pile, "reclamer", "--attente", "5")
    assert presence["statut"] == 200 and presence["corps"]["etat_machine"] == "actif"
    code, vue = api(pile, "GET", "/v1/poste")
    afficher("poste confirmé et vu", json.dumps(vue["poste"], ensure_ascii=False, indent=1))
    assert vue["poste"]["etat"] == "en_ligne" and vue["poste"]["source"] == "longpoll"


def test_route_p6_non_enregistree_401(pile):
    """Une route machine de P6 (battement) n'est pas un chemin à jeton : la porte OIDC la voit et refuse."""
    code = pile.executer(["sh", "-c", "curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' "
                          f"-H \"Authorization: Bearer $(cat /tmp/faux-poste/jeton)\" --data '{{}}' "
                          f"http://127.0.0.1:9119{P}/machine/v1/battement"], utilisateur="hermes",
                         verifier=True).stdout.strip()
    assert code == "401"


def test_inventaire_visible_dans_poste_routage_quotas(pile):
    reponse = faux(pile, "inventaire")
    assert reponse["statut"] == 200 and set(reponse["corps"]["releves"]) == {"poste-codex", "poste-claude"}
    code, routage = api(pile, "GET", "/v1/routage")
    assert code == 200
    assert routage["voies"]["poste-codex"]["badge"] == "releve_du_compte"
    assert routage["voies"]["poste-claude"]["badge"] == "alias_documentes"
    assert routage["politique_poste"]["alias_claude_permis"] == ["opus", "opus[1m]", "sonnet", "haiku"]
    code, quotas = api(pile, "GET", "/v1/quotas")
    assert code == 200 and quotas["poste-codex"]["etat"] == "releve"
    assert quotas["poste-codex"]["compteurs"][0]["windows"][0]["used_percent"] == 41
    code, vue = api(pile, "GET", "/v1/poste")
    assert vue["inventaire"]["contenu"]["connexions"]["codex"] == "compte_chatgpt" and vue["alertes"] == []
    trop_tot = faux(pile, "inventaire")
    assert trop_tot["statut"] == 429 and int(trop_tot["entetes"]["retry-after"]) > 0
    afficher("inventaire : routage et quotas", json.dumps({"voies": {v: routage["voies"][v]["badge"] for v in
                                                                     routage["voies"]},
                                                           "quotas": quotas["poste-codex"]["resume"]},
                                                          ensure_ascii=False, indent=1))


def test_projet_sur_depot_accepte_apres_inventaire(pile):
    code, projet = api(pile, "POST", "/v1/projets", {
        "titre": "Projet sur le dépôt jetable", "objectif": "Vérifier le dépôt.", "depot": "jetable",
        "exploration": {"voie": "poste-codex", "modele": "factice-codex-1", "effort": "low"}})
    assert code == 201, projet
    assert projet["projet"]["depot"] == "jetable" and projet["projet"]["id"].startswith("p_")


# =========================================================================== 3. ordres et révocation


def test_ordre_releve_moins_de_3_s(pile):
    # Attente de 5 s : sous le seuil « hors ligne » de 10 s de cette pile (180 s en production pour 25 s d'attente).
    servir_en_fond(pile, attente=5)
    attendre(lambda: api(pile, "GET", "/v1/poste")[1]["poste"]["etat"] == "en_ligne", 20, "le faux poste n'attend pas")
    time.sleep(1)
    debut = time.time()
    code, ordre = api(pile, "POST", "/v1/poste/releve", {})
    assert code == 202 and ordre["en_attente_du_poste"] is False, ordre
    publie = attendre(lambda: [e for e in journal_du_faux(pile) if e["evenement"] == "inventaire"
                               and e["ordre"] == ordre["ordre"]], 20, "inventaire non publié sur ordre")
    delai = publie[0]["quand"] - debut
    afficher("ordre « releve » → inventaire", f"{delai:.2f} s (statut {publie[0]['statut']})")
    assert publie[0]["statut"] == 200 and delai < 3.0


def test_revocation_401_immediat(pile):
    pile.executer(["cp", "/tmp/faux-poste/jeton", "/tmp/faux-poste/jeton-sauve"], utilisateur="hermes", verifier=True)
    machine = api(pile, "GET", "/v1/poste")[1]["machine"]["machine"]["id"]
    attendre(lambda: pile.executer(["pgrep", "-f", "faux_poste.py servir"]).returncode == 0, 10, "faux poste arrêté")
    debut = time.time()
    code, vue = api(pile, "POST", "/v1/poste/revocation", {"machine_id": machine, "motif": "contrat P5"})
    assert code == 200 and vue["machine"]["etat"] == "revoque"
    arret = attendre(lambda: [e for e in journal_du_faux(pile) if e["evenement"] == "poste_revoque"], 15,
                     "le faux poste n'a pas reçu poste_revoque")
    delai = arret[0]["quand"] - debut
    afficher("révocation pendant l'attente", f"{delai:.2f} s ; {arret[0]['message']}")
    assert delai < 3.0 and arret[0]["message"].startswith("Poste révoqué par le propriétaire le ")
    assert pile.sh("test -f /tmp/faux-poste/jeton", verifier=False).returncode != 0  # jeton effacé par le poste
    suivant = faux(pile, "appel", "reclamer", "--porteur", "fichier:/tmp/faux-poste/jeton-sauve",
                   "--corps", json.dumps({"protocole": "acp-machine/1", "version_poste": "0.11.0",
                                          "peut_executer": False}))
    assert suivant["statut"] == 401 and suivant["corps"] == {"error": "unauthenticated", "detail": "Unauthorized"}


# =========================================================================== 4. présence


def test_poste_arrete_une_notification(pile):
    avant = len(notifications_hors_ligne(pile))
    enroler_et_confirmer(pile, "Poste de présence")
    servir_en_fond(pile, attente=5)
    attendre(lambda: api(pile, "GET", "/v1/poste")[1]["poste"]["etat"] == "en_ligne", 30, "poste jamais en ligne")
    arreter_le_faux(pile)
    premiere = attendre(lambda: notifications_hors_ligne(pile)[avant:], 60, "aucune notification « Poste hors ligne »")
    time.sleep(12)
    assert len(notifications_hors_ligne(pile)[avant:]) == 1, notifications_hors_ligne(pile)[avant:]
    servir_en_fond(pile, attente=5)
    attendre(lambda: api(pile, "GET", "/v1/poste")[1]["poste"]["etat"] == "en_ligne", 30, "retour en ligne non vu")
    arreter_le_faux(pile)
    attendre(lambda: len(notifications_hors_ligne(pile)[avant:]) == 2, 60, "pas de seconde notification")
    afficher("présence du faux poste", json.dumps(notifications_hors_ligne(pile)[avant:], ensure_ascii=False, indent=1))
    assert premiere[0]["priority"] == "4"


def test_redemarrage_de_la_pile_sans_notification(pile):
    servir_en_fond(pile, attente=5)
    attendre(lambda: api(pile, "GET", "/v1/poste")[1]["poste"]["etat"] == "en_ligne", 30, "poste jamais en ligne")
    avant = len(notifications_hors_ligne(pile))
    derniere_vue = api(pile, "GET", "/v1/poste")[1]["poste"]["derniere_vue"]
    docker("restart", pile.nom, delai=300)
    pile.attendre_pret()
    servir_en_fond(pile, attente=5)  # le redémarrage a tué le faux poste : il repart aussitôt, comme la tâche
    pile.attendre_passerelle()
    _modele(pile)
    vue = attendre(lambda: (lambda v: v if v["poste"]["etat"] == "en_ligne" and v["poste"]["derniere_vue"] >
                            derniere_vue else None)(api(pile, "GET", "/v1/poste")[1]), 60, "poste non revu")
    absence = vue["poste"]["derniere_vue"] - derniere_vue
    time.sleep(3 * 5 + SEUIL_S)  # plusieurs passes de l'émetteur au-delà du seuil
    nouvelles = notifications_hors_ligne(pile)[avant:]
    afficher("redémarrage de Hermes", f"absence du poste : {absence} s (seuil {SEUIL_S} s) ; notifications : {nouvelles}")
    # Sans la grâce de redémarrage, une absence plus longue que le seuil notifierait « Poste hors ligne ».
    assert absence > SEUIL_S, f"absence de {absence} s : le test ne prouve rien sous le seuil"
    assert nouvelles == []
    arreter_le_faux(pile)


# =========================================================================== 5. secrets


def test_aucun_jeton_dans_les_journaux(pile):
    sauve = pile.sh("cat /tmp/faux-poste/jeton-sauve", verifier=True).stdout.strip()
    assert sauve.startswith("acpm_")
    journaux = pile.journaux()
    base = pile.executer([PYTHON, "-c", (
        "import sqlite3, json\n"
        "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
        "t = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]\n"
        "print(json.dumps({x: [list(map(str, l)) for l in c.execute(f'SELECT * FROM {x}')] for x in t}))\n")],
        utilisateur="hermes", verifier=True).stdout
    journal = pile.sh("cat /tmp/faux-poste/journal.jsonl", verifier=True).stdout
    for nom, texte in (("docker logs", journaux), ("base du greffon", base), ("journal du faux poste", journal)):
        assert sauve not in texte, nom
        assert "acpm_" not in texte and "acpe_" not in texte, nom
    empreintes = json.loads(base)["machines"]
    assert all(len(l[2]) == 64 for l in empreintes)  # seul le SHA-256 du jeton est gardé
    afficher("secrets", f"{len(journaux)} caractères de journaux, {len(base)} de base, {len(journal)} de journal du "
                        "faux poste : ni jeton, ni code, ni préfixe acpm_/acpe_")
