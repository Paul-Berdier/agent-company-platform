"""Contrats des quotas réels d'abonnement : Codex CLI (compte ChatGPT) et Claude Code.

Un quota d'abonnement n'est **jamais estimé**. Chaque valeur transportée ici vient
d'une source officielle relevée par un worker sur le poste du titulaire :

- Codex : ``codex app-server`` (JSON-RPC), réponse de ``account/rateLimits/read`` ;
- Claude Code : le fichier écrit par la ligne d'état, qui recopie
  ``rate_limits.five_hour`` et ``rate_limits.seven_day`` reçus de Claude Code.

Une valeur que la source ne donne pas reste ``None`` et s'affiche « Inconnu ».
L'usage d'un abonnement est personnel à son titulaire : l'API ne montre ces relevés
qu'au propriétaire de la plateforme.

Les refus sont rédigés en français, y compris pour un champ inconnu, manquant ou
mal typé : un 422 de l'API se lit alors sans traduction. Les contrats sont
stricts (champs supplémentaires interdits, booléen jamais pris pour un nombre).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .limits import DatabaseModel

SubscriptionProvider = Literal["codex", "claude_code"]
QuotaSource = Literal["codex_app_server", "claude_code_statusline"]
ProbeStatus = Literal["ok", "not_signed_in", "cli_missing", "cli_too_old", "unavailable"]

SUBSCRIPTION_PROVIDERS: tuple[str, ...] = get_args(SubscriptionProvider)
QUOTA_SOURCES: tuple[str, ...] = get_args(QuotaSource)
PROBE_STATUSES: tuple[str, ...] = get_args(ProbeStatus)
QUOTA_SOURCE_BY_PROVIDER: dict[str, str] = {
    "codex": "codex_app_server",
    "claude_code": "claude_code_statusline",
}

QUOTA_WINDOW_KEY_MAX = 32
QUOTA_WINDOW_MINUTES_MAX = 527_040
"""366 jours : aucune fenêtre d'abonnement connue n'est plus longue."""
QUOTA_PLAN_MAX = 40
QUOTA_LIMIT_ID_MAX = 64
QUOTA_WINDOWS_MAX = 8
QUOTA_CREDITS_BALANCE_MAX = 32
QUOTA_REACHED_TYPE_MAX = 64
QUOTA_DETAIL_MAX = 300
QUOTA_BATCH_MAX = 16
QUOTA_COUNTER_MAX = 1_000
QUOTA_FUTURE_TOLERANCE = timedelta(minutes=5)
"""Écart d'horloge toléré entre le poste du worker et l'API."""
DEFAULT_LIMIT_ID = "default"
"""Compteur unique d'une source qui n'en nomme aucun (ligne d'état Claude Code, vue
historique ``rateLimits`` de Codex)."""
PROBE_LIMIT_ID = "probe"
"""Identifiant réservé à une lecture en échec, jamais à un compteur de la source.

