"""Options du moteur par URL : refus de pilotes, variables, chemin SQLite inchangé.

Ces vérifications portent sur le chemin PostgreSQL, que ``engine_options`` refuse
d'emprunter tant que le pilote n'est pas installé : sans lui, chaque cas rendrait le
refus de pilote au lieu du comportement testé. Le module est donc ignoré avec une
raison explicite plutôt que de produire une dizaine d'échecs trompeurs ; l'intégration
continue installe l'extra, c'est elle qui fait autorité.
"""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("psycopg") is None,
    reason=(
        "Pilote psycopg absent : installez « acp-database[postgresql] » pour "
        "exercer les options du moteur PostgreSQL"
    ),
)

from sqlalchemy import text

from acp_database import engine as engine_module
from acp_database.engine import engine_options, make_engine
from acp_database.testing import point_global_engine_at

PG_URL = "postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_h1"

DEFAULT_OPTIONS = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 5,
    "pool_timeout": 10,
    "connect_args": {
        "connect_timeout": 5,
        "application_name": "acp",
        "options": (
            "-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=30000 "
            "-c idle_in_transaction_session_timeout=60000"
        ),
    },
}

ENGINE_VARIABLES = (
    "ACP_DATABASE_POOL_SIZE",
    "ACP_DATABASE_MAX_OVERFLOW",
    "ACP_DATABASE_POOL_TIMEOUT_SECONDS",
    "ACP_DATABASE_CONNECT_TIMEOUT_SECONDS",
    "ACP_DATABASE_LOCK_TIMEOUT_MS",
    "ACP_DATABASE_STATEMENT_TIMEOUT_MS",
    "ACP_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS",
    "ACP_DATABASE_APPLICATION_NAME",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in ENGINE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.sqlite
def test_sqlite_options_are_unchanged():
    assert engine_options("sqlite:///./acp.db") == {
        "connect_args": {"check_same_thread": False}
    }
    assert engine_options("sqlite://") == {"connect_args": {"check_same_thread": False}}
    assert engine_options("sqlite+pysqlite:///x.db", maintenance=True) == {
        "connect_args": {"check_same_thread": False}
    }


def test_postgresql_defaults():
    assert engine_options(PG_URL) == DEFAULT_OPTIONS


def test_maintenance_drops_server_timeouts_only():
    options = engine_options(PG_URL, maintenance=True)
    assert options["connect_args"]["options"] == "-c timezone=UTC"
    assert {key: value for key, value in options.items() if key != "connect_args"} == {
        key: value for key, value in DEFAULT_OPTIONS.items() if key != "connect_args"
    }


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("ACP_DATABASE_POOL_SIZE", "12")
    monkeypatch.setenv("ACP_DATABASE_MAX_OVERFLOW", "0")
    monkeypatch.setenv("ACP_DATABASE_POOL_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("ACP_DATABASE_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("ACP_DATABASE_LOCK_TIMEOUT_MS", "1500")
    monkeypatch.setenv("ACP_DATABASE_STATEMENT_TIMEOUT_MS", "45000")
    monkeypatch.setenv("ACP_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS", "90000")
    monkeypatch.setenv("ACP_DATABASE_APPLICATION_NAME", "acp-worker")
    options = engine_options(PG_URL)
    assert (options["pool_size"], options["max_overflow"], options["pool_timeout"]) == (
        12,
        0,
        3,
    )
    assert options["connect_args"] == {
        "connect_timeout": 7,
        "application_name": "acp-worker",
        "options": (
            "-c timezone=UTC -c lock_timeout=1500 -c statement_timeout=45000 "
            "-c idle_in_transaction_session_timeout=90000"
        ),
    }


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("ACP_DATABASE_POOL_SIZE", "abc", "n'est pas un entier"),
        ("ACP_DATABASE_POOL_SIZE", "0", "inférieur au minimum 1"),
        ("ACP_DATABASE_MAX_OVERFLOW", "-1", "inférieur au minimum 0"),
        ("ACP_DATABASE_POOL_TIMEOUT_SECONDS", "1.5", "n'est pas un entier"),
        ("ACP_DATABASE_CONNECT_TIMEOUT_SECONDS", "0", "inférieur au minimum 1"),
        ("ACP_DATABASE_LOCK_TIMEOUT_MS", "cinq", "n'est pas un entier"),
        ("ACP_DATABASE_STATEMENT_TIMEOUT_MS", "-30000", "inférieur au minimum 1"),
        ("ACP_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS", "", None),
    ],
)
def test_invalid_variables_are_refused(monkeypatch, name, value, fragment):
    monkeypatch.setenv(name, value)
    if fragment is None:
        # Une variable vide vaut absence : la valeur par défaut s'applique.
        assert engine_options(PG_URL) == DEFAULT_OPTIONS
        return
    with pytest.raises(RuntimeError, match=f"Variable {name} invalide") as excinfo:
        engine_options(PG_URL)
    assert fragment in str(excinfo.value)


