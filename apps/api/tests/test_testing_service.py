"""Résultats de tests structurés : ingestion worker, statuts distincts et validation dérivée.

Aucun navigateur n'est lancé : le reporter Playwright est simulé par les événements
NDJSON normalisés que le worker transmet (``TestIngestRequest``).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api import events_bus
from acp_api.deps import get_db
from acp_api.main import app
from acp_api.security import create_user_session, hash_password, utcnow
from acp_api.testing_service import derive_technical_validation
from acp_contracts import TestRunSummary, TestTotals
from acp_database.models import (
    ArtifactModel,
    Base,
    EventModel,
    MembershipModel,
    TaskRunModel,
    TestCaseModel,
    TestRunModel,
    UserModel,
    WorkerLeaseModel,
)

PASSWORD = "correct horse battery staple"
STARTED_AT = "2026-09-12T10:00:00+00:00"
FINISHED_AT = "2026-09-12T10:00:12+00:00"


@pytest.fixture
def testing_context(monkeypatch):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    registration_token = f"registration-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", registration_token)
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
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": f"owner-{uuid4().hex}",
                    "display_name": "Propriétaire des tests",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201, bootstrap.text
            owner_csrf = bootstrap.json()["csrf_token"]
            client.headers["X-CSRF-Token"] = owner_csrf
            owner_cookie = client.cookies.get("acp_session")
            organization = client.post(
                "/organizations", json={"name": "Org des tests"}
            ).json()
            workspace = client.post(
                "/workspaces",
                json={"organization_id": organization["id"], "name": "Ws des tests"},
            ).json()
            project = client.post(
                "/projects",
                json={"workspace_id": workspace["id"], "name": "Projet des tests"},
            ).json()
            agent = client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Agent des tests",
                    "role_id": "developer",
                },
            ).json()
            yield {
                "client": client,
                "session_factory": session_factory,
                "organization_id": organization["id"],
                "workspace_id": workspace["id"],
                "project_id": project["id"],
                "agent_id": agent["id"],
                "registration_token": registration_token,
                "owner_cookie": owner_cookie,
                "owner_csrf": owner_csrf,
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


# --- Fabriques ----------------------------------------------------------------


def _register_worker(context, name=None):
    response = context["client"].post(
        "/workers/register",
        headers={"X-Worker-Registration-Token": context["registration_token"]},
        json={
            "name": name or f"worker-{uuid4().hex}",
            # La capacité de test web appartient à l'agent worker (E5) et évolue
            # encore ; ces tests n'en dépendent pas et se contentent de ``git``.
            "capabilities": ["git"],
            "max_concurrency": 1,
            "simulation": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mission_payload(context, title):
    return {
        "project_id": context["project_id"],
        "agent_instance_id": context["agent_id"],
        "title": title,
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
    }


def _restore_owner(context):
    client = context["client"]
    client.cookies.clear()
    client.cookies.set("acp_session", context["owner_cookie"])
    client.headers["X-CSRF-Token"] = context["owner_csrf"]


def _start_attempt(context, worker, title=None):
    """Crée une mission et la fait réclamer par ``worker`` : run réel et lease actif."""

    _restore_owner(context)
    client = context["client"]
    mission = client.post(
        "/missions",
        headers={"Idempotency-Key": f"create-{uuid4().hex}"},
        json=_mission_payload(context, title or f"Mission {uuid4().hex[:8]}"),
    )
    assert mission.status_code == 201, mission.text
    claim = client.post(
        f"/workers/{worker['worker_id']}/claim",
        headers={"Authorization": f"Bearer {worker['token']}"},
        json={"provider_id": "mock"},
    )
    assert claim.status_code == 200, claim.text
    body = claim.json()
    assert body["task"] is not None, body
    return {
        "task_id": body["task"]["id"],
        "run_id": body["attempt_id"],
        "fencing_token": body["fencing_token"],
    }


def _run_begin(**overrides):
    event = {
        "kind": "run_begin",
        "started_at": STARTED_AT,
        "runner_version": "1.47.0",
        "config": {"projects": ["chromium"], "workers": 4},
    }
    event.update(overrides)
    return event


def _test_end(test_id, status="passed", outcome="expected", **overrides):
    event = {
        "kind": "test_end",
        "test_id": test_id,
        "title": f"titre de {test_id}",
        "suite_path": ["specs", "panier"],
        "location": {"file": "tests/panier.spec.ts", "line": 12, "column": 3},
        "project_name": "chromium",
        "attempt": 1,
        "expected_status": "passed",
        "status": status,
        "outcome": outcome,
        "duration_ms": 120,
    }
    event.update(overrides)
    return event


def _run_end(totals=None, **overrides):
    event = {
        "kind": "run_end",
        "finished_at": FINISHED_AT,
        "totals": totals or {},
        "run_status": "completed",
        "exit_code": 0,
    }
    event.update(overrides)
    return event


def _totals(**counters):
    base = {
        "expected": 0,
        "unexpected": 0,
        "flaky": 0,
        "skipped": 0,
        "interrupted": 0,
        "timedOut": 0,
    }
    base.update(counters)
    return base


def _ingest(context, worker, attempt, events, *, fencing_token=None, exit_code=0):
    return context["client"].post(
        f"/workers/{worker['worker_id']}/test-runs",
        headers={
            "Authorization": f"Bearer {worker['token']}",
            "X-Worker-Id": worker["worker_id"],
        },
        json={
            "task_run_id": attempt["run_id"],
            "fencing_token": (
                attempt["fencing_token"] if fencing_token is None else fencing_token
            ),
            "runner": "playwright",
            "runner_version": "1.47.0",
            "config": {"base_url": "http://localhost:4173"},
            "exit_code": exit_code,
            "events": events,
        },
    )


def _green_report():
    return [
        _run_begin(),
        _test_end("panier.spec.ts:12:3"),
        _run_end(_totals(expected=1)),
    ]


def _member_session(context, *, project_ids=()):
    with context["session_factory"]() as db:
        user = UserModel(
            login_normalized=f"membre-{uuid4().hex}",
            display_name="Membre",
            password_hash=hash_password(PASSWORD),
            platform_role="member",
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        for project_id in project_ids:
            db.add(
                MembershipModel(
                    user_id=user.id,
                    scope_type="project",
                    scope_id=project_id,
                    role="member",
                )
            )
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
        return session_token, csrf_token


def _authenticate(context, session_token, csrf_token):
    client = context["client"]
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _drain(queue):
    """Vide une file de réveil du hub d'événements sans jamais attendre."""

    sequences = []
    while True:
        try:
            sequences.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return sequences


