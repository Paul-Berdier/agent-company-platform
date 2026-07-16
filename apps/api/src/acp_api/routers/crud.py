"""CRUD de la hiérarchie Organization → ... → Agent Instance."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from acp_contracts import (
    AgentInstance,
    Department,
    Event,
    Organization,
    Project,
    Team,
    TeamMember,
    Workspace,
)
from acp_database.models import (
    AgentInstanceModel,
    DepartmentModel,
    OrganizationModel,
    ProjectModel,
    TaskModel,
    TeamMemberModel,
    TeamModel,
    WorkspaceModel,
)

from ..deps import ensure_access, get_db, get_principal
from ..events_bus import forward_event, store_event

router = APIRouter(tags=["hierarchy"])


class OrganizationCreate(BaseModel):
    name: str
    description: str = ""


class WorkspaceCreate(BaseModel):
    organization_id: str
    name: str
    kind: str = "generic"
    description: str = ""


class DepartmentCreate(BaseModel):
    workspace_id: str
    name: str
    department_type: str
    office_theme: str = "default"
    config: dict = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    workspace_id: str
    department_id: str | None = None
    name: str
    project_type: str = "generic"
    description: str = ""


class TeamCreate(BaseModel):
    project_id: str
    name: str
    mission: str = ""


class TeamMemberCreate(BaseModel):
    agent_instance_id: str
    role_id: str | None = None


class AgentCreate(BaseModel):
    workspace_id: str
    team_id: str | None = None
    name: str
    role_id: str
    module: str = "core"
    capabilities: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class AgentPatch(BaseModel):
    status: str | None = None
    team_id: str | None = None
    name: str | None = None


def _get_or_404(db: Session, model, entity_id: str):
    obj = db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__tablename__}: introuvable")
    return obj


@router.post("/organizations", response_model=Organization)
def create_organization(body: OrganizationCreate, db: Session = Depends(get_db)):
    obj = OrganizationModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Organization.model_validate(obj, from_attributes=True)


@router.get("/organizations", response_model=list[Organization])
def list_organizations(db: Session = Depends(get_db)):
    return [
        Organization.model_validate(o, from_attributes=True)
        for o in db.query(OrganizationModel).all()
    ]


@router.post("/workspaces", response_model=Workspace)
def create_workspace(body: WorkspaceCreate, db: Session = Depends(get_db)):
    _get_or_404(db, OrganizationModel, body.organization_id)
    obj = WorkspaceModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Workspace.model_validate(obj, from_attributes=True)


@router.get("/workspaces", response_model=list[Workspace])
def list_workspaces(organization_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(WorkspaceModel)
    if organization_id:
        q = q.filter_by(organization_id=organization_id)
    return [Workspace.model_validate(w, from_attributes=True) for w in q.all()]


@router.post("/departments", response_model=Department)
def create_department(
    body: DepartmentCreate,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, workspace_id=body.workspace_id, minimum_role="member")
    _get_or_404(db, WorkspaceModel, body.workspace_id)
    obj = DepartmentModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Department.model_validate(obj, from_attributes=True)


@router.get("/departments", response_model=list[Department])
def list_departments(workspace_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(DepartmentModel)
    if workspace_id:
        q = q.filter_by(workspace_id=workspace_id)
    return [Department.model_validate(d, from_attributes=True) for d in q.all()]


@router.post("/projects", response_model=Project)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, workspace_id=body.workspace_id, minimum_role="member")
    _get_or_404(db, WorkspaceModel, body.workspace_id)
    obj = ProjectModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Project.model_validate(obj, from_attributes=True)


@router.get("/projects", response_model=list[Project])
def list_projects(
    workspace_id: str | None = None,
    department_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(ProjectModel)
    if workspace_id:
        q = q.filter_by(workspace_id=workspace_id)
    if department_id:
        q = q.filter_by(department_id=department_id)
    return [Project.model_validate(p, from_attributes=True) for p in q.all()]


@router.post("/teams", response_model=Team)
def create_team(
    body: TeamCreate,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    _get_or_404(db, ProjectModel, body.project_id)
    obj = TeamModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Team.model_validate(obj, from_attributes=True)


@router.get("/teams", response_model=list[Team])
def list_teams(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(TeamModel)
    if project_id:
        q = q.filter_by(project_id=project_id)
    return [Team.model_validate(t, from_attributes=True) for t in q.all()]


@router.post("/teams/{team_id}/members", response_model=TeamMember)
def add_team_member(team_id: str, body: TeamMemberCreate, db: Session = Depends(get_db)):
    _get_or_404(db, TeamModel, team_id)
    agent = _get_or_404(db, AgentInstanceModel, body.agent_instance_id)
    member = TeamMemberModel(team_id=team_id, **body.model_dump())
    agent.team_id = team_id
    db.merge(member)
    db.commit()
    return TeamMember(team_id=team_id, **body.model_dump())


@router.get("/teams/{team_id}/members", response_model=list[TeamMember])
def list_team_members(team_id: str, db: Session = Depends(get_db)):
    rows = db.query(TeamMemberModel).filter_by(team_id=team_id).all()
    return [
        TeamMember(team_id=r.team_id, agent_instance_id=r.agent_instance_id, role_id=r.role_id)
        for r in rows
    ]


@router.post("/agents", response_model=AgentInstance)
def create_agent(body: AgentCreate, db: Session = Depends(get_db)):
    _get_or_404(db, WorkspaceModel, body.workspace_id)
    obj = AgentInstanceModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return AgentInstance.model_validate(obj, from_attributes=True)


@router.get("/agents", response_model=list[AgentInstance])
def list_agents(
    workspace_id: str | None = None,
    team_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(AgentInstanceModel)
    if workspace_id:
        q = q.filter_by(workspace_id=workspace_id)
    if team_id:
        q = q.filter_by(team_id=team_id)
    return [AgentInstance.model_validate(a, from_attributes=True) for a in q.all()]


@router.patch("/agents/{agent_id}", response_model=AgentInstance)
def patch_agent(
    agent_id: str,
    body: AgentPatch,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    agent = _get_or_404(db, AgentInstanceModel, agent_id)
    changes = body.model_dump(exclude_none=True)
    status_changed = "status" in changes and changes["status"] != agent.status
    for key, value in changes.items():
        setattr(agent, key, value)
    db.commit()
    if status_changed:
        team = db.get(TeamModel, agent.team_id) if agent.team_id else None
        event = Event(
            type="agent.status_changed",
            workspace_id=agent.workspace_id,
            team_id=agent.team_id,
            project_id=team.project_id if team else None,
            agent_instance_id=agent.id,
            payload={"status": agent.status, "name": agent.name, "role_id": agent.role_id},
        )
        store_event(db, event)
        background.add_task(forward_event, event)
    return AgentInstance.model_validate(agent, from_attributes=True)


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Instantané complet pour l'interface pixel art (échelle MVP)."""
    tasks = db.query(TaskModel).all()
    return {
        "organizations": [
            Organization.model_validate(o, from_attributes=True).model_dump(mode="json")
            for o in db.query(OrganizationModel).all()
        ],
        "workspaces": [
            Workspace.model_validate(w, from_attributes=True).model_dump(mode="json")
            for w in db.query(WorkspaceModel).all()
        ],
        "departments": [
            Department.model_validate(d, from_attributes=True).model_dump(mode="json")
            for d in db.query(DepartmentModel).all()
        ],
        "projects": [
            Project.model_validate(p, from_attributes=True).model_dump(mode="json")
            for p in db.query(ProjectModel).all()
        ],
        "teams": [
            Team.model_validate(t, from_attributes=True).model_dump(mode="json")
            for t in db.query(TeamModel).all()
        ],
        "team_members": [
            {"team_id": m.team_id, "agent_instance_id": m.agent_instance_id, "role_id": m.role_id}
            for m in db.query(TeamMemberModel).all()
        ],
        "agents": [
            AgentInstance.model_validate(a, from_attributes=True).model_dump(mode="json")
            for a in db.query(AgentInstanceModel).all()
        ],
        "tasks": [
            {
                "id": t.id,
                "project_id": t.project_id,
                "team_id": t.team_id,
                "agent_instance_id": t.agent_instance_id,
                "title": t.title,
                "status": t.status,
                "workflow_step": t.workflow_step,
                "priority": t.priority,
            }
            for t in tasks
        ],
    }
