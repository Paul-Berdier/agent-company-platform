from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """Instant toujours stocké et relu en UTC.

    SQLite ne conserve pas le décalage d'un ``DateTime(timezone=True)`` : il écrit
    l'heure murale et perd le ``+01:00``. Un appelant qui passerait un instant dans
    le fuseau de l'utilisateur verrait donc l'instant changer en traversant la base.

    Pour les colonnes du Lot F, cela ne serait pas une gêne d'affichage mais une
    perte de garantie : la clé de tir d'un déclenchement est dérivée de son instant
    nominal, donc un instant altéré par l'aller-retour produit une clé différente,
    et la contrainte d'unicité ``(automation_id, fire_key)`` cesse de refuser le
    doublon qu'elle existe pour refuser.

    Ce type normalise donc en UTC avant l'écriture et rattache UTC à la relecture.
    Un ``datetime`` naïf est refusé plutôt que supposé UTC : supposer inventerait un
    instant que l'appelant n'a pas donné.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                "un instant doit être conscient du fuseau avant d'être stocké "
                "(UTC attendu)"
            )
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


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
    exit_code: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=True)
    uri: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


_EVENT_SEQUENCE_PREDICATE = "task_run_id IS NOT NULL AND sequence IS NOT NULL"
_EVENT_JOURNAL_PREDICATE = "journal_seq IS NOT NULL"


class EventModel(_Common, Base):
    """Journal durable des événements métier.

    Deux compteurs, deux portées, jamais interchangeables :

    - ``sequence`` (Lot E) est la séquence monotone allouée par **tentative** : elle
      ordonne une tentative et sert de curseur de reprise à son flux SSE. L'unicité
      ``(task_run_id, sequence)`` est **partielle** car les lignes écrites avant le
      Lot E, et les événements sans run, n'ont ni run ni séquence ;
    - ``journal_seq`` est le compteur monotone du **journal entier** : il donne à la
      portée projet un ordre total, indépendant de la granularité de l'horloge. Son
      unicité est également partielle : les lignes antérieures à la colonne restent
      valides, et la migration les numérote dans leur ordre d'insertion.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index(
            "uq_event_run_sequence",
            "task_run_id",
            "sequence",
            unique=True,
            sqlite_where=text(_EVENT_SEQUENCE_PREDICATE),
            postgresql_where=text(_EVENT_SEQUENCE_PREDICATE),
        ),
        Index("ix_events_task_run_sequence", "task_run_id", "sequence"),
        Index(
            "uq_events_journal_seq",
            "journal_seq",
            unique=True,
            sqlite_where=text(_EVENT_JOURNAL_PREDICATE),
            postgresql_where=text(_EVENT_JOURNAL_PREDICATE),
        ),
        Index("ix_events_journal_seq", "journal_seq"),
    )

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
    schema_version: Mapped[str] = mapped_column(
        String(10), default="1.0", server_default="1.0"
    )
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    journal_seq: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emitted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    __table_args__ = (
        CheckConstraint(
            "global_access IN (0, 1)", name="ck_workers_global_access_boolean"
        ),
        CheckConstraint(
            "global_access = 0 OR project_id IS NULL",
            name="ck_workers_single_scope",
        ),
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    token_prefix: Mapped[str] = mapped_column(String(12))
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    active_runs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="online", index=True)
    simulation: Mapped[int] = mapped_column(Integer, default=1)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    global_access: Mapped[int] = mapped_column(Integer, default=0)
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
    """Livrable d'une tentative.

    ``storage_key`` (Lot E) est la clé d'un blob adressé par contenu ; elle reste
    ``NULL`` pour les artefacts historiques « métadonnées seules ». Le nom fourni par
    le client vit dans ``original_name`` et n'entre jamais dans le chemin de stockage.
    """

    __tablename__ = "artifacts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(1000))
    checksum: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    storage_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )
    content_type: Mapped[str] = mapped_column(
        String(200),
        default="application/octet-stream",
        server_default="application/octet-stream",
    )
    original_name: Mapped[str] = mapped_column(String(500), default="", server_default="")
    source: Mapped[str] = mapped_column(String(50), default="worker", server_default="worker")
    stream_kind: Mapped[str] = mapped_column(String(50), default="", server_default="")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --- Lot D : coffre de secrets, centre MCP, bibliothèque de skills ---------------


