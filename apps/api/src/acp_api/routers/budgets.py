"""Routes utilisateur et worker des budgets appliqués."""

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import (
    BudgetConsumptionSummary,
    BudgetMutationResult,
    BudgetPermitRequest,
    BudgetUsageDelta,
    ProjectBudgetPolicy,
    ProjectBudgetPolicySummary,
)
from acp_database.models import ProjectModel

from ..budget_service import (
    BudgetServiceError,
    begin_budget_write,
    get_project_consumption,
    get_project_policy,
    load_worker_budget_context,
    put_project_policy,
    record_usage,
    reserve_budget,
)
from ..deps import ensure_access, get_db, get_principal
from .workers import authenticate_worker

router = APIRouter(tags=["budgets"])


def _project_or_404(db: Session, project_id: str) -> ProjectModel:
    project = db.get(ProjectModel, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return project


def _raise_service_error(exc: BudgetServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/projects/{project_id}/budget-policy",
    response_model=ProjectBudgetPolicySummary,
)
def read_budget_policy(
    project_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    project = _project_or_404(db, project_id)
    ensure_access(db, principal, project_id=project.id, minimum_role="viewer")
    try:
        return get_project_policy(db, project)
    except BudgetServiceError as exc:
        _raise_service_error(exc)


@router.get(
    "/projects/{project_id}/budget-usage",
    response_model=BudgetConsumptionSummary,
)
def read_budget_usage(
    project_id: str,
    day: date | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    project = _project_or_404(db, project_id)
    ensure_access(db, principal, project_id=project.id, minimum_role="viewer")
    try:
        return get_project_consumption(db, project, day=day)
    except BudgetServiceError as exc:
        _raise_service_error(exc)


@router.put(
    "/projects/{project_id}/budget-policy",
    response_model=ProjectBudgetPolicySummary,
)
def replace_budget_policy(
    project_id: str,
    body: ProjectBudgetPolicy,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    project = _project_or_404(db, project_id)
    ensure_access(db, principal, project_id=project.id, minimum_role="member")
    begin_budget_write(db)
    project = _project_or_404(db, project_id)
    # ``begin_budget_write`` ferme volontairement la transaction de lecture
    # précédente avant de prendre le verrou d'écriture SQLite. L'autorisation
    # observée avant ce rollback n'est donc plus une preuve : une révocation de
    # membership peut avoir gagné entre les deux transactions. Le premier
    # contrôle reste utile pour ne pas laisser un appel non autorisé prendre le
    # verrou, puis celui-ci réétablit la frontière dans la transaction qui écrit.
    ensure_access(db, principal, project_id=project.id, minimum_role="member")
    try:
        return put_project_policy(db, project, body)
    except BudgetServiceError as exc:
        _raise_service_error(exc)


def _worker_context(
    db: Session,
    *,
    worker_id: str,
    run_id: str,
    authorization: str | None,
    fencing_token: int | None,
):
    worker = authenticate_worker(db, worker_id, authorization)
    authenticated_worker_id = worker.id
    begin_budget_write(db)
    worker = authenticate_worker(db, worker_id, authorization)
    if worker.id != authenticated_worker_id:
        raise HTTPException(status_code=401, detail="Identité worker instable")
    try:
        return load_worker_budget_context(
            db,
            worker=worker,
            run_id=run_id,
            fencing_token=fencing_token,
        )
    except BudgetServiceError as exc:
        _raise_service_error(exc)


@router.post(
    "/work/workers/{worker_id}/runs/{run_id}/budget/permit",
    response_model=BudgetMutationResult,
)
def request_budget_permit(
    worker_id: str,
    run_id: str,
    body: BudgetPermitRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    fencing_token: int | None = Header(
        default=None, alias="X-Attempt-Fencing-Token"
    ),
):
    context = _worker_context(
        db,
        worker_id=worker_id,
        run_id=run_id,
        authorization=authorization,
        fencing_token=fencing_token,
    )
    try:
        return reserve_budget(db, context, body)
    except BudgetServiceError as exc:
        _raise_service_error(exc)


@router.post(
    "/work/workers/{worker_id}/runs/{run_id}/budget/usage",
    response_model=BudgetMutationResult,
)
def report_budget_usage(
    worker_id: str,
    run_id: str,
    body: BudgetUsageDelta,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    fencing_token: int | None = Header(
        default=None, alias="X-Attempt-Fencing-Token"
    ),
):
    context = _worker_context(
        db,
        worker_id=worker_id,
        run_id=run_id,
        authorization=authorization,
        fencing_token=fencing_token,
    )
    try:
        return record_usage(db, context, body)
    except BudgetServiceError as exc:
        _raise_service_error(exc)
