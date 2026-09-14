"""Garanties de concurrence, reprise et arrêt du planificateur Lot F."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from acp_api.deps import get_db
from acp_api.routers.scheduler import router
from acp_api.routers.workers import _token_hash
from acp_api.scheduler_service import (
    CATCHUP_GRACE_SECONDS,
    INVALID_CONFIGURATION_RETRY_SECONDS,
    TERMINAL_RUN_STATES,
    SchedulerFenceRejected,
    SchedulerLeaseBusy,
    _reconcile_terminal_runs,
    acquire_scheduler_lease,
    run_scheduler_tick,
)
from acp_contracts.schedule import fire_key
from acp_database import engine as engine_module
from acp_database.models import (
    AlertModel,
    AutomationModel,
    AutomationRunModel,
    Base,
    EventModel,
    OrganizationModel,
    ProjectModel,
    SchedulerLeaseModel,
    TaskModel,
    TaskRunModel,
    WorkerModel,
    WorkspaceModel,
)

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)
TOKEN = "scheduler-worker-secret"


def test_terminal_reconciliation_locks_only_the_non_nullable_occurrence_on_postgres(
    monkeypatch,
) -> None:
    """La requête doit rester exécutable avec ses deux LEFT OUTER JOIN."""

    statements: list[str] = []

    def capture_statement(query: Query):
        statements.append(
            str(query.statement.compile(dialect=postgresql.dialect()))
        )
        return []

    monkeypatch.setattr(Query, "all", capture_statement)
    assert _reconcile_terminal_runs(Session(), observed_at=NOW) == (0, 0)

    assert len(statements) == 1
    assert "LEFT OUTER JOIN tasks" in statements[0]
    assert "LEFT OUTER JOIN task_runs" in statements[0]
    assert statements[0].rstrip().endswith("FOR UPDATE OF automation_runs")


def _engine(path):
    return create_engine(
        f"sqlite+pysqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=QueuePool,
    )


def _mission_template() -> dict:
    return {
        "title": "Mission du planificateur",
        "objective": "Produire un résultat vérifiable",
        "expected_outcome": "Un résultat durable",
        "acceptance_criteria": ["les preuves existent"],
        "autonomy": {
            "mode": "bounded",
            "allowed_actions": ["read"],
            "forbidden_actions": ["deploy"],
            "approval_required_actions": [],
        },
        "resources": [],
        "budget": {"max_tokens": 1000},
        "duration_seconds": 600,
        "priority": 3,
        "required_capabilities": [],
    }


@pytest.fixture
def scheduler_db(tmp_path):
    engine = _engine(tmp_path / "scheduler.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        organization = OrganizationModel(name="Scheduler org")
        db.add(organization)
        db.flush()
        workspace = WorkspaceModel(
            organization_id=organization.id, name="Scheduler workspace"
        )
        db.add(workspace)
        db.flush()
        project = ProjectModel(workspace_id=workspace.id, name="Scheduler project")
        worker = WorkerModel(
            name="scheduler-worker",
            token_hash=_token_hash(TOKEN),
            token_prefix=TOKEN[:8],
            token_expires_at=NOW + timedelta(days=30),
            capabilities=[],
            max_concurrency=2,
            status="online",
            simulation=0,
            global_access=1,
        )
        db.add_all([project, worker])
        db.commit()
        identifiers = {"project_id": project.id, "worker_id": worker.id}
    try:
        yield factory, identifiers
    finally:
        engine.dispose()


def _automation(
    db: Session,
    project_id: str,
    *,
    due: datetime | None,
    policy: str = "run_once",
    interval: int = 3600,
    max_concurrent: int = 1,
    name: str = "Routine",
) -> AutomationModel:
    row = AutomationModel(
        project_id=project_id,
        name=name,
        schedule_kind="interval",
        schedule_expression=str(interval),
        timezone="Europe/Paris",
        mission_template=_mission_template(),
        enabled=1,
        catchup_policy=policy,
        max_concurrent_runs=max_concurrent,
        next_run_at=due,
    )
    db.add(row)
    db.commit()
    return row


def _lease(factory, worker_id: str, holder: str = "a" * 32, now=NOW):
    with factory() as db:
        return acquire_scheduler_lease(
            db, worker_id=worker_id, holder_id=holder, now=now
        )


def _tick(factory, worker_id: str, holder: str, fence: int, now=NOW, limit=25):
    with factory() as db:
        return run_scheduler_tick(
            db,
            worker_id=worker_id,
            holder_id=holder,
            fencing_token=fence,
            now=now,
            limit=limit,
        )


def test_file_sqlite_elects_exactly_one_concurrent_scheduler(scheduler_db):
    factory, ids = scheduler_db
    barrier = Barrier(2)

    def contender(holder: str) -> tuple[str, int | None]:
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                lease = acquire_scheduler_lease(
                    db, worker_id=ids["worker_id"], holder_id=holder, now=NOW
                )
            except SchedulerLeaseBusy:
                return "busy", None
            return "leader", lease.fencing_token

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(contender, ("a" * 32, "b" * 32)))

    assert sorted(state for state, _ in results) == ["busy", "leader"]
    assert [fence for state, fence in results if state == "leader"] == [1]
    with factory() as db:
        assert db.query(SchedulerLeaseModel).count() == 1


def test_expired_lease_increments_fence_and_rejects_stale_holder(scheduler_db):
    factory, ids = scheduler_db
    first = _lease(factory, ids["worker_id"], "a" * 32)

    with factory() as db:
        with pytest.raises(SchedulerLeaseBusy):
            acquire_scheduler_lease(
                db,
                worker_id=ids["worker_id"],
                holder_id="b" * 32,
                now=NOW + timedelta(seconds=44),
            )

    second = _lease(
        factory,
        ids["worker_id"],
        "b" * 32,
        now=NOW + timedelta(seconds=46),
    )
    assert (first.fencing_token, second.fencing_token) == (1, 2)
    with pytest.raises(SchedulerFenceRejected):
        _tick(
            factory,
            ids["worker_id"],
            "a" * 32,
            first.fencing_token,
            now=NOW + timedelta(seconds=46),
        )


def test_catchup_skip_discards_backlog_and_run_once_collapses_it(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        skipped = _automation(
            db,
            ids["project_id"],
            due=NOW - timedelta(minutes=5),
            policy="skip",
            interval=60,
            name="Skip",
        )
        collapsed = _automation(
            db,
            ids["project_id"],
            due=NOW - timedelta(minutes=5),
            policy="run_once",
            interval=60,
            name="Run once",
        )
        skipped_id, collapsed_id = skipped.id, collapsed.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(
        factory, ids["worker_id"], "a" * 32, lease.fencing_token, limit=10
    )
    assert result.catchup_skipped == 1
    assert result.launched == 1
    with factory() as db:
        assert (
            db.query(AutomationRunModel).filter_by(automation_id=skipped_id).count()
            == 1
        )
        skipped_run = (
            db.query(AutomationRunModel).filter_by(automation_id=skipped_id).one()
        )
        assert skipped_run.outcome == "skipped_catchup"
        assert skipped_run.task_id is None
        assert skipped_run.completion_status is None
        occurrences = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=collapsed_id)
            .all()
        )
        assert len(occurrences) == 1
        assert occurrences[0].scheduled_for == NOW - timedelta(minutes=5)
        assert db.get(AutomationModel, skipped_id).next_run_at == NOW + timedelta(
            minutes=1
        )
        assert db.get(AutomationModel, collapsed_id).next_run_at == NOW + timedelta(
            minutes=1
        )
        assert (
            db.query(EventModel)
            .filter_by(type="automation.run_materialized")
            .filter(EventModel.payload["outcome"].as_string() == "skipped_catchup")
            .count()
            == 1
        )


def test_skip_policy_only_skips_beyond_its_explicit_grace(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        inside_id = _automation(
            db,
            ids["project_id"],
            due=NOW - timedelta(seconds=CATCHUP_GRACE_SECONDS),
            policy="skip",
            interval=60,
            name="Dans la grâce",
        ).id
        outside_id = _automation(
            db,
            ids["project_id"],
            due=NOW - timedelta(seconds=CATCHUP_GRACE_SECONDS + 1),
            policy="skip",
            interval=60,
            name="Hors grâce",
        ).id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(
        factory, ids["worker_id"], "a" * 32, lease.fencing_token, limit=10
    )

    assert result.launched == 1
    assert result.catchup_skipped == 1
    with factory() as db:
        inside = db.query(AutomationRunModel).filter_by(automation_id=inside_id).one()
        outside = db.query(AutomationRunModel).filter_by(automation_id=outside_id).one()
        assert inside.outcome == "launched"
        assert inside.task_id is not None
        assert outside.outcome == "skipped_catchup"
        assert outside.task_id is None


def test_capacity_is_applied_and_consumes_the_due_occurrence(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        automation = _automation(db, ids["project_id"], due=NOW)
        active_task = TaskModel(
            project_id=ids["project_id"],
            title="Déjà active",
            status="in_progress",
            is_mission=1,
        )
        db.add(active_task)
        db.flush()
        active_attempt = TaskRunModel(
            task_id=active_task.id,
            status="running",
            attempt_number=1,
            fencing_token=1,
        )
        db.add(active_attempt)
        db.flush()
        active_task.active_run_id = active_attempt.id
        db.add(
            AutomationRunModel(
                automation_id=automation.id,
                fire_key="f" * 32,
                scheduled_for=NOW - timedelta(hours=1),
                fired_at=NOW - timedelta(hours=1),
                task_id=active_task.id,
                trigger_kind="manual",
                outcome="launched",
            )
        )
        db.commit()
        automation_id = automation.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert result.skipped_concurrency == 1
    with factory() as db:
        scheduled = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, trigger_kind="schedule")
            .one()
        )
        assert scheduled.outcome == "skipped_concurrency"
        assert scheduled.task_id is None
        assert db.query(TaskModel).count() == 1


def test_reconnect_after_uncertain_tick_does_not_start_twice(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        automation_id = _automation(db, ids["project_id"], due=NOW).id

    first = _lease(factory, ids["worker_id"], "a" * 32)
    assert _tick(
        factory, ids["worker_id"], "a" * 32, first.fencing_token
    ).launched == 1

    # Le premier tick a réussi mais sa réponse est supposée perdue. Après
    # expiration, un autre processus reprend et relit le curseur persistant.
    second = _lease(
        factory,
        ids["worker_id"],
        "b" * 32,
        now=NOW + timedelta(seconds=46),
    )
    replay = _tick(
        factory,
        ids["worker_id"],
        "b" * 32,
        second.fencing_token,
        now=NOW + timedelta(seconds=46),
    )
    assert replay.launched == 0
    with factory() as db:
        assert (
            db.query(AutomationRunModel).filter_by(automation_id=automation_id).count()
            == 1
        )
        assert db.query(TaskModel).count() == 1


def test_replay_heals_a_legacy_stale_schedule_cursor(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        automation = _automation(db, ids["project_id"], due=NOW)
        db.add(
            AutomationRunModel(
                automation_id=automation.id,
                fire_key=fire_key(automation.id, NOW),
                scheduled_for=NOW,
                fired_at=NOW,
                trigger_kind="schedule",
                outcome="skipped_concurrency",
                detail="ligne importée avec un curseur ancien",
            )
        )
        db.commit()
        automation_id = automation.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert result.replayed == 1
    assert result.launched == 0
    with factory() as db:
        automation = db.get(AutomationModel, automation_id)
        assert automation.next_run_at == NOW + timedelta(hours=1)
        assert db.query(AutomationRunModel).count() == 1
        assert db.query(TaskModel).count() == 0


def test_invalid_routine_is_durable_scrubbed_and_does_not_starve_next_due(
    scheduler_db,
):
    factory, ids = scheduler_db
    secret = "SECRET-ne-doit-jamais-sortir"
    with factory() as db:
        invalid = _automation(
            db,
            ids["project_id"],
            due=NOW,
            name="Corrompue",
        )
        invalid.schedule_kind = "cron"
        invalid.schedule_expression = secret
        invalid.failure_threshold = 2
        healthy = _automation(
            db,
            ids["project_id"],
            due=NOW,
            name="Saine",
        )
        db.commit()
        invalid_id, healthy_id = invalid.id, healthy.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(
        factory, ids["worker_id"], "a" * 32, lease.fencing_token, limit=10
    )

    assert result.failed == 1
    assert result.disabled_after_failures == 0
    assert result.launched == 1
    with factory() as db:
        broken = db.get(AutomationModel, invalid_id)
        assert broken.enabled == 1
        assert broken.next_run_at == NOW + timedelta(
            seconds=INVALID_CONFIGURATION_RETRY_SECONDS
        )
        assert broken.consecutive_failures == 1
        failed = (
            db.query(AutomationRunModel).filter_by(automation_id=invalid_id).one()
        )
        assert failed.outcome == "failed"
        assert failed.task_id is None
        assert failed.detail == "configuration de routine invalide"
        assert secret not in failed.detail
        assert (
            db.query(AutomationRunModel)
            .filter_by(automation_id=healthy_id, outcome="launched")
            .count()
            == 1
        )
        assert db.query(AlertModel).filter_by(automation_id=invalid_id).count() == 0
        serialized_events = " ".join(
            f"{event.type} {event.payload!r}"
            for event in db.query(EventModel)
            .filter_by(project_id=ids["project_id"])
            .all()
        )
        assert secret not in serialized_events
        materialized = (
            db.query(EventModel)
            .filter_by(type="automation.run_materialized")
            .filter(EventModel.payload["automation_id"].as_string() == invalid_id)
            .one()
        )
        assert materialized.payload["reason_code"] == "invalid_configuration"


def test_invalid_template_advances_safely_and_stops_at_default_threshold(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        invalid = _automation(
            db,
            ids["project_id"],
            due=NOW,
            name="Gabarit corrompu",
            interval=60,
        )
        invalid.mission_template = {
            "title": "SECRET-gabarit",
            "objective": "incomplet",
        }
        db.commit()
        automation_id = invalid.id

    holder = "a" * 32
    lease = _lease(factory, ids["worker_id"], holder, now=NOW)
    moments = [
        NOW,
        NOW + timedelta(seconds=61),
        NOW + timedelta(seconds=122),
    ]
    results = []
    for index, moment in enumerate(moments):
        if index:
            lease = _lease(factory, ids["worker_id"], holder, now=moment)
        results.append(
            _tick(
                factory,
                ids["worker_id"],
                holder,
                lease.fencing_token,
                now=moment,
                limit=5,
            )
        )

    assert [result.failed for result in results] == [1, 1, 1]
    assert [result.disabled_after_failures for result in results] == [0, 0, 1]
    with factory() as db:
        automation = db.get(AutomationModel, automation_id)
        assert automation.consecutive_failures == 3
        assert automation.failure_threshold == 3
        assert automation.enabled == 0
        assert automation.next_run_at is None
        failures = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, outcome="failed")
            .order_by(AutomationRunModel.scheduled_for)
            .all()
        )
        assert len(failures) == 3
        assert len({run.fire_key for run in failures}) == 3
        assert all(run.detail == "configuration de routine invalide" for run in failures)
        assert db.query(AlertModel).filter_by(automation_id=automation_id).count() == 1


def test_reused_session_reloads_due_state_instead_of_using_identity_map(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        automation_id = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
        ).id

    holder = "a" * 32
    with factory() as reused:
        lease = acquire_scheduler_lease(
            reused, worker_id=ids["worker_id"], holder_id=holder, now=NOW
        )
        cached = reused.get(AutomationModel, automation_id)
        assert cached.next_run_at == NOW + timedelta(days=1)
        with factory() as concurrent:
            current = concurrent.get(AutomationModel, automation_id)
            current.next_run_at = NOW
            concurrent.commit()

        result = run_scheduler_tick(
            reused,
            worker_id=ids["worker_id"],
            holder_id=holder,
            fencing_token=lease.fencing_token,
            now=NOW,
        )

    assert result.launched == 1
    with factory() as db:
        assert (
            db.query(AutomationRunModel).filter_by(automation_id=automation_id).count()
            == 1
        )


def test_reused_session_reloads_fence_after_external_takeover(scheduler_db):
    factory, ids = scheduler_db
    holder = "a" * 32
    with factory() as stale:
        first = acquire_scheduler_lease(
            stale, worker_id=ids["worker_id"], holder_id=holder, now=NOW
        )
        cached = stale.get(SchedulerLeaseModel, "automation-scheduler")
        assert cached.fencing_token == first.fencing_token
        second = _lease(
            factory,
            ids["worker_id"],
            "b" * 32,
            now=NOW + timedelta(seconds=46),
        )
        assert second.fencing_token == first.fencing_token + 1

        with pytest.raises(SchedulerFenceRejected):
            run_scheduler_tick(
                stale,
                worker_id=ids["worker_id"],
                holder_id=holder,
                fencing_token=first.fencing_token,
                now=NOW + timedelta(seconds=46),
            )


def test_same_holder_renewal_never_shortens_the_scheduler_lease(scheduler_db):
    factory, ids = scheduler_db
    holder = "a" * 32
    first = _lease(factory, ids["worker_id"], holder, now=NOW)
    recent = _lease(
        factory,
        ids["worker_id"],
        holder,
        now=NOW + timedelta(seconds=20),
    )
    stale = _lease(
        factory,
        ids["worker_id"],
        holder,
        now=NOW + timedelta(seconds=10),
    )

    assert first.acquired is True
    assert recent.acquired is False
    assert stale.acquired is False
    assert stale.fencing_token == recent.fencing_token
    assert stale.lease_expires_at == recent.lease_expires_at


def _terminal_occurrence(
    db: Session,
    automation: AutomationModel,
    *,
    number: int,
    status: str,
    fired_at: datetime,
) -> TaskRunModel:
    is_terminal = status in TERMINAL_RUN_STATES
    task = TaskModel(
        project_id=automation.project_id,
        title=f"Tentative {number}",
        status=(
            "done"
            if status == "succeeded"
            else "failed" if is_terminal else "running"
        ),
        is_mission=1,
    )
    db.add(task)
    db.flush()
    attempt = TaskRunModel(
        task_id=task.id,
        status=status,
        attempt_number=1,
        fencing_token=1,
        finished_at=fired_at + timedelta(seconds=1) if is_terminal else None,
    )
    db.add(attempt)
    db.flush()
    db.add(
        AutomationRunModel(
            automation_id=automation.id,
            fire_key=f"{number:032x}",
            scheduled_for=fired_at,
            fired_at=fired_at,
            task_id=task.id,
            trigger_kind="schedule",
            outcome="launched",
        )
    )
    return attempt


def test_terminal_reconciliation_resets_success_and_stops_after_three_failures(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        stopped = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Fragile",
        )
        reset = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Rétablie",
        )
        for number in range(1, 4):
            _terminal_occurrence(
                db,
                stopped,
                number=number,
                status="failed",
                fired_at=NOW - timedelta(minutes=10 - number),
            )
        _terminal_occurrence(
            db,
            reset,
            number=11,
            status="failed",
            fired_at=NOW - timedelta(minutes=6),
        )
        _terminal_occurrence(
            db,
            reset,
            number=12,
            status="succeeded",
            fired_at=NOW - timedelta(minutes=5),
        )
        db.commit()
        stopped_id, reset_id = stopped.id, reset.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert result.reconciled == 5
    assert result.disabled_after_failures == 1
    with factory() as db:
        fragile = db.get(AutomationModel, stopped_id)
        recovered = db.get(AutomationModel, reset_id)
        assert fragile.enabled == 0
        assert fragile.next_run_at is None
        assert fragile.consecutive_failures == 3
        assert recovered.enabled == 1
        assert recovered.consecutive_failures == 0
        alert = db.query(AlertModel).filter_by(automation_id=stopped_id).one()
        assert alert.kind == "automation.repeated_failures"
        assert alert.severity == "critical"
        assert (
            db.query(EventModel)
            .filter_by(type="automation.disabled_after_failures")
            .count()
            == 1
        )
        assert (
            db.query(AutomationRunModel)
            .filter(AutomationRunModel.completion_observed_at.is_not(None))
            .count()
            == 5
        )

    # Une reprise ne recompte aucune terminaison et ne duplique pas l'alerte.
    repeated = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert repeated.reconciled == 0
    with factory() as db:
        assert db.query(AlertModel).filter_by(automation_id=stopped_id).count() == 1


def test_terminal_reconciliation_follows_occurrence_order_not_finish_order(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        late_failure = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Échec tardif dans la séquence",
        )
        late_success = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Succès tardif dans la séquence",
        )
        early_success = _terminal_occurrence(
            db,
            late_failure,
            number=101,
            status="running",
            fired_at=NOW - timedelta(minutes=2),
        )
        _terminal_occurrence(
            db,
            late_failure,
            number=102,
            status="failed",
            fired_at=NOW - timedelta(minutes=1),
        )
        early_failure = _terminal_occurrence(
            db,
            late_success,
            number=201,
            status="running",
            fired_at=NOW - timedelta(minutes=2),
        )
        _terminal_occurrence(
            db,
            late_success,
            number=202,
            status="succeeded",
            fired_at=NOW - timedelta(minutes=1),
        )
        db.commit()
        late_failure_id = late_failure.id
        late_success_id = late_success.id
        early_success_id = early_success.id
        early_failure_id = early_failure.id

    lease = _lease(factory, ids["worker_id"])
    first = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert first.reconciled == 0
    with factory() as db:
        assert db.get(AutomationModel, late_failure_id).consecutive_failures == 0
        assert db.get(AutomationModel, late_success_id).consecutive_failures == 0
        successful_attempt = db.get(TaskRunModel, early_success_id)
        failed_attempt = db.get(TaskRunModel, early_failure_id)
        successful_attempt.status = "succeeded"
        successful_attempt.finished_at = NOW
        failed_attempt.status = "failed"
        failed_attempt.finished_at = NOW
        db.commit()

    second = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert second.reconciled == 4
    with factory() as db:
        # Succès ancien puis échec récent : le suffixe contient un échec.
        assert db.get(AutomationModel, late_failure_id).consecutive_failures == 1
        # Échec ancien puis succès récent : le succès remet bien le suffixe à zéro.
        assert db.get(AutomationModel, late_success_id).consecutive_failures == 0


def test_configuration_failure_waits_for_earlier_launched_occurrence(scheduler_db):
    factory, ids = scheduler_db
    with factory() as db:
        automation = _automation(
            db,
            ids["project_id"],
            due=NOW,
            name="Configuration après tâche en cours",
            interval=60,
            max_concurrent=2,
        )
        earlier = _terminal_occurrence(
            db,
            automation,
            number=301,
            status="running",
            fired_at=NOW - timedelta(minutes=1),
        )
        automation.mission_template = {
            "title": "Gabarit corrompu",
            "execution_mode": "inconnu",
        }
        db.commit()
        automation_id = automation.id
        earlier_id = earlier.id

    lease = _lease(factory, ids["worker_id"])
    first = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert first.failed == 1
    assert first.reconciled == 0
    with factory() as db:
        automation = db.get(AutomationModel, automation_id)
        failure = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, outcome="failed")
            .one()
        )
        assert automation.consecutive_failures == 0
        assert failure.completion_status == "failed"
        assert failure.completion_observed_at is None
        attempt = db.get(TaskRunModel, earlier_id)
        attempt.status = "succeeded"
        attempt.finished_at = NOW
        db.commit()

    second = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert second.reconciled == 2
    with factory() as db:
        automation = db.get(AutomationModel, automation_id)
        ordered = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id)
            .order_by(AutomationRunModel.scheduled_for, AutomationRunModel.id)
            .all()
        )
        assert automation.consecutive_failures == 1
        assert [item.completion_status for item in ordered] == ["succeeded", "failed"]
        assert all(item.completion_observed_at == NOW for item in ordered)


def test_reconciliation_uses_initial_attempt_even_after_a_successful_retry(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        automation = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Retry stable",
        )
        task = TaskModel(
            project_id=ids["project_id"],
            title="Mission retentée",
            status="done",
            is_mission=1,
        )
        db.add(task)
        db.flush()
        initial = TaskRunModel(
            task_id=task.id,
            status="failed",
            attempt_number=1,
            fencing_token=1,
            finished_at=NOW - timedelta(minutes=2),
        )
        retry = TaskRunModel(
            task_id=task.id,
            status="succeeded",
            attempt_number=2,
            fencing_token=2,
            finished_at=NOW - timedelta(minutes=1),
        )
        db.add_all([initial, retry])
        db.flush()
        task.active_run_id = retry.id
        occurrence = AutomationRunModel(
            automation_id=automation.id,
            fire_key="d" * 32,
            scheduled_for=NOW - timedelta(minutes=3),
            fired_at=NOW - timedelta(minutes=3),
            task_id=task.id,
            trigger_kind="schedule",
            outcome="launched",
        )
        db.add(occurrence)
        db.commit()
        automation_id, occurrence_id = automation.id, occurrence.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)

    assert result.reconciled == 1
    with factory() as db:
        occurrence = db.get(AutomationRunModel, occurrence_id)
        automation = db.get(AutomationModel, automation_id)
        assert occurrence.completion_status == "failed"
        assert occurrence.completion_observed_at == NOW
        assert automation.consecutive_failures == 1
        assert automation.enabled == 1

    # La classification est écrite une fois : ajouter ou modifier un retry ne
    # réinterprète jamais rétroactivement l'occurrence d'origine.
    repeated = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)
    assert repeated.reconciled == 0


def test_interrupted_initial_attempt_counts_as_failure_and_can_stop_routine(
    scheduler_db,
):
    factory, ids = scheduler_db
    with factory() as db:
        automation = _automation(
            db,
            ids["project_id"],
            due=NOW + timedelta(days=1),
            name="Interrompue",
        )
        automation.failure_threshold = 1
        _terminal_occurrence(
            db,
            automation,
            number=31,
            status="interrupted",
            fired_at=NOW - timedelta(minutes=1),
        )
        db.commit()
        automation_id = automation.id

    lease = _lease(factory, ids["worker_id"])
    result = _tick(factory, ids["worker_id"], "a" * 32, lease.fencing_token)

    assert result.reconciled == 1
    assert result.disabled_after_failures == 1
    with factory() as db:
        automation = db.get(AutomationModel, automation_id)
        occurrence = (
            db.query(AutomationRunModel).filter_by(automation_id=automation_id).one()
        )
        assert automation.consecutive_failures == 1
        assert automation.enabled == 0
        assert occurrence.completion_status == "interrupted"
        assert db.query(AlertModel).filter_by(automation_id=automation_id).count() == 1


def test_scheduler_routes_require_worker_token_and_fence(scheduler_db):
    factory, ids = scheduler_db
    application = FastAPI()
    application.include_router(router)

    def override_db():
        with factory() as db:
            yield db

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        path = f"/workers/{ids['worker_id']}/automation-scheduler"
        unauthenticated = client.post(
            f"{path}/lease", json={"holder_id": "a" * 32}
        )
        assert unauthenticated.status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        lease = client.post(
            f"{path}/lease", headers=headers, json={"holder_id": "a" * 32}
        )
        assert lease.status_code == 200, lease.text
        fence = lease.json()["fencing_token"]
        assert client.post(
            f"{path}/tick",
            headers=headers,
            json={"holder_id": "a" * 32, "limit": 1},
        ).status_code == 409
        tick = client.post(
            f"{path}/tick",
            headers={**headers, "X-Scheduler-Fencing-Token": str(fence)},
            json={"holder_id": "a" * 32, "limit": 1},
        )
        assert tick.status_code == 200, tick.text


def test_project_scoped_worker_is_forbidden_from_every_scheduler_operation(
    scheduler_db,
):
    factory, ids = scheduler_db
    scoped_token = "project-scoped-scheduler-token"
    with factory() as db:
        scoped = WorkerModel(
            name="project-scoped-worker",
            token_hash=_token_hash(scoped_token),
            token_prefix=scoped_token[:8],
            token_expires_at=NOW + timedelta(days=30),
            capabilities=[],
            max_concurrency=1,
            status="online",
            simulation=0,
            project_id=ids["project_id"],
            global_access=0,
        )
        db.add(scoped)
        db.commit()
        scoped_id = scoped.id

    application = FastAPI()
    application.include_router(router)

    def override_db():
        with factory() as db:
            yield db

    application.dependency_overrides[get_db] = override_db
    base = f"/workers/{scoped_id}/automation-scheduler"
    headers = {
        "Authorization": f"Bearer {scoped_token}",
        "X-Scheduler-Fencing-Token": "1",
    }
    with TestClient(application) as client:
        for path, body in (
            ("/lease", {"holder_id": "a" * 32}),
            ("/tick", {"holder_id": "a" * 32, "limit": 1}),
            ("/lease/release", {"holder_id": "a" * 32}),
        ):
            response = client.post(f"{base}{path}", headers=headers, json=body)
            assert response.status_code == 403
            assert "privilège global" in response.json()["detail"]


def test_production_app_exposes_the_authenticated_scheduler_protocol():
    from acp_api.main import app

    paths = app.openapi()["paths"]
    base = "/workers/{worker_id}/automation-scheduler"
    assert "post" in paths[f"{base}/lease"]
    assert "post" in paths[f"{base}/tick"]
    assert "post" in paths[f"{base}/lease/release"]
    tick_parameters = paths[f"{base}/tick"]["post"]["parameters"]
    assert any(
        parameter["in"] == "header"
        and parameter["name"] == "X-Scheduler-Fencing-Token"
        for parameter in tick_parameters
    )


def test_legacy_sqlite_is_upgraded_additively(tmp_path):
    engine = _engine(tmp_path / "legacy-scheduler.db")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE automations ("
                "id VARCHAR(36) PRIMARY KEY, created_at DATETIME NOT NULL, "
                "project_id VARCHAR(36) NOT NULL, name VARCHAR(200) NOT NULL, "
                "schedule_kind VARCHAR(20) NOT NULL, "
                "schedule_expression VARCHAR(200) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE automation_runs ("
                "id VARCHAR(36) PRIMARY KEY, created_at DATETIME NOT NULL, "
                "automation_id VARCHAR(36) NOT NULL, fire_key VARCHAR(64) NOT NULL, "
                "scheduled_for DATETIME NOT NULL, fired_at DATETIME NOT NULL, "
                "outcome VARCHAR(30) NOT NULL)"
            )
        )
    Base.metadata.create_all(engine)
    engine_module._upgrade_sqlite_schema(engine)
    schema = inspect(engine)
    automation_columns = {
        column["name"] for column in schema.get_columns("automations")
    }
    run_columns = {
        column["name"] for column in schema.get_columns("automation_runs")
    }
    assert {"consecutive_failures", "failure_threshold"} <= automation_columns
    assert {"completion_observed_at", "completion_status"} <= run_columns
    assert "scheduler_leases" in schema.get_table_names()
    assert ("scheduler_key",) in {
        tuple(index.get("column_names") or ())
        for index in schema.get_indexes("scheduler_leases")
        if index.get("unique")
    } | {
        tuple(item.get("column_names") or ())
        for item in schema.get_unique_constraints("scheduler_leases")
    }
    engine.dispose()
