"""Garanties de stockage ajoutées pour le service complet du Lot F."""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from acp_database import engine as engine_module
from acp_database.models import (
    AlertModel,
    AutomationCommandModel,
    AutomationModel,
    AutomationRunModel,
    AutomationWebhookRotationModel,
    Base,
    BudgetUsageModel,
    BudgetUsageReportModel,
    NotificationPreferencesModel,
    ProjectBudgetPolicyModel,
    TaskModel,
    TaskRunModel,
)


NEW_TABLES = {
    "automation_commands",
    "automation_webhook_rotations",
    "notification_preferences",
    "project_budget_policies",
    "budget_usage_reports",
}

LOT_F_PARITY_TABLES = (
    "workers",
    "automation_webhook_rotations",
    "automation_commands",
    "automation_runs",
    "scheduler_leases",
    "budget_usage",
    "alerts",
    "notification_preferences",
    "project_budget_policies",
    "budget_usage_reports",
)


def _memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture
def engine():
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _automation(**overrides) -> AutomationModel:
    values = {
        "project_id": "project-1",
        "name": "Routine",
        "schedule_kind": "cron",
        "schedule_expression": "0 9 * * *",
        "mission_template": {"title": "Routine"},
    }
    values.update(overrides)
    return AutomationModel(**values)


def _run(**overrides) -> AutomationRunModel:
    values = {
        "automation_id": "automation-1",
        "fire_key": "0" * 32,
        "scheduled_for": datetime(2026, 9, 13, 7, tzinfo=timezone.utc),
        "outcome": "launched",
    }
    values.update(overrides)
    return AutomationRunModel(**values)


def _report(**overrides) -> BudgetUsageReportModel:
    values = {
        "task_run_id": "run-1",
        "report_id": "report-1",
        "permit_id": "permit-1",
        "project_id": "project-1",
        "provider": "openai",
        "source": "provider",
        "phase": "execution",
        "tokens_input": 0,
        "accounting_day": "2026-09-14",
        "verdict_snapshot": {
            "state": "ok",
            "measured": True,
            "limit_reached": None,
            "cost": None,
            "currency": "EUR",
            "tokens_input": 0,
            "tokens_output": None,
            "tool_calls": None,
            "usage_reported": True,
            "estimated": False,
        },
    }
    values.update(overrides)
    return BudgetUsageReportModel(**values)


def _unique_columns(inspector, table: str) -> set[tuple[str, ...]]:
    result = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table)
    }
    result |= {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    return result


def _normalized_expression(value: str | None) -> str:
    return "".join((value or "").lower().split())


def _structural_signature(inspector, table: str):
    columns = tuple(
        (
            column["name"],
            "".join(str(column["type"]).upper().split()),
            bool(column["nullable"]),
            bool(column.get("primary_key")),
            column.get("default"),
        )
        for column in inspector.get_columns(table)
    )
    checks = {
        (constraint.get("name"), _normalized_expression(constraint.get("sqltext")))
        for constraint in inspector.get_check_constraints(table)
    }
    foreign_keys = {
        (
            tuple(constraint.get("constrained_columns") or ()),
            constraint.get("referred_table"),
            tuple(constraint.get("referred_columns") or ()),
        )
        for constraint in inspector.get_foreign_keys(table)
    }
    return {
        "columns": columns,
        "primary_key": tuple(
            inspector.get_pk_constraint(table).get("constrained_columns") or ()
        ),
        "checks": checks,
        "foreign_keys": foreign_keys,
        "uniques": _unique_columns(inspector, table),
    }


def test_create_all_exposes_the_extended_schema(engine):
    inspector = inspect(engine)
    assert NEW_TABLES <= set(inspector.get_table_names())

    automation = {column["name"] for column in inspector.get_columns("automations")}
    assert {
        "webhook_enabled",
        "webhook_secret_hash",
        "webhook_rotated_at",
        "webhook_rotation_number",
        "create_idempotency_key",
        "create_request_fingerprint",
    } <= automation

    rotations = {
        column["name"]
        for column in inspector.get_columns("automation_webhook_rotations")
    }
    assert {
        "automation_id",
        "principal_id",
        "idempotency_key",
        "request_fingerprint",
        "secret_hash",
        "rotation_number",
        "rotated_at",
    } <= rotations

    commands = {
        column["name"] for column in inspector.get_columns("automation_commands")
    }
    assert {
        "automation_id",
        "principal_id",
        "command",
        "idempotency_key",
        "request_fingerprint",
        "postcondition",
        "result_revision",
    } <= commands
    assert "mutation_revision" in automation

    runs = {column["name"] for column in inspector.get_columns("automation_runs")}
    assert "trigger_kind" in runs
    assert "schedule_timezone" in runs
    run_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("automation_runs")
    }
    assert run_indexes["ix_automation_runs_reconcile_order"] == (
        "automation_id",
        "completion_observed_at",
        "scheduled_for",
        "id",
        "outcome",
    )

    alerts = {column["name"] for column in inspector.get_columns("alerts")}
    assert {"acknowledgement_comment", "acknowledged_by_user_id"} <= alerts

    cache = {
        column["name"]: column for column in inspector.get_columns("budget_usage")
    }
    assert {
        "cost_reported",
        "tokens_input_reported",
        "tokens_output_reported",
        "tool_calls_reported",
    } <= set(cache)
    assert "NUMERIC" in str(cache["cost"]["type"]).upper()

    ledger = {
        column["name"]: column
        for column in inspector.get_columns("budget_usage_reports")
    }
    assert {
        "task_run_id",
        "report_id",
        "permit_id",
        "project_id",
        "provider",
        "kind",
        "source",
        "phase",
        "cost",
        "currency",
        "tokens_input",
        "tokens_output",
        "tool_calls",
        "estimated",
        "allowed",
        "reconciled_at",
        "accounting_day",
        "verdict_snapshot",
        "occurred_at",
    } <= set(ledger)
    for name in ("cost", "currency", "tokens_input", "tokens_output", "tool_calls"):
        assert ledger[name]["nullable"] is True


