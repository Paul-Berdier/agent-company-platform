"""Tests du pont vers l'API Runs officielle Hermes Agent v0.21.1."""

import json
import re
import time
from datetime import datetime, timezone

import httpx
import pytest

from acp_contracts import (
    ContextSummaryRequest,
    EvaluationRequest,
    PlanningRequest,
    PlanRevisionRequest,
    PlanStep,
)
from acp_contracts.sessions import SessionContext
from acp_provider_sdk import ProviderUnavailableError

from acp_provider_gateway.providers.hermes import (
    HermesClient,
    HermesOrchestratorProvider,
    HermesSettings,
)

RUN_ID = "run_" + "a" * 32
OTHER_RUN_ID = "run_" + "b" * 32

SESSION = SessionContext(
    session_id="sess-1",
    organization_id="org-1",
    workspace_id="ws-1",
    project_id="proj-1",
    agent_instance_id="agent-1",
    provider_id="hermes",
    external_session_id="hermes-ext-42",
)


def ready_health(*, status: str = "ok", gateway_state: str = "running") -> dict:
    checks = {
        "state_db": {"status": "ok"},
        "config": {"status": "ok"},
        "model": {"status": "ok"},
        "disk": {"status": "ok", "used_percent": 42.1, "free_bytes": 1000000},
        "gateway": {
            "status": "ok",
            "state": gateway_state,
            "connected_platforms": 1,
            "platforms": 1,
        },
        "background_queues": {
            "status": "ok",
            "active_api_runs": 0,
            "process_completions": 0,
            "active_delegations": 0,
        },
    }
    return {
        "status": status,
        "readiness": {"status": status, "checks": checks},
        "platform": "hermes-agent",
        "version": "0.21.1",
        "gateway_state": gateway_state,
        "platforms": {"api_server": {"state": "connected"}},
        "active_agents": 0,
        "gateway_busy": False,
        "gateway_drainable": gateway_state == "running",
        "exit_reason": None,
        "updated_at": "2026-09-11T10:00:00+00:00",
        "pid": 4242,
    }


def run_capabilities() -> dict:
    return {
        "object": "hermes.api_server.capabilities",
        "platform": "hermes-agent",
        "model": "hermes-agent",
        "auth": {"type": "bearer", "required": True},
        "runtime": {
            "mode": "server_agent",
            "tool_execution": "server",
            "split_runtime": False,
        },
        "features": {
            "run_submission": True,
            "run_status": True,
            "runs_idempotency": {
                "supported": True,
                "durable": True,
                "retention_seconds": 86400,
            },
            "run_events_sse": True,
            "run_stop": True,
            "run_steer": True,
            "run_approval_response": True,
            "tool_progress_events": True,
            "approval_events": True,
        },
        "endpoints": {
            "runs": {"method": "POST", "path": "/v1/runs"},
            "run_status": {"method": "GET", "path": "/v1/runs/{run_id}"},
        },
    }


