"""Boîte d'envoi transactionnelle et relais avec reprise (Lot H3).

Ce que ces tests verrouillent, dans l'ordre du module :

1. la ligne d'outbox part **dans la transaction métier** : présente avant le commit
   de l'appelant, absente après son rollback, jamais écrite sans
   ``ACP_EVENT_RELAY_ENABLED=1`` ;
2. le relais livre dans l'ordre du journal, s'arrête à la première erreur de
   transport, recule la ligne fautive et ne renvoie jamais une ligne livrée ;
3. la sémantique est **au-moins-une-fois** : un incident entre le 2xx et le commit
   du relais renvoie l'événement, et c'est le registre du service d'événements
   qui l'ignore — pas le relais ;
4. une ligne abandonnée après ``ACP_OUTBOX_MAX_ATTEMPTS`` essais est une lettre
   morte, listable et remise en attente à la demande.

Le moteur vient de ``acp_database.testing`` : SQLite sur fichier par défaut, schéma
PostgreSQL éphémère si ``ACP_TEST_DATABASE_URL`` est posée.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from acp_api import events_bus, outbox
from acp_api.events_bus import publish, store_event
from acp_api.outbox import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    OutboxConfigurationError,
    RelayReport,
    enqueue,
    list_dead,
    relay_enabled,
    relay_once,
    requeue_dead,
)
from acp_contracts import Event
from acp_database.models import EventModel, EventOutboxModel
from acp_database.testing import make_test_engine

#: Horloge de test, postérieure à l'horloge réelle : une ligne enfilée par
#: ``store_event`` (horloge réelle) est donc toujours due à ``NOW``.
NOW = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
RELAY_ENVIRON = {
    "ACP_EVENT_SERVICE_URL": "https://events.test",
    "ACP_EVENT_SERVICE_TOKEN": "relay-secret",
}


# --- Outillage -------------------------------------------------------------------


class SpyTransport:
    """Transport espion : rejoue ``outcomes`` (statut ou exception) puis répond 202."""

    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any, headers: dict, timeout: float) -> httpx.Response:
        self.calls.append(
            {"url": url, "json": json, "headers": dict(headers), "timeout": timeout}
        )
        outcome = self.outcomes.pop(0) if self.outcomes else 202
        if isinstance(outcome, BaseException):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", url), text="ko")

    @property
    def event_ids(self) -> list[str]:
        return [call["json"]["id"] for call in self.calls]


@pytest.fixture
def database(tmp_path):
    engine = make_test_engine(tmp_path, concurrent=True)
    try:
        yield engine
    finally:
        engine.close()


@pytest.fixture
def session_factory(database):
    return sessionmaker(bind=database.engine, expire_on_commit=False)


@pytest.fixture
def relay_on(monkeypatch):
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")


def _store(session_factory, count: int, *, project_id: str = "projet-1") -> list[Event]:
    events = [Event(type="task.progress", project_id=project_id, payload={"i": i}) for i in range(count)]
    with session_factory() as db:
        for event in events:
            store_event(db, event)
    return events


def _outbox_rows(session_factory) -> list[EventOutboxModel]:
    with session_factory() as db:
        return (
            db.query(EventOutboxModel).order_by(EventOutboxModel.journal_seq).all()
        )


# --- 1. Écriture dans la transaction métier -------------------------------------


def test_the_variable_must_be_exactly_one():
    assert relay_enabled({"ACP_EVENT_RELAY_ENABLED": "1"}) is True
    for value in ("true", "yes", " 1", "1 ", "0", ""):
        assert relay_enabled({"ACP_EVENT_RELAY_ENABLED": value}) is False
    assert relay_enabled({}) is False


def test_store_event_writes_the_outbox_row_in_the_same_transaction(
    session_factory, relay_on
):
    event = Event(type="task.progress", project_id="projet-1")
    with session_factory() as db:
        model = store_event(db, event, commit=False)
        # 0.9.1 : la ligne d'outbox naît au commit, avec le numéro de journal
        # attribué sous le verrou ; avant lui, ni numéro ni ligne d'outbox.
        assert model.journal_seq is None
        assert db.query(EventOutboxModel).count() == 0
        # Invisible hors de la transaction tant que l'appelant n'a pas validé.
        with session_factory() as observer:
            assert observer.query(EventOutboxModel).count() == 0
        db.commit()
    rows = _outbox_rows(session_factory)
    assert [row.event_id for row in rows] == [event.id]
    assert rows[0].journal_seq == model.journal_seq == 1
    assert rows[0].project_id == "projet-1"
    assert rows[0].consumer == "event-service"
    assert rows[0].attempts == 0
    assert rows[0].delivered_at is None and rows[0].dead_at is None
    assert rows[0].next_attempt_at is not None


def test_a_business_rollback_leaves_no_outbox_row(session_factory, relay_on):
    event = Event(type="task.progress", project_id="projet-1", task_run_id="run-1")
    with session_factory() as db:
        publish(db, event, commit=False)
        assert db.query(EventModel).count() == 1
        db.rollback()
    with session_factory() as db:
        assert db.query(EventModel).count() == 0
        assert db.query(EventOutboxModel).count() == 0


def test_publish_enqueues_with_the_allocated_journal_seq(session_factory, relay_on):
    event = Event(type="task.progress", project_id="projet-1", task_run_id="run-1")
    with session_factory() as db:
        assert publish(db, event) == 1
        model = db.get(EventModel, event.id)
        row = db.get(EventOutboxModel, event.id)
        assert row is not None
        assert row.journal_seq == model.journal_seq == 1


@pytest.mark.parametrize("value", [None, "true", "0"])
def test_no_outbox_row_without_the_exact_variable(session_factory, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ACP_EVENT_RELAY_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", value)
    _store(session_factory, 1)
    with session_factory() as db:
        publish(db, Event(type="task.progress", project_id="p", task_run_id="r"))
        assert db.query(EventModel).count() == 2
        assert db.query(EventOutboxModel).count() == 0


def test_enqueue_refuses_an_event_without_journal_seq(session_factory):
    with session_factory() as db:
        with pytest.raises(ValueError, match="numéro de journal"):
            enqueue(db, EventModel(id="x", type="t", occurred_at=NOW, payload={}))


def test_a_deferred_publication_is_invisible_to_the_relay_until_commit(
    session_factory, relay_on
):
    """``publish(commit=False)`` : le relais ne voit rien avant le commit de l'appelant."""

    transport = SpyTransport()
    with session_factory() as writer:
        publish(
            writer,
            Event(type="task.progress", project_id="p", task_run_id="r"),
            commit=False,
        )
        report = relay_once(session_factory, transport, environ=RELAY_ENVIRON)
        assert report == RelayReport()
        assert transport.calls == []
        writer.commit()
    report = relay_once(session_factory, transport, environ=RELAY_ENVIRON)
    assert report.delivered == 1
    assert len(transport.calls) == 1


