"""Tests de persistance, reprise et isolation des conversations Hermes."""

from datetime import UTC, datetime, timedelta

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.gateway import (
    GatewayClient,
    GatewayDiagnostic,
    GatewayRun,
    GatewayUnavailableError,
    get_gateway_client,
)
from acp_api.main import app
from acp_api.security import create_user_session, hash_password
from acp_database.models import (
    Base,
    ConversationModel,
    ConversationTurnModel,
    MembershipModel,
    OrganizationModel,
    ProjectModel,
    UserModel,
    WorkerModel,
    WorkspaceModel,
)

BOOTSTRAP_TOKEN = "conversation-bootstrap-token"
PASSWORD = "conversation test password"
RUN_ID = "run_0123456789abcdef0123456789abcdef"


class FakeGateway(GatewayClient):
    def __init__(self) -> None:
        self.submit_keys: list[str] = []
        self.fail_first_submission = False
        self.status_reads = 0
        self.read_status = "completed"
        self.submit_status = "queued"
        self.stop_failures = 0
        self.stopped_runs = []

    async def diagnose_hermes(self) -> GatewayDiagnostic:
        return GatewayDiagnostic(
            provider_id="hermes",
            status="ready",
            configured=True,
            ready=True,
            expected_version="0.21.1",
            detected_version="0.21.1",
            model="hermes-agent",
            latency_ms=12.5,
            detail="Hermes est prêt.",
        )

    async def submit_hermes_run(self, **kwargs) -> GatewayRun:
        self.submit_keys.append(kwargs["idempotency_key"])
        if self.fail_first_submission and len(self.submit_keys) == 1:
            raise GatewayUnavailableError("coupure simulée")
        return GatewayRun(run_id=RUN_ID, status=self.submit_status)

    async def get_hermes_run(self, run_id: str) -> GatewayRun:
        assert run_id == RUN_ID
        self.status_reads += 1
        return GatewayRun(
            run_id=RUN_ID,
            status=self.read_status,
            session_id="hermes-session",
            model="hermes-agent",
            output="Réponse Hermes persistée",
            usage={"input_tokens": 4, "output_tokens": 3},
        )


    async def stop_hermes_run(self, run_id: str) -> GatewayRun:
        self.stopped_runs.append(run_id)
        if self.stop_failures:
            self.stop_failures -= 1
            raise GatewayUnavailableError("arrêt indéterminé")
        return GatewayRun(run_id=run_id, status="stopping")


@pytest.fixture
def conversation_client(monkeypatch):
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    gateway = FakeGateway()

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_gateway_client] = lambda: gateway
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={
                    "login": "owner",
                    "display_name": "Propriétaire",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201
            csrf = bootstrap.json()["csrf_token"]
            with session_factory() as db:
                organization = OrganizationModel(name="Organisation")
                db.add(organization)
                db.flush()
                workspace = WorkspaceModel(
                    organization_id=organization.id,
                    name="Espace",
                )
                db.add(workspace)
                db.flush()
                project = ProjectModel(workspace_id=workspace.id, name="Projet")
                db.add(project)
                db.commit()
                project_id = project.id
                workspace_id = workspace.id
            yield client, session_factory, gateway, csrf, project_id, workspace_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_gateway_client, None)
        engine.dispose()


def _create_conversation(client: TestClient, csrf: str, project_id: str | None):
    response = client.post(
        "/conversations",
        headers={"X-CSRF-Token": csrf},
        json={"project_id": project_id, "title": "Diagnostic du projet"},
    )
    assert response.status_code == 201
    return response.json()


