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


def test_heartbeat_cannot_add_or_change_claim_scope():
    for field, value in (("project_id", "project-2"), ("global_access", True)):
        with pytest.raises(ValidationError, match="Extra inputs"):
            WorkerHeartbeatRequest.model_validate({field: value})
