"""Tests de l'évaluateur cron et du calcul d'occurrences en Europe/Paris.

Les dates de bascule d'heure sont **calculées** (dernier dimanche de mars et
d'octobre) et non codées en dur : ces tests doivent rester vrais les années
suivantes.
"""

from __future__ import annotations

import calendar
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from acp_contracts import (
    DEFAULT_TIMEZONE,
    INTERVAL_MAX_SECONDS,
    INTERVAL_MIN_SECONDS,
    CronExpression,
    IntervalSchedule,
    ScheduleError,
    fire_key,
    next_occurrence,
    resolve_timezone,
)

PARIS = resolve_timezone(DEFAULT_TIMEZONE)
TRANSITION_YEARS = (2026, 2027, 2028)


def _last_sunday(year: int, month: int) -> date:
    """Dernier dimanche du mois : le jour où l'heure légale européenne bascule."""

    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=last.isoweekday() % 7)


def _paris(day: date, hour: int, minute: int = 0, *, fold: int = 0) -> datetime:
    """Instant conscient construit à partir d'une heure murale parisienne."""

    return datetime(day.year, day.month, day.day, hour, minute, fold=fold, tzinfo=PARIS)


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


# --- Analyse de l'expression -------------------------------------------------


def test_parses_the_star_form_on_every_field():
    cron = CronExpression.parse("* * * * *")

    assert cron.minutes == frozenset(range(0, 60))
    assert cron.hours == frozenset(range(0, 24))
    assert cron.days_of_month == frozenset(range(1, 32))
    assert cron.months == frozenset(range(1, 13))
    assert cron.days_of_week == frozenset(range(0, 7))
    assert cron.day_of_month_restricted is False
    assert cron.day_of_week_restricted is False


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("5 * * * *", {5}),
        ("5-8 * * * *", {5, 6, 7, 8}),
        ("0-30/10 * * * *", {0, 10, 20, 30}),
        ("*/15 * * * *", {0, 15, 30, 45}),
        ("0,5,30-32,*/20 * * * *", {0, 5, 20, 30, 31, 32, 40}),
    ],
)
def test_parses_each_supported_field_form(expression: str, expected: set[int]):
    assert CronExpression.parse(expression).minutes == frozenset(expected)


def test_parses_the_other_fields():
    cron = CronExpression.parse("0 8-18/2 1,15 */3 1-5")

    assert cron.hours == frozenset({8, 10, 12, 14, 16, 18})
    assert cron.days_of_month == frozenset({1, 15})
    assert cron.months == frozenset({1, 4, 7, 10})
    assert cron.days_of_week == frozenset({1, 2, 3, 4, 5})
    assert cron.day_of_month_restricted is True
    assert cron.day_of_week_restricted is True


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "* * * *",
        "* * * * * *",
        "60 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * 32 * *",
        "* * * 0 *",
        "* * * 13 *",
        "* * * * 8",
        "*/0 * * * *",
        "*/-1 * * * *",
        "10-5 * * * *",
        "5-10/0 * * * *",
        "1,,2 * * * *",
        "1, * * * *",
        "-5 * * * *",
        "5- * * * *",
        "abc * * * *",
        "5/15 * * * *",
        "* * * * ?",
    ],
)
def test_rejects_invalid_expressions(expression: str):
    with pytest.raises(ScheduleError):
        CronExpression.parse(expression)


@pytest.mark.parametrize("value", [None, 42, ["* * * * *"]])
def test_rejects_non_textual_expressions(value: object):
    with pytest.raises(ScheduleError):
        CronExpression.parse(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("expression", "field"),
    [
        ("99 * * * *", "minute"),
        ("0 99 * * *", "heure"),
        ("0 0 99 * *", "jour du mois"),
        ("0 0 1 99 *", "mois"),
        ("0 0 1 1 99", "jour de semaine"),
    ],
)
def test_error_names_the_faulty_field(expression: str, field: str):
    with pytest.raises(ScheduleError) as failure:
        CronExpression.parse(expression)

    assert field in str(failure.value)


