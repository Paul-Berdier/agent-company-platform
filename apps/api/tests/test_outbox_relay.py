"""Commande ``python -m acp_api.outbox_relay`` : codes de sortie, boucle et lettres mortes.

Les codes sont la seule interface qu'un orchestrateur lit : ``0`` succès, ``2``
usage ou configuration invalide, ``3`` lot ``--once`` interrompu par le transport.
La boucle ``--follow`` est exercée avec un drapeau d'arrêt injecté : aucun signal
réel n'est envoyé, aucune attente n'est illimitée.
"""

from __future__ import annotations

import io
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from acp_api.events_bus import store_event
from acp_api.outbox import RelayReport, list_dead
from acp_api.outbox_relay import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
from acp_api import outbox_relay
from acp_contracts import Event
from acp_database.models import EventOutboxModel
from acp_database.testing import make_test_engine

#: Horloge de test postérieure à l'horloge réelle (voir ``test_outbox``).
NOW = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)


class SpyTransport:
    """Transport espion : rejoue ``outcomes`` (statut ou exception) puis répond 202.

    Copie volontaire de celui de ``test_outbox`` : le mode d'import ``importlib``
    n'autorise pas l'import d'un module de test voisin.
    """

    def __init__(self, outcomes: list | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict] = []

    def post(self, url: str, *, json, headers: dict, timeout: float) -> httpx.Response:
        self.calls.append(
            {"url": url, "json": json, "headers": dict(headers), "timeout": timeout}
        )
        outcome = self.outcomes.pop(0) if self.outcomes else 202
        if isinstance(outcome, BaseException):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", url), text="ko")


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")
    monkeypatch.setenv("ACP_EVENT_SERVICE_URL", "https://events.test")
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "relay-secret")
    monkeypatch.delenv("ACP_OUTBOX_MAX_ATTEMPTS", raising=False)
    database = make_test_engine(tmp_path, concurrent=True)
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


def _run(argv, **kwargs) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


# --- --once -----------------------------------------------------------------------


def test_once_returns_zero_after_a_complete_batch(session_factory):
    _store(session_factory, 3)
    transport = SpyTransport()

    code, out, err = _run(["--once"], session_factory=session_factory, transport=transport)

    assert code == EXIT_OK
    assert "livrés : 3" in out
    assert err == ""
    assert len(transport.calls) == 3


def test_once_is_the_default_mode(session_factory):
    _store(session_factory, 1)
    transport = SpyTransport()
    code, out, _ = _run([], session_factory=session_factory, transport=transport)
    assert code == EXIT_OK
    assert "livrés : 1" in out


def test_once_returns_three_when_the_transport_interrupts_the_batch(session_factory):
    _store(session_factory, 3)
    transport = SpyTransport([202, httpx.ConnectError("injoignable")])

    code, out, err = _run(
        ["--once"], session_factory=session_factory, transport=transport, clock=lambda: NOW
    )

    assert code == EXIT_INTERRUPTED
    assert "livrés : 1" in out and "échecs : 1" in out
    assert "rejouées" in err
    with session_factory() as db:
        pending = db.query(EventOutboxModel).filter_by(delivered_at=None).count()
    assert pending == 2


def test_configuration_errors_exit_with_two(session_factory, monkeypatch):
    _store(session_factory, 1)
    transport = SpyTransport()
    monkeypatch.delenv("ACP_EVENT_SERVICE_TOKEN")

    code, _, err = _run(["--once"], session_factory=session_factory, transport=transport)

    assert code == EXIT_USAGE
    assert "ACP_EVENT_SERVICE_TOKEN" in err
    assert transport.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--batch-size", "0"],
        ["--poll-interval-ms", "0"],
    ],
)
def test_absurd_bounds_exit_with_two(session_factory, argv):
    code, _, err = _run(argv, session_factory=session_factory, transport=SpyTransport())
    assert code == EXIT_USAGE
    assert err.strip()


def test_contradictory_modes_are_refused_by_the_parser(session_factory, capsys):
    code = main(["--once", "--follow"], session_factory=session_factory, transport=SpyTransport())
    assert code == EXIT_USAGE
    assert "not allowed" in capsys.readouterr().err


def test_the_batch_size_option_bounds_a_pass(session_factory):
    _store(session_factory, 3)
    transport = SpyTransport()
    code, out, _ = _run(
        ["--once", "--batch-size", "2"], session_factory=session_factory, transport=transport
    )
    assert code == EXIT_OK
    assert "livrés : 2" in out
    assert len(transport.calls) == 2


