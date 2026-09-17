"""Chaîne Alembic sur PostgreSQL (base de test ``ACP_TEST_DATABASE_URL``).

Chaque test remet le schéma ``public`` à zéro : la base du lot lui est réservée.
"""

import io

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, text

from acp_database import engine as engine_module
from acp_database.locking import LockUnavailableError, advisory_session_lock
from acp_database.migrate import (
    EXIT_OK,
    MIGRATION_LOCK_KEY,
    check_drift,
    current_revision,
    main,
    run_downgrade,
    run_upgrade,
)
from acp_database.models import Base
from acp_database.schema_state import (
    VERSION_TABLE,
    SchemaOutOfDateError,
    autogenerate_options,
    check_schema_current,
    head_revision,
)
from acp_database.testing import (
    point_global_engine_at,
    reset_public_schema,
    schema_inventory,
)

pytestmark = pytest.mark.postgres

PARTIAL_INDEXES = {
    "uq_event_run_sequence": "WHERE ((task_run_id IS NOT NULL) AND (sequence IS NOT NULL))",
    "uq_events_journal_seq": "WHERE (journal_seq IS NOT NULL)",
    "ix_event_outbox_pending": "WHERE ((delivered_at IS NULL) AND (dead_at IS NULL))",
}


@pytest.fixture
def pg_engine(postgresql_url):
    """Moteur de maintenance sur une base ``public`` vidée avant le test."""

    reset_public_schema(postgresql_url)
    engine = engine_module.make_engine(postgresql_url, maintenance=True)
    try:
        yield engine
    finally:
        engine.dispose()


def _compare(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"version_table": VERSION_TABLE, **autogenerate_options()}
        )
        return compare_metadata(context, Base.metadata)


def _ddl_statements(engine):
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith(("CREATE", "ALTER", "DROP")):
            statements.append(statement)

    return statements


def test_upgrade_matches_model_and_second_upgrade_emits_no_ddl(pg_engine):
    assert check_schema_current(pg_engine) == check_schema_current(pg_engine)
    assert check_schema_current(pg_engine).ok is False
    assert check_schema_current(pg_engine).current is None

    run_upgrade(pg_engine)
    assert check_schema_current(pg_engine).ok is True
    assert current_revision(pg_engine) == head_revision()
    assert _compare(pg_engine) == []
    assert check_drift(pg_engine) == []
    assert len(schema_inventory(pg_engine)) == 48

    statements = _ddl_statements(pg_engine)
    run_upgrade(pg_engine)
    assert statements == []
    assert current_revision(pg_engine) == head_revision()


def test_alembic_schema_equals_create_all_schema(pg_engine, postgresql_url):
    run_upgrade(pg_engine)
    migrated = schema_inventory(pg_engine)
    reset_public_schema(postgresql_url)
    Base.metadata.create_all(pg_engine)
    assert schema_inventory(pg_engine) == migrated


def test_downgrade_to_base_then_upgrade(pg_engine):
    run_upgrade(pg_engine)
    first = schema_inventory(pg_engine)
    run_downgrade(pg_engine, "base")
    assert inspect(pg_engine).get_table_names() == [VERSION_TABLE]
    assert current_revision(pg_engine) is None
    run_upgrade(pg_engine)
    assert schema_inventory(pg_engine) == first
    assert current_revision(pg_engine) == head_revision()


def test_pg_indexes_carry_partial_predicates_and_circular_fk(pg_engine):
    run_upgrade(pg_engine)
    with pg_engine.connect() as connection:
        rows = dict(
            connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = ANY(:names)"
                ),
                {"names": list(PARTIAL_INDEXES)},
            ).all()
        )
        assert set(rows) == set(PARTIAL_INDEXES)
        for name, predicate in PARTIAL_INDEXES.items():
            assert rows[name].endswith(predicate), rows[name]
        assert rows["uq_event_run_sequence"].startswith("CREATE UNIQUE INDEX")
        assert rows["uq_events_journal_seq"].startswith("CREATE UNIQUE INDEX")
        assert rows["ix_event_outbox_pending"].startswith("CREATE INDEX")
        constraints = connection.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'tasks'::regclass AND contype = 'f'"
            )
        ).scalars().all()
        assert "tasks_active_run_id_fkey" in constraints


def test_advisory_lock_refuses_concurrent_migration(pg_engine):
    with pg_engine.connect() as holder:
        with advisory_session_lock(holder, MIGRATION_LOCK_KEY, timeout_seconds=5):
            with pytest.raises(LockUnavailableError, match="acp_database.migrate"):
                run_upgrade(pg_engine, lock_timeout_seconds=0.3)
            assert current_revision(pg_engine) is None
    run_upgrade(pg_engine, lock_timeout_seconds=5)
    assert current_revision(pg_engine) == head_revision()


def test_init_db_refuses_unmigrated_postgresql_without_creating_tables(
    postgresql_url, monkeypatch
):
    reset_public_schema(postgresql_url)
    point_global_engine_at(monkeypatch, postgresql_url)
    with pytest.raises(SchemaOutOfDateError) as excinfo:
        engine_module.init_db()
    message = str(excinfo.value)
    assert "python -m acp_database.migrate upgrade" in message
    assert "aucune (table alembic_version absente)" in message
    assert head_revision() in message
    assert inspect(engine_module.get_engine()).get_table_names() == []


def test_init_db_accepts_migrated_postgresql(postgresql_url, monkeypatch):
    reset_public_schema(postgresql_url)
    maintenance = engine_module.make_engine(postgresql_url, maintenance=True)
    try:
        run_upgrade(maintenance)
    finally:
        maintenance.dispose()
    point_global_engine_at(monkeypatch, postgresql_url)
    statements = _ddl_statements(engine_module.get_engine())
    engine_module.init_db()
    assert statements == []


def test_init_db_refuses_stale_revision(postgresql_url, monkeypatch):
    reset_public_schema(postgresql_url)
    maintenance = engine_module.make_engine(postgresql_url, maintenance=True)
    try:
        run_upgrade(maintenance, "0001")
    finally:
        maintenance.dispose()
    point_global_engine_at(monkeypatch, postgresql_url)
    with pytest.raises(SchemaOutOfDateError, match="révision courante 0001"):
        engine_module.init_db()
    assert not inspect(engine_module.get_engine()).has_table("event_outbox")


def test_cli_upgrade_twice_check_and_current(pg_engine, postgresql_url):
    def cli(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = main([*argv, "--database-url", postgresql_url], stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()

    code, out, err = cli("upgrade")
    assert (code, err) == (EXIT_OK, "")
    assert f"Schéma migré de aucune vers {head_revision()}" in out
    code, out, err = cli("upgrade")
    assert (code, err) == (EXIT_OK, "")
    assert "aucun DDL émis" in out
    code, out, err = cli("check")
    assert (code, err) == (EXIT_OK, "")
    assert "conforme au modèle" in out
    code, out, err = cli("current")
    assert (code, err) == (EXIT_OK, "")
    assert f"Révision courante : {head_revision()}" in out
