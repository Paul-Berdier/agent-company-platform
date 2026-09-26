"""Relevés des quotas réels d'abonnement du poste : forme des compteurs Codex et ligne d'état Claude Code.

Étape P5 : la sonde Codex elle-même (processus, séquence, délais, arrêt d'arbre) est éprouvée par
``test_sondes_codex.py`` contre ``faux_codex.py`` ; restent ici la conversion de ``account/rateLimits/read`` en relevés
au contrat, l'environnement de la CLI et la lecture du fichier de la ligne d'état.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from acp_poste import subscription_quotas as quotas
from acp_poste.sondes_codex import extraire_compte
from acp_poste.subscription_quotas import API_KEY_VARIABLES, codex_environment, probe_claude_snapshot
from acp_poste_contrat import SubscriptionQuotaBatch


class _Faux:
    """Instantanés de ``account/rateLimits/read`` dans la forme publiée par Codex 0.156.1 (``faux_codex.py``)."""

    EMAIL = "titulaire@example.com"

    @staticmethod
    def snapshot(limit_id, name, primary_used, secondary_used, *, reached=None):
        def fenetre(utilise, minutes, remise):
            return {"usedPercent": utilise, "windowDurationMins": minutes, "resetsAt": remise}

        return {"limitId": limit_id, "limitName": name, "primary": fenetre(primary_used, 300, 1_790_000_000),
                "secondary": fenetre(secondary_used, 10080, 1_790_500_000),
                "credits": {"hasCredits": False, "unlimited": False, "balance": None}, "planType": "prolite",
                "rateLimitReachedType": reached}


FAKE = _Faux()


def test_the_codex_environment_carries_no_api_key_and_points_to_the_profile(tmp_path: Path):
    source = {name: "sk-proj-" + "x" * 30 for name in API_KEY_VARIABLES}
    source.update({"PATH": "chemin", "ACP_SECRET": "valeur", "HTTPS_PROXY": "http://proxy.test:3128"})
    environment = codex_environment(tmp_path / "codex-home", source=source)
    assert not set(API_KEY_VARIABLES) & set(environment)
    assert "ACP_SECRET" not in environment
    assert environment["CODEX_HOME"] == str(tmp_path / "codex-home")
    assert environment["PATH"] == "chemin" and environment["HTTPS_PROXY"] == "http://proxy.test:3128"


def test_counters_follow_the_multi_bucket_view_then_the_single_view():
    codex = FAKE.snapshot("codex", "Codex", 42, 7)
    other = FAKE.snapshot("codex_other", "Autre", 100, 55, reached="rate_limit_reached")
    reports = quotas.codex_reports_from_rate_limits(
        {"rateLimits": codex, "rateLimitsByLimitId": {"codex": codex, "codex_other": other}},
        account_plan="prolite", observed_at=datetime.now(UTC))
    assert [(r.limit_id, r.limit_reached, r.reached_type) for r in reports] == [
        ("codex", False, None), ("codex_other", True, "rate_limit_reached")]
    (single,) = quotas.codex_reports_from_rate_limits({"rateLimits": codex, "rateLimitsByLimitId": None},
                                                       account_plan="prolite", observed_at=datetime.now(UTC))
    assert single.limit_id == "codex" and [w.used_percent for w in single.windows] == [42, 7]
    legacy = {"limitId": "codex", "primary": {"usedPercent": 12, "windowDurationMins": None, "resetsAt": None},
              "secondary": None, "planType": "prolite"}
    (ancien,) = quotas.codex_reports_from_rate_limits({"rateLimits": legacy}, account_plan=None,
                                                      observed_at=datetime.now(UTC))
    assert ancien.limit_reached is None and ancien.windows[0].window_minutes is None


def test_a_malformed_counter_is_refused():
    broken = FAKE.snapshot("codex", "Codex", 42, 7)
    broken["primary"]["usedPercent"] = "beaucoup"
    with pytest.raises(quotas.QuotaMalForme):
        quotas.codex_reports_from_rate_limits({"rateLimits": broken}, account_plan=None, observed_at=datetime.now(UTC))


def test_one_counter_outside_the_contract_fails_the_whole_reading():
    """Aucun compteur transmis à moitié : les derniers relevés réussis restent affichés."""

    valid = FAKE.snapshot("codex", "Codex", 10, 20)
    beyond = FAKE.snapshot("codex_other", "GPT-6 Astra", 140, 20)
    reports = quotas.codex_reports_from_rate_limits(
        {"rateLimits": valid, "rateLimitsByLimitId": {"codex": valid, "codex_other": beyond}},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert [(report.status, report.limit_id, report.plan) for report in reports] == [
        ("unavailable", "probe", "prolite")
    ]
    assert "« codex_other »" in reports[0].detail
    assert "used_percent" in reports[0].detail
    SubscriptionQuotaBatch.model_validate({"reports": [report.model_dump(mode="json") for report in reports]})


def test_too_many_counters_are_refused_rather_than_truncated():
    many = {f"compteur_{index:02d}": FAKE.snapshot(f"compteur_{index:02d}", "C", 1, 1) for index in range(16)}
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": many["compteur_00"], "rateLimitsByLimitId": many},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert (report.status, report.limit_id, report.plan) == ("unavailable", "probe", "prolite")
    assert "16 compteurs" in report.detail

    fifteen = dict(list(many.items())[:15])
    reports = quotas.codex_reports_from_rate_limits(
        {"rateLimits": many["compteur_00"], "rateLimitsByLimitId": fifteen},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert [report.status for report in reports] == ["ok"] * 15


def test_the_unknown_plan_of_the_source_stays_unknown():
    """``PlanType`` de Codex vaut « unknown » quand le serveur ignore l'offre."""

    counter = FAKE.snapshot("codex", "Codex", 10, 20)
    counter["planType"] = "unknown"
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": counter}, account_plan=None, observed_at=datetime.now(UTC)
    )
    assert (report.status, report.plan) == ("ok", None)
    # Comme une offre absente du compteur : celle lue par « account/read » s'applique.
    (from_account,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": counter}, account_plan="prolite", observed_at=datetime.now(UTC)
    )
    assert from_account.plan == "prolite"
    assert extraire_compte({"account": {"type": "chatgpt", "planType": "unknown"}}) == ("compte_chatgpt", None)
    without_plan = FAKE.snapshot("codex", "Codex", 10, 20)
    del without_plan["planType"]
    (inherited,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": without_plan}, account_plan="unknown", observed_at=datetime.now(UTC)
    )
    assert inherited.plan is None