# --- 2. Relais : ordre, arrêt à la première erreur, reprise ----------------------


def test_the_relay_sends_the_unchanged_event_with_delivery_headers(
    session_factory, relay_on
):
    (event,) = _store(session_factory, 1)
    transport = SpyTransport()

    report = relay_once(session_factory, transport, now=NOW, environ=RELAY_ENVIRON)

    assert report == RelayReport(delivered=1, cursor_hint=1)
    (call,) = transport.calls
    assert call["url"] == "https://events.test/internal/events"
    assert call["json"] == event.model_dump(mode="json")
    assert call["headers"] == {
        "Authorization": "Bearer relay-secret",
        "X-ACP-Event-Id": event.id,
        "X-ACP-Journal-Seq": "1",
        "X-ACP-Delivery-Attempt": "1",
    }
    assert call["timeout"] == DEFAULT_HTTP_TIMEOUT_SECONDS
    (row,) = _outbox_rows(session_factory)
    assert row.delivered_at == NOW
    assert row.attempts == 0


def test_the_http_timeout_comes_from_the_environment(session_factory, relay_on):
    _store(session_factory, 1)
    transport = SpyTransport()
    relay_once(
        session_factory,
        transport,
        environ={**RELAY_ENVIRON, "ACP_OUTBOX_HTTP_TIMEOUT_SECONDS": "7.5"},
    )
    assert transport.calls[0]["timeout"] == 7.5
    with pytest.raises(OutboxConfigurationError, match="ACP_OUTBOX_HTTP_TIMEOUT_SECONDS"):
        relay_once(
            session_factory,
            transport,
            environ={**RELAY_ENVIRON, "ACP_OUTBOX_HTTP_TIMEOUT_SECONDS": "0"},
        )


