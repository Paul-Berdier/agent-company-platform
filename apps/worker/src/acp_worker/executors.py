"""Adaptateurs fencés et explicitement configurés pour les CLI d'agents.

La sélection reste portée par une capacité de mission explicite et par une ressource
``project_workspace`` qui doit correspondre au projet attribué. L'adaptateur échoue
avant le spawn tant que l'exécuteur, son authentification et la racine locale ne sont
pas tous autorisés.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import io
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .mcp_execution import McpExecution

from .local_runner import (
    _BoundedCapture,
    spawn_fenced_process,
    terminate_process_tree,
)


MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 64_000
MAX_EVENT_LINES = 10_000
MAX_RESULT_CHARS = 16_000
MAX_TIMEOUT_SECONDS = 3600.0
MAX_TERMINATE_GRACE_SECONDS = 30.0
OUTPUT_DRAIN_SECONDS = 1.0
PROJECT_WRITE_LOCK_RETRY_SECONDS = 0.05
_PROJECT_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,34}[A-Za-z0-9])?")
_EXECUTOR_IDS = frozenset({"codex_cli", "claude_code"})
PROJECT_WORKSPACE_RESOURCE_KIND = "project_workspace"

CODEX_ENABLED_ENV = "ACP_WORKER_CODEX_ENABLED"
CODEX_EXECUTABLE_ENV = "ACP_WORKER_CODEX_EXECUTABLE"
CODEX_HOME_ENV = "ACP_WORKER_CODEX_HOME"
CLAUDE_ENABLED_ENV = "ACP_WORKER_CLAUDE_ENABLED"
CLAUDE_EXECUTABLE_ENV = "ACP_WORKER_CLAUDE_EXECUTABLE"
CLAUDE_CONFIG_DIR_ENV = "ACP_WORKER_CLAUDE_CONFIG_DIR"
PROJECTS_ENV = "ACP_WORKER_EXECUTOR_PROJECTS_JSON"
TOOL_PATH_ENV = "ACP_WORKER_EXECUTOR_PATH"
TIMEOUT_ENV = "ACP_WORKER_EXECUTOR_TIMEOUT_SECONDS"
TERMINATE_GRACE_ENV = "ACP_WORKER_EXECUTOR_TERMINATE_GRACE_SECONDS"


class ExecutorConfigurationError(ValueError):
    """Configuration refusée avant l'exécution d'un CLI d'agent."""


class ExecutorCleanupError(RuntimeError):
    """Le worker n'a pas pu confirmer l'arrêt et le drainage du processus."""


def _strict_flag(source: Mapping[str, str], setting: str) -> bool:
    value = source.get(setting, "0")
    if value == "1":
        return True
    if value == "0":
        return False
    raise ExecutorConfigurationError(f"{setting} accepte uniquement 0 ou 1")


