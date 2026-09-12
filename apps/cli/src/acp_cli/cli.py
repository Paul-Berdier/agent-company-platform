"""Point d'entrée ``acp`` : orchestration sûre, scriptable et sans magie cachée."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO
from urllib.parse import quote, urlencode, urlsplit

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


class CommandError(RuntimeError):
    """Échec métier explicite : ni une erreur d'usage, ni une erreur de transport.

    Le message est déjà rédigé pour l'utilisateur ; ``code`` identifie la cause
    de façon stable pour les scripts (`--json`).
    """

    def __init__(self, code: str, message: str, exit_code: ExitCode = ExitCode.REMOTE) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


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

# Miroirs locaux des motifs de ``acp_contracts`` (le CLI ne dépend pas des contrats) :
# ils permettent un refus immédiat, avant tout appel réseau. Le serveur revalide.
SECRET_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,62}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")
GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
GITHUB_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
WINDOWS_ABSOLUTE_PATTERN = re.compile("^[A-Za-z]:[\\\\/]")

MCP_EXPORT_FORMATS = ("hermes", "claude", "codex")
MCP_TIMEOUT_RANGE = (1, 120)
TERMINAL_PROBE_STATES = {
    "succeeded",
    "failed",
    "rejected",
    "expired",
    "invalidated",
    "cancelled",
}
PENDING_PROBE_STATES = {"pending_approval", "queued", "claimed"}
KNOWN_PROBE_STATES = TERMINAL_PROBE_STATES | PENDING_PROBE_STATES
MAX_SKILL_ARCHIVE_BYTES = 25 * 1024 * 1024


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


DASH_TOLERANT_VALUE_FLAGS = {"--arg"}


def _command_group(argv: Sequence[str]) -> str | None:
    """Premier jeton qui n'est ni une option globale ni la valeur de l'une d'elles."""

    index = 0
    while index < len(argv):
        token = argv[index]
        if token in GLOBAL_VALUE_FLAGS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _attach_dash_tolerant_values(argv: Sequence[str]) -> list[str]:
    """Accole la valeur des options qui acceptent légitimement un tiret initial.

    `acp mcp add --command /usr/bin/npx --arg -y --arg --json` transmet « -y » et
    « --json » comme arguments du programme MCP : ni argparse ni la normalisation
    des options globales ne doivent les réinterpréter. La réécriture est donc
    appliquée avant tout, et restreinte au seul groupe qui déclare `--arg`.
    """

    if _command_group(argv) != "mcp":
        return list(argv)
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in DASH_TOLERANT_VALUE_FLAGS and index + 1 < len(argv):
            normalized.append(f"{token}={argv[index + 1]}")
            index += 2
            continue
        normalized.append(token)
        index += 1
    return normalized


def _add_unsupported_group(subcommands: argparse._SubParsersAction, name: str, actions: Sequence[str]) -> None:
    group = subcommands.add_parser(name, help="commande prévue mais non raccordée")
    nested = group.add_subparsers(dest="unsupported_action", required=True)
    for action in actions:
        parser = nested.add_parser(action)
        parser.add_argument("arguments", nargs=argparse.REMAINDER)
        parser.set_defaults(handler="unsupported", unsupported_name=f"{name} {action}")


def _add_secrets_group(commands: argparse._SubParsersAction) -> None:
    """`acp secrets` : la valeur d'un secret n'est jamais acceptée en argument."""

    secrets = commands.add_parser("secrets", help="gérer les secrets chiffrés côté serveur")
    actions = secrets.add_subparsers(dest="secret_action", required=True)

    status = actions.add_parser("status", help="état du coffre de secrets")
    status.set_defaults(handler="secrets_status")

    listing = actions.add_parser("list", help="lister les secrets (jamais leurs valeurs)")
    listing.set_defaults(handler="secrets_list")

    setter = actions.add_parser("set", help="créer un secret (valeur lue sur l'entrée standard)")
    setter.add_argument("name")
    # Ces deux entrées n'existent que pour refuser explicitement une valeur en clair.
    setter.add_argument("forbidden_value", nargs="?", help=argparse.SUPPRESS)
    setter.add_argument("--value", help=argparse.SUPPRESS)
    setter.add_argument(
        "--value-stdin",
        action="store_true",
        help="lire la valeur sur l'entrée standard (obligatoire)",
    )
    setter.add_argument("--project", help="portée projet au lieu de la portée plateforme")
    setter.add_argument("--description", default="")
    setter.set_defaults(handler="secrets_set")

    rotate = actions.add_parser("rotate", help="remplacer la valeur d'un secret")
    rotate.add_argument("secret_id")
    rotate.add_argument("forbidden_value", nargs="?", help=argparse.SUPPRESS)
    rotate.add_argument("--value", help=argparse.SUPPRESS)
    rotate.add_argument(
        "--value-stdin",
        action="store_true",
        help="lire la nouvelle valeur sur l'entrée standard (obligatoire)",
    )
    rotate.set_defaults(handler="secrets_rotate")

    revoke = actions.add_parser("revoke", help="révoquer un secret")
    revoke.add_argument("secret_id")
    revoke.set_defaults(handler="secrets_revoke")


