"""Intégration de la tranche métier mission, y compris les refus de sécurité."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from acp_api import budget_service
from acp_api.deps import get_db
from acp_api.main import app
from acp_api.routers import missions as missions_router
from acp_api.routers.work import _compare_and_set_run_status
from acp_api.security import create_user_session, hash_password, utcnow
from acp_database.engine import _upgrade_sqlite_schema
from acp_database.models import (
    ApprovalModel,
    MembershipModel,
    MissionCommandModel,
    MissionCommentModel,
    TaskModel,
    TaskRunModel,
    UserModel,
)
from acp_database.testing import make_test_engine


@pytest.fixture
def mission_context(monkeypatch, tmp_path):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    registration_token = f"registration-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", registration_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    database = make_test_engine(tmp_path, concurrent=True)
    session_factory = sessionmaker(bind=database.engine, expire_on_commit=False)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": f"owner-{uuid4().hex}",
                    "display_name": "Mission owner",
                    "password": "correct horse battery staple",
                },
            )
            assert bootstrap.status_code == 201
            client.headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
            organization = client.post("/organizations", json={"name": "Mission org"}).json()
            workspace = client.post(
                "/workspaces",
                json={"organization_id": organization["id"], "name": "Mission ws"},
            ).json()
            project = client.post(
                "/projects",
                json={"workspace_id": workspace["id"], "name": "Mission project"},
            ).json()
            monkeypatch.setenv(
                "ACP_WORKER_REGISTRATION_PROJECT_ID", project["id"]
            )
            monkeypatch.setenv("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", "0")
            agent = client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Mission agent",
                    "role_id": "developer",
                },
            ).json()
            registration = client.post(
                "/workers/register",
                headers={"X-Worker-Registration-Token": registration_token},
                json={
                    "name": f"mission-worker-{uuid4().hex}",
                    "capabilities": ["git"],
                    "max_concurrency": 1,
                    "simulation": False,
                    "project_id": project["id"],
                },
            )
            assert registration.status_code == 201
            yield {
                "client": client,
                "session_factory": session_factory,
                "project_id": project["id"],
                "workspace_id": workspace["id"],
                "agent_id": agent["id"],
                "worker": registration.json(),
                "registration_token": registration_token,
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close()


def _mission_payload(context, title="Mission test"):
    return {
        "project_id": context["project_id"],
        "agent_instance_id": context["agent_id"],
        "title": title,
        "objective": "Produire une modification vérifiable",
        "expected_outcome": "Une sortie testée et documentée",
        "acceptance_criteria": ["les tests passent", "la preuve est consultable"],
        "autonomy": {
            "mode": "bounded",
            "allowed_actions": ["read", "edit_project"],
            "forbidden_actions": ["deploy"],
            "approval_required_actions": ["git_publish"],
        },
        "resources": [
            {
                "kind": "git_repository",
                "identifier": "workspace",
                "access": "write",
            }
        ],
        "budget": {"max_tokens": 10_000, "max_tool_calls": 50},
        "duration_seconds": 3600,
        "required_capabilities": ["git"],
    }


def _create_mission(context, title="Mission test", *, idempotency_key=None):
    response = context["client"].post(
        "/missions",
        headers={"Idempotency-Key": idempotency_key or f"create-{uuid4().hex}"},
        json=_mission_payload(context, title),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _worker_headers(context, *, fencing_token=None):
    worker = context["worker"]
    headers = {
        "Authorization": f"Bearer {worker['token']}",
        "X-Worker-Id": worker["worker_id"],
    }
    if fencing_token is not None:
        headers["X-Attempt-Fencing-Token"] = str(fencing_token)
    return headers


def _claim(context):
    worker = context["worker"]
    response = context["client"].post(
        f"/workers/{worker['worker_id']}/claim",
        headers={"Authorization": f"Bearer {worker['token']}"},
        json={"provider_id": "mock"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_multi_agent_execution_survives_admission_read_and_worker_claim(mission_context):
    from acp_database.models import WorkerModel
    client = mission_context["client"]
    body = _mission_payload(mission_context)
    body.update(autonomy={"mode": "supervised"},
                resources=[{"kind": "project_workspace", "identifier": body["project_id"], "access": "read"}],
                budget={"max_tool_calls": 12},
                required_capabilities=["agent_team", "codex_cli", "claude_code"],
                execution={"mode": "multi_agent", "executors": ["codex_cli", "claude_code"], "max_concurrency": 2})
    with mission_context["session_factory"]() as db:
        worker = db.get(WorkerModel, mission_context["worker"]["worker_id"])
        worker.capabilities = body["required_capabilities"]
        db.commit()
    response = client.post("/missions", json=body, headers={"Idempotency-Key": "team-create"})
    assert response.status_code == 201, response.text
    mission = response.json()
    assert mission["execution"] == body["execution"]
    assert client.get(f"/missions/{mission['id']}").json()["execution"] == body["execution"]
    updated = client.put(f"/projects/{body['project_id']}/budget-policy",
                         json={"max_spawned_agents_per_run": 2})
    assert updated.status_code == 200, updated.text
    claim = _claim(mission_context)
    assert claim["mission"]["execution"] == body["execution"]
    assert claim["execution_limits"]["max_agents"] == 2


def test_worker_receives_pinned_skill_and_revocation_blocks_later_reads(mission_context):
    import hashlib
    from acp_database.models import SkillModel, SkillRevisionModel, SkillBindingModel
    content = "# Compétence approuvée\nComparer les résultats avec les critères de la mission.\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    client = mission_context["client"]
    with mission_context["session_factory"]() as db:
        owner = db.query(UserModel).filter_by(platform_role="owner").one()
        skill = SkillModel(name="qa-guide", display_name="Guide QA", kind="documentary",
                           source_kind="manual", status="active", created_by_user_id=owner.id)
        db.add(skill)
        db.flush()
        revision = SkillRevisionModel(skill_id=skill.id, number=1, fingerprint=digest,
            files=[{"path": "SKILL.md", "sha256": digest, "size": len(content.encode()), "text": True}],
            skill_md=content, kind="documentary", storage_path="fixture-not-read",
            requires_approval=1, approved_at=utcnow(), approval_fingerprint=digest,
            approved_by_user_id=owner.id, created_by_user_id=owner.id)
        db.add(revision)
        db.flush()
        skill.current_revision_id = revision.id
        binding = SkillBindingModel(skill_id=skill.id, revision_id=revision.id,
            project_id=mission_context["project_id"], enabled=1, created_by_user_id=owner.id)
        db.add(binding)
        db.commit()
        skill_id = skill.id
    _create_mission(mission_context, idempotency_key="skill-execution")
    claim = _claim(mission_context)
    worker = mission_context["worker"]
    url = f"/work/workers/{worker['worker_id']}/runs/{claim['attempt_id']}/extensions"
    headers = {"Authorization": f"Bearer {worker['token']}",
               "X-Attempt-Fencing-Token": str(claim["fencing_token"])}
    response = client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["skills"][0]["content"] == content
    assert client.get(url).status_code in {401, 409}
    with mission_context["session_factory"]() as db:
        db.get(TaskRunModel, claim["attempt_id"]).status = "stopping"
        db.commit()
    assert client.get(url, headers=headers).status_code == 409
    with mission_context["session_factory"]() as db:
        db.get(TaskRunModel, claim["attempt_id"]).status = "preparing"
        db.commit()
    assert client.get(url, headers=headers).status_code == 200
    with mission_context["session_factory"]() as db:
        db.get(SkillModel, skill_id).status = "revoked"
        db.commit()
    assert client.get(url, headers=headers).status_code == 409


def test_create_stop_retry_and_comments_are_pilotable_and_idempotent(mission_context):
    client = mission_context["client"]
    invalid = _mission_payload(mission_context)
    invalid["budget"] = {}
    assert client.post("/missions", json=invalid).status_code == 422
    assert client.post(
        "/missions", json=_mission_payload(mission_context)
    ).status_code == 400

    create_key = "create-mission-1"
    mission = _create_mission(mission_context, idempotency_key=create_key)
    create_replay = client.post(
        "/missions",
        headers={"Idempotency-Key": create_key},
        json=_mission_payload(mission_context),
    )
    assert create_replay.status_code == 201
    assert create_replay.json()["id"] == mission["id"]
    changed_payload = _mission_payload(mission_context)
    changed_payload["objective"] = "Une intention différente"
    assert client.post(
        "/missions",
        headers={"Idempotency-Key": create_key},
        json=changed_payload,
    ).status_code == 409
    listed_missions = client.get("/missions").json()
    assert len(listed_missions) == 1
    assert listed_missions[0]["required_capabilities"] == ["git"]
    sibling_project = client.post(
        "/projects",
        json={
            "workspace_id": mission_context["workspace_id"],
            "name": "Sibling project for assignment",
        },
    )
    assert sibling_project.status_code == 200
    sibling_team = client.post(
        "/teams",
        json={"project_id": sibling_project.json()["id"], "name": "Sibling team"},
    )
    assert sibling_team.status_code == 200
    sibling_agent = client.post(
        "/agents",
        json={
            "workspace_id": mission_context["workspace_id"],
            "team_id": sibling_team.json()["id"],
            "name": "Sibling-only agent",
            "role_id": "developer",
        },
    )
    assert sibling_agent.status_code == 200

    with mission_context["session_factory"]() as db:
        creation_command = (
            db.query(MissionCommandModel)
            .filter_by(command="create", idempotency_key=create_key)
            .one()
        )
        assert creation_command.task_id == mission["id"]
        assert creation_command.principal_id
        assert len(creation_command.request_fingerprint) == 64
    assert mission["status"] == "queued"
    assert mission["current_run"]["attempt_number"] == 1
    assert mission["objective"] == "Produire une modification vérifiable"
    assert mission["team_id"] is None
    assert mission["agent_instance_id"] == mission_context["agent_id"]
    assert mission["autonomy"]["mode"] == "bounded"
    assert mission["resources"][0]["identifier"] == "workspace"
    assert mission["budget"]["max_tokens"] == 10_000
    assert mission["required_capabilities"] == ["git"]
    mission_id = mission["id"]

    first_run_id = mission["current_run"]["id"]
    comment_payload = {
        "run_id": first_run_id,
        "body": "  Vérifier aussi le journal.  ",
    }
    comment = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "comment-1"},
        json=comment_payload,
    )
    replay = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "comment-1"},
        json=comment_payload,
    )
    assert comment.status_code == replay.status_code == 201
    assert replay.json()["id"] == comment.json()["id"]
    assert replay.json()["body"] == "Vérifier aussi le journal."
    assert replay.json()["run_id"] == first_run_id
    conflicting_comment = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "comment-1"},
        json={"run_id": first_run_id, "body": "Corps différent"},
    )
    assert conflicting_comment.status_code == 409
    missing_run = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "comment-without-run"},
        json={"body": "Commentaire non lié"},
    )
    assert missing_run.status_code == 422
    assert len(client.get(f"/missions/{mission_id}/comments").json()) == 1

    assert client.post(f"/missions/{mission_id}/stop").status_code == 400
    stop_headers = {"Idempotency-Key": "stop-attempt-1"}
    stopped = client.post(f"/missions/{mission_id}/stop", headers=stop_headers)
    stopped_again = client.post(
        f"/missions/{mission_id}/stop", headers=stop_headers
    )
    assert stopped.status_code == stopped_again.status_code == 200
    assert stopped.json()["run"]["status"] == "cancelled"
    assert stopped.json()["already_stopped"] is False
    assert stopped_again.json()["already_stopped"] is True
    assert client.post(f"/tasks/{mission_id}/queue").status_code == 409
    generic_patch = client.patch(
        f"/tasks/{mission_id}", json={"title": "Contournement générique"}
    )
    assert generic_patch.status_code == 409
    assert client.get(f"/missions/{mission_id}").json()["title"] == mission["title"]
    ordinary = client.post(
        "/tasks",
        json={
            "project_id": mission_context["project_id"],
            "title": "Tâche ordinaire",
        },
    )
    assert ordinary.status_code == 200
    ordinary_patch = client.patch(
        f"/tasks/{ordinary.json()['id']}", json={"title": "Tâche modifiée"}
    )
    assert ordinary_patch.status_code == 200
    assert ordinary_patch.json()["title"] == "Tâche modifiée"
    assert len(client.get(f"/missions/{mission_id}/runs").json()) == 1

    assert (
        client.post(f"/missions/{mission_id}/retry", json={"reason": "Nouvel essai"})
        .status_code
        == 400
    )
    retried = client.post(
        f"/missions/{mission_id}/retry",
        headers={"Idempotency-Key": "retry-1"},
        json={"reason": "Nouvel essai contrôlé"},
    )
    replayed = client.post(
        f"/missions/{mission_id}/retry",
        headers={"Idempotency-Key": "retry-1"},
        json={"reason": "Nouvel essai contrôlé"},
    )
    assert retried.status_code == replayed.status_code == 201
    assert retried.json()["id"] == replayed.json()["id"]
    changed_retry = client.post(
        f"/missions/{mission_id}/retry",
        headers={"Idempotency-Key": "retry-1"},
        json={"reason": "Corps différent"},
    )
    assert changed_retry.status_code == 409
    assert retried.json()["attempt_number"] == 2
    assert retried.json()["fencing_token"] == 2
    comment_on_new_run = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "comment-1"},
        json={"run_id": retried.json()["id"], "body": "Portée nouvelle tentative"},
    )
    assert comment_on_new_run.status_code == 201
    assert comment_on_new_run.json()["id"] != comment.json()["id"]
    assert comment_on_new_run.json()["run_id"] == retried.json()["id"]
    owner_scoped_comment = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "principal-scoped-comment"},
        json={"run_id": retried.json()["id"], "body": "Avis propriétaire"},
    )
    assert owner_scoped_comment.status_code == 201
    delayed_stop = client.post(
        f"/missions/{mission_id}/stop", headers=stop_headers
    )
    assert delayed_stop.status_code == 200
    assert delayed_stop.json()["run"]["id"] == stopped.json()["run"]["id"]
    assert delayed_stop.json()["already_stopped"] is True
    assert client.get(f"/missions/{mission_id}").json()["current_run"]["id"] == retried.json()["id"]
    assert client.post(
        f"/missions/{mission_id}/retry",
        headers={"Idempotency-Key": "retry-concurrent"},
        json={"reason": "Ne doit pas créer une troisième tentative"},
    ).status_code == 409
    assert len(client.get(f"/missions/{mission_id}/runs").json()) == 2

    with mission_context["session_factory"]() as db:
        second_member = UserModel(
            login_normalized=f"member-{uuid4().hex}",
            display_name="Second mission member",
            password_hash=hash_password("correct horse battery staple"),
            platform_role="member",
            password_changed_at=utcnow(),
        )
        db.add(second_member)
        db.flush()
        db.add(
            MembershipModel(
                user_id=second_member.id,
                scope_type="project",
                scope_id=mission_context["project_id"],
                role="member",
            )
        )
        _, second_session_token, second_csrf_token = create_user_session(
            db, second_member.id
        )
        db.commit()
    client.cookies.clear()
    client.cookies.set("acp_session", second_session_token)
    client.headers["X-CSRF-Token"] = second_csrf_token
    member_scoped_comment = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "principal-scoped-comment"},
        json={"run_id": retried.json()["id"], "body": "Avis membre"},
    )
    member_comment_replay = client.post(
        f"/missions/{mission_id}/comments",
        headers={"Idempotency-Key": "principal-scoped-comment"},
        json={"run_id": retried.json()["id"], "body": "Avis membre"},
    )
    assert (
        member_scoped_comment.status_code
        == member_comment_replay.status_code
        == 201
    )
    assert member_comment_replay.json()["id"] == member_scoped_comment.json()["id"]
    assert member_scoped_comment.json()["id"] != owner_scoped_comment.json()["id"]
    same_stop_key_other_principal = client.post(
        f"/missions/{mission_id}/stop", headers=stop_headers
    )
    assert same_stop_key_other_principal.status_code == 200
    assert same_stop_key_other_principal.json()["run"]["id"] == retried.json()["id"]
    inaccessible_assignment = _mission_payload(mission_context)
    inaccessible_assignment["agent_instance_id"] = sibling_agent.json()["id"]
    assert client.post(
        "/missions",
        headers={"Idempotency-Key": "inaccessible-agent"},
        json=inaccessible_assignment,
    ).status_code == 422
    same_key_other_principal = client.post(
        "/missions",
        headers={"Idempotency-Key": create_key},
        json=_mission_payload(mission_context),
    )
    assert same_key_other_principal.status_code == 201
    assert same_key_other_principal.json()["id"] != mission_id


def test_idempotency_keys_reject_spaces_controls_and_non_ascii(mission_context):
    client = mission_context["client"]
    payload = _mission_payload(mission_context, "Mission clé invalide")
    for invalid_key in (b"contains space", b"control\x7f", b"non-ascii-\xe9"):
        response = client.post(
            "/missions",
            headers=[(b"Idempotency-Key", invalid_key)],
            json=payload,
        )
        assert response.status_code == 400, response.text


@pytest.mark.sqlite
def test_sqlite_upgrade_replaces_legacy_command_scope_and_refuses_ambiguity(tmp_path):
    def legacy_engine(name):
        engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}")
        with engine.begin() as connection:
            for statement in (
                "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)",
                "CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, "
                "created_by_user_id VARCHAR(36))",
                "CREATE TABLE task_runs (id VARCHAR(36) PRIMARY KEY, "
                "task_id VARCHAR(36) NOT NULL, created_at DATETIME NOT NULL)",
                "CREATE TABLE mission_commands ("
                "task_id VARCHAR(36) NOT NULL, command VARCHAR(50) NOT NULL, "
                "idempotency_key VARCHAR(200) NOT NULL, task_run_id VARCHAR(36), "
                "id VARCHAR(36) PRIMARY KEY, created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_mission_command_key UNIQUE "
                "(task_id, command, idempotency_key))",
                "CREATE TABLE mission_comments ("
                "task_id VARCHAR(36) NOT NULL, task_run_id VARCHAR(36), "
                "author_user_id VARCHAR(36) NOT NULL, body TEXT NOT NULL, "
                "idempotency_key VARCHAR(200), id VARCHAR(36) PRIMARY KEY, "
                "created_at DATETIME NOT NULL, "
                "CONSTRAINT uq_mission_comment_key UNIQUE "
                "(task_id, idempotency_key))",
            ):
                connection.execute(text(statement))
        return engine

    engine = legacy_engine("legacy-safe.db")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES ('user-1')"))
        connection.execute(
            text(
                "INSERT INTO tasks (id, created_by_user_id) "
                "VALUES ('task-1', 'user-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO task_runs (id, task_id, created_at) "
                "VALUES ('run-1', 'task-1', '2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mission_commands "
                "(task_id, command, idempotency_key, task_run_id, id, created_at) "
                "VALUES ('task-1', 'stop', 'shared-key', 'run-1', 'command-1', "
                "'2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mission_comments "
                "(task_id, task_run_id, author_user_id, body, idempotency_key, "
                "id, created_at) VALUES "
                "('task-1', 'run-1', 'user-1', 'Commentaire historique', "
                "'legacy-comment', 'comment-1', '2026-01-01 00:00:00')"
            )
        )
    _upgrade_sqlite_schema(engine)
    constraints = inspect(engine).get_unique_constraints("mission_commands")
    assert ("task_id", "command", "idempotency_key") not in {
        tuple(constraint.get("column_names") or ()) for constraint in constraints
    }
    assert any(
        index["name"] == "uq_mission_command_principal_key" and index["unique"]
        for index in inspect(engine).get_indexes("mission_commands")
    )
    comment_constraints = inspect(engine).get_unique_constraints("mission_comments")
    assert ("task_id", "idempotency_key") not in {
        tuple(constraint.get("column_names") or ())
        for constraint in comment_constraints
    }
    assert (
        "author_user_id",
        "task_run_id",
        "idempotency_key",
    ) in {
        tuple(constraint.get("column_names") or ())
        for constraint in comment_constraints
    }
    with engine.begin() as connection:
        assert connection.execute(
            text(
                "SELECT principal_id FROM mission_commands WHERE id = 'command-1'"
            )
        ).scalar_one() == "user-1"
        connection.execute(text("INSERT INTO users (id) VALUES ('user-2')"))
        connection.execute(
            text(
                "INSERT INTO mission_commands "
                "(task_id, command, idempotency_key, principal_id, "
                "request_fingerprint, task_run_id, id, created_at) VALUES "
                "('task-1', 'stop', 'shared-key', 'user-2', '', 'run-1', "
                "'command-2', '2026-01-01 00:00:00')"
            )
        )
        comment_fingerprint = connection.execute(
            text(
                "SELECT request_fingerprint FROM mission_comments "
                "WHERE id = 'comment-1'"
            )
        ).scalar_one()
        assert len(comment_fingerprint) == 64
        connection.execute(
            text(
                "INSERT INTO mission_comments "
                "(task_id, task_run_id, author_user_id, body, idempotency_key, "
                "request_fingerprint, id, created_at) VALUES "
                "('task-1', 'run-1', 'user-2', 'Commentaire historique', "
                "'legacy-comment', :fingerprint, 'comment-2', "
                "'2026-01-01 00:00:00')"
            ),
            {
                "fingerprint": comment_fingerprint,
            },
        )
    _upgrade_sqlite_schema(engine)
    engine.dispose()

    ambiguous_engine = legacy_engine("legacy-ambiguous.db")
    with ambiguous_engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES ('user-1')"))
        for suffix in ("1", "2"):
            connection.execute(
                text(
                    "INSERT INTO tasks (id, created_by_user_id) "
                    "VALUES (:task_id, 'user-1')"
                ),
                {"task_id": f"task-{suffix}"},
            )
            connection.execute(
                text(
                    "INSERT INTO mission_commands "
                    "(task_id, command, idempotency_key, id, created_at) "
                    "VALUES (:task_id, 'create', 'duplicate', :command_id, "
                    "'2026-01-01 00:00:00')"
                ),
                {"task_id": f"task-{suffix}", "command_id": f"command-{suffix}"},
            )
    with pytest.raises(RuntimeError, match="ambigu"):
        _upgrade_sqlite_schema(ambiguous_engine)
    ambiguous_engine.dispose()

    unscoped_comment_engine = legacy_engine("legacy-comment-without-run.db")
    with unscoped_comment_engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id) VALUES ('user-1')"))
        connection.execute(
            text(
                "INSERT INTO tasks (id, created_by_user_id) "
                "VALUES ('task-1', 'user-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mission_comments "
                "(task_id, author_user_id, body, idempotency_key, id, created_at) "
                "VALUES ('task-1', 'user-1', 'Portée inconnue', 'keyed', "
                "'comment-ambiguous', '2026-01-01 00:00:00')"
            )
        )
    with pytest.raises(RuntimeError, match="mission_comments.*portée fiable"):
        _upgrade_sqlite_schema(unscoped_comment_engine)
    unscoped_comment_engine.dispose()


def test_concurrent_comments_replay_or_reject_by_payload(mission_context):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Commentaires concurrents")
    mission_id = mission["id"]
    run_id = mission["current_run"]["id"]
    path = f"/missions/{mission_id}/comments"
    payload = {"run_id": run_id, "body": "Même diagnostic"}

    def post_comment(key, candidate):
        return client.post(
            path,
            headers={"Idempotency-Key": key},
            json=candidate,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        same_payload = list(
            executor.map(
                lambda _: post_comment("concurrent-comment-replay", payload),
                range(2),
            )
        )
    assert {response.status_code for response in same_payload} == {201}
    assert len({response.json()["id"] for response in same_payload}) == 1

    conflicting_payloads = [
        {"run_id": run_id, "body": "Diagnostic A"},
        {"run_id": run_id, "body": "Diagnostic B"},
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        conflicting = list(
            executor.map(
                lambda candidate: post_comment(
                    "concurrent-comment-conflict", candidate
                ),
                conflicting_payloads,
            )
        )
    assert sorted(response.status_code for response in conflicting) == [201, 409]
    comments = client.get(path).json()
    assert len([row for row in comments if row["body"] == "Même diagnostic"]) == 1
    assert len([row for row in comments if row["body"].startswith("Diagnostic ")]) == 1


def test_concurrent_create_and_stop_with_same_keys_have_one_effect(mission_context):
    client = mission_context["client"]
    payload = _mission_payload(mission_context, "Mission concurrente")

    def create_once():
        return client.post(
            "/missions",
            headers={"Idempotency-Key": "concurrent-create"},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        create_responses = list(executor.map(lambda _: create_once(), range(2)))
    assert {response.status_code for response in create_responses} == {201}
    mission_ids = {response.json()["id"] for response in create_responses}
    assert len(mission_ids) == 1
    mission_id = mission_ids.pop()

    conflicting_payload = {
        **payload,
        "objective": "Payload concurrent différent",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        conflicting_responses = list(
            executor.map(
                lambda candidate: client.post(
                    "/missions",
                    headers={"Idempotency-Key": "concurrent-conflict"},
                    json=candidate,
                ),
                (payload, conflicting_payload),
            )
        )
    assert sorted(
        response.status_code for response in conflicting_responses
    ) == [201, 409]

    def stop_once():
        return client.post(
            f"/missions/{mission_id}/stop",
            headers={"Idempotency-Key": "concurrent-stop"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        stop_responses = list(executor.map(lambda _: stop_once(), range(2)))
    assert {response.status_code for response in stop_responses} == {200}
    assert {
        response.json()["run"]["id"] for response in stop_responses
    } == {create_responses[0].json()["current_run"]["id"]}

    def retry_once():
        return client.post(
            f"/missions/{mission_id}/retry",
            headers={"Idempotency-Key": "concurrent-retry"},
            json={"reason": "Relance concurrente identique"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        retry_responses = list(executor.map(lambda _: retry_once(), range(2)))
    assert {response.status_code for response in retry_responses} == {201}
    assert len({response.json()["id"] for response in retry_responses}) == 1
    assert len(client.get(f"/missions/{mission_id}/runs").json()) == 2
    with mission_context["session_factory"]() as db:
        assert (
            db.query(MissionCommandModel)
            .filter_by(command="create", idempotency_key="concurrent-create")
            .count()
            == 1
        )
        assert (
            db.query(MissionCommandModel)
            .filter_by(command="stop", idempotency_key="concurrent-stop")
            .count()
            == 1
        )
        assert (
            db.query(MissionCommandModel)
            .filter_by(command="retry", idempotency_key="concurrent-retry")
            .count()
            == 1
        )


def test_stale_worker_compare_and_set_cannot_overwrite_stopping(mission_context):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Mission course d'arrêt")
    claim = _claim(mission_context)
    run_id = claim["attempt_id"]
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=_worker_headers(
            mission_context, fencing_token=claim["fencing_token"]
        ),
        json={"status": "running"},
    ).status_code == 200

    with mission_context["session_factory"]() as observer:
        observed_status = observer.get(TaskRunModel, run_id).status
    assert observed_status == "running"
    with mission_context["session_factory"]() as stopper:
        assert (
            stopper.query(TaskRunModel)
            .filter_by(id=run_id, status="running")
            .update({TaskRunModel.status: "stopping"}, synchronize_session=False)
            == 1
        )
        stopper.commit()
    with mission_context["session_factory"]() as stale_worker:
        assert not _compare_and_set_run_status(
            stale_worker,
            run_id=run_id,
            expected_status=observed_status,
            target_status="failed",
        )
        stale_worker.rollback()
        assert stale_worker.get(TaskRunModel, run_id).status == "stopping"


def test_worker_fencing_evidence_and_user_acceptance_are_separate(mission_context):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Mission validation")
    claim = _claim(mission_context)
    assert claim["attempt_id"] == mission["current_run"]["id"]
    assert claim["attempt_number"] == claim["fencing_token"] == 1
    assert claim["task_run"]["status"] == "preparing"
    assert claim["mission"]["acceptance_criteria"] == [
        "les tests passent",
        "la preuve est consultable",
    ]
    assert claim["mission"]["duration_seconds"] == 3600
    run_id = claim["attempt_id"]
    worker_id = mission_context["worker"]["worker_id"]
    auth_only = {
        "Authorization": f"Bearer {mission_context['worker']['token']}"
    }

    renew_path = f"/workers/{worker_id}/leases/{run_id}/renew"
    assert client.post(renew_path, headers=auth_only).status_code == 409
    assert client.post(
        renew_path,
        headers={**auth_only, "X-Attempt-Fencing-Token": "999"},
    ).status_code == 409
    renewal = client.post(
        renew_path,
        headers={**auth_only, "X-Attempt-Fencing-Token": "1"},
    )
    assert renewal.status_code == 200
    assert renewal.json()["status"] == "preparing"
    assert renewal.json()["stop_requested"] is False

    assert client.patch(
        f"/task-runs/{run_id}",
        headers=_worker_headers(mission_context),
        json={"status": "running"},
    ).status_code == 409
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=_worker_headers(mission_context, fencing_token=999),
        json={"status": "running"},
    ).status_code == 409
    running_headers = _worker_headers(mission_context, fencing_token=1)
    assert client.patch(
        f"/task-runs/{run_id}", headers=running_headers, json={"status": "running"}
    ).status_code == 200

    event = {
        "type": "task.progress",
        "project_id": mission_context["project_id"],
        "task_id": mission["id"],
        "task_run_id": run_id,
        "payload": {"step": "tests"},
    }
    assert client.post(
        "/events", headers=_worker_headers(mission_context), json=event
    ).status_code == 409
    assert client.post("/events", headers=running_headers, json=event).status_code == 200

    assert client.patch(
        f"/task-runs/{run_id}",
        headers=running_headers,
        json={
            "status": "succeeded",
            "technical_validation": {"status": "passed", "summary": "tests OK"},
        },
    ).status_code == 422
    evidence = {
        "kind": "test_run",
        "summary": "Suite API verte",
        "command": "pytest -q",
        "exit_code": 0,
        "data": {"passed": 12},
    }
    for _ in range(2):
        assert client.patch(
            f"/task-runs/{run_id}",
            headers=running_headers,
            json={
                "technical_validation": {"status": "passed", "summary": "tests OK"},
                "evidence": [evidence],
            },
        ).status_code == 200
    detail = client.get(f"/missions/{mission['id']}").json()
    assert len(detail["current_run"]["evidence"]) == 1
    succeeded = client.patch(
        f"/task-runs/{run_id}",
        headers=running_headers,
        json={"status": "succeeded"},
    )
    assert succeeded.status_code == 200

    detail = client.get(f"/missions/{mission['id']}").json()
    assert detail["status"] == "succeeded"
    assert detail["current_run"]["technical_validation"]["status"] == "passed"
    assert detail["current_run"]["user_acceptance"]["status"] == "pending"
    with mission_context["session_factory"]() as db:
        assert db.get(TaskModel, mission["id"]).status == "review"
    assert client.post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "premature-retry"},
        json={"reason": "Pas avant décision"},
    ).status_code == 409

    acceptance_path = f"/missions/{mission['id']}/runs/{run_id}/acceptance"
    def decide(decision):
        return client.post(
            acceptance_path,
            json={"decision": decision, "comment": f"Décision {decision}"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(decide, ("accepted", "rejected")))
    assert sorted(response.status_code for response in decisions) == [200, 409]
    winner = next(response for response in decisions if response.status_code == 200)
    winning_decision = winner.json()["user_acceptance"]["status"]
    assert winning_decision in {"accepted", "rejected"}
    assert (
        client.get(f"/missions/{mission['id']}")
        .json()["current_run"]["user_acceptance"]["status"]
        == winning_decision
    )
    assert client.post(
        acceptance_path,
        json={"decision": winning_decision, "comment": "replay"},
    ).status_code == 200
    opposite = "rejected" if winning_decision == "accepted" else "accepted"
    assert client.post(
        acceptance_path, json={"decision": opposite, "comment": "contradiction"}
    ).status_code == 409


def test_simulation_worker_cannot_claim_a_real_mission(mission_context):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Mission réelle")
    simulated = client.post(
        "/workers/register",
        headers={
            "X-Worker-Registration-Token": mission_context["registration_token"]
        },
        json={
            "name": f"simulated-{uuid4().hex}",
            "capabilities": ["git"],
            "simulation": True,
            "project_id": mission_context["project_id"],
        },
    )
    assert simulated.status_code == 201
    simulated_worker = simulated.json()
    self_promotion = client.post(
        f"/workers/{simulated_worker['worker_id']}/heartbeat",
        headers={"Authorization": f"Bearer {simulated_worker['token']}"},
        json={"simulation": False},
    )
    assert self_promotion.status_code == 409
    refused = client.post(
        f"/workers/{simulated_worker['worker_id']}/claim",
        headers={"Authorization": f"Bearer {simulated_worker['token']}"},
        json={},
    )
    assert refused.status_code == 200
    assert refused.json()["task"] is None
    assert refused.json()["reason"] == (
        "worker de simulation interdit pour une mission réelle"
    )
    assert client.get(f"/missions/{mission['id']}").json()["status"] == "queued"

    claimed = _claim(mission_context)
    assert claimed["task"]["id"] == mission["id"]


def test_get_mission_by_run_is_scoped_and_rejects_non_mission(mission_context):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Mission deep-link")
    run_id = mission["current_run"]["id"]
    direct = client.get(f"/missions/by-run/{run_id}")
    assert direct.status_code == 200
    assert direct.json()["id"] == mission["id"]
    assert client.get(f"/missions/by-run/{uuid4()}").status_code == 404

    with mission_context["session_factory"]() as db:
        legacy = TaskModel(
            project_id=mission_context["project_id"],
            title="Legacy task",
        )
        db.add(legacy)
        db.flush()
        legacy_run = TaskRunModel(task_id=legacy.id, status="queued")
        db.add(legacy_run)
        db.commit()
        legacy_run_id = legacy_run.id
    assert client.get(f"/missions/by-run/{legacy_run_id}").status_code == 404

    other_project = client.post(
        "/projects",
        json={
            "workspace_id": mission_context["workspace_id"],
            "name": "Autre projet",
        },
    )
    assert other_project.status_code == 200
    with mission_context["session_factory"]() as db:
        viewer = UserModel(
            login_normalized=f"viewer-{uuid4().hex}",
            display_name="Inter-project viewer",
            password_hash=hash_password("correct horse battery staple"),
            platform_role="viewer",
            password_changed_at=utcnow(),
        )
        db.add(viewer)
        db.flush()
        db.add(
            MembershipModel(
                user_id=viewer.id,
                scope_type="project",
                scope_id=other_project.json()["id"],
                role="viewer",
            )
        )
        _, session_token, csrf_token = create_user_session(db, viewer.id)
        db.commit()
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token
    assert client.get(f"/missions/by-run/{run_id}").status_code == 403


def test_running_stop_is_observable_and_approval_action_change_invalidates(
    mission_context,
):
    client = mission_context["client"]
    mission = _create_mission(mission_context, "Mission arrêt")
    claim = _claim(mission_context)
    run_id = claim["attempt_id"]
    fencing = claim["fencing_token"]
    worker_id = mission_context["worker"]["worker_id"]
    worker_headers = _worker_headers(mission_context, fencing_token=fencing)
    assert client.patch(
        f"/task-runs/{run_id}", headers=worker_headers, json={"status": "running"}
    ).status_code == 200

    approval_body = {
        "project_id": mission_context["project_id"],
        "task_run_id": run_id,
        "action": "git_publish",
        "target": "origin/feature",
        "consequences": ["rend la branche visible"],
        "scope": {"repository": "workspace"},
        "footprint": {"refs": ["refs/heads/feature"]},
        "reason": "Publication demandée",
    }
    approval = client.post("/approvals", json=approval_body)
    assert approval.status_code == 201, approval.text
    approval_id = approval.json()["id"]
    assert len(approval.json()["action_fingerprint"]) == 64
    assert client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "APPROVED", "comment": "Périmètre vérifié"},
    ).status_code == 200
    execution = {
        key: approval_body[key]
        for key in ("action", "target", "consequences", "scope", "footprint")
    }
    execution.update({"task_run_id": run_id, "fencing_token": fencing})
    assert client.post(
        f"/approvals/{approval_id}/validate",
        headers=_worker_headers(mission_context),
        json=execution,
    ).status_code == 200
    changed = {**execution, "target": "origin/main"}
    invalidated = client.post(
        f"/approvals/{approval_id}/validate",
        headers=_worker_headers(mission_context),
        json=changed,
    )
    assert invalidated.status_code == 409
    rows = client.get(
        "/approvals", params={"project_id": mission_context["project_id"]}
    ).json()
    assert next(row for row in rows if row["id"] == approval_id)["status"] == "INVALIDATED"

    expired_body = {**approval_body, "target": "origin/expired"}
    expired = client.post("/approvals", json=expired_body)
    assert expired.status_code == 201, expired.text
    expired_id = expired.json()["id"]
    assert client.post(
        f"/approvals/{expired_id}/decision",
        json={"decision": "APPROVED", "comment": "Courte validité"},
    ).status_code == 200
    with mission_context["session_factory"]() as db:
        db.query(ApprovalModel).filter_by(id=expired_id).update(
            {ApprovalModel.expires_at: utcnow() - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()
    expired_execution = {
        key: expired_body[key]
        for key in ("action", "target", "consequences", "scope", "footprint")
    }
    expired_execution.update({"task_run_id": run_id, "fencing_token": fencing})
    assert client.post(
        f"/approvals/{expired_id}/validate",
        headers=_worker_headers(mission_context),
        json=expired_execution,
    ).status_code == 409
    rows = client.get(
        "/approvals", params={"project_id": mission_context["project_id"]}
    ).json()
    assert next(row for row in rows if row["id"] == expired_id)["status"] == "EXPIRED"

    stop_guard_body = {**approval_body, "target": "origin/stop-guard"}
    stop_guard = client.post("/approvals", json=stop_guard_body)
    assert stop_guard.status_code == 201, stop_guard.text
    stop_guard_id = stop_guard.json()["id"]
    assert client.post(
        f"/approvals/{stop_guard_id}/decision",
        json={"decision": "APPROVED", "comment": "Valide avant arrêt"},
    ).status_code == 200
    stop_guard_execution = {
        key: stop_guard_body[key]
        for key in ("action", "target", "consequences", "scope", "footprint")
    }
    stop_guard_execution.update({"task_run_id": run_id, "fencing_token": fencing})

    stop_headers = {"Idempotency-Key": "stop-running-attempt"}
    stopped = client.post(
        f"/missions/{mission['id']}/stop", headers=stop_headers
    )
    assert stopped.status_code == 200
    assert stopped.json()["run"]["status"] == "stopping"
    assert client.post(
        f"/approvals/{stop_guard_id}/decision",
        json={"decision": "REJECTED", "comment": "Décision trop tardive"},
    ).status_code == 409
    assert client.post(
        f"/approvals/{stop_guard_id}/validate",
        headers=_worker_headers(mission_context),
        json=stop_guard_execution,
    ).status_code == 409
    rows = client.get(
        "/approvals", params={"project_id": mission_context["project_id"]}
    ).json()
    assert next(row for row in rows if row["id"] == stop_guard_id)["status"] == "INVALIDATED"
    assert client.post("/approvals", json=approval_body).status_code == 409
    assert client.post(
        f"/missions/{mission['id']}/stop", headers=stop_headers
    ).json()["already_stopped"] is True
    assert client.post(
        "/approvals",
        json={**approval_body, "target": "origin/late"},
    ).status_code == 409
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=worker_headers,
        json={"status": "failed"},
    ).status_code == 409
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=worker_headers,
        json={"append_logs": [{"level": "info", "message": "trop tard"}]},
    ).status_code == 409
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=worker_headers,
        json={
            "status": "succeeded",
            "technical_validation": {"status": "passed", "summary": "trop tard"},
            "evidence": [{"kind": "test", "summary": "preuve tardive"}],
        },
    ).status_code == 409
    renewal = client.post(
        f"/workers/{worker_id}/leases/{run_id}/renew",
        headers={
            "Authorization": f"Bearer {mission_context['worker']['token']}",
            "X-Attempt-Fencing-Token": str(fencing),
        },
    )
    assert renewal.status_code == 200
    assert renewal.json()["stop_requested"] is True
    assert renewal.json()["status"] == "stopping"
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=worker_headers,
        json={"status": "cancelled", "append_logs": [{"message": "arrêt confirmé"}]},
    ).status_code == 200

    retried = client.post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "after-stop"},
        json={"reason": "Reprise explicite après arrêt"},
    )
    assert retried.status_code == 201
    assert retried.json()["attempt_number"] == 2
    assert retried.json()["id"] != run_id


def test_project_policy_limits_new_missions_and_retries(mission_context):
    client = mission_context["client"]
    policy = client.put(
        f"/projects/{mission_context['project_id']}/budget-policy",
        json={"max_concurrent_missions": 1, "max_retries_per_mission": 0},
    )
    assert policy.status_code == 200, policy.text

    mission = _create_mission(mission_context, "Mission bornée")
    refused = client.post(
        "/missions",
        headers={"Idempotency-Key": "capacity-refused"},
        json=_mission_payload(mission_context, "Mission concurrente"),
    )
    assert refused.status_code == 409
    assert "concurrentes" in refused.json()["detail"]

    with mission_context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        run = db.get(TaskRunModel, mission["current_run"]["id"])
        assert task is not None and run is not None
        run.status = "failed"
        task.status = "failed"
        task.active_run_id = None
        db.commit()

    retry = client.post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "retry-over-project-policy"},
        json={"reason": "Ne doit pas dépasser la borne"},
    )
    assert retry.status_code == 409
    assert "relances" in retry.json()["detail"]
    with mission_context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        assert task is not None
        assert task.attempt_counter == 1
        assert db.query(TaskRunModel).filter_by(task_id=mission["id"]).count() == 1


def test_concurrent_retries_share_the_project_capacity_atomically(mission_context):
    client = mission_context["client"]
    first = _create_mission(mission_context, "Relance concurrente A")
    second = _create_mission(mission_context, "Relance concurrente B")
    with mission_context["session_factory"]() as db:
        for mission in (first, second):
            task = db.get(TaskModel, mission["id"])
            run = db.get(TaskRunModel, mission["current_run"]["id"])
            assert task is not None and run is not None
            run.status = "failed"
            task.status = "failed"
            task.active_run_id = None
        db.commit()

    policy = client.put(
        f"/projects/{mission_context['project_id']}/budget-policy",
        json={"max_concurrent_missions": 1, "max_retries_per_mission": 3},
    )
    assert policy.status_code == 200, policy.text

    start = Barrier(2)

    def retry(mission: dict, suffix: str):
        start.wait(timeout=10)
        return client.post(
            f"/missions/{mission['id']}/retry",
            headers={"Idempotency-Key": f"capacity-retry-{suffix}"},
            json={"reason": "Course réelle sur la capacité projet"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda item: retry(*item),
                ((first, "a"), (second, "b")),
            )
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    refusal = next(response for response in responses if response.status_code == 409)
    assert "concurrentes" in refusal.json()["detail"]
    with mission_context["session_factory"]() as db:
        active = (
            db.query(TaskRunModel)
            .join(TaskModel, TaskModel.id == TaskRunModel.task_id)
            .filter(
                TaskModel.project_id == mission_context["project_id"],
                TaskModel.is_mission == 1,
                TaskRunModel.status == "queued",
            )
            .count()
        )
        assert active == 1
        tasks = db.query(TaskModel).filter(
            TaskModel.id.in_([first["id"], second["id"]])
        ).all()
        assert sorted(task.attempt_counter for task in tasks) == [1, 2]


def test_retry_reloads_counter_and_latest_status_after_waiting_for_policy_lock(
    mission_context,
    monkeypatch,
):
    context = mission_context
    mission = _create_mission(context, "Relance devenue obsolète")
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        first = db.get(TaskRunModel, mission["current_run"]["id"])
        assert task is not None and first is not None
        first.status = "failed"
        task.status = "failed"
        task.active_run_id = None
        db.commit()

    policy = context["client"].put(
        f"/projects/{context['project_id']}/budget-policy",
        json={"max_concurrent_missions": 3, "max_retries_per_mission": 1},
    )
    assert policy.status_code == 200, policy.text

    real_begin = missions_router.begin_budget_write
    injected = False

    def completed_retry_before_lock(db):
        nonlocal injected
        db.rollback()
        if not injected:
            injected = True
            with context["session_factory"]() as concurrent:
                task = concurrent.get(TaskModel, mission["id"])
                assert task is not None
                task.attempt_counter = 2
                concurrent.add(
                    TaskRunModel(
                        task_id=task.id,
                        status="failed",
                        attempt_number=2,
                        fencing_token=2,
                        technical_validation={"status": "failed"},
                        user_acceptance={"status": "pending"},
                    )
                )
                concurrent.commit()
        real_begin(db)

    monkeypatch.setattr(
        missions_router,
        "begin_budget_write",
        completed_retry_before_lock,
    )
    refused = context["client"].post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "stale-counter-after-wait"},
        json={"reason": "Ne doit pas créer une troisième tentative"},
    )
    assert refused.status_code == 409, refused.text
    assert "relances" in refused.json()["detail"]
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        assert task is not None and task.attempt_counter == 2
        assert db.query(TaskRunModel).filter_by(task_id=task.id).count() == 2


def test_retry_reloads_an_active_winning_attempt_after_waiting_for_policy_lock(
    mission_context,
    monkeypatch,
):
    context = mission_context
    mission = _create_mission(context, "Relance gagnante devenue active")
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        first = db.get(TaskRunModel, mission["current_run"]["id"])
        assert task is not None and first is not None
        first.status = "failed"
        task.status = "failed"
        task.active_run_id = None
        db.commit()

    real_begin = missions_router.begin_budget_write
    injected = False

    def active_retry_before_lock(db):
        nonlocal injected
        db.rollback()
        if not injected:
            injected = True
            with context["session_factory"]() as concurrent:
                task = concurrent.get(TaskModel, mission["id"])
                assert task is not None
                winning = TaskRunModel(
                    task_id=task.id,
                    status="queued",
                    attempt_number=2,
                    fencing_token=2,
                    technical_validation={"status": "pending"},
                    user_acceptance={"status": "pending"},
                )
                concurrent.add(winning)
                concurrent.flush()
                task.attempt_counter = 2
                task.active_run_id = winning.id
                task.status = "queued"
                concurrent.commit()
        real_begin(db)

    monkeypatch.setattr(missions_router, "begin_budget_write", active_retry_before_lock)
    refused = context["client"].post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "active-after-policy-wait"},
        json={"reason": "Ne doit pas ignorer la tentative gagnante"},
    )
    assert refused.status_code == 409, refused.text
    assert "active" in refused.json()["detail"]
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        assert task is not None and task.attempt_counter == 2
        assert db.query(TaskRunModel).filter_by(task_id=task.id).count() == 2


def test_retry_reloads_latest_run_after_the_serialization_lock(
    mission_context,
    monkeypatch,
):
    context = mission_context
    mission = _create_mission(context, "Relance et snapshot PostgreSQL")
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        first = db.get(TaskRunModel, mission["current_run"]["id"])
        assert task is not None and first is not None
        first.status = "failed"
        task.status = "failed"
        task.active_run_id = None
        db.commit()

    policy = context["client"].put(
        f"/projects/{context['project_id']}/budget-policy",
        json={"max_concurrent_missions": 3, "max_retries_per_mission": 3},
    )
    assert policy.status_code == 200, policy.text

    real_lock_policy = budget_service._lock_policy
    injected = False

    def insert_completed_run_before_policy_lock(db, project_id):
        nonlocal injected
        if not injected:
            injected = True
            task = db.get(TaskModel, mission["id"])
            assert task is not None
            task.attempt_counter = 2
            task.status = "succeeded"
            task.active_run_id = None
            db.add(
                TaskRunModel(
                    task_id=task.id,
                    status="succeeded",
                    attempt_number=2,
                    fencing_token=2,
                    technical_validation={"status": "passed"},
                    user_acceptance={"status": "pending"},
                )
            )
            db.flush()
        return real_lock_policy(db, project_id)

    monkeypatch.setattr(
        budget_service,
        "_lock_policy",
        insert_completed_run_before_policy_lock,
    )
    refused = context["client"].post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "snapshot-refreshed-after-run-lock"},
        json={"reason": "Ne doit pas ignorer la réussite la plus récente"},
    )
    assert refused.status_code == 409, refused.text
    assert "réussite" in refused.json()["detail"]


def test_retry_counter_cas_refuses_a_changed_observation(
    mission_context,
    monkeypatch,
):
    context = mission_context
    mission = _create_mission(context, "CAS du compteur de relance")
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        run = db.get(TaskRunModel, mission["current_run"]["id"])
        assert task is not None and run is not None
        run.status = "failed"
        task.status = "failed"
        task.active_run_id = None
        db.commit()

    real_enforce = missions_router.enforce_mission_retry_limit

    def drift_counter_after_check(db, task, policy):
        real_enforce(db, task, policy)
        db.query(TaskModel).filter(TaskModel.id == task.id).update(
            {TaskModel.attempt_counter: TaskModel.attempt_counter + 1},
            synchronize_session=False,
        )

    monkeypatch.setattr(
        missions_router,
        "enforce_mission_retry_limit",
        drift_counter_after_check,
    )
    refused = context["client"].post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "counter-cas-drift"},
        json={"reason": "La valeur observée ne doit plus être vraie"},
    )
    assert refused.status_code == 409, refused.text
    assert "concurrente" in refused.json()["detail"]
    with context["session_factory"]() as db:
        task = db.get(TaskModel, mission["id"])
        assert task is not None and task.attempt_counter == 1
        assert db.query(TaskRunModel).filter_by(task_id=task.id).count() == 1


def test_retry_revalidates_access_in_each_transaction_after_rollback(
    mission_context,
    monkeypatch,
):
    context = mission_context
    mission = _create_mission(context, "Relance et révocation concurrentes")
    real_ensure_access = missions_router.ensure_access
    checks = 0

    def access_disappears_after_locked_decision(*args, **kwargs):
        nonlocal checks
        checks += 1
        if checks >= 4:
            raise missions_router.HTTPException(
                status_code=403,
                detail="Accès révoqué pendant la relance",
            )
        return real_ensure_access(*args, **kwargs)

    monkeypatch.setattr(
        missions_router,
        "ensure_access",
        access_disappears_after_locked_decision,
    )
    refused = context["client"].post(
        f"/missions/{mission['id']}/retry",
        headers={"Idempotency-Key": "revoked-after-retry-rollback"},
        json={"reason": "La tentative active force rollback puis replay"},
    )
    assert refused.status_code == 403, refused.text
    assert checks == 4


def test_mission_routes_require_session_and_current_csrf(mission_context):
    client = mission_context["client"]
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/missions", json=_mission_payload(mission_context)).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.cookies.clear()
    assert client.get("/missions").status_code == 401
    assert client.post("/missions", json=_mission_payload(mission_context)).status_code == 401
