"""ManualOrchestratorProvider : un humain valide ou fournit les plans.

Chaque demande est journalisée dans une file consultable via
`GET /v1/manual/pending` ; un plan minimal est retourné immédiatement pour
ne pas bloquer les workers, et peut être révisé ensuite.
"""

from datetime import datetime, timezone
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


class ManualOrchestratorProvider(OrchestratorProvider):
    def __init__(self) -> None:
        self.pending: dict[str, dict] = {}
        self.resolved: dict[str, dict] = {}

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id="manual",
            kind=ProviderKind.ORCHESTRATOR,
            name="Manual Orchestrator",
            capabilities=["plan", "revise", "evaluate", "summarize"],
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id="manual", available=True,
            detail=f"{len(self.pending)} demande(s) en attente d'un humain",
        )

    def _record(self, kind: str, payload: dict) -> str:
        request_id = uuid4().hex[:12]
        self.pending[request_id] = {
            "id": request_id,
            "kind": kind,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        return request_id

    def resolve(self, request_id: str, resolution: dict) -> bool:
        item = self.pending.pop(request_id, None)
        if item is None:
            return False
        item["resolution"] = resolution
        self.resolved[request_id] = item
        return True

    async def create_plan(self, request: PlanningRequest) -> PlanningResult:
        request_id = self._record("plan", request.model_dump(mode="json"))
        return PlanningResult(
            plan_id=f"manual-{request_id}",
            steps=[PlanStep(id="s1", title=f"Validation humaine : {request.goal}")],
            rationale="En attente d'un plan détaillé fourni par un humain.",
            provider_id="manual",
            raw={"pending_request_id": request_id},
        )

    async def revise_plan(self, request: PlanRevisionRequest) -> PlanningResult:
        request_id = self._record("revise", request.model_dump(mode="json"))
        return PlanningResult(
            plan_id=request.plan_id,
            steps=request.previous_steps,
            rationale=f"Révision soumise à un humain (demande {request_id}).",
            provider_id="manual",
            raw={"pending_request_id": request_id},
        )

    async def evaluate_result(self, request: EvaluationRequest) -> EvaluationResult:
        request_id = self._record("evaluate", request.model_dump(mode="json"))
        return EvaluationResult(
            approved=True,
            score=0.5,
            feedback=f"Approbation provisoire ; revue humaine en attente ({request_id}).",
            provider_id="manual",
        )

    async def summarize_context(self, request: ContextSummaryRequest) -> ContextSummary:
        return ContextSummary(
            summary=f"{len(request.items)} élément(s) transmis pour synthèse humaine.",
            provider_id="manual",
        )
