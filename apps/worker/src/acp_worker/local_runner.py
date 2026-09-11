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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Sequence


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
MAX_CONFIGURED_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 24 * 60 * 60

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
    """Valide et copie l'enveloppe mission non secrète annoncée par l'API."""

    if "mission" not in claim:
        return None
    mission = claim.get("mission")
    if not isinstance(mission, Mapping):
        raise RunnerRequestError("claim mission invalide")
    if set(mission) != _MISSION_FIELDS:
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

    return {
        "id": mission["id"],
        "objective": mission["objective"],
        "expected_outcome": mission["expected_outcome"],
        "acceptance_criteria": criteria,
        "autonomy": autonomy_copy,
        "resources": resources_copy,
        "budget": budget_copy,
        "duration_seconds": duration,
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


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _windows_taskkill_tree(process_id: int) -> None:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    taskkill = (system_root / "System32" / "taskkill.exe").resolve(strict=False)
    if not taskkill.is_file():
        return
    try:
        killer = await asyncio.create_subprocess_exec(
            str(taskkill),
            "/PID",
            str(process_id),
            "/T",
            "/F",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                key: value
                for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
            },
        )
        try:
            await asyncio.wait_for(killer.wait(), timeout=5.0)
        except TimeoutError:
            killer.kill()
            await killer.wait()
    except OSError:
        return


async def _terminate_process(
    process: asyncio.subprocess.Process, grace_seconds: float
) -> None:
    """Arrête le groupe puis force tout l'arbre de la tentative."""

    process_id = process.pid
    if os.name == "nt":
        try:
            # CREATE_NEW_PROCESS_GROUP fait de ``pid`` l'identifiant du groupe.
            os.kill(process_id, signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            pass
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=grace_seconds)
            except TimeoutError:
                pass
        # ``taskkill /T`` est lancé comme argv absolu, sans cmd.exe ni shell.
        await _windows_taskkill_tree(process_id)
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
        return

    try:
        os.killpg(process_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    if grace_seconds > 0:
        try:
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        except TimeoutError:
            pass
    try:
        # Le parent peut être sorti alors qu'un descendant ignore SIGTERM.
        os.killpg(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.returncode is None:
        await process.wait()


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
    execution_deadline = started_clock + timeout_seconds
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
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=run_directory,
            env=restricted_run_environment(config, request, request_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_process_group_options(),
        )
    except OSError:
        finished_at = _utc_now()
        result = LocalRunnerResult(
            status="spawn_failed",
            exit_code=None,
            termination_reason="spawn_error",
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

    assert process.stdout is not None
    assert process.stderr is not None
    stdout_capture = _BoundedCapture(config.max_output_bytes)
    stderr_capture = _BoundedCapture(config.max_output_bytes)
    stdout_task = asyncio.create_task(stdout_capture.read(process.stdout))
    stderr_task = asyncio.create_task(stderr_capture.read(process.stderr))
    wait_task = asyncio.create_task(process.wait())
    stop_task = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    termination_reason = "exit"
    status = "failed"
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
            await _terminate_process(process, 0)
        elif stop_task is not None and stop_task in done:
            termination_reason = "stop_requested"
            status = "cancelled"
            await _terminate_process(process, config.terminate_grace_seconds)
        else:
            termination_reason = "timeout"
            status = "timed_out"
            await _terminate_process(process, config.terminate_grace_seconds)
    except asyncio.CancelledError:
        termination_reason = "task_cancelled"
        status = "cancelled"
        await _terminate_process(process, config.terminate_grace_seconds)
    finally:
        if stop_task is not None:
            stop_task.cancel()
        if process.returncode is None:
            await process.wait()
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=max(0.05, execution_deadline - monotonic()),
            )
        except TimeoutError:
            termination_reason = "output_stream_timeout"
            status = "timed_out"
            await _terminate_process(process, config.terminate_grace_seconds)
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            stdout = stdout_capture.snapshot()
            stderr = stderr_capture.snapshot()
        wait_task.cancel()

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
