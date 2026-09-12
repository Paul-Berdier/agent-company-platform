"""Résolution des extensions (serveurs MCP et skills) d'un projet et instantané de mission.

Les lignes de bindings sont créées directement en base : ce module ne dépend ni des
routes MCP ni des routes skills, uniquement des modèles et de ``resolve_project_extensions``.
"""

from datetime import timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.extensions import resolve_project_extensions
from acp_api.main import app
from acp_api.security import create_user_session, hash_password, utcnow
from acp_database.models import (
    Base,
    McpBindingModel,
    McpServerModel,
    McpServerRevisionModel,
    SkillBindingModel,
    SkillModel,
    SkillRevisionModel,
    TaskModel,
    UserModel,
)

BOOTSTRAP_TOKEN = "extensions-bootstrap-token-with-enough-entropy"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def context(monkeypatch):
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
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={"login": "owner", "display_name": "Propriétaire", "password": PASSWORD},
            )
            assert bootstrap.status_code == 201
            client.headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
            organization = client.post("/organizations", json={"name": "Org"}).json()
            workspace = client.post(
                "/workspaces", json={"organization_id": organization["id"], "name": "Ws"}
            ).json()
            project_a = client.post(
                "/projects", json={"workspace_id": workspace["id"], "name": "Projet A"}
            ).json()
            project_b = client.post(
                "/projects", json={"workspace_id": workspace["id"], "name": "Projet B"}
            ).json()
            agent = client.post(
                "/agents",
                json={"workspace_id": workspace["id"], "name": "Agent", "role_id": "developer"},
            ).json()
            with session_factory() as db:
                owner_id = db.query(UserModel).filter_by(login_normalized="owner").one().id
            yield {
                "client": client,
                "session_factory": session_factory,
                "owner_id": owner_id,
                "workspace_id": workspace["id"],
                "project_a": project_a["id"],
                "project_b": project_b["id"],
                "agent_id": agent["id"],
            }
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


def _mcp_server(db, owner_id, *, name, status="active", revision_number=1):
    server = McpServerModel(
        name=name,
        display_name=name.title(),
        source_kind="manual",
        transport="http",
        execution_location="platform",
        status=status,
        created_by_user_id=owner_id,
    )
    db.add(server)
    db.flush()
    revision = McpServerRevisionModel(
        server_id=server.id,
        number=revision_number,
        config={"transport": "http", "http": {"url": "https://mcp.example/mcp"}},
        fingerprint="f" * 64,
        created_by_user_id=owner_id,
    )
    db.add(revision)
    db.flush()
    server.current_revision_id = revision.id
    return server, revision


def _mcp_binding(db, owner_id, server, revision, project_id, *, allowed_tools, enabled=1, revoked=False):
    binding = McpBindingModel(
        server_id=server.id,
        project_id=project_id,
        revision_id=revision.id,
        allowed_tools=allowed_tools,
        enabled=enabled,
        created_by_user_id=owner_id,
        revoked_at=utcnow() if revoked else None,
    )
    db.add(binding)
    db.flush()
    return binding


def _skill(db, owner_id, *, name, status="active", revision_number=1):
    skill = SkillModel(
        name=name,
        display_name=name.title(),
        kind="documentary",
        source_kind="manual",
        status=status,
        created_by_user_id=owner_id,
    )
    db.add(skill)
    db.flush()
    revision = SkillRevisionModel(
        skill_id=skill.id,
        number=revision_number,
        fingerprint="a" * 64,
        files=[{"path": "SKILL.md", "size": 10, "sha256": "b" * 64, "text": True}],
        skill_md="---\nname: x\n---\n",
        kind="documentary",
        storage_path="unused",
        created_by_user_id=owner_id,
    )
    db.add(revision)
    db.flush()
    skill.current_revision_id = revision.id
    return skill, revision


def _skill_binding(db, owner_id, skill, revision, project_id, *, enabled=1, revoked=False):
    binding = SkillBindingModel(
        skill_id=skill.id,
        project_id=project_id,
        revision_id=revision.id,
        enabled=enabled,
        created_by_user_id=owner_id,
        revoked_at=utcnow() if revoked else None,
    )
    db.add(binding)
    db.flush()
    return binding


