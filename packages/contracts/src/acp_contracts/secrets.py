"""Contrats du coffre de secrets.

La valeur d'un secret n'entre que par ``SecretCreate``/``SecretRotate`` et ne
ressort jamais : ``SecretSummary`` ne contient que des métadonnées.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SecretScopeType = Literal["platform", "project"]
SECRET_NAME_PATTERN = r"^[A-Z][A-Z0-9_]{1,62}$"
SECRET_VALUE_MAX_CHARS = 8192


class SecretCreate(BaseModel):
    name: str = Field(pattern=SECRET_NAME_PATTERN)
    value: str = Field(min_length=1, max_length=SECRET_VALUE_MAX_CHARS, repr=False)
    scope_type: SecretScopeType = "platform"
    project_id: str | None = None
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def scope_matches_project(self) -> "SecretCreate":
        if self.scope_type == "project" and not self.project_id:
            raise ValueError("un secret de portée « project » exige project_id")
        if self.scope_type == "platform" and self.project_id is not None:
            raise ValueError("un secret de portée « platform » n'accepte pas de project_id")
        return self


class SecretRotate(BaseModel):
    value: str = Field(min_length=1, max_length=SECRET_VALUE_MAX_CHARS, repr=False)


class SecretSummary(BaseModel):
    id: str
    name: str
    scope_type: SecretScopeType
    project_id: str | None = None
    description: str = ""
    key_id: str
    created_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    referenced_by_mcp_servers: list[str] = Field(default_factory=list)  # ids


class SecretsStatus(BaseModel):
    configured: bool
    primary_key_id: str | None = None
    key_count: int = 0
    message: str
