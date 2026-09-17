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
from acp_api.outbox import list_dead
from acp_api.outbox_relay import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
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
