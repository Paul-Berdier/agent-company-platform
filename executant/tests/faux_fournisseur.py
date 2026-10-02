"""FAUX fournisseur de modèle pour Codex CLI (API « responses », flux SSE), pour les tests de l'image de l'exécutant.

Il remplace OpenAI dans un conteneur jetable SANS réseau : ``codex exec`` le joint par
``-c model_provider="faux"`` et ``-c model_providers.faux={…base_url="http://127.0.0.1:<port>/v1"…}``, sans aucun
identifiant. Il ne prouve rien de la qualité d'un modèle : il fait exécuter à Codex des appels d'outil CHOISIS par le
test (une commande qui tente de lire ``auth.json``, par exemple), puis rend la sortie structurée attendue, et il
journalise chaque requête reçue (le résultat de l'outil y revient, dans ``function_call_output``).

    python3 faux_fournisseur.py <port> <scenario.json> <journal.jsonl>

Scénario : ``{"reponses": [<réponse>…]}`` ; la n-ième requête reçoit la n-ième réponse (la dernière se répète).
Une réponse : ``{"appel": {"name": "<outil>", "arguments": {…}}}``, ``{"libre": {"name": "<outil>", "input": "…"}}``
(outil à entrée libre, comme ``apply_patch``) ou ``{"message": "<texte>"}``.
Bibliothèque standard seulement.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USAGE = {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 5,
         "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 15}


def evenements(rang: int, reponse: dict) -> list[tuple[str, dict]]:
    ident = f"resp_{rang}"
    if "appel" in reponse:
        appel = reponse["appel"]
        item = {"type": "function_call", "id": f"fc_{rang}", "call_id": f"call_{rang}", "name": appel["name"],
                "arguments": json.dumps(appel.get("arguments", {}))}
    elif "libre" in reponse:  # outil à entrée libre (« apply_patch » de Codex 0.156.1)
        libre = reponse["libre"]
        item = {"type": "custom_tool_call", "id": f"ctc_{rang}", "call_id": f"call_{rang}", "name": libre["name"],
                "input": libre["input"]}
    else:
        item = {"type": "message", "role": "assistant", "id": f"msg_{rang}", "status": "completed",
                "content": [{"type": "output_text", "text": reponse.get("message", ""), "annotations": []}]}
    return [("response.created", {"type": "response.created", "response": {"id": ident}}),
            ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
            ("response.completed", {"type": "response.completed", "response": {"id": ident, "usage": USAGE}})]


def main(argv: list[str]) -> int:
    port, scenario_chemin, journal = int(argv[1]), argv[2], argv[3]
    with open(scenario_chemin, encoding="utf-8") as flux:
        reponses = json.load(flux)["reponses"]
    verrou = threading.Lock()
    compteur = [0]

    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # silencieux
            pass

        def _journal(self, entree: dict) -> None:
            with verrou, open(journal, "a", encoding="utf-8") as flux:
                flux.write(json.dumps(entree, ensure_ascii=False) + "\n")

        def do_GET(self) -> None:  # noqa: N802
            self._journal({"methode": "GET", "chemin": self.path})
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            longueur = int(self.headers.get("Content-Length") or 0)
            brut = self.rfile.read(longueur) if longueur else b""
            try:
                corps = json.loads(brut.decode("utf-8")) if brut else None
            except ValueError:
                corps = None
            with verrou:
                rang = compteur[0]
                compteur[0] += 1
            self._journal({"methode": "POST", "chemin": self.path, "rang": rang, "corps": corps})
            if not self.path.endswith("/responses"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            reponse = reponses[min(rang, len(reponses) - 1)]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for nom, donnees in evenements(rang, reponse):
                self.wfile.write(f"event: {nom}\ndata: {json.dumps(donnees)}\n\n".encode("utf-8"))
            self.wfile.flush()
            self.close_connection = True

    serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
    print(f"[faux-fournisseur] port {port}", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
