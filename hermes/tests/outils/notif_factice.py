"""Faux serveur ntfy de TEST (étape P4), en HTTPS : il reçoit les notifications de l'émetteur d'acp-poste
à la place de ``https://ntfy.sh``. Jamais dans l'image Railway.

Certificat ``ntfy.acp.test`` signé par l'autorité jetable de l'image de test. Chaque requête est
consignée (une ligne JSON) : méthode, chemin, PRÉSENCE et empreinte SHA-256 de ``Authorization`` (jamais
sa valeur), en-têtes ``Title``, ``Click``, ``Priority`` et corps. ``--echecs N`` fait répondre 500 aux N
premières requêtes (preuve de la reprise).

Usage : python notif_factice.py --port 443 --certificat ntfy.pem --cle ntfy.key --journal /tmp/ntfy.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--hote", default="0.0.0.0")
    arguments.add_argument("--port", type=int, default=443)
    arguments.add_argument("--certificat", required=True)
    arguments.add_argument("--cle", required=True)
    arguments.add_argument("--journal", required=True)
    arguments.add_argument("--echecs", type=int, default=0)
    options = arguments.parse_args()
    verrou = threading.Lock()
    compteur = {"n": 0}

    class Gestionnaire(BaseHTTPRequestHandler):
        def _repondre(self, code: int) -> None:
            corps = json.dumps({"id": "factice", "event": "message"}).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_POST(self) -> None:  # noqa: N802
            longueur = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(longueur).decode("utf-8", "replace")
            autorisation = self.headers.get("Authorization")
            with verrou:
                compteur["n"] += 1
                rang = compteur["n"]
            code = 500 if rang <= options.echecs else 200
            entree = {"t": time.time(), "methode": "POST", "chemin": self.path, "code": code,
                      "autorisation_presente": autorisation is not None,
                      "autorisation_sha256": hashlib.sha256(autorisation.encode("utf-8")).hexdigest()
                      if autorisation else None,
                      "title": self.headers.get("Title"), "click": self.headers.get("Click"),
                      "priority": self.headers.get("Priority"), "corps": corps}
            with verrou, open(options.journal, "a", encoding="utf-8") as flux:
                flux.write(json.dumps(entree, ensure_ascii=False) + "\n")
            self._repondre(code)

        def do_GET(self) -> None:  # noqa: N802
            self._repondre(200)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    serveur = ThreadingHTTPServer((options.hote, options.port), Gestionnaire)
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.load_cert_chain(options.certificat, options.cle)
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True)
    print(f"[notif-factice] https://{options.hote}:{options.port}", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
