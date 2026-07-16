import os

import httpx
from sqlalchemy.orm import Session

from acp_contracts import Event
from acp_database.models import EventModel

EVENT_SERVICE_URL = os.environ.get("ACP_EVENT_SERVICE_URL", "http://localhost:8001")


def store_event(db: Session, event: Event) -> None:
    db.add(
        EventModel(
            id=event.id,
            type=event.type,
            occurred_at=event.occurred_at,
            organization_id=event.organization_id,
            workspace_id=event.workspace_id,
            department_id=event.department_id,
            project_id=event.project_id,
            team_id=event.team_id,
            agent_instance_id=event.agent_instance_id,
            task_id=event.task_id,
            task_run_id=event.task_run_id,
            payload=event.payload,
        )
    )
    db.commit()


async def forward_event(event: Event) -> None:
    """Pousse l'événement vers le service temps réel ; jamais bloquant pour le métier."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{EVENT_SERVICE_URL.rstrip('/')}/internal/events",
                json=event.model_dump(mode="json"),
            )
    except httpx.HTTPError:
        pass
