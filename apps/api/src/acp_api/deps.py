from collections.abc import Generator

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from acp_database import get_session_factory, init_db
from acp_database.models import MembershipModel, ProjectModel

_ROLE_ORDER = {"viewer": 0, "member": 1, "owner": 2}


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_principal(x_user_id: str | None = Header(default=None)) -> str | None:
    """Identité simple par en-tête (MVP). None = mode développement ouvert."""
    return x_user_id


def ensure_access(
    db: Session,
    principal: str | None,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    minimum_role: str = "viewer",
) -> None:
    """Vérifie les permissions par workspace et par projet.

    Sans principal (mode dev), l'accès est ouvert. Avec principal, il faut
    une membership sur le projet, ou à défaut sur son workspace.
    """
    if principal is None:
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


def init() -> None:
    init_db()
