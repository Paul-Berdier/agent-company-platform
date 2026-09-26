"""Adaptateur Hermes du noyau d'acp-poste : SEUL module du noyau qui importe l'interne de Hermes.

Chaque nom est importé depuis son MODULE DE DÉFINITION à la version épinglée (0.21.5, commit
f97608f), jamais par un pointeur PLUGIN-COMPAT : dans ``hermes_cli.kanban_db``, ``connect`` et
``heartbeat_worker`` ne sont que des pointeurs (compat_manifest.json), et un greffon qui les résout
par l'ancien chemin est désactivé (hermes_cli/plugin_compat.py:32). Le workflow image.yml le
vérifie par ``hermes plugins compat`` sur tout le dossier du greffon (``noyau/`` compris) et
``test_chaque_fonction_vient_de_son_module_de_definition`` compare ``__module__`` à
:data:`MODULES_DE_DEFINITION`.

Étape P4 (docs/refonte/autonomie.md § 8) : un tableau kanban PAR PROJET, créé par le greffon.
L'héritage de P1 (tableau unique « poste », assigné « poste-windows », carte de triage) est
retiré, comme le plan le demande (§ 9).

Lecture SQL directe, en lecture seule, UNIQUEMENT pour les événements d'un tableau
(:func:`evenements_apres`, :func:`dernier_evenement`) : Hermes n'expose aucune fonction publique
qui lise ``task_events`` par tableau après un identifiant (le greffon kanban natif le fait en SQL :
plugins/kanban/dashboard/plugin_api.py:1698). Le schéma lu est vérifié par
``test_schema_des_evenements_attendu``.
"""

from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import time
from typing import Any, Iterator, List, Optional, Tuple

from agent.delegation_context import is_dispatcher_owned_worker_context, owned_kanban_task
from agent.estop import disengage, engage, get_state
from agent.redact import redact_sensitive_text
from hermes_cli.kanban_db import (
    Task,
    add_comment,
    archive_task,
    block_task,
    child_ids,
    claim_task,
    complete_task,
    create_board,
    create_task,
    get_task,
    heartbeat_claim,
    kanban_db_path,
    latest_summaries,
    link_tasks,
    list_boards,
    list_comments,
    list_events,
    list_runs,
    list_tasks,
    normalize_reasoning_effort,
    parent_ids,
    reclaim_task,
    request_review,
    schedule_task,
    specify_triage_task,
    unblock_task,
)
from hermes_cli.kanban_db_connect import connect, write_txn
from hermes_cli.kanban_db_dispatch import heartbeat_worker
from hermes_constants import VALID_REASONING_EFFORTS, get_hermes_home
from plugins.plugin_storage import plugin_db
from tools.registry import no_cache_check_fn

# Voies du poste Windows : ce ne sont PAS des profils de Hermes. Le répartiteur range leurs cartes
# en « skipped_nonspawnable » (hermes_cli/kanban_db_dispatch.py:2011-2017) ; seul le poste les
# réclame (P6).
VOIES_POSTE: Tuple[str, str] = ("poste-codex", "poste-claude")
PREFIXE_VOIE_POSTE = "poste-"
# Créateur inscrit sur chaque carte émise par le greffon (tasks.created_by).
CREATEUR = "acp-poste"
# Préfixe des clés d'idempotence des cartes émises par le greffon (= demandes.cle).
PREFIXE_CLE = "acp:"
# Profil de Hermes qui exécute les cartes de la voie « hermes » (managed scope : dispatch_profiles).
PROFIL_HERMES = "default"

# Module de définition attendu pour chaque nom importé (vérifié par les tests).
MODULES_DE_DEFINITION = {
    "Task": "hermes_cli.kanban_db",
    "create_board": "hermes_cli.kanban_db",
    "list_boards": "hermes_cli.kanban_db",
    "create_task": "hermes_cli.kanban_db",
    "get_task": "hermes_cli.kanban_db",
    "list_tasks": "hermes_cli.kanban_db",
    "link_tasks": "hermes_cli.kanban_db",
    "add_comment": "hermes_cli.kanban_db",
    "archive_task": "hermes_cli.kanban_db",
    "list_comments": "hermes_cli.kanban_db",
    "list_events": "hermes_cli.kanban_db",
    "parent_ids": "hermes_cli.kanban_db",
    "child_ids": "hermes_cli.kanban_db",
    "block_task": "hermes_cli.kanban_db",
    "unblock_task": "hermes_cli.kanban_db",
    "schedule_task": "hermes_cli.kanban_db",
    "reclaim_task": "hermes_cli.kanban_db",
    "specify_triage_task": "hermes_cli.kanban_db",
    "claim_task": "hermes_cli.kanban_db",
    "heartbeat_claim": "hermes_cli.kanban_db",
    "complete_task": "hermes_cli.kanban_db",
    "latest_summaries": "hermes_cli.kanban_db",
    "list_runs": "hermes_cli.kanban_db",
    "request_review": "hermes_cli.kanban_db",
    "normalize_reasoning_effort": "hermes_cli.kanban_db",
    "kanban_db_path": "hermes_cli.kanban_db",
    "connect": "hermes_cli.kanban_db_connect",
    "write_txn": "hermes_cli.kanban_db_connect",
    "heartbeat_worker": "hermes_cli.kanban_db_dispatch",
    "owned_kanban_task": "agent.delegation_context",
    "is_dispatcher_owned_worker_context": "agent.delegation_context",
    "engage": "agent.estop",
    "disengage": "agent.estop",
    "get_state": "agent.estop",
    "plugin_db": "plugins.plugin_storage",
    "redact_sensitive_text": "agent.redact",
    "get_hermes_home": "hermes_constants",
    "no_cache_check_fn": "tools.registry",
}

