"""Outbox et journal sous PostgreSQL (base de test ``ACP_TEST_DATABASE_URL``, Lot H3).

Ce que SQLite ne peut pas prouver, et que ces tests prouvent sur un vrai
PostgreSQL 16 (schéma éphémère par test) :

- douze écrivains concurrents, chacun dans sa session, obtiennent des ``journal_seq``
  **contigus et ordonnés par commit** — c'est le verrou consultatif
  ``events.journal`` qui le garantit, pas ``FOR UPDATE`` ;
- le relais livre dans l'ordre exact de ``journal_seq`` ;
- deux relais parallèles (``SKIP LOCKED``) ne livrent jamais la même ligne ;
- une violation 23505 sur un index d'allocation, provoquée par une autre session,
  est reconnue par son diagnostic psycopg et rejouée jusqu'au succès ;
- la rétention retire les lignes d'outbox livrées **avant** leurs événements, sous
  une clé étrangère réellement appliquée.

Sans ``ACP_TEST_DATABASE_URL``, chaque test est ignoré avec sa raison ; avec
``ACP_TEST_DATABASE_REQUIRED=1`` et une base injoignable, il échoue.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from acp_api import events_bus
from acp_api.artifacts_storage import LocalArtifactStorage
from acp_api.events_bus import publish, store_event
from acp_api.outbox import RelayReport, relay_once
from acp_api.retention import purge_expired
from acp_contracts import Event
from acp_database.models import EventModel, EventOutboxModel
from acp_database.testing import make_test_engine, skip_or_fail_without_postgresql

pytestmark = pytest.mark.postgres

#: Horloge de test postérieure à l'horloge réelle (voir ``test_outbox``).
NOW = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
RELAY_ENVIRON = {
    "ACP_EVENT_SERVICE_URL": "https://events.test",
    "ACP_EVENT_SERVICE_TOKEN": "relay-secret",
}
WRITERS = 12


class SpyTransport:
    """Transport espion, sûr entre fils : enregistre chaque envoi avec son fil."""

    def __init__(self, *, delay_seconds: float = 0.0, outcomes: list[Any] | None = None):
        self.delay_seconds = delay_seconds
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def post(self, url: str, *, json: Any, headers: dict, timeout: float) -> httpx.Response:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        with self._lock:
            self.calls.append(
                {
                    "thread": threading.current_thread().name,
                    "event_id": json["id"],
                    "journal_seq": int(headers["X-ACP-Journal-Seq"]),
                }
            )
            outcome = self.outcomes.pop(0) if self.outcomes else 202
        if isinstance(outcome, BaseException):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", url))


@pytest.fixture
def pg_sessions(tmp_path, monkeypatch):
    """Fabrique de sessions sur un schéma PostgreSQL éphémère, relais d'outbox activé."""

    skip_or_fail_without_postgresql()
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")
    database = make_test_engine(tmp_path, concurrent=True)
    assert database.backend == "postgresql"
    try:
        yield sessionmaker(bind=database.engine, expire_on_commit=False)
    finally:
        database.close()


def _store(session_factory, count: int) -> list[Event]:
    events = [Event(type="task.progress", project_id="p") for _ in range(count)]
    with session_factory() as db:
        for event in events:
            store_event(db, event)
    return events


# --- 1. Douze écrivains concurrents ---------------------------------------------


@pytest.mark.concurrency
def test_twelve_concurrent_writers_get_contiguous_commit_ordered_journal_seqs(
    pg_sessions,
):
    """1..12 sans trou, et l'ordre des commits est l'ordre des numéros.

    Chaque écrivain garde sa transaction ouverte un instant après l'allocation :
    sans le verrou consultatif, un second écrivain allouerait le même numéro pendant
    cette fenêtre (``FOR UPDATE`` ne verrouille que la ligne maximale existante) et
    l'ordre des commits ne serait plus celui des numéros.
    """

    run_id = "run-concurrent"
    barrier = threading.Barrier(WRITERS)
    committed: list[tuple[float, str]] = []
    record_lock = threading.Lock()

    def write(index: int) -> str:
        event = Event(
            type="task.progress", project_id="p", task_run_id=run_id, payload={"i": index}
        )
        barrier.wait(timeout=10)
        with pg_sessions() as db:
            publish(db, event, commit=False)
            time.sleep(0.03)
            db.commit()
            stamp = time.monotonic()
        with record_lock:
            committed.append((stamp, event.id))
        return event.id

    with ThreadPoolExecutor(max_workers=WRITERS) as pool:
        event_ids = list(pool.map(write, range(WRITERS)))

    with pg_sessions() as db:
        rows = {
            row.id: row
            for row in db.query(EventModel).filter(EventModel.id.in_(event_ids)).all()
        }
        outbox = {
            row.event_id: row.journal_seq for row in db.query(EventOutboxModel).all()
        }
    assert sorted(rows[i].journal_seq for i in event_ids) == list(range(1, WRITERS + 1))
    assert sorted(rows[i].sequence for i in event_ids) == list(range(1, WRITERS + 1))
    by_commit = [rows[event_id].journal_seq for _, event_id in sorted(committed)]
    assert by_commit == list(range(1, WRITERS + 1)), "ordre de commit = ordre de numéro"
    assert {i: rows[i].journal_seq for i in event_ids} == outbox

    transport = SpyTransport()
    report = relay_once(pg_sessions, transport, now=NOW, environ=RELAY_ENVIRON)
    assert report == RelayReport(delivered=WRITERS, cursor_hint=WRITERS)
    assert [call["journal_seq"] for call in transport.calls] == list(range(1, WRITERS + 1))
    assert [call["event_id"] for call in transport.calls] == [
        event_id for _, event_id in sorted(committed)
    ]


