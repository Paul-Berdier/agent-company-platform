"""Contrats du centre MCP : serveurs, révisions, probes, bindings, catalogue, import/export.

Aucun contrat de ce module ne transporte une valeur de secret : seules des
références (``SecretRef``) circulent. Les valeurs sont chiffrées côté serveur et
injectées uniquement au moment d'un appel autorisé.
"""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .limits import CapturedStr
from .limits import DatabaseModel as BaseModel

McpTransport = Literal["http", "stdio"]
McpExecutionLocation = Literal["platform", "runner"]
McpServerStatus = Literal["draft", "active", "disabled", "revoked"]
McpProbeStatus = Literal[
    "pending_approval",
    "queued",
    "claimed",
    "succeeded",
    "failed",
    "rejected",
    "expired",
    "invalidated",
    "cancelled",
]
McpSourceKind = Literal["catalog", "remote_url", "import", "manual"]
McpRiskLevel = Literal["info", "caution", "danger"]
McpImportFormat = Literal["auto", "hermes", "claude", "codex"]
McpExportFormat = Literal["hermes", "claude", "codex"]

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,62})$"
_SLUG_RE = re.compile(SLUG_PATTERN)

TOOL_DESCRIPTION_MAX_CHARS = 2000
STDERR_TAIL_MAX_CHARS = 4096


def validate_slug(value: str) -> str:
    """Impose le format slug ``^[a-z0-9](?:[a-z0-9-]{0,62})$`` aux identifiants publics."""

    if not isinstance(value, str) or not _SLUG_RE.fullmatch(value):
        raise ValueError(
            "identifiant invalide : un slug est attendu (minuscules, chiffres et tirets, "
            "63 caractères au plus, commençant par une lettre ou un chiffre)"
        )
    return value


class SecretRef(BaseModel):
    """Référence vers un secret du coffre ; jamais une valeur."""

    secret_id: str = Field(min_length=1, max_length=36)


class McpHttpConfig(BaseModel):
    """Configuration d'un serveur MCP Streamable HTTP exécuté depuis la plateforme."""

    url: str = Field(min_length=1, max_length=2000)  # https obligatoire sauf allowlist (validé côté serveur)
    headers: dict[str, str] = Field(default_factory=dict)  # valeurs littérales NON secrètes uniquement
    header_secrets: dict[str, SecretRef] = Field(default_factory=dict)  # en-tête -> référence de secret
    timeout_seconds: int = Field(default=15, ge=1, le=120)


class McpStdioConfig(BaseModel):
    """Configuration d'un serveur MCP stdio lancé sur un runner désigné."""

    command: str = Field(min_length=1, max_length=2000)  # chemin absolu exigé (contrôlé côté serveur)
    args: list[str] = Field(default_factory=list, max_length=200)
    env: dict[str, str] = Field(default_factory=dict)  # valeurs NON secrètes
    env_secrets: dict[str, SecretRef] = Field(default_factory=dict)
    cwd: str | None = Field(default=None, max_length=2000)
    timeout_seconds: int = Field(default=20, ge=1, le=120)


class McpServerConfig(BaseModel):
    """Configuration d'un serveur : exactement le bloc correspondant au transport."""

    transport: McpTransport
    http: McpHttpConfig | None = None
    stdio: McpStdioConfig | None = None

    @model_validator(mode="after")
    def block_matches_transport(self) -> "McpServerConfig":
        if self.transport == "http":
            if self.http is None:
                raise ValueError("le transport http exige le bloc de configuration « http »")
            if self.stdio is not None:
                raise ValueError("le transport http n'accepte pas de bloc « stdio »")
        else:
            if self.stdio is None:
                raise ValueError("le transport stdio exige le bloc de configuration « stdio »")
            if self.http is not None:
                raise ValueError("le transport stdio n'accepte pas de bloc « http »")
        return self

    @property
    def execution_location(self) -> McpExecutionLocation:
        return "platform" if self.transport == "http" else "runner"


class McpServerCreate(BaseModel):
    name: str
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    source_kind: McpSourceKind = "manual"
    origin: str = Field(default="", max_length=500)
    config: McpServerConfig
    target_worker_id: str | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def name_is_slug(cls, value: str) -> str:
        return validate_slug(value)


class McpServerRevisionCreate(BaseModel):
    config: McpServerConfig
    target_worker_id: str | None = None
    note: str = Field(default="", max_length=2000)


class McpRiskFlag(BaseModel):
    code: str
    level: McpRiskLevel
    message: str


class McpDiscoveredTool(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)

    @field_validator("description")
    @classmethod
    def bound_description(cls, value: str) -> str:
        return value[:TOOL_DESCRIPTION_MAX_CHARS]


class McpDiscovery(BaseModel):
    protocol_version: str
    server_info: dict[str, Any] = Field(default_factory=dict)
    tools: list[McpDiscoveredTool] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False


class McpRevisionDiff(BaseModel):
    previous_number: int | None = None
    changed_fields: list[str] = Field(default_factory=list)
    endpoint_changed: bool = False
    command_changed: bool = False
    secrets_added: list[str] = Field(default_factory=list)
    secrets_removed: list[str] = Field(default_factory=list)
    tools_added: list[str] = Field(default_factory=list)
    tools_removed: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    reasons: list[str] = Field(default_factory=list)