def test_create_all_declares_foreign_keys_and_idempotence_keys(engine):
    inspector = inspect(engine)
    assert ("project_id", "user_id") in _unique_columns(
        inspector, "notification_preferences"
    )
    assert ("project_id",) in _unique_columns(inspector, "project_budget_policies")
    assert ("task_run_id", "report_id") in _unique_columns(
        inspector, "budget_usage_reports"
    )
    assert (
        "project_id",
        "created_by_user_id",
        "create_idempotency_key",
    ) in _unique_columns(inspector, "automations")
    assert (
        "automation_id",
        "principal_id",
        "idempotency_key",
    ) in _unique_columns(inspector, "automation_webhook_rotations")
    assert ("automation_id", "rotation_number") in _unique_columns(
        inspector, "automation_webhook_rotations"
    )
    assert (
        "automation_id",
        "principal_id",
        "command",
        "idempotency_key",
    ) in _unique_columns(inspector, "automation_commands")

    alert_foreign_keys = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("alerts")
    }
    assert ("users", ("acknowledged_by_user_id",)) in alert_foreign_keys

    ledger_foreign_keys = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("budget_usage_reports")
    }
    assert {
        ("task_runs", ("task_run_id",)),
        ("projects", ("project_id",)),
    } <= ledger_foreign_keys

    rotation_foreign_keys = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("automation_webhook_rotations")
    }
    assert {
        ("automations", ("automation_id",)),
        ("users", ("principal_id",)),
    } <= rotation_foreign_keys

    command_foreign_keys = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("automation_commands")
    }
    assert {
        ("automations", ("automation_id",)),
        ("users", ("principal_id",)),
    } <= command_foreign_keys


