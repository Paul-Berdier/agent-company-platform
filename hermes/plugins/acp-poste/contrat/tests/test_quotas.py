"""Contrats des quotas réels d'abonnement (Codex CLI par compte ChatGPT, Claude Code).

Ces contrats ne transportent que des valeurs relevées à la source officielle : une
valeur inconnue reste ``None`` (« Inconnu » à l'écran), jamais une estimation. Les
refus sont explicites et rédigés en français, y compris pour un champ inconnu ou
manquant, afin qu'un 422 de l'API se lise sans traduction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import acp_poste_contrat
from acp_poste_contrat import (
    DEFAULT_QUOTA_STALE_SECONDS,
    QUOTA_BATCH_MAX,
    QUOTA_SOURCE_BY_PROVIDER,
    QUOTA_WINDOWS_MAX,
    QuotaCredits,
    QuotaWindow,
    QuotaWindowView,
    SubscriptionQuotaBatch,
    SubscriptionQuotaIngestResult,
    SubscriptionQuotaList,
    SubscriptionQuotaReport,
    SubscriptionQuotaView,
)

def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _window(**overrides) -> dict:
    payload = {
        "key": "primary",
        "used_percent": 42,
        "window_minutes": 300,
        "resets_at": "2026-09-24T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def _report(**overrides) -> dict:
    payload = {
        "provider": "codex",
        "status": "ok",
        "source": "codex_app_server",
        "plan": "prolite",
        "limit_id": "codex",
        "windows": [_window(), _window(key="secondary", used_percent=7, window_minutes=10080)],
        "credits": {"has_credits": False, "unlimited": False, "balance": None},
        "limit_reached": False,
        "reached_type": None,
        "observed_at": _now().isoformat(),
        "detail": None,
    }
    payload.update(overrides)
    return payload


def _messages(error: ValidationError) -> str:
    return " | ".join(item["msg"] for item in error.errors())


# --- Rapport valide ---------------------------------------------------------


def test_a_complete_codex_report_is_accepted_and_normalised_to_utc():
    observed = datetime(2026, 9, 20, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    report = SubscriptionQuotaReport.model_validate(
        _report(observed_at=observed.isoformat())
    )

    assert report.provider == "codex"
    assert report.limit_id == "codex"
    assert report.observed_at == observed.astimezone(UTC)
    assert report.observed_at.tzinfo == UTC
    assert report.windows[0].used_percent == 42
    assert isinstance(report.windows[0].used_percent, int)
    assert report.windows[0].resets_at == datetime(2026, 9, 24, 12, tzinfo=UTC)
    assert report.credits == QuotaCredits(has_credits=False, unlimited=False, balance=None)


def test_a_claude_report_keeps_fractional_percentages_and_unknown_values():
    report = SubscriptionQuotaReport.model_validate(
        _report(
            provider="claude_code",
            source="claude_code_statusline",
            plan=None,
            limit_id="default",
            windows=[
                _window(key="five_hour", used_percent=12.5, window_minutes=300, resets_at=None),
                _window(key="seven_day", used_percent=None, window_minutes=10080, resets_at=None),
            ],
            credits=None,
            limit_reached=None,
        )
    )

    assert report.windows[0].used_percent == 12.5
    assert report.windows[1].used_percent is None
    assert report.limit_reached is None


def test_limit_id_defaults_by_status_and_windows_to_an_empty_list():
    report = SubscriptionQuotaReport.model_validate(
        {
            "provider": "codex",
            "status": "not_signed_in",
            "source": "codex_app_server",
            "observed_at": _now().isoformat(),
            "detail": "Profil Codex dédié non connecté.",
        }
    )

    assert report.limit_id == "probe"
    assert report.windows == []
    assert report.credits is None

    successful = {key: value for key, value in _report().items() if key != "limit_id"}
    assert SubscriptionQuotaReport.model_validate(successful).limit_id == "default"


def test_a_failed_reading_never_takes_the_identity_of_a_counter():
    """Un échec porte l'identifiant réservé « probe » : il ne remplace jamais un compteur."""

    assert acp_poste_contrat.PROBE_LIMIT_ID == "probe"
    failure = {
        "provider": "claude_code",
        "status": "unavailable",
        "source": "claude_code_statusline",
        "observed_at": _now().isoformat(),
        "detail": "Relevé de la ligne d'état Claude Code mal formé : quotas non relevés.",
    }
    assert SubscriptionQuotaReport.model_validate({**failure, "limit_id": "probe"}).limit_id == "probe"
    for counter in ("default", "codex"):
        with pytest.raises(ValidationError) as caught:
            SubscriptionQuotaReport.model_validate({**failure, "limit_id": counter})
        assert "identifiant réservé « probe »" in _messages(caught.value)

    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(limit_id="probe"))
    assert "« probe » est réservé aux lectures en échec" in _messages(caught.value)


def test_source_is_bound_to_its_provider():
    assert QUOTA_SOURCE_BY_PROVIDER == {
        "codex": "codex_app_server",
        "claude_code": "claude_code_statusline",
    }
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(source="claude_code_statusline"))
    assert "source" in _messages(caught.value)
    assert "codex_app_server" in _messages(caught.value)


