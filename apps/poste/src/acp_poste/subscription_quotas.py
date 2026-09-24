"""Relevé des quotas réels d'abonnement sur le poste (Codex CLI, Claude Code).

Deux sources officielles, jamais d'estimation :

- **Codex CLI** connecté par compte ChatGPT : la sonde lance ``codex app-server``
  (JSON-RPC 2.0 en JSONL sur stdio, sans l'en-tête ``jsonrpc``) avec
  ``CODEX_HOME`` = profil dédié du poste, dans un environnement minimal d'où toute
  clé d'API est absente (``OPENAI_API_KEY``, ``CODEX_API_KEY``,
  ``CODEX_ACCESS_TOKEN``) : la lecture se fait en mode compte. Elle vérifie la
  version (0.100.0 au minimum), conduit ``initialize`` puis la notification
  ``initialized``, ``account/read`` et ``account/rateLimits/read``, et produit un
  relevé par compteur (``rateLimitsByLimitId``, sinon la vue ``rateLimits``).
- **Claude Code** : aucune API ne donne les limites d'un compte individuel. La sonde
  lit le fichier écrit par la ligne d'état de Claude Code, qui recopie
  ``rate_limits.five_hour`` et ``rate_limits.seven_day`` reçus de Claude Code.

Chaque sonde rend toujours des relevés valides au sens de ``SubscriptionQuotaReport`` :
un échec devient un état explicite (``not_signed_in``, ``cli_missing``,
``cli_too_old``, ``unavailable``) accompagné d'une explication en français, jamais
une exception ni une valeur inventée. Un échec porte l'identifiant réservé ``probe`` :
il ne remplace jamais le dernier relevé réussi d'un compteur, et un seul compteur hors
contrat fait échouer toute la lecture plutôt que d'en transmettre une partie. Le
processus Codex est lancé sans shell dans la
clôture du runner local (Job Object sous Windows) et son arbre est arrêté à la fin,
y compris après un dépassement de délai ou une annulation. Aucune valeur
d'environnement, adresse électronique, identifiant de compte ni message d'erreur du
serveur n'est journalisé ou transmis.

Refonte « Hermes au centre » : la boucle qui transmettait les relevés à l'API ACP a
été retirée avec cette API, et avec elle son intervalle d'envoi. ``acp-poste quotas``
relève et affiche les quotas sur le poste, seulement si ``ACP_WORKER_SUBSCRIPTION_QUOTAS``
vaut ``1`` : sans cet accord, rien n'est lancé ni lu. Leur envoi à Hermes (route
machine du greffon ``acp-poste``) arrive en P6.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from acp_poste_contrat import (
    DEFAULT_LIMIT_ID,
    PROBE_LIMIT_ID,
    QUOTA_BATCH_MAX,
    QUOTA_DETAIL_MAX,
    QUOTA_PLAN_MAX,
    QUOTA_SOURCE_BY_PROVIDER,
    SubscriptionQuotaReport,
)

from .claude_statusline import SNAPSHOT_ENV as CLAUDE_SNAPSHOT_ENV
from .claude_statusline import SNAPSHOT_SOURCE as CLAUDE_SNAPSHOT_SOURCE
from .claude_statusline import SNAPSHOT_WINDOW_MINUTES as CLAUDE_WINDOW_MINUTES
from .claude_statusline import default_snapshot_path as default_claude_snapshot_path
from .executors import ExecutorConfig
from .local_runner import FencedProcess, FencedSpawnError, spawn_fenced_process, terminate_process_tree


ENABLED_ENV = "ACP_WORKER_SUBSCRIPTION_QUOTAS"
QUOTA_CODEX_HOME_ENV = "ACP_WORKER_QUOTA_CODEX_HOME"
QUOTA_CODEX_EXECUTABLE_ENV = "ACP_WORKER_QUOTA_CODEX_EXECUTABLE"
EXECUTOR_CODEX_HOME_ENV = "ACP_WORKER_CODEX_HOME"

DEFAULT_PROBE_TIMEOUT_SECONDS = 20.0
MIN_PROBE_TIMEOUT_SECONDS = 1.0
MAX_PROBE_TIMEOUT_SECONDS = 120.0
MINIMUM_CODEX_VERSION = (0, 100, 0)
MAX_LINE_BYTES = 1024 * 1024
MAX_VERSION_BYTES = 4096
MAX_SNAPSHOT_BYTES = 64 * 1024
MAX_CODEX_COUNTERS = QUOTA_BATCH_MAX - 1
"""Un lot porte au plus 16 relevés : une place reste réservée à Claude Code."""
TERMINATE_GRACE_SECONDS = 0.2
CLEAN_EXIT_GRACE_SECONDS = 2.0
CLIENT_NAME = "acp_poste"
CLIENT_TITLE = "Agent Company Platform — poste"
CLIENT_VERSION = "1.0"
"""Version du dialogue de cette sonde avec l'app-server, pas celle du produit."""
# Format du fichier de la ligne d'état : défini par son écrivain, ``claude_statusline``.

