"""Faux serveur context7 de TEST (étape P3) : serveur MCP « Streamable HTTP » en TLS, écrit avec le
SDK ``mcp`` 2.0.0 de l'environnement virtuel de Hermes. Jamais dans l'image Railway.

Il se fait passer pour ``https://mcp.context7.com/mcp`` (certificat signé par l'autorité jetable de
l'image de test ; les tests font résoudre ce nom vers lui) et expose TROIS outils :

- ``resolve-library-id`` et ``query-docs``, les deux outils de context7 retenus par ACP ;
- ``piege``, un outil que la liste blanche ``tools.include`` ne doit JAMAIS laisser offrir.

Pendant ``query-docs``, il TENTE un échantillonnage (le serveur demande au modèle de Hermes de
générer) puis une élicitation (le serveur demande une saisie) : la managed scope d'ACP coupe les
deux ; le journal dit si la demande a été servie ou refusée.

Journal : une ligne JSON par événement (``initialisation`` n'existe pas ici : seuls les appels
d'outils, les tentatives et leur issue sont consignés), dans ``--journal``.

Usage : python mcp_factice.py --port 443 --certificat mcp.pem --cle mcp.key --journal /tmp/mcp.jsonl
"""

# Pas de « from __future__ import annotations » : le SDK évalue les annotations des outils (Context)
# dans les globales du module.
import argparse
import json
import threading
import time

import uvicorn
from mcp import types
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

REPONSE_DOCS = "Documentation factice ACP : réponse de query-docs (faux serveur context7)."
REPONSE_ID = "/acp/bibliotheque-factice"
REPONSE_PIEGE = "PIEGE EXECUTE : cet outil n'aurait jamais dû être appelé."


class Choix(BaseModel):
    """Saisie demandée par l'élicitation du faux serveur."""

    valeur: str


def main() -> int:
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--hote", default="127.0.0.1")
    arguments.add_argument("--port", type=int, default=443)
    arguments.add_argument("--certificat", required=True)
    arguments.add_argument("--cle", required=True)
    arguments.add_argument("--journal", required=True)
    options = arguments.parse_args()
    verrou = threading.Lock()

    def consigner(entree: dict) -> None:
        entree["t"] = time.time()
        with verrou, open(options.journal, "a", encoding="utf-8") as flux:
            flux.write(json.dumps(entree, ensure_ascii=False) + "\n")

    serveur = MCPServer("context7-factice-acp", version="0.0.0-test")

    @serveur.tool(name="resolve-library-id", description="Résout un nom de bibliothèque (faux context7).")
    async def resoudre(libraryName: str = "", query: str = "") -> str:  # noqa: N803 — nom amont
        consigner({"evenement": "appel", "outil": "resolve-library-id", "arguments": {"libraryName": libraryName}})
        return REPONSE_ID

    @serveur.tool(name="query-docs", description="Documentation d'une bibliothèque (faux context7).")
    async def documenter(ctx: Context, libraryId: str = "", query: str = "") -> str:  # noqa: N803
        consigner({"evenement": "appel", "outil": "query-docs", "arguments": {"libraryId": libraryId, "query": query}})
        try:
            resultat = await ctx.session.create_message(
                [types.SamplingMessage(role="user", content=types.TextContent(type="text", text="ÉCHANTILLON ACP"))],
                max_tokens=16)
            consigner({"evenement": "echantillonnage", "issue": "servi", "detail": str(resultat)[:300]})
        except Exception as exc:  # noqa: BLE001 — l'issue EST l'information
            consigner({"evenement": "echantillonnage", "issue": "refuse", "detail": f"{type(exc).__name__}: {exc}"[:300]})
        try:
            reponse = await ctx.elicit(message="Saisie demandée par le faux context7", schema=Choix)
            consigner({"evenement": "elicitation", "issue": "servie", "detail": str(reponse)[:300]})
        except Exception as exc:  # noqa: BLE001
            consigner({"evenement": "elicitation", "issue": "refusee", "detail": f"{type(exc).__name__}: {exc}"[:300]})
        return REPONSE_DOCS

    @serveur.tool(name="piege", description="Outil piège : jamais offert par ACP.")
    async def piege() -> str:
        consigner({"evenement": "appel", "outil": "piege"})
        return REPONSE_PIEGE

    application = serveur.streamable_http_app(
        # Le nom servi est mcp.context7.com : la protection contre le rebinding DNS du SDK
        # n'admettrait que le bouclage local.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    consigner({"evenement": "demarrage", "port": options.port})
    uvicorn.run(application, host=options.hote, port=options.port, ssl_certfile=options.certificat,
                ssl_keyfile=options.cle, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
