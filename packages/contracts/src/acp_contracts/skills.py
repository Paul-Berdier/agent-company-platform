"""Contrats de la bibliothèque de skills (format ``SKILL.md`` + frontmatter Hermes/agentskills).

Les contenus importés (README, SKILL.md, scripts) sont des données non fiables :
ils sont bornés et présentés comme tels, jamais interprétés comme des instructions.
"""

import posixpath
import re
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel as FileTransportModel
from pydantic import Field, field_validator

from .limits import DatabaseModel as BaseModel
from .limits import NulFreeStr
from .mcp import validate_slug

SkillKind = Literal["documentary", "scripted", "native_plugin"]
SkillStatus = Literal["draft", "active", "disabled", "revoked"]
SkillSourceKind = Literal["manual", "directory", "archive", "github", "catalog"]
SkillFindingLevel = Literal["info", "caution", "danger"]

GIT_SHA_PATTERN = r"^[0-9a-fA-F]{40}$"
GITHUB_REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
SKILL_FILE_CONTENT_MAX_CHARS = 200_000

_GIT_SHA_RE = re.compile(GIT_SHA_PATTERN)
_GITHUB_REPOSITORY_RE = re.compile(GITHUB_REPOSITORY_PATTERN)


class SkillFile(BaseModel):
    path: str
    size: int = Field(ge=0)
    sha256: str
    text: bool


class SkillDependencies(BaseModel):
    required_environment_variables: list[dict[str, Any]] = Field(default_factory=list)
    requires_toolsets: list[str] = Field(default_factory=list)
    requires_tools: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    network_indicators: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class SkillScanFinding(BaseModel):
    level: SkillFindingLevel
    code: str
    message: str
    path: str | None = None


class SkillRevisionDiff(BaseModel):
    previous_number: int | None = None
    files_added: list[str] = Field(default_factory=list)
    files_removed: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    scripts_added: list[str] = Field(default_factory=list)
    network_indicators_added: list[str] = Field(default_factory=list)
    permissions_added: list[str] = Field(default_factory=list)
    kind_changed: bool = False
    requires_approval: bool = False
    reasons: list[str] = Field(default_factory=list)


class SkillRevision(BaseModel):
    id: str
    skill_id: str
    number: int
    fingerprint: str
    files: list[SkillFile] = Field(default_factory=list)
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    license: str | None = None
    dependencies: SkillDependencies = Field(default_factory=SkillDependencies)
    scan: list[SkillScanFinding] = Field(default_factory=list)
    kind: SkillKind
    change_summary: SkillRevisionDiff | None = None
    requires_approval: bool = False
    approved: bool = False
    approved_at: datetime | None = None
    source_ref: str = ""
    note: str = ""
    created_at: datetime
    superseded_at: datetime | None = None


class SkillBinding(BaseModel):
    id: str
    skill_id: str
    skill_name: str
    project_id: str
    revision_id: str
    revision_number: int
    enabled: bool = True
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class SkillSummary(BaseModel):
    id: str
    name: str
    display_name: str
    description: str = ""
    category: str = "general"
    kind: SkillKind
    source_kind: SkillSourceKind
    origin: str = ""
    status: SkillStatus
    current_revision_number: int | None = None
    binding_count: int = 0
    requires_approval: bool = False  # révision courante non approuvée
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class SkillDetail(SkillSummary):
    current_revision: SkillRevision | None = None
    revisions: list[SkillRevision] = Field(default_factory=list)
    bindings: list[SkillBinding] = Field(default_factory=list)
    apply_notes: list[str] = Field(default_factory=list)


# --- Sources d'import -------------------------------------------------------


class SkillSourceFile(FileTransportModel):
    """Le contenu va au fichier, sans transformation ; seul le chemin est persisté."""

    path: NulFreeStr = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=2_000_000)


class SkillSourceManual(BaseModel):
    kind: Literal["manual"] = "manual"
    files: list[SkillSourceFile] = Field(min_length=1, max_length=500)

    @field_validator("files")
    @classmethod
    def contains_root_skill_md(cls, value: list[SkillSourceFile]) -> list[SkillSourceFile]:
        if not any(posixpath.normpath(file.path.replace("\\", "/")) == "SKILL.md" for file in value):
            raise ValueError("la source manuelle doit contenir un fichier SKILL.md à la racine")
        return value


class SkillSourceDirectory(BaseModel):
    kind: Literal["directory"] = "directory"
    path: str = Field(min_length=1, max_length=2000)


class SkillSourceArchive(BaseModel):
    kind: Literal["archive"] = "archive"
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)


class SkillSourceGithub(BaseModel):
    kind: Literal["github"] = "github"
    repository: str  # owner/repo
    ref: str  # SHA de commit (40 hex) : jamais une branche ni un tag
    path: str = Field(default="", max_length=1000)

    @field_validator("repository")
    @classmethod
    def repository_is_owner_repo(cls, value: str) -> str:
        if not _GITHUB_REPOSITORY_RE.fullmatch(value):
            raise ValueError("dépôt GitHub invalide : format « owner/repo » attendu")
        return value

    @field_validator("ref")
    @classmethod
    def ref_is_full_sha(cls, value: str) -> str:
        if not _GIT_SHA_RE.fullmatch(value):
            raise ValueError(
                "ref invalide : épinglez un commit complet (SHA de 40 caractères hexadécimaux)"
            )
        return value.lower()


SkillSource = Annotated[
    Union[SkillSourceManual, SkillSourceDirectory, SkillSourceArchive, SkillSourceGithub],
    Field(discriminator="kind"),
]


class SkillImportRequest(BaseModel):
    source: SkillSource
    name: str | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def name_is_slug(cls, value: str | None) -> str | None:
        return None if value is None else validate_slug(value)


class SkillRevisionCreate(BaseModel):
    source: SkillSource
    note: str = Field(default="", max_length=2000)


class SkillBindingCreate(BaseModel):
    project_id: str = Field(min_length=1)


class SkillRevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class SkillRollbackRequest(BaseModel):
    revision_number: int = Field(ge=1)
    note: str = Field(default="", max_length=2000)


class SkillApproveRequest(BaseModel):
    comment: str = Field(default="", max_length=2000)


class SkillFileContent(BaseModel):
    path: str
    text: bool
    content: str | None = None  # ≤ 200 000 caractères, sinon tronqué
    truncated: bool = False
    size: int = Field(ge=0)
    sha256: str


class SkillCatalogEntry(BaseModel):
    id: str
    display_name: str
    description: str = ""
    repository: str
    path: str = ""
    documentation_url: str = ""
    license: str | None = None
    verified_at: str
    verification: str
    note: str = "épingler un commit (SHA) avant installation"


class SkillSearchResult(BaseModel):
    installed: list[SkillSummary] = Field(default_factory=list)
    catalog: list[SkillCatalogEntry] = Field(default_factory=list)