def test_the_relay_stops_at_the_first_transport_error_then_resumes_in_order(
    session_factory, relay_on
):
    """Échec au 2ᵉ envoi : seul le 1ᵉʳ est livré ; la reprise livre 2 puis 3, une fois."""

    events = _store(session_factory, 3)
    failing = SpyTransport([202, httpx.ConnectError("service injoignable")])

    report = relay_once(session_factory, failing, now=NOW, environ=RELAY_ENVIRON)

    assert report.delivered == 1
    assert report.failed == 1
    assert report.dead == 0
    assert report.cursor_hint == 1
    assert report.interrupted
    assert "ConnectError" in report.error
    assert failing.event_ids == [events[0].id, events[1].id]
    first, second, third = _outbox_rows(session_factory)
    assert first.delivered_at == NOW
    assert second.delivered_at is None
    assert second.attempts == 0
    assert second.next_attempt_at == NOW + timedelta(seconds=2)
    assert "ConnectError" in second.last_error
    assert third.attempts == 0 and third.delivered_at is None

    # Trop tôt : la ligne reculée n'est pas due, et l'ordre interdit de livrer la 3ᵉ.
    early = SpyTransport()
    assert relay_once(
        session_factory, early, now=NOW + timedelta(seconds=1), environ=RELAY_ENVIRON
    ) == RelayReport()
    assert early.calls == []

    healthy = SpyTransport()
    report = relay_once(
        session_factory, healthy, now=NOW + timedelta(seconds=3), environ=RELAY_ENVIRON
    )
    assert report == RelayReport(delivered=2, cursor_hint=3)
    assert healthy.event_ids == [events[1].id, events[2].id]
    assert [call["headers"]["X-ACP-Delivery-Attempt"] for call in healthy.calls] == ["1", "1"]
    assert [row.delivered_at for row in _outbox_rows(session_factory)] == [
        NOW,
        NOW + timedelta(seconds=3),
        NOW + timedelta(seconds=3),
    ]
    # Plus rien à livrer : aucune ligne livrée n'est renvoyée.
    again = SpyTransport()
    assert relay_once(session_factory, again, environ=RELAY_ENVIRON) == RelayReport()
    assert again.calls == []


def test_a_non_2xx_status_is_a_transport_failure(session_factory, relay_on):
    _store(session_factory, 2)
    transport = SpyTransport([503])

    report = relay_once(session_factory, transport, now=NOW, environ=RELAY_ENVIRON)

    assert report == RelayReport(failed=1, error="HTTP 503: ko")
    assert len(transport.calls) == 1
    first, second = _outbox_rows(session_factory)
    assert first.attempts == 0 and first.last_error == "HTTP 503: ko"
    assert second.attempts == 0


