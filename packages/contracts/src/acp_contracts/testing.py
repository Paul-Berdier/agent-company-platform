"""Contrats des exécutions de tests structurées (Lot E).

Un succès provient d'assertions et d'un code de sortie réels. Les statuts
``passed``, ``failed``, ``timedOut``, ``skipped`` et ``interrupted`` ainsi que le
caractère ``flaky`` sont conservés distinctement : ils ne sont jamais réduits à
« vert / rouge ».

Le reporter Playwright n'émet rien sur le réseau : il écrit un NDJSON local que le
worker authentifié ingère (``TestIngestRequest``). Les champs de ce flux d'ingestion
sont donc traités comme non fiables : tout est borné et les chemins de pièces jointes
restent relatifs au dossier de rapport.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .limits import CapturedStr, Int32, Int64
from .limits import DatabaseModel as BaseModel
from .operations import ArtifactSummary

TestStatus = Literal["passed", "failed", "timedOut", "skipped", "interrupted"]
TestOutcome = Literal["expected", "unexpected", "flaky", "skipped"]
TestRunStatus = Literal["running", "completed", "failed", "interrupted", "timed_out"]

TEST_ERROR_MAX_CHARS = 8000
"""Borne du message et de l'extrait d'erreur conservés par cas de test."""

TEST_STEPS_MAX = 200
"""Nombre maximal d'étapes conservées pour un cas de test."""

TEST_ANNOTATIONS_MAX = 50
TEST_ATTACHMENTS_MAX = 50
TEST_SUITE_DEPTH_MAX = 20
REPORTER_EVENTS_MAX = 5000
"""Nombre maximal d'événements de reporter ingérés en une requête."""


class TestStep(BaseModel):
    """Étape d'un cas de test (``test.step``, action, hook)."""

    __test__ = False  # objet de données : pytest ne doit pas le collecter

    title: str = Field(max_length=500)
    category: str = Field(default="", max_length=50)
    duration_ms: Int64 = Field(default=0, ge=0)
    error: bool = False


class TestTotals(BaseModel):
    """Compteurs par catégorie ; ``flaky`` et ``skipped`` restent visibles."""

    __test__ = False

    expected: int = Field(default=0, ge=0)
    unexpected: int = Field(default=0, ge=0)
    flaky: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    interrupted: int = Field(default=0, ge=0)
    timedOut: int = Field(default=0, ge=0)  # noqa: N815 — nom Playwright conservé


class TestCaseResult(BaseModel):
    """Résultat d'un cas de test, avec ses pièces jointes déjà téléversées."""

    __test__ = False

    id: str
    test_run_id: str
    suite_path: list[str] = Field(default_factory=list, max_length=TEST_SUITE_DEPTH_MAX)
    title: str = Field(max_length=500)
    test_id: str = Field(max_length=200)
    location: dict[str, Any] = Field(default_factory=dict)
    project_name: str = Field(default="", max_length=200)
    attempt: Int32 = Field(default=1, ge=1)
    expected_status: str = Field(default="passed", max_length=20)
    status: TestStatus
    outcome: TestOutcome
    duration_ms: Int64 = Field(default=0, ge=0)
    error_message: CapturedStr = Field(default="", max_length=TEST_ERROR_MAX_CHARS)
    error_snippet: CapturedStr = Field(default="", max_length=TEST_ERROR_MAX_CHARS)
    steps: list[TestStep] = Field(default_factory=list, max_length=TEST_STEPS_MAX)
    annotations: list[dict[str, Any]] = Field(
        default_factory=list, max_length=TEST_ANNOTATIONS_MAX
    )
    attachments: list[ArtifactSummary] = Field(
        default_factory=list, max_length=TEST_ATTACHMENTS_MAX
    )


class TestRunSummary(BaseModel):
    """Exécution de tests rattachée à une tentative de mission."""

    __test__ = False

    id: str
    task_run_id: str
    project_id: str
    worker_id: str | None = None
    runner: str = Field(default="playwright", max_length=50)
    runner_version: str = Field(default="", max_length=50)
    status: TestRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: Int64 | None = Field(default=None, ge=0)
    totals: TestTotals = Field(default_factory=TestTotals)
    exit_code: Int64 | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    case_count: int = Field(default=0, ge=0)


