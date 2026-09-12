"""Import assisté de configurations MCP existantes (Hermes, Claude Code, Codex) — spec §4.5.

Trois règles gouvernent ce module :

1. **Le contenu importé est une donnée non fiable.** Il est borné, analysé avec les
   analyseurs de la bibliothèque standard (``json``, ``tomllib``) ou un chargeur YAML sûr
   qui refuse les alias (``SafeImportYamlLoader``, contre l'expansion « billion laughs »),
   et jamais exécuté ni interprété comme une instruction. Une imbrication extrême, une
   valeur hors bornes ou un format inconnu produisent un état explicite, jamais une
   erreur serveur.
2. **Aucune valeur de secret ne ressort.** Une valeur d'en-tête ou de variable
   d'environnement qui ressemble à un secret (par sa clé) ou qui porte une variable
   ``${VAR}`` n'est pas recopiée : elle devient un *candidat de secret* dont seule une
   version masquée (``***`` + deux derniers caractères) est renvoyée, à relier
   explicitement à un secret du coffre au moment de l'application.
3. **Aucun faux succès.** Ce qu'un format exprime et que la plateforme ne sait pas
   reproduire (SSE, WebSocket, OAuth, certificat client, approbation par outil…) est
   listé dans ``unsupported`` et, quand cela rendrait le serveur inopérant, l'entrée est
   marquée non importable au lieu d'être approximée.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session

from acp_contracts import (
    McpHttpConfig,
    McpImportApplyRequest,
    McpImportApplyResult,
    McpImportEntry,
    McpImportPreview,
    McpImportSecretCandidate,
    McpServerConfig,
    McpStdioConfig,
    SecretRef,
)
from acp_database.models import McpServerModel, SecretModel

from ..outbound import OutboundPolicy
from . import service
from .service import ConfigRefused

#: Borne de lecture, identique à celle du contrat ``McpImportPreviewRequest``.
MAX_IMPORT_CHARS = 1_000_000

DEFAULT_HTTP_TIMEOUT = 15
DEFAULT_STDIO_TIMEOUT = 20
TIMEOUT_RANGE = (1, 120)

MAX_ENTRIES = 200
MAX_ARGS = 200
MAX_REASON_CHARS = 300

# Une clé dont le nom évoque un secret ne voit jamais sa valeur recopiée.
_SECRET_KEY_RE = re.compile(
    r"(TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTHORIZATION|CREDENTIAL|BEARER)", re.IGNORECASE
)
# ``${VAR}`` et ``${VAR:-valeur par défaut}`` (substitution Hermes/Claude/Codex).
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

_CODEX_TABLE_RE = re.compile(r"^\s*\[\s*mcp_servers\s*\.", re.MULTILINE)
_HERMES_KEY_RE = re.compile(r"^\s*mcp_servers\s*:", re.MULTILINE)


class ImportParseError(ValueError):
    """Contenu illisible : l'aperçu renvoie une erreur explicite, jamais une entrée inventée."""


class SafeImportYamlLoader(yaml.SafeLoader):
    """Chargeur YAML sûr qui **refuse les alias** (``*ancre``).

    ``yaml.safe_load`` n'exécute rien, mais il développe les alias : un fichier de
    quelques kilo-octets peut alors occuper plusieurs gigaoctets en mémoire (« billion
    laughs »). Un import est une donnée non fiable : l'alias est refusé et expliqué.
    """

    def compose_node(self, parent, index):  # type: ignore[override]
        if self.check_event(yaml.events.AliasEvent):
            # Le nom de l'ancre est un fragment du document importé : on le situe sans
            # le recopier, comme toute erreur d'analyse (spec §0.3).
            mark = self.peek_event().start_mark
            where = f" (ligne {mark.line + 1}, colonne {mark.column + 1})" if mark else ""
            raise yaml.YAMLError(
                f"alias YAML refusé{where} : développez les ancres avant l'import"
            )
        return super().compose_node(parent, index)