def test_the_backoff_doubles_and_is_capped_at_five_minutes(session_factory, relay_on):
    _store(session_factory, 1)
    moment = NOW
    expected = [2, 4, 8, 16, 32, 64, 128, 256]
    for attempt, delay in enumerate(expected, start=1):
        report = relay_once(
            session_factory,
            SpyTransport([422]),
            now=moment,
            environ={**RELAY_ENVIRON, "ACP_OUTBOX_MAX_ATTEMPTS": "20"},
        )
        assert report.failed == 1 and report.dead == 0
        (row,) = _outbox_rows(session_factory)
        assert row.attempts == attempt
        assert row.next_attempt_at == moment + timedelta(seconds=delay)
        moment = row.next_attempt_at
    for _ in range(3):
        relay_once(
            session_factory,
            SpyTransport([422]),
            now=moment,
            environ={**RELAY_ENVIRON, "ACP_OUTBOX_MAX_ATTEMPTS": "20"},
        )
        (row,) = _outbox_rows(session_factory)
        assert row.next_attempt_at == moment + timedelta(seconds=300)
        moment = row.next_attempt_at


def test_the_last_error_is_truncated_to_the_column_width(session_factory, relay_on):
    _store(session_factory, 1)
    transport = SpyTransport([httpx.ConnectError("x" * 2000)])
    relay_once(session_factory, transport, environ=RELAY_ENVIRON)
    (row,) = _outbox_rows(session_factory)
    assert len(row.last_error) == 500


# --- 3. Au-moins-une-fois : renvoi après incident, ignoré par le registre ------


def _flaky_factory(session_factory: Callable, failures: list[str]) -> Callable:
    """Fabrique dont le premier ``commit`` échoue : l'incident « entre 2xx et commit »."""

    def make():
        db = session_factory()
        original = db.commit

        def commit():
            if failures and any(isinstance(row, EventOutboxModel) and row.delivered_at is not None for row in db.dirty):
                failures.pop()
                db.rollback()
                raise RuntimeError("commit refusé (injection de panne)")
            original()

        db.commit = commit
        return db

    return make


def test_a_failure_between_ack_and_commit_redelivers_and_the_service_ignores_it(
    session_factory, relay_on, monkeypatch
):
    """Le renvoi est attendu (au-moins-une-fois) ; le service répond ``duplicate``."""

    from fastapi.testclient import TestClient

    from acp_event_service import main as event_service

    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "relay-secret")
    event_service.ledger.reset()
    broadcasts: list[str] = []

    async def record(event):
        broadcasts.append(event.id)

    monkeypatch.setattr(event_service.manager, "broadcast", record)
    (event,) = _store(session_factory, 1)

    class ServiceTransport:
        def __init__(self) -> None:
            self.client = TestClient(event_service.app)
            self.responses: list[dict] = []

        def post(self, url, *, json, headers, timeout):
            response = self.client.post(url, json=json, headers=headers)
            self.responses.append(response.json())
            return response

    transport = ServiceTransport()
    environ = {**RELAY_ENVIRON, "ACP_EVENT_SERVICE_URL": "http://127.0.0.1:8001"}

    with pytest.raises(RuntimeError, match="injection de panne"):
        relay_once(_flaky_factory(session_factory, ["panne"]), transport, now=NOW, environ=environ)

    assert transport.responses == [{"ok": True}]
    assert broadcasts == [event.id]
    (row,) = _outbox_rows(session_factory)
    assert row.delivered_at is None, "la panne a bien empêché le commit du relais"

    report = relay_once(session_factory, transport, now=NOW + timedelta(seconds=61), environ=environ)

    assert report.delivered == 1
    assert transport.responses == [{"ok": True}, {"ok": True, "duplicate": True}]
    assert broadcasts == [event.id], "le doublon n'est pas rediffusé"
    (row,) = _outbox_rows(session_factory)
    assert row.delivered_at is not None


# --- 4. Lettres mortes ------------------------------------------------------------