def _add_mcp_config_options(parser: argparse.ArgumentParser) -> None:
    """Options communes à `acp mcp add` et `acp mcp update` (configuration complète)."""

    parser.add_argument("--url", help="endpoint MCP Streamable HTTP (transport http)")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="K=V|K=@SECRET_ID",
        help="en-tête littéral, ou référence de secret avec @",
    )
    parser.add_argument("--command", help="chemin absolu de l'exécutable (transport stdio)")
    parser.add_argument("--arg", action="append", default=[], help="argument de la commande stdio")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="K=V|K=@SECRET_ID",
        help="variable d'environnement littérale, ou référence de secret avec @",
    )
    parser.add_argument("--cwd", help="répertoire de travail du transport stdio")
    parser.add_argument("--runner", help="worker autorisé à lancer le transport stdio")
    parser.add_argument("--timeout", type=int, help="délai d'appel en secondes (1 à 120)")
    parser.add_argument("--note", default="", help="note attachée à la révision")


def _add_mcp_group(commands: argparse._SubParsersAction) -> None:
    """`acp mcp` : catalogue, révisions, sondes, liaisons et export."""

    mcp = commands.add_parser("mcp", help="gérer les serveurs MCP")
    actions = mcp.add_subparsers(dest="mcp_action", required=True)

    catalog = actions.add_parser("catalog", help="catalogue de serveurs vérifiés")
    catalog.set_defaults(handler="mcp_catalog")

    add = actions.add_parser("add", help="déclarer un serveur MCP (révision 1, statut draft)")
    add.add_argument("name", help="identifiant court (slug)")
    add.add_argument("--display", help="nom affiché (défaut : le slug)")
    add.add_argument("--description", default="")
    _add_mcp_config_options(add)
    add.set_defaults(handler="mcp_add")

    update = actions.add_parser("update", help="créer une nouvelle révision de configuration")
    update.add_argument("server_id")
    _add_mcp_config_options(update)
    update.set_defaults(handler="mcp_update")

    listing = actions.add_parser("list", help="lister les serveurs MCP")
    listing.add_argument("--status")
    listing.set_defaults(handler="mcp_list")

    show = actions.add_parser("show", help="détail d'un serveur MCP")
    show.add_argument("server_id")
    show.set_defaults(handler="mcp_show")

    tools = actions.add_parser("tools", help="outils découverts sur la révision courante")
    tools.add_argument("server_id")
    tools.set_defaults(handler="mcp_tools")

    test = actions.add_parser("test", help="lancer une sonde de découverte")
    test.add_argument("server_id")
    test.add_argument("--wait", action="store_true", help="attendre un état terminal")
    test.add_argument("--interval", type=float, default=2.0, help="intervalle d'interrogation")
    test.add_argument("--timeout", type=float, default=0.0, help="0 = sans limite")
    test.set_defaults(handler="mcp_test")

    probes = actions.add_parser("probes", help="consulter et décider des sondes")
    probe_actions = probes.add_subparsers(dest="probe_action", required=True)
    probes_list = probe_actions.add_parser("list", help="lister les sondes")
    probes_list.add_argument("--server")
    probes_list.add_argument("--status")
    probes_list.set_defaults(handler="mcp_probes_list")
    probes_show = probe_actions.add_parser("show", help="détail d'une sonde")
    probes_show.add_argument("probe_id")
    probes_show.set_defaults(handler="mcp_probes_show")
    probes_approve = probe_actions.add_parser("approve", help="autoriser une sonde stdio")
    probes_approve.add_argument("probe_id")
    probes_approve.add_argument("--comment", default="")
    probes_approve.set_defaults(handler="mcp_probes_decide", decision="approved")
    probes_reject = probe_actions.add_parser("reject", help="refuser une sonde stdio")
    probes_reject.add_argument("probe_id")
    probes_reject.add_argument("--comment", default="")
    probes_reject.set_defaults(handler="mcp_probes_decide", decision="rejected")

    bind = actions.add_parser("bind", help="autoriser un serveur sur un projet")
    bind.add_argument("server_id")
    bind.add_argument("--project", required=True)
    bind.add_argument("--tool", action="append", default=[], help="outil autorisé (répétable)")
    bind.set_defaults(handler="mcp_bind")

    bindings = actions.add_parser("bindings", help="lister les liaisons MCP")
    bindings.add_argument("--project")
    bindings.add_argument("--server")
    bindings.set_defaults(handler="mcp_bindings")

    unbind = actions.add_parser("unbind", help="révoquer une liaison MCP")
    unbind.add_argument("binding_id")
    unbind.set_defaults(handler="mcp_unbind")

    activate = actions.add_parser("activate", help="activer la révision courante")
    activate.add_argument("server_id")
    activate.set_defaults(handler="mcp_activate")

    disable = actions.add_parser("disable", help="désactiver un serveur (réversible)")
    disable.add_argument("server_id")
    disable.set_defaults(handler="mcp_disable")

    revoke = actions.add_parser("revoke", help="révoquer un serveur (irréversible)")
    revoke.add_argument("server_id")
    revoke.add_argument("--reason", help="motif conservé dans l'audit")
    revoke.set_defaults(handler="mcp_revoke")

    rollback = actions.add_parser("rollback", help="revenir à une révision antérieure")
    rollback.add_argument("server_id")
    rollback.add_argument("--revision", type=int, help="numéro de révision cible")
    rollback.add_argument("--note", default="")
    rollback.set_defaults(handler="mcp_rollback")

    export = actions.add_parser("export", help="exporter la configuration MCP")
    export.add_argument("--format", dest="export_format", choices=MCP_EXPORT_FORMATS, required=True)
    export.add_argument("--project")
    export.set_defaults(handler="mcp_export")

    # `acp mcp import` est prévu par la spécification mais pas encore raccordé :
    # le sous-groupe reste déclaré pour éviter une erreur d'usage trompeuse.
    importer = actions.add_parser("import", help="commande prévue mais non raccordée")
    importer.add_argument("arguments", nargs=argparse.REMAINDER)
    importer.set_defaults(handler="unsupported", unsupported_name="mcp import")


