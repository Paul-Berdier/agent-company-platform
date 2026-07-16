from pydantic import BaseModel

from .enums import MemoryScope, SessionScope


class SessionContext(BaseModel):
    """Contexte d'isolation transmis à chaque appel provider.

    La plateforme n'envoie jamais automatiquement le contexte d'un projet
    à un autre : chaque session est bornée à sa hiérarchie.
    """

    session_id: str = ""
    scope: SessionScope = SessionScope.PROJECT
    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    team_id: str | None = None
    agent_instance_id: str | None = None
    provider_id: str | None = None
    external_session_id: str | None = None
    memory_scope: MemoryScope = MemoryScope.PROJECT