class SecretModel(_Common, Base):
    """Secret chiffré au repos (jeton Fernet) ; la valeur en clair n'est jamais stockée.

    SQLite considère les NULL comme distincts dans une contrainte d'unicité : l'unicité
    du nom pour la portée ``platform`` (``project_id`` NULL) est donc aussi appliquée
    en Python par le service.
    """

    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint(
            "name", "scope_type", "project_id", name="uq_secret_name_scope_project"
        ),
    )

    name: Mapped[str] = mapped_column(String(64), index=True)
    scope_type: Mapped[str] = mapped_column(String(20))  # platform | project
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    key_id: Mapped[str] = mapped_column(String(16))
    ciphertext: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class McpServerModel(_Common, Base):
    """Serveur MCP déclaré sur la plateforme ; la configuration vit dans les révisions."""

    __tablename__ = "mcp_servers"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # slug
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    source_kind: Mapped[str] = mapped_column(String(20))  # catalog | remote_url | import | manual
    origin: Mapped[str] = mapped_column(Text().with_variant(String(500), "sqlite"), default="")
    transport: Mapped[str] = mapped_column(String(10))  # http | stdio
    execution_location: Mapped[str] = mapped_column(String(20))  # platform | runner
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id"), nullable=True
    )  # runner désigné pour stdio
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[str] = mapped_column(Text, default="")
    last_probe_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class McpServerRevisionModel(_Common, Base):
    """Révision immuable de configuration (références de secrets uniquement, jamais de valeur)."""

    __tablename__ = "mcp_server_revisions"
    __table_args__ = (
        UniqueConstraint("server_id", "number", name="uq_mcp_server_revision_number"),
    )

    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # sha256 du JSON canonique
    discovery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    discovery_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    change_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_approval: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class McpProbeModel(_Common, Base):
    """Diagnostic d'un serveur : exécuté côté API (http) ou autorisé puis délégué à un runner (stdio)."""

    __tablename__ = "mcp_probes"

    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"), index=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_server_revisions.id"), index=True
    )
    transport: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    authorization: Mapped[dict] = mapped_column(JSON, default=dict)  # vide pour http
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_comment: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id"), nullable=True, index=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # validité de l'autorisation


class McpBindingModel(_Common, Base):
    """Rattachement d'un serveur à un projet avec un sous-ensemble d'outils autorisés."""

    __tablename__ = "mcp_bindings"
    __table_args__ = (
        UniqueConstraint("server_id", "project_id", name="uq_mcp_binding_server_project"),
    )

    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("mcp_server_revisions.id"))
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)  # non vide
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SkillModel(_Common, Base):
    """Skill installé sur la plateforme ; le contenu vit dans les révisions."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # slug
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="general")
    kind: Mapped[str] = mapped_column(String(20))  # documentary | scripted | native_plugin
    source_kind: Mapped[str] = mapped_column(String(20))  # manual | directory | archive | github | catalog
    origin: Mapped[str] = mapped_column(Text().with_variant(String(500), "sqlite"), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[str] = mapped_column(Text, default="")


class SkillRevisionModel(_Common, Base):
    """Révision immuable d'un skill : manifeste des fichiers, frontmatter, scan indicatif."""

    __tablename__ = "skill_revisions"
    __table_args__ = (
        UniqueConstraint("skill_id", "number", name="uq_skill_revision_number"),
    )

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # sha256 de [{path, sha256}]
    files: Mapped[list] = mapped_column(JSON, default=list)  # {path, size, sha256, text}
    skill_md: Mapped[str] = mapped_column(Text, default="")
    frontmatter: Mapped[dict] = mapped_column(JSON, default=dict)
    license: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dependencies: Mapped[dict] = mapped_column(JSON, default=dict)
    scan: Mapped[list] = mapped_column(JSON, default=list)  # {level, code, message, path}
    kind: Mapped[str] = mapped_column(String(20))
    storage_path: Mapped[str] = mapped_column(String(1000))
    change_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_approval: Mapped[int] = mapped_column(Integer, default=0)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_ref: Mapped[str] = mapped_column(Text().with_variant(String(500), "sqlite"), default="")  # chemin, sha256 d'archive, owner/repo@sha


