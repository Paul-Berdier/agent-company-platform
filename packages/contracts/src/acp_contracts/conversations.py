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


HermesNativeListingStatus = Literal[
    "available",
    "unavailable",
    "not_configured",
    "unsupported",
]


class HermesNativeSkill(BaseModel):
    """Skill annoncé par Hermes lui-même (`GET /v1/skills`).

    Contenu non fiable et borné : la plateforme l'affiche comme une donnée lue
    et ne réécrit jamais la configuration native d'Hermes.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=200)


class HermesNativeToolset(BaseModel):
    """Toolset annoncé par Hermes lui-même (`GET /v1/toolsets`)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=500)
    enabled: bool
    configured: bool
    tools: list[str] = Field(default_factory=list)


class HermesNativeListing(BaseModel):
    """Résultat d'une lecture seule des skills et toolsets natifs d'Hermes.

    `read_at` n'est renseigné que lorsque les listes ont réellement été lues :
    une lecture impossible reste un état explicite et sans contenu.
    """

    model_config = ConfigDict(extra="forbid")

    status: HermesNativeListingStatus
    skills: list[HermesNativeSkill] = Field(default_factory=list)
    toolsets: list[HermesNativeToolset] = Field(default_factory=list)
    message: str
    read_at: datetime | None = None

    @model_validator(mode="after")
    def require_a_real_read(self) -> "HermesNativeListing":
        if self.status == "available":
            if self.read_at is None:
                raise ValueError("Une lecture réussie doit porter sa date de lecture")
            return self
        if self.skills or self.toolsets:
            raise ValueError("Aucun contenu n'est annonçable sans lecture réussie")
        if self.read_at is not None:
            raise ValueError("Une lecture non aboutie n'a pas de date de lecture")
        return self
