"""Contrat de communication avec Hermes, version 1.0.

Ces modèles décrivent uniquement le format « sur le fil » de l'API HTTP de
Hermes. Ils sont volontairement distincts des contrats de la plateforme :
si Hermes évolue, seul ce fichier et l'adaptateur changent.
"""

from typing import Any

from pydantic import BaseModel, Field

HERMES_CONTRACT_VERSION = "1.0"


class HermesSessionRef(BaseModel):
    external_session_id: str | None = None
    project_ref: str | None = None
    agent_ref: str | None = None


class HermesPlanRequest(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    session: HermesSessionRef
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class HermesPlanTask(BaseModel):
    ref: str
    label: str
    detail: str = ""
    role: str | None = None
    after: list[str] = Field(default_factory=list)
    effort: str = "medium"


class HermesPlanResponse(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    plan_ref: str
    tasks: list[HermesPlanTask]
    reasoning: str = ""


class HermesReviseRequest(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    session: HermesSessionRef
    plan_ref: str
    tasks: list[HermesPlanTask]
    feedback: str
    context: dict[str, Any] = Field(default_factory=dict)


class HermesEvaluateRequest(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    session: HermesSessionRef
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)
    criteria: list[str] = Field(default_factory=list)


class HermesEvaluateResponse(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    verdict: str  # approved | rejected
    score: float = 0.0
    comments: str = ""


class HermesSummarizeRequest(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    session: HermesSessionRef
    items: list[dict[str, Any]] = Field(default_factory=list)
    max_tokens: int = 1024


class HermesSummarizeResponse(BaseModel):
    contract_version: str = HERMES_CONTRACT_VERSION
    summary: str
