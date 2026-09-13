"""API des routines planifiées, de leur calendrier et de leur webhook."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from acp_contracts import (
    AutomationCreate,
    AutomationDetail,
    AutomationRunSummary,
    AutomationSummary,
    AutomationUpdate,
    AutomationWebhookSecret,
    AutomationWebhookStatus,
    AutomationWebhookTrigger,
    CalendarEntry,
)
from acp_database.models import AutomationModel, AutomationRunModel

from .. import automation_service as service
from ..deps import (
    accessible_agent_ids,
    accessible_project_ids,
    ensure_access,
    get_db,
    get_principal,
)
from ..events_bus import forward_event

router = APIRouter(tags=["automations"])


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


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, service.AutomationNotFound):
        return HTTPException(status_code=404, detail="Automatisation introuvable")
    if isinstance(error, service.ProjectNotFound):
        return HTTPException(status_code=404, detail="Projet introuvable")
    if isinstance(error, service.AssignmentInvalid):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, service.WebhookAuthenticationFailed):
        return HTTPException(
            status_code=401,
            detail="Authentification du webhook refusée",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    raise error


def _automation_for_access(
    db: Session,
    principal: str,
    automation_id: str,
    *,
    minimum_role: str,
) -> AutomationModel:
    try:
        row = service.automation_or_error(db, automation_id)
    except service.AutomationNotFound as exc:
        raise _translate_error(exc) from exc
    ensure_access(
        db,
        principal,
        project_id=row.project_id,
        minimum_role=minimum_role,
    )
    return row


def _forward(background: BackgroundTasks, result: service.ServiceResult) -> None:
    for event in result.events:
        background.add_task(forward_event, event)


@router.post(
    "/projects/{project_id}/automations",
    response_model=AutomationDetail,
    status_code=201,
)
def create_automation(
    project_id: str,
    body: AutomationCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    ensure_access(db, principal, project_id=project_id, minimum_role="member")
    try:
        result = service.create_automation(
            db,
            project_id=project_id,
            body=body,
            principal_id=principal,
            allowed_agent_ids=accessible_agent_ids(db, principal),
        )
    except (service.AutomationServiceError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    _forward(background, result)
    return service.detail_contract(db, result.value)


@router.get("/automations", response_model=list[AutomationSummary])
def list_automations(
    project_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    visible = accessible_project_ids(db, principal)
    query = db.query(AutomationModel).filter(AutomationModel.project_id.in_(visible))
    if project_id is not None:
        ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
        query = query.filter(AutomationModel.project_id == project_id)
    if enabled is not None:
        query = query.filter(AutomationModel.enabled == int(enabled))
    rows = (
        query.order_by(AutomationModel.created_at.desc(), AutomationModel.id.desc())
        .limit(limit)
        .all()
    )
    return [service.summary_contract(row) for row in rows]


# Cette route statique doit précéder ``/{automation_id}`` dans le schéma et dans la
# documentation, sinon « calendar » ressemble à tort à un identifiant.
@router.get("/automations/calendar", response_model=list[CalendarEntry])
def automation_calendar(
    start: datetime | None = None,
    end: datetime | None = None,
    project_id: str | None = None,
    automation_id: str | None = None,
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    current = service.utcnow()
    start = start or current - timedelta(days=30)
    end = end or current + timedelta(days=90)
    visible = accessible_project_ids(db, principal)
    query = db.query(AutomationModel).filter(AutomationModel.project_id.in_(visible))
    if project_id is not None:
        ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
        query = query.filter(AutomationModel.project_id == project_id)
    if automation_id is not None:
        row = _automation_for_access(
            db, principal, automation_id, minimum_role="viewer"
        )
        if project_id is not None and row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Automatisation introuvable")
        query = query.filter(AutomationModel.id == automation_id)
    try:
        return service.list_calendar(
            db,
            query.order_by(AutomationModel.id).all(),
            start=start,
            end=end,
            now=current,
            limit=limit,
        )
    except ValueError as exc:
        raise _translate_error(exc) from exc


@router.get("/automations/{automation_id}", response_model=AutomationDetail)
def get_automation(
    automation_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="viewer")
    return service.detail_contract(db, row)


@router.patch("/automations/{automation_id}", response_model=AutomationDetail)
def update_automation(
    automation_id: str,
    body: AutomationUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="member")
    try:
        result = service.update_automation(
            db,
            row,
            body=body,
            allowed_agent_ids=accessible_agent_ids(db, principal),
        )
    except (service.AutomationServiceError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    _forward(background, result)
    return service.detail_contract(db, result.value)


@router.post("/automations/{automation_id}/enable", response_model=AutomationDetail)
def enable_automation(
    automation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="member")
    try:
        result = service.set_automation_enabled(db, row, enabled=True)
    except (service.AutomationServiceError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    _forward(background, result)
    return service.detail_contract(db, result.value)


@router.post("/automations/{automation_id}/disable", response_model=AutomationDetail)
def disable_automation(
    automation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="member")
    result = service.set_automation_enabled(db, row, enabled=False)
    _forward(background, result)
    return service.detail_contract(db, result.value)


@router.post(
    "/automations/{automation_id}/trigger",
    response_model=AutomationRunSummary,
    status_code=201,
)
def trigger_automation_manually(
    automation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _idempotency_key(idempotency_key)
    _automation_for_access(db, principal, automation_id, minimum_role="member")
    try:
        result = service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="manual",
            scheduled_for=service.utcnow(),
            identity=key,
            principal_id=principal,
        )
    except (service.AutomationServiceError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    _forward(background, result)
    return service.run_contract(result.value)


@router.get(
    "/automations/{automation_id}/runs",
    response_model=list[AutomationRunSummary],
)
def list_automation_runs(
    automation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _automation_for_access(db, principal, automation_id, minimum_role="viewer")
    rows = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation_id)
        .order_by(
            AutomationRunModel.scheduled_for.desc(), AutomationRunModel.id.desc()
        )
        .limit(limit)
        .all()
    )
    return [service.run_contract(row) for row in rows]


@router.get(
    "/automations/{automation_id}/webhook",
    response_model=AutomationWebhookStatus,
)
def get_webhook_status(
    automation_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="viewer")
    return service.webhook_status_contract(row)


@router.post(
    "/automations/{automation_id}/webhook",
    response_model=AutomationWebhookSecret,
    status_code=201,
)
def enable_or_rotate_webhook(
    automation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="member")
    result = service.rotate_webhook(db, row)
    _forward(background, result)
    return result.value


@router.delete(
    "/automations/{automation_id}/webhook",
    response_model=AutomationWebhookStatus,
)
def disable_automation_webhook(
    automation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    row = _automation_for_access(db, principal, automation_id, minimum_role="member")
    result = service.disable_webhook(db, row)
    _forward(background, result)
    return result.value


def _bearer_secret(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None
    return token


@router.post(
    "/automations/{automation_id}/webhook/trigger",
    response_model=AutomationRunSummary,
    status_code=201,
)
def trigger_automation_webhook(
    automation_id: str,
    body: AutomationWebhookTrigger,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    try:
        service.authenticate_webhook(
            db, automation_id, _bearer_secret(authorization)
        )
        result = service.materialize_occurrence(
            db,
            automation_id=automation_id,
            trigger_kind="webhook",
            scheduled_for=service.utcnow(),
            identity=body.event_id,
        )
    except (service.AutomationServiceError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    _forward(background, result)
    return service.run_contract(result.value)
