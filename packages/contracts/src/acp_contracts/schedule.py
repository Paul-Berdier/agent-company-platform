"""Planification : expressions cron à cinq champs et occurrences en heure locale.

Ce module ne dépend que de la bibliothèque standard. Il fournit :

- :class:`CronExpression`, l'analyse stricte d'une expression à cinq champs ;
- :func:`next_occurrence`, la prochaine occurrence en UTC d'une expression
  interprétée dans un fuseau **local** (Europe/Paris par défaut) ;
- :class:`IntervalSchedule`, une durée fixe entre deux déclenchements ;
- :func:`fire_key`, l'empreinte déterministe d'un déclenchement nominal.

Les heures qu'écrit un utilisateur sont des heures locales : ``30 2 * * *``
demande 02:30 à Paris, pas 02:30 UTC. Les deux bascules d'heure d'été sont donc
traitées explicitement — voir :func:`next_occurrence`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Paris"
INTERVAL_MIN_SECONDS = 60
INTERVAL_MAX_SECONDS = 31_536_000
FIRE_KEY_LENGTH = 32
SEARCH_HORIZON_DAYS = 1_461
"""Quatre années : la recherche est bornée, jamais infinie (cas du 30 février)."""


class ScheduleError(ValueError):
    """Une planification invalide : elle est refusée à l'écriture."""


# --- Analyse de l'expression -------------------------------------------------


@dataclass(frozen=True)
class _FieldSpec:
    """Description d'un champ cron : son nom français et ses bornes."""

    label: str
    low: int
    high: int


_MINUTE = _FieldSpec("minute", 0, 59)
_HOUR_OF_DAY = _FieldSpec("heure", 0, 23)
_DAY_OF_MONTH = _FieldSpec("jour du mois", 1, 31)
_MONTH = _FieldSpec("mois", 1, 12)
_DAY_OF_WEEK = _FieldSpec("jour de semaine", 0, 7)

_ALL_TERM = re.compile(r"\*(?:/(?P<step>[0-9]{1,5}))?")
_RANGE_TERM = re.compile(
    r"(?P<start>[0-9]{1,5})-(?P<end>[0-9]{1,5})(?:/(?P<step>[0-9]{1,5}))?"
)
_SINGLE_TERM = re.compile(r"(?P<value>[0-9]{1,5})")
_INTERVAL_SECONDS = re.compile(r"[0-9]{1,10}")


def _reject(field: _FieldSpec, reason: str) -> ScheduleError:
    """Construit le refus d'un champ.

    Le message nomme le champ fautif et ne recopie jamais ce que l'appelant a
    fourni : l'expression vient d'une requête, la republier l'exposerait.
    """

    return ScheduleError(f"champ « {field.label} » invalide : {reason}")


def _parse_value(raw: str, field: _FieldSpec) -> int:
    value = int(raw)
    if not field.low <= value <= field.high:
        raise _reject(field, f"valeur hors bornes ({field.low}-{field.high} attendu)")
    return value


def _parse_step(raw: str | None, field: _FieldSpec) -> int:
    if raw is None:
        return 1
    step = int(raw)
    if step <= 0:
        raise _reject(field, "pas strictement positif attendu")
    return step


def _parse_term(term: str, field: _FieldSpec) -> set[int]:
    """Analyse une des formes acceptées : ``*``, ``n``, ``a-b``, ``a-b/p``, ``*/p``."""

    match = _ALL_TERM.fullmatch(term)
    if match is not None:
        step = _parse_step(match.group("step"), field)
        return set(range(field.low, field.high + 1, step))

    match = _RANGE_TERM.fullmatch(term)
    if match is not None:
        start = _parse_value(match.group("start"), field)
        end = _parse_value(match.group("end"), field)
        if start > end:
            raise _reject(field, "intervalle décroissant")
        step = _parse_step(match.group("step"), field)
        return set(range(start, end + 1, step))

    match = _SINGLE_TERM.fullmatch(term)
    if match is not None:
        return {_parse_value(match.group("value"), field)}

    raise _reject(field, "syntaxe non reconnue")


def _parse_field(raw: str, field: _FieldSpec) -> frozenset[int]:
    values: set[int] = set()
    for term in raw.split(","):
        values |= _parse_term(term, field)
    return frozenset(values)


def _is_restricted(raw: str) -> bool:
    """Vrai quand un champ de jour restreint réellement les dates.

    La règle est celle de cron : un champ qui **commence** par ``*`` n'est pas
    restreint, y compris sous la forme ``*/2``. C'est ce qui décide ensuite entre
    l'union et l'intersection des deux champs de jour — et s'en écarter ferait
    déclencher une routine des jours que l'utilisateur n'a pas demandés, puisque
    ``*/2 * 1`` se lirait « les jours impairs **ou** le lundi » au lieu de
    « les jours impairs **et** le lundi ».
    """

    return not raw.startswith("*")


