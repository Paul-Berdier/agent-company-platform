"""Sonde MCP stdio exécutée sur un runner authentifié.

Un serveur MCP en transport ``stdio`` ne peut pas être interrogé depuis l'API :
son exécutable vit sur la machine du worker. Cette sonde lance le programme
demandé — uniquement s'il figure dans l'allowlist locale d'exécutables absolus —
et conduit la poignée de main JSON-RPC minimale (``initialize``,
``notifications/initialized``, ``tools/list`` paginé) pour rapporter les outils
réellement exposés.

Règles de sûreté :

* jamais de shell : le spawn passe par le même helper fencé que le runner local
  (``spawn_fenced_process``), donc session POSIX ou Job Object Windows ;
* l'allowlist est comparée après ``Path.resolve`` ; toute commande hors
  allowlist échoue **sans lancement** ;
* l'environnement transmis est minimal (``PATH``, ``SYSTEMROOT``, ``TEMP``,
  ``TMP``, ``HOME``, ``USERPROFILE``) augmenté des variables fournies par
  l'API ; aucune variable du worker n'est héritée ;
* les valeurs d'environnement injectées par l'API (valeurs de secrets résolues
  depuis le coffre) ne sont jamais journalisées ; elles sont expurgées de tout
  ce que le serveur sonde renvoie (``stderr_tail``, ``server_info``, outils)
  avant d'être retournées à l'API ;
* aucun faux succès : une absence de réponse, une sortie non JSON, une réponse
  ``initialize`` incomplète, un dépassement de délai ou un refus d'allowlist
  produisent ``status="failed"`` avec un code d'erreur explicite.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Sequence

from .local_runner import (
    FencedProcess,
    FencedSpawnError,
    spawn_fenced_process,
    terminate_process_tree,
)


ENABLED_ENV = "ACP_WORKER_MCP_STDIO_ENABLED"
ALLOWED_EXECUTABLES_ENV = "ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES"
TIMEOUT_ENV = "ACP_WORKER_MCP_STDIO_TIMEOUT_SECONDS"

DEFAULT_TIMEOUT_SECONDS = 20
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "agent-company-platform-worker"
CLIENT_VERSION = "0.4.0"

# Marqueur substitué aux valeurs d'environnement injectées par l'API dans tout
# contenu produit par le serveur sondé.
REDACTED_PLACEHOLDER = "***"
# En deçà de cette longueur, une valeur (``1``, ``on``, ``dev``) apparaîtrait
# partout et rendrait le diagnostic illisible sans rien protéger d'utile.
MIN_REDACTED_VALUE_CHARS = 4
# Profondeur maximale parcourue lors de l'expurgation : au-delà, la structure
# est remplacée par le marqueur (échec fermé) plutôt que retournée non examinée.
MAX_REDACTION_DEPTH = 64
STDERR_TAIL_MAX_CHARS = 4096
TOOL_DESCRIPTION_MAX_CHARS = 2000
MAX_TOOL_PAGES = 20
MAX_TOOLS = 500
MAX_LINE_BYTES = 4 * 1024 * 1024
TERMINATE_GRACE_SECONDS = 0.2
# Après la fermeture de stdin, un serveur correct sort de lui-même : lui laisser
# ce délai évite de transformer une fin propre en code de terminaison forcée.
CLEAN_EXIT_GRACE_SECONDS = 2.0

# Seules ces variables du worker sont recopiées ; tout le reste (jetons
# d'enregistrement, secrets du gateway, configuration interne) reste invisible.
INHERITED_ENVIRONMENT_NAMES = (
    "PATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
)

_INITIALIZE_ID = 1
_FIRST_TOOLS_ID = 2


class McpProbeConfigurationError(ValueError):
    """Configuration de la sonde MCP refusée avant toute exécution."""


class _ProbeFailure(Exception):
    """Échec structuré de l'échange, converti en ``error`` du résultat."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class McpStdioProbeConfig:
    """Autorisation locale d'exécuter des serveurs MCP stdio.

    ``enabled`` seul ne suffit jamais : sans allowlist d'exécutables absolus la
    capacité n'est pas annoncée et la sonde refuse tout lancement.
    """

    enabled: bool = False
    allowed_executables: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise McpProbeConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")
        if not isinstance(self.timeout_seconds, int) or isinstance(
            self.timeout_seconds, bool
        ):
            raise McpProbeConfigurationError(f"{TIMEOUT_ENV} doit être un entier")
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise McpProbeConfigurationError(
                f"{TIMEOUT_ENV} doit être compris entre "
                f"{MIN_TIMEOUT_SECONDS} et {MAX_TIMEOUT_SECONDS} secondes"
            )
        for entry in self.allowed_executables:
            if not isinstance(entry, str) or not Path(entry).is_absolute():
                raise McpProbeConfigurationError(
                    f"{ALLOWED_EXECUTABLES_ENV} n'accepte que des chemins absolus"
                )
        if self.enabled and not self.allowed_executables:
            raise McpProbeConfigurationError(
                f"{ENABLED_ENV}=1 exige au moins un exécutable dans "
                f"{ALLOWED_EXECUTABLES_ENV}"
            )

    @classmethod
    def disabled(cls) -> "McpStdioProbeConfig":
        return cls()

    @classmethod
    def from_environ(
        cls, environ: Mapping[str, str] | None = None
    ) -> "McpStdioProbeConfig":
        """Construit la configuration depuis l'environnement, fermée par défaut."""

        source = os.environ if environ is None else environ
        raw_enabled = source.get(ENABLED_ENV, "0").strip()
        if raw_enabled in {"", "0"}:
            enabled = False
        elif raw_enabled == "1":
            enabled = True
        else:
            raise McpProbeConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")

        raw_allowed = source.get(ALLOWED_EXECUTABLES_ENV, "")
        allowed = tuple(
            entry.strip() for entry in raw_allowed.split(os.pathsep) if entry.strip()
        )

        raw_timeout = source.get(TIMEOUT_ENV, "").strip()
        if raw_timeout:
            try:
                timeout_seconds = int(raw_timeout)
            except ValueError as exc:
                raise McpProbeConfigurationError(
                    f"{TIMEOUT_ENV} doit être un entier"
                ) from exc
        else:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        return cls(
            enabled=enabled,
            allowed_executables=allowed,
            timeout_seconds=timeout_seconds,
        )

    def status(self) -> str:
        """Libellé d'état pour ``doctor`` (jamais de chemin ni de secret)."""

        return "enabled" if self.enabled and self.allowed_executables else "disabled"

    def resolved_allowlist(self) -> set[str]:
        """Allowlist canonicalisée, comparable à une commande reçue."""

        resolved: set[str] = set()
        for entry in self.allowed_executables:
            try:
                resolved.add(_canonical_path(entry))
            except OSError:
                continue
        return resolved

    def allows(self, command: str) -> bool:
        if not self.enabled or not self.allowed_executables:
            return False
        if not isinstance(command, str) or not command:
            return False
        candidate = Path(command)
        if not candidate.is_absolute():
            return False
        try:
            return _canonical_path(command) in self.resolved_allowlist()
        except OSError:
            return False


