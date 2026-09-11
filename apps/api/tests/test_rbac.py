"""Frontières d'accès des routes métier et des listes multi-projets."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.security import create_user_session, hash_password, utcnow
from acp_database.models import Base, UserModel

BOOTSTRAP_TOKEN = "rbac-bootstrap-token-with-enough-entropy"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def rbac_client(monkeypatch):
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={
                    "login": "owner",
                    "display_name": "Propriétaire",
                    "password": PASSWORD,
                },
            )
            assert response.status_code == 201
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _create_user_session(session_factory, login: str, platform_role: str):
    with session_factory() as db:
        user = UserModel(
            login_normalized=login,
            display_name=login.title(),
            password_hash=hash_password(PASSWORD),
            platform_role=platform_role,
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
        return user.id, session_token, csrf_token


def _authenticate(client: TestClient, session_token: str, csrf_token: str) -> None:
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _create_project(client: TestClient, suffix: str) -> dict[str, str]:
    organization = client.post("/organizations", json={"name": f"Org {suffix}"})
    assert organization.status_code == 200
    workspace = client.post(
        "/workspaces",
        json={"organization_id": organization.json()["id"], "name": f"Ws {suffix}"},
    )
    assert workspace.status_code == 200
    department = client.post(
        "/departments",
        json={
            "workspace_id": workspace.json()["id"],
            "name": f"Department {suffix}",
            "department_type": "software_development",
        },
    )
    assert department.status_code == 200
    project = client.post(
        "/projects",
        json={
            "workspace_id": workspace.json()["id"],
            "department_id": department.json()["id"],
            "name": f"Project {suffix}",
        },
    )
    assert project.status_code == 200
    agent = client.post(
        "/agents",
        json={
            "workspace_id": workspace.json()["id"],
            "name": f"Agent {suffix}",
            "role_id": "developer",
        },
    )
    assert agent.status_code == 200
    task = client.post(
        "/tasks",
        json={
            "project_id": project.json()["id"],
            "agent_instance_id": agent.json()["id"],
            "title": f"Task {suffix}",
        },
    )
    assert task.status_code == 200
    return {
        "organization_id": organization.json()["id"],
        "workspace_id": workspace.json()["id"],
        "department_id": department.json()["id"],
        "project_id": project.json()["id"],
        "agent_id": agent.json()["id"],
        "task_id": task.json()["id"],
    }


def test_business_routes_are_closed_without_a_server_session(rbac_client):
    client, _ = rbac_client
    client.cookies.clear()

    assert client.get("/health").status_code == 200
    for path in (
        "/organizations",
        "/workspaces",
        "/projects",
        "/tasks",
        "/task-runs",
        "/events",
        "/sessions",
        "/memberships",
        "/workers",
        "/overview",
        "/company/level",
        "/modules",
        "/locks",
        "/approvals",
        "/artifacts",
    ):
        assert client.get(path).status_code == 401, path
    assert client.post("/organizations", json={"name": "Interdite"}).status_code == 401


def test_memberships_filter_reads_and_gate_writes(rbac_client):
    client, session_factory = rbac_client
    first = _create_project(client, "A")
    second = _create_project(client, "B")
    for context in (first, second):
        session = client.post(
            "/sessions",
            json={
                "scope": "project",
                "workspace_id": context["workspace_id"],
                "project_id": context["project_id"],
            },
        )
        assert session.status_code == 200
        memory = client.post(
            "/memories",
            json={
                "scope": "PROJECT",
                "owner_id": context["project_id"],
                "content": {"project": context["project_id"]},
            },
        )
        assert memory.status_code == 200
        approval = client.post(
            "/approvals",
            json={
                "project_id": context["project_id"],
                "action": "git_publish",
                "reason": "Validation RBAC",
            },
        )
        assert approval.status_code == 201

    viewer_id, viewer_session, viewer_csrf = _create_user_session(
        session_factory, "viewer", "viewer"
    )
    operator_id, operator_session, operator_csrf = _create_user_session(
        session_factory, "operator", "operator"
    )
    for user_id, role in ((viewer_id, "viewer"), (operator_id, "member")):
        membership = client.post(
            "/memberships",
            json={
                "user_id": user_id,
                "scope_type": "workspace" if role == "member" else "project",
                "scope_id": (
                    first["workspace_id"] if role == "member" else first["project_id"]
                ),
                "role": role,
            },
        )
        assert membership.status_code == 200

    _authenticate(client, viewer_session, viewer_csrf)
    assert {row["id"] for row in client.get("/organizations").json()} == {
        first["organization_id"]
    }
    assert {row["id"] for row in client.get("/workspaces").json()} == {
        first["workspace_id"]
    }
    assert {row["id"] for row in client.get("/projects").json()} == {
        first["project_id"]
    }
    assert {row["id"] for row in client.get("/departments").json()} == {
        first["department_id"]
    }
    assert {row["id"] for row in client.get("/agents").json()} == {first["agent_id"]}
    assert {row["id"] for row in client.get("/tasks").json()} == {first["task_id"]}
    assert {row["project_id"] for row in client.get("/events").json()} == {
        first["project_id"]
    }
    assert {row["project_id"] for row in client.get("/sessions").json()} == {
        first["project_id"]
    }
    assert {row["project_id"] for row in client.get("/approvals").json()} == {
        first["project_id"]
    }
    overview = client.get("/overview").json()
    assert {row["id"] for row in overview["projects"]} == {first["project_id"]}
    assert {row["id"] for row in overview["workspaces"]} == {first["workspace_id"]}
    assert {row["id"] for row in overview["departments"]} == {
        first["department_id"]
    }
    assert {row["id"] for row in overview["agents"]} == {first["agent_id"]}
    assert (
        client.get(
            "/memories",
            params={"scope": "PROJECT", "owner_id": first["project_id"]},
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/memories",
            params={"scope": "PROJECT", "owner_id": second["project_id"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/tasks", json={"project_id": first["project_id"], "title": "Refusée"}
        ).status_code
        == 403
    )
    assert client.get("/workers").status_code == 403

    _authenticate(client, operator_session, operator_csrf)
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            "/tasks", json={"project_id": first["project_id"], "title": "Sans CSRF"}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = operator_csrf
    assert (
        client.post(
            "/tasks", json={"project_id": first["project_id"], "title": "Autorisée"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/tasks", json={"project_id": second["project_id"], "title": "Isolée"}
        ).status_code
        == 403
    )
    assert client.post("/organizations", json={"name": "Trop haut"}).status_code == 403
    assert client.get("/workers").status_code == 200
    assert (
        client.post(
            "/memberships",
            json={
                "user_id": operator_id,
                "scope_type": "workspace",
                "scope_id": second["workspace_id"],
                "role": "member",
            },
        ).status_code
        == 403
    )
