"""Validation commune des écritures worker protégées par fencing token."""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from acp_database.models import TaskRunModel, WorkerLeaseModel

from .routers.workers import _as_utc, expire_task_leases, utcnow


ATTEMPT_FENCING_HEADER = "X-Attempt-Fencing-Token"
_FENCING_TOKEN_PATTERN = re.compile(r"^[1-9][0-9]{0,18}$")


def refused_attempt_fence() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="Fencing token absent, invalide ou périmé pour cette tentative",
    )


def parse_attempt_fencing_token(raw_value: str | None) -> int:
    if raw_value is None or _FENCING_TOKEN_PATTERN.fullmatch(raw_value) is None:
        raise refused_attempt_fence()
    return int(raw_value)


def _lock_run(db: Session, run_id: str) -> TaskRunModel | None:
    """Verrouille la tentative avant la décision d'écriture."""

    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            update(TaskRunModel)
            .where(TaskRunModel.id == run_id)
            .values(updated_at=TaskRunModel.updated_at)
        )
        return (
            db.query(TaskRunModel)
            .filter_by(id=run_id)
            .populate_existing()
            .first()
        )
    return (
        db.query(TaskRunModel)
        .filter_by(id=run_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def require_active_worker_attempt(
    db: Session,
    *,
    worker_id: str,
    run_id: str,
    fencing_token: int,
    lock: bool = False,
    expire_leases: bool = True,
) -> tuple[WorkerLeaseModel, TaskRunModel]:
    """Exige simultanément un lease actif et le fence exact du run."""

    if expire_leases:
        expire_task_leases(db)

    run = _lock_run(db, run_id) if lock else db.get(TaskRunModel, run_id)
    lease_query = db.query(WorkerLeaseModel).filter_by(
        worker_id=worker_id,
        task_run_id=run_id,
        status="active",
    )
    if lock and db.get_bind().dialect.name != "sqlite":
        lease_query = lease_query.with_for_update()
    lease = lease_query.populate_existing().first()

    if (
        run is None
        or lease is None
        or _as_utc(lease.lease_expires_at) <= utcnow()
        or fencing_token != run.fencing_token
    ):
        raise refused_attempt_fence()
    return lease, run
