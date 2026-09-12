"""Routes de la bibliothèque de skills (``/skills``) et des extensions de projet.

Fondation du Lot D : les deux routeurs sont déclarés et inclus dans ``main.py`` ;
les routes (recherche, catalogue, import, révisions, approbation, bindings) sont
raccordées par l'agent B sur ``router``. ``GET /projects/{project_id}/extensions``
ne peut pas vivre sous le préfixe ``/skills`` : il se déclare sur ``extensions_router``
(sans préfixe), dans ce même fichier comme l'exige la spécification.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/skills", tags=["skills"])
extensions_router = APIRouter(tags=["extensions"])
