"""Contrats versionnés des conversations pilotées par Hermes."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ConversationStatus = Literal["active", "archived"]
ConversationTurnStatus = Literal[
    "submitting",
    "running",
    "completed",
    "failed",
    "interrupted",
]
ConnectionStatus = Literal["connected", "degraded", "unavailable"]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationTurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=100_000)
    model: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConversationStatus | None = None

    @model_validator(mode="after")
    def require_change(self) -> "ConversationPatch":
        if self.title is None and self.status is None:
            raise ValueError("Au moins une modification est requise")
        return self


class ConversationTurn(BaseModel):
    id: str
    client_request_id: str
    status: ConversationTurnStatus
    user_content: str
    assistant_content: str | None = None
    provider_run_id: str | None = None
    provider_model: str | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationTurnList(BaseModel):
    items: list[ConversationTurn] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    id: str
    project_id: str | None
    title: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    turns: list[ConversationTurn] = Field(default_factory=list)


class ConversationList(BaseModel):
    items: list[ConversationSummary] = Field(default_factory=list)


class HermesConnectionDiagnostic(BaseModel):
    status: ConnectionStatus
    healthy: bool
    message: str
    capabilities: list[str] = Field(default_factory=list)
    checked_at: datetime