def _add_skills_group(commands: argparse._SubParsersAction) -> None:
    """`acp skills` : bibliothèque, révisions, approbations et liaisons."""

    skills = commands.add_parser("skills", help="gérer la bibliothèque de skills")
    actions = skills.add_subparsers(dest="skill_action", required=True)

    search = actions.add_parser("search", help="chercher parmi les skills installés et le catalogue")
    search.add_argument("query")
    search.set_defaults(handler="skills_search")

    catalog = actions.add_parser("catalog", help="catalogue de skills vérifiés")
    catalog.set_defaults(handler="skills_catalog")

    listing = actions.add_parser("list", help="lister les skills installés")
    listing.set_defaults(handler="skills_list")

    show = actions.add_parser("show", help="détail d'un skill")
    show.add_argument("skill_id")
    show.set_defaults(handler="skills_show")

    files = actions.add_parser("files", help="lister les fichiers d'une révision")
    files.add_argument("skill_id")
    files.add_argument("--revision", type=int)
    files.set_defaults(handler="skills_files")

    cat = actions.add_parser("cat", help="afficher un fichier texte d'une révision")
    cat.add_argument("skill_id")
    cat.add_argument("path")
    cat.add_argument("--revision", type=int)
    cat.set_defaults(handler="skills_cat")

    install = actions.add_parser("install", help="installer un skill depuis une source")
    install.add_argument(
        "source",
        help="dir:/chemin | archive:/chemin.zip | github:owner/repo@SHA[:chemin] | skill-md:/chemin/SKILL.md",
    )
    install.add_argument("--name")
    install.add_argument("--note", default="")
    install.set_defaults(handler="skills_install")

    update = actions.add_parser("update", help="créer une révision depuis une source")
    update.add_argument("skill_id")
    update.add_argument("source")
    update.add_argument("--note", default="")
    update.set_defaults(handler="skills_update")

    approve = actions.add_parser("approve", help="approuver une révision qui l'exige")
    approve.add_argument("skill_id")
    approve.add_argument("--revision", type=int)
    approve.add_argument("--comment", default="")
    approve.set_defaults(handler="skills_approve")

    activate = actions.add_parser("activate", help="activer la révision courante")
    activate.add_argument("skill_id")
    activate.set_defaults(handler="skills_activate")

    disable = actions.add_parser("disable", help="désactiver un skill (réversible)")
    disable.add_argument("skill_id")
    disable.set_defaults(handler="skills_disable")

    revoke = actions.add_parser("revoke", help="révoquer un skill (irréversible)")
    revoke.add_argument("skill_id")
    revoke.add_argument("--reason")
    revoke.set_defaults(handler="skills_revoke")

    rollback = actions.add_parser("rollback", help="revenir à une révision antérieure")
    rollback.add_argument("skill_id")
    rollback.add_argument("--revision", type=int)
    rollback.add_argument("--note", default="")
    rollback.set_defaults(handler="skills_rollback")

    bind = actions.add_parser("bind", help="autoriser un skill sur un projet")
    bind.add_argument("skill_id")
    bind.add_argument("--project", required=True)
    bind.set_defaults(handler="skills_bind")

    bindings = actions.add_parser("bindings", help="lister les liaisons de skills")
    bindings.add_argument("--project")
    bindings.add_argument("--skill")
    bindings.set_defaults(handler="skills_bindings")

    unbind = actions.add_parser("unbind", help="révoquer une liaison de skill")
    unbind.add_argument("binding_id")
    unbind.set_defaults(handler="skills_unbind")


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
    projects_extensions = project_actions.add_parser(
        "extensions", help="extensions MCP et skills résolues pour un projet"
    )
    projects_extensions.add_argument("project_id")
    projects_extensions.set_defaults(handler="projects_extensions")

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

    _add_secrets_group(commands)
    _add_mcp_group(commands)
    _add_skills_group(commands)
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


def _emit_notice(code: str, message: str, *, as_json: bool, stream: TextIO) -> None:
    """Avis non bloquant : reste lisible par machine lorsque `--json` est demandé."""

    if as_json:
        _emit({"notice": {"code": code, "message": message}}, as_json=True, stream=stream)
    else:
        print(message, file=stream)


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


def _path_segment(value: str) -> str:
    """Encode un identifiant en un seul segment de chemin, jamais vide.

    Un identifiant vide construirait l'URL d'une collection (`/secrets/`) au lieu
    de celle d'une ressource : la commande est refusée avant tout appel.
    """

    identifier = str(value).strip()
    if not identifier:
        raise UsageError("l'identifiant ne peut pas être vide")
    return quote(identifier, safe="")


def _filtered_params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value}


def _targets_secrets(argv: Sequence[str]) -> bool:
    """Indique si la ligne de commande vise le groupe `secrets`.

    Seul ce groupe peut transporter du matériel secret : la censure des messages
    d'usage y est appliquée, sans dégrader la lisibilité des autres commandes.
    """

    return _command_group(argv) == "secrets"