def test_automation_command_journal_scopes_keys_and_revisions(engine):
    with Session(engine) as db:
        db.add(
            AutomationCommandModel(
                automation_id="automation-1",
                principal_id="user-1",
                command="enable",
                idempotency_key="same-key",
                request_fingerprint="a" * 64,
                postcondition={"enabled": True},
                result_revision=1,
            )
        )
        db.commit()
        db.add(
            AutomationCommandModel(
                automation_id="automation-1",
                principal_id="user-1",
                command="unknown",
                idempotency_key="invalid-command",
                request_fingerprint="c" * 64,
                postcondition={},
                result_revision=3,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(
            AutomationCommandModel(
                automation_id="automation-1",
                principal_id="user-1",
                command="enable",
                idempotency_key="same-key",
                request_fingerprint="a" * 64,
                postcondition={"enabled": True},
                result_revision=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add_all(
            [
                AutomationCommandModel(
                    automation_id="automation-1",
                    principal_id="user-2",
                    command="enable",
                    idempotency_key="same-key",
                    request_fingerprint="a" * 64,
                    postcondition={"enabled": True},
                    result_revision=1,
                ),
                AutomationCommandModel(
                    automation_id="automation-1",
                    principal_id="user-1",
                    command="disable",
                    idempotency_key="same-key",
                    request_fingerprint="b" * 64,
                    postcondition={"enabled": False},
                    result_revision=2,
                ),
            ]
        )
        db.commit()


def test_defaults_keep_unknown_usage_distinct_from_real_zero(engine):
    with Session(engine) as db:
        automation = _automation()
        run = _run()
        cache = BudgetUsageModel(task_run_id="run-1")
        alert = AlertModel(
            project_id="project-1",
            kind="budget.exceeded",
            severity="critical",
            title="Budget dépassé",
            dedupe_key="budget:1",
            dedupe_key_active="budget:1",
        )
        preferences = NotificationPreferencesModel(
            project_id="project-1", user_id="user-1"
        )
        policy = ProjectBudgetPolicyModel(project_id="project-1")
        report = _report()
        db.add_all([automation, run, cache, alert, preferences, policy, report])
        db.commit()
        for value in (automation, run, cache, alert, preferences, policy, report):
            db.refresh(value)

        assert automation.webhook_enabled == 0
        assert automation.webhook_secret_hash is None
        assert automation.webhook_rotated_at is None
        assert automation.webhook_rotation_number == 0
        assert run.trigger_kind == "schedule"
        assert alert.acknowledgement_comment == ""
        assert cache.cost == Decimal("0.000000")
        assert cache.usage_reported == 0
        assert (
            cache.cost_reported,
            cache.tokens_input_reported,
            cache.tokens_output_reported,
            cache.tool_calls_reported,
        ) == (0, 0, 0, 0)
        assert preferences.channel == "in_app"
        assert preferences.enabled == 1
        assert preferences.minimum_severity == "warning"
        assert (
            preferences.budget_alerts,
            preferences.automation_failures,
            preferences.storage_alerts,
        ) == (1, 1, 1)
        assert policy.timezone == "Europe/Paris"
        assert policy.policy == {}
        assert report.kind == "usage"
        assert report.permit_id == "permit-1"
        assert report.accounting_day == "2026-09-14"
        assert report.verdict_snapshot["state"] == "ok"
        assert report.allowed == 1
        assert report.reconciled_at is None
        assert report.tokens_input == 0
        assert report.cost is None


def test_notification_preferences_and_budget_policy_have_one_current_row(engine):
    with Session(engine) as db:
        db.add(
            NotificationPreferencesModel(project_id="project-1", user_id="user-1")
        )
        db.commit()
        db.add(
            NotificationPreferencesModel(project_id="project-1", user_id="user-1")
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(ProjectBudgetPolicyModel(project_id="project-1"))
        db.commit()
        db.add(ProjectBudgetPolicyModel(project_id="project-1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_usage_ledger_is_exactly_once_and_keeps_reservations_distinct(engine):
    with Session(engine) as db:
        db.add(_report(kind="reservation", cost=Decimal("1.25"), currency="EUR"))
        db.commit()
        stored = db.query(BudgetUsageReportModel).one()
        assert stored.kind == "reservation"
        assert stored.cost == Decimal("1.250000")

        db.add(_report(kind="usage", tokens_input=12))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Le rapprochement pré/post-effet utilise deux identifiants explicites.
        db.add(_report(report_id="usage-1", kind="usage", tokens_input=12))
        db.commit()
        assert db.query(BudgetUsageReportModel).count() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "guess"},
        {"source": "unknown"},
        {"phase": "billing"},
        {"tokens_input": -1},
        {
            "tokens_input": None,
            "cost": Decimal("1000000000000"),
            "currency": "EUR",
        },
        {"tokens_input": None, "cost": Decimal("1"), "currency": None},
        {
            "tokens_input": None,
            "cost": None,
            "currency": None,
            "tokens_output": None,
            "tool_calls": None,
        },
    ],
)
def test_usage_ledger_rejects_invalid_or_unmeasured_rows(engine, overrides):
    with Session(engine) as db:
        db.add(_report(**overrides))
        with pytest.raises(IntegrityError):
            db.commit()


LEGACY_AUTOMATIONS = """
CREATE TABLE automations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schedule_kind VARCHAR(20) NOT NULL,
    schedule_expression VARCHAR(200) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris',
    mission_template JSON NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0,
    catchup_policy VARCHAR(20) NOT NULL DEFAULT 'skip',
    max_concurrent_runs INTEGER NOT NULL DEFAULT 1,
    next_run_at DATETIME,
    last_fire_key VARCHAR(64),
    created_by_user_id VARCHAR(36)
)
"""

LEGACY_WORKERS = """
CREATE TABLE workers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    name VARCHAR(200) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    token_prefix VARCHAR(12) NOT NULL,
    token_expires_at DATETIME NOT NULL,
    capabilities JSON NOT NULL,
    max_concurrency INTEGER NOT NULL,
    active_runs INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    simulation INTEGER NOT NULL,
    metadata JSON NOT NULL,
    last_seen_at DATETIME,
    lease_expires_at DATETIME
)
"""

LEGACY_ROTATIONS = """
CREATE TABLE automation_webhook_rotations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    automation_id VARCHAR(36) NOT NULL,
    principal_id VARCHAR(36) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    secret_hash VARCHAR(64) NOT NULL,
    rotation_number INTEGER NOT NULL,
    rotated_at DATETIME NOT NULL
)
"""

LEGACY_COMMANDS = """
CREATE TABLE automation_commands (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    automation_id VARCHAR(36) NOT NULL,
    principal_id VARCHAR(36) NOT NULL,
    command VARCHAR(30) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    postcondition JSON NOT NULL DEFAULT '{}',
    result_revision BIGINT NOT NULL
)
"""

LEGACY_RUNS = """
CREATE TABLE automation_runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    automation_id VARCHAR(36) NOT NULL,
    fire_key VARCHAR(64) NOT NULL,
    scheduled_for DATETIME NOT NULL,
    fired_at DATETIME NOT NULL,
    task_id VARCHAR(36),
    outcome VARCHAR(30) NOT NULL,
    detail VARCHAR(500) NOT NULL DEFAULT '',
    CONSTRAINT uq_automation_runs_fire_key UNIQUE (automation_id, fire_key)
)
"""

LEGACY_SCHEDULER_LEASES = """
CREATE TABLE scheduler_leases (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    scheduler_key VARCHAR(64) NOT NULL,
    owner_worker_id VARCHAR(36),
    holder_id VARCHAR(64),
    fencing_token INTEGER NOT NULL DEFAULT 0,
    lease_expires_at DATETIME,
    last_renewed_at DATETIME,
    released_at DATETIME
)
"""

LEGACY_BUDGET_USAGE = """
CREATE TABLE budget_usage (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    task_run_id VARCHAR(36) NOT NULL UNIQUE,
    cost FLOAT NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    usage_reported INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME
)
"""

LEGACY_ALERTS = """
CREATE TABLE alerts (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    kind VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(300) NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    task_id VARCHAR(36),
    automation_id VARCHAR(36),
    acknowledged_at DATETIME,
    acknowledged_by_user_id VARCHAR(36),
    dedupe_key VARCHAR(64) NOT NULL,
    dedupe_key_active VARCHAR(64),
    CONSTRAINT uq_alerts_dedupe_active UNIQUE (project_id, dedupe_key_active),
    FOREIGN KEY(acknowledged_by_user_id) REFERENCES users (id)
)
"""

LEGACY_NOTIFICATION_PREFERENCES = """
CREATE TABLE notification_preferences (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    channel VARCHAR(20) NOT NULL DEFAULT 'in_app',
    enabled INTEGER NOT NULL DEFAULT 1,
    minimum_severity VARCHAR(20) NOT NULL DEFAULT 'warning',
    budget_alerts INTEGER NOT NULL DEFAULT 1,
    automation_failures INTEGER NOT NULL DEFAULT 1,
    storage_alerts INTEGER NOT NULL DEFAULT 1,
    updated_at DATETIME
)
"""

LEGACY_PROJECT_BUDGET_POLICIES = """
CREATE TABLE project_budget_policies (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris',
    policy JSON NOT NULL DEFAULT '{}',
    updated_at DATETIME
)
"""

LEGACY_LEDGER_WITHOUT_KIND = """
CREATE TABLE budget_usage_reports (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    task_run_id VARCHAR(36) NOT NULL,
    report_id VARCHAR(128) NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    source VARCHAR(20) NOT NULL,
    phase VARCHAR(20) NOT NULL,
    cost NUMERIC(18, 6),
    currency VARCHAR(3),
    tokens_input INTEGER,
    tokens_output INTEGER,
    tool_calls INTEGER,
    estimated INTEGER NOT NULL DEFAULT 0,
    occurred_at DATETIME NOT NULL
)
"""

PARTIAL_INVALID_AUTOMATIONS = """
CREATE TABLE automations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schedule_kind VARCHAR(20) NOT NULL,
    schedule_expression VARCHAR(200) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris',
    mission_template JSON NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0,
    catchup_policy VARCHAR(20) NOT NULL DEFAULT 'skip',
    max_concurrent_runs INTEGER NOT NULL DEFAULT 1,
    next_run_at DATETIME,
    last_fire_key VARCHAR(64),
    created_by_user_id VARCHAR(36),
    consecutive_failures INTEGER NOT NULL DEFAULT 0
)
"""

AUTOMATION_INSERT = text(
    "INSERT INTO automations ("
    "id, created_at, project_id, name, description, schedule_kind, "
    "schedule_expression, timezone, mission_template, enabled, catchup_policy, "
    "max_concurrent_runs, created_by_user_id, create_idempotency_key, "
    "create_request_fingerprint, webhook_enabled, webhook_rotation_number, "
    "consecutive_failures, failure_threshold"
    ") VALUES ("
    ":id, '2026-01-02', :project_id, 'Routine', '', 'cron', '0 9 * * *', "
    "'Europe/Paris', '{}', 0, 'skip', 1, :created_by_user_id, "
    ":create_idempotency_key, :create_request_fingerprint, 0, "
    ":webhook_rotation_number, :consecutive_failures, :failure_threshold"
    ")"
)


def _seed_automation_parent_scope(connection) -> None:
    connection.execute(
        text(
            "INSERT INTO organizations (id, created_at, name, description) "
            "VALUES ('organization-1', '2026-01-01', 'Organisation', '')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO users ("
            "id, created_at, login_normalized, display_name, password_hash, "
            "platform_role, is_active, password_changed_at"
            ") VALUES ("
            "'user-1', '2026-01-01', 'owner@example.test', 'Owner', 'hash', "
            "'owner', 1, '2026-01-01'"
            ")"
        )
    )
    connection.execute(
        text(
            "INSERT INTO workspaces ("
            "id, created_at, organization_id, name, kind, description"
            ") VALUES ("
            "'workspace-1', '2026-01-01', 'organization-1', "
            "'Workspace', 'generic', ''"
            ")"
        )
    )
    connection.execute(
        text(
            "INSERT INTO projects ("
            "id, created_at, workspace_id, name, project_type, description, status"
            ") VALUES ("
            "'project-1', '2026-01-01', 'workspace-1', 'Project', "
            "'generic', '', 'active'"
            ")"
        )
    )
    connection.execute(
        TaskModel.__table__.insert().values(
            id="task-1",
            project_id="project-1",
            title="Mission historique",
        )
    )
    connection.execute(
        TaskRunModel.__table__.insert().values(
            id="task-run-1",
            task_id="task-1",
        )
    )


def _automation_values(**overrides):
    values = {
        "id": "automation-extra",
        "project_id": "project-1",
        "created_by_user_id": None,
        "create_idempotency_key": None,
        "create_request_fingerprint": None,
        "webhook_rotation_number": 0,
        "consecutive_failures": 0,
        "failure_threshold": 3,
    }
    values.update(overrides)
    return values


def _assert_automation_insert_rejected(engine, **overrides) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(AUTOMATION_INSERT, _automation_values(**overrides))


def _assert_sql_rejected(engine, statement: str) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text(statement))


def test_sqlite_fresh_init_is_idempotent_and_keeps_model_parity(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_fresh_twice.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        first = {
            table_name: _structural_signature(inspect(engine), table_name)
            for table_name in LOT_F_PARITY_TABLES
        }
        engine_module.init_db()
        second = {
            table_name: _structural_signature(inspect(engine), table_name)
            for table_name in LOT_F_PARITY_TABLES
        }
        assert second == first
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_sqlite_upgrade_replaces_known_legacy_ledger_cost_check(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_legacy_ledger_cost_check.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    expected = "cost IS NULL OR (cost >= 0 AND cost <= 999999999999)"
    legacy = "cost IS NULL OR cost >= 0"
    with bootstrap.begin() as connection:
        ddl = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'budget_usage_reports'"
            )
        ).scalar_one()
        assert expected in ddl
        connection.execute(text('DROP TABLE "budget_usage_reports"'))
        connection.execute(text(ddl.replace(expected, legacy)))
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        checks = {
            constraint.get("name"): _normalized_expression(
                constraint.get("sqltext")
            )
            for constraint in inspect(engine).get_check_constraints(
                "budget_usage_reports"
            )
        }
        assert checks["ck_budget_report_cost"] == _normalized_expression(expected)
        engine_module.init_db()
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_sqlite_upgrade_is_additive_idempotent_and_backfills_defaults(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_extensions_legacy.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    # Chaque table Lot F ciblée existe déjà, mais avec un DDL historique incomplet.
    # Les tables parentes générales restent celles du modèle courant.
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        for table_name in (
            "budget_usage_reports",
            "project_budget_policies",
            "notification_preferences",
            "scheduler_leases",
            "automation_commands",
            "automation_webhook_rotations",
            "alerts",
            "budget_usage",
            "automation_runs",
            "workers",
            "automations",
        ):
            connection.execute(text(f'DROP TABLE "{table_name}"'))
        for ddl in (
            LEGACY_WORKERS,
            LEGACY_AUTOMATIONS,
            LEGACY_ROTATIONS,
            LEGACY_COMMANDS,
            LEGACY_RUNS,
            LEGACY_SCHEDULER_LEASES,
            LEGACY_BUDGET_USAGE,
            LEGACY_ALERTS,
            LEGACY_NOTIFICATION_PREFERENCES,
            LEGACY_PROJECT_BUDGET_POLICIES,
            LEGACY_LEDGER_WITHOUT_KIND,
        ):
            connection.execute(text(ddl))
        _seed_automation_parent_scope(connection)
        connection.execute(
            text(
                "CREATE INDEX ix_automations_legacy_name "
                "ON automations (name)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE automation_migration_audit ("
                "automation_id VARCHAR(36) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER trg_automations_legacy_insert "
                "AFTER INSERT ON automations BEGIN "
                "INSERT INTO automation_migration_audit (automation_id) "
                "VALUES (NEW.id); END"
            )
        )
        connection.execute(
            text("CREATE INDEX ix_alerts_local_title ON alerts (title)")
        )
        connection.execute(
            text(
                "CREATE TABLE alert_migration_audit ("
                "alert_id VARCHAR(36) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER trg_alerts_local_insert "
                "AFTER INSERT ON alerts BEGIN "
                "INSERT INTO alert_migration_audit (alert_id) "
                "VALUES (NEW.id); END"
            )
        )
        connection.execute(
            text(
                "INSERT INTO workers ("
                "id, created_at, name, token_hash, token_prefix, token_expires_at, "
                "capabilities, max_concurrency, active_runs, status, simulation, "
                "metadata) VALUES ("
                "'worker-legacy', '2026-01-01', 'Worker legacy', 'hash', 'prefix', "
                "'2027-01-01', '[]', 1, 0, 'online', 0, '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO automations "
                "(id, created_at, project_id, name, schedule_kind, "
                "schedule_expression, mission_template) VALUES "
                "('automation-legacy', '2026-01-01', 'project-1', 'Routine', "
                "'cron', '0 9 * * *', '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO automation_webhook_rotations ("
                "id, created_at, automation_id, principal_id, idempotency_key, "
                "request_fingerprint, secret_hash, rotation_number, rotated_at"
                ") VALUES ("
                "'rotation-legacy', '2026-01-01', 'automation-legacy', 'user-1', "
                "'rotation-request-1', 'fingerprint', 'secret-hash', 1, "
                "'2026-01-01'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO automation_commands ("
                "id, created_at, automation_id, principal_id, command, "
                "idempotency_key, request_fingerprint, postcondition, "
                "result_revision) VALUES ("
                "'command-legacy', '2026-01-01', 'automation-legacy', 'user-1', "
                "'disable', 'command-request-1', 'fingerprint', "
                ":postcondition, 1)"
            ),
            {"postcondition": json.dumps({"enabled": False})},
        )
        connection.execute(
            text(
                "INSERT INTO automation_runs "
                "(id, created_at, automation_id, fire_key, scheduled_for, "
                "fired_at, outcome) VALUES "
                "('run-legacy', '2026-01-01', 'automation-legacy', 'fire-1', "
                "'2026-01-01', '2026-01-01', 'launched')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO scheduler_leases ("
                "id, created_at, scheduler_key, owner_worker_id, holder_id, "
                "fencing_token) VALUES ("
                "'lease-legacy', '2026-01-01', 'automation-scheduler', "
                "'worker-legacy', 'holder-1', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO budget_usage "
                "(id, created_at, task_run_id) VALUES "
                "('usage-legacy', '2026-01-01', 'task-run-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO alerts "
                "(id, created_at, project_id, kind, severity, title, dedupe_key) "
                "VALUES ('alert-legacy', '2026-01-01', 'project-1', "
                "'budget.exceeded', 'critical', 'Budget', 'budget:1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO notification_preferences ("
                "id, created_at, project_id, user_id) VALUES ("
                "'preferences-legacy', '2026-01-01', 'project-1', 'user-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO project_budget_policies ("
                "id, created_at, project_id) VALUES ("
                "'policy-legacy', '2026-01-01', 'project-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO budget_usage_reports "
                "(id, created_at, task_run_id, report_id, project_id, provider, "
                "source, phase, tokens_input, occurred_at) VALUES "
                "('report-legacy', '2026-01-01', 'task-run-1', 'report-1', "
                "'project-1', 'openai', 'provider', 'execution', 12, "
                "'2026-01-01 00:30:00+02:00')"
            )
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        inspector = inspect(engine)
        assert NEW_TABLES <= set(inspector.get_table_names())
        fresh = _memory_engine()
        try:
            Base.metadata.create_all(fresh)
            fresh_inspector = inspect(fresh)
            for table_name in LOT_F_PARITY_TABLES:
                assert _structural_signature(
                    inspector, table_name
                ) == _structural_signature(fresh_inspector, table_name)
        finally:
            fresh.dispose()

        with engine.connect() as connection:
            automation = connection.execute(
                text(
                    "SELECT webhook_enabled, webhook_secret_hash, webhook_rotated_at, "
                    "webhook_rotation_number, create_idempotency_key, "
                    "create_request_fingerprint, mutation_revision "
                    "FROM automations WHERE id = 'automation-legacy'"
                )
            ).one()
            assert tuple(automation) == (0, None, None, 0, None, None, 0)
            assert connection.execute(
                text(
                    "SELECT trigger_kind, schedule_timezone FROM automation_runs "
                    "WHERE id = 'run-legacy'"
                )
            ).one() == ("schedule", "Europe/Paris")
            cache = connection.execute(
                text(
                    "SELECT cost_reported, tokens_input_reported, "
                    "tokens_output_reported, tool_calls_reported "
                    "FROM budget_usage WHERE id = 'usage-legacy'"
                )
            ).one()
            assert tuple(cache) == (0, 0, 0, 0)
            cache_columns = {
                column["name"]: "".join(
                    str(column["type"]).upper().split()
                )
                for column in inspector.get_columns("budget_usage")
            }
            assert cache_columns["cost"] == "NUMERIC(18,6)"
            assert cache_columns["tokens_input"] == "BIGINT"
            assert cache_columns["tokens_output"] == "BIGINT"
            assert cache_columns["tool_calls"] == "BIGINT"
            assert connection.execute(
                text(
                    "SELECT acknowledgement_comment FROM alerts "
                    "WHERE id = 'alert-legacy'"
                )
            ).scalar() == ""
            ledger = connection.execute(
                text(
                    "SELECT kind, permit_id, allowed, reconciled_at, accounting_day, "
                    "verdict_snapshot "
                    "FROM budget_usage_reports WHERE id = 'report-legacy'"
                )
            ).one()
            assert tuple(ledger[:5]) == (
                "usage",
                "legacy:report-legacy",
                1,
                None,
                "2025-12-31",
            )
            snapshot = json.loads(ledger.verdict_snapshot)
            assert snapshot == {
                "cost": None,
                "currency": "EUR",
                "estimated": False,
                "limit_reached": None,
                "measured": True,
                "state": "unknown",
                "tokens_input": 12,
                "tokens_output": None,
                "tool_calls": None,
                "usage_reported": True,
            }
            assert connection.execute(
                text(
                    "SELECT automation_id FROM automation_webhook_rotations "
                    "WHERE id = 'rotation-legacy'"
                )
            ).scalar_one() == "automation-legacy"

        assert ("task_run_id", "report_id") in _unique_columns(
            inspector, "budget_usage_reports"
        )
        run_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in inspector.get_indexes("automation_runs")
        }
        assert run_indexes["ix_automation_runs_reconcile_order"] == (
            "automation_id",
            "completion_observed_at",
            "scheduled_for",
            "id",
            "outcome",
        )
        assert (
            "project_id",
            "created_by_user_id",
            "create_idempotency_key",
        ) in _unique_columns(inspector, "automations")
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("automations")
        }
        assert checks == {
            "ck_automations_create_idempotency_complete",
            "ck_automations_consecutive_failures",
            "ck_automations_failure_threshold",
            "ck_automations_webhook_rotation_number",
            "ck_automations_mutation_revision",
        }
        foreign_keys = {
            (
                foreign_key["referred_table"],
                tuple(foreign_key["constrained_columns"]),
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys("automations")
        }
        assert foreign_keys == {
            ("projects", ("project_id",), ("id",)),
            ("users", ("created_by_user_id",), ("id",)),
        }
        named_uniques = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("automations")
        }
        assert named_uniques["uq_automations_create_principal_key"] == (
            "project_id",
            "created_by_user_id",
            "create_idempotency_key",
        )
        assert "ix_automations_legacy_name" in {
            index["name"] for index in inspector.get_indexes("automations")
        }
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type = 'trigger' "
                    "AND name = 'trg_automations_legacy_insert'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM sqlite_master WHERE "
                    "type = 'index' AND name = 'ix_alerts_local_title'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                text(
                    "SELECT COUNT(*) FROM sqlite_master WHERE "
                    "type = 'trigger' AND name = 'trg_alerts_local_insert'"
                )
            ).scalar_one() == 1

        _assert_automation_insert_rejected(
            engine,
            id="automation-orphan-project",
            project_id="project-absent",
        )
        _assert_automation_insert_rejected(
            engine,
            id="automation-orphan-user",
            created_by_user_id="user-absent",
        )
        _assert_automation_insert_rejected(
            engine,
            id="automation-incomplete-key",
            created_by_user_id="user-1",
            create_idempotency_key="request-1",
        )
        _assert_automation_insert_rejected(
            engine,
            id="automation-negative-rotation",
            webhook_rotation_number=-1,
        )
        _assert_automation_insert_rejected(
            engine,
            id="automation-negative-failures",
            consecutive_failures=-1,
        )
        _assert_automation_insert_rejected(
            engine,
            id="automation-zero-threshold",
            failure_threshold=0,
        )
        _assert_sql_rejected(
            engine,
            "UPDATE workers SET project_id = 'project-1', global_access = 1 "
            "WHERE id = 'worker-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE automation_commands SET command = 'unknown' "
            "WHERE id = 'command-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE automation_runs SET trigger_kind = 'guess' "
            "WHERE id = 'run-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE budget_usage SET tokens_input = -1 "
            "WHERE id = 'usage-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE budget_usage SET cost = 1000000000000 "
            "WHERE id = 'usage-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE budget_usage SET cost_reported = 9 "
            "WHERE id = 'usage-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE alerts SET severity = 'urgent' "
            "WHERE id = 'alert-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE alerts SET task_id = 'task-absent' "
            "WHERE id = 'alert-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE notification_preferences SET enabled = NULL "
            "WHERE id = 'preferences-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE project_budget_policies SET timezone = '' "
            "WHERE id = 'policy-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE budget_usage_reports SET tokens_input = NULL "
            "WHERE id = 'report-legacy'",
        )
        _assert_sql_rejected(
            engine,
            "UPDATE budget_usage_reports SET cost = 1000000000000, "
            "currency = 'EUR' WHERE id = 'report-legacy'",
        )

        creation_key = {
            "created_by_user_id": "user-1",
            "create_idempotency_key": "request-duplicate",
            "create_request_fingerprint": "a" * 64,
        }
        with engine.begin() as connection:
            connection.execute(
                AUTOMATION_INSERT,
                _automation_values(id="automation-key-first", **creation_key),
            )
        _assert_automation_insert_rejected(
            engine,
            id="automation-key-second",
            **creation_key,
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO alerts ("
                    "id, created_at, project_id, kind, severity, title, detail, "
                    "acknowledgement_comment, dedupe_key, dedupe_key_active"
                    ") VALUES ("
                    "'alert-after-upgrade', '2026-01-02', 'project-1', "
                    "'storage.warning', 'warning', 'Après upgrade', '', '', "
                    "'storage:2', 'storage:2')"
                )
            )
        # L'index et le trigger spécifiques à l'installation ne sont pas perdus
        # par les deux reconstructions. Chaque trigger a vu une ligne avant et après.
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM automation_migration_audit")
            ).scalar_one() == 2
            assert connection.execute(
                text("SELECT COUNT(*) FROM alert_migration_audit")
            ).scalar_one() == 2

        # Un deuxième démarrage est sans effet sur les lignes et les index.
        engine_module.init_db()
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT COUNT(*) FROM budget_usage_reports")
            ).scalar() == 1
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_sqlite_automation_rebuild_refuses_invalid_data_atomically(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_invalid_partial.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        connection.execute(text('DROP TABLE "automations"'))
        connection.execute(text(PARTIAL_INVALID_AUTOMATIONS))
        _seed_automation_parent_scope(connection)
        connection.execute(
            text(
                "INSERT INTO automations ("
                "id, created_at, project_id, name, schedule_kind, "
                "schedule_expression, mission_template, consecutive_failures"
                ") VALUES ("
                "'automation-invalid', '2026-01-01', 'project-1', 'Routine', "
                "'cron', '0 9 * * *', '{}', -1"
                ")"
            )
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="compteur d'échecs négatif"):
            engine_module.init_db()

        engine = engine_module.get_engine()
        inspector = inspect(engine)
        columns = {
            column["name"] for column in inspector.get_columns("automations")
        }
        # BEGIN IMMEDIATE englobe aussi les ALTER antérieurs au préflight.
        assert "webhook_rotation_number" not in columns
        assert "failure_threshold" not in columns
        assert inspector.has_table("automations_lot_f_constraints_v2") is False
        assert inspector.get_check_constraints("automations") == []
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(
                text(
                    "SELECT consecutive_failures FROM automations "
                    "WHERE id = 'automation-invalid'"
                )
            ).scalar_one() == -1
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


@pytest.mark.parametrize(
    ("invalid_column", "invalid_value"),
    [("tokens_input", -1), ("cost", 1000000000000)],
)
def test_sqlite_lot_f_rebuild_refuses_invalid_cache_atomically(
    tmp_path, monkeypatch, invalid_column, invalid_value
):
    database = tmp_path / f"lot_f_invalid_cache_{invalid_column}.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        connection.execute(text('DROP TABLE "budget_usage"'))
        connection.execute(text(LEGACY_BUDGET_USAGE))
        _seed_automation_parent_scope(connection)
        connection.execute(
            text(
                "CREATE INDEX ix_budget_usage_local_currency "
                "ON budget_usage (currency)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE budget_usage_migration_audit ("
                "usage_id VARCHAR(36) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER trg_budget_usage_local_insert "
                "AFTER INSERT ON budget_usage BEGIN "
                "INSERT INTO budget_usage_migration_audit (usage_id) "
                "VALUES (NEW.id); END"
            )
        )
        connection.execute(
            text(
                "INSERT INTO budget_usage ("
                f"id, created_at, task_run_id, {invalid_column}) VALUES ("
                "'usage-invalid', '2026-01-01', 'task-run-1', :invalid_value)"
            ),
            {"invalid_value": invalid_value},
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="budget_usage.*données incompatibles"):
            engine_module.init_db()

        engine = engine_module.get_engine()
        inspector = inspect(engine)
        columns = {
            column["name"]: "".join(str(column["type"]).upper().split())
            for column in inspector.get_columns("budget_usage")
        }
        assert columns["cost"] == "FLOAT"
        assert "cost_reported" not in columns
        assert inspector.has_table("budget_usage_lot_f_model_parity_v3") is False
        with engine.connect() as connection:
            objects = {
                (row.type, row.name)
                for row in connection.execute(
                    text(
                        "SELECT type, name FROM sqlite_master WHERE name IN ("
                        "'ix_budget_usage_local_currency', "
                        "'trg_budget_usage_local_insert')"
                    )
                )
            }
        assert objects == {
            ("index", "ix_budget_usage_local_currency"),
            ("trigger", "trg_budget_usage_local_insert"),
        }
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(
                text(
                    f"SELECT {invalid_column} FROM budget_usage "
                    "WHERE id = 'usage-invalid'"
                )
            ).scalar_one() == invalid_value
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


@pytest.mark.parametrize(
    ("cost", "currency", "expected_error"),
    [
        (None, None, "sans mesure=1, paire coût/devise=0"),
        (1.25, None, "sans mesure=0, paire coût/devise=1"),
        (1000000000000, "EUR", "budget_usage_reports.*données incompatibles"),
    ],
)
def test_sqlite_ledger_backfill_refuses_dishonest_rows_atomically(
    tmp_path, monkeypatch, cost, currency, expected_error
):
    database = tmp_path / f"lot_f_invalid_ledger_{cost is None}.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        connection.execute(text('DROP TABLE "budget_usage_reports"'))
        connection.execute(text(LEGACY_LEDGER_WITHOUT_KIND))
        _seed_automation_parent_scope(connection)
        connection.execute(
            text(
                "INSERT INTO budget_usage_reports ("
                "id, created_at, task_run_id, report_id, project_id, provider, "
                "source, phase, cost, currency, occurred_at) VALUES ("
                "'report-invalid', '2026-01-01', 'task-run-1', 'report-1', "
                "'project-1', 'openai', 'provider', 'execution', :cost, "
                ":currency, '2026-01-01')"
            ),
            {"cost": cost, "currency": currency},
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=expected_error):
            engine_module.init_db()
        engine = engine_module.get_engine()
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("budget_usage_reports")
        }
        assert "permit_id" not in columns
        assert inspect(engine).has_table(
            "budget_usage_reports_lot_f_model_parity_v3"
        ) is False
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_sqlite_lot_f_rebuild_refuses_incompatible_local_unique(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_local_unique.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX uq_alerts_local_title ON alerts (title)")
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="alerts.*UNIQUE"):
            engine_module.init_db()
        engine = engine_module.get_engine()
        assert "uq_alerts_local_title" in {
            index["name"] for index in inspect(engine).get_indexes("alerts")
        }
        assert inspect(engine).has_table("alerts_lot_f_model_parity_v3") is False
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_sqlite_partial_unique_never_satisfies_model_uniqueness(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_partial_unique.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        connection.execute(text('DROP TABLE "scheduler_leases"'))
        connection.execute(text(LEGACY_SCHEDULER_LEASES))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_scheduler_leases_key "
                "ON scheduler_leases (scheduler_key) "
                "WHERE owner_worker_id IS NOT NULL"
            )
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="scheduler_leases.*UNIQUE"):
            engine_module.init_db()
        engine = engine_module.get_engine()
        partial = next(
            index
            for index in inspect(engine).get_indexes("scheduler_leases")
            if index["name"] == "uq_scheduler_leases_key"
        )
        assert "sqlite_where" in (partial.get("dialect_options") or {})
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def _replace_table_ddl(connection, table_name: str, old: str, new: str) -> None:
    ddl = connection.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = :table_name"
        ),
        {"table_name": table_name},
    ).scalar_one()
    indexes = connection.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = :table_name "
            "AND sql IS NOT NULL ORDER BY name"
        ),
        {"table_name": table_name},
    ).scalars().all()
    replacement = ddl.replace(old, new, 1)
    assert replacement != ddl
    connection.execute(text(f'DROP TABLE "{table_name}"'))
    connection.exec_driver_sql(replacement)
    for statement in indexes:
        connection.exec_driver_sql(statement)


