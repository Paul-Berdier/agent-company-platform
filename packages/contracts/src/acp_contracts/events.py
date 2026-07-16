from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """Événement métier réel diffusé au front pixel art et journalisé."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str  # ex: task.started, agent.status_changed, task.progress
    occurred_at: datetime = Field(default_factory=_now)
    organization_id: str | None = None
    workspace_id: str | None = None
    department_id: str | None = None
    project_id: str | None = None
    team_id: str | None = None
    agent_instance_id: str | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    version: str = "1.0"
    events: list[Event]
