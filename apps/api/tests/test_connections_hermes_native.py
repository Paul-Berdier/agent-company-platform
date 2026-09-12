"""Consultation en lecture seule des skills et toolsets natifs Hermes.

La route API ne fait que relayer ce que le gateway a lu chez Hermes : elle
n'écrit rien, exige une session et ne renvoie jamais 500 quand la passerelle
est injoignable.
"""

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.gateway import GatewayClient, GatewayUnavailableError, get_gateway_client
from acp_api.main import app
from acp_contracts import HermesNativeListing
from acp_database.models import Base

BOOTSTRAP_TOKEN = "native-listing-bootstrap-token"
PASSWORD = "native listing test password"
READ_AT = datetime(2026, 9, 12, 8, 30, tzinfo=timezone.utc)
GATEWAY_TOKEN = "gateway-internal-secret"


def _available_payload() -> dict:
    return {
        "status": "available",
        "skills": [
            {
                "name": "pdf-report",
                "description": "Génère un rapport PDF",
                "category": "documents",
            }
        ],
        "toolsets": [
            {
                "name": "filesystem",
                "label": "Système de fichiers",
                "description": "Lecture et écriture locales",
                "enabled": True,
                "configured": True,
                "tools": ["read_file"],
            }
        ],
        "message": "Lecture Hermes : 1 skill(s) et 1 toolset(s) annoncés.",
        "read_at": READ_AT.isoformat(),
    }


class FakeGateway(GatewayClient):
    """Passerelle simulée : aucune sortie réseau, comportement pilotable."""

    def __init__(self) -> None:
        self.calls = 0
        self.failure: Exception | None = None
        self.listing = HermesNativeListing.model_validate(_available_payload())

    async def hermes_native_listing(self) -> HermesNativeListing:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.listing


@pytest.fixture
def native_client(monkeypatch):
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    gateway = FakeGateway()

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_gateway_client] = lambda: gateway
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={
                    "login": "owner",
                    "display_name": "Propriétaire",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201
            yield client, gateway
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_gateway_client, None)
        engine.dispose()


def test_native_listing_requires_a_session(native_client):
    client, gateway = native_client
    client.cookies.clear()

    assert client.get("/connections/hermes/native-listing").status_code == 401
    assert gateway.calls == 0


def test_native_listing_relays_what_hermes_announced(native_client):
    client, gateway = native_client

    response = client.get("/connections/hermes/native-listing")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["skills"][0]["name"] == "pdf-report"
    assert body["toolsets"][0]["tools"] == ["read_file"]
    assert body["read_at"].startswith("2026-09-12T08:30:00")
    assert gateway.calls == 1


def test_native_listing_is_read_only(native_client):
    client, gateway = native_client

    assert client.post("/connections/hermes/native-listing").status_code == 405
    assert client.delete("/connections/hermes/native-listing").status_code == 405
    assert gateway.calls == 0


def test_native_listing_reports_an_unreachable_gateway(native_client):
    client, gateway = native_client
    gateway.failure = GatewayUnavailableError("jeton de service absent")

    response = client.get("/connections/hermes/native-listing")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert "passerelle" in body["message"].lower()
    assert body["skills"] == []
    assert body["toolsets"] == []
    assert body["read_at"] is None


def test_native_listing_relays_a_not_configured_hermes(native_client):
    client, gateway = native_client
    gateway.listing = HermesNativeListing(
        status="not_configured",
        message="Configuration Hermes incomplète : lecture impossible.",
    )

    body = client.get("/connections/hermes/native-listing").json()

    assert body["status"] == "not_configured"
    assert body["skills"] == []
    assert body["read_at"] is None


@pytest.mark.asyncio
async def test_gateway_client_validates_the_listing_contract():
    payload = _available_payload()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = GatewayClient(
        base_url="https://gateway.test",
        service_token=GATEWAY_TOKEN,
        transport=httpx.MockTransport(handler),
    )

    listing = await client.hermes_native_listing()

    assert listing.status == "available"
    assert listing.skills[0].name == "pdf-report"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/providers/hermes/native-listing"
    assert requests[0].headers["Authorization"] == f"Bearer {GATEWAY_TOKEN}"


@pytest.mark.asyncio
async def test_gateway_client_refuses_an_invalid_listing_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "available", "message": "vide"})

    client = GatewayClient(
        base_url="https://gateway.test",
        service_token=GATEWAY_TOKEN,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GatewayUnavailableError):
        await client.hermes_native_listing()