def test_sqlite_automation_partial_unique_is_rebuilt_as_total(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_automation_partial_unique.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    unique_ddl = (
        "CONSTRAINT uq_automations_create_principal_key UNIQUE "
        "(project_id, created_by_user_id, create_idempotency_key), "
    )
    with bootstrap.begin() as connection:
        _replace_table_ddl(connection, "automations", unique_ddl, "")
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_automations_create_principal_key "
                "ON automations (project_id, created_by_user_id, "
                "create_idempotency_key) WHERE name = 'covered'"
            )
        )
        _seed_automation_parent_scope(connection)
        connection.execute(
            AUTOMATION_INSERT,
            _automation_values(
                id="automation-partial",
                created_by_user_id="user-1",
                create_idempotency_key="request-partial",
                create_request_fingerprint="a" * 64,
            ),
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        total = next(
            constraint
            for constraint in inspect(engine).get_unique_constraints("automations")
            if tuple(constraint.get("column_names") or ())
            == (
                "project_id",
                "created_by_user_id",
                "create_idempotency_key",
            )
        )
        assert total["name"] == "uq_automations_create_principal_key"
        assert _connection_count(engine, "automations", "automation-partial") == 1
        _assert_automation_insert_rejected(
            engine,
            id="automation-duplicate-after-rebuild",
            created_by_user_id="user-1",
            create_idempotency_key="request-partial",
            create_request_fingerprint="a" * 64,
        )
        engine_module.init_db()
        assert _connection_count(engine, "automations", "automation-partial") == 1
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def _connection_count(engine, table_name: str, row_id: str) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}" WHERE id = :row_id'),
            {"row_id": row_id},
        ).scalar_one()


