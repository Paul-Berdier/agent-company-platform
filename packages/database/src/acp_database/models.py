from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class UserModel(_Common, Base):
    __tablename__ = "users"
    login_normalized: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    platform_role: Mapped[str] = mapped_column(String(50), default="owner", index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    bootstrap_marker: Mapped[str | None] = mapped_column(
        String(32), unique=True, nullable=True
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserSessionModel(_Common, Base):
    __tablename__ = "user_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ConversationModel(_Common, Base):
    __tablename__ = "conversations"

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Nouvelle conversation")
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    provider_id: Mapped[str] = mapped_column(String(100), default="hermes")
    provider_session_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, index=True
    )


class ConversationTurnModel(_Common, Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_request_id",
            name="uq_conversation_turn_client_request",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    client_request_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    user_content: Mapped[str] = mapped_column(Text)
    requested_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assistant_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="submitting", index=True)
    provider_run_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, index=True
    )


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
    # Une mission réutilise la tâche comme agrégat durable. Ces colonnes restent
    # optionnelles afin de conserver la compatibilité des tâches historiques.
    is_mission: Mapped[int] = mapped_column(Integer, default=0, index=True)
    objective: Mapped[str] = mapped_column(Text, default="")
    expected_outcome: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    autonomy: Mapped[dict] = mapped_column(JSON, default=dict)
    resources: Mapped[list] = mapped_column(JSON, default=list)
    budget: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    attempt_counter: Mapped[int] = mapped_column(Integer, default=0)
    active_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", use_alter=True), nullable=True, index=True
    )


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
    attempt_number: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    stop_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stop_requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    technical_validation: Mapped[dict] = mapped_column(JSON, default=dict)
    user_acceptance: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, index=True
    )


class MissionCommandModel(_Common, Base):
    """Journal de déduplication des commandes utilisateur non naturellement idempotentes."""

    __tablename__ = "mission_commands"
    __table_args__ = (
        UniqueConstraint(
            "principal_id",
            "command",
            "idempotency_key",
            name="uq_mission_command_principal_key",
        ),
    )

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    command: Mapped[str] = mapped_column(String(50))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    task_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id"), nullable=True
    )


class MissionCommentModel(_Common, Base):
    __tablename__ = "mission_comments"
    __table_args__ = (
        UniqueConstraint(
            "author_user_id",
            "task_run_id",
            "idempotency_key",
            name="uq_mission_comment_principal_run_key",
        ),
        CheckConstraint(
            "idempotency_key IS NULL OR task_run_id IS NOT NULL",
            name="ck_mission_comment_key_requires_run",
        ),
    )

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    task_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id"), nullable=True, index=True
    )
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), default="")


class MissionEvidenceModel(_Common, Base):
    __tablename__ = "mission_evidence"
    __table_args__ = (
        UniqueConstraint(
            "task_run_id", "fingerprint", name="uq_mission_evidence_fingerprint"
        ),
    )

    task_run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id"), index=True
    )
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uri: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


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


class WorkerModel(_Common, Base):
    __tablename__ = "workers"
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    token_prefix: Mapped[str] = mapped_column(String(12))
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    active_runs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="online", index=True)
    simulation: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkerLeaseModel(_Common, Base):
    __tablename__ = "worker_leases"
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    required_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ResourceLockModel(_Common, Base):
    __tablename__ = "resource_locks"
    __table_args__ = (UniqueConstraint("resource_type", "resource_key"),)
    resource_type: Mapped[str] = mapped_column(String(50), index=True)
    resource_key: Mapped[str] = mapped_column(String(1000))
    owner_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApprovalModel(_Common, Base):
    __tablename__ = "approvals"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_run_id: Mapped[str | None] = mapped_column(ForeignKey("task_runs.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str] = mapped_column(String(1000), default="")
    consequences: Mapped[list] = mapped_column(JSON, default=list)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    footprint: Mapped[dict] = mapped_column(JSON, default=dict)
    action_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    reason: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="WAITING_APPROVAL", index=True)
    requested_by: Mapped[str] = mapped_column(String(200))
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_comment: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidated_reason: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArtifactModel(_Common, Base):
    __tablename__ = "artifacts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(1000))
    checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