# --- Refus explicites en français ------------------------------------------


def test_unknown_fields_are_refused_in_french():
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(email="titulaire@example.com"))
    assert "champ inconnu refusé" in _messages(caught.value)
    assert "email" in _messages(caught.value)

    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(remaining_percent=58))
    assert "champ inconnu refusé" in _messages(caught.value)


def test_missing_required_fields_are_named_in_french():
    payload = _report()
    del payload["observed_at"]
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(payload)
    assert "champ obligatoire absent" in _messages(caught.value)
    assert "observed_at" in _messages(caught.value)

    window = _window()
    del window["used_percent"]
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(window)
    assert "champ obligatoire absent" in _messages(caught.value)


@pytest.mark.parametrize(
    "value",
    [-1, 100.01, 101, float("nan"), float("inf"), True, "42", [42]],
)
def test_used_percent_is_a_finite_number_between_zero_and_one_hundred(value):
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(used_percent=value))
    assert "used_percent" in _messages(caught.value)
    assert "Input should" not in _messages(caught.value)


@pytest.mark.parametrize("value", [0, 100, 0.5, 99.99])
def test_used_percent_accepts_the_whole_closed_range(value):
    assert QuotaWindow.model_validate(_window(used_percent=value)).used_percent == value


@pytest.mark.parametrize("value", [0, -5, 527_041, 300.0, True, "300"])
def test_window_minutes_is_a_positive_bounded_integer(value):
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(window_minutes=value))
    assert "window_minutes" in _messages(caught.value)


@pytest.mark.parametrize("key", ["", "x" * 33, "Primary", "cinq heures", 7, None])
def test_window_key_is_a_short_lowercase_identifier(key):
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(key=key))
    assert "key" in _messages(caught.value)


def test_window_reset_instant_must_carry_its_timezone():
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(resets_at="2026-09-24T12:00:00"))
    assert "fuseau" in _messages(caught.value)
    with pytest.raises(ValidationError) as caught:
        QuotaWindow.model_validate(_window(resets_at="demain"))
    assert "resets_at" in _messages(caught.value)


def test_windows_are_bounded_and_their_keys_unique():
    many = [_window(key=f"w{index}") for index in range(QUOTA_WINDOWS_MAX + 1)]
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(windows=many))
    assert f"au maximum {QUOTA_WINDOWS_MAX}" in _messages(caught.value)

    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(windows=[_window(), _window()]))
    assert "fenêtre en double" in _messages(caught.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan", "p" * 41),
        ("plan", ""),
        ("limit_id", "l" * 65),
        ("limit_id", "compteur codex"),
        ("reached_type", "r" * 65),
        ("detail", "d" * 301),
        ("detail", "texte\x00nul"),
    ],
)
def test_text_fields_have_explicit_french_bounds(field, value):
    overrides = {field: value}
    if field == "reached_type":
        overrides["limit_reached"] = True
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(**overrides))
    assert field in _messages(caught.value)
    assert "Input should" not in _messages(caught.value)


@pytest.mark.parametrize(
    "field,value",
    [("provider", "chatgpt"), ("status", "estimated"), ("source", "journal_codex")],
)
def test_enumerations_are_closed(field, value):
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(**{field: value}))
    assert field in _messages(caught.value)
    assert "valeurs admises" in _messages(caught.value)


def test_credits_are_strictly_typed_and_bounded():
    with pytest.raises(ValidationError) as caught:
        QuotaCredits.model_validate({"has_credits": 1, "unlimited": False, "balance": None})
    assert "has_credits" in _messages(caught.value)
    with pytest.raises(ValidationError) as caught:
        QuotaCredits.model_validate({"has_credits": True, "unlimited": False, "balance": "9" * 33})
    assert "balance" in _messages(caught.value)


def test_observed_at_must_be_aware_and_not_beyond_five_minutes_in_the_future():
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(observed_at="2026-09-24T10:00:00"))
    assert "fuseau" in _messages(caught.value)

    ahead = _now() + timedelta(minutes=6)
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(observed_at=ahead.isoformat()))
    assert "futur" in _messages(caught.value)

    tolerated = _now() + timedelta(minutes=4)
    report = SubscriptionQuotaReport.model_validate(_report(observed_at=tolerated.isoformat()))
    assert report.observed_at == tolerated


def test_a_failed_probe_carries_an_explanation_and_no_measure():
    base = {
        "status": "not_signed_in",
        "limit_id": "probe",
        "plan": None,
        "windows": [],
        "credits": None,
        "limit_reached": None,
        "detail": None,
    }
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(_report(**base))
    assert "detail" in _messages(caught.value)

    for field, value in (
        ("windows", [_window()]),
        ("credits", {"has_credits": True, "unlimited": False, "balance": "3"}),
        ("limit_reached", False),
    ):
        with pytest.raises(ValidationError) as caught:
            SubscriptionQuotaReport.model_validate(
                _report(**{**base, "detail": "Profil non connecté.", field: value})
            )
        assert "aucune mesure" in _messages(caught.value)


