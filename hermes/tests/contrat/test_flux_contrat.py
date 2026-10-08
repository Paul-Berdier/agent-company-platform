"""Contrat du flux d'invalidation GET /v1/flux (cahier P7 § 5.2, § 13.2), piloté depuis l'hôte (voir conftest.py).

Pile : faux fournisseur d'identité, image de test (le VRAI tableau de bord de Hermes : porte d'authentification et
six intergiciels HTTP empilés devant les routes), modèle factice à scénarios, poste SIMULÉ (outils/poste_simule.py).
Le flux est lu DANS le conteneur, en bouclage local (outils/lecteur_flux.py), avec le jeton porteur du fournisseur
d'identité, comme le reste des routes de lecture ; chaque trame est horodatée par l'horloge du conteneur, la même que
celle des requêtes du test.

Ce qui est prouvé ici, sur l'image réellement construite :
- 401 sans session (vraie porte), en-têtes ``text/event-stream; charset=utf-8``, ``no-store``, ``X-Accel-Buffering:
  no`` ; trame ``etat`` complète ; sémantique de ``Last-Event-ID`` ; ``discussions_suivies`` vrai (le compteur de
  Hermes est lu dans le processus du tableau de bord) ;
- passage SANS TAMPON à travers les six intergiciels (le S du cahier § 1.3, § 5.6) : la trame ``changement`` arrive
  moins de 5 s après la réponse donnée par la route ``POST /v1/questions/{q}/reponse``, battement laissé à 15 s
  (correction K20 : un flux tamponné n'arriverait qu'au battement suivant, ou à la fin) ;
- battement (réglage abaissé à 1 s), ``fin`` après la durée (abaissée à 5 s), flux fermé par le serveur ;
- 429 ``trop_de_flux`` au-delà de ``flux_max`` ; place rendue après la déconnexion d'un client, AVANT le premier
  battement (correction K10).
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
SCENARIOS = "/tmp/acp-scenarios.json"
P = "/api/plugins/acp-poste"
PYTHON = "/opt/hermes/.venv/bin/python"
SUJETS = ["projets", "questions", "poste", "quotas", "notifications", "pause", "discussions"]
TITRE = "Flux contrat P7"


@pytest.fixture(scope="module")
def pile(ressources, image_tests):
    reseau = ressources.reseau()
    idp = ressources.nom("idp")
    ressources.conteneurs.append(idp)
    docker("run", "-d", "--name", idp, "--network", reseau, "--network-alias", "idp.acp.test",
           "--entrypoint", PYTHON, image_tests, "/opt/acp-tests/outils/idp_factice.py", "--emetteur",
           "https://idp.acp.test:8443", "--port", "8443", "--certificat", "/opt/acp-tests/ac/idp.pem",
           "--cle", "/opt/acp-tests/ac/idp.key")
    volume = ressources.volume(image_tests, {"config.yaml": MODELE})
    hermes = lancer(ressources, image_tests, dict(ENV_VALIDE), volume=volume, reseau=reseau)
    scenarios = {f"rôle « planification » — projet « {TITRE} »": {
        "dans": "systeme", "etapes": [{"outil": "tool_call", "arguments": {"calls": [
            {"name": "projet_etat", "arguments": {}}]}}], "resume_final": "Vu."}}
    hermes.executer(["sh", "-c", f"cat > {SCENARIOS}"], utilisateur="hermes", entree=json.dumps(
        scenarios, ensure_ascii=False), verifier=True)
    docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/modele_factice.py", "--port",
           "18080", "--journal", JOURNAL_FACTICE, "--scenarios", SCENARIOS)
    attendre_modele_factice(hermes, JOURNAL_FACTICE)
    return hermes


def jeton(hermes: Conteneur) -> str:
    sortie = hermes.executer(["curl", "-s", "--cacert", "/opt/acp-tests/ac/ac.pem",
                              "https://idp.acp.test:8443/emettre?sub=proprietaire&aud=acp-tableau"], verifier=True).stdout
    return json.loads(sortie)["id_token"]


def simule(hermes: Conteneur, *arguments: str) -> Dict[str, Any]:
    sortie = hermes.executer([PYTHON, "/opt/acp-tests/outils/poste_simule.py", *arguments], utilisateur="hermes",
                             delai=120)
    assert sortie.returncode == 0, (arguments, sortie.stdout[-2000:], sortie.stderr[-3000:])
    return json.loads(sortie.stdout.strip().splitlines()[-1])


def requete(hermes: Conteneur, methode: str, chemin: str, corps: Optional[Any] = None, *,
            avec_jeton: bool = True, delai: float = 60) -> Dict[str, Any]:
    """Requête au VRAI tableau de bord, faite DANS le conteneur : statut, corps JSON et instant de la réponse (horloge
    du conteneur, celle des trames du lecteur). ``delai`` borne aussi l'attente entre deux morceaux : un flux accepté
    par erreur (200 au lieu de 429) échoue donc vite, au lieu de tenir jusqu'à sa fin."""
    code = (
        "import httpx, json, sys, time\n"
        "m, u, j, c, d = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])\n"
        "e = {'Authorization': 'Bearer ' + j} if j else {}\n"
        "if c: e['Content-Type'] = 'application/json'\n"
        "r = httpx.request(m, u, headers=e, content=c.encode() if c else None, timeout=d)\n"
        "t = time.time()\n"
        "try:\n    corps = r.json()\nexcept ValueError:\n    corps = r.text[:2000]\n"
        "print(json.dumps({'t': t, 'code': r.status_code, 'corps': corps, "
        "'entetes': {k.lower(): v for k, v in r.headers.items()}}))\n")
    sortie = hermes.executer([PYTHON, "-c", code, methode, f"http://127.0.0.1:9119{P}{chemin}",
                              jeton(hermes) if avec_jeton else "",
                              json.dumps(corps, ensure_ascii=False) if corps is not None else "", str(delai)],
                             verifier=True)
    return json.loads(sortie.stdout.strip().splitlines()[-1])