Un échec n'a donc jamais l'identité d'un compteur réussi : il ne peut pas remplacer
le dernier relevé réussi, qui reste affiché avec sa date."""
DEFAULT_QUOTA_STALE_SECONDS = 1800
QUOTA_STALE_SECONDS_MIN = 60
QUOTA_STALE_SECONDS_MAX = 604_800

_WINDOW_KEY = re.compile(r"[a-z0-9][a-z0-9_]{0,31}")
_LIMIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


# --- Vérifications élémentaires, messages en français ------------------------------


def _text(value: Any, *, label: str, max_chars: int, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        raise ValueError(f"« {label} » doit être une chaîne de caractères")
    if "\x00" in value:
        raise ValueError(f"« {label} » : le caractère NUL (\\x00) est interdit")
    if not value.strip():
        raise ValueError(f"« {label} » ne peut pas être vide")
    if len(value) > max_chars:
        raise ValueError(f"« {label} » : au maximum {max_chars} caractères")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ValueError(f"« {label} » : identifiant au format invalide")
    return value


def _optional_text(value: Any, *, label: str, max_chars: int) -> str | None:
    if value is None:
        return None
    return _text(value, label=label, max_chars=max_chars)


def _choice(value: Any, *, label: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"« {label} » : valeurs admises : {', '.join(choices)}")
    return value


def _flag(value: Any, *, label: str, nullable: bool = False) -> bool | None:
    if value is None and nullable:
        return None
    if type(value) is not bool:
        raise ValueError(f"« {label} » doit être un booléen (true ou false)")
    return value


def _count(value: Any, *, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"« {label} » doit être un entier compris entre {minimum} et {maximum}")
    return value


def _instant(value: Any, *, label: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"« {label} » : horodatage ISO 8601 illisible") from None
    if not isinstance(value, datetime):
        raise ValueError(f"« {label} » doit être un horodatage ISO 8601")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"« {label} » doit porter son fuseau (UTC attendu)")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise ValueError(f"« {label} » : horodatage hors de la plage UTC lisible") from None


def _remaining(used: int | float | None) -> int | float | None:
    """Part restante déduite de la seule part utilisée relevée, sans autre calcul."""

    if used is None:
        return None
    return round(100 - used, 4)


# --- Socle -----------------------------------------------------------------------


class _QuotaContract(DatabaseModel):
    """Frontière JSON stricte : tout écart est refusé avec un message français."""

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def _declared_fields_only(cls, data: Any) -> Any:
        if isinstance(data, BaseModel):
            data = data.model_dump()
        if not isinstance(data, Mapping):
            raise ValueError("un objet JSON est attendu")
        unknown = sorted(str(key) for key in data if key not in cls.model_fields)
        if unknown:
            raise ValueError(
                "champ inconnu refusé : " + ", ".join(f"« {name} »" for name in unknown)
            )
        missing = [
            name
            for name, info in cls.model_fields.items()
            if info.is_required() and name not in data
        ]
        if missing:
            raise ValueError(
                "champ obligatoire absent : " + ", ".join(f"« {name} »" for name in missing)
            )
        return data


# --- Fenêtres et crédits ---------------------------------------------------------------


class QuotaWindow(_QuotaContract):
    """Une fenêtre de limite telle que la source la donne.

    ``key`` reprend le nom de la source (``primary``/``secondary`` pour Codex,
    ``five_hour``/``seven_day`` pour Claude Code) ; la durée est portée par
    ``window_minutes``. Chaque valeur inconnue de la source vaut ``None``.
    """

    key: str
    used_percent: int | float | None
    window_minutes: int | None
    resets_at: datetime | None

    @field_validator("key", mode="before")
    @classmethod
    def _key(cls, value: Any) -> str:
        return _text(value, label="key", max_chars=QUOTA_WINDOW_KEY_MAX, pattern=_WINDOW_KEY)

    @field_validator("used_percent", mode="before")
    @classmethod
    def _used_percent(cls, value: Any) -> int | float | None:
        if value is None:
            return None
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("« used_percent » doit être un nombre fini compris entre 0 et 100")
        return value

    @field_validator("window_minutes", mode="before")
    @classmethod
    def _window_minutes(cls, value: Any) -> int | None:
        if value is None:
            return None
        return _count(value, label="window_minutes", minimum=1, maximum=QUOTA_WINDOW_MINUTES_MAX)

    @field_validator("resets_at", mode="before")
    @classmethod
    def _resets_at(cls, value: Any) -> datetime | None:
        return None if value is None else _instant(value, label="resets_at")


class QuotaWindowView(QuotaWindow):
    """Fenêtre servie au propriétaire : ``remaining_percent`` = 100 − ``used_percent``."""

    remaining_percent: int | float | None

    @field_validator("remaining_percent", mode="before")
    @classmethod
    def _remaining_percent(cls, value: Any) -> int | float | None:
        if value is None:
            return None
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("« remaining_percent » doit être un nombre fini compris entre 0 et 100")
        return value

    @model_validator(mode="after")
    def _remaining_matches_used(self) -> QuotaWindowView:
        if self.remaining_percent != _remaining(self.used_percent):
            raise ValueError(
                "« remaining_percent » doit valoir 100 − « used_percent », "
                "ou être inconnu quand la part utilisée l'est"
            )
        return self

    @classmethod
    def from_window(cls, window: QuotaWindow) -> QuotaWindowView:
        return cls(
            key=window.key,
            used_percent=window.used_percent,
            window_minutes=window.window_minutes,
            resets_at=window.resets_at,
            remaining_percent=_remaining(window.used_percent),
        )


class QuotaCredits(_QuotaContract):
    """Crédits rapportés par l'app-server Codex ; ``balance`` reste le texte de la source."""

    has_credits: bool
    unlimited: bool
    balance: str | None

    @field_validator("has_credits", "unlimited", mode="before")
    @classmethod
    def _flags(cls, value: Any, info) -> bool:
        return _flag(value, label=info.field_name)

    @field_validator("balance", mode="before")
    @classmethod
    def _balance(cls, value: Any) -> str | None:
        return _optional_text(value, label="balance", max_chars=QUOTA_CREDITS_BALANCE_MAX)


