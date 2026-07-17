"""Contrats des artefacts, verrous et approbations sensibles."""

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResourceType(str, Enum):
    GIT_REPOSITORY = "git_repository"
    GIT_BRANCH = "git_branch"
    FILESYSTEM_PATH = "filesystem_path"
    BLENDER_FILE = "blender_file"
    UNREAL_ASSET = "unreal_asset"
    UNREAL_MAP = "unreal_map"
    BUILD_TARGET = "build_target"


class LockAcquireRequest(BaseModel):
    worker_id: str
    owner_run_id: str
    resource_type: ResourceType
    resource_key: str = Field(min_length=1, max_length=1000)
    lease_seconds: int = Field(default=60, ge=15, le=300)


class LockOwnerRequest(BaseModel):
    worker_id: str
    owner_run_id: str
    lease_seconds: int = Field(default=60, ge=15, le=300)


class ResourceLock(BaseModel):
    id: str
    resource_type: ResourceType
    resource_key: str
    owner_run_id: str
    worker_id: str
    status: str
    lease_expires_at: datetime
    created_at: datetime | None = None


class ApprovalAction(str, Enum):
    DELETE_FILES = "delete_files"
    DELETE_ASSETS = "delete_assets"
    MODIFY_MAIN_MAP = "modify_main_map"
    IMPORT_FINAL_ASSET = "import_final_asset"
    BUILD_OR_COOK = "build_or_cook"
    GIT_PUBLISH = "git_publish"
    MERGE = "merge"
    DEPLOY = "deploy"
    PRODUCTION_ACTION = "production_action"
    PAID_PURCHASE_OR_DOWNLOAD = "paid_purchase_or_download"
    CROSS_PROJECT_CONTEXT = "cross_project_context"
    NEW_SECRET_ACCESS = "new_secret_access"


class ApprovalStatus(str, Enum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalRequestCreate(BaseModel):
    project_id: str
    task_run_id: str | None = None
    action: ApprovalAction
    reason: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    expires_in_seconds: int = Field(default=3600, ge=60, le=86400)


class ApprovalDecision(BaseModel):
    decision: ApprovalStatus
    comment: str = Field(default="", max_length=2000)

    @field_validator("decision")
    @classmethod
    def final_decision(cls, value: ApprovalStatus) -> ApprovalStatus:
        if value not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise ValueError("la décision doit être APPROVED ou REJECTED")
        return value


class ApprovalRequest(BaseModel):
    id: str
    project_id: str
    task_run_id: str | None = None
    action: ApprovalAction
    reason: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus
    requested_by: str
    decided_by: str | None = None
    decision_comment: str = ""
    decided_at: datetime | None = None
    expires_at: datetime
    created_at: datetime | None = None


class ArtifactCreate(BaseModel):
    project_id: str
    task_run_id: str
    kind: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=1000)
    checksum: str | None = Field(default=None, max_length=200)
    size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def project_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("le chemin d'artefact doit rester relatif au projet")
        return normalized


class Artifact(BaseModel):
    id: str
    project_id: str
    task_run_id: str
    worker_id: str
    kind: str
    path: str
    checksum: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
