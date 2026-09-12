"""Expurgation des valeurs de secrets injectées, partagée par l'API et le worker.

Les deux sondes MCP injectent des valeurs déchiffrées du coffre dans un tiers non
fiable : en-têtes HTTP pour le transport ``http`` (sonde exécutée par l'API),
variables d'environnement pour le transport ``stdio`` (sonde exécutée par le
runner). Un serveur MCP bavard qui réécrit ces valeurs dans ``serverInfo``, dans
la description d'un outil ou sur stderr les publierait dans une réponse API
lisible par tout utilisateur authentifié (``GET /mcp/servers/{id}``,
``GET /mcp/probes/{id}``) et dans l'interface web.

Ce module est le seul endroit où la règle est écrite : les deux transports
appliquent exactement la même expurgation, sur tout ce qui provient du serveur
sondé, avant écriture en base.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


# Marqueur substitué aux valeurs injectées dans tout contenu produit par un tiers.
REDACTED_PLACEHOLDER = "***"
# Toute valeur non vide est expurgée. Un secret de 1 à 3 caractères rend le
# diagnostic bruyant (le marqueur apparaît partout), mais ``SecretCreate.value``
# autorise ``min_length=1`` : un plancher plus haut laisserait sortir en clair
# une valeur que l'utilisateur a déclarée secrète, ce qu'interdit la règle
# « aucun secret ne sort du serveur ».
MIN_REDACTED_VALUE_CHARS = 1
# Profondeur maximale parcourue : au-delà, la branche est remplacée par le
# marqueur (échec fermé) plutôt que retournée sans avoir été examinée.
MAX_REDACTION_DEPTH = 64


def redaction_values(injected: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Valeurs injectées à masquer dans tout ce que le serveur sondé renvoie.

    ``injected`` est la table nom → valeur transmise au tiers (en-têtes résolus
    ou variables d'environnement résolues). Seules les valeurs textuelles non
    vides sont retenues ; les noms restent visibles, seule la valeur est un
    secret.
    """

    if not isinstance(injected, Mapping):
        return ()
    values = {
        value
        for name, value in injected.items()
        if isinstance(name, str)
        and name
        and isinstance(value, str)
        and len(value) >= MIN_REDACTED_VALUE_CHARS
    }
    # Les plus longues d'abord : une valeur contenue dans une autre ne doit pas
    # laisser passer le reste du secret englobant.
    return tuple(sorted(values, key=len, reverse=True))


def redact_text(value: str, redactions: Sequence[str]) -> str:
    """Remplace chaque valeur injectée par le marqueur dans une chaîne."""

    for secret in redactions:
        if secret and secret in value:
            value = value.replace(secret, REDACTED_PLACEHOLDER)
    return value


def redact_data(value: Any, redactions: Sequence[str], depth: int = 0) -> Any:
    """Expurge récursivement une structure JSON produite par un tiers.

    Au-delà de ``MAX_REDACTION_DEPTH``, la branche est remplacée par le
    marqueur : un contenu non examiné ne doit jamais être retourné tel quel.
    """

    if not redactions:
        return value
    if depth > MAX_REDACTION_DEPTH:
        return REDACTED_PLACEHOLDER
    if isinstance(value, str):
        return redact_text(value, redactions)
    if isinstance(value, Mapping):
        return {
            (redact_text(key, redactions) if isinstance(key, str) else key): (
                redact_data(item, redactions, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_data(item, redactions, depth + 1) for item in value]
    return value
