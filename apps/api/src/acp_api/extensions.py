"""Résolution des extensions (serveurs MCP et skills) effectivement actives pour un projet.

Un binding n'est retenu que s'il est ``enabled`` et non révoqué **et** que la ressource
liée (serveur MCP ou skill) est ``active``. La révision rapportée est celle du binding,
jamais la révision courante de la ressource : une révision créée mais non activée ne
change pas ce que le projet utilise. Le résultat est figé dans ``TaskModel.meta["extensions"]``
à la création d'une mission.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from acp_contracts import ProjectExtensions, ProjectMcpExtension, ProjectSkillExtension
from acp_database.models import (
    McpBindingModel,
    McpServerModel,
    McpServerRevisionModel,
    SkillBindingModel,
    SkillModel,
    SkillRevisionModel,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_project_extensions(db: Session, project_id: str) -> ProjectExtensions:
    """Retourne les extensions utilisables par ``project_id`` (bindings actifs sur ressources actives)."""

    mcp_rows = (
        db.query(McpBindingModel, McpServerModel, McpServerRevisionModel)
        .join(McpServerModel, McpServerModel.id == McpBindingModel.server_id)
        .join(McpServerRevisionModel, McpServerRevisionModel.id == McpBindingModel.revision_id)
        .filter(
            McpBindingModel.project_id == project_id,
            McpBindingModel.enabled == 1,
            McpBindingModel.revoked_at.is_(None),
            McpServerModel.status == "active",
        )
        .order_by(McpServerModel.name.asc())
        .all()
    )
    skill_rows = (
        db.query(SkillBindingModel, SkillModel, SkillRevisionModel)
        .join(SkillModel, SkillModel.id == SkillBindingModel.skill_id)
        .join(SkillRevisionModel, SkillRevisionModel.id == SkillBindingModel.revision_id)
        .filter(
            SkillBindingModel.project_id == project_id,
            SkillBindingModel.enabled == 1,
            SkillBindingModel.revoked_at.is_(None),
            SkillModel.status == "active",
        )
        .order_by(SkillModel.name.asc())
        .all()
    )
    return ProjectExtensions(
        project_id=project_id,
        mcp=[
            ProjectMcpExtension(
                server_id=server.id,
                name=server.name,
                revision_number=revision.number,
                allowed_tools=list(binding.allowed_tools or []),
                enabled=bool(binding.enabled),
                server_status=server.status,
            )
            for binding, server, revision in mcp_rows
        ],
        skills=[
            ProjectSkillExtension(
                skill_id=skill.id,
                name=skill.name,
                revision_number=revision.number,
                enabled=bool(binding.enabled),
                skill_status=skill.status,
            )
            for binding, skill, revision in skill_rows
        ],
        resolved_at=_utcnow(),
    )
