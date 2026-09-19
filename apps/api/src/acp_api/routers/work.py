"""Tâches, task runs et attribution aux workers d'exécution."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from acp_contracts import (
    EvidenceCreate,
    Event,
    SessionContext,
    Task,
    TaskRun,
    TechnicalValidation,
    WorkerClaimRequest,
    WorkerLeaseResponse,
)
from acp_contracts.enums import SessionScope
from acp_database.models import (
    AgentInstanceModel,
    MissionEvidenceModel,
    ProjectModel,
    SessionModel,
    TaskModel,
    TaskRunModel,
    TeamMemberModel,
    TeamModel,
    WorkerLeaseModel,
    WorkerModel,
    WorkspaceModel,
)

from ..deps import accessible_project_ids, ensure_access, get_db, get_principal
from ..events_bus import publish
from .workers import (
    WORKER_LEASE_SECONDS,
    _as_utc,
    authenticate_worker,
    expire_task_leases,
    refresh_active_runs,
    utcnow,
)

router = APIRouter(tags=["work"])


class TaskCreate(BaseModel):
    project_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None
    title: str
    description: str = ""
    priority: int = 3
    meta: dict = Field(default_factory=dict)


class TaskPatch(BaseModel):
    status: str | None = None
    workflow_step: str | None = None
    agent_instance_id: str | None = None
    title: str | None = None
    description: str | None = None
    priority: int | None = None


class ClaimRequest(BaseModel):
    worker_id: str
    provider_id: str = "mock"


class TaskRunPatch(BaseModel):
    status: str | None = None
    workflow_step: str | None = None
    plan: dict | None = None
    result: dict | None = None
    append_logs: list[dict] = Field(default_factory=list)
    technical_validation: TechnicalValidation | None = None
    evidence: list[EvidenceCreate] = Field(default_factory=list)


_RUN_STATES = {
    "pending",
    "queued",
    "preparing",
    "running",
    "waiting_approval",
    "blocked",
    "stopping",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
}
_TERMINAL_RUN_STATES = {"blocked", "succeeded", "failed", "cancelled", "interrupted"}
_RUN_TRANSITIONS = {
    "pending": {"queued", "preparing", "running", "failed", "cancelled"},
    "queued": {"preparing", "running", "failed", "cancelled"},
    "preparing": {
        "running", "waiting_approval", "blocked", "stopping", "failed",
        "cancelled", "interrupted",
    },
    "running": {
        "waiting_approval", "blocked", "stopping", "succeeded", "failed",
        "cancelled", "interrupted",
    },
    "waiting_approval": {"running", "blocked", "stopping", "failed", "cancelled", "interrupted"},
    "stopping": {"cancelled", "interrupted"},
    "blocked": set(),
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
    "interrupted": set(),
}
_TASK_STATUS_BY_RUN = {
    "queued": "queued",
    "preparing": "planning",
    "running": "in_progress",
    "waiting_approval": "review",
    "blocked": "blocked",
    "succeeded": "done",
    "failed": "failed",
    "cancelled": "backlog",
    "interrupted": "blocked",
}
_AGENT_STATUS_BY_RUN = {
    "preparing": "thinking",
    "running": "working",
    "waiting_approval": "reviewing",
    "blocked": "blocked",
    "succeeded": "idle",
    "failed": "idle",
    "cancelled": "idle",
    "interrupted": "blocked",
}
_TERMINAL_EVENT_BY_RUN = {
    "blocked": "task.blocked",
    "succeeded": "task.completed",
    "failed": "task.failed",
    "cancelled": "task.cancelled",
    "interrupted": "task.interrupted",
}


def _emit(db: Session, background: BackgroundTasks, event: Event) -> None:
    """Journalise l'événement dans la transaction de la route, **avant** son commit.

    La route valide ensuite l'effet et l'événement d'un seul commit (0.9.1). Jusqu'en
    0.9.0, l'événement partait dans une seconde transaction, après le commit métier :
    un délai de verrou y rendait un 503 « réessayez » pour un effet déjà validé
    (claim orphelin, tâche en double) et l'événement était perdu. Numéros, réveil des
    flux et relais attendent le commit ; une transaction annulée n'annonce rien.
    """

    publish(db, event, commit=False, background=background)


def _task_event_ids(db: Session, task: TaskModel) -> dict:
    project = db.get(ProjectModel, task.project_id)
    workspace = db.get(WorkspaceModel, project.workspace_id) if project else None
    return {
        "organization_id": workspace.organization_id if workspace else None,
        "workspace_id": project.workspace_id if project else None,
        "department_id": project.department_id if project else None,
        "project_id": task.project_id,
        "team_id": task.team_id,
        "agent_instance_id": task.agent_instance_id,
        "task_id": task.id,
    }


@router.post("/tasks", response_model=Task)
def create_task(
    body: TaskCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    project = db.get(ProjectModel, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if body.team_id is not None:
        team = db.get(TeamModel, body.team_id)
        if team is None or team.project_id != body.project_id:
            raise HTTPException(status_code=422, detail="Équipe hors du projet")
    if body.agent_instance_id is not None:
        agent = db.get(AgentInstanceModel, body.agent_instance_id)
        if agent is None or agent.workspace_id != project.workspace_id:
            raise HTTPException(status_code=422, detail="Agent hors du workspace du projet")
    obj = TaskModel(**body.model_dump())
    db.add(obj)
    db.flush()
    _emit(db, background, Event(type="task.created", **_task_event_ids(db, obj),
                                payload={"title": obj.title, "status": obj.status}))
    db.commit()
    return Task.model_validate(obj, from_attributes=True)


@router.get("/tasks", response_model=list[Task])
def list_tasks(
    project_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = db.query(TaskModel).filter(
        TaskModel.project_id.in_(accessible_project_ids(db, principal))
    )
    if project_id:
        q = q.filter_by(project_id=project_id)
    if status:
        q = q.filter_by(status=status)
    return [Task.model_validate(t, from_attributes=True) for t in q.all()]


@router.patch("/tasks/{task_id}", response_model=Task)
def patch_task(
    task_id: str,
    body: TaskPatch,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    task = db.get(TaskModel, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    if task.is_mission:
        raise HTTPException(
            status_code=409,
            detail="Utilisez les routes /missions pour modifier une mission",
        )
    if body.status is not None and body.status != "backlog":
        raise HTTPException(
            status_code=422,
            detail="Cet état est géré par la file et le run, pas par la modification de tâche",
        )
    if body.agent_instance_id is not None:
        project = db.get(ProjectModel, task.project_id)
        agent = db.get(AgentInstanceModel, body.agent_instance_id)
        if project is None or agent is None or agent.workspace_id != project.workspace_id:
            raise HTTPException(status_code=422, detail="Agent hors du workspace du projet")
    changes = body.model_dump(exclude_none=True)
    status_changed = "status" in changes and changes["status"] != task.status
    for key, value in changes.items():
        setattr(task, key, value)
    if status_changed:
        _emit(db, background, Event(type="task.status_changed", **_task_event_ids(db, task),
                                    payload={"status": task.status, "title": task.title,
                                             "workflow_step": task.workflow_step}))
    db.commit()
    return Task.model_validate(task, from_attributes=True)


@router.post("/tasks/{task_id}/queue", response_model=Task)
def queue_task(
    task_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    task = db.get(TaskModel, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    if task.is_mission:
        raise HTTPException(
            status_code=409,
            detail="Utilisez /missions/{id}/retry pour relancer une mission",
        )
    task.status = "queued"
    _emit(db, background, Event(type="task.queued", **_task_event_ids(db, task),
                                payload={"title": task.title}))
    db.commit()
    return Task.model_validate(task, from_attributes=True)


def _lock_queued_run(db: Session, task_id: str) -> tuple[bool, TaskRunModel | None]:
    """Verrouille la tentative en file d'une tâche **avant** de réserver la tâche.

    C'est l'ordre de l'arrêt et de la relance d'une mission, et de la politique de
    budget : la tentative, puis la tâche. Jusqu'en 0.9.0, le claim réservait la tâche
    puis attendait la tentative, qu'un arrêt tenait en attendant la tâche
    (interblocage 40P01, 500). ``SKIP LOCKED`` : une tentative tenue par un arrêt ou
    une relance en cours fait passer au candidat suivant au lieu d'attendre.

    Rend ``(False, None)`` si la tentative est tenue ou n'est plus en file ;
    ``(True, None)`` pour une tâche historique sans tentative ; ``(True, run)`` sinon.
    SQLite ignore ``FOR UPDATE`` : son verrou de fichier sérialise déjà les claims.
    """

    latest = (
        db.query(TaskRunModel.id)
        .filter_by(task_id=task_id, status="queued")
        .order_by(TaskRunModel.attempt_number.desc(), TaskRunModel.created_at.desc())
        .first()
    )
    if latest is None:
        return True, None
    run = (
        db.query(TaskRunModel)
        .filter(TaskRunModel.id == latest.id, TaskRunModel.status == "queued")
        .with_for_update(skip_locked=True)
        .populate_existing()
        .one_or_none()
    )
    return run is not None, run


def _claim_next_task(
    body: WorkerClaimRequest,
    background: BackgroundTasks,
    db: Session,
    worker: WorkerModel,
):
    if worker.active_runs >= worker.max_concurrency:
        return {"task": None, "reason": "capacité de concurrence atteinte"}

    scope_global_access = worker.global_access == 1
    scope_project_id = worker.project_id
    if scope_global_access:
        project_filter = None
    elif scope_project_id:
        project_filter = TaskModel.project_id == scope_project_id
    else:
        return {
            "task": None,
            "reason": "worker sans périmètre de projet autorisé",
        }

    worker_capabilities = set(worker.capabilities or [])
    task = None
    reserved_run: TaskRunModel | None = None
    simulation_rejected_real_mission = False
    candidates = db.query(TaskModel).filter(TaskModel.status == "queued")
    if project_filter is not None:
        # La frontière de tenant est appliquée dans SQL avant le verrou/claim :
        # une tâche étrangère n'entre jamais dans le jeu de candidats du worker.
        candidates = candidates.filter(project_filter)
    # Aucun ``FOR UPDATE SKIP LOCKED`` sur les candidats : sous PostgreSQL le
    # premier worker verrouillerait toute la file jusqu'à son commit et le second
    # recevrait « aucune tâche compatible » à tort. La mise à jour conditionnelle
    # ``status = 'queued'`` ci-dessous est l'unique arbitre de l'attribution, sur
    # les deux moteurs : un candidat déjà pris rend 0 ligne et l'on passe au suivant.
    for candidate in (
        candidates
        .order_by(TaskModel.priority, TaskModel.created_at)
        .all()
    ):
        if worker.simulation and candidate.is_mission:
            simulation_rejected_real_mission = True
            continue
        required = set((candidate.meta or {}).get("required_capabilities", []))
        if not required.issubset(worker_capabilities):
            continue
        available, queued_run = _lock_queued_run(db, candidate.id)
        if not available:
            continue
        reservation = db.query(TaskModel).filter(
            TaskModel.id == candidate.id, TaskModel.status == "queued"
        )
        if project_filter is not None:
            reservation = reservation.filter(project_filter)
        reserved = (
            reservation
            .update({TaskModel.status: "planning"}, synchronize_session=False)
        )
        if reserved == 1:
            task = candidate
            reserved_run = queued_run
            break
    if task is None:
        reason = None
        reason = (
            "worker de simulation interdit pour une mission réelle"
            if simulation_rejected_real_mission
            else "aucune tâche compatible"
        )
        return {"task": None, **({"reason": reason} if reason else {})}

    project = db.get(ProjectModel, task.project_id)
    workspace = db.get(WorkspaceModel, project.workspace_id)

    agent = None
    if task.agent_instance_id:
        agent = db.get(AgentInstanceModel, task.agent_instance_id)
    if agent is None and task.team_id:
        member_ids = [
            m.agent_instance_id
            for m in db.query(TeamMemberModel).filter_by(team_id=task.team_id).all()
        ]
        if member_ids:
            candidates = (
                db.query(AgentInstanceModel)
                .filter(AgentInstanceModel.id.in_(member_ids))
                .all()
            )
            agent = next((a for a in candidates if a.status == "idle"), None) or candidates[0]
    if agent is None:
        agent = (
            db.query(AgentInstanceModel)
            .filter_by(workspace_id=project.workspace_id, status="idle")
            .first()
        )
    if agent is None:
        return {"task": None, "reason": "aucun agent disponible"}

    session = SessionModel(
        scope=SessionScope.AGENT_EXECUTION.value,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        project_id=project.id,
        team_id=task.team_id,
        agent_instance_id=agent.id,
        provider_id=body.provider_id,
        memory_scope="PROJECT",
    )
    run = reserved_run
    if run is None:
        # Compatibilité des tâches historiques mises en file sans tentative.
        task.attempt_counter = max(task.attempt_counter or 0, 0) + 1
        run = TaskRunModel(
            task_id=task.id,
            attempt_number=task.attempt_counter,
            fencing_token=task.attempt_counter,
            technical_validation={"status": "pending"},
            user_acceptance={"status": "pending"},
        )
        db.add(run)
    run.agent_instance_id = agent.id
    run.status = "preparing" if task.is_mission else "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    task.status = "planning"
    task.agent_instance_id = agent.id
    agent.status = "thinking"
    db.add(session)
    db.flush()
    run.session_id = session.id
    capacity = db.query(WorkerModel).filter(
        WorkerModel.id == worker.id,
        WorkerModel.active_runs < WorkerModel.max_concurrency,
    )
    if scope_global_access:
        capacity = capacity.filter(
            WorkerModel.global_access == 1,
            WorkerModel.project_id.is_(None),
        )
    else:
        capacity = capacity.filter(
            WorkerModel.global_access == 0,
            WorkerModel.project_id == scope_project_id,
        )
    # Tous les prédicats de portée et de capacité font partie de l'UPDATE : une
    # modification concurrente du périmètre annule toute la transaction de claim.
    capacity_reserved = (
        capacity.update(
            {WorkerModel.active_runs: WorkerModel.active_runs + 1},
            synchronize_session=False,
        )
    )
    if capacity_reserved != 1:
        db.rollback()
        return {"task": None, "reason": "capacité de concurrence atteinte"}
    db.refresh(worker)
    lease = WorkerLeaseModel(
        worker_id=worker.id,
        task_id=task.id,
        task_run_id=run.id,
        status="active",
        required_capabilities=(task.meta or {}).get("required_capabilities", []),
        lease_expires_at=utcnow() + timedelta(seconds=WORKER_LEASE_SECONDS),
        last_renewed_at=utcnow(),
    )
    worker.status = "busy" if worker.active_runs >= worker.max_concurrency else "online"
    db.add(lease)
    task.active_run_id = run.id if task.is_mission else task.active_run_id

    ids = _task_event_ids(db, task)
    _emit(db, background, Event(type="task.status_changed", **ids,
                                payload={"status": "planning", "title": task.title}))
    _emit(db, background, Event(
        type="agent.status_changed",
        organization_id=ids["organization_id"], workspace_id=ids["workspace_id"],
        department_id=ids["department_id"], project_id=ids["project_id"],
        team_id=task.team_id, agent_instance_id=agent.id,
        payload={"status": "thinking", "name": agent.name, "role_id": agent.role_id},
    ))
    # Un seul commit pour la réservation et ses événements : un worker qui reçoit
    # une erreur n'a rien réservé, et une réservation validée est toujours journalisée.
    db.commit()

    context = SessionContext(
        session_id=session.id,
        scope=SessionScope.AGENT_EXECUTION,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        project_id=project.id,
        team_id=task.team_id,
        agent_instance_id=agent.id,
        provider_id=body.provider_id,
    )
    response = {
        "task": Task.model_validate(task, from_attributes=True).model_dump(mode="json"),
        "task_run": TaskRun.model_validate(run, from_attributes=True).model_dump(mode="json"),
        "session": context.model_dump(mode="json"),
        "agent": {"id": agent.id, "name": agent.name, "role_id": agent.role_id},
        "project": {"id": project.id, "name": project.name, "project_type": project.project_type},
        "required_capabilities": (task.meta or {}).get("required_capabilities", []),
        "attempt_id": run.id,
        "attempt_number": run.attempt_number,
        "fencing_token": run.fencing_token,
        "stop_requested": run.stop_requested_at is not None,
    }
    if task.is_mission:
        response["mission"] = {
            "id": task.id,
            "objective": task.objective,
            "expected_outcome": task.expected_outcome,
            "acceptance_criteria": list(task.acceptance_criteria or []),
            "autonomy": dict(task.autonomy or {}),
            "resources": list(task.resources or []),
            "budget": dict(task.budget or {}),
            "duration_seconds": task.duration_seconds,
        }
    # Forme identique sur les deux dialectes : SQLite relit ses instants naïfs,
    # PostgreSQL les relit en UTC ; le worker reçoit toujours un décalage explicite.
    response["lease_expires_at"] = _as_utc(lease.lease_expires_at).isoformat()
    return response


@router.post("/workers/{worker_id}/claim")
def claim_next_task(
    worker_id: str,
    body: WorkerClaimRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Attribue une tâche compatible à un worker authentifié."""
    worker = authenticate_worker(db, worker_id, authorization)
    expire_task_leases(db)
    db.refresh(worker)
    return _claim_next_task(body, background, db, worker)


