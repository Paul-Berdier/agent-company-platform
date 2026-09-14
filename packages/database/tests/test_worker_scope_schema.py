"""Persistance fail-closed du périmètre de claim des workers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_database import engine as engine_module
from acp_database.models import Base, ProjectModel, WorkerModel


def _sqlite_engine(url: str):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _worker(**overrides) -> WorkerModel:
    values = {
        "name": "worker-scope",
        "token_hash": "a" * 64,
        "token_prefix": "prefix",
        "token_expires_at": datetime(2030, 1, 1, tzinfo=timezone.utc),
        "capabilities": [],
        "simulation": 1,
    }
    values.update(overrides)
    return WorkerModel(**values)


def test_fresh_worker_schema_enforces_one_explicit_scope():
    engine = _sqlite_engine("sqlite://")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("workers")}
        assert {"project_id", "global_access"} <= columns
        assert "ix_workers_project_id" in {
            index["name"] for index in inspector.get_indexes("workers")
        }
        foreign_keys = {
            (foreign_key["referred_table"], tuple(foreign_key["constrained_columns"]))
            for foreign_key in inspector.get_foreign_keys("workers")
        }
        assert ("projects", ("project_id",)) in foreign_keys
        checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("workers")
        }
        assert {
            "ck_workers_global_access_boolean",
            "ck_workers_single_scope",
        } <= checks

        with Session(engine) as db:
            db.add(_worker(global_access=2))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
            db.add(_worker(name="double-scope", project_id="project-1", global_access=1))
            with pytest.raises(IntegrityError):
                db.commit()
    finally:
        engine.dispose()


LEGACY_WORKERS = """
CREATE TABLE workers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME NOT NULL,
    name VARCHAR(200) NOT NULL UNIQUE,
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


def test_sqlite_legacy_workers_are_migrated_to_an_unscoped_quarantine(
    tmp_path, monkeypatch
):
    database = tmp_path / "legacy-workers.db"
    url = f"sqlite:///{database.as_posix()}"
    bootstrap = _sqlite_engine(url)
    with bootstrap.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text(LEGACY_WORKERS))
        connection.execute(
            text(
                "INSERT INTO workers ("
                "id, created_at, name, token_hash, token_prefix, token_expires_at, "
                "capabilities, max_concurrency, active_runs, status, simulation, metadata"
                ") VALUES ("
                "'legacy-worker', '2026-01-01', 'legacy', :token_hash, 'prefix', "
                "'2030-01-01', '[]', 1, 0, 'online', 1, '{}'"
                ")"
            ),
            {"token_hash": "a" * 64},
        )
    bootstrap.dispose()

    monkeypatch.setenv("ACP_DATABASE_URL", url)
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("workers")}
        assert {"project_id", "global_access"} <= columns
        assert "ix_workers_project_id" in {
            index["name"] for index in inspector.get_indexes("workers")
        }
        assert ("projects", ("project_id",)) in {
            (foreign_key["referred_table"], tuple(foreign_key["constrained_columns"]))
            for foreign_key in inspector.get_foreign_keys("workers")
        }
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT project_id, global_access FROM workers "
                    "WHERE id = 'legacy-worker'"
                )
            ).one() == (None, 0)

        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO projects (id) VALUES ('project-1')")
            )
        for statement in (
            "UPDATE workers SET global_access = 2 WHERE id = 'legacy-worker'",
            "UPDATE workers SET project_id = 'project-1', global_access = 1 "
            "WHERE id = 'legacy-worker'",
            "UPDATE workers SET project_id = 'missing-project' "
            "WHERE id = 'legacy-worker'",
        ):
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(statement))

        # La migration est idempotente et la quarantaine ne se transforme jamais
        # implicitement en privilège global lors d'un redémarrage.
        engine_module.init_db()
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT project_id, global_access FROM workers "
                    "WHERE id = 'legacy-worker'"
                )
            ).one() == (None, 0)
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()