class McpServerRevision(BaseModel):
    id: str
    server_id: str
    number: int
    config: McpServerConfig  # les SecretRef restent des références
    fingerprint: str
    discovery: McpDiscovery | None = None
    discovered_at: datetime | None = None
    discovery_current: bool = False  # discovery_fingerprint == fingerprint
    risk_flags: list[McpRiskFlag] = Field(default_factory=list)
    change_summary: McpRevisionDiff | None = None
    requires_approval: bool = False
    note: str = ""
    created_at: datetime
    superseded_at: datetime | None = None


class McpProbeAuthorization(BaseModel):
    action: Literal["mcp_stdio_launch"] = "mcp_stdio_launch"
    target: str
    consequences: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    expires_at: datetime


class McpProbeResult(BaseModel):
    protocol_version: str | None = None
    server_info: dict[str, Any] | None = None
    tools: list[McpDiscoveredTool] = Field(default_factory=list)
    exit_code: int | None = None
    stderr_tail: CapturedStr = ""
    duration_ms: int | None = None
    error: str | None = None

    @field_validator("stderr_tail")
    @classmethod
    def keep_tail(cls, value: str) -> str:
        return value[-STDERR_TAIL_MAX_CHARS:] if len(value) > STDERR_TAIL_MAX_CHARS else value


class McpProbe(BaseModel):
    id: str
    server_id: str
    revision_id: str
    transport: McpTransport
    status: McpProbeStatus
    authorization: McpProbeAuthorization | None = None
    requested_by_user_id: str
    decided_by_user_id: str | None = None
    decided_at: datetime | None = None
    decision_comment: str = ""
    worker_id: str | None = None
    claimed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    result: McpProbeResult | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    expires_at: datetime


class McpProbeDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)


class McpBindingCreate(BaseModel):
    project_id: str = Field(min_length=1)
    allowed_tools: list[str] = Field(min_length=1, max_length=500)


class McpBindingPatch(BaseModel):
    allowed_tools: list[str] | None = Field(default=None, max_length=500)
    enabled: bool | None = None

    @field_validator("allowed_tools")
    @classmethod
    def tools_not_empty(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and not value:
            raise ValueError("allowed_tools ne peut pas être vide : retirez le binding pour tout couper")
        return value


class McpBinding(BaseModel):
    id: str
    server_id: str
    server_name: str
    project_id: str
    revision_id: str
    revision_number: int
    allowed_tools: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class McpServerSummary(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    source_kind: McpSourceKind
    origin: str = ""
    transport: McpTransport
    execution_location: McpExecutionLocation
    status: McpServerStatus
    current_revision_number: int | None = None
    discovery_current: bool = False
    tool_count: int = 0
    binding_count: int = 0
    target_worker_id: str | None = None
    last_probe_status: McpProbeStatus | None = None
    last_probe_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class McpServerDetail(McpServerSummary):
    current_revision: McpServerRevision | None = None
    revisions: list[McpServerRevision] = Field(default_factory=list)
    bindings: list[McpBinding] = Field(default_factory=list)
    probes: list[McpProbe] = Field(default_factory=list)  # 10 dernières
    apply_notes: list[str] = Field(default_factory=list)


class McpRevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class McpRollbackRequest(BaseModel):
    revision_number: int = Field(ge=1)
    note: str = Field(default="", max_length=2000)


# --- Catalogue ---------------------------------------------------------------


class McpCatalogEntry(BaseModel):
    id: str
    display_name: str
    description: str = ""
    transport: McpTransport
    config: McpServerConfig  # header_secrets/env_secrets vides ; required_secrets liste les noms attendus
    required_secrets: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    documentation_url: str = ""
    verified_at: str  # date ISO
    verification: str  # ce qui a été vérifié (« documentation lue », jamais « exécuté »)


# --- Import --------------------------------------------------------------------


class McpImportPreviewRequest(BaseModel):
    format: McpImportFormat = "auto"
    content: str = Field(max_length=1_000_000)


class McpImportSecretCandidate(BaseModel):
    location: Literal["header", "env", "url"]
    key: str
    suggested_secret_name: str
    masked_value: str  # "***" + 2 derniers caractères au plus


class McpImportEntry(BaseModel):
    name: str
    source_name: str
    transport: McpTransport | None = None
    config: McpServerConfig | None = None
    secret_candidates: list[McpImportSecretCandidate] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflict: Literal["none", "existing_server"] = "none"
    importable: bool = False


class McpImportPreview(BaseModel):
    detected_format: Literal["hermes", "claude", "codex"] | None = None
    entries: list[McpImportEntry] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class McpImportApplyRequest(BaseModel):
    format: McpImportFormat = "auto"
    content: str = Field(max_length=1_000_000)
    names: list[str] = Field(default_factory=list)  # entrées à importer
    secret_mapping: dict[str, str] = Field(default_factory=dict)  # suggested_secret_name -> secret_id
    on_conflict: Literal["skip", "new_revision"] = "skip"


class McpImportApplyResult(BaseModel):
    created: list[McpServerSummary] = Field(default_factory=list)
    revised: list[McpServerSummary] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --- Export --------------------------------------------------------------------


class McpExport(BaseModel):
    format: McpExportFormat
    project_id: str | None = None
    content: str
    placeholders: list[str] = Field(default_factory=list)  # ACP_SECRET_<NOM>
    partial_compatibility: list[str] = Field(default_factory=list)
    apply_notes: list[str] = Field(default_factory=list)