class SkillBindingModel(_Common, Base):
    """Rattachement d'un skill à un projet."""

    __tablename__ = "skill_bindings"
    __table_args__ = (
        UniqueConstraint("skill_id", "project_id", name="uq_skill_binding_skill_project"),
    )

    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("skill_revisions.id"))
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --- Lot E : tests structurés et liens de livrables ----------------------------


class TestRunModel(_Common, Base):
    """Exécution de tests rattachée à une tentative de mission.

    Une seule exécution par tentative et par runner : l'ingestion du worker est
    idempotente et ne crée jamais un second résultat pour la même tentative.
    """

    __test__ = False  # table de données : pytest ne doit pas collecter la classe
    __tablename__ = "test_runs"
    __table_args__ = (
        UniqueConstraint("task_run_id", "runner", name="uq_test_run_attempt_runner"),
    )

    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id"), nullable=True
    )
    runner: Mapped[str] = mapped_column(String(50), default="playwright")
    runner_version: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=True)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_code: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=True)
    # Référence simple et non contrainte : la rétention peut effacer le rapport
    # sans avoir à réécrire l'exécution de tests.
    report_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class TestCaseModel(_Common, Base):
    """Cas de test d'une exécution ; chaque tentative garde sa ligne."""

    __test__ = False
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint(
            "test_run_id", "test_id", "attempt", name="uq_test_case_run_test_attempt"
        ),
    )

    test_run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), index=True)
    suite_path: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(500))
    test_id: Mapped[str] = mapped_column(String(200))
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    project_name: Mapped[str] = mapped_column(String(200), default="")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    expected_status: Mapped[str] = mapped_column(String(20), default="passed")
    status: Mapped[str] = mapped_column(String(20), index=True)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    error_snippet: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    annotations: Mapped[list] = mapped_column(JSON, default=list)
    attachment_artifact_ids: Mapped[list] = mapped_column(JSON, default=list)


class ArtifactLinkModel(_Common, Base):
    """Lien de téléchargement signé, lié à un artefact et à un utilisateur.

    Seule l'empreinte du jeton est stockée : la valeur signée n'existe que dans
    l'URL remise à l'utilisateur, et la révocation passe par ``revoked_at``.
    """

    __tablename__ = "artifact_links"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_count: Mapped[int] = mapped_column(Integer, default=0)


# --- Lot F : automatisations planifiées, budgets appliqués et alertes ----------


class AutomationModel(_Common, Base):
    """Routine planifiée d'un projet : un gabarit de mission et un calendrier.

    Une automatisation **naît désactivée** : elle ne se déclenche jamais du seul fait
    d'avoir été créée, et son activation est un geste explicite.

    ``next_run_at`` est indexé parce que le planificateur ne pose qu'une question à
    chaque examen : « quelles automatisations actives sont dues ? ». Sans index,
    cette question coûte une lecture complète de la table toutes les trente secondes.
    """

    __tablename__ = "automations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "created_by_user_id",
            "create_idempotency_key",
            name="uq_automations_create_principal_key",
        ),
        CheckConstraint(
            "(create_idempotency_key IS NULL AND create_request_fingerprint IS NULL) "
            "OR (create_idempotency_key IS NOT NULL AND "
            "create_request_fingerprint IS NOT NULL AND created_by_user_id IS NOT NULL)",
            name="ck_automations_create_idempotency_complete",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_automations_consecutive_failures",
        ),
        CheckConstraint(
            "failure_threshold >= 1", name="ck_automations_failure_threshold"
        ),
        CheckConstraint(
            "webhook_rotation_number >= 0",
            name="ck_automations_webhook_rotation_number",
        ),
        CheckConstraint(
            "mutation_revision >= 0",
            name="ck_automations_mutation_revision",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    schedule_kind: Mapped[str] = mapped_column(String(20))  # cron | interval
    schedule_expression: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(  # nom IANA, fuseau de référence
        String(64), default="Europe/Paris", server_default="Europe/Paris"
    )
    mission_template: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    catchup_policy: Mapped[str] = mapped_column(  # skip | run_once
        String(20), default="skip", server_default="skip"
    )
    max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True, index=True
    )
    last_fire_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Les anciennes lignes n'avaient pas de commande de création. Pour toutes les
    # nouvelles lignes, cette paire est complète et l'index composite arbitre les
    # requêtes concurrentes dans le scope projet + principal.
    create_idempotency_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    create_request_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # Le secret brut n'est jamais persisté. Une rotation remplace uniquement son
    # empreinte et conserve l'instant public de rotation pour l'interface.
    webhook_enabled: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    webhook_secret_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    webhook_rotated_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    # Numéro monotone de rotation : comparer seulement l'empreinte du secret ne
    # permettrait pas de détecter deux rotations distinctes réutilisant le même
    # secret fourni par le client.
    webhook_rotation_number: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    failure_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3"
    )
    # Révision monotone des commandes de configuration utilisateur. Elle ne suit
    # pas les curseurs du planificateur : elle sert uniquement à reconnaître un
    # rejeu dont une commande ultérieure a rendu le résultat obsolète.
    mutation_revision: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )


