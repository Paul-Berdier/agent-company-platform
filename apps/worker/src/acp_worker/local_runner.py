"""Backend de processus local, borné et piloté par le lease du worker.

Le programme exécuté est une configuration locale de l'opérateur. Une mission
ne peut fournir ni exécutable, ni arguments : elle est sérialisée dans un
fichier JSON placé dans un répertoire neuf propre à la tentative. Le chemin de
ce fichier est le seul argument ajouté à l'argv configuré.

Ce backend n'est pas une sandbox de sécurité complète. Il fournit néanmoins la
frontière minimale testable du worker : aucun shell, cwd dédié, environnement
allowlisté, temps et captures bornés, arrêt effectif et preuve structurée.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping, Sequence


EVIDENCE_SCHEMA = "acp.local-process.evidence.v1"
EVIDENCE_FILENAME = "evidence.json"
REQUEST_SCHEMA = "acp.local-process.request.v1"
RUNNER_ARGV_ENV = "ACP_WORKER_RUNNER_ARGV_JSON"
RUN_ROOT_ENV = "ACP_WORKER_RUN_ROOT"
RUN_TIMEOUT_ENV = "ACP_WORKER_RUN_TIMEOUT_SECONDS"
RUN_OUTPUT_LIMIT_ENV = "ACP_WORKER_RUN_MAX_OUTPUT_BYTES"
RUN_ENV_ALLOWLIST_ENV = "ACP_WORKER_RUN_ENV_ALLOWLIST"
RUN_TERMINATE_GRACE_ENV = "ACP_WORKER_RUN_TERMINATE_GRACE_SECONDS"

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_TERMINATE_GRACE_SECONDS = 1.0
OUTPUT_DRAIN_GRACE_SECONDS = 1.0
MAX_CONFIGURED_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 24 * 60 * 60

# ``subprocess`` n'expose pas ce drapeau de CreateProcess : sous Windows le
# processus est créé suspendu pour être affecté à son Job Object avant
# d'exécuter la moindre instruction du programme.
CREATE_SUSPENDED = 0x00000004
JOB_DRAIN_TIMEOUT_SECONDS = 5.0

_RUN_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_ENVIRONMENT = {
    "ACP_RUN_REQUEST_PATH",
    "ACP_RUN_DIRECTORY",
    "ACP_RUN_ID",
    "ACP_RUN_ATTEMPT_ID",
    "ACP_RUN_FENCING_TOKEN",
}
_FORBIDDEN_PLATFORM_ENVIRONMENT = {
    "ACP_BOOTSTRAP_TOKEN",
    "ACP_EVENT_SERVICE_TOKEN",
    "ACP_GATEWAY_SERVICE_TOKEN",
    "ACP_WORKER_REGISTRATION_TOKEN",
    "HERMES_API_KEY",
    "HERMES_SERVICE_TOKEN",
}
_TASK_COMMAND_FIELDS = {
    "argv",
    "command",
    "commands",
    "executable",
    "program",
    "runner_command",
    "shell",
}
_MISSION_FIELDS = {
    "id",
    "objective",
    "expected_outcome",
    "acceptance_criteria",
    "autonomy",
    "resources",
    "budget",
    "duration_seconds",
}


class RunnerConfigurationError(RuntimeError):
    """La politique locale est absente ou dangereuse."""


class RunnerRequestError(ValueError):
    """La mission reçue n'est pas une enveloppe exécutable sûre."""


@dataclass(frozen=True)
class LocalRunnerConfig:
    """Configuration locale immuable d'un unique programme autorisé."""

    argv: tuple[str, ...]
    run_root: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    environment_allowlist: tuple[str, ...] = ()
    terminate_grace_seconds: float = DEFAULT_TERMINATE_GRACE_SECONDS

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise RunnerConfigurationError(
                "l'argv du runner doit être une liste non vide de chaînes"
            )
        if any("\x00" in item for item in self.argv):
            raise RunnerConfigurationError("l'argv du runner contient un octet nul")

        executable = Path(self.argv[0]).expanduser()
        if not executable.is_absolute():
            raise RunnerConfigurationError("l'exécutable du runner doit être un chemin absolu")
        try:
            executable = executable.resolve(strict=True)
        except OSError as exc:
            raise RunnerConfigurationError("l'exécutable du runner est introuvable") from exc
        if not executable.is_file():
            raise RunnerConfigurationError("l'exécutable du runner doit être un fichier")

        run_root = self.run_root.expanduser().resolve(strict=False)
        try:
            executable.relative_to(run_root)
        except ValueError:
            pass
        else:
            raise RunnerConfigurationError(
                "l'exécutable ne peut pas se trouver dans la racine inscriptible des runs"
            )

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise RunnerConfigurationError(
                f"le timeout doit être compris entre 0 et {MAX_TIMEOUT_SECONDS} secondes"
            )
        if (
            isinstance(self.max_output_bytes, bool)
            or not isinstance(self.max_output_bytes, int)
            or not 1 <= self.max_output_bytes <= MAX_CONFIGURED_OUTPUT_BYTES
        ):
            raise RunnerConfigurationError(
                f"la capture doit être comprise entre 1 et {MAX_CONFIGURED_OUTPUT_BYTES} octets"
            )
        if (
            isinstance(self.terminate_grace_seconds, bool)
            or not isinstance(self.terminate_grace_seconds, (int, float))
            or not math.isfinite(self.terminate_grace_seconds)
            or not 0 <= self.terminate_grace_seconds <= 10
        ):
            raise RunnerConfigurationError(
                "le délai d'arrêt doit être compris entre 0 et 10 secondes"
            )

        normalized_names: list[str] = []
        for name in self.environment_allowlist:
            if not isinstance(name, str) or not _ENVIRONMENT_NAME.fullmatch(name):
                raise RunnerConfigurationError(f"variable d'environnement invalide: {name!r}")
            if name.upper() in _RESERVED_ENVIRONMENT:
                raise RunnerConfigurationError(f"variable d'environnement réservée: {name}")
            if name.upper() in _FORBIDDEN_PLATFORM_ENVIRONMENT:
                raise RunnerConfigurationError(
                    f"secret de contrôle interdit dans l'environnement du runner: {name}"
                )
            if name not in normalized_names:
                normalized_names.append(name)

        object.__setattr__(self, "argv", (str(executable), *self.argv[1:]))
        object.__setattr__(self, "run_root", run_root)
        object.__setattr__(self, "environment_allowlist", tuple(normalized_names))

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> LocalRunnerConfig | None:
        """Charge une politique explicite, ou ``None`` si elle est entièrement absente.

        Une configuration partielle ou invalide lève toujours une erreur : le
        worker ne retombe jamais sur un binaire du ``PATH`` ni sur un shell.
        """

        source = os.environ if environment is None else environment
        raw_argv = source.get(RUNNER_ARGV_ENV)
        raw_root = source.get(RUN_ROOT_ENV)
        configured_values = (
            raw_argv,
            raw_root,
            source.get(RUN_TIMEOUT_ENV),
            source.get(RUN_OUTPUT_LIMIT_ENV),
            source.get(RUN_ENV_ALLOWLIST_ENV),
            source.get(RUN_TERMINATE_GRACE_ENV),
        )
        if not any(value is not None for value in configured_values):
            return None
        if not raw_argv or not raw_root:
            raise RunnerConfigurationError(
                f"{RUNNER_ARGV_ENV} et {RUN_ROOT_ENV} sont requis ensemble"
            )
        try:
            decoded = json.loads(raw_argv)
        except json.JSONDecodeError as exc:
            raise RunnerConfigurationError(
                f"{RUNNER_ARGV_ENV} doit contenir du JSON valide"
            ) from exc
        if (
            not isinstance(decoded, list)
            or not decoded
            or any(not isinstance(item, str) or not item for item in decoded)
        ):
            raise RunnerConfigurationError(
                f"{RUNNER_ARGV_ENV} doit être un tableau JSON non vide de chaînes"
            )

        allowlist = tuple(
            item.strip()
            for item in source.get(RUN_ENV_ALLOWLIST_ENV, "").split(",")
            if item.strip()
        )
        try:
            timeout_seconds = float(source.get(RUN_TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS))
            max_output_bytes = int(
                source.get(RUN_OUTPUT_LIMIT_ENV, DEFAULT_MAX_OUTPUT_BYTES)
            )
            terminate_grace_seconds = float(
                source.get(RUN_TERMINATE_GRACE_ENV, DEFAULT_TERMINATE_GRACE_SECONDS)
            )
        except (TypeError, ValueError) as exc:
            raise RunnerConfigurationError("limites numériques du runner invalides") from exc
        return cls(
            argv=tuple(decoded),
            run_root=Path(raw_root),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            environment_allowlist=allowlist,
            terminate_grace_seconds=terminate_grace_seconds,
        )


