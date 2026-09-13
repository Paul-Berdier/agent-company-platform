"""Parcours API du Lot F : routines, calendrier, webhook et concurrence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
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
from acp_database.models import (
    AgentInstanceModel,
    AutomationModel,
    AutomationRunModel,
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
            "viewer_token": viewer_token,
            "viewer_csrf": viewer_csrf,
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
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authenticate(context, *, viewer: bool) -> None:
    role = "viewer" if viewer else "owner"
    context["client"].cookies.set("acp_session", context[f"{role}_token"])
    context["client"].headers["X-CSRF-Token"] = context[f"{role}_csrf"]


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

    enabled = client.post(f"/automations/{automation_id}/enable")
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    assert enabled.json()["next_run_at"] is not None

    patched = client.patch(
        f"/automations/{automation_id}",
        json={"name": "Routine renommée", "schedule": {
            "kind": "interval", "expression": "7200", "timezone": "Europe/Paris"
        }},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Routine renommée"
    assert patched.json()["schedule"]["expression"] == "7200"

    only_enabled = client.get("/automations", params={"enabled": True}).json()
    assert [item["id"] for item in only_enabled] == [automation_id]
    disabled = client.post(f"/automations/{automation_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["next_run_at"] is None

    invalid = _payload(context)
    invalid["mission_template"]["team_id"] = context["foreign_team_id"]
    response = client.post(
        f"/projects/{context['project_id']}/automations", json=invalid
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Équipe hors du projet"


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


def test_webhook_secret_is_one_time_hashed_rotatable_and_event_id_is_idempotent(
    automation_context,
):
    context = automation_context
    client = context["client"]
    automation_id = _create(context)["id"]
    assert client.post(f"/automations/{automation_id}/enable").status_code == 200

    configured = client.post(f"/automations/{automation_id}/webhook")
    assert configured.status_code == 201, configured.text
    secret = configured.json()["secret"]
    status = client.get(f"/automations/{automation_id}/webhook")
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert "secret" not in status.json()
    with context["session_factory"]() as db:
        stored = db.get(AutomationModel, automation_id)
        assert stored.webhook_secret_hash != secret
        assert len(stored.webhook_secret_hash) == 64
        assert secret not in str(stored.__dict__)

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
    rotated = client.post(f"/automations/{automation_id}/webhook")
    assert rotated.status_code == 201
    assert rotated.json()["secret"] != secret
    assert client.post(
        f"/automations/{automation_id}/webhook/trigger",
        headers={"Authorization": f"Bearer {secret}"},
        json={"event_id": "old-secret", "payload": {}},
    ).status_code == 401
    disabled = client.delete(f"/automations/{automation_id}/webhook")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["secret_configured"] is False


def test_calendar_uses_materialized_past_dst_and_persistent_interval_anchor(
    automation_context,
):
    context = automation_context
    client = context["client"]
    cron = _create(
        context, name="02:30 Paris", kind="cron", expression="30 2 * * *"
    )
    automation_id = cron["id"]
    assert client.post(f"/automations/{automation_id}/enable").status_code == 200
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
    enabled = client.post(f"/automations/{interval['id']}/enable").json()
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


def test_viewer_can_read_but_cannot_mutate_and_csrf_is_required(automation_context):
    context = automation_context
    automation_id = _create(context)["id"]
    _authenticate(context, viewer=True)
    assert context["client"].get(f"/automations/{automation_id}").status_code == 200
    assert context["client"].get("/automations").status_code == 200
    assert context["client"].post(
        f"/automations/{automation_id}/enable"
    ).status_code == 403

    _authenticate(context, viewer=False)
    context["client"].headers.pop("X-CSRF-Token")
    assert context["client"].post(
        f"/automations/{automation_id}/enable"
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