def _canonical_path(value: str) -> str:
    """Forme comparable d'un chemin (résolution + casse Windows)."""

    resolved = str(Path(value).resolve(strict=False))
    return os.path.normcase(resolved)


def probe_environment(requested: Mapping[str, Any] | None) -> dict[str, str]:
    """Environnement minimal du serveur MCP, augmenté des variables demandées."""

    environment: dict[str, str] = {}
    for name in INHERITED_ENVIRONMENT_NAMES:
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    if isinstance(requested, Mapping):
        for name, value in requested.items():
            if isinstance(name, str) and name and isinstance(value, str):
                environment[name] = value
    return environment


def redaction_values(requested: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Valeurs injectées par l'API à masquer dans tout ce que le serveur renvoie.

    Ce sont des valeurs de secrets résolues depuis le coffre : un serveur MCP
    bavard qui les réécrit sur stderr ou dans ``serverInfo`` les publierait dans
    une réponse API lisible par tout utilisateur authentifié.
    """

    if not isinstance(requested, Mapping):
        return ()
    values = {
        value
        for name, value in requested.items()
        if isinstance(name, str)
        and name
        and isinstance(value, str)
        and len(value) >= MIN_REDACTED_VALUE_CHARS
    }
    # Les plus longues d'abord : une valeur contenue dans une autre ne doit pas
    # laisser passer le reste du secret englobant.
    return tuple(sorted(values, key=len, reverse=True))


def _redact_text(value: str, redactions: Sequence[str]) -> str:
    for secret in redactions:
        if secret and secret in value:
            value = value.replace(secret, REDACTED_PLACEHOLDER)
    return value


def _redact_data(value: Any, redactions: Sequence[str], depth: int = 0) -> Any:
    """Expurge récursivement une structure JSON produite par le serveur sondé.

    Au-delà de ``MAX_REDACTION_DEPTH``, la branche est remplacée par le marqueur :
    un contenu non examiné ne doit jamais être retourné tel quel.
    """

    if not redactions:
        return value
    if depth > MAX_REDACTION_DEPTH:
        return REDACTED_PLACEHOLDER
    if isinstance(value, str):
        return _redact_text(value, redactions)
    if isinstance(value, Mapping):
        return {
            (_redact_text(key, redactions) if isinstance(key, str) else key): (
                _redact_data(item, redactions, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_data(item, redactions, depth + 1) for item in value]
    return value


def _bounded_tail(value: str) -> str:
    return value[-STDERR_TAIL_MAX_CHARS:] if value else ""


def _result(
    *,
    status: str,
    error: str | None,
    duration_ms: int,
    protocol_version: str | None = None,
    server_info: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    exit_code: int | None = None,
    stderr_tail: str = "",
    redactions: Sequence[str] = (),
) -> dict[str, Any]:
    """Corps du ``POST result``, déjà expurgé des valeurs injectées.

    Tout ce qui vient du serveur sondé (``stderr_tail``, ``server_info``,
    outils) est du contenu non fiable : l'expurgation a lieu ici, au seul
    endroit par lequel un résultat sort de la sonde.
    """

    return {
        "status": status,
        "protocol_version": (
            None
            if protocol_version is None
            else _redact_text(protocol_version, redactions)
        ),
        "server_info": (
            None if server_info is None else _redact_data(server_info, redactions)
        ),
        "tools": [_redact_data(tool, redactions) for tool in tools or []],
        "exit_code": exit_code,
        "stderr_tail": _bounded_tail(_redact_text(stderr_tail, redactions)),
        "duration_ms": duration_ms,
        "error": error,
    }


def _normalize_tool(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        return None
    description = raw.get("description")
    if not isinstance(description, str):
        description = ""
    schema = raw.get("inputSchema")
    if not isinstance(schema, Mapping):
        schema = {}
    return {
        "name": name,
        "description": description[:TOOL_DESCRIPTION_MAX_CHARS],
        "input_schema": dict(schema),
    }


class _StderrTail:
    """Conserve la fin de stderr même si la lecture est interrompue.

    L'état vit hors de la tâche : un arrêt forcé du serveur ne doit jamais
    effacer le diagnostic déjà capturé.
    """

    def __init__(self) -> None:
        self.text = ""

    async def read(self, stream: asyncio.StreamReader) -> None:
        while True:
            try:
                chunk = await stream.read(4096)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            self.text = (self.text + chunk.decode("utf-8", errors="replace"))[
                -STDERR_TAIL_MAX_CHARS:
            ]


async def _send(process: FencedProcess, message: dict[str, Any]) -> None:
    stdin = process.stdin
    if stdin is None:
        raise _ProbeFailure("protocol")
    stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
    try:
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError) as exc:
        raise _ProbeFailure("closed") from exc


async def _read_response(
    stream: asyncio.StreamReader, identifier: int
) -> dict[str, Any]:
    """Lit des lignes jusqu'à la réponse portant ``identifier``.

    Les notifications du serveur (sans ``id``) sont ignorées ; toute ligne qui
    n'est pas du JSON UTF-8 est une violation du protocole.
    """

    while True:
        try:
            line = await stream.readline()
        except (ValueError, asyncio.LimitOverrunError) as exc:
            raise _ProbeFailure("protocol") from exc
        if not line:
            raise _ProbeFailure("closed")
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _ProbeFailure("protocol") from exc
        if not isinstance(payload, dict):
            raise _ProbeFailure("protocol")
        if payload.get("id") != identifier:
            continue
        if "error" in payload:
            raise _ProbeFailure("server_error")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise _ProbeFailure("protocol")
        return result


async def _handshake(process: FencedProcess) -> tuple[str, dict[str, Any]]:
    """Conduit ``initialize`` puis ``notifications/initialized``.

    La spécification MCP 2025-06-18 impose ``protocolVersion`` et ``serverInfo``
    dans la réponse à ``initialize``. Leur absence est une réponse mal formée :
    la sonde échoue en ``protocol`` plutôt que de rapporter un succès à
    ``protocol_version: null``, que le contrat ``McpDiscovery`` (``protocol_version:
    str`` requis) ne pourrait pas représenter.
    """

    stdout = process.stdout
    if stdout is None:
        raise _ProbeFailure("protocol")
    await _send(
        process,
        {
            "jsonrpc": "2.0",
            "id": _INITIALIZE_ID,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        },
    )
    result = await _read_response(stdout, _INITIALIZE_ID)
    protocol_version = result.get("protocolVersion")
    if not isinstance(protocol_version, str) or not protocol_version.strip():
        raise _ProbeFailure("protocol")
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict):
        raise _ProbeFailure("protocol")
    await _send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return protocol_version, dict(server_info)


async def _list_tools(process: FencedProcess) -> list[dict[str, Any]]:
    stdout = process.stdout
    if stdout is None:
        raise _ProbeFailure("protocol")
    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    for page in range(MAX_TOOL_PAGES):
        identifier = _FIRST_TOOLS_ID + page
        params: dict[str, Any] = {} if cursor is None else {"cursor": cursor}
        await _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "method": "tools/list",
                "params": params,
            },
        )
        result = await _read_response(stdout, identifier)
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise _ProbeFailure("protocol")
        for raw in raw_tools:
            normalized = _normalize_tool(raw)
            if normalized is not None and len(tools) < MAX_TOOLS:
                tools.append(normalized)
        next_cursor = result.get("nextCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            return tools
        if len(tools) >= MAX_TOOLS:
            # Une liste tronquée annoncée comme complète serait un faux succès.
            raise _ProbeFailure("too_many_tools")
        cursor = next_cursor
    raise _ProbeFailure("too_many_tools")


def _requested_command(request: Mapping[str, Any]) -> tuple[str, list[str]]:
    command = request.get("command")
    if not isinstance(command, str) or not command:
        raise _ProbeFailure("invalid_request")
    raw_args = request.get("args", [])
    if raw_args is None:
        raw_args = []
    if not isinstance(raw_args, (list, tuple)) or any(
        not isinstance(item, str) for item in raw_args
    ):
        raise _ProbeFailure("invalid_request")
    return command, list(raw_args)


def _working_directory(request: Mapping[str, Any], fallback: str) -> str:
    """Répertoire de travail : celui fourni s'il est absolu et existant, sinon neuf."""

    requested = request.get("cwd")
    if isinstance(requested, str) and requested:
        candidate = Path(requested)
        if candidate.is_absolute() and candidate.is_dir():
            return str(candidate)
    return fallback


def _effective_timeout(request: Mapping[str, Any], config: McpStdioProbeConfig) -> float:
    """La requête peut réduire le délai local, jamais l'étendre."""

    timeout = float(config.timeout_seconds)
    requested = request.get("timeout_seconds")
    if isinstance(requested, (int, float)) and not isinstance(requested, bool):
        if MIN_TIMEOUT_SECONDS <= float(requested) <= MAX_TIMEOUT_SECONDS:
            timeout = min(timeout, float(requested))
    return timeout


async def run_stdio_probe(
    request: Mapping[str, Any], config: McpStdioProbeConfig
) -> dict[str, Any]:
    """Interroge un serveur MCP stdio local et retourne toujours un verdict réel.

    Le dictionnaire retourné est le corps attendu par
    ``POST /mcp/worker/probes/{id}/result`` : ``status`` plus les champs de
    ``McpProbeResult``. Cette coroutine ne lève jamais : tout échec devient un
    ``status="failed"`` accompagné d'un ``error`` parmi ``disabled``,
    ``invalid_request``, ``not_allowed``, ``spawn_error``,
    ``job_assignment_failed``, ``timeout``, ``protocol``, ``closed``,
    ``server_error``, ``too_many_tools`` ou ``process_tree_cleanup_failed``.

    Une liste d'outils qui dépasserait ``MAX_TOOLS`` ou ``MAX_TOOL_PAGES`` est un
    échec explicite : une découverte tronquée ne doit jamais être présentée comme
    complète. Une réponse ``initialize`` sans ``protocolVersion`` ou sans
    ``serverInfo`` l'est aussi.

    Les valeurs d'environnement injectées par l'API sont expurgées de tout ce que
    le serveur renvoie : le résultat est lisible par tout utilisateur autorisé
    sur ``GET /mcp/probes/{id}``.
    """

    started = monotonic()

    def elapsed_ms() -> int:
        return max(0, round((monotonic() - started) * 1000))

    if not config.enabled or not config.allowed_executables:
        return _result(status="failed", error="disabled", duration_ms=elapsed_ms())
    try:
        command, args = _requested_command(request)
    except _ProbeFailure as failure:
        return _result(status="failed", error=failure.code, duration_ms=elapsed_ms())
    if not config.allows(command):
        return _result(status="failed", error="not_allowed", duration_ms=elapsed_ms())

    environment = probe_environment(request.get("env"))
    redactions = redaction_values(request.get("env"))
    timeout_seconds = _effective_timeout(request, config)

    # ``ignore_cleanup_errors`` : un fichier laissé verrouillé par le serveur
    # arrêté ne doit jamais transformer un verdict en exception.
    with tempfile.TemporaryDirectory(
        prefix="acp-mcp-probe-", ignore_cleanup_errors=True
    ) as scratch:
        cwd = _working_directory(request, scratch)
        try:
            fenced = await spawn_fenced_process(
                [command, *args],
                cwd=cwd,
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=MAX_LINE_BYTES,
            )
        except FencedSpawnError as exc:
            return _result(
                status="failed",
                error=exc.reason,
                duration_ms=elapsed_ms(),
                redactions=redactions,
            )

        assert fenced.stderr is not None
        tail = _StderrTail()
        stderr_task = asyncio.create_task(tail.read(fenced.stderr))
        protocol_version: str | None = None
        server_info: dict[str, Any] | None = None
        tools: list[dict[str, Any]] = []
        error: str | None = None
        try:
            try:
                protocol_version, server_info = await asyncio.wait_for(
                    _handshake(fenced), timeout=timeout_seconds
                )
                tools = await asyncio.wait_for(
                    _list_tools(fenced),
                    timeout=max(0.001, timeout_seconds - (monotonic() - started)),
                )
            except TimeoutError:
                error = "timeout"
            except _ProbeFailure as failure:
                error = failure.code
            except (OSError, ValueError):
                error = "protocol"
        finally:
            await _close_stdin(fenced)
            if error is None:
                await _await_clean_exit(fenced, CLEAN_EXIT_GRACE_SECONDS)
            stopped = await terminate_process_tree(
                fenced.process, TERMINATE_GRACE_SECONDS
            )
            fenced.close_fence()
            await asyncio.wait({stderr_task}, timeout=1.0)
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)

        if error is None and not stopped:
            # Aucun faux succès : un arbre de processus dont l'arrêt n'est pas
            # confirmé est un échec, même si la découverte a répondu.
            error = "process_tree_cleanup_failed"
        return _result(
            status="succeeded" if error is None else "failed",
            error=error,
            duration_ms=elapsed_ms(),
            protocol_version=protocol_version,
            server_info=server_info,
            tools=tools,
            exit_code=fenced.returncode,
            stderr_tail=tail.text,
            redactions=redactions,
        )


async def _await_clean_exit(process: FencedProcess, grace_seconds: float) -> None:
    """Laisse au serveur le temps de sortir seul après la fermeture de stdin.

    ``Process.wait`` peut ne se résoudre qu'à la fermeture de tous les tubes
    hérités : on interroge ``returncode``, publié dès la sortie réelle.
    """

    deadline = monotonic() + grace_seconds
    while process.returncode is None and monotonic() < deadline:
        await asyncio.sleep(0.01)


async def _close_stdin(process: FencedProcess) -> None:
    """Ferme l'entrée standard du serveur pour lui signaler la fin de l'échange."""

    stdin = process.stdin
    if stdin is None:
        return
    try:
        stdin.close()
        await asyncio.wait_for(stdin.wait_closed(), timeout=1.0)
    except (OSError, RuntimeError, TimeoutError, ConnectionResetError):
        pass
