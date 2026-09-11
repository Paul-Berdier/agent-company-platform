import hashlib
import json
import os
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from .models import Base

DEFAULT_URL = "sqlite:///./acp.db"


@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("ACP_DATABASE_URL", DEFAULT_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    """Crée les tables manquantes (MVP ; une migration Alembic viendra ensuite)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _upgrade_sqlite_schema(engine)


def _backfill_mission_command_principals(connection) -> None:
    """Attribue les anciennes commandes seulement quand l'auteur est certain.

    Une commande sans auteur de mission, ou deux anciennes commandes qui se
    retrouveraient sous la même clé principal/commande, nécessitent une décision
    opérateur. Le démarrage est alors refusé plutôt que de rendre la déduplication
    ambiguë ou de rejouer un effet.
    """

    rows = connection.execute(
        text(
            "SELECT mc.id, mc.command, mc.idempotency_key, mc.principal_id, "
            "t.created_by_user_id "
            "FROM mission_commands AS mc "
            "LEFT JOIN tasks AS t ON t.id = mc.task_id"
        )
    ).mappings().all()
    groups: dict[tuple[str, str, str], list[dict]] = {}
    unattributed = []
    for row in rows:
        effective_principal = row["principal_id"] or row["created_by_user_id"]
        if effective_principal is None:
            if row["principal_id"] is None:
                unattributed.append(row["id"])
            continue
        groups.setdefault(
            (effective_principal, row["command"], row["idempotency_key"]), []
        ).append(row)
    ambiguous = [
        grouped
        for grouped in groups.values()
        if len(grouped) > 1 and any(row["principal_id"] is None for row in grouped)
    ]
    if unattributed or ambiguous:
        raise RuntimeError(
            "Migration mission_commands refusée: "
            f"{len(unattributed)} commande(s) sans principal et "
            f"{len(ambiguous)} groupe(s) de clés ambigu(s)"
        )
    for grouped in groups.values():
        row = grouped[0]
        if row["principal_id"] is None:
            connection.execute(
                text(
                    "UPDATE mission_commands SET principal_id = :principal_id "
                    "WHERE id = :command_id AND principal_id IS NULL"
                ),
                {
                    "principal_id": row["created_by_user_id"],
                    "command_id": row["id"],
                },
            )


def _replace_task_scoped_mission_command_constraint(connection) -> None:
    """Retire l'ancienne unicité par mission, non supprimable via ALTER SQLite."""

    constraints = inspect(connection).get_unique_constraints("mission_commands")
    legacy_columns = ("task_id", "command", "idempotency_key")
    if not any(
        tuple(constraint.get("column_names") or ()) == legacy_columns
        for constraint in constraints
    ):
        return
    replacement = "mission_commands_principal_scope_v2"
    if inspect(connection).has_table(replacement):
        raise RuntimeError(
            "Migration mission_commands refusée: table temporaire déjà présente"
        )
    connection.execute(
        text(
            f"CREATE TABLE {replacement} ("
            "task_id VARCHAR(36) NOT NULL, "
            "command VARCHAR(50) NOT NULL, "
            "idempotency_key VARCHAR(200) NOT NULL, "
            "principal_id VARCHAR(36), "
            "request_fingerprint VARCHAR(64) NOT NULL DEFAULT '', "
            "task_run_id VARCHAR(36), "
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "created_at DATETIME NOT NULL, "
            "FOREIGN KEY(task_id) REFERENCES tasks (id), "
            "FOREIGN KEY(principal_id) REFERENCES users (id), "
            "FOREIGN KEY(task_run_id) REFERENCES task_runs (id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {replacement} ("
            "task_id, command, idempotency_key, principal_id, "
            "request_fingerprint, task_run_id, id, created_at"
            ") SELECT task_id, command, idempotency_key, principal_id, "
            "request_fingerprint, task_run_id, id, created_at "
            "FROM mission_commands"
        )
    )
    connection.execute(text("DROP TABLE mission_commands"))
    connection.execute(
        text(f"ALTER TABLE {replacement} RENAME TO mission_commands")
    )


def _mission_comment_fingerprint(*, body: str, run_id: str | None) -> str:
    canonical = json.dumps(
        {"body": body, "run_id": run_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _backfill_mission_comment_fingerprints(connection) -> None:
    """Backfill only comments whose idempotency scope is unambiguous.

    A legacy keyed comment without an attempt cannot safely be attached to a
    principal/run scope: choosing the latest run could turn a delayed retry into
    a new effect.  Such a database therefore requires operator intervention.
    """

    rows = connection.execute(
        text(
            "SELECT c.id, c.task_id, c.task_run_id, c.author_user_id, c.body, "
            "c.idempotency_key, c.request_fingerprint, "
            "r.task_id AS run_task_id "
            "FROM mission_comments AS c "
            "LEFT JOIN task_runs AS r ON r.id = c.task_run_id"
        )
    ).mappings().all()
    invalid = []
    scopes: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        key = row["idempotency_key"]
        if key is not None:
            if (
                row["author_user_id"] is None
                or row["task_run_id"] is None
                or row["run_task_id"] != row["task_id"]
            ):
                invalid.append(row["id"])
                continue
            scopes.setdefault(
                (row["author_user_id"], row["task_run_id"], key), []
            ).append(row["id"])
        expected = _mission_comment_fingerprint(
            body=row["body"], run_id=row["task_run_id"]
        )
        stored = row["request_fingerprint"] or ""
        if stored and stored != expected:
            invalid.append(row["id"])
            continue
        if not stored:
            connection.execute(
                text(
                    "UPDATE mission_comments SET request_fingerprint = :fingerprint "
                    "WHERE id = :comment_id"
                ),
                {"fingerprint": expected, "comment_id": row["id"]},
            )
    ambiguous = [ids for ids in scopes.values() if len(ids) > 1]
    if invalid or ambiguous:
        raise RuntimeError(
            "Migration mission_comments refusée: "
            f"{len(invalid)} commentaire(s) sans portée fiable et "
            f"{len(ambiguous)} groupe(s) de clés ambigu(s)"
        )


def _replace_task_scoped_mission_comment_constraint(connection) -> None:
    """Remplace l'ancienne clé mission/key par la portée principal/run/key."""

    constraints = inspect(connection).get_unique_constraints("mission_comments")
    legacy_columns = ("task_id", "idempotency_key")
    if not any(
        tuple(constraint.get("column_names") or ()) == legacy_columns
        for constraint in constraints
    ):
        return
    replacement = "mission_comments_principal_run_scope_v2"
    if inspect(connection).has_table(replacement):
        raise RuntimeError(
            "Migration mission_comments refusée: table temporaire déjà présente"
        )
    connection.execute(
        text(
            f"CREATE TABLE {replacement} ("
            "task_id VARCHAR(36) NOT NULL, "
            "task_run_id VARCHAR(36), "
            "author_user_id VARCHAR(36) NOT NULL, "
            "body TEXT NOT NULL, "
            "idempotency_key VARCHAR(200), "
            "request_fingerprint VARCHAR(64) NOT NULL DEFAULT '', "
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "created_at DATETIME NOT NULL, "
            "CONSTRAINT uq_mission_comment_principal_run_key UNIQUE "
            "(author_user_id, task_run_id, idempotency_key), "
            "CONSTRAINT ck_mission_comment_key_requires_run CHECK "
            "(idempotency_key IS NULL OR task_run_id IS NOT NULL), "
            "FOREIGN KEY(task_id) REFERENCES tasks (id), "
            "FOREIGN KEY(task_run_id) REFERENCES task_runs (id), "
            "FOREIGN KEY(author_user_id) REFERENCES users (id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {replacement} ("
            "task_id, task_run_id, author_user_id, body, idempotency_key, "
            "request_fingerprint, id, created_at"
            ") SELECT task_id, task_run_id, author_user_id, body, "
            "idempotency_key, request_fingerprint, id, created_at "
            "FROM mission_comments"
        )
    )
    connection.execute(text("DROP TABLE mission_comments"))
    connection.execute(
        text(f"ALTER TABLE {replacement} RENAME TO mission_comments")
    )


def _upgrade_sqlite_schema(engine) -> None:
    """Migration additive minimale pour les bases SQLite MVP déjà créées.

    ``create_all`` ne complète pas une table existante. Ces ajouts sont tous
    rétrocompatibles et idempotents ; une vraie chaîne Alembic remplacera ce
    mécanisme lorsque le projet sortira du mode SQLite local.
    """

    if engine.dialect.name != "sqlite":
        return
    additions = {
        "tasks": {
            "is_mission": "INTEGER NOT NULL DEFAULT 0",
            "objective": "TEXT NOT NULL DEFAULT ''",
            "expected_outcome": "TEXT NOT NULL DEFAULT ''",
            "acceptance_criteria": "JSON NOT NULL DEFAULT '[]'",
            "autonomy": "JSON NOT NULL DEFAULT '{}'",
            "resources": "JSON NOT NULL DEFAULT '[]'",
            "budget": "JSON NOT NULL DEFAULT '{}'",
            "duration_seconds": "INTEGER",
            "created_by_user_id": "VARCHAR(36)",
            "attempt_counter": "INTEGER NOT NULL DEFAULT 0",
            "active_run_id": "VARCHAR(36)",
        },
        "task_runs": {
            "attempt_number": "INTEGER NOT NULL DEFAULT 0",
            "fencing_token": "INTEGER NOT NULL DEFAULT 0",
            "stop_requested_at": "DATETIME",
            "stop_requested_by_user_id": "VARCHAR(36)",
            "technical_validation": "JSON NOT NULL DEFAULT '{}'",
            "user_acceptance": "JSON NOT NULL DEFAULT '{}'",
            "updated_at": "DATETIME",
        },
        "approvals": {
            "target": "VARCHAR(1000) NOT NULL DEFAULT ''",
            "consequences": "JSON NOT NULL DEFAULT '[]'",
            "scope": "JSON NOT NULL DEFAULT '{}'",
            "footprint": "JSON NOT NULL DEFAULT '{}'",
            "action_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
            "invalidated_at": "DATETIME",
            "invalidated_reason": "TEXT NOT NULL DEFAULT ''",
        },
        "mission_commands": {
            "principal_id": "VARCHAR(36)",
            "request_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
        },
        "mission_comments": {
            "request_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, definition in columns.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN "{column_name}" {definition}'
                    )
                )
        if inspector.has_table("mission_commands"):
            _backfill_mission_command_principals(connection)
            _replace_task_scoped_mission_command_constraint(connection)
        if inspector.has_table("mission_comments"):
            _backfill_mission_comment_fingerprints(connection)
            _replace_task_scoped_mission_comment_constraint(connection)
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_is_mission ON tasks (is_mission)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_active_run_id ON tasks (active_run_id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_task_runs_attempt_number "
                "ON task_runs (attempt_number)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_mission_command_principal_key "
                "ON mission_commands (principal_id, command, idempotency_key) "
                "WHERE principal_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mission_commands_task_id "
                "ON mission_commands (task_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mission_commands_principal_id "
                "ON mission_commands (principal_id)"
            )
        )
        if inspect(connection).has_table("mission_comments"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_task_id "
                    "ON mission_comments (task_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_task_run_id "
                    "ON mission_comments (task_run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_author_user_id "
                    "ON mission_comments (author_user_id)"
                )
            )
        connection.execute(
            text(
                "UPDATE task_runs SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
