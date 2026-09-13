"""Alertes in-app : isolation, acquittement transactionnel et préférences."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api import alerts_service
from acp_api.alerts_service import alert_dedupe_key, open_or_escalate_alert
from acp_api.deps import get_db
from acp_api.routers.alerts import router
from acp_api.security import create_user_session
from acp_database.models import (
    AlertModel,
    Base,
    EventModel,
    MembershipModel,
    NotificationPreferencesModel,
    OrganizationModel,
    ProjectModel,
    UserModel,
    WorkspaceModel,
)


@dataclass
class AlertApiContext:
    client: TestClient
    session_factory: sessionmaker
    project_a: str
    project_b: str
    member: tuple[str, str, str]
    viewer: tuple[str, str, str]
    outsider: tuple[str, str, str]


def _user_with_session(db, *, login: str) -> tuple[str, str, str]:
    user = UserModel(
        login_normalized=login,
        display_name=login.title(),
        password_hash="not-used-by-session-tests",
        platform_role="viewer",
    )
    db.add(user)
    db.flush()
    _row, session_token, csrf_token = create_user_session(db, user.id)
    return user.id, session_token, csrf_token


def _authenticate(client: TestClient, identity: tuple[str, str, str]) -> None:
    _user_id, session_token, csrf_token = identity
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


@pytest.fixture
def alert_api() -> AlertApiContext:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        organization = OrganizationModel(name="Alertes")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Atelier")
        db.add(workspace)
        db.flush()
        project_a = ProjectModel(workspace_id=workspace.id, name="Visible")
        project_b = ProjectModel(workspace_id=workspace.id, name="Isolé")
        db.add_all([project_a, project_b])
        db.flush()
        member = _user_with_session(db, login="alert-member")
        viewer = _user_with_session(db, login="alert-viewer")
        outsider = _user_with_session(db, login="alert-outsider")
        db.add_all(
            [
                MembershipModel(
                    user_id=member[0],
                    scope_type="project",
                    scope_id=project_a.id,
                    role="member",
                ),
                MembershipModel(
                    user_id=viewer[0],
                    scope_type="project",
                    scope_id=project_a.id,
                    role="viewer",
                ),
                MembershipModel(
                    user_id=outsider[0],
                    scope_type="project",
                    scope_id=project_b.id,
                    role="member",
                ),
            ]
        )
        db.commit()
        ids = (project_a.id, project_b.id)

    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield AlertApiContext(
                client=client,
                session_factory=session_factory,
                project_a=ids[0],
                project_b=ids[1],
                member=member,
                viewer=viewer,
                outsider=outsider,
            )
    finally:
        engine.dispose()


def _insert_alert(
    context: AlertApiContext,
    *,
    project_id: str,
    kind: str,
    severity: str,
    created_at: datetime,
    alert_id: str,
    acknowledged: bool = False,
) -> str:
    dedupe = alert_dedupe_key(kind, {"fixture": alert_id})
    with context.session_factory() as db:
        row = AlertModel(
            id=alert_id,
            project_id=project_id,
            kind=kind,
            severity=severity,
            title=f"Alerte {kind}",
            detail="détail",
            acknowledgement_comment="",
            dedupe_key=dedupe,
            dedupe_key_active=None if acknowledged else dedupe,
            created_at=created_at,
            acknowledged_at=created_at if acknowledged else None,
            acknowledged_by_user_id=(context.member[0] if acknowledged else None),
        )
        db.add(row)
        db.commit()
        return row.id


def test_alert_list_requires_a_session_and_isolates_projects(alert_api):
    context = alert_api
    now = datetime(2026, 9, 13, 20, tzinfo=UTC)
    older_id = "00000000-0000-0000-0000-000000000001"
    newer_id = "00000000-0000-0000-0000-000000000002"
    _insert_alert(
        context,
        project_id=context.project_a,
        kind="budget",
        severity="warning",
        created_at=now,
        alert_id=older_id,
    )
    _insert_alert(
        context,
        project_id=context.project_a,
        kind="storage",
        severity="critical",
        created_at=now + timedelta(minutes=1),
        alert_id=newer_id,
        acknowledged=True,
    )
    _insert_alert(
        context,
        project_id=context.project_b,
        kind="secret",
        severity="critical",
        created_at=now + timedelta(hours=1),
        alert_id="00000000-0000-0000-0000-000000000003",
    )

    assert context.client.get("/alerts").status_code == 401
    _authenticate(context.client, context.member)

    response = context.client.get("/alerts")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [newer_id, older_id]
    assert {row["project_id"] for row in response.json()} == {context.project_a}

    assert [
        row["id"] for row in context.client.get("/alerts", params={"open": True}).json()
    ] == [older_id]
    assert [
        row["id"]
        for row in context.client.get(
            "/alerts", params={"open": False, "severity": "critical"}
        ).json()
    ] == [newer_id]
    assert (
        context.client.get(
            "/alerts", params={"project_id": context.project_b}
        ).json()
        == []
    )
    assert context.client.get("/alerts", params={"severity": "fatal"}).status_code == 422


def test_acknowledgement_is_csrf_protected_rbac_scoped_and_idempotent(alert_api):
    context = alert_api
    with context.session_factory() as db:
        alert, transition = open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="automation_failure",
            severity="warning",
            title="Routine en échec",
            dimensions={"automation_id": "routine-1"},
        )
        db.commit()
        alert_id = alert.id
    assert transition == "opened"

    _authenticate(context.client, context.member)
    csrf = context.client.headers.pop("X-CSRF-Token")
    assert (
        context.client.post(
            f"/alerts/{alert_id}/acknowledge", json={"comment": "vu"}
        ).status_code
        == 403
    )
    context.client.headers["X-CSRF-Token"] = csrf

    first = context.client.post(
        f"/alerts/{alert_id}/acknowledge", json={"comment": "  résolu  "}
    )
    assert first.status_code == 200
    assert first.json()["acknowledgement_comment"] == "résolu"
    assert first.json()["acknowledged_by_user_id"] == context.member[0]
    assert first.json()["acknowledged_at"] is not None

    replay = context.client.post(
        f"/alerts/{alert_id}/acknowledge", json={"comment": "ne remplace pas"}
    )
    assert replay.status_code == 200
    assert replay.json()["acknowledgement_comment"] == "résolu"
    with context.session_factory() as db:
        types = [
            event_type
            for (event_type,) in db.query(EventModel.type)
            .filter(EventModel.payload["alert_id"].as_string() == alert_id)
            .all()
        ]
        stored = db.get(AlertModel, alert_id)
        assert stored is not None
        assert stored.dedupe_key_active is None
        assert stored.acknowledgement_comment == "résolu"
    assert types.count("alert.opened") == 1
    assert types.count("alert.acknowledged") == 1

    _authenticate(context.client, context.viewer)
    assert (
        context.client.post(
            f"/alerts/{alert_id}/acknowledge", json={"comment": "interdit"}
        ).status_code
        == 403
    )
    other_id = _insert_alert(
        context,
        project_id=context.project_b,
        kind="hidden",
        severity="warning",
        created_at=datetime.now(UTC),
        alert_id="00000000-0000-0000-0000-000000000004",
    )
    _authenticate(context.client, context.member)
    assert (
        context.client.post(
            f"/alerts/{other_id}/acknowledge", json={"comment": "intrus"}
        ).status_code
        == 404
    )


def test_open_escalate_is_canonical_monotone_and_emits_only_transitions(alert_api):
    context = alert_api
    with context.session_factory() as db:
        first, opened = open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="budget",
            severity="info",
            title="Budget observé",
            dimensions={"provider": "hermes", "limit": "daily"},
        )
        db.commit()
        first_id = first.id
    with context.session_factory() as db:
        escalated, transition = open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="budget",
            severity="critical",
            title="Budget bloqué",
            detail="Limite atteinte",
            dimensions={"limit": "daily", "provider": "hermes"},
        )
        db.commit()
        assert escalated.id == first_id
        assert escalated.severity == "critical"
    with context.session_factory() as db:
        unchanged, replay = open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="budget",
            severity="warning",
            title="Ne rétrograde pas",
            dimensions={"provider": "hermes", "limit": "daily"},
        )
        db.commit()
        assert unchanged.id == first_id
        assert unchanged.severity == "critical"
        events = (
            db.query(EventModel)
            .filter(EventModel.payload["alert_id"].as_string() == first_id)
            .order_by(EventModel.journal_seq)
            .all()
        )

    assert (opened, transition, replay) == ("opened", "escalated", "unchanged")
    assert [event.type for event in events] == ["alert.opened", "alert.escalated"]
    assert all("detail" not in event.payload for event in events)
    assert all("title" not in event.payload for event in events)


def test_alert_events_explicitly_disable_outbound_forwarding(alert_api, monkeypatch):
    context = alert_api
    real_publish = alerts_service.publish
    observed: list[bool] = []

    def guarded_publish(*args, **kwargs):
        observed.append(kwargs.get("forward"))
        assert kwargs.get("forward") is False
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(alerts_service, "publish", guarded_publish)
    with context.session_factory() as db:
        open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="storage",
            severity="warning",
            title="Stockage presque plein",
            dimensions={"limit": "project"},
        )
        db.commit()
    assert observed == [False]


def test_open_alert_stays_in_the_callers_transaction_on_sqlite(alert_api):
    context = alert_api
    with context.session_factory() as db:
        opened, transition = open_or_escalate_alert(
            db,
            project_id=context.project_a,
            kind="transaction_test",
            severity="warning",
            title="Ne doit pas survivre",
            dimensions={"test": "rollback"},
        )
        opened_id = opened.id
        assert transition == "opened"
        db.rollback()

    with context.session_factory() as db:
        assert db.get(AlertModel, opened_id) is None
        assert (
            db.query(EventModel)
            .filter(EventModel.payload["alert_id"].as_string() == opened_id)
            .count()
            == 0
        )


def test_notification_preferences_are_strict_personal_and_persisted(alert_api):
    context = alert_api
    _authenticate(context.client, context.viewer)

    defaults = context.client.get(
        f"/projects/{context.project_a}/notification-preferences"
    )
    assert defaults.status_code == 200
    assert defaults.json()["channel"] == "in_app"
    assert defaults.json()["minimum_severity"] == "warning"

    csrf = context.client.headers.pop("X-CSRF-Token")
    assert (
        context.client.put(
            f"/projects/{context.project_a}/notification-preferences",
            json={"enabled": False},
        ).status_code
        == 403
    )
    context.client.headers["X-CSRF-Token"] = csrf
    invalid = context.client.put(
        f"/projects/{context.project_a}/notification-preferences",
        json={"enabled": 1},
    )
    assert invalid.status_code == 422
    unavailable = context.client.put(
        f"/projects/{context.project_a}/notification-preferences",
        json={"channel": "email"},
    )
    assert unavailable.status_code == 422

    updated = context.client.put(
        f"/projects/{context.project_a}/notification-preferences",
        json={
            "channel": "in_app",
            "enabled": True,
            "minimum_severity": "critical",
            "budget_alerts": False,
            "automation_failures": True,
            "storage_alerts": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["minimum_severity"] == "critical"
    assert updated.json()["budget_alerts"] is False
    assert updated.json()["storage_alerts"] is False
    assert (
        context.client.get(
            f"/projects/{context.project_a}/notification-preferences"
        ).json()
        == updated.json()
    )

    _authenticate(context.client, context.member)
    personal = context.client.get(
        f"/projects/{context.project_a}/notification-preferences"
    )
    assert personal.status_code == 200
    assert personal.json()["minimum_severity"] == "warning"
    with context.session_factory() as db:
        rows = (
            db.query(NotificationPreferencesModel)
            .filter_by(project_id=context.project_a)
            .all()
        )
        assert {(row.user_id, row.minimum_severity) for row in rows} == {
            (context.viewer[0], "critical"),
            (context.member[0], "warning"),
        }

    _authenticate(context.client, context.outsider)
    assert (
        context.client.get(
            f"/projects/{context.project_a}/notification-preferences"
        ).status_code
        == 403
    )


def test_concurrent_opening_keeps_one_active_alert(tmp_path):
    database_path = tmp_path / "alerts-race.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        organization = OrganizationModel(name="Course")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Course")
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Course")
        db.add(project)
        db.commit()
        project_id = project.id

    barrier = Barrier(2)
    output: list[tuple[str, str]] = []
    output_lock = Lock()

    def open_same_alert() -> None:
        with factory() as db:
            barrier.wait()
            alert, transition = open_or_escalate_alert(
                db,
                project_id=project_id,
                kind="automation_failure",
                severity="warning",
                title="Même cause",
                dimensions={"automation_id": "one"},
            )
            db.commit()
            with output_lock:
                output.append((alert.id, transition))

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(open_same_alert) for _ in range(2)]
            for future in futures:
                future.result(timeout=30)
        with factory() as db:
            rows = db.query(AlertModel).filter_by(project_id=project_id).all()
            opened_events = db.query(EventModel).filter_by(type="alert.opened").count()
        assert len(rows) == 1
        assert opened_events == 1
        assert len({alert_id for alert_id, _transition in output}) == 1
        assert sorted(transition for _alert_id, transition in output) == [
            "opened",
            "unchanged",
        ]
    finally:
        engine.dispose()