def test_sqlite_wrong_server_defaults_are_rebuilt_without_rewriting_rows(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_wrong_defaults.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        _replace_table_ddl(
            connection,
            "automations",
            "enabled INTEGER DEFAULT '0' NOT NULL",
            "enabled INTEGER DEFAULT '1' NOT NULL",
        )
        _replace_table_ddl(
            connection,
            "scheduler_leases",
            "fencing_token INTEGER DEFAULT '0' NOT NULL",
            "fencing_token INTEGER DEFAULT '7' NOT NULL",
        )
        _seed_automation_parent_scope(connection)
        connection.execute(
            text(
                "INSERT INTO automations ("
                "id, created_at, project_id, name, description, schedule_kind, "
                "schedule_expression, mission_template) VALUES ("
                "'automation-old-default', '2026-01-01', 'project-1', "
                "'Routine', '', 'cron', '0 9 * * *', '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO scheduler_leases (id, created_at, scheduler_key) "
                "VALUES ('lease-old-default', '2026-01-01', 'scheduler-old')"
            )
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        defaults = {
            (table_name, column["name"]): column.get("default")
            for table_name in ("automations", "scheduler_leases")
            for column in inspect(engine).get_columns(table_name)
        }
        assert defaults[("automations", "enabled")] == "'0'"
        assert defaults[("scheduler_leases", "fencing_token")] == "'0'"
        with engine.begin() as connection:
            assert connection.execute(
                text(
                    "SELECT enabled FROM automations "
                    "WHERE id = 'automation-old-default'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                text(
                    "SELECT fencing_token FROM scheduler_leases "
                    "WHERE id = 'lease-old-default'"
                )
            ).scalar_one() == 7
            connection.execute(
                text(
                    "INSERT INTO automations ("
                    "id, created_at, project_id, name, description, schedule_kind, "
                    "schedule_expression, mission_template) VALUES ("
                    "'automation-new-default', '2026-01-02', 'project-1', "
                    "'Routine 2', '', 'cron', '0 10 * * *', '{}')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO scheduler_leases "
                    "(id, created_at, scheduler_key) VALUES "
                    "('lease-new-default', '2026-01-02', 'scheduler-new')"
                )
            )
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT enabled FROM automations "
                    "WHERE id = 'automation-new-default'"
                )
            ).scalar_one() == 0
            assert connection.execute(
                text(
                    "SELECT fencing_token FROM scheduler_leases "
                    "WHERE id = 'lease-new-default'"
                )
            ).scalar_one() == 0
        engine_module.init_db()
        assert _connection_count(engine, "automations", "automation-old-default") == 1
        assert _connection_count(engine, "scheduler_leases", "lease-old-default") == 1
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


