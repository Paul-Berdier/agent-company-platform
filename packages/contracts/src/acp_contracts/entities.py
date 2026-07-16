from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import AgentStatus, TaskRunStatus, TaskStatus


class _Entity(BaseModel):
    id: str
    created_at: datetime | None = None


class Organization(_Entity):
    name: str
    description: str = ""


class Workspace(_Entity):
    organization_id: str
    name: str
    kind: str = "generic"  # personnel, professionnel, scolaire, expérimental...
    description: str = ""


class Department(_Entity):
    workspace_id: str
    name: str
    department_type: str  # référence un type fourni par un module (plugin)
    office_theme: str = "default"
    config: dict[str, Any] = Field(default_factory=dict)


class Project(_Entity):
    workspace_id: str
    department_id: str | None = None
    name: str
    project_type: str = "generic"  # web-app, data-pipeline, research, game...
    description: str = ""
    status: str = "active"


class Team(_Entity):
    project_id: str
    name: str
    mission: str = ""


class TeamMember(BaseModel):
    team_id: str
    agent_instance_id: str
    role_id: str | None = None


class AgentInstance(_Entity):
    team_id: str | None = None
    workspace_id: str
    name: str
    role_id: str  # rôle défini par un module, jamais codé en dur dans le cœur
    module: str = "core"
    status: AgentStatus = AgentStatus.IDLE
    capabilities: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class Task(_Entity):
    project_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    workflow_step: str | None = None
    priority: int = 3
    meta: dict[str, Any] = Field(default_factory=dict)


class TaskRun(_Entity):
    task_id: str
    agent_instance_id: str | None = None
    session_id: str | None = None
    status: TaskRunStatus = TaskRunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    plan: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
