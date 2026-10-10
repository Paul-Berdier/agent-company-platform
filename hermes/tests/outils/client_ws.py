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
   Dans ces trois modes, la sortie porte aussi ``cle`` (étape P9) : la clé stockée de la session
   (``stored_session_id``), sous laquelle ``/api/sessions`` la liste.

Étape P7, part D (cahier P7 § 9.4) : trois modes de la discussion réduite, avec les SEULES méthodes de la liste blanche
d'ACP (apps/interface/src/jsonrpc/canal.ts) :
   - ``clarify-poser`` : ``client.capabilities {server_requests: true}``, ``session.create {}``, ``prompt.submit`` du
     texte donné (« OUTIL:clarify » : le modèle factice appelle l'outil clarify), attend la requête ``clarify`` du
     serveur, puis SE DÉCONNECTE sans répondre (le téléphone se ferme) ;
   - ``clarify-reprendre`` (texte = clé stockée de la session, puis la réponse) : un SECOND client lit
     ``session.active_list`` sans capacités (lecture seule, comme la file Questions), puis annonce ses capacités, fait
     ``session.resume {session_id: clé}``, reçoit la même requête dans ``open_requests``, y répond
     (``{answers}`` pour un lot, ``{answer}`` sinon) et attend ``message.complete`` ;
   - ``clarify-interrompre`` : comme ``clarify-poser``, puis ``session.interrupt`` pendant la question : attend
     ``request.cancel`` et ``message.complete``.

Usage : python client_ws.py <mode> <jeton> <fichier de sortie JSON> [texte] [réponse]
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
        creee = (await attendre(lambda m: m.get("id") == 1))["result"]
        session = creee["session_id"]
        info = await attendre(evenement("session.info"), 120)
        # Étape P9 : « cle » = clé STOCKÉE de la session (stored_session_id), celle que liste /api/sessions ;
        # « session_id » n'est que l'identifiant de la connexion /api/ws.
        resultat = {"session_id": session, "cle": creee.get("stored_session_id"),
                    "outils_session": (info["params"].get("payload") or {}).get("tools")}
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


class Fil:
    """Une connexion /api/ws : envoi numéroté, messages reçus gardés (l'ordre des trames n'est pas garanti)."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.recus: list = []
        self.numero = 0

    async def attendre(self, predicat, delai: float = 240) -> dict:
        for message in self.recus:
            if predicat(message):
                return message
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            brut = await asyncio.wait_for(self.ws.recv(), timeout=max(1.0, limite - time.monotonic()))
            for ligne in str(brut).splitlines():
                if ligne.strip():
                    message = json.loads(ligne)
                    self.recus.append(message)
                    if predicat(message):
                        return message
        raise TimeoutError("message JSON-RPC attendu non reçu")

    async def appeler(self, methode: str, params: dict, delai: float = 120):
        self.numero += 1
        numero = f"acp-{self.numero}"
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": numero, "method": methode, "params": params}) + "\n")
        reponse = await self.attendre(lambda m: m.get("id") == numero and "method" not in m, delai)
        if "error" in reponse:
            raise RuntimeError(f"{methode} refusée : {reponse['error']}")
        return reponse["result"]

    def evenements(self, session: str) -> list:
        return [m["params"]["type"] for m in self.recus if m.get("method") == "event"
                and (m.get("params") or {}).get("session_id") == session]


def _requete_clarify(m: dict) -> bool:
    return m.get("method") == "clarify" and isinstance(m.get("id"), str)


def _evenement(type_: str, session: str):
    return lambda m: (m.get("method") == "event" and (m.get("params") or {}).get("type") == type_
                      and (m.get("params") or {}).get("session_id") == session)


async def clarify(mode: str, jeton: str, texte: str, reponse: str) -> dict:
    async with websockets.connect(f"ws://{BASE}/api/ws?ticket={ticket(jeton)}", max_size=None,
                                  open_timeout=30) as ws:
        fil = Fil(ws)
        await fil.attendre(lambda m: (m.get("params") or {}).get("type") == "gateway.ready", 60)
        if mode == "clarify-reprendre":
            cle = texte
            # Lecture seule d'abord, SANS capacités (comme la file Questions d'ACP).
            actives = await fil.appeler("session.active_list", {})
            attente = [{"status": s.get("status"), "session_key": s.get("session_key"), "id": s.get("id")}
                       for s in actives.get("sessions", []) if s.get("session_key") == cle]
            capacites = await fil.appeler("client.capabilities", {"server_requests": True})
            reprise = await fil.appeler("session.resume", {"session_id": cle})
            session = reprise["session_id"]
            ouvertes = reprise.get("open_requests") or []
            [ouverte] = [r for r in ouvertes if r.get("method") == "clarify"]
            questions = (ouverte.get("params") or {}).get("questions")
            resultat_clarify = ({"answers": {q["qid"]: reponse for q in questions}} if questions
                                else {"answer": reponse})
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": ouverte["id"], "result": resultat_clarify}) + "\n")
            fin = await fil.attendre(_evenement("message.complete", session), 240)
            return {"attente": attente, "capacites": capacites, "session_id": session,
                    "statut_reprise": reprise.get("status"), "open_requests": ouvertes,
                    "reponse_envoyee": resultat_clarify, "fin": fin["params"].get("payload"),
                    "evenements": fil.evenements(session)}
        capacites = await fil.appeler("client.capabilities", {"server_requests": True})
        creee = await fil.appeler("session.create", {})
        session = creee["session_id"]
        # Laisse passer la découverte MCP du tableau de bord (voir le mode « prompt »).
        await asyncio.sleep(8)
        envoi = await fil.appeler("prompt.submit", {"session_id": session, "text": texte})
        requete = await fil.attendre(_requete_clarify, 240)
        resultat = {"capacites": capacites, "session_id": session, "cle": creee.get("stored_session_id"),
                    "envoi": envoi, "requete": requete}
        if mode == "clarify-interrompre":
            resultat["interruption"] = await fil.appeler("session.interrupt", {"session_id": session})
            annulee = await fil.attendre(_evenement("request.cancel", session), 120)
            fin = await fil.attendre(_evenement("message.complete", session), 120)
            resultat["annulation"] = annulee["params"].get("payload")
            resultat["fin"] = fin["params"].get("payload")
            resultat["evenements"] = fil.evenements(session)
        # Fin du bloc : la connexion se ferme SANS avoir répondu (le téléphone se ferme).
        return resultat


def main() -> int:
    mode, jeton, fichier = sys.argv[1], sys.argv[2], sys.argv[3]
    texte = sys.argv[4] if len(sys.argv) > 4 else ""
    reponse = sys.argv[5] if len(sys.argv) > 5 else ""
    if mode in {"clarify-poser", "clarify-reprendre", "clarify-interrompre"}:
        resultat = asyncio.run(clarify(mode, jeton, texte, reponse))
        with open(fichier, "w", encoding="utf-8") as flux:
            json.dump(resultat, flux, ensure_ascii=False)
        return 0
    if mode not in {"preview-restart", "session", "prompt"}:
        print(f"mode inconnu : {mode}", file=sys.stderr)
        return 2
    resultat = asyncio.run(dialoguer(mode, jeton, texte))
    with open(fichier, "w", encoding="utf-8") as flux:
        json.dump(resultat, flux, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
