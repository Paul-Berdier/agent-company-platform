"""Crochets communs à toutes les suites Python du dépôt.

Le marqueur ``sqlite`` (``pytest.ini``) désigne un test qui exige le moteur SQLite :
lecture de ``sqlite_master``, parité de mise à niveau SQLite, comportement propre à
pysqlite. Tant que rien ne l'appliquait, la suite complète lancée avec
``ACP_TEST_DATABASE_URL`` exécutait ces tests contre PostgreSQL et échouait ; ils sont
désormais ignorés, avec leur raison, quand la base de test est PostgreSQL. Le job
SQLite de l'intégration continue les exécute.
"""

from __future__ import annotations

import pytest

from acp_database.testing import database_backend


def pytest_collection_modifyitems(config, items):
    if database_backend() != "postgresql":
        return
    skip = pytest.mark.skip(
        reason="test propre à SQLite : ACP_TEST_DATABASE_URL désigne PostgreSQL"
    )
    for item in items:
        if item.get_closest_marker("sqlite") is not None:
            item.add_marker(skip)
