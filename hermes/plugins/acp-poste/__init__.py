"""Greffon groupé acp-poste, côté agent (squelette de l'étape P1).

Hermes importe ce paquet dans chacun de ses processus et appelle :func:`register`
(hermes_cli/plugins.py). En P1, le greffon n'enregistre encore rien : ni outil
``poste_*``, ni fournisseur de jeton machine, ni route à jeton. Ils arrivent en P5 ; les
annoncer maintenant ferait croire à une délégation qui n'existe pas.

La partie tableau de bord (``dashboard/plugin_api.py``) est montée indépendamment, sous
``/api/plugins/acp-poste/`` (hermes_cli/web_server_dashboard.py:798-874).
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def register(ctx) -> None:  # noqa: ARG001 — signature imposée par Hermes
    """Point d'entrée du greffon. Squelette P1 : aucun enregistrement."""
    _log.debug("acp-poste : squelette P1 chargé ; aucun outil ni fournisseur enregistré.")
