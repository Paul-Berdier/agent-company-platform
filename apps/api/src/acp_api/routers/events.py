"""Lecture paginée du journal d'événements (``GET /runs/{id}/events``, ``/projects/...``).

Ces lectures réconcilient l'interface après une coupure de flux : une reconnexion
ne relance jamais une mission et ne duplique aucun événement, elle relit par curseur.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
Les routes sont livrées par l'agent E1.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["events"])