def test_a_row_becomes_a_dead_letter_after_max_attempts_then_can_be_requeued(
    session_factory, relay_on
):
    (event,) = _store(session_factory, 1)
    moment = NOW
    for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
        report = relay_once(
            session_factory,
            SpyTransport([422]),
            now=moment,
            environ=RELAY_ENVIRON,
        )
        assert report.failed == 1
        assert report.dead == (1 if attempt == DEFAULT_MAX_ATTEMPTS else 0)
        moment += timedelta(seconds=400)
    (row,) = _outbox_rows(session_factory)
    assert row.attempts == DEFAULT_MAX_ATTEMPTS == 8
    assert row.dead_at is not None
    assert row.delivered_at is None

    # Une lettre morte n'est plus tentée.
    ignored = SpyTransport()
    assert relay_once(session_factory, ignored, now=moment, environ=RELAY_ENVIRON) == RelayReport()
    assert ignored.calls == []

    with session_factory() as db:
        assert [dead.event_id for dead in list_dead(db)] == [event.id]
        assert list_dead(db, consumer="autre") == []
        assert requeue_dead(db, now=moment) == 1
        assert list_dead(db) == []
    (row,) = _outbox_rows(session_factory)
    assert row.dead_at is None and row.attempts == 0
    assert row.next_attempt_at == moment
    assert "422" in row.last_error, "la cause de l'abandon reste lisible"

    healthy = SpyTransport()
    assert relay_once(session_factory, healthy, now=moment, environ=RELAY_ENVIRON).delivered == 1
    assert healthy.calls[0]["headers"]["X-ACP-Delivery-Attempt"] == "1"


def test_a_dead_letter_no_longer_holds_the_queue(session_factory, relay_on):
    """Une ligne reculée retient la file ; une lettre morte la libère."""

    events = _store(session_factory, 2)
    with session_factory() as db:
        head = db.get(EventOutboxModel, events[0].id)
        head.attempts = 3
        head.next_attempt_at = NOW + timedelta(seconds=8)
        db.commit()
    held = SpyTransport()
    assert relay_once(session_factory, held, now=NOW, environ=RELAY_ENVIRON) == RelayReport()
    assert held.calls == [], "la 2ᵉ ligne n'a pas doublé la 1ʳᵉ"

    with session_factory() as db:
        head = db.get(EventOutboxModel, events[0].id)
        head.dead_at = NOW
        db.commit()
    freed = SpyTransport()
    report = relay_once(session_factory, freed, now=NOW, environ=RELAY_ENVIRON)
    assert report == RelayReport(delivered=1, cursor_hint=2)
    assert freed.event_ids == [events[1].id]


def test_max_attempts_is_read_from_the_environment(session_factory, relay_on):
    _store(session_factory, 1)
    environ = {**RELAY_ENVIRON, "ACP_OUTBOX_MAX_ATTEMPTS": "2"}
    moment = NOW
    for expected_dead in (0, 1):
        report = relay_once(
            session_factory, SpyTransport([422]), now=moment, environ=environ
        )
        assert report.dead == expected_dead
        moment += timedelta(seconds=400)
    for bad in ("0", "huit"):
        with pytest.raises(OutboxConfigurationError, match="ACP_OUTBOX_MAX_ATTEMPTS"):
            relay_once(
                session_factory,
                SpyTransport(),
                environ={**RELAY_ENVIRON, "ACP_OUTBOX_MAX_ATTEMPTS": bad},
            )


# --- 5. Refus de configuration ---------------------------------------------------


def test_the_relay_refuses_to_run_without_a_token_or_with_an_insecure_origin(
    session_factory, relay_on
):
    _store(session_factory, 1)
    transport = SpyTransport()
    with pytest.raises(OutboxConfigurationError, match="ACP_EVENT_SERVICE_TOKEN"):
        relay_once(session_factory, transport, environ={"ACP_EVENT_SERVICE_URL": "https://events.test"})
    with pytest.raises(OutboxConfigurationError, match="ACP_EVENT_SERVICE_URL"):
        relay_once(
            session_factory,
            transport,
            environ={**RELAY_ENVIRON, "ACP_EVENT_SERVICE_URL": "http://events.example"},
        )
    with pytest.raises(OutboxConfigurationError, match="batch_size"):
        relay_once(session_factory, transport, batch_size=0, environ=RELAY_ENVIRON)
    assert transport.calls == []


