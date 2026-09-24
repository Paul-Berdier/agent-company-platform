"""Modèle factice compatible OpenAI, pour les tests : aucun appel réseau réel.

Répond sur ``/v1/models`` et ``/v1/chat/completions`` (réponse unique ou flux SSE) par un
texte fixe, et consigne chaque requête reçue, une ligne JSON par requête, dans le journal
donné. Les tests s'en servent pour configurer Hermes sans fournisseur réel et pour
prouver qu'un scénario n'a appelé AUCUN modèle (journal vide).

Usage : python modele_factice.py --port 18080 --journal /tmp/modele-factice.jsonl
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPONSE = "Réponse du modèle factice ACP."
MODELE = "acp-factice"


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--hote", default="127.0.0.1")
    arguments.add_argument("--port", type=int, default=18080)
    arguments.add_argument("--journal", required=True)
    options = arguments.parse_args()
    verrou = threading.Lock()

    def consigner(entree: dict) -> None:
        with verrou, open(options.journal, "a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")

    class Gestionnaire(BaseHTTPRequestHandler):
        def _json(self, code: int, corps: object) -> None:
            donnees = json.dumps(corps).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def do_GET(self) -> None:  # noqa: N802
            consigner({"methode": "GET", "chemin": self.path, "t": time.time()})
            if self.path.rstrip("/").endswith("/models"):
                self._json(200, {"object": "list", "data": [{"id": MODELE, "object": "model", "owned_by": "acp"}]})
            else:
                self._json(404, {"error": {"message": "inconnu"}})

        def do_POST(self) -> None:  # noqa: N802
            longueur = int(self.headers.get("Content-Length") or 0)
            try:
                corps = json.loads(self.rfile.read(longueur) or b"{}")
            except ValueError:
                corps = {}
            consigner({"methode": "POST", "chemin": self.path, "modele": corps.get("model"),
                       "flux": bool(corps.get("stream")), "t": time.time()})
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._json(404, {"error": {"message": "inconnu"}})
                return
            identifiant = f"chatcmpl-{uuid.uuid4().hex}"
            cree = int(time.time())
            if corps.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                morceaux = [
                    {"role": "assistant", "content": ""},
                    {"content": REPONSE},
                ]
                for delta in morceaux:
                    evenement = {"id": identifiant, "object": "chat.completion.chunk", "created": cree,
                                 "model": MODELE, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(evenement)}\n\n".encode("utf-8"))
                fin = {"id": identifiant, "object": "chat.completion.chunk", "created": cree, "model": MODELE,
                       "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
                self.wfile.write(f"data: {json.dumps(fin)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return
            self._json(200, {
                "id": identifiant, "object": "chat.completion", "created": cree, "model": MODELE,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": REPONSE},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    serveur = ThreadingHTTPServer((options.hote, options.port), Gestionnaire)
    print(f"[modele-factice] http://{options.hote}:{options.port}/v1", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
