"""Modèles du Lot E : colonnes ajoutées, nouvelles tables et unicité de séquence.

La séquence par run est le curseur de reprise du flux : deux événements d'une même
tentative ne peuvent pas la partager, sinon une reconnexion sauterait ou dupliquerait
un événement. Les lignes historiques (sans run ni séquence) restent acceptées, d'où
un index unique **partiel**.

``journal_seq`` est le second compteur, à l'échelle du journal entier : il donne à la
portée projet un **ordre total**, que l'horloge de la machine soit fine ou non. La
migration le remplit pour les lignes antérieures, dans leur ordre d'insertion.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from acp_api.streams import read_project_page
from acp_database import engine as engine_module
from acp_database.models import (
    ArtifactLinkModel,
    Base,
    EventModel,
    TestCaseModel,
    TestRunModel,
)

LOT_E_TABLES = {"test_runs", "test_cases", "artifact_links"}

LEGACY_PROJECT_ID = "projet-historique"
"""Projet des lignes d'événements écrites **avant** le compteur de journal."""

LEGACY_PROJECT_EVENT_IDS = ("legacy-c", "legacy-b", "legacy-a")
"""Ordre d'insertion des lignes historiques, volontairement inverse de l'ordre des identifiants."""

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

LEGACY_ARTIFACTS_TABLE = """
CREATE TABLE artifacts (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    task_run_id VARCHAR(36) NOT NULL,
    worker_id VARCHAR(36) NOT NULL,
    kind VARCHAR(100) NOT NULL,
    path VARCHAR(1000) NOT NULL,
    checksum VARCHAR(200),
    size_bytes INTEGER,
    metadata JSON
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


def _index_sql(connection, name: str) -> str:
    row = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = :name"),
        {"name": name},
    ).first()
    return (row[0] or "") if row else ""


def _event(**overrides) -> EventModel:
    payload = {
        "type": "task.started",
        "occurred_at": datetime(2026, 9, 12, tzinfo=timezone.utc),
        "payload": {},
    }
    payload.update(overrides)
    return EventModel(**payload)


# --- colonnes ajoutées --------------------------------------------------------


def test_events_gains_the_stream_columns(inspector):
    columns = {column["name"]: column for column in inspector.get_columns("events")}
    assert {
        "schema_version",
        "sequence",
        "conversation_id",
        "step_id",
        "executor",
        "emitted_by",
    } <= set(columns)
    assert columns["schema_version"]["nullable"] is False
    assert columns["sequence"]["nullable"] is True


def test_events_gains_the_journal_sequence_column(inspector):
    """``journal_seq`` existe et reste nullable pour les lignes historiques."""

    columns = {column["name"]: column for column in inspector.get_columns("events")}
    assert "journal_seq" in columns
    assert columns["journal_seq"]["nullable"] is True


def test_artifacts_gains_the_content_columns(inspector):
    columns = {column["name"]: column for column in inspector.get_columns("artifacts")}
    assert {
        "storage_key",
        "content_type",
        "original_name",
        "source",
        "stream_kind",
        "deleted_at",
    } <= set(columns)
    assert columns["storage_key"]["nullable"] is True
    assert columns["content_type"]["nullable"] is False
    assert columns["deleted_at"]["nullable"] is True


def test_artifact_storage_key_is_indexed(engine):
    with engine.connect() as connection:
        assert "ix_artifacts_storage_key" in _index_names(connection, "artifacts")


def test_event_sequence_indexes_exist(engine):
    with engine.connect() as connection:
        names = _index_names(connection, "events")
        assert {"uq_event_run_sequence", "ix_events_task_run_sequence"} <= names
        sql = _index_sql(connection, "uq_event_run_sequence")
        assert "UNIQUE" in sql.upper()
        assert "task_run_id IS NOT NULL" in sql
        assert "sequence IS NOT NULL" in sql


def test_event_journal_sequence_indexes_exist(engine):
    """Le compteur de journal est indexé, et son unicité est partielle comme la séquence."""

    with engine.connect() as connection:
        names = _index_names(connection, "events")
        assert {"uq_events_journal_seq", "ix_events_journal_seq"} <= names
        sql = _index_sql(connection, "uq_events_journal_seq")
        assert "UNIQUE" in sql.upper()
        assert "journal_seq IS NOT NULL" in sql


# --- nouvelles tables ---------------------------------------------------------


def test_create_all_creates_the_three_lot_e_tables(inspector):
    assert LOT_E_TABLES <= set(inspector.get_table_names())


def test_models_map_to_the_expected_tables():
    assert TestRunModel.__tablename__ == "test_runs"
    assert TestCaseModel.__tablename__ == "test_cases"
    assert ArtifactLinkModel.__tablename__ == "artifact_links"


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        (
            "test_runs",
            {
                "task_run_id",
                "project_id",
                "worker_id",
                "runner",
                "runner_version",
                "status",
                "started_at",
                "finished_at",
                "duration_ms",
                "totals",
                "exit_code",
                "report_artifact_id",
                "config",
            },
        ),
        (
            "test_cases",
            {
                "test_run_id",
                "suite_path",
                "title",
                "test_id",
                "location",
                "project_name",
                "attempt",
                "expected_status",
                "status",
                "outcome",
                "duration_ms",
                "error_message",
                "error_snippet",
                "steps",
                "annotations",
                "attachment_artifact_ids",
            },
        ),
        (
            "artifact_links",
            {
                "artifact_id",
                "user_id",
                "token_hash",
                "expires_at",
                "revoked_at",
                "used_count",
                "created_at",
            },
        ),
    ],
)
def test_expected_columns_exist(inspector, table: str, columns: set[str]):
    existing = {column["name"] for column in inspector.get_columns(table)}
    assert columns <= existing, columns - existing


def test_artifact_link_never_stores_the_plain_token(inspector):
    names = {column["name"] for column in inspector.get_columns("artifact_links")}
    assert "token" not in names
    assert "token_hash" in names


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("test_runs", ("task_run_id", "runner")),
        ("test_cases", ("test_run_id", "test_id", "attempt")),
        ("artifact_links", ("token_hash",)),
    ],
)
def test_unique_constraints_are_declared(inspector, table: str, columns: tuple[str, ...]):
    declared = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }
    declared |= {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    assert columns in declared


def test_foreign_keys_target_existing_tables(inspector):
    test_run_fks = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("test_runs")
    }
    assert ("task_runs", ("task_run_id",)) in test_run_fks
    assert ("projects", ("project_id",)) in test_run_fks
    assert ("workers", ("worker_id",)) in test_run_fks
    assert ("test_runs", ("test_run_id",)) in {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("test_cases")
    }
    link_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("artifact_links")}
    assert {"artifacts", "users"} <= link_fks


# --- unicité de la séquence par run -------------------------------------------


def test_two_events_of_the_same_run_cannot_share_a_sequence(engine):
    with Session(engine) as db:
        db.add(_event(task_run_id="run-1", sequence=1))
        db.commit()
        db.add(_event(task_run_id="run-1", sequence=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_two_runs_may_reuse_the_same_sequence(engine):
    with Session(engine) as db:
        db.add(_event(task_run_id="run-1", sequence=1))
        db.add(_event(task_run_id="run-2", sequence=1))
        db.commit()
        assert db.query(EventModel).count() == 2


def test_historical_events_without_run_or_sequence_stay_accepted(engine):
    with Session(engine) as db:
        db.add(_event())
        db.add(_event())
        db.add(_event(task_run_id="run-1"))
        db.add(_event(task_run_id="run-1"))
        db.commit()
        assert db.query(EventModel).count() == 4


def test_two_events_cannot_share_a_journal_sequence(engine):
    """L'ordre total du journal repose sur cette unicité : deux lignes, deux numéros."""

    with Session(engine) as db:
        db.add(_event(task_run_id="run-1", sequence=1, journal_seq=1))
        db.commit()
        db.add(_event(task_run_id="run-2", sequence=1, journal_seq=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_events_without_a_journal_sequence_stay_accepted(engine):
    """Unicité **partielle** : les lignes antérieures à la migration restent valides."""

    with Session(engine) as db:
        db.add(_event())
        db.add(_event())
        db.commit()
        assert db.query(EventModel).filter(EventModel.journal_seq.is_(None)).count() == 2


def test_event_schema_version_defaults_to_the_current_version(engine):
    with Session(engine) as db:
        event = _event(task_run_id="run-1", sequence=1)
        db.add(event)
        db.commit()
        assert event.schema_version == "1.0"


# --- migration d'une base existante -------------------------------------------


@pytest.fixture
def legacy_database(tmp_path, monkeypatch):
    database = tmp_path / "lot_e.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    bootstrap = create_engine(f"sqlite:///{database.as_posix()}")
    with bootstrap.begin() as connection:
        connection.execute(text(LEGACY_EVENTS_TABLE))
        connection.execute(text(LEGACY_ARTIFACTS_TABLE))
        connection.execute(
            text(
                "INSERT INTO events (id, created_at, type, occurred_at, payload) "
                "VALUES ('legacy-1', '2026-01-01 00:00:00', 'task.started', "
                "'2026-01-01 00:00:00', '{}')"
            )
        )
        # Trois lignes de projet écrites à la **même** date, et dont les
        # identifiants décroissent : ni l'horodatage ni l'identifiant ne peuvent
        # les ordonner, seul l'ordre d'insertion le peut.
        for identifier in LEGACY_PROJECT_EVENT_IDS:
            connection.execute(
                text(
                    "INSERT INTO events (id, created_at, type, occurred_at, "
                    "project_id, payload) VALUES (:event_id, "
                    "'2026-01-01 00:00:00', 'task.progress', "
                    "'2026-01-01 00:00:00', :project_id, '{}')"
                ),
                {"event_id": identifier, "project_id": LEGACY_PROJECT_ID},
            )
    bootstrap.dispose()
    try:
        yield database
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


def test_init_db_upgrades_an_existing_database_and_stays_idempotent(legacy_database):
    engine_module.init_db()
    engine = engine_module.get_engine()
    inspector = inspect(engine)
    assert LOT_E_TABLES <= set(inspector.get_table_names())
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    assert {"schema_version", "sequence", "conversation_id", "step_id"} <= event_columns
    artifact_columns = {column["name"] for column in inspector.get_columns("artifacts")}
    assert {"storage_key", "content_type", "stream_kind", "deleted_at"} <= artifact_columns

    # Deuxième passage sur la même base : aucune erreur, mêmes objets.
    engine_module.init_db()
    engine_module._upgrade_sqlite_schema(engine)
    with engine.connect() as connection:
        assert {"uq_event_run_sequence", "ix_events_task_run_sequence"} <= _index_names(
            connection, "events"
        )
        assert "ix_artifacts_storage_key" in _index_names(connection, "artifacts")
        assert "task_run_id IS NOT NULL" in _index_sql(connection, "uq_event_run_sequence")
        historical = connection.execute(
            text("SELECT schema_version, sequence FROM events WHERE id = 'legacy-1'")
        ).first()
    assert historical is not None
    assert historical[0] == "1.0"
    assert historical[1] is None


def test_the_migration_numbers_existing_rows_in_insertion_order(legacy_database):
    """Les lignes antérieures reçoivent un ``journal_seq`` unique et croissant."""

    engine_module.init_db()
    engine = engine_module.get_engine()
    with engine.connect() as connection:
        assert {"uq_events_journal_seq", "ix_events_journal_seq"} <= _index_names(
            connection, "events"
        )
        rows = connection.execute(
            text("SELECT id, journal_seq FROM events ORDER BY rowid")
        ).all()

    numbers = [row[1] for row in rows]
    assert all(number is not None for number in numbers), "ligne historique non numérotée"
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


def test_a_second_migration_leaves_the_journal_sequences_untouched(legacy_database):
    """Idempotence : rejouer la migration ne renumérote ni ne casse rien."""

    engine_module.init_db()
    engine = engine_module.get_engine()
    statement = text("SELECT id, journal_seq FROM events ORDER BY rowid")
    with engine.connect() as connection:
        before = connection.execute(statement).all()

    engine_module.init_db()
    engine_module._upgrade_sqlite_schema(engine)

    with engine.connect() as connection:
        assert connection.execute(statement).all() == before


def test_a_migrated_database_is_read_in_insertion_order(legacy_database):
    """La page projet rend les lignes migrées dans leur ordre d'écriture, sans trou."""

    engine_module.init_db()
    engine = engine_module.get_engine()
    with Session(engine) as db:
        page = read_project_page(db, LEGACY_PROJECT_ID, limit=10)

    assert [event.id for event in page.events] == list(LEGACY_PROJECT_EVENT_IDS)
    assert page.has_more is False


def test_upgraded_database_enforces_the_journal_sequence_uniqueness(legacy_database):
    """Deux lignes ne peuvent pas partager un numéro de journal après migration."""

    engine_module.init_db()
    engine = engine_module.get_engine()
    with engine.begin() as connection:
        taken = connection.execute(text("SELECT MAX(journal_seq) FROM events")).scalar()
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO events (id, created_at, type, occurred_at, payload, "
                    "schema_version, journal_seq) VALUES ('doublon', "
                    "'2026-01-01 00:00:00', 'task.started', '2026-01-01 00:00:00', "
                    "'{}', '1.0', :journal_seq)"
                ),
                {"journal_seq": taken},
            )


def test_upgraded_database_enforces_the_sequence_uniqueness(legacy_database):
    engine_module.init_db()
    engine = engine_module.get_engine()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO events (id, created_at, type, occurred_at, payload, "
                "schema_version, task_run_id, sequence) VALUES ('e1', "
                "'2026-01-01 00:00:00', 'task.started', '2026-01-01 00:00:00', '{}', "
                "'1.0', 'run-1', 1)"
            )
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO events (id, created_at, type, occurred_at, payload, "
                    "schema_version, task_run_id, sequence) VALUES ('e2', "
                    "'2026-01-01 00:00:00', 'task.started', '2026-01-01 00:00:00', '{}', "
                    "'1.0', 'run-1', 1)"
                )
            )
