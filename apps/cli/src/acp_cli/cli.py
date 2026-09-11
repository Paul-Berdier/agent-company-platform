"""Point d'entrée ``acp`` : orchestration sûre, scriptable et sans magie cachée."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import time
import uuid
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO
from urllib.parse import quote, urlencode

import httpx

from . import __version__
from .client import ACPClient, APIError, NetworkError, ProtocolError, SESSION_COOKIE_NAME
from .config import (
    ConfigError,
    PendingOperation,
    Settings,
    default_config_path,
    load_settings,
    mutate_settings,
    normalized_api_endpoint,
    normalized_origin,
    pending_dispatch_lock,
    settings_with_url_overrides,
)


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    AUTH = 3
    REMOTE = 4
    NETWORK = 5
    UNSUPPORTED = 6
    INTERRUPTED = 130


class UsageError(ValueError):
    pass


class UnsupportedError(RuntimeError):
    pass


class PendingOperationError(RuntimeError):
    """Résultat incertain laissant une mutation récupérable avec la même clé."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        idempotency_key: str,
        error_code: str,
        exit_code: ExitCode,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.idempotency_key = idempotency_key
        self.error_code = error_code
        self.exit_code = exit_code
        self.status_code = status_code

    @property
    def recovery(self) -> str:
        if self.operation == "mission-create":
            return "retry_same_run_command"
        return "retry_same_stop_command"


TERMINAL_MISSION_STATES = {
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
}
TERMINAL_TURN_STATES = {"completed", "failed", "interrupted"}
GLOBAL_FLAGS = {"--json", "--non-interactive"}
GLOBAL_VALUE_FLAGS = {"--api-url", "--web-url", "--config"}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


def _normalize_global_options(argv: Sequence[str]) -> list[str]:
    """Autorise les options globales avant ou après les sous-commandes."""

    front: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value in GLOBAL_FLAGS:
            front.append(value)
            index += 1
            continue
        matched_inline = next(
            (flag for flag in GLOBAL_VALUE_FLAGS if value.startswith(f"{flag}=")),
            None,
        )
        if matched_inline:
            front.append(value)
            index += 1
            continue
        if value in GLOBAL_VALUE_FLAGS:
            if index + 1 >= len(argv):
                # Laisser argparse produire le message canonique.
                front.append(value)
                index += 1
            else:
                front.extend((value, argv[index + 1]))
                index += 2
            continue
        rest.append(value)
        index += 1
    return front + rest


