"""Modèles du Lot F : automatisations, déclenchements, consommation et alertes.

Trois garanties de ce lot ne sont pas des vérifications en mémoire mais des
contraintes de base de données, et c'est tout l'intérêt de ce fichier :

- ``(automation_id, fire_key)`` est unique : deux planificateurs concurrents qui
  matérialisent la **même** occurrence nominale ne peuvent pas créer deux missions,
  la base en refuse un ;
- ``budget_usage.task_run_id`` est unique : une tentative n'a qu'un seul cache
  saturé sous verrou, dérivé du ledger immuable sans écraser un rapport concurrent ;
- ``(project_id, dedupe_key_active)`` est unique : une même cause ne produit jamais
  deux alertes **ouvertes**, mais peut en recréer une après acquittement, puisque
  ``NULL`` n'entre pas en conflit avec ``NULL`` dans un index unique SQL.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import BigInteger, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from acp_contracts.schedule import fire_key, next_occurrence
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
    OrganizationModel,
    ProjectModel,
    WorkspaceModel,
)

LOT_F_TABLES = {
    "automations",
    "automation_commands",
    "automation_runs",
    "budget_usage",
    "alerts",
}

LEGACY_EVENT_ID = "evenement-anterieur-au-lot-f"
"""Ligne écrite **avant** la montée de schéma ; elle doit survivre intacte."""


def test_budget_counters_compile_to_postgresql_bigint() -> None:
    dialect = postgresql.dialect()
    for model in (BudgetUsageModel, BudgetUsageReportModel):
        for name in ("tokens_input", "tokens_output", "tool_calls"):
            column_type = model.__table__.c[name].type
            assert isinstance(column_type, BigInteger)
            assert column_type.compile(dialect=dialect) == "BIGINT"

LEGACY_EVENTS_TABLE = """
CREATE TABLE events (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    type VARCHAR(100) NOT NULL,
    occurred_at DATETIME NOT NULL,
    organization_id VARCHAR(36),
    workspace_id VARCHAR(36),
    department_id VARCHAR(36),
    project_id VARCHAR(36),
    team_id VARCHAR(36),
    agent_instance_id VARCHAR(36),
    task_id VARCHAR(36),
    task_run_id VARCHAR(36),
    payload JSON
)
"""

LEGACY_AUTOMATION_RUNS_TABLE = """
CREATE TABLE automation_runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    automation_id VARCHAR(36) NOT NULL,
    fire_key VARCHAR(64) NOT NULL,
    scheduled_for DATETIME NOT NULL,
    fired_at DATETIME NOT NULL,
    task_id VARCHAR(36),
    outcome VARCHAR(30) NOT NULL,
    detail VARCHAR(500) NOT NULL DEFAULT ''
)
"""


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


@pytest.fixture
def inspector(engine):
    return inspect(engine)


def _index_names(connection, table: str) -> set[str]:
    rows = connection.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :table"),
        {"table": table},
    ).all()
    return {row[0] for row in rows}


def _unique_column_sets(inspector, table: str) -> set[tuple[str, ...]]:
    """Unicités déclarées, qu'elles viennent d'une contrainte ou d'un index unique."""

    declared = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }
    declared |= {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    return declared


def _automation(**overrides) -> AutomationModel:
    payload = {
        "project_id": "projet-1",
        "name": "Revue quotidienne",
        "schedule_kind": "cron",
        "schedule_expression": "30 2 * * *",
        "mission_template": {"title": "Revue"},
    }
    payload.update(overrides)
    return AutomationModel(**payload)


def _automation_run(**overrides) -> AutomationRunModel:
    payload = {
        "automation_id": "automatisation-1",
        "fire_key": "cle-de-tir-1",
        "scheduled_for": datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc),
        "fired_at": datetime(2026, 3, 29, 1, 30, 12, tzinfo=timezone.utc),
        "outcome": "launched",
    }
    payload.update(overrides)
    return AutomationRunModel(**payload)


def _budget_usage(**overrides) -> BudgetUsageModel:
    payload = {"task_run_id": "tentative-1"}
    payload.update(overrides)
    return BudgetUsageModel(**payload)


def _alert(**overrides) -> AlertModel:
    payload = {
        "project_id": "projet-1",
        "kind": "budget.exceeded",
        "severity": "critical",
        "title": "Budget dépassé",
        "dedupe_key": "budget:mission-1",
        "dedupe_key_active": "budget:mission-1",
    }
    payload.update(overrides)
    return AlertModel(**payload)


