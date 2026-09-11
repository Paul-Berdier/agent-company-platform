"""Événements, sessions, mémoire, permissions, modules et configuration des bureaux."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import and_, or_
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
    TaskModel,
    TaskRunModel,
    TeamModel,
    UserModel,
    WorkerLeaseModel,
    WorkspaceModel,
)

from ..deps import (
    accessible_agent_ids,
    accessible_department_ids,
    accessible_project_ids,
    accessible_workspace_ids,
    ensure_access,
    get_db,
    get_principal,
    is_platform_owner,
    require_platform_role,
)
from ..events_bus import forward_event, store_event
from .workers import _as_utc, authenticate_worker, utcnow

router = APIRouter(tags=["platform"])

_WORKER_EVENT_TYPES = {
    "task.plan_ready",
    "task.progress",
    "task.log",
    "task.test_started",
    "task.test_finished",
    "task.artifact_created",
}


@router.post("/events")
def post_event(
    event: Event,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
):
    """Ingestion réservée au worker qui détient le lease du run référencé."""

    if not worker_id:
        raise HTTPException(status_code=401, detail="X-Worker-Id requis")
    worker = authenticate_worker(db, worker_id, authorization)
    if not event.task_run_id or not event.task_id:
        raise HTTPException(status_code=422, detail="task_run_id et task_id sont requis")
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(
            worker_id=worker.id,
            task_run_id=event.task_run_id,
            task_id=event.task_id,
            status="active",
        )
        .first()
    )
    if lease is None or _as_utc(lease.lease_expires_at) <= utcnow():
        raise HTTPException(status_code=409, detail="Lease actif requis pour cet événement")
    task = db.get(TaskModel, lease.task_id)
    run = db.get(TaskRunModel, lease.task_run_id)
    if task is None or run is None or event.project_id != task.project_id:
        raise HTTPException(status_code=400, detail="Événement hors du projet du run")
    if event.type not in _WORKER_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Type d'événement worker non autorisé ; les terminaux sont produits par l'API",
        )
    project = db.get(ProjectModel, task.project_id)
    workspace = db.get(WorkspaceModel, project.workspace_id) if project else None
    if project is None or workspace is None:
        raise HTTPException(status_code=409, detail="Scope métier du run introuvable")
    canonical_scope = {
        "organization_id": workspace.organization_id,
        "workspace_id": project.workspace_id,
        "department_id": project.department_id,
        "project_id": task.project_id,
        "team_id": task.team_id,
        "agent_instance_id": run.agent_instance_id,
        "task_id": task.id,
        "task_run_id": run.id,
    }
    for field, expected in canonical_scope.items():
        supplied = getattr(event, field)
        if supplied is not None and supplied != expected:
            raise HTTPException(status_code=400, detail=f"Scope d'événement incohérent: {field}")
    if db.get(EventModel, event.id) is not None:
        raise HTTPException(status_code=409, detail="Identifiant d'événement déjà utilisé")
    canonical_event = event.model_copy(update=canonical_scope)
    store_event(db, canonical_event)
    background.add_task(forward_event, canonical_event)
    return {"ok": True, "id": canonical_event.id}


@router.get("/events")
def list_events(
    project_id: str | None = None,
    workspace_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(EventModel).order_by(EventModel.occurred_at.desc())
    if not is_platform_owner(db, principal):
        project_ids = accessible_project_ids(db, principal)
        workspace_ids = accessible_workspace_ids(db, principal)
        q = q.filter(
            or_(
                EventModel.project_id.in_(project_ids),
                and_(
                    EventModel.project_id.is_(None),
                    EventModel.workspace_id.in_(workspace_ids),
                ),
            )
        )
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
def create_session(
    body: SessionContext,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _ensure_session_scope(db, principal, body, minimum_role="member")
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
def list_sessions(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(SessionModel)
    if not is_platform_owner(db, principal):
        project_ids = accessible_project_ids(db, principal)
        workspace_ids = accessible_workspace_ids(db, principal)
        q = q.filter(
            or_(
                SessionModel.project_id.in_(project_ids),
                and_(
                    SessionModel.project_id.is_(None),
                    SessionModel.workspace_id.in_(workspace_ids),
                ),
            )
        )
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


def _ensure_session_scope(
    db: Session,
    principal: str,
    body: SessionContext,
    *,
    minimum_role: str,
) -> None:
    """Valide toute la hiérarchie avant de persister un contexte provider."""

    if body.project_id:
        project = db.get(ProjectModel, body.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        ensure_access(db, principal, project_id=project.id, minimum_role=minimum_role)
        if body.workspace_id and body.workspace_id != project.workspace_id:
            raise HTTPException(status_code=422, detail="Workspace incohérent avec le projet")
        workspace = db.get(WorkspaceModel, project.workspace_id)
    elif body.workspace_id:
        workspace = db.get(WorkspaceModel, body.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace introuvable")
        ensure_access(db, principal, workspace_id=workspace.id, minimum_role=minimum_role)
    else:
        require_platform_role(db, principal, "owner")
        workspace = None
    if body.organization_id and (
        workspace is None or body.organization_id != workspace.organization_id
    ):
        raise HTTPException(status_code=422, detail="Organisation incohérente avec le scope")
    if body.team_id:
        team = db.get(TeamModel, body.team_id)
        if team is None or not body.project_id or team.project_id != body.project_id:
            raise HTTPException(status_code=422, detail="Équipe incohérente avec le projet")
    if body.agent_instance_id:
        agent = db.get(AgentInstanceModel, body.agent_instance_id)
        if agent is None or workspace is None or agent.workspace_id != workspace.id:
            raise HTTPException(status_code=422, detail="Agent incohérent avec le workspace")


def _ensure_memory_access(
    db: Session,
    principal: str,
    scope: str,
    owner_id: str,
    *,
    minimum_role: str,
) -> None:
    if scope == MemoryScope.GLOBAL.value:
        require_platform_role(db, principal, "owner")
        return
    if scope == MemoryScope.WORKSPACE.value:
        if db.get(WorkspaceModel, owner_id) is None:
            raise HTTPException(status_code=404, detail="Workspace introuvable")
        ensure_access(db, principal, workspace_id=owner_id, minimum_role=minimum_role)
        return
    if scope == MemoryScope.PROJECT.value:
        if db.get(ProjectModel, owner_id) is None:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        ensure_access(db, principal, project_id=owner_id, minimum_role=minimum_role)
        return
    if scope == MemoryScope.TEAM.value:
        team = db.get(TeamModel, owner_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Équipe introuvable")
        ensure_access(db, principal, project_id=team.project_id, minimum_role=minimum_role)
        return
    if scope == MemoryScope.AGENT.value:
        agent = db.get(AgentInstanceModel, owner_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent introuvable")
        ensure_access(db, principal, workspace_id=agent.workspace_id, minimum_role=minimum_role)
        return
    if scope == MemoryScope.TASK_RUN.value:
        run = db.get(TaskRunModel, owner_id)
        task = db.get(TaskModel, run.task_id) if run else None
        if task is None:
            raise HTTPException(status_code=404, detail="Task run introuvable")
        ensure_access(db, principal, project_id=task.project_id, minimum_role=minimum_role)
        return
    raise HTTPException(status_code=422, detail="Scope mémoire inconnu")


@router.post("/memories", response_model=MemoryItem)
def create_memory(
    body: MemoryItem,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _ensure_memory_access(
        db, principal, body.scope.value, body.owner_id, minimum_role="member"
    )
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
def list_memories(
    scope: str,
    owner_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _ensure_memory_access(db, principal, scope, owner_id, minimum_role="viewer")
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
def create_membership(
    body: MembershipCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    if body.scope_type not in ("workspace", "project"):
        raise HTTPException(status_code=422, detail="scope_type: workspace ou project")
    if body.role not in ("viewer", "member", "operator", "owner"):
        raise HTTPException(status_code=422, detail="Rôle de membership inconnu")
    if db.get(UserModel, body.user_id) is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if body.scope_type == "workspace":
        if db.get(WorkspaceModel, body.scope_id) is None:
            raise HTTPException(status_code=404, detail="Workspace introuvable")
        ensure_access(
            db, principal, workspace_id=body.scope_id, minimum_role="owner"
        )
    else:
        if db.get(ProjectModel, body.scope_id) is None:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        ensure_access(db, principal, project_id=body.scope_id, minimum_role="owner")
    duplicate = (
        db.query(MembershipModel)
        .filter_by(
            user_id=body.user_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Membership déjà existante")
    obj = MembershipModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return {"id": obj.id, **body.model_dump()}


@router.get("/memberships")
def list_memberships(
    user_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(MembershipModel)
    if not is_platform_owner(db, principal):
        project_ids = accessible_project_ids(db, principal)
        workspace_ids = accessible_workspace_ids(db, principal)
        q = q.filter(
            or_(
                and_(
                    MembershipModel.scope_type == "project",
                    MembershipModel.scope_id.in_(project_ids),
                ),
                and_(
                    MembershipModel.scope_type == "workspace",
                    MembershipModel.scope_id.in_(workspace_ids),
                ),
            )
        )
    if user_id:
        q = q.filter_by(user_id=user_id)
    return [
        {"id": m.id, "user_id": m.user_id, "scope_type": m.scope_type,
         "scope_id": m.scope_id, "role": m.role}
        for m in q.all()
    ]


@router.get("/company/level")
def company_level(
    request: Request,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Niveau de croissance calculé depuis les métriques réelles (jamais
    depuis une affirmation libre) ; seuils fournis par les modules."""
    from acp_database.models import TaskModel

    project_ids = accessible_project_ids(db, principal)
    projects = (
        db.query(ProjectModel)
        .filter(ProjectModel.id.in_(project_ids), ProjectModel.status == "active")
        .count()
    )
    agents = (
        db.query(AgentInstanceModel)
        .filter(AgentInstanceModel.id.in_(accessible_agent_ids(db, principal)))
        .count()
    )
    completed = (
        db.query(TaskModel)
        .filter(TaskModel.project_id.in_(project_ids), TaskModel.status == "done")
        .count()
    )

    levels = sorted(
        (lvl for m in request.app.state.modules.values() for lvl in m.growth),
        key=lambda level: level.level,
    )
    current = None
    unlocked: list[str] = []
    for level in levels:
        if (projects >= level.min_projects and agents >= level.min_agents
                and completed >= level.min_completed_tasks):
            current = level
            unlocked.extend(level.unlocks)
    next_level = next((l for l in levels if current is None or l.level == current.level + 1), None)
    return {
        "level": current.level if current else 0,
        "name": current.name if current else "—",
        "metrics": {"projects": projects, "agents": agents, "completed_tasks": completed},
        "unlocked": unlocked,
        "next": None if next_level is None or (current and next_level.level <= current.level) else {
            "level": next_level.level,
            "name": next_level.name,
            "min_projects": next_level.min_projects,
            "min_agents": next_level.min_agents,
            "min_completed_tasks": next_level.min_completed_tasks,
        },
    }


@router.get("/modules")
def list_modules(request: Request, _principal: str = Depends(get_principal)):
    modules = request.app.state.modules
    return {name: manifest.model_dump(mode="json") for name, manifest in modules.items()}


@router.get("/departments/{department_id}/office-config")
def department_office_config(
    department_id: str,
    request: Request,
    capacity: int = 0,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
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
    if dept.id not in accessible_department_ids(db, principal):
        raise HTTPException(status_code=403, detail="Accès refusé pour ce département")
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
