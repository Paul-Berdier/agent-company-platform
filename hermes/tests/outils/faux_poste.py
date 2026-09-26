"""FAUX poste Windows, pour les tests de contrat seulement (étape P5) : il parle le protocole ``acp-machine/1`` au
VRAI tableau de bord de Hermes (bouclage local du conteneur de test, ``http://127.0.0.1:9119``), à travers la vraie
couture d'authentification par jeton. Il n'exécute rien : il s'enrôle, attend ses ordres en long-poll et publie
l'inventaire de l'exemple partagé (``fixtures_machine/inventaire_requete.json``, daté de maintenant).

Chaque réponse du greffon est validée par les MODÈLES DU CONTRAT PARTAGÉ (``acp_poste_contrat.machine``), comme le
fera le vrai poste : une réponse hors contrat fait échouer la commande (code 5).

Le jeton machine n'est JAMAIS imprimé : il est rangé dans ``/tmp/faux-poste/jeton`` (0600, conteneur jetable) ; les
sorties et le journal (``/tmp/faux-poste/journal.jsonl``) n'en portent que l'empreinte courte.

Sous-commandes (sortie : un objet JSON sur la dernière ligne de la sortie standard) :

  enroler <code> [--nom N]            enrôlement (porteur : code d'enrôlement)
  appel <route> [--porteur P] [--corps JSON|@fichier] [--brut TEXTE]
                                      appel d'une route machine (P : jeton, aucun, code:<code>, brut:<valeur>,
                                      fichier:<chemin>)
  reclamer [--attente N] [--acquitter 1,2]   une réclamation (long-poll)
  inventaire                          publie l'inventaire de l'exemple (daté de maintenant)
  servir [--attente N] [--duree S]    boucle : réclamer, acquitter, publier sur ordre « releve » ; s'arrête sur 401
                                      poste_revoque (jeton effacé, code 0), sur le 401 de la couture (jeton gardé, code 4)
                                      ou à la fin de la durée (code 0)
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/hermes/plugins/acp-poste/contrat")

from acp_poste_contrat import machine as contrat  # noqa: E402

DOSSIER = Path("/tmp/faux-poste")
JETON = DOSSIER / "jeton"
JOURNAL = DOSSIER / "journal.jsonl"
FIXTURES = Path("/opt/acp-tests/outils/fixtures_machine")
HOTE, PORT = "127.0.0.1", 9119
ENTETES = {"Content-Type": "application/json", "Accept": "application/json",
           "User-Agent": "acp-poste/0.11.0 (acp-machine/1) faux-poste-de-test", "X-ACP-Protocole": contrat.PROTOCOLE}


def _sortie(objet, code: int = 0) -> int:
    os.write(1, (json.dumps(objet, ensure_ascii=False) + "\n").encode("utf-8"))
    return code


def _journaliser(evenement: str, **details) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    ligne = {"quand": round(time.time(), 3), "evenement": evenement, **details}
    with JOURNAL.open("a", encoding="utf-8") as flux:
        flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def _jeton() -> str:
    return JETON.read_text(encoding="ascii").strip()


def _empreinte(jeton: str) -> str:
    return contrat.empreinte_courte(contrat.empreinte_jeton(jeton))


def poster(route: str, corps, porteur: str | None, *, brut: bytes | None = None, delai: float = 70):
    """(statut, corps décodé, en-têtes utiles, durée) d'un POST sur une route machine."""
    entetes = dict(ENTETES)
    if porteur:
        entetes["Authorization"] = f"Bearer {porteur}"
    donnees = brut if brut is not None else json.dumps(corps).encode("utf-8")
    connexion = http.client.HTTPConnection(HOTE, PORT, timeout=delai)
    debut = time.monotonic()
    try:
        connexion.request("POST", route, body=donnees, headers=entetes)
        reponse = connexion.getresponse()
        contenu = reponse.read(contrat.TAILLE_MAX_REPONSE + 1)
        garder = {k.lower(): v for k, v in reponse.getheaders() if k.lower() in ("cache-control", "retry-after")}
        statut = reponse.status
    finally:
        connexion.close()
    try:
        decode = json.loads(contenu.decode("utf-8"))
    except ValueError:
        decode = contenu.decode("utf-8", "replace")
    return statut, decode, garder, round(time.monotonic() - debut, 3)


