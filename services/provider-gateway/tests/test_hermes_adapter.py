"""Tests d'intégration simulés de l'adaptateur Hermes.

Un faux serveur Hermes (httpx.MockTransport) répond au contrat v1 ; on
vérifie la traduction vers les contrats de la plateforme et la résilience
quand Hermes est absent ou en panne.
"""

import httpx
import pytest

from acp_contracts import (
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

SESSION = SessionContext(
    session_id="sess-1",
    organization_id="org-1",
    workspace_id="ws-1",
    project_id="proj-1",
    agent_instance_id="agent-1",
    provider_id="hermes",
    external_session_id="hermes-ext-42",
)


def fake_hermes(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/v1/plans":
        return httpx.Response(200, json={
            "contract_version": "1.0",
            "plan_ref": "hermes-plan-1",
            "tasks": [
                {"ref": "t1", "label": "Cadrer le besoin", "detail": "", "after": []},
                {"ref": "t2", "label": "Implémenter", "detail": "", "after": ["t1"],
                 "role": "backend-developer", "effort": "large"},
            ],
            "reasoning": "Découpage en deux temps.",
        })
    if request.url.path.endswith("/revisions"):
        return httpx.Response(200, json={
            "contract_version": "1.0",
            "plan_ref": "hermes-plan-1",
            "tasks": [{"ref": "t1", "label": "Cadrer (révisé)", "detail": "", "after": []}],
            "reasoning": "Révision prise en compte.",
        })
    if request.url.path == "/v1/evaluations":
        return httpx.Response(200, json={
            "contract_version": "1.0",
            "verdict": "approved",
            "score": 0.9,
            "comments": "Conforme.",
        })
    return httpx.Response(404)


def make_provider(transport: httpx.AsyncBaseTransport) -> HermesOrchestratorProvider:
    settings = HermesSettings(base_url="http://hermes.test", service_token="token",
                              timeout_seconds=5, max_retries=1)
    return HermesOrchestratorProvider(HermesClient(settings, transport=transport))


async def test_create_plan_maps_contract():
    provider = make_provider(httpx.MockTransport(fake_hermes))
    result = await provider.create_plan(PlanningRequest(session=SESSION, goal="Construire l'auth"))
    assert result.plan_id == "hermes-plan-1"
    assert result.provider_id == "hermes"
    assert [s.id for s in result.steps] == ["t1", "t2"]
    assert result.steps[1].depends_on == ["t1"]
    assert result.steps[1].role_id == "backend-developer"


async def test_revise_plan_maps_contract():
    provider = make_provider(httpx.MockTransport(fake_hermes))
    result = await provider.revise_plan(PlanRevisionRequest(
        session=SESSION, plan_id="hermes-plan-1",
        previous_steps=[PlanStep(id="t1", title="Cadrer le besoin")],
        feedback="Simplifier",
    ))
    assert result.steps[0].title == "Cadrer (révisé)"


async def test_evaluate_maps_verdict():
    provider = make_provider(httpx.MockTransport(fake_hermes))
    result = await provider.evaluate_result(EvaluationRequest(
        session=SESSION, task_summary="Auth livrée"
    ))
    assert result.approved is True
    assert result.score == pytest.approx(0.9)


async def test_health_ok():
    provider = make_provider(httpx.MockTransport(fake_hermes))
    health = await provider.health_check()
    assert health.available is True


async def test_unconfigured_is_unavailable_not_crash():
    provider = HermesOrchestratorProvider(HermesClient(HermesSettings(base_url="")))
    health = await provider.health_check()
    assert health.available is False
    with pytest.raises(ProviderUnavailableError):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))


async def test_server_error_raises_unavailable_after_retries():
    calls = {"count": 0}

    def failing(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    provider = make_provider(httpx.MockTransport(failing))
    with pytest.raises(ProviderUnavailableError):
        await provider.create_plan(PlanningRequest(session=SESSION, goal="x"))
    assert calls["count"] == 2  # 1 essai + 1 retry (max_retries=1)
