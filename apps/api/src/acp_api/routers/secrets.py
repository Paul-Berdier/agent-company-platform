"""Routes du coffre de secrets (``/secrets``).

Fondation du Lot D : le routeur est déclaré et inclus dans ``main.py`` ; les routes
(statut, création, liste, rotation, révocation) sont raccordées par l'agent A.
Aucune valeur de secret ne doit jamais figurer dans une réponse de ce routeur.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/secrets", tags=["secrets"])
