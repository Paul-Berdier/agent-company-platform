"""Exécution d'une suite de tests web (Playwright) sur un runner authentifié.

La plateforme n'installe jamais Playwright et ne fournit jamais de credential au
processus de test. L'opérateur configure un argv absolu et une racine de projet ;
le worker lance ce programme dans la clôture d'arrêt du runner local
(``spawn_fenced_process`` / ``terminate_process_tree``), lui impose un fichier de
rapport NDJSON local (``ACP_REPORT_FILE``), puis ingère ce rapport avec sa propre
identité.

Règles non négociables appliquées ici :

* **jamais de shell, jamais de spawn direct** : le lancement passe par les deux
  points d'entrée publics du runner du Lot D ; un arrêt d'arbre non prouvé
  (``terminate_process_tree`` → ``False``) interdit tout succès ;
* **aucun faux succès** : un NDJSON absent ou vide est un échec explicite
  (« aucun résultat de test produit »), jamais une réussite ; les statuts
  ``passed``, ``failed``, ``timedOut``, ``skipped``, ``interrupted`` et le
  caractère ``flaky`` sont conservés distinctement ;
* **aucune pièce jointe hors périmètre** : seul un chemin dont la résolution
  canonique reste sous le répertoire de sortie de la tentative est téléversé ;
  les liens et les ``..`` sont refusés et signalés ;
* **aucune republication de secret** : tout ce que le rapport contient traverse
  ``redact_text`` / ``redact_data`` avec les valeurs d'environnement injectées
  par l'opérateur comme liste d'expurgation ;
* **aucune image dans une preuve de mission** : la ``MissionEvidence`` produite
  résume des compteurs, un code de sortie et l'identifiant du ``test_run``.

Un rapport partiellement corrompu ou une pièce jointe refusée ne perdent jamais
le reste du rapport : tout ce qui est lisible est ingéré, le refus est compté,
signalé dans la preuve — et interdit le verdict ``passed``, parce qu'une preuve
incomplète ne démontre pas une suite verte.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import httpx
from acp_contracts import WorkerCapability
from acp_contracts.redaction import redact_data, redact_text, redaction_values
from acp_contracts.testing import (
    REPORTER_EVENTS_MAX,
    ReporterEvent,
    TestIngestRequest,
)
from pydantic import ValidationError

from .local_runner import (
    FencedSpawnError,
    spawn_fenced_process,
    terminate_process_tree,
)


ENABLED_ENV = "ACP_WORKER_WEBTEST_ENABLED"
ARGV_ENV = "ACP_WORKER_WEBTEST_ARGV_JSON"
CWD_ENV = "ACP_WORKER_WEBTEST_CWD"
TIMEOUT_ENV = "ACP_WORKER_WEBTEST_TIMEOUT_SECONDS"
MAX_ARTIFACT_BYTES_ENV = "ACP_WORKER_WEBTEST_MAX_ARTIFACT_BYTES"
ENV_ALLOWLIST_ENV = "ACP_WORKER_WEBTEST_ENV_ALLOWLIST"
SIMULATION_ENV = "ACP_WORKER_SIMULATION"

DEFAULT_TIMEOUT_SECONDS = 900.0
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 7200.0
DEFAULT_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024
MAX_CONFIGURED_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024

REPORT_FILENAME = "report.ndjson"
STDOUT_FILENAME = "stdout.log"
STDERR_FILENAME = "stderr.log"
OUTPUT_NAMESPACE = "web-tests"

#: Taille maximale du NDJSON lu en mémoire ligne par ligne.
MAX_REPORT_BYTES = 32 * 1024 * 1024
#: Au-delà, une ligne est déclarée inexploitable sans être décodée.
MAX_REPORT_LINE_BYTES = 2 * 1024 * 1024
#: Grâce accordée avant l'arrêt forcé de l'arbre de processus.
TERMINATE_GRACE_SECONDS = 1.0
#: Pas d'interrogation de la sortie du processus (``returncode`` est publié dès
#: la sortie réelle, sans attendre la fermeture des descripteurs hérités).
POLL_INTERVAL_SECONDS = 0.05
#: Lecture par blocs pour l'empreinte des pièces jointes.
CHUNK_BYTES = 1024 * 1024

EMPTY_TOTALS: dict[str, int] = {
    "expected": 0,
    "unexpected": 0,
    "flaky": 0,
    "skipped": 0,
    "interrupted": 0,
    "timedOut": 0,
}

_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LEASE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

#: Variables posées par la plateforme : jamais allowlistables par l'opérateur.
RESERVED_ENVIRONMENT = {
    "ACP_REPORT_FILE",
    "ACP_WEBTEST_OUTPUT_DIR",
    "PLAYWRIGHT_HTML_OPEN",
}
#: Secrets de contrôle de la plateforme : jamais transmis au processus de test.
FORBIDDEN_PLATFORM_ENVIRONMENT = {
    "ACP_BOOTSTRAP_TOKEN",
    "ACP_EVENT_SERVICE_TOKEN",
    "ACP_GATEWAY_SERVICE_TOKEN",
    "ACP_WORKER_REGISTRATION_TOKEN",
    "HERMES_API_KEY",
    "HERMES_SERVICE_TOKEN",
}

#: Socle hérité : de quoi lancer Node et un navigateur déjà installé, rien de plus.
_WINDOWS_BASELINE = (
    "SYSTEMROOT",
    "WINDIR",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "PATH",
    "PATHEXT",
    "COMSPEC",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS",
)
_POSIX_BASELINE = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "XDG_CACHE_HOME",
)

#: Messages d'échec, en français, prêts pour une preuve de mission.
ERROR_MESSAGES = {
    "disabled": "capacité tests web non configurée",
    "output_directory_exists": "répertoire de sortie déjà utilisé par cette tentative",
    "output_directory_unavailable": "répertoire de sortie impossible à créer",
    "spawn_error": "programme de tests impossible à lancer",
    "job_assignment_failed": "clôture d'arrêt impossible à établir",
    "timeout": "délai de la suite de tests dépassé",
    "stopped": "arrêt demandé pendant la suite de tests",
    "process_tree_cleanup_failed": "arrêt complet de l'arbre de processus non prouvé",
    "no_test_results": "aucun résultat de test produit",
    "report_too_large": "rapport de tests trop volumineux pour être ingéré",
    "too_many_reporter_events": "rapport de tests au-delà de la limite d'ingestion",
    "ingest_payload_invalid": "rapport de tests non conforme au contrat d'ingestion",
    "ingest_failed": "ingestion du rapport refusée par l'API",
}


class WebTestConfigurationError(ValueError):
    """Configuration des tests web refusée avant toute exécution."""


class AttachmentRefused(ValueError):
    """Pièce jointe refusée : elle n'est ni téléversée ni transmise.

    ``reason`` vaut ``hors_perimetre``, ``lien``, ``absent`` ou ``invalide``.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class WebTestApiError(RuntimeError):
    """Appel API refusé ; le rapport local n'est jamais perdu pour autant."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebTestConfig:
    """Autorisation locale d'exécuter une suite de tests web.

    ``enabled`` seul ne suffit jamais : sans argv absolu ni racine de projet la
    capacité n'est pas annoncée et ``run_web_tests`` refuse tout lancement.
    """

    enabled: bool = False
    argv: tuple[str, ...] = ()
    cwd: Path | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES
    environment_allowlist: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise WebTestConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")
        object.__setattr__(self, "argv", _checked_argv(self.argv))
        object.__setattr__(self, "cwd", _checked_cwd(self.cwd))
        object.__setattr__(
            self, "timeout_seconds", _checked_timeout(self.timeout_seconds)
        )
        object.__setattr__(
            self, "max_artifact_bytes", _checked_artifact_bytes(self.max_artifact_bytes)
        )
        object.__setattr__(
            self,
            "environment_allowlist",
            _checked_allowlist(self.environment_allowlist),
        )
        if self.enabled and not self.configured:
            raise WebTestConfigurationError(
                f"{ENABLED_ENV}=1 exige {ARGV_ENV} et {CWD_ENV}"
            )

    @classmethod
    def disabled(cls) -> "WebTestConfig":
        return cls()

    @property
    def configured(self) -> bool:
        """Vrai quand le programme et sa racine de projet sont tous deux connus."""

        return bool(self.argv) and self.cwd is not None

    def status(self) -> str:
        """Libellé d'état pour ``doctor``."""

        return "enabled" if self.enabled and self.configured else "disabled"

    @classmethod
    def from_environ(
        cls, environ: Mapping[str, str] | None = None
    ) -> "WebTestConfig":
        """Construit la configuration depuis l'environnement, fermée par défaut.

        Une valeur présente mais illisible est toujours une erreur : le worker ne
        retombe jamais sur un binaire du ``PATH``, un shell ou une limite relâchée.
        """

        source = os.environ if environ is None else environ
        raw_enabled = source.get(ENABLED_ENV, "0").strip()
        if raw_enabled in {"", "0"}:
            enabled = False
        elif raw_enabled == "1":
            enabled = True
        else:
            raise WebTestConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")

        raw_argv = source.get(ARGV_ENV)
        raw_cwd = source.get(CWD_ENV)
        if enabled and (not raw_argv or not raw_cwd):
            raise WebTestConfigurationError(
                f"{ENABLED_ENV}=1 exige {ARGV_ENV} et {CWD_ENV}"
            )
        if not enabled and raw_argv is None and raw_cwd is None:
            return cls()

        argv: tuple[str, ...] = ()
        if raw_argv:
            try:
                decoded = json.loads(raw_argv)
            except json.JSONDecodeError as exc:
                raise WebTestConfigurationError(
                    f"{ARGV_ENV} doit contenir du JSON valide"
                ) from exc
            if (
                not isinstance(decoded, list)
                or not decoded
                or any(not isinstance(item, str) or not item for item in decoded)
            ):
                raise WebTestConfigurationError(
                    f"{ARGV_ENV} doit être un tableau JSON non vide de chaînes"
                )
            argv = tuple(decoded)

        cwd = Path(raw_cwd) if raw_cwd else None

        raw_timeout = (source.get(TIMEOUT_ENV) or "").strip()
        if raw_timeout:
            try:
                timeout_seconds = float(raw_timeout)
            except ValueError as exc:
                raise WebTestConfigurationError(
                    f"{TIMEOUT_ENV} doit être un nombre de secondes"
                ) from exc
        else:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        raw_bytes = (source.get(MAX_ARTIFACT_BYTES_ENV) or "").strip()
        if raw_bytes:
            try:
                max_artifact_bytes = int(raw_bytes)
            except ValueError as exc:
                raise WebTestConfigurationError(
                    f"{MAX_ARTIFACT_BYTES_ENV} doit être un entier d'octets"
                ) from exc
        else:
            max_artifact_bytes = DEFAULT_MAX_ARTIFACT_BYTES

        allowlist = tuple(
            item.strip()
            for item in (source.get(ENV_ALLOWLIST_ENV) or "").split(",")
            if item.strip()
        )
        return cls(
            enabled=enabled,
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_artifact_bytes=max_artifact_bytes,
            environment_allowlist=allowlist,
        )

    def doctor_report(self) -> dict[str, Any]:
        """Détail affiché par ``doctor`` lorsque la capacité est configurée.

        L'argv et la racine de projet sont des chemins choisis par l'opérateur sur
        sa propre machine : ils sont affichés pour qu'il vérifie ce qui sera lancé.
        Les **noms** allowlistés peuvent en revanche désigner un secret : seul leur
        nombre est publié, et aucune **valeur** d'environnement ne l'est jamais.
        """

        return {
            "web_tests_argv": list(self.argv),
            "web_tests_cwd": str(self.cwd),
            "web_tests_timeout_seconds": self.timeout_seconds,
            "web_tests_max_artifact_bytes": self.max_artifact_bytes,
            "web_tests_env_allowlist": len(self.environment_allowlist),
        }


