"""Motifs de secrets refusés dans les textes que le greffon écrit sur une carte ou transmet au poste
(objectif, consigne, réponse, surcharge), et dans l'inventaire reçu du poste.

Étape P5 : la liste vit désormais dans le contrat partagé (``acp_poste_contrat.motifs_secrets``), seule
copie pour le greffon, le poste et ``scripts/balayer_secrets.py`` (parité vérifiée par
``contrat/tests/test_motifs_parite.py``). Ce module la réexporte pour les modules du noyau."""

from __future__ import annotations

from . import contrat_partage  # noqa: F401 — met le contrat partagé sur sys.path

from acp_poste_contrat.motifs_secrets import MOTIFS, motif_trouve  # noqa: E402,F401

__all__ = ["MOTIFS", "motif_trouve"]