def _porteur(valeur: str | None) -> str | None:
    if valeur in (None, "jeton"):
        return _jeton()
    if valeur == "aucun":
        return None
    if valeur.startswith("code:"):
        return valeur[5:]
    if valeur.startswith("brut:"):
        return valeur[5:]
    if valeur.startswith("fichier:"):
        return Path(valeur[8:]).read_text(encoding="ascii").strip()
    raise SystemExit(f"porteur inconnu : {valeur}")


def inventaire_de_l_exemple() -> dict:
    inventaire = json.loads((FIXTURES / "inventaire_requete.json").read_text(encoding="utf-8"))
    quand = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    inventaire["releve_le"] = quand
    inventaire["bac_a_sable_codex"]["lu_le"] = quand
    for releve in inventaire["releves"]:
        releve["releve_le"] = quand
        for compteur in releve["compteurs"]:
            compteur["observed_at"] = quand
    return inventaire


def _valider(modele, corps, quoi: str):
    try:
        return contrat.valider(modele, corps, quoi=quoi)
    except ValueError as exc:
        _journaliser("hors_contrat", quoi=quoi, detail=str(exc)[:300])
        raise SystemExit(_sortie({"erreur": "réponse hors contrat", "detail": str(exc)[:300]}, 5))


def enroler(code: str, nom: str) -> int:
    requete = dict(json.loads((FIXTURES / "enrolement_requete.json").read_text(encoding="utf-8")), nom=nom)
    statut, corps, entetes, duree = poster(contrat.ROUTE_ENROLEMENT, requete, code)
    if statut != 201:
        return _sortie({"statut": statut, "corps": corps}, 3)
    reponse = _valider(contrat.ReponseEnrolement, corps, "réponse d'enrôlement")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    JETON.write_text(reponse.jeton, encoding="ascii")
    os.chmod(JETON, 0o600)
    _journaliser("enrolement", machine=reponse.machine_id, empreinte=reponse.empreinte)
    return _sortie({"statut": statut, "machine_id": reponse.machine_id, "empreinte": reponse.empreinte,
                    "empreinte_recalculee": _empreinte(reponse.jeton), "etat": reponse.etat,
                    "cache_control": entetes.get("cache-control"), "duree": duree})


def reclamer(attente: int, acquittes) -> tuple:
    requete = dict(json.loads((FIXTURES / "reclamer_requete.json").read_text(encoding="utf-8")),
                   ordres_acquittes=list(acquittes), attente_max_s=attente)
    return poster(contrat.ROUTE_RECLAMER, requete, _jeton(), delai=attente + 15)


