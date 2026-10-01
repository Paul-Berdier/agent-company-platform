"""Fichiers de pilotage des agents touchés par une carte (cahier P6 § 6.6, point 2 ; décision D90).

Un seul chemin touché ⇒ la carte passe **en revue** (``request_review`` côté Hermes) : le propriétaire accepte ou
refuse depuis la page Questions. Claude Code ne protège ni ``CLAUDE.md``, ni ``AGENTS.md``, ni ``.github/workflows``
(cahier § 1.3, C2) : cette détection est la vraie protection.

Chemins visés, **à toute profondeur** : ``CLAUDE.md``, ``AGENTS.md``, ``.claude/``, ``.codex/``, ``.agents/``,
``.github/`` entier (les actions composites s'exécutent aussi), ``hermes/gere/``, ``.gitmodules``, ``.gitattributes``
(ses filtres s'exécutent), ``.husky/``, ``.pre-commit-config.yaml``, ``.devcontainer/``, ``.vscode/``, ``.mcp.json``,
``.npmrc``, ``.envrc``, plus ``pilotage_supplementaire`` de la politique du dépôt.

Normalisation de chaque composant : casse ignorée, ``\\`` ramené à ``/``, Unicode NFC, points et espaces finaux
retirés (Windows lirait ``CLAUDE.md.`` comme ``CLAUDE.md`` quand le propriétaire récupérera la branche), espaces
initiaux aussi, par prudence. Renommages : ancien ET nouveau chemins ; suppressions comprises ; tout lien symbolique
(mode 120000) ou sous-module (gitlink, mode 160000) ajouté compte aussi.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable, Sequence

from acp_poste_contrat.machine import CHEMINS_PILOTAGE_MAX

from .depots import Changement, mode_gitlink, mode_lien

FICHIERS = ("claude.md", "agents.md", ".gitmodules", ".gitattributes", ".pre-commit-config.yaml", ".mcp.json",
            ".npmrc", ".envrc")
DOSSIERS = ((".claude",), (".codex",), (".agents",), (".github",), ("hermes", "gere"), (".husky",),
            (".devcontainer",), (".vscode",))


def composants(chemin: str) -> list[str]:
    """Composants normalisés d'un chemin (casse, séparateurs, NFC, points et espaces finaux)."""
    texte = unicodedata.normalize("NFC", chemin.replace("\\", "/"))
    propres = []
    for partie in texte.split("/"):
        # Espaces des deux côtés (prudence : plus de revues, jamais moins), points finaux.
        partie = partie.strip(" ").rstrip(" .").casefold()
        if partie:
            propres.append(partie)
    return propres


def _contient(parties: Sequence[str], dossier: Sequence[str]) -> bool:
    n = len(dossier)
    return any(tuple(parties[i:i + n]) == tuple(dossier) for i in range(len(parties) - n + 1))


def est_pilotage(chemin: str, supplementaires: Iterable[str] = ()) -> bool:
    parties = composants(chemin)
    if not parties:
        return False
    if parties[-1] in FICHIERS:
        return True
    # Un composant de dossier visé n'importe où dans le chemin (un fichier SOUS ce dossier, ou le dossier lui-même).
    if any(_contient(parties, dossier) for dossier in DOSSIERS):
        return True
    for supplement in supplementaires:
        cible = composants(supplement)
        if cible and parties[:len(cible)] == cible:
            return True
    return False


def chemins_de_pilotage(changements: Iterable[Changement], supplementaires: Iterable[str] = ()) -> list[str]:
    """Chemins de pilotage touchés (dans l'ordre, sans doublon, au plus 50 : la limite du contrat)."""
    supplementaires = tuple(supplementaires)
    touches: list[str] = []
    for changement in changements:
        candidats = list(changement.chemins)
        retenus = [c for c in candidats if est_pilotage(c, supplementaires)]
        if mode_lien(changement) or mode_gitlink(changement):
            retenus = retenus or candidats[-1:]
        for chemin in retenus:
            if chemin not in touches:
                touches.append(chemin[:300])
    return touches[:CHEMINS_PILOTAGE_MAX]