# --- Lettres mortes ---------------------------------------------------------------


def _make_dead(session_factory, event_id: str) -> None:
    with session_factory() as db:
        row = db.get(EventOutboxModel, event_id)
        row.attempts = 8
        row.dead_at = NOW
        row.last_error = "HTTP 503: ko"
        db.commit()


def test_list_dead_prints_the_dead_letters_without_changing_them(session_factory):
    events = _store(session_factory, 2)
    _make_dead(session_factory, events[1].id)

    code, out, _ = _run(["--list-dead"], session_factory=session_factory)

    assert code == EXIT_OK
    assert "1 lettre(s) morte(s)" in out
    assert events[1].id in out and "HTTP 503" in out
    assert events[0].id not in out
    with session_factory() as db:
        assert len(list_dead(db)) == 1


def test_list_dead_says_so_when_there_is_nothing(session_factory):
    code, out, _ = _run(["--list-dead"], session_factory=session_factory)
    assert code == EXIT_OK
    assert "Aucune lettre morte" in out


def test_requeue_dead_puts_the_letters_back_in_line(session_factory):
    events = _store(session_factory, 1)
    _make_dead(session_factory, events[0].id)
    later = NOW + timedelta(minutes=5)

    code, out, _ = _run(
        ["--requeue-dead"], session_factory=session_factory, clock=lambda: later
    )

    assert code == EXIT_OK
    assert "1 lettre(s) morte(s) remise(s)" in out
    with session_factory() as db:
        row = db.get(EventOutboxModel, events[0].id)
        assert row.dead_at is None and row.attempts == 0
        assert row.next_attempt_at == later
    transport = SpyTransport()
    code, _, _ = _run(
        ["--once"], session_factory=session_factory, transport=transport, clock=lambda: later
    )
    assert code == EXIT_OK
    assert len(transport.calls) == 1


# --- --follow ---------------------------------------------------------------------


def test_follow_delivers_then_stops_cleanly_on_the_stop_flag(session_factory):
    _store(session_factory, 2)
    stop = threading.Event()

    class StoppingTransport(SpyTransport):
        def post(self, url, **kwargs):
            response = super().post(url, **kwargs)
            if len(self.calls) == 2:
                stop.set()
            return response

    transport = StoppingTransport()
    code, out, err = _run(
        ["--follow", "--poll-interval-ms", "10"],
        session_factory=session_factory,
        transport=transport,
        stop=stop,
    )

    assert code == EXIT_OK
    assert "livrés : 2" in out
    assert "arrêté proprement" in out
    assert err == ""
    assert len(transport.calls) == 2


def test_startup_waits_for_migrations_and_connection_recovery():
    from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeoutError
    from acp_database.schema_state import SchemaOutOfDateError, SchemaState
    errors = [SchemaOutOfDateError(SchemaState(current=None, head="head", ok=False)), OperationalError("sql", {}, Exception("secret")), PoolTimeoutError("pool saturé")]
    attempts = []
    waits = []

    class Stop:
        event = threading.Event()

        def wait(self, seconds):
            waits.append(seconds)
            return False

    def initialize():
        attempts.append(1)
        if errors:
            raise errors.pop(0)

    err = io.StringIO()
    assert outbox_relay.wait_for_schema(initialize, timeout=10, stop=Stop(), err=err, monotonic=lambda: sum(waits))
    assert len(attempts) == 4 and waits == [1, 2, 4]
    assert "secret" not in err.getvalue()


def test_startup_wait_has_a_deadline_and_explicit_exit_code(monkeypatch):
    import acp_database
    import signal
    from acp_database.schema_state import SchemaOutOfDateError, SchemaState

    def unavailable():
        raise SchemaOutOfDateError(SchemaState(current=None, head="head", ok=False))

    monkeypatch.setattr(acp_database, "init_db", unavailable)
    handler = signal.getsignal(signal.SIGTERM)
    code, _, err = _run(["--follow", "--schema-wait-seconds", "0"])
    assert code == 4
    assert "délai" in err and "traceback" not in err.lower()
    assert signal.getsignal(signal.SIGTERM) == handler


