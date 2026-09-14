"""Point d'entrée ``acp`` : orchestration sûre, scriptable et sans magie cachée."""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
import time
import uuid
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, NamedTuple, Sequence, TextIO
from urllib.parse import quote, urlencode, urlsplit

import httpx

from . import __version__
from .client import (
    ACPClient,
    APIError,
    NetworkError,
    ProtocolError,
    SESSION_COOKIE_NAME,
    USER_AGENT,
)
from .client import _error_detail as _api_error_detail
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


class CommandError(RuntimeError):
    """Échec métier explicite : ni une erreur d'usage, ni une erreur de transport.

    Le message est déjà rédigé pour l'utilisateur ; ``code`` identifie la cause
    de façon stable pour les scripts (`--json`).
    """

    def __init__(self, code: str, message: str, exit_code: ExitCode = ExitCode.REMOTE) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


class AutomationTriggerError(CommandError):
    """Résultat de déclenchement incertain, rejouable avec la même clé.

    Contrairement aux créations de mission, cette mutation n'occupe pas le
    registre ``pending`` historique du CLI. La clé est donc toujours rendue dans
    l'erreur afin que l'appelant puisse la fournir explicitement au rejeu.
    """

    def __init__(
        self,
        message: str,
        *,
        idempotency_key: str,
        code: str,
        exit_code: ExitCode,
        status_code: int | None = None,
    ) -> None:
        super().__init__(code, message, exit_code)
        self.idempotency_key = idempotency_key
        self.status_code = status_code


