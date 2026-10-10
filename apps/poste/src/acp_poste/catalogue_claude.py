"""Alias et efforts de Claude Code **documentés** (cahier P5 § 10.3, décision D59).

Aucune commande de Claude Code ne liste les modèles d'un compte, et la résolution réelle d'un alias n'est observée
qu'à l'exécution (``system/init``, étape P6). En P5, la seule source autorisée est la documentation officielle
(``code.claude.com``, pages « Model configuration » : alias et niveaux d'effort), lue le 26/09/2026. Cette table est
**datée** et liée à une **plage de versions** : elle n'est rendue que si la version lue de Claude Code est au moins
2.1.280 (version depuis laquelle ``opus`` désigne Opus 5.5 selon la documentation) ; hors plage, les alias sont
publiés sans résolution ni efforts (« Inconnu »).

Chaque entrée porte ``nature: "alias_documente"`` et ``source_efforts: "documentation"`` : le poste ne présente jamais
ces valeurs comme observées. ``isDefault`` vaut ``null`` pour tous (la documentation ne désigne pas d'alias par
défaut ; ``default`` n'est pas un alias). Que l'abonnement suive la ligne « API Anthropic » de la documentation reste
supposé, tranché par ``system/init`` à la première exécution (P6). À relire à chaque montée de version.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DOCUMENTATION_LUE_LE = date(2026, 9, 26)
PLAGE_MINIMALE = (2, 1, 280)
_TOUS = ("low", "medium", "high", "xhigh", "max")

# (alias, résolution documentée sur l'API Anthropic, efforts documentés, effort par défaut documenté).
# Efforts ``None`` : inconnus (dépendent de la disponibilité ou du mode) ; ``()`` : aucun (absent de la table).
TABLE = (
    ("opus", "claude-opus-5-5", _TOUS, "medium"),
    ("sonnet", "claude-sonnet-5", _TOUS, "high"),
    ("fable", "claude-fable-5-1", _TOUS, "high"),
    ("haiku", None, (), None),
    ("opus[1m]", "claude-opus-5-5", _TOUS, "medium"),
    ("sonnet[1m]", "claude-sonnet-5", _TOUS, "high"),
    ("best", None, None, None),
    ("opusplan", None, None, None),
)


def dans_la_plage(version: tuple[int, int, int] | None) -> bool:
    return version is not None and version >= PLAGE_MINIMALE


def modeles_documentes(version: tuple[int, int, int] | None) -> list[dict[str, Any]]:
    """Modèles du relevé Claude (forme ``ModeleReleve``) : table complète dans la plage, alias seuls hors plage."""

    connue = dans_la_plage(version)
    modeles = []
    for alias, resolution, efforts, defaut in TABLE:
        modeles.append({
            "id": alias,
            "displayName": alias,
            "isDefault": None,
            "supportedReasoningEfforts": (list(efforts) if efforts is not None else None) if connue else None,
            "defaultReasoningEffort": defaut if connue else None,
            "serviceTiers": [],
            "defaultServiceTier": None,
            "nature": "alias_documente",
            "resolution_documentee": resolution if connue else None,
            "source_efforts": "documentation",
        })
    return modeles
