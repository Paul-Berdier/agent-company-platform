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


def _backfill_event_journal_sequence(connection) -> None:
    """Numérote les lignes d'événements antérieures au compteur de journal.

    Sous SQLite le ``rowid`` est unique et croît dans l'ordre d'insertion : il donne
    donc exactement l'ordre d'écriture recherché, là où ``created_at`` ne le donne
    pas (granularité d'horloge d'environ 1,5 ms sous Windows, donc égalités
    courantes).

    Le décalage par le maximum déjà attribué garantit l'idempotence dans le seul cas
    délicat : une base **partiellement** numérotée, où un ``rowid`` nu pourrait
    heurter un numéro déjà pris. Sur une base jamais migrée ce maximum vaut zéro et
    la numérotation est exactement le ``rowid``. Il est lu puis passé en paramètre
    plutôt qu'écrit en sous-requête : la valeur doit être figée **avant** la mise à
    jour de la table qu'elle interroge.
    """

    pending = connection.execute(
        text("SELECT COUNT(*) FROM events WHERE journal_seq IS NULL")
    ).scalar()
    if not pending:
        return
    offset = (
        connection.execute(text("SELECT MAX(journal_seq) FROM events")).scalar() or 0
    )
    connection.execute(
        text(
            "UPDATE events SET journal_seq = rowid + :offset WHERE journal_seq IS NULL"
        ),
        {"offset": int(offset)},
    )


