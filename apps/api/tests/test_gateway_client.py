import asyncio

import httpx
import pytest

from acp_api.gateway import GatewayClient, GatewayUnavailableError


def test_gateway_client_sends_service_auth_and_idempotency_key():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            202,
            json={
                "run_id": "run_0123456789abcdef0123456789abcdef",
                "status": "queued",
                "replayed": False,
            },
        )

    client = GatewayClient(
        base_url="https://gateway.test",
        service_token="internal-secret",
        transport=httpx.MockTransport(handler),
    )
    run = asyncio.run(
        client.submit_hermes_run(
            prompt="Bonjour",
            session_id="conversation-1",
            idempotency_key="turn-1",
        )
    )

    assert run.status == "queued"
    assert len(captured) == 1
    assert captured[0].headers["authorization"] == "Bearer internal-secret"
    assert captured[0].headers["idempotency-key"] == "turn-1"
    assert captured[0].url.path == "/v1/providers/hermes/runs"


def test_gateway_client_fails_closed_without_service_token():
    client = GatewayClient(
        base_url="https://gateway.test",
        service_token="",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(GatewayUnavailableError, match="jeton de service"):
        asyncio.run(client.diagnose_hermes())


def test_gateway_client_rejects_an_invalid_diagnostic_contract():
    client = GatewayClient(
        base_url="https://gateway.test",
        service_token="internal-secret",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"ready": "yes"})
        ),
    )

    with pytest.raises(GatewayUnavailableError, match="diagnostic Hermes"):
        asyncio.run(client.diagnose_hermes())


@pytest.mark.parametrize(
    "base_url",
    [
        "http://gateway.example",
        "https://user:secret@gateway.example",
        "https://gateway.example/v1",
        "https://gateway.example?token=secret",
    ],
)
def test_gateway_client_never_sends_its_bearer_to_an_unsafe_origin(base_url: str):
    captured: list[httpx.Request] = []
    client = GatewayClient(
        base_url=base_url,
        service_token="internal-secret",
        transport=httpx.MockTransport(
            lambda request: (
                captured.append(request),
                httpx.Response(200, json={}),
            )[1]
        ),
    )

    with pytest.raises(GatewayUnavailableError, match="origine"):
        asyncio.run(client.diagnose_hermes())
    assert captured == []