@dataclass(frozen=True)
class LocalRunRequest:
    run_id: str
    attempt_id: str
    attempt_number: int
    fencing_token: int
    payload: Mapping[str, Any]
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        _validate_component("run_id", self.run_id)
        _validate_component("attempt_id", self.attempt_id)
        if not isinstance(self.attempt_number, int) or isinstance(self.attempt_number, bool):
            raise RunnerRequestError("attempt_number doit être un entier")
        if self.attempt_number < 1:
            raise RunnerRequestError("attempt_number doit être positif")
        if not isinstance(self.fencing_token, int) or isinstance(self.fencing_token, bool):
            raise RunnerRequestError("fencing_token doit être un entier")
        if self.fencing_token < 1:
            raise RunnerRequestError("fencing_token doit être positif")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise RunnerRequestError("timeout de tentative invalide")


@dataclass(frozen=True)
class StreamCapture:
    text: str
    captured_bytes: int
    total_bytes: int
    truncated: bool
    sha256: str

    def as_evidence(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "captured_bytes": self.captured_bytes,
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class LocalRunnerResult:
    status: str
    exit_code: int | None
    termination_reason: str
    run_directory: Path
    request_sha256: str
    command_sha256: str
    executable: str
    timeout_seconds: float
    max_output_bytes: int
    started_at: str
    finished_at: str
    duration_ms: int
    stdout: StreamCapture
    stderr: StreamCapture

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded" and self.exit_code == 0

    def evidence(self, request: LocalRunRequest) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_SCHEMA,
            "kind": "local_process",
            "run_id": request.run_id,
            "attempt_id": request.attempt_id,
            "attempt_number": request.attempt_number,
            "fencing_token": request.fencing_token,
            "status": self.status,
            "termination_reason": self.termination_reason,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "request_sha256": self.request_sha256,
            "command_sha256": self.command_sha256,
            "executable": self.executable,
            "limits": {
                "timeout_seconds": self.timeout_seconds,
                "max_output_bytes_per_stream": self.max_output_bytes,
            },
            # Ne divulgue pas le chemin absolu de la machine dans l'API.
            "run_directory": self.run_directory.name,
            "stdout": self.stdout.as_evidence(),
            "stderr": self.stderr.as_evidence(),
        }


class _BoundedCapture:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._buffer = bytearray()
        self._total = 0
        self._digest = hashlib.sha256()

    async def read(self, stream: asyncio.StreamReader) -> StreamCapture:
        while True:
            chunk = await stream.read(64 * 1024)
            if not chunk:
                break
            self._total += len(chunk)
            self._digest.update(chunk)
            remaining = self._limit - len(self._buffer)
            if remaining > 0:
                self._buffer.extend(chunk[:remaining])
        return self.snapshot()

    def snapshot(self) -> StreamCapture:
        raw = bytes(self._buffer)
        return StreamCapture(
            text=raw.decode("utf-8", errors="replace"),
            captured_bytes=len(raw),
            total_bytes=self._total,
            truncated=self._total > len(raw),
            sha256=self._digest.hexdigest(),
        )

    def raw_snapshot(self) -> bytes:
        """Retourne la capture bornée pour une validation binaire interne."""

        return bytes(self._buffer)


