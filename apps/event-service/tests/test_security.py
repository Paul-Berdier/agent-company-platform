import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from acp_event_service.main import app


EVENT = {"type": "task.progress", "payload": {"progress": 25}}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_remains_public_without_internal_token(monkeypatch, client):
    monkeypatch.delenv("ACP_EVENT_SERVICE_TOKEN", raising=False)

    response = client.get("/health")

    assert response.status_code == 200


def test_ingestion_fails_closed_when_internal_token_is_not_configured(
    monkeypatch, client
):
    monkeypatch.delenv("ACP_EVENT_SERVICE_TOKEN", raising=False)

    response = client.post("/internal/events", json=EVENT)

    assert response.status_code == 503
    assert "n'est pas configurée" in response.json()["detail"]


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer incorrect",
        "Basic service-secret",
        "bearer service-secret",
    ],
)
def test_ingestion_rejects_missing_or_invalid_bearer(
    monkeypatch, client, authorization
):
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "service-secret")
    headers = {"Authorization": authorization} if authorization else {}

    response = client.post("/internal/events", json=EVENT, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_ingestion_accepts_exact_internal_bearer(monkeypatch, client):
    monkeypatch.setenv("ACP_EVENT_SERVICE_TOKEN", "service-secret")

    response = client.post(
        "/internal/events",
        json=EVENT,
        headers={"Authorization": "Bearer service-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_anonymous_websocket_is_closed_by_default(monkeypatch, client):
    monkeypatch.delenv(
        "ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET", raising=False
    )

    with client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()
        assert message == {
            "type": "error",
            "code": "anonymous_websocket_disabled",
            "message": (
                "Le flux WebSocket anonyme est désactivé. "
                "Utilisez un canal utilisateur authentifié."
            ),
        }
        with pytest.raises(WebSocketDisconnect) as caught:
            websocket.receive_text()

    assert caught.value.code == 4403


def test_unsafe_development_opt_in_reenables_anonymous_websocket(
    monkeypatch, client
):
    monkeypatch.setenv("ACP_UNSAFE_ALLOW_ANONYMOUS_EVENT_WEBSOCKET", "true")

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text("keep-alive")