@router.post(
    "/workers/{worker_id}/leases/{run_id}/renew",
    response_model=WorkerLeaseResponse,
)
def renew_task_lease(
    worker_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    fencing_token: int | None = Header(
        default=None, alias="X-Attempt-Fencing-Token"
    ),
):
    worker = authenticate_worker(db, worker_id, authorization)
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker.id, task_run_id=run_id, status="active")
        .first()
    )
    if lease is None:
        raise HTTPException(status_code=404, detail="Lease actif introuvable")
    run = db.get(TaskRunModel, run_id)
    task = db.get(TaskModel, run.task_id) if run is not None else None
    if run is None or task is None or lease.task_id != task.id:
        raise HTTPException(status_code=409, detail="Lease incohérent avec la tentative")
    if task.is_mission and fencing_token != run.fencing_token:
        raise HTTPException(status_code=409, detail="Fencing token requis ou périmé")
    now = utcnow()
    if _as_utc(lease.lease_expires_at) <= now:
        expire_task_leases(db)
        raise HTTPException(
            status_code=409,
            detail="Lease expiré ; renouvellement refusé et run interrompu",
        )
    renewed_until = now + timedelta(seconds=WORKER_LEASE_SECONDS)
    # Compare-and-set : le bail lu ci-dessus a pu être expiré ou libéré entre-temps
    # (expiration concurrente, fin de tentative). Une affectation ORM le rouvrirait
    # depuis une lecture périmée ; le prédicat SQL est réévalué par la base.
    renewed = (
        db.query(WorkerLeaseModel)
        .filter(
            WorkerLeaseModel.id == lease.id,
            WorkerLeaseModel.status == "active",
            WorkerLeaseModel.lease_expires_at > now,
        )
        .update(
            {
                WorkerLeaseModel.last_renewed_at: now,
                WorkerLeaseModel.lease_expires_at: renewed_until,
            },
            synchronize_session=False,
        )
    )
    if renewed != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Lease plus actif ; renouvellement refusé",
        )
    db.commit()
    return WorkerLeaseResponse(
        worker_id=worker.id,
        task_run_id=run_id,
        lease_expires_at=renewed_until,
        status=run.status,
        stop_requested=run.stop_requested_at is not None or run.status == "stopping",
        fencing_token=run.fencing_token,
    )