def test_conversation_is_persisted_and_completed_after_reload(conversation_client):
    client, session_factory, gateway, csrf, project_id, _ = conversation_client
    conversation = _create_conversation(client, csrf, project_id)

    accepted = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json={"client_request_id": "browser-request-1", "content": "Analyse ceci"},
    )
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "running"
    assert len(gateway.submit_keys) == 1

    resumed = client.get(
        f"/conversations/{conversation['id']}/turns/{accepted.json()['id']}"
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["assistant_content"] == "Réponse Hermes persistée"
    assert resumed.json()["usage"]["output_tokens"] == 3

    detail = client.get(f"/conversations/{conversation['id']}").json()
    assert detail["turns"][0]["assistant_content"] == "Réponse Hermes persistée"
    with session_factory() as db:
        assert db.query(ConversationModel).count() == 1
        assert db.query(ConversationTurnModel).count() == 1


def test_retry_after_uncertain_submission_reuses_the_same_idempotency_key(
    conversation_client,
):
    client, session_factory, gateway, csrf, project_id, _ = conversation_client
    gateway.fail_first_submission = True
    conversation = _create_conversation(client, csrf, project_id)
    payload = {"client_request_id": "stable-request", "content": "Reprendre sans doublon"}

    first = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert first.status_code == 202
    assert first.json()["status"] == "submitting"
    assert "même clé d'idempotence" in first.json()["error"]

    retry = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert retry.status_code == 202
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["status"] == "running"
    assert gateway.submit_keys[0] == gateway.submit_keys[1]
    with session_factory() as db:
        assert db.query(ConversationTurnModel).count() == 1

    conflict = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json={**payload, "content": "Autre contenu"},
    )
    assert conflict.status_code == 409


def test_general_conversation_is_private_and_project_write_requires_role(
    conversation_client,
):
    client, session_factory, _, csrf, project_id, workspace_id = conversation_client
    general = _create_conversation(client, csrf, None)
    project_conversation = _create_conversation(client, csrf, project_id)

    with session_factory() as db:
        viewer = UserModel(
            login_normalized=f"viewer-{uuid4().hex}",
            display_name="Lecteur",
            password_hash=hash_password(PASSWORD),
            platform_role="viewer",
            bootstrap_marker=None,
        )
        db.add(viewer)
        db.flush()
        db.add(
            MembershipModel(
                user_id=viewer.id,
                scope_type="workspace",
                scope_id=workspace_id,
                role="viewer",
            )
        )
        session, session_token, viewer_csrf = create_user_session(db, viewer.id)
        db.commit()
        assert session.id

    client.cookies.set("acp_session", session_token)
    assert client.get(f"/conversations/{general['id']}").status_code == 404
    assert client.get(f"/conversations/{project_conversation['id']}").status_code == 200
    denied = client.post(
        f"/conversations/{project_conversation['id']}/turns",
        headers={"X-CSRF-Token": viewer_csrf},
        json={"client_request_id": "viewer-write", "content": "Interdit"},
    )
    assert denied.status_code == 403
    visible_ids = {item["id"] for item in client.get("/conversations").json()["items"]}
    assert general["id"] not in visible_ids
    assert project_conversation["id"] in visible_ids


def test_hermes_diagnostic_is_authenticated_and_mapped(conversation_client):
    client, _, _, csrf, _, _ = conversation_client
    diagnostic = client.post(
        "/connections/hermes/diagnostic",
        headers={"X-CSRF-Token": csrf},
    )
    assert diagnostic.status_code == 200
    assert diagnostic.json()["status"] == "connected"
    assert diagnostic.json()["healthy"] is True
    assert diagnostic.json()["capabilities"] == ["runs", "model:hermes-agent"]

    client.cookies.clear()
    assert client.get("/connections/hermes/diagnostic").status_code == 401


def test_onboarding_creates_a_personal_project_without_exposing_hierarchy(
    conversation_client,
):
    client, session_factory, _, csrf, _, _ = conversation_client
    before = client.get("/onboarding/status")
    assert before.status_code == 200
    assert before.json()["bootstrap_completed"] is True
    assert before.json()["hermes_ready"] is True
    assert before.json()["project_count"] == 1
    assert before.json()["runner_ready"] is False

    created = client.post(
        "/onboarding/projects",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Mon premier projet",
            "project_type": "research",
            "description": "Un contexte volontairement court.",
        },
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Mon premier projet"
    with session_factory() as db:
        workspace = db.get(WorkspaceModel, created.json()["workspace_id"])
        assert workspace is not None
        assert workspace.kind == "personal"
        assert (
            db.query(MembershipModel)
            .filter_by(scope_type="project", scope_id=created.json()["id"])
            .count()
            == 1
        )

    after = client.get("/onboarding/status")
    assert after.json()["project_count"] == 2