def _checked_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if not argv:
        return ()
    if any(not isinstance(item, str) or not item for item in argv):
        raise WebTestConfigurationError(
            f"{ARGV_ENV} doit être un tableau JSON non vide de chaînes"
        )
    if any("\x00" in item for item in argv):
        raise WebTestConfigurationError(f"{ARGV_ENV} contient un octet nul")
    try:
        executable = Path(argv[0]).expanduser()
    except (OSError, ValueError, RuntimeError) as exc:
        raise WebTestConfigurationError(
            f"{ARGV_ENV} contient un chemin invalide"
        ) from exc
    if not executable.is_absolute():
        raise WebTestConfigurationError(
            f"{ARGV_ENV} doit commencer par un chemin absolu d'exécutable"
        )
    try:
        executable = executable.resolve(strict=True)
    except OSError as exc:
        raise WebTestConfigurationError(
            f"{ARGV_ENV} désigne un exécutable introuvable"
        ) from exc
    if not executable.is_file():
        raise WebTestConfigurationError(f"{ARGV_ENV} doit désigner un fichier")
    return (str(executable), *argv[1:])


def _checked_cwd(cwd: Path | str | None) -> Path | None:
    if cwd is None:
        return None
    try:
        candidate = Path(cwd).expanduser()
    except (OSError, ValueError, RuntimeError) as exc:
        raise WebTestConfigurationError(f"{CWD_ENV} contient un chemin invalide") from exc
    if not candidate.is_absolute():
        raise WebTestConfigurationError(f"{CWD_ENV} doit être un chemin absolu")
    try:
        resolved = candidate.resolve(strict=False)
        is_directory = resolved.is_dir()
    except OSError as exc:
        raise WebTestConfigurationError(f"{CWD_ENV} contient un chemin invalide") from exc
    if not is_directory:
        raise WebTestConfigurationError(
            f"{CWD_ENV} doit désigner un répertoire de projet existant"
        )
    return resolved


