"""Chaîne Alembic sous SQLite : parité avec ``init_db()``, estampille et CLI.

Toujours exécuté (aucune base externe). Les comportements d'Alembic 1.20 face aux
index partiels et aux ``server_default`` littéraux ont été vérifiés
empiriquement avant d'écrire ces assertions ; le premier test fige ce constat.
"""

import io

import pytest
from acp_database import engine as engine_module
from acp_database.migrate import (
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    check_drift,
    current_revision,
    main,
    run_downgrade,
    run_upgrade,
)
from acp_database.models import Base
from acp_database.schema_state import (
    VERSION_TABLE,
    autogenerate_options,
    check_schema_current,
    head_revision,
    literal_default_text,
)
from acp_database.testing import point_global_engine_at, schema_inventory
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, text

pytestmark = pytest.mark.sqlite

EMPTY_DEFAULT_COLUMNS = {
    ("alerts", "acknowledgement_comment"),
    ("artifacts", "original_name"),
    ("artifacts", "stream_kind"),
    ("event_outbox", "last_error"),
}
PARTIAL_INDEXES = {
    "uq_event_run_sequence": "task_run_id IS NOT NULL AND sequence IS NOT NULL",
    "uq_events_journal_seq": "journal_seq IS NOT NULL",
    "ix_event_outbox_pending": "delivered_at IS NULL AND dead_at IS NULL",
}


def _url(tmp_path, name: str) -> str:
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def _compare(engine, *, options=None):
    opts = {"version_table": VERSION_TABLE}
    opts.update(options if options is not None else autogenerate_options())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts=opts)
        return compare_metadata(context, Base.metadata)


def _version(engine) -> str | None:
    with engine.connect() as connection:
        if not inspect(connection).has_table(VERSION_TABLE):
            return None
        return connection.execute(
            text(f"SELECT version_num FROM {VERSION_TABLE}")
        ).scalar_one()


def _index_sql(engine, name: str) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = :name"),
            {"name": name},
        ).scalar_one()


@pytest.fixture
def initialized(tmp_path, monkeypatch):
    """Base SQLite fraîche produite par ``init_db()`` (moteur global)."""

    url = _url(tmp_path, "init.db")
    point_global_engine_at(monkeypatch, url)
    engine_module.init_db()
    return url, engine_module.get_engine()


def test_literal_default_comparator_is_required_and_verified_by_catalogue(
    initialized,
):
    """Constat empirique figé : sans comparateur littéral, trois faux écarts.

    Alembic rend ``server_default=""`` par la chaîne vide alors que SQLite relit
    ``''`` ; le comparateur nominatif ramène les deux au même littéral. Le
    catalogue prouve que la valeur stockée est bien la chaîne vide.
    """

    _url_, engine = initialized
    naive = _compare(
        engine,
        options={"compare_type": True, "compare_server_default": True},
    )
    reported = {
        (entry[0][2], entry[0][3])
        for entry in naive
        if isinstance(entry, list) and entry[0][0] == "modify_default"
    }
    assert reported == EMPTY_DEFAULT_COLUMNS
    assert len(naive) == len(EMPTY_DEFAULT_COLUMNS)
    assert _compare(engine) == []
    with engine.connect() as connection:
        for table, column in sorted(EMPTY_DEFAULT_COLUMNS):
            rows = connection.execute(text(f"PRAGMA table_info({table})")).all()
            stored = next(row[4] for row in rows if row[1] == column)
            assert stored == "''"
            assert literal_default_text(stored) == ""


def test_init_db_matches_model_stamps_head_and_is_idempotent(initialized):
    url, engine = initialized
    assert _compare(engine) == []
    assert _version(engine) == head_revision()
    assert check_schema_current(engine).ok is True
    before = schema_inventory(engine)

    created = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("CREATE TABLE"):
            created.append(statement)

    engine_module.init_db()
    assert created == []
    assert schema_inventory(engine) == before
    assert _version(engine) == head_revision()
    assert current_revision(engine) == head_revision()


def test_partial_indexes_are_written_with_their_predicates(initialized):
    """Le catalogue, pas seulement Alembic, atteste les prédicats partiels."""

    _url_, engine = initialized
    for name, predicate in PARTIAL_INDEXES.items():
        sql = _index_sql(engine, name)
        assert f"WHERE {predicate}" in sql, sql
    assert "UNIQUE" in _index_sql(engine, "uq_event_run_sequence")
    assert "UNIQUE" in _index_sql(engine, "uq_events_journal_seq")
    assert "UNIQUE" not in _index_sql(engine, "ix_event_outbox_pending")