def _event_types(context, run_id):
    with context["session_factory"]() as db:
        return [
            row.type
            for row in db.query(EventModel)
            .filter_by(task_run_id=run_id)
            .order_by(EventModel.sequence)
            .all()
        ]


# --- Ingestion ----------------------------------------------------------------


def test_a_full_report_is_ingested_once_and_replaying_it_changes_nothing(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("panier.spec.ts:12:3"),
        _test_end("panier.spec.ts:30:3", status="failed", outcome="unexpected"),
        _run_end(_totals(expected=1, unexpected=1), run_status="failed", exit_code=1),
    ]

    first = _ingest(testing_context, worker, attempt, events, exit_code=1)
    assert first.status_code == 200, first.text
    detail = first.json()
    assert detail["task_run_id"] == attempt["run_id"]
    assert detail["case_count"] == 2
    assert len(detail["cases"]) == 2
    assert detail["status"] == "failed"
    assert detail["runner_version"] == "1.47.0"
    # Les horodatages du rapport font foi : 10:00:00 → 10:00:12.
    assert detail["duration_ms"] == 12_000

    second = _ingest(testing_context, worker, attempt, events, exit_code=1)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == detail["id"]
    assert second.json()["case_count"] == 2

    with testing_context["session_factory"]() as db:
        assert (
            db.query(TestRunModel).filter_by(task_run_id=attempt["run_id"]).count() == 1
        )
        assert db.query(TestCaseModel).filter_by(test_run_id=detail["id"]).count() == 2

    types = _event_types(testing_context, attempt["run_id"])
    assert types.count("test.run.started") == 1
    assert types.count("test.case.finished") == 2
    assert types.count("test.run.finished") == 1


