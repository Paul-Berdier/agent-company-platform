"""Tests du protocole d'enregistrement et d'attribution des workers."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from acp_api.main import app
from acp_database import get_session_factory
from acp_database.models import TaskModel, WorkerLeaseModel, WorkerModel


REGISTRATION_TOKEN = "test-registration-secret"


def _register(client: TestClient, name: str, capabilities: list[str]):
    os.environ["ACP_WORKER_REGISTRATION_TOKEN"] = REGISTRATION_TOKEN
    return client.post(
        "/workers/register",
        headers={"X-Worker-Registration-Token": REGISTRATION_TOKEN},
        json={
            "name": name,
            "capabilities": capabilities,
            "max_concurrency": 1,
            "simulation": True,
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
    with TestClient(app) as client:
        denied = client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": "wrong"},
            json={"name": f"denied-{uuid4().hex}", "capabilities": []},
        )
        assert denied.status_code == 401

        response = _register(client, f"worker-{uuid4().hex}", ["git"])
        assert response.status_code == 201
        registration = response.json()
        assert registration["token"]

        with get_session_factory()() as db:
            worker = db.get(WorkerModel, registration["worker_id"])
            assert worker is not None
            assert worker.token_hash != registration["token"]
            assert registration["token"] not in worker.token_hash


def test_heartbeat_capability_matching_concurrency_and_lease_release():
    with TestClient(app) as client:
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

        client.patch(f"/task-runs/{run_id}", json={"status": "succeeded"})
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


def test_expired_lease_requeues_task_and_releases_capacity():
    with TestClient(app) as client:
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

        heartbeat = client.post(
            f"/workers/{worker_id}/heartbeat", headers=headers, json={}
        ).json()
        assert heartbeat["active_runs"] == 0
        tasks = client.get("/tasks", params={"project_id": project_id}).json()
        assert next(item for item in tasks if item["id"] == task["id"])["status"] == "queued"
        runs = client.get("/task-runs", params={"task_id": task["id"]}).json()
        assert next(item for item in runs if item["id"] == run_id)["status"] == "failed"


def test_resource_locks_artifacts_and_approvals():
    with TestClient(app) as client:
        first = _register(client, f"worker-{uuid4().hex}", ["git", "codex_cli"]).json()
        second = _register(client, f"worker-{uuid4().hex}", ["git", "codex_cli"]).json()
        first_headers = {"Authorization": f"Bearer {first['token']}"}
        second_headers = {"Authorization": f"Bearer {second['token']}"}
        with get_session_factory()() as db:
            db.query(TaskModel).filter_by(status="queued").update({"status": "done"})
            db.commit()
        project_id, first_agent = _project_with_agent(client)
        workspace_id = client.get("/projects").json()[-1]["workspace_id"]
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
            json={
                "project_id": project_id,
                "task_run_id": run_ids[0],
                "kind": "report",
                "path": "reports/result.json",
                "size_bytes": 42,
            },
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