def _mask_secret_material(message: str, argv: Sequence[str]) -> str:
    """Remplace toute valeur accolée à un `=` par `***` dans un message d'usage.

    argparse cite l'argument fautif ; sur le groupe `secrets`, cette citation
    pourrait recopier une valeur en clair dans stderr ou dans un journal.
    """

    if not _targets_secrets(argv):
        return message
    masked = re.sub(r"(?<==)\S+", "***", message)
    return re.sub(
        r"unrecognized arguments:.*",
        "arguments surnuméraires : utilisez --value-stdin, jamais un argument, "
        "pour la valeur d'un secret",
        masked,
        flags=re.DOTALL,
    )


def _refuse_secret_value_arguments(args: argparse.Namespace) -> None:
    """Refuse toute valeur de secret passée en argument, sans jamais la répéter."""

    if getattr(args, "forbidden_value", None) is not None or getattr(args, "value", None) is not None:
        raise UsageError(
            "la valeur d'un secret ne se passe jamais en argument : utilisez --value-stdin"
        )


def _read_secret_value(args: argparse.Namespace, stdin: TextIO) -> str:
    """Lit la valeur sur l'entrée standard en retirant un seul saut de ligne final."""

    if not args.value_stdin:
        raise UsageError(
            "--value-stdin est obligatoire : la valeur d'un secret n'est jamais passée en argument"
        )
    raw = stdin.read()
    if raw.endswith("\n"):
        raw = raw[:-1]
        if raw.endswith("\r"):
            raw = raw[:-1]
    if not raw.strip():
        raise UsageError("la valeur lue sur l'entrée standard est vide")
    return raw


def _secret_scope(project: str | None) -> dict[str, Any]:
    if project:
        return {"scope_type": "project", "project_id": project}
    return {"scope_type": "platform", "project_id": None}


def _handle_secrets_set(args: argparse.Namespace, client: ACPClient, stdin: TextIO) -> Any:
    _refuse_secret_value_arguments(args)
    project = _optional_option_text(args.project, "--project")
    name = _require_text(args.name, "le nom du secret")
    if not SECRET_NAME_PATTERN.match(name):
        raise UsageError(
            "le nom d'un secret doit respecter ^[A-Z][A-Z0-9_]{1,62}$ (majuscules, chiffres, tirets bas)"
        )
    value = _read_secret_value(args, stdin)
    body = {
        "name": name,
        "value": value,
        "description": args.description,
        **_secret_scope(project),
    }
    return client.request("POST", "/secrets", json_body=body)


def _handle_secrets_rotate(args: argparse.Namespace, client: ACPClient, stdin: TextIO) -> Any:
    _refuse_secret_value_arguments(args)
    value = _read_secret_value(args, stdin)
    return client.request(
        "POST",
        f"/secrets/{_path_segment(args.secret_id)}/rotate",
        json_body={"value": value},
    )


def _require_option_text(value: str | None, option: str) -> str:
    if value is None:
        raise UsageError(f"{option} est obligatoire")
    text = value.strip()
    if not text:
        raise UsageError(f"{option} ne peut pas être vide")
    return text


def _optional_option_text(value: str | None, option: str) -> str | None:
    """Normalise une option facultative : absente, ou non vide après nettoyage."""

    if value is None:
        return None
    text = value.strip()
    if not text:
        raise UsageError(f"{option} ne peut pas être vide")
    return text


def _require_revision_number(value: int | None) -> int:
    if value is None:
        raise UsageError("--revision est obligatoire")
    if value < 1:
        raise UsageError("--revision doit être un entier strictement positif")
    return value


def _is_absolute_path(value: str) -> bool:
    """Accepte les chemins absolus POSIX et Windows sans normaliser la chaîne."""

    candidate = value.strip()
    if not candidate:
        return False
    if candidate.startswith("/") or candidate.startswith("\\"):
        return True
    return bool(WINDOWS_ABSOLUTE_PATTERN.match(candidate))