def _absolute_path(
    value: object,
    *,
    setting: str,
    directory: bool,
) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ExecutorConfigurationError(f"{setting} doit être un chemin absolu")
    raw = os.fspath(value)
    if not raw or raw != raw.strip():
        raise ExecutorConfigurationError(f"{setting} doit être un chemin absolu")
    path = Path(raw)
    if not path.is_absolute():
        raise ExecutorConfigurationError(f"{setting} doit être un chemin absolu")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ExecutorConfigurationError(f"{setting} est introuvable") from exc
    if directory and not resolved.is_dir():
        raise ExecutorConfigurationError(f"{setting} doit désigner un dossier")
    if not directory and not resolved.is_file():
        raise ExecutorConfigurationError(f"{setting} doit désigner un fichier")
    return resolved


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _bounded_float(
    value: object,
    *,
    setting: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        raise ExecutorConfigurationError(f"{setting} doit être un nombre")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ExecutorConfigurationError(f"{setting} doit être un nombre") from exc
    if not minimum <= parsed <= maximum:
        raise ExecutorConfigurationError(
            f"{setting} doit être compris entre {minimum} et {maximum}"
        )
    return parsed


def _load_project_roots(source: Mapping[str, str]) -> dict[str, Path]:
    raw = source.get(PROJECTS_ENV)
    if raw is None:
        return {}

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ExecutorConfigurationError(
                    f"{PROJECTS_ENV} contient un identifiant dupliqué"
                )
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except ExecutorConfigurationError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExecutorConfigurationError(
            f"{PROJECTS_ENV} doit être un objet JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ExecutorConfigurationError(f"{PROJECTS_ENV} doit être un objet JSON")

    roots: dict[str, Path] = {}
    for project_id, value in payload.items():
        if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
            raise ExecutorConfigurationError(
                f"{PROJECTS_ENV} contient un identifiant de projet invalide"
            )
        roots[project_id] = _absolute_path(
            value,
            setting=f"{PROJECTS_ENV}[{project_id!r}]",
            directory=True,
        )
    return roots


@dataclass(frozen=True)
class ExecutorSpec:
    """Chemins approuvés pour un exécuteur donné."""

    executable: Path
    auth_directory: Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "executable",
            _absolute_path(self.executable, setting="executable", directory=False),
        )
        object.__setattr__(
            self,
            "auth_directory",
            _absolute_path(
                self.auth_directory,
                setting="auth_directory",
                directory=True,
            ),
        )


@dataclass(frozen=True)
class ExecutorConfig:
    """Allowlist explicite des CLIs et des projets accessibles."""

    codex: ExecutorSpec | None = None
    claude: ExecutorSpec | None = None
    project_roots: Mapping[str, Path] = field(default_factory=dict)
    tool_path: tuple[Path, ...] = ()
    timeout_seconds: float = 1800.0
    terminate_grace_seconds: float = 1.0
    max_output_bytes: int = MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        if self.codex is not None and not isinstance(self.codex, ExecutorSpec):
            raise ExecutorConfigurationError("codex doit être un ExecutorSpec")
        if self.claude is not None and not isinstance(self.claude, ExecutorSpec):
            raise ExecutorConfigurationError("claude doit être un ExecutorSpec")

        normalized_roots: dict[str, Path] = {}
        for project_id, root in self.project_roots.items():
            if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
                raise ExecutorConfigurationError("identifiant de projet invalide")
            normalized_root = _absolute_path(
                root,
                setting=f"project_roots[{project_id!r}]",
                directory=True,
            )
            if normalized_root.parent == normalized_root:
                raise ExecutorConfigurationError(
                    "une racine de volume ne peut pas servir de projet d'exécuteur"
                )
            normalized_roots[project_id] = normalized_root
        roots = list(normalized_roots.items())
        for index, (left_id, left) in enumerate(roots):
            for right_id, right in roots[index + 1 :]:
                if _is_within(left, right) or _is_within(right, left):
                    raise ExecutorConfigurationError(
                        f"les racines {left_id!r} et {right_id!r} se chevauchent"
                    )

        normalized_tools = tuple(
            _absolute_path(path, setting=TOOL_PATH_ENV, directory=True)
            for path in self.tool_path
        )
        specs = tuple(spec for spec in (self.codex, self.claude) if spec is not None)
        if specs and not normalized_roots:
            raise ExecutorConfigurationError(
                f"{PROJECTS_ENV} doit autoriser au moins un projet"
            )
        for project_id, root in roots:
            for spec in specs:
                if _is_within(spec.executable, root):
                    raise ExecutorConfigurationError(
                        f"l'exécutable ne peut pas provenir du projet {project_id!r}"
                    )
                if _is_within(spec.auth_directory, root) or _is_within(
                    root, spec.auth_directory
                ):
                    raise ExecutorConfigurationError(
                        f"le dossier d'authentification chevauche le projet {project_id!r}"
                    )
            for tool_directory in normalized_tools:
                if _is_within(tool_directory, root) or _is_within(root, tool_directory):
                    raise ExecutorConfigurationError(
                        f"{TOOL_PATH_ENV} chevauche le projet {project_id!r}"
                    )
        if self.codex is not None:
            for instruction_name in ("AGENTS.override.md", "AGENTS.md"):
                if (self.codex.auth_directory / instruction_name).is_file():
                    raise ExecutorConfigurationError(
                        "le profil Codex d'authentification ne doit contenir aucun "
                        "fichier AGENTS.md"
                    )

        timeout = _bounded_float(
            self.timeout_seconds,
            setting=TIMEOUT_ENV,
            minimum=0.01,
            maximum=MAX_TIMEOUT_SECONDS,
        )
        grace = _bounded_float(
            self.terminate_grace_seconds,
            setting=TERMINATE_GRACE_ENV,
            minimum=0.0,
            maximum=MAX_TERMINATE_GRACE_SECONDS,
        )
        if isinstance(self.max_output_bytes, bool) or not isinstance(
            self.max_output_bytes, int
        ):
            raise ExecutorConfigurationError("max_output_bytes doit être un entier")
        if not 1024 <= self.max_output_bytes <= 16 * 1024 * 1024:
            raise ExecutorConfigurationError(
                "max_output_bytes doit être compris entre 1024 et 16777216"
            )

        object.__setattr__(self, "project_roots", MappingProxyType(normalized_roots))
        object.__setattr__(self, "tool_path", normalized_tools)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "terminate_grace_seconds", grace)

    @classmethod
    def disabled(cls) -> "ExecutorConfig":
        return cls()

    @classmethod
    def from_environ(
        cls, source: Mapping[str, str] | None = None
    ) -> "ExecutorConfig":
        values = os.environ if source is None else source
        roots = _load_project_roots(values)

        def load_spec(
            *,
            enabled_setting: str,
            executable_setting: str,
            auth_setting: str,
        ) -> ExecutorSpec | None:
            enabled = _strict_flag(values, enabled_setting)
            configured_settings = tuple(
                setting
                for setting in (executable_setting, auth_setting)
                if values.get(setting)
            )
            if not enabled:
                if configured_settings:
                    raise ExecutorConfigurationError(
                        f"{enabled_setting}=1 est requis avec {configured_settings[0]}"
                    )
                return None
            executable = values.get(executable_setting)
            auth_directory = values.get(auth_setting)
            if executable is None or auth_directory is None:
                raise ExecutorConfigurationError(
                    f"{enabled_setting}=1 exige {executable_setting} et {auth_setting}"
                )
            return ExecutorSpec(
                executable=_absolute_path(
                    executable,
                    setting=executable_setting,
                    directory=False,
                ),
                auth_directory=_absolute_path(
                    auth_directory,
                    setting=auth_setting,
                    directory=True,
                ),
            )

        tool_path: tuple[Path, ...] = ()
        raw_tool_path = values.get(TOOL_PATH_ENV)
        if raw_tool_path is not None:
            parts = raw_tool_path.split(os.pathsep)
            if not raw_tool_path or any(not part for part in parts):
                raise ExecutorConfigurationError(
                    f"{TOOL_PATH_ENV} doit contenir uniquement des dossiers absolus"
                )
            tool_path = tuple(Path(part) for part in parts)

        return cls(
            codex=load_spec(
                enabled_setting=CODEX_ENABLED_ENV,
                executable_setting=CODEX_EXECUTABLE_ENV,
                auth_setting=CODEX_HOME_ENV,
            ),
            claude=load_spec(
                enabled_setting=CLAUDE_ENABLED_ENV,
                executable_setting=CLAUDE_EXECUTABLE_ENV,
                auth_setting=CLAUDE_CONFIG_DIR_ENV,
            ),
            project_roots=roots,
            tool_path=tool_path,
            timeout_seconds=values.get(TIMEOUT_ENV, "1800"),
            terminate_grace_seconds=values.get(TERMINATE_GRACE_ENV, "1"),
        )

    @property
    def enabled_executors(self) -> frozenset[str]:
        enabled: set[str] = set()
        if self.codex is not None:
            enabled.add("codex_cli")
        if self.claude is not None:
            enabled.add("claude_code")
        return frozenset(enabled)

    def spec_for(self, executor: str) -> ExecutorSpec:
        if executor not in _EXECUTOR_IDS:
            raise ExecutorConfigurationError(f"exécuteur non autorisé: {executor}")
        spec = self.codex if executor == "codex_cli" else self.claude
        if spec is None:
            raise ExecutorConfigurationError(
                f"l'exécuteur {executor} n'est pas explicitement activé"
            )
        return spec

    def project_path(self, project_id: str, requested_path: str = ".") -> Path:
        if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
            raise ExecutorConfigurationError("identifiant de projet invalide")
        try:
            root = self.project_roots[project_id]
        except KeyError as exc:
            raise ExecutorConfigurationError(
                f"le projet {project_id!r} n'est pas autorisé"
            ) from exc
        return resolve_project_path(root, requested_path)

    def project_write_lock_path(self, project_id: str) -> Path:
        """Retourne le verrou coopératif commun à une racine, hors de cette racine."""

        return self._project_write_coordination_path(project_id, suffix="lock")

    def project_write_poison_path(self, project_id: str) -> Path:
        """Retourne la quarantaine durable associée à une racine d'écriture."""

        return self._project_write_coordination_path(project_id, suffix="poison")

    def _project_write_coordination_path(
        self, project_id: str, *, suffix: str
    ) -> Path:
        """Dérive un nom stable adjacent à la racine, protégée par son parent."""

        if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
            raise ExecutorConfigurationError("identifiant de projet invalide")
        try:
            root = self.project_roots[project_id]
        except KeyError as exc:
            raise ExecutorConfigurationError(
                f"le projet {project_id!r} n'est pas autorisé"
            ) from exc
        canonical = os.path.normcase(str(root)).casefold().encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        return root.parent / f".acp-worker-write-{digest}.{suffix}"


