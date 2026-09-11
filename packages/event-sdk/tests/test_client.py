import httpx

from acp_contracts import Event
from acp_event_sdk import EventClient


async def test_missing_worker_credentials_fails_closed_without_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = EventClient(
        "http://api.test",
        transport=httpx.MockTransport(handler),
    )

    assert await client.emit(Event(type="task.progress")) is False
    assert requests == []


async def test_worker_identity_is_sent_and_only_2xx_is_accepted():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    client = EventClient(
        "http://api.test",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert await client.emit(Event(type="task.progress")) is True
    assert requests[0].headers["X-Worker-Id"] == "worker-1"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"


async def test_rejected_event_is_not_reported_as_delivered():
    client = EventClient(
        "http://api.test",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(409, json={"detail": "lease expiré"})
        ),
    )

    assert await client.emit(Event(type="task.progress")) is False
