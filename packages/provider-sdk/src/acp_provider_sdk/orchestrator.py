"""Abstraction des orchestrator providers.

Le cœur de la plateforme ne connaît que cette interface. Hermes, Claude,
Codex ou un orchestrateur manuel en sont des implémentations
interchangeables, branchées dans le provider-gateway.
"""

from abc import ABC, abstractmethod

from acp_contracts import (
    ContextSummary,
    ContextSummaryRequest,
    EvaluationRequest,
    EvaluationResult,
    PlanningRequest,
    PlanningResult,
    PlanRevisionRequest,
    ProviderDescriptor,
    ProviderHealth,
)


class OrchestratorProvider(ABC):
    """Contrat unique de tout orchestrateur (mock, manual, hermes, claude...)."""

    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        ...

    @abstractmethod
    async def create_plan(self, request: PlanningRequest) -> PlanningResult:
        ...

    @abstractmethod
    async def revise_plan(self, request: PlanRevisionRequest) -> PlanningResult:
        ...

    @abstractmethod
    async def evaluate_result(self, request: EvaluationRequest) -> EvaluationResult:
        ...

    @abstractmethod
    async def summarize_context(self, request: ContextSummaryRequest) -> ContextSummary:
        ...
