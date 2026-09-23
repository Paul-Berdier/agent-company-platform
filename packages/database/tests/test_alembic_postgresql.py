"""Chaîne Alembic sur PostgreSQL (base de test ``ACP_TEST_DATABASE_URL``).

Chaque test remet le schéma ``public`` à zéro : la base du lot lui est réservée.
"""

import io

import pytest
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
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, text

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


# Entiers non bornés par leur source : code de sortie Windows (DWORD non signé,
# 0xC000013A = 3221225786 après un CTRL_BREAK), tailles et durées, compteur du
# journal entier. En INTEGER (int4), PostgreSQL les refuse au-delà de 2^31 - 1.
WIDE_INTEGER_COLUMNS = (
    ("artifacts", "size_bytes"),
    ("event_outbox", "journal_seq"),
    ("events", "journal_seq"),
    ("mission_evidence", "exit_code"),
    ("test_cases", "duration_ms"),
    ("test_runs", "duration_ms"),
    ("test_runs", "exit_code"),
)


def _data_types(engine, columns) -> dict[tuple[str, str], str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        ).all()
    found = {(row[0], row[1]): row[2] for row in rows}
    return {column: found.get(column) for column in columns}


def test_0003_widens_unbounded_integers_and_downgrade_restores_them(pg_engine):
    run_upgrade(pg_engine, "0002")
    assert set(_data_types(pg_engine, WIDE_INTEGER_COLUMNS).values()) == {"integer"}

    run_upgrade(pg_engine)
    assert head_revision() == "0003"
    assert set(_data_types(pg_engine, WIDE_INTEGER_COLUMNS).values()) == {"bigint"}
    assert check_drift(pg_engine) == []

    run_downgrade(pg_engine, "0002")
    assert current_revision(pg_engine) == "0002"
    assert set(_data_types(pg_engine, WIDE_INTEGER_COLUMNS).values()) == {"integer"}

    run_upgrade(pg_engine)
    assert set(_data_types(pg_engine, WIDE_INTEGER_COLUMNS).values()) == {"bigint"}


def test_0003_downgrade_fails_closed_on_a_value_beyond_int4(pg_engine):
    """Redescendre ne tronque jamais : une valeur > 2^31 - 1 fait échouer la révision."""

    run_upgrade(pg_engine)
    beyond = 2**31 + 7
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO events (id, created_at, type, occurred_at, payload, "
                "schema_version, journal_seq) VALUES ('evt-wide', now(), 't', now(), "
                "'{}', '1.0', :seq)"
            ),
            {"seq": beyond},
        )
    with pytest.raises(Exception, match="out of range"):
        run_downgrade(pg_engine, "0002")
    assert current_revision(pg_engine) == head_revision()
    with pg_engine.connect() as connection:
        assert connection.execute(
            text("SELECT journal_seq FROM events WHERE id = 'evt-wide'")
        ).scalar_one() == beyond
    assert set(_data_types(pg_engine, WIDE_INTEGER_COLUMNS).values()) == {"bigint"}


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
    assert "conforme aux contrôles effectués" in out
    assert "pas leur expression SQL" in out
    code, out, err = cli("current")
    assert (code, err) == (EXIT_OK, "")
    assert f"Révision courante : {head_revision()}" in out


@pytest.mark.parametrize("revision", ["head", "heads", "0003"])
@pytest.mark.parametrize("allow_unverified_revision", [False, True])
def test_stamp_refuses_empty_postgresql_database(pg_engine, revision, allow_unverified_revision):
    from acp_database.migrate import run_stamp
    with pytest.raises(RuntimeError, match="schéma différent"):
        run_stamp(pg_engine, revision, allow_unverified_revision=allow_unverified_revision)
    assert current_revision(pg_engine) is None


def test_stamp_refuses_intermediate_revision_without_explicit_override(pg_engine):
    from acp_database.migrate import run_stamp
    run_upgrade(pg_engine)
    with pytest.raises(RuntimeError, match="intermédiaire"):
        run_stamp(pg_engine, "0001")
    assert current_revision(pg_engine) == head_revision()


