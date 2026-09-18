"""Logique métier du centre MCP : empreintes, risques, révisions, probes, bindings, exports.

Règles structurantes :

- une révision est immuable et ne contient **que des références** de secrets ;
- une valeur de secret n'est déchiffrée que pour un appel autorisé (probe HTTP côté API,
  claim d'un probe stdio par un runner authentifié) et ne figure dans aucune réponse
  utilisateur, aucun export, aucun événement ;
- rien n'est activé sans découverte courante ; un lancement stdio exige une autorisation
  explicite portant l'empreinte exacte de la révision ;
- une absence de résultat produit un état explicite (``failed``, ``expired``, ``invalidated``),
  jamais un succès implicite.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

import yaml
from sqlalchemy.orm import Session

from acp_contracts import (
    Event,
    McpBinding,
    McpDiscoveredTool,
    McpDiscovery,
    McpExport,
    McpProbe,
    McpProbeAuthorization,
    McpProbeResult,
    McpRevisionDiff,
    McpRiskFlag,
    McpServerConfig,
    McpServerDetail,
    McpServerRevision,
    McpServerSummary,
    McpStdioConfig,
)
from acp_contracts.redaction import redact_data, redact_text, redaction_values
from acp_database.models import (
    McpBindingModel,
    McpProbeModel,
    McpServerModel,
    McpServerRevisionModel,
    SecretModel,
    WorkerModel,
)

from ..events_bus import store_event
from ..outbound import OutboundPolicy, OutboundPolicyError, PinnedHttpClient
from ..secrets_vault import SecretsVault, VaultDecryptionFailed
from .client import McpClientError, discover_http

# --- constantes ---------------------------------------------------------------------------

PROBE_AUTHORIZATION_TTL = timedelta(hours=1)
PROBE_LEASE_SECONDS = 180
MAX_PROBES_IN_DETAIL = 10

ACTIVE_PROBE_STATUSES = ("pending_approval", "queued", "claimed")
TERMINAL_PROBE_STATUSES = (
    "succeeded",
    "failed",
    "rejected",
    "expired",
    "invalidated",
    "cancelled",
)
ACCEPTED_AUTHORIZATION_STATUSES = ("queued", "claimed", "succeeded", "failed")

SECRET_PLACEHOLDER_PREFIX = "ACP_SECRET_"
STDIO_PROBE_CAPABILITY = "mcp_stdio_probe"

#: Codes de risque qui interdisent l'enregistrement d'une configuration (spec §4.4).
REFUSED_RISK_CODES = (
    "relative_command",
    "unpinned_package",
    "header_looks_secret",
    "env_looks_secret",
)

_SECRET_KEY_RE = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD|AUTHORIZATION|CREDENTIAL)", re.IGNORECASE)
#: Jeton HTTP (RFC 9110) : tout autre nom d'en-tête permettrait une injection.
_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

STDIO_CONSEQUENCES = [
    "Lance un processus sur le runner désigné avec les variables d'environnement configurées.",
    "Le processus peut lire les valeurs des secrets référencés par la configuration.",
    "Le processus accède au système de fichiers et au réseau du runner, selon ce que la commande autorise.",
    "L'autorisation ne vaut que pour cette empreinte de configuration et expire au bout d'une heure.",
]


class SecretResolutionError(RuntimeError):
    """Un secret référencé est introuvable ou révoqué : aucun appel n'est tenté."""


class HeaderNotTransmittable(RuntimeError):
    """Un en-tête résolu n'est pas transmissible : l'appel est refusé avant tout envoi."""


class ProbeTransitionConflict(RuntimeError):
    """Le lease d'un probe a changé avant l'écriture de son résultat terminal."""


class ConfigRefused(ValueError):
    """Configuration refusée par la politique (risque bloquant ou URL invalide)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- horodatage ----------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite rend des dates naïves : on les relit comme de l'UTC."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# --- empreintes et références de secrets ----------------------------------------------------


def canonical_fingerprint(config: McpServerConfig) -> str:
    """Empreinte sha256 du JSON canonique de la configuration (références comprises)."""

    payload = config.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def secret_ids_in_config(config: dict) -> set[str]:
    """Identifiants de secrets référencés par une configuration (jamais des valeurs)."""

    ids: set[str] = set()
    for block in ("http", "stdio"):
        section = config.get(block) if isinstance(config, dict) else None
        if not isinstance(section, dict):
            continue
        for field in ("header_secrets", "env_secrets"):
            refs = section.get(field) or {}
            if not isinstance(refs, dict):
                continue
            for ref in refs.values():
                if isinstance(ref, dict) and isinstance(ref.get("secret_id"), str):
                    ids.add(ref["secret_id"])
    return ids


def referencing_server_ids(
    db: Session, secret_id: str, *, active_only: bool = False
) -> list[str]:
    """Serveurs dont la révision courante référence ``secret_id`` (statut ``active`` seulement si demandé)."""

    query = db.query(McpServerModel).filter(McpServerModel.current_revision_id.is_not(None))
    if active_only:
        query = query.filter(McpServerModel.status == "active")
    result: list[str] = []
    for server in query.order_by(McpServerModel.created_at, McpServerModel.id).all():
        revision = db.get(McpServerRevisionModel, server.current_revision_id)
        if revision is not None and secret_id in secret_ids_in_config(revision.config or {}):
            result.append(server.id)
    return result


def foreign_project_secrets(db: Session, config: Mapping[str, Any], project_id: str) -> list[str]:
    """Noms des secrets de portée projet référencés par ``config`` qui appartiennent à un autre projet."""

    names: list[str] = []
    for secret_id in sorted(secret_ids_in_config(dict(config or {}))):
        secret = db.get(SecretModel, secret_id)
        if secret is None:
            continue
        if secret.scope_type == "project" and secret.project_id != project_id:
            names.append(secret.name)
    return sorted(names)


def resolve_secret_values(
    db: Session,
    vault: SecretsVault,
    refs: Mapping[str, Any],
    *,
    purpose: str,
    touch: bool = True,
) -> dict[str, str]:
    """Déchiffre les secrets référencés pour un appel autorisé ; met à jour ``last_used_at``.

    ``purpose`` documente l'appel autorisé (``mcp_probe``, ``mcp_stdio_claim``) ; il n'est
    jamais journalisé avec une valeur. ``touch=False`` sert aux résolutions qui ne
    transmettent rien au tiers (contrôle d'expurgation d'un résultat de runner) : elles ne
    doivent pas faire croire à un usage du secret.
    """

    resolved: dict[str, str] = {}
    now = utcnow()
    for key, ref in refs.items():
        secret_id = ref.secret_id if hasattr(ref, "secret_id") else (ref or {}).get("secret_id")
        secret = db.get(SecretModel, secret_id) if secret_id else None
        if secret is None:
            raise SecretResolutionError(
                f"Secret introuvable pour « {key} » : la référence {secret_id!r} n'existe plus."
            )
        if secret.revoked_at is not None:
            raise SecretResolutionError(
                f"Secret « {secret.name} » révoqué : l'appel ({purpose}) est refusé."
            )
        try:
            resolved[key] = vault.decrypt(secret.ciphertext)
        except VaultDecryptionFailed as exc:
            # Clé retirée de ACP_SECRETS_KEYS ou jeton altéré : état explicite pour l'appelant,
            # jamais une erreur serveur ni un appel tenté avec une valeur vide.
            raise SecretResolutionError(
                f"Secret « {secret.name} » illisible : la clé de chiffrement {secret.key_id} n'est "
                f"plus dans ACP_SECRETS_KEYS ; l'appel ({purpose}) est refusé."
            ) from exc
        if touch:
            secret.last_used_at = now
    return resolved


def record_event(
    db: Session, event_type: str, *, project_id: str | None = None, payload: dict[str, Any]
) -> None:
    """Événement d'audit durable ; le payload ne contient jamais de valeur de secret.

    ``store_event`` alloue le numéro de journal : une ligne écrite sans lui sort de
    la page projet jusqu'au prochain redémarrage, puis y remonte hors d'ordre.
    ``commit=False`` laisse la transaction à l'appelant, comme avant.
    """

    store_event(
        db,
        Event(type=event_type, project_id=project_id, payload=payload),
        commit=False,
    )


# --- risques ---------------------------------------------------------------------------------


def _command_basename(command: str) -> str:
    tail = re.split(r"[\\/]", command.strip())[-1].lower()
    for suffix in (".cmd", ".exe", ".bat", ".ps1"):
        if tail.endswith(suffix):
            return tail[: -len(suffix)]
    return tail


_FLOATING_VERSION_SEGMENTS = frozenset({"x", "X", "*", "latest", "next", "canary", "stable"})
_VERSION_RANGE_CHARACTERS = frozenset("^~><=|,! \t")


def is_absolute_command(command: str) -> bool:
    """Chemin absolu POSIX (``/usr/bin/x``) ou Windows (``C:\\x``, ``\\\\serveur\\part``)."""

    value = (command or "").strip()
    if not value:
        return False
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _looks_like_path(argument: str) -> bool:
    return argument.startswith(("/", "\\", ".", "~")) or bool(_WINDOWS_DRIVE_RE.match(argument))


def _is_concrete_version(version: str) -> bool:
    """Vrai pour « 1.2.3 », « v2025.8.21 », « 1.0.0-rc.1 » ; faux pour « latest », « ^1.0 », « 1.x »."""

    value = version.strip()
    if not value or _VERSION_RANGE_CHARACTERS.intersection(value):
        return False
    head = value[1:] if value[0] in "vV" else value
    if not head[:1].isdigit():
        return False
    return not _FLOATING_VERSION_SEGMENTS.intersection(re.split(r"[.\-+]", head))


def _is_pinned_package(spec: str) -> bool:
    """Un paquet n'est épinglé que s'il porte une version concrète (« @1.2.3 », « ==1.0 »)."""

    if "==" in spec:
        return _is_concrete_version(spec.rsplit("==", 1)[1])
    name = spec[1:] if spec.startswith("@") else spec  # portée npm « @scope/paquet »
    if "@" not in name:
        return False
    return _is_concrete_version(name.rsplit("@", 1)[1])


def unpinned_package(config: McpStdioConfig) -> str | None:
    """Paquet lancé par ``npx``/``uvx``/``pipx run`` sans version épinglée, le cas échéant."""

    runner = _command_basename(config.command)
    arguments = list(config.args)
    if runner == "pipx":
        if not arguments or arguments[0] != "run":
            return None
        arguments = arguments[1:]
    elif runner not in {"npx", "uvx"}:
        return None
    for argument in arguments:
        if argument.startswith("-") or _looks_like_path(argument):
            continue
        return None if _is_pinned_package(argument) else argument
    return None


def risk_flags_for(config: McpServerConfig) -> list[McpRiskFlag]:
    """Avis de risque sur une configuration ; l'ordre fixe la priorité des refus."""

    flags: list[McpRiskFlag] = []
    if config.transport == "http" and config.http is not None:
        url = config.http.url.strip()
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:  # URL illisible : la politique de sortie la refusera explicitement
            host = ""
        if url.lower().startswith("http://"):
            flags.append(
                McpRiskFlag(
                    code="http_without_tls",
                    level="danger",
                    message=(
                        "Point d'accès en http sans TLS : les en-têtes, dont les secrets injectés, "
                        "circulent en clair."
                    ),
                )
            )
        for name, value in config.http.headers.items():
            if _SECRET_KEY_RE.search(name) and value.strip():
                flags.append(
                    McpRiskFlag(
                        code="header_looks_secret",
                        level="caution",
                        message=(
                            f"L'en-tête « {name} » porte une valeur littérale qui ressemble à un "
                            "secret : utilisez une référence de secret (header_secrets)."
                        ),
                    )
                )
        if host in _LOCALHOST_HOSTS or host.endswith(".localhost"):
            flags.append(
                McpRiskFlag(
                    code="localhost_target",
                    level="info",
                    message=(
                        "Cible locale : elle est résolue dans le contexte d'exécution de la "
                        "plateforme, pas depuis un service distant."
                    ),
                )
            )
    elif config.stdio is not None:
        if not is_absolute_command(config.stdio.command):
            flags.append(
                McpRiskFlag(
                    code="relative_command",
                    level="danger",
                    message=(
                        f"Commande relative « {config.stdio.command} » : indiquez le chemin absolu "
                        "de l'exécutable sur le runner (le PATH du runner n'est pas une garantie)."
                    ),
                )
            )
        unpinned = unpinned_package(config.stdio)
        if unpinned is not None:
            flags.append(
                McpRiskFlag(
                    code="unpinned_package",
                    level="danger",
                    message=(
                        f"Paquet « {unpinned} » lancé sans version épinglée : ajoutez « @version » "
                        "(ou « ==version ») pour éviter une mise à jour silencieuse."
                    ),
                )
            )
        for name, value in config.stdio.env.items():
            if _SECRET_KEY_RE.search(name) and value.strip():
                flags.append(
                    McpRiskFlag(
                        code="env_looks_secret",
                        level="caution",
                        message=(
                            f"La variable « {name} » porte une valeur littérale qui ressemble à un "
                            "secret : utilisez une référence de secret (env_secrets)."
                        ),
                    )
                )
    return flags