def test_error_does_not_echo_the_submitted_expression():
    """Le message ne republie ni l'expression ni le jeton fautif de l'appelant."""

    expression = "0 9z9 13 * 5"
    with pytest.raises(ScheduleError) as failure:
        CronExpression.parse(expression)

    message = str(failure.value)
    assert expression not in message
    assert "9z9" not in message
    assert "heure" in message


# --- Sémantique des jours ----------------------------------------------------


def test_day_of_week_seven_is_normalised_to_sunday():
    cron = CronExpression.parse("0 0 * * 7")

    assert cron.days_of_week == frozenset({0})
    assert cron.matches_date(date(2026, 1, 4)) is True  # dimanche
    assert cron.matches_date(date(2026, 1, 5)) is False  # lundi
    assert CronExpression.parse("0 0 * * 5-7").days_of_week == frozenset({0, 5, 6})


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 13), True),  # mardi 13 : jour du mois seul
        (date(2026, 1, 9), True),  # vendredi 9 : jour de semaine seul
        (date(2026, 2, 13), True),  # vendredi 13 : les deux
        (date(2026, 1, 14), False),  # ni l'un ni l'autre
    ],
)
def test_day_of_month_and_day_of_week_are_a_union(day: date, expected: bool):
    """POSIX : quand les deux champs sont restreints, un seul suffit à faire mouche."""

    assert CronExpression.parse("0 12 13 * 5").matches_date(day) is expected


def test_a_day_field_starting_with_a_star_is_not_restricted():
    """Règle de cron : un champ de jour commençant par ``*`` n'est pas restreint.

    ``*/2`` énumère certes une partie des jours, mais il commence par ``*`` : cron
    le traite comme non restreint, ce qui impose l'**intersection** des deux champs
    de jour au lieu de leur union. Prendre ``*/2`` pour un champ restreint ferait
    lire ``*/2 * 1`` comme « les jours impairs **ou** le lundi » et déclencherait la
    routine des jours que personne n'a demandés.
    """

    cron = CronExpression.parse("0 0 */2 * 1")

    assert cron.day_of_month_restricted is False
    # 12 janvier 2026 : un lundi, mais un jour pair, donc absent de ``*/2``.
    assert date(2026, 1, 12).isoweekday() == 1
    assert 12 not in cron.days_of_month
    assert cron.matches_date(date(2026, 1, 12)) is False
    # 5 janvier 2026 : un lundi ET un jour impair — les deux champs concordent.
    assert cron.matches_date(date(2026, 1, 5)) is True


def test_a_single_restricted_day_field_applies_alone():
    dom_only = CronExpression.parse("0 12 13 * *")
    dow_only = CronExpression.parse("0 12 * * 5")

    assert dom_only.matches_date(date(2026, 1, 13)) is True
    assert dom_only.matches_date(date(2026, 1, 9)) is False
    assert dow_only.matches_date(date(2026, 1, 9)) is True
    assert dow_only.matches_date(date(2026, 1, 13)) is False


def test_the_union_drives_the_next_occurrences():
    moment = _utc(_paris(date(2026, 1, 1), 0))
    days: list[date] = []
    for _ in range(4):
        moment = next_occurrence("0 12 13 * 5", moment)
        assert moment is not None
        days.append(moment.astimezone(PARIS).date())

    assert days == [
        date(2026, 1, 2),  # vendredi
        date(2026, 1, 9),  # vendredi
        date(2026, 1, 13),  # mardi 13
        date(2026, 1, 16),  # vendredi
    ]


# --- Occurrences en heure locale --------------------------------------------


def test_resolved_paris_zone_carries_both_seasonal_offsets():
    assert datetime(2026, 1, 15, 12, tzinfo=PARIS).utcoffset() == timedelta(hours=1)
    assert datetime(2026, 7, 15, 12, tzinfo=PARIS).utcoffset() == timedelta(hours=2)