__all__ = [
    "CREATEUR", "MODULES_DE_DEFINITION", "PREFIXE_CLE", "PREFIXE_VOIE_POSTE", "PROFIL_HERMES",
    "VALID_REASONING_EFFORTS", "VOIES_POSTE", "connexion", "dernier_evenement", "est_voie_poste",
    "evenements_apres", "effort_hermes", "masquer", *MODULES_DE_DEFINITION,
]


def est_voie_poste(assigne: Optional[str]) -> bool:
    """Vrai pour tout assigné ``poste-*`` (les deux voies de P4, mais aussi un nom forgé)."""
    return bool(assigne) and str(assigne).startswith(PREFIXE_VOIE_POSTE)


def effort_hermes(effort: Optional[str]) -> Optional[str]:
    """L'effort tel que Hermes l'accepte sur une carte (``normalize_reasoning_effort``), ou None
    s'il est hors de l'énumération de Hermes (kanban_db.py:115-127 lèverait)."""
    if not effort:
        return None
    try:
        return normalize_reasoning_effort(effort)
    except ValueError:
        return None


# Course du contrôle d'écriture de Hermes 0.21.5 (hermes_state_repair.py:537-573, appelé par
# kanban_db_connect.connect) : il voit le fichier « -wal » (ou « -shm ») d'un tableau par is_file(), puis
# os.access() échoue parce qu'un AUTRE processus (répartiteur, émetteur, worker) vient de refermer la
# dernière connexion et SQLite a supprimé ce fichier ; il conclut alors à tort « read-only for this user ».
# Constaté au contrat P4 (seconde partie) sur un poste simulé. Seul ce faux négatif est rejoué, et seulement
# si le fichier nommé n'existe plus : un fichier vraiment en lecture seule lève tout de suite.
_COURSE_DU_WAL = re.compile(r"file (\S+-(?:wal|shm)) is read-only for this user")
TENTATIVES_DE_CONNEXION = 3


def course_du_wal(exc: BaseException) -> bool:
    """Vrai si ``exc`` est le faux « read-only » du contrôle de Hermes sur un -wal/-shm disparu depuis."""
    trouve = _COURSE_DU_WAL.search(str(exc)) if isinstance(exc, sqlite3.OperationalError) else None
    return bool(trouve) and not os.path.exists(trouve.group(1))


def _connecter(tableau: str) -> sqlite3.Connection:
    for tentative in range(1, TENTATIVES_DE_CONNEXION + 1):
        try:
            return connect(board=tableau)
        except sqlite3.OperationalError as exc:
            if tentative == TENTATIVES_DE_CONNEXION or not course_du_wal(exc):
                raise
            time.sleep(0.05 * tentative)
    raise AssertionError("inatteignable")  # pragma: no cover


@contextlib.contextmanager
def connexion(tableau: str) -> Iterator[sqlite3.Connection]:
    """Connexion au tableau ``tableau``, toujours nommé explicitement, toujours refermée
    (kanban_db_connect.py:739-752) ; rejouée sur la seule course du contrôle d'écriture de Hermes
    (:func:`course_du_wal`)."""
    conn = _connecter(tableau)
    try:
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def evenements_apres(conn: sqlite3.Connection, apres: int, limite: int = 500) -> List[Tuple[int, str, str, Any, int]]:
    """Événements du tableau d'identifiant > ``apres`` (lecture seule), par ordre croissant."""
    lignes = conn.execute(
        "SELECT id, task_id, kind, payload, created_at FROM task_events WHERE id > ? ORDER BY id LIMIT ?",
        (int(apres), int(limite))).fetchall()
    return [(int(l[0]), str(l[1]), str(l[2]), l[3], int(l[4])) for l in lignes]


def dernier_evenement(conn: sqlite3.Connection) -> int:
    """Identifiant du dernier événement du tableau (0 s'il n'y en a aucun)."""
    return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM task_events").fetchone()[0])


def masquer(texte: Any) -> str:
    """Texte passé par le masquage des secrets de Hermes (``redact_sensitive_text``, forcé)."""
    if texte is None:
        return ""
    try:
        return redact_sensitive_text(str(texte), force=True)
    except Exception:  # noqa: BLE001 — un masquage qui échoue ne doit jamais laisser passer le texte brut
        return "(texte masqué)"
