"""Contrats de périmètre explicite des workers."""

import pytest
from pydantic import ValidationError

from acp_contracts import WorkerHeartbeatRequest, WorkerRegistrationRequest


def test_registration_requires_exactly_one_claim_scope():
    with pytest.raises(ValidationError, match="exactement un périmètre"):
        WorkerRegistrationRequest(name="unscoped")
    with pytest.raises(ValidationError, match="exactement un périmètre"):
        WorkerRegistrationRequest(
            name="double-scoped", project_id="project-1", global_access=True
        )

    project = WorkerRegistrationRequest(
        name="project-worker", project_id="  project-1  "
    )
    assert project.project_id == "project-1"
    assert project.global_access is False
    global_worker = WorkerRegistrationRequest(name="global-worker", global_access=True)
    assert global_worker.project_id is None
    assert global_worker.global_access is True


@pytest.mark.parametrize(
    "name,expected",
    [
        (" ", "nom du worker"),
        ("   ", "nom du worker"),
        ("\t\n", "nom du worker"),
        ("poste\x00principal", "NUL"),
    ],
)
def test_registration_refuses_a_blank_name_or_a_nul_character(name: str, expected: str):
    """Même règle que la vue des quotas : un nom de worker se lit toujours."""

    with pytest.raises(ValidationError) as caught:
        WorkerRegistrationRequest(name=name, global_access=True)
    messages = " | ".join(str(item["msg"]) for item in caught.value.errors())
    assert expected in messages
    assert WorkerRegistrationRequest(name=" poste ", global_access=True).name == " poste "


def test_heartbeat_cannot_add_or_change_claim_scope():
    for field, value in (("project_id", "project-2"), ("global_access", True)):
        with pytest.raises(ValidationError, match="Extra inputs"):
            WorkerHeartbeatRequest.model_validate({field: value})