def _checked_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebTestConfigurationError(f"{TIMEOUT_ENV} doit être un nombre")
    parsed = float(value)
    if not math.isfinite(parsed) or not MIN_TIMEOUT_SECONDS <= parsed <= MAX_TIMEOUT_SECONDS:
        raise WebTestConfigurationError(
            f"{TIMEOUT_ENV} doit être compris entre {MIN_TIMEOUT_SECONDS:g} et "
            f"{MAX_TIMEOUT_SECONDS:g} secondes"
        )
    return parsed


def _checked_artifact_bytes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebTestConfigurationError(f"{MAX_ARTIFACT_BYTES_ENV} doit être un entier")
    if not 1 <= value <= MAX_CONFIGURED_ARTIFACT_BYTES:
        raise WebTestConfigurationError(
            f"{MAX_ARTIFACT_BYTES_ENV} doit être compris entre 1 et "
            f"{MAX_CONFIGURED_ARTIFACT_BYTES} octets"
        )
    return value


def _checked_allowlist(names: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for name in names:
        if not isinstance(name, str) or _ENVIRONMENT_NAME.fullmatch(name) is None:
            raise WebTestConfigurationError(
                f"{ENV_ALLOWLIST_ENV} contient une variable invalide: {name!r}"
            )
        if name.upper() in RESERVED_ENVIRONMENT:
            raise WebTestConfigurationError(
                f"{ENV_ALLOWLIST_ENV} contient une variable réservée: {name}"
            )
        if name.upper() in FORBIDDEN_PLATFORM_ENVIRONMENT:
            raise WebTestConfigurationError(
                f"secret de contrôle interdit dans l'environnement des tests web: {name}"
            )
        if name not in normalized:
            normalized.append(name)
    return tuple(normalized)


# ---------------------------------------------------------------------------
# Tentative et transport API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebTestLease:
    """Identité bornée de la tentative et racine d'écriture des sorties."""

    worker_id: str
    task_run_id: str
    attempt_number: int
    fencing_token: int
    project_id: str
    output_root: Path

    def __post_init__(self) -> None:
        for name in ("worker_id", "task_run_id", "project_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _LEASE_COMPONENT.fullmatch(value) is None:
                raise ValueError(
                    f"{name} doit être un identifiant ASCII borné sans séparateur"
                )
        if (
            not isinstance(self.attempt_number, int)
            or isinstance(self.attempt_number, bool)
            or self.attempt_number < 1
        ):
            raise ValueError("attempt_number doit être un entier positif")
        if (
            not isinstance(self.fencing_token, int)
            or isinstance(self.fencing_token, bool)
            or self.fencing_token < 1
        ):
            raise ValueError("fencing_token doit être un entier positif")
        object.__setattr__(self, "output_root", Path(self.output_root).expanduser())

    @property
    def output_directory(self) -> Path:
        """Répertoire neuf, propre à cette tentative et à ce runner."""

        return (
            self.output_root
            / OUTPUT_NAMESPACE
            / self.task_run_id
            / f"attempt-{self.attempt_number}"
        )


@dataclass(frozen=True)
class ArtifactUpload:
    """Fichier local prêt à être téléversé comme artefact de la tentative."""

    path: Path
    original_name: str
    content_type: str
    kind: str
    stream_kind: str
    sha256: str
    size_bytes: int


@runtime_checkable
class WebTestApi(Protocol):
    """Appels API nécessaires à l'ingestion d'une exécution de tests."""

    async def upload_artifact(
        self, upload: ArtifactUpload, lease: WebTestLease
    ) -> Mapping[str, Any]: ...

    async def ingest_test_run(
        self, body: Mapping[str, Any], lease: WebTestLease
    ) -> Mapping[str, Any]: ...


def _fencing_headers(fencing_token: int) -> dict[str, str]:
    """En-tête de clôture de tentative, identique à celui de la boucle worker.

    Dupliqué volontairement : importer ``main`` depuis ce module créerait un
    cycle d'import (``main`` route vers ``run_web_tests``).
    """

    if (
        not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
    ):
        raise WebTestApiError("fencing", "fencing_token positif requis")
    return {"X-Attempt-Fencing-Token": str(fencing_token)}


class WorkerTestApi:
    """Transport HTTP authentifié du worker pour les artefacts et l'ingestion.

    Le client fourni porte déjà ``Authorization`` et ``X-Worker-Id`` : ce module
    n'a jamais connaissance du jeton lui-même.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_url: str,
        worker_id: str,
        *,
        timeout: float = 60.0,
    ) -> None:
        self._client = client
        self._api_url = api_url.rstrip("/")
        self._worker_id = worker_id
        self._timeout = timeout

    async def upload_artifact(
        self, upload: ArtifactUpload, lease: WebTestLease
    ) -> Mapping[str, Any]:
        url = f"{self._api_url}/workers/{self._worker_id}/artifacts/content"
        try:
            with upload.path.open("rb") as handle:
                response = await self._client.post(
                    url,
                    headers=_fencing_headers(lease.fencing_token),
                    data={
                        "kind": upload.kind,
                        "stream_kind": upload.stream_kind,
                        "task_run_id": lease.task_run_id,
                        "project_id": lease.project_id,
                        "original_name": upload.original_name,
                    },
                    files={
                        "file": (
                            upload.original_name,
                            handle,
                            upload.content_type,
                        )
                    },
                    timeout=self._timeout,
                )
        except OSError as exc:
            raise WebTestApiError("io", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise WebTestApiError("transport", str(exc)) from exc
        return _decoded(response)

    async def ingest_test_run(
        self, body: Mapping[str, Any], lease: WebTestLease
    ) -> Mapping[str, Any]:
        url = f"{self._api_url}/workers/{self._worker_id}/test-runs"
        try:
            response = await self._client.post(
                url,
                headers=_fencing_headers(lease.fencing_token),
                json=dict(body),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise WebTestApiError("transport", str(exc)) from exc
        return _decoded(response)


def _decoded(response: httpx.Response) -> Mapping[str, Any]:
    if response.status_code >= 400:
        raise WebTestApiError(
            f"http_{response.status_code}",
            f"réponse API {response.status_code}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise WebTestApiError("protocol", "réponse API non JSON") from exc
    if not isinstance(payload, dict):
        raise WebTestApiError("protocol", "réponse API inattendue")
    return payload


# ---------------------------------------------------------------------------
# Capacité et routage
# ---------------------------------------------------------------------------


def mission_requests_web_tests(mission: Mapping[str, Any] | None) -> bool:
    """Vrai si la mission déclare une ressource ``kind == "web_test_suite"``."""

    if not isinstance(mission, Mapping):
        return False
    resources = mission.get("resources")
    if not isinstance(resources, list):
        return False
    return any(
        isinstance(resource, Mapping) and resource.get("kind") == "web_test_suite"
        for resource in resources
    )


def web_tests_available(
    config: WebTestConfig, capabilities: Sequence[str], *, simulation: bool
) -> bool:
    """Trois conditions cumulatives avant de router une mission vers Playwright.

    Capacité réellement annoncée à l'API, worker non simulé, configuration locale
    complète. Une seule manquante ⇒ comportement du Lot C inchangé.
    """

    return (
        not simulation
        and WorkerCapability.WEB_TESTS.value in set(capabilities)
        and config.enabled
        and config.configured
    )


# ---------------------------------------------------------------------------
# Environnement et pièces jointes
# ---------------------------------------------------------------------------


def web_test_environment(
    config: WebTestConfig,
    output_directory: Path,
    source: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Environnement du processus de test et sous-ensemble injecté par l'opérateur.

    Le second dictionnaire ne contient que les variables explicitement
    allowlistées : ce sont les seules valeurs que l'opérateur peut avoir choisies
    comme secrets, donc la liste d'expurgation appliquée à tout ce que le rapport
    republie. Le socle hérité (``PATH``, ``TEMP``, …) et les variables posées par
    la plateforme n'en font pas partie : les expurger rendrait tout diagnostic
    illisible sans protéger quoi que ce soit.
    """

    inherited = os.environ if source is None else source
    baseline = _WINDOWS_BASELINE if os.name == "nt" else _POSIX_BASELINE
    environment = {
        name: inherited[name]
        for name in baseline
        if name in inherited and name.upper() not in FORBIDDEN_PLATFORM_ENVIRONMENT
    }
    injected = {
        name: inherited[name]
        for name in config.environment_allowlist
        if name in inherited
        and name.upper() not in FORBIDDEN_PLATFORM_ENVIRONMENT
        and name.upper() not in RESERVED_ENVIRONMENT
    }
    environment.update(injected)
    environment.update(
        {
            "ACP_REPORT_FILE": str(output_directory / REPORT_FILENAME),
            "ACP_WEBTEST_OUTPUT_DIR": str(output_directory),
            "PLAYWRIGHT_HTML_OPEN": "never",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment, injected


def resolve_attachment(output_directory: Path, relative: str) -> Path:
    """Résout une pièce jointe et refuse tout ce qui sort du répertoire de sortie.

    Le contrat ``ReporterAttachment`` borne déjà la *forme* du chemin ; cette
    fonction borne le *système de fichiers* : chaque composant est vérifié contre
    les liens, puis la résolution canonique doit rester sous le répertoire de la
    tentative. Un lien est refusé même lorsqu'il pointe à l'intérieur : accepter
    une exception reviendrait à faire confiance à la cible du jour.
    """

    if not isinstance(relative, str) or not relative.strip():
        raise AttachmentRefused("invalide", "Pièce jointe refusée : chemin vide.")
    normalized = relative.replace("\\", "/").strip()
    if normalized.startswith("//"):
        raise AttachmentRefused(
            "hors_perimetre", "Pièce jointe refusée : chemin UNC."
        )
    if len(normalized) >= 2 and normalized[1] == ":":
        raise AttachmentRefused(
            "hors_perimetre", "Pièce jointe refusée : chemin absolu Windows."
        )
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise AttachmentRefused(
            "hors_perimetre",
            "Pièce jointe refusée : chemin sortant du répertoire de sortie.",
        )

    root = Path(output_directory).resolve(strict=False)
    current = root
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        current = current / part
        try:
            if current.is_symlink():
                raise AttachmentRefused(
                    "lien",
                    "Pièce jointe refusée : le chemin traverse un lien symbolique.",
                )
        except OSError as exc:
            raise AttachmentRefused(
                "absent", "Pièce jointe refusée : chemin illisible."
            ) from exc

    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AttachmentRefused(
            "hors_perimetre",
            "Pièce jointe refusée : la résolution canonique sort du répertoire.",
        ) from exc
    if os.path.normcase(os.path.realpath(resolved)) != os.path.normcase(str(resolved)):
        raise AttachmentRefused(
            "lien", "Pièce jointe refusée : lien détecté à la résolution finale."
        )
    if not resolved.is_file():
        raise AttachmentRefused(
            "absent", "Pièce jointe refusée : fichier absent ou non régulier."
        )
    return resolved


def _stream_kind(content_type: str, *, report: bool = False) -> str:
    if report:
        return "report"
    lowered = (content_type or "").split(";", 1)[0].strip().lower()
    if lowered.startswith("image/"):
        return "screenshot"
    if lowered.startswith("video/"):
        return "video"
    if lowered in {"application/zip", "application/x-zip-compressed"}:
        return "trace"
    return "file"


def _sha256_of(path: Path, *, limit: int) -> tuple[str, int]:
    """Empreinte et taille réelles, en s'arrêtant net au-delà de ``limit``.

    La lecture est bornée : un fichier qui grossit pendant qu'on le lit ne peut
    pas faire boucler le worker ni dépasser le budget d'artefacts.
    """

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while size <= limit:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


# ---------------------------------------------------------------------------
# Lecture du rapport NDJSON
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportIngestion:
    """Résultat de la lecture ligne à ligne du NDJSON du reporter."""

    events: tuple[ReporterEvent, ...] = ()
    corrupt_lines: int = 0
    error: str | None = None


def read_report(path: Path) -> ReportIngestion:
    """Lit le NDJSON ligne par ligne ; une ligne corrompue est comptée, pas fatale.

    Un fichier absent, vide ou sans aucune ligne exploitable est un échec
    explicite : le worker ne présente jamais « aucun test » comme une réussite.
    """

    try:
        if not path.is_file():
            return ReportIngestion(error="no_test_results")
        if path.stat().st_size > MAX_REPORT_BYTES:
            return ReportIngestion(error="report_too_large")
    except OSError:
        return ReportIngestion(error="no_test_results")

    events: list[ReporterEvent] = []
    corrupt = 0
    try:
        with path.open("rb") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped:
                    continue
                if len(stripped) > MAX_REPORT_LINE_BYTES:
                    corrupt += 1
                    continue
                try:
                    payload = json.loads(stripped.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    corrupt += 1
                    continue
                if not isinstance(payload, dict):
                    corrupt += 1
                    continue
                try:
                    events.append(ReporterEvent.model_validate(payload))
                except ValidationError:
                    corrupt += 1
                    continue
                if len(events) > REPORTER_EVENTS_MAX:
                    return ReportIngestion(
                        events=tuple(events[:REPORTER_EVENTS_MAX]),
                        corrupt_lines=corrupt,
                        error="too_many_reporter_events",
                    )
    except OSError:
        return ReportIngestion(
            events=tuple(events), corrupt_lines=corrupt, error="no_test_results"
        )
    if not events:
        return ReportIngestion(corrupt_lines=corrupt, error="no_test_results")
    return ReportIngestion(events=tuple(events), corrupt_lines=corrupt)


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebTestOutcome:
    """Verdict réel d'une exécution de tests web, jamais une image."""

    status: str
    output_directory: Path
    exit_code: int | None = None
    totals: dict[str, int] = field(default_factory=lambda: dict(EMPTY_TOTALS))
    case_count: int = 0
    test_run_id: str | None = None
    report_artifact_id: str | None = None
    error: str | None = None
    corrupt_lines: int = 0
    refused_attachments: tuple[dict[str, Any], ...] = ()
    duration_ms: int = 0
    runner_version: str = ""

    @property
    def succeeded(self) -> bool:
        """Succès technique : des assertions réelles, toutes attendues, et une preuve complète.

        ``flaky`` et ``skipped`` n'empêchent pas le succès (ils restent affichés).
        Un rapport partiellement illisible ou une pièce jointe refusée l'empêchent
        en revanche : une preuve incomplète ne démontre pas une suite verte.
        """

        return (
            self.error is None
            and self.status == "completed"
            and self.exit_code == 0
            and self.case_count > 0
            and self.corrupt_lines == 0
            and not self.refused_attachments
            and self.test_run_id is not None
            and self.totals.get("unexpected", 0) == 0
            and self.totals.get("interrupted", 0) == 0
            and self.totals.get("timedOut", 0) == 0
        )

    def summary(self) -> str:
        exit_label = "absent" if self.exit_code is None else str(self.exit_code)
        parts = [
            f"Tests web {self.status}; code de sortie {exit_label}; "
            f"{self.case_count} cas; "
            f"attendus {self.totals.get('expected', 0)}, "
            f"inattendus {self.totals.get('unexpected', 0)}, "
            f"flaky {self.totals.get('flaky', 0)}, "
            f"ignorés {self.totals.get('skipped', 0)}, "
            f"interrompus {self.totals.get('interrupted', 0)}, "
            f"expirés {self.totals.get('timedOut', 0)}; "
            f"test_run {self.test_run_id or 'absent'}."
        ]
        if self.corrupt_lines:
            parts.append(
                f" {self.corrupt_lines} ligne(s) de rapport inexploitable(s)."
            )
        if self.refused_attachments:
            parts.append(
                f" {len(self.refused_attachments)} pièce(s) jointe(s) refusée(s)."
            )
        if self.error is not None:
            parts.append(
                f" Échec : {ERROR_MESSAGES.get(self.error, self.error)}."
            )
        return "".join(parts)[:4000]

    def evidence(self) -> dict[str, Any]:
        """Preuve de mission ``web_tests`` : des compteurs, jamais un média."""

        return {
            "kind": "web_tests",
            "summary": self.summary(),
            "data": {
                "status": self.status,
                "exit_code": self.exit_code,
                "totals": dict(self.totals),
                "case_count": self.case_count,
                "test_run_id": self.test_run_id,
                "report_artifact_id": self.report_artifact_id,
                "runner": "playwright",
                "runner_version": self.runner_version,
                "corrupt_lines": self.corrupt_lines,
                "refused_attachments": [
                    dict(entry) for entry in self.refused_attachments
                ],
                "duration_ms": self.duration_ms,
                "error": self.error,
                # Jamais le chemin absolu de la machine dans un corps d'API.
                "output_directory": self.output_directory.name,
            },
            "exit_code": self.exit_code,
        }


# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------


def _effective_timeout(
    mission: Mapping[str, Any] | None,
    config: WebTestConfig,
    remaining_seconds: float | None = None,
) -> float:
    """La mission peut réduire le délai local, jamais l'étendre.

    ``remaining_seconds`` est ce qu'il reste du budget global de la tentative :
    la suite de tests n'en reçoit jamais davantage, exactement comme le
    programme local du Lot C.
    """

    timeout = float(config.timeout_seconds)
    if isinstance(mission, Mapping):
        duration = mission.get("duration_seconds")
        if isinstance(duration, int) and not isinstance(duration, bool) and duration > 0:
            timeout = min(timeout, float(duration))
    if (
        isinstance(remaining_seconds, (int, float))
        and not isinstance(remaining_seconds, bool)
        and math.isfinite(remaining_seconds)
    ):
        timeout = min(timeout, float(remaining_seconds))
    return max(MIN_TIMEOUT_SECONDS, timeout)


async def _await_exit(
    process: asyncio.subprocess.Process,
    timeout: float,
    stop_event: asyncio.Event | None,
) -> str:
    """Attend la sortie réelle du processus, le délai, ou l'arrêt du lease.

    ``returncode`` est publié dès la sortie du processus, sans attendre la
    fermeture des descripteurs hérités : un petit-fils qui survit ne transforme
    donc pas un succès en délai dépassé.
    """

    deadline = monotonic() + timeout
    while process.returncode is None:
        if stop_event is not None and stop_event.is_set():
            return "stopped"
        if monotonic() >= deadline:
            return "timeout"
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return "exited"


def _os_error_message(exc: OSError) -> str:
    """Diagnostic d'une erreur système sans le moindre chemin de fichier.

    ``str(exc)`` vaudrait ``[Errno 13] Permission denied: '<chemin absolu>'`` :
    republier cela dans ``MissionEvidence`` exposerait la racine d'exécution du
    worker et le nom de fichier choisi par le reporter. Seul le numéro d'erreur
    est utile au diagnostic et il ne porte aucune donnée non fiable.
    """

    errno = exc.errno
    if errno is None:
        return "Pièce jointe illisible : erreur système."
    return f"Pièce jointe illisible : erreur système (errno {errno})."


def _refusal(
    *,
    path: str,
    name: str,
    reason: str,
    message: str,
    size_bytes: int | None,
    redactions: Sequence[str] = (),
) -> dict[str, Any]:
    """Refus signalé dans la preuve de mission, donc expurgé comme le rapport.

    ``path`` et ``name`` viennent du reporter : ce sont des chaînes non fiables
    qui finiront dans un corps d'API lisible par les membres du projet.
    ``message`` est tout aussi hostile — un ``str(OSError)`` porte le nom de
    fichier annoncé par le reporter **et** le chemin absolu de la machine — donc
    il passe par la même expurgation. Les appelants n'y mettent de toute façon
    qu'un texte constant : la règle vaut pour ceux qui viendront après.
    """

    return {
        "path": redact_text(path, redactions),
        "name": redact_text(name, redactions),
        "reason": reason,
        "message": redact_text(message, redactions),
        "size_bytes": size_bytes,
    }


async def run_web_tests(
    mission: Mapping[str, Any] | None,
    config: WebTestConfig,
    *,
    api: WebTestApi,
    lease: WebTestLease,
    stop_event: asyncio.Event | None = None,
    remaining_seconds: float | None = None,
) -> WebTestOutcome:
    """Lance la suite configurée, ingère son rapport et retourne le verdict réel.

    Tout échec devient un ``WebTestOutcome`` dont ``succeeded`` vaut ``False`` et
    dont ``error`` porte un code explicite. La seule exception propagée est
    l'annulation de la tâche appelante, et seulement **après** l'arrêt prouvé de
    l'arbre de processus : une tentative annulée ne laisse jamais un navigateur
    derrière elle.
    """

    started = monotonic()

    def elapsed_ms() -> int:
        return max(0, round((monotonic() - started) * 1000))

    if not config.enabled or not config.configured:
        return WebTestOutcome(
            status="failed",
            output_directory=lease.output_root,
            error="disabled",
            duration_ms=elapsed_ms(),
        )

    output_directory = lease.output_directory
    try:
        # ``exist_ok=False`` : un répertoire déjà présent signale un rejeu
        # implicite de la même tentative, jamais écrasé en silence.
        output_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return WebTestOutcome(
            status="failed",
            output_directory=output_directory,
            error="output_directory_exists",
            duration_ms=elapsed_ms(),
        )
    except OSError:
        return WebTestOutcome(
            status="failed",
            output_directory=output_directory,
            error="output_directory_unavailable",
            duration_ms=elapsed_ms(),
        )

    environment, injected = web_test_environment(config, output_directory)
    redactions = redaction_values(injected)
    timeout_seconds = _effective_timeout(mission, config, remaining_seconds)

    status = "completed"
    error: str | None = None
    exit_code: int | None = None
    assert config.cwd is not None
    try:
        # stdout/stderr vont dans des fichiers du répertoire de sortie : aucun
        # tube hérité, donc aucun descendant capable de bloquer le drainage.
        with (
            (output_directory / STDOUT_FILENAME).open("wb") as out_handle,
            (output_directory / STDERR_FILENAME).open("wb") as err_handle,
        ):
            fenced = await spawn_fenced_process(
                config.argv,
                cwd=config.cwd,
                env=environment,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=out_handle.fileno(),
                stderr=err_handle.fileno(),
            )
    except FencedSpawnError as exc:
        return WebTestOutcome(
            status="failed",
            output_directory=output_directory,
            error=exc.reason,
            duration_ms=elapsed_ms(),
        )
    except OSError:
        return WebTestOutcome(
            status="failed",
            output_directory=output_directory,
            error="output_directory_unavailable",
            duration_ms=elapsed_ms(),
        )

    try:
        reason = await _await_exit(fenced.process, timeout_seconds, stop_event)
        if reason == "timeout":
            status, error = "timed_out", "timeout"
        elif reason == "stopped":
            status, error = "interrupted", "stopped"
    except asyncio.CancelledError:
        status, error = "interrupted", "stopped"
        raise
    finally:
        stopped = await terminate_process_tree(
            fenced.process, TERMINATE_GRACE_SECONDS if error else 0
        )
        exit_code = fenced.returncode
        fenced.close_fence()
        if not stopped and error is None:
            # Aucun faux succès : un arbre dont l'arrêt n'est pas prouvé peut
            # encore écrire dans le répertoire de sortie que l'on s'apprête à lire.
            status, error = "failed", "process_tree_cleanup_failed"

    ingestion = read_report(output_directory / REPORT_FILENAME)
    corrupt_lines = ingestion.corrupt_lines
    if ingestion.error is not None and error is None:
        error = ingestion.error

    run_begin = next(
        (event for event in ingestion.events if event.kind == "run_begin"), None
    )
    run_end = next(
        (event for event in ingestion.events if event.kind == "run_end"), None
    )
    cases = [event for event in ingestion.events if event.kind == "test_end"]
    # Le rapport est du contenu non fiable : tout ce qui en sort et sera
    # republié (preuve de mission comprise) est expurgé dès son extraction.
    runner_version = redact_text(
        run_begin.runner_version if run_begin is not None else "", redactions
    )
    totals = (
        dict(run_end.totals.model_dump())
        if run_end is not None and run_end.totals is not None
        else _derived_totals(cases)
    )

    if status == "completed":
        if not ingestion.events:
            status = "failed"
        elif run_end is None:
            # Sans ``run_end``, la suite n'est jamais allée au bout : le worker
            # ne peut pas prétendre qu'elle s'est terminée normalement.
            status = "interrupted"
        elif run_end.run_status in {"interrupted", "timed_out"}:
            status = run_end.run_status
        elif exit_code == 0 and run_end.run_status in {None, "completed"}:
            status = "completed"
        else:
            status = "failed"

    if not ingestion.events:
        # ``status`` porte déjà la cause réelle (``timed_out``, ``interrupted``
        # ou ``failed``) : rien d'exploitable n'a été produit, jamais un succès.
        return WebTestOutcome(
            status=status,
            output_directory=output_directory,
            exit_code=exit_code,
            totals=totals,
            error=error or "no_test_results",
            corrupt_lines=corrupt_lines,
            duration_ms=elapsed_ms(),
            runner_version=runner_version,
        )

    refused: list[dict[str, Any]] = []
    budget = config.max_artifact_bytes
    forwarded: list[ReporterEvent] = []
    for event in ingestion.events:
        if event.kind != "test_end":
            forwarded.append(event)
            continue
        kept = []
        for attachment in event.attachments:
            uploaded, budget, refusal = await _upload_attachment(
                api,
                lease,
                output_directory,
                attachment.path,
                name=attachment.name,
                content_type=attachment.content_type,
                budget=budget,
                kind="test_attachment",
                report=False,
                redactions=redactions,
            )
            if refusal is not None:
                refused.append(refusal)
                continue
            assert uploaded is not None
            kept.append(
                attachment.model_copy(
                    update={
                        "sha256": uploaded["sha256"],
                        "size_bytes": uploaded["size_bytes"],
                    }
                )
            )
        forwarded.append(event.model_copy(update={"attachments": kept}))

    report_artifact_id: str | None = None
    if run_end is not None and run_end.report_path:
        uploaded, budget, refusal = await _upload_attachment(
            api,
            lease,
            output_directory,
            run_end.report_path,
            name="report",
            content_type="text/html",
            budget=budget,
            kind="test_report",
            report=True,
            redactions=redactions,
        )
        if refusal is not None:
            refused.append(refusal)
        elif uploaded is not None:
            report_artifact_id = uploaded["artifact_id"]

    body: dict[str, Any] = {
        "task_run_id": lease.task_run_id,
        "fencing_token": lease.fencing_token,
        "runner": "playwright",
        "runner_version": runner_version,
        "config": redact_data(
            dict(run_begin.config) if run_begin is not None else {}, redactions
        ),
        # Le code de sortie réel du processus fait foi, pas celui que le rapport
        # s'attribue : c'est lui qui prouve ce que la suite a fait.
        "exit_code": exit_code,
        "events": [
            redact_data(event.model_dump(mode="json"), redactions)
            for event in forwarded
        ],
    }
    test_run_id: str | None = None
    try:
        request = TestIngestRequest.model_validate(body)
    except ValidationError:
        error = error or "ingest_payload_invalid"
    else:
        try:
            detail = await api.ingest_test_run(
                request.model_dump(mode="json"), lease
            )
        except WebTestApiError:
            error = error or "ingest_failed"
        else:
            candidate = detail.get("id")
            test_run_id = candidate if isinstance(candidate, str) else None
            if test_run_id is None:
                error = error or "ingest_failed"

    return WebTestOutcome(
        status=status,
        output_directory=output_directory,
        exit_code=exit_code,
        totals=totals,
        case_count=len(cases),
        test_run_id=test_run_id,
        report_artifact_id=report_artifact_id,
        error=error,
        corrupt_lines=corrupt_lines,
        refused_attachments=tuple(refused),
        duration_ms=elapsed_ms(),
        runner_version=runner_version,
    )


def _derived_totals(cases: Sequence[ReporterEvent]) -> dict[str, int]:
    """Compteurs reconstruits quand ``run_end`` manque (suite interrompue)."""

    totals = dict(EMPTY_TOTALS)
    for case in cases:
        if case.outcome in totals:
            totals[case.outcome] += 1
        if case.status == "timedOut":
            totals["timedOut"] += 1
        elif case.status == "interrupted":
            totals["interrupted"] += 1
    return totals


async def _upload_attachment(
    api: WebTestApi,
    lease: WebTestLease,
    output_directory: Path,
    relative: str,
    *,
    name: str,
    content_type: str,
    budget: int,
    kind: str,
    report: bool,
    redactions: Sequence[str],
) -> tuple[dict[str, Any] | None, int, dict[str, Any] | None]:
    """Téléverse une pièce jointe ou la refuse explicitement, sans jamais lever."""

    try:
        resolved = resolve_attachment(output_directory, relative)
    except AttachmentRefused as refusal:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason=refusal.reason,
                message=str(refusal),
                size_bytes=None,
                redactions=redactions,
            ),
        )
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="absent",
                # Jamais ``str(exc)`` : une OSError CPython porte le chemin
                # absolu de la machine, interdit dans un corps d'API (§ evidence).
                message=_os_error_message(exc),
                size_bytes=None,
                redactions=redactions,
            ),
        )
    if size > budget:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="quota",
                message=(
                    "Pièce jointe refusée : plafond "
                    f"{MAX_ARTIFACT_BYTES_ENV} atteint ({size} octets)."
                ),
                size_bytes=size,
                redactions=redactions,
            ),
        )
    try:
        digest, measured = _sha256_of(resolved, limit=budget)
    except OSError as exc:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="absent",
                message=_os_error_message(exc),
                size_bytes=size,
                redactions=redactions,
            ),
        )
    if measured > budget:
        # Le fichier a grossi entre la mesure et la lecture : refus, pas de dépassement.
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="quota",
                message="Pièce jointe refusée : taille modifiée pendant la lecture.",
                size_bytes=measured,
                redactions=redactions,
            ),
        )
    upload = ArtifactUpload(
        path=resolved,
        # Le nom d'origine est republié par l'API (champ ``original_name`` et
        # nom de fichier multipart) puis rendu dans les Livrables : il vient du
        # reporter, donc il s'expurge exactement comme les événements ingérés.
        # `_resolve_report_artifact_id` côté API rapproche ce nom du
        # ``report_path`` de ``run_end``, lui aussi expurgé : les deux côtés
        # restent cohérents.
        original_name=redact_text(resolved.name, redactions),
        content_type=content_type or "application/octet-stream",
        kind=kind,
        stream_kind=_stream_kind(content_type, report=report),
        sha256=digest,
        size_bytes=measured,
    )
    try:
        summary = await api.upload_artifact(upload, lease)
    except WebTestApiError as exc:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="api",
                message=f"Téléversement refusé par l'API ({exc.reason}).",
                size_bytes=measured,
                redactions=redactions,
            ),
        )
    artifact_id = summary.get("id")
    if not isinstance(artifact_id, str) or not artifact_id:
        return (
            None,
            budget,
            _refusal(
                path=relative,
                name=name,
                reason="api",
                message="Téléversement sans identifiant d'artefact.",
                size_bytes=measured,
                redactions=redactions,
            ),
        )
    return (
        {"artifact_id": artifact_id, "sha256": digest, "size_bytes": measured},
        budget - measured,
        None,
    )