class AutomationWebhookRotationModel(_Common, Base):
    """Journal sans secret brut des rotations de webhook.

    La clé d'idempotence appartient à un principal et à une automatisation. La
    réponse peut être reconstruite à partir du secret que le client rejoue, tandis
    que seules ses empreintes sont persistées. ``rotation_number`` établit si ce
    journal désigne encore la configuration courante.
    """

    __tablename__ = "automation_webhook_rotations"
    __table_args__ = (
        UniqueConstraint(
            "automation_id",
            "principal_id",
            "idempotency_key",
            name="uq_webhook_rotation_principal_key",
        ),
        UniqueConstraint(
            "automation_id",
            "rotation_number",
            name="uq_webhook_rotation_number",
        ),
        CheckConstraint(
            "rotation_number >= 1", name="ck_webhook_rotation_number_positive"
        ),
    )

    automation_id: Mapped[str] = mapped_column(
        ForeignKey("automations.id"), index=True
    )
    principal_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    secret_hash: Mapped[str] = mapped_column(String(64))
    rotation_number: Mapped[int] = mapped_column(Integer)
    rotated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class AutomationCommandModel(_Common, Base):
    """Journal transactionnel des mutations rejouables d'une automatisation.

    La clé appartient à un principal, une automatisation et un type de commande.
    ``request_fingerprint`` interdit de réutiliser la clé avec une autre intention,
    tandis que ``postcondition`` permet de vérifier qu'un rejeu n'a pas été rendu
    obsolète par une mutation ultérieure. Le journal et l'événement métier sont
    validés dans la même transaction que la mutation.
    """

    __tablename__ = "automation_commands"
    __table_args__ = (
        UniqueConstraint(
            "automation_id",
            "principal_id",
            "command",
            "idempotency_key",
            name="uq_automation_command_principal_key",
        ),
        CheckConstraint(
            "command IN ('update', 'enable', 'disable', 'webhook.disable')",
            name="ck_automation_commands_command",
        ),
        CheckConstraint(
            "result_revision >= 1",
            name="ck_automation_commands_result_revision",
        ),
    )

    automation_id: Mapped[str] = mapped_column(
        ForeignKey("automations.id"), index=True
    )
    principal_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    command: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    postcondition: Mapped[dict] = mapped_column(JSON, default=dict)
    result_revision: Mapped[int] = mapped_column(BigInteger)