def _yaml_reason(exc: BaseException) -> str:
    """Message d'erreur YAML qui ne recopie **jamais** le contenu importé.

    ``MarkedYAMLError.__str__`` compose son message avec ``get_snippet()``, c'est-à-dire
    la ligne fautive du fichier analysé : la formater ferait ressortir la valeur qui s'y
    trouve (un en-tête mal fermé, par exemple) dans ``McpImportPreview.errors`` — donc
    dans une réponse d'API, dans le DOM et dans la sortie du CLI. Seuls la position et le
    libellé produits par l'analyseur sont conservés (spec §0.3).
    """

    if isinstance(exc, (yaml.composer.ComposerError, yaml.constructor.ConstructorError)):
        # Ces deux familles ne citent un fragment du document que dans les sous-cas
        # nommés ci-dessous (une ancre ``&nom`` ou une étiquette ``!tag``). Les autres,
        # dont le document multiple, ont un libellé purement structurel : les renvoyer
        # au traitement générique donne un diagnostic juste sans rien recopier.
        problem = str(getattr(exc, "problem", "") or "")
        names_a_fragment = any(
            marker in problem
            for marker in (
                "found duplicate anchor",
                "found undefined alias",
                "could not determine a constructor for the tag",
            )
        )
        if names_a_fragment:
            mark = exc.problem_mark or exc.context_mark
            where = (
                f" (ligne {mark.line + 1}, colonne {mark.column + 1})"
                if mark is not None
                else ""
            )
            return (
                f"YAML illisible{where} : étiquette ou ancre non prise en charge à cet endroit."
            )[:MAX_REASON_CHARS]
    if isinstance(exc, yaml.MarkedYAMLError):
        # ``context``/``problem`` sont les libellés de l'analyseur ; ``context_mark`` situe
        # le début de la construction fautive (le guillemet ouvrant, par exemple), ce qui
        # est plus actionnable que la position où l'analyse s'est arrêtée.
        labels = [str(part).strip() for part in (exc.context, exc.problem) if part]
        detail = " : ".join(labels) or "structure YAML invalide"
        mark = exc.context_mark or exc.problem_mark
        if mark is not None:
            return (
                f"YAML illisible (ligne {mark.line + 1}, colonne {mark.column + 1}) : {detail}"
            )[:MAX_REASON_CHARS]
        return f"YAML illisible : {detail}"[:MAX_REASON_CHARS]
    if isinstance(exc, yaml.YAMLError):
        # Refus levés par ``SafeImportYamlLoader`` (alias) : message écrit ici, sans contenu.
        return f"YAML illisible : {exc}"[:MAX_REASON_CHARS]
    return "YAML illisible : le document est trop imbriqué pour être analysé."


def _validation_reason(exc: ValidationError) -> str:
    """Première erreur pydantic, rendue lisible et bornée (le contenu est non fiable)."""

    errors = exc.errors()
    if not errors:
        return "valeur refusée par le contrat"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "configuration"
    return f"{location} : {first.get('msg', 'valeur refusée')}"[:MAX_REASON_CHARS]


# --- détection de format --------------------------------------------------------------------


def detect_format(content: str) -> str | None:
    """Devine le format d'une configuration ; ``None`` quand rien ne correspond."""

    if not isinstance(content, str) or not content.strip():
        return None
    try:
        document = json.loads(content)
    except (ValueError, RecursionError):
        # Contenu illisible ou trop imbriqué : ce n'est pas du JSON exploitable, on
        # continue avec les autres détections plutôt que de laisser filer une erreur.
        document = None
    if isinstance(document, dict) and isinstance(document.get("mcpServers"), dict):
        return "claude"
    if isinstance(document, dict) and isinstance(document.get("projects"), dict):
        for project in document["projects"].values():
            if isinstance(project, dict) and isinstance(project.get("mcpServers"), dict):
                return "claude"
    if _CODEX_TABLE_RE.search(content):
        return "codex"
    if _HERMES_KEY_RE.search(content):
        return "hermes"
    return None


# --- utilitaires de normalisation -----------------------------------------------------------


def _looks_secret(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key or ""))


def mask_value(value: str) -> str:
    """``***`` suivi des deux derniers caractères au plus (jamais davantage)."""

    text = "" if value is None else str(value)
    return f"***{text[-2:]}" if len(text) > 2 else "***"


def suggested_secret_name(server_name: str, key: str) -> str:
    """Nom de secret proposé ``<NOM_SERVEUR>_<CLE>`` conforme à ``^[A-Z][A-Z0-9_]{1,62}$``."""

    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", f"{server_name}_{key}").strip("_").upper()
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"S_{cleaned}".strip("_")
    if len(cleaned) < 2:
        cleaned = f"{cleaned}_SECRET"
    return cleaned[:63]


def slugify(raw: str) -> str:
    """Nom technique de serveur (slug) déduit du nom d'origine."""

    slug = re.sub(r"[^a-z0-9]+", "-", str(raw).strip().lower()).strip("-")
    return slug[:63].strip("-") or "serveur-importe"


