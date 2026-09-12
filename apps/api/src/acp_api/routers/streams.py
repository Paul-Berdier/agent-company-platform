"""Flux d'événements SSE servi par l'API métier (``GET /streams/...``).

L'API détient la base, les sessions et le RBAC : le flux utilisateur est servi ici,
jamais par ``apps/event-service`` qui reste un relais interne sans accès aux données.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
Les routes sont livrées par l'agent E1 (``streams.py``, ``events_bus.py``).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["streams"])