def _parse_key_value_option(
    values: Sequence[str], option: str
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Sépare les valeurs littérales des références de secrets (`K=@SECRET_ID`)."""

    literals: dict[str, str] = {}
    references: dict[str, dict[str, str]] = {}
    expected = f"{option} attend K=V (valeur littérale) ou K=@SECRET_ID (référence de secret)"
    for raw in values:
        if "=" not in raw:
            raise UsageError(expected)
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise UsageError(expected)
        if key in literals or key in references:
            raise UsageError(f"{option} définit « {key} » deux fois")
        if value.startswith("@"):
            secret_id = value[1:].strip()
            if not secret_id:
                raise UsageError(f"{option} attend une référence de secret non vide après « @ »")
            references[key] = {"secret_id": secret_id}
        else:
            literals[key] = value
    return literals, references


def _build_mcp_config(args: argparse.Namespace) -> dict[str, Any]:
    """Construit la configuration complète d'un serveur MCP (un seul transport)."""

    if args.url and args.command:
        raise UsageError("--url et --command s'excluent : un serveur MCP a un seul transport")
    if not args.url and not args.command:
        raise UsageError("--url (transport http) ou --command (transport stdio) est obligatoire")
    timeout = args.timeout
    if timeout is not None and not (MCP_TIMEOUT_RANGE[0] <= timeout <= MCP_TIMEOUT_RANGE[1]):
        raise UsageError(
            f"--timeout doit être compris entre {MCP_TIMEOUT_RANGE[0]} et {MCP_TIMEOUT_RANGE[1]} secondes"
        )
    if args.url:
        for option, value in (
            ("--arg", args.arg),
            ("--env", args.env),
            ("--cwd", args.cwd),
            ("--runner", args.runner),
        ):
            if value:
                raise UsageError(f"{option} ne s'applique qu'au transport stdio (--command)")
        parts = urlsplit(args.url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise UsageError("--url doit être une URL http(s) absolue")
        headers, header_secrets = _parse_key_value_option(args.header, "--header")
        http: dict[str, Any] = {
            "url": args.url,
            "headers": headers,
            "header_secrets": header_secrets,
        }
        if timeout is not None:
            http["timeout_seconds"] = timeout
        return {"transport": "http", "http": http}
    if args.header:
        raise UsageError("--header ne s'applique qu'au transport http (--url)")
    if not _is_absolute_path(args.command):
        raise UsageError("--command exige un chemin absolu vers l'exécutable")
    env, env_secrets = _parse_key_value_option(args.env, "--env")
    stdio: dict[str, Any] = {
        "command": args.command,
        "args": list(args.arg),
        "env": env,
        "env_secrets": env_secrets,
    }
    if args.cwd:
        stdio["cwd"] = args.cwd
    if timeout is not None:
        stdio["timeout_seconds"] = timeout
    return {"transport": "stdio", "stdio": stdio}


def _handle_mcp_add(args: argparse.Namespace, client: ACPClient) -> Any:
    name = _require_text(args.name, "le nom du serveur")
    if not SLUG_PATTERN.match(name):
        raise UsageError(
            "le nom d'un serveur MCP doit être un slug : minuscules, chiffres et tirets, 63 caractères au plus"
        )
    body = {
        "name": name,
        "display_name": args.display or name,
        "description": args.description,
        "config": _build_mcp_config(args),
        "target_worker_id": args.runner,
        "note": args.note,
    }
    return client.request("POST", "/mcp/servers", json_body=body)


def _handle_mcp_update(args: argparse.Namespace, client: ACPClient) -> Any:
    body = {
        "config": _build_mcp_config(args),
        "target_worker_id": args.runner,
        "note": args.note,
    }
    return client.request(
        "POST",
        f"/mcp/servers/{_path_segment(args.server_id)}/revisions",
        json_body=body,
    )


def _handle_mcp_bind(args: argparse.Namespace, client: ACPClient) -> Any:
    tools: list[str] = []
    for raw in args.tool:
        tool = raw.strip()
        if not tool:
            raise UsageError("--tool exige un nom d'outil non vide")
        if tool not in tools:
            tools.append(tool)
    if not tools:
        raise UsageError("--tool est obligatoire : les outils autorisés sont listés explicitement")
    project = _require_option_text(args.project, "--project")
    return client.request(
        "POST",
        f"/mcp/servers/{_path_segment(args.server_id)}/bindings",
        json_body={"project_id": project, "allowed_tools": tools},
    )


def _handle_mcp_probes_list(args: argparse.Namespace, client: ACPClient) -> Any:
    """Sans `--server`, le filtre d'état est délégué à l'API ; sinon il est local."""

    if not args.server:
        return client.request("GET", "/mcp/probes", params=_filtered_params(status=args.status))
    body = client.request("GET", f"/mcp/servers/{_path_segment(args.server)}/probes")
    if not args.status:
        return body
    return [
        item
        for item in _items(body)
        if isinstance(item, dict) and item.get("status") == args.status
    ]


def _handle_mcp_tools(args: argparse.Namespace, client: ACPClient) -> dict[str, Any]:
    """Extrait les outils découverts sans jamais inventer de succès de découverte."""

    detail = client.request("GET", f"/mcp/servers/{_path_segment(args.server_id)}")
    if not isinstance(detail, dict):
        raise ProtocolError("l'API n'a pas retourné un serveur MCP exploitable")
    revision = detail.get("current_revision")
    discovery = revision.get("discovery") if isinstance(revision, dict) else None
    tools = discovery.get("tools") if isinstance(discovery, dict) else None
    return {
        "server_id": detail.get("id"),
        "revision_number": detail.get("current_revision_number"),
        "discovery_current": bool(detail.get("discovery_current")),
        "tools": tools if isinstance(tools, list) else [],
    }


def _export_notes(export: Mapping[str, Any], key: str) -> list[str]:
    """Liste de notes d'export, bornée au format attendu (données non fiables)."""

    value = export.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


def _handle_mcp_export(
    args: argparse.Namespace, client: ACPClient, *, stdout: TextIO, stderr: TextIO
) -> None:
    export = client.request(
        "GET",
        "/mcp/export",
        params=_filtered_params(format=args.export_format, project_id=args.project),
    )
    if args.json:
        _emit(export, as_json=True, stream=stdout)
        return
    if not isinstance(export, dict) or not isinstance(export.get("content"), str):
        raise ProtocolError("l'API n'a pas retourné un export MCP exploitable")
    # Le contenu est écrit tel quel : il est destiné à être redirigé vers un fichier.
    stdout.write(export["content"])
    placeholders = _export_notes(export, "placeholders")
    if placeholders:
        print(
            "Variables à définir dans l'environnement cible : " + ", ".join(placeholders),
            file=stderr,
        )
    for note in _export_notes(export, "partial_compatibility"):
        print(f"Compatibilité partielle : {note}", file=stderr)
    for note in _export_notes(export, "apply_notes"):
        print(f"À appliquer manuellement : {note}", file=stderr)


def _validated_probe(body: Any) -> dict[str, Any]:
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("id"), str)
        or not body["id"]
        or body.get("status") not in KNOWN_PROBE_STATES
    ):
        raise ProtocolError("l'API n'a pas retourné une sonde MCP exploitable")
    return body