def completed_status(output: str, *, run_id: str = RUN_ID) -> dict:
    return {
        "object": "hermes.run",
        "run_id": run_id,
        "status": "completed",
        "created_at": 1789110000.0,
        "updated_at": 1789110001.0,
        "session_id": "hermes-ext-42",
        "model": "hermes-agent",
        "output": output,
        "usage": {"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
        "last_event": "run.completed",
    }


class FakeHermes:
    def __init__(
        self,
        *,
        output: str = "summary",
        health: dict | None = None,
        capabilities: dict | None = None,
        statuses: list[dict | str] | None = None,
        accepted: dict | None = None,
        post_status_codes: list[int] | None = None,
    ) -> None:
        self.output = output
        self.health = health or ready_health()
        self.capabilities = capabilities or run_capabilities()
        self.statuses = list(statuses or ["completed"])
        self.accepted = accepted or {
            "run_id": RUN_ID,
            "status": "started",
            "replayed": False,
        }
        self.post_status_codes = list(post_status_codes or [202])
        self.requests: list[httpx.Request] = []
        self.run_payload: dict | None = None
        self.idempotency_keys: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json=self.health)
        if request.url.path == "/v1/capabilities":
            return httpx.Response(200, json=self.capabilities)
        if request.url.path == "/v1/runs" and request.method == "POST":
            self.run_payload = json.loads(request.content)
            self.idempotency_keys.append(request.headers.get("Idempotency-Key", ""))
            code = self.post_status_codes.pop(0) if self.post_status_codes else 202
            if code != 202:
                return httpx.Response(code, json={"error": "temporary"})
            return httpx.Response(202, json=self.accepted)
        if request.url.path == f"/v1/runs/{RUN_ID}":
            item = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            if isinstance(item, dict):
                return httpx.Response(200, json=item)
            if item == "completed":
                return httpx.Response(200, json=completed_status(self.output))
            data = {
                "object": "hermes.run",
                "run_id": RUN_ID,
                "status": item,
                "created_at": 1789110000.0,
                "updated_at": 1789110000.5,
                "session_id": "hermes-ext-42",
                "model": "hermes-agent",
            }
            if item == "failed":
                data["error"] = "upstream model failed"
            return httpx.Response(200, json=data)
        return httpx.Response(404, json={"error": "not found"})


