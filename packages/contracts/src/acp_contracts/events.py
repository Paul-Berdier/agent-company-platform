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


# --- Lot E : flux durable par run --------------------------------------------

EVENT_SCHEMA_VERSION = "1.0"
"""Version du schéma d'événement transporté par le flux (``StreamEvent``)."""


class StreamEvent(BaseModel):
    """Événement tel qu'il est rendu au flux authentifié et aux lectures paginées.

    ``sequence`` est la séquence monotone allouée par run dans la transaction
    métier : elle sert de curseur de reprise (``Last-Event-ID``, ``after_seq``).
    Elle est absente des lignes historiques écrites avant le Lot E.

    Aucun média ne transite ici : le ``payload`` d'un événement de média ne porte
    qu'une référence d'artefact (``artifact_id``, ``content_type``, ``size_bytes``,
    ``sha256``, ``stream_kind``).
    """

    schema_version: str = Field(default=EVENT_SCHEMA_VERSION, max_length=10)
    id: str = Field(max_length=36)
    sequence: int | None = Field(default=None, ge=1)
    type: str = Field(max_length=100)
    occurred_at: datetime
    project_id: str | None = Field(default=None, max_length=36)
    conversation_id: str | None = Field(default=None, max_length=36)
    task_id: str | None = Field(default=None, max_length=36)
    task_run_id: str | None = Field(default=None, max_length=36)
    step_id: str | None = Field(default=None, max_length=64)
    executor: str | None = Field(default=None, max_length=64)
    emitted_by: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventPage(BaseModel):
    """Page de journal rendue par une lecture ``GET`` (réconciliation du flux).

    ``next_cursor`` est la séquence du dernier événement rendu ; ``retention_days``
    vaut ``0`` quand la rétention est illimitée et ``None`` quand elle est inconnue.
    """

    events: list[StreamEvent] = Field(default_factory=list)
    next_cursor: int | None = Field(default=None, ge=1)
    has_more: bool = False
    retention_days: int | None = Field(default=None, ge=0)
