"""Modèles de la surface HTTP officielle Hermes Agent utilisée par le gateway.

La plateforme conserve son propre contrat planification/évaluation. Ces
modèles ne prétendent pas qu'Hermes expose ces opérations : elles sont
traduites en runs Hermes puis validées à la frontière de l'adaptateur.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

HERMES_API_VERSION = "0.21.1"
# Alias conservé pour les imports existants ; il désigne désormais la version
# d'API Hermes vérifiée, et non un contrat HTTP inventé par la plateforme.
HERMES_CONTRACT_VERSION = HERMES_API_VERSION


class HermesWireModel(BaseModel):
    """Valide le noyau v0.21.1 tout en conservant ses métadonnées officielles."""

    model_config = ConfigDict(extra="allow")


class HermesReadinessCheck(HermesWireModel):
    status: Literal["ok", "degraded"]


class HermesReadiness(HermesWireModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, HermesReadinessCheck]


class HermesDetailedHealth(HermesWireModel):
    status: Literal["ok", "degraded"]
    readiness: HermesReadiness
    platform: Literal["hermes-agent"]
    version: str = Field(min_length=1)
    gateway_state: str = Field(min_length=1)


class HermesAuthCapabilities(HermesWireModel):
    type: Literal["bearer"]
    required: bool


class HermesIdempotencyCapabilities(HermesWireModel):
    supported: bool
    durable: bool
    retention_seconds: int = Field(gt=0)


class HermesFeatures(HermesWireModel):
    """Sous-ensemble nécessaire à l'adaptateur synchrone fondé sur les runs."""

    run_submission: bool
    run_status: bool
    runs_idempotency: HermesIdempotencyCapabilities


class HermesCapabilities(HermesWireModel):
    object: Literal["hermes.api_server.capabilities"]
    platform: Literal["hermes-agent"]
    model: str = Field(min_length=1)
    auth: HermesAuthCapabilities
    features: HermesFeatures


class HermesRunRequest(BaseModel):
    input: str = Field(min_length=1)
    session_id: str | None = None
    instructions: str = Field(min_length=1)


HermesRunAcceptedState = Literal[
    "started",
    "queued",
    "running",
    "waiting_for_approval",
    "stopping",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]

HermesRunStatusState = Literal[
    "queued",
    "running",
    "waiting_for_approval",
    "stopping",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]


class HermesRunAccepted(HermesWireModel):
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    status: HermesRunAcceptedState
    replayed: bool = False


class HermesRunStatus(HermesWireModel):
    object: Literal["hermes.run"]
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    status: HermesRunStatusState
    session_id: str | None = None
    model: str | None = None
    output: str | None = None
    error: str | None = None
    usage: dict[str, Any] | None = None


class HermesPlanOutputStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    role_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    estimated_effort: str = "medium"


class HermesPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[HermesPlanOutputStep] = Field(min_length=1)
    rationale: str = ""

    @model_validator(mode="after")
    def validate_dependencies(self) -> "HermesPlanOutput":
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        known = set(ids)
        for step in self.steps:
            if step.id in step.depends_on:
                raise ValueError("a step cannot depend on itself")
            if unknown := set(step.depends_on).difference(known):
                raise ValueError(f"unknown dependency ids: {sorted(unknown)}")
        unresolved = {step.id: set(step.depends_on) for step in self.steps}
        resolved: set[str] = set()
        while unresolved:
            ready = {step_id for step_id, deps in unresolved.items() if deps <= resolved}
            if not ready:
                raise ValueError("step dependencies must be acyclic")
            resolved.update(ready)
            for step_id in ready:
                unresolved.pop(step_id)
        return self


class HermesEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: StrictBool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str = ""
