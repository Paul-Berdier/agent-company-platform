"""Routes du centre MCP (``/mcp``).

Fondation du Lot D : le routeur est déclaré et inclus dans ``main.py`` ; les routes
(catalogue, serveurs, révisions, probes, bindings, export, import, claim worker)
sont raccordées par les agents A et H.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/mcp", tags=["mcp"])
