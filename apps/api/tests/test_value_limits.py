"""Valeurs que PostgreSQL refuse et que SQLite acceptait : même verdict sur les deux dialectes.

SQLite stocke des entiers de 64 bits, des textes de longueur quelconque et l'octet
NUL ; PostgreSQL refuse un entier hors de la plage de sa colonne, un texte plus long
que son ``VARCHAR(n)`` et tout texte contenant ``\\x00``. Chaque test tourne sur le
moteur de ``make_test_engine`` : SQLite sans ``ACP_TEST_DATABASE_URL``, un schéma
PostgreSQL éphémère avec. Une valeur légitime (code de sortie Windows, durée, taille)
doit passer partout ; une valeur impossible à stocker doit être refusée en 422
français partout, jamais en 500 sur un seul dialecte.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from acp_api.deps import get_db
from acp_api.main import app
from acp_database.models import (
    ArtifactModel,
    MissionEvidenceModel,
    TestCaseModel,
    TestRunModel,
)
from acp_database.testing import make_test_engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

PASSWORD = "correct horse battery staple"
# 0xC000013A : code rendu par Windows à un programme arrêté par CTRL_BREAK.
WINDOWS_CTRL_BREAK_EXIT = 3221225786
# 0xC0000005 : violation d'accès.
WINDOWS_ACCESS_VIOLATION_EXIT = 3221225477
BEYOND_INT64 = 2**63


@pytest.fixture
def limits_context(monkeypatch, tmp_path):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    registration_token = f"registration-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", registration_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    database = make_test_engine(tmp_path)
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
                    "display_name": "Propriétaire des bornes",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201, bootstrap.text
            client.headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
            organization = client.post(
                "/organizations", json={"name": "Org des bornes"}
            ).json()
            workspace = client.post(
                "/workspaces",
                json={"organization_id": organization["id"], "name": "Ws des bornes"},
            ).json()
            project = client.post(
                "/projects",
                json={"workspace_id": workspace["id"], "name": "Projet des bornes"},
            ).json()
            monkeypatch.setenv("ACP_WORKER_REGISTRATION_PROJECT_ID", project["id"])
            monkeypatch.setenv("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", "0")
            agent = client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Agent des bornes",
                    "role_id": "developer",
                },
            ).json()
            worker = client.post(
                "/workers/register",
                headers={"X-Worker-Registration-Token": registration_token},
                json={
                    "name": f"worker-{uuid4().hex}",
                    "capabilities": ["git"],
                    "max_concurrency": 4,
                    "simulation": False,
                    "project_id": project["id"],
                },
            )
            assert worker.status_code == 201, worker.text
            yield {
                "client": client,
                "session_factory": session_factory,
                "backend": database.backend,
                "workspace_id": workspace["id"],
                "project_id": project["id"],
                "agent_id": agent["id"],
                "worker": worker.json(),
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close()


def _start_attempt(context) -> dict:
    """Crée une mission et la fait réclamer : tentative réelle et bail actif."""

    client = context["client"]
    mission = client.post(
        "/missions",
        headers={"Idempotency-Key": f"create-{uuid4().hex}"},
        json={
            "project_id": context["project_id"],
            "agent_instance_id": context["agent_id"],
            "title": f"Mission {uuid4().hex[:8]}",
            "objective": "Produire une modification vérifiable",
            "expected_outcome": "Une sortie testée et documentée",
            "acceptance_criteria": ["les tests passent"],
            "autonomy": {
                "mode": "bounded",
                "allowed_actions": ["read", "edit_project"],
                "forbidden_actions": ["deploy"],
                "approval_required_actions": [],
            },
            "resources": [
                {"kind": "git_repository", "identifier": "workspace", "access": "write"}
            ],
            "budget": {"max_tokens": 10_000, "max_tool_calls": 50},
            "duration_seconds": 3600,
            "required_capabilities": ["git"],
        },
    )
    assert mission.status_code == 201, mission.text
    worker = context["worker"]
    claim = client.post(
        f"/workers/{worker['worker_id']}/claim",
        headers={"Authorization": f"Bearer {worker['token']}"},
        json={"provider_id": "mock"},
    )
    assert claim.status_code == 200, claim.text
    body = claim.json()
    assert body["task"] is not None, body
    return {
        "mission_id": mission.json()["id"],
        "task_id": body["task"]["id"],
        "run_id": body["attempt_id"],
        "fencing_token": body["fencing_token"],
    }


def _worker_headers(context, attempt=None) -> dict[str, str]:
    worker = context["worker"]
    headers = {
        "Authorization": f"Bearer {worker['token']}",
        "X-Worker-Id": worker["worker_id"],
    }
    if attempt is not None:
        headers["X-Attempt-Fencing-Token"] = str(attempt["fencing_token"])
    return headers


def _patch_run(context, attempt, payload):
    return context["client"].patch(
        f"/task-runs/{attempt['run_id']}",
        headers=_worker_headers(context, attempt),
        json=payload,
    )


def _evidence(exit_code: int) -> dict:
    return {
        "kind": "command",
        "summary": "Programme arrêté par CTRL_BREAK",
        "command": "node serveur.js",
        "exit_code": exit_code,
    }


def _ingest(context, attempt, *, exit_code, duration_ms, events=None):
    worker = context["worker"]
    return context["client"].post(
        f"/workers/{worker['worker_id']}/test-runs",
        headers=_worker_headers(context),
        json={
            "task_run_id": attempt["run_id"],
            "fencing_token": attempt["fencing_token"],
            "runner": "playwright",
            "runner_version": "1.47.0",
            "exit_code": exit_code,
            "events": events
            or [
                {"kind": "run_begin", "started_at": "2026-09-12T10:00:00+00:00"},
                {
                    "kind": "test_end",
                    "test_id": "panier.spec.ts:12:3",
                    "title": "le panier survit",
                    "attempt": 1,
                    "status": "failed",
                    "outcome": "unexpected",
                    "duration_ms": duration_ms,
                },
                {
                    "kind": "run_end",
                    "finished_at": "2026-09-12T10:00:12+00:00",
                    "run_status": "failed",
                    "exit_code": exit_code,
                    "totals": {"unexpected": 1},
                },
            ],
        },
    )


def _french_refusal(response) -> str:
    """Texte des refus 422 : chaque message doit être en français et sans SQL."""

    assert response.status_code == 422, response.text
    text = response.text
    for leak in ("INSERT", "UPDATE ", "SELECT", "psycopg", "sqlite3", "[SQL"):
        assert leak not in text, text
    return text


# --- R14 : entiers au-delà de 2^31 ---------------------------------------------


def test_a_windows_exit_code_is_kept_as_mission_evidence(limits_context):
    context = limits_context
    attempt = _start_attempt(context)
    assert _patch_run(context, attempt, {"status": "running"}).status_code == 200

    response = _patch_run(
        context, attempt, {"evidence": [_evidence(WINDOWS_CTRL_BREAK_EXIT)]}
    )

    assert response.status_code == 200, response.text
    with context["session_factory"]() as db:
        stored = db.query(MissionEvidenceModel).filter_by(
            task_run_id=attempt["run_id"]
        ).one()
        assert stored.exit_code == WINDOWS_CTRL_BREAK_EXIT


def test_a_test_report_keeps_a_windows_exit_code_and_a_long_duration(limits_context):
    context = limits_context
    attempt = _start_attempt(context)
    long_duration = 3_000_000_000  # 34,7 jours en millisecondes, au-delà de 2^31

    response = _ingest(
        context,
        attempt,
        exit_code=WINDOWS_ACCESS_VIOLATION_EXIT,
        duration_ms=long_duration,
    )

    assert response.status_code == 200, response.text
    with context["session_factory"]() as db:
        run = db.query(TestRunModel).filter_by(task_run_id=attempt["run_id"]).one()
        assert run.exit_code == WINDOWS_ACCESS_VIOLATION_EXIT
        case = db.query(TestCaseModel).filter_by(test_run_id=run.id).one()
        assert case.duration_ms == long_duration


def test_an_artifact_of_more_than_two_gibibytes_keeps_its_size(limits_context):
    context = limits_context
    attempt = _start_attempt(context)
    size = 5 * 1024**3
    worker = context["worker"]

    response = context["client"].post(
        f"/workers/{worker['worker_id']}/artifacts",
        headers=_worker_headers(context, attempt),
        json={
            "project_id": context["project_id"],
            "task_run_id": attempt["run_id"],
            "kind": "archive",
            "path": "dist/image-disque.img",
            "size_bytes": size,
        },
    )

    assert response.status_code == 201, response.text
    with context["session_factory"]() as db:
        artifact = db.get(ArtifactModel, response.json()["id"])
        assert artifact.size_bytes == size


def test_an_exit_code_beyond_64_bits_is_refused_in_french_on_both_dialects(
    limits_context,
):
    context = limits_context
    attempt = _start_attempt(context)
    assert _patch_run(context, attempt, {"status": "running"}).status_code == 200

    evidence = _patch_run(context, attempt, {"evidence": [_evidence(BEYOND_INT64)]})
    report = _ingest(context, attempt, exit_code=BEYOND_INT64, duration_ms=1)

    assert "hors de la plage" in _french_refusal(evidence)
    assert "hors de la plage" in _french_refusal(report)
    with context["session_factory"]() as db:
        assert db.query(MissionEvidenceModel).count() == 0
        assert db.query(TestRunModel).count() == 0


@pytest.mark.parametrize("instant", ["9999-12-31T23:00:00-05:00", "0001-01-01T00:00:00+05:00"])
def test_worker_event_refuses_unreadable_utc_timestamp(limits_context, instant):
    context = limits_context
    attempt = _start_attempt(context)
    response = context["client"].post(
        "/events", headers=_worker_headers(context, attempt),
        json={"type": "task.progress", "occurred_at": instant,
              "task_id": attempt["task_id"], "task_run_id": attempt["run_id"],
              "project_id": context["project_id"]},
    )
    assert "UTC" in _french_refusal(response)


@pytest.mark.parametrize("name,reason", [("n" * 201, "200"), ("avant\x00après", "NUL")])
def test_crud_values_have_same_refusal_on_both_databases(limits_context, name, reason):
    response = limits_context["client"].post("/organizations", json={"name": name})
    assert reason in _french_refusal(response)


def test_generated_workflow_title_does_not_fail_a_mission(limits_context):
    context = limits_context
    attempt = _start_attempt(context)
    assert _patch_run(context, attempt, {"status": "running"}).status_code == 200
    response = _patch_run(context, attempt, {"workflow_step": "titre" * 50})
    assert response.status_code == 200, response.text
    from acp_database.models import TaskModel
    with context["session_factory"]() as db:
        title = db.get(TaskModel, attempt["task_id"]).workflow_step
    assert len(title) == 100 and title.endswith("…")


def test_report_with_nul_keeps_machine_error_with_visible_replacement(limits_context):
    context = limits_context
    attempt = _start_attempt(context)
    response = _ingest(context, attempt, exit_code=1, duration_ms=0, events=[
        {"kind": "run_begin", "started_at": "2026-09-19T10:00:00Z"},
        {"kind": "test_end", "test_id": "nul", "title": "sortie binaire",
         "status": "failed", "outcome": "unexpected", "error_message": "avant\x00après"},
        {"kind": "run_end", "finished_at": "2026-09-19T10:00:01Z", "run_status": "failed"},
    ])
    assert response.status_code == 200, response.text
    with context["session_factory"]() as db:
        assert db.query(TestCaseModel).one().error_message == "avant�après"


async def test_real_local_process_nul_outputs_reach_the_terminal_patch(
    limits_context, tmp_path
):
    """Une sortie binaire réelle ne doit perdre ni sa preuve ni son état terminal."""
    import hashlib
    import json
    import sys

    from acp_database.models import TaskRunModel, WorkerLeaseModel
    from acp_worker.local_runner import (
        EVIDENCE_FILENAME,
        REQUEST_SCHEMA,
        LocalRunnerConfig,
        LocalRunRequest,
        run_local_program,
    )
    from acp_worker.main import platform_evidence

    context = limits_context
    attempt = _start_attempt(context)
    assert _patch_run(context, attempt, {"status": "running"}).status_code == 200
    request = LocalRunRequest(
        run_id=attempt["task_id"], attempt_id=attempt["run_id"],
        attempt_number=1, fencing_token=attempt["fencing_token"],
        payload={"schema": REQUEST_SCHEMA},
    )
    execution = await run_local_program(
        LocalRunnerConfig(
            argv=(sys.executable, "-I", "-c",
                  "import sys; sys.stdout.buffer.write(b'stdout\\x00tail'); "
                  "sys.stderr.buffer.write(b'stderr\\x00tail')"),
            run_root=tmp_path / "real-runner", timeout_seconds=5,
            max_output_bytes=1024, terminate_grace_seconds=0.05,
        ),
        request,
    )
    assert execution.succeeded
    assert execution.stdout.text == "stdout\x00tail"
    assert execution.stderr.text == "stderr\x00tail"
    evidence = platform_evidence(execution, request)
    response = _patch_run(context, attempt, {
        "status": "succeeded",
        "technical_validation": {"status": "passed"},
        "evidence": [evidence],
        "result": {"execution_mode": "real_local_process", "evidence": [evidence]},
    })
    assert response.status_code == 200, response.text
    with context["session_factory"]() as db:
        stored = db.query(MissionEvidenceModel).filter_by(task_run_id=attempt["run_id"]).one()
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.status == "succeeded"
        assert db.query(WorkerLeaseModel).filter_by(task_run_id=run.id).one().status == "released"
        for stream in ("stdout", "stderr"):
            raw = stream.encode() + b"\x00tail"
            expected = stream + "�tail"
            assert stored.data[stream]["text"] == expected
            assert run.result["evidence"][0]["data"][stream]["text"] == expected
            assert stored.data[stream]["sha256"] == hashlib.sha256(raw).hexdigest()
            assert stored.data[stream]["captured_bytes"] == len(raw)
            # Les octets et empreintes locaux restent la preuve originale.
            assert evidence["data"][stream]["text"] == raw.decode()
    local = json.loads((execution.run_directory / EVIDENCE_FILENAME).read_text(encoding="utf-8"))
    assert local["stdout"]["text"] == "stdout\x00tail"
    assert local["stderr"]["text"] == "stderr\x00tail"
