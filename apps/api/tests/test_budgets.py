"""Intégration des budgets appliqués : sécurité, atomicité et inconnues."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from acp_api import budget_service
from acp_api.deps import get_db, get_principal
from acp_api.routers import budgets
from acp_api.routers.workers import _token_hash
from acp_contracts import MAX_BUDGET_COST, MAX_BUDGET_COUNTER
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


def test_policy_write_rechecks_access_after_opening_the_write_transaction(
    budget_context, monkeypatch
):
    context = budget_context
    context["principal"]["id"] = context["member"]
    real_ensure_access = budgets.ensure_access
    real_begin = budgets.begin_budget_write
    events: list[str] = []

    def access_that_disappears(db, principal, **scope):
        events.append("access")
        if events.count("access") == 1:
            # L'accès est encore valide dans la première transaction de lecture.
            return real_ensure_access(db, principal, **scope)
        raise HTTPException(status_code=403, detail="Accès révoqué entre transactions")

    def observed_begin(db):
        events.append("begin")
        return real_begin(db)

    monkeypatch.setattr(budgets, "ensure_access", access_that_disappears)
    monkeypatch.setattr(budgets, "begin_budget_write", observed_begin)

    response = context["client"].put(
        f"/projects/{context['project']}/budget-policy",
        json={"max_concurrent_missions": 2},
    )

    assert response.status_code == 403
    assert events == ["access", "begin", "access"]
    with context["session_factory"]() as db:
        assert db.query(ProjectBudgetPolicyModel).count() == 0


def test_accounting_timezone_is_frozen_after_the_first_ledger_entry(
    budget_context, monkeypatch
):
    context = budget_context
    fixed = datetime(2026, 9, 14, 0, 30, tzinfo=UTC)
    monkeypatch.setattr(budget_service, "utcnow", lambda: fixed)
    assert _put_policy(
        context,
        {"timezone": "UTC", "daily_budget": {"max_tool_calls": 10}},
    ).status_code == 200
    first = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("timezone-anchor", tool_calls=1),
    )
    assert first.status_code == 200 and first.json()["permit_allowed"] is True

    moved = _put_policy(
        context,
        {
            "timezone": "America/Los_Angeles",
            "daily_budget": {"max_tool_calls": 10},
        },
    )
    assert moved.status_code == 409
    assert "fuseau comptable" in moved.json()["detail"]
    unchanged_timezone = _put_policy(
        context,
        {
            "timezone": "UTC",
            "daily_budget": {"max_tool_calls": 10},
            "max_retries_per_mission": 2,
        },
    )
    assert unchanged_timezone.status_code == 200
    assert unchanged_timezone.json()["max_retries_per_mission"] == 2


def test_cost_cache_saturates_and_future_effect_is_refused_before_overflow(
    budget_context,
):
    context = budget_context
    first_bound = 600_000_000_000
    second_bound = 399_999_999_999
    for permit_id, cost in (
        ("large-cost-1", first_bound),
        ("large-cost-2", second_bound),
    ):
        response = context["client"].post(
            _path(context, "permit"),
            headers=_headers(context),
            json=_permit(
                permit_id,
                cost=cost,
                currency="EUR",
                tool_calls=1,
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["permit_allowed"] is True

    for report_id, permit_id, cost in (
        ("large-usage-1", "large-cost-1", first_bound),
        # Simule un fournisseur qui viole sa borne : le ledger exact doit garder
        # le rapport au lieu de perdre toute la transaction sur overflow du cache.
        ("large-usage-2", "large-cost-2", 999_999_999_999),
    ):
        response = context["client"].post(
            _path(context, "usage"),
            headers=_headers(context),
            json={
                "report_id": report_id,
                "permit_id": permit_id,
                "provider": "mock",
                "phase": "tool",
                "source": "provider",
                "cost": cost,
                "currency": "EUR",
                "tool_calls": 1,
            },
        )
        assert response.status_code == 200, response.text

    with context["session_factory"]() as db:
        cache = db.query(BudgetUsageModel).filter_by(
            task_run_id=context["runs"][0]
        ).one()
        assert Decimal(cache.cost) == Decimal(str(MAX_BUDGET_COST))
        assert (
            db.query(BudgetUsageReportModel)
            .filter_by(task_run_id=context["runs"][0], kind="usage")
            .count()
            == 2
        )

    refused = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit(
            "large-cost-3",
            cost=1,
            currency="EUR",
            tool_calls=1,
        ),
    )
    assert refused.status_code == 422
    assert "capacité monétaire" in refused.json()["detail"]


def test_integer_cache_saturates_without_losing_post_effect_reports(budget_context):
    context = budget_context
    for permit_id in ("large-counter-1", "large-counter-2"):
        response = context["client"].post(
            _path(context, "permit"),
            headers=_headers(context),
            json=_permit(permit_id, tool_calls=1),
        )
        assert response.status_code == 200, response.text
        assert response.json()["permit_allowed"] is True

    for report_id, permit_id, tool_calls in (
        ("large-counter-usage-1", "large-counter-1", MAX_BUDGET_COUNTER - 1),
        ("large-counter-usage-2", "large-counter-2", MAX_BUDGET_COUNTER),
    ):
        response = context["client"].post(
            _path(context, "usage"),
            headers=_headers(context),
            json={
                "report_id": report_id,
                "permit_id": permit_id,
                "provider": "mock",
                "phase": "tool",
                "source": "platform",
                "tool_calls": tool_calls,
            },
        )
        assert response.status_code == 200, response.text
    assert response.json()["verdict"]["tool_calls"] == MAX_BUDGET_COUNTER
    assert response.json()["verdict"]["saturated_metrics"] == ["tool_calls"]

    with context["session_factory"]() as db:
        cache = (
            db.query(BudgetUsageModel)
            .filter_by(task_run_id=context["runs"][0])
            .one()
        )
        assert cache.tool_calls == MAX_BUDGET_COUNTER
        reports = (
            db.query(BudgetUsageReportModel)
            .filter_by(task_run_id=context["runs"][0], kind="usage")
            .order_by(BudgetUsageReportModel.report_id)
            .all()
        )
        assert [report.tool_calls for report in reports] == [
            MAX_BUDGET_COUNTER - 1,
            MAX_BUDGET_COUNTER,
        ]

    consumption = context["client"].get(
        f"/projects/{context['project']}/budget-usage"
    )
    assert consumption.status_code == 200, consumption.text
    assert consumption.json()["totals"]["tool_calls"] == MAX_BUDGET_COUNTER
    assert consumption.json()["totals"]["saturated_metrics"] == ["tool_calls"]


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


def test_lease_is_rechecked_after_waiting_for_budget_locks(
    budget_context, monkeypatch
):
    context = budget_context
    before_expiry = datetime.now(UTC)
    after_expiry = before_expiry + timedelta(seconds=2)
    with context["session_factory"]() as db:
        lease = (
            db.query(WorkerLeaseModel)
            .filter_by(task_run_id=context["runs"][0], status="active")
            .one()
        )
        lease.lease_expires_at = before_expiry + timedelta(seconds=1)
        db.commit()

    clock = {"now": before_expiry}
    monkeypatch.setattr(budget_service, "utcnow", lambda: clock["now"])
    original_lock_policy = budget_service._lock_policy

    def delayed_policy_lock(db, project_id):
        result = original_lock_policy(db, project_id)
        clock["now"] = after_expiry
        return result

    monkeypatch.setattr(budget_service, "_lock_policy", delayed_policy_lock)
    response = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("expired-while-waiting", tool_calls=1),
    )

    assert response.status_code == 409
    assert "Lease expiré" in response.json()["detail"]
    with context["session_factory"]() as db:
        assert (
            db.query(BudgetUsageReportModel)
            .filter_by(report_id="expired-while-waiting")
            .count()
            == 0
        )

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


def test_exact_zero_cost_does_not_create_a_false_currency_conflict(budget_context):
    context = budget_context
    _set_task_budget(context, 0, {"max_cost": 10, "currency": "USD"})
    assert _put_policy(
        context,
        {"daily_budget": {"max_cost": 10, "currency": "EUR"}},
    ).status_code == 200

    local_zero = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit(
            "local-zero-other-currency",
            provider="local-runner",
            cost=0,
            currency="USD",
            tokens_input=0,
            tokens_output=0,
            tool_calls=1,
        ),
    )
    assert local_zero.status_code == 200, local_zero.text
    assert local_zero.json()["permit_allowed"] is True
    assert local_zero.json()["verdict"]["cost"] == 0

    # Un montant positif reste non convertible et est donc refusé.
    positive = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit(
            "positive-other-currency",
            provider="external-provider",
            cost=1,
            currency="USD",
            tool_calls=1,
        ),
    )
    assert positive.status_code == 200, positive.text
    assert positive.json()["permit_allowed"] is False
    assert positive.json()["verdict"]["state"] == "unknown"


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


def test_unreconciled_conservative_dimensions_remain_counted(budget_context):
    context = budget_context
    _set_task_budget(
        context,
        0,
        {
            "max_cost": 1,
            "currency": "EUR",
            "max_tokens": 10,
            "max_tool_calls": 10,
        },
    )
    reserved = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit(
            "conservative-pending",
            cost=1,
            currency="EUR",
            tokens_input=4,
            tokens_output=6,
            tool_calls=1,
        ),
    )
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["permit_allowed"] is True

    # Aucun rapport d'usage n'arrive. Un nouvel effet ne peut donc pas récupérer
    # implicitement le coût ou les jetons réservés comme s'ils valaient zéro.
    next_effect = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit(
            "after-missing-usage",
            cost=0.000001,
            currency="EUR",
            tokens_input=0,
            tokens_output=1,
            tool_calls=1,
        ),
    )
    assert next_effect.status_code == 200, next_effect.text
    assert next_effect.json()["permit_allowed"] is False
    assert next_effect.json()["verdict"]["state"] == "exceeded"

    with context["session_factory"]() as db:
        pending = db.query(BudgetUsageReportModel).filter_by(
            report_id="conservative-pending"
        ).one()
        assert pending.reconciled_at is None


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


def test_permit_id_is_required_and_auth_happens_before_the_write_lock(
    budget_context, monkeypatch
):
    context = budget_context
    begun = 0
    real_begin = budgets.begin_budget_write

    def observed_begin(db):
        nonlocal begun
        begun += 1
        return real_begin(db)

    monkeypatch.setattr(budgets, "begin_budget_write", observed_begin)
    missing = {
        "report_id": "missing-permit",
        "provider": "mock",
        "phase": "tool",
        "source": "platform",
        "tool_calls": 1,
    }
    assert context["client"].post(
        _path(context, "usage"), headers=_headers(context), json=missing
    ).status_code == 422
    assert context["client"].post(
        _path(context, "permit"), json=_permit("unauthenticated", tool_calls=1)
    ).status_code == 401
    assert begun == 0


def test_subquantum_positive_cost_never_rounds_to_zero(budget_context):
    context = budget_context
    _set_task_budget(
        context,
        0,
        {"max_cost": 0.0000005, "currency": "EUR"},
    )
    response = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("subquantum", cost=0.0000004, currency="EUR"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["permit_allowed"] is False
    assert response.json()["verdict"]["state"] == "exceeded"
    with context["session_factory"]() as db:
        row = db.query(BudgetUsageReportModel).filter_by(
            report_id="subquantum"
        ).one()
        assert row.cost == Decimal("0.000001")


def test_replay_returns_the_original_verdict_after_totals_change(budget_context):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 3})
    first_body = _permit("stable-first", tool_calls=1)
    first = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=first_body
    )
    assert first.status_code == 200
    assert first.json()["verdict"]["state"] == "ok"

    later = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("stable-later", tool_calls=2),
    )
    assert later.json()["verdict"]["state"] == "warning"
    replay = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=first_body
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    assert replay.json()["verdict"] == first.json()["verdict"]

    denied_body = _permit("stable-denied", tool_calls=1)
    denied = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=denied_body
    )
    assert denied.json()["permit_allowed"] is False
    _set_task_budget(context, 0, {"max_tool_calls": 100})
    denied_replay = context["client"].post(
        _path(context, "permit"), headers=_headers(context), json=denied_body
    )
    assert denied_replay.json()["permit_allowed"] is False
    assert denied_replay.json()["verdict"] == denied.json()["verdict"]


def test_reservation_and_usage_keep_the_same_accounting_day_across_midnight(
    budget_context, monkeypatch
):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 10})
    assert _put_policy(
        context,
        {"timezone": "Europe/Paris", "daily_budget": {"max_tool_calls": 1}},
    ).status_code == 200

    monkeypatch.setattr(
        budget_service,
        "utcnow",
        lambda: datetime(2026, 1, 1, 22, 59, tzinfo=UTC),
    )
    permit = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("before-midnight", provider="OpenAI", tool_calls=1),
    )
    assert permit.json()["permit_allowed"] is True

    monkeypatch.setattr(
        budget_service,
        "utcnow",
        lambda: datetime(2026, 1, 1, 23, 1, tzinfo=UTC),
    )
    usage = context["client"].post(
        _path(context, "usage"),
        headers=_headers(context),
        json={
            "report_id": "after-midnight-usage",
            "permit_id": "before-midnight",
            "provider": "openai",
            "phase": "tool",
            "source": "platform",
            "tool_calls": 1,
        },
    )
    assert usage.status_code == 200, usage.text
    next_day = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("new-day", provider="openai", tool_calls=1),
    )
    assert next_day.json()["permit_allowed"] is True

    with context["session_factory"]() as db:
        by_id = {
            row.report_id: row
            for row in db.query(BudgetUsageReportModel).all()
        }
        assert by_id["before-midnight"].accounting_day == "2026-01-01"
        assert by_id["after-midnight-usage"].accounting_day == "2026-01-01"
        assert by_id["new-day"].accounting_day == "2026-01-02"

    context["principal"]["id"] = context["viewer"]
    previous = context["client"].get(
        f"/projects/{context['project']}/budget-usage?day=2026-01-01"
    )
    assert previous.status_code == 200, previous.text
    body = previous.json()
    assert body["totals"]["reports"] == 1
    assert body["totals"]["tool_calls"] == 1
    assert body["totals"]["cost"] is None
    assert body["providers"][0]["provider"] == "openai"
    assert body["missions"][0]["mission_id"] == context["tasks"][0]


def test_budget_alert_has_one_stable_kind_and_escalates(budget_context):
    context = budget_context
    _set_task_budget(context, 0, {"max_tool_calls": 2})
    warning = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("warning-alert", provider="OpenAI", tool_calls=2),
    )
    assert warning.json()["verdict"]["state"] == "warning"
    exceeded = context["client"].post(
        _path(context, "permit"),
        headers=_headers(context),
        json=_permit("critical-alert", provider="openai", tool_calls=1),
    )
    assert exceeded.json()["verdict"]["state"] == "exceeded"
    with context["session_factory"]() as db:
        alerts = db.query(AlertModel).all()
        assert len(alerts) == 1
        assert alerts[0].kind == "budget.guard"
        assert alerts[0].severity == "critical"


def test_first_policy_put_is_concurrent_safe(budget_context):
    context = budget_context
    # Remove the row potentially created by previous helpers in this isolated fixture.
    with context["session_factory"]() as db:
        db.query(ProjectBudgetPolicyModel).delete()
        db.commit()

    def write(limit: int):
        with TestClient(context["app"], raise_server_exceptions=False) as client:
            return client.put(
                f"/projects/{context['project']}/budget-policy",
                json={"max_concurrent_missions": limit},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, (2, 3)))
    assert [response.status_code for response in responses] == [200, 200]
    with context["session_factory"]() as db:
        rows = db.query(ProjectBudgetPolicyModel).all()
        assert len(rows) == 1
        assert rows[0].policy["max_concurrent_missions"] in {2, 3}
