"""Contrat HTTP interne du gateway pour les runs conversationnels Hermes."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import acp_provider_gateway.main as gateway_main
from acp_provider_gateway.providers.hermes import (
    HermesClient,
    HermesOrchestratorProvider,
    HermesSettings,
)

RUN_ID = "run_" + "a" * 32
GATEWAY_TOKEN = "gateway-internal-secret"
HERMES_TOKEN = "hermes-upstream-secret"


def _ready_health(*, version: str = "0.21.1") -> dict:
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
        "status": "ok",
        "readiness": {"status": "ok", "checks": checks},
        "platform": "hermes-agent",
        "version": version,
        "gateway_state": "running",
    }


def _capabilities() -> dict:
    return {
        "object": "hermes.api_server.capabilities",
        "platform": "hermes-agent",
        "model": "hermes-agent",
        "auth": {"type": "bearer", "required": True},
        "features": {
            "run_submission": True,
            "run_status": True,
            "run_stop": True,
            "runs_idempotency": {
                "supported": True,
                "durable": True,
                "retention_seconds": 86400,
            },
        },
    }


def _provider(
    handler,
    *,
    base_url: str = "https://hermes.test",
    service_token: str = HERMES_TOKEN,
    max_retries: int = 0,
) -> HermesOrchestratorProvider:
    settings = HermesSettings(
        base_url=base_url,
        service_token=service_token,
        timeout_seconds=0.01,
        max_retries=max_retries,
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


def test_only_liveness_is_public_and_gateway_auth_fails_closed(monkeypatch):
    with TestClient(gateway_main.app) as client:
        assert client.get("/health").status_code == 200

        monkeypatch.delenv("ACP_GATEWAY_SERVICE_TOKEN")
        unconfigured = client.get("/v1/providers")
        assert unconfigured.status_code == 503
        assert GATEWAY_TOKEN not in unconfigured.text

        monkeypatch.setenv("ACP_GATEWAY_SERVICE_TOKEN", GATEWAY_TOKEN)
        unauthorized = client.get(
            "/v1/providers", headers={"Authorization": "Bearer wrong"}
        )
        assert unauthorized.status_code == 401
        assert unauthorized.headers["www-authenticate"] == "Bearer"
        assert GATEWAY_TOKEN not in unauthorized.text

        assert client.get("/v1/providers", headers=_authorization()).status_code == 200


def test_diagnostic_reports_not_configured_without_calling_hermes(monkeypatch):
    calls = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(
        gateway_main,
        "hermes_provider",
        _provider(unexpected, base_url="", service_token=""),
    )
    with TestClient(gateway_main.app) as client:
        response = client.get(
            "/v1/providers/hermes/diagnostic", headers=_authorization()
        )

    assert response.status_code == 200
    assert response.json() == {
        "provider_id": "hermes",
        "status": "not_configured",
        "configured": False,
        "ready": False,
        "expected_version": "0.21.1",
        "detail": "Configuration Hermes incomplète",
    }
    assert calls == []


def test_diagnostic_reports_ready_with_typed_non_secret_fields(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/capabilities":
            return httpx.Response(200, json=_capabilities())
        return httpx.Response(404)

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        response = client.get(
            "/v1/providers/hermes/diagnostic", headers=_authorization()
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["configured"] is True
    assert body["ready"] is True
    assert body["expected_version"] == "0.21.1"
    assert body["detected_version"] == "0.21.1"
    assert body["model"] == "hermes-agent"
    assert body["latency_ms"] >= 0
    assert HERMES_TOKEN not in response.text
    assert all(
        request.headers["Authorization"] == f"Bearer {HERMES_TOKEN}"
        for request in requests
    )


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("unauthorized", "unauthorized"),
        ("timeout", "timeout"),
        ("version", "incompatible_version"),
        ("json", "invalid_response"),
    ],
)
def test_diagnostic_classifies_upstream_failures_without_secrets(
    monkeypatch, failure, expected_status
):
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "unauthorized":
            return httpx.Response(401, json={"error": HERMES_TOKEN})
        if failure == "timeout":
            raise httpx.ReadTimeout(HERMES_TOKEN, request=request)
        if failure == "json":
            return httpx.Response(200, content=b"{")
        return httpx.Response(200, json=_ready_health(version="0.22.0"))

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        response = client.get(
            "/v1/providers/hermes/diagnostic", headers=_authorization()
        )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert response.json()["configured"] is True
    assert response.json()["ready"] is False
    assert HERMES_TOKEN not in response.text
    assert GATEWAY_TOKEN not in response.text


def test_submit_is_asynchronous_and_forwards_caller_idempotency_key(monkeypatch):
    requests: list[httpx.Request] = []
    admissions = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal admissions
        requests.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/capabilities":
            return httpx.Response(200, json=_capabilities())
        if request.url.path == "/v1/runs" and request.method == "POST":
            admissions += 1
            return httpx.Response(
                202,
                json={"run_id": RUN_ID, "status": "started"},
                headers={
                    "Idempotency-Replayed": "true" if admissions > 1 else "false"
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    body = {
        "prompt": "Bonjour Hermes",
        "model": "hermes-agent",
        "metadata": {"conversation_id": "conv-1", "project_id": "project-1"},
        "session_id": "acp-conversation-conv-1",
    }
    headers = {**_authorization(), "Idempotency-Key": "conversation-turn-1"}
    with TestClient(gateway_main.app) as client:
        first = client.post(
            "/v1/providers/hermes/runs", json=body, headers=headers
        )
        replay = client.post(
            "/v1/providers/hermes/runs", json=body, headers=headers
        )

    assert first.status_code == 202
    assert first.json() == {
        "run_id": RUN_ID,
        "status": "started",
        "replayed": False,
        "session_id": "acp-conversation-conv-1",
        "model": "hermes-agent",
    }
    assert replay.status_code == 202
    assert replay.json()["run_id"] == RUN_ID
    assert replay.json()["replayed"] is True

    run_posts = [request for request in requests if request.url.path == "/v1/runs"]
    assert len(run_posts) == 2
    assert all(
        request.headers["Idempotency-Key"] == "conversation-turn-1"
        for request in run_posts
    )
    upstream_body = json.loads(run_posts[0].content)
    assert upstream_body["input"] == "Bonjour Hermes"
    assert upstream_body["session_id"] == "acp-conversation-conv-1"
    assert "instructions" in upstream_body
    assert "metadata" not in upstream_body
    assert all(not request.url.path.startswith(f"/v1/runs/{RUN_ID}") for request in requests)


@pytest.mark.parametrize(
    "key",
    [None, "", "contains space", "x" * 256],
)
def test_submit_rejects_missing_or_invalid_idempotency_key(monkeypatch, key):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    headers = _authorization()
    if key is not None:
        headers["Idempotency-Key"] = key
    with TestClient(gateway_main.app) as client:
        response = client.post(
            "/v1/providers/hermes/runs",
            json={"prompt": "Bonjour"},
            headers=headers,
        )

    assert response.status_code == 422
    assert calls == []


def test_read_returns_one_validated_snapshot_without_preflight_or_poll(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == f"/v1/runs/{RUN_ID}"
        return httpx.Response(
            200,
            json={
                "object": "hermes.run",
                "run_id": RUN_ID,
                "status": "running",
                "session_id": "acp-conversation-conv-1",
                "model": "hermes-agent",
            },
        )

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        response = client.get(
            f"/v1/providers/hermes/runs/{RUN_ID}", headers=_authorization()
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": RUN_ID,
        "status": "running",
        "replayed": False,
        "session_id": "acp-conversation-conv-1",
        "model": "hermes-agent",
    }
    assert len(requests) == 1


def test_read_rejects_invalid_run_id_before_upstream(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        response = client.get(
            "/v1/providers/hermes/runs/not-a-run", headers=_authorization()
        )

    assert response.status_code == 422
    assert calls == []


@pytest.mark.parametrize("operation", ["plan", "evaluate"])
def test_operation_replays_across_gateway_restart_then_reads_validated_result(monkeypatch, operation):
    calls = []
    reservations = {}
    output = ({"steps": [{"id": "one", "title": "Faire", "executor": "codex_cli"}]}
              if operation == "plan" else {"approved": True, "score": 0.9, "feedback": "Prouvé"})

    def handler(request):
        calls.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=_ready_health())
        if request.url.path == "/v1/capabilities":
            return httpx.Response(200, json=_capabilities())
        if request.url.path == "/v1/runs":
            key = request.headers["Idempotency-Key"]
            replay = key in reservations
            if replay:
                assert reservations[key] == request.content
            reservations[key] = request.content
            return httpx.Response(202, json={"run_id": RUN_ID, "status": "completed" if replay else "started"},
                                  headers={"Idempotency-Replayed": str(replay).lower()})
        assert request.method == "GET"
        return httpx.Response(200, json={"object": "hermes.run", "run_id": RUN_ID,
                                       "status": "completed", "output": json.dumps(output)})

    body = {"session": {}}
    body.update({"goal": "Objectif", "context": {"execution": {"mode": "multi_agent", "executors": ["codex_cli"]}}}
                if operation == "plan" else {"task_summary": "Tâche", "produced_output": {"evidence": "Preuve"}})
    headers = {**_authorization(), "Idempotency-Key": f"attempt-42-{operation}"}
    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        first = client.post(f"/v1/providers/hermes/operations/{operation}", json=body, headers=headers)
        assert first.status_code == 202
        assert first.json()["run_id"] == RUN_ID
        assert first.json()["result"] is None
        assert not any(r.url.path == f"/v1/runs/{RUN_ID}" for r in calls)
        monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
        replay = client.post(f"/v1/providers/hermes/operations/{operation}", json=body, headers=headers)
        assert replay.status_code == 202
        assert replay.json()["replayed"] is True
        result = client.get(f"/v1/providers/hermes/operations/{operation}/{RUN_ID}", headers=_authorization())
    assert len(reservations) == 1
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["result"]["provider_id"] == "hermes"
    if operation == "plan":
        assert result.json()["result"]["steps"][0]["executor"] == "codex_cli"
    else:
        assert result.json()["result"]["approved"] is True


@pytest.mark.parametrize("path", ["operations/plan", "plan", "operations/evaluate", "evaluate"])
def test_every_hermes_operation_requires_caller_key_before_upstream(monkeypatch, path):
    calls = []
    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(lambda request: calls.append(request)))
    body = {"session": {}}
    body.update({"goal": "x"} if path.endswith("plan") else {"task_summary": "x", "produced_output": {"evidence": "x"}})
    with TestClient(gateway_main.app) as client:
        result = client.post(f"/v1/providers/hermes/{path}", json=body, headers=_authorization())
    assert result.status_code == 422
    assert calls == []


@pytest.mark.parametrize("status,output,expected", [
    ("completed", "not-json", "failed"),
    ("completed", '{"approved":"yes","score":1}', "failed"),
    ("waiting_for_approval", None, "waiting_for_approval"),
    ("failed", None, "failed"),
    ("cancelled", None, "cancelled"),
])
def test_operation_snapshot_has_no_false_success_or_raw_error(monkeypatch, status, output, expected):
    def handler(request):
        return httpx.Response(200, json={"object": "hermes.run", "run_id": RUN_ID,
                                       "status": status, "output": output, "error": HERMES_TOKEN})
    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        result = client.get(f"/v1/providers/hermes/operations/evaluate/{RUN_ID}", headers=_authorization())
    assert result.status_code == 200
    assert result.json()["status"] == expected
    assert result.json()["result"] is None
    assert result.json()["error"]
    assert HERMES_TOKEN not in result.text


def test_stop_acknowledges_only_stopping_then_reads_actual_cancellation(monkeypatch):
    calls = []
    state = "waiting_for_approval"
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.url.path.endswith("/stop")
            return httpx.Response(200, json={"status": "stopping"})
        return httpx.Response(200, json={"object": "hermes.run", "run_id": RUN_ID, "status": state})
    monkeypatch.setattr(gateway_main, "hermes_provider", _provider(handler))
    with TestClient(gateway_main.app) as client:
        stopped = client.post(f"/v1/providers/hermes/runs/{RUN_ID}/stop", headers=_authorization())
        assert stopped.status_code == 202
        assert stopped.json()["status"] == "stopping"
        state = "cancelled"
        terminal = client.post(f"/v1/providers/hermes/runs/{RUN_ID}/stop", headers=_authorization())
    assert terminal.json()["status"] == "cancelled"
    assert sum(method == "POST" for method, _ in calls) == 1
