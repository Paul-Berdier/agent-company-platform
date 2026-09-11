import httpx
import pytest

from acp_api import events_bus
from acp_contracts import Event


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
