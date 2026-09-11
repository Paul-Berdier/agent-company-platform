"""Contrats de données versionnés partagés par tous les services de la plateforme.

Le cœur métier ne dépend que de ces contrats : jamais d'une implémentation
de provider (Hermes, Claude, Codex, ...).
"""

CONTRACTS_VERSION = "1.0"

from .auth import (  # noqa: F401
    AuthenticatedUser,
    AuthSessionResponse,
    AuthStatusResponse,
    LoginRequest,
    LogoutResponse,
    OwnerBootstrapRequest,
)
from .enums import (  # noqa: F401
    AgentStatus,
    MemoryClassification,
    MemoryScope,
    PermissionRole,
    ProviderKind,
    SessionScope,
    SharingPolicy,
    TaskRunStatus,
    TaskStatus,
)
from .entities import (  # noqa: F401
    AgentInstance,
    Department,
    Organization,
    Project,
    Task,
    TaskRun,
    Team,
    TeamMember,
    Workspace,
)
from .conversations import (  # noqa: F401
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationPatch,
    ConversationStatus,
    ConversationSummary,
    ConversationTurn,
    ConversationTurnCreate,
    ConversationTurnList,
    ConversationTurnStatus,
    HermesConnectionDiagnostic,
)
from .events import Event, EventEnvelope  # noqa: F401
from .memory import MemoryItem  # noqa: F401
from .providers import (  # noqa: F401
    ContextSummary,
    ContextSummaryRequest,
    EvaluationRequest,
    EvaluationResult,
    PlanningRequest,
    PlanningResult,
    PlanRevisionRequest,
    PlanStep,
    ProviderDescriptor,
    ProviderHealth,
)
from .sessions import SessionContext  # noqa: F401
from .operations import (  # noqa: F401
    ApprovalAction,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    Artifact,
    ArtifactCreate,
    LockAcquireRequest,
    LockOwnerRequest,
    ResourceLock,
    ResourceType,
)
from .workers import (  # noqa: F401
    WorkerCapability,
    WorkerClaimRequest,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerLeaseResponse,
    WorkerRegistrationRequest,
    WorkerRegistrationResponse,
    WorkerSnapshot,
    WorkerStatus,
)