class TestRunDetail(TestRunSummary):
    """Exécution complète : cas de test et rapport HTML éventuel."""

    __test__ = False

    cases: list[TestCaseResult] = Field(default_factory=list)
    report_artifact: ArtifactSummary | None = None


# --- Ingestion du reporter (NDJSON normalisé) ---------------------------------


def _relative_report_path(value: str) -> str:
    """Refuse tout chemin qui sortirait du dossier de rapport du reporter."""

    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError("le chemin de pièce jointe est obligatoire")
    if normalized.startswith("//"):
        raise ValueError("un chemin UNC n'est pas un chemin de rapport")
    if len(normalized) >= 2 and normalized[1] == ":":
        raise ValueError("un chemin absolu Windows n'est pas un chemin de rapport")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("le chemin de pièce jointe doit rester relatif au rapport")
    return normalized


class ReporterAttachment(BaseModel):
    """Pièce jointe annoncée par le reporter : un chemin local, jamais un contenu."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    path: str = Field(max_length=1000)
    sha256: str = Field(default="", max_length=64)
    size_bytes: Int64 = Field(default=0, ge=0)

    @field_validator("path")
    @classmethod
    def path_stays_in_the_report(cls, value: str) -> str:
        return _relative_report_path(value)


class ReporterEvent(BaseModel):
    """Ligne NDJSON normalisée produite par le reporter Playwright.

    Un seul modèle porte les quatre variantes ``kind`` : les champs absents d'une
    variante gardent leur défaut, et ``extra="forbid"`` empêche un reporter modifié
    d'injecter une clé inattendue dans la base.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["run_begin", "test_end", "run_end", "error"]

    # run_begin
    started_at: datetime | None = None
    runner_version: str = Field(default="", max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)

    # test_end
    test_id: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=500)
    suite_path: list[str] = Field(default_factory=list, max_length=TEST_SUITE_DEPTH_MAX)
    location: dict[str, Any] = Field(default_factory=dict)
    project_name: str = Field(default="", max_length=200)
    attempt: Int32 = Field(default=1, ge=1)
    expected_status: str = Field(default="passed", max_length=20)
    status: TestStatus | None = None
    outcome: TestOutcome | None = None
    duration_ms: Int64 = Field(default=0, ge=0)
    error_message: CapturedStr = Field(default="", max_length=TEST_ERROR_MAX_CHARS)
    error_snippet: CapturedStr = Field(default="", max_length=TEST_ERROR_MAX_CHARS)
    steps: list[TestStep] = Field(default_factory=list, max_length=TEST_STEPS_MAX)
    annotations: list[dict[str, Any]] = Field(
        default_factory=list, max_length=TEST_ANNOTATIONS_MAX
    )
    attachments: list[ReporterAttachment] = Field(
        default_factory=list, max_length=TEST_ATTACHMENTS_MAX
    )

    # run_end
    finished_at: datetime | None = None
    totals: TestTotals | None = None
    run_status: TestRunStatus | None = None
    exit_code: Int64 | None = None
    report_path: str | None = Field(default=None, max_length=1000)

    # error
    message: CapturedStr = Field(default="", max_length=2000)

    @field_validator("report_path")
    @classmethod
    def report_path_stays_in_the_report(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _relative_report_path(value)

    @model_validator(mode="after")
    def required_fields_of_the_variant(self) -> "ReporterEvent":
        if self.kind == "test_end":
            if not self.test_id:
                raise ValueError("un événement test_end exige test_id")
            if self.status is None or self.outcome is None:
                raise ValueError("un événement test_end exige status et outcome")
        if self.kind == "error" and not self.message:
            raise ValueError("un événement error exige message")
        return self


class TestIngestRequest(BaseModel):
    """Lot d'événements de reporter transmis par un worker authentifié."""

    __test__ = False

    task_run_id: str
    fencing_token: int = Field(ge=1)
    runner: Literal["playwright"]
    runner_version: str = Field(default="", max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    exit_code: Int64 | None = None
    events: list[ReporterEvent] = Field(max_length=REPORTER_EVENTS_MAX)
