"""Parcours personnel court : état de préparation et premier projet."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from acp_contracts import Project
from acp_database.models import (
    MembershipModel,
    OrganizationModel,
    ProjectModel,
    WorkerModel,
    WorkspaceModel,
)

from ..deps import get_auth_context, get_db, require_csrf
from ..gateway import GatewayClient, GatewayUnavailableError, get_gateway_client
from ..security import AuthContext

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    bootstrap_completed: bool
    hermes_configured: bool
    hermes_ready: bool
    hermes_status: str
    project_count: int
    runner_ready: bool


class PersonalProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    project_type: str = Field(default="generic", min_length=1, max_length=100)
    description: str = Field(default="", max_length=10_000)


def _accessible_project_count(db: Session, context: AuthContext) -> int:
    if context.user.platform_role == "owner":
        return db.query(ProjectModel).count()
    project_ids = {
        row.scope_id
        for row in db.query(MembershipModel)
        .filter_by(user_id=context.user.id, scope_type="project")
        .all()
    }
    workspace_ids = {
        row.scope_id
        for row in db.query(MembershipModel)
        .filter_by(user_id=context.user.id, scope_type="workspace")
        .all()
    }
    query = db.query(ProjectModel)
    return sum(
        1
        for project in query.all()
        if project.id in project_ids or project.workspace_id in workspace_ids
    )


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    client: GatewayClient = Depends(get_gateway_client),
):
    try:
        diagnostic = await client.diagnose_hermes()
        hermes_configured = diagnostic.configured
        hermes_ready = diagnostic.ready
        hermes_status = diagnostic.status
    except GatewayUnavailableError:
        hermes_configured = False
        hermes_ready = False
        hermes_status = "unavailable"
    runner_ready = (
        db.query(WorkerModel)
        .filter(
            WorkerModel.status == "online",
            WorkerModel.simulation == 0,
            or_(
                and_(
                    WorkerModel.global_access == 1,
                    WorkerModel.project_id.is_(None),
                ),
                and_(
                    WorkerModel.global_access == 0,
                    WorkerModel.project_id.is_not(None),
                ),
            ),
        )
        .first()
        is not None
    )
    return OnboardingStatus(
        bootstrap_completed=True,
        hermes_configured=hermes_configured,
        hermes_ready=hermes_ready,
        hermes_status=hermes_status,
        project_count=_accessible_project_count(db, context),
        runner_ready=runner_ready,
    )


def _personal_workspace(db: Session, context: AuthContext) -> WorkspaceModel:
    memberships = (
        db.query(MembershipModel)
        .filter_by(user_id=context.user.id, scope_type="workspace")
        .all()
    )
    for membership in memberships:
        workspace = db.get(WorkspaceModel, membership.scope_id)
        if workspace is not None and workspace.kind == "personal":
            return workspace

    organization = OrganizationModel(
        name=f"Espace personnel de {context.user.display_name}",
        description="Créé par l'assistant de démarrage.",
    )
    db.add(organization)
    db.flush()
    workspace = WorkspaceModel(
        organization_id=organization.id,
        name="Mon espace",
        kind="personal",
        description="Espace personnel par défaut.",
    )
    db.add(workspace)
    db.flush()
    db.add(
        MembershipModel(
            user_id=context.user.id,
            scope_type="workspace",
            scope_id=workspace.id,
            role="owner",
        )
    )
    return workspace


@router.post("/projects", response_model=Project, status_code=201)
def create_personal_project(
    body: PersonalProjectCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if context.user.platform_role == "viewer":
        raise HTTPException(status_code=403, detail="Accès en lecture seule")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du projet est requis")
    workspace = _personal_workspace(db, context)
    project = ProjectModel(
        workspace_id=workspace.id,
        name=name,
        project_type=body.project_type.strip(),
        description=body.description.strip(),
    )
    db.add(project)
    db.flush()
    db.add(
        MembershipModel(
            user_id=context.user.id,
            scope_type="project",
            scope_id=project.id,
            role="owner" if context.user.platform_role == "owner" else "member",
        )
    )
    db.commit()
    return Project.model_validate(project, from_attributes=True)
