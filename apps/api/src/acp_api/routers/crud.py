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
def create_organization(
    body: OrganizationCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    obj = OrganizationModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Organization.model_validate(obj, from_attributes=True)


@router.get("/organizations", response_model=list[Organization])
def list_organizations(
    db: Session = Depends(get_db), principal: str = Depends(get_principal)
):
    query = db.query(OrganizationModel)
    if not is_platform_owner(db, principal):
        workspace_ids = accessible_workspace_ids(db, principal)
        organization_ids = {
            organization_id
            for (organization_id,) in db.query(WorkspaceModel.organization_id)
            .filter(WorkspaceModel.id.in_(workspace_ids))
            .all()
        }
        query = query.filter(OrganizationModel.id.in_(organization_ids))
    return [
        Organization.model_validate(o, from_attributes=True)
        for o in query.all()
    ]


@router.post("/workspaces", response_model=Workspace)
def create_workspace(
    body: WorkspaceCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    _get_or_404(db, OrganizationModel, body.organization_id)
    obj = WorkspaceModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Workspace.model_validate(obj, from_attributes=True)


@router.get("/workspaces", response_model=list[Workspace])
def list_workspaces(
    organization_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(WorkspaceModel)
    q = q.filter(WorkspaceModel.id.in_(accessible_workspace_ids(db, principal)))
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
def list_departments(
    workspace_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(DepartmentModel).filter(
        DepartmentModel.id.in_(accessible_department_ids(db, principal))
    )
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
    if body.department_id is not None:
        department = _get_or_404(db, DepartmentModel, body.department_id)
        if department.workspace_id != body.workspace_id:
            raise HTTPException(status_code=422, detail="Département hors du workspace")
    obj = ProjectModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return Project.model_validate(obj, from_attributes=True)


@router.get("/projects", response_model=list[Project])
def list_projects(
    workspace_id: str | None = None,
    department_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(ProjectModel).filter(
        ProjectModel.id.in_(accessible_project_ids(db, principal))
    )
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
def list_teams(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(TeamModel).filter(
        TeamModel.project_id.in_(accessible_project_ids(db, principal))
    )
    if project_id:
        q = q.filter_by(project_id=project_id)
    return [Team.model_validate(t, from_attributes=True) for t in q.all()]


@router.post("/teams/{team_id}/members", response_model=TeamMember)
def add_team_member(
    team_id: str,
    body: TeamMemberCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    team = _get_or_404(db, TeamModel, team_id)
    ensure_access(db, principal, project_id=team.project_id, minimum_role="member")
    agent = _get_or_404(db, AgentInstanceModel, body.agent_instance_id)
    project = _get_or_404(db, ProjectModel, team.project_id)
    if agent.workspace_id != project.workspace_id:
        raise HTTPException(status_code=422, detail="Agent hors du workspace du projet")
    member = TeamMemberModel(team_id=team_id, **body.model_dump())
    agent.team_id = team_id
    db.merge(member)
    db.commit()
    return TeamMember(team_id=team_id, **body.model_dump())


@router.get("/teams/{team_id}/members", response_model=list[TeamMember])
def list_team_members(
    team_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    team = _get_or_404(db, TeamModel, team_id)
    ensure_access(db, principal, project_id=team.project_id)
    rows = db.query(TeamMemberModel).filter_by(team_id=team_id).all()
    return [
        TeamMember(team_id=r.team_id, agent_instance_id=r.agent_instance_id, role_id=r.role_id)
        for r in rows
    ]


@router.post("/agents", response_model=AgentInstance)
def create_agent(
    body: AgentCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    ensure_access(db, principal, workspace_id=body.workspace_id, minimum_role="member")
    _get_or_404(db, WorkspaceModel, body.workspace_id)
    if body.team_id is not None:
        team = _get_or_404(db, TeamModel, body.team_id)
        project = _get_or_404(db, ProjectModel, team.project_id)
        if project.workspace_id != body.workspace_id:
            raise HTTPException(status_code=422, detail="Équipe hors du workspace")
    obj = AgentInstanceModel(**body.model_dump())
    db.add(obj)
    db.commit()
    return AgentInstance.model_validate(obj, from_attributes=True)


@router.get("/agents", response_model=list[AgentInstance])
def list_agents(
    workspace_id: str | None = None,
    team_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(AgentInstanceModel).filter(
        AgentInstanceModel.id.in_(accessible_agent_ids(db, principal))
    )
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
    principal: str = Depends(get_principal),
):
    agent = _get_or_404(db, AgentInstanceModel, agent_id)
    ensure_access(db, principal, workspace_id=agent.workspace_id, minimum_role="member")
    changes = body.model_dump(exclude_none=True)
    if body.team_id is not None:
        team = _get_or_404(db, TeamModel, body.team_id)
        project = _get_or_404(db, ProjectModel, team.project_id)
        if project.workspace_id != agent.workspace_id:
            raise HTTPException(status_code=422, detail="Équipe hors du workspace")
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
def overview(
    db: Session = Depends(get_db), principal: str = Depends(get_principal)
):
    """Instantané complet pour l'interface pixel art (échelle MVP)."""
    workspace_ids = accessible_workspace_ids(db, principal)
    project_ids = accessible_project_ids(db, principal)
    if is_platform_owner(db, principal):
        organizations = db.query(OrganizationModel).all()
    else:
        organizations = (
            db.query(OrganizationModel)
            .join(WorkspaceModel, WorkspaceModel.organization_id == OrganizationModel.id)
            .filter(WorkspaceModel.id.in_(workspace_ids))
            .distinct()
            .all()
        )
    workspaces = db.query(WorkspaceModel).filter(WorkspaceModel.id.in_(workspace_ids)).all()
    departments = db.query(DepartmentModel).filter(
        DepartmentModel.id.in_(accessible_department_ids(db, principal))
    ).all()
    projects = db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()
    teams = db.query(TeamModel).filter(TeamModel.project_id.in_(project_ids)).all()
    team_ids = {team.id for team in teams}
    agents = db.query(AgentInstanceModel).filter(
        AgentInstanceModel.id.in_(accessible_agent_ids(db, principal))
    ).all()
    tasks = db.query(TaskModel).filter(TaskModel.project_id.in_(project_ids)).all()
    return {
        "organizations": [
            Organization.model_validate(o, from_attributes=True).model_dump(mode="json")
            for o in organizations
        ],
        "workspaces": [
            Workspace.model_validate(w, from_attributes=True).model_dump(mode="json")
            for w in workspaces
        ],
        "departments": [
            Department.model_validate(d, from_attributes=True).model_dump(mode="json")
            for d in departments
        ],
        "projects": [
            Project.model_validate(p, from_attributes=True).model_dump(mode="json")
            for p in projects
        ],
        "teams": [
            Team.model_validate(t, from_attributes=True).model_dump(mode="json")
            for t in teams
        ],
        "team_members": [
            {"team_id": m.team_id, "agent_instance_id": m.agent_instance_id, "role_id": m.role_id}
            for m in db.query(TeamMemberModel)
            .filter(TeamMemberModel.team_id.in_(team_ids))
            .all()
        ],
        "agents": [
            AgentInstance.model_validate(a, from_attributes=True).model_dump(mode="json")
            for a in agents
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
