from enum import Enum


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    QUEUED = "queued"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


class TaskRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    REVIEWING = "reviewing"
    BLOCKED = "blocked"
    OFFLINE = "offline"


class MemoryScope(str, Enum):
    GLOBAL = "GLOBAL"
    WORKSPACE = "WORKSPACE"
    PROJECT = "PROJECT"
    TEAM = "TEAM"
    AGENT = "AGENT"
    TASK_RUN = "TASK_RUN"


class MemoryClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


class SharingPolicy(str, Enum):
    NONE = "none"          # jamais partagé hors de son scope
    SCOPE_ONLY = "scope_only"
    SHAREABLE = "shareable"  # peut être injecté dans un contexte descendant


class SessionScope(str, Enum):
    GLOBAL_PROVIDER = "global_provider"
    WORKSPACE = "workspace"
    PROJECT = "project"
    AGENT_EXECUTION = "agent_execution"


class ProviderKind(str, Enum):
    ORCHESTRATOR = "orchestrator"
    EXECUTION = "execution"
    TOOL = "tool"


class PermissionRole(str, Enum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"