def test_a_case_repeated_inside_one_batch_is_stored_once(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    duplicated = _test_end("panier.spec.ts:12:3")
    response = _ingest(
        testing_context,
        worker,
        attempt,
        [_run_begin(), duplicated, duplicated, _run_end(_totals(expected=1))],
    )
    assert response.status_code == 200, response.text
    assert response.json()["case_count"] == 1


def test_every_playwright_status_and_flaky_is_kept_distinct(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("a.spec.ts:1:1", status="passed", outcome="expected"),
        _test_end("b.spec.ts:1:1", status="failed", outcome="unexpected"),
        _test_end("c.spec.ts:1:1", status="timedOut", outcome="unexpected"),
        _test_end("d.spec.ts:1:1", status="skipped", outcome="skipped"),
        _test_end("e.spec.ts:1:1", status="interrupted", outcome="unexpected"),
        _test_end("f.spec.ts:1:1", status="passed", outcome="flaky"),
        _run_end(
            _totals(
                expected=1, unexpected=3, flaky=1, skipped=1, interrupted=1, timedOut=1
            ),
            run_status="failed",
            exit_code=1,
        ),
    ]
    response = _ingest(testing_context, worker, attempt, events, exit_code=1)
    assert response.status_code == 200, response.text
    detail = response.json()
    stored = {case["test_id"]: case for case in detail["cases"]}
    assert stored["a.spec.ts:1:1"]["status"] == "passed"
    assert stored["b.spec.ts:1:1"]["status"] == "failed"
    assert stored["c.spec.ts:1:1"]["status"] == "timedOut"
    assert stored["d.spec.ts:1:1"]["status"] == "skipped"
    assert stored["e.spec.ts:1:1"]["status"] == "interrupted"
    assert stored["f.spec.ts:1:1"]["outcome"] == "flaky"
    assert detail["totals"] == _totals(
        expected=1, unexpected=3, flaky=1, skipped=1, interrupted=1, timedOut=1
    )


def test_flaky_and_skipped_do_not_prevent_a_passed_validation_but_stay_visible(
    testing_context,
):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("a.spec.ts:1:1"),
        _test_end("b.spec.ts:1:1", status="passed", outcome="flaky"),
        _test_end("c.spec.ts:1:1", status="skipped", outcome="skipped"),
        _run_end(_totals(expected=1, flaky=1, skipped=1)),
    ]
    response = _ingest(testing_context, worker, attempt, events)
    assert response.status_code == 200, response.text
    assert response.json()["totals"]["flaky"] == 1
    assert response.json()["totals"]["skipped"] == 1

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "passed"
        assert "instable" in run.technical_validation["summary"]
        assert "ignoré" in run.technical_validation["summary"]


def test_a_report_without_any_case_fails_with_the_no_assertion_reason(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    response = _ingest(
        testing_context, worker, attempt, [_run_begin(), _run_end(_totals())]
    )
    assert response.status_code == 200, response.text
    assert response.json()["case_count"] == 0

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "aucune assertion exécutée" in run.technical_validation["summary"]


def test_a_non_zero_exit_code_fails_even_when_every_case_passed(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("a.spec.ts:1:1"),
        _run_end(_totals(expected=1), run_status="failed", exit_code=3),
    ]
    response = _ingest(testing_context, worker, attempt, events, exit_code=3)
    assert response.status_code == 200, response.text
    assert response.json()["exit_code"] == 3

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "3" in run.technical_validation["summary"]


def test_a_report_that_under_reports_its_failures_never_passes(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected"),
        # Totaux mensongers : le reporter annonce zéro échec.
        _run_end(_totals(expected=1), run_status="completed", exit_code=0),
    ]
    response = _ingest(testing_context, worker, attempt, events)
    assert response.status_code == 200, response.text
    assert response.json()["totals"]["unexpected"] >= 1

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"


def test_a_retried_test_that_finally_passes_is_flaky_and_not_a_failure(testing_context):
    """Playwright émet une ligne par tentative : seule la dernière décide du verdict."""

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        # Première tentative rouge, puis reprise verte : le test est instable.
        _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected", attempt=1),
        _test_end("a.spec.ts:1:1", status="passed", outcome="flaky", attempt=2),
        _run_end(_totals(flaky=1)),
    ]
    response = _ingest(testing_context, worker, attempt, events)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["case_count"] == 2
    assert detail["totals"]["flaky"] == 1
    assert detail["totals"]["unexpected"] == 0

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "passed"


def test_a_retried_test_that_stays_red_is_still_counted_as_unexpected(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected", attempt=1),
        _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected", attempt=2),
        # Totaux mensongers : la reprise n'a pas sauvé le test.
        _run_end(_totals(flaky=1)),
    ]
    response = _ingest(testing_context, worker, attempt, events)
    assert response.status_code == 200, response.text
    assert response.json()["totals"]["unexpected"] == 1

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"