def _validate_component(name: str, value: str) -> None:
    if not isinstance(value, str) or not _RUN_COMPONENT.fullmatch(value):
        raise RunnerRequestError(
            f"{name} doit être un identifiant ASCII borné sans séparateur de chemin"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunnerRequestError("la requête du runner doit être sérialisable en JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _empty_capture() -> StreamCapture:
    return StreamCapture(
        text="",
        captured_bytes=0,
        total_bytes=0,
        truncated=False,
        sha256=_sha256(b""),
    )


def _persist_evidence(result: LocalRunnerResult, request: LocalRunRequest) -> Path:
    """Écrit la preuve bornée avant tout envoi réseau du worker."""

    destination = result.run_directory / EVIDENCE_FILENAME
    temporary = result.run_directory / f".{EVIDENCE_FILENAME}.tmp"
    body = _canonical_json(result.evidence(request))
    try:
        with temporary.open("xb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _safe_run_directory(config: LocalRunnerConfig, request: LocalRunRequest) -> Path:
    config.run_root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(config.run_root, 0o700)
    except OSError:
        pass
    root = config.run_root.resolve(strict=True)
    candidate = (root / f"{request.run_id}--{request.attempt_id}").resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RunnerRequestError("le répertoire de tentative sort de la racine des runs") from exc
    try:
        candidate.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RunnerRequestError(
            "le répertoire de cette tentative existe déjà; rejeu implicite refusé"
        ) from exc
    return candidate


def _task_requests_command(meta: Any) -> bool:
    if not isinstance(meta, Mapping):
        return False
    containers: list[Mapping[Any, Any]] = [meta]
    for namespace in ("execution", "runner"):
        nested = meta.get(namespace)
        if isinstance(nested, Mapping):
            containers.append(nested)
    return any(
        isinstance(key, str) and key.casefold() in _TASK_COMMAND_FIELDS
        for container in containers
        for key in container
    )


def _non_empty_strings(value: Any, field: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RunnerRequestError(f"mission.{field} doit être une liste de chaînes non vides")
    if not allow_empty and not value:
        raise RunnerRequestError(f"mission.{field} ne peut pas être vide")
    return list(value)


def mission_snapshot_from_claim(claim: Mapping[str, Any]) -> dict[str, Any] | None:
    """Valide et copie les champs de mission allowlistés annoncés par l'API."""

    if "mission" not in claim:
        return None
    mission = claim.get("mission")
    if not isinstance(mission, Mapping):
        raise RunnerRequestError("claim mission invalide")
    if set(mission) not in (_MISSION_FIELDS, _MISSION_FIELDS | {"execution"}):
        raise RunnerRequestError("claim mission incomplet ou contenant des champs inconnus")

    task = claim.get("task")
    if not isinstance(task, Mapping) or mission.get("id") != task.get("id"):
        raise RunnerRequestError("mission.id doit correspondre à la tâche attribuée")
    for field in ("id", "objective", "expected_outcome"):
        value = mission.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RunnerRequestError(f"mission.{field} doit être une chaîne non vide")
    criteria = _non_empty_strings(
        mission.get("acceptance_criteria"), "acceptance_criteria", allow_empty=False
    )
    duration = mission.get("duration_seconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or not 1 <= duration <= 31_536_000
    ):
        raise RunnerRequestError("mission.duration_seconds doit être un entier positif")

    autonomy = mission.get("autonomy")
    autonomy_fields = {
        "mode",
        "allowed_actions",
        "forbidden_actions",
        "approval_required_actions",
    }
    if not isinstance(autonomy, Mapping) or set(autonomy) != autonomy_fields:
        raise RunnerRequestError("mission.autonomy invalide")
    if autonomy.get("mode") not in {"supervised", "bounded", "autonomous"}:
        raise RunnerRequestError("mission.autonomy.mode invalide")
    autonomy_copy = {
        "mode": autonomy["mode"],
        "allowed_actions": _non_empty_strings(
            autonomy.get("allowed_actions"), "autonomy.allowed_actions", allow_empty=True
        ),
        "forbidden_actions": _non_empty_strings(
            autonomy.get("forbidden_actions"),
            "autonomy.forbidden_actions",
            allow_empty=True,
        ),
        "approval_required_actions": _non_empty_strings(
            autonomy.get("approval_required_actions"),
            "autonomy.approval_required_actions",
            allow_empty=True,
        ),
    }

    resources = mission.get("resources")
    if not isinstance(resources, list):
        raise RunnerRequestError("mission.resources doit être une liste")
    resources_copy: list[dict[str, str]] = []
    resource_fields = {"kind", "identifier", "access", "description"}
    for item in resources:
        if not isinstance(item, Mapping) or set(item) != resource_fields:
            raise RunnerRequestError("ressource de mission invalide")
        if item.get("access") not in {"read", "write"}:
            raise RunnerRequestError("accès de ressource de mission invalide")
        if any(not isinstance(item.get(field), str) for field in resource_fields):
            raise RunnerRequestError("champs de ressource de mission invalides")
        if not item["kind"].strip() or not item["identifier"].strip():
            raise RunnerRequestError("ressource de mission sans type ou identifiant")
        resources_copy.append({field: item[field] for field in resource_fields})

    budget = mission.get("budget")
    budget_fields = {"max_cost", "currency", "max_tokens", "max_tool_calls"}
    if not isinstance(budget, Mapping) or set(budget) != budget_fields:
        raise RunnerRequestError("mission.budget invalide")
    currency = budget.get("currency")
    if not isinstance(currency, str) or len(currency) != 3:
        raise RunnerRequestError("mission.budget.currency invalide")
    max_cost = budget.get("max_cost")
    if max_cost is not None and (
        not isinstance(max_cost, (int, float))
        or isinstance(max_cost, bool)
        or not math.isfinite(max_cost)
        or max_cost < 0
    ):
        raise RunnerRequestError("mission.budget.max_cost invalide")
    for field in ("max_tokens", "max_tool_calls"):
        value = budget.get(field)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise RunnerRequestError(f"mission.budget.{field} invalide")
    if all(budget.get(field) is None for field in ("max_cost", "max_tokens", "max_tool_calls")):
        raise RunnerRequestError("mission.budget doit définir au moins une limite")
    budget_copy = {field: budget[field] for field in budget_fields}

    execution = mission.get("execution")
    if execution is not None:
        from acp_contracts import MissionExecution
        from pydantic import ValidationError

        try:
            execution = MissionExecution.model_validate(execution).model_dump(mode="json")
        except ValidationError as exc:
            raise RunnerRequestError("mission.execution invalide") from exc
        required = set(claim.get("required_capabilities", []))
        if "agent_team" not in required or required & {"codex_cli", "claude_code"} != set(execution["executors"]):
            raise RunnerRequestError("capacités d'équipe incohérentes avec les exécuteurs")
        if autonomy_copy["mode"] != "supervised" or any(autonomy_copy[key] for key in ("allowed_actions", "forbidden_actions", "approval_required_actions")):
            raise RunnerRequestError("une équipe exige la supervision sans listes d'actions")
        project_id = claim.get("session", {}).get("project_id")
        if len(resources_copy) != 1 or resources_copy[0]["kind"] != "project_workspace" or resources_copy[0]["identifier"] != project_id:
            raise RunnerRequestError("une équipe exige exactement le workspace attribué")
        if resources_copy[0]["access"] == "write" and "codex_cli" not in execution["executors"]:
            raise RunnerRequestError("seul Codex peut écrire dans un workspace d'équipe")

    return {
        "id": mission["id"],
        "objective": mission["objective"],
        "expected_outcome": mission["expected_outcome"],
        "acceptance_criteria": criteria,
        "autonomy": autonomy_copy,
        "resources": resources_copy,
        "budget": budget_copy,
        "duration_seconds": duration,
        **({"execution": execution} if "execution" in mission else {}),
    }


def validate_claim_for_local_runner(
    claim: Mapping[str, Any],
) -> dict[str, Any] | None:
    task = claim.get("task")
    run = claim.get("task_run")
    if not isinstance(task, Mapping) or not isinstance(run, Mapping):
        raise RunnerRequestError("claim sans tâche ou task run")
    meta = task.get("meta", {})
    if not isinstance(meta, Mapping):
        raise RunnerRequestError("task.meta doit être un objet")
    if _task_requests_command(meta):
        raise RunnerRequestError("une mission ne peut pas fournir de commande au runner")
    return mission_snapshot_from_claim(claim)


def validate_safe_local_policy(mission: Mapping[str, Any] | None) -> None:
    """Refuse ce que le backend local sans sandbox ne peut pas garantir.

    La seule enveloppe mission actuellement admise est supervisée, sans action
    accordée, interdite ou soumise à approbation, et avec des ressources en lecture
    seule. Une interdiction déclarée serait trompeuse sans sandbox capable de
    l'appliquer.
    Le programme fixe peut produire son résultat dans le dossier de tentative,
    mais aucune capacité d'écriture projet n'est promise.
    """

    if mission is None:
        return
    autonomy = mission["autonomy"]
    if autonomy["mode"] != "supervised":
        raise RunnerRequestError(
            "le runner local accepte uniquement les missions supervisées"
        )
    if autonomy["allowed_actions"]:
        raise RunnerRequestError(
            "le runner local ne peut garantir aucune allowed_action de mission"
        )
    if autonomy["forbidden_actions"]:
        raise RunnerRequestError(
            "le runner local ne peut garantir aucune forbidden_action de mission"
        )
    if autonomy["approval_required_actions"]:
        raise RunnerRequestError(
            "le runner local ne sait pas valider les actions soumises à approbation"
        )
    if any(resource["access"] == "write" for resource in mission["resources"]):
        raise RunnerRequestError(
            "le runner local non sandboxé refuse les ressources en écriture"
        )


def request_from_claim(claim: Mapping[str, Any], plan: Mapping[str, Any]) -> LocalRunRequest:
    """Construit l'entrée versionnée sans accepter de commande côté mission."""

    task = claim.get("task")
    run = claim.get("task_run")
    mission = validate_claim_for_local_runner(claim)
    validate_safe_local_policy(mission)
    assert isinstance(task, Mapping)
    assert isinstance(run, Mapping)

    run_id = run.get("id")
    attempt_id = claim.get("attempt_id")
    attempt_number = claim.get("attempt_number")
    fencing_token = claim.get("fencing_token")
    if attempt_id != run_id:
        raise RunnerRequestError("attempt_id doit correspondre au task run attribué")
    if not isinstance(plan, Mapping) or not isinstance(plan.get("plan_id"), str):
        raise RunnerRequestError("plan versionné requis pour l'exécution locale")

    session = claim.get("session")
    agent = claim.get("agent")
    project = claim.get("project")
    if not isinstance(session, Mapping):
        raise RunnerRequestError("claim sans session")
    if not isinstance(agent, Mapping):
        raise RunnerRequestError("claim sans agent")
    if not isinstance(project, Mapping):
        raise RunnerRequestError("claim sans projet")

    payload = {
        "schema": REQUEST_SCHEMA,
        "task": {
            "id": task.get("id"),
            "title": task.get("title"),
            "description": task.get("description", ""),
        },
        "task_run": {"id": run_id},
        "attempt": {
            "id": attempt_id,
            "number": attempt_number,
            "fencing_token": fencing_token,
        },
        "session": {
            field: session.get(field)
            for field in (
                "session_id",
                "organization_id",
                "workspace_id",
                "project_id",
                "team_id",
                "agent_instance_id",
                "provider_id",
            )
        },
        "agent": {field: agent.get(field) for field in ("id", "name", "role_id")},
        "project": {
            field: project.get(field) for field in ("id", "name", "project_type")
        },
        "mission": mission,
        "required_capabilities": claim.get("required_capabilities", []),
        "plan": dict(plan),
    }
    return LocalRunRequest(
        run_id=run_id,
        attempt_id=attempt_id,
        attempt_number=attempt_number,
        fencing_token=fencing_token,
        payload=payload,
        timeout_seconds=(mission["duration_seconds"] if mission is not None else None),
    )


def restricted_run_environment(
    config: LocalRunnerConfig,
    request: LocalRunRequest,
    request_path: Path,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construit un environnement neuf et sans secrets implicites."""

    inherited = os.environ if source is None else source
    baseline = (
        ("SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        if os.name == "nt"
        else ("LANG", "LC_ALL", "TMPDIR")
    )
    permitted = (*baseline, *config.environment_allowlist)
    environment = {
        name: inherited[name]
        for name in permitted
        if name in inherited and name.upper() not in _RESERVED_ENVIRONMENT
    }
    environment.update(
        {
            "ACP_RUN_REQUEST_PATH": str(request_path),
            "ACP_RUN_DIRECTORY": str(request_path.parent),
            "ACP_RUN_ID": request.run_id,
            "ACP_RUN_ATTEMPT_ID": request.attempt_id,
            "ACP_RUN_FENCING_TOKEN": str(request.fencing_token),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


class FencedSpawnError(OSError):
    """Le processus n'a pas pu être lancé dans sa clôture d'arrêt.

    ``reason`` vaut ``spawn_error`` (création impossible) ou
    ``job_assignment_failed`` (Windows : job non créé, affectation refusée ou
    reprise impossible ; le processus suspendu a été tué, rien n'a été exécuté).
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class _Win32Api:
    """Fonctions et structures kernel32 utilisées par la clôture Windows."""

    TH32CS_SNAPPROCESS = 0x00000002
    TH32CS_SNAPTHREAD = 0x00000004
    PROCESS_TERMINATE = 0x0001
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    THREAD_SUSPEND_RESUME = 0x0002
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS = 1
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    ERROR_NO_MORE_FILES = 18
    ERROR_INVALID_PARAMETER = 87
    RESUME_THREAD_FAILED = 0xFFFFFFFF

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.invalid_handle = ctypes.c_void_p(-1).value

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        self.ProcessEntry = ProcessEntry
        self.ThreadEntry = ThreadEntry
        self.ExtendedLimitInformation = ExtendedLimitInformation
        self.BasicAccountingInformation = BasicAccountingInformation

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.IsProcessInJob.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.BOOL),
        ]
        kernel32.IsProcessInJob.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        self.kernel32 = kernel32

    def last_error(self, function: str) -> OSError:
        code = self.ctypes.get_last_error()
        return OSError(code, f"{function} a échoué (erreur Windows {code})")


_WIN32_API: _Win32Api | None = None


def _win32() -> _Win32Api:
    global _WIN32_API
    if _WIN32_API is None:
        _WIN32_API = _Win32Api()
    return _WIN32_API


def _windows_create_job() -> int:
    """Crée un job anonyme qui tue ses processus à la fermeture du dernier handle.

    Aucun drapeau ``BREAKAWAY`` n'est accordé : tout descendant, y compris ceux
    créés par un lanceur intermédiaire (``.venv``, ``npx.cmd``, ``uvx``), reste
    dans le job.
    """

    api = _win32()
    api.ctypes.set_last_error(0)
    handle = api.kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise api.last_error("CreateJobObjectW")
    limits = api.ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = api.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    api.ctypes.set_last_error(0)
    if not api.kernel32.SetInformationJobObject(
        handle,
        api.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        api.ctypes.byref(limits),
        api.ctypes.sizeof(limits),
    ):
        error = api.last_error("SetInformationJobObject")
        api.kernel32.CloseHandle(handle)
        raise error
    return int(handle)


def _windows_assign_process_to_job(job_handle: int, process_id: int) -> None:
    """Affecte le processus (encore suspendu) au job et vérifie l'affectation."""

    api = _win32()
    api.ctypes.set_last_error(0)
    process_handle = api.kernel32.OpenProcess(
        api.PROCESS_SET_QUOTA
        | api.PROCESS_TERMINATE
        | api.PROCESS_QUERY_LIMITED_INFORMATION
        | api.SYNCHRONIZE,
        False,
        process_id,
    )
    if not process_handle:
        raise api.last_error("OpenProcess")
    try:
        api.ctypes.set_last_error(0)
        if not api.kernel32.AssignProcessToJobObject(job_handle, process_handle):
            raise api.last_error("AssignProcessToJobObject")
        in_job = api.wintypes.BOOL(False)
        api.ctypes.set_last_error(0)
        if not api.kernel32.IsProcessInJob(
            process_handle, job_handle, api.ctypes.byref(in_job)
        ):
            raise api.last_error("IsProcessInJob")
        if not in_job.value:
            raise OSError("le processus n'appartient pas au job après affectation")
    finally:
        api.kernel32.CloseHandle(process_handle)


def _windows_resume_process(process_id: int) -> None:
    """Reprend les threads d'un processus créé avec ``CREATE_SUSPENDED``."""

    api = _win32()
    api.ctypes.set_last_error(0)
    snapshot = api.kernel32.CreateToolhelp32Snapshot(api.TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == api.invalid_handle:
        raise api.last_error("CreateToolhelp32Snapshot")
    resumed = 0
    try:
        entry = api.ThreadEntry()
        entry.dwSize = api.ctypes.sizeof(entry)
        api.ctypes.set_last_error(0)
        present = api.kernel32.Thread32First(snapshot, api.ctypes.byref(entry))
        if not present:
            raise api.last_error("Thread32First")
        while present:
            if int(entry.th32OwnerProcessID) == process_id:
                api.ctypes.set_last_error(0)
                thread = api.kernel32.OpenThread(
                    api.THREAD_SUSPEND_RESUME, False, int(entry.th32ThreadID)
                )
                if not thread:
                    raise api.last_error("OpenThread")
                try:
                    api.ctypes.set_last_error(0)
                    previous = api.kernel32.ResumeThread(thread)
                finally:
                    api.kernel32.CloseHandle(thread)
                if previous == api.RESUME_THREAD_FAILED:
                    raise api.last_error("ResumeThread")
                resumed += 1
            api.ctypes.set_last_error(0)
            present = api.kernel32.Thread32Next(snapshot, api.ctypes.byref(entry))
        if api.ctypes.get_last_error() not in {0, api.ERROR_NO_MORE_FILES}:
            raise api.last_error("Thread32Next")
    finally:
        api.kernel32.CloseHandle(snapshot)
    if resumed == 0:
        raise OSError("aucun thread initial à reprendre pour le processus suspendu")


def _windows_job_active_processes(job_handle: int) -> int:
    api = _win32()
    accounting = api.BasicAccountingInformation()
    api.ctypes.set_last_error(0)
    if not api.kernel32.QueryInformationJobObject(
        job_handle,
        api.JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS,
        api.ctypes.byref(accounting),
        api.ctypes.sizeof(accounting),
        None,
    ):
        raise api.last_error("QueryInformationJobObject")
    return int(accounting.ActiveProcesses)


def _windows_terminate_job(job_handle: int) -> bool:
    api = _win32()
    api.ctypes.set_last_error(0)
    return bool(api.kernel32.TerminateJobObject(job_handle, 1))


class _WindowsJobObject:
    """Handle d'un Job Object vivant pendant toute l'exécution fencée."""

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    @property
    def handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("job déjà fermé")
        return self._handle

    def terminate_and_drain(self, timeout_seconds: float) -> bool:
        """Termine le job puis attend, borné, que ``ActiveProcesses`` tombe à 0."""

        try:
            terminated = _windows_terminate_job(self.handle)
            deadline = monotonic() + timeout_seconds
            while True:
                active = _windows_job_active_processes(self.handle)
                if active == 0:
                    return True
                if not terminated or monotonic() >= deadline:
                    return False
                time.sleep(0.01)
        except (OSError, RuntimeError):
            return False

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            _win32().kernel32.CloseHandle(handle)


# Le job appartient au spawn, pas à l'appelant : ce registre permet à
# ``_terminate_process`` de le retrouver sans changer sa signature publique
# (``executors.py`` l'appelle encore avec deux arguments sur un processus sans job).
_FENCE_JOBS: "weakref.WeakKeyDictionary[asyncio.subprocess.Process, _WindowsJobObject]" = (
    weakref.WeakKeyDictionary()
)


def _register_fence_job(
    process: asyncio.subprocess.Process, job: _WindowsJobObject
) -> None:
    _FENCE_JOBS[process] = job


def _fence_job_for(
    process: asyncio.subprocess.Process,
) -> _WindowsJobObject | None:
    return _FENCE_JOBS.get(process)


def _forget_fence_job(process: asyncio.subprocess.Process) -> None:
    _FENCE_JOBS.pop(process, None)


async def _await_critical_section(work: Callable[[], bool]) -> bool:
    """Exécute ``work`` dans un thread sans jamais l'abandonner à une annulation.

    La destruction d'un arbre de processus est une section critique : si
    l'appelant est annulé pendant l'appel, le thread termine son travail et
    l'annulation n'est relancée qu'ensuite.
    """

    task = asyncio.create_task(asyncio.to_thread(work))
    cancellation_received = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancellation_received = True
            if task.done():
                result = task.result()
                break
    if cancellation_received:
        raise asyncio.CancelledError
    return result


@dataclass(eq=False)
class FencedProcess:
    """Processus lancé sans shell dans une clôture d'arrêt.

    POSIX : nouvelle session (``killpg``). Windows : nouveau groupe de processus
    et Job Object ``KILL_ON_JOB_CLOSE`` attaché avant la première instruction du
    programme. Le handle du job vit tant que l'appelant n'a pas appelé
    ``close_fence``.
    """

    process: asyncio.subprocess.Process
    job: _WindowsJobObject | None = None

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    @property
    def stdin(self) -> asyncio.StreamWriter | None:
        return self.process.stdin

    @property
    def stdout(self) -> asyncio.StreamReader | None:
        return self.process.stdout

    @property
    def stderr(self) -> asyncio.StreamReader | None:
        return self.process.stderr

    def close_fence(self) -> None:
        """Ferme le job (dernier filet : tue ce qui y resterait)."""

        job, self.job = self.job, None
        _forget_fence_job(self.process)
        if job is not None:
            job.close()


def _process_group_options() -> dict[str, Any]:
    """Options de création d'un groupe/session propre au processus lancé."""

    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _fenced_spawn_options() -> dict[str, Any]:
    """Options du spawn fencé : groupe propre, et suspension initiale sous Windows."""

    options = _process_group_options()
    if os.name == "nt":
        options["creationflags"] = int(options["creationflags"]) | CREATE_SUSPENDED
    return options


async def _discard_suspended_process(process: asyncio.subprocess.Process) -> None:
    """Tue un processus qui n'a jamais été repris et libère son transport."""

    try:
        process.kill()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(_wait_for_process_exit(process), timeout=5.0)
    except TimeoutError:
        pass
    _close_process_transport(process)


async def spawn_fenced_process(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    env: Mapping[str, str],
    stdin: int,
    stdout: int,
    stderr: int,
    limit: int | None = None,
) -> FencedProcess:
    """Lance ``argv`` sans shell dans sa clôture ; échoue fermé sinon.

    Sous Windows le processus est créé suspendu, affecté à un Job Object neuf
    puis repris : aucune instruction du programme ne s'exécute hors du job. Toute
    erreur de cette séquence tue le processus suspendu et lève
    ``FencedSpawnError('job_assignment_failed')``.
    """

    options: dict[str, Any] = dict(_fenced_spawn_options())
    if limit is not None:
        options["limit"] = limit
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=dict(env),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            **options,
        )
    except OSError as exc:
        raise FencedSpawnError("spawn_error", str(exc)) from exc
    if os.name != "nt":
        return FencedProcess(process=process)

    job: _WindowsJobObject | None = None
    try:
        job = _WindowsJobObject(_windows_create_job())
        _windows_assign_process_to_job(job.handle, process.pid)
        _windows_resume_process(process.pid)
    except OSError as exc:
        await _discard_suspended_process(process)
        if job is not None:
            job.close()
        raise FencedSpawnError("job_assignment_failed", str(exc)) from exc
    _register_fence_job(process, job)
    return FencedProcess(process=process, job=job)


async def _wait_for_process_exit(process: asyncio.subprocess.Process) -> int:
    """Attend la fin du processus sans attendre la fermeture de ses pipes.

    Les transports asyncio peuvent ne résoudre ``Process.wait`` qu'après la
    fermeture de tous les pipes hérités. Un petit-fils peut donc masquer la sortie
    réelle du parent et transformer à tort son succès en timeout. ``returncode``
    est publié dès que le processus est signalé ; le polling borné par la deadline
    externe permet alors de nettoyer l'arbre avant de drainer les flux.
    """

    while process.returncode is None:
        await asyncio.sleep(0.01)
    return process.returncode


async def _windows_force_terminate_tree(
    process_id: int, *, include_root: bool
) -> bool:
    """Termine l'arbre Windows identifié avant de faire disparaître sa racine.

    ``taskkill /T`` peut être indisponible sous un jeton Windows restreint. Le
    snapshot Toolhelp permet d'ouvrir les processus encore vivants avant toute
    terminaison, ce qui évite à la fois la perte de filiation et la réutilisation
    accidentelle d'un PID entre l'énumération et l'arrêt.
    """

    def terminate_tree() -> bool:
        import ctypes
        from ctypes import wintypes

        snapshot_flag = 0x00000002  # TH32CS_SNAPPROCESS
        process_terminate = 0x0001
        synchronize = 0x00100000
        wait_object_0 = 0x00000000
        wait_timeout = 0x00000102
        error_no_more_files = 18
        error_invalid_parameter = 87
        invalid_handle = ctypes.c_void_p(-1).value

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry),
        ]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry),
        ]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        known_family_ids = {process_id}

        def process_depths() -> tuple[bool, dict[int, int]]:
            snapshot = kernel32.CreateToolhelp32Snapshot(snapshot_flag, 0)
            if not snapshot or snapshot == invalid_handle:
                return False, {}
            parents: dict[int, int] = {}
            try:
                entry = ProcessEntry()
                entry.dwSize = ctypes.sizeof(entry)
                ctypes.set_last_error(0)
                present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
                if not present:
                    return False, {}
                while present:
                    parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                    ctypes.set_last_error(0)
                    present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
                if ctypes.get_last_error() not in {0, error_no_more_files}:
                    return False, {}
            finally:
                kernel32.CloseHandle(snapshot)

            depths = {candidate: 0 for candidate in known_family_ids}
            changed = True
            while changed:
                changed = False
                for candidate, parent in parents.items():
                    if candidate not in depths and parent in depths:
                        depths[candidate] = depths[parent] + 1
                        changed = True
            known_family_ids.update(depths)
            targets = {
                candidate: depth
                for candidate, depth in depths.items()
                if candidate in parents and (include_root or candidate != process_id)
            }
            return True, targets

        all_stopped = True
        converged = False
        pinned_handles: dict[int, Any] = {}
        # Les passes suivantes attrapent un descendant créé entre un snapshot et
        # l'arrêt de son parent. Les handles restent ouverts pour empêcher toute
        # réutilisation de PID pendant cette convergence bornée.
        try:
            for _ in range(4):
                snapshot_ok, depths = process_depths()
                if not snapshot_ok:
                    all_stopped = False
                    continue
                ordered_ids = sorted(
                    depths,
                    key=lambda candidate: depths[candidate],
                    reverse=True,
                )
                if not ordered_ids:
                    converged = True
                    break
                # Ouvrir tous les handles avant de tuer la racine épingle
                # l'identité des processus malgré leur éventuelle sortie.
                for candidate in ordered_ids:
                    if candidate in pinned_handles:
                        continue
                    ctypes.set_last_error(0)
                    handle = kernel32.OpenProcess(
                        process_terminate | synchronize,
                        False,
                        candidate,
                    )
                    if handle:
                        pinned_handles[candidate] = handle
                    elif ctypes.get_last_error() != error_invalid_parameter:
                        all_stopped = False
                handles = [
                    (candidate, pinned_handles[candidate])
                    for candidate in ordered_ids
                    if candidate in pinned_handles
                ]
                for _, handle in handles:
                    state = kernel32.WaitForSingleObject(handle, 0)
                    if state == wait_timeout:
                        if not kernel32.TerminateProcess(handle, 1):
                            # Une sortie concurrente reste un succès si le handle
                            # est devenu signalé entre les deux appels.
                            if kernel32.WaitForSingleObject(handle, 0) != wait_object_0:
                                all_stopped = False
                    elif state != wait_object_0:
                        all_stopped = False
                wait_deadline = monotonic() + 0.75
                for _, handle in handles:
                    remaining_ms = max(
                        0,
                        round((wait_deadline - monotonic()) * 1000),
                    )
                    state = kernel32.WaitForSingleObject(handle, remaining_ms)
                    if state != wait_object_0:
                        all_stopped = False
        finally:
            for handle in pinned_handles.values():
                kernel32.CloseHandle(handle)
        return all_stopped and converged

    kill_task = asyncio.create_task(asyncio.to_thread(terminate_tree))
    cancellation_received = False
    while True:
        try:
            result = await asyncio.shield(kill_task)
            break
        except asyncio.CancelledError:
            cancellation_received = True
            if kill_task.done():
                result = kill_task.result()
                break
    if cancellation_received:
        raise asyncio.CancelledError
    return result