def test_a_plan_outside_the_contract_is_never_forwarded():
    oversized = FAKE.snapshot("codex", "Codex", 10, 20)
    oversized["planType"] = "p" * 41
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": oversized}, account_plan=None, observed_at=datetime.now(UTC)
    )
    assert (report.status, report.limit_id, report.plan) == ("unavailable", "probe", None)
    assert "plan" in report.detail

def _write_snapshot(path: Path, **overrides) -> dict:
    document = {
        "source": "claude-code-statusline",
        "observed_at": (datetime.now(UTC) - timedelta(minutes=3)).replace(microsecond=0).isoformat(),
        "windows": {
            "five_hour": {"used_percentage": 23.5, "resets_at": 1_790_000_000},
            "seven_day": {"used_percentage": None, "resets_at": None},
        },
    }
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


async def test_the_status_line_snapshot_becomes_a_claude_code_report(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    document = _write_snapshot(snapshot)
    report = await probe_claude_snapshot(snapshot)

    assert report.provider == "claude_code"
    assert report.source == "claude_code_statusline"
    assert report.status == "ok"
    assert report.limit_id == "default"
    assert report.observed_at == datetime.fromisoformat(document["observed_at"])
    assert [(w.key, w.used_percent, w.window_minutes, w.resets_at) for w in report.windows] == [
        ("five_hour", 23.5, 300, datetime.fromtimestamp(1_790_000_000, UTC)),
        ("seven_day", None, 10080, None),
    ]
    assert report.plan is None and report.credits is None and report.limit_reached is None


async def test_a_missing_status_line_snapshot_is_unavailable_with_an_explanation(tmp_path: Path):
    report = await probe_claude_snapshot(tmp_path / "absent.json")
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert report.windows == []
    assert "absent" in report.detail
    assert "ligne d'état" in report.detail


@pytest.mark.parametrize(
    "content",
    [
        "{pas du json",
        json.dumps([1, 2]),
        json.dumps({"source": "autre-chose", "observed_at": "2026-09-24T08:00:00+00:00", "windows": {}}),
        json.dumps({"source": "claude-code-statusline", "observed_at": 12, "windows": {}}),
        json.dumps(
            {
                "source": "claude-code-statusline",
                "observed_at": "2026-09-24T08:00:00+00:00",
                "windows": {"five_hour": {"used_percentage": "beaucoup", "resets_at": None}},
            }
        ),
        json.dumps(
            {
                "source": "claude-code-statusline",
                "observed_at": "2026-09-24T08:00:00+00:00",
                "windows": {"five_hour": {"used_percentage": 12, "resets_at": 1e30}},
            }
        ),
    ],
)
async def test_an_unreadable_snapshot_is_unavailable_and_never_raises(tmp_path: Path, content: str):
    snapshot = tmp_path / "claude-code.json"
    snapshot.write_text(content, encoding="utf-8")
    report = await probe_claude_snapshot(snapshot)
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert report.windows == []


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"observed_at": "2026-09-24T08:00:00"}, "observed_at"),
        ({"observed_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat()}, "observed_at"),
        ({"windows": {"five_hour": {"used_percentage": 150, "resets_at": None}}}, "used_percent"),
    ],
)
async def test_a_snapshot_outside_the_contract_is_unavailable(tmp_path: Path, overrides, field):
    snapshot = tmp_path / "claude-code.json"
    _write_snapshot(snapshot, **overrides)
    report = await probe_claude_snapshot(snapshot)
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert field in report.detail


async def test_an_oversized_or_directory_snapshot_is_unavailable(tmp_path: Path):
    large = tmp_path / "large.json"
    large.write_text(" " * (quotas.MAX_SNAPSHOT_BYTES + 1), encoding="ascii")
    assert (await probe_claude_snapshot(large)).status == "unavailable"
    directory = tmp_path / "dossier.json"
    directory.mkdir()
    assert (await probe_claude_snapshot(directory)).status == "unavailable"


# --------------------------------------------------------------------------
# Lot de relevés
# --------------------------------------------------------------------------
