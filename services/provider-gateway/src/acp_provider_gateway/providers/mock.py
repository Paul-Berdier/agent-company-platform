"""MockOrchestratorProvider : plans déterministes pour le MVP et les tests."""

from uuid import uuid4

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
from acp_provider_sdk import OrchestratorProvider


class MockOrchestratorProvider(OrchestratorProvider):
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="mock",
            kind=ProviderKind.ORCHESTRATOR,
            name="Mock Orchestrator",
            capabilities=["plan", "revise", "evaluate", "summarize"],
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider_id="mock", available=True, latency_ms=0.1)

    async def create_plan(self, request: PlanningRequest) -> PlanningResult:
        goal = request.goal.strip() or "Objectif"
        steps = [
            PlanStep(id="s1", title=f"Analyser : {goal}", estimated_effort="small"),
            PlanStep(id="s2", title=f"Réaliser : {goal}", depends_on=["s1"]),
            PlanStep(id="s3", title="Contrôler la qualité", depends_on=["s2"],
                     estimated_effort="small"),
        ]
        return PlanningResult(
            plan_id=f"mock-{uuid4().hex[:8]}",
            steps=steps,
            rationale="Plan simulé en trois étapes (analyse, réalisation, contrôle).",
            provider_id="mock",
        )

    async def revise_plan(self, request: PlanRevisionRequest) -> PlanningResult:
        steps = list(request.previous_steps)
        steps.append(
            PlanStep(
                id=f"rev-{len(steps) + 1}",
                title=f"Prendre en compte le retour : {request.feedback[:80]}",
                depends_on=[steps[-1].id] if steps else [],
            )
        )
        return PlanningResult(
            plan_id=request.plan_id,
            steps=steps,
            rationale="Révision simulée : une étape ajoutée pour le retour.",
            provider_id="mock",
        )

    async def evaluate_result(self, request: EvaluationRequest) -> EvaluationResult:
        return EvaluationResult(
            approved=True,
            score=0.85,
            feedback="Résultat simulé conforme aux critères.",
            provider_id="mock",
        )

    async def summarize_context(self, request: ContextSummaryRequest) -> ContextSummary:
        count = len(request.items)
        return ContextSummary(
            summary=f"Résumé simulé de {count} élément(s) de contexte.",
            provider_id="mock",
        )