def test_any_iana_zone_resolves_not_only_the_default_one():
    """Le module s'appuie sur la vraie base IANA, pas sur une table écrite à la main.

    Une table maquillée en fuseau ne connaîtrait que les quelques noms qu'on y aurait
    inscrits, figerait une règle de bascule que le législateur peut changer, et
    calculerait autre chose que l'intégration continue. Ces trois fuseaux ont des
    règles distinctes de celle de Paris ; les résoudre prouve que la base est
    complète. Là où le système ne la fournit pas — Windows — le paquet ``tzdata``
    est déclaré en dépendance.
    """

    assert resolve_timezone("America/New_York").utcoffset(
        datetime(2026, 1, 15, 12)
    ) == timedelta(hours=-5)
    assert resolve_timezone("Asia/Kolkata").utcoffset(
        datetime(2026, 1, 15, 12)
    ) == timedelta(hours=5, minutes=30)
    # L'Australie bascule à l'inverse de l'Europe : en janvier elle est en heure d'été.
    assert resolve_timezone("Australia/Sydney").utcoffset(
        datetime(2026, 1, 15, 12)
    ) == timedelta(hours=11)


def test_unknown_timezone_is_rejected():
    with pytest.raises(ScheduleError):
        resolve_timezone("Mars/Olympus")


def test_next_occurrence_matches_local_time_in_winter():
    result = next_occurrence("30 2 * * *", datetime(2026, 1, 15, 12, 0, tzinfo=UTC))

    assert result == datetime(2026, 1, 16, 1, 30, tzinfo=UTC)
    assert result.astimezone(PARIS).hour == 2


def test_next_occurrence_matches_local_time_in_summer():
    result = next_occurrence("30 2 * * *", datetime(2026, 7, 15, 12, 0, tzinfo=UTC))

    assert result == datetime(2026, 7, 16, 0, 30, tzinfo=UTC)
    assert result.astimezone(PARIS).hour == 2


def test_next_occurrence_accepts_a_parsed_expression_and_a_tzinfo():
    cron = CronExpression.parse("30 2 * * *")

    assert next_occurrence(cron, datetime(2026, 1, 15, 12, 0, tzinfo=UTC), PARIS) == (
        datetime(2026, 1, 16, 1, 30, tzinfo=UTC)
    )


def test_next_occurrence_rejects_a_naive_reference():
    with pytest.raises(ScheduleError):
        next_occurrence("30 2 * * *", datetime(2026, 1, 15, 12, 0))


@pytest.mark.parametrize("year", TRANSITION_YEARS)
def test_spring_transition_skips_the_nonexistent_local_time(year: int):
    """02:30 n'existe pas le jour du passage à l'heure d'été : on saute le jour."""

    transition = _last_sunday(year, 3)
    after = _utc(_paris(transition - timedelta(days=1), 12))

    result = next_occurrence("30 2 * * *", after)

    assert result is not None
    local = result.astimezone(PARIS)
    assert local.date() != transition  # ni 02:30 ni un décalage vers 03:30
    assert local.date() == transition + timedelta(days=1)
    assert (local.hour, local.minute) == (2, 30)
    assert result == _utc(_paris(transition + timedelta(days=1), 2, 30))


@pytest.mark.parametrize("year", TRANSITION_YEARS)
def test_spring_transition_keeps_an_existing_local_time(year: int):
    """Le jour de bascule n'est pas sauté en entier : 03:30 existe bien."""

    transition = _last_sunday(year, 3)
    after = _utc(_paris(transition - timedelta(days=1), 12))

    result = next_occurrence("30 3 * * *", after)

    assert result == _utc(_paris(transition, 3, 30))
    assert result.astimezone(PARIS).utcoffset() == timedelta(hours=2)


@pytest.mark.parametrize("year", TRANSITION_YEARS)
def test_autumn_transition_keeps_only_the_first_ambiguous_time(year: int):
    """02:30 existe deux fois : seule la première (fold=0) déclenche."""

    transition = _last_sunday(year, 10)
    after = _utc(_paris(transition - timedelta(days=1), 12))

    first = next_occurrence("30 2 * * *", after)

    assert first == _utc(_paris(transition, 2, 30, fold=0))
    assert first.astimezone(PARIS).utcoffset() == timedelta(hours=2)

    second = next_occurrence("30 2 * * *", first)

    assert second != _utc(_paris(transition, 2, 30, fold=1))
    assert second.astimezone(PARIS).date() == transition + timedelta(days=1)
    assert second == _utc(_paris(transition + timedelta(days=1), 2, 30))