def _ensure_unique_index(
    connection, *, table: str, columns: tuple[str, ...], name: str
) -> None:
    """Repose une unicité absente d'une table déjà créée sans elle.

    ``create_all`` ne complète jamais une table existante : une base où la table
    aurait été créée sans sa contrainte perdrait la garantie **silencieusement**.
    Un index unique donne exactement la même garantie et se crée, lui, de façon
    additive. La création est omise si l'unicité est déjà déclarée, afin de ne pas
    doubler l'index automatique posé par ``create_all``.
    """

    inspector = inspect(connection)
    declared = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table)
    }
    declared |= {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    if columns in declared:
        return
    column_list = ", ".join(f'"{column}"' for column in columns)
    connection.execute(
        text(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({column_list})')
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
        "events": {
            "schema_version": "VARCHAR(10) NOT NULL DEFAULT '1.0'",
            "sequence": "INTEGER",
            "journal_seq": "INTEGER",
            "conversation_id": "VARCHAR(36)",
            "step_id": "VARCHAR(64)",
            "executor": "VARCHAR(64)",
            "emitted_by": "VARCHAR(64)",
        },
        "artifacts": {
            "storage_key": "VARCHAR(200)",
            "content_type": "VARCHAR(200) NOT NULL DEFAULT 'application/octet-stream'",
            "original_name": "VARCHAR(500) NOT NULL DEFAULT ''",
            "source": "VARCHAR(50) NOT NULL DEFAULT 'worker'",
            "stream_kind": "VARCHAR(50) NOT NULL DEFAULT ''",
            "deleted_at": "DATETIME",
        },
        "automations": {
            "description": "TEXT NOT NULL DEFAULT ''",
            "timezone": "VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris'",
            "mission_template": "JSON NOT NULL DEFAULT '{}'",
            "enabled": "INTEGER NOT NULL DEFAULT 0",
            "catchup_policy": "VARCHAR(20) NOT NULL DEFAULT 'skip'",
            "max_concurrent_runs": "INTEGER NOT NULL DEFAULT 1",
            "next_run_at": "DATETIME",
            "last_fire_key": "VARCHAR(64)",
            "created_by_user_id": "VARCHAR(36)",
            "webhook_enabled": "INTEGER NOT NULL DEFAULT 0",
            "webhook_secret_hash": "VARCHAR(64)",
            "webhook_rotated_at": "DATETIME",
        },
        "automation_runs": {
            "task_id": "VARCHAR(36)",
            "trigger_kind": "VARCHAR(20) NOT NULL DEFAULT 'schedule'",
            "detail": "VARCHAR(500) NOT NULL DEFAULT ''",
        },
        "budget_usage": {
            "cost": "FLOAT NOT NULL DEFAULT 0",
            "currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'",
            "tokens_input": "INTEGER NOT NULL DEFAULT 0",
            "tokens_output": "INTEGER NOT NULL DEFAULT 0",
            "tool_calls": "INTEGER NOT NULL DEFAULT 0",
            "usage_reported": "INTEGER NOT NULL DEFAULT 0",
            "cost_reported": "INTEGER NOT NULL DEFAULT 0",
            "tokens_input_reported": "INTEGER NOT NULL DEFAULT 0",
            "tokens_output_reported": "INTEGER NOT NULL DEFAULT 0",
            "tool_calls_reported": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "DATETIME",
        },
        "alerts": {
            "detail": "TEXT NOT NULL DEFAULT ''",
            "task_id": "VARCHAR(36)",
            "automation_id": "VARCHAR(36)",
            "acknowledged_at": "DATETIME",
            "acknowledged_by_user_id": "VARCHAR(36)",
            "acknowledgement_comment": "TEXT NOT NULL DEFAULT ''",
            "dedupe_key_active": "VARCHAR(64)",
        },
        "notification_preferences": {
            "project_id": "VARCHAR(36)",
            "user_id": "VARCHAR(36)",
            "channel": "VARCHAR(20) NOT NULL DEFAULT 'in_app'",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "minimum_severity": "VARCHAR(20) NOT NULL DEFAULT 'warning'",
            "budget_alerts": "INTEGER NOT NULL DEFAULT 1",
            "automation_failures": "INTEGER NOT NULL DEFAULT 1",
            "storage_alerts": "INTEGER NOT NULL DEFAULT 1",
            "updated_at": "DATETIME",
        },
        "project_budget_policies": {
            "project_id": "VARCHAR(36)",
            "timezone": "VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris'",
            "policy": "JSON NOT NULL DEFAULT '{}'",
            "updated_at": "DATETIME",
        },
        "budget_usage_reports": {
            "task_run_id": "VARCHAR(36)",
            "report_id": "VARCHAR(128)",
            "permit_id": "VARCHAR(128)",
            "project_id": "VARCHAR(36)",
            "provider": "VARCHAR(100)",
            "kind": "VARCHAR(20) NOT NULL DEFAULT 'usage'",
            "source": "VARCHAR(20)",
            "phase": "VARCHAR(20)",
            "cost": "NUMERIC(18, 6)",
            "currency": "VARCHAR(3)",
            "tokens_input": "INTEGER",
            "tokens_output": "INTEGER",
            "tool_calls": "INTEGER",
            "estimated": "INTEGER NOT NULL DEFAULT 0",
            "allowed": "INTEGER NOT NULL DEFAULT 1",
            "reconciled_at": "DATETIME",
            "occurred_at": "DATETIME",
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
        if inspect(connection).has_table("events"):
            # Unicité partielle : les événements historiques et ceux sans
            # tentative n'ont pas de séquence et ne doivent pas être refusés.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_event_run_sequence "
                    "ON events (task_run_id, sequence) "
                    "WHERE task_run_id IS NOT NULL AND sequence IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_task_run_sequence "
                    "ON events (task_run_id, sequence)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_conversation_id "
                    "ON events (conversation_id)"
                )
            )
            # Ordre total du journal : unicité partielle, car une ligne peut
            # rester non numérotée le temps d'un démarrage interrompu.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_journal_seq "
                    "ON events (journal_seq) WHERE journal_seq IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_journal_seq "
                    "ON events (journal_seq)"
                )
            )
            _backfill_event_journal_sequence(connection)
        if inspect(connection).has_table("artifacts"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_artifacts_storage_key "
                    "ON artifacts (storage_key)"
                )
            )
        if inspect(connection).has_table("automations"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_project_id "
                    "ON automations (project_id)"
                )
            )
            # Le planificateur ne pose qu'une question à chaque examen :
            # « quelles automatisations actives sont dues ? ». Sans cet index,
            # elle coûte une lecture complète de la table toutes les trente secondes.
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_next_run_at "
                    "ON automations (next_run_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_created_by_user_id "
                    "ON automations (created_by_user_id)"
                )
            )
        if inspect(connection).has_table("automation_runs"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automation_runs_automation_id "
                    "ON automation_runs (automation_id)"
                )
            )
            # Unicité de l'occurrence nominale : c'est elle, et non une
            # vérification en mémoire, qui interdit deux missions pour un même
            # déclenchement planifié.
            _ensure_unique_index(
                connection,
                table="automation_runs",
                columns=("automation_id", "fire_key"),
                name="uq_automation_runs_fire_key",
            )
            connection.execute(
                text(
                    "UPDATE automation_runs SET trigger_kind = 'schedule' "
                    "WHERE trigger_kind IS NULL OR trigger_kind = ''"
                )
            )
        if inspect(connection).has_table("budget_usage"):
            # Une seule ligne de consommation par tentative : les incréments
            # concurrents portent alors tous sur la même ligne.
            _ensure_unique_index(
                connection,
                table="budget_usage",
                columns=("task_run_id",),
                name="ix_budget_usage_task_run_id",
            )
            connection.execute(
                text(
                    "UPDATE budget_usage SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("alerts"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_alerts_project_id "
                    "ON alerts (project_id)"
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_alerts_kind ON alerts (kind)")
            )
            # ``dedupe_key_active`` vaut ``NULL`` une fois l'alerte acquittée, et
            # ``NULL`` n'entre pas en conflit avec ``NULL`` : l'unicité ne porte donc
            # que sur les alertes **ouvertes**.
            _ensure_unique_index(
                connection,
                table="alerts",
                columns=("project_id", "dedupe_key_active"),
                name="uq_alerts_dedupe_active",
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_alerts_acknowledged_by_user_id "
                    "ON alerts (acknowledged_by_user_id)"
                )
            )
        if inspect(connection).has_table("notification_preferences"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_notification_preferences_project_id "
                    "ON notification_preferences (project_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_notification_preferences_user_id "
                    "ON notification_preferences (user_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="notification_preferences",
                columns=("project_id", "user_id"),
                name="uq_notification_preferences_project_user",
            )
            connection.execute(
                text(
                    "UPDATE notification_preferences SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("project_budget_policies"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_project_budget_policies_project_id "
                    "ON project_budget_policies (project_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="project_budget_policies",
                columns=("project_id",),
                name="uq_project_budget_policies_project",
            )
            connection.execute(
                text(
                    "UPDATE project_budget_policies SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("budget_usage_reports"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_task_run_id "
                    "ON budget_usage_reports (task_run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_project_id "
                    "ON budget_usage_reports (project_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_provider "
                    "ON budget_usage_reports (provider)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_occurred_at "
                    "ON budget_usage_reports (occurred_at)"
                )
            )
            _ensure_unique_index(
                connection,
                table="budget_usage_reports",
                columns=("task_run_id", "report_id"),
                name="uq_budget_usage_reports_run_report",
            )
            connection.execute(
                text(
                    "UPDATE budget_usage_reports SET kind = 'usage' "
                    "WHERE kind IS NULL OR kind = ''"
                )
            )
        connection.execute(
            text(
                "UPDATE task_runs SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