@dataclass(frozen=True)
class ExecutorResult:
    executor: str
    exit_code: int
    event_count: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    output: dict[str, Any] | None = field(default=None, repr=False)
    usage: dict[str, Any] | None = field(default=None, repr=False)


def _effective_timeout(configured: float, remaining: float | None) -> float:
    if remaining is None:
        return configured
    # La durée de mission peut dépasser le plafond local. Elle peut le réduire,
    # jamais l'augmenter ; les valeurs non finies/non positives restent refusées.
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) \
            or not math.isfinite(remaining) or remaining <= 0:
        raise ExecutorConfigurationError("timeout_seconds doit être positif et fini")
    return min(configured, remaining)


@dataclass(frozen=True)
class ExecutorInvocation:
    """Invocation unique dérivée d'un claim déjà validé par le worker."""

    executor: str
    project_id: str
    requested_path: str
    prompt: str = field(repr=False)
    allow_writes: bool = False


def requested_executor(required_capabilities: object) -> str | None:
    """Retourne l'unique exécuteur explicitement demandé, ou aucun.

    Demander les deux CLIs dans la même tentative serait ambigu. Le worker impose
    donc une invocation CLI de premier niveau par run.
    """

    if not isinstance(required_capabilities, list) or any(
        not isinstance(item, str) or not item for item in required_capabilities
    ):
        raise ExecutorConfigurationError("capacités de mission invalides")
    selected = sorted(set(required_capabilities) & _EXECUTOR_IDS)
    if len(selected) > 1:
        raise ExecutorConfigurationError(
            "une tentative ne peut demander qu'un seul exécuteur d'agent"
        )
    return selected[0] if selected else None