def test_the_batch_size_bounds_a_pass(session_factory, relay_on):
    _store(session_factory, 5)
    transport = SpyTransport()
    report = relay_once(session_factory, transport, batch_size=2, environ=RELAY_ENVIRON)
    assert report == RelayReport(delivered=2, cursor_hint=2)
    report = relay_once(session_factory, transport, batch_size=100, environ=RELAY_ENVIRON)
    assert report == RelayReport(delivered=3, cursor_hint=5)
    assert [call["headers"]["X-ACP-Journal-Seq"] for call in transport.calls] == [
        "1", "2", "3", "4", "5"
    ]


def test_another_consumer_sees_nothing(session_factory, relay_on):
    _store(session_factory, 2)
    transport = SpyTransport()
    assert relay_once(
        session_factory, transport, consumer="autre", environ=RELAY_ENVIRON
    ) == RelayReport()
    assert transport.calls == []


# --- 6. Message empoisonné (0.9.1) -------------------------------------------------


class RealHttpxTransport:
    """Le vrai ``httpx.Client`` du transport de production, sur un serveur simulé.

    ``SpyTransport`` n'encode ni les en-têtes ni le corps : c'est ``httpx`` qui le
    fait, dans ``build_request``, et c'est là que naissaient les erreurs qui
    bloquaient la file en 0.9.0. Ce transport reproduit ``HttpxTransport.post`` à
    l'identique, le réseau en moins.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.client = httpx.Client(
            transport=httpx.MockTransport(self._handle), trust_env=False
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"ok": True})

    def post(self, url: str, *, json: Any, headers: dict, timeout: float) -> httpx.Response:
        return self.client.post(url, json=json, headers=dict(headers), timeout=timeout)

    @property
    def event_ids(self) -> list[str]:
        import json as json_module

        return [json_module.loads(request.content)["id"] for request in self.requests]


def test_a_non_ascii_event_id_is_delivered_through_the_real_httpx_client(
    session_factory, relay_on
):
    """0.9.0 : ``httpx`` encode les en-têtes en ASCII et levait ``UnicodeEncodeError``,
    une exception hors transport qui laissait la ligne en tête de file pour toujours."""

    accented = Event(id="événement-0001", type="task.progress", project_id="p")
    plain = Event(type="task.progress", project_id="p")
    with session_factory() as db:
        store_event(db, accented)
        store_event(db, plain)
    transport = RealHttpxTransport()

    report = relay_once(session_factory, transport, now=NOW, environ=RELAY_ENVIRON)

    assert report == RelayReport(delivered=2, cursor_hint=2)
    assert transport.event_ids == ["événement-0001", plain.id], (
        "le corps JSON porte l'identifiant exact, en UTF-8"
    )
    first, second = transport.requests
    # L'en-tête n'est qu'une aide au diagnostic : encodé en pourcentage (RFC 3986),
    # il reste de l'ASCII ; un UUID, lui, passe inchangé.
    assert first.headers["X-ACP-Event-Id"] == "%C3%A9v%C3%A9nement-0001"
    assert second.headers["X-ACP-Event-Id"] == plain.id
    assert all(row.delivered_at == NOW for row in _outbox_rows(session_factory))


@pytest.mark.sqlite
def test_an_unreadable_event_is_dead_lettered_and_frees_the_queue(
    session_factory, relay_on
):
    """Une charge utile illisible (JSON corrompu dans la base) lève à la relecture.

    Erreur déterministe : la rejouer ne changerait rien. La ligne part en lettre
    morte au premier essai, avec sa cause, et la suivante est livrée dans le même
    passage. Le pendant PostgreSQL (date illisible par psycopg) est dans
    ``test_outbox_postgresql``.
    """

    from sqlalchemy import text

    unreadable, healthy = _store(session_factory, 2)
    with session_factory() as db:
        db.execute(
            text("UPDATE events SET payload = '{pas du json' WHERE id = :event_id"),
            {"event_id": unreadable.id},
        )
        db.commit()
    transport = RealHttpxTransport()

    report = relay_once(session_factory, transport, now=NOW, environ=RELAY_ENVIRON)

    assert report == RelayReport(delivered=1, failed=1, dead=1, cursor_hint=2)
    assert transport.event_ids == [healthy.id]
    dead_row, delivered_row = _outbox_rows(session_factory)
    assert dead_row.dead_at == NOW
    assert dead_row.attempts == 1
    assert dead_row.delivered_at is None
    assert "message non transmissible" in dead_row.last_error
    assert "JSONDecodeError" in dead_row.last_error
    assert delivered_row.delivered_at == NOW


def test_an_unexpected_transport_exception_is_counted_and_never_escapes(
    session_factory, relay_on
):
    """Une exception inconnue du transport compte un essai et recule la ligne ;
    au-delà de ``ACP_OUTBOX_MAX_ATTEMPTS``, lettre morte — jamais une boucle sans fin."""

    (event,) = _store(session_factory, 1)
    environ = {**RELAY_ENVIRON, "ACP_OUTBOX_MAX_ATTEMPTS": "3"}
    moment = NOW
    for attempt in (1, 2, 3):
        report = relay_once(
            session_factory,
            SpyTransport([RuntimeError("bogue du transport")]),
            now=moment,
            environ=environ,
        )
        assert report.failed == 1
        assert report.dead == (1 if attempt == 3 else 0)
        assert "RuntimeError" in report.error
        (row,) = _outbox_rows(session_factory)
        assert row.attempts == attempt
        moment += timedelta(seconds=400)
    (row,) = _outbox_rows(session_factory)
    assert row.dead_at is not None
    assert "bogue du transport" in row.last_error
    with session_factory() as db:
        assert [dead.event_id for dead in list_dead(db)] == [event.id]


@pytest.mark.sqlite
def test_an_orphan_outbox_row_is_dead_lettered_instead_of_stopping_the_relay(
    database, session_factory, relay_on
):
    """Une corruption héritée d'une base sans FK ne retient plus la file.

    Le moteur normal conserve ses FK actives ; seule une connexion indépendante
    fabrique la corruption historique, hors transaction, avant de les réactiver.
    """

    import sqlite3
    from contextlib import closing

    (event,) = _store(session_factory, 1)
    with closing(sqlite3.connect(database.engine.url.database, isolation_level=None)) as corruption:
        corruption.execute("PRAGMA foreign_keys=OFF")
        try:
            corruption.execute(
                "INSERT INTO event_outbox "
                "(event_id, journal_seq, project_id, consumer, attempts, "
                "next_attempt_at, last_error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "evenement-disparu", 0, "p", "event-service", 0,
                    (NOW - timedelta(minutes=1)).isoformat(), "", NOW.isoformat(),
                ),
            )
        finally:
            corruption.execute("PRAGMA foreign_keys=ON")
            assert corruption.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    transport = SpyTransport()

    report = relay_once(session_factory, transport, now=NOW, environ=RELAY_ENVIRON)

    assert report == RelayReport(delivered=1, failed=1, dead=1, cursor_hint=1)
    assert transport.event_ids == [event.id]
    with session_factory() as db:
        orphan = db.get(EventOutboxModel, "evenement-disparu")
        assert orphan.dead_at == NOW
        assert "orpheline" in orphan.last_error


@pytest.mark.parametrize("outcome", [401, 403, 429, 503, httpx.ConnectError("indisponible")])
def test_consumer_outages_never_dead_letter_a_valid_head(session_factory, relay_on, outcome):
    events = _store(session_factory, 2)
    moment = NOW
    for _ in range(DEFAULT_MAX_ATTEMPTS + 2):
        transport = SpyTransport([outcome])
        report = relay_once(session_factory, transport, now=moment, environ=RELAY_ENVIRON)
        assert report.failed == 1 and report.dead == 0
        assert transport.event_ids == [events[0].id]
        head, _ = _outbox_rows(session_factory)
        assert head.attempts == 0 and head.dead_at is None
        moment += timedelta(seconds=400)
    transport = SpyTransport()
    assert relay_once(session_factory, transport, now=moment, environ=RELAY_ENVIRON).delivered == 2
    assert transport.event_ids == [event.id for event in events]


@pytest.mark.sqlite
@pytest.mark.concurrency
def test_sqlite_http_delivery_leaves_the_database_writable(session_factory, relay_on):
    """Le POST attend une vraie publication concurrente : aucun verrou SQLite ne fuit."""
    from concurrent.futures import ThreadPoolExecutor
    _store(session_factory, 1)

    def publish_while_sending():
        with session_factory() as db:
            store_event(db, Event(type="task.progress", project_id="p"))

    class ConcurrentTransport(SpyTransport):
        def post(self, url, *, json, headers, timeout):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(publish_while_sending).result(timeout=2)
            return super().post(url, json=json, headers=headers, timeout=timeout)

    assert relay_once(session_factory, ConcurrentTransport(), now=NOW, environ=RELAY_ENVIRON).delivered == 1


@pytest.mark.sqlite
def test_sqlite_reservation_blocks_a_second_relay_and_recovers_after_a_crash(session_factory, relay_on):
    _store(session_factory, 1)

    class CrashTransport(SpyTransport):
        def post(self, url, **kwargs):
            assert relay_once(session_factory, SpyTransport(), now=NOW, environ=RELAY_ENVIRON) == RelayReport()
            raise KeyboardInterrupt("arrêt brutal simulé")

    with pytest.raises(KeyboardInterrupt):
        relay_once(session_factory, CrashTransport(), now=NOW, environ=RELAY_ENVIRON)
    assert relay_once(session_factory, SpyTransport(), now=NOW, environ=RELAY_ENVIRON) == RelayReport()
    assert relay_once(session_factory, SpyTransport(), now=NOW + timedelta(minutes=1), environ=RELAY_ENVIRON).delivered == 1


@pytest.mark.sqlite
def test_sqlite_late_response_cannot_overwrite_a_new_reservation(session_factory, relay_on):
    _store(session_factory, 1)
    later = NOW + timedelta(minutes=1)

    class LateTransport(SpyTransport):
        def post(self, url, **kwargs):
            assert relay_once(session_factory, SpyTransport([503]), now=later, environ=RELAY_ENVIRON).failed == 1
            return httpx.Response(422, request=httpx.Request("POST", url))

    assert relay_once(session_factory, LateTransport(), now=NOW, environ=RELAY_ENVIRON) == RelayReport()
    (row,) = _outbox_rows(session_factory)
    assert row.attempts == 0 and row.last_error == "HTTP 503: ko"
    assert row.next_attempt_at == later + timedelta(seconds=2)


def test_relay_uses_an_explicit_private_http_destination(session_factory, relay_on):
    _store(session_factory, 1)
    transport = RealHttpxTransport()
    assert relay_once(session_factory, transport, now=NOW, environ={
        **RELAY_ENVIRON,
        "ACP_EVENT_SERVICE_URL": "http://event-service:8000",
        "ACP_INTERNAL_HTTP_HOSTS": "event-service",
    }).delivered == 1
    assert str(transport.requests[0].url) == "http://event-service:8000/internal/events"


# --- 7. Garde structurelle --------------------------------------------------------


def test_only_events_bus_and_outbox_instantiate_the_outbox_model():
    """Aucun autre module de production ne fabrique une ligne d'outbox à la main."""

    root = Path(__file__).resolve().parents[3]
    roots = [
        *root.glob("apps/*/src"),
        *root.glob("packages/*/src"),
        *root.glob("services/*/src"),
        root / "scripts",
    ]
    offenders = []
    for source_root in roots:
        for path in source_root.rglob("*.py"):
            # ``class EventOutboxModel(Base)`` est une définition, pas une instanciation.
            if re.search(r"(?<!class )EventOutboxModel\(", path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(root).as_posix())
    assert sorted(offenders) == ["apps/api/src/acp_api/outbox.py"]
    assert events_bus._enqueue_outbox is outbox.enqueue
