import os

import httpx
from sqlalchemy.orm import Session

from acp_contracts import Event, ServiceOriginError, normalize_service_origin
from acp_database.models import EventModel

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
    service_token = os.environ.get("ACP_EVENT_SERVICE_TOKEN", "").strip()
    if not service_token:
        return
    try:
        event_service_url = normalize_service_origin(
            os.environ.get("ACP_EVENT_SERVICE_URL", "http://localhost:8001"),
            setting="ACP_EVENT_SERVICE_URL",
        )
    except ServiceOriginError:
        return

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{event_service_url}/internal/events",
                json=event.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {service_token}"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        pass