def test_compare_metadata_detects_a_missing_partial_index(initialized):
    _url_, engine = initialized
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_events_journal_seq"))
    diffs = _compare(engine)
    assert [(entry[0], entry[1].name) for entry in diffs] == [
        ("add_index", "uq_events_journal_seq")
    ]
    assert check_drift(engine) == ["index uq_events_journal_seq sur events à créer"]


def test_alembic_upgrade_on_empty_sqlite_equals_fresh_init_db(initialized, tmp_path):
    _url_, reference = initialized
    engine = engine_module.make_engine(_url(tmp_path, "alembic.db"))
    try:
        assert inspect(engine).get_table_names() == []
        run_upgrade(engine)
        assert _version(engine) == head_revision()
        assert _compare(engine) == []
        assert schema_inventory(engine) == schema_inventory(reference)
        assert len(schema_inventory(engine)) == 50
    finally:
        engine.dispose()


def test_downgrade_to_base_then_upgrade_again(tmp_path):
    engine = engine_module.make_engine(_url(tmp_path, "cycle.db"))
    try:
        run_upgrade(engine)
        first = schema_inventory(engine)
        run_downgrade(engine, "base")
        assert inspect(engine).get_table_names() == [VERSION_TABLE]
        assert current_revision(engine) is None
        assert check_schema_current(engine).ok is False
        run_upgrade(engine)
        assert schema_inventory(engine) == first
        assert current_revision(engine) == head_revision()
    finally:
        engine.dispose()


def test_upgrade_to_first_revision_then_head(tmp_path):
    engine = engine_module.make_engine(_url(tmp_path, "steps.db"))
    try:
        run_upgrade(engine, "0001")
        assert _version(engine) == "0001"
        assert not inspect(engine).has_table("event_outbox")
        assert len(schema_inventory(engine)) == 47
        run_upgrade(engine)
        assert inspect(engine).has_table("event_outbox")
        assert _version(engine) == head_revision()
    finally:
        engine.dispose()


def test_0003_changes_nothing_on_sqlite_whose_integers_are_already_64_bit(tmp_path):
    """0003 élargit des colonnes PostgreSQL ; sous SQLite elle n'émet aucun DDL.

    SQLite stocke tout INTEGER sur 64 bits et n'applique pas la longueur d'un
    VARCHAR : la variante SQLite du modèle garde le DDL historique, et une valeur
    au-delà de 2^31 y est déjà conservée à l'identique.
    """

    engine = engine_module.make_engine(_url(tmp_path, "wide.db"))
    try:
        run_upgrade(engine, "0002")
        before = schema_inventory(engine)
        run_upgrade(engine, "0003")
        assert _version(engine) == "0003"
        assert schema_inventory(engine) == before
        run_downgrade(engine, "0002")
        assert _version(engine) == "0002"
        assert schema_inventory(engine) == before
        run_upgrade(engine)
        assert _compare(engine) == []
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO events (id, created_at, type, occurred_at, payload, "
                    "schema_version, journal_seq) VALUES ('evt-wide', "
                    "'2026-09-19 00:00:00', 't', '2026-09-19 00:00:00', '{}', '1.0', "
                    ":seq)"
                ),
                {"seq": 2**40},
            )
            assert connection.execute(
                text("SELECT journal_seq FROM events WHERE id = 'evt-wide'")
            ).scalar_one() == 2**40
    finally:
        engine.dispose()


def test_check_drift_reports_extra_table(initialized):
    _url_, engine = initialized
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE locale_extra (id INTEGER PRIMARY KEY)"))
    assert check_drift(engine) == ["table locale_extra à supprimer"]


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_refuses_upgrade_and_downgrade_on_sqlite(initialized):
    url, _engine = initialized
    code, out, err = _cli(["upgrade", "--database-url", url])
    assert code == EXIT_REFUSED
    assert out == ""
    assert "SQLite est migré par init_db() ; Alembic n'y fait qu'estampiller" in err
    code, _out, err = _cli(
        [
            "downgrade",
            "--to",
            "base",
            "--yes-i-understand-data-loss",
            "--database-url",
            url,
        ]
    )
    assert code == EXIT_REFUSED
    assert "SQLite est migré par init_db()" in err


