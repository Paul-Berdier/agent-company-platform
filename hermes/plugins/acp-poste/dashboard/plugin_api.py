"""Routes du greffon acp-poste dans le tableau de bord de Hermes.

Hermes importe ce fichier par son chemin et monte ``router`` sous
``/api/plugins/acp-poste/`` au démarrage du tableau de bord
(hermes_cli/web_server_dashboard.py:798-874) ; il ne passe PAS par le paquet du greffon,
d'où le chargement explicite de ``meta.py`` ci-dessous. Toutes les routes sont derrière
la porte d'authentification du tableau de bord (hermes_cli/dashboard_auth/middleware.py) :
sans session, ``401``.

La lecture des fichiers se fait hors de la boucle d'événements : le ping des WebSocket
de l'agent tourne sur cette boucle (web_server.py:1158-1164).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

_DOSSIER_GREFFON = Path(__file__).resolve().parent.parent


def _charger(nom: str) -> ModuleType:
    cle = f"acp_poste_greffon_{nom}"
    module = sys.modules.get(cle)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(cle, _DOSSIER_GREFFON / f"{nom}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"module {nom}.py du greffon acp-poste introuvable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[cle] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(cle, None)
        raise
    return module


_meta = _charger("meta")

router = APIRouter()


def mesurer_reseau(request: Request) -> Dict[str, Any]:
    """Ce que le tableau de bord voit de la requête : pair, schéma, hôte, et la seule PRÉSENCE des
    en-têtes posés par un bord (jamais la valeur de X-Forwarded-For, qui porte l'adresse du
    client). Sert à mesurer le bord Railway avant de renseigner dashboard.trusted_proxies."""
    entetes = request.headers
    return {
        "pair": request.client.host if request.client else None,
        "schema_vu": request.url.scheme,
        "hote": entetes.get("host"),
        "entetes_transmis": {nom: nom in entetes for nom in _meta.ENTETES_MESURES},
        "x_forwarded_proto": (entetes.get("x-forwarded-proto") or "")[:16] or None,
    }


@router.get("/v1/meta")
async def lire_meta(request: Request) -> Dict[str, Any]:
    """Contrat, versions (greffon, Hermes en cours et testée), OpenRPC, état du démarrage, garde
    d'exécution du processus du tableau de bord, mesure réseau et commit déployé."""
    return await run_in_threadpool(_meta.construire_meta, reseau=mesurer_reseau(request))
