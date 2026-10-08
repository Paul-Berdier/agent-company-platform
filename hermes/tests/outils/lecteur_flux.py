"""Lecteur du flux d'invalidation GET /api/plugins/acp-poste/v1/flux, pour les tests seulement (étape P7).

Lancé DANS le conteneur Hermes du contrat (``docker exec -d``), en bouclage local, derrière la vraie porte
d'authentification (jeton porteur du fournisseur d'identité factice) et les six intergiciels du tableau de bord. Il
écrit une ligne JSON par événement, horodatée par l'horloge du conteneur (la même que celle des requêtes du test) :

  {"t": …, "pid": …, "statut": 200, "entetes": {…}}    réponse reçue
  {"t": …, "trame": {"event": …, "id": …, "data": …, "donnees": {…}, "commentaires": [...], "retry": …}}
  {"t": …, "fin": "serveur" | "duree" | "erreur", "detail": …}

Le lecteur s'arrête quand le serveur ferme le flux, ou après ``--duree`` secondes : il ferme alors la connexion
(déconnexion RÉELLE du client, que le serveur doit voir).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from typing import Any, Dict

import httpx


def ecrire(journal: str, donnees: Dict[str, Any]) -> None:
    with open(journal, "a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(dict(donnees, t=time.time()), ensure_ascii=False) + "\n")


def analyser(brut: str) -> Dict[str, Any]:
    trame: Dict[str, Any] = {}
    for ligne in brut.split("\n"):
        if ligne.startswith(":"):
            trame.setdefault("commentaires", []).append(ligne[1:].strip())
            continue
        champ, _, valeur = ligne.partition(":")
        trame[champ] = valeur[1:] if valeur.startswith(" ") else valeur
    if "data" in trame:
        try:
            trame["donnees"] = json.loads(trame["data"])
        except ValueError:
            trame["donnees"] = None
    return trame


def principal() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--url", default="http://127.0.0.1:9119/api/plugins/acp-poste/v1/flux")
    parseur.add_argument("--jeton", required=True)
    parseur.add_argument("--journal", required=True)
    parseur.add_argument("--dernier-id")
    parseur.add_argument("--duree", type=float, default=60.0)
    arguments = parseur.parse_args()
    entetes = {"Authorization": f"Bearer {arguments.jeton}", "Accept": "text/event-stream"}
    if arguments.dernier_id:
        entetes["Last-Event-ID"] = arguments.dernier_id
    client = httpx.Client(timeout=httpx.Timeout(30.0, read=None))
    try:
        reponse = client.send(client.build_request("GET", arguments.url, headers=entetes), stream=True)
    except httpx.HTTPError as exc:
        ecrire(arguments.journal, {"fin": "erreur", "detail": type(exc).__name__})
        return 1
    ecrire(arguments.journal, {"pid": os.getpid(), "statut": reponse.status_code,
                               "entetes": {k.lower(): v for k, v in reponse.headers.items()}})
    if reponse.status_code != 200:
        ecrire(arguments.journal, {"fin": "serveur", "corps": reponse.read().decode("utf-8", "replace")[:2000]})
        return 0

    def couper() -> None:
        # Déconnexion réelle : ``shutdown`` réveille la lecture bloquée et envoie la fin de connexion au serveur.
        ecrire(arguments.journal, {"fin": "duree"})
        flux_reseau = reponse.extensions.get("network_stream")
        sock = flux_reseau.get_extra_info("socket") if flux_reseau is not None else None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    minuterie = threading.Timer(arguments.duree, couper)
    minuterie.daemon = True
    minuterie.start()
    tampon = b""
    try:
        for morceau in reponse.iter_raw():
            tampon += morceau
            while b"\n\n" in tampon:
                brut, tampon = tampon.split(b"\n\n", 1)
                ecrire(arguments.journal, {"trame": analyser(brut.decode("utf-8"))})
        if minuterie.is_alive():
            minuterie.cancel()
            ecrire(arguments.journal, {"fin": "serveur"})
    except Exception as exc:  # noqa: BLE001 — coupure par la minuterie, ou réseau
        if minuterie.is_alive():
            minuterie.cancel()
            ecrire(arguments.journal, {"fin": "erreur", "detail": type(exc).__name__})
    finally:
        try:
            reponse.close()
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
