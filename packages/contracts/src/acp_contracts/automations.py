"""Contrats des automatisations planifiées, de leur calendrier et des budgets.

Une automatisation est une intention répétée : un gabarit de mission et un
calendrier. Ce module ne planifie rien — il **refuse à l'écriture** ce que le
planificateur ne saurait pas calculer, pour qu'aucune automatisation muette ne
puisse être enregistrée.

L'analyse des expressions et des fuseaux appartient à :mod:`acp_contracts.schedule`,
seule autorité du dépôt sur ces sujets : ce module s'en sert, il ne la réécrit pas.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from .missions import (
    MAX_BUDGET_COUNTER,
    MAX_BUDGET_COST,
    MissionAutonomy,
    MissionBudget,
    MissionCreate,
    MissionResource,
)
from .schedule import (
    DEFAULT_TIMEZONE,
    CronExpression,
    IntervalSchedule,
    ScheduleError,
    next_occurrence,
    resolve_timezone,
)

AutomationScheduleKind = Literal["cron", "interval"]
AutomationCatchupPolicy = Literal["skip", "run_once"]
AutomationTriggerKind = Literal["manual", "schedule", "webhook"]
AutomationRunOutcome = Literal[
    "launched",
    "skipped_concurrency",
    "skipped_disabled",
    "skipped_catchup",
    "failed",
]
AutomationCompletionStatus = Literal[
    "blocked", "succeeded", "failed", "cancelled", "interrupted"
]
CalendarEntryState = Literal["planned", "past"]
BudgetState = Literal["unknown", "ok", "warning", "exceeded"]
BudgetUsagePhase = Literal["planning", "execution", "evaluation", "tool"]
BudgetUsageSource = Literal["provider", "platform"]

MAX_CONCURRENT_RUNS = 5
"""Borne haute de ``max_concurrent_runs`` : au delà, une routine se piétine."""

WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
"""Taille maximale du corps HTTP d'un déclenchement webhook (1 Mio)."""

WEBHOOK_MAX_PAYLOAD_DEPTH = 32
"""Profondeur JSON maximale d'un payload webhook après décodage."""

WEBHOOK_MAX_PAYLOAD_NODES = 10_000
"""Nombre maximal de valeurs JSON dans un payload webhook."""

BUDGET_LIMIT_NAMES = ("max_cost", "max_tokens", "max_tool_calls")
"""Noms admis dans ``BudgetVerdict.limit_reached``.

Ce sont exactement les champs de :class:`~acp_contracts.missions.MissionBudget` : le
verdict nomme la limite telle qu'elle a été écrite par l'utilisateur, pas un synonyme
inventé par le service qui l'évalue.
"""

MAX_LEDGER_COST = Decimal(str(MAX_BUDGET_COST))


def _strict_decimal_cost(value: object) -> object:
    """Convertit un nombre JSON en Decimal sans accepter booléen ni chaîne."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return value
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("le coût doit être un nombre fini positif ou nul")
    if amount > MAX_LEDGER_COST:
        raise ValueError("le coût dépasse la capacité du ledger")
    return amount


class _AutomationContract(BaseModel):
    """Socle strict partagé par les frontières JSON du Lot F.

    Une faute de frappe ne doit jamais être ignorée et ``true`` ne doit pas
    devenir silencieusement le nombre ``1`` dans une limite de concurrence.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


class AutomationMissionAutonomy(MissionAutonomy):
    """Version sans champs implicites de l'autonomie d'un gabarit."""

    model_config = ConfigDict(extra="forbid")


class AutomationMissionResource(MissionResource):
    """Version sans champs implicites d'une ressource de gabarit."""

    model_config = ConfigDict(extra="forbid")


class AutomationMissionBudget(MissionBudget):
    """Budget de mission strict : booléens et valeurs infinies sont refusés."""

    model_config = ConfigDict(extra="forbid")

    max_cost: float | None = Field(
        default=None,
        ge=0,
        le=MAX_BUDGET_COST,
        allow_inf_nan=False,
        strict=True,
    )
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    max_tokens: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )
    max_tool_calls: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )


# --- Planification -----------------------------------------------------------


