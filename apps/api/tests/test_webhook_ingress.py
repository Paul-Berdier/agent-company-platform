import asyncio

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from acp_api.webhook_ingress import RequestIngressGuardMiddleware


async def _consume(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse({"size": len(body)})


def _client(*, max_body_bytes: int = 8, max_requests: int = 2) -> TestClient:
    app = Starlette(
        routes=[
            Route(
                "/automations/{automation_id}/webhook/trigger",
                _consume,
                methods=["POST"],
            ),
            Route("/other", _consume, methods=["POST"]),
            Route("/projects/{project_id}/automations", _consume, methods=["POST"]),
            Route("/projects/{project_id}/budget", _consume, methods=["PUT"]),
            Route("/skills/import", _consume, methods=["POST"]),
            Route(
                "/workers/{worker_id}/artifacts/content",
                _consume,
                methods=["POST"],
            ),
        ]
    )
    app.add_middleware(
        RequestIngressGuardMiddleware,
        max_body_bytes=max_body_bytes,
        skill_source_max_body_bytes=12,
        max_requests=max_requests,
        window_seconds=60,
    )
    return TestClient(app)


def test_webhook_content_length_is_rejected_before_the_body_is_read() -> None:
    with _client() as client:
        response = client.post(
            "/automations/auto-1/webhook/trigger", content=b"123456789"
        )

    assert response.status_code == 413


def test_chunked_webhook_is_stopped_when_the_accumulated_body_is_too_large() -> None:
    def chunks():
        yield b"12345"
        yield b"6789"

    with _client() as client:
        response = client.post(
            "/automations/auto-1/webhook/trigger", content=chunks()
        )

    assert response.status_code == 413


def test_webhook_rate_limit_runs_before_authentication_and_returns_retry_after() -> None:
    with _client() as client:
        assert client.post(
            "/automations/auto-1/webhook/trigger", content=b"{}"
        ).status_code == 200
        assert client.post(
            "/automations/auto-2/webhook/trigger", content=b"{}"
        ).status_code == 200
        refused = client.post(
            "/automations/auto-3/webhook/trigger", content=b"{}"
        )

    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "60"


def test_general_json_routes_are_bounded_before_application_parsing() -> None:
    with _client() as client:
        automation = client.post(
            "/projects/project-1/automations", content=b"123456789"
        )
        budget = client.put("/projects/project-1/budget", content=b"123456789")

    assert automation.status_code == 413
    assert budget.status_code == 413


def test_conflicting_content_lengths_are_rejected_before_application_code() -> None:
    reached = []
    sent: list[dict] = []

    async def app(scope, receive, send) -> None:
        reached.append(scope)

    async def receive() -> dict:
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    guard = RequestIngressGuardMiddleware(app, max_body_bytes=8)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/other",
        "headers": [
            (b"content-length", b"1"),
            (b"content-length", b"2"),
        ],
    }

    asyncio.run(guard(scope, receive, send))

    assert reached == []
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 400


@pytest.mark.parametrize("invalid_length", [b"", b"+1", b" 1", b"1 ", b"1_0"])
def test_non_decimal_content_length_is_rejected_before_application_code(
    invalid_length: bytes,
) -> None:
    reached = []
    sent: list[dict] = []

    async def app(scope, receive, send) -> None:
        reached.append(scope)

    async def receive() -> dict:
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    guard = RequestIngressGuardMiddleware(app, max_body_bytes=8)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/other",
        "headers": [(b"content-length", invalid_length)],
    }

    asyncio.run(guard(scope, receive, send))

    assert reached == []
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 400


def test_skill_source_has_a_larger_cap_and_artifact_upload_keeps_streaming() -> None:
    with _client() as client:
        skill = client.post("/skills/import", content=b"123456789")
        artifact = client.post(
            "/workers/worker-1/artifacts/content", content=b"123456789"
        )

    assert skill.status_code == 200
    assert skill.json() == {"size": 9}
    assert artifact.status_code == 200
    assert artifact.json() == {"size": 9}


def test_rate_limit_cache_recovers_after_the_window() -> None:
    now = [0.0]
    guard = RequestIngressGuardMiddleware(
        app=None,
        max_requests=1,
        window_seconds=60,
        max_tracked_clients=2,
        clock=lambda: now[0],
    )

    def scope(address: str) -> dict:
        return {"type": "http", "client": (address, 1234)}

    assert guard._rate_allowed(scope("192.0.2.1"))
    assert guard._rate_allowed(scope("192.0.2.2"))
    assert guard._rate_allowed(scope("192.0.2.3"))
    assert not guard._rate_allowed(scope("192.0.2.4"))
    assert len(guard._requests) == 2

    now[0] = 61.0
    assert guard._rate_allowed(scope("192.0.2.3"))
    assert "192.0.2.3" in guard._requests
    assert len(guard._requests) == 2