def _raise_when_probe_failed(probe_id: str, status: str) -> None:
    if status != "succeeded":
        raise CommandError(
            "probe_failed",
            f"la sonde {probe_id} s'est terminée avec l'état « {status} »",
        )


def _handle_mcp_test(
    args: argparse.Namespace,
    client: ACPClient,
    *,
    stdout: TextIO,
    stderr: TextIO,
    sleep: Callable[[float], None],
) -> None:
    """Lance une sonde puis, avec `--wait`, suit son état sans jamais l'annuler."""

    if args.interval <= 0:
        raise UsageError("--interval doit être strictement positif")
    if args.timeout < 0:
        raise UsageError("--timeout ne peut pas être négatif")
    current = _validated_probe(
        client.request("POST", f"/mcp/servers/{_path_segment(args.server_id)}/probe")
    )
    probe_id = current["id"]
    status = current["status"]
    _emit(current, as_json=args.json, stream=stdout)
    if not args.wait:
        if status in TERMINAL_PROBE_STATES:
            _raise_when_probe_failed(probe_id, status)
            return
        if status == "pending_approval":
            _emit_notice(
                "probe_pending_approval",
                f"Sonde {probe_id} en attente d'autorisation : "
                f"`acp mcp probes approve {probe_id}` ou `acp mcp probes reject {probe_id}`.",
                as_json=args.json,
                stream=stderr,
            )
        else:
            _emit_notice(
                "probe_pending",
                f"Sonde {probe_id} à l'état « {status} » : suivez-la avec "
                f"`acp mcp probes show {probe_id}` ou relancez avec --wait.",
                as_json=args.json,
                stream=stderr,
            )
        return
    started_at = time.monotonic()
    while status not in TERMINAL_PROBE_STATES:
        if args.timeout and time.monotonic() - started_at >= args.timeout:
            raise CommandError(
                "client",
                f"délai d'attente dépassé : la sonde {probe_id} continue côté serveur ; "
                f"suivez-la avec `acp mcp probes show {probe_id}`",
            )
        try:
            sleep(args.interval)
            current = _validated_probe(
                client.request("GET", f"/mcp/probes/{_path_segment(probe_id)}")
            )
        except KeyboardInterrupt:
            # Aucune requête d'annulation : la sonde appartient au serveur.
            raise CommandError(
                "interrupted",
                f"la sonde {probe_id} continue côté serveur : aucune annulation n'a été demandée ; "
                f"suivez-la avec `acp mcp probes show {probe_id}`",
                ExitCode.INTERRUPTED,
            ) from None
        if current["status"] != status:
            status = current["status"]
            _emit(current, as_json=args.json, stream=stdout)
    _raise_when_probe_failed(probe_id, status)


def _parse_skill_source(raw: str) -> dict[str, Any]:
    """Traduit une source de skill en contrat `SkillSource`, fichiers lus localement."""

    expected = (
        "SOURCE doit commencer par dir:, archive:, github: ou skill-md: "
        "(exemple : dir:/srv/skills/demo)"
    )
    if raw.startswith("dir:"):
        path = raw[len("dir:") :]
        if not path.strip():
            raise UsageError("dir: attend un chemin non vide")
        if not _is_absolute_path(path):
            raise UsageError("dir: exige un chemin absolu autorisé côté serveur")
        return {"kind": "directory", "path": path}
    if raw.startswith("archive:"):
        return _read_skill_archive(raw[len("archive:") :])
    if raw.startswith("github:"):
        return _parse_github_source(raw[len("github:") :])
    if raw.startswith("skill-md:"):
        return _read_skill_markdown(raw[len("skill-md:") :])
    raise UsageError(expected)


def _system_reason(exc: OSError) -> str:
    """Cause lisible d'une erreur système, sans exposer de trace Python."""

    return exc.strerror or str(exc)


