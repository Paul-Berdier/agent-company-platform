"""Parité de la mise à niveau SQLite entre une base 0.8.0 et une base fraîche.

Le modèle 0.8.0 est relu depuis l'historique git (commit ``e71ebf6``, dernier
état publié avant le Lot H) et chargé dans un module isolé : la base « legacy »
est donc réellement celle qu'un déploiement 0.8.0 a produite, pas une copie
dérivée du modèle courant.
"""

import subprocess
import sys
import types
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

from acp_database import engine as engine_module
from acp_database.schema_state import VERSION_TABLE, head_revision
from acp_database.testing import point_global_engine_at, schema_inventory

pytestmark = pytest.mark.sqlite

LEGACY_COMMIT = "e71ebf6"
LEGACY_MODEL_PATH = "packages/database/src/acp_database/models.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Objets que la mise à niveau 0.8.0 (engine.py du commit e71ebf6) ajoutait par
# DDL brut, en doublon des contraintes de table, et que ``init_db()`` doit
# conserver sur une telle base sans jamais les recréer sur une base fraîche.
LEGACY_DUPLICATE_INDEXES = {
    "uq_mission_command_principal_key": (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mission_command_principal_key "
        "ON mission_commands (principal_id, command, idempotency_key) "
        "WHERE principal_id IS NOT NULL"
    ),
    "uq_scheduler_leases_key": (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduler_leases_key "
        "ON scheduler_leases (scheduler_key)"
    ),
}
LEGACY_AD_HOC_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_alerts_acknowledged_by_user_id "
    "ON alerts (acknowledged_by_user_id)"
)
REBUILD_MARKERS = (
    "_lot_f_model_parity_v3",
    "_lot_f_constraints_v2",
    "_principal_scope_v2",
    "_principal_run_scope_v2",
)


@pytest.fixture(scope="module")
def legacy_models():
    """Module ``models.py`` du commit 0.8.0, ou test ignoré si git ne peut le relire."""

    try:
        completed = subprocess.run(
            ["git", "show", f"{LEGACY_COMMIT}:{LEGACY_MODEL_PATH}"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        pytest.skip(f"git indisponible, modèle 0.8.0 non relu : {exc}")
    if completed.returncode != 0:
        pytest.skip(
            f"commit {LEGACY_COMMIT} introuvable, modèle 0.8.0 non relu : "
            + completed.stderr.decode("utf-8", "replace").strip()
        )
    module = types.ModuleType("acp_legacy_models_0_8_0")
    module.__file__ = f"<git:{LEGACY_COMMIT}:{LEGACY_MODEL_PATH}>"
    exec(compile(completed.stdout.decode("utf-8"), module.__file__, "exec"), module.__dict__)
    assert "event_outbox" not in module.Base.metadata.tables
    return module


def _legacy_database(tmp_path, legacy_models, *, with_duplicates: bool) -> str:
    """Base telle que la version 0.8.0 la laissait après son ``init_db()``."""

    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    bootstrap = create_engine(url)
    try:
        legacy_models.Base.metadata.create_all(bootstrap)
        with bootstrap.begin() as connection:
            connection.execute(text(LEGACY_AD_HOC_INDEX))
            if with_duplicates:
                for ddl in LEGACY_DUPLICATE_INDEXES.values():
                    connection.execute(text(ddl))
            connection.execute(text("INSERT INTO users (id, login_normalized, display_name, password_hash, platform_role, is_active, password_changed_at, created_at) VALUES ('user-1', 'legacy', 'Legacy', 'x', 'owner', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"))
            connection.execute(text("INSERT INTO scheduler_leases (id, scheduler_key, created_at) VALUES ('lease-1', 'automations', '2026-01-01 00:00:00')"))
    finally:
        bootstrap.dispose()
    return url


def _index_names(engine, table: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table)}


def _capture_statements(engine) -> list[str]:
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    return statements


def test_fresh_database_has_no_duplicate_indexes(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    point_global_engine_at(monkeypatch, url)
    engine_module.init_db()
    engine = engine_module.get_engine()
    assert "uq_mission_command_principal_key" not in _index_names(engine, "mission_commands")
    assert "uq_scheduler_leases_key" not in _index_names(engine, "scheduler_leases")
    assert "ix_alerts_acknowledged_by_user_id" in _index_names(engine, "alerts")
    assert ("principal_id", "command", "idempotency_key") in {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints("mission_commands")
    }
    assert ("scheduler_key",) in {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints("scheduler_leases")
    }


def test_legacy_0_8_0_database_upgrades_without_rebuild(
    tmp_path, monkeypatch, legacy_models
):
    url = _legacy_database(tmp_path, legacy_models, with_duplicates=True)
    point_global_engine_at(monkeypatch, url)
    engine = engine_module.get_engine()
    assert not inspect(engine).has_table("event_outbox")
    assert not inspect(engine).has_table(VERSION_TABLE)
    statements = _capture_statements(engine)

    engine_module.init_db()

    rebuilds = [
        statement
        for statement in statements
        if any(marker in statement for marker in REBUILD_MARKERS)
    ]
    assert rebuilds == []
    assert inspect(engine).has_table("event_outbox")
    with engine.connect() as connection:
        assert connection.execute(
            text(f"SELECT version_num FROM {VERSION_TABLE}")
        ).scalar_one() == head_revision()
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM scheduler_leases")
        ).scalar_one() == 1
    # Les index doublons historiques restent présents, nommés et uniques.
    for table, name in (
        ("mission_commands", "uq_mission_command_principal_key"),
        ("scheduler_leases", "uq_scheduler_leases_key"),
    ):
        index = next(
            index for index in inspect(engine).get_indexes(table) if index["name"] == name
        )
        assert index["unique"]


def test_legacy_database_inventory_equals_fresh_except_duplicates(
    tmp_path, monkeypatch, legacy_models
):
    fresh_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    point_global_engine_at(monkeypatch, fresh_url)
    engine_module.init_db()
    fresh = schema_inventory(engine_module.get_engine())

    legacy_url = _legacy_database(tmp_path, legacy_models, with_duplicates=True)
    point_global_engine_at(monkeypatch, legacy_url)
    engine_module.init_db()
    legacy = schema_inventory(engine_module.get_engine())

    for name in LEGACY_DUPLICATE_INDEXES:
        table = "mission_commands" if "mission" in name else "scheduler_leases"
        extra = legacy[table]["indexes"].pop(name)
        assert extra["unique"] is True
    assert legacy == fresh


def test_legacy_database_without_duplicates_gains_none(
    tmp_path, monkeypatch, legacy_models
):
    """Une base 0.8.0 créée par ``create_all`` seul ne reçoit pas de doublon."""

    url = _legacy_database(tmp_path, legacy_models, with_duplicates=False)
    point_global_engine_at(monkeypatch, url)
    engine_module.init_db()
    engine = engine_module.get_engine()
    assert "uq_mission_command_principal_key" not in _index_names(engine, "mission_commands")
    assert "uq_scheduler_leases_key" not in _index_names(engine, "scheduler_leases")


def test_legacy_models_are_really_from_git(legacy_models):
    assert sys.modules.get("acp_legacy_models_0_8_0") is None
    assert not hasattr(legacy_models, "EventOutboxModel")
    alerts = legacy_models.Base.metadata.tables["alerts"]
    assert not alerts.c.acknowledged_by_user_id.index