def header_issue(name: str, value: str) -> tuple[str, str] | None:
    """Refus structurel d'un en-tête HTTP (injection d'en-tête, encodage impossible)."""

    if not _HEADER_NAME_RE.fullmatch(name or ""):
        return (
            "invalid_header_name",
            f"Nom d'en-tête refusé « {name} » : seuls les caractères d'un jeton HTTP sont "
            "acceptés (ni espace, ni deux-points, ni retour à la ligne).",
        )
    if _CONTROL_CHARS_RE.search(value or ""):
        return (
            "invalid_header_value",
            f"Valeur de l'en-tête « {name} » refusée : les caractères de contrôle permettraient "
            "d'injecter un autre en-tête.",
        )
    try:
        (value or "").encode("ascii")
    except UnicodeEncodeError:
        return (
            "invalid_header_value",
            f"Valeur de l'en-tête « {name} » refusée : un en-tête HTTP doit être encodable en "
            "ASCII (encodez la valeur, par exemple en base64, avant de l'enregistrer).",
        )
    return None


def env_issue(name: str, value: str) -> tuple[str, str] | None:
    """Refus structurel d'une variable d'environnement transmise au runner."""

    if not name or "=" in name or _CONTROL_CHARS_RE.search(name):
        return (
            "invalid_env_name",
            f"Nom de variable refusé « {name} » : un nom non vide sans « = » ni caractère de "
            "contrôle est attendu.",
        )
    if "\x00" in (value or ""):
        return (
            "invalid_env_value",
            f"Valeur de la variable « {name} » refusée : le caractère nul est interdit dans "
            "l'environnement d'un processus.",
        )
    return None


def ensure_transmittable_headers(headers: Mapping[str, str]) -> None:
    """Contrôle les en-têtes **après** résolution des secrets ; le message ne cite aucune valeur."""

    for name, value in headers.items():
        issue = header_issue(name, value)
        if issue is not None:
            code, _ = issue
            raise HeaderNotTransmittable(
                f"En-tête « {name} » non transmissible ({code}) : la valeur résolue contient des "
                "caractères interdits dans un en-tête HTTP (ASCII sans caractère de contrôle)."
            )


def blocking_risk(flags: Iterable[McpRiskFlag]) -> McpRiskFlag | None:
    """Premier risque qui interdit l'enregistrement, selon l'ordre de ``REFUSED_RISK_CODES``."""

    by_code = {flag.code: flag for flag in flags}
    for code in REFUSED_RISK_CODES:
        if code in by_code:
            return by_code[code]
    return None


def validate_config(config: McpServerConfig, policy: OutboundPolicy) -> list[McpRiskFlag]:
    """Contrôle une configuration avant enregistrement ; lève ``ConfigRefused`` si elle est refusée."""

    if config.transport == "http" and config.http is not None:
        pairs = [*config.http.headers.items(), *((name, "") for name in config.http.header_secrets)]
        for name, value in pairs:
            issue = header_issue(name, value)
            if issue is not None:
                raise ConfigRefused(*issue)
    elif config.stdio is not None:
        pairs = [*config.stdio.env.items(), *((name, "") for name in config.stdio.env_secrets)]
        for name, value in pairs:
            issue = env_issue(name, value)
            if issue is not None:
                raise ConfigRefused(*issue)
    flags = risk_flags_for(config)
    blocking = blocking_risk(flags)
    if blocking is not None:
        raise ConfigRefused(blocking.code, blocking.message)
    if config.transport == "http" and config.http is not None:
        try:
            policy.validate_url(config.http.url)
        except OutboundPolicyError as exc:
            raise ConfigRefused(exc.code, str(exc)) from exc
    return flags


# --- diff de révision --------------------------------------------------------------------------