def make_provider(
    handler,
    *,
    max_retries: int = 0,
    run_timeout_seconds: float = 1,
    poll_interval_seconds: float = 0,
) -> HermesOrchestratorProvider:
    settings = HermesSettings(
        base_url="https://hermes.test",
        service_token="secret-token",
        timeout_seconds=5,
        max_retries=max_retries,
        run_timeout_seconds=run_timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return HermesOrchestratorProvider(
        HermesClient(settings, transport=httpx.MockTransport(handler))
    )


def assert_secret_headers(fake: FakeHermes) -> None:
    assert fake.requests
    assert all(
        request.headers.get("Authorization") == "Bearer secret-token"
        for request in fake.requests
    )


async def test_descriptor_names_run_backed_platform_operations():
    provider = make_provider(FakeHermes())
    assert provider.descriptor.name == "Hermes Agent API Runs 0.21.1"
    assert provider.descriptor.capabilities == [
        "plan",
        "revise",
        "evaluate",
        "summarize",
    ]


async def test_create_plan_uses_official_routes_and_maps_strict_json():
    output = json.dumps(
        {
            "steps": [
                {
                    "id": "t1",
                    "title": "Cadrer le besoin",
                    "description": "",
                    "role_id": None,
                    "depends_on": [],
                    "estimated_effort": "small",
                },
                {
                    "id": "t2",
                    "title": "Implémenter",
                    "description": "",
                    "role_id": "backend-developer",
                    "depends_on": ["t1"],
                    "estimated_effort": "large",
                },
            ],
            "rationale": "Découpage en deux temps.",
        }
    )
    fake = FakeHermes(output=output, statuses=["queued", "running", "completed"])
    provider = make_provider(fake)

    result = await provider.create_plan(
        PlanningRequest(session=SESSION, goal="Construire l'auth")
    )

    assert result.plan_id == RUN_ID
    assert result.provider_id == "hermes"
    assert [step.id for step in result.steps] == ["t1", "t2"]
    assert result.steps[1].depends_on == ["t1"]
    assert result.steps[1].role_id == "backend-developer"
    assert result.raw["run"]["created_at"] == 1789110000.0
    assert result.raw["run"]["last_event"] == "run.completed"
    assert [request.url.path for request in fake.requests] == [
        "/health/detailed",
        "/v1/capabilities",
        "/v1/runs",
        f"/v1/runs/{RUN_ID}",
        f"/v1/runs/{RUN_ID}",
        f"/v1/runs/{RUN_ID}",
    ]
    assert fake.run_payload is not None
    assert fake.run_payload["session_id"] == "hermes-ext-42"
    submitted = json.loads(fake.run_payload["input"])
    assert submitted == {
        "operation": "plan",
        "payload": {
            "constraints": [],
            "context": {},
            "objective": "Construire l'auth",
        },
    }
    assert "exactly one JSON object" in fake.run_payload["instructions"]
    assert len(fake.idempotency_keys) == 1
    assert re.fullmatch(r"acp-plan-[0-9a-f]{32}", fake.idempotency_keys[0])
    assert_secret_headers(fake)


async def test_revise_plan_keeps_platform_plan_id():
    fake = FakeHermes(
        output=json.dumps(
            {
                "steps": [
                    {
                        "id": "t1",
                        "title": "Cadrer (révisé)",
                        "description": "",
                        "role_id": None,
                        "depends_on": [],
                        "estimated_effort": "medium",
                    }
                ],
                "rationale": "Révision prise en compte.",
            }
        )
    )
    provider = make_provider(fake)

    result = await provider.revise_plan(
        PlanRevisionRequest(
            session=SESSION,
            plan_id="platform-plan-1",
            previous_steps=[PlanStep(id="t1", title="Cadrer le besoin")],
            feedback="Simplifier",
        )
    )

    assert result.plan_id == "platform-plan-1"
    assert result.steps[0].title == "Cadrer (révisé)"
    assert json.loads(fake.run_payload["input"])["operation"] == "revise"


async def test_evaluate_maps_strict_boolean_verdict():
    fake = FakeHermes(
        output=json.dumps(
            {"approved": True, "score": 0.9, "feedback": "Conforme."}
        )
    )
    provider = make_provider(fake)

    result = await provider.evaluate_result(
        EvaluationRequest(session=SESSION, task_summary="Auth livrée")
    )

    assert result.approved is True
    assert result.score == pytest.approx(0.9)
    assert result.feedback == "Conforme."
    assert json.loads(fake.run_payload["input"])["operation"] == "evaluate"


async def test_summarize_uses_completed_run_plain_text():
    fake = FakeHermes(output="Résumé fiable.")
    provider = make_provider(fake)

    result = await provider.summarize_context(
        ContextSummaryRequest(session=SESSION, items=[{"kind": "note", "value": "x"}])
    )

    assert result.summary == "Résumé fiable."
    assert result.provider_id == "hermes"
    assert json.loads(fake.run_payload["input"])["operation"] == "summarize"


async def test_session_fallback_is_namespaced_when_no_external_id_exists():
    session_a = SESSION.model_copy(
        update={"external_session_id": None, "organization_id": "org-a"}
    )
    session_b = SESSION.model_copy(
        update={"external_session_id": None, "organization_id": "org-b"}
    )
    fake_a = FakeHermes(output="A")
    fake_b = FakeHermes(output="B")

    await make_provider(fake_a).summarize_context(
        ContextSummaryRequest(session=session_a, items=[])
    )
    await make_provider(fake_b).summarize_context(
        ContextSummaryRequest(session=session_b, items=[])
    )

    assert re.fullmatch(r"acp-[0-9a-f]{64}", fake_a.run_payload["session_id"])
    assert fake_a.run_payload["session_id"] != fake_b.run_payload["session_id"]


async def test_pydantic_supported_context_values_are_serialized_for_run_input():
    output = json.dumps(
        {
            "steps": [{"id": "t1", "title": "Faire", "depends_on": []}],
            "rationale": "",
        }
    )
    fake = FakeHermes(output=output)
    provider = make_provider(fake)

    await provider.create_plan(
        PlanningRequest(
            session=SESSION,
            goal="x",
            context={"at": datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)},
        )
    )

    submitted = json.loads(fake.run_payload["input"])
    assert submitted["payload"]["context"]["at"] == "2026-09-11T10:00:00Z"