class AutomationSchedule(_AutomationContract):
    """Calendrier d'une automatisation : une expression et le fuseau qui la lit.

    L'expression est interprétée en heure **locale** : ``30 2 * * *`` demande 02:30
    à Paris, pas 02:30 UTC. Le fuseau fait donc partie du contrat et n'est pas un
    détail d'affichage.
    """

    kind: AutomationScheduleKind
    expression: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default=DEFAULT_TIMEZONE, min_length=1, max_length=64)

    @model_validator(mode="after")
    def schedule_must_be_computable(self) -> AutomationSchedule:
        """Refuse toute planification que l'évaluateur ne saurait pas calculer.

        Une expression acceptée ici est une expression dont le planificateur saura
        tirer une prochaine occurrence. L'exiger à l'écriture est le seul moment où
        l'utilisateur est là pour corriger sa saisie : plus tard, une automatisation
        sans occurrence se contenterait de ne jamais rien faire.
        """

        try:
            parsed = self._parse()
            zone = resolve_timezone(self.timezone)
        except ScheduleError as exc:
            # Le message d'origine nomme déjà le champ fautif et ne recopie pas
            # l'expression fournie : le reformuler l'exposerait à nouveau.
            raise ValueError(str(exc)) from exc
        if isinstance(parsed, CronExpression) and (
            next_occurrence(parsed, datetime.now(UTC), zone) is None
        ):
            raise ValueError(
                "expression cron sans aucune occurrence dans les quatre années à "
                "venir : vérifiez le jour du mois et le mois"
            )
        return self

    def _parse(self) -> CronExpression | IntervalSchedule:
        if self.kind == "cron":
            return CronExpression.parse(self.expression)
        return IntervalSchedule.parse(self.expression)

    def parsed(self) -> CronExpression | IntervalSchedule:
        """Expression analysée, selon le genre de planification.

        L'analyse est refaite à la demande plutôt que conservée : un modèle validé
        garantit qu'elle aboutit, et rien ici n'a besoin d'être mis en cache.
        """

        return self._parse()

    def resolved_timezone(self) -> tzinfo:
        """Fuseau effectif, déjà validé par :func:`resolve_timezone`."""

        return resolve_timezone(self.timezone)


# --- Gabarit de mission -------------------------------------------------------


