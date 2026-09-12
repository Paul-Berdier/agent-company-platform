"""Exécutions de tests structurées (ingestion worker et lectures membres).

Un succès provient d'assertions et d'un code de sortie réels ; les statuts
Playwright restent distincts et ne sont jamais réduits à « vert / rouge ».

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet
(``/workers/{worker_id}/test-runs``, ``/runs/{run_id}/test-run``, ``/test-runs/{id}``).
Les routes sont livrées par l'agent E3 (avec ``testing_service.py``).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["testing"])