async def test_unsupported_context_value_becomes_provider_error_before_admission():
    fake = FakeHermes()
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="non sérialisable"):
        await provider.create_plan(
            PlanningRequest(session=SESSION, goal="x", context={"bad": object()})
        )

    assert all(request.url.path != "/v1/runs" for request in fake.requests)


async def test_health_uses_authenticated_detailed_readiness_and_capabilities():
    fake = FakeHermes()
    provider = make_provider(fake)

    health = await provider.health_check()

    assert health.available is True
    assert "0.21.1" in health.detail
    assert [request.url.path for request in fake.requests] == [
        "/health/detailed",
        "/v1/capabilities",
    ]
    assert_secret_headers(fake)


@pytest.mark.parametrize(
    ("base_url", "token", "expected"),
    [
        ("", "secret", "HERMES_BASE_URL"),
        ("https://hermes.test", "", "HERMES_API_KEY"),
    ],
)
async def test_incomplete_configuration_fails_closed(base_url, token, expected):
    provider = HermesOrchestratorProvider(
        HermesClient(HermesSettings(base_url=base_url, service_token=token))
    )

    health = await provider.health_check()

    assert health.available is False
    assert expected in health.detail
    with pytest.raises(ProviderUnavailableError, match=expected):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_degraded_readiness_fails_before_capability_or_run_calls():
    health = ready_health(status="degraded")
    health["readiness"]["checks"]["model"]["status"] = "degraded"
    fake = FakeHermes(health=health)
    provider = make_provider(fake)

    result = await provider.health_check()

    assert result.available is False
    assert "model" in result.detail
    assert [request.url.path for request in fake.requests] == ["/health/detailed"]
    with pytest.raises(ProviderUnavailableError, match="Readiness"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))
    assert all(request.url.path != "/v1/runs" for request in fake.requests)


async def test_draining_gateway_is_not_available_for_new_runs():
    fake = FakeHermes(health=ready_health(gateway_state="draining"))
    provider = make_provider(fake)

    health = await provider.health_check()

    assert health.available is False
    assert "draining" in health.detail
    assert [request.url.path for request in fake.requests] == ["/health/detailed"]


async def test_wrong_hermes_version_fails_closed():
    detailed = ready_health()
    detailed["version"] = "0.22.0"
    fake = FakeHermes(health=detailed)
    provider = make_provider(fake)

    health = await provider.health_check()

    assert health.available is False
    assert "0.22.0" in health.detail


async def test_missing_readiness_check_fails_closed():
    detailed = ready_health()
    detailed["readiness"]["checks"].pop("state_db")
    fake = FakeHermes(health=detailed)
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="state_db"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_capabilities_with_optional_extras_remain_compatible():
    fake = FakeHermes()
    provider = make_provider(fake)

    health = await provider.health_check()

    assert health.available is True


async def test_hermes_auth_must_be_required():
    capabilities = run_capabilities()
    capabilities["auth"]["required"] = False
    fake = FakeHermes(capabilities=capabilities)
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="auth.required"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


@pytest.mark.parametrize(
    "feature_path",
    ["run_submission", "run_status", "runs_idempotency.supported", "runs_idempotency.durable"],
)
async def test_missing_required_capability_fails_closed(feature_path):
    capabilities = run_capabilities()
    if "." in feature_path:
        parent, child = feature_path.split(".")
        capabilities["features"][parent][child] = False
    else:
        capabilities["features"][feature_path] = False
    fake = FakeHermes(capabilities=capabilities)
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match=re.escape(feature_path)):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))

    assert all(request.url.path != "/v1/runs" for request in fake.requests)


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled", "interrupted"])
async def test_non_success_terminal_status_fails_closed(terminal_status):
    fake = FakeHermes(statuses=[terminal_status])
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match=terminal_status):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_non_terminal_run_times_out_after_bounded_poll():
    fake = FakeHermes(statuses=["running"])
    provider = make_provider(
        fake,
        run_timeout_seconds=0.01,
        poll_interval_seconds=0.02,
    )

    started = time.monotonic()
    with pytest.raises(ProviderUnavailableError, match="Délai d'attente dépassé"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))

    polls = [request for request in fake.requests if request.url.path.startswith("/v1/runs/")]
    assert polls
    assert time.monotonic() - started < 0.2


