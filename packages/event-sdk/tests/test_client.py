import httpx

import acp_event_sdk.client as event_client_module
from acp_contracts import Event
from acp_event_sdk import EventClient


async def test_missing_worker_credentials_fails_closed_without_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = EventClient(
        "https://api.test",
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
        "https://api.test",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert await client.emit(Event(type="task.progress")) is True
    assert requests[0].headers["X-Worker-Id"] == "worker-1"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"


async def test_event_client_disables_environment_proxies_for_bearer_requests(
    monkeypatch,
):
    client_options: list[dict] = []
    original_async_client = httpx.AsyncClient

    def async_client_spy(**kwargs):
        client_options.append(kwargs)
        return original_async_client(**kwargs)

    monkeypatch.setattr(event_client_module.httpx, "AsyncClient", async_client_spy)
    client = EventClient(
        "https://api.test",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(202, json={"ok": True})
        ),
    )

    assert await client.emit(Event(type="task.progress")) is True
    assert len(client_options) == 1
    assert client_options[0]["trust_env"] is False


async def test_rejected_event_is_not_reported_as_delivered():
    client = EventClient(
        "https://api.test",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(409, json={"detail": "lease expiré"})
        ),
    )

    assert await client.emit(Event(type="task.progress")) is False


async def test_insecure_api_origin_never_receives_worker_credentials():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    client = EventClient(
        "http://api.example",
        worker_id="worker-1",
        worker_token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert await client.emit(Event(type="task.progress")) is False
    assert requests == []
