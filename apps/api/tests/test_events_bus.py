"""Relais direct, porte du relais d'outbox, collisions et verrou du journal.

Les tests ``test_forwarder_*`` décrivent le relais direct **sans**
``ACP_EVENT_RELAY_ENABLED`` : ils restent vrais tels quels. Les suivants couvrent
le Lot H3 : la porte dans ``forward_event`` lui-même, la reconnaissance d'une
collision par le diagnostic psycopg, et le verrou pris avant toute allocation sur
les deux chemins d'écriture.
"""

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from acp_api import events_bus
from acp_contracts import Event
from acp_database.models import EventModel
from acp_database.testing import make_test_engine


class _RecordingAsyncClient:
    def __init__(self, calls: list[dict], **_kwargs):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        request = httpx.Request("POST", url)
        return httpx.Response(202, request=request)


@pytest.mark.asyncio
async def test_forwarder_sends_secret_only_in_authorization_header(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "forwarder-secret")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "https://events.test")
    monkeypatch.setattr(
        events_bus.httpx,
        "AsyncClient",
        lambda **kwargs: _RecordingAsyncClient(calls, **kwargs),
    )

    await events_bus.forward_event(Event(type="task.progress"))

    assert len(calls) == 1
    assert calls[0]["url"] == "https://events.test/internal/events"
    assert calls[0]["headers"] == {
        "Authorization": "Bearer forwarder-secret"
    }
    assert "forwarder-secret" not in calls[0]["url"]


@pytest.mark.asyncio
async def test_forwarder_disables_environment_proxies_for_bearer_requests(monkeypatch):
    calls: list[dict] = []
    client_options: list[dict] = []
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "forwarder-secret")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "https://events.test")

    def client_factory(**kwargs):
        client_options.append(kwargs)
        return _RecordingAsyncClient(calls, **kwargs)

    monkeypatch.setattr(events_bus.httpx, "AsyncClient", client_factory)

    await events_bus.forward_event(Event(type="task.progress"))

    assert len(calls) == 1
    assert len(client_options) == 1
    assert client_options[0]["trust_env"] is False


@pytest.mark.asyncio
async def test_forwarder_makes_no_request_without_service_token(monkeypatch):
    calls: list[dict] = []
    monkeypatch.delenv("ACP_EVENT_SERVICE_TOKEN", raising=False)
    monkeypatch.setattr(
        events_bus.httpx,
        "AsyncClient",
        lambda **kwargs: _RecordingAsyncClient(calls, **kwargs),
    )

    await events_bus.forward_event(Event(type="task.progress"))

    assert calls == []


@pytest.mark.asyncio
async def test_forwarder_makes_no_request_to_an_insecure_origin(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "forwarder-secret")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "http://events.example")
    monkeypatch.setattr(
        events_bus.httpx,
        "AsyncClient",
        lambda **kwargs: _RecordingAsyncClient(calls, **kwargs),
    )

    await events_bus.forward_event(Event(type="task.progress"))

    assert calls == []


# --- Lot H3 : porte du relais d'outbox -----------------------------------------


@pytest.mark.asyncio
async def test_forwarder_is_silent_when_the_outbox_relay_is_enabled(monkeypatch):
    """Avec ``ACP_EVENT_RELAY_ENABLED=1``, aucun POST direct : l'outbox est l'unique chemin."""

    calls: list[dict] = []
    client_factories: list[dict] = []
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "forwarder-secret")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "https://events.test")

    def client_factory(**kwargs):
        client_factories.append(kwargs)
        return _RecordingAsyncClient(calls, **kwargs)

    monkeypatch.setattr(events_bus.httpx, "AsyncClient", client_factory)

    await events_bus.forward_event(Event(type="task.progress"))

    assert calls == []
    assert client_factories == [], "aucun client HTTP n'est même construit"


@pytest.mark.asyncio
async def test_forwarder_still_posts_when_the_variable_is_not_exactly_one(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "true")
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "forwarder-secret")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "https://events.test")
    monkeypatch.setattr(
        events_bus.httpx,
        "AsyncClient",
        lambda **kwargs: _RecordingAsyncClient(calls, **kwargs),
    )

    await events_bus.forward_event(Event(type="task.progress"))

    assert len(calls) == 1


# --- Lot H3 : reconnaissance d'une collision -----------------------------------


def _integrity_error(message: str, *, sqlstate=None, constraint=None) -> IntegrityError:
    """``IntegrityError`` dont l'``orig`` imite psycopg (``sqlstate``, ``diag``)."""

    class _Original:
        def __init__(self) -> None:
            self.sqlstate = sqlstate
            self.diag = SimpleNamespace(constraint_name=constraint)

        def __str__(self) -> str:
            return message

    return IntegrityError("INSERT INTO events", {}, _Original())


