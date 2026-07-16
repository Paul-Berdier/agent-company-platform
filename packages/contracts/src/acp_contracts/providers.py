"""Contrats des orchestrator providers (version 1.0).

Toute communication avec un orchestrateur externe (Hermes, Claude, Codex, ...)
passe par ces modèles — jamais par les classes internes du service distant.
"""

from typing import Any

from pydantic import BaseModel, Field

from .enums import ProviderKind
from .sessions import SessionContext

PROVIDER_CONTRACT_VERSION = "1.0"


class ProviderDescriptor(BaseModel):
    id: str
    kind: ProviderKind
    name: str
    contract_version: str = PROVIDER_CONTRACT_VERSION
    capabilities: list[str] = Field(default_factory=list)


class ProviderHealth(BaseModel):
    provider_id: str
    available: bool
    latency_ms: float | None = None
    detail: str = ""


class PlanStep(BaseModel):
    id: str
    title: str
    description: str = ""
    role_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    estimated_effort: str = "medium"


class PlanningRequest(BaseModel):
    session: SessionContext
    goal: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class PlanningResult(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    rationale: str = ""
    provider_id: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class PlanRevisionRequest(BaseModel):
    session: SessionContext
    plan_id: str
    previous_steps: list[PlanStep]
    feedback: str
    context: dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    session: SessionContext
    task_summary: str
    produced_output: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    approved: bool
    score: float = 0.0
    feedback: str = ""
    provider_id: str = ""


class ContextSummaryRequest(BaseModel):
    session: SessionContext
    items: list[dict[str, Any]] = Field(default_factory=list)
    max_tokens: int = 1024


class ContextSummary(BaseModel):
    summary: str
    provider_id: str = ""