@dataclass(frozen=True)
class CronExpression:
    """Expression cron à cinq champs : minute, heure, jour du mois, mois, jour de semaine.

    Un champ est dit « restreint » quand il vaut autre chose que ``*`` : c'est ce
    qui déclenche la sémantique d'union POSIX entre jour du mois et jour de
    semaine (voir :meth:`matches_date`).
    """

    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]
    day_of_month_restricted: bool
    day_of_week_restricted: bool

    @classmethod
    def parse(cls, expression: str) -> CronExpression:
        """Analyse une expression à cinq champs séparés par des espaces.

        Le jour de semaine va de ``0`` (dimanche) à ``6`` ; ``7`` est accepté et
        normalisé vers ``0``.
        """

        if not isinstance(expression, str):
            raise ScheduleError(
                "expression cron invalide : cinq champs textuels sont attendus"
            )
        fields = expression.split()
        if len(fields) != 5:
            raise ScheduleError(
                "expression cron invalide : cinq champs sont attendus "
                "(minute, heure, jour du mois, mois, jour de semaine)"
            )

        raw_day_of_month, raw_day_of_week = fields[2], fields[4]
        days_of_week = frozenset(
            0 if value == 7 else value
            for value in _parse_field(raw_day_of_week, _DAY_OF_WEEK)
        )
        return cls(
            minutes=_parse_field(fields[0], _MINUTE),
            hours=_parse_field(fields[1], _HOUR_OF_DAY),
            days_of_month=_parse_field(raw_day_of_month, _DAY_OF_MONTH),
            months=_parse_field(fields[3], _MONTH),
            days_of_week=days_of_week,
            day_of_month_restricted=_is_restricted(raw_day_of_month),
            day_of_week_restricted=_is_restricted(raw_day_of_week),
        )

    def matches_date(self, day: date) -> bool:
        """Applique la sémantique POSIX des deux champs de jour.

        Quand le jour du mois et le jour de semaine sont **tous deux** restreints,
        la date correspond dès que **l'un des deux** correspond : c'est une union,
        pas une intersection. Quand un seul est restreint, il s'applique seul.
        """

        if day.month not in self.months:
            return False
        day_of_month_matches = day.day in self.days_of_month
        day_of_week_matches = day.isoweekday() % 7 in self.days_of_week
        if self.day_of_month_restricted and self.day_of_week_restricted:
            return day_of_month_matches or day_of_week_matches
        return day_of_month_matches and day_of_week_matches

    def matches(self, moment: datetime) -> bool:
        """Vrai quand l'heure **locale** ``moment`` satisfait l'expression."""

        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and self.matches_date(moment.date())
        )


# --- Fuseau horaire ----------------------------------------------------------


def resolve_timezone(timezone: str | tzinfo = DEFAULT_TIMEZONE) -> tzinfo:
    """Retourne le ``tzinfo`` d'un nom IANA.

    La base IANA est la seule autorité admise ici. Aucune règle de bascule n'est
    réécrite à la main : une table maquillée en fuseau donnerait un résultat
    différent de celui de l'intégration continue, ne connaîtrait qu'une poignée de
    fuseaux, et figerait une règle que le législateur peut changer. Là où le système
    ne fournit pas la base — Windows — le paquet de données ``tzdata`` la fournit ;
    il est déclaré en dépendance pour ces plateformes.

    Le nom vient d'une requête : un fuseau inconnu est refusé sans être recopié
    dans le message.
    """

    if isinstance(timezone, tzinfo):
        return timezone
    if not isinstance(timezone, str) or not timezone:
        raise ScheduleError("fuseau horaire invalide : un nom IANA est attendu")
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        # Distinguer les deux causes : un nom que l'utilisateur a mal écrit, et une
        # base de fuseaux absente de la machine. Les confondre ferait chercher une
        # faute de frappe là où il manque une dépendance.
        if not _timezone_database_available():
            raise ScheduleError(
                "base de fuseaux horaires introuvable sur cette machine : "
                "installez le paquet « tzdata »"
            ) from exc
        raise ScheduleError("fuseau horaire inconnu") from exc
    except ValueError as exc:
        raise ScheduleError("fuseau horaire inconnu") from exc


def _timezone_database_available() -> bool:
    """Vrai quand la base IANA est lisible, en s'appuyant sur un fuseau toujours présent."""

    try:
        ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        return False
    return True


# --- Occurrences -------------------------------------------------------------


def _as_utc(moment: datetime) -> datetime:
    """Exige un instant conscient du fuseau et le ramène en UTC."""

    if not isinstance(moment, datetime):
        raise ScheduleError("l'instant de référence doit être un datetime")
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ScheduleError(
            "l'instant de référence doit être conscient du fuseau (UTC attendu)"
        )
    return moment.astimezone(UTC)