def servir(attente: int, duree: float) -> int:
    fin = time.monotonic() + duree
    acquittes: list = []
    while time.monotonic() < fin:
        try:
            statut, corps, _entetes, temps = reclamer(attente, acquittes)
        except OSError as exc:  # Hermes redémarre : repli court, puis nouvel essai
            _journaliser("reseau", detail=type(exc).__name__)
            time.sleep(1)
            continue
        acquittes = []
        if statut == 401:
            if isinstance(corps, dict) and corps == contrat.CORPS_401_COUTURE:
                _journaliser("couture_401")
                return _sortie({"arret": "couture_401", "jeton_garde": JETON.exists()}, 4)
            detail = _valider(contrat.ErreurMachine, corps, "erreur 401").detail
            if detail.code == "poste_revoque":
                JETON.unlink(missing_ok=True)
                _journaliser("poste_revoque", message=detail.message)
                return _sortie({"arret": "poste_revoque", "message": detail.message, "jeton_garde": JETON.exists()})
        if statut in (502, 503, 504) or statut >= 500:
            _journaliser("indisponible", statut=statut)
            time.sleep(1)
            continue
        if statut != 200:
            _journaliser("refus", statut=statut, corps=corps)
            return _sortie({"arret": "refus", "statut": statut, "corps": corps}, 2)
        reponse = _valider(contrat.ReponseReclamer, corps, "réponse de réclamation")
        _journaliser("reclamer", duree=temps, ordres=[o.id for o in reponse.ordres], etat=reponse.etat_machine,
                     remplace=reponse.remplace)
        for ordre in reponse.ordres:
            if ordre.genre == "releve":
                statut_i, corps_i, _e, _t = poster(contrat.ROUTE_INVENTAIRE, inventaire_de_l_exemple(), _jeton())
                _journaliser("inventaire", ordre=ordre.id, statut=statut_i)
            acquittes.append(ordre.id)
        if reponse.prochaine_attente_s:
            time.sleep(min(reponse.prochaine_attente_s, 5))
    return _sortie({"arret": "duree"})


def main(argv) -> int:
    analyseur = argparse.ArgumentParser()
    sous = analyseur.add_subparsers(dest="commande", required=True)
    a = sous.add_parser("enroler")
    a.add_argument("code")
    a.add_argument("--nom", default="Poste de contrat")
    a = sous.add_parser("appel")
    a.add_argument("route", choices=("enrolement", "reclamer", "inventaire"))
    a.add_argument("--porteur", default="jeton")
    a.add_argument("--corps", default=None)
    a.add_argument("--brut", default=None)
    a.add_argument("--type", default=None)
    a = sous.add_parser("reclamer")
    a.add_argument("--attente", type=int, default=5)
    a.add_argument("--acquitter", default="")
    sous.add_parser("inventaire")
    a = sous.add_parser("servir")
    a.add_argument("--attente", type=int, default=25)
    a.add_argument("--duree", type=float, default=600)
    arguments = analyseur.parse_args(argv)
    if arguments.commande == "enroler":
        return enroler(arguments.code, arguments.nom)
    if arguments.commande == "appel":
        route = {"enrolement": contrat.ROUTE_ENROLEMENT, "reclamer": contrat.ROUTE_RECLAMER,
                 "inventaire": contrat.ROUTE_INVENTAIRE}[arguments.route]
        corps = None
        if arguments.corps:
            corps = json.loads(Path(arguments.corps[1:]).read_text(encoding="utf-8")) if arguments.corps.startswith("@") \
                else json.loads(arguments.corps)
        if arguments.type:
            ENTETES["Content-Type"] = arguments.type
        statut, reponse, entetes, duree = poster(route, corps if corps is not None else {}, _porteur(arguments.porteur),
                                                brut=arguments.brut.encode("utf-8") if arguments.brut else None)
        return _sortie({"statut": statut, "corps": reponse, "entetes": entetes, "duree": duree})
    if arguments.commande == "reclamer":
        acquittes = [int(x) for x in arguments.acquitter.split(",") if x]
        statut, corps, entetes, duree = reclamer(arguments.attente, acquittes)
        if statut == 200:
            _valider(contrat.ReponseReclamer, corps, "réponse de réclamation")
        return _sortie({"statut": statut, "corps": corps, "entetes": entetes, "duree": duree})
    if arguments.commande == "inventaire":
        statut, corps, entetes, duree = poster(contrat.ROUTE_INVENTAIRE, inventaire_de_l_exemple(), _jeton())
        if statut == 200:
            _valider(contrat.ReponseInventaire, corps, "réponse d'inventaire")
        return _sortie({"statut": statut, "corps": corps, "entetes": entetes, "duree": duree})
    return servir(arguments.attente, arguments.duree)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
