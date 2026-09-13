"""Artefacts, verrous à lease et approbations humaines."""

import hashlib
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from acp_contracts import (
    ApprovalDecision,
    ApprovalExecutionCheck,
    ApprovalRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    ApprovalValidationResult,
    Artifact,
    ArtifactCreate,
    ArtifactSummary,
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

from ..deps import accessible_project_ids, ensure_access, get_db, get_principal
from .artifacts import receive_worker_artifact_content
from .workers import _as_utc, authenticate_worker, expire_task_leases, utcnow

router = APIRouter(tags=["operations"])


def _lock_contract(lock: ResourceLockModel) -> ResourceLock:
    return ResourceLock.model_validate(lock, from_attributes=True)


def _approval_contract(approval: ApprovalModel) -> ApprovalRequest:
    return ApprovalRequest.model_validate(approval, from_attributes=True)


def _action_fingerprint(
    *, action: str, target: str, consequences: list[str], scope: dict, footprint: dict
) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "target": target,
            "consequences": consequences,
            "scope": scope,
            "footprint": footprint,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
def list_locks(
    active_only: bool = True,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    now = utcnow()
    query = (
        db.query(ResourceLockModel)
        .join(TaskRunModel, TaskRunModel.id == ResourceLockModel.owner_run_id)
        .join(TaskModel, TaskModel.id == TaskRunModel.task_id)
        .filter(TaskModel.project_id.in_(accessible_project_ids(db, principal)))
    )
    rows = (
        query.filter(ResourceLockModel.status == "active").all()
        if active_only
        else query.all()
    )
    return [
        _lock_contract(lock)
        for lock in rows
        if not active_only or _as_utc(lock.lease_expires_at) > now
    ]


def _expire_approvals(db: Session) -> None:
    now = utcnow()
    changed = (
        db.query(ApprovalModel)
        .filter(
            ApprovalModel.status.in_(
                [
                    ApprovalStatus.WAITING_APPROVAL.value,
                    ApprovalStatus.APPROVED.value,
                ]
            ),
            ApprovalModel.expires_at <= now,
        )
        .update(
            {ApprovalModel.status: ApprovalStatus.EXPIRED.value},
            synchronize_session=False,
        )
    )
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
    task = None
    run = None
    if body.task_run_id:
        run = (
            db.query(TaskRunModel)
            .filter_by(id=body.task_run_id)
            .with_for_update()
            .first()
        )
        task = db.get(TaskModel, run.task_id) if run else None
        if task is None or task.project_id != body.project_id:
            raise HTTPException(status_code=400, detail="Task run hors du projet")
        if task.is_mission and (
            not body.target
            or not body.consequences
            or not body.scope
            or not body.footprint
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Une approbation de mission exige cible, conséquences, "
                    "portée et empreinte"
                ),
            )
        scoped_project = body.scope.get("project_id")
        if scoped_project is not None and scoped_project != body.project_id:
            raise HTTPException(status_code=422, detail="Portée hors du projet")
    values = body.model_dump(exclude={"expires_in_seconds"}, mode="json")
    fingerprint = _action_fingerprint(
        action=body.action.value,
        target=body.target,
        consequences=body.consequences,
        scope=body.scope,
        footprint=body.footprint,
    )
    approval = ApprovalModel(
        **values,
        action_fingerprint=fingerprint,
        status=ApprovalStatus.WAITING_APPROVAL.value,
        requested_by=principal or "development-user",
        expires_at=utcnow() + timedelta(seconds=body.expires_in_seconds),
    )
    if task is not None and task.is_mission and run is not None:
        if run.status == "stopping":
            raise HTTPException(
                status_code=409,
                detail="Aucune approbation ne peut être demandée pendant l'arrêt",
            )
        if run.status in {"preparing", "running"}:
            source_status = run.status
            transitioned = (
                db.query(TaskRunModel)
                .filter(
                    TaskRunModel.id == run.id,
                    TaskRunModel.status == source_status,
                )
                .update(
                    {TaskRunModel.status: "waiting_approval"},
                    synchronize_session=False,
                )
            )
            if transitioned != 1:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="État de tentative modifié pendant la demande d'approbation",
                )
            db.refresh(run)
            task.status = "review"
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return _approval_contract(approval)


