from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class _Common:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OrganizationModel(_Common, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class WorkspaceModel(_Common, Base):
    __tablename__ = "workspaces"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(50), default="generic")
    description: Mapped[str] = mapped_column(Text, default="")


class DepartmentModel(_Common, Base):
    __tablename__ = "departments"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(200))
    department_type: Mapped[str] = mapped_column(String(100))
    office_theme: Mapped[str] = mapped_column(String(100), default="default")
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class ProjectModel(_Common, Base):
    __tablename__ = "projects"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    project_type: Mapped[str] = mapped_column(String(100), default="generic")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="active")


class TeamModel(_Common, Base):
    __tablename__ = "teams"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    mission: Mapped[str] = mapped_column(Text, default="")


class TeamMemberModel(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    agent_instance_id: Mapped[str] = mapped_column(
        ForeignKey("agent_instances.id"), primary_key=True
    )
    role_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AgentInstanceModel(_Common, Base):
    __tablename__ = "agent_instances"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[str] = mapped_column(String(100))
    module: Mapped[str] = mapped_column(String(100), default="core")
    status: Mapped[str] = mapped_column(String(50), default="idle")
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskModel(_Common, Base):
    __tablename__ = "tasks"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_instances.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="backlog", index=True)
    workflow_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskRunModel(_Common, Base):
    __tablename__ = "task_runs"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_instances.id"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list)


class EventModel(_Common, Base):
    __tablename__ = "events"
    type: Mapped[str] = mapped_column(String(100), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class SessionModel(_Common, Base):
    __tablename__ = "sessions"
    scope: Mapped[str] = mapped_column(String(50))
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    memory_scope: Mapped[str] = mapped_column(String(50), default="PROJECT")


class MemoryModel(_Common, Base):
    __tablename__ = "memories"
    scope: Mapped[str] = mapped_column(String(50), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    classification: Mapped[str] = mapped_column(String(50), default="internal")
    sharing_policy: Mapped[str] = mapped_column(String(50), default="scope_only")
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)


class MembershipModel(_Common, Base):
    __tablename__ = "memberships"
    user_id: Mapped[str] = mapped_column(String(200), index=True)
    scope_type: Mapped[str] = mapped_column(String(50))  # workspace | project
    scope_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(50), default="member")


class ProviderModel(_Common, Base):
    __tablename__ = "providers"
    kind: Mapped[str] = mapped_column(String(50))  # orchestrator | execution | tool
    name: Mapped[str] = mapped_column(String(200))
    provider_key: Mapped[str] = mapped_column(String(100), unique=True)
    contract_version: Mapped[str] = mapped_column(String(20), default="1.0")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
