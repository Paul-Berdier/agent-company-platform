"""Contrats utilisateur pour piloter une mission et ses tentatives.

Une mission est l'intention durable. Chaque exécution est une tentative immuable :
une relance crée toujours un nouveau ``MissionRun`` avec un fencing token supérieur.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .limits import DatabaseModel as BaseModel
from .limits import Int64, captured_local_process_data

MAX_BUDGET_COST = 999_999_999_999.0
"""Plafond représentable sans saturer le ledger monétaire NUMERIC(18, 6)."""

MAX_BUDGET_COUNTER = 9_007_199_254_740_991
"""Plus grand compteur entier exact à la fois en Python, SQL BIGINT et JavaScript."""


class MissionRunStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    STOPPING = "stopping"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class AutonomyMode(str, Enum):
    SUPERVISED = "supervised"
    BOUNDED = "bounded"
    AUTONOMOUS = "autonomous"


class MissionAutonomy(BaseModel):
    mode: AutonomyMode = AutonomyMode.BOUNDED
    allowed_actions: list[str] = Field(default_factory=list, max_length=100)
    forbidden_actions: list[str] = Field(default_factory=list, max_length=100)
    approval_required_actions: list[str] = Field(default_factory=list, max_length=100)


class MissionResource(BaseModel):
    kind: str = Field(min_length=1, max_length=100)
    identifier: str = Field(min_length=1, max_length=1000)
    access: Literal["read", "write"] = "read"
    description: str = Field(default="", max_length=1000)


class MissionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cost: float | None = Field(
        default=None,
        ge=0,
        le=MAX_BUDGET_COST,
        allow_inf_nan=False,
        strict=True,
    )
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    max_tokens: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )
    max_tool_calls: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def has_a_limit(self) -> "MissionBudget":
        if self.max_cost is None and self.max_tokens is None and self.max_tool_calls is None:
            raise ValueError("le budget doit définir au moins une limite")
        return self


class MissionCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=10_000)
    expected_outcome: str = Field(min_length=1, max_length=10_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    autonomy: MissionAutonomy
    resources: list[MissionResource] = Field(default_factory=list, max_length=100)
    budget: MissionBudget
    duration_seconds: int = Field(ge=1, le=31_536_000)
    team_id: str | None = None
    agent_instance_id: str | None = None
    priority: int = Field(default=3, ge=1, le=5)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("acceptance_criteria", "required_capabilities")
    @classmethod
    def unique_non_empty_strings(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("les valeurs vides sont interdites")
        return list(dict.fromkeys(cleaned))


class TechnicalValidation(BaseModel):
    status: Literal["pending", "passed", "failed"] = "pending"
    summary: str = Field(default="", max_length=10_000)
    checked_at: datetime | None = None


class UserAcceptance(BaseModel):
    status: Literal["pending", "accepted", "rejected"] = "pending"
    comment: str = Field(default="", max_length=10_000)
    decided_by: str | None = None
    decided_at: datetime | None = None


class EvidenceCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any] = Field(default_factory=dict)
    command: str | None = Field(default=None, max_length=4000)
    exit_code: Int64 | None = None
    uri: str | None = Field(default=None, max_length=2000)
    checksum: str | None = Field(default=None, max_length=200)

    @field_validator("data", mode="before")
    @classmethod
    def captured_streams(cls, value, info):
        if info.data.get("kind") == "local_process":
            return captured_local_process_data(value)
        return value


class MissionEvidence(EvidenceCreate):
    id: str
    task_run_id: str
    worker_id: str
    created_at: datetime | None = None


class MissionRun(BaseModel):
    id: str
    mission_id: str
    attempt_number: int
    fencing_token: int
    status: MissionRunStatus
    agent_instance_id: str | None = None
    session_id: str | None = None
    stop_requested: bool = False
    stop_requested_at: datetime | None = None
    technical_validation: TechnicalValidation = Field(default_factory=TechnicalValidation)
    user_acceptance: UserAcceptance = Field(default_factory=UserAcceptance)
    evidence: list[MissionEvidence] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class MissionSummary(BaseModel):
    id: str
    project_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None
    title: str
    objective: str
    expected_outcome: str
    acceptance_criteria: list[str]
    autonomy: MissionAutonomy
    resources: list[MissionResource]
    budget: MissionBudget
    duration_seconds: int
    priority: int
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)
    status: MissionRunStatus
    current_run: MissionRun
    created_at: datetime | None = None


class MissionDetail(MissionSummary):
    runs: list[MissionRun] = Field(default_factory=list)


class MissionStopResponse(BaseModel):
    mission_id: str
    run: MissionRun
    already_stopped: bool


class MissionRetryRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class MissionCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    run_id: str | None = None

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("le commentaire ne peut pas être vide")
        return value


class MissionComment(BaseModel):
    id: str
    mission_id: str
    run_id: str | None = None
    author_user_id: str
    body: str
    created_at: datetime | None = None


class MissionAcceptanceDecision(BaseModel):
    decision: Literal["accepted", "rejected"]
    comment: str = Field(default="", max_length=10_000)
