"""Tables du Lot D : création, contraintes d'unicité et idempotence d'``init_db``."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from acp_database import engine as engine_module
from acp_database.models import (
    Base,
    McpBindingModel,
    McpProbeModel,
    McpServerModel,
    McpServerRevisionModel,
    SecretModel,
    SkillBindingModel,
    SkillModel,
    SkillRevisionModel,
)

LOT_D_TABLES = {
    "secrets",
    "mcp_servers",
    "mcp_server_revisions",
    "mcp_probes",
    "mcp_bindings",
    "skills",
    "skill_revisions",
    "skill_bindings",
}


def _memory_engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture
def inspector():
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    try:
        yield inspect(engine)
    finally:
        engine.dispose()


def _unique_column_sets(inspector, table: str) -> set[tuple[str, ...]]:
    sets = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }
    sets |= {
        tuple(index["column_names"])
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    return sets


def test_create_all_creates_the_eight_lot_d_tables(inspector):
    assert LOT_D_TABLES <= set(inspector.get_table_names())


def test_models_map_to_the_expected_tables():
    assert SecretModel.__tablename__ == "secrets"
    assert McpServerModel.__tablename__ == "mcp_servers"
    assert McpServerRevisionModel.__tablename__ == "mcp_server_revisions"
    assert McpProbeModel.__tablename__ == "mcp_probes"
    assert McpBindingModel.__tablename__ == "mcp_bindings"
    assert SkillModel.__tablename__ == "skills"
    assert SkillRevisionModel.__tablename__ == "skill_revisions"
    assert SkillBindingModel.__tablename__ == "skill_bindings"


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("secrets", ("name", "scope_type", "project_id")),
        ("mcp_servers", ("name",)),
        ("mcp_server_revisions", ("server_id", "number")),
        ("mcp_bindings", ("server_id", "project_id")),
        ("skills", ("name",)),
        ("skill_revisions", ("skill_id", "number")),
        ("skill_bindings", ("skill_id", "project_id")),
    ],
)
def test_unique_constraints_are_declared(inspector, table: str, columns: tuple[str, ...]):
    assert columns in _unique_column_sets(inspector, table)


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("secrets", {"key_id", "ciphertext", "created_by_user_id", "rotated_at", "revoked_at", "last_used_at"}),
        ("mcp_servers", {"transport", "execution_location", "status", "current_revision_id", "target_worker_id", "last_probe_id", "revoked_reason"}),
        ("mcp_server_revisions", {"config", "fingerprint", "discovery", "discovery_fingerprint", "risk_flags", "change_summary", "requires_approval", "superseded_at"}),
        ("mcp_probes", {"authorization", "requested_by_user_id", "decided_by_user_id", "worker_id", "lease_expires_at", "result", "error", "expires_at"}),
        ("mcp_bindings", {"revision_id", "allowed_tools", "enabled", "revoked_at"}),
        ("skills", {"category", "kind", "source_kind", "origin", "status", "current_revision_id", "revoked_reason"}),
        ("skill_revisions", {"fingerprint", "files", "skill_md", "frontmatter", "license", "dependencies", "scan", "kind", "storage_path", "approval_fingerprint", "source_ref"}),
        ("skill_bindings", {"revision_id", "enabled", "revoked_at"}),
    ],
)
def test_expected_columns_exist(inspector, table: str, columns: set[str]):
    existing = {column["name"] for column in inspector.get_columns(table)}
    assert columns <= existing, columns - existing


def test_secret_ciphertext_never_stores_a_plain_column_named_value(inspector):
    assert "value" not in {column["name"] for column in inspector.get_columns("secrets")}


def test_foreign_keys_target_existing_tables(inspector):
    fks = {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspector.get_foreign_keys("mcp_probes")
    }
    assert ("mcp_servers", ("server_id",)) in fks
    assert ("mcp_server_revisions", ("revision_id",)) in fks
    assert ("workers", ("worker_id",)) in fks
    binding_fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("skill_bindings")}
    assert {"skills", "projects", "skill_revisions", "users"} <= binding_fks


@pytest.mark.sqlite
def test_init_db_stays_idempotent_on_an_existing_database(tmp_path, monkeypatch):
    database = tmp_path / "lot_d.db"
    monkeypatch.setenv("ACP_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()
    try:
        engine_module.init_db()
        engine = engine_module.get_engine()
        assert LOT_D_TABLES <= set(inspect(engine).get_table_names())
        # Deuxième passage sur une base déjà créée : aucune erreur, mêmes tables.
        engine_module.init_db()
        engine_module._upgrade_sqlite_schema(engine)
        inspector = inspect(engine)
        assert LOT_D_TABLES <= set(inspector.get_table_names())
        assert ("server_id", "number") in _unique_column_sets(inspector, "mcp_server_revisions")
    finally:
        engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()
