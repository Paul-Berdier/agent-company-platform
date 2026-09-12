"""Contrats du Lot E : flux d'événements, tests structurés et livrables.

Ces tests vérifient les validateurs et les bornes, jamais la simple présence d'un
champ : une borne absente laisserait un reporter ou un worker publier un volume
arbitraire dans la base.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import acp_contracts
from acp_contracts import (
    EVENT_SCHEMA_VERSION,
    ArtifactLink,
    ArtifactPage,
    ArtifactSummary,
    Event,
    EventPage,
    ReporterAttachment,
    ReporterEvent,
    StreamEvent,
    TestCaseResult,
    TestIngestRequest,
    TestRunDetail,
    TestRunSummary,
    TestStep,
    TestTotals,
)

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _stream_event(**overrides) -> StreamEvent:
    payload = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "task.started",
        "occurred_at": NOW,
    }
    payload.update(overrides)
    return StreamEvent(**payload)


def _artifact_summary(**overrides) -> ArtifactSummary:
    payload = {
        "id": "22222222-2222-2222-2222-222222222222",
        "project_id": "33333333-3333-3333-3333-333333333333",
        "task_run_id": "44444444-4444-4444-4444-444444444444",
        "kind": "web_test",
        "created_at": NOW,
    }
    payload.update(overrides)
    return ArtifactSummary(**payload)


def _case(**overrides) -> TestCaseResult:
    payload = {
        "id": "55555555-5555-5555-5555-555555555555",
        "test_run_id": "66666666-6666-6666-6666-666666666666",
        "suite_path": ["panier.spec.ts", "Panier"],
        "title": "ajoute un article",
        "test_id": "panier.spec.ts:12:3",
        "location": {"file": "panier.spec.ts", "line": 12, "column": 3},
        "attempt": 1,
        "expected_status": "passed",
        "status": "passed",
        "outcome": "expected",
        "duration_ms": 1200,
    }
    payload.update(overrides)
    return TestCaseResult(**payload)


def _run_summary(**overrides) -> TestRunSummary:
    payload = {
        "id": "66666666-6666-6666-6666-666666666666",
        "task_run_id": "44444444-4444-4444-4444-444444444444",
        "project_id": "33333333-3333-3333-3333-333333333333",
        "worker_id": None,
        "runner": "playwright",
        "status": "completed",
        "started_at": NOW,
        "finished_at": NOW + timedelta(seconds=12),
        "duration_ms": 12000,
        "totals": TestTotals(expected=3),
        "exit_code": 0,
        "case_count": 3,
    }
    payload.update(overrides)
    return TestRunSummary(**payload)


# --- events.py ---------------------------------------------------------------


def test_event_schema_version_is_the_documented_constant():
    assert EVENT_SCHEMA_VERSION == "1.0"


def test_legacy_event_contract_is_unchanged():
    legacy = Event(type="task.started")
    assert set(Event.model_fields) == {
        "id",
        "type",
        "occurred_at",
        "organization_id",
        "workspace_id",
        "department_id",
        "project_id",
        "team_id",
        "agent_instance_id",
        "task_id",
        "task_run_id",
        "payload",
    }
    assert legacy.payload == {}


def test_stream_event_defaults_are_explicit():
    event = _stream_event()
    assert event.schema_version == EVENT_SCHEMA_VERSION
    assert event.sequence is None
    assert event.conversation_id is None
    assert event.step_id is None
    assert event.executor is None
    assert event.emitted_by is None
    assert event.payload == {}


def test_stream_event_keeps_the_allocated_sequence():
    assert _stream_event(sequence=7).sequence == 7


@pytest.mark.parametrize("sequence", [0, -1])
def test_stream_event_rejects_a_non_monotonic_sequence(sequence: int):
    with pytest.raises(ValidationError):
        _stream_event(sequence=sequence)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("type", "x" * 101),
        ("step_id", "x" * 65),
        ("executor", "x" * 65),
        ("emitted_by", "x" * 65),
        ("conversation_id", "x" * 37),
        ("schema_version", "x" * 11),
    ],
)
def test_stream_event_bounds_every_string(field: str, value: str):
    with pytest.raises(ValidationError):
        _stream_event(**{field: value})


def test_event_page_defaults_to_an_empty_page():
    page = EventPage()
    assert page.events == []
    assert page.next_cursor is None
    assert page.has_more is False
    assert page.retention_days is None


def test_event_page_carries_the_cursor_of_the_last_event():
    page = EventPage(events=[_stream_event(sequence=4)], next_cursor=4, has_more=True)
    assert page.next_cursor == 4
    assert page.events[0].sequence == 4


def test_event_page_accepts_unlimited_retention_as_zero():
    assert EventPage(retention_days=0).retention_days == 0


@pytest.mark.parametrize(("field", "value"), [("next_cursor", 0), ("retention_days", -1)])
def test_event_page_rejects_impossible_counters(field: str, value: int):
    with pytest.raises(ValidationError):
        EventPage(**{field: value})


# --- testing.py --------------------------------------------------------------


def test_test_totals_default_to_zero_and_keep_each_status_distinct():
    totals = TestTotals()
    assert totals.model_dump() == {
        "expected": 0,
        "unexpected": 0,
        "flaky": 0,
        "skipped": 0,
        "interrupted": 0,
        "timedOut": 0,
    }


@pytest.mark.parametrize(
    "field", ["expected", "unexpected", "flaky", "skipped", "interrupted", "timedOut"]
)
def test_test_totals_reject_negative_counters(field: str):
    with pytest.raises(ValidationError):
        TestTotals(**{field: -1})


@pytest.mark.parametrize("status", ["passed", "failed", "timedOut", "skipped", "interrupted"])
def test_test_case_accepts_every_playwright_status(status: str):
    assert _case(status=status).status == status


@pytest.mark.parametrize("status", ["green", "red", "ok", "passed ", "PASSED"])
def test_test_case_rejects_a_reduced_status(status: str):
    with pytest.raises(ValidationError):
        _case(status=status)


@pytest.mark.parametrize("outcome", ["expected", "unexpected", "flaky", "skipped"])
def test_test_case_accepts_every_outcome(outcome: str):
    assert _case(outcome=outcome).outcome == outcome


def test_test_case_rejects_an_unknown_outcome():
    with pytest.raises(ValidationError):
        _case(outcome="probablement")


def test_test_case_bounds_the_error_text():
    assert len(_case(error_message="x" * 8000).error_message) == 8000
    with pytest.raises(ValidationError):
        _case(error_message="x" * 8001)
    with pytest.raises(ValidationError):
        _case(error_snippet="x" * 8001)


def test_test_case_bounds_the_step_list():
    steps = [TestStep(title=f"étape {index}") for index in range(200)]
    assert len(_case(steps=steps).steps) == 200
    with pytest.raises(ValidationError):
        _case(steps=steps + [TestStep(title="étape 201")])


def test_test_case_rejects_a_zero_attempt():
    with pytest.raises(ValidationError):
        _case(attempt=0)


def test_test_step_defaults_mark_no_error():
    step = TestStep(title="clique sur Ajouter")
    assert step.category == ""
    assert step.duration_ms == 0
    assert step.error is False


def test_test_step_rejects_a_negative_duration():
    with pytest.raises(ValidationError):
        TestStep(title="clique", duration_ms=-1)


def test_test_run_detail_extends_the_summary():
    detail = TestRunDetail(
        **_run_summary().model_dump(),
        cases=[_case()],
        report_artifact=_artifact_summary(stream_kind="report"),
    )
    assert detail.runner == "playwright"
    assert detail.case_count == 3
    assert detail.cases[0].status == "passed"
    assert detail.report_artifact is not None
    assert detail.report_artifact.stream_kind == "report"


def test_test_run_detail_accepts_a_run_without_report():
    detail = TestRunDetail(**_run_summary().model_dump(), cases=[])
    assert detail.report_artifact is None
    assert detail.cases == []


@pytest.mark.parametrize(
    "status", ["running", "completed", "failed", "interrupted", "timed_out"]
)
def test_test_run_summary_accepts_every_run_status(status: str):
    assert _run_summary(status=status).status == status


def test_test_run_summary_rejects_an_unknown_run_status():
    with pytest.raises(ValidationError):
        _run_summary(status="cancelled")


def test_test_run_summary_rejects_a_negative_case_count():
    with pytest.raises(ValidationError):
        _run_summary(case_count=-1)


# --- ingestion du reporter ---------------------------------------------------


def test_reporter_event_refuses_an_unknown_field():
    with pytest.raises(ValidationError):
        ReporterEvent(kind="run_begin", token="secret")


def test_reporter_event_refuses_an_unknown_kind():
    with pytest.raises(ValidationError):
        ReporterEvent(kind="run_paused")


def test_reporter_test_end_requires_a_status_and_an_outcome():
    with pytest.raises(ValidationError):
        ReporterEvent(kind="test_end", test_id="panier.spec.ts:12:3", title="ajoute")
    event = ReporterEvent(
        kind="test_end",
        test_id="panier.spec.ts:12:3",
        title="ajoute",
        status="failed",
        outcome="unexpected",
    )
    assert event.status == "failed"
    assert event.outcome == "unexpected"


def test_reporter_test_end_requires_a_test_identifier():
    with pytest.raises(ValidationError):
        ReporterEvent(kind="test_end", title="ajoute", status="passed", outcome="expected")


def test_reporter_error_requires_a_message():
    with pytest.raises(ValidationError):
        ReporterEvent(kind="error")
    assert ReporterEvent(kind="error", message="reporter interrompu").message


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "C:\\Windows\\system32\\config\\sam",
        "../../secrets.env",
        "captures/../../secrets.env",
        "\\\\serveur\\partage\\x.png",
    ],
)
def test_reporter_attachment_refuses_a_path_outside_the_report(path: str):
    with pytest.raises(ValidationError):
        ReporterAttachment(name="capture", path=path)


def test_reporter_attachment_keeps_a_relative_path_normalized():
    attachment = ReporterAttachment(name="capture", path="captures\\echec.png")
    assert attachment.path == "captures/echec.png"


def test_reporter_attachment_refuses_an_empty_path():
    with pytest.raises(ValidationError):
        ReporterAttachment(name="capture", path="")


def test_test_ingest_request_requires_a_fencing_token():
    with pytest.raises(ValidationError):
        TestIngestRequest(
            task_run_id="44444444-4444-4444-4444-444444444444",
            fencing_token=0,
            runner="playwright",
            events=[],
        )


def test_test_ingest_request_refuses_another_runner():
    with pytest.raises(ValidationError):
        TestIngestRequest(
            task_run_id="44444444-4444-4444-4444-444444444444",
            fencing_token=1,
            runner="jest",
            events=[],
        )


def test_test_ingest_request_bounds_the_event_batch():
    events = [ReporterEvent(kind="error", message="x") for _ in range(5000)]
    request = TestIngestRequest(
        task_run_id="44444444-4444-4444-4444-444444444444",
        fencing_token=3,
        runner="playwright",
        events=events,
    )
    assert len(request.events) == 5000
    assert request.exit_code is None
    assert request.config == {}
    with pytest.raises(ValidationError):
        TestIngestRequest(
            task_run_id="44444444-4444-4444-4444-444444444444",
            fencing_token=3,
            runner="playwright",
            events=events + [ReporterEvent(kind="error", message="x")],
        )


# --- operations.py -----------------------------------------------------------


def test_artifact_summary_defaults_describe_a_metadata_only_artifact():
    summary = _artifact_summary()
    assert summary.has_content is False
    assert summary.content_type == "application/octet-stream"
    assert summary.original_name == ""
    assert summary.stream_kind == ""
    assert summary.source == "worker"
    assert summary.size_bytes is None
    assert summary.checksum is None


def test_artifact_summary_never_exposes_the_storage_key():
    assert "storage_key" not in ArtifactSummary.model_fields
    assert "path" not in ArtifactSummary.model_fields


def test_artifact_summary_rejects_a_negative_size():
    with pytest.raises(ValidationError):
        _artifact_summary(size_bytes=-1)


def test_artifact_link_carries_an_expiry():
    link = ArtifactLink(
        artifact_id="22222222-2222-2222-2222-222222222222",
        url="https://apercu.example/artifacts/22222222/content?token=v1...",
        expires_at=NOW + timedelta(minutes=5),
    )
    assert link.expires_at > NOW


def test_artifact_page_defaults_to_an_empty_page():
    page = ArtifactPage()
    assert page.items == []
    assert page.next_cursor is None


def test_artifact_page_keeps_the_opaque_cursor():
    page = ArtifactPage(items=[_artifact_summary()], next_cursor="2026-09-12T10:00:00Z|22222222")
    assert page.next_cursor == "2026-09-12T10:00:00Z|22222222"
    assert len(page.items) == 1


# --- réexports ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "EVENT_SCHEMA_VERSION",
        "StreamEvent",
        "EventPage",
        "TestStep",
        "TestTotals",
        "TestCaseResult",
        "TestRunSummary",
        "TestRunDetail",
        "ReporterAttachment",
        "ReporterEvent",
        "TestIngestRequest",
        "ArtifactSummary",
        "ArtifactLink",
        "ArtifactPage",
    ],
)
def test_lot_e_contracts_are_reexported(name: str):
    assert hasattr(acp_contracts, name)