# --- existence des tables et des colonnes -------------------------------------


def test_create_all_creates_the_four_lot_f_tables(inspector):
    assert LOT_F_TABLES <= set(inspector.get_table_names())


def test_models_map_to_the_expected_tables():
    assert AutomationModel.__tablename__ == "automations"
    assert AutomationCommandModel.__tablename__ == "automation_commands"
    assert AutomationRunModel.__tablename__ == "automation_runs"
    assert BudgetUsageModel.__tablename__ == "budget_usage"
    assert AlertModel.__tablename__ == "alerts"


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        (
            "automations",
            {
                "project_id",
                "name",
                "description",
                "schedule_kind",
                "schedule_expression",
                "timezone",
                "mission_template",
                "enabled",
                "catchup_policy",
                "max_concurrent_runs",
                "next_run_at",
                "last_fire_key",
                "created_by_user_id",
                "create_idempotency_key",
                "create_request_fingerprint",
                "webhook_rotation_number",
                "created_at",
            },
        ),
        (
            "automation_runs",
            {
                "automation_id",
                "fire_key",
                "scheduled_for",
                "fired_at",
                "task_id",
                "outcome",
                "detail",
                "created_at",
            },
        ),
        (
            "budget_usage",
            {
                "task_run_id",
                "cost",
                "currency",
                "tokens_input",
                "tokens_output",
                "tool_calls",
                "usage_reported",
                "updated_at",
                "created_at",
            },
        ),
        (
            "alerts",
            {
                "project_id",
                "kind",
                "severity",
                "title",
                "detail",
                "task_id",
                "automation_id",
                "acknowledged_at",
                "acknowledged_by_user_id",
                "dedupe_key",
                "dedupe_key_active",
                "created_at",
            },
        ),
    ],
)
def test_expected_columns_exist(inspector, table: str, columns: set[str]):
    existing = {column["name"] for column in inspector.get_columns(table)}
    assert columns <= existing, columns - existing


def test_scheduled_for_and_fired_at_stay_two_distinct_columns(inspector):
    """L'instant nominal identifie l'occurrence ; l'instant réel dit ce qui s'est passé.

    Les confondre rendrait la clé d'unicité inutile : deux exécutions réelles n'ont
    jamais exactement le même instant.
    """

    columns = {
        column["name"]: column for column in inspector.get_columns("automation_runs")
    }
    assert {"scheduled_for", "fired_at"} <= set(columns)
    assert columns["scheduled_for"]["nullable"] is False
    assert columns["fired_at"]["nullable"] is False


def test_foreign_keys_target_existing_tables(inspector):
    automation_fks = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("automations")
    }
    assert ("projects", ("project_id",)) in automation_fks
    assert ("users", ("created_by_user_id",)) in automation_fks

    run_fks = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("automation_runs")
    }
    assert ("automations", ("automation_id",)) in run_fks
    assert ("tasks", ("task_id",)) in run_fks

    assert ("task_runs", ("task_run_id",)) in {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("budget_usage")
    }

    alert_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("alerts")}
    assert {"projects", "tasks", "automations", "users"} <= alert_fks


# --- index ---------------------------------------------------------------------


def test_next_run_at_is_indexed(engine):
    """Le planificateur ne pose qu'une question à chaque examen : « qui est dû ? ».

    Sans index, cette question coûte une lecture complète de la table toutes les
    trente secondes.
    """

    with engine.connect() as connection:
        assert "ix_automations_next_run_at" in _index_names(connection, "automations")


def test_scoping_columns_are_indexed(engine):
    with engine.connect() as connection:
        automations = _index_names(connection, "automations")
        assert {
            "ix_automations_project_id",
            "ix_automations_created_by_user_id",
        } <= automations
        assert "ix_automation_runs_automation_id" in _index_names(
            connection, "automation_runs"
        )
        alerts = _index_names(connection, "alerts")
        assert {"ix_alerts_project_id", "ix_alerts_kind"} <= alerts


# --- valeurs par défaut --------------------------------------------------------


def test_an_automation_is_born_disabled(engine):
    """Une automatisation ne se déclenche jamais du seul fait d'avoir été créée."""

    with Session(engine) as db:
        automation = _automation()
        db.add(automation)
        db.commit()
        db.refresh(automation)
        assert automation.enabled == 0


