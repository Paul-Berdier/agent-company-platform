"""Événements, sessions, mémoire, permissions, modules et configuration des bureaux."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from acp_contracts import Event, MemoryItem, SessionContext
from acp_contracts.enums import MemoryScope, SharingPolicy
from acp_database.models import (
    AgentInstanceModel,
    DepartmentModel,
    EventModel,
    MembershipModel,
    MemoryModel,
    ProjectModel,
    SessionModel,
    TeamModel,
    WorkspaceModel,
)

from ..deps import ensure_access, get_db, get_principal
from ..events_bus import forward_event, store_event

router = APIRouter(tags=["platform"])


@router.post("/events")
def post_event(event: Event, background: BackgroundTasks, db: Session = Depends(get_db)):
    store_event(db, event)
    background.add_task(forward_event, event)
    return {"ok": True, "id": event.id}


@router.get("/events")
def list_events(
    project_id: str | None = None,
    workspace_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(EventModel).order_by(EventModel.occurred_at.desc())
    if project_id:
        q = q.filter_by(project_id=project_id)
    if workspace_id:
        q = q.filter_by(workspace_id=workspace_id)
    rows = q.limit(min(limit, 500)).all()
    return [
        {
            "id": e.id,
            "type": e.type,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            "organization_id": e.organization_id,
            "workspace_id": e.workspace_id,
            "department_id": e.department_id,
            "project_id": e.project_id,
            "team_id": e.team_id,
            "agent_instance_id": e.agent_instance_id,
            "task_id": e.task_id,
            "task_run_id": e.task_run_id,
            "payload": e.payload,
        }
        for e in rows
    ]


@router.post("/sessions", response_model=SessionContext)
def create_session(body: SessionContext, db: Session = Depends(get_db)):
    obj = SessionModel(
        scope=body.scope.value,
        organization_id=body.organization_id,
        workspace_id=body.workspace_id,
        project_id=body.project_id,
        team_id=body.team_id,
        agent_instance_id=body.agent_instance_id,
        provider_id=body.provider_id,
        external_session_id=body.external_session_id,
        memory_scope=body.memory_scope.value,
    )
    db.add(obj)
    db.commit()
    body.session_id = obj.id
    return body


@router.get("/sessions")
def list_sessions(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(SessionModel)
    if project_id:
        q = q.filter_by(project_id=project_id)
    return [
        {
            "session_id": s.id,
            "scope": s.scope,
            "organization_id": s.organization_id,
            "workspace_id": s.workspace_id,
            "project_id": s.project_id,
            "team_id": s.team_id,
            "agent_instance_id": s.agent_instance_id,
            "provider_id": s.provider_id,
            "external_session_id": s.external_session_id,
            "memory_scope": s.memory_scope,
        }
        for s in q.all()
    ]


def _not_expired(m: MemoryModel) -> bool:
    if m.ttl_seconds is None:
        return True
    created = m.created_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < created + timedelta(seconds=m.ttl_seconds)


@router.post("/memories", response_model=MemoryItem)
def create_memory(body: MemoryItem, db: Session = Depends(get_db)):
    obj = MemoryModel(
        scope=body.scope.value,
        owner_id=body.owner_id,
        source=body.source,
        classification=body.classification.value,
        sharing_policy=body.sharing_policy.value,
        ttl_seconds=body.ttl_seconds,
        content=body.content,
    )
    db.add(obj)
    db.commit()
    body.id = obj.id
    body.created_at = obj.created_at
    return body


@router.get("/memories")
def list_memories(scope: str, owner_id: str, db: Session = Depends(get_db)):
    rows = db.query(MemoryModel).filter_by(scope=scope, owner_id=owner_id).all()
    return [_memory_dict(m) for m in rows if _not_expired(m)]


def _memory_dict(m: MemoryModel) -> dict:
    return {
        "id": m.id,
        "scope": m.scope,
        "owner_id": m.owner_id,
        "source": m.source,
        "classification": m.classification,
        "sharing_policy": m.sharing_policy,
        "ttl_seconds": m.ttl_seconds,
        "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/projects/{project_id}/context")
def project_context(
    project_id: str,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    """Assemble le contexte mémoire d'UN projet, sans jamais fuiter celui des autres.

    Inclus : mémoire PROJECT du projet, TEAM/AGENT de ses équipes, et les
    éléments WORKSPACE / GLOBAL explicitement `shareable`.
    """
    ensure_access(db, principal, project_id=project_id)
    project = db.get(ProjectModel, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    workspace = db.get(WorkspaceModel, project.workspace_id)
    team_ids = [t.id for t in db.query(TeamModel).filter_by(project_id=project_id).all()]
    agent_ids = [
        a.id
        for a in db.query(AgentInstanceModel)
        .filter(AgentInstanceModel.team_id.in_(team_ids))
        .all()
    ] if team_ids else []

    items: list[MemoryModel] = []
    items += db.query(MemoryModel).filter_by(
        scope=MemoryScope.PROJECT.value, owner_id=project_id
    ).all()
    if team_ids:
        items += (
            db.query(MemoryModel)
            .filter(MemoryModel.scope == MemoryScope.TEAM.value,
                    MemoryModel.owner_id.in_(team_ids))
            .all()
        )
    if agent_ids:
        items += (
            db.query(MemoryModel)
            .filter(MemoryModel.scope == MemoryScope.AGENT.value,
                    MemoryModel.owner_id.in_(agent_ids))
            .all()
        )
    items += (
        db.query(MemoryModel)
        .filter_by(scope=MemoryScope.WORKSPACE.value, owner_id=project.workspace_id,
                   sharing_policy=SharingPolicy.SHAREABLE.value)
        .all()
    )
    if workspace:
        items += (
            db.query(MemoryModel)
            .filter_by(scope=MemoryScope.GLOBAL.value, owner_id=workspace.organization_id,
                       sharing_policy=SharingPolicy.SHAREABLE.value)
            .all()
        )
    return {
        "project_id": project_id,
        "items": [_memory_dict(m) for m in items if _not_expired(m)],
    }


class MembershipCreate(BaseModel):
    user_id: str
    scope_type: str  # workspace | project
    scope_id: str
    role: str = "member"


@router.post("/memberships")
def create_membership(body: MembershipCreate, db: Session = Depends(get_db)):
    if body.scope_type not in ("workspace", "project"):
        raise HTTPException(status_code=422, detail="scope_type: workspace ou project")
    obj = MembershipModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return {"id": obj.id, **body.model_dump()}


@router.get("/memberships")
def list_memberships(user_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(MembershipModel)
    if user_id:
        q = q.filter_by(user_id=user_id)
    return [
        {"id": m.id, "user_id": m.user_id, "scope_type": m.scope_type,
         "scope_id": m.scope_id, "role": m.role}
        for m in q.all()
    ]


@router.get("/modules")
def list_modules(request: Request):
    modules = request.app.state.modules
    return {name: manifest.model_dump(mode="json") for name, manifest in modules.items()}


@router.get("/departments/{department_id}/office-config")
def department_office_config(
    department_id: str,
    request: Request,
    capacity: int = 0,
    db: Session = Depends(get_db),
):
    """Configuration data-driven du bureau pixel art d'un département.

    Si un module fournit des templates de salles pour ce secteur, le plus
    petit template couvrant `capacity` est retenu (stations, dimensions,
    portes, fenêtres). Sinon, repli sur les stations historiques du module.
    """
    from acp_agent_sdk import select_room_template

    dept = db.get(DepartmentModel, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Département introuvable")
    modules = request.app.state.modules
    definition = None
    for manifest in modules.values():
        for d in manifest.departments:
            if d.department_type == dept.department_type:
                definition = d
                break
        if definition:
            break
    if definition is None:  # repli générique : le cœur vit sans module métier
        definition = modules["core"].departments[0]
    config = definition.model_dump(mode="json")

    all_templates = [t for m in modules.values() for t in m.room_templates]
    template = select_room_template(all_templates, dept.department_type, capacity)
    if template is not None:
        config.update({
            "template_id": template.id,
            "width": template.width,
            "height": template.height,
            "capacity": template.capacity,
            "stations": [s.model_dump(mode="json") for s in template.stations],
            "doors": template.doors,
            "windows": template.windows,
            "office_theme": template.theme,
            "upgrade_to": template.upgrade_to,
        })

    config.update({
        "department_id": dept.id,
        "department_type": dept.department_type,
        "office_theme": config.get("office_theme") or dept.office_theme or definition.office_theme,
    })
    config.update(dept.config or {})
    return config