@pytest.mark.parametrize("mode", ["missing", "unknown"])
def test_sqlite_lot_f_rebuild_refuses_non_addable_column_drift(
    tmp_path, monkeypatch, mode
):
    database = tmp_path / f"lot_f_column_drift_{mode}.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as connection:
        if mode == "missing":
            connection.execute(text('DROP TABLE "scheduler_leases"'))
            connection.execute(
                text(
                    "CREATE TABLE scheduler_leases ("
                    "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                    "created_at DATETIME NOT NULL, "
                    "owner_worker_id VARCHAR(36), holder_id VARCHAR(64), "
                    "fencing_token INTEGER NOT NULL DEFAULT 0, "
                    "lease_expires_at DATETIME, last_renewed_at DATETIME, "
                    "released_at DATETIME)"
                )
            )
        else:
            connection.execute(
                text(
                    "ALTER TABLE scheduler_leases "
                    "ADD COLUMN tenant_hint TEXT"
                )
            )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="colonnes incompatibles"):
            engine_module.init_db()
        engine = engine_module.get_engine()
        columns = {
            column["name"]
            for column in inspect(engine).get_columns("scheduler_leases")
        }
        assert ("scheduler_key" not in columns) if mode == "missing" else (
            "tenant_hint" in columns
        )
        assert inspect(engine).has_table(
            "scheduler_leases_lot_f_model_parity_v3"
        ) is False
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()