# --- 2. Deux relais parallèles ----------------------------------------------------


@pytest.mark.concurrency
def test_two_parallel_relays_never_deliver_the_same_row(pg_sessions):
    """``SKIP LOCKED`` : chaque ligne part une seule fois, quel que soit le relais.

    Les deux relais se partagent réellement le lot : la réclamation est ligne à
    ligne, un verrou posé sur tout le lot aurait affamé le second relais.
    """

    events = _store(pg_sessions, 24)
    transport = SpyTransport(delay_seconds=0.01)
    started = threading.Barrier(2)

    def relay(name: str) -> RelayReport:
        threading.current_thread().name = name
        started.wait(timeout=10)
        return relay_once(pg_sessions, transport, now=NOW, environ=RELAY_ENVIRON)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(relay, ["relais-A", "relais-B"]))

    delivered_ids = [call["event_id"] for call in transport.calls]
    assert len(delivered_ids) == len(set(delivered_ids)) == 24
    assert set(delivered_ids) == {event.id for event in events}
    assert sum(report.delivered for report in reports) == 24
    assert all(not report.interrupted for report in reports)
    assert len({call["thread"] for call in transport.calls}) == 2, (
        "les deux relais ont réellement travaillé en parallèle"
    )
    with pg_sessions() as db:
        assert (
            db.query(EventOutboxModel).filter(EventOutboxModel.delivered_at.is_(None)).count()
            == 0
        )


# --- 3. Collision 23505 reconnue et rejouée -------------------------------------


def test_a_23505_collision_from_another_session_is_recognized_and_replayed(
    pg_sessions, monkeypatch
):
    """Une autre session prend le numéro alloué : le diagnostic psycopg est reconnu, l'écriture rejouée."""

    _store(pg_sessions, 1)
    real_allocate = events_bus.allocate_journal_seq
    real_recognize = events_bus._is_allocation_collision
    allocations: list[int] = []
    recognized: list[IntegrityError] = []

    def allocate_then_lose_the_race(db: Session) -> int:
        number = real_allocate(db)
        allocations.append(number)
        if len(allocations) == 1:
            # Une session concurrente, sans verrou, valide ce numéro avant nous.
            with pg_sessions() as rival:
                rival.add(
                    EventModel(
                        id="rival",
                        type="task.progress",
                        occurred_at=NOW,
                        payload={},
                        journal_seq=number,
                    )
                )
                rival.commit()
        return number

    def recognize(error: IntegrityError) -> bool:
        recognized.append(error)
        return real_recognize(error)

    monkeypatch.setattr(events_bus, "allocate_journal_seq", allocate_then_lose_the_race)
    monkeypatch.setattr(events_bus, "_is_allocation_collision", recognize)

    event = Event(type="task.progress", project_id="p")
    with pg_sessions() as db:
        model = store_event(db, event)
        assert model.journal_seq == 3

    assert allocations == [2, 3]
    (error,) = recognized
    assert error.orig.sqlstate == "23505"
    assert error.orig.diag.constraint_name == "uq_events_journal_seq"
    with pg_sessions() as db:
        numbers = sorted(seq for (seq,) in db.query(EventModel.journal_seq).all())
        assert numbers == [1, 2, 3]
        row = db.get(EventOutboxModel, event.id)
        assert row is not None and row.journal_seq == 3, (
            "la ligne d'outbox de l'essai perdu a été annulée avec son point de sauvegarde"
        )
        assert db.query(EventOutboxModel).count() == 2


# --- 4. Rétention sous clé étrangère appliquée -----------------------------------


def test_retention_removes_delivered_outbox_rows_before_their_events(
    pg_sessions, tmp_path
):
    """PostgreSQL applique la clé étrangère : l'ordre de suppression est prouvé ici."""

    old, recent = Event(type="task.progress", project_id="p"), Event(
        type="task.progress", project_id="p"
    )
    with pg_sessions() as db:
        old_model = store_event(db, old, commit=False)
        old_model.occurred_at = NOW - timedelta(days=400)
        recent_model = store_event(db, recent, commit=False)
        recent_model.occurred_at = NOW - timedelta(days=1)
        db.commit()
    transport = SpyTransport()
    assert relay_once(pg_sessions, transport, now=NOW, environ=RELAY_ENVIRON).delivered == 2

    with pg_sessions() as db:
        report = purge_expired(
            db, LocalArtifactStorage(tmp_path / "blobs"), now=NOW, apply=True
        )

    assert report.events_deleted == 1
    with pg_sessions() as db:
        assert [row.id for row in db.query(EventModel).all()] == [recent.id]
        assert [row.event_id for row in db.query(EventOutboxModel).all()] == [recent.id]


def test_retention_keeps_an_event_whose_delivery_failed(pg_sessions, tmp_path):
    (event,) = _store(pg_sessions, 1)
    with pg_sessions() as db:
        db.get(EventModel, event.id).occurred_at = NOW - timedelta(days=400)
        db.commit()
    assert relay_once(
        pg_sessions,
        SpyTransport(outcomes=[503]),
        now=NOW,
        environ=RELAY_ENVIRON,
    ).failed == 1

    with pg_sessions() as db:
        report = purge_expired(
            db, LocalArtifactStorage(tmp_path / "blobs"), now=NOW, apply=True
        )

    assert report.events_deleted == 0
    assert report.events_pending_relay == 1
    with pg_sessions() as db:
        assert db.query(EventModel).count() == 1