@router.post(
    "/approvals/{approval_id}/validate",
    response_model=ApprovalValidationResult,
)
def validate_approval_for_execution(
    approval_id: str,
    body: ApprovalExecutionCheck,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
):
    """Valide une approbation contre l'effet exact que le worker va produire.

    Une divergence est persistée comme invalidation avant de refuser l'action :
    une ancienne approbation ne peut donc pas être rejouée avec une cible élargie.
    """

    if not worker_id:
        raise HTTPException(status_code=401, detail="X-Worker-Id requis")
    worker = authenticate_worker(db, worker_id, authorization)
    _expire_approvals(db)
    # Lock in the same order as mission stop: run first, then approval.  This
    # prevents a decision/validation from observing an approval after STOPPING
    # has invalidated the run's pending effects.
    run = (
        db.query(TaskRunModel)
        .filter_by(id=body.task_run_id)
        .with_for_update()
        .first()
    )
    task = db.get(TaskModel, run.task_id) if run is not None else None
    approval = (
        db.query(ApprovalModel)
        .filter_by(id=approval_id)
        .with_for_update()
        .first()
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approbation introuvable")
    if (
        run is None
        or task is None
        or approval.task_run_id != run.id
        or approval.project_id != task.project_id
    ):
        raise HTTPException(status_code=409, detail="Approbation hors de cette tentative")
    _require_active_run_lease(db, worker.id, run.id)
    if task.is_mission and body.fencing_token != run.fencing_token:
        raise HTTPException(status_code=409, detail="Fencing token périmé")
    if task.is_mission and (
        run.status != "waiting_approval" or run.stop_requested_at is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="Approbation non exécutable dans l'état courant de la tentative",
        )
    if _as_utc(approval.expires_at) <= utcnow():
        approval.status = ApprovalStatus.EXPIRED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Approbation expirée")

    submitted_fingerprint = _action_fingerprint(
        action=body.action.value,
        target=body.target,
        consequences=body.consequences,
        scope=body.scope,
        footprint=body.footprint,
    )
    if approval.status != ApprovalStatus.APPROVED.value:
        raise HTTPException(
            status_code=409,
            detail=f"Approbation non exécutable: {approval.status}",
        )
    if submitted_fingerprint != approval.action_fingerprint:
        approval.status = ApprovalStatus.INVALIDATED.value
        approval.invalidated_at = utcnow()
        approval.invalidated_reason = "action_envelope_changed"
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Action modifiée ; approbation invalidée",
        )
    return ApprovalValidationResult(
        approval_id=approval.id,
        valid=True,
        status=ApprovalStatus.APPROVED,
        action_fingerprint=approval.action_fingerprint,
        expires_at=approval.expires_at,
    )


@router.get("/approvals", response_model=list[ApprovalRequest])
def list_approvals(
    project_id: str | None = None,
    status: ApprovalStatus | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _expire_approvals(db)
    query = db.query(ApprovalModel).filter(
        ApprovalModel.project_id.in_(accessible_project_ids(db, principal))
    )
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

    # Mission stop locks the run before invalidating its approvals.  Decisions
    # use the same lock order and finish with a CAS, which is also safe on
    # SQLite where SELECT FOR UPDATE is ignored but writes are serialized.
    if approval.task_run_id:
        run = (
            db.query(TaskRunModel)
            .filter_by(id=approval.task_run_id)
            .with_for_update()
            .first()
        )
        task = db.get(TaskModel, run.task_id) if run is not None else None
        if task is None or task.project_id != approval.project_id:
            raise HTTPException(status_code=409, detail="Approbation hors de cette tentative")
        if task.is_mission and (
            run.status != "waiting_approval" or run.stop_requested_at is not None
        ):
            raise HTTPException(
                status_code=409,
                detail="La tentative n'accepte plus de décision d'approbation",
            )

    locked_approval = (
        db.query(ApprovalModel)
        .filter_by(id=approval_id)
        .with_for_update()
        .first()
    )
    if (
        locked_approval is None
        or locked_approval.status != ApprovalStatus.WAITING_APPROVAL.value
    ):
        raise HTTPException(status_code=409, detail="Approbation déjà finalisée")
    if _as_utc(locked_approval.expires_at) <= utcnow():
        locked_approval.status = ApprovalStatus.EXPIRED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Approbation expirée")
    decided_at = utcnow()
    transitioned = (
        db.query(ApprovalModel)
        .filter(
            ApprovalModel.id == approval_id,
            ApprovalModel.status == ApprovalStatus.WAITING_APPROVAL.value,
        )
        .update(
            {
                ApprovalModel.status: body.decision.value,
                ApprovalModel.decided_by: principal or "development-owner",
                ApprovalModel.decision_comment: body.comment,
                ApprovalModel.decided_at: decided_at,
            },
            synchronize_session=False,
        )
    )
    if transitioned != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Approbation déjà finalisée")
    db.commit()
    db.refresh(locked_approval)
    return _approval_contract(locked_approval)


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


@router.post(
    "/workers/{worker_id}/artifacts/content",
    response_model=ArtifactSummary,
    status_code=201,
)
async def upload_artifact_content(
    worker_id: str,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Téléverse le contenu d'un livrable (``multipart/form-data``, §6).

    L'identité du worker est vérifiée **avant** de lire le corps : un appelant sans
    jeton ne fait jamais écrire un octet. La lecture, les plafonds et l'idempotence
    par sha256 vivent dans ``routers/artifacts.py``.
    """

    worker = authenticate_worker(db, worker_id, authorization)
    return await receive_worker_artifact_content(db, worker, request)


# ``GET /artifacts`` est servi par ``routers/artifacts.py`` depuis le Lot E : la
# bibliothèque est paginée (``ArtifactPage``) et expose le contenu téléversé. La
# version « liste complète » qui vivait ici est supprimée plutôt que dupliquée —
# deux routes sur le même chemin auraient laissé la seconde inatteignable.
