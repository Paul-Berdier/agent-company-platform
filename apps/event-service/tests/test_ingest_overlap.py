"""Livraisons qui se recouvrent : un identifiant n'est jamais diffusé deux fois.

Avant 0.9.1, la route vérifiait ``seen()``, attendait la diffusion, puis appelait
``remember()`` : entre les deux, un renvoi du relais (délai HTTP de 3 s dépassé par une
diffusion lente) trouvait l'identifiant « jamais vu » et le rediffusait. Ces tests
bloquent la première diffusion sur un ``asyncio.Event`` pour reproduire exactement ce
recouvrement.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from acp_event_service import main as event_service

HEADERS = {"Authorization": "Bearer service-secret"}
EVENT = {"id": "44444444-4444-4444-8444-444444444444", "type": "task.progress"}


@pytest.fixture
def gate(monkeypatch):
    """Diffusion retenue jusqu'à ``gate.release`` ; compte chaque diffusion."""

    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "service-secret")
    event_service.ledger.reset()

    class Gate:
        def __init__(self) -> None:
            self.entered = asyncio.Event()
            self.released = asyncio.Event()
            self.broadcasts: list[str] = []
            self.fail_next = False

        async def broadcast(self, event) -> None:
            self.broadcasts.append(event.id)
            self.entered.set()
            await self.released.wait()
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("diffusion interrompue")

        def release(self) -> None:
            self.released.set()

    instance = Gate()
    monkeypatch.setattr(event_service.manager, "broadcast", instance.broadcast)
    try:
        yield instance
    finally:
        event_service.ledger.reset()


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=event_service.app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://event-service")


async def test_an_overlapping_resend_waits_and_is_acknowledged_without_a_second_broadcast(gate):
    async with _client() as client:
        first = asyncio.create_task(client.post("/internal/events", json=EVENT, headers=HEADERS))
        await asyncio.wait_for(gate.entered.wait(), 5)
        second = asyncio.create_task(client.post("/internal/events", json=EVENT, headers=HEADERS))
        await asyncio.sleep(0.05)
        assert not second.done(), "le renvoi attend la fin de la diffusion en cours"
        gate.release()
        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.json() == {"ok": True}
    assert second_response.status_code == 200
    assert second_response.json() == {"ok": True, "duplicate": True}
    assert gate.broadcasts == [EVENT["id"]]


async def test_a_resend_asks_to_retry_while_the_broadcast_is_still_running(gate, monkeypatch):
    monkeypatch.setattr(event_service, "inflight_wait", 0.05)
    async with _client() as client:
        first = asyncio.create_task(client.post("/internal/events", json=EVENT, headers=HEADERS))
        await asyncio.wait_for(gate.entered.wait(), 5)

        busy = await client.post("/internal/events", json=EVENT, headers=HEADERS)

        assert busy.status_code == 503
        assert busy.headers["retry-after"] == "1"
        assert "en cours de diffusion" in busy.json()["detail"]
        gate.release()
        assert (await first).json() == {"ok": True}
        again = await client.post("/internal/events", json=EVENT, headers=HEADERS)

    assert again.json() == {"ok": True, "duplicate": True}
    assert gate.broadcasts == [EVENT["id"]]


async def test_a_failed_broadcast_is_never_remembered_and_the_waiting_resend_takes_over(gate):
    gate.fail_next = True
    async with _client() as client:
        first = asyncio.create_task(client.post("/internal/events", json=EVENT, headers=HEADERS))
        await asyncio.wait_for(gate.entered.wait(), 5)
        second = asyncio.create_task(client.post("/internal/events", json=EVENT, headers=HEADERS))
        await asyncio.sleep(0.05)
        gate.release()
        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.status_code == 500
    # Le renvoi en attente reprend la diffusion lui-même : l'événement n'est pas perdu.
    assert second_response.json() == {"ok": True}
    assert gate.broadcasts == [EVENT["id"], EVENT["id"]]
    assert event_service.ledger.seen(EVENT["id"]) is True


def test_the_wait_setting_is_validated():
    from acp_event_service.dedupe import INFLIGHT_WAIT_ENV, inflight_wait_seconds

    assert inflight_wait_seconds({}) == 2.0
    assert inflight_wait_seconds({INFLIGHT_WAIT_ENV: "0.5"}) == 0.5
    for bad in ("0", "-1", "deux", "nan"):
        with pytest.raises(RuntimeError, match=INFLIGHT_WAIT_ENV):
            inflight_wait_seconds({INFLIGHT_WAIT_ENV: bad})