def _regular_file_stat(raw_path: str, path: Path, *, what: str) -> os.stat_result:
    """Inspecte un fichier local, toute erreur système devenant une erreur d'usage."""

    try:
        info = path.stat()
    except OSError as exc:
        raise UsageError(
            f"lecture impossible de {what} « {raw_path} » : {_system_reason(exc)}"
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise UsageError(f"{what} « {raw_path} » n'est pas un fichier régulier")
    return info


def _read_skill_archive(raw_path: str) -> dict[str, Any]:
    if not raw_path.strip():
        raise UsageError("archive: attend un chemin non vide")
    path = Path(raw_path)
    if not path.exists():
        raise UsageError(f"archive introuvable : {raw_path}")
    info = _regular_file_stat(raw_path, path, what="l'archive")
    if info.st_size > MAX_SKILL_ARCHIVE_BYTES:
        raise UsageError("l'archive dépasse la limite locale de 25 MiB")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise UsageError(
            f"lecture impossible de l'archive « {raw_path} » : {_system_reason(exc)}"
        ) from exc
    return {
        "kind": "archive",
        "filename": path.name,
        "content_base64": base64.b64encode(payload).decode("ascii"),
    }


def _parse_github_source(rest: str) -> dict[str, Any]:
    if "@" not in rest:
        raise UsageError(
            "github: exige un commit épinglé, sous la forme github:owner/repo@SHA[:sous/chemin]"
        )
    repository, _, remainder = rest.partition("@")
    ref, _, path = remainder.partition(":")
    if not GITHUB_REPOSITORY_PATTERN.match(repository):
        raise UsageError("github: attend un dépôt de la forme owner/repo")
    if not GITHUB_SHA_PATTERN.match(ref):
        raise UsageError("github: exige un SHA de commit de 40 caractères hexadécimaux")
    return {
        "kind": "github",
        "repository": repository,
        "ref": ref.lower(),
        "path": path.strip("/"),
    }


def _read_skill_markdown(raw_path: str) -> dict[str, Any]:
    if not raw_path.strip():
        raise UsageError("skill-md: attend un chemin non vide")
    path = Path(raw_path)
    if not path.exists():
        raise UsageError(f"fichier SKILL.md introuvable : {raw_path}")
    _regular_file_stat(raw_path, path, what="le fichier SKILL.md")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UsageError("le fichier SKILL.md doit être encodé en UTF-8") from exc
    except OSError as exc:
        raise UsageError(
            f"lecture impossible du fichier SKILL.md « {raw_path} » : {_system_reason(exc)}"
        ) from exc
    return {"kind": "manual", "files": [{"path": "SKILL.md", "content": content}]}


def _normalize_skill_path(value: str) -> str:
    path = value.replace("\\", "/").strip().lstrip("/")
    if not path:
        raise UsageError("le chemin du fichier ne peut pas être vide")
    if any(segment in {"", ".", ".."} for segment in path.split("/")):
        raise UsageError("le chemin du fichier doit être relatif à la racine du skill, sans « .. »")
    return path


def _resolve_skill_revision(args: argparse.Namespace, client: ACPClient) -> int:
    """Retourne la révision demandée, sinon la révision courante déclarée par l'API."""

    if args.revision is not None:
        return _require_revision_number(args.revision)
    detail = client.request("GET", f"/skills/{_path_segment(args.skill_id)}")
    number = detail.get("current_revision_number") if isinstance(detail, dict) else None
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise CommandError(
            "no_current_revision",
            "ce skill n'a pas de révision courante : précisez --revision",
        )
    return number


def _handle_skills_files(args: argparse.Namespace, client: ACPClient) -> Any:
    number = _resolve_skill_revision(args, client)
    return client.request(
        "GET", f"/skills/{_path_segment(args.skill_id)}/revisions/{number}/files"
    )


def _handle_skills_cat(
    args: argparse.Namespace, client: ACPClient, *, stdout: TextIO, stderr: TextIO
) -> None:
    path = _normalize_skill_path(args.path)
    number = _resolve_skill_revision(args, client)
    body = client.request(
        "GET",
        f"/skills/{_path_segment(args.skill_id)}/revisions/{number}/files/{quote(path, safe='/')}",
    )
    if not isinstance(body, dict):
        raise ProtocolError("l'API n'a pas retourné un fichier de skill exploitable")
    if not body.get("text"):
        raise CommandError(
            "binary_file",
            f"« {path} » n'est pas un fichier texte : consultez ses métadonnées avec `acp skills files`",
        )
    content = body.get("content")
    if not isinstance(content, str):
        raise ProtocolError("l'API n'a pas retourné le contenu du fichier")
    if args.json:
        _emit(body, as_json=True, stream=stdout)
        return
    # Contenu importé : affiché tel quel, comme une donnée, sans interprétation.
    stdout.write(content)
    if body.get("truncated"):
        print("Contenu tronqué par le serveur : lisez le fichier complet côté source.", file=stderr)


COMPLETION_COMMANDS = (
    "login logout doctor projects chat run runs pending approvals artifacts open workers "
    "secrets mcp skills automations completion"
)
COMPLETION_SUBCOMMANDS = (
    "list add extensions watch stop show discard status set rotate revoke catalog tools "
    "update test probes approve reject bind bindings unbind activate disable rollback "
    "export import search files cat install"
)


def _completion_script(shell: str) -> str:
    commands = COMPLETION_COMMANDS
    words = f"{COMPLETION_COMMANDS} {COMPLETION_SUBCOMMANDS}"
    if shell == "bash":
        return f'complete -W "{words}" acp'
    if shell == "zsh":
        return (
            f'#compdef acp\n_arguments "1:commande:({commands})" '
            f'"2:sous-commande:({COMPLETION_SUBCOMMANDS})"'
        )
    return (
        "Register-ArgumentCompleter -Native -CommandName acp -ScriptBlock {\n"
        "  param($wordToComplete)\n"
        f'  "{words}".Split(" ") | Where-Object {{ $_ -like "$wordToComplete*" }}\n'
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
    stderr: TextIO,
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
    if handler == "projects_extensions":
        path = f"/projects/{_path_segment(args.project_id)}/extensions"
        return True, client.request("GET", path), client.settings
    if handler == "secrets_status":
        return True, client.request("GET", "/secrets/status"), client.settings
    if handler == "secrets_list":
        return True, client.request("GET", "/secrets"), client.settings
    if handler == "secrets_set":
        return True, _handle_secrets_set(args, client, stdin), client.settings
    if handler == "secrets_rotate":
        return True, _handle_secrets_rotate(args, client, stdin), client.settings
    if handler == "secrets_revoke":
        path = f"/secrets/{_path_segment(args.secret_id)}"
        return True, client.request("DELETE", path), client.settings
    if handler == "mcp_catalog":
        return True, client.request("GET", "/mcp/catalog"), client.settings
    if handler == "mcp_add":
        return True, _handle_mcp_add(args, client), client.settings
    if handler == "mcp_update":
        return True, _handle_mcp_update(args, client), client.settings
    if handler == "mcp_list":
        params = _filtered_params(status=args.status)
        return True, client.request("GET", "/mcp/servers", params=params), client.settings
    if handler == "mcp_show":
        path = f"/mcp/servers/{_path_segment(args.server_id)}"
        return True, client.request("GET", path), client.settings
    if handler == "mcp_tools":
        return True, _handle_mcp_tools(args, client), client.settings
    if handler == "mcp_test":
        _handle_mcp_test(args, client, stdout=stdout, stderr=stderr, sleep=sleep)
        return False, None, client.settings
    if handler == "mcp_probes_list":
        return True, _handle_mcp_probes_list(args, client), client.settings
    if handler == "mcp_probes_show":
        path = f"/mcp/probes/{_path_segment(args.probe_id)}"
        return True, client.request("GET", path), client.settings
    if handler == "mcp_probes_decide":
        path = f"/mcp/probes/{_path_segment(args.probe_id)}/decision"
        body = {"decision": args.decision, "comment": args.comment}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "mcp_bind":
        return True, _handle_mcp_bind(args, client), client.settings
    if handler == "mcp_bindings":
        params = _filtered_params(project_id=args.project, server_id=args.server)
        return True, client.request("GET", "/mcp/bindings", params=params), client.settings
    if handler == "mcp_unbind":
        path = f"/mcp/bindings/{_path_segment(args.binding_id)}"
        return True, client.request("DELETE", path), client.settings
    if handler in {"mcp_activate", "mcp_disable"}:
        action = "activate" if handler == "mcp_activate" else "disable"
        path = f"/mcp/servers/{_path_segment(args.server_id)}/{action}"
        return True, client.request("POST", path), client.settings
    if handler == "mcp_revoke":
        path = f"/mcp/servers/{_path_segment(args.server_id)}/revoke"
        body = {"reason": _require_option_text(args.reason, "--reason")}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "mcp_rollback":
        path = f"/mcp/servers/{_path_segment(args.server_id)}/rollback"
        body = {"revision_number": _require_revision_number(args.revision), "note": args.note}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "mcp_export":
        _handle_mcp_export(args, client, stdout=stdout, stderr=stderr)
        return False, None, client.settings
    if handler == "skills_search":
        params = {"q": _require_text(args.query, "la requête de recherche")}
        return True, client.request("GET", "/skills/search", params=params), client.settings
    if handler == "skills_catalog":
        return True, client.request("GET", "/skills/catalog"), client.settings
    if handler == "skills_list":
        return True, client.request("GET", "/skills"), client.settings
    if handler == "skills_show":
        path = f"/skills/{_path_segment(args.skill_id)}"
        return True, client.request("GET", path), client.settings
    if handler == "skills_files":
        return True, _handle_skills_files(args, client), client.settings
    if handler == "skills_cat":
        _handle_skills_cat(args, client, stdout=stdout, stderr=stderr)
        return False, None, client.settings
    if handler == "skills_install":
        body = {
            "source": _parse_skill_source(args.source),
            "name": _optional_option_text(args.name, "--name"),
            "note": args.note,
        }
        return True, client.request("POST", "/skills/import", json_body=body), client.settings
    if handler == "skills_update":
        path = f"/skills/{_path_segment(args.skill_id)}/revisions"
        body = {"source": _parse_skill_source(args.source), "note": args.note}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "skills_approve":
        number = _require_revision_number(args.revision)
        path = f"/skills/{_path_segment(args.skill_id)}/revisions/{number}/approve"
        body = {"comment": args.comment}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler in {"skills_activate", "skills_disable"}:
        action = "activate" if handler == "skills_activate" else "disable"
        path = f"/skills/{_path_segment(args.skill_id)}/{action}"
        return True, client.request("POST", path), client.settings
    if handler == "skills_revoke":
        path = f"/skills/{_path_segment(args.skill_id)}/revoke"
        body = {"reason": _require_option_text(args.reason, "--reason")}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "skills_rollback":
        path = f"/skills/{_path_segment(args.skill_id)}/rollback"
        body = {"revision_number": _require_revision_number(args.revision), "note": args.note}
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "skills_bind":
        body = {"project_id": _require_option_text(args.project, "--project")}
        path = f"/skills/{_path_segment(args.skill_id)}/bindings"
        return True, client.request("POST", path, json_body=body), client.settings
    if handler == "skills_bindings":
        params = _filtered_params(project_id=args.project, skill_id=args.skill)
        return True, client.request("GET", "/skills/bindings", params=params), client.settings
    if handler == "skills_unbind":
        path = f"/skills/bindings/{_path_segment(args.binding_id)}"
        return True, client.request("DELETE", path), client.settings
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
    normalized = _normalize_global_options(_attach_dash_tolerant_values(raw_argv))
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
            stderr=err,
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
        message = _mask_secret_material(str(exc), raw_argv)
        _emit_error("usage", message, as_json=as_json, stream=err)
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
    except CommandError as exc:
        as_json = "--json" in raw_argv
        _emit_error(exc.code, str(exc), as_json=as_json, stream=err)
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