# --- Terminaison et stricte postériorité -------------------------------------


def test_impossible_expression_returns_none_and_terminates():
    """Le 30 février n'arrive jamais : la recherche est bornée, pas infinie."""

    started = time.monotonic()
    result = next_occurrence("0 0 30 2 *", datetime(2026, 1, 1, tzinfo=UTC))
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 10.0


def test_next_occurrence_is_strictly_after_the_reference():
    occurrence = datetime(2026, 1, 16, 1, 30, tzinfo=UTC)

    assert next_occurrence("30 2 * * *", occurrence) == datetime(
        2026, 1, 17, 1, 30, tzinfo=UTC
    )


def test_next_occurrence_ignores_the_seconds_of_the_reference():
    reference = datetime(2026, 1, 16, 1, 29, 59, 999_999, tzinfo=UTC)

    assert next_occurrence("30 2 * * *", reference) == datetime(
        2026, 1, 16, 1, 30, tzinfo=UTC
    )


# --- Intervalles -------------------------------------------------------------


@pytest.mark.parametrize("seconds", [INTERVAL_MIN_SECONDS, 900, INTERVAL_MAX_SECONDS])
def test_interval_accepts_bounded_durations(seconds: int):
    assert IntervalSchedule(seconds).seconds == seconds


@pytest.mark.parametrize("seconds", [0, 59, INTERVAL_MAX_SECONDS + 1, -60, True, 60.5])
def test_interval_rejects_out_of_bounds_durations(seconds: object):
    with pytest.raises(ScheduleError):
        IntervalSchedule(seconds)  # type: ignore[arg-type]


@pytest.mark.parametrize(("value", "expected"), [("900", 900), (3600, 3600)])
def test_interval_parses_a_stored_expression(value: object, expected: int):
    assert IntervalSchedule.parse(value).seconds == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["", "abc", "12.5", " 900 ", "0x10", "1e3"])
def test_interval_parse_rejects_invalid_expressions(value: str):
    with pytest.raises(ScheduleError):
        IntervalSchedule.parse(value)


def test_interval_next_occurrence_is_a_duration_not_a_wall_clock():
    """Un intervalle ne subit pas la bascule d'heure : c'est volontaire."""

    transition = _last_sunday(2026, 3)
    after = _utc(_paris(transition, 1, 30))
    schedule = IntervalSchedule(3600)

    result = schedule.next_occurrence(after)

    assert result == after + timedelta(hours=1)
    assert result.astimezone(PARIS).hour == 3  # 01:30 + 1 h = 03:30 locale


def test_interval_next_occurrence_rejects_a_naive_reference():
    with pytest.raises(ScheduleError):
        IntervalSchedule(60).next_occurrence(datetime(2026, 1, 1, 12, 0))


# --- Empreinte de déclenchement ---------------------------------------------


def test_fire_key_is_identical_for_two_representations_of_the_same_instant():
    instant = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    local = instant.astimezone(PARIS)

    assert local.utcoffset() != timedelta(0)
    assert fire_key("automation-1", local) == fire_key("automation-1", instant)


def test_fire_key_treats_a_naive_instant_as_utc():
    instant = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)

    assert fire_key("automation-1", instant.replace(tzinfo=None)) == fire_key(
        "automation-1", instant
    )


def test_fire_key_is_a_short_hexadecimal_digest():
    key = fire_key("automation-1", datetime(2026, 3, 29, 0, 30, tzinfo=UTC))

    assert len(key) == 32
    assert set(key) <= set("0123456789abcdef")


def test_fire_key_separates_automations_and_instants():
    instant = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)

    assert fire_key("automation-1", instant) != fire_key("automation-2", instant)
    assert fire_key("automation-1", instant) != fire_key(
        "automation-1", instant + timedelta(minutes=1)
    )
