"""Intégration des budgets appliqués : sécurité, atomicité et inconnues."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from acp_api import budget_service
from acp_api.deps import get_db, get_principal
from acp_api.routers import budgets
from acp_api.routers.workers import _token_hash
from acp_database.models import (
    AlertModel,
    Base,
    BudgetUsageModel,
    BudgetUsageReportModel,
    EventModel,
    MembershipModel,
    OrganizationModel,
    ProjectBudgetPolicyModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    UserModel,
    WorkerLeaseModel,
    WorkerModel,
    WorkspaceModel,
)


@pytest.fixture
def budget_context(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'budgets.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=QueuePool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    token = f"worker-{uuid4().hex}"
    with session_factory() as db:
        organization = OrganizationModel(name="Budget org")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(organization_id=organization.id, name="Budget ws")
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Budget project")
        db.add(project)
        viewer = UserModel(
            login_normalized=f"viewer-{uuid4().hex}",
            display_name="Budget viewer",
            password_hash="test",
            platform_role="member",
        )
        member = UserModel(
            login_normalized=f"member-{uuid4().hex}",
            display_name="Budget member",
            password_hash="test",
            platform_role="member",
        )
        db.add_all([project, viewer, member])
        db.flush()
        db.add_all(
            [
                MembershipModel(
                    user_id=viewer.id,
                    scope_type="project",
                    scope_id=project.id,
                    role="viewer",
                ),
                MembershipModel(
                    user_id=member.id,
                    scope_type="project",
                    scope_id=project.id,
                    role="member",
                ),
            ]
        )
        worker = WorkerModel(
            name=f"budget-worker-{uuid4().hex}",
            token_hash=_token_hash(token),
            token_prefix=token[:8],
            token_expires_at=datetime.now(UTC) + timedelta(days=30),
            capabilities=[],
            max_concurrency=4,
            active_runs=2,
            status="online",
            simulation=0,
        )
        db.add(worker)
        db.flush()
        run_ids = []
        task_ids = []
        for index in range(2):
            task = TaskModel(
                project_id=project.id,
                title=f"Mission {index}",
                is_mission=1,
                budget={"max_tool_calls": 10, "currency": "EUR"},
                duration_seconds=3600,
                status="in_progress",
            )
            db.add(task)
            db.flush()
            run = TaskRunModel(
                task_id=task.id,
                status="running",
                attempt_number=1,
                fencing_token=index + 3,
            )
            db.add(run)
            db.flush()
            task.active_run_id = run.id
            db.add(
                WorkerLeaseModel(
                    worker_id=worker.id,
                    task_id=task.id,
                    task_run_id=run.id,
                    status="active",
                    lease_expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            task_ids.append(task.id)
            run_ids.append(run.id)
        db.commit()
        ids = {
            "project": project.id,
            "viewer": viewer.id,
            "member": member.id,
            "worker": worker.id,
            "runs": run_ids,
            "tasks": task_ids,
        }

    principal = {"id": ids["member"]}
    app = FastAPI()
    app.include_router(budgets.router)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_principal] = lambda: principal["id"]
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield {
                "app": app,
                "client": client,
                "session_factory": session_factory,
                "principal": principal,
                "token": token,
                **ids,
            }
    finally:
        engine.dispose()


def _headers(context, run_index=0, *, token=None, fence=None):
    return {
        "Authorization": f"Bearer {token or context['token']}",
        "X-Attempt-Fencing-Token": str(
            fence if fence is not None else run_index + 3
        ),
    }


def _path(context, kind, run_index=0):
    return (
        f"/work/workers/{context['worker']}/runs/"
        f"{context['runs'][run_index]}/budget/{kind}"
    )


def _permit(identifier, **metrics):
    return {
        "permit_id": identifier,
        "provider": metrics.pop("provider", "mock"),
        "phase": metrics.pop("phase", "tool"),
        **metrics,
    }


def _set_task_budget(context, run_index, budget):
    with context["session_factory"]() as db:
        task = db.get(TaskModel, context["tasks"][run_index])
        task.budget = budget
        db.commit()


def _put_policy(context, payload):
    context["principal"]["id"] = context["member"]
    return context["client"].put(
        f"/projects/{context['project']}/budget-policy", json=payload
    )


def test_policy_defaults_rbac_persistence_and_currency_validation(budget_context):
    context = budget_context
    context["principal"]["id"] = context["viewer"]
    response = context["client"].get(
        f"/projects/{context['project']}/budget-policy"
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Paris"
    assert response.json()["daily_budget"] is None

    denied = context["client"].put(
        f"/projects/{context['project']}/budget-policy",
        json={"max_concurrent_missions": 2},
    )
    assert denied.status_code == 403

    saved = _put_policy(
        context,
        {
            "timezone": "Europe/Paris",
            "daily_budget": {"max_tool_calls": 2},
            "provider_budgets": [],
            "max_concurrent_missions": 2,
            "max_retries_per_mission": 1,
            "max_spawned_agents_per_run": 3,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["daily_budget"]["max_tool_calls"] == 2
    with context["session_factory"]() as db:
        assert db.query(ProjectBudgetPolicyModel).count() == 1

    incompatible = _put_policy(
        context,
        {
            "daily_budget": {"max_cost": 10, "currency": "EUR"},
            "provider_budgets": [
                {
                    "provider": "openai",
                    "budget": {"max_cost": 5, "currency": "USD"},
                }
            ],
        },
    )
    assert incompatible.status_code == 422


def test_worker_auth_fencing_and_live_lease_are_mandatory(budget_context):
    context = budget_context
    body = _permit("secure-permit", tool_calls=1)
    assert context["client"].post(_path(context, "permit"), json=body).status_code == 401
    assert context["client"].post(
        _path(context, "permit"),
        headers=_headers(context, token="wrong"),
        json=body,
    ).status_code == 401
    assert context["client"].post(
        _path(context, "permit"),
        headers=_headers(context, fence=999),
        json=body,
    ).status_code == 409

    with context["session_factory"]() as db:
        lease = db.query(WorkerLeaseModel).filter_by(
            task_run_id=context["runs"][0]
        ).one()
        lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=body
    ).status_code == 409


def test_unknown_is_denied_zero_is_known_and_boundary_is_allowed(budget_context):
    context = budget_context
    _set_task_budget(context, 0, {"max_cost": 1, "currency": "EUR"})
    unknown = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("unknown-cost", tool_calls=0),
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["permit_allowed"] is False
    assert unknown.json()["verdict"]["state"] == "unknown"
    assert unknown.json()["verdict"]["cost"] is None

    _set_task_budget(context, 1, {"max_cost": 0, "currency": "EUR"})
    real_zero = context["client"].post(
        _path(context, "permit", 1),
        headers=_headers(context, 1),
        json=_permit("real-zero", cost=0, currency="EUR"),
    )
    assert real_zero.status_code == 200, real_zero.text
    assert real_zero.json()["permit_allowed"] is True
    assert real_zero.json()["verdict"]["state"] == "ok"
    assert real_zero.json()["verdict"]["cost"] == 0

    _set_task_budget(context, 0, {"max_tool_calls": 1})
    boundary = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("at-boundary", tool_calls=1),
    )
    assert boundary.status_code == 200, boundary.text
    assert boundary.json()["permit_allowed"] is True
    assert boundary.json()["verdict"]["state"] == "warning"
    beyond = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("past-boundary", tool_calls=1),
    )
    assert beyond.status_code == 200
    assert beyond.json()["permit_allowed"] is False
    assert beyond.json()["verdict"]["state"] == "exceeded"


def test_permit_and_usage_are_exactly_once_and_reconcile_without_double_count(
    budget_context,
):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 2})
    permit = _permit("permit-1", tool_calls=1)
    first = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=permit
    )
    replay = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=permit
    )
    assert first.status_code == replay.status_code == 200
    assert first.json()["idempotent"] is False
    assert replay.json()["idempotent"] is True
    changed = dict(permit, tool_calls=2)
    assert context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=changed
    ).status_code == 409

    usage = {
        "report_id": "usage-1",
        "permit_id": "permit-1",
        "provider": "mock",
        "phase": "tool",
        "source": "platform",
        "tool_calls": 1,
    }
    recorded = context["client"].post(
        _path(context, "usage"), headers=_headers(context), json=usage
    )
    replayed = context["client"].post(
        _path(context, "usage"), headers=_headers(context), json=usage
    )
    assert recorded.status_code == replayed.status_code == 200
    assert recorded.json()["idempotent"] is False
    assert replayed.json()["idempotent"] is True

    with context["session_factory"]() as db:
        reports = (
            db.query(BudgetUsageReportModel)
            .filter_by(task_run_id=context["runs"][0])
            .all()
        )
        assert len(reports) == 2
        reservation = next(row for row in reports if row.kind == "reservation")
        assert reservation.reconciled_at is not None
        cache = db.query(BudgetUsageModel).filter_by(
            task_run_id=context["runs"][0]
        ).one()
        assert cache.tool_calls == 1
        assert cache.tool_calls_reported == 1
        assert cache.usage_reported == 0

    second_report = dict(usage, report_id="usage-2")
    assert context["client"].post(
        _path(context, "usage"), headers=_headers(context), json=second_report
    ).status_code == 409


def test_daily_and_provider_limits_span_attempts_without_implicit_fx(budget_context):
    context = budget_context
    for index in range(2):
        _set_task_budget(context, index, {"max_tool_calls": 10})
    response = _put_policy(
        context,
        {
            "daily_budget": {"max_tool_calls": 1},
            "provider_budgets": [
                {"provider": "openai", "budget": {"max_tool_calls": 1}}
            ],
        },
    )
    assert response.status_code == 200, response.text
    one = context["client"].post(
        _path(context, "permit", 0),
        headers=_headers(context, 0),
        json=_permit("daily-1", provider="OpenAI", tool_calls=1),
    )
    two = context["client"].post(
        _path(context, "permit", 1),
        headers=_headers(context, 1),
        json=_permit("daily-2", provider="openai", tool_calls=1),
    )
    assert one.json()["permit_allowed"] is True
    assert two.json()["permit_allowed"] is False

    # Une policy fournisseur peut avoir sa devise lorsque le plafond journalier
    # n'en a pas ; le budget EUR de la mission ne doit jamais être converti en USD.
    _set_task_budget(context, 1, {"max_cost": 10, "currency": "EUR"})
    assert _put_policy(
        context,
        {
            "provider_budgets": [
                {
                    "provider": "openai",
                    "budget": {"max_cost": 10, "currency": "USD"},
                }
            ]
        },
    ).status_code == 200
    currency_conflict = context["client"].post(
        _path(context, "permit", 1),
        headers=_headers(context, 1),
        json=_permit("no-fx", provider="openai", cost=1, currency="USD"),
    )
    assert currency_conflict.status_code == 200
    assert currency_conflict.json()["permit_allowed"] is False
    assert currency_conflict.json()["verdict"]["state"] == "unknown"


def test_concurrent_permits_use_one_atomic_daily_slot(budget_context):
    context = budget_context
    for index in range(2):
        _set_task_budget(context, index, {"max_tool_calls": 10})
    assert _put_policy(
        context, {"daily_budget": {"max_tool_calls": 1}}
    ).status_code == 200

    def request(index):
        with TestClient(context["app"], raise_server_exceptions=False) as client:
            response = client.post(
                _path(context, "permit", index),
                headers=_headers(context, index),
                json=_permit(f"concurrent-{index}", tool_calls=1),
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, (0, 1)))
    assert [status for status, _ in results] == [200, 200]
    assert sorted(body["permit_allowed"] for _, body in results) == [False, True]
    with context["session_factory"]() as db:
        rows = db.query(BudgetUsageReportModel).filter_by(kind="reservation").all()
        assert len(rows) == 2
        assert sum(row.allowed for row in rows) == 1


def test_daily_window_uses_real_iana_dst_boundaries(budget_context, monkeypatch):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 10})
    assert _put_policy(
        context,
        {"timezone": "Europe/Paris", "daily_budget": {"max_tool_calls": 1}},
    ).status_code == 200

    # Le 29 mars 2026 dure 23 heures à Paris : minuit suivant vaut 22:00 UTC.
    monkeypatch.setattr(
        budget_service, "utcnow", lambda: datetime(2026, 3, 29, 21, 59, tzinfo=UTC)
    )
    before = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("dst-before", tool_calls=1),
    )
    monkeypatch.setattr(
        budget_service, "utcnow", lambda: datetime(2026, 3, 29, 22, 1, tzinfo=UTC)
    )
    after = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("dst-after", tool_calls=1),
    )
    assert before.status_code == after.status_code == 200
    assert before.json()["permit_allowed"] is True
    assert after.json()["permit_allowed"] is True


def test_ledger_cache_alert_and_event_roll_back_together(budget_context, monkeypatch):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 10})

    def fail_event(*args, **kwargs):
        raise RuntimeError("synthetic event failure")

    monkeypatch.setattr(budget_service, "_emit_budget_event", fail_event)
    response = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("rollback", tool_calls=1),
    )
    assert response.status_code == 500
    with context["session_factory"]() as db:
        assert db.query(BudgetUsageReportModel).count() == 0
        assert db.query(BudgetUsageModel).count() == 0
        assert db.query(AlertModel).count() == 0
        assert db.query(EventModel).count() == 0


def test_platform_cannot_self_report_provider_cost_or_tokens(budget_context):
    context = budget_context
    invalid = {
        "report_id": "forged-provider-usage",
        "permit_id": "anything",
        "provider": "mock",
        "phase": "tool",
        "source": "platform",
        "cost": 1,
        "currency": "EUR",
    }
    response = context["client"].post(
        _path(context, "usage"), headers=_headers(context), json=invalid
    )
    assert response.status_code == 422
