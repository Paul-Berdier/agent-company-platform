"""API worker authentifiée du planificateur d'automatisations."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..deps import get_db
from ..scheduler_service import (
    SchedulerFenceRejected,
    SchedulerLeaseBusy,
    acquire_scheduler_lease,
    release_scheduler_lease,
    run_scheduler_tick,
)
from .workers import authenticate_worker

router = APIRouter(
    prefix="/workers/{worker_id}/automation-scheduler",
    tags=["automation-scheduler"],
)


class _StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SchedulerLeaseRequest(_StrictBody):
    holder_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9]+$")


class SchedulerTickRequest(SchedulerLeaseRequest):
    limit: int = Field(default=25, ge=1, le=100)


class SchedulerLeaseResponse(_StrictBody):
    worker_id: str
    holder_id: str
    fencing_token: int
    lease_expires_at: datetime
    acquired: bool


class SchedulerTickResponse(_StrictBody):
    fencing_token: int
    reconciled: int
    disabled_after_failures: int
    examined: int
    launched: int
    replayed: int
    skipped_concurrency: int
    skipped_disabled: int
    catchup_skipped: int
    failed: int


def _worker(
    db: Session, worker_id: str, authorization: str | None
) -> None:
    worker = authenticate_worker(db, worker_id, authorization)
    if worker.global_access != 1:
        raise HTTPException(
            status_code=403,
            detail="Le planificateur exige un worker avec privilège global explicite",
        )


@router.post("/lease", response_model=SchedulerLeaseResponse)
def acquire_lease(
    worker_id: str,
    body: SchedulerLeaseRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _worker(db, worker_id, authorization)
    try:
        lease = acquire_scheduler_lease(
            db, worker_id=worker_id, holder_id=body.holder_id
        )
    except SchedulerLeaseBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SchedulerLeaseResponse(**lease.__dict__)


@router.post("/tick", response_model=SchedulerTickResponse)
def tick(
    worker_id: str,
    body: SchedulerTickRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    fencing_token: int | None = Header(
        default=None, alias="X-Scheduler-Fencing-Token"
    ),
):
    _worker(db, worker_id, authorization)
    if fencing_token is None or fencing_token < 1:
        raise HTTPException(status_code=409, detail="Fence planificateur requis")
    try:
        result = run_scheduler_tick(
            db,
            worker_id=worker_id,
            holder_id=body.holder_id,
            fencing_token=fencing_token,
            limit=body.limit,
        )
    except SchedulerFenceRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SchedulerTickResponse(fencing_token=fencing_token, **result.__dict__)


@router.post("/lease/release", status_code=204)
def release_lease(
    worker_id: str,
    body: SchedulerLeaseRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    fencing_token: int | None = Header(
        default=None, alias="X-Scheduler-Fencing-Token"
    ),
) -> Response:
    _worker(db, worker_id, authorization)
    if fencing_token is None or fencing_token < 1:
        raise HTTPException(status_code=409, detail="Fence planificateur requis")
    try:
        release_scheduler_lease(
            db,
            worker_id=worker_id,
            holder_id=body.holder_id,
            fencing_token=fencing_token,
        )
    except SchedulerFenceRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)
