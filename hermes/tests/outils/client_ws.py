"""Client de TEST du vrai tableau de bord de Hermes par ``/api/ws`` (JSON-RPC sur WebSocket).

Lancé DANS le conteneur de test (bouclage local, interpréteur de Hermes, bibliothèque
``websockets`` de son environnement), avec un jeton d'identité du faux fournisseur :

1. ``POST /api/auth/ws-ticket`` avec ``Authorization: Bearer <jeton>`` : ticket à usage unique
   (hermes_cli/dashboard_auth/routes.py:458-470) ;
2. ``ws://127.0.0.1:9119/api/ws?ticket=…`` : la même surface JSON-RPC que le client Ink, servie
   DANS le processus du tableau de bord (hermes_cli/web_routers/chat_ws.py:583-601) ;
3. ``session.create`` puis, selon le mode :
   - ``preview-restart`` : ``preview.restart`` (tui_gateway/methods_prompt.py:1075-1133), avec
     « OUTIL:terminal » dans la console de l'aperçu, jusqu'à ``preview.restart.complete`` ;
   - ``session`` : rien de plus ; les outils de la session sont relevés dans ``session.info`` ;
   - ``prompt`` (étape P3) : ``prompt.submit`` avec le texte donné (tui_gateway/methods_prompt.py:564),
     jusqu'à ``message.complete`` : un tour complet de la discussion du tableau de bord.

Usage : python client_ws.py <preview-restart|session|prompt> <jeton> <fichier de sortie JSON> [texte]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request

import websockets

BASE = "127.0.0.1:9119"


def ticket(jeton: str) -> str:
    requete = urllib.request.Request(f"http://{BASE}/api/auth/ws-ticket", method="POST",
                                     headers={"Authorization": f"Bearer {jeton}"})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read())["ticket"]


async def dialoguer(mode: str, jeton: str, texte: str = "") -> dict:
    recus: list = []
    async with websockets.connect(f"ws://{BASE}/api/ws?ticket={ticket(jeton)}", max_size=None,
                                  open_timeout=30) as ws:

        async def attendre(predicat, delai: float = 180) -> dict:
            # Un message déjà reçu (l'ordre des événements n'est pas garanti) compte aussi.
            for message in recus:
                if predicat(message):
                    return message
            limite = time.monotonic() + delai
            while time.monotonic() < limite:
                brut = await asyncio.wait_for(ws.recv(), timeout=max(1.0, limite - time.monotonic()))
                message = json.loads(brut)
                recus.append(message)
                if predicat(message):
                    return message
            raise TimeoutError("réponse JSON-RPC attendue non reçue")

        def evenement(type_: str):
            return lambda m: m.get("method") == "event" and (m.get("params") or {}).get("type") == type_

        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {}}))
        session = (await attendre(lambda m: m.get("id") == 1))["result"]["session_id"]
        info = await attendre(evenement("session.info"), 120)
        resultat = {"session_id": session, "outils_session": (info["params"].get("payload") or {}).get("tools")}
        if mode == "preview-restart":
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "preview.restart", "params": {
                "session_id": session, "url": "http://127.0.0.1:1", "cwd": "/tmp", "context": "OUTIL:terminal"}}))
            resultat["reponse"] = await attendre(lambda m: m.get("id") == 2)
            resultat["fin"] = await attendre(evenement("preview.restart.complete"))
        elif mode == "prompt":
            # Le tableau de bord ne lance la découverte MCP qu'à la première connexion /api/ws et
            # n'attend que mcp_discovery_timeout (1,5 s) avant de figer les outils de la session ; une
            # découverte plus lente les ajoute avant le premier tour (tui_gateway/server.py:2243-2275).
            # On laisse ce délai passer avant d'envoyer le message.
            await asyncio.sleep(8)
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "prompt.submit",
                                      "params": {"session_id": session, "text": texte}}))
            resultat["reponse"] = await attendre(lambda m: m.get("id") == 2)
            resultat["fin"] = await attendre(evenement("message.complete"), 300)
    resultat["evenements"] = [m.get("params") for m in recus if m.get("method") == "event"
                              and (m.get("params") or {}).get("type", "").startswith("preview.restart")]
    return resultat


def main() -> int:
    mode, jeton, fichier = sys.argv[1], sys.argv[2], sys.argv[3]
    texte = sys.argv[4] if len(sys.argv) > 4 else ""
    if mode not in {"preview-restart", "session", "prompt"}:
        print(f"mode inconnu : {mode}", file=sys.stderr)
        return 2
    resultat = asyncio.run(dialoguer(mode, jeton, texte))
    with open(fichier, "w", encoding="utf-8") as flux:
        json.dump(resultat, flux, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