def test_invalid_variable_refuses_engine_construction(monkeypatch):
    monkeypatch.setenv("ACP_DATABASE_STATEMENT_TIMEOUT_MS", "beaucoup")
    with pytest.raises(RuntimeError, match="ACP_DATABASE_STATEMENT_TIMEOUT_MS"):
        make_engine(PG_URL)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://acp:acp@127.0.0.1:55432/acp_h1",
        "postgresql+psycopg2://acp:acp@127.0.0.1:55432/acp_h1",
        "postgresql+asyncpg://acp:acp@127.0.0.1:55432/acp_h1",
    ],
)
def test_other_postgresql_drivers_are_refused(url):
    with pytest.raises(RuntimeError, match="postgresql\\+psycopg"):
        engine_options(url)
    with pytest.raises(RuntimeError, match="refusé"):
        make_engine(url)


def test_unknown_dialects_are_refused():
    with pytest.raises(RuntimeError, match="non pris en charge"):
        engine_options("mysql+pymysql://x/y")
    with pytest.raises(RuntimeError, match="URL de base invalide"):
        engine_options("pas une url")


def test_missing_psycopg_names_the_extra(monkeypatch):
    monkeypatch.setattr(engine_module, "_psycopg_available", lambda: False)
    with pytest.raises(RuntimeError, match=r"acp-database\[postgresql\]"):
        engine_options(PG_URL)


@pytest.mark.sqlite
def test_make_engine_sqlite_enables_foreign_keys(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.sqlite
def test_get_engine_follows_environment(monkeypatch, tmp_path):
    url = f"sqlite:///{(tmp_path / 'global.db').as_posix()}"
    point_global_engine_at(monkeypatch, url)
    engine = engine_module.get_engine()
    assert engine.dialect.name == "sqlite"
    assert str(engine.url) == url
    assert engine_module.get_engine() is engine


def test_get_engine_refuses_invalid_url(monkeypatch):
    point_global_engine_at(monkeypatch, "postgresql://acp:acp@127.0.0.1:55432/acp_h1")
    with pytest.raises(RuntimeError, match="postgresql\\+psycopg"):
        engine_module.get_engine()


@pytest.mark.postgres
def test_postgresql_session_settings(postgresql_url):
    engine = make_engine(postgresql_url)
    maintenance = make_engine(postgresql_url, maintenance=True)
    try:
        with engine.connect() as connection:
            settings = {
                name: connection.execute(text(f"SHOW {name}")).scalar_one()
                for name in (
                    "timezone",
                    "lock_timeout",
                    "statement_timeout",
                    "idle_in_transaction_session_timeout",
                    "application_name",
                )
            }
        assert settings == {
            "timezone": "UTC",
            "lock_timeout": "5s",
            "statement_timeout": "30s",
            "idle_in_transaction_session_timeout": "1min",
            "application_name": "acp",
        }
        with maintenance.connect() as connection:
            assert connection.execute(text("SHOW timezone")).scalar_one() == "UTC"
            assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "0"
            assert connection.execute(text("SHOW lock_timeout")).scalar_one() == "0"
    finally:
        engine.dispose()
        maintenance.dispose()