def test_project_without_binding_resolves_to_empty_lists(context):
    with context["session_factory"]() as db:
        resolved = resolve_project_extensions(db, context["project_a"])
    assert resolved.project_id == context["project_a"]
    assert resolved.mcp == []
    assert resolved.skills == []
    assert resolved.resolved_at.tzinfo is not None
    assert resolved.resolved_at.utcoffset() == timezone.utc.utcoffset(None)


def test_enabled_mcp_binding_on_active_server_is_resolved(context):
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        server, revision = _mcp_server(db, owner_id, name="context7", revision_number=3)
        _mcp_binding(
            db, owner_id, server, revision, context["project_a"], allowed_tools=["resolve", "docs"]
        )
        db.commit()
        resolved = resolve_project_extensions(db, context["project_a"])
        other = resolve_project_extensions(db, context["project_b"])
    assert len(resolved.mcp) == 1
    extension = resolved.mcp[0]
    assert extension.server_id == server.id
    assert extension.name == "context7"
    assert extension.revision_number == 3
    assert extension.allowed_tools == ["resolve", "docs"]
    assert extension.enabled is True
    assert extension.server_status == "active"
    assert other.mcp == []


@pytest.mark.parametrize(
    ("server_status", "binding_enabled", "binding_revoked"),
    [
        ("disabled", 1, False),
        ("revoked", 1, False),
        ("draft", 1, False),
        ("active", 0, False),
        ("active", 1, True),
    ],
)
def test_mcp_binding_is_absent_when_server_or_binding_is_not_usable(
    context, server_status, binding_enabled, binding_revoked
):
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        server, revision = _mcp_server(db, owner_id, name="srv", status=server_status)
        _mcp_binding(
            db,
            owner_id,
            server,
            revision,
            context["project_a"],
            allowed_tools=["tool"],
            enabled=binding_enabled,
            revoked=binding_revoked,
        )
        db.commit()
        resolved = resolve_project_extensions(db, context["project_a"])
    assert resolved.mcp == []


def test_enabled_skill_binding_on_active_skill_is_resolved(context):
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        skill, revision = _skill(db, owner_id, name="pdf-tools", revision_number=2)
        _skill_binding(db, owner_id, skill, revision, context["project_a"])
        db.commit()
        resolved = resolve_project_extensions(db, context["project_a"])
        other = resolve_project_extensions(db, context["project_b"])
    assert len(resolved.skills) == 1
    extension = resolved.skills[0]
    assert extension.skill_id == skill.id
    assert extension.name == "pdf-tools"
    assert extension.revision_number == 2
    assert extension.enabled is True
    assert extension.skill_status == "active"
    assert other.skills == []


@pytest.mark.parametrize(
    ("skill_status", "binding_enabled", "binding_revoked"),
    [
        ("disabled", 1, False),
        ("revoked", 1, False),
        ("draft", 1, False),
        ("active", 0, False),
        ("active", 1, True),
    ],
)
def test_skill_binding_is_absent_when_skill_or_binding_is_not_usable(
    context, skill_status, binding_enabled, binding_revoked
):
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        skill, revision = _skill(db, owner_id, name="skill", status=skill_status)
        _skill_binding(
            db,
            owner_id,
            skill,
            revision,
            context["project_a"],
            enabled=binding_enabled,
            revoked=binding_revoked,
        )
        db.commit()
        resolved = resolve_project_extensions(db, context["project_a"])
    assert resolved.skills == []


def test_binding_revision_is_the_bound_revision_not_the_current_one(context):
    """Une révision devenue courante sans activation ne change pas la révision liée."""

    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        skill, revision = _skill(db, owner_id, name="pinned", revision_number=1)
        _skill_binding(db, owner_id, skill, revision, context["project_a"])
        newer = SkillRevisionModel(
            skill_id=skill.id,
            number=2,
            fingerprint="c" * 64,
            files=[],
            kind="documentary",
            storage_path="unused",
            created_by_user_id=owner_id,
        )
        db.add(newer)
        db.flush()
        skill.current_revision_id = newer.id
        db.commit()
        resolved = resolve_project_extensions(db, context["project_a"])
    assert [item.revision_number for item in resolved.skills] == [1]