class AutomationRunModel(_Common, Base):
    """Déclenchement **matérialisé** d'une automatisation, lancé ou refusé.

    L'unicité ``(automation_id, fire_key)`` est la garantie d'absence de doublon du
    lot, et ce n'est pas une vérification en mémoire : deux planificateurs
    concurrents insèrent la même paire, la base en refuse un, et celui-là abandonne
    sans créer de mission.

    ``scheduled_for`` et ``fired_at`` sont deux colonnes distinctes et doivent le
    rester : l'instant **nominal** identifie l'occurrence, l'instant **réel** dit ce
    qui s'est passé. Les confondre rendrait la clé d'unicité inutile, puisque deux
    exécutions réelles n'ont jamais exactement le même instant.
    """

    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("automation_id", "fire_key", name="uq_automation_runs_fire_key"),
        Index(
            "ix_automation_runs_reconcile_order",
            "automation_id",
            "completion_observed_at",
            "scheduled_for",
            "id",
            "outcome",
        ),
        CheckConstraint(
            "trigger_kind IN ('manual', 'schedule', 'webhook')",
            name="ck_automation_runs_trigger_kind",
        ),
        CheckConstraint(
            "outcome IN ('launched', 'skipped_concurrency', 'skipped_disabled', "
            "'skipped_catchup', 'failed')",
            name="ck_automation_runs_outcome",
        ),
        CheckConstraint(
            "length(schedule_timezone) > 0",
            name="ck_automation_runs_schedule_timezone_nonempty",
        ),
    )

    automation_id: Mapped[str] = mapped_column(
        ForeignKey("automations.id"), index=True
    )
    fire_key: Mapped[str] = mapped_column(String(64))
    scheduled_for: Mapped[datetime] = mapped_column(UtcDateTime)
    fired_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
    # Snapshot immuable : un PATCH du calendrier parent ne réétiquette jamais
    # l'heure locale d'une occurrence déjà matérialisée.
    schedule_timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Paris", server_default="Europe/Paris"
    )
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    trigger_kind: Mapped[str] = mapped_column(
        String(20), default="schedule", server_default="schedule"
    )
    # launched | skipped_concurrency | skipped_disabled | skipped_catchup | failed
    outcome: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(String(500), default="")
    completion_observed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True, index=True
    )
    completion_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )


