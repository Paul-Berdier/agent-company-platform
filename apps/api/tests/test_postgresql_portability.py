"""Portabilité PostgreSQL de l'API (Lot H2b) : missions, distribution du travail, probes.

Chaque test isole un défaut démontré par le balayage PostgreSQL : un prédicat
``json = json`` que PostgreSQL ne sait pas évaluer, un ``FOR UPDATE SKIP LOCKED``
qui privait le second worker de toute tâche, des mutations ORM depuis une lecture
périmée, un ``IntegrityError`` rendu en 500, un diagnostic HTTP qui gardait sa
transaction ouverte pendant l'appel réseau, des chemins de stockage absolus.

Sans ``ACP_TEST_DATABASE_URL``, la fabrique ``make_test_engine`` rend un fichier
SQLite : les tests non marqués y tournent et y observent la même sémantique.
Avec la variable, ils tournent sur un schéma PostgreSQL éphémère. Les tests
``postgres`` n'existent que là où seul PostgreSQL exerce le défaut ; ils sont
ignorés sans base configurée et échouent si ``ACP_TEST_DATABASE_REQUIRED=1``.
"""

from __future__ import annotations

import json
import shutil
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from acp_api import events_bus
from acp_api.attempt_fencing import _lock_run
from acp_api.deps import get_db
from acp_api.main import app
from acp_api.mcp import service as mcp_service
from acp_api.routers import artifacts as artifacts_router
from acp_api.routers import mcp as mcp_router
from acp_api.routers import missions as missions_router
from acp_api.routers import operations as operations_router
from acp_api.routers import work as work_router
from acp_api.routers import workers as workers_router
from acp_api.routers.workers import expire_task_leases
from acp_api.secrets_vault import generate_key
from acp_api.skills import service as skills_service
from acp_database.models import (
    ArtifactModel,
    EventModel,
    McpProbeModel,
    McpServerModel,
    McpServerRevisionModel,
    ResourceLockModel,
    SkillRevisionModel,
    TaskModel,
    TaskRunModel,
    TestRunModel,
    WorkerLeaseModel,
    WorkerModel,
)
from acp_database.testing import (
    make_test_engine,
    point_global_engine_at,
    skip_or_fail_without_postgresql,
)

PASSWORD = "correct horse battery staple"
PUBLIC_IP = "93.184.216.34"


# --- Fabrique d'application -----------------------------------------------------


class _FakeMcpServer:
    """Serveur MCP HTTP simulé ; ``hooks`` s'exécutent à chaque requête reçue."""

    def __init__(self) -> None:
        self.hooks: list = []
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for hook in list(self.hooks):
            hook(request)
        if request.method == "DELETE":
            return httpx.Response(200)
        payload = json.loads(request.content)
        method = payload.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "portability-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "portability-fake", "version": "0.1"},
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "search",
                                "description": "Recherche",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )
        return httpx.Response(400)


def _fake_resolver(host, port=None, *args, **kwargs):
    if host != "mcp.example":
        raise socket.gaierror(-2, "Name or service not known")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port or 0))]