def _add_unsupported_group(subcommands: argparse._SubParsersAction, name: str, actions: Sequence[str]) -> None:
    group = subcommands.add_parser(name, help="commande prévue mais non raccordée")
    nested = group.add_subparsers(dest="unsupported_action", required=True)
    for action in actions:
        parser = nested.add_parser(action)
        parser.add_argument("arguments", nargs=argparse.REMAINDER)
        parser.set_defaults(handler="unsupported", unsupported_name=f"{name} {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="acp", description="Agent Company Platform CLI")
    parser.add_argument("--json", action="store_true", help="sortie JSON stable (NDJSON pour watch)")
    parser.add_argument("--non-interactive", action="store_true", help="interdire toute invite interactive")
    parser.add_argument("--api-url", help="URL de l'API ACP (ou ACP_API_URL)")
    parser.add_argument("--web-url", help="URL de l'interface web (ou ACP_WEB_URL)")
    parser.add_argument("--config", type=Path, help="fichier de configuration (ou ACP_CONFIG_PATH)")
    parser.add_argument("--version", action="version", version=f"acp {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="ouvrir une session")
    login.add_argument("--login", dest="login_name", help="identifiant utilisateur")
    login.add_argument(
        "--password-stdin",
        action="store_true",
        help="lire le mot de passe sur l'entrée standard",
    )
    login.set_defaults(handler="login")

    logout = commands.add_parser("logout", help="révoquer la session locale et serveur")
    logout.set_defaults(handler="logout")

    doctor = commands.add_parser("doctor", help="tester l'API et la session")
    doctor.set_defaults(handler="doctor")

    projects = commands.add_parser("projects", help="gérer les projets")
    project_actions = projects.add_subparsers(dest="project_action", required=True)
    projects_list = project_actions.add_parser("list", help="lister les projets accessibles")
    projects_list.add_argument("--workspace")
    projects_list.add_argument("--department")
    projects_list.set_defaults(handler="projects_list")
    projects_add = project_actions.add_parser("add", help="ajouter un projet")
    projects_add.add_argument("--workspace", required=True)
    projects_add.add_argument("--name", required=True)
    projects_add.add_argument("--department")
    projects_add.add_argument("--type", dest="project_type", default="generic")
    projects_add.add_argument("--description", default="")
    projects_add.set_defaults(handler="projects_add")

    chat = commands.add_parser("chat", help="envoyer un message ponctuel à Hermes")
    chat.add_argument("message", nargs="?", help="message ; sinon lu sur stdin")
    chat.add_argument("--project", required=True)
    chat.add_argument("--conversation", help="réutiliser une conversation")
    chat.add_argument("--title")
    chat.add_argument("--model")
    chat.add_argument("--timeout", type=float, default=120.0)
    chat.add_argument("--poll-interval", type=float, default=1.0)
    chat.set_defaults(handler="chat")

    run = commands.add_parser("run", help="créer et mettre en file une mission")
    run.add_argument("--project", required=True)
    run.add_argument("--goal", required=True)
    run.add_argument("--title")
    run.add_argument("--expected")
    run.add_argument("--accept", action="append", default=[])
    run.add_argument(
        "--autonomy",
        choices=("supervised", "bounded", "autonomous"),
        default="supervised",
    )
    run.add_argument("--allow", action="append", default=[])
    run.add_argument("--forbid", action="append", default=[])
    run.add_argument("--require-approval", action="append", default=[])
    run.add_argument(
        "--resource",
        action="append",
        default=[],
        metavar="KIND=IDENTIFIER[:read|write]",
    )
    run.add_argument("--max-cost", type=float)
    run.add_argument("--currency", default="EUR")
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--max-tool-calls", type=int, default=100)
    run.add_argument("--duration", dest="duration_seconds", type=int, default=3600)
    run.add_argument("--team")
    run.add_argument("--agent")
    run.add_argument("--priority", type=int, choices=range(1, 6))
    run.add_argument("--require-capability", action="append", default=[])
    run.add_argument(
        "--idempotency-key",
        help="fournir une clé stable (sinon reprise pending automatique)",
    )
    run.set_defaults(handler="run")

    runs = commands.add_parser("runs", help="suivre ou arrêter une mission")
    run_actions = runs.add_subparsers(dest="run_action", required=True)
    watch = run_actions.add_parser("watch", help="suivre le run courant d'une mission")
    watch.add_argument("mission_id")
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--timeout", type=float, default=0.0, help="0 = sans limite")
    watch.add_argument("--once", action="store_true")
    watch.set_defaults(handler="runs_watch")
    stop = run_actions.add_parser("stop", help="demander l'arrêt du run courant")
    stop.add_argument("mission_id")
    stop.add_argument("--idempotency-key")
    stop.set_defaults(handler="runs_stop")

    pending = commands.add_parser(
        "pending", help="inspecter ou abandonner une mutation au résultat incertain"
    )
    pending_actions = pending.add_subparsers(dest="pending_action", required=True)
    pending_show = pending_actions.add_parser("show", help="afficher la reprise locale")
    pending_show.set_defaults(handler="pending_show")
    pending_discard = pending_actions.add_parser(
        "discard", help="abandonner explicitement la reprise locale"
    )
    pending_discard.add_argument(
        "--yes",
        action="store_true",
        help="confirmer le risque de dupliquer un effet déjà appliqué",
    )
    pending_discard.set_defaults(handler="pending_discard")

    approvals = commands.add_parser("approvals", help="consulter les approbations")
    approval_actions = approvals.add_subparsers(dest="approval_action", required=True)
    approvals_list = approval_actions.add_parser("list")
    approvals_list.add_argument("--project")
    approvals_list.add_argument("--status")
    approvals_list.set_defaults(handler="approvals_list")

    artifacts = commands.add_parser("artifacts", help="consulter les artefacts")
    artifact_actions = artifacts.add_subparsers(dest="artifact_action", required=True)
    artifacts_list = artifact_actions.add_parser("list")
    artifacts_list.add_argument("--run", required=True)
    artifacts_list.add_argument("--project")
    artifacts_list.set_defaults(handler="artifacts_list")

    open_command = commands.add_parser("open", help="afficher l'URL web d'un run")
    open_command.add_argument("--run", required=True)
    open_command.add_argument(
        "--browser",
        action="store_true",
        help="ouvrir explicitement l'URL dans le navigateur par défaut",
    )
    open_command.set_defaults(handler="open")

    workers = commands.add_parser("workers", help="consulter les workers")
    worker_actions = workers.add_subparsers(dest="worker_action", required=True)
    workers_list = worker_actions.add_parser("list")
    workers_list.set_defaults(handler="workers_list")

    completion = commands.add_parser("completion", help="générer une complétion shell")
    completion.add_argument("shell", choices=("bash", "zsh", "powershell"))
    completion.set_defaults(handler="completion")

    _add_unsupported_group(commands, "mcp", ("add", "test"))
    _add_unsupported_group(commands, "skills", ("search", "install"))
    _add_unsupported_group(commands, "automations", ("list",))
    return parser


def _stream_is_interactive(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def _emit(data: Any, *, as_json: bool, stream: TextIO) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str), file=stream)
    elif isinstance(data, str):
        print(data, file=stream)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stream)