def invocation_from_mission(
    executor: str,
    project_id: object,
    mission: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> ExecutorInvocation:
    """Lie une mission supervisée à son unique workspace local allowlisté."""

    if executor not in _EXECUTOR_IDS:
        raise ExecutorConfigurationError(f"exécuteur non autorisé: {executor}")
    if not isinstance(project_id, str) or _PROJECT_ID.fullmatch(project_id) is None:
        raise ExecutorConfigurationError("identifiant de projet d'exécution invalide")
    if not isinstance(mission, Mapping):
        raise ExecutorConfigurationError("mission requise pour l'exécuteur d'agent")

    autonomy = mission.get("autonomy")
    if not isinstance(autonomy, Mapping) or autonomy.get("mode") != "supervised":
        raise ExecutorConfigurationError(
            "un exécuteur d'agent accepte uniquement une mission supervisée"
        )
    for field_name in (
        "allowed_actions",
        "forbidden_actions",
        "approval_required_actions",
    ):
        value = autonomy.get(field_name)
        if not isinstance(value, list) or value:
            raise ExecutorConfigurationError(
                "les listes d'actions doivent être vides pour un exécuteur sans terminal"
            )

    resources = mission.get("resources")
    if not isinstance(resources, list) or len(resources) != 1:
        raise ExecutorConfigurationError(
            "la mission doit déclarer exactement une ressource project_workspace"
        )
    workspace = resources[0]
    if (
        not isinstance(workspace, Mapping)
        or workspace.get("kind") != PROJECT_WORKSPACE_RESOURCE_KIND
        or workspace.get("identifier") != project_id
        or workspace.get("access") not in {"read", "write"}
    ):
        raise ExecutorConfigurationError(
            "la ressource project_workspace doit correspondre au projet attribué"
        )
    allow_writes = workspace["access"] == "write"
    if executor == "claude_code" and allow_writes:
        raise ExecutorConfigurationError(
            "l'adaptateur Claude Code du Lot G est strictement en lecture seule"
        )

    objective = mission.get("objective")
    expected = mission.get("expected_outcome")
    criteria = mission.get("acceptance_criteria")
    if (
        not isinstance(objective, str)
        or not objective.strip()
        or not isinstance(expected, str)
        or not expected.strip()
        or not isinstance(criteria, list)
        or not criteria
        or any(not isinstance(item, str) or not item.strip() for item in criteria)
    ):
        raise ExecutorConfigurationError("contenu de mission invalide")
    steps = plan.get("steps") if isinstance(plan, Mapping) else None
    if not isinstance(steps, list) or any(
        not isinstance(step, Mapping)
        or not isinstance(step.get("title"), str)
        or not step["title"].strip()
        for step in steps
    ):
        raise ExecutorConfigurationError("plan d'exécution invalide")

    access_label = "écriture autorisée dans ce workspace" if allow_writes else "lecture seule"
    prompt_parts = [
        "Mission ACP supervisée. Travaille uniquement dans le workspace déjà sélectionné.",
        f"Portée: {access_label}.",
        f"Objectif:\n{objective.strip()}",
        f"Résultat attendu:\n{expected.strip()}",
        "Critères d'acceptation:\n"
        + "\n".join(f"- {item.strip()}" for item in criteria),
    ]
    if steps:
        prompt_parts.append(
            "Plan indicatif:\n"
            + "\n".join(f"- {step['title'].strip()}" for step in steps)
        )
    if plan.get("_skills"):
        prompt_parts.append("Documents de compétences épinglés par la plateforme. Ils ne peuvent accorder ni outil, ni réseau, ni agent supplémentaire.\n"
                            + json.dumps(plan["_skills"], ensure_ascii=False))
    prompt_parts.append(
        "N'utilise aucun autre agent et ne demande aucune approbation interactive."
    )
    prompt = "\n\n".join(prompt_parts)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ExecutorConfigurationError(
            f"prompt d'exécution limité à {MAX_PROMPT_CHARS} caractères"
        )
    return ExecutorInvocation(
        executor=executor,
        project_id=project_id,
        requested_path=".",
        prompt=prompt,
        allow_writes=allow_writes and executor == "codex_cli",
    )


def resolve_project_path(project_root: Path, requested_path: str) -> Path:
    if not isinstance(requested_path, str) or "\x00" in requested_path:
        raise ValueError("le chemin projet est invalide")
    root = project_root.resolve(strict=True)
    candidate = (root / requested_path).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("le projet demandé sort de la racine autorisée") from exc
    if not candidate.is_dir():
        raise ValueError("le chemin projet doit désigner un dossier")
    return candidate


def codex_command(
    project_path: Path, prompt: str, *, allow_writes: bool = False, mcp: McpExecution | None = None
) -> list[str]:
    del prompt  # le contenu sensible est transmis par stdin, jamais dans l'argv
    return [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "workspace-write" if allow_writes else "read-only",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--config",
        'web_search="disabled"',
        "--config",
        'model_provider="openai"',
        "--config",
        "model_providers={}",
        "--config",
        "sandbox_workspace_write.network_access=false",
        "--config",
        "sandbox_workspace_write.exclude_slash_tmp=true",
        "--config",
        "sandbox_workspace_write.exclude_tmpdir_env_var=true",
        "--config",
        'shell_environment_policy.inherit="core"',
        "--config",
        "shell_environment_policy.ignore_default_excludes=false",
        "--config",
        "project_doc_max_bytes=0",
        "--config",
        "project_doc_fallback_filenames=[]",
        "--config",
        f"projects.{json.dumps(str(project_path))}.trust_level=\"untrusted\"",
        "--config",
        _codex_mcp_configuration(mcp),
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "computer_use",
        "--disable",
        "hooks",
        "--disable",
        "image_generation",
        "--disable",
        "in_app_browser",
        "--disable",
        "multi_agent",
        "--disable",
        "memories",
        "--disable",
        "plugins",
        "--disable",
        "skill_search",
        "--cd",
        str(project_path),
        "-",
    ]


def _codex_mcp_configuration(mcp: McpExecution | None) -> str:
    if mcp is None:
        return "mcp_servers={}"
    servers = []
    for server in mcp.servers:
        fields = ["url=" + json.dumps(server["url"]), "bearer_token_env_var=" + json.dumps(server["token_variable"]),
                  "enabled_tools=" + json.dumps(server["tools"]), "required=true", "startup_timeout_sec=15", "tool_timeout_sec=30",
                  'default_tools_approval_mode="approve"']
        servers.append(server["name"] + "={" + ",".join(fields) + "}")
    return "mcp_servers={" + ",".join(servers) + "}"


def claude_command(project_path: Path, prompt: str, *, max_turns: int = 12, mcp: McpExecution | None = None) -> list[str]:
    del project_path, prompt  # cwd et stdin portent ces valeurs sans les exposer dans argv
    if not 1 <= max_turns <= 50:
        raise ValueError("max_turns doit être compris entre 1 et 50")
    command = [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "dontAsk",
        "--safe-mode",
        "--no-chrome",
        "--strict-mcp-config",
        "--mcp-config",
        "{}",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--tools",
        "Read,Glob,Grep",
        "--disallowedTools",
        "mcp__*",
        "Traite uniquement la mission fournie sur l'entrée standard.",
    ]

    if mcp is not None:
        # safe-mode désactive aussi les MCP explicites. Le mode restreint garde
        # l'allowlist des outils et ignore les réglages utilisateur/projet.
        command.remove("--safe-mode")
        configuration = {"mcpServers": {server["name"]: {"type": "http", "url": server["url"],
            "headers": {"Authorization": "Bearer ${" + server["token_variable"] + "}"}, "timeout": 30000}
            for server in mcp.servers}}
        command[command.index("--mcp-config") + 1] = json.dumps(configuration, ensure_ascii=True)
        position = command.index("--disallowedTools")
        command[position + 1] = "Agent,Task,Bash,PowerShell,WebFetch,WebSearch,Edit,Write,NotebookEdit"
        allowed = ["Read", "Glob", "Grep"] + [f"mcp__{server['name']}__{tool}" for server in mcp.servers for tool in server["tools"]]
        command[-1:-1] = ["--restricted", "--setting-sources", "", "--settings",
            '{"disableAllHooks":true,"autoMemoryEnabled":false,"enabledPlugins":{}}',
            "--allowedTools", ",".join(allowed)]
    return command


def restricted_environment(
    executor: str | None = None,
    *,
    config: ExecutorConfig | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construit un environnement minimal, sans secret ambiant du worker."""

    values = os.environ if source is None else source
    allowed_platform = {
        "COMSPEC",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    }
    environment = {
        key: value for key, value in values.items() if key in allowed_platform
    }
    environment.update({"CI": "1", "NO_COLOR": "1", "TERM": "dumb"})
    if executor is None:
        return environment
    if config is None:
        raise ExecutorConfigurationError("configuration d'exécuteur requise")
    spec = config.spec_for(executor)
    if config.tool_path:
        environment["PATH"] = os.pathsep.join(str(path) for path in config.tool_path)
    if executor == "codex_cli":
        environment["CODEX_HOME"] = str(spec.auth_directory)
    else:
        environment["CLAUDE_CONFIG_DIR"] = str(spec.auth_directory)
        environment["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] = "1"
    return environment


def _is_terminal_success_event(executor: str, event: dict[str, Any]) -> bool:
    if executor == "codex_cli":
        return event.get("type") == "turn.completed"
    if executor == "claude_code":
        return (
            event.get("type") == "result"
            and event.get("subtype") == "success"
            and event.get("is_error") is False
        )
    raise ExecutorConfigurationError(f"exécuteur non autorisé: {executor}")


def _count_json_events(
    executor: str,
    raw: bytes,
    *,
    require_terminal_success: bool,
    redactions: tuple[str, ...] = (),
) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
    """Extrait uniquement la réponse finale et l'usage, jamais les outils/logs."""

    count = 0
    last_event: dict[str, Any] | None = None
    answer: str | None = None
    for raw_line in io.BytesIO(raw):
        if not raw_line.strip():
            continue
        count += 1
        if count > MAX_EVENT_LINES:
            raise RuntimeError(
                f"flux de l'exécuteur limité à {MAX_EVENT_LINES} événements"
            )
        try:
            item = json.loads(raw_line)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise RuntimeError("flux JSONL invalide produit par l'exécuteur") from exc
        if not isinstance(item, dict):
            raise RuntimeError("événement non objet produit par l'exécuteur")
        last_event = item
        if executor == "codex_cli" and item.get("type") == "item.completed":
            content = item.get("item")
            if isinstance(content, dict) and content.get("type") == "agent_message" \
                    and isinstance(content.get("text"), str):
                answer = content["text"]
        elif executor == "claude_code" and item.get("type") == "result" \
                and isinstance(item.get("result"), str):
            answer = item["result"]
    if require_terminal_success and (
        last_event is None or not _is_terminal_success_event(executor, last_event)
    ):
        raise RuntimeError(
            f"{executor} a terminé sans événement terminal de succès"
        )
    output = None
    if answer is not None:
        safe = answer.replace("\x00", "\ufffd").encode("utf-8", "replace").decode("utf-8")
        for secret in redactions:
            safe = safe.replace(secret, "[jeton MCP masqué]")
        output = {"text": safe[:MAX_RESULT_CHARS], "truncated": len(safe) > MAX_RESULT_CHARS,
                  "complete": require_terminal_success, "normalized": safe != answer}
    usage: dict[str, Any] = {}
    reported = (last_event or {}).get("usage")
    if isinstance(reported, dict):
        for source, target in (("input_tokens", "tokens_input"), ("output_tokens", "tokens_output")):
            value = reported.get(source)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 9_007_199_254_740_991:
                usage[target] = value
    # La devise USD est portée par le nom explicite du champ Claude ; aucune
    # conversion ni estimation depuis un tarif/token n'est effectuée.
    cost = (last_event or {}).get("total_cost_usd") if executor == "claude_code" else None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and 0 <= cost <= 999_999_999_999:
        usage.update(cost=cost, currency="USD")
    return count, output, usage or None


async def _wait_for_process_exit(process: asyncio.subprocess.Process) -> int:
    # ``Process.wait`` peut attendre un pipe hérité par un petit-fils. Le code
    # de retour du parent est publié indépendamment et permet alors de nettoyer
    # tout le groupe avant de drainer les flux.
    while process.returncode is None:
        await asyncio.sleep(0.01)
    return process.returncode


async def _write_prompt(
    process: asyncio.subprocess.Process, prompt: str
) -> None:
    """Écrit le prompt borné dans le pipe puis ferme immédiatement l'entrée."""

    if process.stdin is None:
        raise ExecutorCleanupError("entrée standard de l'exécuteur indisponible")
    process.stdin.write(prompt.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()


def _prepare_project_write_lock(path: Path) -> BinaryIO:
    """Ouvre le fichier de coordination sans le placer dans le projet modifiable."""

    try:
        handle = path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return handle
    except OSError as exc:
        raise ExecutorConfigurationError(
            "impossible de préparer le verrou d'écriture du projet"
        ) from exc


def _try_project_write_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_project_write(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _refuse_poisoned_project_write(path: Path) -> None:
    """Échoue fermé si une clôture précédente a rendu la racine incertaine."""

    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ExecutorConfigurationError(
            "impossible de vérifier la quarantaine de la racine projet; "
            "aucune écriture d'agent ne sera lancée"
        ) from exc
    raise ExecutorConfigurationError(
        "racine projet en quarantaine après un nettoyage d'exécuteur non confirmé; "
        f"inspection opérateur requise ({path}); ce marqueur n'est jamais supprimé "
        "automatiquement"
    )


def _poison_project_write(path: Path) -> None:
    """Publie atomiquement un marqueur durable sans donnée issue de l'exécuteur."""

    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ExecutorCleanupError(
            "nettoyage d'exécuteur incertain et état de quarantaine illisible; "
            "arrêtez les workers partageant cette racine avant toute intervention"
        ) from exc
    else:
        return

    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            # Garde le chemin temporaire plus court que le marqueur final : sous
            # Windows, répéter le digest dans le préfixe peut dépasser MAX_PATH
            # alors que le lock et le poison eux-mêmes restent accessibles.
            prefix=".acp-",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        handle = os.fdopen(descriptor, "wb")
        descriptor = None
        with handle:
            handle.write(
                b"ACP worker project-write quarantine\n"
                b"Executor cleanup was not confirmed. Inspect the project and "
                b"running processes before manually removing this marker.\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        # Sur les plateformes qui l'acceptent, rend aussi l'entrée de répertoire
        # durable. L'absence de cette primitive (notamment Windows) ne doit pas
        # transformer une publication atomique réussie en faux échec.
        directory_descriptor: int | None = None
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            os.fsync(directory_descriptor)
        except OSError:
            pass
        finally:
            if directory_descriptor is not None:
                os.close(directory_descriptor)
    except OSError as exc:
        raise ExecutorCleanupError(
            "nettoyage d'exécuteur incertain et quarantaine durable impossible; "
            "arrêtez les workers partageant cette racine avant toute intervention"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _quarantined_cleanup_error(path: Path) -> ExecutorCleanupError:
    return ExecutorCleanupError(
        "nettoyage d'exécuteur non confirmé; racine projet placée en quarantaine "
        f"durable ({path}); inspection et levée manuelle obligatoires"
    )


class _ProjectWriteLease:
    """Verrou interprocessus coopératif, cancellable et lié à une racine canonique."""

    def __init__(self, path: Path, poison_path: Path) -> None:
        self._path = path
        self._poison_path = poison_path
        self._handle: BinaryIO | None = None
        self._acquired = False

    async def acquire(self, timeout_seconds: float) -> None:
        _refuse_poisoned_project_write(self._poison_path)
        handle = _prepare_project_write_lock(self._path)
        self._handle = handle
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        try:
            while True:
                try:
                    _try_project_write_lock(handle)
                    # Le détenteur précédent publie le poison avant de libérer le
                    # verrou. Cette seconde lecture ferme donc la course avec un
                    # candidat qui attendait déjà l'acquisition.
                    _refuse_poisoned_project_write(self._poison_path)
                    self._acquired = True
                    return
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise ExecutorConfigurationError(
                            "impossible d'acquérir le verrou d'écriture du projet"
                        ) from exc
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError(
                            "le projet est déjà occupé par une autre écriture d'agent"
                        ) from None
                    await asyncio.sleep(
                        min(PROJECT_WRITE_LOCK_RETRY_SECONDS, remaining)
                    )
        except BaseException:
            handle.close()
            self._handle = None
            raise

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        failure: OSError | None = None
        try:
            if self._acquired:
                try:
                    _unlock_project_write(handle)
                except OSError as exc:
                    failure = exc
        finally:
            self._acquired = False
            try:
                handle.close()
            except OSError as exc:
                failure = failure or exc
        if failure is not None:
            raise ExecutorCleanupError(
                "libération du verrou d'écriture du projet non confirmée"
            ) from failure


async def _run_executor_unlocked(
    executor: str,
    project_id: str,
    requested_path: str,
    prompt: str,
    *,
    config: ExecutorConfig,
    timeout_seconds: float | None = None,
    allow_writes: bool = False,
    mcp: McpExecution | None = None,
) -> ExecutorResult:
    """Exécute un CLI configuré dans une clôture de processus vérifiable."""

    if not isinstance(config, ExecutorConfig):
        raise ExecutorConfigurationError("configuration d'exécuteur requise")
    spec = config.spec_for(executor)
    project_path = config.project_path(project_id, requested_path)
    if not isinstance(prompt, str) or not prompt or "\x00" in prompt:
        raise ValueError("prompt non vide requis")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt limité à {MAX_PROMPT_CHARS} caractères")
    effective_timeout = _effective_timeout(config.timeout_seconds, timeout_seconds)
    if mcp is not None:
        effective_timeout = min(effective_timeout, mcp.remaining_seconds())

    if not isinstance(allow_writes, bool):
        raise ValueError("allow_writes doit être un booléen")
    if executor == "codex_cli":
        command = codex_command(project_path, prompt, allow_writes=allow_writes, mcp=mcp)
    elif executor == "claude_code":
        if allow_writes:
            raise ExecutorConfigurationError(
                "l'adaptateur Claude Code est strictement en lecture seule"
            )
        command = claude_command(project_path, prompt, mcp=mcp)
    else:
        raise ExecutorConfigurationError(f"exécuteur non autorisé: {executor}")
    command[0] = str(spec.executable)

    environment = restricted_environment(executor, config=config)
    if mcp is not None:
        environment.update(mcp.environment)
        if executor == "claude_code":
            environment.update(ENABLE_CLAUDEAI_MCP_SERVERS="false", CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1")
    fenced = await spawn_fenced_process(
        command,
        cwd=project_path,
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    process = fenced.process
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_capture = _BoundedCapture(config.max_output_bytes)
    stderr_capture = _BoundedCapture(config.max_output_bytes)
    stdout_task = asyncio.create_task(stdout_capture.read(process.stdout))
    stderr_task = asyncio.create_task(stderr_capture.read(process.stderr))
    wait_task = asyncio.create_task(_wait_for_process_exit(process))
    cleanup_confirmed = False
    cleanup_failure: BaseException | None = None
    capture_problem = False
    try:
        try:
            async with asyncio.timeout(effective_timeout):
                await _write_prompt(process, prompt)
                exit_code = await wait_task
        except TimeoutError:
            cleanup_confirmed = await terminate_process_tree(
                process, config.terminate_grace_seconds
            )
            if not cleanup_confirmed:
                raise ExecutorCleanupError(
                    f"arrêt de l'arbre {executor} non confirmé après timeout"
                )
            raise TimeoutError(
                f"{executor} a dépassé {effective_timeout:g} secondes"
            )
        cleanup_confirmed = await terminate_process_tree(process, 0)
        if not cleanup_confirmed:
            raise ExecutorCleanupError(
                f"arrêt des descendants de {executor} non confirmé"
            )
    except asyncio.CancelledError:
        cleanup_confirmed = await asyncio.shield(
            terminate_process_tree(process, config.terminate_grace_seconds)
        )
        if not cleanup_confirmed:
            raise ExecutorCleanupError(
                f"arrêt de l'arbre {executor} non confirmé après annulation"
            ) from None
        raise
    finally:
        try:
            if not cleanup_confirmed:
                try:
                    final_cleanup_confirmed = await asyncio.shield(
                        terminate_process_tree(
                            process, config.terminate_grace_seconds
                        )
                    )
                except BaseException as exc:  # conserve la clôture fail-closed
                    cleanup_failure = exc
                    cleanup_confirmed = False
                else:
                    cleanup_confirmed = final_cleanup_confirmed
        finally:
            try:
                fenced.close_fence()
            except BaseException as exc:  # le drainage doit rester inconditionnel
                cleanup_failure = cleanup_failure or exc
                cleanup_confirmed = False

        capture_tasks = {stdout_task, stderr_task}
        done_captures, pending_captures = await asyncio.wait(
            capture_tasks,
            timeout=OUTPUT_DRAIN_SECONDS,
        )
        capture_problem = bool(pending_captures) or any(
            task.cancelled() or task.exception() is not None
            for task in done_captures
        )
        for task in pending_captures:
            task.cancel()
        if pending_captures:
            await asyncio.wait(pending_captures, timeout=0.1)
        wait_task.cancel()
        await asyncio.gather(wait_task, return_exceptions=True)
        if cleanup_failure is not None:
            raise ExecutorCleanupError(
                f"clôture finale de l'arbre {executor} impossible"
            ) from cleanup_failure
        if not cleanup_confirmed:
            raise ExecutorCleanupError(
                f"arrêt final de l'arbre {executor} non confirmé"
            )
        if capture_problem:
            raise ExecutorCleanupError(
                f"drainage des flux de {executor} non confirmé"
            )

    stdout = stdout_capture.snapshot()
    stderr = stderr_capture.snapshot()
    if stdout.truncated or stderr.truncated:
        raise RuntimeError(
            f"sortie de l'exécuteur supérieure à {config.max_output_bytes} octets"
        )
    event_count, output, usage = _count_json_events(
        executor,
        stdout_capture.raw_snapshot(),
        require_terminal_success=exit_code == 0,
        redactions=tuple(mcp.environment.values()) if mcp is not None else (),
    )
    return ExecutorResult(
        executor=executor,
        exit_code=exit_code,
        event_count=event_count,
        stdout_sha256=stdout.sha256,
        stderr_sha256=stderr.sha256,
        stdout_bytes=stdout.total_bytes,
        stderr_bytes=stderr.total_bytes,
        output=output,
        usage=usage,
    )


async def run_executor(
    executor: str,
    project_id: str,
    requested_path: str,
    prompt: str,
    *,
    config: ExecutorConfig,
    timeout_seconds: float | None = None,
    allow_writes: bool = False,
    mcp: McpExecution | None = None,
) -> ExecutorResult:
    """Sérialise toute écriture Codex visant la même racine, même entre workers."""

    if not isinstance(config, ExecutorConfig):
        raise ExecutorConfigurationError("configuration d'exécuteur requise")
    if not isinstance(allow_writes, bool):
        raise ValueError("allow_writes doit être un booléen")
    if not allow_writes:
        return await _run_executor_unlocked(
            executor,
            project_id,
            requested_path,
            prompt,
            config=config,
            timeout_seconds=timeout_seconds,
            allow_writes=False,
            mcp=mcp,
        )

    if executor != "codex_cli":
        raise ExecutorConfigurationError(
            "seul Codex peut recevoir une ressource projet en écriture"
        )
    effective_timeout = _effective_timeout(config.timeout_seconds, timeout_seconds)
    if mcp is not None:
        effective_timeout = min(effective_timeout, mcp.remaining_seconds())
    poison_path = config.project_write_poison_path(project_id)
    lease = _ProjectWriteLease(
        config.project_write_lock_path(project_id),
        poison_path,
    )
    started_at = asyncio.get_running_loop().time()
    await lease.acquire(effective_timeout)
    try:
        remaining = effective_timeout - (
            asyncio.get_running_loop().time() - started_at
        )
        if remaining < 0.01:
            raise TimeoutError(
                "le délai de l'exécuteur a expiré en attendant le verrou du projet"
            )
        try:
            return await _run_executor_unlocked(
                executor,
                project_id,
                requested_path,
                prompt,
                config=config,
                timeout_seconds=remaining,
                allow_writes=True,
                mcp=mcp,
            )
        except ExecutorCleanupError as exc:
            # Le marqueur est publié pendant que ce worker détient encore le
            # verrou : tout candidat déjà en attente le verra après acquisition.
            _poison_project_write(poison_path)
            raise _quarantined_cleanup_error(poison_path) from exc
    finally:
        try:
            lease.release()
        except ExecutorCleanupError as exc:
            _poison_project_write(poison_path)
            raise _quarantined_cleanup_error(poison_path) from exc