def test_a_partial_ingestion_leaves_the_validation_pending_until_the_run_ends(
    testing_context,
):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    partial = _ingest(
        testing_context,
        worker,
        attempt,
        [_run_begin(), _test_end("a.spec.ts:1:1")],
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "running"
    assert partial.json()["finished_at"] is None

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation.get("status") == "pending"

    completed = _ingest(
        testing_context,
        worker,
        attempt,
        [_test_end("b.spec.ts:1:1"), _run_end(_totals(expected=2))],
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["case_count"] == 2

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "passed"

    types = _event_types(testing_context, attempt["run_id"])
    assert types.count("test.run.started") == 1
    assert types.count("test.case.finished") == 2
    assert types.count("test.run.finished") == 1


def test_an_interrupted_run_never_passes(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _test_end("b.spec.ts:1:1", status="interrupted", outcome="unexpected"),
            _run_end(
                _totals(expected=1, interrupted=1),
                run_status="interrupted",
                exit_code=130,
            ),
        ],
        exit_code=130,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "interrupted"

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "interrompu" in run.technical_validation["summary"]


def test_a_fencing_token_ahead_of_the_attempt_is_accepted(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    response = _ingest(
        testing_context,
        worker,
        attempt,
        _green_report(),
        fencing_token=attempt["fencing_token"] + 1,
    )
    assert response.status_code == 200, response.text


def test_a_reporter_error_is_kept_without_hiding_the_verdict(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            {"kind": "error", "message": "configuration Playwright illisible"},
            _run_end(_totals(), run_status="failed", exit_code=1),
        ],
        exit_code=1,
    )
    assert response.status_code == 200, response.text
    assert response.json()["config"]["reporter_errors"] == [
        "configuration Playwright illisible"
    ]

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "aucune assertion exécutée" in run.technical_validation["summary"]


def test_a_green_report_sent_after_a_red_one_never_erases_the_failure(testing_context):
    """Une seconde ingestion ne repeint pas en vert des cas rouges déjà enregistrés."""

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    red = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected"),
            _run_end(_totals(unexpected=1), run_status="failed", exit_code=1),
        ],
        exit_code=1,
    )
    assert red.status_code == 200, red.text

    green = _ingest(
        testing_context,
        worker,
        attempt,
        [_run_end(_totals(expected=1), run_status="completed", exit_code=0)],
        exit_code=0,
    )
    assert green.status_code == 200, green.text
    assert green.json()["totals"]["unexpected"] == 1

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"


def test_a_second_run_end_never_lowers_a_non_zero_exit_code(testing_context):
    """Un échec porté par le seul code de sortie ne redevient jamais vert.

    Tous les cas sont verts : l'échec vient du processus lui-même (teardown global,
    erreur de configuration, plantage après les assertions). Aucune ligne rouge ne
    protège donc le verdict — c'est le code de sortie qui doit résister à un second
    ``run_end`` annonçant ``0``.
    """

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    red = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _run_end(_totals(expected=1), run_status="failed", exit_code=7),
        ],
        exit_code=7,
    )
    assert red.status_code == 200, red.text
    assert red.json()["exit_code"] == 7

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"

    green = _ingest(
        testing_context,
        worker,
        attempt,
        [_run_end(_totals(expected=1), run_status="completed", exit_code=0)],
        exit_code=0,
    )
    assert green.status_code == 200, green.text
    assert green.json()["exit_code"] == 7
    assert green.json()["status"] == "failed"

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "7" in run.technical_validation["summary"]


def test_a_reported_exit_code_never_erases_the_one_the_worker_measured(testing_context):
    """Le code de sortie mesuré par le worker fait foi dès la première ingestion.

    Le processus de test reçoit ``ACP_REPORT_FILE`` : n'importe quelle ligne NDJSON
    qu'il ajoute lui-même annoncerait ``exit_code=0``. Si cette valeur écrasait celle
    du worker, une suite réellement sortie en ``1`` obtiendrait une validation
    technique verte — exactement ce que ``_merged_totals`` interdit déjà pour les
    compteurs bloquants.
    """

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)

    forged = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _run_end(_totals(expected=1), run_status="completed", exit_code=0),
        ],
        exit_code=1,
    )

    assert forged.status_code == 200, forged.text
    assert forged.json()["exit_code"] == 1
    assert forged.json()["status"] == "failed"

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"
        assert "1" in run.technical_validation["summary"]


def test_a_reported_failure_still_raises_a_zero_exit_code(testing_context):
    """Dans l'autre sens, le rapport peut toujours **signaler** un échec.

    Le contrôle est asymétrique par construction : il empêche d'effacer un échec,
    jamais d'en déclarer un.
    """

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)

    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _run_end(_totals(expected=1), run_status="failed", exit_code=9),
        ],
        exit_code=0,
    )

    assert response.status_code == 200, response.text
    assert response.json()["exit_code"] == 9
    assert response.json()["status"] == "failed"