async def _windows_taskkill_tree(process_id: int) -> bool:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    taskkill = (system_root / "System32" / "taskkill.exe").resolve(strict=False)
    if not taskkill.is_file():
        return False

    def kill_tree() -> bool:
        try:
            completed = subprocess.run(
                [str(taskkill), "/PID", str(process_id), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
                },
                timeout=5.0,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    # Un subprocess synchrone déporté ferme ses handles avant de rendre la main
    # et n'ajoute pas un second transport Proactor au cycle de nettoyage. La
    # destruction d'arbre est une section critique : si l'appelant est annulé,
    # ``shield`` laisse le thread finir et nous l'attendons avant de poursuivre.
    kill_task = asyncio.create_task(asyncio.to_thread(kill_tree))
    cancellation_received = False
    while True:
        try:
            result = await asyncio.shield(kill_task)
            break
        except asyncio.CancelledError:
            # Une seconde annulation peut arriver pendant le nettoyage. Ne jamais
            # abandonner le thread et ses handles : la boucle n'attend au plus que
            # le timeout interne de ``subprocess.run``.
            cancellation_received = True
            if kill_task.done():
                result = kill_task.result()
                break
    if cancellation_received:
        raise asyncio.CancelledError
    return result


def _close_process_transport(process: asyncio.subprocess.Process) -> None:
    """Ferme explicitement pipes et handles une fois le processus terminé.

    ``asyncio.subprocess.Process`` n'expose pas de méthode publique de fermeture.
    Sous Proactor, laisser le transport à son destructeur après une lecture de pipe
    annulée déclenche des erreurs non levables à la fermeture de la boucle.
    """

    transport = getattr(process, "_transport", None)
    close = getattr(transport, "close", None)
    if callable(close):
        try:
            close()
        except (OSError, RuntimeError, ValueError):
            # Le transport peut avoir été fermé par la notification de sortie
            # entre le contrôle précédent et cet ultime repli.
            pass


async def _terminate_process(
    process: asyncio.subprocess.Process, grace_seconds: float
) -> bool:
    """Arrête le groupe puis force tout l'arbre de la tentative.

    Sous Windows, la preuve d'arrêt vient du Job Object attaché au spawn : lui
    seul retrouve un descendant dont la filiation est rompue (lanceur ``.venv``,
    ``npx.cmd``, ``uvx``). La passe Toolhelp est conservée comme vérification
    indépendante ; l'arbre n'est déclaré arrêté que si le job est vide.
    """

    process_id = process.pid
    if os.name == "nt":
        job = _fence_job_for(process)
        if process.returncode is None and grace_seconds > 0:
            try:
                # CREATE_NEW_PROCESS_GROUP fait de ``pid`` l'identifiant du groupe.
                os.kill(process_id, signal.CTRL_BREAK_EVENT)
            except (OSError, ValueError):
                pass
            try:
                await asyncio.wait_for(
                    _wait_for_process_exit(process), timeout=grace_seconds
                )
            except TimeoutError:
                pass

        job_drained = True
        if job is not None:
            job_drained = await _await_critical_section(
                lambda: job.terminate_and_drain(JOB_DRAIN_TIMEOUT_SECONDS)
            )

        # L'énumération native retrouve les descendants même lorsque la racine
        # vient de sortir. Ne jamais rouvrir le PID racine dans ce cas : son handle
        # asyncio suffit à épingler son identité jusqu'à la fermeture du transport.
        if process.returncode is None:
            # L'outil système bénéficie encore de la filiation vivante ; la passe
            # native qui suit sert de repli et de vérification indépendante.
            await _windows_taskkill_tree(process_id)
        tree_stopped = await _windows_force_terminate_tree(
            process_id,
            include_root=process.returncode is None,
        )
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(_wait_for_process_exit(process), timeout=5.0)
            except TimeoutError:
                _close_process_transport(process)
        return process.returncode is not None and tree_stopped and job_drained

    try:
        os.killpg(process_id, signal.SIGTERM)
    except ProcessLookupError:
        return True
    if grace_seconds > 0:
        try:
            await asyncio.wait_for(
                _wait_for_process_exit(process), timeout=grace_seconds
            )
        except TimeoutError:
            pass
    try:
        # Le parent peut être sorti alors qu'un descendant ignore SIGTERM.
        os.killpg(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.returncode is None:
        try:
            await asyncio.wait_for(_wait_for_process_exit(process), timeout=5.0)
        except TimeoutError:
            _close_process_transport(process)
            return False
    return True


async def terminate_process_tree(
    process: asyncio.subprocess.Process, grace_seconds: float
) -> bool:
    """Arrête l'arbre d'un processus fencé et confirme qu'il ne reste rien.

    Point d'entrée public de la logique d'arrêt du runner, réutilisé par la
    sonde MCP stdio. Le comportement est strictement celui du runner :
    grâce éventuelle, Job Object sous Windows, ``killpg`` sous POSIX, puis
    vérification indépendante. Retourne ``False`` si l'arrêt complet n'a pas
    pu être prouvé.
    """

    return await _terminate_process(process, grace_seconds)


async def run_local_program(
    config: LocalRunnerConfig,
    request: LocalRunRequest,
    *,
    stop_event: asyncio.Event | None = None,
) -> LocalRunnerResult:
    """Exécute l'argv configuré et retourne toujours le verdict technique réel.

    Les erreurs de configuration/requête lèvent avant le spawn. Un échec de
    création de processus, un code non nul, un timeout ou un arrêt restent des
    résultats structurés, jamais des réussites.
    """

    request_body = _canonical_json(request.payload)
    run_directory = _safe_run_directory(config, request)
    request_path = run_directory / "request.json"
    with request_path.open("xb") as handle:
        handle.write(request_body)
    try:
        os.chmod(request_path, 0o600)
    except OSError:
        pass

    argv: Sequence[str] = (*config.argv, str(request_path))
    command_sha256 = _sha256(_canonical_json(list(config.argv)))
    request_sha256 = _sha256(request_body)
    started_at = _utc_now()
    started_clock = monotonic()
    timeout_seconds = min(
        config.timeout_seconds,
        request.timeout_seconds or config.timeout_seconds,
    )
    empty = _empty_capture()
    if stop_event is not None and stop_event.is_set():
        result = LocalRunnerResult(
            status="cancelled",
            exit_code=None,
            termination_reason="stop_requested",
            run_directory=run_directory,
            request_sha256=request_sha256,
            command_sha256=command_sha256,
            executable=Path(config.argv[0]).name,
            timeout_seconds=timeout_seconds,
            max_output_bytes=config.max_output_bytes,
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
            stdout=empty,
            stderr=empty,
        )
        _persist_evidence(result, request)
        return result
    try:
        fenced = await spawn_fenced_process(
            argv,
            cwd=run_directory,
            env=restricted_run_environment(config, request, request_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FencedSpawnError as exc:
        finished_at = _utc_now()
        result = LocalRunnerResult(
            status="spawn_failed",
            exit_code=None,
            termination_reason=exc.reason,
            run_directory=run_directory,
            request_sha256=request_sha256,
            command_sha256=command_sha256,
            executable=Path(config.argv[0]).name,
            timeout_seconds=timeout_seconds,
            max_output_bytes=config.max_output_bytes,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
            stdout=empty,
            stderr=empty,
        )
        _persist_evidence(result, request)
        return result

    process = fenced.process
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_capture = _BoundedCapture(config.max_output_bytes)
    stderr_capture = _BoundedCapture(config.max_output_bytes)
    stdout_task = asyncio.create_task(stdout_capture.read(process.stdout))
    stderr_task = asyncio.create_task(stderr_capture.read(process.stderr))
    wait_task = asyncio.create_task(_wait_for_process_exit(process))
    stop_task = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    termination_reason = "exit"
    status = "failed"
    process_tree_stopped = True
    try:
        waiters = {wait_task}
        if stop_task is not None:
            waiters.add(stop_task)
        done, _ = await asyncio.wait(
            waiters,
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if wait_task in done:
            status = "succeeded" if wait_task.result() == 0 else "failed"
            # A configured program must not turn a successful parent exit into
            # an untracked background workload. Terminate anything that still
            # belongs to the process group/tree before accepting the result.
            process_tree_stopped = await _terminate_process(process, 0)
        elif stop_task is not None and stop_task in done:
            termination_reason = "stop_requested"
            status = "cancelled"
            process_tree_stopped = await _terminate_process(
                process, config.terminate_grace_seconds
            )
        else:
            termination_reason = "timeout"
            status = "timed_out"
            process_tree_stopped = await _terminate_process(
                process, config.terminate_grace_seconds
            )
    except asyncio.CancelledError:
        termination_reason = "task_cancelled"
        status = "cancelled"
        process_tree_stopped = await _terminate_process(
            process, config.terminate_grace_seconds
        )
    finally:
        if process.returncode is None:
            process_tree_stopped = (
                await _terminate_process(process, config.terminate_grace_seconds)
                and process_tree_stopped
            )
        capture_tasks = {stdout_task, stderr_task}
        capture_cancelled = False
        try:
            _, pending_captures = await asyncio.wait(
                capture_tasks,
                timeout=OUTPUT_DRAIN_GRACE_SECONDS,
            )
        except asyncio.CancelledError:
            pending_captures = capture_tasks
            capture_cancelled = True
            termination_reason = "task_cancelled"
            status = "cancelled"
        capture_failed = any(
            task.done()
            and (task.cancelled() or task.exception() is not None)
            for task in capture_tasks
        )
        if pending_captures or capture_failed:
            # `asyncio.wait_for(gather(...))` attend l'annulation complète du read
            # Proactor et peut donc dépasser son timeout si un descendant a gardé
            # le pipe. Fermer d'abord les transports puis borner l'attente évite ce
            # deadlock de nettoyage.
            if not capture_cancelled and termination_reason == "exit":
                termination_reason = "output_stream_timeout"
                status = "timed_out"
            _close_process_transport(process)
            for task in pending_captures:
                task.cancel()
            if pending_captures:
                await asyncio.gather(*pending_captures, return_exceptions=True)
        for task in capture_tasks:
            if task.done() and not task.cancelled():
                try:
                    task.exception()
                except (OSError, RuntimeError, ValueError):
                    pass
        stdout = stdout_capture.snapshot()
        stderr = stderr_capture.snapshot()
        if stop_task is not None:
            stop_task.cancel()
        wait_task.cancel()
        await asyncio.gather(
            *(task for task in (stop_task, wait_task) if task is not None),
            return_exceptions=True,
        )
        if not process_tree_stopped:
            if status == "succeeded":
                status = "failed"
            if not termination_reason.endswith("_process_tree_cleanup_failed"):
                termination_reason = (
                    f"{termination_reason}_process_tree_cleanup_failed"
                )
        # Dernier filet : fermer le job tue ce qui aurait survécu à toutes les
        # passes précédentes. Le verdict a déjà été figé : la clôture ne
        # transforme jamais un nettoyage non confirmé en succès.
        fenced.close_fence()

    result = LocalRunnerResult(
        status=status,
        exit_code=process.returncode,
        termination_reason=termination_reason,
        run_directory=run_directory,
        request_sha256=request_sha256,
        command_sha256=command_sha256,
        executable=Path(config.argv[0]).name,
        timeout_seconds=timeout_seconds,
        max_output_bytes=config.max_output_bytes,
        started_at=started_at,
        finished_at=_utc_now(),
        duration_ms=max(0, round((monotonic() - started_clock) * 1000)),
        stdout=stdout,
        stderr=stderr,
    )
    _persist_evidence(result, request)
    return result