@pytest.fixture
def portability_context(monkeypatch, tmp_path):
    """Application complète sur le moteur de ``make_test_engine`` (SQLite ou PostgreSQL).

    Le ``lifespan`` appelle ``init_db()`` sur ``ACP_DATABASE_URL`` : cette variable
    est pointée sur un fichier SQLite jetable, indépendant du moteur de test qui,
    lui, sert les routes via ``get_db``.
    """

    bootstrap_token = f"bootstrap-{uuid4().hex}"
    registration_token = f"registration-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", registration_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("ACP_ARTIFACT_STORAGE_DIR", str(tmp_path / "blobs"))
    monkeypatch.delenv("ACP_OUTBOUND_PRIVATE_ALLOWLIST", raising=False)
    monkeypatch.delenv("ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP", raising=False)
    point_global_engine_at(
        monkeypatch, f"sqlite:///{(tmp_path / 'lifespan.db').as_posix()}"
    )
    database = make_test_engine(tmp_path, concurrent=True)
    session_factory = sessionmaker(bind=database.engine, expire_on_commit=False)
    fake = _FakeMcpServer()

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[mcp_router.get_dns_resolver] = lambda: _fake_resolver
    app.dependency_overrides[mcp_router.get_http_transport] = lambda: httpx.MockTransport(
        fake.handle
    )
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": f"owner-{uuid4().hex}",
                    "display_name": "Propriétaire portabilité",
                    "password": PASSWORD,
                },
            )
            assert bootstrap.status_code == 201, bootstrap.text
            client.headers["X-CSRF-Token"] = bootstrap.json()["csrf_token"]
            organization = client.post("/organizations", json={"name": "Org H2b"}).json()
            workspace = client.post(
                "/workspaces",
                json={"organization_id": organization["id"], "name": "Ws H2b"},
            ).json()
            project = client.post(
                "/projects", json={"workspace_id": workspace["id"], "name": "Projet H2b"}
            ).json()
            monkeypatch.setenv("ACP_WORKER_REGISTRATION_PROJECT_ID", project["id"])
            monkeypatch.setenv("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS", "0")

            def agent(name: str) -> str:
                response = client.post(
                    "/agents",
                    json={
                        "workspace_id": workspace["id"],
                        "name": name,
                        "role_id": "developer",
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()["id"]

            def register(
                name: str,
                capabilities: list[str] | None = None,
                *,
                max_concurrency: int = 1,
            ) -> dict:
                response = client.post(
                    "/workers/register",
                    headers={"X-Worker-Registration-Token": registration_token},
                    json={
                        "name": f"{name}-{uuid4().hex[:6]}",
                        "capabilities": capabilities or ["git", "mcp_stdio_probe"],
                        "max_concurrency": max_concurrency,
                        "simulation": False,
                        "project_id": project["id"],
                        "global_access": False,
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()

            context = {
                "client": client,
                "session_factory": session_factory,
                "backend": database.backend,
                "project_id": project["id"],
                "workspace_id": workspace["id"],
                "agent_id": agent("Agent H2b"),
                "new_agent": agent,
                "register": register,
                "fake": fake,
                "storage": tmp_path / "skills",
                "tmp_path": tmp_path,
            }
            context["worker"] = register("worker-h2b")
            yield context
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(mcp_router.get_dns_resolver, None)
        app.dependency_overrides.pop(mcp_router.get_http_transport, None)
        database.close()


@pytest.fixture
def _require_postgresql():
    return skip_or_fail_without_postgresql()


@pytest.fixture
def postgresql_context(_require_postgresql, portability_context):
    """Même application, mais uniquement quand PostgreSQL est la base de test."""

    assert portability_context["backend"] == "postgresql"
    return portability_context


# --- Aides --------------------------------------------------------------------


def _worker_auth(worker: dict, *, fencing_token: int | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {worker['token']}",
        "X-Worker-Id": worker["worker_id"],
    }
    if fencing_token is not None:
        headers["X-Attempt-Fencing-Token"] = str(fencing_token)
    return headers


def _claim(context, worker: dict | None = None) -> dict:
    worker = worker or context["worker"]
    response = context["client"].post(
        f"/workers/{worker['worker_id']}/claim",
        headers={"Authorization": f"Bearer {worker['token']}"},
        json={"provider_id": "mock"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _queue_task(context, title: str, *, agent_id: str | None = None) -> dict:
    client = context["client"]
    task = client.post(
        "/tasks",
        json={
            "project_id": context["project_id"],
            "agent_instance_id": agent_id or context["agent_id"],
            "title": title,
            "meta": {"required_capabilities": ["git"]},
        },
    )
    assert task.status_code == 200, task.text
    queued = client.post(f"/tasks/{task.json()['id']}/queue")
    assert queued.status_code == 200, queued.text
    return queued.json()


def _create_mission(context, title: str) -> dict:
    response = context["client"].post(
        "/missions",
        headers={"Idempotency-Key": f"create-{uuid4().hex}"},
        json={
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
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _succeed_mission_attempt(context, run_id: str, fencing_token: int) -> None:
    client = context["client"]
    headers = _worker_auth(context["worker"], fencing_token=fencing_token)
    assert client.patch(
        f"/task-runs/{run_id}", headers=headers, json={"status": "running"}
    ).status_code == 200
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=headers,
        json={
            "technical_validation": {"status": "passed", "summary": "tests OK"},
            "evidence": [
                {
                    "kind": "test_run",
                    "summary": "Suite verte",
                    "command": "pytest -q",
                    "exit_code": 0,
                    "data": {"passed": 1},
                }
            ],
        },
    ).status_code == 200
    succeeded = client.patch(
        f"/task-runs/{run_id}", headers=headers, json={"status": "succeeded"}
    )
    assert succeeded.status_code == 200, succeeded.text


def _events_of_type(context, event_type: str, run_id: str) -> list[EventModel]:
    with context["session_factory"]() as db:
        return (
            db.query(EventModel)
            .filter_by(type=event_type, task_run_id=run_id)
            .all()
        )


# --- 1. Acceptation : compare-and-set portable ---------------------------------


def test_acceptance_decision_is_a_portable_compare_and_set(portability_context):
    """Le refus 409 vient d'un prédicat sur ``user_acceptance->>'status'``, jamais d'un 500."""

    context = portability_context
    client = context["client"]
    mission = _create_mission(context, "Mission acceptation")
    claim = _claim(context)
    run_id = claim["attempt_id"]
    _succeed_mission_attempt(context, run_id, claim["fencing_token"])
    acceptance_path = f"/missions/{mission['id']}/runs/{run_id}/acceptance"

    def decide(decision: str):
        return client.post(
            acceptance_path, json={"decision": decision, "comment": f"Décision {decision}"}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(decide, ("accepted", "rejected")))
    assert sorted(response.status_code for response in decisions) == [200, 409], [
        (response.status_code, response.text) for response in decisions
    ]
    winner = next(response for response in decisions if response.status_code == 200)
    winning = winner.json()["user_acceptance"]["status"]
    losing = "rejected" if winning == "accepted" else "accepted"
    assert decide(winning).status_code == 200
    contradiction = decide(losing)
    assert contradiction.status_code == 409
    assert contradiction.json()["detail"] == "Acceptation déjà décidée"
    with context["session_factory"]() as db:
        run = db.get(TaskRunModel, run_id)
        assert run.user_acceptance["status"] == winning
        assert db.get(TaskModel, mission["id"]).status == (
            "done" if winning == "accepted" else "blocked"
        )


# --- 2. Distribution du travail ------------------------------------------------


@pytest.mark.postgres
@pytest.mark.concurrency
def test_two_workers_claiming_concurrently_each_obtain_a_task(postgresql_context):
    """Le premier worker ne verrouille plus tous les candidats du second.

    Le worker A est suspendu au milieu de sa transaction de claim (dans ``utcnow``,
    appelé après la réservation de sa tâche) le temps que B réclame : B doit
    obtenir l'autre tâche, pas « aucune tâche compatible ». La fenêtre est bornée
    car, sans ``FOR UPDATE``, B attend le commit de A sur la ligne de la première
    tâche avant de passer à la seconde.
    """

    context = postgresql_context
    client = context["client"]
    worker_a = context["worker"]
    worker_b = context["register"]("worker-b")
    first = _queue_task(context, "Tâche 1")
    second = _queue_task(context, "Tâche 2", agent_id=context["new_agent"]("Agent B"))
    real_utcnow = work_router.utcnow
    a_inside = threading.Event()
    b_done = threading.Event()
    paused = {"count": 0}

    def pausing_utcnow():
        if paused["count"] == 0:
            paused["count"] += 1
            a_inside.set()
            b_done.wait(2)
        return real_utcnow()

    results: dict[str, dict] = {}

    def claim_b():
        assert a_inside.wait(15)
        try:
            results["b"] = _claim(context, worker_b)
        finally:
            b_done.set()

    thread = threading.Thread(target=claim_b)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(work_router, "utcnow", pausing_utcnow)
            thread.start()
            results["a"] = _claim(context, worker_a)
    finally:
        b_done.set()
        thread.join(30)
    assert not thread.is_alive()
    assert results["a"]["task"] is not None, results["a"]
    assert results["b"]["task"] is not None, results["b"]
    assert {results["a"]["task"]["id"], results["b"]["task"]["id"]} == {
        first["id"],
        second["id"],
    }
    with context["session_factory"]() as db:
        assert db.get(WorkerModel, worker_a["worker_id"]).active_runs == 1
        assert db.get(WorkerModel, worker_b["worker_id"]).active_runs == 1
    assert client.post(
        f"/workers/{worker_a['worker_id']}/claim",
        headers={"Authorization": f"Bearer {worker_a['token']}"},
        json={},
    ).json()["reason"] == "capacité de concurrence atteinte"


def test_a_terminal_attempt_never_overwrites_a_concurrent_claim_counter(
    portability_context,
):
    """La fin d'une tentative ne doit pas écraser la réservation d'un claim concurrent.

    Le compteur ``active_runs`` arbitre l'admission d'un claim. Il était décrémenté
    depuis la valeur lue à l'authentification du worker : un claim validé entre
    cette lecture et l'écriture disparaissait, et le worker repassait sous sa
    capacité réelle — donc admettait des tentatives au-delà de ``max_concurrency``.
    Ici, le claim concurrent est déclenché pendant la requête terminale, après
    l'authentification.
    """

    context = portability_context
    client = context["client"]
    worker = context["worker"]
    first = _queue_task(context, "Tâche terminale")
    second = _queue_task(context, "Tâche concurrente", agent_id=context["new_agent"]("Agent 2"))
    with context["session_factory"]() as db:
        row = db.get(WorkerModel, worker["worker_id"])
        row.max_concurrency = 2
        db.commit()

    claimed = _claim(context)
    assert claimed["task"]["id"] == first["id"], claimed
    run_id = claimed["task_run"]["id"]
    fencing_token = claimed["fencing_token"]
    assert client.patch(
        f"/task-runs/{run_id}",
        headers=_worker_auth(worker, fencing_token=fencing_token),
        json={"status": "running"},
    ).status_code == 200

    # Le second claim s'exécute au milieu de la requête terminale, après que
    # celle-ci a lu la ligne du worker.
    real_authenticate = work_router.authenticate_worker
    injected = {"done": False}

    def authenticate_then_claim(db, worker_id, authorization):
        row = real_authenticate(db, worker_id, authorization)
        if not injected["done"]:
            injected["done"] = True
            injected["claim"] = _claim(context)
        return row

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(work_router, "authenticate_worker", authenticate_then_claim)
        terminal = client.patch(
            f"/task-runs/{run_id}",
            headers=_worker_auth(worker, fencing_token=fencing_token),
            json={"status": "failed", "result": {"summary": "échec attendu"}},
        )
    assert terminal.status_code == 200, terminal.text
    assert injected["claim"]["task"]["id"] == second["id"], injected["claim"]

    with context["session_factory"]() as db:
        stored = db.get(WorkerModel, worker["worker_id"]).active_runs
        active_leases = (
            db.query(WorkerLeaseModel)
            .filter_by(worker_id=worker["worker_id"], status="active")
            .count()
        )
    assert (stored, active_leases) == (1, 1), (
        f"compteur {stored} pour {active_leases} bail(s) actif(s) : la réservation "
        "du claim concurrent a été écrasée"
    )


def test_lease_renewal_is_refused_once_the_lease_is_no_longer_active(portability_context):
    """Le renouvellement est un compare-and-set : un bail fermé entre-temps n'est pas rouvert."""

    context = portability_context
    client = context["client"]
    _queue_task(context, "Tâche à renouveler")
    claim = _claim(context)
    run_id = claim["task_run"]["id"]
    worker = context["worker"]
    renew_path = f"/workers/{worker['worker_id']}/leases/{run_id}/renew"
    auth = {"Authorization": f"Bearer {worker['token']}"}

    before = client.post(renew_path, headers=auth)
    assert before.status_code == 200, before.text
    real_utcnow = work_router.utcnow
    closed = {"done": False}

    def closing_utcnow():
        if not closed["done"]:
            closed["done"] = True
            with context["session_factory"]() as db:
                db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).update(
                    {WorkerLeaseModel.status: "released"}, synchronize_session=False
                )
                db.commit()
        return real_utcnow()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(work_router, "utcnow", closing_utcnow)
        refused = client.post(renew_path, headers=auth)
    assert closed["done"]
    assert refused.status_code == 409, refused.text
    assert "renouvellement refusé" in refused.json()["detail"]
    with context["session_factory"]() as db:
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one()
        assert lease.status == "released"
        assert lease.last_renewed_at is not None


# --- 3. Expiration des baux et heartbeat ---------------------------------------


@pytest.mark.concurrency
def test_expiring_the_same_lease_twice_concurrently_interrupts_once(portability_context):
    """Deux expirations simultanées : une seule transition, un seul ``task.interrupted``."""

    context = portability_context
    _queue_task(context, "Tâche abandonnée")
    claim = _claim(context)
    run_id = claim["task_run"]["id"]
    with context["session_factory"]() as db:
        db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).update(
            {WorkerLeaseModel.lease_expires_at: datetime.now(timezone.utc) - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()

    barrier = Barrier(2)
    counts: list[int] = []
    failures: list[BaseException] = []

    def expire_once():
        try:
            with context["session_factory"]() as db:
                barrier.wait(10)
                counts.append(expire_task_leases(db))
        except BaseException as exc:  # pragma: no cover - diagnostic
            failures.append(exc)

    threads = [threading.Thread(target=expire_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not failures, failures
    assert sorted(counts) == [0, 1]
    assert len(_events_of_type(context, "task.interrupted", run_id)) == 1
    with context["session_factory"]() as db:
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one()
        assert lease.status == "expired"
        run = db.get(TaskRunModel, run_id)
        assert run.status == "interrupted"
        assert sum(1 for entry in run.logs if "Lease worker expiré" in entry["message"]) == 1
        assert db.get(TaskModel, run.task_id).status == "blocked"
        assert db.get(WorkerModel, context["worker"]["worker_id"]).active_runs == 0


def test_expiry_only_transitions_leases_already_expired(portability_context):
    """Un bail encore valide n'est ni relu ni touché : le filtre est dans le SQL."""

    context = portability_context
    _queue_task(context, "Tâche vivante")
    claim = _claim(context)
    run_id = claim["task_run"]["id"]
    with context["session_factory"]() as db:
        assert expire_task_leases(db) == 0
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one()
        assert lease.status == "active"
        assert db.get(TaskRunModel, run_id).status == "running"
    assert _events_of_type(context, "task.interrupted", run_id) == []


@pytest.mark.postgres
@pytest.mark.concurrency
def test_a_renewal_committed_during_the_expiry_keeps_the_lease(postgresql_context):
    """Le compare-and-set de l'expiration revérifie l'échéance (0.9.1).

    L'expiration lit un bail échu, puis attend le verrou de ligne d'un renouvellement
    en cours. Sous READ COMMITTED, PostgreSQL ne réévalue que le filtre de l'UPDATE
    sur la nouvelle version : sans l'échéance dans ce filtre, le bail tout juste
    renouvelé (200 rendu au worker) était expiré et la tentative interrompue.
    """

    context = postgresql_context
    _queue_task(context, "Tâche renouvelée à l'échéance")
    claim = _claim(context)
    run_id = claim["task_run"]["id"]
    now = datetime.now(timezone.utc)
    with context["session_factory"]() as db:
        db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).update(
            {WorkerLeaseModel.lease_expires_at: now - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()

    renewer = context["session_factory"]()
    renewer.query(WorkerLeaseModel).filter_by(task_run_id=run_id).update(
        {WorkerLeaseModel.lease_expires_at: now + timedelta(seconds=45)},
        synchronize_session=False,
    )
    counts: list[int] = []
    failures: list[BaseException] = []

    def expire_once():
        try:
            with context["session_factory"]() as db:
                counts.append(expire_task_leases(db))
        except BaseException as exc:  # pragma: no cover - diagnostic
            failures.append(exc)

    expiry = threading.Thread(target=expire_once)
    try:
        expiry.start()
        expiry.join(1.0)
        assert expiry.is_alive(), "l'expiration doit attendre le verrou du renouvellement"
        renewer.commit()
    finally:
        renewer.close()
    expiry.join(60)

    assert not failures, failures
    assert counts == [0]
    assert _events_of_type(context, "task.interrupted", run_id) == []
    with context["session_factory"]() as db:
        assert db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one().status == "active"
        assert db.get(TaskRunModel, run_id).status == "running"


@pytest.mark.postgres
@pytest.mark.concurrency
def test_expiring_a_lease_never_deadlocks_with_the_end_of_its_attempt(
    postgresql_context, monkeypatch
):
    """L'expiration verrouille la tentative avant le bail, comme la fin de tentative.

    Jusqu'en 0.9.0, ``expire_task_leases`` fermait le bail (verrou L) puis écrivait
    la tentative (R), quand ``PATCH /task-runs`` tenait R puis écrivait L : chacune
    attendait l'autre et PostgreSQL en annulait une (40P01). Ici, la fin de tentative
    est suspendue juste après avoir verrouillé R, le temps que l'expiration avance.
    """

    context = postgresql_context
    client = context["client"]
    _queue_task(context, "Tâche finie à l'échéance")
    run_id = _claim(context)["task_run"]["id"]
    now = datetime.now(timezone.utc)
    with context["session_factory"]() as db:
        db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).update(
            {WorkerLeaseModel.lease_expires_at: now - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()
    # Pour la fin de tentative, le bail est encore valide : elle lit son horloge
    # dans ``work`` ; l'expiration, dans ``workers``, le voit échu.
    monkeypatch.setattr(work_router, "utcnow", lambda: now - timedelta(minutes=10))

    completion_holds_run = threading.Event()
    expiry_holds_lease = threading.Event()
    real_compare_and_set = work_router._compare_and_set_run_status
    real_set_committed_value = workers_router.set_committed_value

    def compare_and_set_after_the_expiry(*args, **kwargs):
        completion_holds_run.set()
        # Ancien ordre : l'expiration ferme le bail pendant cette pause. Nouvel ordre :
        # elle attend la tentative, et la pause s'achève sur son délai.
        expiry_holds_lease.wait(2)
        return real_compare_and_set(*args, **kwargs)

    def lease_closed(*args, **kwargs):
        expiry_holds_lease.set()
        return real_set_committed_value(*args, **kwargs)

    monkeypatch.setattr(
        work_router, "_compare_and_set_run_status", compare_and_set_after_the_expiry
    )
    monkeypatch.setattr(workers_router, "set_committed_value", lease_closed)

    completion: dict = {}
    counts: list[int] = []
    failures: list[BaseException] = []

    def complete() -> None:
        completion["response"] = client.patch(
            f"/task-runs/{run_id}",
            headers=_worker_auth(context["worker"]),
            json={"status": "failed"},
        )

    def expire() -> None:
        try:
            with context["session_factory"]() as db:
                counts.append(expire_task_leases(db))
        except BaseException as exc:  # pragma: no cover - diagnostic
            failures.append(exc)

    finisher = threading.Thread(target=complete)
    finisher.start()
    assert completion_holds_run.wait(30), "la fin de tentative n'a pas verrouillé R"
    expiry = threading.Thread(target=expire)
    expiry.start()
    finisher.join(60)
    expiry.join(60)
    assert not finisher.is_alive() and not expiry.is_alive()

    assert not failures, failures
    assert completion["response"].status_code == 200, completion["response"].text
    # La fin de tentative a relâché le bail avant que l'expiration le lise : rien à
    # expirer, aucune interruption fantôme.
    assert counts == [0]
    assert _events_of_type(context, "task.interrupted", run_id) == []
    assert len(_events_of_type(context, "task.failed", run_id)) == 1
    with context["session_factory"]() as db:
        assert db.get(TaskRunModel, run_id).status == "failed"
        lease = db.query(WorkerLeaseModel).filter_by(task_run_id=run_id).one()
        assert lease.status == "released"


@pytest.mark.postgres
@pytest.mark.concurrency
def test_a_claim_never_deadlocks_with_the_stop_of_a_queued_mission(
    postgresql_context, monkeypatch
):
    """Le claim prend la tentative en file avant la tâche, comme l'arrêt (R3).

    Jusqu'en 0.9.0, le claim réservait la tâche T puis attendait la tentative R,
    qu'un arrêt tenait en attendant d'écrire T : interblocage (40P01). Le claim
    verrouille désormais R d'abord, en ``SKIP LOCKED`` : une tentative tenue par un
    arrêt est passée, et l'arrêt s'applique.
    """

    context = postgresql_context
    client = context["client"]
    mission = _create_mission(context, "Mission arrêtée pendant un claim")

    stop_holds_run = threading.Event()
    claim_holds_task = threading.Event()
    real_invalidate = missions_router._invalidate_run_approvals
    real_session_model = work_router.SessionModel

    def invalidate_after_the_claim(*args, **kwargs):
        stop_holds_run.set()
        # Ancien ordre : le claim réserve T pendant cette pause, puis attend R.
        claim_holds_task.wait(2)
        return real_invalidate(*args, **kwargs)

    def session_model(*args, **kwargs):
        claim_holds_task.set()
        return real_session_model(*args, **kwargs)

    monkeypatch.setattr(missions_router, "_invalidate_run_approvals", invalidate_after_the_claim)
    monkeypatch.setattr(work_router, "SessionModel", session_model)

    stop: dict = {}

    def stop_mission() -> None:
        stop["response"] = client.post(
            f"/missions/{mission['id']}/stop",
            headers={"Idempotency-Key": f"stop-{uuid4().hex}"},
        )

    stopper = threading.Thread(target=stop_mission)
    stopper.start()
    assert stop_holds_run.wait(30), "l'arrêt n'a pas verrouillé la tentative"
    claimed = client.post(
        f"/workers/{context['worker']['worker_id']}/claim",
        headers={"Authorization": f"Bearer {context['worker']['token']}"},
        json={"provider_id": "mock"},
    )
    stopper.join(60)
    assert not stopper.is_alive()

    assert stop["response"].status_code == 200, stop["response"].text
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["task"] is None
    with context["session_factory"]() as db:
        run = db.query(TaskRunModel).filter_by(task_id=mission["id"]).one()
        assert run.status == "cancelled"
        assert db.get(TaskModel, mission["id"]).status == "backlog"
        assert db.query(WorkerLeaseModel).filter_by(task_run_id=run.id).count() == 0
    assert len(_events_of_type(context, "mission.stop_requested", run.id)) == 1


class _LockTimeout:
    """Erreur psycopg minimale : ``55P03``, le délai de verrou de PostgreSQL."""

    sqlstate = "55P03"

    def __str__(self) -> str:
        return "canceling statement due to lock timeout"


def _journal_lock_times_out(monkeypatch) -> None:
    """Le verrou du journal, pris au commit, dépasse son délai."""

    def refuse(_db):
        raise OperationalError("SELECT pg_advisory_xact_lock(...)", {}, _LockTimeout())

    monkeypatch.setattr(events_bus, "_ensure_write_transaction", refuse)


def test_a_claim_whose_events_cannot_be_journaled_reserves_nothing(
    portability_context, monkeypatch
):
    """R6 : réservation et événements partent d'un seul commit.

    Jusqu'en 0.9.0, le claim validait la tâche, la tentative, le bail et
    ``active_runs``, puis journalisait ses événements dans une seconde transaction.
    Un délai de verrou à ce moment rendait 503 « réessayez » au worker alors que la
    réservation était validée : la tâche restait orpheline jusqu'à l'expiration du
    bail. Désormais le 503 dit vrai : rien n'est réservé.
    """

    context = portability_context
    client = context["client"]
    task = _queue_task(context, "Tâche dont le journal est saturé")
    _journal_lock_times_out(monkeypatch)

    refused = client.post(
        f"/workers/{context['worker']['worker_id']}/claim",
        headers={"Authorization": f"Bearer {context['worker']['token']}"},
        json={"provider_id": "mock"},
    )

    assert refused.status_code == 503, refused.text
    assert refused.headers["retry-after"] == "1"
    with context["session_factory"]() as db:
        assert db.get(TaskModel, task["id"]).status == "queued"
        assert db.query(WorkerLeaseModel).count() == 0
        assert db.get(WorkerModel, context["worker"]["worker_id"]).active_runs == 0
        assert db.query(TaskRunModel).filter_by(task_id=task["id"]).count() == 0

    monkeypatch.undo()
    claimed = _claim(context)
    assert claimed["task"]["id"] == task["id"], "le worker qui réessaie obtient la tâche"


def test_a_task_whose_creation_event_cannot_be_journaled_is_not_created(
    portability_context, monkeypatch
):
    """R6 : un 503 après commit poussait le client à réessayer, d'où des doublons."""

    context = portability_context
    _journal_lock_times_out(monkeypatch)
    refused = context["client"].post(
        "/tasks",
        json={"project_id": context["project_id"], "title": "Tâche à ne pas dupliquer"},
    )
    assert refused.status_code == 503, refused.text
    with context["session_factory"]() as db:
        assert db.query(TaskModel).filter_by(title="Tâche à ne pas dupliquer").count() == 0
        assert db.query(EventModel).filter_by(type="task.created").count() == 0


@pytest.mark.concurrency
def test_heartbeat_never_overwrites_a_concurrent_claim(portability_context):
    """``active_runs`` est recalculé par la base sous verrou, jamais réécrit depuis une lecture.

    Le worker (capacité 2) détient déjà un bail mais son compteur a dérivé à 0
    (comme après une fin de tentative perdue) ; le heartbeat, qui doit le
    rattraper, est suspendu juste avant d'écrire son propre bail (``timedelta``)
    pendant qu'un second claim tente de passer. Quel que soit l'ordre final, le
    compteur doit refléter les deux baux actifs et le worker refuser un troisième
    claim : une affectation ORM depuis le compte relu avant le claim l'aurait
    ramené à 1.
    """

    context = portability_context
    client = context["client"]
    worker = context["register"]("worker-double", max_concurrency=2)
    auth = {"Authorization": f"Bearer {worker['token']}"}
    _queue_task(context, "Tâche déjà tenue")
    assert _claim(context, worker)["task"] is not None
    with context["session_factory"]() as db:
        db.query(WorkerModel).filter_by(id=worker["worker_id"]).update(
            {WorkerModel.active_runs: 0}, synchronize_session=False
        )
        db.commit()
    _queue_task(context, "Tâche pendant le heartbeat", agent_id=context["new_agent"]("Agent 2"))
    real_timedelta = workers_router.timedelta
    claim_result: dict = {}
    claim_thread = threading.Thread(
        target=lambda: claim_result.update(_claim(context, worker))
    )
    fired = {"done": False}

    def racing_timedelta(*args, **kwargs):
        if not fired["done"]:
            fired["done"] = True
            claim_thread.start()
            claim_thread.join(2)
        return real_timedelta(*args, **kwargs)

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(workers_router, "timedelta", racing_timedelta)
            heartbeat = client.post(f"/workers/{worker['worker_id']}/heartbeat", headers=auth, json={})
    finally:
        claim_thread.join(30)
    assert fired["done"]
    assert not claim_thread.is_alive()
    assert heartbeat.status_code == 200, heartbeat.text
    assert claim_result.get("task") is not None, claim_result
    with context["session_factory"]() as db:
        stored = db.get(WorkerModel, worker["worker_id"])
        assert stored.active_runs == 2
        assert (
            db.query(WorkerLeaseModel)
            .filter_by(worker_id=worker["worker_id"], status="active")
            .count()
            == 2
        )
    assert client.post(
        f"/workers/{worker['worker_id']}/claim", headers=auth, json={}
    ).json()["reason"] == "capacité de concurrence atteinte"
    settled = client.post(f"/workers/{worker['worker_id']}/heartbeat", headers=auth, json={})
    assert settled.json()["active_runs"] == 2
    assert settled.json()["status"] == "busy"


# --- 4. Verrous de ressources --------------------------------------------------


def _acquire_payload(context, run_id: str, resource_key: str) -> dict:
    return {
        "worker_id": context["worker"]["worker_id"],
        "owner_run_id": run_id,
        "resource_type": "git_branch",
        "resource_key": resource_key,
    }


def test_lock_acquisition_lost_to_a_concurrent_insert_is_a_conflict(portability_context):
    """L'unicité ``(resource_type, resource_key)`` violée à l'insertion répond 409, pas 500."""

    context = portability_context
    client = context["client"]
    _queue_task(context, "Tâche verrou")
    run_id = _claim(context)["task_run"]["id"]
    resource_key = f"refs/heads/h2b-{uuid4().hex}"
    real_timedelta = operations_router.timedelta
    fired = {"done": False}

    def competing_timedelta(*args, **kwargs):
        if not fired["done"]:
            fired["done"] = True
            with context["session_factory"]() as db:
                db.add(
                    ResourceLockModel(
                        resource_type="git_branch",
                        resource_key=resource_key,
                        owner_run_id=run_id,
                        worker_id=context["worker"]["worker_id"],
                        status="active",
                        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                    )
                )
                db.commit()
        return real_timedelta(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(operations_router, "timedelta", competing_timedelta)
        lost = client.post(
            "/locks/acquire",
            headers=_worker_auth(context["worker"]),
            json=_acquire_payload(context, run_id, resource_key),
        )
    assert fired["done"]
    assert lost.status_code == 409, lost.text
    assert lost.json()["detail"] == "Ressource déjà verrouillée"
    with context["session_factory"]() as db:
        assert (
            db.query(ResourceLockModel).filter_by(resource_key=resource_key).count() == 1
        )
    # Le détenteur peut toujours renouveler ; la route n'a laissé aucune transaction ouverte.
    again = client.post(
        "/locks/acquire",
        headers=_worker_auth(context["worker"]),
        json=_acquire_payload(context, run_id, resource_key),
    )
    assert again.status_code == 201, again.text


def test_lock_renewal_is_a_compare_and_set(portability_context):
    """Un lock libéré entre la lecture et l'écriture n'est pas ressuscité par le renouvellement."""

    context = portability_context
    client = context["client"]
    _queue_task(context, "Tâche renouvellement de verrou")
    run_id = _claim(context)["task_run"]["id"]
    acquired = client.post(
        "/locks/acquire",
        headers=_worker_auth(context["worker"]),
        json=_acquire_payload(context, run_id, f"refs/heads/renew-{uuid4().hex}"),
    )
    assert acquired.status_code == 201, acquired.text
    lock_id = acquired.json()["id"]
    owner = {"worker_id": context["worker"]["worker_id"], "owner_run_id": run_id}
    real_utcnow = operations_router.utcnow
    fired = {"done": False}

    def releasing_utcnow():
        if not fired["done"]:
            fired["done"] = True
            with context["session_factory"]() as db:
                db.query(ResourceLockModel).filter_by(id=lock_id).update(
                    {ResourceLockModel.status: "released"}, synchronize_session=False
                )
                db.commit()
        return real_utcnow()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(operations_router, "utcnow", releasing_utcnow)
        refused = client.post(
            f"/locks/{lock_id}/renew", headers=_worker_auth(context["worker"]), json=owner
        )
    assert fired["done"]
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "Ce lock n'est plus détenu par ce run"
    with context["session_factory"]() as db:
        assert db.get(ResourceLockModel, lock_id).status == "released"


# --- 5. Verrous de tentative et sérialisation des instants -----------------------


@pytest.mark.postgres
def test_locking_the_quota_of_an_unknown_attempt_is_an_explicit_refusal(postgresql_context):
    with postgresql_context["session_factory"]() as db:
        with pytest.raises(HTTPException) as refused:
            artifacts_router._lock_artifact_quota(db, f"absente-{uuid4().hex}")
    assert refused.value.status_code == 404
    assert refused.value.detail == "Tentative introuvable"


def test_locking_an_unknown_attempt_returns_none(portability_context):
    with portability_context["session_factory"]() as db:
        assert _lock_run(db, f"absente-{uuid4().hex}") is None


def test_claim_lease_expiry_and_pagination_cursor_are_serialized_in_utc(portability_context):
    """Les instants servis portent toujours ``+00:00``, que la base les relise naïfs ou non."""

    context = portability_context
    client = context["client"]
    _queue_task(context, "Tâche horodatée")
    claim = _claim(context)
    assert claim["lease_expires_at"].endswith("+00:00")
    parsed = datetime.fromisoformat(claim["lease_expires_at"])
    assert parsed.tzinfo is not None
    assert parsed > datetime.now(timezone.utc)

    run_id = claim["task_run"]["id"]
    created = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    identifiers: list[str] = []
    with context["session_factory"]() as db:
        for index in range(2):
            artifact = ArtifactModel(
                project_id=context["project_id"],
                task_run_id=run_id,
                worker_id=context["worker"]["worker_id"],
                kind="report",
                path=f"sortie/{index}",
                created_at=created + timedelta(minutes=index),
            )
            db.add(artifact)
            db.flush()
            identifiers.append(artifact.id)
        db.commit()
    page = client.get("/artifacts", params={"project_id": context["project_id"], "limit": 1})
    assert page.status_code == 200, page.text
    assert [item["id"] for item in page.json()["items"]] == [identifiers[1]]
    cursor = page.json()["next_cursor"]
    assert cursor
    moment, identifier = artifacts_router._decode_cursor(cursor)
    assert moment.tzinfo is not None
    assert moment == created + timedelta(minutes=1)
    assert identifier == identifiers[1]
    rest = client.get(
        "/artifacts", params={"project_id": context["project_id"], "limit": 1, "cursor": cursor}
    )
    assert [item["id"] for item in rest.json()["items"]] == [identifiers[0]]
    assert rest.json()["next_cursor"] is None


# --- 6. Diagnostics MCP --------------------------------------------------------


def _http_server(context, name: str) -> dict:
    response = context["client"].post(
        "/mcp/servers",
        json={
            "name": name,
            "display_name": f"Serveur {name}",
            "config": {
                "transport": "http",
                "http": {
                    "url": "https://mcp.example/mcp",
                    "headers": {"X-Client": "acp"},
                    "timeout_seconds": 5,
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _probe_rows(context, server_id: str) -> list[McpProbeModel]:
    with context["session_factory"]() as db:
        return db.query(McpProbeModel).filter_by(server_id=server_id).all()


def test_http_probe_is_committed_as_queued_before_the_network_call(portability_context):
    """Pendant l'appel réseau, une autre connexion voit déjà le probe ``queued`` validé."""

    context = portability_context
    server = _http_server(context, f"http-{uuid4().hex[:8]}")
    seen: list[str] = []

    def observe(_request):
        if not seen:
            seen.extend(probe.status for probe in _probe_rows(context, server["id"]))

    context["fake"].hooks.append(observe)
    probe = context["client"].post(f"/mcp/servers/{server['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert seen == ["queued"]
    assert probe.json()["status"] == "succeeded"
    assert [row.status for row in _probe_rows(context, server["id"])] == ["succeeded"]


def test_http_probe_result_is_discarded_when_the_probe_was_invalidated_meanwhile(
    portability_context,
):
    """Le résultat n'est écrit que par ``queued → succeeded`` : un probe invalidé reste invalidé."""

    context = portability_context
    server = _http_server(context, f"http-{uuid4().hex[:8]}")
    fired = {"done": False}

    def invalidate(_request):
        if not fired["done"]:
            fired["done"] = True
            with context["session_factory"]() as db:
                db.query(McpProbeModel).filter_by(server_id=server["id"], status="queued").update(
                    {
                        McpProbeModel.status: "invalidated",
                        McpProbeModel.error: "Révision courante modifiée : l'autorisation ne correspond plus.",
                        McpProbeModel.finished_at: datetime.now(timezone.utc),
                    },
                    synchronize_session=False,
                )
                db.commit()

    context["fake"].hooks.append(invalidate)
    probe = context["client"].post(f"/mcp/servers/{server['id']}/probe")
    assert fired["done"]
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "invalidated"
    assert probe.json()["result"] is None
    with context["session_factory"]() as db:
        stored = db.get(McpServerModel, server["id"])
        assert stored.last_probe_id is None
        revision = db.get(McpServerRevisionModel, stored.current_revision_id)
        assert not revision.discovery
        assert db.query(EventModel).filter_by(type="mcp.probe.succeeded").count() == 0


@pytest.mark.postgres
def test_probe_decision_is_a_compare_and_set(postgresql_context):
    """Deux décisions concurrentes : la seconde perd le CAS ``pending_approval → …`` et répond 409."""

    context = postgresql_context
    client = context["client"]
    secret = client.post("/secrets", json={"name": "STDIO_KEY", "value": "valeur-secrète"})
    assert secret.status_code == 201, secret.text
    created = client.post(
        "/mcp/servers",
        json={
            "name": f"stdio-{uuid4().hex[:8]}",
            "display_name": "Serveur stdio",
            "config": {
                "transport": "stdio",
                "stdio": {
                    "command": "/opt/mcp/bin/server",
                    "args": ["--root", "/data"],
                    "env": {"LOG_LEVEL": "info"},
                    "env_secrets": {"API_KEY": {"secret_id": secret.json()["id"]}},
                    "cwd": "/data",
                    "timeout_seconds": 10,
                },
            },
            "target_worker_id": context["worker"]["worker_id"],
        },
    )
    assert created.status_code == 201, created.text
    probe = client.post(f"/mcp/servers/{created.json()['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "pending_approval"
    probe_id = probe.json()["id"]
    real_current_revision = mcp_service.current_revision
    fired = {"done": False}

    def rejecting_current_revision(db, server):
        if not fired["done"]:
            fired["done"] = True
            with context["session_factory"]() as other:
                other.query(McpProbeModel).filter_by(id=probe_id).update(
                    {
                        McpProbeModel.status: "rejected",
                        McpProbeModel.error: "Lancement refusé par le propriétaire.",
                        McpProbeModel.finished_at: datetime.now(timezone.utc),
                    },
                    synchronize_session=False,
                )
                other.commit()
        return real_current_revision(db, server)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(mcp_service, "current_revision", rejecting_current_revision)
        lost = client.post(f"/mcp/probes/{probe_id}/decision", json={"decision": "approved"})
    assert fired["done"]
    assert lost.status_code == 409, lost.text
    assert "rejected" in lost.json()["detail"]
    with context["session_factory"]() as db:
        stored = db.get(McpProbeModel, probe_id)
        assert stored.status == "rejected"
        assert stored.decided_by_user_id is None
        assert db.query(EventModel).filter_by(type="mcp.probe.decided").count() == 0


# --- 7. Stockage des révisions de skills ----------------------------------------


SKILL_MD = """---
name: portable
description: Compétence dont le stockage suit la racine configurée
---
Corps.
"""


def test_skill_revisions_are_stored_relative_to_the_storage_root(
    portability_context, monkeypatch
):
    """La base ne mémorise que ``<skill_id>/<numéro>`` ; la racine vient de l'environnement."""

    context = portability_context
    client = context["client"]
    imported = client.post(
        "/skills/import",
        json={
            "source": {
                "kind": "manual",
                "files": [
                    {"path": "SKILL.md", "content": SKILL_MD},
                    {"path": "reference/guide.md", "content": "# Guide portable\n"},
                ],
            },
            "note": "",
        },
    )
    assert imported.status_code == 201, imported.text
    skill_id = imported.json()["id"]
    with context["session_factory"]() as db:
        revision = db.query(SkillRevisionModel).filter_by(skill_id=skill_id).one()
        assert revision.storage_path == f"{skill_id}/1"
    file_path = f"/skills/{skill_id}/revisions/1/files/reference/guide.md"
    assert client.get(file_path).json()["content"] == "# Guide portable\n"

    moved_root = context["tmp_path"] / "skills-moved"
    shutil.move(str(context["storage"]), str(moved_root))
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(moved_root))
    relocated = client.get(file_path)
    assert relocated.status_code == 200, relocated.text
    assert relocated.json()["content"] == "# Guide portable\n"
    # Une nouvelle révision s'écrit sous la nouvelle racine, toujours en relatif.
    second = client.post(
        f"/skills/{skill_id}/revisions",
        json={
            "source": {
                "kind": "manual",
                "files": [
                    {"path": "SKILL.md", "content": SKILL_MD},
                    {"path": "reference/guide.md", "content": "# Guide portable v2\n"},
                ],
            }
        },
    )
    assert second.status_code == 201, second.text
    assert (moved_root / skill_id / "2" / "reference" / "guide.md").exists()
    with context["session_factory"]() as db:
        numbers = {
            revision.number: revision.storage_path
            for revision in db.query(SkillRevisionModel).filter_by(skill_id=skill_id).all()
        }
    assert numbers == {1: f"{skill_id}/1", 2: f"{skill_id}/2"}
    assert (
        client.get(f"/skills/{skill_id}/revisions/2/files/reference/guide.md").json()["content"]
        == "# Guide portable v2\n"
    )


def _import_portable_skill(client, content: str) -> str:
    imported = client.post(
        "/skills/import",
        json={
            "source": {
                "kind": "manual",
                "files": [
                    {"path": "SKILL.md", "content": SKILL_MD},
                    {"path": "reference/guide.md", "content": content},
                ],
            }
        },
    )
    assert imported.status_code == 201, imported.text
    return imported.json()["id"]


def _set_storage_path(context, skill_id: str, storage_path: str) -> None:
    """Réécrit la ligne comme l'aurait laissée une version antérieure (aucune migration)."""

    with context["session_factory"]() as db:
        revision = db.query(SkillRevisionModel).filter_by(skill_id=skill_id).one()
        revision.storage_path = storage_path
        db.commit()


def test_a_legacy_absolute_storage_path_under_the_root_is_still_read_as_is(
    portability_context,
):
    """Les révisions 0.8.0 gardent leur chemin absolu : aucune migration de données."""

    context = portability_context
    client = context["client"]
    skill_id = _import_portable_skill(client, "# Guide historique\n")
    _set_storage_path(context, skill_id, str(context["storage"] / skill_id / "1"))

    response = client.get(f"/skills/{skill_id}/revisions/1/files/reference/guide.md")
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "# Guide historique\n"


def test_a_legacy_relative_storage_path_from_0_8_0_is_still_read(
    portability_context, monkeypatch
):
    """R28 : racine relative par défaut en 0.8.0, chemin mémorisé ``acp-data/skills/<id>/1``.

    Le joindre à la racine doublait le préfixe (``acp-data/skills/acp-data/skills/…``) :
    la lecture répondait 404 et le retour arrière 409, fichiers pourtant intacts.
    """

    context = portability_context
    client = context["client"]
    workdir = context["tmp_path"] / "service"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("ACP_SKILLS_STORAGE_DIR")
    skill_id = _import_portable_skill(client, "# Guide relatif\n")
    assert (workdir / "acp-data" / "skills" / skill_id / "1" / "SKILL.md").is_file()
    # Valeur exacte que ``store_revision`` de la 0.8.0 renvoyait avec la racine par défaut.
    legacy = str(Path(skills_service.DEFAULT_STORAGE_DIR) / skill_id / "1")
    assert not Path(legacy).is_absolute()
    _set_storage_path(context, skill_id, legacy)

    response = client.get(f"/skills/{skill_id}/revisions/1/files/reference/guide.md")
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "# Guide relatif\n"
    rolled_back = client.post(f"/skills/{skill_id}/rollback", json={"revision_number": 1})
    assert rolled_back.status_code == 200, rolled_back.text


def test_a_legacy_absolute_path_follows_its_moved_root(portability_context, monkeypatch):
    """Volume déplacé : le chemin absolu mémorisé n'existe plus, la racine configurée si."""

    context = portability_context
    client = context["client"]
    skill_id = _import_portable_skill(client, "# Guide déplacé\n")
    _set_storage_path(context, skill_id, str(context["storage"] / skill_id / "1"))
    moved_root = context["tmp_path"] / "volume-neuf"
    shutil.move(str(context["storage"]), str(moved_root))
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(moved_root))

    response = client.get(f"/skills/{skill_id}/revisions/1/files/reference/guide.md")
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "# Guide déplacé\n"


def test_a_storage_path_outside_the_configured_root_is_refused(
    portability_context, monkeypatch
):
    """Un chemin mémorisé hors de ``ACP_SKILLS_STORAGE_DIR`` n'est jamais suivi.

    La ligne peut venir d'une sauvegarde restaurée ou d'une ancienne racine : la lire
    telle quelle ferait servir par l'API un répertoire que l'opérateur n'a pas désigné.
    """

    context = portability_context
    client = context["client"]
    skill_id = _import_portable_skill(client, "# Guide historique\n")
    outside = context["tmp_path"] / "hors-racine"
    shutil.copytree(str(context["storage"]), str(outside))
    _set_storage_path(context, skill_id, str(outside / skill_id / "1"))
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(context["tmp_path"] / "ailleurs"))

    response = client.get(f"/skills/{skill_id}/revisions/1/files/reference/guide.md")
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "hors de la racine" in detail and "ACP_SKILLS_STORAGE_DIR" in detail
    rolled_back = client.post(f"/skills/{skill_id}/rollback", json={"revision_number": 1})
    assert rolled_back.status_code == 409, rolled_back.text
    assert "hors de la racine" in rolled_back.json()["detail"]


def test_a_relative_storage_path_cannot_escape_the_root(portability_context):
    """``../`` dans la colonne ne mène jamais hors de la racine : seul l'emplacement
    canonique ``<racine>/<skill_id>/<numéro>`` est lu."""

    context = portability_context
    client = context["client"]
    skill_id = _import_portable_skill(client, "# Guide légitime\n")
    planted = context["tmp_path"] / "piege" / skill_id / "1" / "reference"
    planted.mkdir(parents=True)
    (planted / "guide.md").write_text("# Contenu planté\n", encoding="utf-8")
    _set_storage_path(context, skill_id, f"../piege/{skill_id}/1")

    response = client.get(f"/skills/{skill_id}/revisions/1/files/reference/guide.md")
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "# Guide légitime\n"


# --- 8. Horodatages naïfs du reporter -------------------------------------------


def test_naive_reporter_timestamps_are_read_as_utc(portability_context):
    """Un horodatage sans fuseau est réputé UTC : durée exacte et instants servis en ``+00:00``."""

    context = portability_context
    client = context["client"]
    _create_mission(context, "Mission testée")
    claim = _claim(context)
    run_id = claim["attempt_id"]
    ingestion = client.post(
        f"/workers/{context['worker']['worker_id']}/test-runs",
        headers=_worker_auth(context["worker"]),
        json={
            "task_run_id": run_id,
            "fencing_token": claim["fencing_token"],
            "runner": "playwright",
            "runner_version": "1.47.0",
            "config": {},
            "exit_code": 0,
            "events": [
                {"kind": "run_begin", "started_at": "2026-09-12T10:00:00"},
                {
                    "kind": "test_end",
                    "test_id": "t1",
                    "title": "cas 1",
                    "suite_path": ["specs"],
                    "location": {"file": "tests/a.spec.ts", "line": 1, "column": 1},
                    "project_name": "chromium",
                    "attempt": 1,
                    "expected_status": "passed",
                    "status": "passed",
                    "outcome": "expected",
                    "duration_ms": 10,
                },
                {
                    "kind": "run_end",
                    "finished_at": "2026-09-12T10:00:12",
                    "totals": {"expected": 1},
                    "run_status": "completed",
                    "exit_code": 0,
                },
            ],
        },
    )
    assert ingestion.status_code == 200, ingestion.text
    body = ingestion.json()
    assert body["duration_ms"] == 12_000
    assert datetime.fromisoformat(body["started_at"]) == datetime(
        2026, 9, 12, 10, 0, tzinfo=timezone.utc
    )
    assert datetime.fromisoformat(body["finished_at"]) == datetime(
        2026, 9, 12, 10, 0, 12, tzinfo=timezone.utc
    )
    with context["session_factory"]() as db:
        stored = db.query(TestRunModel).filter_by(task_run_id=run_id).one()
        assert stored.duration_ms == 12_000
        assert stored.started_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 9, 12, 10, 0, tzinfo=timezone.utc
        )
        if context["backend"] == "postgresql":
            assert stored.started_at.utcoffset() == timedelta(0)
            assert stored.finished_at.utcoffset() == timedelta(0)
            assert db.execute(
                text("SELECT started_at::text FROM test_runs WHERE id = :id"),
                {"id": stored.id},
            ).scalar_one().startswith("2026-09-12 10:00:00")