API_KEY_VARIABLES = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
# Seules ces variables du poste sont recopiées : de quoi lancer le CLI (et son
# lanceur npm sous Windows), trouver le profil utilisateur, et joindre le réseau à
# travers un éventuel mandataire. Jetons du poste, clés d'API et configuration
# interne restent invisibles de Codex.
INHERITED_ENVIRONMENT_NAMES = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "LANG",
    "LC_ALL",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)
_POSIX_PROXY_NAMES = ("https_proxy", "http_proxy", "no_proxy")

_VERSION = re.compile(r"(\d{1,6})\.(\d{1,6})\.(\d{1,6})")
_LIMIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")
_WINDOW_KEYS = ("primary", "secondary")

CODEX_MISSING = (
    "Codex CLI introuvable sur le poste : installez-le ou renseignez "
    f"{QUOTA_CODEX_EXECUTABLE_ENV} (chemin absolu)."
)
CODEX_PROFILE_MISSING = (
    "Profil Codex dédié du poste absent : créez-le puis connectez-le vous-même "
    "avec « codex login » (CODEX_HOME = profil du poste)."
)
CODEX_NOT_SIGNED_IN = (
    "Profil Codex dédié non connecté : connectez-le vous-même avec « codex login » "
    "(CODEX_HOME = profil du poste)."
)
CODEX_API_KEY_ACCOUNT = (
    "Profil Codex connecté par clé d'API : aucun quota d'abonnement ChatGPT à relever. "
    "Connectez un compte ChatGPT avec « codex login »."
)
CODEX_OTHER_ACCOUNT = (
    "Profil Codex connecté hors compte ChatGPT : aucun quota d'abonnement à relever."
)
CODEX_VERSION_UNREADABLE = "Version de Codex CLI illisible : quotas non relevés."
CODEX_MALFORMED = "Réponse de l'app-server Codex mal formée : quotas non relevés."
CODEX_CLOSED = "L'app-server Codex s'est arrêté avant de répondre : quotas non relevés."
CODEX_FENCE_FAILED = (
    "Isolation du processus Codex impossible (clôture de l'arbre de processus) : "
    "sonde non lancée."
)
CODEX_CLEANUP_UNCONFIRMED = (
    "Arrêt de l'app-server Codex non confirmé : relevé écarté par prudence."
)
CLAUDE_MISSING = (
    "Aucun relevé de la ligne d'état Claude Code : fichier absent. Réglez la ligne "
    "d'état de Claude Code sur « python -m acp_poste.claude_statusline » "
    "(apps/poste/README.md, § Ligne d'état Claude Code), puis utilisez Claude Code "
    "une fois."
)
CLAUDE_UNREADABLE = "Relevé de la ligne d'état Claude Code illisible : quotas non relevés."
CLAUDE_MALFORMED = "Relevé de la ligne d'état Claude Code mal formé : quotas non relevés."
CLAUDE_TOO_LARGE = "Relevé de la ligne d'état Claude Code trop volumineux : fichier ignoré."


class SubscriptionQuotaConfigurationError(ValueError):
    """Configuration des quotas refusée avant tout lancement."""


class _Malformed(Exception):
    """Réponse ou fichier hors de la forme attendue."""


class _Closed(Exception):
    """Le processus a fermé sa sortie avant la réponse attendue."""


