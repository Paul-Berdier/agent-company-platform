"""Modèle factice compatible OpenAI, pour les tests : aucun appel réseau réel.

Répond sur ``/v1/models`` et ``/v1/chat/completions`` (réponse unique ou flux SSE) et
consigne chaque requête reçue, une ligne JSON par requête, dans le journal donné. Les tests
s'en servent pour configurer Hermes sans fournisseur réel et pour prouver qu'un scénario
n'a appelé AUCUN modèle (journal vide).

Scénarios d'appel d'outil (étape P2), pour prouver qu'aucun outil d'exécution n'est rendu :

- « OUTIL:<nom> » dans le dernier message utilisateur, ou une entrée du fichier
  ``--scenarios`` (JSON ``{"sous-chaîne du dernier message utilisateur": "<nom>"}``, relu à
  chaque requête ; sert aux workers kanban, dont le message est « work kanban task <id> ») :
  le modèle répond par UN appel de l'outil ``<nom>`` avec des arguments témoins fixes (par
  exemple ``terminal`` → ``touch /tmp/acp-temoins/terminal``) ; « OUTIL:tool_call><outil> »
  appelle le pont des outils différés avec ``<outil>`` et ses arguments témoins (relecture P2 :
  Hermes déballe le pont avant le crochet de la garde) ;
- dès qu'un résultat d'outil arrive (dernier message de rôle ``tool``) : réponse « fin » ; dans
  un worker kanban qui n'a pas encore appelé ``kanban_complete``, un appel de
  ``kanban_complete`` d'abord.

Le journal consigne pour chaque complétion : les outils OFFERTS, le rôle du dernier message,
l'outil demandé, les résultats d'outils reçus (tronqués à 400 caractères) et, depuis P3, le début
du premier message système (6 000 caractères, champ ``systeme``) et son index des skills
(``<available_skills>``, champ ``index_skills``). Sans marqueur ni scénario : réponse texte fixe,
comme en P1.

Usage : python modele_factice.py --port 18080 --journal /tmp/modele-factice.jsonl
        [--scenarios /tmp/scenarios.json]
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

REPONSE = "Réponse du modèle factice ACP."
FIN = "fin"
MODELE = "acp-factice"
TEMOINS = "/tmp/acp-temoins"
_MARQUEUR = re.compile(r"OUTIL:([A-Za-z0-9_.-]+(?:>[A-Za-z0-9_.-]+)?)")

# Arguments témoins : un outil d'exécution qui s'exécuterait VRAIMENT laisserait un fichier dans
# /tmp/acp-temoins (les tests vérifient qu'il n'y en a aucun).
ARGUMENTS_TEMOINS: Dict[str, Dict[str, Any]] = {
    "terminal": {"command": f"touch {TEMOINS}/terminal"},
    "process_manage": {"action": "list"},
    "read_file": {"path": "/etc/hostname"},
    "write_file": {"path": f"{TEMOINS}/write_file", "content": "témoin"},
    "patch": {"path": f"{TEMOINS}/patch", "old_string": "a", "new_string": "b"},
    "search_files": {"pattern": "acp", "path": "/opt/data"},
    "execute_code": {"code": f"open('{TEMOINS}/execute_code', 'w').write('témoin')"},
    "cronjob_manage": {"action": "create", "schedule": "1m", "prompt": f"touch {TEMOINS}/cronjob"},
    "delegate_task": {"goal": f"touch {TEMOINS}/delegate_task"},
    "tool_call": {"calls": [{"name": "terminal", "arguments": {"command": f"touch {TEMOINS}/tool_call"}}]},
    "browser_navigate": {"url": "http://127.0.0.1:9119/"},
    "computer_use": {"action": "screenshot"},
    "manage_connections": {"action": "list"},
    "manage_catalog": {"action": "list"},
    "kanban_create": {"title": "Carte créée par l'agent", "assignee": "default", "skills": ["x"],
                      "model": "m", "provider": "p", "workspace_kind": "dir", "workspace_path": "/opt/data"},
    "kanban_attach_url": {"url": "http://attache.acp.test/fichier"},
    "skills_list": {},
    "todo_list": {"todos": [{"id": "1", "content": "carte de test ACP", "status": "pending"}]},
    # Étape P3 : outils du faux serveur context7 (outils/mcp_factice.py) et d'une skill du catalogue.
    "mcp__context7__resolve_library_id": {"libraryName": "acp"},
    "mcp__context7__query_docs": {"libraryId": "/acp/bibliotheque-factice", "query": "témoin ACP"},
    "mcp__context7__piege": {},
    "skill_view": {"name": "acp-redaction"},
}


def _texte(contenu: Any) -> str:
    """Texte d'un message OpenAI (chaîne ou liste de parties)."""
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return "\n".join(str(p.get("text", "")) for p in contenu if isinstance(p, dict))
    return ""


def _outils_offerts(corps: Dict[str, Any]) -> List[str]:
    noms: List[str] = []
    for outil in corps.get("tools") or []:
        if isinstance(outil, dict):
            fonction = outil.get("function") or {}
            if isinstance(fonction, dict) and fonction.get("name"):
                noms.append(str(fonction["name"]))
    return sorted(noms)


def _lire_scenarios(chemin: Optional[str]) -> Dict[str, str]:
    if not chemin:
        return {}
    try:
        with open(chemin, encoding="utf-8") as flux:
            donnees = json.load(flux)
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in donnees.items()} if isinstance(donnees, dict) else {}


