"""Contrats partagés pour les workers d'exécution distants."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkerCapability(str, Enum):
    GIT = "git"
    FILESYSTEM_PROJECT = "filesystem_project"
    SHELL_RESTRICTED = "shell_restricted"
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    BLENDER = "blender"
    BLENDER_MCP = "blender_mcp"
    UNREAL_ENGINE = "unreal_engine"
    UNREAL_MCP = "unreal_mcp"
    NANOSWORLD_COOK = "nanosworld_cook"
    ASSET_VALIDATION = "asset_validation"
    IMAGE_CAPTURE = "image_capture"


class WorkerStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    REVOKED = "revoked"


class WorkerRegistrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capabilities: list[WorkerCapability] = Field(default_factory=list)
    max_concurrency: int = Field(default=1, ge=1, le=32)
    simulation: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[WorkerCapability]) -> list[WorkerCapability]:
        return list(dict.fromkeys(value))


class WorkerRegistrationResponse(BaseModel):
    worker_id: str
    token: str
    token_expires_at: datetime
    heartbeat_interval_seconds: int


class WorkerHeartbeatRequest(BaseModel):
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
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_seen_at: datetime | None = None
    lease_expires_at: datetime | None = None
    token_expires_at: datetime
    created_at: datetime | None = None


class WorkerClaimRequest(BaseModel):
    provider_id: str = "mock"


class WorkerLeaseResponse(BaseModel):
    worker_id: str
    task_run_id: str
    lease_expires_at: datetime
