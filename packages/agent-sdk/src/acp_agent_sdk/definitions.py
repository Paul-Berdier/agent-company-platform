"""Définitions déclaratives fournies par les modules métier.

Aucun rôle, station ou workflow n'est codé en dur dans le moteur : tout
provient de ces manifestes chargés depuis `plugins/*/plugin.json`.
"""

from typing import Any

from pydantic import BaseModel, Field


class Capability(BaseModel):
    id: str
    name: str
    description: str = ""
    required_providers: list[str] = Field(default_factory=list)


class RoleDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    sprite: str = "worker"  # clé de sprite générique côté moteur pixel art


class StationDefinition(BaseModel):
    id: str
    name: str
    kind: str = "desk"  # desk, whiteboard, server-rack, lab-bench...
    x: int = 0
    y: int = 0


class WorkflowStep(BaseModel):
    id: str
    name: str
    role_id: str | None = None
    validator: str | None = None  # id d'un validateur fourni par le module


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    project_types: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)


class DepartmentDefinition(BaseModel):
    department_type: str
    name: str
    office_theme: str = "default"
    stations: list[StationDefinition] = Field(default_factory=list)
    available_animations: list[str] = Field(default_factory=list)
    status_mapping: dict[str, str] = Field(default_factory=dict)
    roles: list[RoleDefinition] = Field(default_factory=list)


class ModuleManifest(BaseModel):
    module: str
    version: str = "0.1.0"
    description: str = ""
    departments: list[DepartmentDefinition] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    workflows: list[WorkflowDefinition] = Field(default_factory=list)
    indicators: list[dict[str, Any]] = Field(default_factory=list)
    adapters: list[dict[str, Any]] = Field(default_factory=list)
