"""Bibliothèque de livrables (``/artifacts``) et liens signés.

Un contenu produit par un test est traité comme non fiable : téléchargement forcé,
``nosniff``, CSP restrictive, jamais d'exécution dans l'origine de la plateforme.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
Les routes sont livrées par l'agent E2 (avec ``retention.py``).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["artifacts"])