def test_extensions_route_requires_viewer_access(context):
    client = context["client"]
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        server, revision = _mcp_server(db, owner_id, name="bound")
        _mcp_binding(db, owner_id, server, revision, context["project_a"], allowed_tools=["t"])
        db.commit()

    response = client.get(f"/projects/{context['project_a']}/extensions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == context["project_a"]
    assert [item["name"] for item in body["mcp"]] == ["bound"]
    assert body["skills"] == []
    assert client.get(f"/projects/{context['project_b']}/extensions").json()["mcp"] == []
    assert client.get(f"/projects/{uuid4()}/extensions").status_code == 404

    _, viewer_session, viewer_csrf = _create_user_session(
        context["session_factory"], "viewer", "viewer"
    )
    viewer_id = None
    with context["session_factory"]() as db:
        viewer_id = db.query(UserModel).filter_by(login_normalized="viewer").one().id
    membership = client.post(
        "/memberships",
        json={
            "user_id": viewer_id,
            "scope_type": "project",
            "scope_id": context["project_a"],
            "role": "viewer",
        },
    )
    assert membership.status_code == 200
    client.cookies.clear()
    client.cookies.set("acp_session", viewer_session)
    client.headers["X-CSRF-Token"] = viewer_csrf
    assert client.get(f"/projects/{context['project_a']}/extensions").status_code == 200
    assert client.get(f"/projects/{context['project_b']}/extensions").status_code == 403
    client.cookies.clear()
    assert client.get(f"/projects/{context['project_a']}/extensions").status_code == 401


def _mission_payload(context):
    return {
        "project_id": context["project_a"],
        "agent_instance_id": context["agent_id"],
        "title": "Mission avec extensions",
        "objective": "Produire une modification vérifiable",
        "expected_outcome": "Une sortie testée",
        "acceptance_criteria": ["les tests passent"],
        "autonomy": {"mode": "bounded"},
        "budget": {"max_tokens": 1000},
        "duration_seconds": 3600,
    }


def test_mission_creation_freezes_the_extensions_snapshot(context):
    client = context["client"]
    owner_id = context["owner_id"]
    with context["session_factory"]() as db:
        server, revision = _mcp_server(db, owner_id, name="frozen-mcp", revision_number=1)
        _mcp_binding(db, owner_id, server, revision, context["project_a"], allowed_tools=["a"])
        skill, skill_revision = _skill(db, owner_id, name="frozen-skill", revision_number=1)
        _skill_binding(db, owner_id, skill, skill_revision, context["project_a"])
        db.commit()

    created = client.post(
        "/missions",
        headers={"Idempotency-Key": f"create-{uuid4().hex}"},
        json=_mission_payload(context),
    )
    assert created.status_code == 201, created.text
    mission_id = created.json()["id"]

    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission_id)
        snapshot = task.meta["extensions"]
        assert task.meta["mission"] is True  # les clés existantes sont conservées
        assert snapshot["project_id"] == context["project_a"]
        assert [item["name"] for item in snapshot["mcp"]] == ["frozen-mcp"]
        assert snapshot["mcp"][0]["revision_number"] == 1
        assert snapshot["mcp"][0]["allowed_tools"] == ["a"]
        assert [item["name"] for item in snapshot["skills"]] == ["frozen-skill"]
        assert snapshot["skills"][0]["revision_number"] == 1
        assert isinstance(snapshot["resolved_at"], str)

        # Une révision ultérieure et un nouveau binding ne modifient pas l'instantané.
        newer = SkillRevisionModel(
            skill_id=skill.id,
            number=2,
            fingerprint="d" * 64,
            files=[],
            kind="documentary",
            storage_path="unused",
            created_by_user_id=owner_id,
        )
        db.add(newer)
        db.flush()
        skill.current_revision_id = newer.id
        binding = db.query(SkillBindingModel).filter_by(skill_id=skill.id).one()
        binding.revision_id = newer.id
        other_server, other_revision = _mcp_server(db, owner_id, name="later-mcp")
        _mcp_binding(db, owner_id, other_server, other_revision, context["project_a"], allowed_tools=["z"])
        db.commit()

    live = client.get(f"/projects/{context['project_a']}/extensions").json()
    assert {item["name"] for item in live["mcp"]} == {"frozen-mcp", "later-mcp"}
    assert live["skills"][0]["revision_number"] == 2

    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission_id)
        assert task.meta["extensions"] == snapshot

    detail = client.get(f"/missions/{mission_id}")
    assert detail.status_code == 200
    assert "extensions" not in detail.json()  # le contrat MissionSummary n'est pas modifié
