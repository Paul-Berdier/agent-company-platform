"""Surface REST orientée utilisateur pour piloter des missions.

Les tables ``tasks`` et ``task_runs`` restent la source de vérité. Une mission est
une tâche enrichie et chaque relance crée une nouvelle tentative clôturable, sans
réutiliser une exécution dont les effets peuvent être incertains.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    Event,
    MissionAcceptanceDecision,
    MissionAutonomy,
    MissionBudget,
    MissionComment,
    MissionCommentCreate,
    MissionCreate,
    MissionDetail,
    MissionEvidence,
    MissionResource,
    MissionRetryRequest,
    MissionRun,
    MissionRunStatus,
    MissionStopResponse,
    MissionSummary,
    TechnicalValidation,
    UserAcceptance,
)
from acp_database.models import (
    AgentInstanceModel,
    ApprovalModel,
    MissionCommandModel,
    MissionCommentModel,
    MissionEvidenceModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    TeamModel,
)

from ..budget_service import (
    BudgetServiceError,
    begin_budget_write,
    enforce_mission_retry_limit,
    enforce_project_mission_capacity,
    lock_mission_retry_context,
)
from ..deps import (
    accessible_agent_ids,
    accessible_project_ids,
    ensure_access,
    get_db,
    get_principal,
)
from ..extensions import resolve_project_extensions
from .work import _emit, _task_event_ids
from .workers import utcnow

router = APIRouter(prefix="/missions", tags=["missions"])

_ACTIVE_RUN_STATES = {
    "queued",
    "preparing",
    "running",
    "waiting_approval",
    "stopping",
}
_RETRYABLE_RUN_STATES = {"blocked", "failed", "cancelled", "interrupted"}


def _canonical_fingerprint(value: dict) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _principal_command(
    db: Session, *, principal: str, command: str, key: str
) -> MissionCommandModel | None:
    return (
        db.query(MissionCommandModel)
        .filter_by(
            principal_id=principal,
            command=command,
            idempotency_key=key,
        )
        .first()
    )


def _mission_or_404(db: Session, mission_id: str) -> TaskModel:
    task = db.get(TaskModel, mission_id)
    if task is None or not task.is_mission:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return task


def _validate_assignment(
    db: Session,
    body: MissionCreate,
    project: ProjectModel,
    principal: str,
) -> None:
    if body.team_id is not None:
        team = db.get(TeamModel, body.team_id)
        if team is None or team.project_id != body.project_id:
            raise HTTPException(status_code=422, detail="Équipe hors du projet")
    if body.agent_instance_id is not None:
        agent = db.get(AgentInstanceModel, body.agent_instance_id)
        if agent is None or agent.workspace_id != project.workspace_id:
            raise HTTPException(
                status_code=422, detail="Agent hors du workspace du projet"
            )
        if body.agent_instance_id not in accessible_agent_ids(db, principal):
            raise HTTPException(
                status_code=422, detail="Agent inaccessible depuis ce projet"
            )


def _evidence_contract(row: MissionEvidenceModel) -> MissionEvidence:
    return MissionEvidence(
        id=row.id,
        task_run_id=row.task_run_id,
        worker_id=row.worker_id,
        kind=row.kind,
        summary=row.summary,
        data=row.data or {},
        command=row.command,
        exit_code=row.exit_code,
        uri=row.uri,
        checksum=row.checksum,
        created_at=row.created_at,
    )


def mission_run_contract(db: Session, run: TaskRunModel) -> MissionRun:
    evidence = (
        db.query(MissionEvidenceModel)
        .filter_by(task_run_id=run.id)
        .order_by(MissionEvidenceModel.created_at, MissionEvidenceModel.id)
        .all()
    )
    return MissionRun(
        id=run.id,
        mission_id=run.task_id,
        attempt_number=run.attempt_number,
        fencing_token=run.fencing_token,
        status=run.status,
        agent_instance_id=run.agent_instance_id,
        session_id=run.session_id,
        stop_requested=run.stop_requested_at is not None,
        stop_requested_at=run.stop_requested_at,
        technical_validation=TechnicalValidation.model_validate(
            run.technical_validation or {"status": "pending"}
        ),
        user_acceptance=UserAcceptance.model_validate(
            run.user_acceptance or {"status": "pending"}
        ),
        evidence=[_evidence_contract(row) for row in evidence],
        plan=run.plan,
        result=run.result,
        logs=list(run.logs or []),
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
    )


def _mission_contract(
    db: Session, task: TaskModel, *, include_runs: bool
) -> MissionSummary | MissionDetail:
    runs = (
        db.query(TaskRunModel)
        .filter_by(task_id=task.id)
        .order_by(TaskRunModel.attempt_number, TaskRunModel.created_at)
        .all()
    )
    if not runs:
        raise HTTPException(status_code=409, detail="Mission sans tentative")
    run_contracts = [mission_run_contract(db, run) for run in runs]
    values = dict(
        id=task.id,
        project_id=task.project_id,
        team_id=task.team_id,
        agent_instance_id=task.agent_instance_id,
        title=task.title,
        objective=task.objective,
        expected_outcome=task.expected_outcome,
        acceptance_criteria=task.acceptance_criteria or [],
        autonomy=MissionAutonomy.model_validate(task.autonomy or {}),
        resources=[MissionResource.model_validate(item) for item in task.resources or []],
        budget=MissionBudget.model_validate(task.budget or {}),
        duration_seconds=task.duration_seconds,
        priority=task.priority,
        required_capabilities=list(
            (task.meta or {}).get("required_capabilities", [])
        ),
        status=run_contracts[-1].status,
        current_run=run_contracts[-1],
        created_at=task.created_at,
    )
    if include_runs:
        return MissionDetail(**values, runs=run_contracts)
    return MissionSummary(**values)


def _snapshot(task: TaskModel) -> dict:
    return {
        "objective": task.objective,
        "expected_outcome": task.expected_outcome,
        "acceptance_criteria": list(task.acceptance_criteria or []),
        "autonomy": dict(task.autonomy or {}),
        "resources": list(task.resources or []),
        "budget": dict(task.budget or {}),
        "duration_seconds": task.duration_seconds,
    }


@router.post("", response_model=MissionDetail, status_code=201)
def create_mission(
    body: MissionCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _idempotency_key(idempotency_key)
    request_fingerprint = _canonical_fingerprint(
        {"command": "create", "payload": body.model_dump(mode="json")}
    )
    previous_command = _principal_command(
        db, principal=principal, command="create", key=key
    )
    if previous_command is not None:
        if previous_command.request_fingerprint != request_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key déjà utilisée avec un autre payload",
            )
        previous_task = _mission_or_404(db, previous_command.task_id)
        ensure_access(
            db, principal, project_id=previous_task.project_id, minimum_role="viewer"
        )
        return _mission_contract(db, previous_task, include_runs=True)

    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    project = db.get(ProjectModel, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    _validate_assignment(db, body, project, principal)
    try:
        enforce_project_mission_capacity(db, body.project_id)
    except BudgetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    task = TaskModel(
        project_id=body.project_id,
        team_id=body.team_id,
        agent_instance_id=body.agent_instance_id,
        title=body.title,
        description=body.objective,
        status="queued",
        priority=body.priority,
        meta={
            "mission": True,
            "execution_mode": "real",
            "required_capabilities": body.required_capabilities,
        },
        is_mission=1,
        objective=body.objective,
        expected_outcome=body.expected_outcome,
        acceptance_criteria=body.acceptance_criteria,
        autonomy=body.autonomy.model_dump(mode="json"),
        resources=[item.model_dump(mode="json") for item in body.resources],
        budget=body.budget.model_dump(mode="json"),
        duration_seconds=body.duration_seconds,
        created_by_user_id=principal,
        attempt_counter=1,
    )
    db.add(task)
    db.flush()
    # Instantané des extensions (MCP + skills) figé dans la même transaction que la mission.
    task.meta = {
        **(task.meta or {}),
        "extensions": resolve_project_extensions(db, body.project_id).model_dump(mode="json"),
    }
    run = TaskRunModel(
        task_id=task.id,
        agent_instance_id=body.agent_instance_id,
        status=MissionRunStatus.QUEUED.value,
        attempt_number=1,
        fencing_token=1,
        plan={"mission_snapshot": body.model_dump(mode="json")},
        technical_validation={"status": "pending"},
        user_acceptance={"status": "pending"},
    )
    db.add(run)
    db.flush()
    task.active_run_id = run.id
    db.add(
        MissionCommandModel(
            task_id=task.id,
            task_run_id=run.id,
            command="create",
            idempotency_key=key,
            principal_id=principal,
            request_fingerprint=request_fingerprint,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous_command = _principal_command(
            db, principal=principal, command="create", key=key
        )
        if previous_command is None:
            raise HTTPException(status_code=409, detail="Création concurrente")
        if previous_command.request_fingerprint != request_fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key déjà utilisée avec un autre payload",
            )
        previous_task = _mission_or_404(db, previous_command.task_id)
        ensure_access(
            db, principal, project_id=previous_task.project_id, minimum_role="viewer"
        )
        return _mission_contract(db, previous_task, include_runs=True)
    _emit(
        db,
        background,
        Event(
            type="mission.created",
            **_task_event_ids(db, task),
            task_run_id=run.id,
            payload={"title": task.title, "attempt_number": 1, "status": "queued"},
        ),
    )
    return _mission_contract(db, task, include_runs=True)


@router.get("", response_model=list[MissionSummary])
def list_missions(
    project_id: str | None = None,
    status: MissionRunStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    query = db.query(TaskModel).filter(
        TaskModel.is_mission == 1,
        TaskModel.project_id.in_(accessible_project_ids(db, principal)),
    )
    if project_id is not None:
        ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
        query = query.filter_by(project_id=project_id)
    tasks = query.order_by(TaskModel.created_at.desc()).all()
    missions = [_mission_contract(db, task, include_runs=False) for task in tasks]
    if status is not None:
        missions = [mission for mission in missions if mission.status == status]
    return missions[:limit]


@router.get("/by-run/{run_id}", response_model=MissionDetail)
def get_mission_by_run(
    run_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    run = db.get(TaskRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Tentative introuvable")
    task = _mission_or_404(db, run.task_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    return _mission_contract(db, task, include_runs=True)


@router.get("/{mission_id}", response_model=MissionDetail)
def get_mission(
    mission_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    return _mission_contract(db, task, include_runs=True)


@router.get("/{mission_id}/runs", response_model=list[MissionRun])
def list_mission_runs(
    mission_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    rows = (
        db.query(TaskRunModel)
        .filter_by(task_id=task.id)
        .order_by(TaskRunModel.attempt_number, TaskRunModel.created_at)
        .all()
    )
    return [mission_run_contract(db, row) for row in rows]


def _invalidate_run_approvals(db: Session, run_id: str, reason: str) -> None:
    now = utcnow()
    # The run row is locked by the caller before this compare-and-set.  Keeping
    # invalidation in the same transaction makes STOPPING win over a concurrent
    # human decision without relying on stale ORM instances.
    with db.no_autoflush:
        db.query(ApprovalModel).filter(
            ApprovalModel.task_run_id == run_id,
            ApprovalModel.status.in_(["WAITING_APPROVAL", "APPROVED"]),
        ).update(
            {
                ApprovalModel.status: "INVALIDATED",
                ApprovalModel.invalidated_at: now,
                ApprovalModel.invalidated_reason: reason,
            },
            synchronize_session=False,
        )


@router.post("/{mission_id}/stop", response_model=MissionStopResponse)
def stop_mission(
    mission_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _idempotency_key(idempotency_key)
    request_fingerprint = _canonical_fingerprint(
        {"command": "stop", "mission_id": mission_id}
    )
    terminal = {"blocked", "succeeded", "failed", "cancelled", "interrupted"}
    for _ in range(5):
        task = _mission_or_404(db, mission_id)
        ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
        previous_command = _principal_command(
            db, principal=principal, command="stop", key=key
        )
        if previous_command is not None:
            if (
                previous_command.task_id != task.id
                or previous_command.request_fingerprint != request_fingerprint
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key déjà utilisée pour un autre arrêt",
                )
            previous_run = db.get(TaskRunModel, previous_command.task_run_id)
            if previous_run is None or previous_run.task_id != task.id:
                raise HTTPException(
                    status_code=409, detail="Commande d'arrêt incohérente"
                )
            return MissionStopResponse(
                mission_id=task.id,
                run=mission_run_contract(db, previous_run),
                already_stopped=True,
            )

        run = (
            db.query(TaskRunModel)
            .filter_by(task_id=task.id)
            .order_by(TaskRunModel.attempt_number.desc(), TaskRunModel.created_at.desc())
            .with_for_update()
            .first()
        )
        if run is None:
            raise HTTPException(status_code=409, detail="Mission sans tentative")
        source_status = run.status
        already_stopped = source_status in terminal or source_status == "stopping"
        if not already_stopped:
            now = utcnow()
            target_status = "cancelled" if source_status == "queued" else "stopping"
            updates = {
                TaskRunModel.status: target_status,
                TaskRunModel.stop_requested_at: run.stop_requested_at or now,
                TaskRunModel.stop_requested_by_user_id: (
                    run.stop_requested_by_user_id or principal
                ),
            }
            if target_status == "cancelled":
                updates[TaskRunModel.finished_at] = now
            transitioned = (
                db.query(TaskRunModel)
                .filter(
                    TaskRunModel.id == run.id,
                    TaskRunModel.status == source_status,
                )
                .update(updates, synchronize_session=False)
            )
            if transitioned != 1:
                db.rollback()
                continue
            db.refresh(run)
            if target_status == "cancelled":
                task.status = "backlog"
                task.active_run_id = None
            else:
                task.status = "in_progress"
            _invalidate_run_approvals(db, run.id, "mission_stopped")

        db.add(
            MissionCommandModel(
                task_id=task.id,
                task_run_id=run.id,
                command="stop",
                idempotency_key=key,
                principal_id=principal,
                request_fingerprint=request_fingerprint,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        if not already_stopped:
            _emit(
                db,
                background,
                Event(
                    type="mission.stop_requested",
                    **_task_event_ids(db, task),
                    task_run_id=run.id,
                    payload={
                        "status": run.status,
                        "attempt_number": run.attempt_number,
                    },
                ),
            )
        return MissionStopResponse(
            mission_id=task.id,
            run=mission_run_contract(db, run),
            already_stopped=already_stopped,
        )
    raise HTTPException(status_code=409, detail="État d'arrêt concurrent instable")


def _idempotency_key(value: str | None) -> str:
    key = value or ""
    if (
        not 1 <= len(key) <= 200
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in key)
    ):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key requis (1 à 200 caractères ASCII visibles)",
        )
    return key


def _retry_replay(
    db: Session,
    *,
    principal: str,
    key: str,
    task_id: str,
    request_fingerprint: str,
) -> TaskRunModel | None:
    command = _principal_command(db, principal=principal, command="retry", key=key)
    if command is None:
        return None
    if (
        command.task_id != task_id
        or command.request_fingerprint != request_fingerprint
    ):
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key déjà utilisée pour une autre relance ou un autre payload",
        )
    if command.task_run_id is None:
        raise HTTPException(status_code=409, detail="Commande idempotente incohérente")
    run = db.get(TaskRunModel, command.task_run_id)
    if run is None or run.task_id != task_id:
        raise HTTPException(status_code=409, detail="Commande idempotente incohérente")
    return run


def _retry_replay_after_rollback(
    db: Session,
    *,
    principal: str,
    key: str,
    task_id: str,
    request_fingerprint: str,
) -> TaskRunModel | None:
    """Rouvre une lecture idempotente sans réutiliser l'autorisation annulée.

    ``rollback`` ferme aussi la transaction dans laquelle l'appartenance avait été
    vérifiée. La relire avant le replay évite de divulguer une tentative après une
    révocation concurrente.
    """

    db.rollback()
    current_task = _mission_or_404(db, task_id)
    ensure_access(
        db,
        principal,
        project_id=current_task.project_id,
        minimum_role="member",
    )
    return _retry_replay(
        db,
        principal=principal,
        key=key,
        task_id=task_id,
        request_fingerprint=request_fingerprint,
    )


@router.post("/{mission_id}/retry", response_model=MissionRun, status_code=201)
def retry_mission(
    mission_id: str,
    body: MissionRetryRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _idempotency_key(idempotency_key)
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    request_fingerprint = _canonical_fingerprint(
        {
            "command": "retry",
            "mission_id": task.id,
            "payload": body.model_dump(mode="json"),
        }
    )
    replayed_run = _retry_replay(
        db,
        principal=principal,
        key=key,
        task_id=task.id,
        request_fingerprint=request_fingerprint,
    )
    if replayed_run is not None:
        return mission_run_contract(db, replayed_run)

    task_id = task.id
    project_id = task.project_id
    # La lecture d'accès ci-dessus ne doit pas devenir la transaction de décision.
    # SQLite prend son verrou d'écriture avant toute lecture concurrentielle ; sur
    # PostgreSQL, les verrous suivent run -> projet/policy -> mission, comme le
    # chemin de réservation budgétaire du worker.
    begin_budget_write(db)
    task = _mission_or_404(db, task_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    if task.project_id != project_id:
        raise HTTPException(status_code=409, detail="Le projet de la mission a changé")
    try:
        policy, task, latest = lock_mission_retry_context(
            db,
            task_id=task_id,
            project_id=project_id,
        )
    except BudgetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    # L'attente des verrous run/policy peut avoir laissé le temps de révoquer l'accès.
    ensure_access(db, principal, project_id=project_id, minimum_role="member")
    # Une requête de même clé a pu valider sa commande pendant notre attente.
    # Le replay précède les plafonds afin de rester idempotent même si cette
    # première relance a consommé la dernière place autorisée.
    replayed_run = _retry_replay(
        db,
        principal=principal,
        key=key,
        task_id=task_id,
        request_fingerprint=request_fingerprint,
    )
    if replayed_run is not None:
        return mission_run_contract(db, replayed_run)
    if latest is None:
        raise HTTPException(status_code=409, detail="Mission sans tentative")
    if latest.status in _ACTIVE_RUN_STATES or task.active_run_id is not None:
        replayed_run = _retry_replay_after_rollback(
            db,
            principal=principal,
            key=key,
            task_id=task_id,
            request_fingerprint=request_fingerprint,
        )
        if replayed_run is not None:
            return mission_run_contract(db, replayed_run)
        raise HTTPException(status_code=409, detail="Une tentative est encore active")
    if latest.status == "succeeded":
        acceptance = (latest.user_acceptance or {}).get("status", "pending")
        if acceptance != "rejected":
            raise HTTPException(
                status_code=409,
                detail="Une réussite doit être rejetée explicitement avant relance",
            )
    elif latest.status not in _RETRYABLE_RUN_STATES:
        raise HTTPException(status_code=409, detail="Cette tentative ne peut pas être relancée")

    try:
        enforce_mission_retry_limit(db, task, policy)
    except BudgetServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    observed_attempt_counter = int(task.attempt_counter or 0)
    updated = (
        db.query(TaskModel)
        .filter(
            TaskModel.id == task.id,
            TaskModel.project_id == project_id,
            TaskModel.active_run_id.is_(None),
            TaskModel.attempt_counter == observed_attempt_counter,
        )
        .update(
            {TaskModel.attempt_counter: TaskModel.attempt_counter + 1},
            synchronize_session=False,
        )
    )
    if updated != 1:
        replayed_run = _retry_replay_after_rollback(
            db,
            principal=principal,
            key=key,
            task_id=task_id,
            request_fingerprint=request_fingerprint,
        )
        if replayed_run is not None:
            return mission_run_contract(db, replayed_run)
        raise HTTPException(status_code=409, detail="Une tentative concurrente a gagné")
    db.refresh(task)
    attempt_number = task.attempt_counter
    run = TaskRunModel(
        task_id=task.id,
        agent_instance_id=task.agent_instance_id,
        status="queued",
        attempt_number=attempt_number,
        fencing_token=attempt_number,
        plan={"mission_snapshot": _snapshot(task), "retry_reason": body.reason},
        technical_validation={"status": "pending"},
        user_acceptance={"status": "pending"},
        logs=[{"level": "info", "message": f"Relance contrôlée: {body.reason}"}],
    )
    command = MissionCommandModel(
        task_id=task.id,
        command="retry",
        idempotency_key=key,
        principal_id=principal,
        request_fingerprint=request_fingerprint,
    )
    db.add_all([run, command])
    try:
        db.flush()
        command.task_run_id = run.id
        task.active_run_id = run.id
        task.status = "queued"
        db.commit()
    except IntegrityError:
        replayed_run = _retry_replay_after_rollback(
            db,
            principal=principal,
            key=key,
            task_id=task_id,
            request_fingerprint=request_fingerprint,
        )
        if replayed_run is None:
            raise HTTPException(status_code=409, detail="Relance concurrente")
        return mission_run_contract(db, replayed_run)
    _emit(
        db,
        background,
        Event(
            type="mission.retried",
            **_task_event_ids(db, task),
            task_run_id=run.id,
            payload={"attempt_number": attempt_number, "reason": body.reason},
        ),
    )
    return mission_run_contract(db, run)


@router.post("/{mission_id}/runs/{run_id}/acceptance", response_model=MissionRun)
def decide_acceptance(
    mission_id: str,
    run_id: str,
    body: MissionAcceptanceDecision,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    run = (
        db.query(TaskRunModel)
        .filter_by(id=run_id)
        .with_for_update()
        .first()
    )
    if run is None or run.task_id != task.id:
        raise HTTPException(status_code=404, detail="Tentative introuvable")
    if run.status != "succeeded" or (run.technical_validation or {}).get("status") != "passed":
        raise HTTPException(
            status_code=409,
            detail="Seule une tentative techniquement réussie peut être acceptée",
        )
    current = (run.user_acceptance or {}).get("status", "pending")
    if current != "pending":
        if current == body.decision:
            return mission_run_contract(db, run)
        raise HTTPException(status_code=409, detail="Acceptation déjà décidée")
    decision = {
        "status": body.decision,
        "comment": body.comment,
        "decided_by": principal,
        "decided_at": utcnow().isoformat(),
    }
    # Compare-and-set sur le seul champ décisionnel : ``user_acceptance->>'status'``
    # (``json_extract`` sous SQLite). Comparer le document JSON entier n'est pas
    # portable : PostgreSQL n'a pas d'opérateur d'égalité pour ``json``. Un statut
    # absent (document vide des tentatives historiques) vaut « pending », comme
    # dans la lecture ci-dessus.
    acceptance_status = TaskRunModel.user_acceptance["status"].as_string()
    decided = (
        db.query(TaskRunModel)
        .filter(
            TaskRunModel.id == run.id,
            or_(acceptance_status == "pending", acceptance_status.is_(None)),
        )
        .update(
            {TaskRunModel.user_acceptance: decision},
            synchronize_session=False,
        )
    )
    if decided != 1:
        db.rollback()
        current_run = db.get(TaskRunModel, run_id)
        if current_run is None:
            raise HTTPException(status_code=404, detail="Tentative introuvable")
        current = (current_run.user_acceptance or {}).get("status", "pending")
        if current == body.decision:
            return mission_run_contract(db, current_run)
        raise HTTPException(status_code=409, detail="Acceptation déjà décidée")
    db.refresh(run)
    task.status = "done" if body.decision == "accepted" else "blocked"
    db.commit()
    _emit(
        db,
        background,
        Event(
            type=f"mission.{body.decision}",
            **_task_event_ids(db, task),
            task_run_id=run.id,
            payload={"comment": body.comment, "decided_by": principal},
        ),
    )
    return mission_run_contract(db, run)


def _comment_contract(row: MissionCommentModel) -> MissionComment:
    return MissionComment(
        id=row.id,
        mission_id=row.task_id,
        run_id=row.task_run_id,
        author_user_id=row.author_user_id,
        body=row.body,
        created_at=row.created_at,
    )


def _idempotent_comment(
    db: Session,
    *,
    principal: str,
    run_id: str,
    key: str,
) -> MissionCommentModel | None:
    return (
        db.query(MissionCommentModel)
        .filter_by(
            author_user_id=principal,
            task_run_id=run_id,
            idempotency_key=key,
        )
        .first()
    )


def _replay_comment(
    row: MissionCommentModel,
    *,
    task_id: str,
    request_fingerprint: str,
) -> MissionComment:
    if row.task_id != task_id or row.request_fingerprint != request_fingerprint:
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key déjà utilisée avec un autre commentaire",
        )
    return _comment_contract(row)


@router.post("/{mission_id}/comments", response_model=MissionComment, status_code=201)
def add_comment(
    mission_id: str,
    body: MissionCommentCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="member")
    key = _idempotency_key(idempotency_key) if idempotency_key is not None else None
    if key is not None and body.run_id is None:
        raise HTTPException(
            status_code=422,
            detail="run_id est requis pour rendre un commentaire idempotent",
        )
    if body.run_id is not None:
        run = db.get(TaskRunModel, body.run_id)
        if run is None or run.task_id != task.id:
            raise HTTPException(status_code=422, detail="Tentative hors de la mission")
    request_fingerprint = _canonical_fingerprint(
        {"body": body.body, "run_id": body.run_id}
    )
    if key is not None:
        existing = _idempotent_comment(
            db,
            principal=principal,
            run_id=body.run_id,
            key=key,
        )
        if existing is not None:
            return _replay_comment(
                existing,
                task_id=task.id,
                request_fingerprint=request_fingerprint,
            )
    comment = MissionCommentModel(
        task_id=task.id,
        task_run_id=body.run_id,
        author_user_id=principal,
        body=body.body,
        idempotency_key=key,
        request_fingerprint=request_fingerprint,
    )
    db.add(comment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if key is None or body.run_id is None:
            raise HTTPException(
                status_code=409, detail="Création de commentaire concurrente"
            ) from exc
        existing = _idempotent_comment(
            db,
            principal=principal,
            run_id=body.run_id,
            key=key,
        )
        if existing is None:
            raise HTTPException(
                status_code=409, detail="Création de commentaire concurrente"
            ) from exc
        return _replay_comment(
            existing,
            task_id=task.id,
            request_fingerprint=request_fingerprint,
        )
    db.refresh(comment)
    return _comment_contract(comment)


@router.get("/{mission_id}/comments", response_model=list[MissionComment])
def list_comments(
    mission_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    task = _mission_or_404(db, mission_id)
    ensure_access(db, principal, project_id=task.project_id, minimum_role="viewer")
    rows = (
        db.query(MissionCommentModel)
        .filter_by(task_id=task.id)
        .order_by(MissionCommentModel.created_at, MissionCommentModel.id)
        .all()
    )
    return [_comment_contract(row) for row in rows]