class AutomationMutationError(CommandError):
    """Mutation d'automatisation incertaine, avec matériel de rejeu explicite."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        idempotency_key: str,
        recovery: str,
        code: str,
        exit_code: ExitCode,
        status_code: int | None = None,
        retry_secret: str | None = None,
    ) -> None:
        super().__init__(code, message, exit_code)
        self.operation = operation
        self.idempotency_key = idempotency_key
        self.recovery = recovery
        self.status_code = status_code
        self.retry_secret = retry_secret


class AutomationOutcomeError(CommandError):
    """Occurrence enregistrée mais mission non lancée : sortie non nulle scriptable."""

    def __init__(self, result: dict[str, Any]) -> None:
        outcome = str(result["outcome"])
        super().__init__(
            "automation_" + outcome,
            "le déclenchement a été enregistré sans lancer de mission (" + outcome + ")",
            ExitCode.REMOTE,
        )
        self.result = result


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
MCP_IMPORT_FORMATS = ("auto", "hermes", "claude", "codex")
MCP_IMPORT_CONFLICTS = ("skip", "new_revision")
MCP_TIMEOUT_RANGE = (1, 120)
# Le fichier d'import est lu localement : le serveur ne lit jamais un chemin fourni par le client.
MAX_IMPORT_FILE_BYTES = 1024 * 1024
MAX_IMPORT_CHARS = 1_000_000
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

# --- Lot F : automatisations -------------------------------------------------
AUTOMATION_DEFAULT_TIMEZONE = "Europe/Paris"
AUTOMATION_MAX_CONCURRENT_RUNS = 5
AUTOMATION_MAX_LIMIT = 500
AUTOMATION_TEMPLATE_MAX_BYTES = 1024 * 1024
AUTOMATION_INTERVAL_MIN_SECONDS = 60
AUTOMATION_INTERVAL_MAX_SECONDS = 31_536_000
AUTOMATION_WEBHOOK_SECRET_MAX_BYTES = 512
AUTOMATION_WEBHOOK_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,200}$")
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- Lot E : événements, tests structurés et artefacts -----------------------
# Bornes du §6 de la spécification, reprises côté client pour refuser une
# commande impossible avant tout appel réseau. Le serveur revalide.
EVENTS_MAX_LIMIT = 500
EVENTS_MAX_PAGES = 10_000
SSE_MAX_EVENT_CHARS = 1024 * 1024
FOLLOW_SEEN_IDS_MAX = 5000
# Noms de trames SSE du serveur (`apps/api/src/acp_api/streams.py`, spec §5.2).
# Seul `acp.event` porte un événement de journal : les deux autres pilotent la
# connexion et ne doivent jamais être écrits sur la sortie standard.
SSE_EVENT_NAME = "acp.event"
SSE_ROTATE_EVENT = "acp.stream.rotate"
SSE_CLOSED_EVENT = "acp.stream.closed"
# Le serveur ferme le flux après `ACP_STREAM_MAX_SECONDS` (900 s) « pour que le
# client se reconnecte » (§5.2). La reconnexion est bornée : une observation ne
# boucle jamais indéfiniment sur un serveur qui tournerait sans rien émettre.
FOLLOW_MAX_ROTATIONS = 8
# Genres de flux du §3.2, seuls filtres exposés par `GET /artifacts` (§6).
ARTIFACT_STREAM_KINDS = ("screenshot", "video", "trace", "report", "file")
# Paramètre de vue du lien profond Studio (§2.5, §10). Le shell web ne lit que
# celui-ci (`apps/web/src/studio-ui.ts::STUDIO_VIEW_PARAM`) ; `view` appartient
# déjà à une autre vue de la même application.
STUDIO_VIEW_PARAM = "vue"
STUDIO_VIEW_VALUE = "studio"
ARTIFACT_CHUNK_BYTES = 1024 * 1024
# Utilisé seulement quand l'API n'annonce pas de taille : sinon la taille
# annoncée fait foi et tout octet supplémentaire interrompt le téléchargement.
ARTIFACT_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
ARTIFACT_LIST_MAX_PAGES = 1000
ARTIFACT_LINK_DEFAULT_TTL_SECONDS = 300
ARTIFACT_LINK_MAX_TTL_SECONDS = 900
DOWNLOAD_NAME_MAX_CHARS = 200
TEST_TOTALS_KEYS = ("expected", "unexpected", "flaky", "skipped", "interrupted", "timedOut")
# Ordre du résumé serveur (`testing_service.py::derive_technical_validation`).
TEST_FAILING_TOTALS = ("unexpected", "interrupted", "timedOut")
TEXT_CONTENT_TYPES = {"application/json", "application/x-ndjson", "application/xml"}
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{index}" for prefix in ("COM", "LPT") for index in range(1, 10)
}


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

    # Import assisté : le fichier est lu localement, seul son contenu est envoyé, et rien
    # n'est créé sans `--apply` accompagné des entrées explicitement nommées.
    importer = actions.add_parser("import", help="importer une configuration MCP existante")
    importer.add_argument("path", help="fichier de configuration local (1 MiB au plus)")
    importer.add_argument(
        "--format",
        dest="import_format",
        choices=MCP_IMPORT_FORMATS,
        default="auto",
        help="format du fichier (défaut : détection automatique)",
    )
    importer.add_argument(
        "--apply",
        action="store_true",
        help="appliquer les entrées nommées (sans cette option, la commande se limite à l'aperçu)",
    )
    importer.add_argument(
        "--name", action="append", default=[], help="entrée de l'aperçu à importer (répétable)"
    )
    importer.add_argument(
        "--map",
        dest="mapping",
        action="append",
        default=[],
        metavar="SECRET_NAME=SECRET_ID",
        help="relie un candidat de secret à un secret existant du coffre (répétable)",
    )
    importer.add_argument(
        "--on-conflict",
        choices=MCP_IMPORT_CONFLICTS,
        default=None,
        help="nom déjà pris : ignorer (défaut) ou créer une révision (l'ancienne est conservée)",
    )
    importer.set_defaults(handler="mcp_import")


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


def _add_automation_template_option(
    parser: argparse.ArgumentParser, *, required: bool
) -> None:
    source = parser.add_mutually_exclusive_group(required=required)
    source.add_argument(
        "--template",
        "--template-json",
        dest="template_json",
        metavar="JSON",
        help="gabarit de mission sous forme d'objet JSON",
    )
    source.add_argument(
        "--template-file",
        type=Path,
        help="fichier UTF-8 contenant l'objet JSON du gabarit",
    )


def _add_automation_schedule_options(
    parser: argparse.ArgumentParser, *, required: bool
) -> None:
    parser.add_argument(
        "--schedule-kind",
        choices=("cron", "interval"),
        required=required,
        help="type de calendrier",
    )
    parser.add_argument(
        "--expression",
        required=required,
        help="expression cron (5 champs) ou intervalle (ex. 15m)",
    )
    parser.add_argument(
        "--timezone",
        default=AUTOMATION_DEFAULT_TIMEZONE if required else None,
        help=f"fuseau IANA (défaut : {AUTOMATION_DEFAULT_TIMEZONE})",
    )


def _add_automations_group(commands: argparse._SubParsersAction) -> None:
    """`acp automations` : routines, exécutions et calendrier."""

    automations = commands.add_parser(
        "automations", help="gérer les routines planifiées"
    )
    actions = automations.add_subparsers(dest="automation_action", required=True)

    listing = actions.add_parser("list", help="lister les automatisations accessibles")
    listing.add_argument("--project", help="restreindre à un projet")
    state = listing.add_mutually_exclusive_group()
    state.add_argument(
        "--enabled", dest="enabled", action="store_const", const=True
    )
    state.add_argument(
        "--disabled", dest="enabled", action="store_const", const=False
    )
    listing.set_defaults(enabled=None)
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler="automations_list")

    create = actions.add_parser(
        "create", help="créer une automatisation désactivée"
    )
    create.add_argument("--project", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--description", default="")
    _add_automation_schedule_options(create, required=True)
    _add_automation_template_option(create, required=True)
    create.add_argument(
        "--catchup", choices=("skip", "run_once"), default="skip"
    )
    create.add_argument("--max-concurrent-runs", type=int, default=1)
    create.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    create.set_defaults(handler="automations_create")

    show = actions.add_parser("show", help="afficher le détail d'une automatisation")
    show.add_argument("automation_id")
    show.set_defaults(handler="automations_show")

    update = actions.add_parser("update", help="modifier une automatisation")
    update.add_argument("automation_id")
    update.add_argument("--name")
    update.add_argument("--description")
    _add_automation_schedule_options(update, required=False)
    _add_automation_template_option(update, required=False)
    update.add_argument("--catchup", choices=("skip", "run_once"))
    update.add_argument("--max-concurrent-runs", type=int)
    update.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    update.set_defaults(handler="automations_update")

    enable = actions.add_parser("enable", help="activer une automatisation")
    enable.add_argument("automation_id")
    enable.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    enable.set_defaults(handler="automations_enable")

    disable = actions.add_parser("disable", help="désactiver une automatisation")
    disable.add_argument("automation_id")
    disable.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    disable.set_defaults(handler="automations_disable")

    trigger = actions.add_parser(
        "trigger", help="déclencher immédiatement une automatisation"
    )
    trigger.add_argument("automation_id")
    trigger.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    trigger.set_defaults(handler="automations_trigger")

    runs = actions.add_parser("runs", help="lister les déclenchements d'une automatisation")
    runs.add_argument("automation_id")
    runs.add_argument("--limit", type=int, default=100)
    runs.set_defaults(handler="automations_runs")

    calendar = actions.add_parser(
        "calendar", help="afficher les occurrences passées et prévues"
    )
    calendar.add_argument("--project")
    calendar.add_argument("--automation", dest="automation_id")
    calendar.add_argument("--start", help="début RFC 3339 avec décalage UTC")
    calendar.add_argument("--end", help="fin RFC 3339 avec décalage UTC")
    calendar.add_argument("--limit", type=int, default=500)
    calendar.set_defaults(handler="automations_calendar")

    webhook = actions.add_parser(
        "webhook", help="consulter, faire tourner ou désactiver le webhook"
    )
    webhook_actions = webhook.add_subparsers(
        dest="automation_webhook_action", required=True
    )
    webhook_status = webhook_actions.add_parser(
        "status", help="afficher l'état sans révéler le secret"
    )
    webhook_status.add_argument("automation_id")
    webhook_status.set_defaults(handler="automations_webhook_status")

    webhook_rotate = webhook_actions.add_parser(
        "rotate", help="installer un nouveau secret de webhook"
    )
    webhook_rotate.add_argument("automation_id")
    # Une valeur positionnelle ou --secret est acceptée par argparse uniquement
    # pour produire un refus générique qui ne la recopie jamais dans stderr.
    webhook_rotate.add_argument("forbidden_secret", nargs="?", help=argparse.SUPPRESS)
    webhook_rotate.add_argument("--secret", dest="forbidden_secret_option", help=argparse.SUPPRESS)
    secret_source = webhook_rotate.add_mutually_exclusive_group()
    secret_source.add_argument(
        "--secret-env",
        metavar="NAME",
        help="lire le secret dans la variable d'environnement NAME",
    )
    secret_source.add_argument(
        "--secret-file",
        type=Path,
        help="lire le secret dans un fichier UTF-8 local",
    )
    webhook_rotate.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    webhook_rotate.set_defaults(handler="automations_webhook_rotate")

    webhook_disable = webhook_actions.add_parser(
        "disable", help="révoquer le secret et désactiver le webhook"
    )
    webhook_disable.add_argument("automation_id")
    webhook_disable.add_argument(
        "--idempotency-key",
        help="clé stable de rejeu (sinon le CLI en génère et l'affiche)",
    )
    webhook_disable.set_defaults(handler="automations_webhook_disable")


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
    events = run_actions.add_parser("events", help="lire le journal d'événements d'un run")
    events.add_argument("run_id", help="identifiant de run ou de mission")
    events.add_argument(
        "--after-seq",
        dest="after_seq",
        type=int,
        help="reprendre après cette séquence (curseur)",
    )
    events.add_argument(
        "--limit",
        type=int,
        help=f"taille de page, 1 à {EVENTS_MAX_LIMIT}",
    )
    events.add_argument(
        "--follow",
        action="store_true",
        help="observer le flux ; Ctrl+C quitte sans arrêter la mission",
    )
    events.set_defaults(handler="runs_events")
    run_tests = run_actions.add_parser("tests", help="résumé de la validation technique d'un run")
    run_tests.add_argument("run_id", help="identifiant de run ou de mission")
    run_tests.set_defaults(handler="runs_tests")

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
    artifacts_list.add_argument(
        "--kind",
        help=(
            "filtrer sur le genre de flux (screenshot, video, trace, report, file) "
            "ou sur le genre d'artefact (ex. test_report)"
        ),
    )
    artifacts_list.add_argument(
        "--type",
        dest="content_type",
        help="filtrer sur le type MIME exact (ex. image/png)",
    )
    artifacts_list.set_defaults(handler="artifacts_list")
    artifacts_get = artifact_actions.add_parser("get", help="télécharger le contenu d'un artefact")
    artifacts_get.add_argument("artifact_id")
    artifacts_get.add_argument("--output", help="fichier ou répertoire de destination")
    artifacts_get.add_argument(
        "--stdout",
        dest="to_stdout",
        action="store_true",
        help="écrire le contenu sur la sortie standard",
    )
    artifacts_get.add_argument(
        "--force",
        action="store_true",
        help="écraser un fichier existant, ou accepter du binaire sur un terminal",
    )
    artifacts_get.set_defaults(handler="artifacts_get")
    artifacts_link = artifact_actions.add_parser("link", help="créer un lien signé temporaire")
    artifacts_link.add_argument("artifact_id")
    artifacts_link.add_argument(
        "--ttl",
        type=int,
        default=ARTIFACT_LINK_DEFAULT_TTL_SECONDS,
        help=f"durée de validité en secondes, 1 à {ARTIFACT_LINK_MAX_TTL_SECONDS}",
    )
    artifacts_link.set_defaults(handler="artifacts_link")

    open_command = commands.add_parser("open", help="afficher l'URL web d'un run")
    open_command.add_argument("--run", required=True)
    open_command.add_argument(
        "--studio",
        action="store_true",
        help="pointer la vue Studio (événements, tests et livrables du run)",
    )
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
    _add_automations_group(commands)
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


def _automation_limit(value: int) -> int:
    if not 1 <= value <= AUTOMATION_MAX_LIMIT:
        raise UsageError(
            f"--limit doit être compris entre 1 et {AUTOMATION_MAX_LIMIT}"
        )
    return value


def _automation_concurrency(value: int) -> int:
    if not 1 <= value <= AUTOMATION_MAX_CONCURRENT_RUNS:
        raise UsageError(
            "--max-concurrent-runs doit être compris entre 1 et "
            f"{AUTOMATION_MAX_CONCURRENT_RUNS}"
        )
    return value


def _read_automation_template_file(path: Path) -> str:
    raw_path = str(path)
    if not raw_path.strip():
        raise UsageError("--template-file attend un chemin non vide")
    if not path.exists():
        raise UsageError(f"fichier de gabarit introuvable : {raw_path}")
    info = _regular_file_stat(raw_path, path, what="le fichier de gabarit")
    if info.st_size > AUTOMATION_TEMPLATE_MAX_BYTES:
        raise UsageError("le fichier de gabarit dépasse la limite locale de 1 MiB")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UsageError("le fichier de gabarit doit être encodé en UTF-8") from exc
    except OSError as exc:
        raise UsageError(
            f"lecture impossible du fichier de gabarit « {raw_path} » : "
            f"{_system_reason(exc)}"
        ) from exc


def _automation_template(args: argparse.Namespace) -> dict[str, Any] | None:
    inline = getattr(args, "template_json", None)
    path = getattr(args, "template_file", None)
    if inline is None and path is None:
        return None
    raw = inline if inline is not None else _read_automation_template_file(path)
    if len(raw.encode("utf-8")) > AUTOMATION_TEMPLATE_MAX_BYTES:
        raise UsageError("le gabarit JSON dépasse la limite locale de 1 MiB")
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"gabarit JSON invalide (ligne {exc.lineno}, colonne {exc.colno})"
        ) from exc
    if not isinstance(template, dict):
        raise UsageError("le gabarit de mission doit être un objet JSON")
    return template


def _automation_schedule(args: argparse.Namespace) -> dict[str, str] | None:
    kind = getattr(args, "schedule_kind", None)
    expression = getattr(args, "expression", None)
    timezone = getattr(args, "timezone", None)
    supplied = (kind is not None, expression is not None, timezone is not None)
    if not any(supplied):
        return None
    if kind is None or expression is None:
        raise UsageError(
            "--schedule-kind et --expression sont requis ensemble pour modifier le calendrier"
        )
    if timezone is None:
        raise UsageError(
            "--timezone est requis avec --schedule-kind et --expression pour "
            "ne pas modifier silencieusement le fuseau existant"
        )
    normalized_expression = _require_text(expression, "--expression")
    if kind == "interval":
        match = re.fullmatch(r"([0-9]+)([smhd]?)", normalized_expression)
        if match is None:
            raise UsageError(
                "--expression interval attend des secondes ou une durée comme 15m, 2h ou 1d"
            )
        amount = int(match.group(1))
        multiplier = {"": 1, "s": 1, "m": 60, "h": 3_600, "d": 86_400}[
            match.group(2)
        ]
        seconds = amount * multiplier
        if not AUTOMATION_INTERVAL_MIN_SECONDS <= seconds <= AUTOMATION_INTERVAL_MAX_SECONDS:
            raise UsageError(
                "l’intervalle doit être compris entre 60 et 31536000 secondes"
            )
        normalized_expression = str(seconds)
    return {
        "kind": kind,
        "expression": normalized_expression,
        "timezone": _require_text(timezone, "--timezone"),
    }


def _automation_create_payload(args: argparse.Namespace) -> dict[str, Any]:
    schedule = _automation_schedule(args)
    template = _automation_template(args)
    assert schedule is not None  # options requises par argparse
    assert template is not None
    return {
        "name": _require_option_text(args.name, "--name"),
        "description": args.description,
        "schedule": schedule,
        "mission_template": template,
        "catchup_policy": args.catchup,
        "max_concurrent_runs": _automation_concurrency(args.max_concurrent_runs),
    }


def _automation_update_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.name is not None:
        payload["name"] = _require_option_text(args.name, "--name")
    if args.description is not None:
        payload["description"] = args.description
    schedule = _automation_schedule(args)
    if schedule is not None:
        payload["schedule"] = schedule
    template = _automation_template(args)
    if template is not None:
        payload["mission_template"] = template
    if args.catchup is not None:
        payload["catchup_policy"] = args.catchup
    if args.max_concurrent_runs is not None:
        payload["max_concurrent_runs"] = _automation_concurrency(
            args.max_concurrent_runs
        )
    if not payload:
        raise UsageError("au moins une modification est requise")
    return payload


def _automation_datetime(value: str | None, option: str) -> tuple[str, datetime] | None:
    if value is None:
        return None
    text = _require_option_text(value, option)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UsageError(f"{option} doit être une date RFC 3339 valide") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise UsageError(f"{option} doit porter un décalage UTC")
    return text, moment


def _automation_calendar_params(args: argparse.Namespace) -> dict[str, Any]:
    start = _automation_datetime(args.start, "--start")
    end = _automation_datetime(args.end, "--end")
    if start is not None and end is not None and start[1] >= end[1]:
        raise UsageError("--end doit être strictement postérieur à --start")
    params: dict[str, Any] = {"limit": _automation_limit(args.limit)}
    if args.project is not None:
        params["project_id"] = _require_option_text(args.project, "--project")
    if args.automation_id is not None:
        params["automation_id"] = _require_option_text(
            args.automation_id, "--automation"
        )
    if start is not None:
        params["start"] = start[0]
    if end is not None:
        params["end"] = end[0]
    return params


def _automation_trigger_failure(
    key: str,
    *,
    code: str,
    exit_code: ExitCode,
    status_code: int | None = None,
) -> AutomationTriggerError:
    return AutomationTriggerError(
        "résultat du déclenchement incertain ; rejouez `acp automations trigger` "
        "avec la même --idempotency-key",
        idempotency_key=key,
        code=code,
        exit_code=exit_code,
        status_code=status_code,
    )


def _automation_mutation_failure(
    key: str,
    *,
    operation: str,
    command: str,
    recovery: str,
    code: str,
    exit_code: ExitCode,
    status_code: int | None = None,
    retry_secret: str | None = None,
) -> AutomationMutationError:
    secret_instruction = (
        " et le même secret via --secret-env ou --secret-file"
        if retry_secret is not None
        else ""
    )
    return AutomationMutationError(
        f"résultat de {operation} incertain ; rejouez `{command}` avec la même "
        f"--idempotency-key{secret_instruction}",
        operation=operation,
        idempotency_key=key,
        recovery=recovery,
        code=code,
        exit_code=exit_code,
        status_code=status_code,
        retry_secret=retry_secret,
    )


def _idempotent_automation_mutation(
    client: ACPClient,
    *,
    method: str,
    path: str,
    key: str,
    operation: str,
    command: str,
    recovery: str,
    validator: Callable[[Any], dict[str, Any]],
    json_body: Any = None,
    retry_secret: str | None = None,
) -> dict[str, Any]:
    """Exécute une mutation dont toute réponse non certaine doit être rejouable."""

    try:
        raw = client.request(
            method,
            path,
            json_body=json_body,
            idempotency_key=key,
        )
    except NetworkError as exc:
        raise _automation_mutation_failure(
            key,
            operation=operation,
            command=command,
            recovery=recovery,
            code="network",
            exit_code=ExitCode.NETWORK,
            retry_secret=retry_secret,
        ) from exc
    except APIError as exc:
        if exc.status_code != 408 and exc.status_code < 500:
            if retry_secret is not None and retry_secret in exc.detail:
                raise APIError(
                    exc.status_code, exc.detail.replace(retry_secret, "***")
                ) from exc
            raise
        raise _automation_mutation_failure(
            key,
            operation=operation,
            command=command,
            recovery=recovery,
            code="api",
            exit_code=ExitCode.REMOTE,
            status_code=exc.status_code,
            retry_secret=retry_secret,
        ) from exc
    except ProtocolError as exc:
        raise _automation_mutation_failure(
            key,
            operation=operation,
            command=command,
            recovery=recovery,
            code="client",
            exit_code=ExitCode.REMOTE,
            retry_secret=retry_secret,
        ) from exc
    try:
        return validator(raw)
    except ProtocolError as exc:
        raise _automation_mutation_failure(
            key,
            operation=operation,
            command=command,
            recovery=recovery,
            code="client",
            exit_code=ExitCode.REMOTE,
            retry_secret=retry_secret,
        ) from exc


def _automation_integer(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def _automation_aware_instant(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return moment.tzinfo is not None and moment.utcoffset() is not None


def _automation_schedule_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("kind") not in ("cron", "interval"):
        return False
    if not isinstance(value.get("expression"), str) or not value["expression"].strip():
        return False
    timezone = value.get("timezone")
    if not isinstance(timezone, str) or not timezone.strip():
        return False
    # La réponse a déjà été validée contre la tzdb IANA du serveur. Une tzdb
    # cliente plus ancienne ne doit pas invalider un identifiant nouvellement
    # créé ou renommé.
    if timezone != timezone.strip() or len(timezone) > 64:
        return False
    return True


def _automation_summary_result(
    value: Any, *, expected_id: str | None = None, expected_enabled: bool | None = None
) -> dict[str, Any]:
    valid = (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and bool(value.get("id"))
        and isinstance(value.get("project_id"), str)
        and bool(value.get("project_id"))
        and isinstance(value.get("name"), str)
        and isinstance(value.get("description"), str)
        and _automation_schedule_result(value.get("schedule"))
        and isinstance(value.get("enabled"), bool)
        and value.get("catchup_policy") in ("skip", "run_once")
        and _automation_integer(value.get("max_concurrent_runs"), minimum=1, maximum=5)
        and (value.get("next_run_at") is None or _automation_aware_instant(value.get("next_run_at")))
        and _automation_aware_instant(value.get("created_at"))
    )
    if not valid:
        raise ProtocolError("réponse d’automatisation incomplète ou hors contrat")
    assert isinstance(value, dict)
    if expected_id is not None and value["id"] != expected_id:
        raise ProtocolError("la réponse vise une autre automatisation")
    if expected_enabled is not None and value["enabled"] is not expected_enabled:
        raise ProtocolError("la réponse ne confirme pas l’état demandé")
    return dict(value)


def _automation_run_result(
    value: Any, *, expected_automation_id: str | None = None
) -> dict[str, Any]:
    valid = (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and bool(value.get("id"))
        and isinstance(value.get("automation_id"), str)
        and bool(value.get("automation_id"))
        and isinstance(value.get("fire_key"), str)
        and re.fullmatch(r"[0-9a-f]{32}", value.get("fire_key", "")) is not None
        and _automation_aware_instant(value.get("scheduled_for"))
        and _automation_aware_instant(value.get("fired_at"))
        and (value.get("task_id") is None or isinstance(value.get("task_id"), str))
        and value.get("trigger_kind") in ("manual", "schedule", "webhook")
        and value.get("outcome") in (
            "launched", "skipped_concurrency", "skipped_disabled", "skipped_catchup", "failed"
        )
        and isinstance(value.get("detail"), str)
        and len(value.get("detail", "")) <= 500
        and "completion_status" in value
    )
    if not valid:
        raise ProtocolError("réponse de déclenchement incomplète ou hors contrat")
    assert isinstance(value, dict)
    if expected_automation_id is not None and value["automation_id"] != expected_automation_id:
        raise ProtocolError("la réponse de déclenchement vise une autre automatisation")
    completion = value.get("completion_status")
    if completion not in (
        None, "succeeded", "failed", "blocked", "cancelled", "interrupted"
    ):
        raise ProtocolError("statut final de déclenchement hors contrat")
    return dict(value)


def _automation_string_list(value: Any, *, required: bool = False) -> bool:
    if not isinstance(value, list) or len(value) > 100 or (required and not value):
        return False
    if not all(isinstance(item, str) and bool(item.strip()) for item in value):
        return False
    normalized = [item.strip() for item in value]
    return len(normalized) == len(set(normalized))


def _automation_budget_result(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "max_cost", "currency", "max_tokens", "max_tool_calls"
    }:
        return False
    cost = value["max_cost"]
    if cost is not None and (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(cost)
        or cost < 0
    ):
        return False
    if not isinstance(value["currency"], str) or re.fullmatch(r"[A-Za-z]{3}", value["currency"]) is None:
        return False
    for name in ("max_tokens", "max_tool_calls"):
        metric = value[name]
        if metric is not None and not _automation_integer(metric, minimum=0):
            return False
    return any(value[name] is not None for name in ("max_cost", "max_tokens", "max_tool_calls"))


def _automation_mission_template_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = {
        "title", "objective", "expected_outcome", "acceptance_criteria",
        "autonomy", "resources", "budget", "duration_seconds", "team_id",
        "agent_instance_id", "priority", "required_capabilities",
    }
    if set(value) != required:
        return False
    for name, maximum in (("title", 300), ("objective", 10_000), ("expected_outcome", 10_000)):
        field = value[name]
        if not isinstance(field, str) or not field or len(field) > maximum:
            return False
    if not _automation_string_list(value["acceptance_criteria"], required=True):
        return False
    autonomy = value["autonomy"]
    if not isinstance(autonomy, dict) or set(autonomy) != {
        "mode", "allowed_actions", "forbidden_actions", "approval_required_actions"
    }:
        return False
    if autonomy["mode"] not in ("supervised", "bounded", "autonomous"):
        return False
    if not all(
        _automation_string_list(autonomy[name])
        for name in ("allowed_actions", "forbidden_actions", "approval_required_actions")
    ):
        return False
    resources = value["resources"]
    if not isinstance(resources, list) or len(resources) > 100:
        return False
    for resource in resources:
        if not isinstance(resource, dict) or set(resource) != {
            "kind", "identifier", "access", "description"
        }:
            return False
        if (
            not isinstance(resource["kind"], str)
            or not resource["kind"]
            or len(resource["kind"]) > 100
            or not isinstance(resource["identifier"], str)
            or not resource["identifier"]
            or len(resource["identifier"]) > 1_000
            or resource["access"] not in ("read", "write")
            or not isinstance(resource["description"], str)
            or len(resource["description"]) > 1_000
        ):
            return False
    if not _automation_budget_result(value["budget"]):
        return False
    if not _automation_integer(value["duration_seconds"], minimum=1, maximum=31_536_000):
        return False
    if not all(value[name] is None or isinstance(value[name], str) for name in ("team_id", "agent_instance_id")):
        return False
    return (
        _automation_integer(value["priority"], minimum=1, maximum=5)
        and _automation_string_list(value["required_capabilities"])
    )


def _automation_normalized_unique_strings(value: Any) -> Any:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return value
    return list(dict.fromkeys(item.strip() for item in value))


def _canonical_automation_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Miroir des seules canonicalisations/defaults des contrats automation."""

    expected = json.loads(json.dumps(payload))
    template = expected.get("mission_template")
    if not isinstance(template, dict):
        return expected
    template.setdefault("resources", [])
    template.setdefault("team_id", None)
    template.setdefault("agent_instance_id", None)
    template.setdefault("priority", 3)
    template.setdefault("required_capabilities", [])
    template["acceptance_criteria"] = _automation_normalized_unique_strings(
        template.get("acceptance_criteria")
    )
    template["required_capabilities"] = _automation_normalized_unique_strings(
        template.get("required_capabilities")
    )

    autonomy = template.get("autonomy")
    if isinstance(autonomy, dict):
        autonomy.setdefault("mode", "bounded")
        autonomy.setdefault("allowed_actions", [])
        autonomy.setdefault("forbidden_actions", [])
        autonomy.setdefault("approval_required_actions", [])

    resources = template.get("resources")
    if isinstance(resources, list):
        canonical_resources = []
        for resource in resources:
            if not isinstance(resource, dict):
                canonical_resources.append(resource)
                continue
            canonical_resources.append(
                {"access": "read", "description": "", **resource}
            )
        template["resources"] = canonical_resources

    budget = template.get("budget")
    if isinstance(budget, dict):
        budget.setdefault("max_cost", None)
        budget.setdefault("currency", "EUR")
        budget.setdefault("max_tokens", None)
        budget.setdefault("max_tool_calls", None)
        if isinstance(budget.get("currency"), str):
            budget["currency"] = budget["currency"].upper()
    return expected