@router.post("/worker/claim", deprecated=True)
def claim_next_task_legacy(
    body: ClaimRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    """Ancien endpoint, désactivé sauf opt-in explicite pour une transition locale."""
    if os.environ.get("ACP_ALLOW_LEGACY_WORKER_CLAIM") != "1":
        raise HTTPException(status_code=410, detail="Enregistrez le worker via /workers/register")
    worker = authenticate_worker(db, body.worker_id, authorization)
    return _claim_next_task(
        WorkerClaimRequest(provider_id=body.provider_id), background, db, worker
    )


@router.get("/task-runs", response_model=list[TaskRun])
def list_task_runs(
    task_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    q = (
        db.query(TaskRunModel)
        .join(TaskModel, TaskModel.id == TaskRunModel.task_id)
        .filter(TaskModel.project_id.in_(accessible_project_ids(db, principal)))
    )
    if task_id:
        q = q.filter(TaskRunModel.task_id == task_id)
    return [TaskRun.model_validate(r, from_attributes=True) for r in q.all()]


def _evidence_fingerprint(evidence: EvidenceCreate) -> str:
    canonical = json.dumps(
        evidence.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compare_and_set_run_status(
    db: Session, *, run_id: str, expected_status: str, target_status: str
) -> bool:
    """Change l'état seulement si aucun autre acteur ne l'a fait entre-temps."""

    return (
        db.query(TaskRunModel)
        .filter(
            TaskRunModel.id == run_id,
            TaskRunModel.status == expected_status,
        )
        .update(
            {TaskRunModel.status: target_status},
            synchronize_session=False,
        )
        == 1
    )


@router.patch("/task-runs/{run_id}", response_model=TaskRun)
def patch_task_run(
    run_id: str,
    body: TaskRunPatch,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
    fencing_token: int | None = Header(
        default=None, alias="X-Attempt-Fencing-Token"
    ),
):
    """Accepte une progression uniquement du worker qui détient le lease actif."""

    if not worker_id:
        raise HTTPException(status_code=401, detail="X-Worker-Id requis")
    worker = authenticate_worker(db, worker_id, authorization)
    # Serialize worker transitions with user stop requests on databases that
    # support row locks. SQLite ignores FOR UPDATE, so the conditional status
    # update below remains the final stale-read guard there.
    run = (
        db.query(TaskRunModel)
        .filter_by(id=run_id)
        .with_for_update()
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Task run introuvable")
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker.id, task_run_id=run.id, status="active")
        .first()
    )
    if lease is None:
        raise HTTPException(status_code=409, detail="Lease actif requis pour modifier ce run")
    if _as_utc(lease.lease_expires_at) <= utcnow():
        raise HTTPException(status_code=409, detail="Lease expiré ; progression refusée")
    task = db.get(TaskModel, run.task_id)
    if task is None or lease.task_id != task.id:
        raise HTTPException(status_code=409, detail="Lease incohérent avec la tâche du run")
    if task.is_mission and fencing_token != run.fencing_token:
        raise HTTPException(status_code=409, detail="Fencing token requis ou périmé")
    if run.status == "stopping" and body.status not in {"cancelled", "interrupted"}:
        raise HTTPException(
            status_code=409,
            detail="Une tentative en arrêt doit être annulée ou interrompue",
        )
    if body.status is not None and body.status not in _RUN_STATES:
        raise HTTPException(status_code=422, detail="État de run inconnu")
    if (
        body.status is not None
        and body.status != run.status
        and body.status not in _RUN_TRANSITIONS.get(run.status, set())
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Transition de run interdite: {run.status} → {body.status}",
        )
    technical_validation = dict(run.technical_validation or {"status": "pending"})
    if body.technical_validation is not None:
        technical_validation = body.technical_validation.model_dump(mode="json")
        technical_validation["checked_at"] = technical_validation.get(
            "checked_at"
        ) or utcnow().isoformat()

    new_evidence: list[tuple[EvidenceCreate, str]] = []
    for evidence in body.evidence:
        fingerprint = _evidence_fingerprint(evidence)
        exists = (
            db.query(MissionEvidenceModel.id)
            .filter_by(task_run_id=run.id, fingerprint=fingerprint)
            .first()
        )
        if exists is None and all(item[1] != fingerprint for item in new_evidence):
            new_evidence.append((evidence, fingerprint))

    if body.status == "succeeded":
        if task.is_mission:
            evidence_count = (
                db.query(MissionEvidenceModel)
                .filter_by(task_run_id=run.id)
                .count()
            ) + len(new_evidence)
            if technical_validation.get("status") != "passed" or evidence_count < 1:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Un succès exige une validation technique passed "
                        "et au moins une preuve structurée"
                    ),
                )
        else:
            # Compatibilité temporaire de l'ancien protocole task-run.
            result = body.result if body.result is not None else run.result
            evidence = result.get("evidence") if isinstance(result, dict) else None
            if (
                not isinstance(result, dict)
                or result.get("technical_validation") != "passed"
                or not isinstance(evidence, list)
                or not evidence
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Un succès exige technical_validation=passed et au moins une preuve",
                )
    previous_status = run.status
    if body.status is not None and body.status != previous_status:
        transitioned = _compare_and_set_run_status(
            db,
            run_id=run.id,
            expected_status=previous_status,
            target_status=body.status,
        )
        if not transitioned:
            db.rollback()
            current = db.get(TaskRunModel, run_id)
            current_status = current.status if current is not None else "absent"
            raise HTTPException(
                status_code=409,
                detail=(
                    "Transition refusée après changement concurrent: "
                    f"{previous_status} → {current_status}"
                ),
            )
        db.refresh(run)
    terminal_event: Event | None = None
    if body.status is not None:
        run.status = body.status
        task.status = (
            "review"
            if task.is_mission and body.status == "succeeded"
            else _TASK_STATUS_BY_RUN.get(body.status, task.status)
        )
        if run.agent_instance_id:
            agent = db.get(AgentInstanceModel, run.agent_instance_id)
            if agent is not None:
                agent.status = _AGENT_STATUS_BY_RUN.get(body.status, agent.status)
        if body.status in _TERMINAL_RUN_STATES:
            run.finished_at = datetime.now(timezone.utc)
            lease.status = "released"
            # Le compteur est recalculé par la base à partir des baux encore
            # actifs, sous verrou de la ligne worker : un décrément depuis la
            # valeur lue à l'authentification écraserait la réservation d'un
            # claim validé entre-temps, et admettrait des tentatives au-delà de
            # la capacité déclarée (ou affamerait un worker libre).
            db.flush()
            active_runs = refresh_active_runs(db, worker.id)
            worker.status = (
                "busy" if active_runs >= worker.max_concurrency else "online"
            )
            if task.is_mission and task.active_run_id == run.id:
                task.active_run_id = None
            terminal_event = Event(
                type=_TERMINAL_EVENT_BY_RUN[body.status],
                **_task_event_ids(db, task),
                task_run_id=run.id,
                payload={
                    "title": task.title,
                    "run_status": body.status,
                    "worker_id": worker.id,
                    "technical_validation": technical_validation.get("status"),
                },
            )
    if body.workflow_step is not None:
        task.workflow_step = body.workflow_step
    if body.plan is not None:
        run.plan = body.plan
    if body.result is not None:
        run.result = body.result
    if body.technical_validation is not None:
        run.technical_validation = technical_validation
    for evidence, fingerprint in new_evidence:
        db.add(
            MissionEvidenceModel(
                task_run_id=run.id,
                worker_id=worker.id,
                fingerprint=fingerprint,
                **evidence.model_dump(),
            )
        )
    if body.append_logs:
        run.logs = list(run.logs or []) + body.append_logs
    if terminal_event is not None:
        _emit(db, background, terminal_event)
    db.commit()
    return TaskRun.model_validate(run, from_attributes=True)