@dataclass
class _Draft:
    """Entrée en cours de normalisation : nom, signalements et candidats de secrets."""

    name: str
    source_name: str
    warnings: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    candidates: list[McpImportSecretCandidate] = field(default_factory=list)
    importable: bool = True

    def refuse(self, message: str) -> None:
        """Signale ce qui n'est pas exprimable et rend l'entrée non importable."""

        self.unsupported.append(message)
        self.importable = False

    def unsupported_option(self, message: str) -> None:
        """Signale une option non reprise sans empêcher l'import du reste."""

        self.unsupported.append(message)

    def candidate(self, location: str, key: str, value: str) -> None:
        self.candidates.append(
            McpImportSecretCandidate(
                location=location,
                key=key,
                suggested_secret_name=suggested_secret_name(self.name, key),
                masked_value=mask_value(value),
            )
        )

    def variable_candidate(self, location: str, key: str, variable: str) -> None:
        """Candidat issu d'un *nom* de variable (``${VAR}``, Codex ``env_vars``/``bearer_token_env_var``).

        Le fichier importé ne contient alors aucune valeur : ``masked_value`` vaut ``***`` et
        le nom de la variable est rappelé en avertissement.
        """

        self.candidates.append(
            McpImportSecretCandidate(
                location=location,
                key=key,
                suggested_secret_name=suggested_secret_name(self.name, key),
                masked_value="***",
            )
        )
        self.warnings.append(
            f"« {key} » était fourni par la variable d'environnement « {variable} » : "
            "choisissez le secret correspondant dans le coffre."
        )


def _classify(draft: _Draft, location: str, key: str, value: Any) -> str | None:
    """Valeur littérale conservée, ou ``None`` quand la clé devient un candidat de secret."""

    text = "" if value is None else str(value)
    placeholder = _PLACEHOLDER_RE.search(text)
    if placeholder is not None:
        exact = _PLACEHOLDER_RE.fullmatch(text.strip())
        if exact is not None and exact.group(2) is not None and not _looks_secret(key):
            # ``${VAR:-défaut}`` sur une clé anodine : la valeur par défaut est explicite
            # dans le fichier, elle est donc conservée telle quelle.
            return exact.group(2)
        # Le fichier ne porte pas la valeur mais le *nom* d'une variable : rien à masquer,
        # et le nom de la variable aide à retrouver le secret correspondant.
        draft.variable_candidate(location, key, placeholder.group(1))
        return None
    if _looks_secret(key):
        draft.candidate(location, key, text)
        return None
    return text


def _collect(draft: _Draft, location: str, raw: Any) -> dict[str, str]:
    """Normalise une table clé/valeur (en-têtes ou environnement)."""

    literals: dict[str, str] = {}
    if not isinstance(raw, Mapping):
        if raw is not None:
            draft.warnings.append(
                f"Table « {location} » ignorée : un objet clé/valeur était attendu."
            )
        return literals
    for key, value in raw.items():
        name = str(key)
        if isinstance(value, (dict, list)):
            draft.warnings.append(f"Valeur composite ignorée pour « {name} » ({location}).")
            continue
        literal = _classify(draft, location, name, value)
        if literal is not None:
            literals[name] = literal
    return literals


#: Mécanismes d'authentification Hermes que l'on accepte de nommer dans un aperçu.
#: Toute autre valeur est rendue « non reconnu » : le contenu importé n'est jamais recopié.
_KNOWN_AUTH_MECHANISMS = frozenset({"oauth", "bearer", "basic", "none"})


def _auth_mechanism(value: Any) -> str:
    """Nomme le mécanisme d'un bloc ``auth:`` sans jamais recopier ce qu'il transporte."""

    candidate: Any = value.get("type") if isinstance(value, Mapping) else value
    if isinstance(candidate, str) and candidate.strip().lower() in _KNOWN_AUTH_MECHANISMS:
        return candidate.strip().lower()
    return "mécanisme non reconnu"