# --- Relevé ---------------------------------------------------------------------------


class _QuotaReportFields(_QuotaContract):
    """Champs et cohérence communs au relevé transmis et à la vue du propriétaire."""

    provider: SubscriptionProvider
    status: ProbeStatus
    source: QuotaSource
    plan: str | None = None
    limit_id: str = DEFAULT_LIMIT_ID
    windows: list[QuotaWindow] = []
    credits: QuotaCredits | None = None
    limit_reached: bool | None = None
    reached_type: str | None = None
    observed_at: datetime
    detail: str | None = None

    @field_validator("provider", mode="before")
    @classmethod
    def _provider(cls, value: Any) -> str:
        return _choice(value, label="provider", choices=SUBSCRIPTION_PROVIDERS)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> str:
        return _choice(value, label="status", choices=PROBE_STATUSES)

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, value: Any) -> str:
        return _choice(value, label="source", choices=QUOTA_SOURCES)

    @field_validator("plan", mode="before")
    @classmethod
    def _plan(cls, value: Any) -> str | None:
        return _optional_text(value, label="plan", max_chars=QUOTA_PLAN_MAX)

    @field_validator("limit_id", mode="before")
    @classmethod
    def _limit_id(cls, value: Any) -> str:
        return _text(value, label="limit_id", max_chars=QUOTA_LIMIT_ID_MAX, pattern=_LIMIT_ID)

    @field_validator("windows", mode="before")
    @classmethod
    def _windows(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("« windows » doit être une liste")
        if len(value) > QUOTA_WINDOWS_MAX:
            raise ValueError(f"« windows » : au maximum {QUOTA_WINDOWS_MAX} fenêtres")
        return value

    @field_validator("limit_reached", mode="before")
    @classmethod
    def _limit_reached(cls, value: Any) -> bool | None:
        return _flag(value, label="limit_reached", nullable=True)

    @field_validator("reached_type", mode="before")
    @classmethod
    def _reached_type(cls, value: Any) -> str | None:
        return _optional_text(value, label="reached_type", max_chars=QUOTA_REACHED_TYPE_MAX)

    @field_validator("observed_at", mode="before")
    @classmethod
    def _observed_at(cls, value: Any) -> datetime:
        return _instant(value, label="observed_at")

    @field_validator("detail", mode="before")
    @classmethod
    def _detail(cls, value: Any) -> str | None:
        return _optional_text(value, label="detail", max_chars=QUOTA_DETAIL_MAX)

    @model_validator(mode="after")
    def _coherent(self):
        expected_source = QUOTA_SOURCE_BY_PROVIDER[self.provider]
        if self.source != expected_source:
            raise ValueError(
                f"« source » : le fournisseur {self.provider} se relève uniquement "
                f"par {expected_source}"
            )
        keys = [window.key for window in self.windows]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        if duplicated:
            raise ValueError("« windows » : fenêtre en double : " + ", ".join(duplicated))
        if self.status != "ok":
            if self.windows or self.credits is not None or self.limit_reached is not None or (
                self.reached_type is not None
            ):
                raise ValueError(
                    f"un relevé à l'état {self.status} ne porte aucune mesure "
                    "(ni fenêtre, ni crédit, ni limite atteinte)"
                )
            if self.detail is None:
                raise ValueError(
                    f"« detail » : un relevé à l'état {self.status} doit expliquer pourquoi"
                )
        if self.reached_type is not None and self.limit_reached is not True:
            raise ValueError("« reached_type » exige « limit_reached » à true")
        return self


class SubscriptionQuotaReport(_QuotaReportFields):
    """Relevé transmis par un worker pour un compteur d'un fournisseur.

    ``observed_at`` est l'instant où la source a répondu, jamais celui de l'envoi.
    Un instant plus de cinq minutes dans le futur (horloge du poste déréglée) est
    refusé : il gagnerait à tort toute comparaison de fraîcheur.

    Une lecture en échec (état autre que ``ok``) porte toujours ``limit_id`` =
    ``probe``, valeur par défaut quand le champ est omis ; un relevé réussi ne la porte
    jamais. Un échec ne prend ainsi jamais la place d'un compteur relevé.
    """

    @model_validator(mode="before")
    @classmethod
    def _failure_identity_by_default(cls, data: Any) -> Any:
        if (
            isinstance(data, Mapping)
            and "limit_id" not in data
            and data.get("status") in PROBE_STATUSES
            and data.get("status") != "ok"
        ):
            return {**data, "limit_id": PROBE_LIMIT_ID}
        return data

    @model_validator(mode="after")
    def _failure_identity(self) -> SubscriptionQuotaReport:
        if self.status == "ok" and self.limit_id == PROBE_LIMIT_ID:
            raise ValueError(
                f"« limit_id » : « {PROBE_LIMIT_ID} » est réservé aux lectures en échec, "
                "jamais à un compteur relevé"
            )
        if self.status != "ok" and self.limit_id != PROBE_LIMIT_ID:
            raise ValueError(
                f"« limit_id » : une lecture en échec ({self.status}) porte l'identifiant "
                f"réservé « {PROBE_LIMIT_ID} », jamais celui d'un compteur"
            )
        return self

    @field_validator("observed_at", mode="after")
    @classmethod
    def _not_in_the_future(cls, value: datetime) -> datetime:
        if value > datetime.now(UTC) + QUOTA_FUTURE_TOLERANCE:
            raise ValueError(
                "« observed_at » est plus de cinq minutes dans le futur : "
                "vérifiez l'horloge du poste du worker"
            )
        return value


class SubscriptionQuotaBatch(_QuotaContract):
    """Lot envoyé par un worker : un relevé par couple (fournisseur, compteur).

    Pour un fournisseur, une lecture est soit réussie (ses compteurs, tous ``ok``),
    soit en échec (un seul relevé ``probe``) : un lot ne mêle jamais les deux.
    """

    reports: list[SubscriptionQuotaReport]

    @field_validator("reports", mode="before")
    @classmethod
    def _reports(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("« reports » doit être une liste")
        if not value:
            raise ValueError("« reports » doit contenir au moins un relevé")
        if len(value) > QUOTA_BATCH_MAX:
            raise ValueError(f"« reports » : au maximum {QUOTA_BATCH_MAX} relevés par lot")
        return value

    @model_validator(mode="after")
    def _distinct(self) -> SubscriptionQuotaBatch:
        seen: set[tuple[str, str]] = set()
        for report in self.reports:
            identity = (report.provider, report.limit_id)
            if identity in seen:
                raise ValueError(
                    f"« reports » : relevé en double pour {report.provider}/{report.limit_id}"
                )
            seen.add(identity)
        outcomes: dict[str, set[bool]] = {}
        for report in self.reports:
            outcomes.setdefault(report.provider, set()).add(report.status == "ok")
        mixed = sorted(provider for provider, kinds in outcomes.items() if len(kinds) > 1)
        if mixed:
            raise ValueError(
                "« reports » : "
                + ", ".join(mixed)
                + " mêle des compteurs relevés et un échec de lecture dans le même lot"
            )
        return self


class SubscriptionQuotaIngestResult(_QuotaContract):
    """Bilan d'un lot : relevés enregistrés, relevés plus anciens ignorés, compteurs retirés."""

    stored: int
    ignored_older: int
    removed: int

    @field_validator("stored", "ignored_older", "removed", mode="before")
    @classmethod
    def _counts(cls, value: Any, info) -> int:
        return _count(value, label=info.field_name, minimum=0, maximum=QUOTA_COUNTER_MAX)


# --- Vue du propriétaire ---------------------------------------------------------------


class SubscriptionQuotaView(_QuotaReportFields):
    """Dernier relevé connu d'un compteur, tel que le propriétaire le lit.

    ``stale`` est vrai quand ``observed_at`` est plus ancien que le seuil de
    fraîcheur de l'API : la valeur est alors affichée « Périmé », jamais comme
    actuelle. ``received_at`` est l'instant de la dernière réception par l'API.
    """

    windows: list[QuotaWindowView] = []
    worker_id: str
    worker_name: str
    received_at: datetime
    stale: bool

    @field_validator("worker_id", mode="before")
    @classmethod
    def _worker_id(cls, value: Any) -> str:
        return _text(value, label="worker_id", max_chars=36)

    @field_validator("worker_name", mode="before")
    @classmethod
    def _worker_name(cls, value: Any) -> str:
        return _text(value, label="worker_name", max_chars=200)

    @field_validator("received_at", mode="before")
    @classmethod
    def _received_at(cls, value: Any) -> datetime:
        return _instant(value, label="received_at")

    @field_validator("stale", mode="before")
    @classmethod
    def _stale(cls, value: Any) -> bool:
        return _flag(value, label="stale")

    @classmethod
    def from_report(
        cls,
        report: _QuotaReportFields,
        *,
        worker_id: str,
        worker_name: str,
        received_at: datetime,
        stale: bool,
    ) -> SubscriptionQuotaView:
        return cls(
            provider=report.provider,
            status=report.status,
            source=report.source,
            plan=report.plan,
            limit_id=report.limit_id,
            windows=[QuotaWindowView.from_window(window) for window in report.windows],
            credits=report.credits,
            limit_reached=report.limit_reached,
            reached_type=report.reached_type,
            observed_at=report.observed_at,
            detail=report.detail,
            worker_id=worker_id,
            worker_name=worker_name,
            received_at=received_at,
            stale=stale,
        )


class SubscriptionQuotaList(_QuotaContract):
    """Réponse de ``GET /subscription-quotas`` (propriétaire de la plateforme seulement)."""

    items: list[SubscriptionQuotaView]
    stale_after_seconds: int
    generated_at: datetime

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("« items » doit être une liste")
        return value

    @field_validator("stale_after_seconds", mode="before")
    @classmethod
    def _stale_after(cls, value: Any) -> int:
        return _count(
            value,
            label="stale_after_seconds",
            minimum=QUOTA_STALE_SECONDS_MIN,
            maximum=QUOTA_STALE_SECONDS_MAX,
        )

    @field_validator("generated_at", mode="before")
    @classmethod
    def _generated_at(cls, value: Any) -> datetime:
        return _instant(value, label="generated_at")
