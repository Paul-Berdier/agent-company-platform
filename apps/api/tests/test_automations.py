"""Parcours API du Lot F : routines, calendrier, webhook et concurrence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event as ThreadEvent
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from acp_api import automation_service
from acp_api.deps import get_db
from acp_api.main import app
from acp_api.security import create_user_session
from acp_contracts import (
    AutomationCreate,
    AutomationUpdate,
    AutomationWebhookRotationRequest,
    WEBHOOK_MAX_BODY_BYTES,
)
from acp_database.models import (
    AgentInstanceModel,
    AutomationCommandModel,
    AutomationModel,
    AutomationRunModel,
    AutomationWebhookRotationModel,
    Base,
    EventModel,
    MembershipModel,
    OrganizationModel,
    ProjectModel,
    ProjectBudgetPolicyModel,
    TaskModel,
    TaskRunModel,
    TeamModel,
    UserModel,
    WorkspaceModel,
)


@pytest.fixture
def automation_context(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'automations.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=QueuePool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        organization = OrganizationModel(name="Automation org")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(
            organization_id=organization.id, name="Automation workspace"
        )
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Automation project")
        sibling = ProjectModel(workspace_id=workspace.id, name="Sibling project")
        db.add_all([project, sibling])
        db.flush()
        agent = AgentInstanceModel(
            workspace_id=workspace.id,
            name="Automation agent",
            role_id="developer",
        )
        foreign_team = TeamModel(project_id=sibling.id, name="Foreign team")
        db.add_all([agent, foreign_team])
        owner = UserModel(
            login_normalized=f"automation-owner-{uuid4().hex}",
            display_name="Automation owner",
            password_hash="not-used",
            platform_role="owner",
        )
        viewer = UserModel(
            login_normalized=f"automation-viewer-{uuid4().hex}",
            display_name="Automation viewer",
            password_hash="not-used",
            platform_role="member",
        )
        db.add_all([owner, viewer])
        db.flush()
        db.add(
            MembershipModel(
                user_id=viewer.id,
                scope_type="project",
                scope_id=project.id,
                role="viewer",
            )
        )
        _, owner_token, owner_csrf = create_user_session(db, owner.id)
        _, viewer_token, viewer_csrf = create_user_session(db, viewer.id)
        db.commit()
        identifiers = {
            "project_id": project.id,
            "sibling_id": sibling.id,
            "workspace_id": workspace.id,
            "agent_id": agent.id,
            "foreign_team_id": foreign_team.id,
            "owner_token": owner_token,
            "owner_csrf": owner_csrf,
            "owner_id": owner.id,
            "viewer_token": viewer_token,
            "viewer_csrf": viewer_csrf,
            "viewer_id": viewer.id,
        }

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.cookies.set("acp_session", identifiers["owner_token"])
            client.headers["X-CSRF-Token"] = identifiers["owner_csrf"]
            yield {
                **identifiers,
                "client": client,
                "session_factory": session_factory,
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _payload(context, *, name="Routine test", kind="interval", expression="3600"):
    return {
        "name": name,
        "description": "Une routine vérifiable",
        "schedule": {
            "kind": kind,
            "expression": expression,
            "timezone": "Europe/Paris",
        },
        "mission_template": {
            "title": "Mission automatique",
            "objective": "Produire un résultat traçable",
            "expected_outcome": "Un résultat testé",
            "acceptance_criteria": ["les tests passent"],
            "autonomy": {
                "mode": "bounded",
                "allowed_actions": ["read"],
                "forbidden_actions": ["deploy"],
                "approval_required_actions": ["git_publish"],
            },
            "resources": [],
            "budget": {"max_tokens": 10_000, "max_tool_calls": 20},
            "duration_seconds": 3600,
            "agent_instance_id": context["agent_id"],
            "required_capabilities": ["git"],
        },
        "catchup_policy": "skip",
        "max_concurrent_runs": 1,
    }


def _create(context, **payload_options):
    response = context["client"].post(
        f"/projects/{context['project_id']}/automations",
        json=_payload(context, **payload_options),
        headers={"Idempotency-Key": f"create-{uuid4().hex}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authenticate(context, *, viewer: bool) -> None:
    role = "viewer" if viewer else "owner"
    context["client"].cookies.set("acp_session", context[f"{role}_token"])
    context["client"].headers["X-CSRF-Token"] = context[f"{role}_csrf"]


def test_oversized_json_is_rejected_before_authentication(automation_context):
    context = automation_context
    client = context["client"]
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    oversized = b"x" * (WEBHOOK_MAX_BODY_BYTES + 1)

    automation = client.post(
        f"/projects/{context['project_id']}/automations", content=oversized
    )
    budget = client.put(
        f"/projects/{context['project_id']}/budget", content=oversized
    )

    assert automation.status_code == 413
    assert budget.status_code == 413


def test_crud_enable_disable_and_assignment_validation(automation_context):
    context = automation_context
    client = context["client"]
    created = _create(context)
    automation_id = created["id"]
    assert created["enabled"] is False
    assert created["next_run_at"] is None
    assert created["recent_runs"] == []

    listed = client.get(
        "/automations", params={"project_id": context["project_id"]}
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [automation_id]
    assert client.get(f"/automations/{automation_id}").status_code == 200

    enabled = client.post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "crud-enable"},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    assert enabled.json()["next_run_at"] is not None

    patched = client.patch(
        f"/automations/{automation_id}",
        json={"name": "Routine renommée", "schedule": {
            "kind": "interval", "expression": "7200", "timezone": "Europe/Paris"
        }},
        headers={"Idempotency-Key": "crud-update"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Routine renommée"
    assert patched.json()["schedule"]["expression"] == "7200"

    only_enabled = client.get("/automations", params={"enabled": True}).json()
    assert [item["id"] for item in only_enabled] == [automation_id]
    disabled = client.post(
        f"/automations/{automation_id}/disable",
        headers={"Idempotency-Key": "crud-disable"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["next_run_at"] is None

    invalid = _payload(context)
    invalid["mission_template"]["team_id"] = context["foreign_team_id"]
    response = client.post(
        f"/projects/{context['project_id']}/automations",
        json=invalid,
        headers={"Idempotency-Key": "invalid-assignment"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Équipe hors du projet"


def test_mutations_require_idempotency_keys(automation_context):
    context = automation_context
    client = context["client"]
    automation_id = _create(context, name="Clés obligatoires")["id"]

    assert client.patch(
        f"/automations/{automation_id}", json={"name": "Sans clé"}
    ).status_code == 400
    assert client.post(f"/automations/{automation_id}/enable").status_code == 400
    assert client.post(f"/automations/{automation_id}/disable").status_code == 400
    assert client.delete(f"/automations/{automation_id}/webhook").status_code == 400


def test_stale_patch_and_toggle_replays_never_reapply_old_intent(
    automation_context,
):
    context = automation_context
    client = context["client"]
    automation_id = _create(context, name="État initial")["id"]
    endpoint = f"/automations/{automation_id}"

    first_patch = client.patch(
        endpoint,
        json={"name": "Intention A"},
        headers={"Idempotency-Key": "patch-a"},
    )
    second_patch = client.patch(
        endpoint,
        json={"name": "Intention B"},
        headers={"Idempotency-Key": "patch-b"},
    )
    stale_patch = client.patch(
        endpoint,
        json={"name": "Intention A"},
        headers={"Idempotency-Key": "patch-a"},
    )
    mismatched_patch = client.patch(
        endpoint,
        json={"name": "Autre payload"},
        headers={"Idempotency-Key": "patch-b"},
    )

    assert first_patch.status_code == 200
    assert second_patch.status_code == 200
    assert stale_patch.status_code == 409
    assert "mutation plus récente" in stale_patch.json()["detail"]
    assert mismatched_patch.status_code == 409
    assert "autre intention" in mismatched_patch.json()["detail"]
    assert client.get(endpoint).json()["name"] == "Intention B"

    enabled = client.post(
        f"{endpoint}/enable", headers={"Idempotency-Key": "toggle-shared"}
    )
    with context["session_factory"]() as db:
        scheduled = db.get(AutomationModel, automation_id)
        assert scheduled is not None and scheduled.next_run_at is not None
        scheduled.next_run_at += timedelta(hours=1)
        advanced_cursor = scheduled.next_run_at
        db.commit()
    scheduler_safe_replay = client.post(
        f"{endpoint}/enable", headers={"Idempotency-Key": "toggle-shared"}
    )
    disabled = client.post(
        f"{endpoint}/disable", headers={"Idempotency-Key": "toggle-shared"}
    )
    stale_enable = client.post(
        f"{endpoint}/enable", headers={"Idempotency-Key": "toggle-shared"}
    )
    replayed_disable = client.post(
        f"{endpoint}/disable", headers={"Idempotency-Key": "toggle-shared"}
    )

    assert enabled.status_code == 200
    assert scheduler_safe_replay.status_code == 200
    assert datetime.fromisoformat(
        scheduler_safe_replay.json()["next_run_at"]
    ) == advanced_cursor
    assert disabled.status_code == 200
    assert stale_enable.status_code == 409
    assert replayed_disable.status_code == 200
    assert replayed_disable.json()["enabled"] is False
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored is not None
        assert stored.name == "Intention B"
        assert stored.enabled == 0
        assert stored.next_run_at is None
        assert stored.mutation_revision == 4
        commands = db.query(AutomationCommandModel).filter_by(
            automation_id=automation_id
        ).all()
        assert len(commands) == 4
        assert all(len(command.request_fingerprint) == 64 for command in commands)
        assert (
            db.query(EventModel).filter_by(type="automation.updated").count()
            == 2
        )
        assert (
            db.query(EventModel).filter_by(type="automation.enabled").count()
            == 1
        )
        assert (
            db.query(EventModel).filter_by(type="automation.disabled").count()
            == 1
        )


def test_exact_patch_replay_survives_disjoint_mutations_and_noop(
    automation_context,
):
    context = automation_context
    client = context["client"]
    automation_id = _create(context, name="Routine stable")["id"]
    endpoint = f"/automations/{automation_id}"

    description = client.patch(
        endpoint,
        json={"description": "Description confirmée"},
        headers={"Idempotency-Key": "description-lost-response"},
    )
    disjoint = client.patch(
        endpoint,
        json={"max_concurrent_runs": 2},
        headers={"Idempotency-Key": "disjoint-capacity"},
    )
    replayed_description = client.patch(
        endpoint,
        json={"description": "Description confirmée"},
        headers={"Idempotency-Key": "description-lost-response"},
    )

    assert description.status_code == 200
    assert disjoint.status_code == 200
    assert replayed_description.status_code == 200
    assert replayed_description.json()["description"] == "Description confirmée"
    assert replayed_description.json()["max_concurrent_runs"] == 2

    noop = client.patch(
        endpoint,
        json={"name": "Routine stable"},
        headers={"Idempotency-Key": "noop-lost-response"},
    )
    later_disjoint = client.patch(
        endpoint,
        json={"description": "Description ultérieure"},
        headers={"Idempotency-Key": "later-description"},
    )
    replayed_noop = client.patch(
        endpoint,
        json={"name": "Routine stable"},
        headers={"Idempotency-Key": "noop-lost-response"},
    )

    assert noop.status_code == 200
    assert later_disjoint.status_code == 200
    assert replayed_noop.status_code == 200
    assert replayed_noop.json()["name"] == "Routine stable"
    assert replayed_noop.json()["description"] == "Description ultérieure"
    with context["session_factory"]() as db:
        assert (
            db.query(EventModel).filter_by(type="automation.updated").count()
            == 3
        )
        assert (
            db.query(AutomationCommandModel)
            .filter_by(automation_id=automation_id)
            .count()
            == 4
        )


def test_same_update_command_under_real_concurrency_mutates_and_emits_once(
    automation_context,
):
    context = automation_context
    automation_id = _create(context, name="Avant concurrence")["id"]
    body = AutomationUpdate(name="Après concurrence")
    barrier = Barrier(2)

    def patch() -> bool:
        with context["session_factory"]() as db:
            stale = db.get(AutomationModel, automation_id)
            assert stale is not None
            barrier.wait(timeout=10)
            result = automation_service.update_automation(
                db,
                stale,
                body=body,
                principal_id=context["owner_id"],
                idempotency_key="same-concurrent-update",
                allowed_agent_ids={context["agent_id"]},
            )
            return result.replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        replays = list(executor.map(lambda _: patch(), range(2)))

    assert sorted(replays) == [False, True]
    with context["session_factory"]() as db:
        current = db.get(AutomationModel, automation_id)
        assert current is not None
        assert current.name == "Après concurrence"
        assert current.mutation_revision == 1
        assert db.query(AutomationCommandModel).filter_by(
            automation_id=automation_id,
            command="update",
            idempotency_key="same-concurrent-update",
        ).count() == 1
        assert db.query(EventModel).filter_by(
            type="automation.updated"
        ).count() == 1


def test_stale_webhook_disable_cannot_revoke_a_new_rotation(automation_context):
    context = automation_context
    client = context["client"]
    automation_id = _create(context, name="Webhook ordonné")["id"]
    endpoint = f"/automations/{automation_id}/webhook"
    first_secret = "F" * 43
    second_secret = "G" * 43

    assert client.post(
        endpoint,
        json={"secret": first_secret},
        headers={"Idempotency-Key": "rotation-before-disable"},
    ).status_code == 201
    disabled = client.delete(
        endpoint, headers={"Idempotency-Key": "disable-a"}
    )
    rotated = client.post(
        endpoint,
        json={"secret": second_secret},
        headers={"Idempotency-Key": "rotation-after-disable"},
    )
    stale_disable = client.delete(
        endpoint, headers={"Idempotency-Key": "disable-a"}
    )

    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert rotated.status_code == 201
    assert stale_disable.status_code == 409
    status = client.get(endpoint)
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored is not None
        assert stored.webhook_enabled == 1
        assert stored.webhook_secret_hash == automation_service._secret_hash(
            second_secret
        )
        assert db.query(AutomationCommandModel).filter_by(
            automation_id=automation_id,
            command="webhook.disable",
        ).count() == 1
        assert db.query(EventModel).filter_by(
            type="automation.webhook_disabled"
        ).count() == 1


def test_create_requires_an_idempotency_key_replays_and_rejects_a_new_body(
    automation_context,
):
    context = automation_context
    client = context["client"]
    endpoint = f"/projects/{context['project_id']}/automations"
    payload = _payload(context, name="Création idempotente")
    payload["description"] = ""
    minimal_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"description", "catchup_policy", "max_concurrent_runs"}
    }

    assert client.post(endpoint, json=minimal_payload).status_code == 400
    first = client.post(
        endpoint,
        json=minimal_payload,
        headers={"Idempotency-Key": "stable-create-key"},
    )
    replay = client.post(
        endpoint,
        json=payload,
        headers={"Idempotency-Key": "stable-create-key"},
    )
    conflict = client.post(
        endpoint,
        json={**payload, "name": "Autre corps"},
        headers={"Idempotency-Key": "stable-create-key"},
    )

    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    with context["session_factory"]() as db:
        assert db.query(AutomationModel).count() == 1
        stored = db.query(AutomationModel).one()
        assert stored.create_idempotency_key == "stable-create-key"
        assert len(stored.create_request_fingerprint) == 64
        assert db.query(EventModel).filter_by(type="automation.created").count() == 1


def test_same_create_key_under_real_concurrency_creates_one_resource(
    automation_context,
):
    context = automation_context
    body = AutomationCreate.model_validate(_payload(context, name="Concurrente"))
    barrier = Barrier(2)

    def create() -> tuple[str, bool]:
        with context["session_factory"]() as db:
            barrier.wait(timeout=10)
            result = automation_service.create_automation(
                db,
                project_id=context["project_id"],
                body=body,
                principal_id=context["owner_id"],
                idempotency_key="concurrent-create-key",
                allowed_agent_ids={context["agent_id"]},
            )
            return result.value.id, result.replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: create(), range(2)))

    assert outcomes[0][0] == outcomes[1][0]
    assert sorted(replayed for _, replayed in outcomes) == [False, True]
    with context["session_factory"]() as db:
        assert db.query(AutomationModel).count() == 1
        assert db.query(EventModel).filter_by(type="automation.created").count() == 1


def test_create_idempotency_key_is_scoped_by_project_and_principal(
    automation_context,
):
    context = automation_context
    body = AutomationCreate.model_validate(_payload(context, name="Clé partagée"))
    scopes = [
        (context["project_id"], context["owner_id"]),
        (context["sibling_id"], context["owner_id"]),
        (context["project_id"], context["viewer_id"]),
    ]
    created_ids = []
    for project_id, principal_id in scopes:
        with context["session_factory"]() as db:
            result = automation_service.create_automation(
                db,
                project_id=project_id,
                body=body,
                principal_id=principal_id,
                idempotency_key="same-key",
                allowed_agent_ids={context["agent_id"]},
            )
            created_ids.append(result.value.id)

    assert len(set(created_ids)) == 3


def test_manual_trigger_is_idempotent_allowed_while_disabled_and_bounded(
    automation_context,
):
    context = automation_context
    client = context["client"]
    created = _create(context)
    automation_id = created["id"]
    assert client.post(f"/automations/{automation_id}/trigger").status_code == 400

    first = client.post(
        f"/automations/{automation_id}/trigger",
        headers={"Idempotency-Key": "manual-stable-key"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["outcome"] == "launched"
    assert first.json()["completion_status"] is None
    assert first.json()["trigger_kind"] == "manual"
    assert first.json()["task_id"]
    replay = client.post(
        f"/automations/{automation_id}/trigger",
        headers={"Idempotency-Key": "manual-stable-key"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]

    saturated = client.post(
        f"/automations/{automation_id}/trigger",
        headers={"Idempotency-Key": "manual-second-key"},
    )
    assert saturated.status_code == 201
    assert saturated.json()["outcome"] == "skipped_concurrency"
    assert saturated.json()["task_id"] is None

    with context["session_factory"]() as db:
        row = db.get(AutomationModel, automation_id)
        assert row.next_run_at is None  # le manuel ne déplace jamais le calendrier
        assert db.query(TaskModel).count() == 1
        task = db.get(TaskModel, first.json()["task_id"])
        assert task.is_mission == 1
        assert task.meta["automation"]["automation_run_id"] == first.json()["id"]
        assert task.meta["extensions"]["project_id"] == context["project_id"]
        attempt = db.query(TaskRunModel).filter_by(task_id=task.id).one()
        assert attempt.plan["automation_snapshot"]["trigger_kind"] == "manual"
        assert db.query(EventModel).filter_by(type="mission.created").count() == 1


def test_webhook_secret_is_client_supplied_hashed_recoverable_and_event_is_idempotent(
    automation_context,
):
    context = automation_context
    client = context["client"]
    automation_id = _create(context)["id"]
    assert client.post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "webhook-enable"},
    ).status_code == 200

    endpoint = f"/automations/{automation_id}/webhook"
    secret = "A" * 43
    first_headers = {"Idempotency-Key": "webhook-rotation-1"}
    assert client.post(endpoint, json={"secret": secret}).status_code == 400
    configured = client.post(
        endpoint,
        json={"secret": secret},
        headers=first_headers,
    )
    assert configured.status_code == 201, configured.text
    assert configured.json()["secret"] == secret
    replayed_rotation = client.post(
        endpoint,
        json={"secret": secret},
        headers=first_headers,
    )
    assert replayed_rotation.status_code == 201
    assert replayed_rotation.json() == configured.json()
    conflicting_rotation = client.post(
        endpoint,
        json={"secret": "B" * 43},
        headers=first_headers,
    )
    assert conflicting_rotation.status_code == 409
    status = client.get(f"/automations/{automation_id}/webhook")
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert "secret" not in status.json()
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored.webhook_secret_hash != secret
        assert len(stored.webhook_secret_hash) == 64
        assert secret not in str(stored.__dict__)
        rotations = db.query(AutomationWebhookRotationModel).all()
        assert len(rotations) == 1
        assert rotations[0].rotation_number == 1
        assert rotations[0].secret_hash == stored.webhook_secret_hash
        assert secret not in str(rotations[0].__dict__)
        assert (
            db.query(EventModel)
            .filter_by(type="automation.webhook_rotated")
            .count()
            == 1
        )

    body = {
        "event_id": "external-event-001",
        "payload": {"confidential_value": "must-not-enter-events"},
    }
    assert client.post(
        f"/automations/{automation_id}/webhook/trigger", json=body
    ).status_code == 401
    # Le webhook n'emprunte ni la session navigateur ni le CSRF : son unique
    # autorité est le secret bearer configuré pour cette routine.
    client.cookies.delete("acp_session")
    client.headers.pop("X-CSRF-Token")
    fired = client.post(
        f"/automations/{automation_id}/webhook/trigger",
        headers={"Authorization": f"Bearer {secret}"},
        json=body,
    )
    assert fired.status_code == 201, fired.text
    replay = client.post(
        f"/automations/{automation_id}/webhook/trigger",
        headers={"Authorization": f"Bearer {secret}"},
        json=body,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == fired.json()["id"]
    with context["session_factory"]() as db:
        assert db.query(AutomationRunModel).filter_by(
            automation_id=automation_id, trigger_kind="webhook"
        ).count() == 1
        event_text = " ".join(str(row.payload) for row in db.query(EventModel).all())
        assert "must-not-enter-events" not in event_text
        assert "external-event-001" not in event_text
        assert secret not in event_text

    _authenticate(context, viewer=False)
    new_secret = "B" * 43
    rotated = client.post(
        endpoint,
        json={"secret": new_secret},
        headers={"Idempotency-Key": "webhook-rotation-2"},
    )
    assert rotated.status_code == 201
    assert rotated.json()["secret"] == new_secret
    superseded_replay = client.post(
        endpoint,
        json={"secret": secret},
        headers=first_headers,
    )
    assert superseded_replay.status_code == 409
    assert client.post(
        f"/automations/{automation_id}/webhook/trigger",
        headers={"Authorization": f"Bearer {secret}"},
        json={"event_id": "old-secret", "payload": {}},
    ).status_code == 401
    disabled = client.delete(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": "webhook-disable"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["secret_configured"] is False
    disabled_replay = client.post(
        endpoint,
        json={"secret": new_secret},
        headers={"Idempotency-Key": "webhook-rotation-2"},
    )
    assert disabled_replay.status_code == 409
    with context["session_factory"]() as db:
        assert db.query(AutomationWebhookRotationModel).count() == 2
        assert (
            db.query(EventModel)
            .filter_by(type="automation.webhook_rotated")
            .count()
            == 2
        )


def test_same_webhook_rotation_under_real_concurrency_rotates_once(
    automation_context,
):
    context = automation_context
    automation_id = _create(context, name="Rotation concurrente")["id"]
    body = AutomationWebhookRotationRequest(secret="C" * 43)
    barrier = Barrier(2)

    def rotate() -> tuple[str, bool]:
        with context["session_factory"]() as db:
            row = db.get(AutomationModel, automation_id)
            assert row is not None
            barrier.wait(timeout=10)
            result = automation_service.rotate_webhook(
                db,
                row,
                body=body,
                principal_id=context["owner_id"],
                idempotency_key="concurrent-webhook-rotation",
            )
            return result.value.secret, result.replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: rotate(), range(2)))

    assert [secret for secret, _ in outcomes] == ["C" * 43, "C" * 43]
    assert sorted(replayed for _, replayed in outcomes) == [False, True]
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored is not None
        assert stored.webhook_rotation_number == 1
        assert db.query(AutomationWebhookRotationModel).count() == 1
        assert (
            db.query(EventModel)
            .filter_by(type="automation.webhook_rotated")
            .count()
            == 1
        )


def test_a_new_rotation_supersedes_the_old_key_even_with_the_same_secret(
    automation_context,
):
    context = automation_context
    client = context["client"]
    automation_id = _create(context, name="Même secret, nouvelle rotation")["id"]
    endpoint = f"/automations/{automation_id}/webhook"
    body = {"secret": "D" * 43}

    first = client.post(
        endpoint,
        json=body,
        headers={"Idempotency-Key": "same-secret-first"},
    )
    second = client.post(
        endpoint,
        json=body,
        headers={"Idempotency-Key": "same-secret-second"},
    )
    obsolete_replay = client.post(
        endpoint,
        json=body,
        headers={"Idempotency-Key": "same-secret-first"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert obsolete_replay.status_code == 409
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored is not None
        assert stored.webhook_rotation_number == 2
        assert db.query(AutomationWebhookRotationModel).count() == 2


def test_webhook_revocation_waits_for_an_authenticated_trigger_transaction(
    automation_context,
):
    context = automation_context
    automation_id = _create(context, name="Révocation linéarisable")["id"]
    assert context["client"].post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "linearizable-enable"},
    ).status_code == 200
    secret = "E" * 43
    assert context["client"].post(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": "linearizable-secret"},
        json={"secret": secret},
    ).status_code == 201

    authenticated = ThreadEvent()
    release_trigger = ThreadEvent()
    disable_started = ThreadEvent()
    moment = datetime(2026, 9, 14, 13, tzinfo=UTC)

    def trigger():
        with context["session_factory"]() as db:
            automation_service.authenticate_webhook(db, automation_id, secret)
            authenticated.set()
            assert release_trigger.wait(timeout=10)
            return automation_service.materialize_occurrence(
                db,
                automation_id=automation_id,
                trigger_kind="webhook",
                scheduled_for=moment,
                identity="event-before-disable",
                now=moment,
            )

    def disable():
        assert authenticated.wait(timeout=10)
        with context["session_factory"]() as db:
            disable_started.set()
            return automation_service.disable_webhook(
                db,
                AutomationModel(id=automation_id),
                principal_id=context["owner_id"],
                idempotency_key="linearizable-disable",
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        trigger_future = executor.submit(trigger)
        assert authenticated.wait(timeout=10)
        disable_future = executor.submit(disable)
        assert disable_started.wait(timeout=10)
        try:
            with pytest.raises(FutureTimeout):
                disable_future.result(timeout=0.2)
        finally:
            release_trigger.set()
        triggered = trigger_future.result(timeout=10)
        disabled = disable_future.result(timeout=10)

    assert triggered.value.outcome == "launched"
    assert disabled.value.enabled is False
    with context["session_factory"]() as db:
        with pytest.raises(automation_service.WebhookAuthenticationFailed):
            automation_service.authenticate_webhook(db, automation_id, secret)


def test_calendar_uses_materialized_past_dst_and_persistent_interval_anchor(
    automation_context,
):
    context = automation_context
    client = context["client"]
    cron = _create(
        context, name="02:30 Paris", kind="cron", expression="30 2 * * *"
    )
    automation_id = cron["id"]
    assert client.post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "calendar-cron-enable"},
    ).status_code == 200
    with context["session_factory"]() as db:
        automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="schedule",
            scheduled_for=datetime(2026, 3, 28, 1, 30, tzinfo=UTC),
        )

    past = client.get(
        "/automations/calendar",
        params={
            "automation_id": automation_id,
            "start": "2026-03-28T00:00:00Z",
            "end": "2026-03-31T00:00:00Z",
        },
    )
    assert past.status_code == 200, past.text
    assert len(past.json()) == 1
    assert past.json()[0]["state"] == "past"
    assert past.json()[0]["task_id"]

    autumn = client.get(
        "/automations/calendar",
        params={
            "automation_id": automation_id,
            "start": "2026-10-24T00:00:00Z",
            "end": "2026-10-27T00:00:00Z",
        },
    )
    assert autumn.status_code == 200, autumn.text
    entries = autumn.json()
    assert len(entries) == 3
    assert [entry["utc_offset_minutes"] for entry in entries] == [120, 120, 60]
    assert entries[1]["occurs_at_local"].startswith("2026-10-25T02:30:00+02:00")

    interval = _create(context, name="Intervalle ancré")
    enabled = client.post(
        f"/automations/{interval['id']}/enable",
        headers={"Idempotency-Key": "calendar-interval-enable"},
    ).json()
    anchor = datetime.fromisoformat(enabled["next_run_at"])
    with context["session_factory"]() as db:
        scheduled = automation_service.materialize_occurrence(
            db,
            automation_id=interval["id"],
            trigger_kind="schedule",
            scheduled_for=anchor,
        )
        assert scheduled.value.outcome == "launched"
        assert db.get(AutomationModel, interval["id"]).next_run_at == anchor + timedelta(
            hours=1
        )
    interval_calendar = client.get(
        "/automations/calendar",
        params={
            "automation_id": interval["id"],
            "start": (anchor - timedelta(seconds=1)).isoformat(),
            "end": (anchor + timedelta(seconds=7201)).isoformat(),
        },
    )
    assert interval_calendar.status_code == 200, interval_calendar.text
    instants = [datetime.fromisoformat(item["occurs_at_utc"]) for item in interval_calendar.json()]
    assert instants == [anchor, anchor + timedelta(hours=1), anchor + timedelta(hours=2)]

    too_wide = client.get(
        "/automations/calendar",
        params={
            "start": "2026-01-01T00:00:00Z",
            "end": "2027-01-03T00:00:00Z",
        },
    )
    assert too_wide.status_code == 422


def test_calendar_keeps_the_timezone_snapshot_of_materialized_history(
    automation_context,
):
    context = automation_context
    client = context["client"]
    created = _create(
        context,
        name="Historique Paris",
        kind="cron",
        expression="0 9 * * *",
    )
    automation_id = created["id"]
    assert client.post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "timezone-history-enable"},
    ).status_code == 200
    nominal = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
    with context["session_factory"]() as db:
        result = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="schedule",
            scheduled_for=nominal,
            now=nominal,
        )
        assert result.value.schedule_timezone == "Europe/Paris"

    changed = client.patch(
        f"/automations/{automation_id}",
        headers={"Idempotency-Key": "timezone-history-patch"},
        json={
            "schedule": {
                "kind": "cron",
                "expression": "0 9 * * *",
                "timezone": "America/New_York",
            }
        },
    )
    assert changed.status_code == 200, changed.text

    calendar = client.get(
        "/automations/calendar",
        params={
            "automation_id": automation_id,
            "start": "2026-01-15T00:00:00Z",
            "end": "2026-01-16T00:00:00Z",
        },
    )
    assert calendar.status_code == 200, calendar.text
    assert len(calendar.json()) == 1
    entry = calendar.json()[0]
    assert entry["timezone"] == "Europe/Paris"
    assert entry["occurs_at_local"].startswith("2026-01-15T09:00:00+01:00")


def test_viewer_can_read_but_cannot_mutate_and_csrf_is_required(automation_context):
    context = automation_context
    automation_id = _create(context)["id"]
    _authenticate(context, viewer=True)
    assert context["client"].get(f"/automations/{automation_id}").status_code == 200
    assert context["client"].get("/automations").status_code == 200
    assert context["client"].post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "viewer-forbidden-enable"},
    ).status_code == 403

    _authenticate(context, viewer=False)
    context["client"].headers.pop("X-CSRF-Token")
    assert context["client"].post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": "csrf-forbidden-enable"},
    ).status_code == 403


def test_same_manual_key_under_real_concurrency_creates_one_mission(
    automation_context,
):
    context = automation_context
    automation_id = _create(context)["id"]
    barrier = Barrier(2)

    def fire() -> tuple[str, bool]:
        with context["session_factory"]() as db:
            barrier.wait(timeout=10)
            result = automation_service.materialize_occurrence(
                db,
                automation_id=automation_id,
                trigger_kind="manual",
                scheduled_for=datetime.now(UTC),
                identity="same-concurrent-key",
                principal_id=context["owner_id"],
            )
            return result.value.id, result.replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: fire(), range(2)))
    assert outcomes[0][0] == outcomes[1][0]
    assert sorted(replayed for _, replayed in outcomes) == [False, True]
    with context["session_factory"]() as db:
        assert db.query(AutomationRunModel).filter_by(
            automation_id=automation_id
        ).count() == 1
        assert db.query(TaskModel).count() == 1


def test_manual_idempotency_is_scoped_by_principal_but_webhook_is_global(
    automation_context,
):
    context = automation_context
    automation_id = _create(context)["id"]
    with context["session_factory"]() as db:
        automation = db.get(AutomationModel, automation_id)
        automation.max_concurrent_runs = 5
        db.commit()

    moment = datetime(2026, 9, 14, 13, tzinfo=UTC)
    manual_ids = []
    with context["session_factory"]() as db:
        owner = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="manual",
            scheduled_for=moment,
            identity="same-browser-key",
            principal_id=context["owner_id"],
            now=moment,
        )
        manual_ids.append(owner.value.id)
    with context["session_factory"]() as db:
        viewer = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="manual",
            scheduled_for=moment + timedelta(seconds=1),
            identity="same-browser-key",
            principal_id=context["viewer_id"],
            now=moment + timedelta(seconds=1),
        )
        manual_ids.append(viewer.value.id)
    with context["session_factory"]() as db:
        owner_replay = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="manual",
            scheduled_for=moment + timedelta(seconds=2),
            identity="same-browser-key",
            principal_id=context["owner_id"],
            now=moment + timedelta(seconds=2),
        )
        assert owner_replay.replayed is True
        assert owner_replay.value.id == manual_ids[0]

    assert manual_ids[0] != manual_ids[1]
    with context["session_factory"]() as db:
        first_webhook = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="webhook",
            scheduled_for=moment + timedelta(seconds=3),
            identity="same-external-event",
            principal_id=context["owner_id"],
            now=moment + timedelta(seconds=3),
        )
    with context["session_factory"]() as db:
        webhook_replay = automation_service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="webhook",
            scheduled_for=moment + timedelta(seconds=4),
            identity="same-external-event",
            principal_id=context["viewer_id"],
            now=moment + timedelta(seconds=4),
        )
        assert webhook_replay.replayed is True
        assert webhook_replay.value.id == first_webhook.value.id

    with context["session_factory"]() as db:
        assert (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, trigger_kind="manual")
            .count()
            == 2
        )
        assert (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, trigger_kind="webhook")
            .count()
            == 1
        )


def test_concurrent_schedule_patches_reload_and_keep_cursor_consistent(
    automation_context,
):
    context = automation_context
    automation_id = _create(context)["id"]
    moment = datetime(2026, 9, 14, 13, tzinfo=UTC)
    with context["session_factory"]() as db:
        automation = db.get(AutomationModel, automation_id)
        automation.enabled = 1
        automation.next_run_at = moment + timedelta(hours=1)
        db.commit()

    barrier = Barrier(2)

    def patch(expression: str) -> None:
        with context["session_factory"]() as db:
            stale = db.get(AutomationModel, automation_id)
            assert stale.schedule_expression == "3600"
            barrier.wait(timeout=10)
            automation_service.update_automation(
                db,
                stale,
                body=AutomationUpdate(
                    schedule={
                        "kind": "interval",
                        "expression": expression,
                        "timezone": "Europe/Paris",
                    }
                ),
                principal_id=context["owner_id"],
                idempotency_key=f"concurrent-patch-{expression}",
                allowed_agent_ids={context["agent_id"]},
                now=moment,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(patch, ("600", "1200")))

    with context["session_factory"]() as db:
        current = db.get(AutomationModel, automation_id)
        assert current.schedule_expression in {"600", "1200"}
        assert current.next_run_at == moment + timedelta(
            seconds=int(current.schedule_expression)
        )


def test_identical_interval_patch_is_a_noop_and_keeps_its_anchor(
    automation_context,
):
    context = automation_context
    automation_id = _create(context)["id"]
    anchor = datetime(2026, 9, 14, 10, 15, tzinfo=UTC)
    identical = AutomationUpdate(
        schedule={
            "kind": "interval",
            "expression": "3600",
            "timezone": "Europe/Paris",
        }
    )
    with context["session_factory"]() as db:
        automation = db.get(AutomationModel, automation_id)
        assert automation is not None
        automation.enabled = 1
        automation.next_run_at = anchor
        db.commit()

    for replayed_at in (
        datetime(2026, 9, 14, 10, 5, tzinfo=UTC),
        datetime(2026, 9, 14, 10, 6, tzinfo=UTC),
    ):
        with context["session_factory"]() as db:
            automation = db.get(AutomationModel, automation_id)
            result = automation_service.update_automation(
                db,
                automation,
                body=identical,
                principal_id=context["owner_id"],
                idempotency_key=f"identical-{replayed_at.minute}",
                allowed_agent_ids={context["agent_id"]},
                now=replayed_at,
            )
            assert result.replayed is True
            assert result.events == ()
            assert result.value.next_run_at == anchor


def test_schedule_patch_can_repair_an_invalid_persisted_schedule(
    automation_context,
):
    context = automation_context
    automation_id = _create(context, name="Routine à réparer")["id"]
    with context["session_factory"]() as db:
        automation = db.get(AutomationModel, automation_id)
        assert automation is not None
        automation.schedule_kind = "cron"
        automation.schedule_expression = "SECRET-invalid-cron"
        db.commit()

    repaired = context["client"].patch(
        f"/automations/{automation_id}",
        json={
            "schedule": {
                "kind": "interval",
                "expression": "3600",
                "timezone": "Europe/Paris",
            }
        },
        headers={"Idempotency-Key": "repair-invalid-schedule"},
    )

    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["schedule"] == {
        "kind": "interval",
        "expression": "3600",
        "timezone": "Europe/Paris",
    }


def test_concurrent_enable_disable_never_leaves_an_impossible_cursor(
    automation_context,
):
    context = automation_context
    automation_id = _create(context)["id"]
    moment = datetime(2026, 9, 14, 13, tzinfo=UTC)
    barrier = Barrier(2)

    def toggle(enabled: bool) -> None:
        with context["session_factory"]() as db:
            stale = db.get(AutomationModel, automation_id)
            assert stale.enabled == 0
            barrier.wait(timeout=10)
            automation_service.set_automation_enabled(
                db,
                stale,
                enabled=enabled,
                principal_id=context["owner_id"],
                idempotency_key=f"concurrent-toggle-{enabled}",
                now=moment,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(toggle, (True, False)))

    with context["session_factory"]() as db:
        current = db.get(AutomationModel, automation_id)
        if current.enabled:
            assert current.next_run_at == moment + timedelta(hours=1)
        else:
            assert current.next_run_at is None


def test_project_mission_capacity_is_enforced_across_distinct_automations(
    automation_context,
):
    context = automation_context
    first_id = _create(context, name="Routine A")["id"]
    second_id = _create(context, name="Routine B")["id"]
    with context["session_factory"]() as db:
        db.add(
            ProjectBudgetPolicyModel(
                project_id=context["project_id"],
                timezone="Europe/Paris",
                policy={"max_concurrent_missions": 1},
            )
        )
        db.commit()

    first = context["client"].post(
        f"/automations/{first_id}/trigger",
        headers={"Idempotency-Key": "project-capacity-first"},
    )
    assert first.status_code == 201
    assert first.json()["outcome"] == "launched"
    second = context["client"].post(
        f"/automations/{second_id}/trigger",
        headers={"Idempotency-Key": "project-capacity-second"},
    )
    assert second.status_code == 201
    assert second.json()["outcome"] == "skipped_concurrency"
    assert second.json()["detail"] == (
        "Plafond de missions concurrentes atteint pour ce projet"
    )
    replay = context["client"].post(
        f"/automations/{second_id}/trigger",
        headers={"Idempotency-Key": "project-capacity-second"},
    )
    assert replay.json()["id"] == second.json()["id"]
    with context["session_factory"]() as db:
        assert db.query(TaskModel).count() == 1