def _timeout(draft: _Draft, value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        # La valeur illisible vient du fichier importé : la citer la ferait ressortir.
        draft.warnings.append(f"Délai illisible : {default} s retenus.")
        return default
    low, high = TIMEOUT_RANGE
    if seconds < low or seconds > high:
        clamped = min(max(seconds, low), high)
        draft.warnings.append(
            f"Délai de {seconds} s hors bornes ({low}–{high}) : ramené à {clamped} s."
        )
        return clamped
    return seconds


def _args(draft: _Draft, raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        draft.warnings.append("« args » ignoré : une liste était attendue.")
        return []
    args = [str(item) for item in raw[:MAX_ARGS]]
    if len(raw) > MAX_ARGS:
        draft.warnings.append(f"Arguments tronqués à {MAX_ARGS} éléments.")
    if any(_PLACEHOLDER_RE.search(item) for item in args):
        draft.warnings.append(
            "Un argument contient une variable « ${…} » : la plateforme ne les substitue pas, "
            "remplacez-la par sa valeur avant activation."
        )
    return args


def _url(draft: _Draft, raw: Any) -> str | None:
    """URL d'un serveur HTTP, ou ``None`` (entrée refusée) si elle n'est pas exprimable."""

    if not isinstance(raw, str) or not raw.strip():
        draft.refuse("url : une chaîne de caractères non vide était attendue.")
        return None
    url = raw.strip()
    if _PLACEHOLDER_RE.search(url):
        draft.candidate("url", "url", url)
        draft.refuse(
            "url : l'URL contient une variable « ${…} » et la plateforme n'injecte jamais "
            "de secret dans une URL ; déplacez la valeur dans un en-tête."
        )
        return None
    return url


def _command(draft: _Draft, raw: Any) -> str | None:
    """Commande d'un serveur stdio, ou ``None`` (entrée refusée) si elle n'est pas exprimable."""

    if not isinstance(raw, str) or not raw.strip():
        draft.refuse("command : une chaîne de caractères non vide était attendue.")
        return None
    return raw.strip()


def _cwd(draft: _Draft, raw: Any) -> str | None:
    """Répertoire de travail facultatif ; une valeur non textuelle est ignorée et signalée."""

    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not raw.strip():
        draft.warnings.append("« cwd » ignoré : une chaîne de caractères non vide était attendue.")
        return None
    return raw.strip()


def _unique_name(draft_name: str, used: set[str]) -> tuple[str, str | None]:
    if draft_name not in used:
        used.add(draft_name)
        return draft_name, None
    base = draft_name[:60].rstrip("-") or "serveur-importe"
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    unique = f"{base}-{index}"
    used.add(unique)
    return unique, (
        f"Nom déjà utilisé par une autre entrée de cet import : entrée renommée « {unique} »."
    )


def _new_draft(raw_name: str, source_name: str, used: set[str]) -> _Draft:
    name, warning = _unique_name(slugify(raw_name), used)
    draft = _Draft(name=name, source_name=source_name)
    if warning:
        draft.warnings.append(warning)
    if slugify(raw_name) != str(raw_name):
        draft.warnings.append(
            f"Nom technique normalisé en « {name} » (le nom d'origine « {source_name} » est conservé "
            "comme nom affiché)."
        )
    return draft


def _entry(
    draft: _Draft,
    config: McpServerConfig | None,
    existing_names: set[str],
) -> McpImportEntry:
    importable = draft.importable and config is not None
    if config is not None and config.transport == "stdio" and importable:
        draft.warnings.append(
            "Transport stdio : désignez le runner autorisé et faites approuver le lancement "
            "avant toute activation."
        )
    return McpImportEntry(
        name=draft.name,
        source_name=draft.source_name,
        transport=config.transport if (config is not None and importable) else None,
        config=config if importable else None,
        secret_candidates=draft.candidates,
        unsupported=draft.unsupported,
        warnings=draft.warnings,
        conflict="existing_server" if draft.name in existing_names else "none",
        importable=importable,
    )


def _http_config(
    draft: _Draft, url: str, headers: dict[str, str], timeout: int
) -> McpServerConfig | None:
    """Configuration HTTP, ou ``None`` si le contrat la refuse (valeur hors bornes…)."""

    try:
        return McpServerConfig(
            transport="http",
            http=McpHttpConfig(url=url, headers=headers, header_secrets={}, timeout_seconds=timeout),
        )
    except ValidationError as exc:
        draft.refuse(f"configuration refusée par le contrat — {_validation_reason(exc)}")
        return None


def _stdio_config(
    draft: _Draft,
    command: str,
    args: list[str],
    env: dict[str, str],
    cwd: str | None,
    timeout: int,
) -> McpServerConfig | None:
    """Configuration stdio, ou ``None`` si le contrat la refuse."""

    try:
        return McpServerConfig(
            transport="stdio",
            stdio=McpStdioConfig(
                command=command,
                args=args,
                env=env,
                env_secrets={},
                cwd=cwd,
                timeout_seconds=timeout,
            ),
        )
    except ValidationError as exc:
        draft.refuse(f"configuration refusée par le contrat — {_validation_reason(exc)}")
        return None


def _tool_selection_warning(draft: _Draft) -> None:
    draft.warnings.append(
        "Une sélection d'outils existait dans la configuration source : sélection d'outils "
        "à refaire après découverte (les outils autorisés se choisissent par projet)."
    )


def _disabled_warning(draft: _Draft) -> None:
    draft.warnings.append(
        "« enabled: false » dans la configuration source : serveur importé désactivé "
        "(brouillon), à activer explicitement après diagnostic."
    )


# --- Claude Code ------------------------------------------------------------------------------

_CLAUDE_UNSUPPORTED = {
    "oauth": (
        "oauth : la négociation OAuth de Claude Code n'est pas reprise ; configurez un secret "
        "d'en-tête après l'import."
    ),
    "headersHelper": (
        "headersHelper : le programme externe qui fabrique les en-têtes n'est pas repris "
        "(la plateforme n'exécute pas de programme pour construire une requête)."
    ),
}


def _parse_claude(content: str, existing_names: set[str]) -> list[McpImportEntry]:
    try:
        document = json.loads(content)
    except (ValueError, RecursionError) as exc:
        raise ImportParseError(f"JSON illisible : {exc}"[:MAX_REASON_CHARS]) from exc
    if not isinstance(document, dict):
        raise ImportParseError("JSON illisible : un objet était attendu à la racine.")

    sections: list[tuple[str, Any]] = [("", document.get("mcpServers"))]
    projects = document.get("projects")
    if isinstance(projects, dict):
        for path, project in projects.items():
            if isinstance(project, dict):
                sections.append((str(path), project.get("mcpServers")))

    used: set[str] = set()
    entries: list[McpImportEntry] = []
    for prefix, servers in sections:
        if not isinstance(servers, dict):
            continue
        for raw_name, raw in servers.items():
            if len(entries) >= MAX_ENTRIES:
                return entries
            source_name = f"{prefix}:{raw_name}" if prefix else str(raw_name)
            entries.append(_claude_entry(str(raw_name), source_name, raw, used, existing_names))
    return entries


def _claude_entry(
    raw_name: str, source_name: str, raw: Any, used: set[str], existing_names: set[str]
) -> McpImportEntry:
    draft = _new_draft(raw_name, source_name, used)
    if not isinstance(raw, dict):
        draft.refuse("entrée : un objet de configuration était attendu.")
        return _entry(draft, None, existing_names)

    for key, message in _CLAUDE_UNSUPPORTED.items():
        if raw.get(key):
            draft.unsupported_option(message)

    declared = str(raw.get("type") or "").strip().lower()
    if declared in {"sse", "ws", "websocket"}:
        draft.refuse(
            f"{declared} : transport « {declared} » non supporté ; la plateforme n'implémente "
            "que Streamable HTTP (2025-06-18) et stdio."
        )
        return _entry(draft, None, existing_names)

    url = raw.get("url")
    command = raw.get("command")
    if declared == "http" or (not declared and url):
        if not url:
            draft.refuse("url : entrée de type « http » sans URL.")
            return _entry(draft, None, existing_names)
        headers = _collect(draft, "header", raw.get("headers"))
        target = _url(draft, url)
        if target is None:
            return _entry(draft, None, existing_names)
        timeout = _timeout(draft, raw.get("timeout"), DEFAULT_HTTP_TIMEOUT)
        return _entry(draft, _http_config(draft, target, headers, timeout), existing_names)

    if declared == "stdio" or command:
        if not command:
            draft.refuse("command : entrée de type « stdio » sans commande.")
            return _entry(draft, None, existing_names)
        program = _command(draft, command)
        if program is None:
            return _entry(draft, None, existing_names)
        env = _collect(draft, "env", raw.get("env"))
        timeout = _timeout(draft, raw.get("timeout"), DEFAULT_STDIO_TIMEOUT)
        cwd = _cwd(draft, raw.get("cwd"))
        config = _stdio_config(draft, program, _args(draft, raw.get("args")), env, cwd, timeout)
        return _entry(draft, config, existing_names)

    draft.refuse("entrée sans « url » ni « command » : rien à importer.")
    return _entry(draft, None, existing_names)


# --- Codex ------------------------------------------------------------------------------------


def _parse_codex(content: str, existing_names: set[str]) -> list[McpImportEntry]:
    try:
        document = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError, RecursionError) as exc:
        raise ImportParseError(f"TOML illisible : {exc}"[:MAX_REASON_CHARS]) from exc
    servers = document.get("mcp_servers")
    if not isinstance(servers, dict):
        return []

    used: set[str] = set()
    entries: list[McpImportEntry] = []
    for raw_name, raw in servers.items():
        if len(entries) >= MAX_ENTRIES:
            break
        entries.append(_codex_entry(str(raw_name), raw, used, existing_names))
    return entries


def _codex_entry(
    raw_name: str, raw: Any, used: set[str], existing_names: set[str]
) -> McpImportEntry:
    draft = _new_draft(raw_name, str(raw_name), used)
    if not isinstance(raw, dict):
        draft.refuse("entrée : une table TOML était attendue.")
        return _entry(draft, None, existing_names)

    if raw.get("default_tools_approval_mode") is not None:
        draft.unsupported_option(
            "default_tools_approval_mode : le mode d'approbation par défaut de Codex n'est pas "
            "repris ; la plateforme approuve les lancements stdio au cas par cas."
        )
    tools = raw.get("tools")
    if isinstance(tools, dict):
        for sub in tools:
            draft.unsupported_option(
                f"[mcp_servers.{raw_name}.tools.{sub}] : la configuration par outil n'est pas "
                "reprise ; les outils autorisés se choisissent par projet après découverte."
            )
    if raw.get("enabled") is False:
        _disabled_warning(draft)
    if raw.get("enabled_tools") or raw.get("disabled_tools"):
        _tool_selection_warning(draft)

    timeout_raw = raw.get("startup_timeout_sec")
    if timeout_raw is None:
        timeout_raw = raw.get("tool_timeout_sec")

    url = raw.get("url")
    command = raw.get("command")
    if url:
        headers = _collect(draft, "header", raw.get("http_headers"))
        bearer = raw.get("bearer_token_env_var")
        if bearer:
            draft.variable_candidate("header", "Authorization", str(bearer))
        env_headers = raw.get("env_http_headers")
        if isinstance(env_headers, dict):
            for header, variable in env_headers.items():
                draft.variable_candidate("header", str(header), str(variable))
        target = _url(draft, url)
        if target is None:
            return _entry(draft, None, existing_names)
        timeout = _timeout(draft, timeout_raw, DEFAULT_HTTP_TIMEOUT)
        return _entry(draft, _http_config(draft, target, headers, timeout), existing_names)

    if command:
        program = _command(draft, command)
        if program is None:
            return _entry(draft, None, existing_names)
        env = _collect(draft, "env", raw.get("env"))
        env_vars = raw.get("env_vars")
        if isinstance(env_vars, list):
            for variable in env_vars:
                draft.variable_candidate("env", str(variable), str(variable))
        cwd = _cwd(draft, raw.get("cwd"))
        timeout = _timeout(draft, timeout_raw, DEFAULT_STDIO_TIMEOUT)
        config = _stdio_config(draft, program, _args(draft, raw.get("args")), env, cwd, timeout)
        return _entry(draft, config, existing_names)

    draft.refuse("entrée sans « url » ni « command » : rien à importer.")
    return _entry(draft, None, existing_names)


# --- Hermes -----------------------------------------------------------------------------------


def _parse_hermes(content: str, existing_names: set[str]) -> list[McpImportEntry]:
    try:
        document = yaml.load(content, Loader=SafeImportYamlLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise ImportParseError(_yaml_reason(exc)) from exc
    if not isinstance(document, dict):
        raise ImportParseError("YAML illisible : un objet était attendu à la racine.")
    servers = document.get("mcp_servers")
    if not isinstance(servers, dict):
        return []

    used: set[str] = set()
    entries: list[McpImportEntry] = []
    for raw_name, raw in servers.items():
        if len(entries) >= MAX_ENTRIES:
            break
        entries.append(_hermes_entry(str(raw_name), raw, used, existing_names))
    return entries


def _hermes_entry(
    raw_name: str, raw: Any, used: set[str], existing_names: set[str]
) -> McpImportEntry:
    draft = _new_draft(raw_name, str(raw_name), used)
    if not isinstance(raw, dict):
        draft.refuse("entrée : un objet de configuration était attendu.")
        return _entry(draft, None, existing_names)

    if raw.get("auth"):
        # Un bloc ``auth:`` Hermes porte typiquement un jeton en clair : n'en renvoyer
        # que le mécanisme, et seulement s'il appartient à une liste connue. Interpoler
        # la valeur la ferait ressortir dans l'aperçu, le DOM et la sortie du CLI.
        draft.unsupported_option(
            f"auth ({_auth_mechanism(raw['auth'])}) : l'authentification négociée par Hermes "
            "n'est pas reprise ; configurez un secret d'en-tête après l'import."
        )
    if raw.get("client_cert"):
        draft.unsupported_option(
            "client_cert : la plateforme ne présente pas de certificat client aux serveurs MCP."
        )
    if raw.get("identity_header"):
        draft.unsupported_option(
            "identity_header : l'en-tête d'identité propagé par Hermes n'a pas d'équivalent ; "
            "la plateforme appelle le serveur avec sa propre identité."
        )
    if raw.get("enabled") is False:
        _disabled_warning(draft)
    tools = raw.get("tools")
    if isinstance(tools, dict) and (tools.get("include") or tools.get("exclude")):
        _tool_selection_warning(draft)

    url = raw.get("url")
    command = raw.get("command")
    if url:
        headers = _collect(draft, "header", raw.get("headers"))
        target = _url(draft, url)
        if target is None:
            return _entry(draft, None, existing_names)
        timeout = _timeout(draft, raw.get("timeout"), DEFAULT_HTTP_TIMEOUT)
        return _entry(draft, _http_config(draft, target, headers, timeout), existing_names)

    if command:
        program = _command(draft, command)
        if program is None:
            return _entry(draft, None, existing_names)
        env = _collect(draft, "env", raw.get("env"))
        cwd = _cwd(draft, raw.get("cwd"))
        timeout = _timeout(draft, raw.get("timeout"), DEFAULT_STDIO_TIMEOUT)
        config = _stdio_config(draft, program, _args(draft, raw.get("args")), env, cwd, timeout)
        return _entry(draft, config, existing_names)

    draft.refuse("entrée sans « url » ni « command » : rien à importer.")
    return _entry(draft, None, existing_names)


_PARSERS: dict[str, Callable[[str, set[str]], list[McpImportEntry]]] = {
    "claude": _parse_claude,
    "codex": _parse_codex,
    "hermes": _parse_hermes,
}

_FORMAT_LABELS = {
    "claude": "Claude Code (mcpServers)",
    "codex": "Codex ([mcp_servers.*])",
    "hermes": "Hermes (mcp_servers:)",
}


# --- aperçu -----------------------------------------------------------------------------------


def parse_import(
    import_format: str, content: str, existing_names: Iterable[str] | None = None
) -> McpImportPreview:
    """Aperçu normalisé d'une configuration importée ; ne lève jamais sur un contenu hostile."""

    if not isinstance(content, str):
        return McpImportPreview(errors=["Contenu illisible : du texte était attendu."])
    if len(content) > MAX_IMPORT_CHARS:
        return McpImportPreview(
            errors=[
                f"Contenu trop volumineux ({len(content)} caractères) : "
                f"{MAX_IMPORT_CHARS} au maximum."
            ]
        )
    names = {str(name) for name in (existing_names or ())}
    detected = import_format if import_format in _PARSERS else detect_format(content)
    if detected is None:
        return McpImportPreview(
            errors=[
                "Format non reconnu : un fichier Claude Code (« mcpServers »), Codex "
                "(« [mcp_servers.…] ») ou Hermes (« mcp_servers: ») est attendu."
            ]
        )
    try:
        entries = _PARSERS[detected](content, names)
    except ImportParseError as exc:
        return McpImportPreview(detected_format=detected, errors=[str(exc)])
    errors: list[str] = []
    if not entries:
        errors.append(
            f"Aucun serveur MCP trouvé dans ce contenu {_FORMAT_LABELS[detected]} : rien à importer."
        )
    elif len(entries) >= MAX_ENTRIES:
        # L'aperçu s'arrête à cette borne : le dire plutôt que de laisser croire à un tout.
        errors.append(
            f"Aperçu limité à {MAX_ENTRIES} entrées : si la configuration en contient davantage, "
            "les suivantes n'ont pas été lues — importez-la par parties."
        )
    return McpImportPreview(detected_format=detected, entries=entries, errors=errors)


# --- application --------------------------------------------------------------------------------


class _ApplyRefused(RuntimeError):
    """Refus d'une entrée à l'application : message destiné à ``McpImportApplyResult.errors``."""


def _config_with_secrets(
    db: Session, entry: McpImportEntry, mapping: Mapping[str, str]
) -> McpServerConfig:
    """Remplit ``header_secrets``/``env_secrets`` à partir du mapping fourni par l'appelant."""

    assert entry.config is not None  # garanti par ``importable``
    config = entry.config.model_copy(deep=True)
    for candidate in entry.secret_candidates:
        secret_id = (mapping or {}).get(candidate.suggested_secret_name)
        if not secret_id:
            raise _ApplyRefused(
                f"Entrée « {entry.name} » ignorée : secret « {candidate.suggested_secret_name} » "
                f"non fourni pour {candidate.location} « {candidate.key} »."
            )
        secret = db.get(SecretModel, secret_id)
        if secret is None:
            raise _ApplyRefused(
                f"Entrée « {entry.name} » ignorée : le secret {secret_id!r} n'existe pas "
                "dans le coffre."
            )
        if secret.revoked_at is not None:
            raise _ApplyRefused(
                f"Entrée « {entry.name} » ignorée : le secret « {secret.name} » est révoqué."
            )
        if candidate.location == "header" and config.http is not None:
            config.http.header_secrets[candidate.key] = SecretRef(secret_id=secret_id)
        elif candidate.location == "env" and config.stdio is not None:
            config.stdio.env_secrets[candidate.key] = SecretRef(secret_id=secret_id)
        else:
            raise _ApplyRefused(
                f"Entrée « {entry.name} » ignorée : un secret de type « {candidate.location} » "
                "n'est pas injectable dans ce transport."
            )
    return config


def _import_note(entry: McpImportEntry, import_format: str) -> str:
    return (
        f"Importé depuis {import_format} (entrée « {entry.source_name} »). "
        "Configuration reprise telle quelle : à diagnostiquer avant activation."
    )[:2000]


def apply_import(
    db: Session,
    principal: str,
    request: McpImportApplyRequest,
    preview: McpImportPreview,
    *,
    policy: OutboundPolicy | None = None,
) -> McpImportApplyResult:
    """Crée (ou révise) les serveurs choisis à partir d'un aperçu déjà calculé.

    Les serveurs sont créés en ``draft`` : rien n'est actif sans diagnostic ni activation
    explicite. En cas de conflit de nom, ``new_revision`` ajoute une révision — l'ancienne
    est conservée telle quelle, c'est la sauvegarde permettant un retour arrière.
    """

    if len(request.names) > MAX_ENTRIES:
        # Un aperçu ne peut pas contenir plus de MAX_ENTRIES entrées : au-delà, la
        # sélection ne correspond à aucun aperçu. On refuse sans parcourir la liste
        # plutôt que d'ouvrir une boucle serveur sur une entrée contrôlée par le client.
        return McpImportApplyResult(
            errors=[
                f"Sélection refusée ({len(request.names)} noms) : au plus {MAX_ENTRIES} "
                "entrées par application, comme l'aperçu."
            ]
        )

    effective_policy = policy if policy is not None else OutboundPolicy.from_environ(os.environ)
    import_format = preview.detected_format or "import"
    by_name = {entry.name: entry for entry in preview.entries}

    created: list[Any] = []
    revised: list[Any] = []
    skipped: list[str] = []
    errors: list[str] = []
    requested: list[str] = []
    seen: set[str] = set()

    for raw_name in request.names:
        name = str(raw_name)
        if name in seen:
            continue
        seen.add(name)
        requested.append(name)
        entry = by_name.get(name)
        if entry is None:
            skipped.append(name)
            errors.append(
                f"Entrée « {name} » absente de l'aperçu de ce contenu : rien n'a été importé."
            )
            continue
        if not entry.importable or entry.config is None:
            skipped.append(name)
            reason = "; ".join(entry.unsupported) or "configuration incomplète"
            errors.append(f"Entrée « {name} » non importable : {reason}")
            continue
        try:
            config = _config_with_secrets(db, entry, request.secret_mapping)
        except _ApplyRefused as exc:
            skipped.append(name)
            errors.append(str(exc))
            continue
        try:
            flags = service.validate_config(config, effective_policy)
        except ConfigRefused as exc:
            skipped.append(name)
            errors.append(f"Entrée « {name} » refusée ({exc.code}) : {exc}")
            continue

        existing = db.query(McpServerModel).filter_by(name=name).first()
        if existing is not None:
            if request.on_conflict == "skip":
                skipped.append(name)
                continue
            if existing.status == "revoked":
                skipped.append(name)
                errors.append(
                    f"Entrée « {name} » ignorée : un serveur révoqué porte déjà ce nom "
                    "(la révocation est irréversible)."
                )
                continue
            if existing.transport != config.transport:
                skipped.append(name)
                errors.append(
                    f"Entrée « {name} » ignorée : le serveur existant utilise le transport "
                    f"« {existing.transport} » et le transport ne change pas au fil des révisions."
                )
                continue
            revision = service.create_revision(
                db,
                existing,
                config,
                principal=principal,
                note=_import_note(entry, import_format),
                risk_flags=flags,
            )
            service.record_event(
                db,
                "mcp.server.revised",
                payload={
                    "server_id": existing.id,
                    "server_name": existing.name,
                    "revision_id": revision.id,
                    "revision_number": revision.number,
                    "requires_approval": bool(revision.requires_approval),
                    "source": "import",
                },
            )
            revised.append(service.server_summary(db, existing))
            continue

        server = McpServerModel(
            name=name,
            display_name=(entry.source_name or name)[:120],
            description="",
            source_kind="import",
            origin=import_format[:500],
            transport=config.transport,
            execution_location=config.execution_location,
            status="draft",
            created_by_user_id=principal,
        )
        db.add(server)
        db.flush()
        revision = service.create_revision(
            db,
            server,
            config,
            principal=principal,
            note=_import_note(entry, import_format),
            risk_flags=flags,
        )
        service.record_event(
            db,
            "mcp.server.created",
            payload={
                "server_id": server.id,
                "server_name": server.name,
                "transport": server.transport,
                "execution_location": server.execution_location,
                "revision_id": revision.id,
                "risk_flags": [flag.code for flag in flags],
                "source": "import",
            },
        )
        created.append(service.server_summary(db, server))

    service.record_event(
        db,
        "mcp.import.applied",
        payload={
            # Noms et décisions uniquement : ni configuration complète, ni valeur de secret.
            "format": preview.detected_format,
            "on_conflict": request.on_conflict,
            "requested": requested,
            "created": [summary.name for summary in created],
            "revised": [summary.name for summary in revised],
            "skipped": skipped,
            "error_count": len(errors),
        },
    )
    return McpImportApplyResult(created=created, revised=revised, skipped=skipped, errors=errors)