class Lecteur:
    """Un lecteur du flux lancé dans le conteneur (``docker exec -d``) ; son journal y est relu à la demande."""

    numero = 0

    def __init__(self, hermes: Conteneur, *, dernier_id: Optional[str] = None, duree: float = 120) -> None:
        Lecteur.numero += 1
        self.hermes = hermes
        self.journal = f"/tmp/flux-{Lecteur.numero}.jsonl"
        arguments = ["--jeton", jeton(hermes), "--journal", self.journal, "--duree", str(duree)]
        if dernier_id:
            arguments += ["--dernier-id", dernier_id]
        docker("exec", "-d", "-u", "hermes", hermes.nom, PYTHON, "/opt/acp-tests/outils/lecteur_flux.py", *arguments)

    def lignes(self) -> List[Dict[str, Any]]:
        brut = self.hermes.sh(f"cat {self.journal} 2>/dev/null").stdout
        return [json.loads(l) for l in brut.splitlines() if l.strip()]

    def trames(self) -> List[Dict[str, Any]]:
        return [dict(l["trame"], t=l["t"]) for l in self.lignes() if "trame" in l]

    def attendre(self, predicat, delai: float, message: str) -> Any:
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            resultat = predicat(self.lignes())
            if resultat:
                return resultat
            time.sleep(0.5)
        raise AssertionError(f"{message} (après {delai:.0f} s) ; journal : {json.dumps(self.lignes())[-3000:]}")

    def reponse(self, delai: float = 30) -> Dict[str, Any]:
        return self.attendre(lambda l: next((x for x in l if "statut" in x), None), delai, "flux sans réponse")

    def etat(self, delai: float = 30) -> Dict[str, Any]:
        return self.attendre(lambda l: next((x["trame"] for x in l if x.get("trame", {}).get("event") == "etat"),
                                            None), delai, "trame « etat » absente")

    def fin(self, delai: float) -> Dict[str, Any]:
        return self.attendre(lambda l: next((x for x in l if "fin" in x), None), delai, "flux jamais terminé")

    def arreter(self) -> None:
        """Arrête le lecteur (processus tué : le système ferme sa connexion) et attend sa disparition."""
        pid = next((x["pid"] for x in self.lignes() if "pid" in x), None)
        if pid is None or any("fin" in x for x in self.lignes()):
            return
        self.hermes.executer(["kill", str(pid)], utilisateur="hermes")
        limite = time.monotonic() + 20
        while time.monotonic() < limite and self.hermes.executer(["kill", "-0", str(pid)],
                                                                   utilisateur="hermes").returncode == 0:
            time.sleep(0.5)


