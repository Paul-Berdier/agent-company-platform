"""Enregistrement, authentification et présence des workers distants."""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from acp_contracts import (
    Event,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
    WorkerRegistrationRequest,
    WorkerRegistrationResponse,
    WorkerSnapshot,
    WorkerStatus,
)
from acp_database.models import (
    AgentInstanceModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    WorkerLeaseModel,
    WorkerModel,
    WorkspaceModel,
)

from ..deps import get_db, get_principal, require_platform_role
from ..events_bus import store_event

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


def _authorized_registration_scope() -> tuple[str | None, bool]:
    """Lit la portée autorisée par l'opérateur, jamais celle choisie par le client."""

    raw_project = os.environ.get("ACP_WORKER_REGISTRATION_PROJECT_ID")
    raw_global = os.environ.get("ACP_WORKER_REGISTRATION_GLOBAL_ACCESS")
    if raw_global not in {None, "", "0", "1"}:
        raise HTTPException(
            status_code=503,
            detail="Configuration du périmètre d'enrôlement worker invalide",
        )
    project_id = raw_project if raw_project not in {None, ""} else None
    if project_id is not None and (
        project_id != project_id.strip() or len(project_id) > 36
    ):
        raise HTTPException(
            status_code=503,
            detail="Configuration du périmètre d'enrôlement worker invalide",
        )
    global_access = raw_global == "1"
    if global_access == (project_id is not None):
        raise HTTPException(
            status_code=503,
            detail=(
                "Configurez exactement un périmètre d'enrôlement worker côté API"
            ),
        )
    return project_id, global_access


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
        project_id=worker.project_id,
        global_access=worker.global_access == 1,
        metadata=worker.metadata_json or {},
        last_seen_at=worker.last_seen_at,
        lease_expires_at=worker.lease_expires_at,
        token_expires_at=worker.token_expires_at,
        created_at=worker.created_at,
    )


def _lock_worker_row(db: Session, worker_id: str) -> None:
    """Prend le verrou d'écriture du worker avant de recalculer son compteur.

    PostgreSQL : ``SELECT … FOR UPDATE`` attend un claim en cours sur la même
    ligne ; l'instruction suivante prend alors un instantané neuf, dans lequel le
    bail inséré par ce claim est visible. Un ``UPDATE`` seul ne suffirait pas :
    en lecture validée, sa sous-requête ``COUNT`` garde l'instantané pris avant
    l'attente et recompterait sans ce bail. SQLite ignore ``FOR UPDATE`` : une mise
    à jour sans effet prend le verrou de fichier, ce qui sérialise de la même
    façon les écrivains concurrents.
    """

    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            update(WorkerModel)
            .where(WorkerModel.id == worker_id)
            .values(active_runs=WorkerModel.active_runs),
            execution_options={"synchronize_session": False},
        )
        return
    db.query(WorkerModel).filter_by(id=worker_id).with_for_update().one_or_none()


def refresh_active_runs(db: Session, worker_id: str) -> int:
    """Réaligne ``active_runs`` sur le nombre de baux actifs, par la base et sous verrou.

    Le compteur est réservé par le claim (``active_runs + 1`` conditionnel) et
    relâché par les fins de tentative ; ce recalcul est la vérité de rattrapage.
    Il est écrit par une sous-requête ``COUNT`` évaluée par la base, jamais depuis
    une valeur lue plus tôt dans la session : une affectation ORM depuis une
    lecture périmée écraserait la réservation d'un claim validé entre-temps.
    Retourne le compteur écrit et aligne l'objet déjà chargé sans nouvel UPDATE.
    """

    _lock_worker_row(db, worker_id)
    active_leases = (
        select(func.count(WorkerLeaseModel.id))
        .where(
            WorkerLeaseModel.worker_id == worker_id,
            WorkerLeaseModel.status == "active",
        )
        .scalar_subquery()
    )
    db.execute(
        update(WorkerModel)
        .where(WorkerModel.id == worker_id)
        .values(active_runs=active_leases),
        execution_options={"synchronize_session": False},
    )
    active_runs = db.execute(
        select(WorkerModel.active_runs).where(WorkerModel.id == worker_id)
    ).scalar_one()
    worker = db.get(WorkerModel, worker_id)
    if worker is not None:
        set_committed_value(worker, "active_runs", active_runs)
    return active_runs