def test_timezone_defaults_to_europe_paris(engine):
    with Session(engine) as db:
        automation = _automation()
        db.add(automation)
        db.commit()
        db.refresh(automation)
        assert automation.timezone == "Europe/Paris"


def test_automation_scheduling_defaults(engine):
    with Session(engine) as db:
        automation = _automation()
        db.add(automation)
        db.commit()
        db.refresh(automation)
        assert automation.description == ""
        assert automation.catchup_policy == "skip"
        assert automation.max_concurrent_runs == 1
        assert automation.next_run_at is None
        assert automation.last_fire_key is None


def test_automation_run_round_trips(engine):
    with Session(engine) as db:
        run = _automation_run(detail="", task_id="mission-1")
        db.add(run)
        db.commit()
        stored = db.query(AutomationRunModel).one()
        assert stored.outcome == "launched"
        assert stored.task_id == "mission-1"
        assert stored.detail == ""
        assert stored.scheduled_for != stored.fired_at


def test_budget_usage_defaults_to_unreported_zero(engine):
    """``usage_reported`` sépare « zéro jeton rapporté » de « rien n'a été rapporté »."""

    with Session(engine) as db:
        usage = _budget_usage()
        db.add(usage)
        db.commit()
        db.refresh(usage)
        assert usage.cost == 0.0
        assert usage.currency == "EUR"
        assert usage.tokens_input == 0
        assert usage.tokens_output == 0
        assert usage.tool_calls == 0
        assert usage.usage_reported == 0
        assert usage.updated_at is not None


def test_alert_round_trips(engine):
    with Session(engine) as db:
        alert = _alert()
        db.add(alert)
        db.commit()
        stored = db.query(AlertModel).one()
        assert stored.severity == "critical"
        assert stored.detail == ""
        assert stored.acknowledged_at is None
        assert stored.dedupe_key_active == stored.dedupe_key


# --- unicité (automation_id, fire_key) ----------------------------------------


def test_fire_key_uniqueness_is_declared(inspector):
    assert ("automation_id", "fire_key") in _unique_column_sets(
        inspector, "automation_runs"
    )


def test_automation_creation_idempotency_is_declared(inspector):
    assert (
        "project_id",
        "created_by_user_id",
        "create_idempotency_key",
    ) in _unique_column_sets(inspector, "automations")