def test_onboarding_quarantines_an_online_worker_without_effective_scope(
    conversation_client,
):
    client, session_factory, _, _, project_id, _ = conversation_client
    with session_factory() as db:
        worker = WorkerModel(
            name="legacy-unscoped-runner",
            token_hash="0" * 64,
            token_prefix="legacy",
            token_expires_at=datetime.now(UTC) + timedelta(days=1),
            capabilities=[],
            max_concurrency=1,
            active_runs=0,
            status="online",
            simulation=0,
            project_id=None,
            global_access=0,
            metadata_json={},
        )
        db.add(worker)
        db.commit()
        worker_id = worker.id

    assert client.get("/onboarding/status").json()["runner_ready"] is False

    with session_factory() as db:
        worker = db.get(WorkerModel, worker_id)
        assert worker is not None
        worker.project_id = project_id
        db.commit()

    assert client.get("/onboarding/status").json()["runner_ready"] is True


def test_conversation_can_be_renamed_exported_and_archived(conversation_client):
    client, _, _, csrf, project_id, _ = conversation_client
    conversation = _create_conversation(client, csrf, project_id)

    renamed = client.patch(
        f"/conversations/{conversation['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"title": "Compte rendu final"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Compte rendu final"
    searched = client.get("/conversations", params={"search": "RENDU"}).json()
    assert [item["id"] for item in searched["items"]] == [conversation["id"]]

    exported = client.get(f"/conversations/{conversation['id']}/export")
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "private, no-store"
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["id"] == conversation["id"]

    archived = client.patch(
        f"/conversations/{conversation['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"status": "archived"},
    )
    assert archived.json()["status"] == "archived"
    denied = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json={"client_request_id": "after-archive", "content": "Ne pas envoyer"},
    )
    assert denied.status_code == 409


def _submit_turn(client, csrf, conversation, key="request-stop"):
    result = client.post(
        f"/conversations/{conversation['id']}/turns",
        headers={"X-CSRF-Token": csrf},
        json={"client_request_id": key, "content": "Un travail interruptible"},
    )
    assert result.status_code == 202
    return result.json()


def test_waiting_approval_is_explicit_and_stop_intent_survives_transport_error(conversation_client):
    client, factory, gateway, csrf, project_id, _ = conversation_client
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    path = f"/conversations/{conversation['id']}/turns/{turn['id']}"
    gateway.read_status = "waiting_for_approval"
    waiting = client.get(path).json()
    assert waiting["status"] == "waiting_for_approval"
    assert "approbation" in waiting["error"]
    gateway.stop_failures = 1
    stopped = client.post(path + "/stop", headers={"X-CSRF-Token": csrf})
    assert stopped.status_code == 202
    assert stopped.json()["status"] == "stopping"
    assert "pas encore confirmé" in stopped.json()["error"]
    with factory() as db:
        assert db.get(ConversationTurnModel, turn["id"]).status == "stopping"
    gateway.read_status = "running"
    resumed = client.get(path)
    assert resumed.json()["status"] == "stopping"
    assert gateway.stopped_runs == [RUN_ID, RUN_ID]
    gateway.read_status = "cancelled"
    assert client.get(path).json()["status"] == "interrupted"
    assert client.post(path + "/stop", headers={"X-CSRF-Token": csrf}).json()["status"] == "interrupted"
    assert len(gateway.stopped_runs) == 2
    assert len(gateway.submit_keys) == 1