@pytest.mark.parametrize("status", ["waiting_for_approval", "stopping"])
async def test_other_non_terminal_states_wait_until_timeout(status):
    fake = FakeHermes(statuses=[status])
    provider = make_provider(
        fake,
        run_timeout_seconds=0.01,
        poll_interval_seconds=0.02,
    )

    with pytest.raises(ProviderUnavailableError, match="Délai d'attente dépassé"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_replayed_terminal_admission_still_polls_for_output():
    output = json.dumps(
        {
            "steps": [{"id": "t1", "title": "Faire", "depends_on": []}],
            "rationale": "",
        }
    )
    fake = FakeHermes(
        output=output,
        accepted={"run_id": RUN_ID, "status": "completed", "replayed": True},
    )
    provider = make_provider(fake)

    result = await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))

    assert result.plan_id == RUN_ID
    assert any(request.url.path == f"/v1/runs/{RUN_ID}" for request in fake.requests)


@pytest.mark.parametrize(
    "terminal_payload",
    [
        {"object": "hermes.run", "run_id": RUN_ID, "status": "completed"},
        {
            "object": "hermes.run",
            "run_id": RUN_ID,
            "status": "completed",
            "output": {"not": "a string"},
        },
        {"object": "wrong.object", "run_id": RUN_ID, "status": "completed", "output": "{}"},
        {"object": "hermes.run", "run_id": RUN_ID, "status": "unknown", "output": "{}"},
        {"object": "hermes.run", "run_id": RUN_ID, "status": "started", "output": "{}"},
    ],
)
async def test_malformed_terminal_status_fails_closed(terminal_payload):
    provider = make_provider(FakeHermes(statuses=[terminal_payload]))

    with pytest.raises(ProviderUnavailableError):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


@pytest.mark.parametrize(
    "bad_output",
    [
        "not json",
        "```json\n{}\n```",
        "[]",
        '{"steps":[{"id":"t1","id":"t2","title":"x"}],"rationale":"duplicate key"}',
        '{"steps":[{"id":"t1","title":"x"}],"rationale":NaN}',
        '{"steps":[],"rationale":"vide"}',
        '{"steps":[{"id":"t1","title":"x","depends_on":["unknown"]}],"rationale":"x"}',
        '{"steps":[{"id":"t1","title":"x","depends_on":["t1"]}],"rationale":"self"}',
        '{"steps":[{"id":"t1","title":"x","depends_on":["t2"]},{"id":"t2","title":"y","depends_on":["t1"]}],"rationale":"cycle"}',
        '{"steps":[{"id":"t1","title":"x"},{"id":"t1","title":"y"}],"rationale":"duplicate"}',
        '{"steps":[{"id":"t1","title":"x"}],"rationale":"x","extra":true}',
    ],
)
async def test_malformed_plan_output_fails_closed(bad_output):
    provider = make_provider(FakeHermes(output=bad_output))

    with pytest.raises(ProviderUnavailableError):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_string_evaluation_boolean_is_rejected():
    fake = FakeHermes(
        output='{"approved":"false","score":0.2,"feedback":"not a boolean"}'
    )
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="évaluation"):
        await provider.evaluate_result(
            EvaluationRequest(session=SESSION, task_summary="x")
        )


@pytest.mark.parametrize(
    "bad_output",
    [
        '{"approved":false,"score":"0.2","feedback":"string score"}',
        '{"approved":false,"score":1.1,"feedback":"too high"}',
        '{"approved":true,"score":-0.1,"feedback":"too low"}',
    ],
)
async def test_invalid_evaluation_score_fails_closed(bad_output):
    provider = make_provider(FakeHermes(output=bad_output))

    with pytest.raises(ProviderUnavailableError, match="évaluation"):
        await provider.evaluate_result(
            EvaluationRequest(session=SESSION, task_summary="x")
        )


