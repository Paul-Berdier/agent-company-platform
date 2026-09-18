"""Ingestion idempotente du service d'événements (Lot H3).

Le relais d'outbox livre au-moins-une-fois : le service doit reconnaître un
identifiant déjà diffusé et l'acquitter **sans** le rediffuser. Le registre est
borné et en mémoire ; sa limite est documentée, pas cachée.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from acp_event_service import main as event_service
from acp_event_service.dedupe import (
    DEDUPE_SIZE_ENV,
    DEFAULT_DEDUPE_SIZE,
    DeliveryLedger,
    dedupe_size,
)

HEADERS = {"Authorization": "Bearer service-secret"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "service-secret")
    event_service.ledger.reset()
    try:
        yield TestClient(event_service.app)
    finally:
        event_service.ledger.reset()


@pytest.fixture
def broadcasts(monkeypatch):
    seen: list[str] = []

    async def record(event):
        seen.append(event.id)

    monkeypatch.setattr(event_service.manager, "broadcast", record)
    return seen


# --- Registre ---------------------------------------------------------------------


def test_the_ledger_remembers_within_its_window_and_forgets_the_oldest_first():
    ledger = DeliveryLedger(max_ids=3)
    for event_id in ("a", "b", "c"):
        assert ledger.seen(event_id) is False
        ledger.remember(event_id)
    assert all(ledger.seen(event_id) for event_id in ("a", "b", "c"))
    ledger.remember("d")
    assert ledger.seen("a") is False, "le plus ancien sort en premier"
    assert ledger.seen("d") is True
    assert len(ledger) == 3


def test_a_revisited_id_is_refreshed_instead_of_duplicated():
    ledger = DeliveryLedger(max_ids=2)
    ledger.remember("a")
    ledger.remember("b")
    ledger.remember("a")
    ledger.remember("c")
    assert ledger.seen("a") is True and ledger.seen("b") is False
    assert len(ledger) == 2


def test_the_ledger_refuses_an_empty_window():
    with pytest.raises(ValueError):
        DeliveryLedger(max_ids=0)


def test_the_window_size_comes_from_the_environment():
    assert dedupe_size({}) == DEFAULT_DEDUPE_SIZE == 10_000
    assert dedupe_size({DEDUPE_SIZE_ENV: "42"}) == 42
    for bad in ("0", "-1", "dix"):
        with pytest.raises(RuntimeError, match=DEDUPE_SIZE_ENV):
            dedupe_size({DEDUPE_SIZE_ENV: bad})


# --- Route ------------------------------------------------------------------------


def test_a_duplicate_delivery_is_acknowledged_without_a_second_broadcast(
    client, broadcasts
):
    event = {"id": "11111111-1111-4111-8111-111111111111", "type": "task.progress"}

    first = client.post("/internal/events", json=event, headers=HEADERS)
    second = client.post("/internal/events", json=event, headers=HEADERS)

    assert first.status_code == 200 and first.json() == {"ok": True}
    assert second.status_code == 200
    assert second.json() == {"ok": True, "duplicate": True}
    assert broadcasts == [event["id"]]


def test_distinct_ids_are_each_broadcast_once(client, broadcasts):
    for event_id in ("a" * 36, "b" * 36):
        response = client.post(
            "/internal/events", json={"id": event_id, "type": "t"}, headers=HEADERS
        )
        assert response.json() == {"ok": True}
    assert broadcasts == ["a" * 36, "b" * 36]


def test_the_relay_headers_are_optional(client, broadcasts):
    """Le relais direct historique n'envoie aucun en-tête ``X-ACP-*`` : il reste accepté."""

    event = {"id": "22222222-2222-4222-8222-222222222222", "type": "task.progress"}
    with_headers = client.post(
        "/internal/events",
        json=event,
        headers={
            **HEADERS,
            "X-ACP-Event-Id": event["id"],
            "X-ACP-Journal-Seq": "7",
            "X-ACP-Delivery-Attempt": "2",
        },
    )
    assert with_headers.json() == {"ok": True}
    legacy = client.post(
        "/internal/events", json={"type": "task.progress"}, headers=HEADERS
    )
    assert legacy.status_code == 200 and legacy.json() == {"ok": True}
    assert len(broadcasts) == 2


def test_a_rejected_delivery_is_not_remembered(client, broadcasts):
    event = {"id": "33333333-3333-4333-8333-333333333333", "type": "task.progress"}
    refused = client.post("/internal/events", json=event)
    assert refused.status_code == 401
    assert event_service.ledger.seen(event["id"]) is False
    accepted = client.post("/internal/events", json=event, headers=HEADERS)
    assert accepted.json() == {"ok": True}
    assert broadcasts == [event["id"]]
