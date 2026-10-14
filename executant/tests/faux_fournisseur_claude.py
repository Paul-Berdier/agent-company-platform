"""Fournisseur Anthropic Messages FACTICE : outils imposés, aucune inférence réelle.

Uniquement dans le conteneur jetable du témoin Claude. Écoute 127.0.0.1, ne
contacte aucun autre service, ne journalise ni en-têtes ni contenu sur disque.
Les requêtes sont conservées en mémoire pour rechercher les canaris interdits.
Une nouvelle étape exige le retour tool_result de la précédente : les tentatives,
les reprises HTTP et les simples messages de refus ne font pas avancer le test.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def resultats_outils(corps: dict) -> dict[str, dict]:
    resultats = {}
    for message in corps.get("messages", []):
        contenu = message.get("content")
        if message.get("role") != "user" or not isinstance(contenu, list):
            continue
        for bloc in contenu:
            if isinstance(bloc, dict) and bloc.get("type") == "tool_result":
                resultats[bloc.get("tool_use_id")] = bloc
    return resultats


def message(rang: int, modele: str, *, appel: dict | None = None) -> dict:
    contenu = ([{"type": "tool_use", "id": f"toolu_acp_{rang}", "name": appel["name"],
                 "input": appel["input"]}] if appel else [{"type": "text", "text": "Temoin termine."}])
    return {"id": f"msg_acp_{rang}", "type": "message", "role": "assistant", "model": modele,
            "content": contenu, "stop_reason": "tool_use" if appel else "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def evenements(reponse: dict) -> list[tuple[str, dict]]:
    debut = dict(reponse, content=[], stop_reason=None, usage={"input_tokens": 10, "output_tokens": 0})
    events = [("message_start", {"type": "message_start", "message": debut})]
    for index, bloc in enumerate(reponse["content"]):
        outil = bloc["type"] == "tool_use"
        initial = dict(bloc, input={}) if outil else dict(bloc, text="")
        delta = ({"type": "input_json_delta", "partial_json": json.dumps(bloc["input"])} if outil
                 else {"type": "text_delta", "text": bloc["text"]})
        events.extend([
            ("content_block_start", {"type": "content_block_start", "index": index, "content_block": initial}),
            ("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}),
            ("content_block_stop", {"type": "content_block_stop", "index": index}),
        ])
    events.extend([
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": reponse["stop_reason"],
                                                               "stop_sequence": None},
                           "usage": {"output_tokens": 5}}),
        ("message_stop", {"type": "message_stop"}),
    ])
    return events


@contextmanager
def fournisseur(appels: list[dict]):
    """Les appels sont déterminés par le test, jamais par un modèle distant."""
    etat = {"requetes": [], "resultats": {}, "emis": [], "erreurs": [], "outils": []}
    verrou = threading.Lock()

    class Gestion(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_args):
            pass

        def _json(self, status: int, corps: dict):
            brut = json.dumps(corps).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(brut)))
            self.end_headers()
            self.wfile.write(brut)

        def do_GET(self):  # noqa: N802
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "Temoin local"}})

        def do_POST(self):  # noqa: N802
            try:
                longueur = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(400, {"error": "Content-Length invalide"})
                return
            if not 0 < longueur <= 4 * 1024 * 1024:
                self._json(413, {"error": "requete hors borne"})
                return
            try:
                corps = json.loads(self.rfile.read(longueur))
            except (ValueError, UnicodeDecodeError, TimeoutError):
                self._json(400, {"error": "JSON invalide"})
                return
            if not isinstance(corps, dict):
                self._json(400, {"error": "objet JSON attendu"})
                return
            with verrou:
                etat["requetes"].append({"chemin": self.path, "corps": corps})
                if len(etat["requetes"]) > 80:
                    etat["erreurs"].append("trop de requetes")
                    self._json(429, {"error": "temoin hors borne"})
                    return
                if urlsplit(self.path).path == "/v1/messages/count_tokens":
                    self._json(200, {"input_tokens": 10})
                    return
                if urlsplit(self.path).path != "/v1/messages":
                    self._json(404, {"error": "route non prise en charge"})
                    return
                outils = {outil["name"] for outil in corps.get("tools", [])}
                principal = {"Read", "Write", "Grep", "Glob"}.issubset(outils)
                if principal:
                    etat["outils"] = sorted(outils)
                    etat["resultats"].update(resultats_outils(corps))
                    rang = 0
                    while rang < len(appels) and f"toolu_acp_{rang}" in etat["resultats"]:
                        rang += 1
                    appel = appels[rang] if rang < len(appels) else None
                    if appel is not None:
                        etat["emis"].append(rang)
                    reponse = message(rang, corps.get("model", "claude-opus-5-5"), appel=appel)
                else:
                    # Les petites requêtes auxiliaires ne consomment jamais le scénario.
                    reponse = message(999, corps.get("model", "claude-opus-5-5"))
            if not corps.get("stream"):
                self._json(200, reponse)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for nom, donnees in evenements(reponse):
                    self.wfile.write(f"event: {nom}\ndata: {json.dumps(donnees)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.close_connection = True

    class Serveur(ThreadingHTTPServer):
        daemon_threads = True
        block_on_close = False

    serveur = Serveur(("127.0.0.1", 0), Gestion)
    fil = threading.Thread(target=lambda: serveur.serve_forever(poll_interval=0.1), daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{serveur.server_port}", etat
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)
