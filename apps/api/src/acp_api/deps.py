from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from acp_database import get_session_factory, init_db
from acp_database.models import (
    AgentInstanceModel,
    DepartmentModel,
    MembershipModel,
    ProjectModel,
    TaskModel,
    TeamModel,
    UserModel,
    WorkspaceModel,
)

from .security import AuthContext, authenticate_session, csrf_token_is_valid

_ROLE_ORDER = {"viewer": 0, "member": 1, "operator": 1, "owner": 2}
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _active_user(db: Session, principal: str | None) -> UserModel:
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    user = db.get(UserModel, principal)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return user


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    context = authenticate_session(db, request.cookies.get("acp_session"))
    if context is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return context


def require_csrf(
    request: Request, context: AuthContext = Depends(get_auth_context)
) -> AuthContext:
    if not csrf_token_is_valid(context.session, request.headers.get("X-CSRF-Token")):
        raise HTTPException(status_code=403, detail="Requête refusée")
    return context


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> UserModel:
    return context.user


def get_principal(
    request: Request, context: AuthContext = Depends(get_auth_context)
) -> str:
    """Retourne uniquement une identité issue d'une session serveur valide."""
    if request.method.upper() in _UNSAFE_METHODS and not csrf_token_is_valid(
        context.session, request.headers.get("X-CSRF-Token")
    ):
        raise HTTPException(status_code=403, detail="Requête refusée")
    return context.user.id


def ensure_access(
    db: Session,
    principal: str | None,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    minimum_role: str = "viewer",
) -> None:
    """Vérifie les permissions à partir de l'identité de session."""
    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return
    scopes: list[tuple[str, str]] = []
    if project_id:
        scopes.append(("project", project_id))
        project = db.get(ProjectModel, project_id)
        if project is not None:
            workspace_id = workspace_id or project.workspace_id
    if workspace_id:
        scopes.append(("workspace", workspace_id))
    if not scopes:
        return
    needed = _ROLE_ORDER.get(minimum_role, 0)
    for scope_type, scope_id in scopes:
        row = (
            db.query(MembershipModel)
            .filter_by(user_id=principal, scope_type=scope_type, scope_id=scope_id)
            .first()
        )
        if row is not None and _ROLE_ORDER.get(row.role, 0) >= needed:
            return
    raise HTTPException(status_code=403, detail="Accès refusé pour ce contexte")


def require_platform_role(
    db: Session, principal: str | None, *allowed_roles: str
) -> UserModel:
    """Réserve une opération aux rôles de plateforme explicitement autorisés."""

    user = _active_user(db, principal)
    if user.platform_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Accès refusé pour ce rôle")
    return user


def is_platform_owner(db: Session, principal: str | None) -> bool:
    return _active_user(db, principal).platform_role == "owner"


def accessible_project_ids(db: Session, principal: str | None) -> set[str]:
    """Retourne les projets visibles sans interpréter un filtre fourni par le client."""

    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return {project_id for (project_id,) in db.query(ProjectModel.id).all()}
    memberships = db.query(MembershipModel).filter_by(user_id=user.id).all()
    project_ids = {
        membership.scope_id
        for membership in memberships
        if membership.scope_type == "project"
    }
    workspace_ids = {
        membership.scope_id
        for membership in memberships
        if membership.scope_type == "workspace"
    }
    if workspace_ids:
        project_ids.update(
            project_id
            for (project_id,) in db.query(ProjectModel.id)
            .filter(ProjectModel.workspace_id.in_(workspace_ids))
            .all()
        )
    return project_ids


def accessible_workspace_ids(db: Session, principal: str | None) -> set[str]:
    """Inclut les workspaces directs et ceux parents d'un projet autorisé."""

    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return {workspace_id for (workspace_id,) in db.query(WorkspaceModel.id).all()}
    memberships = db.query(MembershipModel).filter_by(user_id=user.id).all()
    workspace_ids = {
        membership.scope_id
        for membership in memberships
        if membership.scope_type == "workspace"
    }
    project_ids = {
        membership.scope_id
        for membership in memberships
        if membership.scope_type == "project"
    }
    if project_ids:
        workspace_ids.update(
            workspace_id
            for (workspace_id,) in db.query(ProjectModel.workspace_id)
            .filter(ProjectModel.id.in_(project_ids))
            .all()
        )
    return workspace_ids


def direct_workspace_ids(db: Session, principal: str | None) -> set[str]:
    """Workspaces réellement accordés, sans élargissement depuis un projet enfant."""

    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return {workspace_id for (workspace_id,) in db.query(WorkspaceModel.id).all()}
    return {
        scope_id
        for (scope_id,) in db.query(MembershipModel.scope_id)
        .filter_by(user_id=user.id, scope_type="workspace")
        .all()
    }


def accessible_department_ids(db: Session, principal: str | None) -> set[str]:
    """Départements des workspaces accordés ou explicitement liés aux projets visibles."""

    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return {department_id for (department_id,) in db.query(DepartmentModel.id).all()}
    workspace_ids = direct_workspace_ids(db, principal)
    department_ids = {
        department_id
        for (department_id,) in db.query(DepartmentModel.id)
        .filter(DepartmentModel.workspace_id.in_(workspace_ids))
        .all()
    }
    project_ids = accessible_project_ids(db, principal)
    department_ids.update(
        department_id
        for (department_id,) in db.query(ProjectModel.department_id)
        .filter(
            ProjectModel.id.in_(project_ids),
            ProjectModel.department_id.is_not(None),
        )
        .all()
    )
    return department_ids


def accessible_agent_ids(db: Session, principal: str | None) -> set[str]:
    """Agents du workspace accordé ou rattachés aux seuls projets visibles."""

    user = _active_user(db, principal)
    if user.platform_role == "owner":
        return {agent_id for (agent_id,) in db.query(AgentInstanceModel.id).all()}
    agent_ids = {
        agent_id
        for (agent_id,) in db.query(AgentInstanceModel.id)
        .filter(AgentInstanceModel.workspace_id.in_(direct_workspace_ids(db, principal)))
        .all()
    }
    project_ids = accessible_project_ids(db, principal)
    team_ids = {
        team_id
        for (team_id,) in db.query(TeamModel.id)
        .filter(TeamModel.project_id.in_(project_ids))
        .all()
    }
    if team_ids:
        agent_ids.update(
            agent_id
            for (agent_id,) in db.query(AgentInstanceModel.id)
            .filter(AgentInstanceModel.team_id.in_(team_ids))
            .all()
        )
    agent_ids.update(
        agent_id
        for (agent_id,) in db.query(TaskModel.agent_instance_id)
        .filter(
            TaskModel.project_id.in_(project_ids),
            TaskModel.agent_instance_id.is_not(None),
        )
        .all()
    )
    return agent_ids


def init() -> None:
    init_db()
