"""Le moteur de test applique les clés étrangères comme le moteur de l'application.

``make_engine`` active ``PRAGMA foreign_keys=ON`` à chaque connexion SQLite : pysqlite
ne les applique pas par défaut, et le schéma en dépend (``event_outbox.event_id`` n'a
volontairement aucune cascade). Un moteur de test qui ne le ferait pas laisserait
passer au vert, sur le seul dialecte de l'intégration continue par défaut, une
suppression ou une référence pendante que la production refuse (23503 sous
PostgreSQL, ``FOREIGN KEY constraint failed`` sous SQLite).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

from acp_database.models import EventOutboxModel
from acp_database.testing import make_test_engine

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


@pytest.mark.sqlite
@pytest.mark.parametrize("concurrent", [False, True], ids=["memoire", "fichier"])
def test_the_sqlite_test_engine_enables_foreign_keys_on_every_connection(
    tmp_path, concurrent
):
    with make_test_engine(tmp_path, concurrent=concurrent) as database:
        # Deux connexions simultanées : sur ``QueuePool``, la seconde est neuve et
        # doit, elle aussi, être passée par l'écouteur.
        with database.engine.connect() as first, database.engine.connect() as second:
            assert first.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert second.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


@pytest.mark.sqlite
def test_a_bare_sqlite_test_engine_enables_foreign_keys_too(tmp_path):
    """``create_schema=False`` sert aux bases historiques : même réglage de connexion."""

    with make_test_engine(tmp_path, concurrent=True, create_schema=False) as database:
        with database.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_the_test_engine_refuses_a_dangling_outbox_row(tmp_path):
    """Sur les deux dialectes, une ligne d'outbox sans événement est refusée."""

    with make_test_engine(tmp_path) as database:
        with pytest.raises(IntegrityError):
            with database.engine.begin() as connection:
                connection.execute(
                    insert(EventOutboxModel).values(
                        event_id=str(uuid4()),
                        journal_seq=1,
                        consumer="event-service",
                        attempts=0,
                        next_attempt_at=NOW,
                        last_error="",
                        created_at=NOW,
                    )
                )
