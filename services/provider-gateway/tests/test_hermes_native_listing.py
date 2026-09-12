"""Lecture seule des skills et toolsets natifs annoncés par Hermes 0.21.1.

Hermes reste la source de vérité de sa configuration : le gateway lit
`GET /v1/skills` et `GET /v1/toolsets` et n'écrit jamais rien. Aucun test ne
touche le réseau réel (`httpx.MockTransport`).
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import acp_provider_gateway.main as gateway_main
from acp_contracts import HermesNativeListing
from acp_provider_gateway.providers.hermes import (
    HermesClient,
    HermesOrchestratorProvider,
    HermesSettings,
)

GATEWAY_TOKEN = "gateway-internal-secret"
HERMES_TOKEN = "hermes-upstream-secret"
NATIVE_PATH = "/v1/providers/hermes/native-listing"


def _ready_health(*, version: str = "0.21.1", status: str = "ok") -> dict:
    checks = {
        name: {"status": "ok"}
        for name in (
            "state_db",
            "config",
            "model",
            "disk",
            "gateway",
            "background_queues",
        )
    }
    return {
        "status": status,
        "readiness": {"status": status, "checks": checks},
        "platform": "hermes-agent",
        "version": version,
        "gateway_state": "running",
    }


def _skills() -> list[dict]:
    return [
        {
            "name": "pdf-report",
            "description": "Génère un rapport PDF",
            "category": "documents",
            "unknown_field": "ignoré",
        },
        {"name": "web-research"},
    ]


def _toolsets() -> list[dict]:
    return [
        {
            "name": "filesystem",
            "label": "Système de fichiers",
            "description": "Lecture et écriture locales",
            "enabled": True,
            "configured": True,
            "tools": ["read_file", "write_file"],
        },
        {
            "name": "browser",
            "label": "Navigateur",
            "description": "",
            "enabled": False,
            "configured": False,
            "tools": [],
        },
    ]


def _provider(
    handler,
    *,
    base_url: str = "https://hermes.test",
    service_token: str = HERMES_TOKEN,
) -> HermesOrchestratorProvider:
    settings = HermesSettings(
        base_url=base_url,
        service_token=service_token,
        timeout_seconds=0.05,
        max_retries=0,
        run_timeout_seconds=1,
        poll_interval_seconds=0,
    )
    return HermesOrchestratorProvider(
        HermesClient(settings, transport=httpx.MockTransport(handler))
    )


def _authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {GATEWAY_TOKEN}"}


@pytest.fixture(autouse=True)
def _gateway_auth(monkeypatch):
    monkeypatch.setenv("ACP_GATEWAY_SERVICE_TOKEN", GATEWAY_TOKEN)


def _read(monkeypatch, handler, **provider_kwargs) -> httpx.Response:
    monkeypatch.setattr(
        gateway_main, "hermes_provider", _provider(handler, **provider_kwargs)
    )
    with TestClient(gateway_main.app) as client:
        return client.get(NATIVE_PATH, headers=_authorization())


def test_native_listing_requires_the_internal_bearer():
    with TestClient(gateway_main.app) as client:
        assert client.get(NATIVE_PATH).status_code == 401


def test_native_listing_reports_not_configured_without_calling_hermes(monkeypatch):
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    response = _read(monkeypatch, unexpected, base_url="", service_token="")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_configured"
    assert body["skills"] == []
    assert body["toolsets"] == []
    assert body["read_at"] is None
    assert body["message"]
    assert calls == []


def test_native_listing_returns_what_hermes_announced(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/skills":
            return httpx.Response(200, json=_skills())
        if request.url.path == "/v1/toolsets":
            return httpx.Response(200, json=_toolsets())
        return httpx.Response(404)

    response = _read(monkeypatch, handler)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["read_at"] is not None
    assert body["skills"] == [
        {
            "name": "pdf-report",
            "description": "Génère un rapport PDF",
            "category": "documents",
        },
        {"name": "web-research", "description": "", "category": ""},
    ]
    assert body["toolsets"][0]["tools"] == ["read_file", "write_file"]
    assert body["toolsets"][1]["enabled"] is False
    assert body["toolsets"][1]["configured"] is False
    assert HERMES_TOKEN not in response.text
    paths = [request.url.path for request in requests]
    assert paths == ["/health/detailed", "/v1/skills", "/v1/toolsets"]
    assert all(
        request.headers["Authorization"] == f"Bearer {HERMES_TOKEN}"
        for request in requests
    )
    assert all(request.method == "GET" for request in requests)


def test_native_listing_accepts_an_enveloped_list_and_bounds_untrusted_text(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/skills":
            return httpx.Response(
                200,
                json={
                    "skills": [
                        {
                            "name": "verbeux",
                            "description": "x" * 4000,
                            "category": "général",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"toolsets": []})

    response = _read(monkeypatch, handler)

    body = response.json()
    assert body["status"] == "available"
    assert len(body["skills"][0]["description"]) == 500
    assert body["toolsets"] == []


def test_native_listing_refuses_a_degraded_readiness_without_reading_the_lists(
    monkeypatch,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health(status="degraded"))
        return httpx.Response(200, json=[])

    response = _read(monkeypatch, handler)

    body = response.json()
    assert body["status"] == "unavailable"
    assert body["skills"] == []
    assert body["toolsets"] == []
    assert body["read_at"] is None
    assert [request.url.path for request in requests] == ["/health/detailed"]


def test_native_listing_reports_unauthorized_hermes_as_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        return httpx.Response(401, json={"error": HERMES_TOKEN})

    response = _read(monkeypatch, handler)

    body = response.json()
    assert body["status"] == "unavailable"
    assert "authentification" in body["message"].lower()
    assert body["skills"] == []
    assert HERMES_TOKEN not in response.text


def test_native_listing_reports_a_missing_route_as_unsupported(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        return httpx.Response(404, json={"detail": "not found"})

    response = _read(monkeypatch, handler)

    body = response.json()
    assert body["status"] == "unsupported"
    assert body["skills"] == []
    assert body["toolsets"] == []
    assert body["read_at"] is None


def test_native_listing_reports_an_invalid_payload_as_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        return httpx.Response(200, content=b"{")

    response = _read(monkeypatch, handler)

    body = response.json()
    assert body["status"] == "unavailable"
    assert body["skills"] == []


def test_native_listing_refuses_an_entry_with_a_wrong_field_type(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/skills":
            return httpx.Response(200, json=[{"name": 42}])
        return httpx.Response(200, json=[])

    response = _read(monkeypatch, handler)

    assert response.json()["status"] == "unavailable"
    assert response.json()["skills"] == []


def test_native_listing_contract_refuses_a_content_without_a_successful_read():
    with pytest.raises(ValidationError):
        HermesNativeListing(
            status="unavailable",
            skills=[{"name": "inventé", "description": "", "category": ""}],
            toolsets=[],
            message="Hermes indisponible",
            read_at=None,
        )
