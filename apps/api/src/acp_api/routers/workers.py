"""Enregistrement, authentification et présence des workers distants."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import (
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerRegistrationRequest,
    WorkerRegistrationResponse,
    WorkerSnapshot,
    WorkerStatus,
)
from acp_database.models import (
    AgentInstanceModel,
    TaskModel,
    TaskRunModel,
    WorkerLeaseModel,
    WorkerModel,
)

from ..deps import get_db

router = APIRouter(prefix="/workers", tags=["workers"])

HEARTBEAT_INTERVAL_SECONDS = 15
WORKER_LEASE_SECONDS = 45
TOKEN_LIFETIME_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_hash(token: str) -> str:
    pepper = os.environ.get("ACP_WORKER_TOKEN_PEPPER", "")
    return hashlib.sha256(f"{pepper}:{token}".encode()).hexdigest()


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Jeton worker manquant")
    return token


def authenticate_worker(
    db: Session, worker_id: str, authorization: str | None
) -> WorkerModel:
    worker = db.get(WorkerModel, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker introuvable")
    token = _bearer_token(authorization)
    if worker.status == WorkerStatus.REVOKED.value:
        raise HTTPException(status_code=403, detail="Worker révoqué")
    if _as_utc(worker.token_expires_at) <= utcnow():
        raise HTTPException(status_code=401, detail="Jeton worker expiré")
    if not hmac.compare_digest(worker.token_hash, _token_hash(token)):
        raise HTTPException(status_code=401, detail="Jeton worker invalide")
    return worker


def worker_snapshot(worker: WorkerModel) -> WorkerSnapshot:
    return WorkerSnapshot(
        id=worker.id,
        name=worker.name,
        capabilities=worker.capabilities or [],
        max_concurrency=worker.max_concurrency,
        active_runs=worker.active_runs,
        status=worker.status,
        simulation=bool(worker.simulation),
        metadata=worker.metadata_json or {},
        last_seen_at=worker.last_seen_at,
        lease_expires_at=worker.lease_expires_at,
        token_expires_at=worker.token_expires_at,
        created_at=worker.created_at,
    )


def expire_task_leases(db: Session) -> int:
    """Libère et remet en file les runs abandonnés après expiration du lease."""
    now = utcnow()
    expired = 0
    leases = db.query(WorkerLeaseModel).filter_by(status="active").all()
    for lease in leases:
        if _as_utc(lease.lease_expires_at) > now:
            continue
        lease.status = "expired"
        run = db.get(TaskRunModel, lease.task_run_id)
        if run is not None and run.status == "running":
            run.status = "failed"
            run.finished_at = now
            run.logs = list(run.logs or []) + [
                {"level": "error", "message": "Lease worker expiré; tâche remise en file"}
            ]
        task = db.get(TaskModel, lease.task_id)
        if task is not None and task.status in {"planning", "in_progress", "review"}:
            task.status = "queued"
            task.workflow_step = None
        if run is not None and run.agent_instance_id:
            agent = db.get(AgentInstanceModel, run.agent_instance_id)
            if agent is not None:
                agent.status = "idle"
        expired += 1
    if expired:
        db.flush()
        worker_ids = {lease.worker_id for lease in leases}
        for worker_id in worker_ids:
            worker = db.get(WorkerModel, worker_id)
            if worker is not None:
                worker.active_runs = (
                    db.query(WorkerLeaseModel)
                    .filter_by(worker_id=worker_id, status="active")
                    .count()
                )
        db.commit()
    return expired


def _mark_stale_workers(db: Session) -> None:
    expire_task_leases(db)
    now = utcnow()
    changed = False
    for worker in db.query(WorkerModel).filter(WorkerModel.status != "revoked").all():
        if worker.lease_expires_at and _as_utc(worker.lease_expires_at) <= now:
            worker.status = WorkerStatus.OFFLINE.value
            changed = True
    if changed:
        db.commit()


@router.post("/register", response_model=WorkerRegistrationResponse, status_code=201)
def register_worker(
    body: WorkerRegistrationRequest,
    db: Session = Depends(get_db),
    registration_token: str | None = Header(
        default=None, alias="X-Worker-Registration-Token"
    ),
):
    expected = os.environ.get("ACP_WORKER_REGISTRATION_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="ACP_WORKER_REGISTRATION_TOKEN doit être configuré sur l'API",
        )
    if not registration_token or not hmac.compare_digest(registration_token, expected):
        raise HTTPException(status_code=401, detail="Jeton d'enregistrement invalide")

    now = utcnow()
    raw_token = secrets.token_urlsafe(32)
    expire_task_leases(db)
    worker = db.query(WorkerModel).filter_by(name=body.name).first()
    if worker is not None and worker.active_runs > 0:
        raise HTTPException(
            status_code=409,
            detail="Impossible de renouveler un worker avec des runs actifs",
        )
    values = {
        "token_hash": _token_hash(raw_token),
        "token_prefix": raw_token[:8],
        "token_expires_at": now + timedelta(days=TOKEN_LIFETIME_DAYS),
        "capabilities": [capability.value for capability in body.capabilities],
        "max_concurrency": body.max_concurrency,
        "active_runs": 0,
        "status": WorkerStatus.ONLINE.value,
        "simulation": int(body.simulation),
        "metadata_json": body.metadata,
        "last_seen_at": now,
        "lease_expires_at": now + timedelta(seconds=WORKER_LEASE_SECONDS),
    }
    if worker is None:
        worker = WorkerModel(name=body.name, **values)
        db.add(worker)
    else:
        for key, value in values.items():
            setattr(worker, key, value)
    db.commit()
    db.refresh(worker)
    return WorkerRegistrationResponse(
        worker_id=worker.id,
        token=raw_token,
        token_expires_at=worker.token_expires_at,
        heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
    )


@router.post("/{worker_id}/heartbeat", response_model=WorkerHeartbeatResponse)
def heartbeat(
    worker_id: str,
    body: WorkerHeartbeatRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    worker = authenticate_worker(db, worker_id, authorization)
    expire_task_leases(db)
    now = utcnow()
    if body.capabilities is not None:
        worker.capabilities = [capability.value for capability in body.capabilities]
    if body.max_concurrency is not None:
        worker.max_concurrency = body.max_concurrency
    if body.simulation is not None:
        worker.simulation = int(body.simulation)
    active_runs = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker.id, status="active")
        .count()
    )
    worker.active_runs = active_runs
    worker.status = (
        WorkerStatus.BUSY.value
        if active_runs >= worker.max_concurrency
        else WorkerStatus.ONLINE.value
    )
    worker.last_seen_at = now
    worker.lease_expires_at = now + timedelta(seconds=WORKER_LEASE_SECONDS)
    db.commit()
    return WorkerHeartbeatResponse(
        worker_id=worker.id,
        status=worker.status,
        server_time=now,
        lease_expires_at=worker.lease_expires_at,
        active_runs=active_runs,
    )


@router.get("", response_model=list[WorkerSnapshot])
def list_workers(db: Session = Depends(get_db)):
    _mark_stale_workers(db)
    return [worker_snapshot(worker) for worker in db.query(WorkerModel).all()]


@router.get("/{worker_id}", response_model=WorkerSnapshot)
def get_worker(worker_id: str, db: Session = Depends(get_db)):
    _mark_stale_workers(db)
    worker = db.get(WorkerModel, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker introuvable")
    return worker_snapshot(worker)