def test_same_creation_key_is_scoped_by_project_and_principal(engine):
    common = {
        "create_idempotency_key": "create-1",
        "create_request_fingerprint": "a" * 64,
    }
    with Session(engine) as db:
        db.add(
            _automation(
                project_id="project-1", created_by_user_id="user-1", **common
            )
        )
        db.commit()
        db.add(
            _automation(
                project_id="project-1", created_by_user_id="user-1", **common
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(
            _automation(
                project_id="project-2", created_by_user_id="user-1", **common
            )
        )
        db.add(
            _automation(
                project_id="project-1", created_by_user_id="user-2", **common
            )
        )
        db.commit()


def test_webhook_rotation_journal_is_uniquely_ordered_and_scoped(inspector):
    assert (
        "automation_id",
        "principal_id",
        "idempotency_key",
    ) in _unique_column_sets(inspector, "automation_webhook_rotations")
    assert ("automation_id", "rotation_number") in _unique_column_sets(
        inspector, "automation_webhook_rotations"
    )
    assert AutomationWebhookRotationModel.__tablename__ == (
        "automation_webhook_rotations"
    )


def test_the_same_occurrence_cannot_be_materialised_twice(engine):
    """Deux planificateurs sur le même instant nominal : la base en refuse un."""

    with Session(engine) as db:
        db.add(_automation_run())
        db.commit()
        db.add(
            _automation_run(
                fired_at=datetime(2026, 3, 29, 1, 30, 45, tzinfo=timezone.utc)
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_two_automations_may_share_a_fire_key(engine):
    with Session(engine) as db:
        db.add(_automation_run(automation_id="automatisation-1"))
        db.add(_automation_run(automation_id="automatisation-2"))
        db.commit()
        assert db.query(AutomationRunModel).count() == 2


# --- unicité et incrément du compteur de consommation --------------------------


def test_budget_usage_is_unique_per_attempt(engine):
    with Session(engine) as db:
        db.add(_budget_usage())
        db.commit()
        db.add(_budget_usage())
        with pytest.raises(IntegrityError):
            db.commit()


def test_tool_calls_increment_atomically(engine):
    """Deux incréments SQL successifs donnent 2 : aucun rapport n'en écrase un autre."""

    with Session(engine) as db:
        db.add(_budget_usage())
        db.commit()
        for _ in range(2):
            db.execute(
                text(
                    "UPDATE budget_usage SET tool_calls = tool_calls + 1 "
                    "WHERE task_run_id = :task_run_id"
                ),
                {"task_run_id": "tentative-1"},
            )
        db.commit()
        total = db.execute(
            text("SELECT tool_calls FROM budget_usage WHERE task_run_id = :task_run_id"),
            {"task_run_id": "tentative-1"},
        ).scalar()
        assert total == 2


# --- déduplication des alertes -------------------------------------------------


def test_alert_dedupe_uniqueness_is_declared(inspector):
    assert ("project_id", "dedupe_key_active") in _unique_column_sets(inspector, "alerts")


def test_two_open_alerts_of_the_same_cause_are_refused(engine):
    with Session(engine) as db:
        db.add(_alert())
        db.commit()
        db.add(_alert(title="Budget dépassé (bis)"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_an_acknowledged_alert_frees_its_cause(engine):
    """``NULL`` n'entre pas en conflit avec ``NULL`` : l'alerte peut renaître."""

    with Session(engine) as db:
        first = _alert()
        db.add(first)
        db.commit()
        first.acknowledged_at = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)
        first.acknowledged_by_user_id = "utilisateur-1"
        first.dedupe_key_active = None
        db.commit()
        db.add(_alert())
        db.commit()
        assert db.query(AlertModel).count() == 2
        assert (
            db.query(AlertModel).filter(AlertModel.dedupe_key_active.isnot(None)).count()
            == 1
        )


def test_several_acknowledged_alerts_of_the_same_cause_coexist(engine):
    with Session(engine) as db:
        for _ in range(3):
            db.add(
                _alert(
                    dedupe_key_active=None,
                    acknowledged_at=datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc),
                )
            )
        db.commit()
        assert db.query(AlertModel).count() == 3


def test_two_projects_may_raise_the_same_cause(engine):
    with Session(engine) as db:
        db.add(_alert(project_id="projet-1"))
        db.add(_alert(project_id="projet-2"))
        db.commit()
        assert db.query(AlertModel).count() == 2


def test_application_sqlite_engine_enforces_foreign_keys(tmp_path, monkeypatch):
    database = tmp_path / "foreign_keys.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    engine = engine_module.get_engine()
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        with Session(engine) as db:
            db.add(
                NotificationPreferencesModel(
                    project_id="missing-project",
                    user_id="missing-user",
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
    finally:
        engine.dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


# --- montée de schéma d'une base antérieure au lot ----------------------------


@pytest.fixture
def legacy_database(tmp_path, monkeypatch):
    database = tmp_path / "lot_f.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    bootstrap = create_engine(f"sqlite:///{database.as_posix()}")
    with bootstrap.begin() as connection:
        connection.execute(text(LEGACY_EVENTS_TABLE))
        connection.execute(
            text(
                "INSERT INTO events (id, created_at, type, occurred_at, payload) "
                "VALUES (:event_id, '2026-01-01 00:00:00', 'task.started', "
                "'2026-01-01 00:00:00', '{}')"
            ),
            {"event_id": LEGACY_EVENT_ID},
        )
    bootstrap.dispose()
    try:
        yield database
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_init_db_upgrades_an_existing_database_without_losing_a_row(legacy_database):
    engine_module.init_db()
    engine = engine_module.get_engine()
    inspector = inspect(engine)
    assert LOT_F_TABLES <= set(inspector.get_table_names())
    with engine.connect() as connection:
        surviving = connection.execute(
            text("SELECT id FROM events WHERE id = :event_id"),
            {"event_id": LEGACY_EVENT_ID},
        ).scalar()
        assert surviving == LEGACY_EVENT_ID

    # Deuxième passage sur la même base : aucune erreur, mêmes objets, même ligne.
    engine_module.init_db()
    engine_module._upgrade_sqlite_schema(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM events")).scalar() == 1
        assert "ix_automations_next_run_at" in _index_names(connection, "automations")
    assert ("automation_id", "fire_key") in _unique_column_sets(
        inspect(engine), "automation_runs"
    )
    assert ("project_id", "dedupe_key_active") in _unique_column_sets(
        inspect(engine), "alerts"
    )


def test_upgrade_repairs_a_table_created_without_its_uniqueness(tmp_path, monkeypatch):
    """Une table présente mais sans sa contrainte n'est pas complétée par ``create_all``.

    La montée doit donc reposer l'unicité elle-même, sinon la garantie d'absence de
    doublon manquerait silencieusement sur une base à moitié créée.
    """

    database = tmp_path / "lot_f_partiel.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    bootstrap = create_engine(f"sqlite:///{database.as_posix()}")
    with bootstrap.begin() as connection:
        connection.execute(text(LEGACY_AUTOMATION_RUNS_TABLE))
    bootstrap.dispose()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        assert ("automation_id", "fire_key") in _unique_column_sets(
            inspect(engine), "automation_runs"
        )
        with Session(engine) as db:
            db.add(
                OrganizationModel(
                    id="organisation-1",
                    name="Organisation",
                )
            )
            db.flush()
            db.add(
                WorkspaceModel(
                    id="espace-1",
                    organization_id="organisation-1",
                    name="Espace",
                )
            )
            db.flush()
            db.add(
                ProjectModel(
                    id="projet-1",
                    workspace_id="espace-1",
                    name="Projet",
                )
            )
            db.flush()
            db.add(_automation(id="automatisation-1"))
            db.commit()
            db.add(_automation_run())
            db.commit()
            db.add(_automation_run())
            with pytest.raises(IntegrityError):
                db.commit()
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


# --- Frontière de stockage : l'instant doit survivre à l'aller-retour ----------


def test_an_aware_non_utc_instant_survives_the_round_trip(engine):
    """SQLite ne stocke pas le décalage : il doit être normalisé avant l'écriture.

    C'est la garantie anti-doublon du lot qui en dépend. Si un appelant écrit
    ``scheduled_for`` dans le fuseau de l'utilisateur, SQLite retient l'heure murale
    — 02:30 — et perd le ``+01:00``. Relire cette ligne pour en redériver la clé de
    tir donnerait alors une clé différente de celle qui est stockée, et la contrainte
    d'unicité ``(automation_id, fire_key)`` cesserait de refuser le doublon de cette
    occurrence : deux planificateurs concurrents créeraient deux missions.
    """

    paris = ZoneInfo("Europe/Paris")
    instant_utc = datetime(2026, 1, 16, 1, 30, tzinfo=timezone.utc)
    instant_paris = instant_utc.astimezone(paris)
    assert instant_paris == instant_utc
    assert instant_paris.hour == 2

    with Session(engine) as db:
        db.add(_automation_run(id="tir-1", scheduled_for=instant_paris))
        db.commit()
        stored = db.get(AutomationRunModel, "tir-1").scheduled_for

    assert stored.tzinfo is not None, "l'instant relu doit rester conscient du fuseau"
    assert stored == instant_utc, "l'instant relu doit désigner le même point du temps"
    assert fire_key("automatisation-1", stored) == fire_key(
        "automatisation-1", instant_paris
    )


def test_a_naive_instant_is_refused_rather_than_guessed(engine):
    """Un ``datetime`` naïf n'a pas d'instant : le supposer UTC inventerait une donnée."""

    with Session(engine) as db:
        db.add(_automation_run(id="tir-2", scheduled_for=datetime(2026, 1, 16, 2, 30)))
        with pytest.raises((StatementError, ValueError)):
            db.commit()


def test_next_run_at_read_back_can_feed_the_scheduler_loop(engine):
    """La boucle naturelle du planificateur relit ``next_run_at`` et le réinjecte."""

    computed = next_occurrence(
        "30 2 * * *", datetime(2026, 1, 15, 12, tzinfo=timezone.utc), "Europe/Paris"
    )
    with Session(engine) as db:
        db.add(_automation(id="automatisation-9", next_run_at=computed))
        db.commit()
        stored = db.get(AutomationModel, "automatisation-9").next_run_at

    assert stored == computed
    assert next_occurrence("30 2 * * *", stored, "Europe/Paris") > stored