def _flat_config(config: McpServerConfig) -> dict[str, Any]:
    data: dict[str, Any] = {"transport": config.transport}
    if config.http is not None:
        data["http.url"] = config.http.url
        data["http.headers"] = dict(sorted(config.http.headers.items()))
        data["http.header_secrets"] = {
            key: ref.secret_id for key, ref in sorted(config.http.header_secrets.items())
        }
        data["http.timeout_seconds"] = config.http.timeout_seconds
    if config.stdio is not None:
        data["stdio.command"] = config.stdio.command
        data["stdio.args"] = list(config.stdio.args)
        data["stdio.env"] = dict(sorted(config.stdio.env.items()))
        data["stdio.env_secrets"] = {
            key: ref.secret_id for key, ref in sorted(config.stdio.env_secrets.items())
        }
        data["stdio.cwd"] = config.stdio.cwd
        data["stdio.timeout_seconds"] = config.stdio.timeout_seconds
    return data


_LAUNCH_FIELDS = ("stdio.command", "stdio.args", "stdio.env", "stdio.env_secrets", "stdio.cwd")
_FIELD_REASONS = {
    "transport": "Le transport change.",
    "http.url": "Le point d'accès HTTP change.",
    "http.headers": "Les en-têtes littéraux changent.",
    "http.header_secrets": "Les secrets injectés en en-tête changent.",
    "http.timeout_seconds": "Le délai d'attente change.",
    "stdio.command": "La commande lancée sur le runner change.",
    "stdio.args": "Les arguments de lancement changent.",
    "stdio.env": "Les variables d'environnement littérales changent.",
    "stdio.env_secrets": "Les secrets injectés en environnement changent.",
    "stdio.cwd": "Le répertoire de travail change.",
    "stdio.timeout_seconds": "Le délai d'attente change.",
}


def compute_revision_diff(
    previous: McpServerRevisionModel | None, config: McpServerConfig
) -> McpRevisionDiff:
    """Diff de ``config`` par rapport à la révision précédente (``None`` = première révision)."""

    new_flat = _flat_config(config)
    if previous is None:
        requires_approval = config.transport == "stdio"
        return McpRevisionDiff(
            previous_number=None,
            changed_fields=[],
            endpoint_changed=False,
            command_changed=False,
            secrets_added=sorted(secret_ids_in_config(config.model_dump(mode="json"))),
            secrets_removed=[],
            tools_added=[],
            tools_removed=[],
            requires_approval=requires_approval,
            reasons=(
                ["Première révision : cette empreinte n'a jamais été autorisée."]
                if requires_approval
                else []
            ),
        )
    previous_config = McpServerConfig.model_validate(previous.config or {})
    old_flat = _flat_config(previous_config)
    changed = [key for key, value in new_flat.items() if old_flat.get(key) != value]
    changed += [key for key in old_flat if key not in new_flat]
    old_secrets = secret_ids_in_config(previous.config or {})
    new_secrets = secret_ids_in_config(config.model_dump(mode="json"))
    launch_changed = any(field in changed for field in _LAUNCH_FIELDS)
    requires_approval = config.transport == "stdio" and (
        launch_changed or "transport" in changed
    )
    reasons = [_FIELD_REASONS[field] for field in changed if field in _FIELD_REASONS]
    return McpRevisionDiff(
        previous_number=previous.number,
        changed_fields=changed,
        endpoint_changed="http.url" in changed or "transport" in changed,
        command_changed="stdio.command" in changed,
        secrets_added=sorted(new_secrets - old_secrets),
        secrets_removed=sorted(old_secrets - new_secrets),
        tools_added=[],
        tools_removed=[],
        requires_approval=requires_approval,
        reasons=reasons,
    )


# --- accès aux lignes -------------------------------------------------------------------------


def current_revision(db: Session, server: McpServerModel) -> McpServerRevisionModel | None:
    if not server.current_revision_id:
        return None
    return db.get(McpServerRevisionModel, server.current_revision_id)


def revisions_of(db: Session, server: McpServerModel) -> list[McpServerRevisionModel]:
    return (
        db.query(McpServerRevisionModel)
        .filter_by(server_id=server.id)
        .order_by(McpServerRevisionModel.number.asc())
        .all()
    )


def bindings_of(
    db: Session, server: McpServerModel, *, live_only: bool = False
) -> list[McpBindingModel]:
    query = db.query(McpBindingModel).filter_by(server_id=server.id)
    if live_only:
        query = query.filter(McpBindingModel.revoked_at.is_(None))
    return query.order_by(McpBindingModel.created_at.asc()).all()