def test_stamp_accepts_intermediate_revision_with_explicit_override(pg_engine):
    from acp_database.migrate import run_stamp
    run_upgrade(pg_engine, "0002")
    run_stamp(pg_engine, "0002", allow_unverified_revision=True)
    assert current_revision(pg_engine) == "0002"


def test_stamp_resolves_short_head_before_checking_schema(pg_engine, monkeypatch):
    from acp_database import migrate
    from alembic.script.revision import Revision, RevisionMap

    script = migrate.ScriptDirectory.from_config(migrate.alembic_config())
    script.revision_map = RevisionMap(lambda: [Revision("abcdef123456", None)])
    monkeypatch.setattr(migrate, "script_directory", lambda: script)
    monkeypatch.setattr(migrate, "head_revision", lambda: "abcdef123456")
    monkeypatch.setattr(migrate.command, "stamp", lambda *_: pytest.fail("tête estampillée sans contrôle"))

    with pytest.raises(RuntimeError, match="schéma différent"):
        migrate.run_stamp(pg_engine, "abcdef", allow_unverified_revision=True)
    assert current_revision(pg_engine) is None


def test_current_revision_without_tables_is_not_ready(pg_engine, postgresql_url, monkeypatch):
    run_upgrade(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE event_outbox"))
    state = check_schema_current(pg_engine)
    assert not state.ok
    assert "event_outbox" in str(SchemaOutOfDateError(state))
    point_global_engine_at(monkeypatch, postgresql_url)
    with pytest.raises(SchemaOutOfDateError, match="event_outbox"):
        engine_module.init_db()


def test_unknown_revision_is_not_misdiagnosed_as_behind(pg_engine):
    run_upgrade(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    state = check_schema_current(pg_engine)
    assert not state.ok
    message = str(SchemaOutOfDateError(state))
    assert "plus récente" in message
    assert "Exécutez" not in message
    with pytest.raises(RuntimeError, match="plus récente"):
        run_upgrade(pg_engine)


def test_drift_detects_removed_check(pg_engine):
    run_upgrade(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("ALTER TABLE event_outbox DROP CONSTRAINT ck_event_outbox_attempts_non_negative"))
    assert any("ck_event_outbox_attempts_non_negative" in item for item in check_drift(pg_engine))


def test_drift_detects_removed_partial_index_predicate(pg_engine):
    run_upgrade(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_events_journal_seq"))
        connection.execute(text("CREATE UNIQUE INDEX uq_events_journal_seq ON events (journal_seq)"))
    assert any("uq_events_journal_seq" in item for item in check_drift(pg_engine))


def test_stamp_accepts_existing_model_schema_without_migrations(pg_engine):
    from acp_database.migrate import run_stamp
    Base.metadata.create_all(pg_engine)
    run_stamp(pg_engine, "head")
    assert check_schema_current(pg_engine).ok


def test_wide_reference_downgrade_refuses_truncation(pg_engine):
    run_upgrade(pg_engine)
    reference = "chemin/" * 100
    from sqlalchemy.orm import Session
    from acp_database.models import SkillModel, UserModel
    with Session(pg_engine) as session:
        owner = UserModel(login_normalized="wide-owner", display_name="Propriétaire", password_hash="test-hash")
        session.add(owner)
        session.flush()
        session.add(SkillModel(
            id="wide-ref", name="wide-ref", display_name="Référence longue",
            kind="documentary", source_kind="directory", origin=reference,
            created_by_user_id=owner.id,
        ))
        session.commit()
    with pytest.raises(RuntimeError, match="500 caractères"):
        run_downgrade(pg_engine, "0002")
    assert current_revision(pg_engine) == "0003"
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT origin FROM skills WHERE id = 'wide-ref'")).scalar_one() == reference


def test_migration_guards_reuse_the_single_available_connection(pg_engine, postgresql_url):
    from sqlalchemy import create_engine
    from acp_database.migrate import run_stamp
    engine = create_engine(postgresql_url, pool_size=1, max_overflow=0, pool_timeout=0.1)
    try:
        run_upgrade(engine)
        run_stamp(engine, "heads", allow_unverified_revision=True)
        assert check_schema_current(engine).ok
    finally:
        engine.dispose()