def expire_task_leases(db: Session) -> int:
    """Interrompt les runs dont le bail est échu, chaque bail une seule fois.

    Le filtre ``lease_expires_at <= now`` vit dans le SQL : un bail encore valide
    n'est ni chargé ni touché. Chaque bail échu est fermé par compare-and-set
    ``active → expired`` ; les mutations de la tentative, de la tâche et de
    l'agent, comme l'événement ``task.interrupted``, ne sont écrites que si ce
    CAS a rendu une ligne. Deux appels concurrents (heartbeat et claim, par
    exemple) ne produisent donc jamais deux interruptions ni deux événements pour
    le même bail. L'effet éventuel du worker reste inconnu : aucune reprise
    automatique n'est rejouée.
    """
    now = utcnow()
    expired = 0
    worker_ids: set[str] = set()
    candidates = (
        db.query(WorkerLeaseModel)
        .filter(
            WorkerLeaseModel.status == "active",
            WorkerLeaseModel.lease_expires_at <= now,
        )
        .order_by(WorkerLeaseModel.created_at, WorkerLeaseModel.id)
        .all()
    )
    for lease in candidates:
        transitioned = (
            db.query(WorkerLeaseModel)
            .filter(
                WorkerLeaseModel.id == lease.id,
                WorkerLeaseModel.status == "active",
                # Revérifié dans le CAS : sous PostgreSQL (READ COMMITTED), un
                # renouvellement validé pendant notre attente ne rend la ligne à ce
                # filtre qu'avec sa nouvelle échéance, et le bail n'est pas expiré.
                WorkerLeaseModel.lease_expires_at <= now,
            )
            .update({WorkerLeaseModel.status: "expired"}, synchronize_session=False)
        )
        if transitioned != 1:
            # Un autre appel a fermé ce bail entre notre lecture et notre écriture.
            db.refresh(lease)
            continue
        set_committed_value(lease, "status", "expired")
        run = db.get(TaskRunModel, lease.task_run_id)
        if run is not None and run.status in {
            "pending",
            "queued",
            "preparing",
            "running",
            "waiting_approval",
            "stopping",
        }:
            run.status = "interrupted"
            run.finished_at = now
            run.logs = list(run.logs or []) + [
                {
                    "level": "error",
                    "message": (
                        "Lease worker expiré ; effet éventuel inconnu, "
                        "reprise automatique interdite"
                    ),
                }
            ]
        task = db.get(TaskModel, lease.task_id)
        if task is not None and task.status in {"planning", "in_progress", "review"}:
            task.status = "blocked"
        if task is not None and task.is_mission and task.active_run_id == lease.task_run_id:
            task.active_run_id = None
        if task is not None and run is not None:
            project = db.get(ProjectModel, task.project_id)
            workspace = db.get(WorkspaceModel, project.workspace_id) if project else None
            # ``store_event`` alloue les deux numéros (séquence de tentative et
            # numéro de journal) : sans eux, la fin forcée de la tentative sortirait
            # du flux et de la page projet, et le Studio resterait « en direct » sur
            # une tentative pourtant close. ``commit=False`` : la boucle possède sa
            # transaction et valide plus bas.
            store_event(
                db,
                Event(
                    type="task.interrupted",
                    organization_id=workspace.organization_id if workspace else None,
                    workspace_id=project.workspace_id if project else None,
                    department_id=project.department_id if project else None,
                    project_id=task.project_id,
                    team_id=task.team_id,
                    agent_instance_id=run.agent_instance_id,
                    task_id=task.id,
                    task_run_id=run.id,
                    payload={
                        "title": task.title,
                        "reason": "worker_lease_expired",
                        "worker_id": lease.worker_id,
                    },
                ),
                commit=False,
            )
        if run is not None and run.agent_instance_id:
            agent = db.get(AgentInstanceModel, run.agent_instance_id)
            if agent is not None:
                agent.status = "blocked"
        worker_ids.add(lease.worker_id)
        expired += 1
    if expired:
        db.flush()
        for worker_id in sorted(worker_ids):
            refresh_active_runs(db, worker_id)
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

    authorized_project_id, authorized_global_access = _authorized_registration_scope()
    if (
        body.project_id != authorized_project_id
        or body.global_access is not authorized_global_access
    ):
        raise HTTPException(
            status_code=403,
            detail="Périmètre worker non autorisé par la configuration de l'API",
        )

    now = utcnow()
    raw_token = secrets.token_urlsafe(32)
    expire_task_leases(db)
    if body.project_id is not None and db.get(ProjectModel, body.project_id) is None:
        raise HTTPException(status_code=422, detail="Projet de worker introuvable")
    worker = db.query(WorkerModel).filter_by(name=body.name).first()
    active_leases = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker.id, status="active")
        .count()
        if worker is not None
        else 0
    )
    if worker is not None and (worker.active_runs > 0 or active_leases > 0):
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
        "project_id": body.project_id,
        "global_access": int(body.global_access),
        "metadata_json": body.metadata,
        "last_seen_at": now,
        "lease_expires_at": now + timedelta(seconds=WORKER_LEASE_SECONDS),
    }
    if worker is None:
        worker = WorkerModel(name=body.name, **values)
        db.add(worker)
    else:
        # La même écriture atomique protège le renouvellement de jeton et le
        # changement de périmètre contre un claim concurrent. Si le claim a
        # réservé la capacité en premier, aucune portée n'est modifiée.
        updated = (
            db.query(WorkerModel)
            .filter(WorkerModel.id == worker.id, WorkerModel.active_runs == 0)
            .update(values, synchronize_session=False)
        )
        if updated != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Impossible de renouveler un worker avec des runs actifs",
            )
    db.commit()
    db.refresh(worker)
    return WorkerRegistrationResponse(
        worker_id=worker.id,
        token=raw_token,
        token_expires_at=worker.token_expires_at,
        heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS,
        project_id=worker.project_id,
        global_access=worker.global_access == 1,
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
    if body.simulation is False and worker.simulation:
        raise HTTPException(
            status_code=409,
            detail=(
                "Un worker de simulation ne peut devenir réel que par un nouvel "
                "enregistrement autorisé"
            ),
        )
    if body.simulation is not None:
        worker.simulation = int(body.simulation)
    # Recalcul par la base, sous le verrou de la ligne : un claim validé pendant ce
    # heartbeat n'est jamais écrasé par un compteur relu avant lui.
    active_runs = refresh_active_runs(db, worker.id)
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
def list_workers(
    db: Session = Depends(get_db), principal: str = Depends(get_principal)
):
    require_platform_role(db, principal, "owner", "operator")
    _mark_stale_workers(db)
    return [worker_snapshot(worker) for worker in db.query(WorkerModel).all()]


@router.get("/{worker_id}", response_model=WorkerSnapshot)
def get_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner", "operator")
    _mark_stale_workers(db)
    worker = db.get(WorkerModel, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail="Worker introuvable")
    return worker_snapshot(worker)
