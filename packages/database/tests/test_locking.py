"""Verrous d'écriture (``write_lock``) et verrous consultatifs de session."""

import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from acp_database.engine import make_engine
from acp_database.locking import (
    LockUnavailableError,
    advisory_session_lock,
    write_lock,
)
from acp_database.models import UserModel
from acp_database.testing import make_test_engine


def _fake_session(dialect_name: str):
    """Session factice : ``write_lock`` ne lit que ``db.connection().dialect``."""

    connection = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
    return SimpleNamespace(connection=lambda: connection)


@pytest.mark.sqlite
def test_write_lock_opens_begin_immediate_without_committing(tmp_path, monkeypatch):
    monkeypatch.delenv("ACP_TEST_DATABASE_URL", raising=False)
    database = make_test_engine(tmp_path, concurrent=True)
    engine = database.engine
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    try:
        with Session(engine) as db:
            write_lock(db, "events")
            driver = db.connection().connection.driver_connection
            assert driver.in_transaction is True
            assert statements.count("BEGIN IMMEDIATE") == 1
            # Déjà en transaction : aucun second BEGIN, la transaction reste celle
            # de l'appelant.
            write_lock(db, "events")
            assert statements.count("BEGIN IMMEDIATE") == 1
            db.add(
                UserModel(
                    login_normalized="verrou",
                    display_name="Verrou",
                    password_hash="x",
                    platform_role="member",
                )
            )
            db.flush()
            # Le verrou d'écriture est bien tenu : un autre écrivain est refusé
            # (délai d'attente réduit pour que le refus soit immédiat).
            other = make_engine(database.url)
            try:
                with other.connect() as competitor:
                    competitor.exec_driver_sql("PRAGMA busy_timeout = 100")
                    with pytest.raises(OperationalError, match="locked"):
                        competitor.exec_driver_sql("BEGIN IMMEDIATE")
            finally:
                other.dispose()
            # Rien n'a été validé prématurément : le rollback efface la ligne.
            db.rollback()
        with Session(engine) as db:
            assert db.query(UserModel).count() == 0
    finally:
        database.close()


def test_write_lock_refuses_unknown_dialect():
    with pytest.raises(RuntimeError, match="oracle"):
        write_lock(_fake_session("oracle"), "events")


@pytest.mark.sqlite
def test_advisory_session_lock_is_a_noop_on_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("ACP_TEST_DATABASE_URL", raising=False)
    database = make_test_engine(tmp_path)
    try:
        with database.engine.connect() as connection:
            with advisory_session_lock(connection, "acp_database.migrate", timeout_seconds=0):
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        database.close()


def test_advisory_session_lock_refuses_unknown_dialect():
    connection = SimpleNamespace(dialect=SimpleNamespace(name="oracle"))
    with pytest.raises(RuntimeError, match="oracle"):
        with advisory_session_lock(connection, "k", timeout_seconds=1):
            pass


@pytest.mark.postgres
@pytest.mark.concurrency
def test_write_lock_serializes_sessions_until_commit(postgresql_url):
    engine = make_engine(postgresql_url)
    acquired_at = {}
    started = threading.Event()
    try:
        with Session(engine) as first:
            write_lock(first, "events")
            with engine.connect() as observer:
                held = observer.execute(
                    text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' AND granted"
                    )
                ).scalar_one()
            assert held >= 1

            def second_writer():
                with Session(engine) as second:
                    started.set()
                    write_lock(second, "events")
                    acquired_at["value"] = time.monotonic()
                    second.rollback()

            worker = threading.Thread(target=second_writer)
            worker.start()
            assert started.wait(5)
            time.sleep(0.5)
            assert "value" not in acquired_at
            released_at = time.monotonic()
            first.commit()
            worker.join(10)
            assert not worker.is_alive()
        assert acquired_at["value"] >= released_at
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_advisory_session_lock_times_out_then_succeeds(postgresql_url):
    engine = make_engine(postgresql_url)
    try:
        with engine.connect() as holder, engine.connect() as candidate:
            with advisory_session_lock(holder, "acp_database.migrate", timeout_seconds=1):
                started = time.monotonic()
                with pytest.raises(LockUnavailableError, match="acp_database.migrate"):
                    with advisory_session_lock(
                        candidate, "acp_database.migrate", timeout_seconds=0.3
                    ):
                        pass
                assert time.monotonic() - started >= 0.3
                # Une autre clé n'est pas bloquée.
                with advisory_session_lock(candidate, "autre", timeout_seconds=0.3):
                    pass
            with advisory_session_lock(candidate, "acp_database.migrate", timeout_seconds=1):
                assert candidate.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_advisory_session_lock_refuses_open_transaction(postgresql_url):
    engine = make_engine(postgresql_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            assert connection.in_transaction()
            with pytest.raises(RuntimeError, match="porte déjà une transaction"):
                with advisory_session_lock(connection, "k", timeout_seconds=1):
                    pass
    finally:
        engine.dispose()
