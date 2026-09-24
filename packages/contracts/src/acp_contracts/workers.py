"""Contrats partagés pour les workers d'exécution distants."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from .limits import DatabaseModel as BaseModel
from .limits import Text100


class WorkerCapability(str, Enum):
    GIT = "git"
    FILESYSTEM_PROJECT = "filesystem_project"
    SHELL_RESTRICTED = "shell_restricted"
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    AGENT_TEAM = "agent_team"
    BLENDER = "blender"
    BLENDER_MCP = "blender_mcp"
    UNREAL_ENGINE = "unreal_engine"
    UNREAL_MCP = "unreal_mcp"
    NANOSWORLD_COOK = "nanosworld_cook"
    ASSET_VALIDATION = "asset_validation"
    IMAGE_CAPTURE = "image_capture"
    MCP_STDIO_PROBE = "mcp_stdio_probe"
    WEB_TESTS = "web_tests"


class WorkerStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    REVOKED = "revoked"


class WorkerRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    capabilities: list[WorkerCapability] = Field(default_factory=list)
    max_concurrency: int = Field(default=1, ge=1, le=32)
    simulation: bool = True
    project_id: str | None = Field(default=None, min_length=1, max_length=36)
    global_access: bool = Field(default=False, strict=True)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[WorkerCapability]) -> list[WorkerCapability]:
        return list(dict.fromkeys(value))

    @field_validator("project_id")
    @classmethod
    def clean_project_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("le projet du worker ne peut pas être vide")
        return cleaned

    @model_validator(mode="after")
    def exactly_one_claim_scope(self) -> "WorkerRegistrationRequest":
        if self.global_access == (self.project_id is not None):
            raise ValueError(
                "un worker doit avoir exactement un périmètre : projet ou global"
            )
        return self


class WorkerRegistrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=36)
    token: str = Field(min_length=1)
    token_expires_at: datetime
    heartbeat_interval_seconds: int = Field(ge=1, strict=True)
    project_id: str | None = Field(min_length=1, max_length=36)
    global_access: bool = Field(strict=True)

    @model_validator(mode="after")
    def exactly_one_claim_scope(self) -> "WorkerRegistrationResponse":
        if self.global_access == (self.project_id is not None):
            raise ValueError(
                "la réponse doit confirmer exactement un périmètre worker"
            )
        return self


class WorkerHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[WorkerCapability] | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=32)
    simulation: bool | None = None


class WorkerHeartbeatResponse(BaseModel):
    worker_id: str
    status: WorkerStatus
    server_time: datetime
    lease_expires_at: datetime
    active_runs: int


class WorkerSnapshot(BaseModel):
    id: str
    name: str
    capabilities: list[WorkerCapability] = Field(default_factory=list)
    max_concurrency: int
    active_runs: int
    status: WorkerStatus
    simulation: bool
    project_id: str | None
    global_access: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_seen_at: datetime | None = None
    lease_expires_at: datetime | None = None
    token_expires_at: datetime
    created_at: datetime | None = None


class WorkerClaimRequest(BaseModel):
    provider_id: Text100 = "mock"


class WorkerLeaseResponse(BaseModel):
    worker_id: str
    task_run_id: str
    lease_expires_at: datetime
    status: str | None = None
    stop_requested: bool = False
    fencing_token: int | None = None
