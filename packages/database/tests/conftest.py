"""Fixtures communes du paquet ``acp_database``, bâties sur ``acp_database.testing``."""

import pytest

from acp_database.testing import (
    database_backend,
    make_test_engine,
    skip_or_fail_without_postgresql,
)


@pytest.fixture
def database_url(tmp_path):
    """URL de la base de test : PostgreSQL si configurée, sinon un fichier SQLite."""

    if database_backend() == "postgresql":
        return skip_or_fail_without_postgresql()
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def test_engine(tmp_path):
    """Moteur prêt à l'emploi (schéma créé), fermé et nettoyé en fin de test."""

    database = make_test_engine(tmp_path)
    try:
        yield database.engine
    finally:
        database.close()


@pytest.fixture
def postgresql_url():
    """URL PostgreSQL de test ; ignore le test (ou échoue si exigée) sinon."""

    return skip_or_fail_without_postgresql()
