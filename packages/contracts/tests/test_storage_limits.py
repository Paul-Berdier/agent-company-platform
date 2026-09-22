"""Bornes communes aux données persistées, avant toute écriture."""
from datetime import datetime, timezone

import pytest
from acp_api.routers.crud import OrganizationCreate
from acp_api.routers.work import TaskPatch
from acp_contracts.events import Event
from acp_contracts.missions import MissionCommentCreate
from acp_contracts.testing import ReporterEvent
from pydantic import ValidationError


@pytest.mark.parametrize("instant", ["9999-12-31T23:00:00-05:00", "0001-01-01T00:00:00+05:00"])
def test_event_refuses_datetime_outside_utc_range(instant):
    with pytest.raises(ValidationError, match="UTC"):
        Event(type="test", occurred_at=instant)


def test_event_normalizes_timezone_before_sqlite_storage():
    value = Event(type="test", occurred_at="2026-09-19T12:00:00+02:00")
    assert value.occurred_at == datetime(2026, 9, 19, 10, tzinfo=timezone.utc)
    assert value.occurred_at.tzinfo is timezone.utc


def test_comment_refuses_nul_in_french():
    with pytest.raises(ValidationError, match="NUL"):
        MissionCommentCreate(body="bonjour\x00suite")


def test_captured_test_error_replaces_nul_without_losing_report():
    event = ReporterEvent(kind="error", message="avant\x00après")
    assert event.message == "avant�après"


def test_crud_name_is_bounded_by_persistent_column():
    with pytest.raises(ValidationError, match="200"):
        OrganizationCreate(name="n" * 201)


def test_generated_workflow_label_is_shortened_visibly():
    patch = TaskPatch(workflow_step="titre" * 40)
    assert len(patch.workflow_step) == 100
    assert patch.workflow_step.endswith("…")


def test_password_secret_is_never_transformed_by_storage_validation():
    from acp_contracts.auth import OwnerBootstrapRequest
    password = "mot-de-passe-secret\x00inchangé"
    request = OwnerBootstrapRequest(login="owner", display_name="Propriétaire", password=password)
    assert request.password.get_secret_value() == password
    assert password not in repr(request)


def test_mcp_captured_stderr_replaces_nul_after_worker_redaction():
    from acp_contracts.mcp import McpProbeResult
    from acp_worker.mcp_probe import _result

    secret = "test-secret-value"
    value = _result(status="failed", error="probe_failed", duration_ms=1,
                    stderr_tail=secret + "\x00sortie", redactions=(secret,))
    original_tail = value["stderr_tail"]
    assert secret not in original_tail
    result = McpProbeResult.model_validate(value)
    assert result.stderr_tail == original_tail.replace("\x00", "�")
    assert value["stderr_tail"] == original_tail


@pytest.mark.parametrize("kind", ["command", "user_note"])
def test_other_evidence_is_not_sanitized_as_machine_output(kind):
    from acp_contracts.missions import EvidenceCreate
    with pytest.raises(ValidationError, match="NUL"):
        EvidenceCreate(kind=kind, summary="saisie utilisateur", data={"stdout": {"text": "avant\x00après"}})


def test_local_process_sanitization_does_not_rewrite_other_fields():
    from acp_api.routers.work import TaskRunPatch
    from acp_contracts.missions import EvidenceCreate

    with pytest.raises(ValidationError, match="NUL"):
        EvidenceCreate(kind="local_process", summary="saisie\x00utilisateur", data={"stdout": {"text": "sortie\x00binaire"}})
    with pytest.raises(ValidationError, match="NUL"):
        TaskRunPatch(result={"secret": "inchangé\x00", "evidence": []})


def test_manual_skill_file_preserves_raw_content_through_nested_contract():
    from acp_contracts.skills import SkillImportRequest

    content = "contenu\x00brut\r\n"
    request = SkillImportRequest.model_validate({
        "source": {"kind": "manual", "files": [{"path": "SKILL.md", "content": content}]},
    })
    assert request.source.files[0].content == content
    assert request.model_dump()["source"]["files"][0]["content"] == content
