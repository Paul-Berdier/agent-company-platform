"""Garanties de stockage ajoutées pour le service complet du Lot F."""

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
    AutomationModel,
    AutomationRunModel,
    Base,
    BudgetUsageModel,
    BudgetUsageReportModel,
    NotificationPreferencesModel,
    ProjectBudgetPolicyModel,
)


NEW_TABLES = {
    "notification_preferences",
    "project_budget_policies",
    "budget_usage_reports",
}


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
        "project_id": "project-1",
        "provider": "openai",
        "source": "provider",
        "phase": "execution",
        "tokens_input": 0,
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


def test_create_all_exposes_the_extended_schema(engine):
    inspector = inspect(engine)
    assert NEW_TABLES <= set(inspector.get_table_names())

    automation = {column["name"] for column in inspector.get_columns("automations")}
    assert {
        "webhook_enabled",
        "webhook_secret_hash",
        "webhook_rotated_at",
    } <= automation

    runs = {column["name"] for column in inspector.get_columns("automation_runs")}
    assert "trigger_kind" in runs

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
        assert report.permit_id is None
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


def test_sqlite_upgrade_is_additive_idempotent_and_backfills_defaults(
    tmp_path, monkeypatch
):
    database = tmp_path / "lot_f_extensions_legacy.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = create_engine(url)
    with bootstrap.begin() as connection:
        for ddl in (
            LEGACY_AUTOMATIONS,
            LEGACY_RUNS,
            LEGACY_BUDGET_USAGE,
            LEGACY_ALERTS,
            LEGACY_LEDGER_WITHOUT_KIND,
        ):
            connection.execute(text(ddl))
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
                "INSERT INTO automation_runs "
                "(id, created_at, automation_id, fire_key, scheduled_for, "
                "fired_at, outcome) VALUES "
                "('run-legacy', '2026-01-01', 'automation-legacy', 'fire-1', "
                "'2026-01-01', '2026-01-01', 'launched')"
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
                "INSERT INTO budget_usage_reports "
                "(id, created_at, task_run_id, report_id, project_id, provider, "
                "source, phase, tokens_input, occurred_at) VALUES "
                "('report-legacy', '2026-01-01', 'task-run-1', 'report-1', "
                "'project-1', 'openai', 'provider', 'execution', 12, '2026-01-01')"
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

        with engine.connect() as connection:
            automation = connection.execute(
                text(
                    "SELECT webhook_enabled, webhook_secret_hash, webhook_rotated_at "
                    "FROM automations WHERE id = 'automation-legacy'"
                )
            ).one()
            assert tuple(automation) == (0, None, None)
            assert connection.execute(
                text(
                    "SELECT trigger_kind FROM automation_runs "
                    "WHERE id = 'run-legacy'"
                )
            ).scalar() == "schedule"
            cache = connection.execute(
                text(
                    "SELECT cost_reported, tokens_input_reported, "
                    "tokens_output_reported, tool_calls_reported "
                    "FROM budget_usage WHERE id = 'usage-legacy'"
                )
            ).one()
            assert tuple(cache) == (0, 0, 0, 0)
            assert connection.execute(
                text(
                    "SELECT acknowledgement_comment FROM alerts "
                    "WHERE id = 'alert-legacy'"
                )
            ).scalar() == ""
            assert connection.execute(
                text(
                    "SELECT kind, permit_id, allowed, reconciled_at "
                    "FROM budget_usage_reports WHERE id = 'report-legacy'"
                )
            ).one() == ("usage", None, 1, None)

        assert ("task_run_id", "report_id") in _unique_columns(
            inspector, "budget_usage_reports"
        )

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