def probes_of(db: Session, server: McpServerModel, *, limit: int | None = None):
    query = (
        db.query(McpProbeModel)
        .filter_by(server_id=server.id)
        .order_by(McpProbeModel.created_at.desc(), McpProbeModel.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def discovery_of(revision: McpServerRevisionModel | None) -> McpDiscovery | None:
    if revision is None or not revision.discovery:
        return None
    return McpDiscovery.model_validate(revision.discovery)


def discovery_is_current(revision: McpServerRevisionModel | None) -> bool:
    return bool(
        revision is not None
        and revision.discovery
        and revision.discovery_fingerprint
        and revision.discovery_fingerprint == revision.fingerprint
    )


def discovered_tool_names(revision: McpServerRevisionModel | None) -> list[str]:
    discovery = discovery_of(revision)
    if discovery is None or not discovery_is_current(revision):
        return []
    return [tool.name for tool in discovery.tools]


def has_accepted_authorization(db: Session, server_id: str, fingerprint: str) -> bool:
    """Une autorisation stdio a déjà été accordée pour cette empreinte exacte."""

    rows = (
        db.query(McpProbeModel)
        .filter(
            McpProbeModel.server_id == server_id,
            McpProbeModel.status.in_(ACCEPTED_AUTHORIZATION_STATUSES),
        )
        .all()
    )
    return any((probe.authorization or {}).get("fingerprint") == fingerprint for probe in rows)


def has_successful_probe(db: Session, server_id: str, fingerprint: str) -> bool:
    """Un diagnostic stdio a abouti pour cette empreinte exacte."""

    rows = (
        db.query(McpProbeModel)
        .filter(McpProbeModel.server_id == server_id, McpProbeModel.status == "succeeded")
        .all()
    )
    return any((probe.authorization or {}).get("fingerprint") == fingerprint for probe in rows)


# --- contrats -----------------------------------------------------------------------------------


def revision_contract(revision: McpServerRevisionModel) -> McpServerRevision:
    return McpServerRevision(
        id=revision.id,
        server_id=revision.server_id,
        number=revision.number,
        config=McpServerConfig.model_validate(revision.config or {}),
        fingerprint=revision.fingerprint,
        discovery=discovery_of(revision),
        discovered_at=revision.discovered_at,
        discovery_current=discovery_is_current(revision),
        risk_flags=[McpRiskFlag.model_validate(flag) for flag in revision.risk_flags or []],
        change_summary=(
            McpRevisionDiff.model_validate(revision.change_summary)
            if revision.change_summary
            else None
        ),
        requires_approval=bool(revision.requires_approval),
        note=revision.note or "",
        created_at=revision.created_at,
        superseded_at=revision.superseded_at,
    )


def probe_contract(probe: McpProbeModel) -> McpProbe:
    return McpProbe(
        id=probe.id,
        server_id=probe.server_id,
        revision_id=probe.revision_id,
        transport=probe.transport,
        status=probe.status,
        authorization=(
            McpProbeAuthorization.model_validate(probe.authorization)
            if probe.authorization
            else None
        ),
        requested_by_user_id=probe.requested_by_user_id,
        decided_by_user_id=probe.decided_by_user_id,
        decided_at=probe.decided_at,
        decision_comment=probe.decision_comment or "",
        worker_id=probe.worker_id,
        claimed_at=probe.claimed_at,
        lease_expires_at=probe.lease_expires_at,
        result=McpProbeResult.model_validate(probe.result) if probe.result else None,
        error=probe.error,
        created_at=probe.created_at,
        finished_at=probe.finished_at,
        expires_at=probe.expires_at,
    )


def binding_contract(db: Session, binding: McpBindingModel) -> McpBinding:
    server = db.get(McpServerModel, binding.server_id)
    revision = db.get(McpServerRevisionModel, binding.revision_id)
    return McpBinding(
        id=binding.id,
        server_id=binding.server_id,
        server_name=server.name if server is not None else "",
        project_id=binding.project_id,
        revision_id=binding.revision_id,
        revision_number=revision.number if revision is not None else 0,
        allowed_tools=list(binding.allowed_tools or []),
        enabled=bool(binding.enabled),
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        revoked_at=binding.revoked_at,
    )


def server_summary(db: Session, server: McpServerModel) -> McpServerSummary:
    revision = current_revision(db, server)
    probe = db.get(McpProbeModel, server.last_probe_id) if server.last_probe_id else None
    return McpServerSummary(
        id=server.id,
        name=server.name,
        display_name=server.display_name,
        description=server.description or "",
        source_kind=server.source_kind,
        origin=server.origin or "",
        transport=server.transport,
        execution_location=server.execution_location,
        status=server.status,
        current_revision_number=revision.number if revision is not None else None,
        discovery_current=discovery_is_current(revision),
        tool_count=len(discovered_tool_names(revision)),
        binding_count=len(bindings_of(db, server, live_only=True)),
        target_worker_id=server.target_worker_id,
        last_probe_status=probe.status if probe is not None else None,
        last_probe_at=(probe.finished_at or probe.created_at) if probe is not None else None,
        created_at=server.created_at,
        updated_at=server.updated_at,
        revoked_at=server.revoked_at,
    )


def server_detail(
    db: Session,
    server: McpServerModel,
    apply_notes: Iterable[str] = (),
    *,
    visible_project_ids: set[str] | None = None,
) -> McpServerDetail:
    """Détail d'un serveur ; ``visible_project_ids`` filtre les rattachements exposés.

    Un rattachement nomme un projet : il n'est montré qu'aux utilisateurs qui ont accès à
    ce projet, comme ``GET /mcp/bindings``. Le compteur ``binding_count`` reste global
    (nombre de rattachements actifs, sans nommer les projets).
    """

    revision = current_revision(db, server)
    summary = server_summary(db, server)
    bindings = bindings_of(db, server)
    if visible_project_ids is not None:
        bindings = [row for row in bindings if row.project_id in visible_project_ids]
    return McpServerDetail(
        **summary.model_dump(),
        current_revision=revision_contract(revision) if revision is not None else None,
        revisions=[revision_contract(row) for row in revisions_of(db, server)],
        bindings=[binding_contract(db, row) for row in bindings],
        probes=[probe_contract(row) for row in probes_of(db, server, limit=MAX_PROBES_IN_DETAIL)],
        apply_notes=list(apply_notes),
    )


# --- révisions -------------------------------------------------------------------------------


def create_revision(
    db: Session,
    server: McpServerModel,
    config: McpServerConfig,
    *,
    principal: str,
    note: str = "",
    risk_flags: Iterable[McpRiskFlag] | None = None,
    discovery_source: McpServerRevisionModel | None = None,
) -> McpServerRevisionModel:
    """Ajoute une révision, la rend courante et périme les autorisations devenues caduques.

    ``discovery_source`` sert au rollback : la découverte est recopiée avec son empreinte,
    identique à celle de la configuration recopiée, donc toujours courante.
    """

    previous = current_revision(db, server)
    now = utcnow()
    flags = list(risk_flags) if risk_flags is not None else risk_flags_for(config)
    diff = compute_revision_diff(previous, config)
    fingerprint = canonical_fingerprint(config)
    requires_approval = diff.requires_approval
    if requires_approval and has_accepted_authorization(db, server.id, fingerprint):
        # L'empreinte a déjà été autorisée (retour à une configuration connue).
        requires_approval = False
        diff = diff.model_copy(
            update={
                "requires_approval": False,
                "reasons": [
                    *diff.reasons,
                    "Une autorisation acceptée existe déjà pour cette empreinte.",
                ],
            }
        )
    numbers = [row.number for row in revisions_of(db, server)]
    revision = McpServerRevisionModel(
        server_id=server.id,
        number=(max(numbers) + 1) if numbers else 1,
        config=config.model_dump(mode="json"),
        fingerprint=fingerprint,
        risk_flags=[flag.model_dump(mode="json") for flag in flags],
        change_summary=diff.model_dump(mode="json"),
        requires_approval=1 if requires_approval else 0,
        created_by_user_id=principal,
        note=note or "",
    )
    if discovery_source is not None and discovery_source.discovery:
        revision.discovery = discovery_source.discovery
        revision.discovered_at = discovery_source.discovered_at
        revision.discovery_fingerprint = discovery_source.discovery_fingerprint
    db.add(revision)
    db.flush()
    if previous is not None:
        previous.superseded_at = now
    server.current_revision_id = revision.id
    server.updated_at = now
    if revision.discovery:
        refresh_tool_diff(db, revision)
    invalidate_stale_probes(db, server)
    return revision


def refresh_tool_diff(db: Session, revision: McpServerRevisionModel) -> None:
    """Complète ``tools_added``/``tools_removed`` dès qu'une découverte est disponible."""

    previous = (
        db.query(McpServerRevisionModel)
        .filter(
            McpServerRevisionModel.server_id == revision.server_id,
            McpServerRevisionModel.number < revision.number,
            McpServerRevisionModel.discovery.is_not(None),
        )
        .order_by(McpServerRevisionModel.number.desc())
        .first()
    )
    if previous is None:
        return
    before = [tool.name for tool in (discovery_of(previous) or McpDiscovery(protocol_version="")).tools]
    after = [tool.name for tool in (discovery_of(revision) or McpDiscovery(protocol_version="")).tools]
    summary = dict(revision.change_summary or {})
    summary["tools_added"] = [name for name in after if name not in before]
    summary["tools_removed"] = [name for name in before if name not in after]
    revision.change_summary = summary


def invalidate_stale_probes(db: Session, server: McpServerModel) -> None:
    """Une autorisation ne survit pas à un changement de révision courante."""

    now = utcnow()
    # Le prédicat doit être réévalué par la base au moment de l'UPDATE. Une
    # révision peut avoir chargé un probe ``queued`` pendant qu'un worker le
    # réclame : une mutation ORM de cet objet devenu périmé écraserait ensuite le
    # ``claimed`` commité et rendrait un payload déjà remis impossible à rapporter.
    # Ce CAS donne la priorité à l'opération qui acquiert/valide la ligne en
    # premier, sous SQLite comme sous PostgreSQL.
    db.query(McpProbeModel).filter(
        McpProbeModel.server_id == server.id,
        McpProbeModel.revision_id != server.current_revision_id,
        McpProbeModel.status.in_(("pending_approval", "queued")),
    ).update(
        {
            McpProbeModel.status: "invalidated",
            McpProbeModel.error: (
                "Révision courante modifiée : l'autorisation ne correspond plus."
            ),
            McpProbeModel.finished_at: now,
        },
        # ``has_accepted_authorization`` peut avoir chargé le même probe dans
        # l'identity-map. Synchroniser évite que la réponse de la route de
        # révision annonce encore ``queued`` après le CAS commité.
        synchronize_session="fetch",
    )


def _cas_probe_status(
    db: Session,
    probe: McpProbeModel,
    *,
    expected_status: str,
    next_status: str,
    values: Mapping[Any, Any] | None = None,
) -> bool:
    """Transitionne une ligne seulement si son état décisionnel est encore celui lu.

    Le prédicat SQL est l'arbitre après toute attente de verrou : PostgreSQL le
    réévalue après le commit concurrent et SQLite après la sérialisation de
    l'écrivain. Le ``refresh`` est indispensable si le CAS perd, car l'identity-map
    pourrait sinon continuer à exposer l'ancien état chargé.
    """

    assignments: dict[Any, Any] = {McpProbeModel.status: next_status}
    assignments.update(values or {})
    transitioned = db.query(McpProbeModel).filter(
        McpProbeModel.id == probe.id,
        McpProbeModel.status == expected_status,
    ).update(assignments, synchronize_session=False)
    db.refresh(probe)
    return transitioned == 1


def expire_probe_if_due(
    db: Session,
    probe: McpProbeModel,
    *,
    now: datetime | None = None,
) -> bool:
    """Périme/invalide un probe par CAS, sans écraser un claim ou un état terminal."""

    _ensure_sqlite_probe_write_transaction(db)
    effective_now = now or utcnow()
    expected_status = probe.status
    next_status: str | None = None
    error: str | None = None
    if expected_status in ("pending_approval", "queued"):
        server = db.get(McpServerModel, probe.server_id)
        if server is not None and server.current_revision_id != probe.revision_id:
            next_status = "invalidated"
            error = "Révision courante modifiée : l'autorisation ne correspond plus."
        elif as_utc(probe.expires_at) is not None and as_utc(probe.expires_at) <= effective_now:
            next_status = "expired"
            error = "Autorisation expirée avant exécution."
    elif expected_status == "claimed":
        lease = as_utc(probe.lease_expires_at)
        if lease is not None and lease <= effective_now:
            next_status = "expired"
            error = "Lease du runner expiré : résultat inconnu, aucun succès supposé."
    if next_status is None:
        return False
    return _cas_probe_status(
        db,
        probe,
        expected_status=expected_status,
        next_status=next_status,
        values={McpProbeModel.error: error, McpProbeModel.finished_at: effective_now},
    )


def expire_probes(db: Session, *, now: datetime | None = None) -> int:
    """Périme les autorisations et leases par transitions atomiques et comptées."""

    _ensure_sqlite_probe_write_transaction(db)
    effective_now = now or utcnow()
    rows = (
        db.query(McpProbeModel)
        .filter(McpProbeModel.status.in_(ACTIVE_PROBE_STATUSES))
        .populate_existing()
        .all()
    )
    return sum(expire_probe_if_due(db, probe, now=effective_now) for probe in rows)


# --- probes -------------------------------------------------------------------------------------


def _redact_tool(tool: McpDiscoveredTool, redactions: Sequence[str]) -> dict[str, Any]:
    """Un outil est entièrement du contenu serveur : nom, description et schéma."""

    return {
        "name": redact_text(tool.name, redactions),
        "description": redact_text(tool.description, redactions),
        "input_schema": redact_data(tool.input_schema, redactions),
    }


def redact_discovery(discovery: McpDiscovery, redactions: Sequence[str]) -> McpDiscovery:
    """Expurge tout ce que le serveur sondé a renvoyé (``serverInfo``, capacités, outils).

    Le contenu d'une découverte est une donnée non fiable écrite en base puis servie à
    tout utilisateur authentifié : un serveur qui réécrit la valeur injectée dans
    ``serverInfo`` ou dans la description d'un outil la publierait sans cette étape.
    Seules les valeurs venant du serveur sont traversées — jamais les noms de champs du
    contrat, qu'une valeur de secret homonyme casserait.
    """

    if not redactions:
        return discovery
    return McpDiscovery.model_validate(
        {
            "protocol_version": redact_text(discovery.protocol_version, redactions),
            "server_info": redact_data(discovery.server_info, redactions),
            "tools": [_redact_tool(tool, redactions) for tool in discovery.tools],
            "capabilities": redact_data(discovery.capabilities, redactions),
            "truncated": discovery.truncated,
        }
    )


def redact_probe_result(result: McpProbeResult, redactions: Sequence[str]) -> McpProbeResult:
    """Même règle pour le résultat de diagnostic persisté dans ``mcp_probes.result``."""

    if not redactions:
        return result
    return McpProbeResult.model_validate(
        {
            "protocol_version": (
                None
                if result.protocol_version is None
                else redact_text(result.protocol_version, redactions)
            ),
            "server_info": (
                None if result.server_info is None else redact_data(result.server_info, redactions)
            ),
            "tools": [_redact_tool(tool, redactions) for tool in result.tools],
            "exit_code": result.exit_code,
            "stderr_tail": redact_text(result.stderr_tail, redactions),
            "duration_ms": result.duration_ms,
            "error": None if result.error is None else redact_text(result.error, redactions),
        }
    )


def stdio_redaction_values(
    db: Session,
    vault: SecretsVault | None,
    revision: McpServerRevisionModel | None,
) -> tuple[str, ...]:
    """Valeurs injectées au runner pour cette révision, à masquer dans ce qu'il rapporte.

    Le runner expurge déjà ; ce second contrôle côté serveur existe parce qu'un runner
    compromis ou ancien ne doit pas pouvoir faire écrire une valeur de secret en base.
    Sans coffre lisible alors que la révision référence des secrets, la vérification est
    impossible : l'appelant en fait un échec explicite, jamais un enregistrement muet.
    """

    if revision is None:
        return ()
    config = McpServerConfig.model_validate(revision.config or {})
    refs = config.stdio.env_secrets if config.stdio is not None else {}
    if not refs:
        return ()
    if vault is None:
        raise SecretResolutionError(
            "Coffre de secrets non configuré : le résultat du runner ne peut pas être "
            "contrôlé (définissez ACP_SECRETS_KEYS)."
        )
    values = resolve_secret_values(db, vault, refs, purpose="mcp_probe_redaction", touch=False)
    return redaction_values(values)


def _attach_discovery(
    db: Session,
    server: McpServerModel,
    revision: McpServerRevisionModel,
    discovery: McpDiscovery,
) -> None:
    revision.discovery = discovery.model_dump(mode="json")
    revision.discovered_at = utcnow()
    revision.discovery_fingerprint = revision.fingerprint
    refresh_tool_diff(db, revision)
    server.updated_at = utcnow()


def run_http_probe(
    db: Session,
    server: McpServerModel,
    revision: McpServerRevisionModel,
    *,
    principal: str,
    vault: SecretsVault | None,
    policy: OutboundPolicy,
    resolver: Callable[..., object],
    transport: Any = None,
) -> McpProbeModel:
    """Exécute la découverte HTTP depuis la plateforme et enregistre un résultat explicite.

    ``vault`` peut être absent : le coffre n'est exigé que si la configuration référence
    au moins un secret d'en-tête, auquel cas son absence produit un échec explicite du
    diagnostic (jamais un appel sans en-tête, jamais un refus de la route entière).

    Le probe ``queued`` est **validé avant** l'appel réseau, qui peut durer jusqu'au
    délai configuré (120 s au plus) : une transaction gardée ouverte pendant ce temps
    retiendrait ses verrous d'écriture et, avec le verrou du journal d'événements,
    bloquerait tous les producteurs d'événements. Le résultat est ensuite écrit par
    compare-and-set ``queued → succeeded/failed`` dans une transaction courte : si le
    probe a quitté ``queued`` pendant l'appel (révision remplacée, autorisation
    périmée), son résultat ne décrit plus la révision courante et n'est ni publié ni
    rattaché.
    """

    config = McpServerConfig.model_validate(revision.config or {})
    now = utcnow()
    probe = McpProbeModel(
        server_id=server.id,
        revision_id=revision.id,
        transport="http",
        status="queued",
        authorization={},
        requested_by_user_id=principal,
        expires_at=now + PROBE_AUTHORIZATION_TTL,
    )
    db.add(probe)
    db.commit()

    allowlist_used: set[tuple[str, str]] = set()
    started = time.monotonic()
    error: str | None = None
    discovery: McpDiscovery | None = None
    # Les valeurs injectées dans la requête : tout ce que le serveur distant renvoie est
    # expurgé avec elles avant d'être écrit en base (§0.3).
    redactions: tuple[str, ...] = ()
    try:
        if config.http.header_secrets and vault is None:
            raise SecretResolutionError(
                "Coffre de secrets non configuré : ce serveur référence des secrets "
                "d'en-tête, définissez ACP_SECRETS_KEYS avant de lancer un diagnostic."
            )
        headers = (
            {}
            if vault is None
            else resolve_secret_values(
                db, vault, config.http.header_secrets, purpose="mcp_probe"
            )
        )
        redactions = redaction_values(headers)
        # Contrôle après résolution : une valeur de secret non transmissible doit produire un
        # échec explicite, jamais une erreur d'encodage non gérée pendant l'envoi.
        ensure_transmittable_headers({**config.http.headers, **headers})
        pinned = PinnedHttpClient(
            policy,
            resolver,
            transport=transport,
            timeout=float(config.http.timeout_seconds),
            on_private_allowlist_used=lambda host, address: allowlist_used.add((host, address)),
        )
        discovery = asyncio.run(discover_http(config.http, headers, pinned=pinned))
    except (SecretResolutionError, HeaderNotTransmittable) as exc:
        error = str(exc)
    except OutboundPolicyError as exc:
        error = f"{exc.code} : {exc}"
    except McpClientError as exc:
        error = f"{exc.code} : {exc}"
    except UnicodeEncodeError:
        # Filet de sécurité : le message d'origine citerait un fragment de la valeur.
        error = "Requête non encodable : la configuration ou un secret contient des caractères refusés par HTTP."
    duration_ms = int((time.monotonic() - started) * 1000)

    for host, address in sorted(allowlist_used):
        record_event(
            db,
            "outbound.private_allowlist_used",
            payload={"host": host, "address": address, "purpose": "mcp_probe"},
        )

    finished_at = utcnow()
    if discovery is not None:
        # Le serveur distant est une source non fiable : sa réponse est expurgée des
        # valeurs qui lui ont été transmises avant d'être persistée et servie.
        discovery = redact_discovery(discovery, redactions)
        next_status = "succeeded"
        error_text: str | None = None
        result = redact_probe_result(
            McpProbeResult(
                protocol_version=discovery.protocol_version,
                server_info=discovery.server_info,
                tools=discovery.tools,
                duration_ms=duration_ms,
            ),
            redactions,
        ).model_dump(mode="json")
    else:
        next_status = "failed"
        # Un message d'erreur peut citer la réponse du serveur distant (erreur JSON-RPC,
        # type de contenu) : il passe par la même expurgation.
        error_text = redact_text(error or "Diagnostic interrompu sans résultat.", redactions)
        result = McpProbeResult(duration_ms=duration_ms, error=error_text).model_dump(
            mode="json"
        )
    written = _cas_probe_status(
        db,
        probe,
        expected_status="queued",
        next_status=next_status,
        values={
            McpProbeModel.result: result,
            McpProbeModel.error: error_text,
            McpProbeModel.finished_at: finished_at,
        },
    )
    if not written:
        # Invalidé ou expiré pendant l'appel réseau : l'état écrit par l'autre
        # transaction fait foi, le résultat obtenu est abandonné.
        return probe
    server.last_probe_id = probe.id
    if discovery is not None:
        _attach_discovery(db, server, revision, discovery)
        record_event(
            db,
            "mcp.probe.succeeded",
            payload={
                "probe_id": probe.id,
                "server_id": server.id,
                "server_name": server.name,
                "revision_id": revision.id,
                "transport": "http",
                "tool_count": len(discovery.tools),
            },
        )
    else:
        record_event(
            db,
            "mcp.probe.failed",
            payload={
                "probe_id": probe.id,
                "server_id": server.id,
                "server_name": server.name,
                "revision_id": revision.id,
                "transport": "http",
                "error": error_text,
            },
        )
    return probe


def request_stdio_probe(
    db: Session,
    server: McpServerModel,
    revision: McpServerRevisionModel,
    *,
    principal: str,
) -> McpProbeModel:
    """Crée une demande d'autorisation de lancement stdio (aucun lancement avant décision)."""

    config = McpServerConfig.model_validate(revision.config or {})
    stdio = config.stdio
    expires_at = utcnow() + PROBE_AUTHORIZATION_TTL
    target = " ".join([stdio.command, *stdio.args]).strip()
    authorization = McpProbeAuthorization(
        action="mcp_stdio_launch",
        target=target,
        consequences=list(STDIO_CONSEQUENCES),
        scope={"execution_location": "runner", "worker_id": server.target_worker_id},
        fingerprint=revision.fingerprint,
        expires_at=expires_at,
    )
    probe = McpProbeModel(
        server_id=server.id,
        revision_id=revision.id,
        transport="stdio",
        status="pending_approval",
        authorization=authorization.model_dump(mode="json"),
        requested_by_user_id=principal,
        expires_at=expires_at,
    )
    db.add(probe)
    db.flush()
    record_event(
        db,
        "mcp.probe.requested",
        payload={
            "probe_id": probe.id,
            "server_id": server.id,
            "server_name": server.name,
            "revision_id": revision.id,
            "transport": "stdio",
            "target": target,
        },
    )
    return probe


def _ensure_sqlite_probe_write_transaction(db: Session) -> None:
    """Prend le verrou d'écriture avant la première lecture décisionnelle SQLite.

    Une transaction déjà ouverte ne peut pas être promue en ``IMMEDIATE``. Dans
    ce cas, les CAS restent l'arbitre final ; les routes claim/report appellent ce
    helper avant toute écriture afin d'obtenir la sérialisation forte usuelle.
    """

    connection = db.connection()
    if connection.dialect.name != "sqlite":
        return
    driver = getattr(connection.connection, "driver_connection", None)
    if driver is None or getattr(driver, "in_transaction", False):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _lock_queued_probe_for_claim(
    db: Session, probe_id: str
) -> McpProbeModel | None:
    """Verrouille un candidat PostgreSQL sans attendre un autre runner.

    SQLite est déjà sérialisé par ``BEGIN IMMEDIATE``. Le CAS qui suit reste
    l'arbitre final sur tous les dialectes et protège aussi un futur appelant qui
    entrerait avec une transaction déjà ouverte.
    """

    query = db.query(McpProbeModel).filter(
        McpProbeModel.id == probe_id,
        McpProbeModel.status == "queued",
    )
    if db.connection().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    return query.populate_existing().one_or_none()


def lock_probe_for_worker_result(db: Session, probe_id: str) -> McpProbeModel | None:
    """Verrouille le probe avant décision d'accepter un résultat de runner.

    PostgreSQL attend le détenteur courant de la ligne (contrairement au claim,
    il ne faut pas ignorer le probe demandé). SQLite sérialise les écrivains par
    ``BEGIN IMMEDIATE`` avant cette lecture.
    """

    _ensure_sqlite_probe_write_transaction(db)
    query = db.query(McpProbeModel).filter(McpProbeModel.id == probe_id)
    if db.connection().dialect.name == "postgresql":
        query = query.with_for_update()
    return query.populate_existing().one_or_none()


def claim_probe_for_worker(
    db: Session, worker: WorkerModel, vault: SecretsVault | None
) -> tuple[McpProbeModel, dict[str, Any]] | None:
    """Attribue un probe autorisé à un runner et résout les secrets **pour lui seul**."""

    _ensure_sqlite_probe_write_transaction(db)
    expire_probes(db)
    candidates = (
        db.query(McpProbeModel)
        .filter(McpProbeModel.status == "queued", McpProbeModel.transport == "stdio")
        .order_by(McpProbeModel.created_at.asc(), McpProbeModel.id.asc())
        .all()
    )
    for probe in candidates:
        server = db.get(McpServerModel, probe.server_id)
        revision = db.get(McpServerRevisionModel, probe.revision_id)
        if server is None or revision is None:
            continue
        if server.target_worker_id:
            # Une cible choisie explicitement par le propriétaire est l'autorité :
            # elle reste valable même pour un runner limité à un projet.
            if server.target_worker_id != worker.id:
                continue
        elif not bool(worker.global_access):
            # Sans cible explicite, le probe appartient à la file plateforme.
            # Un runner de projet ne doit ni l'exécuter, ni provoquer la
            # résolution des secrets qui seront injectés dans son environnement.
            continue
        if server.current_revision_id != revision.id:
            continue
        locked_probe = _lock_queued_probe_for_claim(db, probe.id)
        if locked_probe is None:
            continue
        probe = locked_probe
        # Le serveur a pu être révisé pendant l'attente du verrou PostgreSQL.
        db.refresh(server)
        if server.current_revision_id != revision.id:
            continue
        # Le verrou (ou le verrou d'écriture SQLite pris en amont) peut avoir
        # attendu au-delà du TTL. L'instant lu avant l'attente n'autorise donc
        # jamais le claim : on reprend l'horloge après la lecture verrouillée,
        # avant toute résolution/divulgation de secret.
        decision_now = utcnow()
        expires_at = as_utc(probe.expires_at)
        if expires_at is not None and expires_at <= decision_now:
            expire_probe_if_due(db, probe, now=decision_now)
            continue
        lease_expires_at = decision_now + timedelta(seconds=PROBE_LEASE_SECONDS)
        transitioned = (
            db.query(McpProbeModel)
            .filter(
                McpProbeModel.id == probe.id,
                McpProbeModel.status == "queued",
            )
            .update(
                {
                    McpProbeModel.status: "claimed",
                    McpProbeModel.worker_id: worker.id,
                    McpProbeModel.claimed_at: decision_now,
                    McpProbeModel.lease_expires_at: lease_expires_at,
                },
                synchronize_session=False,
            )
        )
        if transitioned != 1:
            continue
        db.flush()
        db.refresh(probe)
        config = McpServerConfig.model_validate(revision.config or {})
        try:
            if config.stdio.env_secrets and vault is None:
                raise SecretResolutionError(
                    "Coffre de secrets non configuré : les secrets du serveur ne peuvent pas être "
                    "injectés (définissez ACP_SECRETS_KEYS)."
                )
            env_secrets = resolve_secret_values(
                db, vault, config.stdio.env_secrets, purpose="mcp_stdio_claim"
            )
        except SecretResolutionError as exc:
            probe.status = "failed"
            probe.error = str(exc)
            probe.finished_at = decision_now
            record_event(
                db,
                "mcp.probe.failed",
                payload={
                    "probe_id": probe.id,
                    "server_id": server.id,
                    "server_name": server.name,
                    "revision_id": revision.id,
                    "transport": "stdio",
                    "error": probe.error,
                },
            )
            continue
        record_event(
            db,
            "mcp.probe.claimed",
            payload={
                "probe_id": probe.id,
                "server_id": server.id,
                "server_name": server.name,
                "worker_id": worker.id,
            },
        )
        payload = {
            "id": probe.id,
            "server_id": server.id,
            "revision_id": revision.id,
            "command": config.stdio.command,
            "args": list(config.stdio.args),
            "env": {**config.stdio.env, **env_secrets},
            "cwd": config.stdio.cwd,
            "timeout_seconds": config.stdio.timeout_seconds,
            "lease_expires_at": probe.lease_expires_at.isoformat(),
        }
        return probe, payload
    return None


def complete_probe(
    db: Session,
    probe: McpProbeModel,
    result: McpProbeResult,
    *,
    vault: SecretsVault | None = None,
) -> McpProbeModel:
    """Enregistre le résultat d'un runner ; un échec ne produit jamais de découverte.

    Le contenu rapporté vient du serveur MCP sondé : il est expurgé une seconde fois ici,
    côté serveur, avec les valeurs injectées au runner. Le contrôle ne peut pas n'exister
    que dans le worker, sinon un runner compromis ferait écrire un secret en base.
    """

    server = db.get(McpServerModel, probe.server_id)
    revision = db.get(McpServerRevisionModel, probe.revision_id)
    try:
        redactions = stdio_redaction_values(db, vault, revision)
    except SecretResolutionError as exc:
        error = str(exc)
        finished_at = utcnow()
        stored_result = McpProbeResult(
            duration_ms=result.duration_ms, error=error
        ).model_dump(mode="json")
        if not _cas_probe_status(
            db,
            probe,
            expected_status="claimed",
            next_status="failed",
            values={
                McpProbeModel.error: error,
                McpProbeModel.finished_at: finished_at,
                McpProbeModel.result: stored_result,
            },
        ):
            raise ProbeTransitionConflict(
                f"Le diagnostic n'est plus réclamé (état actuel : {probe.status})."
            )
        if server is not None:
            server.last_probe_id = probe.id
        record_event(
            db,
            "mcp.probe.failed",
            payload={
                "probe_id": probe.id,
                "server_id": probe.server_id,
                "server_name": server.name if server is not None else "",
                "revision_id": probe.revision_id,
                "transport": "stdio",
                "error": error,
            },
        )
        return probe
    result = redact_probe_result(result, redactions)
    stored_result = result.model_dump(mode="json")
    finished_at = utcnow()
    failed = bool(result.error) or not result.protocol_version
    error = (
        result.error or "Le runner n'a pas renvoyé de version de protocole."
        if failed
        else None
    )
    terminal_status = "failed" if failed else "succeeded"
    if not _cas_probe_status(
        db,
        probe,
        expected_status="claimed",
        next_status=terminal_status,
        values={
            McpProbeModel.error: error,
            McpProbeModel.finished_at: finished_at,
            McpProbeModel.result: stored_result,
        },
    ):
        raise ProbeTransitionConflict(
            f"Le diagnostic n'est plus réclamé (état actuel : {probe.status})."
        )
    if server is not None:
        server.last_probe_id = probe.id
    if failed:
        record_event(
            db,
            "mcp.probe.failed",
            payload={
                "probe_id": probe.id,
                "server_id": probe.server_id,
                "server_name": server.name if server is not None else "",
                "revision_id": probe.revision_id,
                "transport": "stdio",
                "error": error,
            },
        )
        return probe
    discovery = McpDiscovery(
        protocol_version=result.protocol_version,
        server_info=result.server_info or {},
        tools=list(result.tools),
    )
    if server is not None and revision is not None:
        _attach_discovery(db, server, revision, discovery)
    record_event(
        db,
        "mcp.probe.succeeded",
        payload={
            "probe_id": probe.id,
            "server_id": probe.server_id,
            "server_name": server.name if server is not None else "",
            "revision_id": probe.revision_id,
            "transport": "stdio",
            "tool_count": len(discovery.tools),
        },
    )
    return probe


# --- cycle de vie du serveur ------------------------------------------------------------------


def activate_server(db: Session, server: McpServerModel, *, principal: str) -> list[str]:
    """Rend la révision courante effective pour les projets ; retourne les notes d'application."""

    revision = current_revision(db, server)
    if revision is None or not discovery_is_current(revision):
        raise ConfigRefused(
            "discovery_missing",
            "Aucune découverte courante pour la révision : lancez un diagnostic avant d'activer.",
        )
    if server.transport == "stdio" and not has_successful_probe(
        db, server.id, revision.fingerprint
    ):
        raise ConfigRefused(
            "probe_missing",
            "Aucun diagnostic stdio réussi pour cette empreinte : faites autoriser et exécuter un "
            "diagnostic sur le runner désigné avant d'activer.",
        )
    tools = discovered_tool_names(revision)
    notes: list[str] = []
    for binding in bindings_of(db, server, live_only=True):
        foreign = foreign_project_secrets(db, revision.config or {}, binding.project_id)
        if foreign:
            # La règle « un secret de projet ne sert qu'à son projet » vaut aussi ici : sans ce
            # contrôle, une révision ferait glisser le secret d'un autre projet dans ce binding.
            binding.enabled = 0
            binding.updated_at = utcnow()
            notes.append(
                f"Projet {binding.project_id} : binding désactivé et laissé sur sa révision "
                f"précédente ; la révision {revision.number} référence un secret appartenant à un "
                f"autre projet ({', '.join(foreign)})."
            )
            continue
        kept = [tool for tool in (binding.allowed_tools or []) if tool in tools]
        removed = [tool for tool in (binding.allowed_tools or []) if tool not in tools]
        binding.revision_id = revision.id
        binding.allowed_tools = kept
        binding.updated_at = utcnow()
        if removed:
            notes.append(
                f"Projet {binding.project_id} : outils retirés du binding car absents de la "
                f"découverte courante : {', '.join(removed)}."
            )
        if not kept:
            binding.enabled = 0
            notes.append(
                f"Projet {binding.project_id} : binding désactivé, plus aucun outil autorisé "
                "n'est disponible."
            )
    server.status = "active"
    server.updated_at = utcnow()
    record_event(
        db,
        "mcp.server.activated",
        payload={
            "server_id": server.id,
            "server_name": server.name,
            "revision_id": revision.id,
            "revision_number": revision.number,
            "apply_notes": notes,
        },
    )
    return notes


def disable_server(db: Session, server: McpServerModel) -> None:
    server.status = "disabled"
    server.updated_at = utcnow()
    record_event(
        db,
        "mcp.server.disabled",
        payload={"server_id": server.id, "server_name": server.name},
    )


def revoke_server(db: Session, server: McpServerModel, *, reason: str, principal: str) -> None:
    """Révocation irréversible : bindings coupés, probes non terminaux annulés, historique gardé."""

    now = utcnow()
    server.status = "revoked"
    server.revoked_at = now
    server.revoked_reason = reason
    server.updated_at = now
    for binding in bindings_of(db, server, live_only=True):
        binding.revoked_at = now
        binding.enabled = 0
        binding.updated_at = now
    for probe in probes_of(db, server):
        if probe.status in ACTIVE_PROBE_STATUSES:
            probe.status = "cancelled"
            probe.error = "Serveur révoqué : diagnostic annulé."
            probe.finished_at = now
    record_event(
        db,
        "mcp.server.revoked",
        payload={
            "server_id": server.id,
            "server_name": server.name,
            "reason": reason,
            "revoked_by_user_id": principal,
        },
    )


def rollback_server(
    db: Session, server: McpServerModel, target: McpServerRevisionModel, *, principal: str, note: str
) -> McpServerRevisionModel:
    """Nouvelle révision reprenant la configuration (et la découverte) d'une révision passée."""

    config = McpServerConfig.model_validate(target.config or {})
    revision = create_revision(
        db,
        server,
        config,
        principal=principal,
        note=note,
        risk_flags=[McpRiskFlag.model_validate(flag) for flag in target.risk_flags or []],
        discovery_source=target,
    )
    record_event(
        db,
        "mcp.server.rolled_back",
        payload={
            "server_id": server.id,
            "server_name": server.name,
            "revision_id": revision.id,
            "revision_number": revision.number,
            "restored_from": target.number,
        },
    )
    return revision


# --- exports --------------------------------------------------------------------------------------


def placeholder_for(secret: SecretModel) -> str:
    return f"{SECRET_PLACEHOLDER_PREFIX}{secret.name}"


def _secret_placeholders(
    db: Session, refs: Mapping[str, Any]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Retourne (clé -> ``${ACP_SECRET_X}``, noms de variables, avertissements)."""

    mapping: dict[str, str] = {}
    variables: list[str] = []
    warnings: list[str] = []
    for key, ref in refs.items():
        secret_id = ref.secret_id if hasattr(ref, "secret_id") else (ref or {}).get("secret_id")
        secret = db.get(SecretModel, secret_id) if secret_id else None
        if secret is None:
            warnings.append(
                f"Secret introuvable pour « {key} » : la référence a été omise de l'export."
            )
            continue
        variable = placeholder_for(secret)
        mapping[key] = "${" + variable + "}"
        variables.append(variable)
    return mapping, variables, warnings


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"valeur TOML non supportée : {type(value).__name__}")


def _toml_document(tables: list[tuple[str, dict[str, Any]]]) -> str:
    lines: list[str] = []
    for name, table in tables:
        lines.append(f"[{name}]")
        for key, value in table.items():
            if isinstance(value, dict):
                continue
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
        for key, value in table.items():
            if not isinstance(value, dict) or not value:
                continue
            lines.append(f"[{name}.{key}]")
            for sub_key, sub_value in value.items():
                lines.append(f"{_toml_string(sub_key)} = {_toml_value(sub_value)}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


_HERMES_NOTES = [
    "Définir les variables `ACP_SECRET_*` dans `~/.hermes/.env` du service Hermes (jamais dans `config.yaml`).",
    "Hermes recharge `config.yaml` sous ~30 s, ou immédiatement via la commande `/reload-mcp`.",
    "Une session déjà ouverte conserve ses outils jusqu'au rechargement.",
]
_CLAUDE_NOTES = [
    "Définir les variables `ACP_SECRET_*` dans l'environnement du client avant de le lancer : le fichier ne contient que des placeholders.",
    "Relancer le client pour qu'il relise la configuration des serveurs MCP.",
]
_CODEX_NOTES = [
    "Définir les variables `ACP_SECRET_*` dans l'environnement de Codex : seules les noms de variables sont exportés.",
    "Relancer Codex pour qu'il relise `config.toml`.",
]
_HERMES_PARTIAL = [
    "Hermes n'a pas de portée projet native : la restriction par projet repose sur `tools.include` et sur la plateforme.",
    "Le statut, les révisions et les autorisations de lancement restent gérés par la plateforme : le fichier exporté ne les porte pas.",
]
_CLAUDE_PARTIAL = [
    "Claude Code n'exprime pas de sélection d'outils par serveur : tous les outils découverts seront exposés au client.",
    "La portée projet et les révisions restent gérées par la plateforme.",
]
_CODEX_PARTIAL = [
    "Codex n'accepte qu'un secret d'en-tête par serveur via `bearer_token_env_var` ; les autres en-têtes secrets passent par `env_http_headers`.",
    "La portée projet et les révisions restent gérées par la plateforme.",
]


def _export_rows(
    db: Session, project_id: str | None
) -> list[tuple[McpServerModel, McpServerRevisionModel, list[str] | None]]:
    """Serveurs exportables : actifs, et pour un projet, ceux réellement liés à ce projet."""

    rows: list[tuple[McpServerModel, McpServerRevisionModel, list[str] | None]] = []
    servers = (
        db.query(McpServerModel)
        .filter(McpServerModel.status == "active")
        .order_by(McpServerModel.name.asc())
        .all()
    )
    for server in servers:
        if project_id is None:
            revision = current_revision(db, server)
            if revision is None:
                continue
            rows.append((server, revision, None))
            continue
        binding = (
            db.query(McpBindingModel)
            .filter_by(server_id=server.id, project_id=project_id)
            .filter(McpBindingModel.revoked_at.is_(None), McpBindingModel.enabled == 1)
            .first()
        )
        if binding is None:
            continue
        revision = db.get(McpServerRevisionModel, binding.revision_id)
        if revision is None:
            continue
        rows.append((server, revision, list(binding.allowed_tools or [])))
    return rows


def export_config(db: Session, export_format: str, project_id: str | None = None) -> McpExport:
    """Exporte les serveurs actifs au format Hermes, Claude ou Codex, sans aucune valeur de secret."""

    rows = _export_rows(db, project_id)
    placeholders: list[str] = []
    warnings: list[str] = []
    hermes: dict[str, Any] = {}
    claude: dict[str, Any] = {}
    codex_tables: list[tuple[str, dict[str, Any]]] = []

    for server, revision, allowed_tools in rows:
        config = McpServerConfig.model_validate(revision.config or {})
        if config.transport == "http":
            secret_headers, variables, issues = _secret_placeholders(db, config.http.header_secrets)
            placeholders.extend(variables)
            warnings.extend(issues)
            headers = {**config.http.headers, **secret_headers}
            hermes_entry: dict[str, Any] = {"url": config.http.url}
            if headers:
                hermes_entry["headers"] = headers
            if allowed_tools is not None:
                hermes_entry["tools"] = {"include": list(allowed_tools)}
            hermes_entry["timeout"] = config.http.timeout_seconds
            hermes[server.name] = hermes_entry

            claude_entry: dict[str, Any] = {"type": "http", "url": config.http.url}
            if headers:
                claude_entry["headers"] = headers
            claude[server.name] = claude_entry

            codex_entry: dict[str, Any] = {"url": config.http.url}
            env_http_headers: dict[str, str] = {}
            for header, ref in config.http.header_secrets.items():
                variable = secret_headers.get(header, "")[2:-1]
                if not variable:
                    continue
                if header.lower() == "authorization":
                    codex_entry["bearer_token_env_var"] = variable
                else:
                    env_http_headers[header] = variable
            if allowed_tools is not None:
                codex_entry["enabled_tools"] = list(allowed_tools)
            codex_entry["startup_timeout_sec"] = config.http.timeout_seconds
            if config.http.headers:
                codex_entry["http_headers"] = dict(config.http.headers)
            if env_http_headers:
                codex_entry["env_http_headers"] = env_http_headers
            codex_tables.append((f"mcp_servers.{server.name}", codex_entry))
        else:
            secret_env, variables, issues = _secret_placeholders(db, config.stdio.env_secrets)
            placeholders.extend(variables)
            warnings.extend(issues)
            env = {**config.stdio.env, **secret_env}
            hermes_entry = {"command": config.stdio.command}
            if config.stdio.args:
                hermes_entry["args"] = list(config.stdio.args)
            if env:
                hermes_entry["env"] = env
            if config.stdio.cwd:
                hermes_entry["cwd"] = config.stdio.cwd
            if allowed_tools is not None:
                hermes_entry["tools"] = {"include": list(allowed_tools)}
            hermes_entry["timeout"] = config.stdio.timeout_seconds
            hermes[server.name] = hermes_entry

            claude_entry = {"type": "stdio", "command": config.stdio.command}
            if config.stdio.args:
                claude_entry["args"] = list(config.stdio.args)
            if env:
                claude_entry["env"] = env
            claude[server.name] = claude_entry

            codex_entry = {"command": config.stdio.command}
            if config.stdio.args:
                codex_entry["args"] = list(config.stdio.args)
            if config.stdio.cwd:
                codex_entry["cwd"] = config.stdio.cwd
            if allowed_tools is not None:
                codex_entry["enabled_tools"] = list(allowed_tools)
            codex_entry["startup_timeout_sec"] = config.stdio.timeout_seconds
            if config.stdio.env:
                codex_entry["env"] = dict(config.stdio.env)
            if variables:
                codex_entry["env_vars"] = list(variables)
            codex_tables.append((f"mcp_servers.{server.name}", codex_entry))

    if export_format == "hermes":
        content = yaml.safe_dump(
            {"mcp_servers": hermes}, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
        notes, partial = list(_HERMES_NOTES), list(_HERMES_PARTIAL)
    elif export_format == "claude":
        content = json.dumps({"mcpServers": claude}, indent=2, ensure_ascii=False) + "\n"
        notes, partial = list(_CLAUDE_NOTES), list(_CLAUDE_PARTIAL)
    else:
        content = (
            _toml_document(codex_tables)
            if codex_tables
            else "# Aucun serveur MCP actif à exporter.\n"
        )
        notes, partial = list(_CODEX_NOTES), list(_CODEX_PARTIAL)
    if project_id is not None:
        partial.append(
            "Export restreint au projet : les serveurs non liés à ce projet sont absents du fichier."
        )
    return McpExport(
        format=export_format,
        project_id=project_id,
        content=content,
        placeholders=sorted(set(placeholders)),
        partial_compatibility=partial,
        apply_notes=notes + warnings,
    )