def decider(messages: List[Dict[str, Any]], scenarios: Dict[str, str]) -> Tuple[Optional[str], Dict[str, Any]]:
    """(outil à appeler ou None pour une réponse texte, informations pour le journal)."""
    dernier = messages[-1] if messages else {}
    role = dernier.get("role")
    info: Dict[str, Any] = {"role_dernier": role}
    utilisateurs = [_texte(m.get("content")) for m in messages if m.get("role") == "user"]
    premier_utilisateur = utilisateurs[0] if utilisateurs else ""
    if role == "tool":
        info["resultats_outils"] = [
            {"nom": m.get("name"), "contenu": _texte(m.get("content"))[:400]}
            for m in messages[-8:] if m.get("role") == "tool"]
        appels = [tc.get("function", {}).get("name") for m in messages if m.get("role") == "assistant"
                  for tc in (m.get("tool_calls") or []) if isinstance(tc, dict)]
        if "work kanban task" in premier_utilisateur and "kanban_complete" not in appels:
            return "kanban_complete", info
        return None, info
    if role != "user":
        return None, info
    texte = _texte(dernier.get("content"))
    trouve = _MARQUEUR.findall(texte)
    if trouve:
        return trouve[-1], info
    for motif, outil in scenarios.items():
        if motif and motif in texte:
            return outil, info
    return None, info


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--hote", default="127.0.0.1")
    arguments.add_argument("--port", type=int, default=18080)
    arguments.add_argument("--journal", required=True)
    arguments.add_argument("--scenarios", default=None)
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
            if not isinstance(corps, dict):
                corps = {}
            entree: Dict[str, Any] = {"methode": "POST", "chemin": self.path, "modele": corps.get("model"),
                                      "flux": bool(corps.get("stream")), "t": time.time()}
            if not self.path.rstrip("/").endswith("/chat/completions"):
                consigner(entree)
                self._json(404, {"error": {"message": "inconnu"}})
                return
            messages = [m for m in (corps.get("messages") or []) if isinstance(m, dict)]
            outil, info = decider(messages, _lire_scenarios(options.scenarios))
            entree.update(info)
            # Étape P3 : début du prompt système reçu (la persona SOUL.md en est le premier bloc).
            systeme = [m for m in messages if m.get("role") == "system"]
            entree["systeme"] = _texte(systeme[0].get("content"))[:6000] if systeme else None
            # Étape P3 : index des skills du prompt système (<available_skills>, agent/prompt_builder.py).
            complet = _texte(systeme[0].get("content")) if systeme else ""
            debut, fin = complet.find("<available_skills>"), complet.find("</available_skills>")
            entree["index_skills"] = complet[debut:fin + 19][:20000] if 0 <= debut < fin else None
            entree["outils_offerts"] = _outils_offerts(corps)
            if outil is not None and not entree["outils_offerts"]:
                # Appel auxiliaire de Hermes (titre, résumé…), sans outils : réponse texte.
                entree["auxiliaire"] = True
                outil = None
            entree["outil_demande"] = outil
            consigner(entree)
            identifiant = f"chatcmpl-{uuid.uuid4().hex}"
            cree = int(time.time())
            appel = None
            if outil is not None:
                nom_outil, _, sous_jacent = outil.partition(">")
                arguments_outil = ARGUMENTS_TEMOINS.get(nom_outil, {})
                if sous_jacent:  # « tool_call><outil> » : le pont, avec l'outil et ses arguments témoins
                    arguments_outil = {"calls": [{"name": sous_jacent,
                                                  "arguments": ARGUMENTS_TEMOINS.get(sous_jacent, {})}]}
                if nom_outil == "kanban_complete":
                    arguments_outil = {"summary": "fin du scénario de test ACP"}
                appel = {"id": f"call_{uuid.uuid4().hex[:12]}", "type": "function",
                         "function": {"name": nom_outil,
                                      "arguments": json.dumps(arguments_outil, ensure_ascii=False)}}
            texte = (FIN if info.get("role_dernier") == "tool" else REPONSE) if appel is None else None
            fin = "tool_calls" if appel is not None else "stop"
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            if corps.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                if appel is not None:
                    morceaux = [{"role": "assistant", "content": None,
                                 "tool_calls": [{"index": 0, **appel}]}]
                else:
                    morceaux = [{"role": "assistant", "content": ""}, {"content": texte}]
                for delta in morceaux:
                    evenement = {"id": identifiant, "object": "chat.completion.chunk", "created": cree,
                                 "model": MODELE, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(evenement, ensure_ascii=False)}\n\n".encode("utf-8"))
                dernier = {"id": identifiant, "object": "chat.completion.chunk", "created": cree, "model": MODELE,
                           "choices": [{"index": 0, "delta": {}, "finish_reason": fin}], "usage": usage}
                self.wfile.write(f"data: {json.dumps(dernier)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return
            message: Dict[str, Any] = {"role": "assistant", "content": texte}
            if appel is not None:
                message["tool_calls"] = [appel]
            self._json(200, {
                "id": identifiant, "object": "chat.completion", "created": cree, "model": MODELE,
                "choices": [{"index": 0, "message": message, "finish_reason": fin}], "usage": usage,
            })

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    serveur = ThreadingHTTPServer((options.hote, options.port), Gestionnaire)
    print(f"[modele-factice] http://{options.hote}:{options.port}/v1", flush=True)
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
