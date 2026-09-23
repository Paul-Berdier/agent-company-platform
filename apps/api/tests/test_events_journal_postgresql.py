"""Le verrou du journal est le dernier verrou de la transaction (0.9.1), sous PostgreSQL.

Jusqu'en 0.9.0, ``publish`` et ``store_event`` prenaient
``pg_advisory_xact_lock('events.journal')`` au moment de la publication, au milieu de
la transaction métier, et le gardaient jusqu'au commit. Deux conséquences :

- une transaction qui verrouillait une ligne **après** avoir publié s'opposait à une
  autre qui publiait **après** avoir verrouillé cette ligne : interblocage (40P01),
  observé entre le tick du planificateur et les routes d'automatisation ;
- toute transaction qui publiait tôt bloquait toutes les autres publications jusqu'à
  son commit, au-delà du ``lock_timeout`` (55P03) pour une ingestion un peu longue.

Les numéros sont désormais attribués au commit : ces tests échouent sur l'ancien
``events_bus`` (interblocage, attente du verrou) et passent sur le nouveau.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from acp_api.events_bus import publish
from acp_contracts import Event
from acp_database.models import EventModel, OrganizationModel
from acp_database.testing import make_test_engine, skip_or_fail_without_postgresql

pytestmark = [pytest.mark.postgres, pytest.mark.concurrency]


@pytest.fixture
def session_factory(tmp_path):
    skip_or_fail_without_postgresql()
    database = make_test_engine(tmp_path, concurrent=True)
    assert database.backend == "postgresql"
    try:
        yield sessionmaker(bind=database.engine, expire_on_commit=False)
    finally:
        database.close()


def _organizations(session_factory, *names: str) -> list[str]:
    with session_factory() as db:
        rows = [OrganizationModel(name=name) for name in names]
        db.add_all(rows)
        db.commit()
        return [row.id for row in rows]


def _lock(db, organization_id: str) -> None:
    db.execute(
        select(OrganizationModel.id)
        .where(OrganizationModel.id == organization_id)
        .with_for_update()
    ).one()


def _journal(session_factory) -> list[tuple[str, int]]:
    with session_factory() as db:
        rows = db.query(EventModel).order_by(EventModel.journal_seq).all()
        return [(row.type, row.journal_seq) for row in rows]


def test_publishing_between_two_row_locks_no_longer_deadlocks(session_factory):
    """Motif du planificateur contre une route d'automatisation (K4).

    Le tick verrouille la routine A, publie une alerte, puis verrouille la routine
    B ; la route verrouille B, publie, puis valide. Avec le verrou du journal pris à
    la publication, le tick le tenait en attendant B, et la route attendait le
    journal en tenant B : PostgreSQL annulait l'une des deux (40P01, 500).
    """

    first, second = _organizations(session_factory, "Routine A", "Routine B")
    route = session_factory()
    tick = session_factory()
    failures: list[BaseException] = []
    try:
        _lock(route, second)
        _lock(tick, first)
        publish(tick, Event(type="alert.opened", project_id="p"), commit=False, forward=False)

        def tick_continues() -> None:
            try:
                _lock(tick, second)
                tick.commit()
            except BaseException as exc:  # pragma: no cover - diagnostic
                failures.append(exc)
                tick.rollback()

        waiting = threading.Thread(target=tick_continues)
        waiting.start()
        waiting.join(1.0)
        assert waiting.is_alive(), "le tick doit attendre le verrou de la routine B"

        publish(route, Event(type="automation.updated", project_id="p"), commit=False, forward=False)
        route.commit()
        waiting.join(30)
        assert not waiting.is_alive()
    finally:
        route.close()
        tick.close()

    assert not failures, failures
    # Numérotés dans l'ordre des commits : la route a validé la première.
    assert _journal(session_factory) == [("automation.updated", 1), ("alert.opened", 2)]


def test_an_open_publication_does_not_block_other_publishers(session_factory):
    """Une transaction qui a publié sans valider ne retient plus le journal.

    Auparavant, la seconde publication attendait le commit de la première, au-delà
    du ``lock_timeout`` si celle-ci durait (ingestion d'un gros rapport de tests).
    """

    slow = session_factory()
    outcome: list[object] = []
    try:
        publish(slow, Event(type="test.case.finished", project_id="p"), commit=False, forward=False)

        def other_publisher() -> None:
            try:
                with session_factory() as db:
                    publish(db, Event(type="task.created", project_id="p"), forward=False)
                outcome.append("committed")
            except BaseException as exc:  # pragma: no cover - diagnostic
                outcome.append(exc)

        other = threading.Thread(target=other_publisher)
        other.start()
        other.join(5)
        assert not other.is_alive(), "la seconde publication ne doit pas attendre la première"
        assert outcome == ["committed"]
        slow.commit()
    finally:
        slow.close()

    assert _journal(session_factory) == [("task.created", 1), ("test.case.finished", 2)]


def test_numbers_and_run_sequences_follow_commit_order(session_factory):
    """Deux transactions sur la même tentative : la séquence suit l'ordre des commits."""

    early = session_factory()
    try:
        publish(
            early,
            Event(type="task.progress", project_id="p", task_run_id="run-1"),
            commit=False,
            forward=False,
        )
        with session_factory() as late:
            publish(
                late,
                Event(type="task.completed", project_id="p", task_run_id="run-1"),
                forward=False,
            )
        early.commit()
    finally:
        early.close()

    with session_factory() as db:
        rows = db.query(EventModel).order_by(EventModel.journal_seq).all()
        assert [(row.type, row.journal_seq, row.sequence) for row in rows] == [
            ("task.completed", 1, 1),
            ("task.progress", 2, 2),
        ]
