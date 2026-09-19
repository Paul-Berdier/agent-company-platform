"""Garde de ``reset_public_schema`` : jamais de remise à zéro d'une base non prouvée jetable.

Avant 0.9.1, ``reset_public_schema`` exécutait ``DROP SCHEMA public CASCADE`` sur
n'importe quelle URL PostgreSQL. Une variable ``ACP_TEST_DATABASE_URL`` pointée par
erreur sur la base de production effaçait tout le schéma applicatif au premier test.

Les refus qui ne demandent aucune base tournent partout ; ceux qui touchent une base
réelle utilisent une base dédiée ``<base>_guard``, créée à la demande sur le serveur de
test et jamais celle du lot.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from acp_database.testing import (
    TEST_DATABASE_MARKER,
    UnsafeTestDatabaseError,
    reset_public_schema,
    skip_or_fail_without_postgresql,
)

#: Hôte réservé (RFC 2606) : une connexion y échouerait, ce qui prouve que le refus
#: intervient avant tout accès réseau.
UNREACHABLE = "postgresql+psycopg://acp:secret@db.invalid:5432/production"


@pytest.mark.parametrize("variable", ["ACP_DATABASE_URL", "DATABASE_URL"])
def test_refuses_the_database_of_the_application(variable):
    # Même base, autre mot de passe, autre pilote et casse d'hôte différente.
    launched = {variable: "postgres://acp:autre@DB.INVALID/production"}

    with pytest.raises(UnsafeTestDatabaseError) as refused:
        reset_public_schema(UNREACHABLE, application_urls=launched)

    message = str(refused.value)
    assert variable in message
    assert "refusée" in message
    assert "secret" not in message and "autre" not in message


def test_refuses_a_non_postgresql_url():
    with pytest.raises(UnsafeTestDatabaseError):
        reset_public_schema("sqlite:///./acp.db", application_urls={})


def test_another_database_of_the_same_server_is_not_the_application():
    launched = {"ACP_DATABASE_URL": "postgresql+psycopg://acp:x@db.invalid/production"}

    # Le refus « base applicative » ne vise que la même base ; ici, c'est la
    # connexion elle-même qui échoue, jamais un DROP.
    with pytest.raises(Exception) as failure:
        reset_public_schema(
            "postgresql+psycopg://acp:x@db.invalid/production_test", application_urls=launched
        )
    assert not isinstance(failure.value, UnsafeTestDatabaseError)


def test_a_redirection_made_by_a_test_is_not_the_application_database(monkeypatch):
    # Les tests de disponibilité pointent eux-mêmes ACP_DATABASE_URL sur leur base :
    # seul compte l'environnement relevé au lancement de la suite.
    monkeypatch.setenv("ACP_DATABASE_URL", UNREACHABLE)

    with pytest.raises(Exception) as failure:
        reset_public_schema(UNREACHABLE)
    assert not isinstance(failure.value, UnsafeTestDatabaseError)


def test_a_suite_launched_against_the_application_database_is_refused(tmp_path):
    script = (
        "from acp_database.testing import UnsafeTestDatabaseError, reset_public_schema\n"
        "try:\n"
        f"    reset_public_schema({UNREACHABLE!r})\n"
        "except UnsafeTestDatabaseError as refus:\n"
        "    print('REFUS', refus)\n"
        "    raise SystemExit(7)\n"
    )
    # Le refus est en français : sous Windows, un tube est encodé en cp1252 par
    # défaut, et le relire en UTF-8 perdrait toute la sortie.
    environment = {**os.environ, "ACP_DATABASE_URL": UNREACHABLE, "PYTHONIOENCODING": "utf-8"}
    environment.pop("DATABASE_URL", None)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 7, completed.stderr
    assert "ACP_DATABASE_URL" in completed.stdout


# --- Contre une base réelle ---------------------------------------------------


def _admin(url: str):
    return create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")


@pytest.fixture
def guard_url():
    """Base ``<base>_guard`` vierge : ni marqueur, ni objet dans ``public``."""

    base_url = skip_or_fail_without_postgresql()
    parsed = make_url(base_url)
    name = f"{parsed.database}_guard"
    admin = _admin(base_url)
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    url = parsed.set(database=name).render_as_string(hide_password=False)
    guard = _admin(url)
    try:
        with guard.connect() as connection:
            connection.execute(text(f'COMMENT ON DATABASE "{name}" IS NULL'))
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        guard.dispose()
    return url


def _marked(url: str) -> bool:
    engine = _admin(url)
    try:
        with engine.connect() as connection:
            return (
                connection.execute(
                    text(
                        "SELECT shobj_description(d.oid, 'pg_database') FROM pg_database d "
                        "WHERE d.datname = current_database()"
                    )
                ).scalar()
                == TEST_DATABASE_MARKER
            )
    finally:
        engine.dispose()


def _create_table(url: str, name: str) -> None:
    engine = _admin(url)
    try:
        with engine.connect() as connection:
            connection.execute(text(f"CREATE TABLE public.{name} (id integer)"))
            connection.execute(text(f"INSERT INTO public.{name} VALUES (1)"))
    finally:
        engine.dispose()


def _public_tables(url: str) -> list[str]:
    engine = _admin(url)
    try:
        with engine.connect() as connection:
            return list(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_an_empty_database_is_reset_and_marked_as_a_test_database(guard_url):
    assert not _marked(guard_url)

    reset_public_schema(guard_url)

    assert _marked(guard_url)
    assert _public_tables(guard_url) == []


@pytest.mark.postgres
def test_a_populated_unmarked_database_is_refused_and_left_intact(guard_url):
    _create_table(guard_url, "donnees_reelles")

    with pytest.raises(UnsafeTestDatabaseError) as refused:
        reset_public_schema(guard_url)

    assert _public_tables(guard_url) == ["donnees_reelles"]
    assert not _marked(guard_url)
    assert f"IS '{TEST_DATABASE_MARKER}'" in str(refused.value)


@pytest.mark.postgres
def test_a_marked_database_is_reset_even_after_an_interrupted_run(guard_url):
    reset_public_schema(guard_url)
    # Un lot interrompu laisse ses tables derrière lui : la base, marquée, reste
    # réutilisable sans intervention manuelle.
    _create_table(guard_url, "reste_d_un_lot")

    reset_public_schema(guard_url)

    assert _public_tables(guard_url) == []
    assert _marked(guard_url)