class _RpcError(Exception):
    def __init__(self, method: str, code: object) -> None:
        super().__init__(method)
        self.method = method
        self.code = code if type(code) is int else "inconnu"


def default_codex_home() -> Path:
    return Path.home() / ".acp" / "codex-home"


def _absolute_setting(value: str, setting: str) -> Path:
    if not value or value != value.strip() or not Path(value).is_absolute():
        raise SubscriptionQuotaConfigurationError(f"{setting} doit être un chemin absolu")
    return Path(value)


def _enabled_setting(value: str | None) -> bool:
    if value in (None, "", "0"):
        return False
    if value == "1":
        return True
    raise SubscriptionQuotaConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")


@dataclass(frozen=True)
class SubscriptionQuotaConfig:
    """Réglages locaux du relevé des quotas, fermés par défaut.

    ``enabled`` est l'accord du propriétaire : sans lui, ``collect_reports`` refuse
    et ni Codex CLI ni le fichier de la ligne d'état ne sont touchés.
    ``codex_command`` est l'argv du CLI sans sous-commande ; ``None`` signifie
    « chercher ``codex`` dans le PATH du poste au moment de la sonde ».
    """

    enabled: bool = False
    codex_command: tuple[str, ...] | None = None
    codex_home: Path = field(default_factory=default_codex_home)
    claude_snapshot_path: Path = field(default_factory=default_claude_snapshot_path)
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise SubscriptionQuotaConfigurationError(f"{ENABLED_ENV} accepte uniquement 0 ou 1")
        if self.codex_command is not None:
            if (
                not isinstance(self.codex_command, tuple)
                or not self.codex_command
                or any(not isinstance(part, str) or not part for part in self.codex_command)
                or not Path(self.codex_command[0]).is_absolute()
            ):
                raise SubscriptionQuotaConfigurationError(
                    "la commande Codex des quotas doit commencer par un exécutable absolu"
                )
        for name, setting in (
            ("codex_home", QUOTA_CODEX_HOME_ENV),
            ("claude_snapshot_path", CLAUDE_SNAPSHOT_ENV),
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise SubscriptionQuotaConfigurationError(f"{setting} doit être un chemin absolu")
        timeout = self.probe_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (
            MIN_PROBE_TIMEOUT_SECONDS <= timeout <= MAX_PROBE_TIMEOUT_SECONDS
        ):
            raise SubscriptionQuotaConfigurationError(
                "le délai de la sonde Codex doit être compris entre 1 et 120 secondes"
            )

    @classmethod
    def disabled(cls) -> SubscriptionQuotaConfig:
        return cls()

    @classmethod
    def from_environ(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        executors: ExecutorConfig | None = None,
    ) -> SubscriptionQuotaConfig:
        """Lit l'environnement ; le profil Codex des exécuteurs est réutilisé s'il existe."""

        source = os.environ if environ is None else environ
        enabled = _enabled_setting(source.get(ENABLED_ENV))
        quota_home = source.get(QUOTA_CODEX_HOME_ENV)
        quota_executable = source.get(QUOTA_CODEX_EXECUTABLE_ENV)
        executor_codex = executors.codex if executors is not None else None
        if executor_codex is not None:
            configured = [
                setting
                for setting, value in (
                    (QUOTA_CODEX_HOME_ENV, quota_home),
                    (QUOTA_CODEX_EXECUTABLE_ENV, quota_executable),
                )
                if value
            ]
            if configured:
                raise SubscriptionQuotaConfigurationError(
                    f"{configured[0]} est refusé : le profil de l'exécuteur Codex "
                    f"({EXECUTOR_CODEX_HOME_ENV}) est déjà le profil dédié du poste"
                )
            command: tuple[str, ...] | None = (str(executor_codex.executable),)
            home = executor_codex.auth_directory
        else:
            home = (
                _absolute_setting(quota_home, QUOTA_CODEX_HOME_ENV)
                if quota_home is not None
                else default_codex_home()
            )
            command = (
                (str(_absolute_setting(quota_executable, QUOTA_CODEX_EXECUTABLE_ENV)),)
                if quota_executable is not None
                else None
            )
        raw_snapshot = source.get(CLAUDE_SNAPSHOT_ENV)
        snapshot = (
            _absolute_setting(raw_snapshot, CLAUDE_SNAPSHOT_ENV)
            if raw_snapshot is not None
            else default_claude_snapshot_path()
        )
        return cls(
            enabled=enabled,
            codex_command=command,
            codex_home=home,
            claude_snapshot_path=snapshot,
        )

    def status(self) -> str:
        return "enabled" if self.enabled else "disabled"

    def doctor_report(self) -> dict[str, object]:
        """État pour ``doctor`` : jamais de chemin (profil, fichier) ni de secret."""

        return {"subscription_quotas": self.status()}


# --------------------------------------------------------------------------
# Relevés
# --------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _detail(text: str) -> str:
    return text if len(text) <= QUOTA_DETAIL_MAX else text[: QUOTA_DETAIL_MAX - 1] + "…"


SOURCE_UNKNOWN_PLAN = "unknown"


def _source_plan(plan: str | None) -> str | None:
    """« unknown » est la valeur par laquelle Codex dit ignorer l'offre : elle reste inconnue."""

    return None if plan == SOURCE_UNKNOWN_PLAN else plan


def _safe_plan(plan: object) -> str | None:
    """Plan recopié seulement s'il respecte le contrat ; sinon « Inconnu »."""

    if (
        isinstance(plan, str)
        and plan.strip()
        and len(plan) <= QUOTA_PLAN_MAX
        and "\x00" not in plan
        and plan != SOURCE_UNKNOWN_PLAN
    ):
        return plan
    return None


def _failure(
    provider: str,
    status: str,
    detail: str,
    *,
    plan: object = None,
) -> SubscriptionQuotaReport:
    """Lecture en échec : identifiant réservé, jamais celui d'un compteur réussi."""

    return SubscriptionQuotaReport(
        provider=provider,
        status=status,
        source=QUOTA_SOURCE_BY_PROVIDER[provider],
        plan=_safe_plan(plan),
        limit_id=PROBE_LIMIT_ID,
        observed_at=_now(),
        detail=_detail(detail),
    )


def _field_of(error: ValidationError) -> str:
    for item in error.errors():
        names = [part for part in item.get("loc", ()) if isinstance(part, str)]
        if names:
            return names[-1]
    return "relevé"


def _validated(payload: dict[str, Any], label: str) -> SubscriptionQuotaReport:
    """Valide un relevé construit ; hors contrat, la lecture devient « indisponible »."""

    try:
        return SubscriptionQuotaReport.model_validate(payload)
    except ValidationError as exc:
        return _failure(
            payload["provider"],
            "unavailable",
            f"Relevé {label} refusé par le contrat de la plateforme "
            f"(champ {_field_of(exc)}) : quotas non transmis.",
            plan=payload.get("plan"),
        )


def _epoch(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Malformed
    try:
        return datetime.fromtimestamp(value, UTC).isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        raise _Malformed from exc


def _number_or_none(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Malformed
    return value


# --------------------------------------------------------------------------
# Sonde Codex
# --------------------------------------------------------------------------


def codex_environment(
    codex_home: Path, *, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Environnement minimal du CLI Codex : aucune clé d'API, profil dédié imposé."""

    values = os.environ if source is None else source
    names = INHERITED_ENVIRONMENT_NAMES + (() if os.name == "nt" else _POSIX_PROXY_NAMES)
    environment = {name: values[name] for name in names if name in values}
    for name in API_KEY_VARIABLES:
        environment.pop(name, None)
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def find_on_path(name: str, search_path: str) -> str | None:
    """Cherche ``name`` dans les seuls dossiers absolus du PATH, jamais le dossier courant.

    Sous Windows seules les extensions de ``PATHEXT`` sont essayées : le lanceur npm
    installe aussi un script ``codex`` sans extension, que Windows ne sait pas lancer.
    """

    if os.name == "nt":
        extensions = [
            extension
            for extension in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep)
            if extension
        ]
    else:
        extensions = [""]
    for directory in search_path.split(os.pathsep):
        if not directory or not Path(directory).is_absolute():
            continue
        for extension in extensions:
            candidate = Path(directory) / f"{name}{extension}"
            if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return str(candidate)
    return None


def _codex_argv(config: SubscriptionQuotaConfig, environment: Mapping[str, str]) -> tuple[str, ...] | None:
    if config.codex_command is not None:
        return config.codex_command if Path(config.codex_command[0]).is_file() else None
    found = find_on_path("codex", environment.get("PATH", ""))
    return (found,) if found else None


def parse_codex_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.search(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


async def _drain(stream: asyncio.StreamReader | None) -> None:
    """Vide un flux sans rien conserver : le contenu du CLI n'est jamais journalisé."""

    if stream is None:
        return
    while True:
        try:
            chunk = await stream.read(64 * 1024)
        except (OSError, ValueError):
            return
        if not chunk:
            return


async def _read_bounded(stream: asyncio.StreamReader | None, limit: int) -> bytes:
    if stream is None:
        return b""
    data = bytearray()
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return bytes(data)
        remaining = limit - len(data)
        if remaining > 0:
            data.extend(chunk[:remaining])


async def _close_stdin(process: FencedProcess) -> None:
    stdin = process.stdin
    if stdin is None:
        return
    try:
        stdin.close()
        await asyncio.wait_for(stdin.wait_closed(), timeout=1.0)
    except (OSError, RuntimeError, TimeoutError, ConnectionResetError):
        pass


async def _await_clean_exit(process: FencedProcess, grace_seconds: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + grace_seconds
    while process.returncode is None and loop.time() < deadline:
        await asyncio.sleep(0.01)


async def _shutdown(process: FencedProcess, tasks: list[asyncio.Task], *, graceful: bool) -> bool:
    """Arrête l'arbre du CLI et confirme qu'il ne reste rien ; ne lève jamais."""

    stopped = False
    try:
        await _close_stdin(process)
        if graceful:
            await _await_clean_exit(process, CLEAN_EXIT_GRACE_SECONDS)
        stopped = await terminate_process_tree(process.process, TERMINATE_GRACE_SECONDS)
    except Exception:  # noqa: BLE001 - un arrêt non prouvé reste un échec, jamais une exception
        stopped = False
    finally:
        try:
            process.close_fence()
        except Exception:  # noqa: BLE001
            stopped = False
        if tasks:
            await asyncio.wait(tasks, timeout=1.0)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return stopped


async def _send(process: FencedProcess, message: dict[str, Any]) -> None:
    stdin = process.stdin
    if stdin is None:
        raise _Closed
    stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
    try:
        await stdin.drain()
    except (BrokenPipeError, ConnectionResetError) as exc:
        raise _Closed from exc


async def _read_response(stream: asyncio.StreamReader, identifier: int, method: str) -> dict[str, Any]:
    """Lit jusqu'à la réponse ``identifier`` ; notifications et requêtes du serveur sont ignorées."""

    while True:
        try:
            line = await stream.readline()
        except (ValueError, asyncio.LimitOverrunError) as exc:
            raise _Malformed from exc
        if not line:
            raise _Closed
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Malformed from exc
        if not isinstance(payload, dict):
            raise _Malformed
        if "method" in payload or payload.get("id") != identifier:
            continue
        if "error" in payload:
            error = payload["error"]
            raise _RpcError(method, error.get("code") if isinstance(error, dict) else None)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise _Malformed
        return result


async def _codex_version(argv: tuple[str, ...], environment: dict[str, str], cwd: str) -> str:
    fenced = await spawn_fenced_process(
        [*argv, "--version"],
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout = asyncio.create_task(_read_bounded(fenced.stdout, MAX_VERSION_BYTES))
    stderr = asyncio.create_task(_drain(fenced.stderr))
    graceful = False
    try:
        output = await stdout
        graceful = True
    finally:
        # Protégé contre l'annulation : l'arbre est arrêté même après un délai dépassé.
        stopped = await asyncio.shield(_shutdown(fenced, [stdout, stderr], graceful=graceful))
    if not stopped:
        raise _CleanupUnconfirmed
    return output.decode("utf-8", errors="replace")


class _CleanupUnconfirmed(Exception):
    """L'arrêt complet de l'arbre du CLI n'a pas pu être prouvé."""


def _account_plan(account_result: dict[str, Any]) -> tuple[str | None, str | None]:
    """Retourne (plan, refus) : un refus est l'explication d'un profil sans quota lisible."""

    if "account" not in account_result:
        raise _Malformed
    account = account_result["account"]
    if account is None:
        return None, CODEX_NOT_SIGNED_IN
    if not isinstance(account, dict) or not isinstance(account.get("type"), str):
        raise _Malformed
    if account["type"] == "apiKey":
        return None, CODEX_API_KEY_ACCOUNT
    if account["type"] != "chatgpt":
        return None, CODEX_OTHER_ACCOUNT
    plan = account.get("planType")
    if plan is not None and not isinstance(plan, str):
        raise _Malformed
    return _source_plan(plan), None


def _codex_windows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    windows = []
    for key in _WINDOW_KEYS:
        window = snapshot.get(key)
        if window is None:
            continue
        if not isinstance(window, dict) or "usedPercent" not in window:
            raise _Malformed
        used = _number_or_none(window["usedPercent"])
        if used is None:
            raise _Malformed
        minutes = window.get("windowDurationMins")
        if minutes is not None and type(minutes) is not int:
            raise _Malformed
        windows.append(
            {
                "key": key,
                "used_percent": used,
                "window_minutes": minutes,
                "resets_at": _epoch(window.get("resetsAt")),
            }
        )
    return windows


def _codex_credits(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    credits = snapshot.get("credits")
    if credits is None:
        return None
    if not isinstance(credits, dict):
        raise _Malformed
    has_credits, unlimited = credits.get("hasCredits"), credits.get("unlimited")
    balance = credits.get("balance")
    if type(has_credits) is not bool or type(unlimited) is not bool:
        raise _Malformed
    if balance is not None and not isinstance(balance, str):
        raise _Malformed
    return {"has_credits": has_credits, "unlimited": unlimited, "balance": balance}


def codex_reports_from_rate_limits(
    result: dict[str, Any], *, account_plan: str | None, observed_at: datetime
) -> list[SubscriptionQuotaReport]:
    """Un relevé par compteur de ``account/rateLimits/read``, sans rien déduire d'autre.

    ``rateLimitReachedType`` présent et nul vaut « limite non atteinte » selon le
    serveur ; absent (CLI plus ancien), l'état reste inconnu.
    """

    fallback = result.get("rateLimits")
    if not isinstance(fallback, dict):
        raise _Malformed
    by_limit = result.get("rateLimitsByLimitId")
    if by_limit is not None and not isinstance(by_limit, dict):
        raise _Malformed
    if by_limit:
        counters = sorted(by_limit.items())
    else:
        limit_id = fallback.get("limitId")
        counters = [(limit_id if limit_id is not None else DEFAULT_LIMIT_ID, fallback)]
    if len(counters) > MAX_CODEX_COUNTERS:
        return [
            _failure(
                "codex",
                "unavailable",
                f"L'app-server Codex renvoie {len(counters)} compteurs, au-delà des "
                f"{MAX_CODEX_COUNTERS} transmissibles : aucun n'est transmis tronqué.",
                plan=account_plan,
            )
        ]
    reports = []
    for limit_id, snapshot in counters:
        if not isinstance(limit_id, str) or _LIMIT_ID.fullmatch(limit_id) is None:
            raise _Malformed
        if not isinstance(snapshot, dict):
            raise _Malformed
        plan = snapshot.get("planType", account_plan)
        if plan is not None and not isinstance(plan, str):
            raise _Malformed
        plan = _source_plan(plan)
        if "rateLimitReachedType" in snapshot:
            reached_type = snapshot["rateLimitReachedType"]
            if reached_type is not None and not isinstance(reached_type, str):
                raise _Malformed
            limit_reached: bool | None = reached_type is not None
        else:
            reached_type, limit_reached = None, None
        payload = {
            "provider": "codex",
            "status": "ok",
            "source": "codex_app_server",
            "plan": plan if plan is not None else _source_plan(account_plan),
            "limit_id": limit_id,
            "windows": _codex_windows(snapshot),
            "credits": _codex_credits(snapshot),
            "limit_reached": limit_reached,
            "reached_type": reached_type,
            "observed_at": observed_at,
            "detail": None,
        }
        try:
            reports.append(SubscriptionQuotaReport.model_validate(payload))
        except ValidationError as exc:
            # Toute la lecture échoue : un lot partiel retirerait à tort les derniers
            # relevés réussis du compteur refusé.
            return [
                _failure(
                    "codex",
                    "unavailable",
                    f"Compteur Codex « {limit_id} » refusé par le contrat de la plateforme "
                    f"(champ {_field_of(exc)}) : aucun compteur transmis, les derniers "
                    "relevés réussis restent affichés.",
                    plan=account_plan,
                )
            ]
    return reports


async def _codex_exchange(
    argv: tuple[str, ...], environment: dict[str, str], cwd: str
) -> list[SubscriptionQuotaReport]:
    fenced = await spawn_fenced_process(
        [*argv, "app-server"],
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_LINE_BYTES,
    )
    stderr = asyncio.create_task(_drain(fenced.stderr))
    graceful = False
    try:
        stdout = fenced.stdout
        if stdout is None:
            raise _Closed
        await _send(
            fenced,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": CLIENT_NAME,
                        "title": CLIENT_TITLE,
                        "version": CLIENT_VERSION,
                    }
                },
            },
        )
        await _read_response(stdout, 1, "initialize")
        await _send(fenced, {"method": "initialized"})
        await _send(fenced, {"id": 2, "method": "account/read", "params": {}})
        plan, refusal = _account_plan(await _read_response(stdout, 2, "account/read"))
        if refusal is not None:
            reports = [_failure("codex", "not_signed_in", refusal)]
        else:
            await _send(fenced, {"id": 3, "method": "account/rateLimits/read"})
            limits = await _read_response(stdout, 3, "account/rateLimits/read")
            reports = codex_reports_from_rate_limits(
                limits, account_plan=plan, observed_at=_now()
            )
        graceful = True
    finally:
        stopped = await asyncio.shield(_shutdown(fenced, [stderr], graceful=graceful))
    if not stopped:
        raise _CleanupUnconfirmed
    return reports


async def probe_codex(config: SubscriptionQuotaConfig) -> list[SubscriptionQuotaReport]:
    """Relève les compteurs Codex du profil dédié ; ne lève jamais."""

    environment = codex_environment(config.codex_home)
    argv = _codex_argv(config, environment)
    if argv is None:
        return [_failure("codex", "cli_missing", CODEX_MISSING)]
    if not config.codex_home.is_dir():
        return [_failure("codex", "not_signed_in", CODEX_PROFILE_MISSING)]
    timeout = config.probe_timeout_seconds
    try:
        with tempfile.TemporaryDirectory(
            prefix="acp-quotas-", ignore_cleanup_errors=True
        ) as scratch:
            async with asyncio.timeout(timeout):
                version = parse_codex_version(await _codex_version(argv, environment, scratch))
                if version is None:
                    return [_failure("codex", "unavailable", CODEX_VERSION_UNREADABLE)]
                if version < MINIMUM_CODEX_VERSION:
                    found = ".".join(str(part) for part in version)
                    minimum = ".".join(str(part) for part in MINIMUM_CODEX_VERSION)
                    return [
                        _failure(
                            "codex",
                            "cli_too_old",
                            f"Codex CLI {found} trop ancien : la lecture des limites exige "
                            f"la version {minimum} ou plus récente.",
                        )
                    ]
                return await _codex_exchange(argv, environment, scratch)
    except TimeoutError:
        return [
            _failure(
                "codex",
                "unavailable",
                f"L'app-server Codex n'a pas répondu dans le délai de {timeout:g} s : "
                "quotas non relevés.",
            )
        ]
    except FencedSpawnError as exc:
        if exc.reason == "spawn_error":
            return [_failure("codex", "cli_missing", CODEX_MISSING)]
        return [_failure("codex", "unavailable", CODEX_FENCE_FAILED)]
    except _RpcError as exc:
        return [
            _failure(
                "codex",
                "unavailable",
                f"L'app-server Codex a refusé la lecture ({exc.method}, code {exc.code}) : "
                "quotas non relevés.",
            )
        ]
    except _Closed:
        return [_failure("codex", "unavailable", CODEX_CLOSED)]
    except _CleanupUnconfirmed:
        return [_failure("codex", "unavailable", CODEX_CLEANUP_UNCONFIRMED)]
    except (_Malformed, OSError, ValueError):
        return [_failure("codex", "unavailable", CODEX_MALFORMED)]


# --------------------------------------------------------------------------
# Sonde Claude Code
# --------------------------------------------------------------------------


def _read_snapshot_bytes(path: Path) -> tuple[str, bytes | None]:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_SNAPSHOT_BYTES + 1)
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None
    if len(data) > MAX_SNAPSHOT_BYTES:
        return "too_large", None
    return "ok", data


def claude_report_payload(document: Any) -> dict[str, Any]:
    """Forme du relevé Claude Code, sans valider les bornes (le contrat s'en charge)."""

    if not isinstance(document, dict) or document.get("source") != CLAUDE_SNAPSHOT_SOURCE:
        raise _Malformed
    observed_at = document.get("observed_at")
    windows_document = document.get("windows")
    if not isinstance(observed_at, str) or not isinstance(windows_document, dict):
        raise _Malformed
    known = [key for key in CLAUDE_WINDOW_MINUTES if key in windows_document]
    others = sorted(key for key in windows_document if key not in CLAUDE_WINDOW_MINUTES)
    windows = []
    for key in known + others:
        window = windows_document[key]
        if not isinstance(key, str) or not isinstance(window, dict):
            raise _Malformed
        windows.append(
            {
                "key": key,
                "used_percent": _number_or_none(window.get("used_percentage")),
                "window_minutes": CLAUDE_WINDOW_MINUTES.get(key),
                "resets_at": _epoch(window.get("resets_at")),
            }
        )
    return {
        "provider": "claude_code",
        "status": "ok",
        "source": "claude_code_statusline",
        "plan": None,
        "limit_id": DEFAULT_LIMIT_ID,
        "windows": windows,
        "credits": None,
        "limit_reached": None,
        "reached_type": None,
        "observed_at": observed_at,
        "detail": None,
    }


async def probe_claude_code(config: SubscriptionQuotaConfig) -> SubscriptionQuotaReport:
    """Lit le dernier relevé de la ligne d'état Claude Code ; ne lève jamais."""

    try:
        state, data = await asyncio.to_thread(_read_snapshot_bytes, config.claude_snapshot_path)
        if state == "missing":
            return _failure("claude_code", "unavailable", CLAUDE_MISSING)
        if state == "too_large":
            return _failure("claude_code", "unavailable", CLAUDE_TOO_LARGE)
        if state != "ok" or data is None:
            return _failure("claude_code", "unavailable", CLAUDE_UNREADABLE)
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            return _failure("claude_code", "unavailable", CLAUDE_MALFORMED)
        return _validated(claude_report_payload(document), "Claude Code")
    except _Malformed:
        return _failure("claude_code", "unavailable", CLAUDE_MALFORMED)
    except Exception:  # noqa: BLE001 - une sonde ne fait jamais tomber la boucle
        return _failure("claude_code", "unavailable", CLAUDE_UNREADABLE)


# --------------------------------------------------------------------------
# Lot de relevés
# --------------------------------------------------------------------------


QUOTAS_DISABLED = (
    f"le relevé est désactivé sur ce poste ; {ENABLED_ENV}=1 autorise le lancement de "
    "Codex CLI, qui interroge le serveur d'OpenAI, et la lecture du fichier de la ligne "
    "d'état Claude Code"
)


async def collect_reports(config: SubscriptionQuotaConfig) -> list[dict[str, Any]]:
    """Relevés Codex puis Claude Code, prêts pour ``SubscriptionQuotaBatch``.

    Refuse, sans rien lancer ni lire, tant que le relevé n'est pas autorisé.
    """

    if not config.enabled:
        raise SubscriptionQuotaConfigurationError(QUOTAS_DISABLED)
    codex, claude = await asyncio.gather(probe_codex(config), probe_claude_code(config))
    return [report.model_dump(mode="json") for report in (*codex, claude)]