@pytest.mark.parametrize(
    "constraint", ["uq_event_run_sequence", "uq_events_journal_seq"]
)
def test_a_psycopg_unique_violation_on_an_allocation_index_is_a_collision(constraint):
    """Le diagnostic structuré suffit : le message peut être dans n'importe quelle langue."""

    error = _integrity_error(
        "la valeur d'une clé dupliquée rompt la contrainte unique",
        sqlstate="23505",
        constraint=constraint,
    )
    assert events_bus._is_allocation_collision(error) is True


def test_a_psycopg_unique_violation_on_another_constraint_is_not_a_collision():
    error = _integrity_error(
        "duplicate key value violates unique constraint",
        sqlstate="23505",
        constraint="events_pkey",
    )
    assert events_bus._is_allocation_collision(error) is False
    # Même index, mais un autre SQLSTATE (clé étrangère, par exemple) : pas une collision.
    error = _integrity_error("x", sqlstate="23503", constraint="uq_events_journal_seq")
    assert events_bus._is_allocation_collision(error) is False


def test_sqlite_text_markers_are_still_recognized():
    error = _integrity_error(
        "UNIQUE constraint failed: events.task_run_id, events.sequence"
    )
    assert events_bus._is_allocation_collision(error) is True
    error = _integrity_error("UNIQUE constraint failed: events.id")
    assert events_bus._is_allocation_collision(error) is False


# --- Lot H3 : verrou avant allocation, sur les deux chemins ---------------------


@pytest.fixture
def journal_db(tmp_path):
    database = make_test_engine(tmp_path, concurrent=True)
    try:
        yield sessionmaker(bind=database.engine, expire_on_commit=False)
    finally:
        database.close()


def _spy_allocation(monkeypatch) -> list[str]:
    """Trace ``write_lock`` et les deux allocations, dans l'ordre d'appel."""

    trace: list[str] = []
    real_lock = events_bus.write_lock
    real_journal = events_bus.allocate_journal_seq
    real_sequence = events_bus.allocate_sequence

    def lock(db, key):
        trace.append(f"lock:{key}")
        real_lock(db, key)

    def journal(db):
        trace.append("journal")
        return real_journal(db)

    def sequence(db, run_id):
        trace.append("sequence")
        return real_sequence(db, run_id)

    monkeypatch.setattr(events_bus, "write_lock", lock)
    monkeypatch.setattr(events_bus, "allocate_journal_seq", journal)
    monkeypatch.setattr(events_bus, "allocate_sequence", sequence)
    return trace


def test_publish_takes_the_journal_lock_then_allocates_journal_then_sequence(
    journal_db, monkeypatch
):
    trace = _spy_allocation(monkeypatch)
    with journal_db() as db:
        events_bus.publish(db, Event(type="task.progress", project_id="p", task_run_id="r"))
    assert trace == ["lock:events.journal", "journal", "sequence"]
    assert events_bus.JOURNAL_LOCK_KEY == "events.journal"


def test_store_event_takes_the_same_lock_and_allocates_in_the_same_order(
    journal_db, monkeypatch
):
    """Le chemin des appelants directs suit exactement la discipline de ``publish``."""

    trace = _spy_allocation(monkeypatch)
    with journal_db() as db:
        model = events_bus.store_event(
            db, Event(type="task.completed", project_id="p", task_run_id="r")
        )
        assert (model.journal_seq, model.sequence) == (1, 1)
    assert trace == ["lock:events.journal", "journal", "sequence"]


@pytest.mark.sqlite
def test_the_lock_is_held_by_the_callers_transaction_until_commit(tmp_path, monkeypatch):
    """``commit=False`` : le verrou (BEGIN IMMEDIATE) reste celui de l'appelant."""

    monkeypatch.delenv("ACP_TEST_DATABASE_URL", raising=False)
    database = make_test_engine(tmp_path, concurrent=True)
    journal_db = sessionmaker(bind=database.engine, expire_on_commit=False)
    with journal_db() as db:
        events_bus.store_event(db, Event(type="task.progress", project_id="p"), commit=False)
        driver = db.connection().connection.driver_connection
        assert driver.in_transaction is True
        with journal_db() as observer:
            assert observer.query(EventModel).count() == 0
        db.commit()
    with journal_db() as db:
        assert db.query(EventModel).count() == 1
    database.close()
