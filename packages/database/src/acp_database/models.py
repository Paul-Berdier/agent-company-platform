from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    journal_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    origin: Mapped[str] = mapped_column(String(500), default="")
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
    origin: Mapped[str] = mapped_column(String(500), default="")
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
    source_ref: Mapped[str] = mapped_column(String(500), default="")  # chemin, sha256 d'archive, owner/repo@sha


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
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
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
    )

    automation_id: Mapped[str] = mapped_column(
        ForeignKey("automations.id"), index=True
    )
    fire_key: Mapped[str] = mapped_column(String(64))
    scheduled_for: Mapped[datetime] = mapped_column(UtcDateTime)
    fired_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    # launched | skipped_concurrency | skipped_disabled | failed
    outcome: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(String(500), default="")


class BudgetUsageModel(_Common, Base):
    """Consommation observée d'une tentative : une seule ligne par tentative.

    ``usage_reported`` distingue « le fournisseur a rapporté zéro jeton » de « le
    fournisseur n'a rien rapporté ». Sans ce drapeau, un budget en jetons paraîtrait
    respecté alors que rien n'a jamais été mesuré : il reste à 0 tant qu'aucun bloc
    ``usage`` n'est arrivé.

    Les écritures sont des incréments SQL (``SET x = x + :n``) et jamais une lecture
    suivie d'une écriture : deux rapports concurrents ne doivent pas s'écraser.
    """

    __tablename__ = "budget_usage"

    task_run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id"), unique=True, index=True
    )
    cost: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    currency: Mapped[str] = mapped_column(
        String(3), default="EUR", server_default="EUR"
    )
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    usage_reported: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    acknowledged_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(64))
    dedupe_key_active: Mapped[str | None] = mapped_column(String(64), nullable=True)
