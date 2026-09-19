"""Relais direct, porte du relais d'outbox, collisions et verrou du journal.

Les tests ``test_forwarder_*`` décrivent le relais direct **sans**
``ACP_EVENT_RELAY_ENABLED`` : ils restent vrais tels quels. Les suivants couvrent
le Lot H3 : la porte dans ``forward_event`` lui-même, la reconnaissance d'une
collision par le diagnostic psycopg, puis 0.9.1 : numéros attribués au commit, sous
le verrou du journal pris en dernier, et annonces (réveil, relais) au seul commit de
la transaction racine.
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


# --- 0.9.1 : numéros attribués au commit, sous le verrou du journal -------------


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


def _lock_taken_at_publication(db) -> list[str]:
    """Ce qui précède le commit : le ``BEGIN IMMEDIATE`` sous SQLite, rien sous PostgreSQL."""

    return ["lock:events.journal"] if db.get_bind().dialect.name == "sqlite" else []


def test_publish_numbers_at_commit_under_the_journal_lock(journal_db, monkeypatch):
    """0.9.1 : rien n'est alloué à la publication ; le commit prend le verrou du
    journal, puis alloue journal et tentative, dans cet ordre."""

    trace = _spy_allocation(monkeypatch)
    with journal_db() as db:
        sequence = events_bus.publish(
            db, Event(type="task.progress", project_id="p", task_run_id="r"), commit=False
        )
        before_commit = list(trace)
        db.commit()
        assert before_commit == _lock_taken_at_publication(db)
    assert sequence is None
    assert trace[len(before_commit):] == ["lock:events.journal", "journal", "sequence"]
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
        published_first = _lock_taken_at_publication(db)
    assert trace == [*published_first, "lock:events.journal", "journal", "sequence"]


def test_a_committed_publish_returns_the_sequence_given_at_commit(journal_db):
    with journal_db() as db:
        first = events_bus.publish(db, Event(type="task.progress", project_id="p", task_run_id="r"))
        second = events_bus.publish(db, Event(type="task.progress", project_id="p", task_run_id="r"))
        untracked = events_bus.publish(db, Event(type="project.updated", project_id="p"))
    assert (first, second, untracked) == (1, 2, None)


def test_events_of_one_transaction_are_numbered_in_publication_order(journal_db):
    with journal_db() as db:
        for index in range(3):
            events_bus.store_event(
                db,
                Event(type="task.progress", project_id="p", task_run_id="r", payload={"i": index}),
                commit=False,
            )
        events_bus.store_event(db, Event(type="project.updated", project_id="p"), commit=False)
        db.commit()
    with journal_db() as db:
        rows = db.query(EventModel).order_by(EventModel.journal_seq).all()
    assert [(row.journal_seq, row.sequence) for row in rows] == [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, None),
    ]
    assert [row.payload.get("i") for row in rows] == [0, 1, 2, None]


def test_a_rolled_back_savepoint_drops_only_its_own_events(journal_db):
    """Un point de sauvegarde annulé retire ses événements, pas ceux publiés avant lui ;
    sa libération ne numérote rien avant le commit de la transaction racine."""

    with journal_db() as db:
        events_bus.store_event(db, Event(type="task.progress", project_id="p"), commit=False)
        with db.begin_nested():
            events_bus.store_event(db, Event(type="task.kept", project_id="p"), commit=False)
        assert db.query(EventModel.journal_seq).filter_by(type="task.kept").scalar() is None
        savepoint = db.begin_nested()
        events_bus.store_event(db, Event(type="task.dropped", project_id="p"), commit=False)
        db.flush()
        savepoint.rollback()
        db.commit()
    with journal_db() as db:
        rows = db.query(EventModel).order_by(EventModel.journal_seq).all()
    assert [(row.type, row.journal_seq) for row in rows] == [
        ("task.progress", 1),
        ("task.kept", 2),
    ]


def test_a_rolled_back_transaction_leaves_nothing_to_number(journal_db):
    with journal_db() as db:
        events_bus.store_event(db, Event(type="task.lost", project_id="p"), commit=False)
        db.rollback()
        events_bus.store_event(db, Event(type="task.kept", project_id="p"), commit=False)
        db.commit()
    with journal_db() as db:
        rows = db.query(EventModel).all()
    assert [(row.type, row.journal_seq) for row in rows] == [("task.kept", 1)]


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


# --- 0.9.1 : annonces (réveil et relais) au commit de la transaction racine ------


class _Background:
    """Espion de ``BackgroundTasks`` : retient les relais programmés."""

    def __init__(self) -> None:
        self.tasks: list[tuple] = []

    def add_task(self, function, *args) -> None:
        self.tasks.append((function, *args))


def _drain(queue) -> list[int]:
    values = []
    while not queue.empty():
        values.append(queue.get_nowait())
    return values


def test_a_deferred_publication_is_announced_only_at_the_root_commit(journal_db):
    """Ni réveil ni relais avant le commit racine, même à la libération d'un point
    de sauvegarde (SQLAlchemy y émet pourtant ``after_commit``)."""

    channel = events_bus.project_channel("p-announce")
    queue = events_bus.event_hub.subscribe(channel)
    background = _Background()
    event = Event(type="task.progress", project_id="p-announce", task_run_id="r")
    try:
        with journal_db() as db:
            events_bus.publish(db, event, commit=False, background=background)
            with db.begin_nested():
                events_bus.store_event(db, Event(type="task.note", project_id="x"), commit=False)
            assert _drain(queue) == [] and background.tasks == []
            db.commit()
        assert _drain(queue) == [1]
        assert background.tasks == [(events_bus.forward_event, event)]
    finally:
        events_bus.event_hub.unsubscribe(channel, queue)


def test_a_rolled_back_publication_neither_wakes_nor_forwards(journal_db):
    channel = events_bus.project_channel("p-rollback")
    queue = events_bus.event_hub.subscribe(channel)
    background = _Background()
    try:
        with journal_db() as db:
            events_bus.publish(
                db,
                Event(type="task.progress", project_id="p-rollback"),
                commit=False,
                background=background,
            )
            db.rollback()
            # Une transaction suivante validée n'annonce pas l'événement annulé.
            events_bus.store_event(db, Event(type="task.other", project_id="x"))
        assert _drain(queue) == []
        assert background.tasks == []
    finally:
        events_bus.event_hub.unsubscribe(channel, queue)