def _utc_instant_if_local_time_exists(naive: datetime, zone: tzinfo) -> datetime | None:
    """Convertit une heure locale naïve en UTC, ou ``None`` si elle n'existe pas.

    ``fold = 0`` retient volontairement la **première** des deux occurrences d'une
    heure ambiguë : le dernier dimanche d'octobre, 02:30 existe deux fois et une
    routine ne doit se déclencher qu'une seule fois.

    L'aller-retour détecte l'heure inexistante du dernier dimanche de mars : si la
    reconversion ne redonne pas la même heure locale, cette heure n'a jamais
    existé et l'occurrence est omise. La décaler à 03:30 exécuterait la routine à
    une heure que l'utilisateur n'a pas demandée.
    """

    moment = naive.replace(tzinfo=zone).astimezone(UTC)
    if moment.astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return moment


def next_occurrence(
    expression: str | CronExpression,
    after: datetime,
    timezone: str | tzinfo = DEFAULT_TIMEZONE,
) -> datetime | None:
    """Prochaine occurrence en UTC, strictement postérieure à ``after``.

    L'expression est interprétée dans l'heure **locale** de ``timezone`` : les
    candidats sont construits jour par jour en heure murale, puis reconvertis en
    UTC. Les heures locales inexistantes sont omises et les heures ambiguës ne sont
    retenues qu'une fois.

    Retourne ``None`` quand aucune occurrence ne tombe dans les quatre années qui
    suivent ``after`` : sans cette borne, une expression comme ``0 0 30 2 *`` — le
    30 février — ferait boucler la recherche indéfiniment.
    """

    cron = (
        expression
        if isinstance(expression, CronExpression)
        else CronExpression.parse(expression)
    )
    zone = resolve_timezone(timezone)
    after_utc = _as_utc(after)
    horizon = after_utc + timedelta(days=SEARCH_HORIZON_DAYS)

    hours = sorted(cron.hours)
    minutes = sorted(cron.minutes)
    day = after_utc.astimezone(zone).date()
    last_day = horizon.astimezone(zone).date()

    while day <= last_day:
        if cron.matches_date(day):
            for hour in hours:
                for minute in minutes:
                    naive = datetime(day.year, day.month, day.day, hour, minute)
                    moment = _utc_instant_if_local_time_exists(naive, zone)
                    if moment is None or moment <= after_utc:
                        continue
                    # Les candidats sont produits dans l'ordre croissant : le
                    # premier qui dépasse l'horizon prouve qu'il n'y en a pas.
                    return moment if moment <= horizon else None
        day += timedelta(days=1)
    return None


# --- Intervalles -------------------------------------------------------------


@dataclass(frozen=True)
class IntervalSchedule:
    """Durée fixe entre deux déclenchements, exprimée en secondes."""

    seconds: int

    def __post_init__(self) -> None:
        if isinstance(self.seconds, bool) or not isinstance(self.seconds, int):
            raise ScheduleError(
                "intervalle invalide : un nombre entier de secondes est attendu"
            )
        if not INTERVAL_MIN_SECONDS <= self.seconds <= INTERVAL_MAX_SECONDS:
            raise ScheduleError(
                "intervalle invalide : la durée doit tenir entre "
                f"{INTERVAL_MIN_SECONDS} et {INTERVAL_MAX_SECONDS} secondes"
            )

    @classmethod
    def parse(cls, value: str | int) -> IntervalSchedule:
        """Analyse l'intervalle tel qu'il est stocké : un nombre de secondes."""

        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ScheduleError(
                "intervalle invalide : un nombre entier de secondes est attendu"
            )
        if isinstance(value, str):
            if _INTERVAL_SECONDS.fullmatch(value) is None:
                raise ScheduleError(
                    "intervalle invalide : un nombre entier de secondes est attendu"
                )
            value = int(value)
        return cls(value)

    def next_occurrence(self, after: datetime) -> datetime:
        """``after`` plus l'intervalle.

        Aucun fuseau n'intervient : un intervalle est une durée, pas une heure du
        calendrier. Il ne subit donc pas les bascules d'heure d'été, et c'est
        volontaire.
        """

        return _as_utc(after) + timedelta(seconds=self.seconds)


# --- Empreinte de déclenchement ---------------------------------------------


def fire_key(automation_id: str, scheduled_for: datetime) -> str:
    """Empreinte déterministe d'un déclenchement nominal.

    ``scheduled_for`` est normalisé en UTC : deux représentations du même instant —
    Europe/Paris et UTC, ou un ``datetime`` naïf supposé UTC — produisent la
    **même** clé. C'est ce qui permet à une contrainte d'unicité en base de garantir
    l'absence de doublon entre deux déclencheurs concurrents.
    """

    if not isinstance(scheduled_for, datetime):
        raise ScheduleError("l'instant nominal doit être un datetime")
    if (
        scheduled_for.tzinfo is None
        or scheduled_for.tzinfo.utcoffset(scheduled_for) is None
    ):
        moment = scheduled_for.replace(tzinfo=UTC)
    else:
        moment = scheduled_for.astimezone(UTC)
    digest = hashlib.sha256(f"{automation_id}:{moment.isoformat()}".encode()).hexdigest()
    return digest[:FIRE_KEY_LENGTH]