def _reglage(hermes: Conteneur, cle: str, valeur: Any) -> None:
    simule(hermes, "reglage", cle, json.dumps(valeur))


# =========================================================================== tests


def test_flux_sans_session_401(pile):
    reponse = requete(pile, "GET", "/v1/flux", avec_jeton=False)
    assert reponse["code"] == 401, reponse


def test_flux_entetes_ouverture_et_last_event_id(pile):
    lecteur = Lecteur(pile, duree=5)
    reponse = lecteur.reponse()
    assert reponse["statut"] == 200, reponse
    assert reponse["entetes"]["content-type"] == "text/event-stream; charset=utf-8"
    assert reponse["entetes"]["cache-control"] == "no-store" and reponse["entetes"]["x-accel-buffering"] == "no"
    etat = lecteur.etat()
    assert lecteur.trames()[0]["retry"] == "3000"
    assert etat["donnees"] == {"revision": etat["id"], "sujets": SUJETS, "discussions_suivies": True}, etat
    afficher("flux : trame d'ouverture (pile complète)", json.dumps(etat, ensure_ascii=False))
    # Le même client revient avec la révision qu'il a lue : rien à relire (sauf si un sujet a changé entre-temps,
    # auquel cas la révision a avancé et tout est relu : le test le distingue).
    revenu = Lecteur(pile, dernier_id=etat["id"], duree=3).etat()
    assert revenu["donnees"]["sujets"] == ([] if revenu["id"] == etat["id"] else SUJETS), (etat, revenu)
    autre_epoque = Lecteur(pile, dernier_id="1.0", duree=3).etat()
    assert autre_epoque["donnees"]["sujets"] == SUJETS


def test_flux_changement_moins_de_5_s_apres_une_reponse_par_la_route(pile):
    """Passage sans tampon : battement de 15 s, veilleur de 2 s ; la trame doit arriver en moins de 5 s."""
    for voie in ("poste-codex", "poste-claude"):
        simule(pile, "releve-factice", json.dumps({
            "voie": voie, "source": "releve_factice", "version_cli": "0.0.0-factice",
            "releve_le": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "modeles": [{"id": f"factice-{voie[6:]}-1", "isDefault": True,
                         "supportedReasoningEfforts": ["low", "medium"], "defaultReasoningEffort": "medium",
                         "serviceTiers": ["default"]}],
            "depots": [{"alias": "jetable"}]}))
    lance = requete(pile, "POST", "/v1/projets", {"titre": TITRE, "objectif": "Mesurer le flux.", "depot": "jetable",
                                                   "reponses": "proprietaire", "exploration": {"voie": "poste-claude"}})
    assert lance["code"] == 201, lance
    projet = lance["corps"]["projet"]
    tableau, exploration = projet["tableau"], projet["cartes"]["exploration"]
    simule(pile, "reclamer", tableau, exploration)
    question = simule(pile, "question", tableau, exploration, "Quel nom donner au module ?")
    assert question["etat"] == "escaladee", question
    lecteur = Lecteur(pile, duree=170)
    try:
        _mesurer_le_delai(pile, lecteur, question)
    finally:
        lecteur.arreter()


