"""Adaptateur kanban du greffon acp-poste : SEUL module qui importe l'interne kanban de Hermes.

Chaque fonction est importée depuis son MODULE DE DÉFINITION à la version épinglée
(v2026.9.24, commit f97608f), jamais par un pointeur PLUGIN-COMPAT : dans
``hermes_cli.kanban_db``, ``connect`` et ``heartbeat_worker`` ne sont que des pointeurs
(kanban_db.py, bloc PLUGIN-COMPAT ; compat_manifest.json), et depuis le 2026-09-14 un
greffon qui les résout par l'ancien chemin est désactivé (COMPAT_MANIFEST.md:15-19 ;
hermes_cli/plugin_compat.py:32). Le workflow image.yml le vérifie par
``hermes plugins compat`` et par un test qui compare ``__module__`` de chaque fonction.

Définitions, à la version épinglée :
- hermes_cli/kanban_db.py : create_board :611, create_task :1249, get_task :1494,
  list_tasks :1514, claim_task :2263, heartbeat_claim :2383, complete_task :2723,
  block_task :3208, request_review :3346 ;
- hermes_cli/kanban_db_connect.py : connect :668 ;
- hermes_cli/kanban_db_dispatch.py : heartbeat_worker :610.

Toute opération vise le tableau ``poste``, toujours nommé explicitement. Squelette P1 :
création du tableau, d'une carte en triage et lecture ; l'extension de P4 et la réclamation,
les battements et la clôture par le poste (P6) suivent le plan d'autonomie
(docs/refonte/autonomie.md § 8) ; les imports sont déjà figés ici pour que la garde de
compatibilité les couvre.
"""

from __future__ import annotations

import contextlib
import sqlite3
from typing import Iterator, List, Optional

from hermes_cli.kanban_db import (
    Task,
    block_task,
    claim_task,
    complete_task,
    create_board,
    create_task,
    get_task,
    heartbeat_claim,
    list_tasks,
    request_review,
)
from hermes_cli.kanban_db_connect import connect
from hermes_cli.kanban_db_dispatch import heartbeat_worker

TABLEAU = "poste"
ASSIGNE = "poste-windows"
CREATEUR = "acp-poste"

# Module de définition attendu pour chaque fonction importée (vérifié par les tests).
MODULES_DE_DEFINITION = {
    "create_board": "hermes_cli.kanban_db",
    "create_task": "hermes_cli.kanban_db",
    "get_task": "hermes_cli.kanban_db",
    "list_tasks": "hermes_cli.kanban_db",
    "claim_task": "hermes_cli.kanban_db",
    "heartbeat_claim": "hermes_cli.kanban_db",
    "complete_task": "hermes_cli.kanban_db",
    "block_task": "hermes_cli.kanban_db",
    "request_review": "hermes_cli.kanban_db",
    "connect": "hermes_cli.kanban_db_connect",
    "heartbeat_worker": "hermes_cli.kanban_db_dispatch",
}

__all__ = [
    "ASSIGNE",
    "MODULES_DE_DEFINITION",
    "TABLEAU",
    "assurer_tableau",
    "connexion",
    "creer_carte_triage",
    "lire_carte",
    "lister_cartes",
    # Réexportés pour les phases suivantes (autonomie.md § 8), figés dès P1 sous la garde de
    # compatibilité.
    "block_task",
    "claim_task",
    "complete_task",
    "heartbeat_claim",
    "heartbeat_worker",
    "request_review",
]


def assurer_tableau() -> None:
    """Crée le tableau ``poste`` s'il n'existe pas (sémantique ``mkdir -p``)."""
    create_board(
        TABLEAU,
        name="Poste Windows",
        description="Travaux délégués au poste Windows par acp-poste. Ne pas y créer de carte à la main.",
    )


@contextlib.contextmanager
def connexion() -> Iterator[sqlite3.Connection]:
    """Connexion au tableau ``poste`` ; toujours refermée (kanban_db_connect.py:739-752)."""
    conn = connect(board=TABLEAU)
    try:
        yield conn
    finally:
        conn.close()


def creer_carte_triage(*, titre: str, corps: str, cle_idempotence: str) -> str:
    """Crée une carte en ``triage`` sur le tableau ``poste``, assignée à ``poste-windows``.

    Une carte en triage n'est jamais lancée par le répartiteur ; sans auto-décomposition
    (``kanban.auto_decompose: false``, épinglé), elle y reste jusqu'au geste du
    propriétaire."""
    if not cle_idempotence:
        raise ValueError("clé d'idempotence obligatoire")
    with connexion() as conn:
        return create_task(
            conn,
            title=titre,
            body=corps,
            assignee=ASSIGNE,
            created_by=CREATEUR,
            triage=True,
            idempotency_key=cle_idempotence,
            board=TABLEAU,
        )


def lire_carte(identifiant: str) -> Optional[Task]:
    with connexion() as conn:
        return get_task(conn, identifiant)


def lister_cartes(*, statut: Optional[str] = None) -> List[Task]:
    with connexion() as conn:
        return list_tasks(conn, assignee=ASSIGNE, status=statut)