class AutomationMissionTemplate(_AutomationContract):
    """Corps de mission d'une automatisation : un ``MissionCreate`` sans ``project_id``.

    Le projet vient de l'automatisation elle-même, jamais du gabarit : deux sources
    de portée permettraient à une routine d'un projet de créer des missions dans un
    autre. Les champs restants sont ceux de :class:`MissionCreate`, avec les mêmes
    bornes — un gabarit accepté ici doit produire une mission acceptable.
    """

    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=10_000)
    expected_outcome: str = Field(min_length=1, max_length=10_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    autonomy: AutomationMissionAutonomy
    resources: list[AutomationMissionResource] = Field(
        default_factory=list, max_length=100
    )
    budget: AutomationMissionBudget
    duration_seconds: int = Field(ge=1, le=31_536_000, strict=True)
    team_id: str | None = None
    agent_instance_id: str | None = None
    priority: int = Field(default=3, ge=1, le=5, strict=True)
    required_capabilities: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("acceptance_criteria", "required_capabilities")
    @classmethod
    def unique_non_empty_strings(cls, value: list[str]) -> list[str]:
        """Délègue à ``MissionCreate`` plutôt que de recopier sa règle.

        Recopier la règle la ferait diverger le jour où l'une des deux changerait,
        et un gabarit accepté produirait alors une mission refusée.
        """

        return MissionCreate.unique_non_empty_strings(value)

    def to_mission_create(self, project_id: str) -> MissionCreate:
        """Complète le gabarit avec la portée du projet de l'automatisation."""

        return MissionCreate(project_id=project_id, **self.model_dump())


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("le nom de l'automatisation ne peut pas être vide")
    return value


def _normalise_utc(value: datetime | None, *, label: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"« {label} » doit porter un fuseau")
    return value.astimezone(UTC)


# --- Écritures ----------------------------------------------------------------


class AutomationCreate(_AutomationContract):
    """Création d'une automatisation. Elle naît **désactivée** : l'activer est un geste."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    schedule: AutomationSchedule
    mission_template: AutomationMissionTemplate
    catchup_policy: AutomationCatchupPolicy = "skip"
    max_concurrent_runs: int = Field(default=1, ge=1, le=MAX_CONCURRENT_RUNS)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _clean_name(value)


class AutomationUpdate(_AutomationContract):
    """Modification partielle : tout champ absent reste inchangé.

    Les mêmes champs qu'à la création, tous facultatifs — et la planification est
    revalidée dès qu'elle est fournie, exactement comme à la création.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    schedule: AutomationSchedule | None = None
    mission_template: AutomationMissionTemplate | None = None
    catchup_policy: AutomationCatchupPolicy | None = None
    max_concurrent_runs: int | None = Field(
        default=None, ge=1, le=MAX_CONCURRENT_RUNS
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @model_validator(mode="after")
    def supplied_fields_cannot_be_null(self) -> AutomationUpdate:
        """Un champ absent reste inchangé ; un champ fourni à ``null`` est refusé."""

        null_fields = sorted(
            name for name in self.model_fields_set if getattr(self, name) is None
        )
        if null_fields:
            raise ValueError(
                "les champs fournis ne peuvent pas valoir null : "
                + ", ".join(null_fields)
            )
        return self


# --- Lectures -----------------------------------------------------------------


class AutomationSummary(_AutomationContract):
    """Ce qu'une liste d'automatisations montre d'une routine.

    ``next_run_at`` vaut ``None`` quand la routine est désactivée ou qu'aucune
    occurrence n'est calculable : l'absence de prochaine occurrence est une
    information, pas un défaut d'affichage.
    """

    id: str
    project_id: str
    name: str
    description: str
    schedule: AutomationSchedule
    enabled: bool
    catchup_policy: AutomationCatchupPolicy
    max_concurrent_runs: int = Field(ge=1, le=MAX_CONCURRENT_RUNS)
    next_run_at: datetime | None
    created_at: datetime

    @field_validator("next_run_at", "created_at")
    @classmethod
    def normalise_utc_instants(cls, value: datetime | None) -> datetime | None:
        return _normalise_utc(value, label="instant d'automatisation")


class AutomationRunSummary(_AutomationContract):
    """Déclenchement matérialisé, lancé ou refusé.

    ``scheduled_for`` est l'instant **nominal** qui identifie l'occurrence, ``fired_at``
    l'instant **réel** où le planificateur l'a traitée. Les deux sont conservés :
    seul le premier rend une ``fire_key`` reproductible.
    """

    id: str
    automation_id: str
    fire_key: str = Field(pattern=r"^[0-9a-f]{32}$")
    scheduled_for: datetime
    fired_at: datetime
    task_id: str | None
    trigger_kind: AutomationTriggerKind
    outcome: AutomationRunOutcome
    detail: str = Field(max_length=500)
    completion_status: AutomationCompletionStatus | None

    @field_validator("scheduled_for", "fired_at")
    @classmethod
    def normalise_utc_instants(cls, value: datetime) -> datetime:
        normalised = _normalise_utc(value, label="instant de déclenchement")
        assert normalised is not None
        return normalised


class AutomationWebhookTrigger(_AutomationContract):
    """Événement externe authentifié et idempotent.

    Le secret voyage dans l'en-tête d'autorisation, jamais dans ce corps ni dans
    un URL. ``event_id`` est l'identité stable fournie par l'émetteur.
    """

    event_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bound_payload_shape(cls, value: dict[str, JsonValue]):
        nodes = 0
        stack: list[tuple[JsonValue, int]] = [
            (item, 1) for item in value.values()
        ]
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if nodes > WEBHOOK_MAX_PAYLOAD_NODES:
                raise ValueError("le payload webhook contient trop de valeurs")
            if isinstance(item, dict):
                if item and depth >= WEBHOOK_MAX_PAYLOAD_DEPTH:
                    raise ValueError("le payload webhook est trop profond")
                stack.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                if item and depth >= WEBHOOK_MAX_PAYLOAD_DEPTH:
                    raise ValueError("le payload webhook est trop profond")
                stack.extend((child, depth + 1) for child in item)
        return value


class AutomationWebhookRotationRequest(_AutomationContract):
    """Secret de rotation généré par le client et rejouable sans stockage brut.

    Une valeur base64url représentant au moins 32 octets est exigée. Le serveur ne
    peut pas mesurer l'aléa d'une chaîne reçue ; le client doit donc la produire
    avec un générateur cryptographiquement sûr.
    """

    secret: str = Field(
        min_length=43,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    @field_validator("secret")
    @classmethod
    def require_256_bits_of_material(cls, value: str) -> str:
        padding = "=" * (-len(value) % 4)
        try:
            decoded = base64.b64decode(
                value + padding,
                altchars=b"-_",
                validate=True,
            )
        except (binascii.Error, ValueError) as exc:
            raise ValueError("le secret doit être encodé en base64url") from exc
        if len(decoded) < 32:
            raise ValueError("le secret doit représenter au moins 256 bits")
        return value


class AutomationWebhookStatus(_AutomationContract):
    """Configuration publique du webhook, sans jamais révéler son secret."""

    enabled: bool
    secret_configured: bool
    endpoint_path: str = Field(min_length=1, max_length=500)
    rotated_at: datetime | None

    @field_validator("rotated_at")
    @classmethod
    def normalise_rotation_time(cls, value: datetime | None) -> datetime | None:
        return _normalise_utc(value, label="rotated_at")


class AutomationWebhookSecret(AutomationWebhookStatus):
    """Secret fourni par le client, renvoyé dans la seule réponse de rotation."""

    secret: str = Field(
        min_length=43,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class AutomationDetail(AutomationSummary):
    """Détail d'une automatisation : son gabarit et ses derniers déclenchements."""

    mission_template: AutomationMissionTemplate
    recent_runs: list[AutomationRunSummary]


# --- Calendrier ---------------------------------------------------------------


class CalendarEntry(_AutomationContract):
    """Une occurrence du calendrier, prévue ou passée.

    ``utc_offset_minutes`` est un champ à part entière et non un détail de
    formatage : un jour de bascule, deux entrées du même calendrier n'ont pas le
    même décalage, et l'interface doit pouvoir le montrer sans refaire un calcul de
    fuseau dans le navigateur.
    """

    occurs_at_utc: datetime
    occurs_at_local: str = Field(min_length=1, max_length=64)
    timezone: str = Field(default=DEFAULT_TIMEZONE, min_length=1, max_length=64)
    utc_offset_minutes: int = Field(ge=-1_440, le=1_440)
    automation_id: str
    automation_name: str
    state: CalendarEntryState
    task_id: str | None = None
    outcome: AutomationRunOutcome | None = None

    @model_validator(mode="after")
    def local_time_carries_its_own_offset(self) -> CalendarEntry:
        """Exige trois représentations concordantes du même instant.

        La base IANA reste l'autorité : l'instant UTC, l'heure locale et le
        décalage doivent tous désigner la même occurrence.
        """

        if self.occurs_at_utc.tzinfo is None or self.occurs_at_utc.utcoffset() is None:
            raise ValueError("« occurs_at_utc » doit porter un fuseau")
        moment = self.occurs_at_utc.astimezone(UTC)
        self.occurs_at_utc = moment
        try:
            local = datetime.fromisoformat(self.occurs_at_local)
        except ValueError as exc:
            raise ValueError(
                "« occurs_at_local » doit être une date ISO 8601"
            ) from exc
        offset = local.utcoffset()
        if offset is None:
            raise ValueError(
                "« occurs_at_local » doit porter son décalage UTC (par exemple « +02:00 »)"
            )
        if int(offset.total_seconds() // 60) != self.utc_offset_minutes:
            raise ValueError(
                "le décalage porté par « occurs_at_local » et « utc_offset_minutes » "
                "ne concordent pas"
            )
        try:
            zone = resolve_timezone(self.timezone)
        except ScheduleError as exc:
            raise ValueError(str(exc)) from exc
        expected_local = moment.astimezone(zone)
        if local.astimezone(UTC) != moment:
            raise ValueError(
                "« occurs_at_local » et « occurs_at_utc » ne désignent pas le même instant"
            )
        if offset != expected_local.utcoffset():
            raise ValueError(
                "le décalage local ne correspond pas au fuseau IANA pour cet instant"
            )
        return self

    @classmethod
    def from_occurrence(
        cls,
        *,
        occurs_at_utc: datetime,
        automation_id: str,
        automation_name: str,
        state: CalendarEntryState,
        timezone: str | tzinfo = DEFAULT_TIMEZONE,
        task_id: str | None = None,
        outcome: AutomationRunOutcome | None = None,
    ) -> CalendarEntry:
        """Construit une entrée en dérivant l'heure locale et le décalage du fuseau.

        Passer par ici évite de formater une heure locale à la main : c'est la base
        IANA qui décide du décalage du jour, y compris les deux dimanches de
        bascule. Un instant naïf est lu comme un instant UTC, comme partout ailleurs
        dans la plateforme.
        """

        zone = resolve_timezone(timezone)
        moment = (
            occurs_at_utc.replace(tzinfo=UTC)
            if occurs_at_utc.tzinfo is None
            or occurs_at_utc.tzinfo.utcoffset(occurs_at_utc) is None
            else occurs_at_utc.astimezone(UTC)
        )
        local = moment.astimezone(zone)
        offset = local.utcoffset()
        assert offset is not None  # un instant converti dans un fuseau en a toujours un
        return cls(
            occurs_at_utc=moment,
            occurs_at_local=local.isoformat(),
            timezone=timezone if isinstance(timezone, str) else str(zone),
            utc_offset_minutes=int(offset.total_seconds() // 60),
            automation_id=automation_id,
            automation_name=automation_name,
            state=state,
            task_id=task_id,
            outcome=outcome,
        )


# --- Budgets ------------------------------------------------------------------


class BudgetUsageDelta(_AutomationContract):
    """Incrément de consommation observé pendant une tentative.

    ``None`` signifie « information non rapportée » ; zéro signifie un vrai zéro.
    Cette différence est conservée jusqu'au service de budget.
    """

    report_id: str = Field(min_length=1, max_length=128)
    permit_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=100)
    phase: BudgetUsagePhase
    source: BudgetUsageSource
    cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    tokens_input: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tokens_output: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tool_calls: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    estimated: bool = False

    @field_validator("cost", mode="before")
    @classmethod
    def parse_cost_as_decimal(cls, value: object) -> object:
        return _strict_decimal_cost(value)

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("le fournisseur ne peut pas être vide")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return None if value is None else value.upper()

    @model_validator(mode="after")
    def contains_a_measure(self) -> BudgetUsageDelta:
        if all(
            value is None
            for value in (
                self.cost,
                self.tokens_input,
                self.tokens_output,
                self.tool_calls,
            )
        ):
            raise ValueError("un rapport de consommation doit contenir au moins une mesure")
        if (self.cost is None) != (self.currency is None):
            raise ValueError("un coût et sa devise doivent être rapportés ensemble")
        if self.source == "platform" and any(
            value is not None for value in (self.cost, self.tokens_input, self.tokens_output)
        ):
            raise ValueError(
                "la plateforme ne peut rapporter elle-même que les appels d'outils"
            )
        return self


class BudgetPermitRequest(_AutomationContract):
    """Réservation idempotente exigée avant un nouvel effet consommateur."""

    permit_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=100)
    phase: BudgetUsagePhase
    cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    tokens_input: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tokens_output: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tool_calls: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)

    @field_validator("cost", mode="before")
    @classmethod
    def parse_cost_as_decimal(cls, value: object) -> object:
        return _strict_decimal_cost(value)

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("le fournisseur ne peut pas être vide")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return None if value is None else value.upper()

    @model_validator(mode="after")
    def contains_a_bound(self) -> BudgetPermitRequest:
        if all(
            value is None
            for value in (
                self.cost,
                self.tokens_input,
                self.tokens_output,
                self.tool_calls,
            )
        ):
            raise ValueError("un permis doit réserver au moins une consommation")
        if (self.cost is None) != (self.currency is None):
            raise ValueError("un coût et sa devise doivent être réservés ensemble")
        return self


class ProviderBudgetLimit(_AutomationContract):
    """Plafond journalier propre à un fournisseur réellement identifié."""

    provider: str = Field(min_length=1, max_length=100)
    budget: AutomationMissionBudget

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("le fournisseur ne peut pas être vide")
        return value


class ProjectBudgetPolicy(_AutomationContract):
    """Politique complète d'un projet, remplacée atomiquement par l'API.

    Le budget de chaque mission reste dans son gabarit. Cette politique ajoute les
    bornes transversales demandées : journée, fournisseur, concurrence, relances
    et nombre d'agents créés par une tentative.
    """

    timezone: str = Field(default=DEFAULT_TIMEZONE, min_length=1, max_length=64)
    daily_budget: AutomationMissionBudget | None = None
    provider_budgets: list[ProviderBudgetLimit] = Field(
        default_factory=list, max_length=100
    )
    max_concurrent_missions: int = Field(default=4, ge=1, le=100, strict=True)
    max_retries_per_mission: int = Field(default=3, ge=0, le=20, strict=True)
    max_spawned_agents_per_run: int = Field(default=4, ge=1, le=32, strict=True)

    @model_validator(mode="after")
    def providers_are_unique(self) -> ProjectBudgetPolicy:
        try:
            resolve_timezone(self.timezone)
        except ScheduleError as exc:
            raise ValueError(str(exc)) from exc
        names = [entry.provider.casefold() for entry in self.provider_budgets]
        if len(names) != len(set(names)):
            raise ValueError("un fournisseur ne peut avoir qu'un plafond")
        return self


class ProjectBudgetPolicySummary(ProjectBudgetPolicy):
    """Politique persistée d'un projet."""

    project_id: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalise_updated_at(cls, value: datetime) -> datetime:
        normalised = _normalise_utc(value, label="updated_at")
        assert normalised is not None
        return normalised


class BudgetVerdict(_AutomationContract):
    """Décision de budget et mesures qui l'étayent.

    Chaque quantité inconnue reste ``None``. ``measured`` indique seulement qu'au
    moins une quantité est connue ; il ne permet jamais de conclure qu'un coût
    inconnu est nul parce que, par exemple, les appels d'outils sont comptés.
    """

    state: BudgetState
    measured: bool = False
    limit_reached: str | None = Field(default=None, max_length=64)
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    tokens_input: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tokens_output: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    tool_calls: int | None = Field(default=None, ge=0, le=MAX_BUDGET_COUNTER)
    saturated_metrics: list[
        Literal["tokens_input", "tokens_output", "tool_calls"]
    ] = Field(default_factory=list)
    usage_reported: bool = False
    estimated: bool = False

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("limit_reached")
    @classmethod
    def validate_limit_reached(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned not in BUDGET_LIMIT_NAMES:
            raise ValueError("nom de limite de budget inconnu")
        return cleaned

    @model_validator(mode="after")
    def a_refusal_rests_on_the_relevant_measure(self) -> BudgetVerdict:
        quantities = (self.cost, self.tokens_input, self.tokens_output, self.tool_calls)
        has_measure = any(value is not None for value in quantities)
        if len(set(self.saturated_metrics)) != len(self.saturated_metrics):
            raise ValueError("une métrique saturée ne peut être nommée deux fois")
        if any(
            getattr(self, metric) != MAX_BUDGET_COUNTER
            for metric in self.saturated_metrics
        ):
            raise ValueError(
                "une métrique signalée saturée doit valoir le maximum sûr"
            )
        if self.state in ("warning", "exceeded") and self.limit_reached is None:
            raise ValueError(
                "un état « warning » ou « exceeded » doit nommer la limite atteinte"
            )
        if has_measure != (self.measured or self.estimated):
            raise ValueError(
                "une consommation connue doit être mesurée ou explicitement estimée"
            )
        if self.usage_reported and all(
            value is None for value in (self.cost, self.tokens_input, self.tokens_output)
        ):
            raise ValueError(
                "« usage_reported » exige une consommation rapportée par le fournisseur"
            )
        if self.state == "unknown":
            if self.limit_reached is not None:
                raise ValueError(
                    "un budget de mesure inconnue ne peut pas nommer de limite atteinte"
                )
            return self
        if not has_measure:
            raise ValueError(
                "un budget sans mesure doit avoir l'état « unknown », jamais « ok »"
            )
        if self.state == "ok":
            if self.limit_reached is not None:
                raise ValueError("un budget « ok » ne peut pas nommer de limite atteinte")
            return self
        if self.state == "exceeded" and not self.measured:
            raise ValueError(
                "un état « exceeded » exige une grandeur réellement mesurée : "
                "une estimation ne prouve aucun dépassement"
            )
        assert self.limit_reached is not None
        if self.limit_reached == "max_cost" and self.cost is None:
            raise ValueError("la limite « max_cost » exige un coût connu")
        if self.limit_reached == "max_tokens" and (
            self.tokens_input is None or self.tokens_output is None
        ):
            raise ValueError(
                "la limite « max_tokens » exige les jetons d'entrée et de sortie"
            )
        if self.limit_reached == "max_tool_calls" and self.tool_calls is None:
            raise ValueError("la limite « max_tool_calls » exige un compteur connu")
        return self


class BudgetMutationResult(_AutomationContract):
    """Résultat commun d'un permis ou d'un rapport de consommation."""

    accepted: bool
    idempotent: bool
    permit_allowed: bool
    verdict: BudgetVerdict


class BudgetConsumptionTotals(_AutomationContract):
    """Agrégat explicite : une mesure absente reste inconnue, jamais zéro."""

    reports: int = Field(ge=0, le=MAX_BUDGET_COUNTER, strict=True)
    pending_reservations: int = Field(ge=0, le=MAX_BUDGET_COUNTER, strict=True)
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    tokens_input: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )
    tokens_output: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )
    tool_calls: int | None = Field(
        default=None, ge=0, le=MAX_BUDGET_COUNTER, strict=True
    )
    saturated_metrics: list[
        Literal[
            "reports",
            "pending_reservations",
            "tokens_input",
            "tokens_output",
            "tool_calls",
        ]
    ] = Field(default_factory=list)
    usage_reported: bool
    estimated: bool

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return None if value is None else value.upper()

    @model_validator(mode="after")
    def empty_bucket_has_no_invented_measure(self) -> BudgetConsumptionTotals:
        if len(set(self.saturated_metrics)) != len(self.saturated_metrics):
            raise ValueError("une métrique saturée ne peut être nommée deux fois")
        if any(
            getattr(self, metric) != MAX_BUDGET_COUNTER
            for metric in self.saturated_metrics
        ):
            raise ValueError(
                "une métrique signalée saturée doit valoir le maximum sûr"
            )
        if self.reports == 0 and any(
            value is not None
            for value in (
                self.cost,
                self.currency,
                self.tokens_input,
                self.tokens_output,
                self.tool_calls,
            )
        ):
            raise ValueError("un agrégat vide ne peut pas inventer une mesure")
        if self.reports == 0 and (
            self.pending_reservations
            or self.usage_reported
            or self.estimated
            or self.saturated_metrics
        ):
            raise ValueError("un agrégat vide ne peut porter d'état de consommation")
        if self.cost is not None and self.currency is None:
            raise ValueError("un coût agrégé connu exige une devise unique")
        return self


class BudgetMissionConsumption(_AutomationContract):
    """Consommation active regroupée par mission."""

    mission_id: str = Field(min_length=1)
    task_run_ids: list[str]
    totals: BudgetConsumptionTotals


class BudgetProviderConsumption(_AutomationContract):
    """Consommation active regroupée par fournisseur normalisé."""

    provider: str = Field(min_length=1, max_length=100)
    totals: BudgetConsumptionTotals


class BudgetConsumptionSummary(_AutomationContract):
    """Vue utilisateur du ledger actif pour un jour comptable du projet."""

    project_id: str = Field(min_length=1)
    accounting_day: date
    timezone: str = Field(min_length=1, max_length=64)
    totals: BudgetConsumptionTotals
    missions: list[BudgetMissionConsumption]
    providers: list[BudgetProviderConsumption]