def _mesurer_le_delai(pile, lecteur: Lecteur, question: Dict[str, Any]) -> None:
    assert lecteur.reponse()["statut"] == 200
    lecteur.etat()

    # Attendre le calme (la carte de planification de Hermes finit, l'émetteur passe) : 8 s sans trame de changement,
    # pour que la trame mesurée soit bien celle de la réponse.
    def calme(lignes) -> bool:
        changements = [l["t"] for l in lignes if l.get("trame", {}).get("event") == "changement"]
        dernier = max(changements) if changements else lignes[0]["t"]
        maintenant = float(pile.sh("date +%s.%N", verifier=True).stdout.strip())
        return maintenant - dernier >= 8
    lecteur.attendre(calme, 120, "le tableau de bord ne s'est jamais calmé")
    reponse = requete(pile, "POST", f"/v1/questions/{question['question']}/reponse", {"reponse": "« outil »."})
    assert reponse["code"] == 200, reponse
    trame = lecteur.attendre(
        lambda lignes: next((dict(l["trame"], t=l["t"]) for l in lignes if l.get("trame", {}).get("event") ==
                             "changement" and l["t"] > reponse["t"] - 1
                             and "questions" in l["trame"]["donnees"]["sujets"]), None),
        30, "aucune trame « questions » après la réponse")
    delai = trame["t"] - reponse["t"]
    afficher("flux : délai réponse → trame (six intergiciels, battement 15 s)",
             json.dumps({"delai_s": round(delai, 3), "trame": trame}, ensure_ascii=False))
    assert delai < 5.0, delai
    battements = [t for t in lecteur.trames() if t.get("commentaires") == ["battement"]]
    assert not battements or battements[0]["t"] - lecteur.lignes()[0]["t"] >= 14  # battement laissé à 15 s


def test_flux_battement_et_fin(pile):
    _reglage(pile, "flux_battement_s", 1)
    _reglage(pile, "flux_duree_max_s", 5)
    try:
        lecteur = Lecteur(pile, duree=60)
        debut = lecteur.reponse()["t"]
        fin = lecteur.fin(30)
        assert fin["fin"] == "serveur", fin
        trames = lecteur.trames()
        [derniere] = [t for t in trames if t.get("event") == "fin"]
        assert derniere["donnees"] == {"raison": "duree_max"} and "id" not in derniere
        assert 4.5 <= derniere["t"] - debut <= 9, derniere["t"] - debut
        battements = [t for t in trames if t.get("commentaires") == ["battement"]]
        assert len(battements) >= 3, trames
        afficher("flux : battements et fin (réglages abaissés)", json.dumps(
            [{"t": round(t["t"] - debut, 2), "event": t.get("event"), "commentaires": t.get("commentaires")}
             for t in trames], ensure_ascii=False))
    finally:
        _reglage(pile, "flux_battement_s", 15)
        _reglage(pile, "flux_duree_max_s", 600)


def test_flux_429_et_place_rendue_avant_le_battement(pile):
    _reglage(pile, "flux_max", 2)
    lecteurs: List[Lecteur] = []
    try:
        court = Lecteur(pile, duree=11)  # se déconnecte de lui-même après 11 s (avant le battement de 15 s)
        long = Lecteur(pile, duree=60)
        lecteurs += [court, long]
        assert court.reponse()["statut"] == 200 and long.reponse()["statut"] == 200
        court.etat()
        long.etat()
        refus = requete(pile, "GET", "/v1/flux", delai=8)
        assert refus["code"] == 429 and refus["entetes"]["retry-after"] == "30", refus
        assert refus["corps"] == {"detail": {"code": "trop_de_flux", "message": "Trop de pages ouvertes en temps "
                                                                                "réel : fermez-en une ou attendez."}}
        coupe = court.fin(30)
        assert coupe["fin"] == "duree", coupe
        debut = coupe["t"]
        rendu: Optional[float] = None
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            essai = Lecteur(pile, duree=1)
            reponse = essai.reponse()
            if reponse["statut"] == 200:
                rendu = reponse["t"] - debut
                break
            time.sleep(0.5)
        afficher("flux : place rendue après la déconnexion", json.dumps({"delai_s": rendu}))
        assert rendu is not None and rendu < 10, rendu
    finally:
        for lecteur in lecteurs:
            lecteur.arreter()
        _reglage(pile, "flux_max", 8)