def _automation_requested_fields_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual
            and _automation_requested_fields_match(actual[key], expected_value)
            for key, expected_value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _automation_requested_fields_match(actual_value, expected_value)
                for actual_value, expected_value in zip(actual, expected)
            )
        )
    return actual == expected


def _automation_detail_result(
    value: Any,
    *,
    expected_id: str | None = None,
    expected_enabled: bool | None = None,
    expected_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _automation_summary_result(
        value, expected_id=expected_id, expected_enabled=expected_enabled
    )
    if not _automation_mission_template_result(value.get("mission_template")):
        raise ProtocolError("la réponse n’expose pas le gabarit de mission")
    recent = value.get("recent_runs")
    if not isinstance(recent, list):
        raise ProtocolError("la réponse n’expose pas l’historique des déclenchements")
    for run in recent:
        _automation_run_result(run, expected_automation_id=result["id"])
    if expected_fields is not None and not _automation_requested_fields_match(
        value, _canonical_automation_request(expected_fields)
    ):
        raise ProtocolError(
            "la réponse ne confirme pas tous les champs d’automatisation demandés"
        )
    return result


def _automation_calendar_entry_result(value: Any) -> dict[str, Any]:
    valid = (
        isinstance(value, dict)
        and _automation_aware_instant(value.get("occurs_at_utc"))
        and _automation_aware_instant(value.get("occurs_at_local"))
        and isinstance(value.get("timezone"), str)
        and bool(value.get("timezone"))
        and value["timezone"] == value["timezone"].strip()
        and len(value["timezone"]) <= 64
        and _automation_integer(value.get("utc_offset_minutes"), minimum=-1440, maximum=1440)
        and isinstance(value.get("automation_id"), str)
        and bool(value.get("automation_id"))
        and isinstance(value.get("automation_name"), str)
        and value.get("state") in ("planned", "past")
        and (value.get("task_id") is None or isinstance(value.get("task_id"), str))
        and value.get("outcome") in (
            None, "launched", "skipped_concurrency", "skipped_disabled", "skipped_catchup", "failed"
        )
    )
    if not valid:
        raise ProtocolError("entrée de calendrier incomplète ou hors contrat")
    assert isinstance(value, dict)
    utc = datetime.fromisoformat(value["occurs_at_utc"].replace("Z", "+00:00"))
    local = datetime.fromisoformat(value["occurs_at_local"].replace("Z", "+00:00"))
    if utc != local or int(local.utcoffset().total_seconds() // 60) != value["utc_offset_minutes"]:
        raise ProtocolError("entrée de calendrier temporellement incohérente")
    return dict(value)


def _automation_list_result(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProtocolError("la liste des automatisations est hors contrat")
    return [_automation_summary_result(item) for item in value]


def _automation_runs_result(value: Any, automation_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProtocolError("l’historique des déclenchements est hors contrat")
    return [
        _automation_run_result(item, expected_automation_id=automation_id)
        for item in value
    ]


def _automation_calendar_result(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProtocolError("le calendrier est hors contrat")
    return [_automation_calendar_entry_result(item) for item in value]


def _automation_webhook_status_result(
    value: Any,
    *,
    automation_id: str,
    expected_enabled: bool | None = None,
    expected_secret: str | None = None,
) -> dict[str, Any]:
    status_fields = {
        "enabled",
        "secret_configured",
        "endpoint_path",
        "rotated_at",
    }
    allowed_fields = (
        (status_fields | {"secret"},)
        if expected_secret is not None
        else (status_fields,)
    )
    if not isinstance(value, dict) or set(value) not in allowed_fields:
        raise ProtocolError("réponse webhook incomplète ou hors contrat")
    enabled = value.get("enabled")
    configured = value.get("secret_configured")
    rotated_at = value.get("rotated_at")
    expected_path = f"/automations/{automation_id}/webhook/trigger"
    valid = (
        isinstance(enabled, bool)
        and isinstance(configured, bool)
        and enabled is configured
        and value.get("endpoint_path") == expected_path
        and (rotated_at is None or _automation_aware_instant(rotated_at))
    )
    if expected_enabled is not None:
        valid = valid and enabled is expected_enabled
    if expected_secret is not None:
        returned_secret = value.get("secret")
        valid = (
            valid
            and enabled is True
            and configured is True
            and _automation_aware_instant(rotated_at)
            and returned_secret == expected_secret
        )
    if not valid:
        raise ProtocolError("réponse webhook incohérente")
    return dict(value)


def _strip_one_line_ending(value: str) -> str:
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    return value


def _read_webhook_secret_file(path: Path) -> str:
    """Lit un secret privé sans suivre de lien ni rouvrir le chemin sur POSIX."""

    raw_path = str(path)
    if os.name != "posix":
        info = _regular_file_stat(
            raw_path, path, what="le fichier de secret webhook"
        )
        if info.st_size > AUTOMATION_WEBHOOK_SECRET_MAX_BYTES:
            raise UsageError("le fichier de secret webhook dépasse 512 octets")
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UsageError(
                "le fichier de secret webhook doit être encodé en UTF-8"
            ) from exc
        except OSError as exc:
            raise UsageError(
                "lecture impossible du fichier de secret webhook : "
                f"{_system_reason(exc)}"
            ) from exc

    try:
        before = os.lstat(path)
    except OSError as exc:
        raise UsageError(
            "lecture impossible du fichier de secret webhook : "
            f"{_system_reason(exc)}"
        ) from exc
    if stat.S_ISLNK(before.st_mode):
        raise UsageError("le fichier de secret webhook ne peut pas être un lien symbolique")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise UsageError(
            "lecture impossible du fichier de secret webhook : "
            f"{_system_reason(exc)}"
        ) from exc

    try:
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise UsageError("le fichier de secret webhook n'est pas un fichier régulier")
            if info.st_mode & 0o077:
                raise UsageError(
                    "le fichier de secret webhook doit être privé (chmod 600)"
                )
            if not os.path.samestat(before, info):
                raise UsageError(
                    "le fichier de secret webhook a changé pendant son ouverture"
                )
            if not nofollow:
                # Sur les rares POSIX sans O_NOFOLLOW, les deux comparaisons
                # encadrent open(); la lecture porte ensuite uniquement sur ce FD.
                try:
                    after = os.lstat(path)
                except OSError as exc:
                    raise UsageError(
                        "le fichier de secret webhook a changé pendant son ouverture"
                    ) from exc
                if (
                    stat.S_ISLNK(after.st_mode)
                    or not os.path.samestat(after, info)
                ):
                    raise UsageError(
                        "le fichier de secret webhook a changé pendant son ouverture"
                    )
            if info.st_size > AUTOMATION_WEBHOOK_SECRET_MAX_BYTES:
                raise UsageError("le fichier de secret webhook dépasse 512 octets")
            payload = handle.read(AUTOMATION_WEBHOOK_SECRET_MAX_BYTES + 1)
    except UsageError:
        raise
    except OSError as exc:
        raise UsageError(
            "lecture impossible du fichier de secret webhook : "
            f"{_system_reason(exc)}"
        ) from exc

    if len(payload) > AUTOMATION_WEBHOOK_SECRET_MAX_BYTES:
        raise UsageError("le fichier de secret webhook dépasse 512 octets")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UsageError(
            "le fichier de secret webhook doit être encodé en UTF-8"
        ) from exc


def _automation_webhook_secret(
    args: argparse.Namespace, environ: Mapping[str, str]
) -> str:
    if (
        getattr(args, "forbidden_secret", None) is not None
        or getattr(args, "forbidden_secret_option", None) is not None
    ):
        raise UsageError(
            "le secret webhook ne se passe jamais directement en argument : "
            "utilisez --secret-env ou --secret-file"
        )
    env_name = getattr(args, "secret_env", None)
    secret_file = getattr(args, "secret_file", None)
    if env_name is not None:
        name = env_name.strip()
        if not name or ENVIRONMENT_NAME_PATTERN.fullmatch(name) is None:
            raise UsageError("--secret-env attend un nom de variable valide")
        if name not in environ:
            raise UsageError("la variable demandée par --secret-env est absente")
        secret = environ[name]
    elif secret_file is not None:
        if not str(secret_file).strip():
            raise UsageError("--secret-file attend un chemin non vide")
        secret = _strip_one_line_ending(_read_webhook_secret_file(secret_file))
    else:
        secret = secrets.token_urlsafe(32)
    if AUTOMATION_WEBHOOK_SECRET_PATTERN.fullmatch(secret) is None:
        raise UsageError(
            "le secret webhook doit contenir 43 à 200 caractères base64url"
        )
    padding = "=" * (-len(secret) % 4)
    try:
        decoded = base64.b64decode(
            secret + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise UsageError("le secret webhook doit être encodé en base64url") from exc
    if len(decoded) < 32:
        raise UsageError("le secret webhook doit représenter au moins 256 bits")
    return secret


def _handle_automation_create(
    args: argparse.Namespace, client: ACPClient
) -> dict[str, Any]:
    project_id = _require_option_text(args.project, "--project")
    key = _command_idempotency_key(args.idempotency_key, "automation-create")
    path = f"/projects/{_path_segment(project_id)}/automations"
    payload = _automation_create_payload(args)

    def validate(value: Any) -> dict[str, Any]:
        result = _automation_detail_result(
            value,
            expected_enabled=False,
            expected_fields=payload,
        )
        if result["project_id"] != project_id:
            raise ProtocolError("la réponse vise un autre projet")
        return result

    output = _idempotent_automation_mutation(
        client,
        method="POST",
        path=path,
        key=key,
        operation="création d’automatisation",
        command="acp automations create",
        recovery="retry_automation_create_with_same_key",
        validator=validate,
        json_body=payload,
    )
    output["idempotency_key"] = key
    return output


def _handle_automation_update(
    args: argparse.Namespace, client: ACPClient
) -> dict[str, Any]:
    automation_id = _require_text(args.automation_id, "identifiant")
    path = f"/automations/{_path_segment(automation_id)}"
    payload = _automation_update_payload(args)
    key = _command_idempotency_key(args.idempotency_key, "automation-update")
    output = _idempotent_automation_mutation(
        client,
        method="PATCH",
        path=path,
        key=key,
        operation="modification de l’automatisation",
        command="acp automations update AUTOMATION_ID",
        recovery="retry_automation_update_with_same_key_and_payload",
        validator=lambda value: _automation_detail_result(
            value,
            expected_id=automation_id,
            expected_fields=payload,
        ),
        json_body=payload,
    )
    output["idempotency_key"] = key
    return output


def _handle_automation_enabled(
    args: argparse.Namespace, client: ACPClient, *, enabled: bool
) -> dict[str, Any]:
    automation_id = _require_text(args.automation_id, "identifiant")
    action = "enable" if enabled else "disable"
    key = _command_idempotency_key(
        args.idempotency_key, f"automation-{action}"
    )
    path = f"/automations/{_path_segment(automation_id)}/{action}"
    output = _idempotent_automation_mutation(
        client,
        method="POST",
        path=path,
        key=key,
        operation="activation" if enabled else "désactivation",
        command=f"acp automations {action} AUTOMATION_ID",
        recovery=f"retry_automation_{action}_with_same_key",
        validator=lambda value: _automation_detail_result(
            value,
            expected_id=automation_id,
            expected_enabled=enabled,
        ),
    )
    output["idempotency_key"] = key
    return output


def _handle_automation_webhook_rotate(
    args: argparse.Namespace,
    client: ACPClient,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    automation_id = _require_text(args.automation_id, "identifiant")
    secret = _automation_webhook_secret(args, environ)
    key = _command_idempotency_key(
        args.idempotency_key, "automation-webhook-rotate"
    )
    path = f"/automations/{_path_segment(automation_id)}/webhook"
    output = _idempotent_automation_mutation(
        client,
        method="POST",
        path=path,
        key=key,
        operation="rotation du webhook",
        command="acp automations webhook rotate AUTOMATION_ID",
        recovery="retry_automation_webhook_rotate_with_same_key_and_secret",
        validator=lambda value: _automation_webhook_status_result(
            value,
            automation_id=automation_id,
            expected_enabled=True,
            expected_secret=secret,
        ),
        json_body={"secret": secret},
        retry_secret=secret,
    )
    output["secret"] = secret
    output["idempotency_key"] = key
    return output


def _handle_automation_webhook_disable(
    args: argparse.Namespace, client: ACPClient
) -> dict[str, Any]:
    automation_id = _require_text(args.automation_id, "identifiant")
    key = _command_idempotency_key(
        args.idempotency_key, "automation-webhook-disable"
    )
    path = f"/automations/{_path_segment(automation_id)}/webhook"
    output = _idempotent_automation_mutation(
        client,
        method="DELETE",
        path=path,
        key=key,
        operation="désactivation du webhook",
        command="acp automations webhook disable AUTOMATION_ID",
        recovery="retry_automation_webhook_disable_with_same_key",
        validator=lambda value: _automation_webhook_status_result(
            value,
            automation_id=automation_id,
            expected_enabled=False,
        ),
    )
    output["idempotency_key"] = key
    return output


def _handle_automation_trigger(args: argparse.Namespace, client: ACPClient) -> dict[str, Any]:
    automation_id = _require_text(args.automation_id, "identifiant")
    key = _command_idempotency_key(args.idempotency_key, "automation-trigger")
    path = f"/automations/{_path_segment(automation_id)}/trigger"
    try:
        result = client.request("POST", path, idempotency_key=key)
    except NetworkError as exc:
        raise _automation_trigger_failure(
            key, code="network", exit_code=ExitCode.NETWORK
        ) from exc
    except APIError as exc:
        if exc.status_code != 408 and exc.status_code < 500:
            raise
        raise _automation_trigger_failure(
            key,
            code="api",
            exit_code=ExitCode.REMOTE,
            status_code=exc.status_code,
        ) from exc
    except ProtocolError as exc:
        raise _automation_trigger_failure(
            key, code="client", exit_code=ExitCode.REMOTE
        ) from exc
    try:
        output = _automation_run_result(
            result, expected_automation_id=automation_id
        )
    except ProtocolError:
        raise _automation_trigger_failure(
            key, code="client", exit_code=ExitCode.REMOTE
        )
    output["idempotency_key"] = key
    if output["outcome"] != "launched":
        raise AutomationOutcomeError(output)
    return output


def _targets_secrets(argv: Sequence[str]) -> bool:
    """Indique si la ligne de commande vise le groupe `secrets`.

    Seul ce groupe peut transporter du matériel secret : la censure des messages
    d'usage y est appliquée, sans dégrader la lisibilité des autres commandes.
    """

    if _command_group(argv) == "secrets":
        return True
    # La rotation webhook refuse les secrets en argv, mais argparse pourrait
    # citer un argument surnuméraire. Appliquer la même censure défensive évite
    # de recopier une valeur accidentelle avant même l'entrée dans le handler.
    return (
        _command_group(argv) == "automations"
        and "webhook" in argv
        and "rotate" in argv
    )


def _mask_secret_material(message: str, argv: Sequence[str]) -> str:
    """Remplace toute valeur accolée à un `=` par `***` dans un message d'usage.

    argparse cite l'argument fautif ; sur le groupe `secrets`, cette citation
    pourrait recopier une valeur en clair dans stderr ou dans un journal.
    """

    if not _targets_secrets(argv):
        return message
    masked = re.sub(r"(?<==)\S+", "***", message)
    instruction = (
        "arguments surnuméraires : utilisez --value-stdin, jamais un argument, "
        "pour la valeur d'un secret"
        if _command_group(argv) == "secrets"
        else "arguments surnuméraires : utilisez --secret-env ou --secret-file, "
        "jamais un argument, pour le secret webhook"
    )
    return re.sub(
        r"unrecognized arguments:.*",
        instruction,
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


def _read_import_file(raw_path: str) -> str:
    """Lit le fichier de configuration à importer, borné localement (1 MiB puis 1 000 000 caractères)."""

    if not raw_path.strip():
        raise UsageError("le chemin du fichier de configuration ne peut pas être vide")
    path = Path(raw_path)
    if not path.exists():
        raise UsageError(f"fichier de configuration introuvable : {raw_path}")
    info = _regular_file_stat(raw_path, path, what="le fichier de configuration")
    if info.st_size > MAX_IMPORT_FILE_BYTES:
        raise UsageError("le fichier de configuration dépasse la limite locale de 1 MiB")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UsageError("le fichier de configuration doit être encodé en UTF-8") from exc
    except OSError as exc:
        raise UsageError(
            f"lecture impossible du fichier de configuration « {raw_path} » : {_system_reason(exc)}"
        ) from exc
    if len(content) > MAX_IMPORT_CHARS:
        raise UsageError(
            f"le fichier de configuration dépasse {MAX_IMPORT_CHARS} caractères : "
            "l'API refuse un contenu plus long"
        )
    return content


def _parse_secret_mapping(values: Sequence[str]) -> dict[str, str]:
    """Traduit les `--map SECRET_NAME=SECRET_ID` ; aucune valeur de secret n'est acceptée ici."""

    expected = "--map attend SECRET_NAME=SECRET_ID (nom d'un secret existant du coffre)"
    mapping: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise UsageError(expected)
        name, secret_id = raw.split("=", 1)
        name, secret_id = name.strip(), secret_id.strip()
        if not name or not secret_id:
            raise UsageError(expected)
        if not SECRET_NAME_PATTERN.match(name):
            raise UsageError(
                "--map attend un nom de secret en majuscules (^[A-Z][A-Z0-9_]{1,62}$), "
                "tel que proposé par l'aperçu"
            )
        if name in mapping:
            raise UsageError(f"--map définit « {name} » deux fois")
        mapping[name] = secret_id
    return mapping


def _import_entry_names(values: Sequence[str]) -> list[str]:
    names: list[str] = []
    for raw in values:
        name = raw.strip()
        if not name:
            raise UsageError("--name exige un nom d'entrée non vide")
        if name not in names:
            names.append(name)
    return names


def _import_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ProtocolError("l'API n'a pas retourné un résultat d'import exploitable")
    return [str(item) for item in value]


def _import_table(entries: Sequence[Any]) -> list[str]:
    """Tableau aligné de l'aperçu ; les valeurs viennent du fichier importé (données non fiables)."""

    rows: list[tuple[str, ...]] = [("NOM", "TRANSPORT", "IMPORTABLE", "CONFLIT", "SECRETS", "SOURCE")]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ProtocolError("l'API n'a pas retourné un aperçu d'import exploitable")
        candidates = entry.get("secret_candidates")
        rows.append(
            (
                entry["name"],
                str(entry.get("transport") or "-"),
                "oui" if entry.get("importable") else "non",
                str(entry.get("conflict") or "none"),
                str(len(candidates) if isinstance(candidates, list) else 0),
                str(entry.get("source_name") or "")[:60],
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    return [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip()
        for row in rows
    ]


def _print_import_entry_details(entry: Mapping[str, Any], stream: TextIO) -> None:
    lines: list[str] = []
    for candidate in entry.get("secret_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        lines.append(
            f"  secret à fournir : {candidate.get('suggested_secret_name')} "
            f"({candidate.get('location')} « {candidate.get('key')} », "
            f"valeur masquée {candidate.get('masked_value')})"
        )
    for item in entry.get("unsupported") or []:
        lines.append(f"  non supporté : {item}")
    for item in entry.get("warnings") or []:
        lines.append(f"  avertissement : {item}")
    if lines:
        print(f"{entry.get('name')} :", file=stream)
        for line in lines:
            print(line, file=stream)


def _handle_mcp_import(
    args: argparse.Namespace, client: ACPClient, *, stdout: TextIO, stderr: TextIO
) -> None:
    """Aperçu (par défaut) ou application explicite d'une configuration MCP existante."""

    if not args.apply and (args.name or args.mapping or args.on_conflict):
        raise UsageError(
            "--name, --map et --on-conflict ne s'appliquent qu'avec --apply : "
            "sans --apply, la commande se limite à un aperçu"
        )
    names = _import_entry_names(args.name) if args.apply else []
    mapping = _parse_secret_mapping(args.mapping) if args.apply else {}
    if args.apply and not names:
        raise UsageError(
            "--apply exige au moins une entrée à importer (--name), listée par l'aperçu"
        )
    content = _read_import_file(args.path)

    if not args.apply:
        preview = client.request(
            "POST",
            "/mcp/import/preview",
            json_body={"format": args.import_format, "content": content},
        )
        if not isinstance(preview, dict) or not isinstance(preview.get("entries"), list):
            raise ProtocolError("l'API n'a pas retourné un aperçu d'import exploitable")
        entries = preview["entries"]
        if args.json:
            _emit(preview, as_json=True, stream=stdout)
        else:
            print(f"Format détecté : {preview.get('detected_format') or 'inconnu'}", file=stdout)
            for line in _import_table(entries):
                print(line, file=stdout)
            for entry in entries:
                if isinstance(entry, dict):
                    _print_import_entry_details(entry, stdout)
        for error in _import_string_list(preview, "errors"):
            _emit_notice("import_analysis_error", error, as_json=args.json, stream=stderr)
        if not entries:
            raise CommandError(
                "import_empty", "aucune entrée n'a été trouvée : rien à importer depuis ce fichier"
            )
        _emit_notice(
            "import_preview_only",
            "Aperçu seul : relancez avec --apply --name <entrée> pour créer les serveurs "
            "(ils resteront en brouillon).",
            as_json=args.json,
            stream=stderr,
        )
        return

    result = client.request(
        "POST",
        "/mcp/import/apply",
        json_body={
            "format": args.import_format,
            "content": content,
            "names": names,
            "secret_mapping": mapping,
            "on_conflict": args.on_conflict or "skip",
        },
    )
    if not isinstance(result, dict):
        raise ProtocolError("l'API n'a pas retourné un résultat d'import exploitable")
    created = _items(result.get("created")) if isinstance(result.get("created"), list) else None
    revised = _items(result.get("revised")) if isinstance(result.get("revised"), list) else None
    if created is None or revised is None:
        raise ProtocolError("l'API n'a pas retourné un résultat d'import exploitable")
    skipped = _import_string_list(result, "skipped")
    errors = _import_string_list(result, "errors")
    if args.json:
        _emit(result, as_json=True, stream=stdout)
    else:
        for label, servers in (("créé", created), ("révisé", revised)):
            for server in servers:
                name = server.get("name") if isinstance(server, dict) else None
                identifier = server.get("id") if isinstance(server, dict) else None
                print(f"{label} : {name} ({identifier}) — statut brouillon", file=stdout)
        for name in skipped:
            print(f"ignoré : {name}", file=stdout)
    for error in errors:
        _emit_notice("import_entry_error", error, as_json=args.json, stream=stderr)
    if not created and not revised:
        raise CommandError(
            "import_failed",
            "aucune entrée n'a été importée : chaque refus est détaillé ci-dessus",
        )


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


# ---------------------------------------------------------------------------
# Lot E — journal d'événements, flux, validation technique et artefacts
# ---------------------------------------------------------------------------


def _open_stream(
    client: ACPClient,
    path: str,
    *,
    accept: str,
    params: Mapping[str, Any] | None = None,
    extra_headers: Mapping[str, str] | None = None,
    read_timeout: float | None = None,
) -> tuple[httpx.Client, httpx.Response]:
    """Ouvre une réponse en flux avec la politique de ``ACPClient.request_response``.

    Le transport du client n'expose pas le mode flux ; cette fonction le
    reproduit à l'identique (cookie de session lié à l'origine, pas de proxy
    d'environnement, aucune redirection suivie) pour le SSE et le contenu
    d'artefact, qui ne doivent jamais être chargés entièrement en mémoire.

    La fermeture est rendue à l'appelant (``try``/``finally``) et non confiée à
    un gestionnaire de contexte : ``APIError`` est un dataclass **gelé**, et le
    ``__exit__`` de ``contextlib`` lui affecte ``__traceback__``, ce qui lèverait
    un ``FrozenInstanceError`` à la place de l'erreur d'API réelle.
    """

    headers = {"Accept": accept, "User-Agent": USER_AGENT}
    headers.update(extra_headers or {})
    settings = client.settings
    cookies: dict[str, str] = {}
    if settings.authenticated and settings.session_cookie:
        cookies[SESSION_COOKIE_NAME] = settings.session_cookie
    http = httpx.Client(
        base_url=f"{settings.api_url}/",
        headers=headers,
        cookies=cookies,
        timeout=httpx.Timeout(client.timeout, read=read_timeout),
        transport=client.transport,
        follow_redirects=False,
        trust_env=False,
    )
    try:
        request = http.build_request("GET", path.lstrip("/"), params=params)
        response = http.send(request, stream=True)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        http.close()
        raise NetworkError("API ACP injoignable") from exc
    except httpx.HTTPError as exc:
        http.close()
        raise NetworkError("échec du transport HTTP") from exc
    except BaseException:
        http.close()
        raise
    status = response.status_code
    if status < 400 and not response.is_redirect:
        return http, response
    detail = "requête refusée"
    try:
        if status >= 400:
            response.read()
            detail = _api_error_detail(response)
    except httpx.HTTPError:
        detail = "réponse d'erreur illisible"
    finally:
        response.close()
        http.close()
    if status >= 400:
        raise APIError(status, detail)
    raise ProtocolError("redirection HTTP inattendue")


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _counter(value: Any, label: str) -> int:
    """Compteur de totaux : absent vaut zéro, illisible est refusé."""

    if value is None:
        return 0
    parsed = _positive_int(value)
    if parsed is None:
        raise ProtocolError(f"l'API a retourné un total « {label} » illisible")
    return parsed


def _mission_run_id(client: ACPClient, identifier: str) -> str | None:
    """Identifiant du run courant d'une mission, ou ``None`` si ce n'en est pas une."""

    try:
        detail = client.request("GET", f"/missions/{_path_segment(identifier)}")
    except APIError as exc:
        if exc.status_code == 404:
            return None
        raise
    run = detail.get("current_run") if isinstance(detail, dict) else None
    candidate = run.get("id") if isinstance(run, dict) else None
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


def _run_scoped(
    client: ACPClient, identifier: str, call: Callable[[str], Any]
) -> tuple[str, Any]:
    """Exécute ``call`` sur un run ; si l'identifiant est une mission, la résout.

    La spécification accepte « mission-id | run-id ». Le cas courant (un run)
    ne coûte qu'un appel : la résolution n'a lieu qu'après un 404 franc.
    """

    run_id = _require_text(identifier, "l'identifiant du run")
    try:
        return run_id, call(run_id)
    except APIError as exc:
        if exc.status_code != 404:
            raise
        resolved = _mission_run_id(client, run_id)
        if resolved is None or resolved == run_id:
            raise
        return resolved, call(resolved)


def _events_limit(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= EVENTS_MAX_LIMIT:
        raise UsageError(f"--limit doit être compris entre 1 et {EVENTS_MAX_LIMIT}")
    return value


def _events_after_seq(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UsageError("--after-seq ne peut pas être négatif")
    return value


def _events_page(
    client: ACPClient, run_id: str, *, after_seq: int | None, limit: int | None
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if after_seq is not None:
        params["after_seq"] = after_seq
    if limit is not None:
        params["limit"] = limit
    body = client.request("GET", f"/runs/{_path_segment(run_id)}/events", params=params)
    if not isinstance(body, dict) or not isinstance(body.get("events"), list):
        raise ProtocolError("l'API n'a pas retourné une page d'événements")
    return body


class _EventSink:
    """Écriture dédupliquée des événements, par séquence puis par identifiant.

    Le flux et le journal durable se recouvrent volontairement : la reprise
    relit à partir du dernier curseur reçu, et cette classe garantit qu'aucun
    événement n'est écrit deux fois ni sauté.
    """

    def __init__(self, *, ndjson: bool, stream: TextIO) -> None:
        self._ndjson = ndjson
        self._stream = stream
        self._seen: dict[str, None] = {}
        self.last_sequence: int | None = None
        self.count = 0

    def offer(self, event: Any) -> bool:
        if not isinstance(event, dict):
            raise ProtocolError("l'API a retourné un événement illisible")
        sequence = _positive_int(event.get("sequence"))
        if (
            sequence is not None
            and self.last_sequence is not None
            and sequence <= self.last_sequence
        ):
            return False
        identifier = event.get("id")
        if isinstance(identifier, str) and identifier:
            if identifier in self._seen:
                return False
            self._seen[identifier] = None
            while len(self._seen) > FOLLOW_SEEN_IDS_MAX:
                self._seen.pop(next(iter(self._seen)))
        if sequence is not None:
            self.last_sequence = sequence
        if self._ndjson:
            _emit(event, as_json=True, stream=self._stream)
        else:
            print(_event_line(event), file=self._stream)
        self.count += 1
        return True


def _event_line(event: Mapping[str, Any]) -> str:
    """Ligne lisible : séquence, horodatage, type, identifiant."""

    sequence = _positive_int(event.get("sequence"))
    return " ".join(
        (
            str(sequence) if sequence is not None else "-",
            str(event.get("occurred_at") or "-"),
            str(event.get("type") or "-"),
            str(event.get("id") or "-"),
        )
    )


def _emit_cursor_notice(
    code: str,
    message: str,
    *,
    cursor: int | None,
    as_json: bool,
    stream: TextIO,
) -> None:
    """Avis d'observation : le curseur de reprise reste lisible par machine."""

    if as_json:
        _emit(
            {"notice": {"code": code, "message": message, "next_cursor": cursor}},
            as_json=True,
            stream=stream,
        )
    else:
        print(message, file=stream)


def _drain_events(
    client: ACPClient,
    run_id: str,
    *,
    sink: _EventSink,
    after_seq: int | None,
    limit: int | None,
    resolve: bool,
) -> str:
    """Lit le journal durable page par page jusqu'à épuisement.

    Retourne l'identifiant de run effectivement utilisé (résolu au besoin).
    """

    cursor = after_seq
    pages = 0
    while True:
        if resolve:
            run_id, body = _run_scoped(
                client,
                run_id,
                lambda candidate, position=cursor: _events_page(
                    client, candidate, after_seq=position, limit=limit
                ),
            )
            resolve = False
        else:
            body = _events_page(client, run_id, after_seq=cursor, limit=limit)
        for item in body["events"]:
            sink.offer(item)
        pages += 1
        if not body.get("has_more"):
            return run_id
        if pages >= EVENTS_MAX_PAGES:
            raise ProtocolError("trop de pages d'événements : lecture interrompue")
        next_cursor = _positive_int(body.get("next_cursor"))
        if next_cursor is None or next_cursor <= (cursor or 0):
            raise ProtocolError("le curseur d'événements n'avance pas : lecture interrompue")
        cursor = next_cursor


def _iter_stream_events(response: httpx.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    """Décode un flux SSE en ``(nom de trame, objet JSON)``.

    Le nom est porteur de sens : le serveur n'émet un événement de journal que
    sous ``acp.event``, et pilote la connexion avec ``acp.stream.rotate`` et
    ``acp.stream.closed`` (§5.2). Les confondre reviendrait à écrire une trame de
    contrôle dans le NDJSON du journal. Une trame sans nom est traitée comme un
    événement : c'est la valeur par défaut de la spécification SSE.
    """

    data: list[str] = []
    name = ""
    size = 0
    for line in response.iter_lines():
        if line.startswith(":"):
            continue
        if not line:
            if not data:
                name = ""
                continue
            raw = "\n".join(data)
            frame = name or SSE_EVENT_NAME
            data = []
            name = ""
            size = 0
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                raise ProtocolError("le flux a livré un événement illisible") from exc
            if not isinstance(payload, dict):
                raise ProtocolError("le flux a livré un événement illisible")
            yield frame, payload
            continue
        field, _, value = line.partition(":")
        chunk = value[1:] if value.startswith(" ") else value
        if field == "event":
            name = chunk.strip()
            continue
        if field != "data":
            continue
        size += len(chunk)
        if size > SSE_MAX_EVENT_CHARS:
            raise ProtocolError("le flux a dépassé la taille maximale d'un événement")
        data.append(chunk)


def _degraded_notice(
    reason: str, *, sink: _EventSink, as_json: bool, stream: TextIO
) -> None:
    _emit_cursor_notice(
        "stream_degraded",
        f"Flux interrompu ({reason}) : reprise par lecture du journal durable "
        f"à partir de la séquence {sink.last_sequence or 0}.",
        cursor=sink.last_sequence,
        as_json=as_json,
        stream=stream,
    )


class _StreamOutcome(NamedTuple):
    """Comment un flux SSE s'est terminé.

    ``end`` : le serveur a fermé sans rien dire. ``rotate`` : durée maximale
    atteinte, la mission continue et le client doit se reconnecter au curseur
    porté par la trame. ``closed`` : le serveur a annoncé une fermeture.
    """

    kind: str
    cursor: int | None = None
    reason: str = ""


def _consume_stream(
    client: ACPClient, run_id: str, *, sink: _EventSink, cursor: int | None
) -> _StreamOutcome:
    """Ouvre le flux au curseur donné et n'écrit que les événements de journal."""

    params: dict[str, Any] = {}
    headers: dict[str, str] = {}
    if cursor is not None:
        params["after_seq"] = cursor
        # ``Last-Event-ID`` est prioritaire côté serveur (§6) : les deux portent
        # la même valeur, une reconnexion ne rejoue donc rien.
        headers["Last-Event-ID"] = str(cursor)
    http, response = _open_stream(
        client,
        f"/streams/runs/{_path_segment(run_id)}",
        accept="text/event-stream",
        params=params,
        extra_headers=headers,
        read_timeout=None,
    )
    try:
        for frame, payload in _iter_stream_events(response):
            if frame == SSE_ROTATE_EVENT:
                return _StreamOutcome(
                    "rotate",
                    _positive_int(payload.get("cursor")),
                    str(payload.get("reason") or ""),
                )
            if frame == SSE_CLOSED_EVENT:
                reason = str(payload.get("reason") or "")
                if reason == "unauthorized":
                    # Le serveur revalide session et membership à chaque page :
                    # une révocation en cours d'observation est un refus d'accès,
                    # pas une ligne de journal ni une fin normale.
                    raise CommandError(
                        "stream_unauthorized",
                        "le serveur a fermé le flux : accès révoqué pendant "
                        "l'observation (session ou membership)",
                        ExitCode.AUTH,
                    )
                return _StreamOutcome("closed", None, reason)
            if frame != SSE_EVENT_NAME:
                # Trame de contrôle inconnue : elle ne porte pas un événement de
                # journal et ne sera donc jamais écrite comme tel.
                continue
            sink.offer(payload)
    finally:
        response.close()
        http.close()
    return _StreamOutcome("end")


def _follow_events(
    client: ACPClient,
    run_id: str,
    *,
    sink: _EventSink,
    after_seq: int | None,
    limit: int | None,
    as_json: bool,
    stderr: TextIO,
) -> None:
    """Observation : journal durable, puis flux, puis réconciliation par curseur."""

    run_id = _drain_events(
        client, run_id, sink=sink, after_seq=after_seq, limit=limit, resolve=True
    )
    cursor = sink.last_sequence if sink.last_sequence is not None else after_seq
    rotations = 0
    while True:
        try:
            outcome = _consume_stream(client, run_id, sink=sink, cursor=cursor)
        except APIError as exc:
            # Un refus d'accès ou une requête invalide doivent rester visibles :
            # seule l'indisponibilité du flux lui-même justifie l'interrogation.
            if exc.status_code != 404 and exc.status_code < 500:
                raise
            _degraded_notice(exc.detail, sink=sink, as_json=as_json, stream=stderr)
            break
        except (NetworkError, ProtocolError, httpx.HTTPError) as exc:
            # Une coupure n'invente aucun état : on le dit, puis on relit le
            # journal durable à partir du dernier curseur reçu.
            _degraded_notice(str(exc), sink=sink, as_json=as_json, stream=stderr)
            break
        if outcome.kind == "closed":
            _emit_cursor_notice(
                "stream_closed",
                "Flux fermé par le serveur "
                f"({outcome.reason or 'sans raison annoncée'}) : la mission n'est "
                "pas arrêtée.",
                cursor=sink.last_sequence,
                as_json=as_json,
                stream=stderr,
            )
            break
        if outcome.kind != "rotate":
            break
        if rotations >= FOLLOW_MAX_ROTATIONS:
            _emit_cursor_notice(
                "stream_rotations_exhausted",
                f"Le flux a tourné {rotations} fois : observation arrêtée, la "
                "mission n'est pas arrêtée.",
                cursor=sink.last_sequence,
                as_json=as_json,
                stream=stderr,
            )
            break
        rotations += 1
        cursor = outcome.cursor if outcome.cursor is not None else sink.last_sequence
        _emit_cursor_notice(
            "stream_rotated",
            "Le flux a atteint sa durée maximale : la mission continue, "
            f"reconnexion à partir de la séquence {cursor or 0}.",
            cursor=cursor,
            as_json=as_json,
            stream=stderr,
        )
    _drain_events(
        client, run_id, sink=sink, after_seq=sink.last_sequence, limit=limit, resolve=False
    )
    _emit_cursor_notice(
        "follow_ended",
        "Observation terminée : "
        f"reprenez avec --after-seq {sink.last_sequence or 0} si nécessaire.",
        cursor=sink.last_sequence,
        as_json=as_json,
        stream=stderr,
    )


def _handle_runs_events(
    args: argparse.Namespace,
    client: ACPClient,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    limit = _events_limit(args.limit)
    after_seq = _events_after_seq(args.after_seq)
    # En observation, la sortie est du NDJSON même sans ``--json`` : c'est un
    # flux, pas un tableau.
    sink = _EventSink(ndjson=bool(args.json or args.follow), stream=stdout)
    try:
        if args.follow:
            _follow_events(
                client,
                args.run_id,
                sink=sink,
                after_seq=after_seq,
                limit=limit,
                as_json=args.json,
                stderr=stderr,
            )
            return
        _run_id, body = _run_scoped(
            client,
            args.run_id,
            lambda candidate: _events_page(
                client, candidate, after_seq=after_seq, limit=limit
            ),
        )
        for item in body["events"]:
            sink.offer(item)
        if body.get("has_more"):
            cursor = _positive_int(body.get("next_cursor")) or sink.last_sequence
            _emit_cursor_notice(
                "events_truncated",
                f"Page incomplète : relancez avec --after-seq {cursor} pour la suite.",
                cursor=cursor,
                as_json=args.json,
                stream=stderr,
            )
    except KeyboardInterrupt:
        _emit_cursor_notice(
            "follow_interrupted",
            "Observation interrompue localement : la mission n'est pas arrêtée. "
            f"Reprenez avec --after-seq {sink.last_sequence or 0}.",
            cursor=sink.last_sequence,
            as_json=args.json,
            stream=stderr,
        )
        raise


def _test_summary(detail: Any) -> dict[str, Any]:
    """Dérive la validation technique sans jamais forcer un succès.

    Règle **identique** à celle du serveur
    (`apps/api/src/acp_api/testing_service.py::derive_technical_validation`,
    spec §5.4) : `passed` seulement si `exit_code == 0` — un code de sortie
    absent est un refus —, si `unexpected`, `interrupted` et `timedOut` sont nuls
    et si au moins un cas a été exécuté. `status` est affiché mais n'ajoute
    aucune cause : le CLI est la porte qu'une CI franchit, il ne doit diverger de
    la validation technique de la tentative dans aucun des deux sens.
    """

    if not isinstance(detail, dict):
        raise ProtocolError("l'API n'a pas retourné une exécution de tests")
    raw_totals = detail.get("totals")
    totals_source = raw_totals if isinstance(raw_totals, dict) else {}
    totals = {key: _counter(totals_source.get(key), key) for key in TEST_TOTALS_KEYS}
    case_count = _positive_int(detail.get("case_count"))
    if case_count is None:
        cases = detail.get("cases")
        case_count = len(cases) if isinstance(cases, list) else 0
    status = detail.get("status")
    exit_code = detail.get("exit_code")
    reasons: list[str] = []
    if case_count < 1:
        reasons.append("case_count")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code != 0:
        reasons.append("exit_code")
    reasons.extend(key for key in TEST_FAILING_TOTALS if totals[key] > 0)
    report = detail.get("report_artifact")
    report_id = report.get("id") if isinstance(report, dict) else None
    return {
        "test_run_id": detail.get("id"),
        "task_run_id": detail.get("task_run_id"),
        "runner": detail.get("runner"),
        "status": status,
        "validation": "failed" if reasons else "passed",
        "reasons": reasons,
        "totals": totals,
        "case_count": case_count,
        "duration_ms": detail.get("duration_ms"),
        "exit_code": exit_code,
        "report_artifact_id": report_id,
    }


TEST_TOTAL_LABELS = (
    ("expected", "attendus"),
    ("unexpected", "inattendus"),
    ("flaky", "instables (flaky)"),
    ("skipped", "ignorés"),
    ("timedOut", "expirés (timedOut)"),
    ("interrupted", "interrompus"),
)


def _print_test_summary(summary: Mapping[str, Any], stream: TextIO) -> None:
    validation = "réussie" if summary["validation"] == "passed" else "échouée"
    print(
        f"Exécution de tests {summary['test_run_id']} ({summary['runner']}) — "
        f"statut {summary['status']}, validation technique : {validation}",
        file=stream,
    )
    totals = summary["totals"]
    for key, label in TEST_TOTAL_LABELS:
        print(f"{label} : {totals[key]}", file=stream)
    print(f"cas exécutés : {summary['case_count']}", file=stream)
    print(f"code de sortie : {summary['exit_code']}", file=stream)
    if summary["report_artifact_id"]:
        print(f"rapport : {summary['report_artifact_id']}", file=stream)


def _handle_runs_tests(
    args: argparse.Namespace, client: ACPClient, *, stdout: TextIO
) -> None:
    _run_id, detail = _run_scoped(
        client,
        args.run_id,
        lambda candidate: client.request(
            "GET", f"/runs/{_path_segment(candidate)}/test-run"
        ),
    )
    summary = _test_summary(detail)
    if args.json:
        _emit(summary, as_json=True, stream=stdout)
    else:
        _print_test_summary(summary, stdout)
    if summary["validation"] != "passed":
        raise CommandError(
            "tests_failed",
            "validation technique échouée : " + ", ".join(summary["reasons"]),
        )


def _artifact_matches(
    item: Any, *, run: str, kind: str, content_type: str
) -> bool:
    """Le filtrage reste local : un serveur qui ignore la requête ne fuit rien.

    ``--kind`` accepte les deux vocabulaires du modèle : le genre de flux du §3.2
    (`screenshot`, `video`, `trace`, `report`, `file`) **et** le genre d'artefact
    écrit par le worker (`test_attachment`, `test_report`). Ne comparer que
    `kind` faisait taire le filtre documenté pour tous les livrables du Lot E.
    """

    if not isinstance(item, dict):
        return True
    if item.get("task_run_id") != run:
        return False
    if kind and kind not in {
        str(item.get("kind") or ""),
        str(item.get("stream_kind") or ""),
    }:
        return False
    if content_type and str(item.get("content_type") or "").strip().lower() != content_type:
        return False
    return True


def _handle_artifacts_list(args: argparse.Namespace, client: ACPClient) -> list[Any]:
    run = _require_text(args.run, "--run")
    kind = (args.kind or "").strip()
    content_type = (args.content_type or "").strip().lower()
    base = _filtered_params(task_run_id=run, project_id=args.project)
    if kind in ARTIFACT_STREAM_KINDS:
        # §6 n'expose que `stream_kind` côté serveur : l'envoyer évite de
        # parcourir tous les artefacts du run. Le filtre local reste en place.
        base["stream_kind"] = kind
    collected: list[Any] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    pages = 0
    while True:
        params = dict(base)
        if cursor is not None:
            params["cursor"] = cursor
        body = client.request("GET", "/artifacts", params=params)
        collected.extend(
            item
            for item in _items(body)
            if _artifact_matches(item, run=run, kind=kind, content_type=content_type)
        )
        pages += 1
        next_cursor = body.get("next_cursor") if isinstance(body, dict) else None
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            return collected
        if next_cursor in seen_cursors or pages >= ARTIFACT_LIST_MAX_PAGES:
            raise ProtocolError("le curseur d'artefacts n'avance pas : lecture interrompue")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _clean_file_name(value: Any) -> str:
    """Nom de fichier sûr tiré d'une valeur venue du serveur, ou chaîne vide.

    Le nom d'origine est produit par un worker : il est traité comme une donnée
    hostile. Seul le dernier segment est conservé, et jamais un chemin.
    """

    candidate = str(value or "").replace("\\", "/").split("/")[-1].strip().strip(". ")
    if not candidate or len(candidate) > DOWNLOAD_NAME_MAX_CHARS:
        return ""
    if ":" in candidate or any(ord(character) < 32 for character in candidate):
        return ""
    if candidate.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        return ""
    return candidate


def _download_target(
    output: str | None, summary: Mapping[str, Any], artifact_id: str
) -> Path:
    name = _clean_file_name(summary.get("original_name")) or _clean_file_name(artifact_id)
    if output is None:
        if not name:
            raise UsageError("aucun nom de fichier sûr : précisez --output")
        return Path(name)
    destination = _require_text(output, "--output")
    path = Path(destination)
    if path.is_dir():
        if not name:
            raise UsageError("aucun nom de fichier sûr : précisez un fichier avec --output")
        return path / name
    return path


def _is_text_content_type(value: str) -> bool:
    return value.startswith("text/") or value in TEXT_CONTENT_TYPES


def _write_bytes(stream: TextIO, chunk: bytes) -> None:
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        stream.flush()
        buffer.write(chunk)
        return
    stream.write(chunk.decode("utf-8", errors="replace"))


def _served_content_type(response: httpx.Response) -> str:
    """Type réellement servi par l'API, seul type digne de confiance (§7)."""

    return str(response.headers.get("content-type") or "").split(";")[0].strip().lower()


def _refuse_binary_stdout(content_type: str) -> None:
    """Refuse d'écrire un contenu non textuel sur un terminal interactif."""

    if _is_text_content_type(content_type):
        return
    raise CommandError(
        "binary_stdout",
        f"« {content_type or 'type inconnu'} » est un contenu binaire : "
        "redirigez la sortie, utilisez --output, ou confirmez avec --force",
        ExitCode.USAGE,
    )


def _download_artifact(
    client: ACPClient,
    artifact_id: str,
    *,
    writer: Callable[[bytes], Any],
    max_bytes: int,
    on_content_type: Callable[[str], None] | None = None,
) -> tuple[str, int, str]:
    """Écrit le contenu par morceaux bornés et retourne (sha256, taille, type servi).

    ``on_content_type`` est appelé avec le type servi **avant le premier octet
    écrit** : c'est là que se décide ce qui peut atteindre un terminal.
    """

    digest = hashlib.sha256()
    size = 0
    http, response = _open_stream(
        client,
        f"/artifacts/{_path_segment(artifact_id)}/content",
        accept="*/*",
        read_timeout=client.timeout,
    )
    served = ""
    try:
        served = _served_content_type(response)
        if on_content_type is not None:
            on_content_type(served)
        for chunk in response.iter_bytes(ARTIFACT_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise CommandError(
                    "artifact_too_large",
                    "contenu plus volumineux que la taille annoncée "
                    f"({max_bytes} octets) : téléchargement interrompu",
                )
            digest.update(chunk)
            try:
                writer(chunk)
            except OSError as exc:
                # Disque plein, tube cassé, fichier verrouillé : une panne
                # d'écriture reste une erreur métier, jamais une trace Python.
                raise _write_failed(exc) from exc
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise NetworkError("API ACP injoignable") from exc
    except httpx.HTTPError as exc:
        raise NetworkError("échec du transport HTTP") from exc
    finally:
        response.close()
        http.close()
    return digest.hexdigest(), size, served


def _write_failed(exc: OSError) -> CommandError:
    return CommandError("write_failed", f"écriture impossible : {_system_reason(exc)}")


def _discard(path: Path) -> None:
    """Retire un fichier partiel sans jamais masquer l'erreur qui l'a causé."""

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _verify_checksum(expected: str, digest: str) -> None:
    if expected and expected != digest:
        raise CommandError(
            "checksum_mismatch",
            "empreinte sha256 différente de celle annoncée par l'API : contenu écarté",
        )


def _download_to_file(
    client: ACPClient,
    artifact_id: str,
    target: Path,
    *,
    force: bool,
    max_bytes: int,
    checksum: str,
) -> tuple[str, int, str]:
    parent = target.parent if str(target.parent) else Path(".")
    if force:
        # Écriture dans un fichier temporaire voisin puis remplacement atomique :
        # un téléchargement raté ne détruit jamais le fichier déjà présent.
        try:
            handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - fermé plus bas
                dir=str(parent), prefix=f".{target.name}.", suffix=".part", delete=False
            )
        except OSError as exc:
            raise _write_failed(exc) from exc
        temporary = Path(handle.name)
        try:
            try:
                with handle:
                    digest, size, served = _download_artifact(
                        client, artifact_id, writer=handle.write, max_bytes=max_bytes
                    )
                _verify_checksum(checksum, digest)
                os.replace(temporary, target)
            except OSError as exc:
                raise _write_failed(exc) from exc
        except BaseException:
            _discard(temporary)
            raise
        return digest, size, served
    try:
        handle = target.open("xb")
    except FileExistsError as exc:
        raise CommandError(
            "file_exists",
            f"« {target} » existe déjà : choisissez --output ou confirmez avec --force",
            ExitCode.USAGE,
        ) from exc
    except OSError as exc:
        raise _write_failed(exc) from exc
    try:
        try:
            with handle:
                digest, size, served = _download_artifact(
                    client, artifact_id, writer=handle.write, max_bytes=max_bytes
                )
            _verify_checksum(checksum, digest)
        except OSError as exc:
            raise _write_failed(exc) from exc
    except BaseException:
        _discard(target)
        raise
    return digest, size, served


def _handle_artifacts_get(
    args: argparse.Namespace,
    client: ACPClient,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    artifact_id = _require_text(args.artifact_id, "l'identifiant d'artefact")
    if args.to_stdout and args.output is not None:
        raise UsageError("--stdout et --output s'excluent")
    summary = client.request("GET", f"/artifacts/{_path_segment(artifact_id)}")
    if not isinstance(summary, dict):
        raise ProtocolError("l'API n'a pas retourné un artefact exploitable")
    if summary.get("has_content") is False:
        raise CommandError(
            "no_content", "cet artefact ne porte aucun contenu téléchargeable"
        )
    checksum = str(summary.get("checksum") or "").strip().lower()
    declared_size = _positive_int(summary.get("size_bytes"))
    max_bytes = declared_size if declared_size is not None else ARTIFACT_MAX_DOWNLOAD_BYTES
    declared_type = str(summary.get("content_type") or "").split(";")[0].strip().lower()
    if args.to_stdout:
        guard: Callable[[str], None] | None = None
        if _stream_is_interactive(stdout) and not args.force:
            # Le type déclaré vient d'un worker (§0.4 : contenu non fiable) : il
            # permet de refuser tôt, jamais d'autoriser. Seul le type servi par
            # l'API, déjà ramené à une allowlist (§7), ouvre le terminal.
            _refuse_binary_stdout(declared_type)
            guard = _refuse_binary_stdout
        digest, size, served = _download_artifact(
            client,
            artifact_id,
            writer=lambda chunk: _write_bytes(stdout, chunk),
            max_bytes=max_bytes,
            on_content_type=guard,
        )
        _verify_checksum(checksum, digest)
        result: dict[str, Any] = {
            "artifact_id": artifact_id,
            "path": None,
            "size_bytes": size,
            "checksum": digest,
            "content_type": served or declared_type,
            "declared_content_type": declared_type,
            "verified": bool(checksum),
        }
        if args.json:
            # La sortie standard porte le contenu : les métadonnées vont ailleurs.
            _emit(result, as_json=True, stream=stderr)
        if not checksum:
            _emit_notice(
                "checksum_absent",
                "L'API n'a pas annoncé d'empreinte : le contenu n'a pas pu être vérifié.",
                as_json=args.json,
                stream=stderr,
            )
        return
    target = _download_target(args.output, summary, artifact_id)
    digest, size, served = _download_to_file(
        client,
        artifact_id,
        target,
        force=args.force,
        max_bytes=max_bytes,
        checksum=checksum,
    )
    if not checksum:
        _emit_notice(
            "checksum_absent",
            "L'API n'a pas annoncé d'empreinte : le contenu n'a pas pu être vérifié.",
            as_json=args.json,
            stream=stderr,
        )
    result = {
        "artifact_id": artifact_id,
        "path": str(target),
        "size_bytes": size,
        "checksum": digest,
        "content_type": served or declared_type,
        "declared_content_type": declared_type,
        "verified": bool(checksum),
    }
    if args.json:
        _emit(result, as_json=True, stream=stdout)
    else:
        print(str(target), file=stdout)


def _handle_artifacts_link(
    args: argparse.Namespace,
    client: ACPClient,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    artifact_id = _require_text(args.artifact_id, "l'identifiant d'artefact")
    ttl = args.ttl
    if (
        isinstance(ttl, bool)
        or not isinstance(ttl, int)
        or not 1 <= ttl <= ARTIFACT_LINK_MAX_TTL_SECONDS
    ):
        raise UsageError(
            f"--ttl doit être compris entre 1 et {ARTIFACT_LINK_MAX_TTL_SECONDS} secondes"
        )
    body = client.request(
        "POST",
        f"/artifacts/{_path_segment(artifact_id)}/link",
        params={"ttl_seconds": ttl},
    )
    if not isinstance(body, dict) or not isinstance(body.get("url"), str):
        raise ProtocolError("l'API n'a pas retourné un lien exploitable")
    if args.json:
        _emit(body, as_json=True, stream=stdout)
    else:
        print(body["url"], file=stdout)
    _emit_notice(
        "link_expiry",
        f"Lien signé valable jusqu'à {body.get('expires_at')} : il porte un jeton, "
        "ne le publiez pas.",
        as_json=args.json,
        stream=stderr,
    )


COMPLETION_COMMANDS = (
    "login logout doctor projects chat run runs pending approvals artifacts open workers "
    "secrets mcp skills automations completion"
)
COMPLETION_SUBCOMMANDS = (
    "list add create extensions watch stop show discard status set rotate revoke catalog tools "
    "update test probes approve reject bind bindings unbind activate disable rollback "
    "enable trigger runs calendar webhook export import search files cat install events tests get link"
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
    environ: Mapping[str, str],
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
    if handler == "runs_events":
        _handle_runs_events(args, client, stdout=stdout, stderr=stderr)
        return False, None, client.settings
    if handler == "runs_tests":
        _handle_runs_tests(args, client, stdout=stdout)
        return False, None, client.settings
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
        return True, _handle_artifacts_list(args, client), client.settings
    if handler == "artifacts_get":
        _handle_artifacts_get(args, client, stdout=stdout, stderr=stderr)
        return False, None, client.settings
    if handler == "artifacts_link":
        _handle_artifacts_link(args, client, stdout=stdout, stderr=stderr)
        return False, None, client.settings
    if handler == "open":
        query = {"run": args.run}
        if args.studio:
            # Clé de requête attendue par le shell web
            # (`apps/web/src/studio-ui.ts::STUDIO_VIEW_PARAM`, spec §2.5 et §10).
            # Elle est volontairement distincte du champ `view` de la réponse
            # JSON : les deux ne peuvent pas dériver l'une vers l'autre.
            query[STUDIO_VIEW_PARAM] = STUDIO_VIEW_VALUE
        url = f"{client.settings.web_url}/missions?{urlencode(query)}"
        opened = False
        if args.browser:
            opened = bool(browser_open(url))
            if not opened:
                raise ProtocolError("le navigateur n'a pas accepté l'ouverture de l'URL")
        return (
            True,
            {
                "run_id": args.run,
                "url": url,
                "opened": opened,
                "view": STUDIO_VIEW_VALUE if args.studio else "mission",
            },
            client.settings,
        )
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
    if handler == "mcp_import":
        _handle_mcp_import(args, client, stdout=stdout, stderr=stderr)
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
    if handler == "automations_list":
        params: dict[str, Any] = {"limit": _automation_limit(args.limit)}
        if args.project is not None:
            params["project_id"] = _require_option_text(args.project, "--project")
        if args.enabled is not None:
            params["enabled"] = args.enabled
        result = client.request("GET", "/automations", params=params)
        return True, _automation_list_result(result), client.settings
    if handler == "automations_create":
        return True, _handle_automation_create(args, client), client.settings
    if handler == "automations_show":
        automation_id = _require_text(args.automation_id, "identifiant")
        path = f"/automations/{_path_segment(automation_id)}"
        result = client.request("GET", path)
        return True, _automation_detail_result(result, expected_id=automation_id), client.settings
    if handler == "automations_update":
        return True, _handle_automation_update(args, client), client.settings
    if handler in {"automations_enable", "automations_disable"}:
        return (
            True,
            _handle_automation_enabled(
                args,
                client,
                enabled=handler == "automations_enable",
            ),
            client.settings,
        )
    if handler == "automations_trigger":
        return True, _handle_automation_trigger(args, client), client.settings
    if handler == "automations_runs":
        automation_id = _require_text(args.automation_id, "identifiant")
        path = f"/automations/{_path_segment(automation_id)}/runs"
        params = {"limit": _automation_limit(args.limit)}
        result = client.request("GET", path, params=params)
        return True, _automation_runs_result(result, automation_id), client.settings
    if handler == "automations_calendar":
        result = client.request(
            "GET", "/automations/calendar", params=_automation_calendar_params(args)
        )
        return (
            True,
            _automation_calendar_result(result),
            client.settings,
        )
    if handler == "automations_webhook_status":
        automation_id = _require_text(args.automation_id, "identifiant")
        path = f"/automations/{_path_segment(automation_id)}/webhook"
        result = client.request("GET", path)
        return (
            True,
            _automation_webhook_status_result(
                result, automation_id=automation_id
            ),
            client.settings,
        )
    if handler == "automations_webhook_rotate":
        return (
            True,
            _handle_automation_webhook_rotate(args, client, environ),
            client.settings,
        )
    if handler == "automations_webhook_disable":
        return (
            True,
            _handle_automation_webhook_disable(args, client),
            client.settings,
        )
    if handler == "completion":
        return True, _completion_script(args.shell), client.settings
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
            environ=env,
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
    except AutomationMutationError as exc:
        as_json = "--json" in raw_argv
        if as_json:
            error: dict[str, Any] = {
                "code": exc.code,
                "message": str(exc),
                "operation": exc.operation,
                "idempotency_key": exc.idempotency_key,
                "recovery": exc.recovery,
            }
            if exc.status_code is not None:
                error["status"] = exc.status_code
            if exc.retry_secret is not None:
                error["secret"] = exc.retry_secret
            _emit({"error": error}, as_json=True, stream=err)
        else:
            status = (
                f", HTTP {exc.status_code}"
                if exc.status_code is not None
                else ""
            )
            recovery_secret = (
                f", Webhook-Secret: {exc.retry_secret}"
                if exc.retry_secret is not None
                else ""
            )
            print(
                f"Erreur: {exc} (Idempotency-Key: {exc.idempotency_key}"
                f"{recovery_secret}{status})",
                file=err,
            )
        return int(exc.exit_code)
    except AutomationTriggerError as exc:
        as_json = "--json" in raw_argv
        if as_json:
            error: dict[str, Any] = {
                "code": exc.code,
                "message": str(exc),
                "idempotency_key": exc.idempotency_key,
                "recovery": "retry_automation_trigger_with_same_key",
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
    except AutomationOutcomeError as exc:
        as_json = "--json" in raw_argv
        if as_json:
            _emit(
                {
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "run": exc.result,
                    }
                },
                as_json=True,
                stream=err,
            )
        else:
            print(f"Erreur: {exc}", file=err)
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