@pytest.mark.parametrize("state_extra", [{"unknown_revision": True}, {"missing_tables": ("events",)}])
def test_startup_refuses_an_incompatible_schema_without_waiting(monkeypatch, state_extra):
    import acp_database
    from types import SimpleNamespace
    from acp_database.schema_state import SchemaOutOfDateError
    state = SimpleNamespace(current="autre", head="head", ok=False, **state_extra)

    def incompatible():
        raise SchemaOutOfDateError(state)

    monkeypatch.setattr(acp_database, "init_db", incompatible)
    monkeypatch.setattr(outbox_relay._StopSignal, "wait", lambda *_: pytest.fail("aucune attente attendue"))
    code, _, err = _run(["--follow"])
    assert code == EXIT_USAGE
    assert "Démarrage refusé" in err


def test_follow_backs_off_after_a_transport_error_and_honours_the_stop(session_factory):
    _store(session_factory, 1)
    stop = threading.Event()

    class FailingTransport(SpyTransport):
        def post(self, url, **kwargs):
            self.calls.append(kwargs)
            stop.set()
            raise httpx.ConnectError("injoignable")

    transport = FailingTransport()
    code, out, err = _run(
        ["--follow"], session_factory=session_factory, transport=transport, stop=stop
    )

    assert code == EXIT_OK
    assert "Nouvel essai dans 1 s" in err
    assert "arrêté proprement" in out
    assert len(transport.calls) == 1


def test_follow_survives_a_database_error_with_backoff(session_factory):
    stop = threading.Event()
    calls = []

    def broken_factory():
        calls.append(1)
        stop.set()
        raise RuntimeError("base injoignable")

    code, out, err = _run(
        ["--follow"], session_factory=broken_factory, transport=SpyTransport(), stop=stop
    )

    assert code == EXIT_OK
    assert "base injoignable" in err and "nouvel essai dans 1 s" in err
    assert calls == [1]


def test_follow_keeps_outage_backoff_while_the_head_is_not_yet_due(monkeypatch):
    """Une tête reculée rend un passage vide : ce n'est pas un rétablissement."""
    reports = iter([RelayReport(failed=1, error="HTTP 503"), RelayReport(), RelayReport(failed=1, error="HTTP 503")])
    monkeypatch.setattr(outbox_relay, "relay_once", lambda *args, **kwargs: next(reports))
    waits = []

    class Stop:
        event = threading.Event()

        def wait(self, seconds):
            waits.append(seconds)
            return len(waits) == 3

    assert outbox_relay.follow(
        lambda: None, None, consumer="event-service", batch_size=100,
        poll_interval_seconds=0.5, clock=None, stop=Stop(),
        out=io.StringIO(), err=io.StringIO(),
    ) == EXIT_OK
    assert waits == [1, 0.5, 2]


def test_follow_dead_letters_a_poison_message_and_keeps_delivering(session_factory):
    """0.9.0 : une erreur déterministe hors transport était rejouée sans fin, la file
    restait bloquée derrière elle. Elle devient une lettre morte, la suivante part."""

    poison, healthy = _store(session_factory, 2)
    stop = threading.Event()

    class PoisonTransport(SpyTransport):
        def post(self, url, *, json, headers, timeout):
            self.calls.append({"json": json})
            if len(self.calls) >= 3:
                stop.set()  # garde-fou : jamais d'attente illimitée si la file bloque
            if json["id"] == poison.id:
                raise UnicodeEncodeError("ascii", "é", 0, 1, "ordinal not in range(128)")
            stop.set()
            return httpx.Response(202, request=httpx.Request("POST", url))

    transport = PoisonTransport()
    code, out, err = _run(
        ["--follow", "--poll-interval-ms", "10"],
        session_factory=session_factory,
        transport=transport,
        stop=stop,
        clock=lambda: NOW,
    )

    assert code == EXIT_OK
    assert [call["json"]["id"] for call in transport.calls] == [poison.id, healthy.id]
    assert "lettres mortes : 1" in err
    with session_factory() as db:
        (dead,) = list_dead(db)
        assert dead.event_id == poison.id
        assert "UnicodeEncodeError" in dead.last_error
        assert db.get(EventOutboxModel, healthy.id).delivered_at is not None


def test_follow_stops_immediately_when_already_asked(session_factory):
    stop = threading.Event()
    stop.set()
    transport = SpyTransport()
    code, out, _ = _run(
        ["--follow"], session_factory=session_factory, transport=transport, stop=stop
    )
    assert code == EXIT_OK
    assert transport.calls == []
    assert "arrêté proprement" in out