def test_a_run_end_claiming_to_be_running_still_closes_the_run(testing_context):
    """Un ``run_end`` termine l'exécution, quoi qu'annonce le reporter.

    Sans cela, un reporter modifié étoufferait un échec en laissant l'exécution
    « en cours » : aucune validation technique ne serait écrite et la tentative
    resterait au neutre ``pending``.
    """

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1", status="failed", outcome="unexpected"),
            _run_end(_totals(unexpected=1), run_status="running", exit_code=1),
        ],
        exit_code=1,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert response.json()["finished_at"] is not None

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"

    types = _event_types(testing_context, attempt["run_id"])
    assert types.count("test.run.finished") == 1


def test_a_batch_without_run_end_keeps_the_reported_counters(testing_context):
    """Un lot de rattrapage n'efface pas les totaux annoncés par le rapport.

    ``flaky`` n'est connu que du rapport : recalculer les totaux à partir des seules
    lignes enregistrées le ramènerait silencieusement à ce que les ``outcome``
    montrent, donc le perdrait.
    """

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    first = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _test_end("b.spec.ts:1:1", outcome="flaky"),
            _test_end("c.spec.ts:1:1", status="skipped", outcome="skipped"),
            _run_end(_totals(expected=1, flaky=3, skipped=1)),
        ],
    )
    assert first.status_code == 200, first.text
    assert first.json()["totals"]["flaky"] == 3

    late = _ingest(testing_context, worker, attempt, [_test_end("d.spec.ts:1:1")])
    assert late.status_code == 200, late.text
    totals = late.json()["totals"]
    assert totals["flaky"] == 3
    assert totals["skipped"] == 1
    assert totals["expected"] == 1
    assert late.json()["case_count"] == 4


def test_a_verdict_that_changes_republishes_the_run_finished_event(testing_context):
    """Le journal ne peut pas contredire la validation technique enregistrée."""

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    assert _ingest(testing_context, worker, attempt, _green_report()).status_code == 200

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "passed"

    red = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _test_end("b.spec.ts:1:1", status="failed", outcome="unexpected"),
            _run_end(
                _totals(expected=1, unexpected=1), run_status="failed", exit_code=1
            ),
        ],
        exit_code=1,
    )
    assert red.status_code == 200, red.text

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "failed"

    types = _event_types(testing_context, attempt["run_id"])
    assert types.count("test.run.finished") == 2

    with testing_context["session_factory"]() as db:
        finished = (
            db.query(EventModel)
            .filter_by(task_run_id=attempt["run_id"], type="test.run.finished")
            .order_by(EventModel.sequence)
            .all()
        )
        assert [row.payload["technical_validation"] for row in finished] == [
            "passed",
            "failed",
        ]
        assert finished[-1].payload["exit_code"] == 1


