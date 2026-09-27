"""Relevés des quotas réels d'abonnement sur le poste (Codex CLI, Claude Code) : forme et contrat.

Deux sources officielles, jamais d'estimation :

- **Codex CLI** connecté par compte ChatGPT : ``account/rateLimits/read`` de ``codex app-server``, lu par la sonde
  Codex (:mod:`sondes_codex`) ; :func:`codex_reports_from_rate_limits` en tire un relevé par compteur
  (``rateLimitsByLimitId``, sinon la vue ``rateLimits``). :func:`codex_environment` construit l'environnement minimal
  de la CLI : aucune clé d'API (``OPENAI_API_KEY``, ``CODEX_API_KEY``, ``CODEX_ACCESS_TOKEN``), profil dédié imposé.
- **Claude Code** : aucune API ne donne les limites d'un compte individuel. :func:`probe_claude_snapshot` lit le
  fichier écrit par la ligne d'état de Claude Code (``claude_statusline``), qui recopie ``rate_limits.five_hour`` et
  ``rate_limits.seven_day``.

Chaque relevé est valide au sens de ``SubscriptionQuotaReport`` : un échec devient un état explicite
(``not_signed_in``, ``cli_missing``, ``unavailable``…) accompagné d'une explication en français, jamais une exception
ni une valeur inventée. Un échec porte l'identifiant réservé ``probe`` ; un seul compteur hors contrat fait échouer
toute la lecture plutôt que d'en transmettre une partie.

Étape P5 : l'accord ``ACP_WORKER_SUBSCRIPTION_QUOTAS`` et les réglages ``ACP_WORKER_*`` ont disparu ; l'accord est
désormais ``[sondes] codex`` et ``[sondes] claude`` de ``poste.toml``, et les relevés partent vers Hermes dans
l'inventaire du poste (``compteurs`` de chaque relevé).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Mapping
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

from .claude_statusline import SNAPSHOT_SOURCE as CLAUDE_SNAPSHOT_SOURCE
from .claude_statusline import SNAPSHOT_WINDOW_MINUTES as CLAUDE_WINDOW_MINUTES

MAX_SNAPSHOT_BYTES = 64 * 1024
MAX_CODEX_COUNTERS = QUOTA_BATCH_MAX - 1
"""Un relevé porte au plus 16 compteurs : une place reste réservée à un échec de lecture."""

API_KEY_VARIABLES = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
# Seules ces variables du poste sont recopiées : de quoi lancer le CLI, trouver le profil utilisateur, et joindre
# le réseau à travers un éventuel mandataire. Jetons du poste, clés d'API et configuration interne restent
# invisibles de Codex.
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

CODEX_API_KEY_ACCOUNT = (
    "Profil Codex connecté par clé d'API : aucun quota d'abonnement ChatGPT à relever. "
    "Connectez un compte ChatGPT avec « acp-poste connexion codex »."
)
CODEX_MALFORMED = "Réponse de l'app-server Codex mal formée : quotas non relevés."
# Publié dans l'inventaire (détail d'un compteur) : aucun chemin de lecteur, que la garde « aucun identifiant »
# refuserait. La commande exacte (interpréteur -I et ligne_etat.py installé avec le poste) est dans le README ;
# « python -m acp_poste.claude_statusline » échoue dans la disposition installée, sans venv (relecture de P5).
CLAUDE_MISSING = (
    "Aucun relevé de la ligne d'état Claude Code : fichier absent. Réglez la ligne "
    "d'état de vos sessions Claude Code sur ligne_etat.py, installé avec le poste et lancé "
    "par l'interpréteur du poste en mode -I (apps/poste/README.md, § Ligne d'état Claude "
    "Code), puis utilisez Claude Code une fois."
)
CLAUDE_UNREADABLE = "Relevé de la ligne d'état Claude Code illisible : quotas non relevés."
CLAUDE_MALFORMED = "Relevé de la ligne d'état Claude Code mal formé : quotas non relevés."
CLAUDE_TOO_LARGE = "Relevé de la ligne d'état Claude Code trop volumineux : fichier ignoré."


class QuotaMalForme(Exception):
    """Réponse ou fichier hors de la forme attendue."""


_Malformed = QuotaMalForme


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
# Environnement de Codex CLI
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

def parse_codex_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.search(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

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

# --------------------------------------------------------------------------
# Ligne d'état Claude Code
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

async def probe_claude_snapshot(path: Path) -> SubscriptionQuotaReport:
    """Lit le fichier de la ligne d'état Claude Code ``path`` ; ne lève jamais (étape P5 : chemin de poste.toml)."""

    try:
        state, data = await asyncio.to_thread(_read_snapshot_bytes, path)
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