def _emit_error(
    code: str,
    message: str,
    *,
    as_json: bool,
    stream: TextIO,
    status: int | None = None,
) -> None:
    if as_json:
        error: dict[str, Any] = {"code": code, "message": message}
        if status is not None:
            error["status"] = status
        _emit({"error": error}, as_json=True, stream=stream)
    else:
        print(f"Erreur: {message}", file=stream)


def _items(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        return body["items"]
    raise ProtocolError("l'API n'a pas retourné une liste")


def _require_text(value: str | None, label: str) -> str:
    result = (value or "").strip()
    if not result:
        raise UsageError(f"{label} ne peut pas être vide")
    return result


def _parse_resource(value: str) -> dict[str, str]:
    if "=" not in value:
        raise UsageError("--resource attend KIND=IDENTIFIER[:read|write]")
    kind, identifier = value.split("=", 1)
    access = "read"
    if identifier.endswith(":write"):
        identifier = identifier[:-6]
        access = "write"
    elif identifier.endswith(":read"):
        identifier = identifier[:-5]
    kind = kind.strip()
    identifier = identifier.strip()
    if not kind or not identifier:
        raise UsageError("--resource exige un type et un identifiant non vides")
    return {"kind": kind, "identifier": identifier, "access": access, "description": ""}


def _command_idempotency_key(value: str | None, operation: str) -> str:
    if value is None:
        return f"acp-cli:{operation}:{uuid.uuid4()}"
    key = value.strip()
    if (
        not key
        or len(key) > 200
        or any(ord(character) < 33 or ord(character) > 126 for character in key)
    ):
        raise UsageError(
            "--idempotency-key doit contenir 1 à 200 caractères ASCII visibles"
        )
    return key


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_fingerprint(payload: Mapping[str, Any]) -> str:
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise UsageError("le payload de mission ne peut pas être sérialisé canoniquement") from exc
    return _sha256(canonical)


def _principal_session_fingerprints(settings: Settings) -> tuple[str, ...]:
    """Calcule les liaisons sûres du principal et de la session courants.

    Le matériau d'origine n'est jamais persisté dans l'opération pending.
    """

    bindings: list[str] = []
    if settings.principal_id:
        bindings.append(f"principal\0{settings.principal_id}")
    if settings.session_cookie:
        bindings.append(f"session\0{settings.session_cookie}")
    if not bindings:
        bindings.append("anonymous")
    return tuple(_sha256(binding) for binding in bindings)


def _configuration_identity(settings: Settings) -> tuple[str | None, ...]:
    """État persistant qui ne doit pas être écrasé par une réponse obsolète."""

    return (
        normalized_api_endpoint(settings.api_url),
        settings.web_url,
        settings.session_cookie,
        settings.csrf_token,
        settings.session_origin,
        settings.principal_id,
    )


def _reserve_operation(
    selected_settings: Settings,
    config_path: Path,
    *,
    operation: str,
    payload: Mapping[str, Any],
    explicit_key: str | None,
    baseline_settings: Settings | None = None,
) -> tuple[str, Settings, PendingOperation, bool]:
    """Réserve ou reprend après relecture ; l'appelant détient le dispatch-lock."""

    payload_digest = _payload_fingerprint(payload)
    requested_key = (
        _command_idempotency_key(explicit_key, operation)
        if explicit_key is not None
        else None
    )
    expected_settings = baseline_settings or selected_settings

    def reserve(current: Settings):
        if _configuration_identity(current) != _configuration_identity(
            expected_settings
        ):
            raise ConfigError(
                "la configuration ou la session a changé pendant la commande ; "
                "relancez-la"
            )

        request_settings = replace(
            current,
            api_url=selected_settings.api_url,
            web_url=selected_settings.web_url,
        )
        if normalized_origin(current.api_url) != normalized_origin(
            selected_settings.api_url
        ):
            request_settings = request_settings.without_session()

        endpoint = normalized_api_endpoint(request_settings.api_url)
        principal_sessions = _principal_session_fingerprints(request_settings)
        pending = current.pending_operation
        if pending is not None:
            if pending.operation != operation:
                raise UsageError(
                    "une autre opération reste pending ; consultez `acp pending show` "
                    "ou reprenez exactement sa commande"
                )
            if pending.api_endpoint != endpoint:
                raise UsageError(
                    "l'opération pending appartient à un autre endpoint API ; "
                    "consultez `acp pending show`"
                )
            if pending.principal_session_fingerprint not in principal_sessions:
                raise UsageError(
                    "l'opération pending appartient à un autre principal ou une "
                    "autre session ; consultez `acp pending show`"
                )
            if pending.payload_fingerprint != payload_digest:
                raise UsageError(
                    "une autre opération reste pending ; relancez exactement la "
                    "commande initiale ou utilisez `acp pending discard`"
                )
            if requested_key is not None and requested_key != pending.idempotency_key:
                raise UsageError(
                    "--idempotency-key diverge de l'opération pending"
                )
            resumed = replace(pending, dispatch_count=pending.dispatch_count + 1)
            return (
                replace(current, pending_operation=resumed),
                (
                    resumed.idempotency_key,
                    replace(request_settings, pending_operation=resumed),
                    resumed,
                    True,
                ),
            )

        key = requested_key or _command_idempotency_key(None, operation)
        reserved = PendingOperation(
            operation=operation,
            api_endpoint=endpoint,
            principal_session_fingerprint=principal_sessions[0],
            payload_fingerprint=payload_digest,
            idempotency_key=key,
        )
        return (
            replace(current, pending_operation=reserved),
            (
                key,
                replace(request_settings, pending_operation=reserved),
                reserved,
                False,
            ),
        )

    _, (key, request_settings, token, resumed) = mutate_settings(
        config_path,
        reserve,
        environ={},
    )
    return key, request_settings, token, resumed


def _clear_operation(
    config_path: Path,
    token: PendingOperation,
) -> tuple[Settings, bool]:
    """Efface uniquement la réservation terminée, jamais un état plus récent."""

    def clear(current: Settings):
        if current.pending_operation != token:
            return current, False
        return replace(current, pending_operation=None), True

    return mutate_settings(config_path, clear, environ={})


_CERTAIN_REJECTION_STATUSES = {
    400,
    401,
    403,
    404,
    405,
    409,
    410,
    413,
    415,
    422,
}


def _validate_operation_result(
    operation: str,
    payload: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ProtocolError("réponse de mutation incomplète")
    if operation == "mission-create":
        mission_id = result.get("id")
        if not isinstance(mission_id, str) or not mission_id:
            raise ProtocolError("la création n'expose pas d'identifiant de mission")
    elif operation == "mission-stop":
        if result.get("mission_id") != payload["mission_id"]:
            raise ProtocolError("la réponse d'arrêt vise une autre mission")
        run = result.get("run")
        if not isinstance(run, dict) or not isinstance(run.get("id"), str):
            raise ProtocolError("la réponse d'arrêt n'expose pas de tentative")
    else:
        raise ProtocolError("type de mutation inconnu")
    return result


def _pending_error(
    operation: str,
    key: str,
    *,
    error_code: str,
    exit_code: ExitCode,
    status_code: int | None = None,
) -> PendingOperationError:
    action = "acp run" if operation == "mission-create" else "acp runs stop"
    return PendingOperationError(
        f"résultat incertain ; relancez exactement la même commande {action}",
        operation=operation,
        idempotency_key=key,
        error_code=error_code,
        exit_code=exit_code,
        status_code=status_code,
    )


def _execute_pending_operation_locked(
    client: ACPClient,
    config_path: Path,
    *,
    operation: str,
    payload: Mapping[str, Any],
    path: str,
    explicit_key: str | None,
    baseline_settings: Settings | None,
) -> tuple[dict[str, Any], Settings]:
    key, pending_settings, token, resumed = _reserve_operation(
        client.settings,
        config_path,
        operation=operation,
        payload=payload,
        explicit_key=explicit_key,
        baseline_settings=baseline_settings,
    )
    request_client = ACPClient(
        pending_settings,
        transport=client.transport,
        timeout=client.timeout,
    )
    try:
        raw_result = request_client.request(
            "POST",
            path,
            json_body=payload if operation == "mission-create" else None,
            idempotency_key=key,
        )
        result = _validate_operation_result(operation, payload, raw_result)
    except NetworkError as exc:
        raise _pending_error(
            operation,
            key,
            error_code="network",
            exit_code=ExitCode.NETWORK,
        ) from exc
    except APIError as exc:
        if exc.status_code in _CERTAIN_REJECTION_STATUSES and not resumed:
            _, cleared = _clear_operation(config_path, token)
            if cleared:
                raise
        raise _pending_error(
            operation,
            key,
            error_code="api",
            exit_code=(
                ExitCode.AUTH
                if exc.status_code in {401, 403}
                else ExitCode.REMOTE
            ),
            status_code=exc.status_code,
        ) from exc
    except ProtocolError as exc:
        raise _pending_error(
            operation,
            key,
            error_code="client",
            exit_code=ExitCode.REMOTE,
        ) from exc

    cleared_settings, cleared = _clear_operation(config_path, token)
    output = dict(result)
    output["idempotency_key"] = key
    if not cleared:
        output["pending_reconciliation_required"] = True
    return output, cleared_settings


def _execute_pending_operation(
    client: ACPClient,
    config_path: Path,
    *,
    operation: str,
    payload: Mapping[str, Any],
    path: str,
    explicit_key: str | None,
    baseline_settings: Settings | None = None,
) -> tuple[dict[str, Any], Settings]:
    """Réserve, envoie et finalise sous un verrou de dispatch dédié."""

    with pending_dispatch_lock(config_path):
        return _execute_pending_operation_locked(
            client,
            config_path,
            operation=operation,
            payload=payload,
            path=path,
            explicit_key=explicit_key,
            baseline_settings=baseline_settings,
        )


def _handle_run(
    args: argparse.Namespace,
    client: ACPClient,
    config_path: Path,
    baseline_settings: Settings,
) -> tuple[Any, Settings]:
    payload = _mission_payload(args)
    return _execute_pending_operation(
        client,
        config_path,
        operation="mission-create",
        payload=payload,
        path="/missions",
        explicit_key=args.idempotency_key,
        baseline_settings=baseline_settings,
    )


def _handle_stop(
    args: argparse.Namespace,
    client: ACPClient,
    config_path: Path,
    baseline_settings: Settings,
) -> tuple[Any, Settings]:
    payload = {"mission_id": args.mission_id}
    return _execute_pending_operation(
        client,
        config_path,
        operation="mission-stop",
        payload=payload,
        path=f"/missions/{quote(args.mission_id, safe='')}/stop",
        explicit_key=args.idempotency_key,
        baseline_settings=baseline_settings,
    )


def _handle_login(
    args: argparse.Namespace,
    client: ACPClient,
    config_path: Path,
    baseline_settings: Settings,
    stdin: TextIO,
    stdout: TextIO,
    password_reader: Callable[[str], str],
) -> tuple[Any, Settings]:
    login_name = (args.login_name or "").strip()
    if not login_name:
        if args.non_interactive or args.json:
            raise UsageError("--login est requis en mode non interactif")
        print("Identifiant: ", end="", file=stdout, flush=True)
        login_name = stdin.readline().strip()
    if not login_name:
        raise UsageError("l'identifiant ne peut pas être vide")
    if args.password_stdin:
        password = stdin.readline().rstrip("\r\n")
    elif args.non_interactive or args.json:
        raise UsageError("--password-stdin est requis en mode non interactif")
    else:
        password = password_reader("Mot de passe: ")
    if not password:
        raise UsageError("le mot de passe ne peut pas être vide")

    response = client.request_response(
        "POST",
        "/auth/login",
        json_body={"login": login_name, "password": password},
        authenticated=False,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise ProtocolError("l'API a retourné une réponse non JSON") from exc
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("csrf_token"), str)
        or not body["csrf_token"]
    ):
        raise ProtocolError("réponse de connexion incomplète")
    try:
        cookie = response.cookies.get(SESSION_COOKIE_NAME)
    except httpx.CookieConflict as exc:
        raise ProtocolError("plusieurs cookies de session ont été retournés") from exc
    if not cookie:
        raise ProtocolError("cookie de session absent de la réponse")
    user = body.get("user")
    principal_id = user.get("id") if isinstance(user, dict) else None
    if principal_id is not None and not isinstance(principal_id, str):
        raise ProtocolError("identifiant de principal invalide")

    def persist_login(current: Settings):
        if _configuration_identity(current) != _configuration_identity(
            baseline_settings
        ):
            raise ConfigError(
                "la configuration ou la session a changé pendant la connexion ; "
                "la réponse obsolète n'a pas été enregistrée"
            )
        selected = replace(
            current,
            api_url=client.settings.api_url,
            web_url=client.settings.web_url,
        )
        return (
            selected.with_session(
                cookie,
                body["csrf_token"],
                principal_id=principal_id,
            ),
            None,
        )

    updated, _ = mutate_settings(
        config_path,
        persist_login,
        environ={},
    )
    result = {
        "authenticated": True,
        "api_url": updated.api_url,
        "user": body.get("user"),
        "expires_at": body.get("expires_at"),
    }
    return result, updated


def _handle_doctor(client: ACPClient, config_path: Path) -> tuple[Any, Settings]:
    status = client.request("GET", "/auth/status", authenticated=False)
    result: dict[str, Any] = {
        "api_url": client.settings.api_url,
        "api_reachable": True,
        "authenticated": False,
        "auth": status,
    }
    updated = client.settings
    if client.settings.authenticated:
        session = client.request("GET", "/auth/session")
        if (
            not isinstance(session, dict)
            or not isinstance(session.get("csrf_token"), str)
            or not session["csrf_token"]
        ):
            raise ProtocolError("réponse de session incomplète")
        user = session.get("user")
        principal_id = user.get("id") if isinstance(user, dict) else None
        if principal_id is not None and not isinstance(principal_id, str):
            raise ProtocolError("identifiant de principal invalide")
        expected_origin = normalized_origin(client.settings.api_url)
        expected_cookie = client.settings.session_cookie

        def refresh(current: Settings):
            if (
                normalized_origin(current.api_url) != expected_origin
                or current.session_cookie != expected_cookie
            ):
                return current, False
            return (
                replace(
                    current,
                    csrf_token=session["csrf_token"],
                    principal_id=principal_id or current.principal_id,
                ),
                True,
            )

        updated, _ = mutate_settings(
            config_path,
            refresh,
            environ={},
        )
        result["authenticated"] = True
        result["user"] = session.get("user")
        result["expires_at"] = session.get("expires_at")
    return result, updated


def _handle_logout(client: ACPClient, config_path: Path) -> tuple[Any, Settings]:
    result = client.request("POST", "/auth/logout")
    expected_origin = normalized_origin(client.settings.api_url)
    expected_cookie = client.settings.session_cookie

    def clear_session(current: Settings):
        if (
            normalized_origin(current.api_url) != expected_origin
            or current.session_cookie != expected_cookie
        ):
            return current, False
        return current.without_session(), True

    updated, _ = mutate_settings(config_path, clear_session, environ={})
    return result or {"authenticated": False}, updated


def _pending_summary(pending: PendingOperation | None) -> dict[str, Any]:
    if pending is None:
        return {"pending": False}
    return {
        "pending": True,
        "operation": pending.operation,
        "api_endpoint": pending.api_endpoint,
        "idempotency_key": pending.idempotency_key,
        "payload_fingerprint": pending.payload_fingerprint,
        "dispatch_count": pending.dispatch_count,
        "recovery": (
            "retry_same_run_command"
            if pending.operation == "mission-create"
            else "retry_same_stop_command"
        ),
    }


def _handle_pending_discard(
    args: argparse.Namespace,
    settings: Settings,
    config_path: Path,
    stdin: TextIO,
    stdout: TextIO,
) -> tuple[Any, Settings]:
    expected = settings.pending_operation
    if expected is None:
        return {"discarded": False, "pending": False}, settings

    if not args.yes:
        if args.non_interactive or args.json:
            raise UsageError(
                "--yes est requis sans invite interactive pour abandonner un pending"
            )
        print(
            "Abandonner cette reprise peut dupliquer un effet déjà appliqué. "
            "Confirmer [oui/N] : ",
            end="",
            file=stdout,
            flush=True,
        )
        answer = stdin.readline().strip().casefold()
        if answer not in {"o", "oui", "y", "yes"}:
            return {"discarded": False, **_pending_summary(expected)}, settings

    def discard(current: Settings):
        if current.pending_operation != expected:
            raise UsageError(
                "l'opération pending a changé ; relancez `acp pending show`"
            )
        return replace(current, pending_operation=None), True

    with pending_dispatch_lock(config_path):
        updated, discarded = mutate_settings(config_path, discard, environ={})
    return {
        "discarded": discarded,
        "operation": expected.operation,
        "idempotency_key": expected.idempotency_key,
        "pending": False,
    }, updated


def _handle_chat(
    args: argparse.Namespace,
    client: ACPClient,
    stdin: TextIO,
    stdout: TextIO,
    sleep: Callable[[float], None],
) -> Any:
    message = args.message
    if message is None and not _stream_is_interactive(stdin):
        message = stdin.read()
    if message is None:
        if args.non_interactive or args.json:
            raise UsageError("un message ou une entrée standard est requis")
        print("Message: ", end="", file=stdout, flush=True)
        message = stdin.readline()
    message = _require_text(message, "le message")
    if args.timeout <= 0 or args.poll_interval <= 0:
        raise UsageError("--timeout et --poll-interval doivent être positifs")

    conversation_id = args.conversation
    if conversation_id is None:
        title = args.title or message.splitlines()[0][:120]
        conversation = client.request(
            "POST",
            "/conversations",
            json_body={"project_id": args.project, "title": title},
        )
        if not isinstance(conversation, dict) or not conversation.get("id"):
            raise ProtocolError("la conversation créée n'a pas d'identifiant")
        conversation_id = str(conversation["id"])

    turn = client.request(
        "POST",
        f"/conversations/{quote(conversation_id, safe='')}/turns",
        json_body={
            "client_request_id": str(uuid.uuid4()),
            "content": message,
            "model": args.model,
        },
    )
    if not isinstance(turn, dict) or not turn.get("id"):
        raise ProtocolError("le message créé n'a pas d'identifiant")
    deadline = time.monotonic() + args.timeout
    while turn.get("status") not in TERMINAL_TURN_STATES:
        if time.monotonic() >= deadline:
            raise ProtocolError(
                f"délai dépassé ; le run continue dans la conversation {conversation_id}"
            )
        sleep(args.poll_interval)
        turn = client.request(
            "GET",
            f"/conversations/{quote(conversation_id, safe='')}/turns/{quote(str(turn['id']), safe='')}",
        )
        if not isinstance(turn, dict):
            raise ProtocolError("statut de message invalide")
    return {"conversation_id": conversation_id, "turn": turn}


def _mission_payload(args: argparse.Namespace) -> dict[str, Any]:
    goal = _require_text(args.goal, "--goal")
    if args.duration_seconds < 1:
        raise UsageError("--duration doit être positif")
    if args.max_cost is not None and args.max_cost < 0:
        raise UsageError("--max-cost ne peut pas être négatif")
    if args.max_tokens is not None and args.max_tokens < 0:
        raise UsageError("--max-tokens ne peut pas être négatif")
    if args.max_tool_calls is not None and args.max_tool_calls < 0:
        raise UsageError("--max-tool-calls ne peut pas être négatif")
    budget = {
        "max_cost": args.max_cost,
        "currency": args.currency.upper(),
        "max_tokens": args.max_tokens,
        "max_tool_calls": args.max_tool_calls,
    }
    payload: dict[str, Any] = {
        "project_id": args.project,
        "title": (args.title or goal.splitlines()[0][:300]).strip(),
        "objective": goal,
        "expected_outcome": (args.expected or goal).strip(),
        "acceptance_criteria": args.accept
        or ["Résultat accompagné de preuves vérifiables et conforme à l'objectif."],
        "autonomy": {
            "mode": args.autonomy,
            "allowed_actions": args.allow,
            "forbidden_actions": args.forbid,
            "approval_required_actions": args.require_approval,
        },
        "resources": [_parse_resource(item) for item in args.resource],
        "budget": budget,
        "duration_seconds": args.duration_seconds,
    }
    if args.priority is not None:
        payload["priority"] = args.priority
    if args.require_capability:
        payload["required_capabilities"] = args.require_capability
    if args.team:
        payload["team_id"] = args.team
    if args.agent:
        payload["agent_instance_id"] = args.agent
    return payload


def _current_run(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        raise ProtocolError("détail de mission invalide")
    run = detail.get("current_run")
    if not isinstance(run, dict):
        raise ProtocolError("la mission n'expose pas de run courant")
    return run


def _handle_watch(
    args: argparse.Namespace,
    client: ACPClient,
    *,
    as_json: bool,
    stdout: TextIO,
    sleep: Callable[[float], None],
) -> None:
    if args.interval <= 0:
        raise UsageError("--interval doit être positif")
    if args.timeout < 0:
        raise UsageError("--timeout ne peut pas être négatif")
    started = time.monotonic()
    last_serialized: str | None = None
    while True:
        detail = client.request(
            "GET", f"/missions/{quote(args.mission_id, safe='')}"
        )
        run = _current_run(detail)
        snapshot = {
            "mission_id": args.mission_id,
            "run": run,
        }
        serialized = json.dumps(snapshot, sort_keys=True, default=str)
        if serialized != last_serialized:
            _emit(snapshot, as_json=as_json, stream=stdout)
            last_serialized = serialized
        if args.once or run.get("status") in TERMINAL_MISSION_STATES:
            return
        if args.timeout and time.monotonic() - started >= args.timeout:
            raise ProtocolError("délai de suivi dépassé ; la mission continue")
        sleep(args.interval)


def _completion_script(shell: str) -> str:
    commands = (
        "login logout doctor projects chat run runs pending approvals artifacts open workers "
        "mcp skills automations completion"
    )
    if shell == "bash":
        return f'complete -W "{commands}" acp'
    if shell == "zsh":
        return f'#compdef acp\n_arguments "1:commande:({commands})"'
    return (
        "Register-ArgumentCompleter -Native -CommandName acp -ScriptBlock {\n"
        "  param($wordToComplete)\n"
        f'  "{commands}".Split(" ") | Where-Object {{ $_ -like "$wordToComplete*" }}\n'
        "}"
    )


def _dispatch(
    args: argparse.Namespace,
    client: ACPClient,
    config_path: Path,
    baseline_settings: Settings,
    *,
    stdin: TextIO,
    stdout: TextIO,
    password_reader: Callable[[str], str],
    sleep: Callable[[float], None],
    browser_open: Callable[[str], Any],
) -> tuple[bool, Any, Settings]:
    handler = args.handler
    if handler == "login":
        result, settings = _handle_login(
            args,
            client,
            config_path,
            baseline_settings,
            stdin,
            stdout,
            password_reader,
        )
        return True, result, settings
    if handler == "logout":
        result, settings = _handle_logout(client, config_path)
        return True, result, settings
    if handler == "doctor":
        result, settings = _handle_doctor(client, config_path)
        return True, result, settings
    if handler == "projects_list":
        params = {"workspace_id": args.workspace, "department_id": args.department}
        return True, client.request("GET", "/projects", params={k: v for k, v in params.items() if v}), client.settings
    if handler == "projects_add":
        body = {
            "workspace_id": args.workspace,
            "department_id": args.department,
            "name": args.name,
            "project_type": args.project_type,
            "description": args.description,
        }
        return True, client.request("POST", "/projects", json_body=body), client.settings
    if handler == "chat":
        return True, _handle_chat(args, client, stdin, stdout, sleep), client.settings
    if handler == "run":
        result, settings = _handle_run(
            args, client, config_path, baseline_settings
        )
        return True, result, settings
    if handler == "runs_watch":
        _handle_watch(args, client, as_json=args.json, stdout=stdout, sleep=sleep)
        return False, None, client.settings
    if handler == "runs_stop":
        result, settings = _handle_stop(
            args, client, config_path, baseline_settings
        )
        return True, result, settings
    if handler == "pending_show":
        return True, _pending_summary(client.settings.pending_operation), client.settings
    if handler == "pending_discard":
        result, settings = _handle_pending_discard(
            args,
            client.settings,
            config_path,
            stdin,
            stdout,
        )
        return True, result, settings
    if handler == "approvals_list":
        params = {"project_id": args.project, "status": args.status}
        return True, client.request("GET", "/approvals", params={k: v for k, v in params.items() if v}), client.settings
    if handler == "artifacts_list":
        params = {"task_run_id": args.run, "project_id": args.project}
        body = client.request("GET", "/artifacts", params={k: v for k, v in params.items() if v})
        filtered = [
            artifact
            for artifact in _items(body)
            if not isinstance(artifact, dict) or artifact.get("task_run_id") == args.run
        ]
        return True, filtered, client.settings
    if handler == "open":
        url = f"{client.settings.web_url}/missions?{urlencode({'run': args.run})}"
        opened = False
        if args.browser:
            opened = bool(browser_open(url))
            if not opened:
                raise ProtocolError("le navigateur n'a pas accepté l'ouverture de l'URL")
        return True, {"run_id": args.run, "url": url, "opened": opened}, client.settings
    if handler == "workers_list":
        return True, client.request("GET", "/workers"), client.settings
    if handler == "completion":
        return True, _completion_script(args.shell), client.settings
    if handler == "unsupported":
        raise UnsupportedError(
            f"`acp {args.unsupported_name}` n'est pas encore raccordé à l'API de cette version"
        )
    raise UsageError("commande inconnue")


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
    password_reader: Callable[[str], str] = getpass.getpass,
    sleep: Callable[[float], None] = time.sleep,
    browser_open: Callable[[str], Any] = webbrowser.open,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    env = os.environ if environ is None else environ
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized = _normalize_global_options(raw_argv)
    parser = build_parser()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                args = parser.parse_args(normalized)
            except SystemExit as exc:
                # ``--help`` et ``--version`` gardent le comportement argparse,
                # tout en restant testables via les flux injectés.
                return int(exc.code or 0)
        config_path = args.config or default_config_path(env)
        baseline_settings = load_settings(config_path, environ={})
        settings = settings_with_url_overrides(
            baseline_settings,
            environ=env,
            api_url=args.api_url,
            web_url=args.web_url,
        )
        client = ACPClient(settings, transport=transport)
        should_emit, result, _ = _dispatch(
            args,
            client,
            config_path,
            baseline_settings,
            stdin=input_stream,
            stdout=out,
            password_reader=password_reader,
            sleep=sleep,
            browser_open=browser_open,
        )
        if should_emit:
            if args.handler == "chat" and not args.json:
                turn = result.get("turn", {}) if isinstance(result, dict) else {}
                content = turn.get("assistant_content") if isinstance(turn, dict) else None
                _emit(content or result, as_json=False, stream=out)
            elif args.handler == "open" and not args.json:
                _emit(result["url"], as_json=False, stream=out)
            else:
                _emit(result, as_json=args.json, stream=out)
        return int(ExitCode.OK)
    except UsageError as exc:
        as_json = "--json" in raw_argv
        _emit_error("usage", str(exc), as_json=as_json, stream=err)
        return int(ExitCode.USAGE)
    except UnsupportedError as exc:
        as_json = "--json" in raw_argv
        _emit_error("unsupported", str(exc), as_json=as_json, stream=err)
        return int(ExitCode.UNSUPPORTED)
    except PendingOperationError as exc:
        as_json = "--json" in raw_argv
        if as_json:
            error: dict[str, Any] = {
                "code": exc.error_code,
                "message": str(exc),
                "operation": exc.operation,
                "idempotency_key": exc.idempotency_key,
                "recovery": exc.recovery,
            }
            if exc.status_code is not None:
                error["status"] = exc.status_code
            _emit({"error": error}, as_json=True, stream=err)
        else:
            status = f", HTTP {exc.status_code}" if exc.status_code is not None else ""
            print(
                f"Erreur: {exc} (Idempotency-Key: {exc.idempotency_key}{status})",
                file=err,
            )
        return int(exc.exit_code)
    except APIError as exc:
        code = ExitCode.AUTH if exc.status_code in {401, 403} else ExitCode.REMOTE
        as_json = "--json" in raw_argv
        _emit_error("api", exc.detail, as_json=as_json, stream=err, status=exc.status_code)
        return int(code)
    except NetworkError as exc:
        as_json = "--json" in raw_argv
        _emit_error("network", str(exc), as_json=as_json, stream=err)
        return int(ExitCode.NETWORK)
    except (ConfigError, ProtocolError) as exc:
        as_json = "--json" in raw_argv
        _emit_error("client", str(exc), as_json=as_json, stream=err)
        return int(ExitCode.REMOTE)
    except KeyboardInterrupt:
        as_json = "--json" in raw_argv
        _emit_error(
            "interrupted",
            "suivi interrompu localement ; aucun arrêt de mission n'a été demandé",
            as_json=as_json,
            stream=err,
        )
        return int(ExitCode.INTERRUPTED)
