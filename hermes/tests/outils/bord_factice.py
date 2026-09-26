"""Bord TLS FACTICE imitant le bord de Railway, pour les tests seulement (jamais déployé).

Ce qu'il imite (documentation Railway, rw_full.txt:33403) :
- terminaison TLS, puis relais en HTTP clair vers le service, avec l'en-tête Host d'origine ;
- en-têtes posés : ``X-Forwarded-Proto: https`` (toujours), ``X-Forwarded-Host`` (Host
  d'origine), ``X-Real-IP`` (adresse du client), ``X-Railway-Edge``, ``X-Request-Start`` et
  ``X-Railway-Request-Id`` ;
- routage par l'en-tête Host vers le service qui porte ce domaine ; hôte inconnu : 404.

Ce qu'il SUPPOSE, faute de documentation, et que seul un essai sur Railway tranchera
(docs/refonte/identite.md) : les en-têtes X-Forwarded-*, X-Real-IP, Forwarded et X-Railway-*
envoyés par le client sont RETIRÉS avant d'être reposés (jamais concaténés) ; aucun
X-Forwarded-For n'est posé (la documentation ne le cite pas).

Autres propriétés :
- les redirections ne sont jamais suivies, Set-Cookie est relayé tel quel (plusieurs en-têtes) ;
- le corps des réponses est relayé au fil de l'eau (flux SSE compris), puis la connexion est
  fermée (``Connection: close``) ;
- les WebSockets (``Upgrade: websocket``) sont relayés en tunnel brut après la requête d'amorce ;
- une requête au corps « chunked » est refusée (411) : aucun client des tests n'en envoie ;
- journal JSONL : méthode, hôte, CHEMIN SANS la requête (qui porte code et state OIDC), statut,
  pair, en-têtes du client retirés (noms seulement) ; jamais de corps, de cookie ni de valeur
  d'en-tête d'authentification.

Usage :
  python bord_factice.py --port 443 --certificat bord.pem --cle bord.key --journal /tmp/bord.jsonl \\
      --route hermes-acp.test=hermes-interne:9119 --route identite-acp.test=identite-interne:9091
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple

# En-têtes « hop-by-hop » (RFC 9110 §7.6.1) : jamais relayés tels quels.
SAUT = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "te", "trailer", "upgrade",
        "proxy-authenticate", "proxy-authorization"}
# En-têtes qu'un client ne doit pas pouvoir imposer au service (le bord les repose lui-même).
RETIRES_DU_CLIENT = ("x-forwarded-", "x-real-ip", "forwarded", "x-railway-", "x-request-start")


def _retire(nom: str) -> bool:
    nom = nom.lower()
    return any(nom == p or nom.startswith(p) for p in RETIRES_DU_CLIENT)


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--port", type=int, default=443)
    arguments.add_argument("--certificat", required=True)
    arguments.add_argument("--cle", required=True)
    arguments.add_argument("--journal", required=True)
    arguments.add_argument("--route", action="append", default=[], help="hôte=amont:port")
    options = arguments.parse_args()

    routes: Dict[str, Tuple[str, int]] = {}
    for route in options.route:
        hote, _, amont = route.partition("=")
        nom, _, port = amont.rpartition(":")
        routes[hote.lower()] = (nom, int(port))
    verrou = threading.Lock()

    def journaliser(entree: dict) -> None:
        ligne = json.dumps(entree, ensure_ascii=False)
        with verrou:
            with open(options.journal, "a", encoding="utf-8") as flux:
                flux.write(ligne + "\n")
        print(f"[bord-factice] {entree.get('methode')} {entree.get('hote')}{entree.get('chemin')} "
              f"→ {entree.get('statut')}", flush=True)

    class Relais(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "bord-factice"
        sys_version = ""

        def log_message(self, format: str, *args) -> None:  # noqa: A002 — journal JSONL à la place
            return

        def _repondre_simple(self, code: int, texte: str) -> None:
            corps = texte.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(corps)
            self.close_connection = True

        def _entetes_amont(self, hote: str, pair: str, identifiant: str) -> Tuple[List[Tuple[str, str]], List[str]]:
            relayes: List[Tuple[str, str]] = []
            retires: List[str] = []
            websocket = self.headers.get("Upgrade", "").lower() == "websocket"
            for nom, valeur in self.headers.items():
                bas = nom.lower()
                if _retire(bas):
                    retires.append(bas)
                    continue
                if bas in SAUT and not (websocket and bas in ("connection", "upgrade")):
                    continue
                relayes.append((nom, valeur))
            relayes += [
                ("X-Forwarded-Proto", "https"),
                ("X-Forwarded-Host", hote),
                ("X-Real-IP", pair),
                ("X-Railway-Edge", "bord-factice"),
                ("X-Request-Start", str(int(time.time() * 1000))),
                ("X-Railway-Request-Id", identifiant),
            ]
            return relayes, sorted(set(retires))

        def _traiter(self) -> None:
            debut = time.monotonic()
            identifiant = uuid.uuid4().hex
            pair = self.client_address[0]
            hote = (self.headers.get("Host") or "").split(":", 1)[0].lower()
            chemin = self.path.split("?", 1)[0]
            entree = {"t": round(time.time(), 3), "methode": self.command, "hote": hote, "chemin": chemin,
                      "pair": pair, "id": identifiant}
            amont = routes.get(hote)
            if amont is None:
                self._repondre_simple(404, "Application not found (bord factice)\n")
                journaliser(dict(entree, statut=404, amont=None))
                return
            relayes, retires = self._entetes_amont(hote, pair, identifiant)
            entree.update(amont=f"{amont[0]}:{amont[1]}", entetes_client_retires=retires,
                          entetes_poses=["x-forwarded-proto", "x-forwarded-host", "x-real-ip", "x-railway-edge",
                                         "x-request-start", "x-railway-request-id"])
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._tunnel(amont, relayes, entree)
                return
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                self._repondre_simple(411, "Corps « chunked » non pris en charge par le bord factice\n")
                journaliser(dict(entree, statut=411))
                return
            longueur = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(longueur) if longueur else None
            connexion = http.client.HTTPConnection(amont[0], amont[1], timeout=300)
            try:
                connexion.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for nom, valeur in relayes:
                    connexion.putheader(nom, valeur)
                connexion.endheaders(corps)
                reponse = connexion.getresponse()
            except OSError as exc:
                self._repondre_simple(502, f"Amont injoignable : {exc}\n")
                journaliser(dict(entree, statut=502, erreur=str(exc)))
                connexion.close()
                return
            try:
                # send_response_only : Date et Server viennent de l'amont, jamais en double.
                self.send_response_only(reponse.status, reponse.reason)
                for nom, valeur in reponse.getheaders():
                    if nom.lower() in SAUT or nom.lower() == "content-length" and reponse.chunked:
                        continue
                    self.send_header(nom, valeur)
                self.send_header("X-Railway-Edge", "bord-factice")
                self.send_header("X-Railway-Request-Id", identifiant)
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                if self.command != "HEAD" and reponse.status not in (204, 304):
                    while True:
                        morceau = reponse.read1(65536)
                        if not morceau:
                            break
                        self.wfile.write(morceau)
                        self.wfile.flush()
            except OSError:
                pass
            finally:
                connexion.close()
                journaliser(dict(entree, statut=reponse.status, duree_ms=int((time.monotonic() - debut) * 1000)))

        def _tunnel(self, amont: Tuple[str, int], relayes: List[Tuple[str, str]], entree: dict) -> None:
            """Relais WebSocket : requête d'amorce réécrite, puis octets bruts dans les deux sens."""
            try:
                vers_amont = socket.create_connection(amont, timeout=300)
            except OSError as exc:
                self._repondre_simple(502, f"Amont injoignable : {exc}\n")
                journaliser(dict(entree, statut=502, erreur=str(exc)))
                return
            lignes = [f"{self.command} {self.path} HTTP/1.1"] + [f"{n}: {v}" for n, v in relayes]
            vers_amont.sendall(("\r\n".join(lignes) + "\r\n\r\n").encode("latin-1"))
            client = self.connection
            fini = threading.Event()

            def amont_vers_client() -> None:
                try:
                    while not fini.is_set():
                        donnees = vers_amont.recv(65536)
                        if not donnees:
                            break
                        client.sendall(donnees)
                except OSError:
                    pass
                finally:
                    fini.set()

            fil = threading.Thread(target=amont_vers_client, daemon=True)
            fil.start()
            try:
                while not fini.is_set():
                    donnees = client.recv(65536)
                    if not donnees:
                        break
                    vers_amont.sendall(donnees)
            except OSError:
                pass
            finally:
                fini.set()
                for s in (vers_amont,):
                    try:
                        s.close()
                    except OSError:
                        pass
                self.close_connection = True
                journaliser(dict(entree, statut=101, tunnel="websocket"))

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _traiter

    serveur = ThreadingHTTPServer(("0.0.0.0", options.port), Relais)
    serveur.daemon_threads = True
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.minimum_version = ssl.TLSVersion.TLSv1_2
    contexte.load_cert_chain(options.certificat, options.cle)
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True)
    print(f"[bord-factice] port {options.port} ; routes : "
          + ", ".join(f"{h} → {a[0]}:{a[1]}" for h, a in routes.items()), flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