async def test_empty_summary_fails_closed():
    provider = make_provider(FakeHermes(output="   \n"))

    with pytest.raises(ProviderUnavailableError, match="sans sortie"):
        await provider.summarize_context(ContextSummaryRequest(session=SESSION, items=[]))


async def test_invalid_admission_run_id_is_rejected_before_status_request():
    fake = FakeHermes(accepted={"run_id": "../health/detailed", "status": "started"})
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="admission"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))

    assert [request.url.path for request in fake.requests] == [
        "/health/detailed",
        "/v1/capabilities",
        "/v1/runs",
    ]


async def test_mismatched_status_run_id_fails_closed():
    fake = FakeHermes(statuses=[completed_status("{}", run_id=OTHER_RUN_ID)])
    provider = make_provider(fake)

    with pytest.raises(ProviderUnavailableError, match="autre run"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_post_retry_reuses_same_idempotency_key():
    output = json.dumps(
        {
            "steps": [{"id": "t1", "title": "Faire", "depends_on": []}],
            "rationale": "",
        }
    )
    fake = FakeHermes(output=output, post_status_codes=[503, 202])
    provider = make_provider(fake, max_retries=1)

    result = await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))

    assert result.plan_id == RUN_ID
    assert len(fake.idempotency_keys) == 2
    assert fake.idempotency_keys[0] == fake.idempotency_keys[1]


async def test_client_does_not_retry_auth_errors_or_follow_redirects():
    calls = []

    def unauthorized(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": "unauthorized"})

    provider = make_provider(unauthorized, max_retries=3)
    with pytest.raises(ProviderUnavailableError, match="HTTP 401"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))
    assert len(calls) == 1

    calls.clear()

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"Location": "http://elsewhere.test"})

    provider = make_provider(redirect, max_retries=3)
    with pytest.raises(ProviderUnavailableError, match="HTTP 307"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{", headers={"Content-Type": "application/json"}),
        httpx.Response(200, json=[]),
    ],
)
async def test_malformed_http_json_fails_closed(response):
    def malformed(_request: httpx.Request) -> httpx.Response:
        return response

    provider = make_provider(malformed)
    with pytest.raises(ProviderUnavailableError, match="Hermes"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_client_does_not_automatically_retry_429():
    calls = []

    def rate_limited(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={
                "error": {
                    "message": "Too many concurrent runs",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "concurrency_limit",
                }
            },
        )

    provider = make_provider(rate_limited, max_retries=3)
    with pytest.raises(ProviderUnavailableError, match="HTTP 429"):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))
    assert len(calls) == 1


def test_api_key_environment_name_and_migration_alias(monkeypatch):
    monkeypatch.setenv("HERMES_SERVICE_TOKEN", "legacy")
    monkeypatch.setenv("HERMES_API_KEY", "primary")
    assert HermesSettings().service_token == "primary"

    monkeypatch.delenv("HERMES_API_KEY")
    assert HermesSettings().service_token == "legacy"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://hermes.example",
        "https://user:secret@hermes.example",
        "https://hermes.example/v1",
        "https://hermes.example?token=secret",
    ],
)
async def test_unsafe_hermes_origin_never_receives_the_api_key(base_url: str):
    requests: list[httpx.Request] = []
    settings = HermesSettings(base_url=base_url, service_token="secret-token")
    client = HermesClient(
        settings,
        transport=httpx.MockTransport(
            lambda request: (
                requests.append(request),
                httpx.Response(200, json={}),
            )[1]
        ),
    )

    assert settings.base_url_invalid is True
    assert "secret-token" not in repr(settings)
    with pytest.raises(ProviderUnavailableError, match="HERMES_BASE_URL invalide"):
        await client.get_json("/health/detailed")
    assert requests == []
