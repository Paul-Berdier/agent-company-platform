"""Contrats du Lot F : automatisations planifiées, calendrier, budgets et alertes.

Ces tests portent autant sur les **refus** que sur les acceptations. Une
planification que l'évaluateur ne sait pas calculer doit être rejetée à
l'écriture : la laisser entrer produirait une automatisation muette, qui ne se
déclencherait jamais sans que rien ne le signale à qui l'a créée.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import acp_contracts
from acp_contracts import (
    ALERT_ACKNOWLEDGE_COMMENT_MAX,
    BUDGET_LIMIT_NAMES,
    MAX_BUDGET_COUNTER,
    MAX_BUDGET_COST,
    WEBHOOK_MAX_PAYLOAD_DEPTH,
    WEBHOOK_MAX_PAYLOAD_NODES,
    AlertAcknowledge,
    AlertSummary,
    AutomationCreate,
    AutomationDetail,
    AutomationMissionAutonomy,
    AutomationMissionBudget,
    AutomationMissionResource,
    AutomationMissionTemplate,
    AutomationRunSummary,
    AutomationSchedule,
    AutomationSummary,
    AutomationWebhookRotationRequest,
    AutomationWebhookSecret,
    AutomationWebhookStatus,
    AutomationWebhookTrigger,
    AutomationUpdate,
    BudgetConsumptionSummary,
    BudgetConsumptionTotals,
    BudgetMissionConsumption,
    BudgetMutationResult,
    BudgetPermitRequest,
    BudgetProviderConsumption,
    BudgetUsageDelta,
    BudgetVerdict,
    CalendarEntry,
    CronExpression,
    IntervalSchedule,
    MissionCreate,
    NotificationPreferences,
    NotificationPreferencesSummary,
    ProjectBudgetPolicy,
    ProjectBudgetPolicySummary,
    ProviderBudgetLimit,
    resolve_timezone,
)

NOW = datetime(2026, 9, 13, 8, 30, tzinfo=UTC)
TYPESCRIPT_MIRROR = Path(__file__).resolve().parents[1] / "typescript" / "index.ts"


# --- Fabriques ---------------------------------------------------------------


def _mission_template(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Recette nocturne",
        "objective": "Rejouer la suite de bout en bout chaque nuit",
        "expected_outcome": "Un rapport de recette publié avant 07:00",
        "acceptance_criteria": ["la suite est verte"],
        "autonomy": {"mode": "bounded"},
        "budget": {"max_tool_calls": 50},
        "duration_seconds": 3_600,
    }
    payload.update(overrides)
    return payload


def _automation_create(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Recette nocturne",
        "schedule": {"kind": "cron", "expression": "30 2 * * *"},
        "mission_template": _mission_template(),
    }
    payload.update(overrides)
    return payload


def _automation_summary(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Recette nocturne",
        "description": "Recette complète chaque nuit",
        "schedule": {"kind": "cron", "expression": "30 2 * * *"},
        "enabled": False,
        "catchup_policy": "skip",
        "max_concurrent_runs": 1,
        "next_run_at": None,
        "created_at": NOW,
    }
    payload.update(overrides)
    return payload


def _automation_run(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "33333333-3333-3333-3333-333333333333",
        "automation_id": "11111111-1111-1111-1111-111111111111",
        "fire_key": "a" * 32,
        "scheduled_for": NOW,
        "fired_at": NOW,
        "task_id": None,
        "trigger_kind": "manual",
        "outcome": "launched",
        "detail": "",
        "completion_status": None,
    }
    payload.update(overrides)
    return payload


def _calendar_entry(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "occurs_at_utc": datetime(2026, 7, 1, 0, 30, tzinfo=UTC),
        "occurs_at_local": "2026-07-01T02:30:00+02:00",
        "timezone": "Europe/Paris",
        "utc_offset_minutes": 120,
        "automation_id": "11111111-1111-1111-1111-111111111111",
        "automation_name": "Recette nocturne",
        "state": "planned",
    }
    payload.update(overrides)
    return payload


def _alert(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "44444444-4444-4444-4444-444444444444",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "kind": "budget.exceeded",
        "severity": "critical",
        "title": "Budget dépassé",
        "detail": "",
        "task_id": None,
        "automation_id": None,
        "acknowledged_at": None,
        "acknowledged_by_user_id": None,
        "acknowledgement_comment": "",
        "created_at": NOW,
    }
    payload.update(overrides)
    return payload


def _budget_usage_delta(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report_id": "provider-report-123",
        "permit_id": "permit-123",
        "provider": "OpenAI",
        "phase": "execution",
        "source": "provider",
        "tool_calls": 0,
    }
    payload.update(overrides)
    return payload


def _budget_permit(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "permit_id": "permit-123",
        "provider": "OpenAI",
        "phase": "execution",
        "tool_calls": 1,
    }
    payload.update(overrides)
    return payload


def _messages(error: ValidationError) -> list[str]:
    """Messages produits par nos validateurs, sans l'écho pydantic de l'entrée."""

    return [item["msg"] for item in error.errors()]


# --- Planification -----------------------------------------------------------


def test_cron_schedule_is_accepted_and_exposes_its_parsed_expression() -> None:
    schedule = AutomationSchedule(kind="cron", expression="30 2 * * *")

    parsed = schedule.parsed()

    assert isinstance(parsed, CronExpression)
    assert parsed.minutes == frozenset({30})
    assert parsed.hours == frozenset({2})
    assert schedule.timezone == "Europe/Paris"


def test_interval_schedule_is_accepted_and_exposes_its_parsed_expression() -> None:
    schedule = AutomationSchedule(kind="interval", expression="900")

    parsed = schedule.parsed()

    assert isinstance(parsed, IntervalSchedule)
    assert parsed.seconds == 900


def test_invalid_cron_expression_names_the_faulty_field() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AutomationSchedule(kind="cron", expression="99 2 * * *")

    assert any("minute" in message for message in _messages(excinfo.value))


def test_rejection_message_never_echoes_the_submitted_expression() -> None:
    expression = "99 2 * * *"

    with pytest.raises(ValidationError) as excinfo:
        AutomationSchedule(kind="cron", expression=expression)

    assert all(expression not in message for message in _messages(excinfo.value))


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AutomationSchedule(
            kind="cron", expression="30 2 * * *", timezone="Europe/Atlantide"
        )

    messages = _messages(excinfo.value)
    assert any("fuseau" in message for message in messages)
    assert all("Atlantide" not in message for message in messages)


def test_cron_without_any_occurrence_is_rejected() -> None:
    # Le 30 février n'arrive jamais : sans ce contrôle, l'automatisation serait
    # enregistrée et n'aurait plus jamais de prochaine occurrence.
    with pytest.raises(ValidationError) as excinfo:
        AutomationSchedule(kind="cron", expression="0 0 30 2 *")

    assert any("occurrence" in message for message in _messages(excinfo.value))


def test_interval_out_of_bounds_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AutomationSchedule(kind="interval", expression="30")

    assert any("intervalle" in message for message in _messages(excinfo.value))


def test_interval_expression_must_be_a_number_of_seconds() -> None:
    with pytest.raises(ValidationError):
        AutomationSchedule(kind="interval", expression="30 2 * * *")


def test_unknown_schedule_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AutomationSchedule(kind="rrule", expression="30 2 * * *")


# --- Création et mise à jour --------------------------------------------------


def test_automation_create_defaults_to_skip_and_a_single_run() -> None:
    automation = AutomationCreate(**_automation_create())

    assert automation.catchup_policy == "skip"
    assert automation.max_concurrent_runs == 1
    assert automation.description == ""


@pytest.mark.parametrize("value", [0, 6, -1])
def test_max_concurrent_runs_out_of_range_is_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        AutomationCreate(**_automation_create(max_concurrent_runs=value))


def test_unknown_catchup_policy_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AutomationCreate(**_automation_create(catchup_policy="run_all"))


@pytest.mark.parametrize(
    "payload",
    [
        _automation_create(typo=True),
        _automation_create(
            schedule={
                "kind": "cron",
                "expression": "30 2 * * *",
                "unexpected": True,
            }
        ),
        _automation_create(
            mission_template=_mission_template(unexpected="ignored auparavant")
        ),
        _automation_create(
            mission_template=_mission_template(
                autonomy={"mode": "bounded", "unexpected": True}
            )
        ),
        _automation_create(
            mission_template=_mission_template(
                resources=[
                    {
                        "kind": "repository",
                        "identifier": "acme/service",
                        "unexpected": True,
                    }
                ]
            )
        ),
        _automation_create(
            mission_template=_mission_template(
                budget={"max_tool_calls": 50, "unexpected": True}
            )
        ),
    ],
)
def test_automation_inputs_forbid_unknown_fields_at_every_level(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        AutomationCreate(**payload)


@pytest.mark.parametrize("value", [True, "2"])
def test_automation_concurrency_is_a_strict_integer(value: Any) -> None:
    with pytest.raises(ValidationError):
        AutomationCreate(**_automation_create(max_concurrent_runs=value))


@pytest.mark.parametrize("field", ["duration_seconds", "priority"])
@pytest.mark.parametrize("value", [True, "2"])
def test_mission_template_numbers_are_strict(
    field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        AutomationMissionTemplate(**_mission_template(**{field: value}))


@pytest.mark.parametrize("field", ["max_cost", "max_tokens", "max_tool_calls"])
@pytest.mark.parametrize("value", [True, "12"])
def test_mission_budget_numbers_are_strict(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        AutomationMissionTemplate(
            **_mission_template(budget={field: value})
        )


def test_mission_budget_cost_cannot_exceed_the_ledger_capacity() -> None:
    with pytest.raises(ValidationError, match="less than or equal"):
        AutomationMissionTemplate(
            **_mission_template(budget={"max_cost": MAX_BUDGET_COST + 1})
        )


@pytest.mark.parametrize("field", ["max_tokens", "max_tool_calls"])
def test_mission_budget_counter_cannot_exceed_cross_runtime_capacity(field: str) -> None:
    with pytest.raises(ValidationError, match="less than or equal"):
        AutomationMissionTemplate(
            **_mission_template(budget={field: MAX_BUDGET_COUNTER + 1})
        )


def test_automation_name_cannot_be_blank() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AutomationCreate(**_automation_create(name="   "))

    assert any("nom" in message for message in _messages(excinfo.value))


def test_automation_update_accepts_an_empty_patch() -> None:
    patch = AutomationUpdate()

    assert patch.model_dump(exclude_unset=True) == {}


def test_automation_update_validates_the_schedule_it_carries() -> None:
    with pytest.raises(ValidationError):
        AutomationUpdate(schedule={"kind": "cron", "expression": "0 0 30 2 *"})


def test_automation_update_exposes_the_same_fields_as_creation() -> None:
    assert set(AutomationUpdate.model_fields) == set(AutomationCreate.model_fields)
    assert all(
        field.default is None for field in AutomationUpdate.model_fields.values()
    )


@pytest.mark.parametrize("field", list(AutomationUpdate.model_fields))
def test_automation_update_rejects_explicit_null_for_every_field(field: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        AutomationUpdate(**{field: None})

    assert any("null" in message for message in _messages(excinfo.value))


# --- Gabarit de mission -------------------------------------------------------


def test_mission_template_mirrors_mission_create_without_project_id() -> None:
    assert set(AutomationMissionTemplate.model_fields) == (
        set(MissionCreate.model_fields) - {"project_id"}
    )


def test_mission_template_becomes_a_mission_create() -> None:
    template = AutomationMissionTemplate(**_mission_template())

    mission = template.to_mission_create("22222222-2222-2222-2222-222222222222")

    assert isinstance(mission, MissionCreate)
    assert mission.project_id == "22222222-2222-2222-2222-222222222222"
    assert mission.title == "Recette nocturne"


def test_mission_template_rejects_an_empty_acceptance_criterion() -> None:
    with pytest.raises(ValidationError):
        AutomationMissionTemplate(**_mission_template(acceptance_criteria=["  "]))


def test_mission_template_refuses_a_free_dictionary_in_an_automation() -> None:
    with pytest.raises(ValidationError):
        AutomationCreate(**_automation_create(mission_template={"title": "trop court"}))


# --- Lectures -----------------------------------------------------------------


def test_automation_summary_carries_its_next_run() -> None:
    summary = AutomationSummary(**_automation_summary(next_run_at=NOW, created_at=NOW))

    assert summary.next_run_at == NOW
    assert summary.enabled is False
    assert summary.catchup_policy == "skip"


def test_automation_summary_accepts_an_unscheduled_automation() -> None:
    summary = AutomationSummary(**_automation_summary())

    assert summary.next_run_at is None


@pytest.mark.parametrize(
    "field",
    [
        "description",
        "enabled",
        "catchup_policy",
        "max_concurrent_runs",
        "next_run_at",
        "created_at",
    ],
)
def test_automation_summary_requires_every_persisted_field(field: str) -> None:
    payload = _automation_summary()
    payload.pop(field)

    with pytest.raises(ValidationError):
        AutomationSummary(**payload)


def test_automation_detail_carries_its_template_and_recent_runs() -> None:
    detail = AutomationDetail(
        **_automation_summary(),
        mission_template=_mission_template(),
        recent_runs=[_automation_run()],
    )

    assert isinstance(detail.mission_template, AutomationMissionTemplate)
    assert detail.recent_runs[0].outcome == "launched"
    assert set(AutomationSummary.model_fields) <= set(AutomationDetail.model_fields)


def test_automation_detail_requires_an_explicit_recent_run_list() -> None:
    with pytest.raises(ValidationError):
        AutomationDetail(
            **_automation_summary(),
            mission_template=_mission_template(),
        )


def test_automation_run_outcome_is_constrained() -> None:
    with pytest.raises(ValidationError):
        AutomationRunSummary(**_automation_run(outcome="peut_être"))


def test_automation_run_records_catchup_skip_without_a_task() -> None:
    run = AutomationRunSummary(
        **_automation_run(
            outcome="skipped_catchup",
            task_id=None,
            completion_status=None,
        )
    )

    assert run.outcome == "skipped_catchup"
    assert run.task_id is None


@pytest.mark.parametrize(
    "status",
    ["blocked", "succeeded", "failed", "cancelled", "interrupted"],
)
def test_automation_run_exposes_a_constrained_terminal_status(status: str) -> None:
    run = AutomationRunSummary(**_automation_run(completion_status=status))

    assert run.completion_status == status


def test_automation_run_rejects_a_non_terminal_completion_status() -> None:
    with pytest.raises(ValidationError):
        AutomationRunSummary(**_automation_run(completion_status="running"))


def test_automation_run_keeps_the_nominal_and_the_real_instant_apart() -> None:
    run = AutomationRunSummary(
        **_automation_run(
            scheduled_for=NOW,
            fired_at=datetime(2026, 9, 13, 8, 31, tzinfo=UTC),
            task_id=None,
            outcome="skipped_concurrency",
            detail="déjà une exécution en cours",
        )
    )

    assert run.scheduled_for != run.fired_at
    assert run.task_id is None


@pytest.mark.parametrize(
    "value",
    [
        "a" * 31,
        "a" * 33,
        "A" * 32,
        "g" * 32,
        "not-a-fire-key",
    ],
)
def test_automation_run_rejects_a_malformed_fire_key(value: str) -> None:
    with pytest.raises(ValidationError):
        AutomationRunSummary(**_automation_run(fire_key=value))


def test_automation_run_accepts_the_canonical_fire_key_shape() -> None:
    run = AutomationRunSummary(**_automation_run(fire_key="0123456789abcdef" * 2))

    assert run.fire_key == "0123456789abcdef" * 2


@pytest.mark.parametrize(
    "field", ["task_id", "trigger_kind", "detail", "completion_status"]
)
def test_automation_run_requires_nullable_and_empty_persisted_fields(
    field: str,
) -> None:
    payload = _automation_run()
    payload.pop(field)

    with pytest.raises(ValidationError):
        AutomationRunSummary(**payload)


# --- Calendrier ---------------------------------------------------------------


def test_calendar_entry_keeps_a_positive_offset() -> None:
    entry = CalendarEntry(**_calendar_entry())

    assert entry.utc_offset_minutes == 120
    assert entry.occurs_at_local.endswith("+02:00")


def test_calendar_entry_keeps_a_negative_offset() -> None:
    entry = CalendarEntry(
        **_calendar_entry(
            occurs_at_utc=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
            occurs_at_local="2026-07-01T08:00:00-04:00",
            timezone="America/New_York",
            utc_offset_minutes=-240,
        )
    )

    assert entry.utc_offset_minutes == -240
    assert entry.occurs_at_local.endswith("-04:00")


def test_calendar_entry_rejects_a_local_time_without_offset() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(**_calendar_entry(occurs_at_local="2026-07-01T02:30:00"))

    assert any("décalage" in message for message in _messages(excinfo.value))


def test_calendar_entry_rejects_an_offset_that_contradicts_the_local_time() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(**_calendar_entry(utc_offset_minutes=60))

    assert any("décalage" in message for message in _messages(excinfo.value))


def test_calendar_entry_rejects_an_unknown_timezone() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(**_calendar_entry(timezone="Europe/Atlantide"))

    assert any("fuseau" in message for message in _messages(excinfo.value))


def test_calendar_entry_rejects_local_and_utc_values_for_distinct_instants() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(
            **_calendar_entry(occurs_at_local="2026-07-01T03:30:00+02:00")
        )

    assert any("même instant" in message for message in _messages(excinfo.value))


def test_calendar_entry_rejects_an_offset_impossible_in_the_named_timezone() -> None:
    # +01:00 désigne bien le même instant que 00:30Z, mais Paris est à +02:00
    # ce jour-là. La concordance arithmétique seule ne suffit donc pas.
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(
            **_calendar_entry(
                occurs_at_local="2026-07-01T01:30:00+01:00",
                utc_offset_minutes=60,
            )
        )

    assert any("fuseau IANA" in message for message in _messages(excinfo.value))


def test_calendar_entry_rejects_a_naive_utc_instant() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CalendarEntry(
            **_calendar_entry(occurs_at_utc=datetime(2026, 7, 1, 0, 30))
        )

    assert any("fuseau" in message for message in _messages(excinfo.value))


def test_calendar_entry_outcome_is_constrained() -> None:
    with pytest.raises(ValidationError):
        CalendarEntry(**_calendar_entry(outcome="invented"))


def test_calendar_entry_from_occurrence_follows_the_summer_transition() -> None:
    # Deux entrées du même calendrier, de part et d'autre du dernier dimanche de
    # mars : le décalage n'est pas une constante du fuseau.
    winter = CalendarEntry.from_occurrence(
        occurs_at_utc=datetime(2026, 3, 28, 1, 30, tzinfo=UTC),
        automation_id="11111111-1111-1111-1111-111111111111",
        automation_name="Recette nocturne",
        state="planned",
    )
    summer = CalendarEntry.from_occurrence(
        occurs_at_utc=datetime(2026, 4, 4, 0, 30, tzinfo=UTC),
        automation_id="11111111-1111-1111-1111-111111111111",
        automation_name="Recette nocturne",
        state="planned",
    )

    assert winter.utc_offset_minutes == 60
    assert summer.utc_offset_minutes == 120
    assert winter.occurs_at_local.startswith("2026-03-28T02:30:00")
    assert summer.occurs_at_local.startswith("2026-04-04T02:30:00")
    assert winter.timezone == "Europe/Paris"


def test_calendar_entry_from_occurrence_keeps_a_western_timezone_negative() -> None:
    entry = CalendarEntry.from_occurrence(
        occurs_at_utc=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        timezone="America/New_York",
        automation_id="11111111-1111-1111-1111-111111111111",
        automation_name="Recette nocturne",
        state="past",
        task_id="55555555-5555-5555-5555-555555555555",
        outcome="launched",
    )

    assert entry.utc_offset_minutes == -300
    assert entry.occurs_at_local == "2026-01-15T07:00:00-05:00"
    assert entry.state == "past"
    assert entry.task_id == "55555555-5555-5555-5555-555555555555"


def test_calendar_entry_from_occurrence_rejects_an_unknown_timezone() -> None:
    with pytest.raises(ValueError):
        CalendarEntry.from_occurrence(
            occurs_at_utc=NOW,
            timezone="Europe/Atlantide",
            automation_id="11111111-1111-1111-1111-111111111111",
            automation_name="Recette nocturne",
            state="planned",
        )


def test_calendar_entry_state_is_constrained() -> None:
    with pytest.raises(ValidationError):
        CalendarEntry(**_calendar_entry(state="future"))


# --- Webhook authentifié ------------------------------------------------------


def test_webhook_trigger_keeps_an_idempotency_key_and_json_payload() -> None:
    trigger = AutomationWebhookTrigger(
        event_id="github:delivery:123",
        payload={"ref": "refs/heads/main", "forced": False, "commits": 2},
    )

    assert trigger.event_id == "github:delivery:123"
    assert trigger.payload["forced"] is False


def test_webhook_trigger_rejects_an_empty_event_id() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookTrigger(event_id="")


def test_webhook_trigger_rejects_non_json_payload_values() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookTrigger(event_id="delivery-1", payload={"value": object()})


def test_webhook_trigger_rejects_excessive_payload_depth() -> None:
    payload: dict[str, Any] = {}
    cursor = payload
    for _ in range(WEBHOOK_MAX_PAYLOAD_DEPTH + 1):
        child: dict[str, Any] = {}
        cursor["child"] = child
        cursor = child

    with pytest.raises(ValidationError, match="trop profond"):
        AutomationWebhookTrigger(event_id="delivery-1", payload=payload)


def test_webhook_trigger_rejects_excessive_payload_nodes() -> None:
    payload = {
        f"value-{index}": index
        for index in range(WEBHOOK_MAX_PAYLOAD_NODES + 1)
    }

    with pytest.raises(ValidationError, match="trop de valeurs"):
        AutomationWebhookTrigger(event_id="delivery-1", payload=payload)


def test_webhook_trigger_forbids_credentials_and_other_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookTrigger(
            event_id="delivery-1",
            payload={},
            secret="ne-doit-jamais-voyager-dans-le-corps",
        )


def test_webhook_public_status_never_contains_the_secret() -> None:
    status = AutomationWebhookStatus(
        enabled=True,
        secret_configured=True,
        endpoint_path="/api/v1/automations/abc/webhook",
        rotated_at=None,
    )

    assert set(status.model_dump()) == {
        "enabled",
        "secret_configured",
        "endpoint_path",
        "rotated_at",
    }


def test_webhook_rotation_requires_a_256_bit_base64url_client_secret() -> None:
    request = AutomationWebhookRotationRequest(secret="A" * 43)

    assert request.secret == "A" * 43
    for invalid in ("A" * 42, "A" * 42 + "!", "é" * 43):
        with pytest.raises(ValidationError):
            AutomationWebhookRotationRequest(secret=invalid)


def test_webhook_rotation_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookRotationRequest(secret="A" * 43, generated_by="server")


def test_webhook_status_requires_an_explicit_nullable_rotation_time() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookStatus(
            enabled=False,
            secret_configured=False,
            endpoint_path="/api/v1/automations/abc/webhook",
        )


def test_webhook_secret_is_only_carried_by_the_dedicated_response() -> None:
    response = AutomationWebhookSecret(
        enabled=True,
        secret_configured=True,
        endpoint_path="/api/v1/automations/abc/webhook",
        rotated_at=None,
        secret="A" * 43,
    )

    assert response.secret == "A" * 43


@pytest.mark.parametrize("value", ["short", "x" * 201])
def test_webhook_secret_length_is_bounded(value: str) -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookSecret(
            enabled=True,
            secret_configured=True,
            endpoint_path="/api/v1/automations/abc/webhook",
            rotated_at=None,
            secret=value,
        )


def test_webhook_status_boolean_flags_are_strict() -> None:
    with pytest.raises(ValidationError):
        AutomationWebhookStatus(
            enabled=1,
            secret_configured=True,
            endpoint_path="/api/v1/automations/abc/webhook",
            rotated_at=None,
        )


# --- Budgets ------------------------------------------------------------------


def test_unmeasured_budget_verdict_stays_unknown() -> None:
    verdict = BudgetVerdict(state="unknown")

    assert verdict.state == "unknown"
    assert verdict.measured is False
    assert verdict.usage_reported is False
    assert verdict.limit_reached is None
    assert verdict.cost is None
    assert verdict.tokens_input is None
    assert verdict.tokens_output is None
    assert verdict.tool_calls is None


def test_measured_and_usage_reported_are_two_distinct_facts() -> None:
    # La plateforme compte elle-même les appels d'outils : le verdict est mesuré
    # alors même que le fournisseur n'a rapporté aucune consommation.
    verdict = BudgetVerdict(
        state="warning",
        measured=True,
        usage_reported=False,
        limit_reached="max_tool_calls",
        tool_calls=8,
    )

    assert verdict.measured is True
    assert verdict.usage_reported is False


def test_a_non_measured_verdict_cannot_exceed() -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetVerdict(state="exceeded", measured=False, limit_reached="max_tokens")

    assert any("mesur" in message for message in _messages(excinfo.value))


def test_a_non_ok_verdict_names_the_limit_it_reached() -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetVerdict(state="exceeded", measured=True, tool_calls=8)

    assert any("limite" in message for message in _messages(excinfo.value))


def test_budget_verdict_normalises_its_currency() -> None:
    verdict = BudgetVerdict(
        state="ok", measured=True, currency="eur", tool_calls=0
    )

    assert verdict.currency == "EUR"


def test_budget_verdict_saturates_only_with_an_explicit_safe_integer_signal() -> None:
    with pytest.raises(ValidationError):
        BudgetVerdict(
            state="ok",
            measured=True,
            tool_calls=MAX_BUDGET_COUNTER + 1,
        )
    verdict = BudgetVerdict(
        state="ok",
        measured=True,
        tool_calls=MAX_BUDGET_COUNTER,
        saturated_metrics=["tool_calls"],
    )
    assert verdict.saturated_metrics == ["tool_calls"]
    with pytest.raises(ValidationError):
        BudgetVerdict(
            state="ok",
            measured=True,
            tool_calls=42,
            saturated_metrics=["tool_calls"],
        )


def test_budget_limit_names_match_the_mission_budget_fields() -> None:
    assert set(BUDGET_LIMIT_NAMES) <= set(
        acp_contracts.MissionBudget.model_fields
    )


@pytest.mark.parametrize(
    "field, value",
    [("cost", -1.0), ("tokens_input", -1), ("tokens_output", -1), ("tool_calls", -1)],
)
def test_budget_verdict_refuses_negative_quantities(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        BudgetVerdict(state="ok", **{field: value})


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_budget_verdict_refuses_non_finite_costs(value: float) -> None:
    with pytest.raises(ValidationError):
        BudgetVerdict(state="ok", measured=True, cost=value)


@pytest.mark.parametrize(
    "payload",
    [
        {"state": "ok", "measured": False, "cost": 1.0},
        {"state": "ok", "measured": True},
        {
            "state": "ok",
            "measured": True,
            "usage_reported": True,
            "tool_calls": 1,
        },
        {
            "state": "ok",
            "measured": True,
            "limit_reached": "max_cost",
            "cost": 1.0,
        },
        {
            "state": "unknown",
            "measured": False,
            "limit_reached": "max_cost",
        },
    ],
)
def test_budget_verdict_rejects_inconsistent_measurement_facts(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        BudgetVerdict(**payload)


def test_budget_verdict_rejects_an_unknown_limit_name() -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetVerdict(
            state="warning",
            measured=True,
            tool_calls=1,
            limit_reached="daily_cost",
        )

    assert any("inconnu" in message for message in _messages(excinfo.value))


@pytest.mark.parametrize(
    "payload",
    [
        {
            "state": "warning",
            "measured": True,
            "tool_calls": 1,
            "limit_reached": "max_cost",
        },
        {
            "state": "warning",
            "measured": True,
            "tokens_input": 1,
            "limit_reached": "max_tokens",
        },
        {
            "state": "warning",
            "measured": True,
            "cost": 1.0,
            "limit_reached": "max_tool_calls",
        },
    ],
)
def test_budget_verdict_requires_the_quantity_named_by_its_limit(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        BudgetVerdict(**payload)


def test_budget_usage_delta_preserves_unknowns_and_real_zeroes() -> None:
    delta = BudgetUsageDelta(
        **_budget_usage_delta(provider="  platform  ", source="platform")
    )

    assert delta.provider == "platform"
    assert delta.tool_calls == 0
    assert delta.cost is None
    assert delta.tokens_input is None
    assert delta.tokens_output is None
    assert delta.currency is None


def test_budget_usage_delta_normalises_the_currency_of_a_provider_cost() -> None:
    delta = BudgetUsageDelta(
        **_budget_usage_delta(cost=1.5, currency="eur", tool_calls=None)
    )

    assert delta.cost == 1.5
    assert delta.currency == "EUR"


def test_budget_usage_delta_requires_at_least_one_measure() -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetUsageDelta(
            report_id="provider-report-123",
            permit_id="permit-123",
            provider="OpenAI",
            phase="execution",
            source="provider",
        )

    assert any("mesure" in message for message in _messages(excinfo.value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost", True),
        ("cost", "1.5"),
        ("tokens_input", True),
        ("tokens_input", "1"),
        ("tokens_output", True),
        ("tool_calls", "1"),
        ("estimated", 1),
    ],
)
def test_budget_usage_delta_uses_strict_numeric_and_boolean_types(
    field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        BudgetUsageDelta(**_budget_usage_delta(**{field: value}))


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("nan")])
def test_budget_usage_delta_rejects_invalid_costs(value: float) -> None:
    with pytest.raises(ValidationError):
        BudgetUsageDelta(**_budget_usage_delta(cost=value, currency="EUR"))


def test_budget_usage_delta_rejects_cost_above_cross_runtime_capacity() -> None:
    with pytest.raises(ValidationError, match="capacité du ledger"):
        BudgetUsageDelta(
            **_budget_usage_delta(
                cost=MAX_BUDGET_COST + 0.5,
                currency="EUR",
            )
        )


@pytest.mark.parametrize("field", ["tokens_input", "tokens_output", "tool_calls"])
def test_budget_usage_delta_rejects_counter_above_capacity(field: str) -> None:
    with pytest.raises(ValidationError, match="less than or equal"):
        BudgetUsageDelta(
            **_budget_usage_delta(**{field: MAX_BUDGET_COUNTER + 1})
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost": 1.0, "currency": None},
        {"cost": None, "currency": "EUR"},
    ],
)
def test_budget_usage_delta_requires_cost_and_currency_together(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetUsageDelta(**_budget_usage_delta(**overrides))

    assert any("devise" in message for message in _messages(excinfo.value))


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost": 1.0, "currency": "EUR"},
        {"tokens_input": 10},
        {"tokens_output": 20},
    ],
)
def test_platform_usage_can_only_report_tool_calls(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        BudgetUsageDelta(
            **_budget_usage_delta(source="platform", **overrides)
        )

    assert any("plateforme" in message for message in _messages(excinfo.value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("phase", "billing"),
        ("source", "user"),
        ("report_id", ""),
        ("provider", "   "),
    ],
)
def test_budget_usage_delta_rejects_invalid_identity_fields(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        BudgetUsageDelta(**_budget_usage_delta(**{field: value}))


def test_budget_permit_reserves_a_bounded_future_effect() -> None:
    permit = BudgetPermitRequest(
        **_budget_permit(cost=0.25, currency="eur", tool_calls=None)
    )

    assert permit.permit_id == "permit-123"
    assert permit.phase == "execution"
    assert permit.cost == 0.25
    assert permit.currency == "EUR"


def test_budget_permit_requires_at_least_one_reserved_quantity() -> None:
    with pytest.raises(ValidationError):
        BudgetPermitRequest(
            permit_id="permit-123",
            provider="OpenAI",
            phase="execution",
        )


def test_budget_permit_rejects_cost_above_cross_runtime_capacity() -> None:
    with pytest.raises(ValidationError, match="capacité du ledger"):
        BudgetPermitRequest(
            **_budget_permit(
                cost=MAX_BUDGET_COST + 0.5,
                currency="EUR",
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cost": 1.0, "currency": None},
        {"cost": None, "currency": "EUR"},
        {"phase": "billing"},
        {"permit_id": ""},
        {"provider": "   "},
    ],
)
def test_budget_permit_rejects_incomplete_or_invalid_reservations(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        BudgetPermitRequest(**_budget_permit(**overrides))


def test_budget_mutation_result_carries_idempotence_and_the_verdict() -> None:
    result = BudgetMutationResult(
        accepted=True,
        idempotent=True,
        permit_allowed=True,
        verdict={"state": "ok", "measured": True, "tool_calls": 0},
    )

    assert result.accepted is True
    assert result.idempotent is True
    assert result.permit_allowed is True
    assert result.verdict.state == "ok"


def test_budget_usage_requires_a_non_nullable_permit_id() -> None:
    missing = _budget_usage_delta()
    missing.pop("permit_id")
    with pytest.raises(ValidationError):
        BudgetUsageDelta(**missing)
    with pytest.raises(ValidationError):
        BudgetUsageDelta(**_budget_usage_delta(permit_id=None))


def test_budget_consumption_summary_preserves_unknowns_by_dimension() -> None:
    summary = BudgetConsumptionSummary(
        project_id="project-1",
        accounting_day=date(2026, 9, 14),
        timezone="Europe/Paris",
        totals={
            "reports": 1,
            "pending_reservations": 1,
            "cost": None,
            "currency": None,
            "tokens_input": None,
            "tokens_output": None,
            "tool_calls": 1,
            "usage_reported": False,
            "estimated": False,
        },
        missions=[],
        providers=[],
    )

    assert summary.totals.cost is None
    assert summary.totals.tool_calls == 1
    assert summary.accounting_day == date(2026, 9, 14)


def test_empty_consumption_bucket_cannot_claim_a_zero_measure() -> None:
    with pytest.raises(ValidationError):
        BudgetConsumptionTotals(
            reports=0,
            pending_reservations=0,
            cost=0.0,
            currency="EUR",
            usage_reported=False,
            estimated=False,
        )


def test_consumption_totals_refuse_unsafe_or_false_saturation() -> None:
    common = {
        "reports": 1,
        "pending_reservations": 0,
        "usage_reported": False,
        "estimated": False,
    }
    with pytest.raises(ValidationError):
        BudgetConsumptionTotals(
            **common,
            tool_calls=MAX_BUDGET_COUNTER + 1,
        )
    totals = BudgetConsumptionTotals(
        **common,
        tool_calls=MAX_BUDGET_COUNTER,
        saturated_metrics=["tool_calls"],
    )
    assert totals.saturated_metrics == ["tool_calls"]
    with pytest.raises(ValidationError):
        BudgetConsumptionTotals(
            **common,
            tool_calls=1,
            saturated_metrics=["tool_calls"],
        )


@pytest.mark.parametrize(
    "budget",
    [
        {},
        {"max_cost": float("inf")},
        {"max_cost": float("nan")},
    ],
)
def test_mission_budget_requires_a_real_finite_limit(
    budget: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        AutomationMissionTemplate(**_mission_template(budget=budget))


def test_project_budget_policy_carries_daily_and_provider_limits() -> None:
    policy = ProjectBudgetPolicy(
        timezone="America/New_York",
        daily_budget={"max_cost": 25.0},
        provider_budgets=[
            {"provider": "  OpenAI  ", "budget": {"max_tokens": 100_000}},
            {"provider": "Hermes", "budget": {"max_tool_calls": 500}},
        ],
        max_concurrent_missions=3,
        max_retries_per_mission=2,
        max_spawned_agents_per_run=6,
    )

    assert policy.daily_budget is not None
    assert policy.daily_budget.max_cost == 25.0
    assert policy.timezone == "America/New_York"
    assert [limit.provider for limit in policy.provider_budgets] == [
        "OpenAI",
        "Hermes",
    ]


def test_project_budget_policy_rejects_duplicate_providers_case_insensitively() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ProjectBudgetPolicy(
            provider_budgets=[
                {"provider": "OpenAI", "budget": {"max_cost": 10.0}},
                {"provider": " openai ", "budget": {"max_cost": 20.0}},
            ]
        )

    assert any("fournisseur" in message for message in _messages(excinfo.value))


def test_project_budget_policy_rejects_an_unknown_daily_timezone() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ProjectBudgetPolicy(timezone="Europe/Atlantide")

    assert any("fuseau" in message for message in _messages(excinfo.value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_concurrent_missions", 0),
        ("max_concurrent_missions", True),
        ("max_retries_per_mission", -1),
        ("max_retries_per_mission", "2"),
        ("max_spawned_agents_per_run", 0),
        ("max_spawned_agents_per_run", False),
    ],
)
def test_project_budget_policy_rejects_invalid_operational_bounds(
    field: str, value: Any
) -> None:
    with pytest.raises(ValidationError):
        ProjectBudgetPolicy(**{field: value})


def test_provider_budget_limit_rejects_a_blank_provider() -> None:
    with pytest.raises(ValidationError):
        ProviderBudgetLimit(provider="   ", budget={"max_cost": 10.0})


def test_project_budget_policy_summary_adds_persistence_metadata() -> None:
    summary = ProjectBudgetPolicySummary(
        project_id="22222222-2222-2222-2222-222222222222",
        updated_at=NOW,
    )

    assert summary.timezone == "Europe/Paris"
    assert summary.project_id == "22222222-2222-2222-2222-222222222222"
    assert summary.updated_at == NOW


def test_project_budget_policy_summary_requires_its_update_time() -> None:
    with pytest.raises(ValidationError):
        ProjectBudgetPolicySummary(
            project_id="22222222-2222-2222-2222-222222222222"
        )


# --- Alertes ------------------------------------------------------------------


def test_alert_summary_defaults_to_an_open_alert() -> None:
    alert = AlertSummary(**_alert())

    assert alert.acknowledged_at is None
    assert alert.detail == ""
    assert alert.task_id is None
    assert alert.automation_id is None
    assert alert.acknowledged_by_user_id is None
    assert alert.acknowledgement_comment == ""


@pytest.mark.parametrize(
    "field",
    [
        "detail",
        "task_id",
        "automation_id",
        "acknowledged_at",
        "acknowledged_by_user_id",
        "acknowledgement_comment",
        "created_at",
    ],
)
def test_alert_summary_requires_every_persisted_field(field: str) -> None:
    payload = _alert()
    payload.pop(field)

    with pytest.raises(ValidationError):
        AlertSummary(**payload)


@pytest.mark.parametrize("field", ["created_at", "acknowledged_at"])
def test_alert_summary_rejects_naive_timestamps(field: str) -> None:
    with pytest.raises(ValidationError):
        AlertSummary(**_alert(**{field: datetime(2026, 9, 13, 8, 30)}))


def test_alert_severity_is_constrained() -> None:
    with pytest.raises(ValidationError):
        AlertSummary(**_alert(severity="fatal"))


def test_alert_acknowledge_is_empty_by_default() -> None:
    assert AlertAcknowledge().comment == ""


def test_alert_acknowledge_keeps_a_short_comment() -> None:
    assert AlertAcknowledge(comment="  vu  ").comment == "vu"


def test_alert_acknowledge_accepts_the_documented_comment_boundary() -> None:
    comment = "x" * ALERT_ACKNOWLEDGE_COMMENT_MAX

    assert AlertAcknowledge(comment=comment).comment == comment


def test_alert_acknowledge_refuses_a_long_comment() -> None:
    with pytest.raises(ValidationError):
        AlertAcknowledge(comment="x" * (ALERT_ACKNOWLEDGE_COMMENT_MAX + 1))


def test_alert_acknowledge_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AlertAcknowledge(comment="vu", actor_id="ignored auparavant")


def test_notification_preferences_expose_only_the_real_in_app_channel() -> None:
    preferences = NotificationPreferences()

    assert preferences.channel == "in_app"
    assert preferences.enabled is True
    assert preferences.minimum_severity == "warning"
    assert preferences.budget_alerts is True
    assert preferences.automation_failures is True
    assert preferences.storage_alerts is True


@pytest.mark.parametrize("channel", ["email", "webhook", "sms"])
def test_notification_preferences_reject_unavailable_channels(channel: str) -> None:
    with pytest.raises(ValidationError):
        NotificationPreferences(channel=channel)


@pytest.mark.parametrize(
    "payload",
    [
        {"minimum_severity": "fatal"},
        {"enabled": 1},
        {"budget_alerts": "yes"},
        {"automation_failures": 0},
        {"storage_alerts": None},
        {"email": "ops@example.test"},
    ],
)
def test_notification_preferences_reject_invalid_or_invented_settings(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        NotificationPreferences(**payload)


def test_notification_preferences_summary_adds_project_and_update_time() -> None:
    summary = NotificationPreferencesSummary(
        project_id="22222222-2222-2222-2222-222222222222",
        updated_at=NOW,
    )

    assert summary.project_id == "22222222-2222-2222-2222-222222222222"
    assert summary.updated_at == NOW


def test_notification_preferences_summary_requires_its_update_time() -> None:
    with pytest.raises(ValidationError):
        NotificationPreferencesSummary(
            project_id="22222222-2222-2222-2222-222222222222"
        )


# --- Miroir TypeScript --------------------------------------------------------


def _typescript_interface_body(source: str, name: str) -> str:
    match = re.search(
        rf"^export interface {name}(?: extends \w+)? \{{\n(?P<body>.*?)^\}}",
        source,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"interface TypeScript « {name} » absente du miroir"
    return match.group("body")


def _typescript_fields(source: str, name: str) -> set[str]:
    """Champs déclarés par une interface du miroir, héritage compris."""

    match = re.search(
        rf"^export interface {name}(?: extends (?P<parent>\w+))? \{{\n(?P<body>.*?)^\}}",
        source,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"interface TypeScript « {name} » absente du miroir"
    fields = set(re.findall(r"^  (\w+)\??:", match.group("body"), re.MULTILINE))
    parent = match.group("parent")
    if parent is not None:
        fields |= _typescript_fields(source, parent)
    return fields


def _typescript_required_and_optional_fields(
    source: str, name: str
) -> tuple[set[str], set[str]]:
    body = _typescript_interface_body(source, name)
    required = set(re.findall(r"^  (\w+):", body, re.MULTILINE))
    optional = set(re.findall(r"^  (\w+)\?:", body, re.MULTILINE))
    return required, optional


@pytest.mark.parametrize(
    "model",
    [
        AutomationSchedule,
        AutomationMissionAutonomy,
        AutomationMissionResource,
        AutomationMissionBudget,
        AutomationMissionTemplate,
        AutomationCreate,
        AutomationUpdate,
        AutomationSummary,
        AutomationRunSummary,
        AutomationDetail,
        CalendarEntry,
        AutomationWebhookTrigger,
        AutomationWebhookRotationRequest,
        AutomationWebhookStatus,
        AutomationWebhookSecret,
        BudgetConsumptionSummary,
        BudgetConsumptionTotals,
        BudgetMissionConsumption,
        BudgetUsageDelta,
        BudgetPermitRequest,
        BudgetProviderConsumption,
        ProviderBudgetLimit,
        ProjectBudgetPolicy,
        ProjectBudgetPolicySummary,
        BudgetVerdict,
        BudgetMutationResult,
        AlertSummary,
        AlertAcknowledge,
        NotificationPreferences,
        NotificationPreferencesSummary,
    ],
)
def test_typescript_mirror_declares_the_same_field_names(
    model: type[BaseModel],
) -> None:
    source = TYPESCRIPT_MIRROR.read_text(encoding="utf-8")

    mirrored = _typescript_fields(source, model.__name__)

    assert mirrored == set(model.model_fields), (
        f"divergence entre pydantic et TypeScript pour {model.__name__} : "
        f"{mirrored ^ set(model.model_fields)}"
    )


@pytest.mark.parametrize(
    "name,required,optional",
    [
        (
            "AutomationScheduleInput",
            {"kind", "expression"},
            {"timezone"},
        ),
        (
            "AutomationMissionAutonomyInput",
            set(),
            {
                "mode",
                "allowed_actions",
                "forbidden_actions",
                "approval_required_actions",
            },
        ),
        (
            "AutomationMissionResourceInput",
            {"kind", "identifier"},
            {"access", "description"},
        ),
        (
            "AutomationMissionBudgetInput",
            set(),
            {"max_cost", "currency", "max_tokens", "max_tool_calls"},
        ),
        (
            "AutomationMissionTemplateInput",
            {
                "title",
                "objective",
                "expected_outcome",
                "acceptance_criteria",
                "autonomy",
                "budget",
                "duration_seconds",
            },
            {
                "resources",
                "team_id",
                "agent_instance_id",
                "priority",
                "required_capabilities",
            },
        ),
        (
            "AutomationCreate",
            {"name", "schedule", "mission_template"},
            {"description", "catchup_policy", "max_concurrent_runs"},
        ),
    ],
)
def test_typescript_input_interfaces_preserve_python_default_optionality(
    name: str, required: set[str], optional: set[str]
) -> None:
    source = TYPESCRIPT_MIRROR.read_text(encoding="utf-8")

    actual_required, actual_optional = _typescript_required_and_optional_fields(
        source, name
    )

    assert actual_required == required
    assert actual_optional == optional


def test_typescript_automation_update_is_optional_but_never_nullable() -> None:
    source = TYPESCRIPT_MIRROR.read_text(encoding="utf-8")
    body = _typescript_interface_body(source, "AutomationUpdate")
    required, optional = _typescript_required_and_optional_fields(
        source, "AutomationUpdate"
    )

    assert required == set()
    assert optional == set(AutomationUpdate.model_fields)
    assert "| null" not in body


def test_typescript_budget_usage_requires_a_non_nullable_permit_id() -> None:
    source = TYPESCRIPT_MIRROR.read_text(encoding="utf-8")
    body = _typescript_interface_body(source, "BudgetUsageDelta")
    required, optional = _typescript_required_and_optional_fields(
        source, "BudgetUsageDelta"
    )

    assert "permit_id" in required
    assert "permit_id" not in optional
    assert "permit_id: string;" in body


# --- Exports ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "ALERT_ACKNOWLEDGE_COMMENT_MAX",
        "AlertAcknowledge",
        "AlertSeverity",
        "AlertSummary",
        "AutomationCatchupPolicy",
        "AutomationCreate",
        "AutomationDetail",
        "AutomationMissionAutonomy",
        "AutomationMissionBudget",
        "AutomationMissionResource",
        "AutomationMissionTemplate",
        "AutomationRunOutcome",
        "AutomationRunSummary",
        "AutomationSchedule",
        "AutomationScheduleKind",
        "AutomationSummary",
        "AutomationTriggerKind",
        "AutomationUpdate",
        "AutomationWebhookRotationRequest",
        "AutomationWebhookSecret",
        "AutomationWebhookStatus",
        "AutomationWebhookTrigger",
        "BUDGET_LIMIT_NAMES",
        "BudgetConsumptionSummary",
        "BudgetConsumptionTotals",
        "BudgetMissionConsumption",
        "BudgetMutationResult",
        "BudgetPermitRequest",
        "BudgetProviderConsumption",
        "BudgetState",
        "BudgetUsageDelta",
        "BudgetUsagePhase",
        "BudgetUsageSource",
        "BudgetVerdict",
        "CalendarEntry",
        "CalendarEntryState",
        "MAX_CONCURRENT_RUNS",
        "NotificationChannel",
        "NotificationPreferences",
        "NotificationPreferencesSummary",
        "ProjectBudgetPolicy",
        "ProjectBudgetPolicySummary",
        "ProviderBudgetLimit",
    ],
)
def test_contracts_package_exports_the_lot_f_names(name: str) -> None:
    assert hasattr(acp_contracts, name)


def test_resolve_timezone_stays_the_single_authority() -> None:
    # Les contrats n'ouvrent pas une seconde route vers les fuseaux : le module de
    # planification reste la seule autorité, et ce test le documente.
    assert resolve_timezone("Europe/Paris") is not None
