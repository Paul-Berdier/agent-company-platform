"""HermesOrchestratorProvider : traduit les contrats plateforme ↔ contrat Hermes v1.

Hermes conserve sa mémoire interne ; la plateforme ne transmet que le
contexte explicitement fourni dans la requête (jamais un autre projet).
"""

import time

from acp_contracts import (
    ContextSummary,
    ContextSummaryRequest,
    EvaluationRequest,
    EvaluationResult,
    PlanningRequest,
    PlanningResult,
    PlanRevisionRequest,
    PlanStep,
    ProviderDescriptor,
    ProviderHealth,
)
from acp_contracts.enums import ProviderKind
from acp_contracts.sessions import SessionContext
from acp_provider_sdk import OrchestratorProvider, ProviderUnavailableError

from .client import HermesClient
from .contracts import (
    HermesEvaluateRequest,
    HermesEvaluateResponse,
    HermesPlanRequest,
    HermesPlanResponse,
    HermesPlanTask,
    HermesReviseRequest,
    HermesSessionRef,
    HermesSummarizeRequest,
    HermesSummarizeResponse,
)


def _session_ref(session: SessionContext) -> HermesSessionRef:
    return HermesSessionRef(
        external_session_id=session.external_session_id,
        project_ref=session.project_id,
        agent_ref=session.agent_instance_id,
    )


def _steps_from_tasks(tasks: list[HermesPlanTask]) -> list[PlanStep]:
    return [
        PlanStep(id=t.ref, title=t.label, description=t.detail,
                 role_id=t.role, depends_on=t.after, estimated_effort=t.effort)
        for t in tasks
    ]


def _tasks_from_steps(steps: list[PlanStep]) -> list[HermesPlanTask]:
    return [
        HermesPlanTask(ref=s.id, label=s.title, detail=s.description,
                       role=s.role_id, after=s.depends_on, effort=s.estimated_effort)
        for s in steps
    ]


class HermesOrchestratorProvider(OrchestratorProvider):
    def __init__(self, client: HermesClient | None = None) -> None:
        self._client = client or HermesClient()

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="hermes",
            kind=ProviderKind.ORCHESTRATOR,
            name="Hermes",
            capabilities=["plan", "revise", "evaluate", "summarize"],
        )

    async def health_check(self) -> ProviderHealth:
        if not self._client.settings.configured:
            return ProviderHealth(provider_id="hermes", available=False,
                                  detail="HERMES_BASE_URL non configurée")
        start = time.perf_counter()
        try:
            await self._client.get_json("/health")
        except ProviderUnavailableError as exc:
            return ProviderHealth(provider_id="hermes", available=False, detail=str(exc))
        latency = (time.perf_counter() - start) * 1000
        return ProviderHealth(provider_id="hermes", available=True, latency_ms=latency)

    async def create_plan(self, request: PlanningRequest) -> PlanningResult:
        wire = HermesPlanRequest(
            session=_session_ref(request.session),
            objective=request.goal,
            context=request.context,
            constraints=request.constraints,
        )
        data = await self._client.post_json("/v1/plans", wire.model_dump(mode="json"))
        resp = HermesPlanResponse.model_validate(data)
        return PlanningResult(
            plan_id=resp.plan_ref,
            steps=_steps_from_tasks(resp.tasks),
            rationale=resp.reasoning,
            provider_id="hermes",
            raw=data,
        )

    async def revise_plan(self, request: PlanRevisionRequest) -> PlanningResult:
        wire = HermesReviseRequest(
            session=_session_ref(request.session),
            plan_ref=request.plan_id,
            tasks=_tasks_from_steps(request.previous_steps),
            feedback=request.feedback,
            context=request.context,
        )
        data = await self._client.post_json(
            f"/v1/plans/{request.plan_id}/revisions", wire.model_dump(mode="json")
        )
        resp = HermesPlanResponse.model_validate(data)
        return PlanningResult(
            plan_id=resp.plan_ref,
            steps=_steps_from_tasks(resp.tasks),
            rationale=resp.reasoning,
            provider_id="hermes",
            raw=data,
        )

    async def evaluate_result(self, request: EvaluationRequest) -> EvaluationResult:
        wire = HermesEvaluateRequest(
            session=_session_ref(request.session),
            summary=request.task_summary,
            output=request.produced_output,
            criteria=request.acceptance_criteria,
        )
        data = await self._client.post_json("/v1/evaluations", wire.model_dump(mode="json"))
        resp = HermesEvaluateResponse.model_validate(data)
        return EvaluationResult(
            approved=resp.verdict == "approved",
            score=resp.score,
            feedback=resp.comments,
            provider_id="hermes",
        )

    async def summarize_context(self, request: ContextSummaryRequest) -> ContextSummary:
        wire = HermesSummarizeRequest(
            session=_session_ref(request.session),
            items=request.items,
            max_tokens=request.max_tokens,
        )
        data = await self._client.post_json("/v1/summaries", wire.model_dump(mode="json"))
        resp = HermesSummarizeResponse.model_validate(data)
        return ContextSummary(summary=resp.summary, provider_id="hermes")