def test_stop_recovers_uncertain_admission_with_original_key(conversation_client):
    client, _, gateway, csrf, project_id, _ = conversation_client
    gateway.fail_first_submission = True
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    assert turn["status"] == "submitting"
    result = client.post(
        f"/conversations/{conversation['id']}/turns/{turn['id']}/stop",
        headers={"X-CSRF-Token": csrf},
    )
    assert result.status_code == 202
    assert result.json()["status"] == "stopping"
    assert gateway.submit_keys[0] == gateway.submit_keys[1]
    assert gateway.stopped_runs == [RUN_ID]


def test_expired_ambiguous_admission_is_never_recreated(conversation_client):
    client, factory, gateway, csrf, project_id, _ = conversation_client
    gateway.fail_first_submission = True
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    with factory() as db:
        row = db.get(ConversationTurnModel, turn["id"])
        row.created_at = datetime.now(UTC) - timedelta(hours=25)
        db.commit()
    result = client.get(f"/conversations/{conversation['id']}/turns/{turn['id']}")
    assert result.json()["status"] == "submitting"
    assert "Aucun nouveau run" in result.json()["error"]
    assert len(gateway.submit_keys) == 1


def test_replayed_terminal_admission_is_read_before_completed(conversation_client):
    client, _, gateway, csrf, project_id, _ = conversation_client
    gateway.submit_status = "completed"
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    assert turn["status"] == "completed"
    assert turn["assistant_content"] == "Réponse Hermes persistée"
    assert gateway.status_reads == 1


def test_late_read_cannot_erase_stop_intent_or_terminal_result(conversation_client):
    from acp_api.routers.conversations import _apply_run
    client, factory, _, csrf, project_id, _ = conversation_client
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    with factory() as stale_db:
        stale_turn = stale_db.get(ConversationTurnModel, turn["id"])
        stale_conversation = stale_db.get(ConversationModel, conversation["id"])
        with factory() as other:
            other.get(ConversationTurnModel, turn["id"]).status = "stopping"
            other.commit()
        _apply_run(stale_db, stale_conversation, stale_turn, GatewayRun(run_id=RUN_ID, status="running"))
        assert stale_turn.status == "stopping"
        with factory() as other:
            row = other.get(ConversationTurnModel, turn["id"])
            row.status = "completed"
            row.assistant_content = "preuve finale"
            other.commit()
        _apply_run(stale_db, stale_conversation, stale_turn, GatewayRun(run_id=RUN_ID, status="running"))
        assert stale_turn.status == "completed"
        assert stale_turn.assistant_content == "preuve finale"


def test_stop_requires_csrf_and_member_access(conversation_client):
    client, factory, gateway, csrf, project_id, workspace_id = conversation_client
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    path = f"/conversations/{conversation['id']}/turns/{turn['id']}/stop"
    assert client.post(path).status_code == 403
    with factory() as db:
        user = UserModel(login_normalized="stop-viewer", display_name="Lecteur",
                         password_hash=hash_password(PASSWORD), platform_role="viewer")
        db.add(user)
        db.flush()
        db.add(MembershipModel(user_id=user.id, scope_type="workspace", scope_id=workspace_id, role="viewer"))
        _, token, viewer_csrf = create_user_session(db, user.id)
        db.commit()
    client.cookies.set("acp_session", token)
    assert client.post(path, headers={"X-CSRF-Token": viewer_csrf}).status_code == 403
    assert gateway.stopped_runs == []


@pytest.mark.parametrize("admission_status", ["queued", "completed"])
def test_terminal_get_without_output_is_a_failure_including_replayed_admission(conversation_client, admission_status):
    client, _, gateway, csrf, project_id, _ = conversation_client
    gateway.submit_status = admission_status
    async def empty_result(run_id):
        return GatewayRun(run_id=run_id, status="completed", output="  ")
    gateway.get_hermes_run = empty_result
    conversation = _create_conversation(client, csrf, project_id)
    turn = _submit_turn(client, csrf, conversation)
    result = client.get(f"/conversations/{conversation['id']}/turns/{turn['id']}")
    assert result.json()["status"] == "failed"
    assert result.json()["assistant_content"] is None
    assert "sans réponse exploitable" in result.json()["error"]
    assert len(gateway.submit_keys) == 1