class SchedulerLeaseModel(_Common, Base):
    """Bail singleton du planificateur, arbitré et clôturé par la base.

    ``holder_id`` identifie un processus précis. Deux processus qui réutilisent le
    même jeton worker ne peuvent ainsi jamais partager implicitement le bail.
    ``fencing_token`` augmente à chaque reprise après expiration ou libération :
    une requête retardée d'un ancien leader est donc refusée même après reconnexion.
    """

    __tablename__ = "scheduler_leases"
    __table_args__ = (
        UniqueConstraint("scheduler_key", name="uq_scheduler_leases_key"),
        CheckConstraint(
            "fencing_token >= 0", name="ck_scheduler_leases_fencing_token"
        ),
    )

    scheduler_key: Mapped[str] = mapped_column(String(64))
    owner_worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id"), nullable=True, index=True
    )
    holder_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fencing_token: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True, index=True
    )
    last_renewed_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class BudgetUsageModel(_Common, Base):
    """Consommation observée d'une tentative : une seule ligne par tentative.

    ``usage_reported`` distingue « le fournisseur a rapporté zéro jeton » de « le
    fournisseur n'a rien rapporté ». Sans ce drapeau, un budget en jetons paraîtrait
    respecté alors que rien n'a jamais été mesuré : il reste à 0 tant qu'aucun bloc
    ``usage`` n'est arrivé.

    Le ledger immuable reste l'autorité. Ce cache dérivé est mis à jour sous le
    verrou de la tentative et chaque compteur est saturé à sa capacité maximale :
    deux rapports concurrents ne s'écrasent pas et aucun dépassement de type ne
    transforme une grande consommation en valeur plus petite.
    """

    __tablename__ = "budget_usage"
    __table_args__ = (
        CheckConstraint(
            "cost >= 0 AND cost <= 999999999999",
            name="ck_budget_usage_cost_capacity",
        ),
        CheckConstraint(
            "tokens_input >= 0 AND tokens_input <= 9007199254740991",
            name="ck_budget_usage_tokens_input_capacity",
        ),
        CheckConstraint(
            "tokens_output >= 0 AND tokens_output <= 9007199254740991",
            name="ck_budget_usage_tokens_output_capacity",
        ),
        CheckConstraint(
            "tool_calls >= 0 AND tool_calls <= 9007199254740991",
            name="ck_budget_usage_tool_calls_capacity",
        ),
        CheckConstraint(
            "usage_reported IN (0, 1)",
            name="ck_budget_usage_usage_reported_boolean",
        ),
        CheckConstraint(
            "cost_reported IN (0, 1)",
            name="ck_budget_usage_cost_reported_boolean",
        ),
        CheckConstraint(
            "tokens_input_reported IN (0, 1)",
            name="ck_budget_usage_tokens_input_reported_boolean",
        ),
        CheckConstraint(
            "tokens_output_reported IN (0, 1)",
            name="ck_budget_usage_tokens_output_reported_boolean",
        ),
        CheckConstraint(
            "tool_calls_reported IN (0, 1)",
            name="ck_budget_usage_tool_calls_reported_boolean",
        ),
    )

    task_run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id"), unique=True, index=True
    )
    # ``Numeric`` évite qu'une succession d'incréments monétaires introduise une
    # dérive binaire. L'upgrade SQLite reconstruit également les anciens caches
    # ``FLOAT`` afin que les bases existantes partagent cette garantie.
    cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="EUR", server_default="EUR"
    )
    tokens_input: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    tokens_output: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    tool_calls: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    usage_reported: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Disponibilité par métrique : une mesure réellement rapportée à zéro ne doit
    # jamais être confondue avec une donnée absente.
    cost_reported: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_input_reported: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    tokens_output_reported: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    tool_calls_reported: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AlertModel(_Common, Base):
    """Alerte d'un projet, dédupliquée tant qu'elle reste ouverte.

    ``dedupe_key_active`` vaut ``dedupe_key`` tant que l'alerte est ouverte et passe
    à ``NULL`` à l'acquittement. En SQL, ``NULL`` n'entre pas en conflit avec
    ``NULL`` dans un index unique : plusieurs alertes acquittées de même cause
    coexistent donc, tandis que deux alertes **ouvertes** de même cause sont
    impossibles.

    C'est la raison d'être de cette colonne apparemment redondante : elle obtient
    l'effet d'un index unique partiel sans en dépendre, ce que ``create_all`` ne
    saurait pas produire de façon portable ici.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "dedupe_key_active", name="uq_alerts_dedupe_active"
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alerts_severity",
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20))  # info | warning | critical
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    automation_id: Mapped[str | None] = mapped_column(
        ForeignKey("automations.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    # ``index=True`` : l'index ``ix_alerts_acknowledged_by_user_id`` était déjà
    # posé par la mise à niveau SQLite ad hoc ; le déclarer ici rend le modèle
    # seul juge du schéma, ce que la chaîne Alembic exige.
    acknowledged_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    acknowledgement_comment: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )
    dedupe_key: Mapped[str] = mapped_column(String(64))
    dedupe_key_active: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NotificationPreferencesModel(_Common, Base):
    """Préférences d'alertes d'un utilisateur dans un projet.

    Le seul canal annoncé est ``in_app`` car c'est le seul réellement livré. Les
    booléens par famille permettent de filtrer avant création d'une notification,
    sans prétendre qu'un courriel ou webhook externe existe.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", name="uq_notification_preferences_project_user"
        ),
        CheckConstraint("channel = 'in_app'", name="ck_notification_preferences_channel"),
        CheckConstraint(
            "minimum_severity IN ('info', 'warning', 'critical')",
            name="ck_notification_preferences_minimum_severity",
        ),
        CheckConstraint("enabled IN (0, 1)", name="ck_notification_preferences_enabled"),
        CheckConstraint(
            "budget_alerts IN (0, 1)", name="ck_notification_preferences_budget"
        ),
        CheckConstraint(
            "automation_failures IN (0, 1)",
            name="ck_notification_preferences_automation",
        ),
        CheckConstraint(
            "storage_alerts IN (0, 1)", name="ck_notification_preferences_storage"
        ),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(
        String(20), default="in_app", server_default="in_app"
    )
    enabled: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    minimum_severity: Mapped[str] = mapped_column(
        String(20), default="warning", server_default="warning"
    )
    budget_alerts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    automation_failures: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    storage_alerts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=_now, onupdate=_now
    )