def test_a_reached_type_requires_a_reached_limit():
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaReport.model_validate(
            _report(limit_reached=False, reached_type="rate_limit_reached")
        )
    assert "reached_type" in _messages(caught.value)
    report = SubscriptionQuotaReport.model_validate(
        _report(limit_reached=True, reached_type="rate_limit_reached")
    )
    assert report.reached_type == "rate_limit_reached"


# --- Lot -----------------------------------------------------------------------


def test_a_batch_holds_one_to_sixteen_distinct_reports():
    assert QUOTA_BATCH_MAX == 16
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaBatch.model_validate({"reports": []})
    assert "au moins un relevé" in _messages(caught.value)

    too_many = [_report(limit_id=f"b{index}") for index in range(QUOTA_BATCH_MAX + 1)]
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaBatch.model_validate({"reports": too_many})
    assert f"au maximum {QUOTA_BATCH_MAX}" in _messages(caught.value)

    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaBatch.model_validate({"reports": [_report(), _report()]})
    assert "en double" in _messages(caught.value)

    batch = SubscriptionQuotaBatch.model_validate(
        {
            "reports": [
                _report(),
                _report(
                    provider="claude_code",
                    source="claude_code_statusline",
                    limit_id="codex",
                    plan=None,
                    credits=None,
                    limit_reached=None,
                ),
            ]
        }
    )
    assert [report.provider for report in batch.reports] == ["codex", "claude_code"]


def test_a_batch_never_mixes_counters_and_a_failure_for_one_provider():
    failure = {
        "provider": "codex",
        "status": "unavailable",
        "source": "codex_app_server",
        "observed_at": _now().isoformat(),
        "detail": "L'app-server Codex n'a pas répondu dans le délai de 20 s : quotas non relevés.",
    }
    with pytest.raises(ValidationError) as caught:
        SubscriptionQuotaBatch.model_validate({"reports": [_report(), failure]})
    assert "codex mêle des compteurs relevés et un échec de lecture" in _messages(caught.value)

    claude_failure = {
        **failure,
        "provider": "claude_code",
        "source": "claude_code_statusline",
        "detail": "Relevé de la ligne d'état Claude Code illisible : quotas non relevés.",
    }
    batch = SubscriptionQuotaBatch.model_validate({"reports": [_report(), claude_failure]})
    assert [(report.provider, report.limit_id) for report in batch.reports] == [
        ("codex", "codex"),
        ("claude_code", "probe"),
    ]


def test_ingest_result_counts_are_non_negative_integers():
    result = SubscriptionQuotaIngestResult(stored=2, ignored_older=1, removed=0)
    assert result.model_dump() == {"stored": 2, "ignored_older": 1, "removed": 0}
    with pytest.raises(ValidationError):
        SubscriptionQuotaIngestResult(stored=-1, ignored_older=0, removed=0)


# --- Vue du propriétaire --------------------------------------------------------


def test_a_view_derives_the_remaining_share_from_the_used_share_only():
    report = SubscriptionQuotaReport.model_validate(
        _report(
            windows=[
                _window(used_percent=42),
                _window(key="secondary", used_percent=33.3),
                _window(key="tertiary", used_percent=None),
            ]
        )
    )
    received = _now()
    view = SubscriptionQuotaView.from_report(
        report,
        worker_id="worker-1",
        worker_name="poste-principal",
        received_at=received,
        stale=False,
    )

    assert [window.remaining_percent for window in view.windows] == [58, 66.7, None]
    assert view.worker_name == "poste-principal"
    assert view.received_at == received
    assert view.stale is False
    dumped = view.model_dump(mode="json")
    assert dumped["windows"][0] == {
        "key": "primary",
        "used_percent": 42,
        "window_minutes": 300,
        "resets_at": "2026-09-24T12:00:00Z",
        "remaining_percent": 58,
    }


def test_a_view_refuses_an_inconsistent_remaining_share():
    with pytest.raises(ValidationError) as caught:
        QuotaWindowView.model_validate({**_window(used_percent=40), "remaining_percent": 70})
    assert "remaining_percent" in _messages(caught.value)
    with pytest.raises(ValidationError):
        QuotaWindowView.model_validate({**_window(used_percent=None), "remaining_percent": 100})


def test_a_view_is_not_refused_for_an_old_observation():
    old = _now() - timedelta(days=3)
    report = SubscriptionQuotaReport.model_validate(_report(observed_at=old.isoformat()))
    view = SubscriptionQuotaView.from_report(
        report, worker_id="w", worker_name="n", received_at=old, stale=True
    )
    assert view.stale is True


def test_the_list_carries_its_freshness_threshold():
    assert DEFAULT_QUOTA_STALE_SECONDS == 1800
    listing = SubscriptionQuotaList(items=[], stale_after_seconds=1800, generated_at=_now())
    assert listing.items == []
    with pytest.raises(ValidationError):
        SubscriptionQuotaList(items=[], stale_after_seconds=10, generated_at=_now())
