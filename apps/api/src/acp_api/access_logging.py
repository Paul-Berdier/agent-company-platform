"""Expurgation des bearers placés dans les URLs de livrables signées.

Uvicorn journalise normalement la cible HTTP complète, query string comprise. Les
liens de livrables utilisent volontairement un paramètre ``token`` afin de fonctionner
comme ``src`` de média sans cookie ; ce bearer ne doit jamais atteindre les journaux.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote_plus


REDACTED_QUERY_VALUE = "[REDACTED]"
_QUERY_FIELD = re.compile(r"([?&])([^=&\s]+)=([^&#\s]*)")


def redact_url_query_tokens(value: str) -> str:
    """Masque chaque paramètre dont le nom décodé est exactement ``token``.

    Le nom est décodé avant comparaison afin que ``to%6ben`` ne contourne pas
    l'expurgation alors que Starlette le résout bien vers le paramètre ``token``.
    Les autres paramètres restent byte-for-byte identiques dans le journal.
    """

    def replace(match: re.Match[str]) -> str:
        try:
            name = unquote_plus(match.group(2), errors="strict")
        except UnicodeDecodeError:
            return match.group(0)
        if name != "token":
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}={REDACTED_QUERY_VALUE}"

    return _QUERY_FIELD.sub(replace, value)


class ArtifactTokenAccessLogFilter(logging.Filter):
    """Expurge le message et les arguments structurés de ``uvicorn.access``."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_url_query_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_url_query_tokens(item) if isinstance(item, str) else item
                for item in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_url_query_tokens(item) if isinstance(item, str) else item
                for key, item in record.args.items()
            }
        elif isinstance(record.args, str):
            record.args = redact_url_query_tokens(record.args)
        return True


def install_access_log_redaction(
    logger: logging.Logger | None = None,
) -> ArtifactTokenAccessLogFilter:
    """Installe une seule instance du filtre sur le logger d'accès Uvicorn."""

    target = logger or logging.getLogger("uvicorn.access")
    for current in target.filters:
        if isinstance(current, ArtifactTokenAccessLogFilter):
            return current
    installed = ArtifactTokenAccessLogFilter()
    target.addFilter(installed)
    return installed
