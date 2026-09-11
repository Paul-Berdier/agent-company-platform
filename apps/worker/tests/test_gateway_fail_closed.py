import httpx
import pytest
from pathlib import Path

from acp_worker.config import WorkerConfig
from acp_worker.main import execution_outcome, gateway_evaluate, gateway_plan


def config(gateway_service_token: str | None = "gateway-secret") -> WorkerConfig:
    return WorkerConfig(
        api_url="http://api.test",
        gateway_url="http://gateway.test",
        gateway_service_token=gateway_service_token,
        provider_id="hermes",
        poll_interval=0.1,
        step_seconds=0.0,
        state_dir=Path("."),  # inutilisé par ces tests
        name="test",
        max_concurrency=1,
        simulation=False,
        registration_token=None,
    )


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_gateway_requests_use_the_internal_service_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gateway-secret"
        return httpx.Response(
            200,
            json={"plan_id": "p1", "steps": [{"id": "s1", "title": "Étape"}]},
        )

    async with client(handler) as http:
        result = await gateway_plan(http, config(), {}, "objectif")
    assert result["plan_id"] == "p1"


async def test_gateway_request_fails_closed_without_internal_service_token():
    worker_config = config(None)
    async with client(lambda _: httpx.Response(200, json={})) as http:
        with pytest.raises(RuntimeError, match="ACP_GATEWAY_SERVICE_TOKEN"):
            await gateway_plan(http, worker_config, {}, "objectif")


@pytest.mark.parametrize("status", [401, 404, 503])
async def test_plan_http_failure_never_creates_a_fallback(status: int):
    async with client(lambda _: httpx.Response(status, json={"detail": "no"})) as http:
        with pytest.raises(RuntimeError, match="planification indisponible"):
            await gateway_plan(http, config(), {}, "objectif")


async def test_plan_requires_json_and_non_empty_steps():
    async with client(lambda _: httpx.Response(200, content=b"not json")) as http:
        with pytest.raises(RuntimeError, match="non JSON"):
            await gateway_plan(http, config(), {}, "objectif")
    async with client(
        lambda _: httpx.Response(200, json={"plan_id": "p1", "steps": []})
    ) as http:
        with pytest.raises(RuntimeError, match="sans étape"):
            await gateway_plan(http, config(), {}, "objectif")


async def test_evaluation_requires_explicit_boolean_verdict():
    async with client(lambda _: httpx.Response(200, json={"score": 1})) as http:
        with pytest.raises(RuntimeError, match="verdict booléen explicite"):
            await gateway_evaluate(http, config(), {}, "résultat")
    async with client(lambda _: httpx.Response(200, json={"approved": "yes"})) as http:
        with pytest.raises(RuntimeError, match="verdict booléen explicite"):
            await gateway_evaluate(http, config(), {}, "résultat")


def test_simulation_and_missing_verdict_cannot_succeed():
    assert execution_outcome(None, simulation=True) == ("blocked", "blocked", "task.blocked")
    with pytest.raises(RuntimeError, match="verdict d'évaluation explicite"):
        execution_outcome({}, simulation=False)
    assert execution_outcome({"approved": False}, simulation=False) == (
        "failed",
        "failed",
        "task.failed",
    )