def test_no_ingestion_path_ever_marks_the_attempt_succeeded(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    assert _ingest(testing_context, worker, attempt, _green_report()).status_code == 200

    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        assert run.technical_validation["status"] == "passed"
        assert run.status != "succeeded"
        assert run.user_acceptance.get("status") == "pending"
        assert run.finished_at is None


# --- Refus --------------------------------------------------------------------


def test_a_stale_fencing_token_is_refused(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    with testing_context["session_factory"]() as db:
        run = db.get(TaskRunModel, attempt["run_id"])
        run.fencing_token = attempt["fencing_token"] + 4
        db.commit()

    refused = _ingest(testing_context, worker, attempt, _green_report())
    assert refused.status_code == 409, refused.text

    with testing_context["session_factory"]() as db:
        assert (
            db.query(TestRunModel).filter_by(task_run_id=attempt["run_id"]).count() == 0
        )


def test_an_ingestion_without_an_active_lease_is_refused(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    with testing_context["session_factory"]() as db:
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=attempt["run_id"]).one()
        lease.status = "released"
        db.commit()

    refused = _ingest(testing_context, worker, attempt, _green_report())
    assert refused.status_code == 409, refused.text


def test_an_expired_lease_is_refused(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    with testing_context["session_factory"]() as db:
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=attempt["run_id"]).one()
        lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()

    refused = _ingest(testing_context, worker, attempt, _green_report())
    assert refused.status_code == 409, refused.text


def test_a_worker_of_another_run_cannot_ingest(testing_context):
    first_worker = _register_worker(testing_context, name="worker-a")
    second_worker = _register_worker(testing_context, name="worker-b")
    first_attempt = _start_attempt(testing_context, first_worker, title="Mission A")
    _start_attempt(testing_context, second_worker, title="Mission B")

    refused = _ingest(testing_context, second_worker, first_attempt, _green_report())
    assert refused.status_code == 409, refused.text

    with testing_context["session_factory"]() as db:
        assert db.query(TestRunModel).count() == 0


def test_an_unauthenticated_or_mismatched_worker_is_refused(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    client = testing_context["client"]
    body = {
        "task_run_id": attempt["run_id"],
        "fencing_token": attempt["fencing_token"],
        "runner": "playwright",
        "events": _green_report(),
    }
    anonymous = client.post(f"/workers/{worker['worker_id']}/test-runs", json=body)
    assert anonymous.status_code == 401, anonymous.text

    wrong_token = client.post(
        f"/workers/{worker['worker_id']}/test-runs",
        headers={
            "Authorization": "Bearer jeton-invalide",
            "X-Worker-Id": worker["worker_id"],
        },
        json=body,
    )
    assert wrong_token.status_code == 401, wrong_token.text

    mismatched = client.post(
        f"/workers/{worker['worker_id']}/test-runs",
        headers={
            "Authorization": f"Bearer {worker['token']}",
            "X-Worker-Id": "un-autre-worker",
        },
        json=body,
    )
    assert mismatched.status_code == 401, mismatched.text


def test_an_unknown_attempt_is_refused(testing_context):
    worker = _register_worker(testing_context)
    _start_attempt(testing_context, worker)
    refused = _ingest(
        testing_context,
        worker,
        {"run_id": str(uuid4()), "fencing_token": 1},
        _green_report(),
    )
    assert refused.status_code in (404, 409), refused.text


# --- Pièces jointes et rapport -------------------------------------------------


def test_attachments_are_linked_by_their_sha256_and_never_carry_content(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    digest = "a" * 64
    with testing_context["session_factory"]() as db:
        artifact = ArtifactModel(
            project_id=testing_context["project_id"],
            task_run_id=attempt["run_id"],
            worker_id=worker["worker_id"],
            kind="test-artifact",
            path="interne/ne-doit-pas-fuiter.png",
            checksum=digest,
            size_bytes=2048,
            storage_key=f"{digest[:2]}/{digest}",
            content_type="image/png",
            original_name="echec-1.png",
            source="playwright",
            stream_kind="screenshot",
        )
        db.add(artifact)
        db.commit()
        artifact_id = artifact.id

    events = [
        _run_begin(),
        _test_end(
            "a.spec.ts:1:1",
            status="failed",
            outcome="unexpected",
            attachments=[
                {
                    "name": "screenshot",
                    "content_type": "image/png",
                    "path": "test-results/a/echec-1.png",
                    "sha256": digest,
                    "size_bytes": 2048,
                }
            ],
        ),
        _run_end(_totals(unexpected=1), run_status="failed", exit_code=1),
    ]
    response = _ingest(testing_context, worker, attempt, events, exit_code=1)
    assert response.status_code == 200, response.text
    attachments = response.json()["cases"][0]["attachments"]
    assert [item["id"] for item in attachments] == [artifact_id]
    assert attachments[0]["has_content"] is True
    assert "storage_key" not in attachments[0]
    assert "path" not in attachments[0]
    assert "ne-doit-pas-fuiter" not in response.text


def test_an_unknown_attachment_digest_is_ignored_without_failing_the_ingestion(
    testing_context,
):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    events = [
        _run_begin(),
        _test_end(
            "a.spec.ts:1:1",
            attachments=[
                {
                    "content_type": "image/png",
                    "path": "test-results/a/inconnu.png",
                    "sha256": "b" * 64,
                    "size_bytes": 10,
                }
            ],
        ),
        _run_end(_totals(expected=1)),
    ]
    response = _ingest(testing_context, worker, attempt, events)
    assert response.status_code == 200, response.text
    assert response.json()["cases"][0]["attachments"] == []


def test_the_html_report_artifact_is_attached_to_the_run(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    digest = "c" * 64
    with testing_context["session_factory"]() as db:
        report = ArtifactModel(
            project_id=testing_context["project_id"],
            task_run_id=attempt["run_id"],
            worker_id=worker["worker_id"],
            kind="test-report",
            path="interne/rapport.zip",
            checksum=digest,
            size_bytes=4096,
            storage_key=f"{digest[:2]}/{digest}",
            content_type="application/zip",
            original_name="playwright-report/index.html",
            source="playwright",
            stream_kind="report",
        )
        db.add(report)
        db.commit()
        report_id = report.id

    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("a.spec.ts:1:1"),
            _run_end(_totals(expected=1), report_path="playwright-report/index.html"),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["report_artifact"]["id"] == report_id


# --- Contenu non fiable --------------------------------------------------------


def test_a_case_error_message_is_bounded_and_never_served_as_html(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    hostile = "<script>alert('xss')</script><img src=x onerror=alert(1)>"
    response = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end(
                "a.spec.ts:1:1",
                status="failed",
                outcome="unexpected",
                error_message=hostile,
                error_snippet="x" * 8000,
            ),
            _run_end(_totals(unexpected=1), run_status="failed", exit_code=1),
        ],
        exit_code=1,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    case = response.json()["cases"][0]
    assert case["error_message"] == hostile
    assert len(case["error_snippet"]) == 8000

    too_long = _ingest(
        testing_context,
        worker,
        attempt,
        [
            _run_begin(),
            _test_end("b.spec.ts:1:1", error_message="y" * 8001),
            _run_end(_totals(expected=1)),
        ],
    )
    assert too_long.status_code == 422, too_long.text


def test_the_test_events_wake_an_already_connected_stream(testing_context):
    """Un abonné SSE déjà connecté est réveillé sans attendre une réconciliation."""

    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    run_queue = events_bus.event_hub.subscribe(events_bus.run_channel(attempt["run_id"]))
    project_queue = events_bus.event_hub.subscribe(
        events_bus.project_channel(testing_context["project_id"])
    )
    try:
        assert _ingest(testing_context, worker, attempt, _green_report()).status_code == 200
        awakened = _drain(run_queue)
        # run.started, case.finished, run.finished — dans l'ordre des séquences.
        assert len(awakened) == 3
        assert awakened == sorted(awakened)
        assert len(_drain(project_queue)) == 3
    finally:
        events_bus.event_hub.unsubscribe(
            events_bus.run_channel(attempt["run_id"]), run_queue
        )
        events_bus.event_hub.unsubscribe(
            events_bus.project_channel(testing_context["project_id"]), project_queue
        )


def test_an_event_payload_carries_only_artifact_references(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    digest = "d" * 64
    with testing_context["session_factory"]() as db:
        db.add(
            ArtifactModel(
                project_id=testing_context["project_id"],
                task_run_id=attempt["run_id"],
                worker_id=worker["worker_id"],
                kind="test-artifact",
                path="interne/video.webm",
                checksum=digest,
                size_bytes=999,
                storage_key=f"{digest[:2]}/{digest}",
                content_type="video/webm",
                original_name="video.webm",
                source="playwright",
                stream_kind="video",
            )
        )
        db.commit()

    events = [
        _run_begin(),
        _test_end(
            "a.spec.ts:1:1",
            attachments=[
                {
                    "content_type": "video/webm",
                    "path": "test-results/a/video.webm",
                    "sha256": digest,
                    "size_bytes": 999,
                }
            ],
        ),
        _run_end(_totals(expected=1)),
    ]
    assert _ingest(testing_context, worker, attempt, events).status_code == 200

    with testing_context["session_factory"]() as db:
        case_event = (
            db.query(EventModel)
            .filter_by(task_run_id=attempt["run_id"], type="test.case.finished")
            .one()
        )
        attachment = case_event.payload["attachments"][0]
        assert attachment["sha256"] == digest
        assert attachment["content_type"] == "video/webm"
        assert "content" not in attachment
        assert "base64" not in str(case_event.payload).lower()
        assert case_event.sequence is not None
        assert case_event.executor == "playwright"
        assert case_event.emitted_by == "worker"


# --- Dérivation pure -----------------------------------------------------------


def _summary(**overrides):
    values = {
        "id": "tr-1",
        "task_run_id": "run-1",
        "project_id": "proj-1",
        "runner": "playwright",
        "status": "completed",
        "started_at": datetime(2026, 9, 12, 10, tzinfo=timezone.utc),
        "totals": TestTotals(),
        "exit_code": 0,
        "case_count": 0,
    }
    values.update(overrides)
    return TestRunSummary(**values)


@pytest.mark.parametrize(
    ("totals", "exit_code", "case_count", "expected_status", "expected_fragment"),
    [
        (TestTotals(expected=3), 0, 3, "passed", "3 attendus"),
        (TestTotals(expected=2, flaky=1), 0, 3, "passed", "instable"),
        (TestTotals(expected=2, skipped=1), 0, 3, "passed", "ignoré"),
        (TestTotals(expected=2, flaky=1, skipped=4), 0, 7, "passed", "ignoré"),
        (TestTotals(), 0, 0, "failed", "aucune assertion exécutée"),
        (TestTotals(expected=3), 0, 0, "failed", "aucune assertion exécutée"),
        (TestTotals(expected=3), 1, 3, "failed", "code de sortie"),
        (TestTotals(expected=3), None, 3, "failed", "code de sortie"),
        (TestTotals(expected=2, unexpected=1), 0, 3, "failed", "inattendu"),
        (TestTotals(expected=2, interrupted=1), 0, 3, "failed", "interrompu"),
        (TestTotals(expected=2, timedOut=1), 0, 3, "failed", "délai"),
        (TestTotals(unexpected=2, timedOut=1), 5, 3, "failed", "inattendu"),
    ],
)
def test_the_derivation_covers_every_combination(
    totals, exit_code, case_count, expected_status, expected_fragment
):
    status, summary = derive_technical_validation(
        _summary(totals=totals, exit_code=exit_code, case_count=case_count)
    )
    assert status == expected_status
    assert expected_fragment in summary
    assert status in {"passed", "failed"}


def test_the_derivation_never_returns_succeeded():
    for exit_code in (0, 1, None):
        for case_count in (0, 1):
            status, _ = derive_technical_validation(
                _summary(exit_code=exit_code, case_count=case_count)
            )
            assert status != "succeeded"


def test_the_summary_always_lists_the_six_counters():
    _, summary = derive_technical_validation(
        _summary(totals=TestTotals(expected=1), case_count=1)
    )
    for fragment in (
        "attendu",
        "inattendu",
        "instable",
        "ignoré",
        "interrompu",
        "délai",
    ):
        assert fragment in summary


# --- Lectures ------------------------------------------------------------------


def test_the_run_is_readable_by_attempt_and_by_identifier(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    ingested = _ingest(testing_context, worker, attempt, _green_report())
    assert ingested.status_code == 200, ingested.text
    test_run_id = ingested.json()["id"]

    _restore_owner(testing_context)
    client = testing_context["client"]
    by_attempt = client.get(f"/runs/{attempt['run_id']}/test-run")
    assert by_attempt.status_code == 200, by_attempt.text
    assert by_attempt.json()["id"] == test_run_id
    assert by_attempt.json()["cases"][0]["test_id"] == "panier.spec.ts:12:3"

    by_id = client.get(f"/test-runs/{test_run_id}")
    assert by_id.status_code == 200, by_id.text
    assert by_id.json()["task_run_id"] == attempt["run_id"]


def test_an_attempt_without_a_test_run_answers_an_explicit_404(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    _restore_owner(testing_context)
    missing = testing_context["client"].get(f"/runs/{attempt['run_id']}/test-run")
    assert missing.status_code == 404, missing.text
    assert "exécution de tests" in missing.json()["detail"].lower()

    unknown = testing_context["client"].get(f"/test-runs/{uuid4()}")
    assert unknown.status_code == 404, unknown.text


def test_the_reads_are_closed_without_a_session(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    ingested = _ingest(testing_context, worker, attempt, _green_report())
    assert ingested.status_code == 200
    test_run_id = ingested.json()["id"]

    client = testing_context["client"]
    client.cookies.clear()
    assert client.get(f"/runs/{attempt['run_id']}/test-run").status_code == 401
    assert client.get(f"/test-runs/{test_run_id}").status_code == 401


def test_a_member_of_another_project_cannot_read_the_test_run(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    ingested = _ingest(testing_context, worker, attempt, _green_report())
    assert ingested.status_code == 200
    test_run_id = ingested.json()["id"]

    _restore_owner(testing_context)
    other_project = testing_context["client"].post(
        "/projects",
        json={
            "workspace_id": testing_context["workspace_id"],
            "name": "Projet voisin",
        },
    )
    assert other_project.status_code == 200, other_project.text
    session_token, csrf_token = _member_session(
        testing_context, project_ids=[other_project.json()["id"]]
    )
    _authenticate(testing_context, session_token, csrf_token)

    assert (
        testing_context["client"].get(f"/runs/{attempt['run_id']}/test-run").status_code
        == 403
    )
    assert testing_context["client"].get(f"/test-runs/{test_run_id}").status_code == 403


def test_a_member_of_the_project_reads_the_test_run(testing_context):
    worker = _register_worker(testing_context)
    attempt = _start_attempt(testing_context, worker)
    ingested = _ingest(testing_context, worker, attempt, _green_report())
    assert ingested.status_code == 200
    test_run_id = ingested.json()["id"]

    session_token, csrf_token = _member_session(
        testing_context, project_ids=[testing_context["project_id"]]
    )
    _authenticate(testing_context, session_token, csrf_token)
    assert (
        testing_context["client"].get(f"/runs/{attempt['run_id']}/test-run").status_code
        == 200
    )
    assert testing_context["client"].get(f"/test-runs/{test_run_id}").status_code == 200
