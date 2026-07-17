"""Artefacts, verrous à lease et approbations humaines."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    Artifact,
    ArtifactCreate,
    LockAcquireRequest,
    LockOwnerRequest,
    ResourceLock,
)
from acp_database.models import (
    ApprovalModel,
    ArtifactModel,
    ProjectModel,
    ResourceLockModel,
    TaskModel,
    TaskRunModel,
    WorkerLeaseModel,
)

from ..deps import ensure_access, get_db, get_principal
from .workers import _as_utc, authenticate_worker, expire_task_leases, utcnow

router = APIRouter(tags=["operations"])


def _lock_contract(lock: ResourceLockModel) -> ResourceLock:
    return ResourceLock.model_validate(lock, from_attributes=True)


def _approval_contract(approval: ApprovalModel) -> ApprovalRequest:
    return ApprovalRequest.model_validate(approval, from_attributes=True)


def _artifact_contract(artifact: ArtifactModel) -> Artifact:
    return Artifact(
        id=artifact.id,
        project_id=artifact.project_id,
        task_run_id=artifact.task_run_id,
        worker_id=artifact.worker_id,
        kind=artifact.kind,
        path=artifact.path,
        checksum=artifact.checksum,
        size_bytes=artifact.size_bytes,
        metadata=artifact.metadata_json or {},
        created_at=artifact.created_at,
    )


def _require_active_run_lease(
    db: Session, worker_id: str, run_id: str
) -> WorkerLeaseModel:
    expire_task_leases(db)
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker_id, task_run_id=run_id, status="active")
        .first()
    )
    if lease is None:
        raise HTTPException(status_code=409, detail="Le worker ne possède pas ce run actif")
    return lease


@router.post("/locks/acquire", response_model=ResourceLock, status_code=201)
def acquire_lock(
    body: LockAcquireRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    authenticate_worker(db, body.worker_id, authorization)
    _require_active_run_lease(db, body.worker_id, body.owner_run_id)
    now = utcnow()
    lock = (
        db.query(ResourceLockModel)
        .filter_by(
            resource_type=body.resource_type.value,
            resource_key=body.resource_key,
        )
        .with_for_update()
        .first()
    )
    if lock is not None and lock.status == "active" and _as_utc(lock.lease_expires_at) > now:
        if lock.owner_run_id != body.owner_run_id:
            raise HTTPException(status_code=409, detail="Ressource déjà verrouillée")
    if lock is None:
        lock = ResourceLockModel(
            resource_type=body.resource_type.value,
            resource_key=body.resource_key,
            owner_run_id=body.owner_run_id,
            worker_id=body.worker_id,
        )
        db.add(lock)
    else:
        lock.owner_run_id = body.owner_run_id
        lock.worker_id = body.worker_id
    lock.status = "active"
    lock.last_renewed_at = now
    lock.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    db.commit()
    db.refresh(lock)
    return _lock_contract(lock)


@router.post("/locks/{lock_id}/renew", response_model=ResourceLock)
def renew_lock(
    lock_id: str,
    body: LockOwnerRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    authenticate_worker(db, body.worker_id, authorization)
    _require_active_run_lease(db, body.worker_id, body.owner_run_id)
    lock = db.get(ResourceLockModel, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock introuvable")
    now = utcnow()
    if (
        lock.worker_id != body.worker_id
        or lock.owner_run_id != body.owner_run_id
        or lock.status != "active"
        or _as_utc(lock.lease_expires_at) <= now
    ):
        raise HTTPException(status_code=409, detail="Ce lock n'est plus détenu par ce run")
    lock.last_renewed_at = now
    lock.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    db.commit()
    return _lock_contract(lock)


@router.post("/locks/{lock_id}/release", response_model=ResourceLock)
def release_lock(
    lock_id: str,
    body: LockOwnerRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    authenticate_worker(db, body.worker_id, authorization)
    lock = db.get(ResourceLockModel, lock_id)
    if lock is None:
        raise HTTPException(status_code=404, detail="Lock introuvable")
    if lock.worker_id != body.worker_id or lock.owner_run_id != body.owner_run_id:
        raise HTTPException(status_code=409, detail="Ce lock appartient à un autre run")
    lock.status = "released"
    db.commit()
    return _lock_contract(lock)


@router.get("/locks", response_model=list[ResourceLock])
def list_locks(active_only: bool = True, db: Session = Depends(get_db)):
    now = utcnow()
    query = db.query(ResourceLockModel)
    rows = query.filter_by(status="active").all() if active_only else query.all()
    return [
        _lock_contract(lock)
        for lock in rows
        if not active_only or _as_utc(lock.lease_expires_at) > now
    ]


def _expire_approvals(db: Session) -> None:
    now = utcnow()
    changed = False
    for approval in db.query(ApprovalModel).filter_by(status="WAITING_APPROVAL").all():
        if _as_utc(approval.expires_at) <= now:
            approval.status = ApprovalStatus.EXPIRED.value
            changed = True
    if changed:
        db.commit()


@router.post("/approvals", response_model=ApprovalRequest, status_code=201)
def request_approval(
    body: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    if db.get(ProjectModel, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if body.task_run_id:
        run = db.get(TaskRunModel, body.task_run_id)
        task = db.get(TaskModel, run.task_id) if run else None
        if task is None or task.project_id != body.project_id:
            raise HTTPException(status_code=400, detail="Task run hors du projet")
    values = body.model_dump(exclude={"expires_in_seconds"}, mode="json")
    approval = ApprovalModel(
        **values,
        status=ApprovalStatus.WAITING_APPROVAL.value,
        requested_by=principal or "development-user",
        expires_at=utcnow() + timedelta(seconds=body.expires_in_seconds),
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return _approval_contract(approval)


@router.get("/approvals", response_model=list[ApprovalRequest])
def list_approvals(
    project_id: str | None = None,
    status: ApprovalStatus | None = None,
    db: Session = Depends(get_db),
):
    _expire_approvals(db)
    query = db.query(ApprovalModel)
    if project_id:
        query = query.filter_by(project_id=project_id)
    if status:
        query = query.filter_by(status=status.value)
    return [_approval_contract(row) for row in query.all()]


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalRequest)
def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    _expire_approvals(db)
    approval = db.get(ApprovalModel, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approbation introuvable")
    ensure_access(db, principal, project_id=approval.project_id, minimum_role="owner")
    if approval.status != ApprovalStatus.WAITING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="Approbation déjà finalisée")
    approval.status = body.decision.value
    approval.decided_by = principal or "development-owner"
    approval.decision_comment = body.comment
    approval.decided_at = utcnow()
    db.commit()
    return _approval_contract(approval)


@router.post(
    "/workers/{worker_id}/artifacts", response_model=Artifact, status_code=201
)
def report_artifact(
    worker_id: str,
    body: ArtifactCreate,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    authenticate_worker(db, worker_id, authorization)
    lease = _require_active_run_lease(db, worker_id, body.task_run_id)
    task = db.get(TaskModel, lease.task_id)
    if task is None or task.project_id != body.project_id:
        raise HTTPException(status_code=400, detail="Artefact hors du projet du run")
    values = body.model_dump(exclude={"metadata"})
    artifact = ArtifactModel(
        **values,
        worker_id=worker_id,
        metadata_json=body.metadata,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return _artifact_contract(artifact)


@router.get("/artifacts", response_model=list[Artifact])
def list_artifacts(project_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ArtifactModel)
    if project_id:
        query = query.filter_by(project_id=project_id)
    return [_artifact_contract(row) for row in query.all()]
