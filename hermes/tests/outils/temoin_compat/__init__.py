"""Greffon témoin : importe ``connect`` par le pointeur PLUGIN-COMPAT de kanban_db.

``hermes plugins compat`` doit le signaler et sortir en code 1 ; l'adaptateur d'acp-poste,
lui, importe depuis ``hermes_cli.kanban_db_connect`` (module de définition).
"""

from hermes_cli.kanban_db import connect  # noqa: F401 — ancien chemin, volontairement


def register(ctx) -> None:  # noqa: ARG001
    return None
