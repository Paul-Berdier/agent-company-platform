"""Tests du protocole d'enregistrement et d'attribution des workers."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from acp_api.main import app
from acp_api.security import create_user_session
from acp_database import get_session_factory
from acp_database.models import TaskModel, UserModel, WorkerLeaseModel, WorkerModel


REGISTRATION_TOKEN = "test-registration-secret"


@pytest.fixture(autouse=True)
def _isolate_registration_scope(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ACP_WORKER_REGISTRATION_PROJECT_ID", raising=False)
    monkeypatch.delenv("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", raising=False)


def _authorize_registration(
    *, project_id: str | None = None, global_access: bool = True
) -> None:
    if project_id is None:
        os.environ.pop("ACP_WORKER_REGISTRATION_PROJECT_ID", None)
    else:
        os.environ["ACP_WORKER_REGISTRATION_PROJECT_ID"] = project_id
    os.environ["ACP_WORKER_REGISTRATION_GLOBAL_ACCESS"] = (
        "1" if global_access else "0"
    )


def _authenticate_owner(client: TestClient) -> None:
    """Les opérations humaines passent par une session; les appels worker gardent leur Bearer."""

    with get_session_factory()() as db:
        user = UserModel(
            login_normalized=f"worker-test-owner-{uuid4().hex}",
            display_name="Worker test owner",
            password_hash="not-used-by-this-test",
            platform_role="owner",
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _register(
    client: TestClient,
    name: str,
    capabilities: list[str],
    *,
    project_id: str | None = None,
    global_access: bool = True,
):
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    _authorize_registration(project_id=project_id, global_access=global_access)
    return client.post(
        "/workers/register",
        headers={"X-Worker-Registration-Token": REGISTRATION_TOKEN},
        json={
            "name": name,
            "capabilities": capabilities,
            "max_concurrency": 1,
            "simulation": True,
            "project_id": project_id,
            "global_access": global_access,
            "metadata": {"test": True},
        },
    )


def _project_with_agent(client: TestClient) -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    organization = client.post("/organizations", json={"name": f"Org-{suffix}"}).json()
    workspace = client.post(
        "/workspaces",
        json={"organization_id": organization["id"], "name": f"Ws-{suffix}"},
    ).json()
    project = client.post(
        "/projects", json={"workspace_id": workspace["id"], "name": f"Project-{suffix}"}
    ).json()
    agent = client.post(
        "/agents",
        json={
            "workspace_id": workspace["id"],
            "name": f"Agent-{suffix}",
            "role_id": "developer",
        },
    ).json()
    return project["id"], agent["id"]


def test_registration_requires_bootstrap_token_and_hashes_worker_token():
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    _authorize_registration()
    with TestClient(app) as client:
        denied = client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": "wrong"},
            json={
                "name": f"denied-{uuid4().hex}",
                "capabilities": [],
                "global_access": True,
            },
        )
        assert denied.status_code == 401

        response = _register(client, f"worker-{uuid4().hex}", ["git"])
        assert response.status_code == 201
        registration = response.json()
        assert registration["token"]
        assert registration["project_id"] is None
        assert registration["global_access"] is True

        with get_session_factory()() as db:
            worker = db.get(WorkerModel, registration["worker_id"])
            assert worker is not None
            assert worker.token_hash != registration["token"]
            assert registration["token"] not in worker.token_hash


def test_registration_scope_authorization_fails_closed_when_missing_or_ambiguous():
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    body = {
        "name": f"scope-config-{uuid4().hex}",
        "capabilities": [],
        "global_access": True,
    }
    headers = {"X-Worker-Registration-Token": REGISTRATION_TOKEN}
    with TestClient(app) as client:
        os.environ.pop("ACP_WORKER_REGISTRATION_PROJECT_ID", None)
        os.environ.pop("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", None)
        assert client.post("/workers/register", headers=headers, json=body).status_code == 503

        os.environ["ACP_WORKER_REGISTRATION_PROJECT_ID"] = "project-authorized"
        os.environ["ACP_WORKER_REGISTRATION_GLOBAL_ACCESS"] = "1"
        assert client.post("/workers/register", headers=headers, json=body).status_code == 503


def test_registration_token_cannot_choose_or_change_its_server_authorized_scope():
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    headers = {"X-Worker-Registration-Token": REGISTRATION_TOKEN}
    with TestClient(app) as client:
        _authenticate_owner(client)
        first_project_id, _ = _project_with_agent(client)
        second_project_id, _ = _project_with_agent(client)
        worker_name = f"authorized-scope-{uuid4().hex}"
        _authorize_registration(project_id=first_project_id, global_access=False)

        for unauthorized_body in (
            {"project_id": second_project_id, "global_access": False},
            {"project_id": None, "global_access": True},
        ):
            response = client.post(
                "/workers/register",
                headers=headers,
                json={
                    "name": worker_name,
                    "capabilities": ["git"],
                    **unauthorized_body,
                },
            )
            assert response.status_code == 403

        accepted = client.post(
            "/workers/register",
            headers=headers,
            json={
                "name": worker_name,
                "capabilities": ["git"],
                "project_id": first_project_id,
                "global_access": False,
            },
        )
        assert accepted.status_code == 201
        worker_id = accepted.json()["worker_id"]

        renewed = client.post(
            "/workers/register",
            headers=headers,
            json={
                "name": worker_name,
                "capabilities": ["git"],
                "project_id": first_project_id,
                "global_access": False,
            },
        )
        assert renewed.status_code == 201
        assert renewed.json()["worker_id"] == worker_id

        # Même nom et même secret : sans autorisation serveur correspondante, le
        # réenrôlement ne peut ni changer de projet ni devenir global.
        changed = client.post(
            "/workers/register",
            headers=headers,
            json={
                "name": worker_name,
                "capabilities": ["git"],
                "global_access": True,
            },
        )
        assert changed.status_code == 403
        with get_session_factory()() as db:
            persisted = db.get(WorkerModel, worker_id)
            assert persisted is not None
            assert persisted.project_id == first_project_id
            assert bool(persisted.global_access) is False

        _authorize_registration(global_access=True)
        global_name = f"global-authorized-{uuid4().hex}"
        global_to_project = client.post(
            "/workers/register",
            headers=headers,
            json={
                "name": global_name,
                "capabilities": [],
                "project_id": first_project_id,
                "global_access": False,
            },
        )
        assert global_to_project.status_code == 403


def test_project_scope_is_persisted_and_filters_claims_before_assignment():
    with TestClient(app) as client:
        _authenticate_owner(client)
        with get_session_factory()() as db:
            db.query(TaskModel).filter_by(status="queued").update({"status": "done"})
            db.commit()

        first_project_id, first_agent_id = _project_with_agent(client)
        second_project_id, second_agent_id = _project_with_agent(client)
        foreign_task = client.post(
            "/tasks",
            json={
                "project_id": second_project_id,
                "agent_instance_id": second_agent_id,
                "title": "Foreign project task",
                "meta": {"required_capabilities": ["git"]},
            },
        ).json()
        own_task = client.post(
            "/tasks",
            json={
                "project_id": first_project_id,
                "agent_instance_id": first_agent_id,
                "title": "Scoped project task",
                "meta": {"required_capabilities": ["git"]},
            },
        ).json()
        assert client.post(f"/tasks/{foreign_task['id']}/queue").status_code == 200
        assert client.post(f"/tasks/{own_task['id']}/queue").status_code == 200

        registration = _register(
            client,
            f"scoped-worker-{uuid4().hex}",
            ["git"],
            project_id=first_project_id,
            global_access=False,
        )
        assert registration.status_code == 201
        worker = registration.json()
        assert worker["project_id"] == first_project_id
        assert worker["global_access"] is False
        headers = {"Authorization": f"Bearer {worker['token']}"}

        # Le heartbeat est volontairement incapable d'élargir le périmètre.
        escalation = client.post(
            f"/workers/{worker['worker_id']}/heartbeat",
            headers=headers,
            json={"global_access": True},
        )
        assert escalation.status_code == 422
        with get_session_factory()() as db:
            persisted = db.get(WorkerModel, worker["worker_id"])
            assert persisted is not None
            assert persisted.project_id == first_project_id
            assert bool(persisted.global_access) is False

        claim = client.post(
            f"/workers/{worker['worker_id']}/claim", headers=headers, json={}
        )
        assert claim.status_code == 200
        assert claim.json()["task"]["id"] == own_task["id"]
        with get_session_factory()() as db:
            assert db.get(TaskModel, foreign_task["id"]).status == "queued"

        second_registration = _register(
            client,
            f"second-scoped-worker-{uuid4().hex}",
            ["git"],
            project_id=second_project_id,
            global_access=False,
        ).json()
        second_claim = client.post(
            f"/workers/{second_registration['worker_id']}/claim",
            headers={"Authorization": f"Bearer {second_registration['token']}"},
            json={},
        )
        assert second_claim.status_code == 200
        assert second_claim.json()["task"]["id"] == foreign_task["id"]


def test_unscoped_worker_is_quarantined_and_cannot_claim_any_project():
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    _authorize_registration()
    with TestClient(app) as client:
        _authenticate_owner(client)
        project_id, agent_id = _project_with_agent(client)
        task = client.post(
            "/tasks",
            json={
                "project_id": project_id,
                "agent_instance_id": agent_id,
                "title": "Never exposed to an unscoped worker",
                "meta": {"required_capabilities": ["git"]},
            },
        ).json()
        assert client.post(f"/tasks/{task['id']}/queue").status_code == 200
        refused_registration = client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": REGISTRATION_TOKEN},
            json={
                "name": f"quarantined-worker-{uuid4().hex}",
                "capabilities": ["git"],
            },
        )
        assert refused_registration.status_code == 422

        # Une ligne historique migrée demeure volontairement sans portée. On
        # conserve son jeton seulement pour prouver que même authentifiée elle
        # n'accède à aucune file avant un réenrôlement explicite.
        worker = _register(
            client, f"legacy-quarantined-{uuid4().hex}", ["git"]
        ).json()
        with get_session_factory()() as db:
            persisted = db.get(WorkerModel, worker["worker_id"])
            assert persisted is not None
            persisted.global_access = 0
            persisted.project_id = None
            db.commit()

        claim = client.post(
            f"/workers/{worker['worker_id']}/claim",
            headers={"Authorization": f"Bearer {worker['token']}"},
            json={},
        )
        assert claim.status_code == 200
        assert claim.json()["task"] is None
        assert "sans périmètre" in claim.json()["reason"]
        with get_session_factory()() as db:
            persisted_task = db.get(TaskModel, task["id"])
            assert persisted_task.status == "queued"
            persisted_task.status = "done"
            db.commit()


def test_heartbeat_capability_matching_concurrency_and_lease_release():
    with TestClient(app) as client:
        _authenticate_owner(client)
        worker_name = f"worker-{uuid4().hex}"
        registration = _register(client, worker_name, ["git"]).json()
        worker_id = registration["worker_id"]
        headers = {"Authorization": f"Bearer {registration['token']}"}

        assert client.post(
            f"/workers/{worker_id}/heartbeat",
            headers={"Authorization": "Bearer invalid"},
            json={},
        ).status_code == 401
        heartbeat = client.post(
            f"/workers/{worker_id}/heartbeat", headers=headers, json={}
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["active_runs"] == 0

        project_id, agent_id = _project_with_agent(client)
        incompatible = client.post(
            "/tasks",
            json={
                "project_id": project_id,
                "agent_instance_id": agent_id,
                "title": "Needs Blender",
                "meta": {"required_capabilities": ["blender"]},
            },
        ).json()
        client.post(f"/tasks/{incompatible['id']}/queue")
        no_claim = client.post(
            f"/workers/{worker_id}/claim",
            headers=headers,
            json={"provider_id": "mock"},
        ).json()
        assert no_claim["task"] is None
        assert no_claim["reason"] == "aucune tâche compatible"

        compatible = client.post(
            "/tasks",
            json={
                "project_id": project_id,
                "agent_instance_id": agent_id,
                "title": "Git task",
                "meta": {"required_capabilities": ["git"]},
            },
        ).json()
        assert client.patch(
            f"/tasks/{compatible['id']}", json={"status": "done"}
        ).status_code == 422
        client.post(f"/tasks/{compatible['id']}/queue")
        claim = client.post(
            f"/workers/{worker_id}/claim",
            headers=headers,
            json={"provider_id": "mock"},
        )
        assert claim.status_code == 200
        claimed = claim.json()
        assert claimed["task"]["id"] == compatible["id"]
        assert claimed["required_capabilities"] == ["git"]

        full = client.post(
            f"/workers/{worker_id}/claim", headers=headers, json={}
        ).json()
        assert full["reason"] == "capacité de concurrence atteinte"
        assert _register(client, worker_name, ["git"]).status_code == 409

        run_id = claimed["task_run"]["id"]
        renewal = client.post(
            f"/workers/{worker_id}/leases/{run_id}/renew", headers=headers
        )
        assert renewal.status_code == 200
        assert renewal.json()["task_run_id"] == run_id

        event = {
            "type": "task.progress",
            "project_id": project_id,
            "task_id": compatible["id"],
            "task_run_id": run_id,
            "payload": {"step": "test"},
        }
        assert client.post("/events", json=event).status_code == 401
        worker_headers = {**headers, "X-Worker-Id": worker_id}
        assert client.post("/events", headers=worker_headers, json=event).status_code == 200
        wrong_scope_event = {
            **event,
            "id": str(uuid4()),
            "workspace_id": str(uuid4()),
        }
        assert client.post(
            "/events", headers=worker_headers, json=wrong_scope_event
        ).status_code == 400
        forbidden_terminal_event = {**event, "type": "task.completed"}
        assert client.post(
            "/events", headers=worker_headers, json=forbidden_terminal_event
        ).status_code == 400

        assert client.patch(f"/task-runs/{run_id}", json={"status": "succeeded"}).status_code == 401
        unsupported_success = client.patch(
            f"/task-runs/{run_id}",
            headers=worker_headers,
            json={"status": "succeeded", "result": {"technical_validation": "unknown"}},
        )
        assert unsupported_success.status_code == 422
        assert client.patch(
            f"/task-runs/{run_id}",
            headers=worker_headers,
            json={
                "status": "succeeded",
                "result": {
                    "technical_validation": "passed",
                    "evidence": [{"kind": "test", "exit_code": 0}],
                },
            },
        ).status_code == 200
        terminal_events = client.get(
            "/events", params={"project_id": project_id, "limit": 100}
        ).json()
        assert any(
            item["type"] == "task.completed" and item["task_run_id"] == run_id
            for item in terminal_events
        )
        renewal = client.post(
            f"/workers/{worker_id}/leases/{run_id}/renew", headers=headers
        )
        assert renewal.status_code == 404

        heartbeat = client.post(
            f"/workers/{worker_id}/heartbeat", headers=headers, json={}
        ).json()
        assert heartbeat["active_runs"] == 0


def test_legacy_claim_is_disabled_by_default():
    os.environ.pop("ACP_ALLOW_LEGACY_WORKER_CLAIM", None)
    with TestClient(app) as client:
        response = client.post(
            "/worker/claim", json={"worker_id": "legacy", "provider_id": "mock"}
        )
        assert response.status_code == 410


def test_expired_lease_blocks_uncertain_task_and_releases_capacity():
    with TestClient(app) as client:
        _authenticate_owner(client)
        registration = _register(client, f"worker-{uuid4().hex}", ["git"]).json()
        worker_id = registration["worker_id"]
        headers = {"Authorization": f"Bearer {registration['token']}"}
        project_id, agent_id = _project_with_agent(client)
        task = client.post(
            "/tasks",
            json={
                "project_id": project_id,
                "agent_instance_id": agent_id,
                "title": "Recoverable task",
                "meta": {"required_capabilities": ["git"]},
            },
        ).json()
        client.post(f"/tasks/{task['id']}/queue")
        claim = client.post(
            f"/workers/{worker_id}/claim", headers=headers, json={}
        ).json()
        run_id = claim["task_run"]["id"]

        with get_session_factory()() as db:
            lease = db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one()
            lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

        renewal = client.post(
            f"/workers/{worker_id}/leases/{run_id}/renew", headers=headers
        )
        assert renewal.status_code == 409
        assert "run interrompu" in renewal.json()["detail"]

        heartbeat = client.post(
            f"/workers/{worker_id}/heartbeat", headers=headers, json={}
        ).json()
        assert heartbeat["active_runs"] == 0
        tasks = client.get("/tasks", params={"project_id": project_id}).json()
        assert next(item for item in tasks if item["id"] == task["id"])["status"] == "blocked"
        runs = client.get("/task-runs", params={"task_id": task["id"]}).json()
        interrupted = next(item for item in runs if item["id"] == run_id)
        assert interrupted["status"] == "interrupted"
        assert "reprise automatique interdite" in interrupted["logs"][-1]["message"]
        events = client.get(
            "/events", params={"project_id": project_id, "limit": 100}
        ).json()
        assert any(
            item["type"] == "task.interrupted"
            and item["task_run_id"] == run_id
            and item["payload"]["reason"] == "worker_lease_expired"
            for item in events
        )
        # L'événement doit aussi être numéroté : sans séquence de tentative ni
        # numéro de journal, le Studio ne verrait jamais la tentative se clore.
        run_page = client.get(f"/runs/{run_id}/events").json()
        assert [item["type"] for item in run_page["events"]] == ["task.interrupted"]
        assert run_page["events"][0]["sequence"] is not None
        project_page = client.get(f"/projects/{project_id}/events").json()
        assert any(
            item["type"] == "task.interrupted" for item in project_page["events"]
        )


def test_resource_locks_artifacts_and_approvals():
    with TestClient(app) as client:
        _authenticate_owner(client)
        first = _register(client, f"worker-{uuid4().hex}", ["git", "codex_cli"]).json()
        second = _register(client, f"worker-{uuid4().hex}", ["git", "codex_cli"]).json()
        first_headers = {"Authorization": f"Bearer {first['token']}"}
        second_headers = {"Authorization": f"Bearer {second['token']}"}
        with get_session_factory()() as db:
            db.query(TaskModel).filter_by(status="queued").update({"status": "done"})
            db.commit()
        project_id, first_agent = _project_with_agent(client)
        workspace_id = next(
            project["workspace_id"]
            for project in client.get("/projects").json()
            if project["id"] == project_id
        )
        second_agent = client.post(
            "/agents",
            json={
                "workspace_id": workspace_id,
                "name": f"Agent-{uuid4().hex[:8]}",
                "role_id": "developer",
            },
        ).json()["id"]

        run_ids = []
        for worker, headers, agent in (
            (first, first_headers, first_agent),
            (second, second_headers, second_agent),
        ):
            task = client.post(
                "/tasks",
                json={
                    "project_id": project_id,
                    "agent_instance_id": agent,
                    "title": f"Lock task {worker['worker_id']}",
                    "meta": {"required_capabilities": ["git", "codex_cli"]},
                },
            ).json()
            client.post(f"/tasks/{task['id']}/queue")
            claim = client.post(
                f"/workers/{worker['worker_id']}/claim", headers=headers, json={}
            ).json()
            run_ids.append(claim["task_run"]["id"])
            headers["X-Attempt-Fencing-Token"] = str(claim["fencing_token"])

        resource_key = f"refs/heads/test-{uuid4().hex}"
        acquired = client.post(
            "/locks/acquire",
            headers=first_headers,
            json={
                "worker_id": first["worker_id"],
                "owner_run_id": run_ids[0],
                "resource_type": "git_branch",
                "resource_key": resource_key,
            },
        )
        assert acquired.status_code == 201
        lock_id = acquired.json()["id"]
        conflict = client.post(
            "/locks/acquire",
            headers=second_headers,
            json={
                "worker_id": second["worker_id"],
                "owner_run_id": run_ids[1],
                "resource_type": "git_branch",
                "resource_key": resource_key,
            },
        )
        assert conflict.status_code == 409
        assert client.post(
            f"/locks/{lock_id}/renew",
            headers=first_headers,
            json={"worker_id": first["worker_id"], "owner_run_id": run_ids[0]},
        ).status_code == 200

        artifact_payload = {
            "project_id": project_id,
            "task_run_id": run_ids[0],
            "kind": "report",
            "path": "reports/result.json",
            "size_bytes": 42,
        }
        assert client.post(
            f"/workers/{first['worker_id']}/artifacts",
            headers={"Authorization": f"Bearer {first['token']}"},
            json=artifact_payload,
        ).status_code == 409
        assert client.post(
            f"/workers/{first['worker_id']}/artifacts",
            headers={
                **first_headers,
                "X-Attempt-Fencing-Token": str(
                    int(first_headers["X-Attempt-Fencing-Token"]) + 1
                ),
            },
            json=artifact_payload,
        ).status_code == 409

        invalid_artifact = client.post(
            f"/workers/{first['worker_id']}/artifacts",
            headers=first_headers,
            json={
                "project_id": project_id,
                "task_run_id": run_ids[0],
                "kind": "report",
                "path": "../secret.txt",
            },
        )
        assert invalid_artifact.status_code == 422
        artifact = client.post(
            f"/workers/{first['worker_id']}/artifacts",
            headers=first_headers,
            json=artifact_payload,
        )
        assert artifact.status_code == 201

        assert client.post(
            f"/locks/{lock_id}/release",
            headers=first_headers,
            json={"worker_id": first["worker_id"], "owner_run_id": run_ids[0]},
        ).json()["status"] == "released"
        assert client.post(
            "/locks/acquire",
            headers=second_headers,
            json={
                "worker_id": second["worker_id"],
                "owner_run_id": run_ids[1],
                "resource_type": "git_branch",
                "resource_key": resource_key,
            },
        ).status_code == 201

        approval = client.post(
            "/approvals",
            json={
                "project_id": project_id,
                "task_run_id": run_ids[0],
                "action": "git_publish",
                "reason": "Publier la branche validée",
            },
        )
        assert approval.status_code == 201
        approval_id = approval.json()["id"]
        decision = client.post(
            f"/approvals/{approval_id}/decision",
            json={"decision": "APPROVED", "comment": "Tests vérifiés"},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "APPROVED"
        assert client.post(
            f"/approvals/{approval_id}/decision",
            json={"decision": "REJECTED"},
        ).status_code == 409