class ProjectBudgetPolicyModel(_Common, Base):
    """Politique de budget transversale, une version courante par projet."""

    __tablename__ = "project_budget_policies"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_budget_policies_project"),
        CheckConstraint("length(timezone) > 0", name="ck_project_budget_timezone_nonempty"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Paris", server_default="Europe/Paris"
    )
    policy: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=_now, onupdate=_now
    )


class BudgetUsageReportModel(_Common, Base):
    """Ledger immuable des incréments de consommation reçus exactement une fois.

    La paire ``(task_run_id, report_id)`` est fournie par l'émetteur et constitue
    la frontière d'idempotence. ``budget_usage`` reste le cache agrégé rapide ; ce
    ledger est la preuve rejouable qui permet de le reconstruire.
    """

    __tablename__ = "budget_usage_reports"
    __table_args__ = (
        UniqueConstraint(
            "task_run_id", "report_id", name="uq_budget_usage_reports_run_report"
        ),
        CheckConstraint(
            "kind IN ('reservation', 'usage')", name="ck_budget_report_kind"
        ),
        CheckConstraint("source IN ('provider', 'platform')", name="ck_budget_report_source"),
        CheckConstraint(
            "phase IN ('planning', 'execution', 'evaluation', 'tool')",
            name="ck_budget_report_phase",
        ),
        CheckConstraint("estimated IN (0, 1)", name="ck_budget_report_estimated"),
        CheckConstraint("allowed IN (0, 1)", name="ck_budget_report_allowed"),
        CheckConstraint(
            "length(accounting_day) = 10", name="ck_budget_report_accounting_day"
        ),
        CheckConstraint(
            "cost IS NULL OR (cost >= 0 AND cost <= 999999999999)",
            name="ck_budget_report_cost",
        ),
        CheckConstraint(
            "tokens_input IS NULL OR tokens_input >= 0", name="ck_budget_report_tokens_input"
        ),
        CheckConstraint(
            "tokens_input IS NULL OR tokens_input <= 9007199254740991",
            name="ck_budget_report_tokens_input_capacity",
        ),
        CheckConstraint(
            "tokens_output IS NULL OR tokens_output >= 0", name="ck_budget_report_tokens_output"
        ),
        CheckConstraint(
            "tokens_output IS NULL OR tokens_output <= 9007199254740991",
            name="ck_budget_report_tokens_output_capacity",
        ),
        CheckConstraint(
            "tool_calls IS NULL OR tool_calls >= 0", name="ck_budget_report_tool_calls"
        ),
        CheckConstraint(
            "tool_calls IS NULL OR tool_calls <= 9007199254740991",
            name="ck_budget_report_tool_calls_capacity",
        ),
        CheckConstraint(
            "(cost IS NULL AND currency IS NULL) OR "
            "(cost IS NOT NULL AND currency IS NOT NULL)",
            name="ck_budget_report_cost_currency",
        ),
        CheckConstraint(
            "cost IS NOT NULL OR tokens_input IS NOT NULL OR "
            "tokens_output IS NOT NULL OR tool_calls IS NOT NULL",
            name="ck_budget_report_has_measure",
        ),
    )

    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    report_id: Mapped[str] = mapped_column(String(128))
    permit_id: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    # Une réservation est le permit atomique pré-effet ; un usage est la mesure
    # post-effet. Ils partagent le ledger mais ne peuvent donc pas être confondus.
    kind: Mapped[str] = mapped_column(
        String(20), default="usage", server_default="usage"
    )
    source: Mapped[str] = mapped_column(String(20))
    phase: Mapped[str] = mapped_column(String(20))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tool_calls: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    estimated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    allowed: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Le jour est choisi à la réservation puis copié sur l'usage. Il ne dérive
    # donc jamais de l'heure du rapport, qui peut franchir minuit local.
    accounting_day: Mapped[str] = mapped_column(String(10), index=True)
    # Une réponse rejouée doit rendre exactement la décision originale, même si
    # d'autres usages ont modifié les totaux depuis.
    verdict_snapshot: Mapped[dict] = mapped_column(JSON)
    reconciled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now, index=True)


_EVENT_OUTBOX_PENDING_PREDICATE = "delivered_at IS NULL AND dead_at IS NULL"