def test_cli_current_check_history_on_sqlite(initialized, tmp_path):
    url, _engine = initialized
    head = head_revision()
    code, out, err = _cli(["current", "--database-url", url])
    assert (code, err) == (EXIT_OK, "")
    assert f"Révision courante : {head}" in out and "à jour" in out

    code, out, err = _cli(["check", "--database-url", url])
    assert (code, err) == (EXIT_OK, "")
    assert f"Schéma à jour ({head})" in out

    code, out, err = _cli(["history", "--database-url", url])
    assert (code, err) == (EXIT_OK, "")
    lines = out.strip().splitlines()
    assert lines[0].startswith(f"{head} <- ")
    assert lines[-1].startswith("0001 <- <base>")

    empty = _url(tmp_path, "empty.db")
    code, out, _err = _cli(["current", "--database-url", empty])
    assert code == EXIT_OK
    assert "aucune (table alembic_version absente)" in out and "hors version" in out
    code, out, err = _cli(["check", "--database-url", empty])
    assert (code, out) == (EXIT_REFUSED, "")
    assert "Refus" in err and "hors version" in err


def test_cli_check_refuses_drift(initialized):
    url, engine = initialized
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE locale_extra (id INTEGER PRIMARY KEY)"))
    code, out, err = _cli(["check", "--database-url", url])
    assert (code, out) == (EXIT_REFUSED, "")
    assert "dérive du schéma" in err and "table locale_extra à supprimer" in err


def test_cli_stamp_is_allowed_on_sqlite(tmp_path):
    url = _url(tmp_path, "stamp.db")
    code, out, err = _cli(["stamp", "head", "--database-url", url])
    assert (code, err) == (EXIT_OK, "")
    assert f"Base estampillée à {head_revision()}" in out
    engine = engine_module.make_engine(url)
    try:
        assert inspect(engine).get_table_names() == [VERSION_TABLE]
        assert _version(engine) == head_revision()
    finally:
        engine.dispose()


def test_cli_usage_errors(monkeypatch, tmp_path):
    monkeypatch.delenv("ACP_DATABASE_URL", raising=False)
    url = _url(tmp_path, "usage.db")
    code, _out, err = _cli([])
    assert code == EXIT_USAGE and "Usage incorrect" in err
    code, _out, err = _cli(["inconnue"])
    assert code == EXIT_USAGE and "Usage incorrect" in err
    code, _out, err = _cli(["current"])
    assert code == EXIT_USAGE and "ACP_DATABASE_URL" in err
    code, _out, err = _cli(["downgrade", "--to", "base", "--database-url", url])
    assert code == EXIT_USAGE and "--yes-i-understand-data-loss" in err
    code, out, err = _cli(["--help"])
    assert (code, err) == (EXIT_OK, "")
    assert "python -m acp_database.migrate" in out


def test_cli_refuses_forbidden_drivers(monkeypatch):
    monkeypatch.delenv("ACP_DATABASE_URL", raising=False)
    for url in ("postgresql://acp:acp@localhost/acp", "postgresql+psycopg2://x/y"):
        code, _out, err = _cli(["current", "--database-url", url])
        assert code == EXIT_REFUSED
        assert "postgresql+psycopg" in err


def test_cli_reads_url_from_environment(initialized, monkeypatch):
    url, _engine = initialized
    monkeypatch.setenv("ACP_DATABASE_URL", url)
    code, out, _err = _cli(["current"])
    assert code == EXIT_OK and head_revision() in out


def test_sqlite_refuses_unknown_revision_before_any_schema_changes(tmp_path, monkeypatch):
    from acp_database.schema_state import SchemaOutOfDateError
    url = _url(tmp_path, "future.db")
    point_global_engine_at(monkeypatch, url)
    engine = engine_module.get_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('9999')"))
    with pytest.raises(SchemaOutOfDateError, match="plus récente"):
        engine_module.init_db()
    assert inspect(engine).get_table_names() == ["alembic_version"]
    assert current_revision(engine) == "9999"


def test_inventory_preserves_boolean_grouping_and_literal_case():
    from acp_database.testing import _normalized_expression
    assert _normalized_expression("(a OR b) AND c") != _normalized_expression("a OR (b AND c)")
    assert _normalized_expression("kind = 'A'") != _normalized_expression("kind = 'a'")
    assert _normalized_expression("((a IS NULL) AND (b IS NULL))") == _normalized_expression("a IS NULL AND b IS NULL")


def test_upgrade_guard_reuses_the_single_available_connection(tmp_path):
    from sqlalchemy import create_engine
    engine = create_engine(_url(tmp_path, "single.db"), pool_size=1, max_overflow=0, pool_timeout=0.1)
    try:
        run_upgrade(engine)
        assert check_schema_current(engine).ok
    finally:
        engine.dispose()