class EventOutboxModel(Base):
    """Boîte d'envoi transactionnelle des événements à relayer.

    Une ligne par événement journalisé et par consommateur : elle est écrite dans
    la **même** transaction que la ligne ``events`` et ne disparaît qu'une fois la
    livraison confirmée (``delivered_at``) ou abandonnée (``dead_at``). Le relais
    ne dépend ainsi plus d'un appel direct réussi au moment de la publication.

    La table n'hérite pas de ``_Common`` : sa clé est l'identifiant de l'événement
    lui-même, sans cascade, afin qu'une purge d'événements ne puisse jamais
    effacer silencieusement une livraison encore due. L'index partiel
    ``ix_event_outbox_pending`` ne couvre que les lignes encore à livrer : c'est
    la seule question que pose le relais, et la table grossit avec le journal.

    Le Lot H1 ne livre que le schéma ; le remplissage et la consommation
    appartiennent au Lot H3.
    """

    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_event_outbox_attempts_non_negative"),
        Index(
            "ix_event_outbox_pending",
            "consumer",
            "next_attempt_at",
            sqlite_where=text(_EVENT_OUTBOX_PENDING_PREDICATE),
            postgresql_where=text(_EVENT_OUTBOX_PENDING_PREDICATE),
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id"), primary_key=True
    )
    journal_seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    consumer: Mapped[str] = mapped_column(
        String(50), default="event-service", server_default="event-service"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(UtcDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    dead_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(500), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)


class McpExecutionGrantModel(_Common, Base):
    """Délégation courte au CLI : seul le condensat du jeton est conservé."""

    __tablename__ = "mcp_execution_grants"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), index=True)
    worker_token_hash: Mapped[str] = mapped_column(String(64))
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    fencing_token: Mapped[int] = mapped_column(Integer)
    step_id: Mapped[str] = mapped_column(String(128))
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("mcp_server_revisions.id"))
    allowed_tools: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class McpExecutionCallModel(_Common, Base):
    """Réservation avant effet ; un résultat perdu n'autorise jamais un replay."""

    __tablename__ = "mcp_execution_calls"
    __table_args__ = (
        UniqueConstraint("call_key", name="uq_mcp_execution_call_key"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'unknown', 'denied')",
            name="ck_mcp_execution_call_status",
        ),
    )

    call_key: Mapped[str] = mapped_column(String(64))
    task_run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("mcp_server_revisions.id"))
    step_id: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class SubscriptionQuotaSnapshotModel(_Common, Base):
    """Dernier relevé de quota d'abonnement d'un worker, par fournisseur et compteur.

    Chaque ligne recopie ce que la source officielle a répondu (app-server Codex,
    ligne d'état Claude Code) : ``windows`` et ``credits`` gardent la forme validée
    par ``acp_contracts.subscriptions``, une valeur inconnue y reste ``null``.
    ``observed_at`` est l'instant de la lecture à la source ; un relevé plus ancien
    que celui stocké ne le remplace jamais. Les lignes disparaissent avec leur
    worker : un relevé sans poste connu n'a plus de titulaire vérifiable.
    """

    __tablename__ = "subscription_quota_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "worker_id", "provider", "limit_id", name="uq_subscription_quota_snapshot"
        ),
        CheckConstraint(
            "provider IN ('codex', 'claude_code')", name="ck_subscription_quota_provider"
        ),
        CheckConstraint(
            "status IN ('ok', 'not_signed_in', 'cli_missing', 'cli_too_old', 'unavailable')",
            name="ck_subscription_quota_status",
        ),
        CheckConstraint(
            "source IN ('codex_app_server', 'claude_code_statusline')",
            name="ck_subscription_quota_source",
        ),
        CheckConstraint(
            "limit_reached IS NULL OR limit_reached IN (0, 1)",
            name="ck_subscription_quota_limit_reached",
        ),
    )

    worker_id: Mapped[str] = mapped_column(
        ForeignKey("workers.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(32))
    limit_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32))
    plan: Mapped[str | None] = mapped_column(String(40), nullable=True)
    windows: Mapped[list] = mapped_column(JSON)
    credits: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    limit_reached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reached_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime)
