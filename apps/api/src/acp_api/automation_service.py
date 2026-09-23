"""Service métier des automatisations, indépendant de FastAPI.

Les routes authentifient et autorisent les appels. Ce module possède la mutation
transactionnelle : une occurrence, sa mission, sa première tentative et ses
événements durables sont validés ensemble, ou pas du tout.
"""

from __future__ import annotations

import hashlib
import heapq
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Generic, Literal, TypeVar

from pydantic import ValidationError
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    AutomationCreate,
    AutomationDetail,
    AutomationMissionTemplate,
    AutomationRunSummary,
    AutomationSchedule,
    AutomationSummary,
    AutomationTriggerKind,
    AutomationUpdate,
    AutomationWebhookRotationRequest,
    AutomationWebhookSecret,
    AutomationWebhookStatus,
    CalendarEntry,
    Event,
)
from acp_contracts.schedule import (
    CronExpression,
    IntervalSchedule,
    fire_key as schedule_fire_key,
    next_occurrence as next_cron_occurrence,
)
from acp_database.models import (
    AgentInstanceModel,
    AutomationCommandModel,
    AutomationModel,
    AutomationRunModel,
    AutomationWebhookRotationModel,
    ProjectModel,
    TaskModel,
    TaskRunModel,
    TeamModel,
    WorkspaceModel,
)

from .budget_service import BudgetServiceError, enforce_project_mission_capacity
from .events_bus import store_event
from .extensions import resolve_project_extensions

T = TypeVar("T")

ACTIVE_RUN_STATES = frozenset(
    {"queued", "preparing", "running", "waiting_approval", "stopping"}
)
CALENDAR_MAX_DAYS = 366
CALENDAR_MAX_ENTRIES = 500
RECENT_RUN_LIMIT = 20
AutomationCommandType = Literal["update", "enable", "disable", "webhook.disable"]


class AutomationServiceError(RuntimeError):
    """Erreur métier traduite en réponse HTTP par le routeur."""


class AutomationNotFound(AutomationServiceError):
    pass


class ProjectNotFound(AutomationServiceError):
    pass


class AssignmentInvalid(AutomationServiceError):
    pass


class WebhookAuthenticationFailed(AutomationServiceError):
    pass


class IdempotencyConflict(AutomationServiceError):
    pass


@dataclass(frozen=True)
class ServiceResult(Generic[T]):
    value: T
    events: tuple[Event, ...] = field(default_factory=tuple)
    replayed: bool = False


def utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("un instant doit porter un fuseau")
    return moment.astimezone(UTC)


def _database_utc(moment: datetime | None) -> datetime | None:
    """Rattache UTC aux anciennes colonnes SQLite qui perdent leur fuseau."""

    if moment is None:
        return None
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _canonical_fingerprint(value: dict) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _project(db: Session, project_id: str) -> ProjectModel:
    row = db.get(ProjectModel, project_id)
    if row is None:
        raise ProjectNotFound(project_id)
    return row


def automation_or_error(db: Session, automation_id: str) -> AutomationModel:
    row = (
        db.query(AutomationModel)
        .filter_by(id=automation_id)
        .populate_existing()
        .one_or_none()
    )
    if row is None:
        raise AutomationNotFound(automation_id)
    return row


def _ensure_sqlite_write_transaction(db: Session) -> None:
    """Sérialise une décision avant sa première lecture sous SQLite."""

    connection = db.connection()
    if connection.dialect.name != "sqlite":
        return
    driver = getattr(connection.connection, "driver_connection", None)
    if driver is None or getattr(driver, "in_transaction", False):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _locked_automation(db: Session, automation_id: str) -> AutomationModel:
    """Recharge la routine courante sous verrou, sans réutiliser l'identity-map."""

    _ensure_sqlite_write_transaction(db)
    row = (
        db.query(AutomationModel)
        .filter_by(id=automation_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if row is None:
        raise AutomationNotFound(automation_id)
    return row


def _schedule_contract(row: AutomationModel) -> AutomationSchedule:
    return AutomationSchedule(
        kind=row.schedule_kind,
        expression=row.schedule_expression,
        timezone=row.timezone,
    )


def run_contract(row: AutomationRunModel) -> AutomationRunSummary:
    return AutomationRunSummary(
        id=row.id,
        automation_id=row.automation_id,
        fire_key=row.fire_key,
        scheduled_for=row.scheduled_for,
        fired_at=row.fired_at,
        task_id=row.task_id,
        trigger_kind=row.trigger_kind,
        outcome=row.outcome,
        detail=row.detail or "",
        completion_status=row.completion_status,
    )


def summary_contract(row: AutomationModel) -> AutomationSummary:
    return AutomationSummary(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        description=row.description or "",
        schedule=_schedule_contract(row),
        enabled=bool(row.enabled),
        catchup_policy=row.catchup_policy,
        max_concurrent_runs=row.max_concurrent_runs,
        next_run_at=row.next_run_at,
        created_at=_database_utc(row.created_at),
    )


def detail_contract(db: Session, row: AutomationModel) -> AutomationDetail:
    recent = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=row.id)
        .order_by(AutomationRunModel.scheduled_for.desc(), AutomationRunModel.id.desc())
        .limit(RECENT_RUN_LIMIT)
        .populate_existing()
        .all()
    )
    summary = summary_contract(row).model_dump()
    return AutomationDetail(
        **summary,
        mission_template=AutomationMissionTemplate.model_validate(
            row.mission_template or {}
        ),
        recent_runs=[run_contract(item) for item in recent],
    )


def webhook_status_contract(row: AutomationModel) -> AutomationWebhookStatus:
    return AutomationWebhookStatus(
        enabled=bool(row.webhook_enabled),
        secret_configured=row.webhook_secret_hash is not None,
        endpoint_path=f"/automations/{row.id}/webhook/trigger",
        rotated_at=row.webhook_rotated_at,
    )


def _automation_postcondition(
    row: AutomationModel, fields: set[str]
) -> dict[str, object]:
    """Capture uniquement les champs visés, dans leur forme contractuelle."""

    result: dict[str, object] = {}
    for field in sorted(fields):
        if field == "name":
            result[field] = row.name
        elif field == "description":
            result[field] = row.description or ""
        elif field == "schedule":
            result[field] = _schedule_contract(row).model_dump(mode="json")
        elif field == "mission_template":
            result[field] = AutomationMissionTemplate.model_validate(
                row.mission_template or {}
            ).model_dump(mode="json")
        elif field == "catchup_policy":
            result[field] = row.catchup_policy
        elif field == "max_concurrent_runs":
            result[field] = row.max_concurrent_runs
        elif field == "enabled":
            result[field] = bool(row.enabled)
        elif field == "next_run_at":
            moment = _database_utc(row.next_run_at)
            result[field] = moment.isoformat() if moment is not None else None
        elif field == "webhook_enabled":
            result[field] = bool(row.webhook_enabled)
        elif field == "webhook_secret_configured":
            result[field] = row.webhook_secret_hash is not None
        elif field == "webhook_rotation_number":
            result[field] = row.webhook_rotation_number
        else:  # Une entrée de journal inconnue indique une corruption, pas un no-op.
            raise IdempotencyConflict(
                "Postcondition de commande d'automatisation inconnue"
            )
    return result


def _mutation_fingerprint(
    command: AutomationCommandType, payload: dict[str, object]
) -> str:
    return _canonical_fingerprint({"command": command, "payload": payload})


def _replayed_mutation_command(
    db: Session,
    row: AutomationModel,
    *,
    command: AutomationCommandType,
    principal_id: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> AutomationCommandModel | None:
    replay = (
        db.query(AutomationCommandModel)
        .filter_by(
            automation_id=row.id,
            principal_id=principal_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        .populate_existing()
        .one_or_none()
    )
    if replay is None:
        return None
    if replay.request_fingerprint != request_fingerprint:
        raise IdempotencyConflict(
            "Idempotency-Key déjà utilisée avec une autre intention"
        )
    expected = replay.postcondition or {}
    current = _automation_postcondition(row, set(expected))
    # Une mutation ultérieure portant sur un autre champ ne rend pas cette
    # commande obsolète. La postcondition ciblée est l'arbitre : elle refuse bien
    # un ancien PATCH dont le champ a été réécrit, tout en permettant au client de
    # récupérer le résultat d'une réponse perdue après une mutation disjointe.
    # ``result_revision`` reste conservée dans le journal pour l'audit.
    if current != expected:
        raise IdempotencyConflict(
            "Cette commande a été remplacée par une mutation plus récente"
        )
    return replay


def _record_mutation_command(
    db: Session,
    row: AutomationModel,
    *,
    command: AutomationCommandType,
    principal_id: str,
    idempotency_key: str,
    request_fingerprint: str,
    postcondition_fields: set[str],
) -> AutomationCommandModel:
    row.mutation_revision += 1
    journal = AutomationCommandModel(
        automation_id=row.id,
        principal_id=principal_id,
        command=command,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        postcondition=_automation_postcondition(row, postcondition_fields),
        result_revision=row.mutation_revision,
    )
    db.add(journal)
    db.flush()
    return journal


def _event_for(
    db: Session,
    row: AutomationModel,
    event_type: str,
    *,
    payload: dict,
    task: TaskModel | None = None,
    task_run: TaskRunModel | None = None,
) -> Event:
    project = db.get(ProjectModel, row.project_id)
    workspace = (
        db.get(WorkspaceModel, project.workspace_id) if project is not None else None
    )
    return Event(
        type=event_type,
        organization_id=workspace.organization_id if workspace else None,
        workspace_id=project.workspace_id if project else None,
        department_id=project.department_id if project else None,
        project_id=row.project_id,
        team_id=task.team_id if task else None,
        agent_instance_id=task.agent_instance_id if task else None,
        task_id=task.id if task else None,
        task_run_id=task_run.id if task_run else None,
        payload=payload,
    )


def _store_events(db: Session, events: list[Event]) -> None:
    for event in events:
        store_event(db, event, commit=False, emitted_by="automation-service")


def _validate_assignment(
    db: Session,
    template: AutomationMissionTemplate,
    project: ProjectModel,
    *,
    allowed_agent_ids: set[str] | None,
) -> None:
    try:
        template.to_mission_create(project.id)
    except ValidationError:
        raise AssignmentInvalid("Le gabarit de mission ou son workspace ne correspond pas au projet.") from None
    if template.team_id is not None:
        team = db.get(TeamModel, template.team_id)
        if team is None or team.project_id != project.id:
            raise AssignmentInvalid("Équipe hors du projet")
    if template.agent_instance_id is not None:
        agent = db.get(AgentInstanceModel, template.agent_instance_id)
        if agent is None or agent.workspace_id != project.workspace_id:
            raise AssignmentInvalid("Agent hors du workspace du projet")
        if allowed_agent_ids is not None and agent.id not in allowed_agent_ids:
            raise AssignmentInvalid("Agent inaccessible depuis ce projet")


def next_run_after(
    row: AutomationModel,
    after: datetime,
    *,
    reset_interval_anchor: bool = False,
) -> datetime | None:
    """Calcule le prochain tir, en conservant la phase d'un intervalle.

    Une expression cron est calendaire. Un intervalle, lui, repart de son
    ``next_run_at`` persistant : les lectures de calendrier ne déplacent donc jamais
    sa phase. Lors d'une première activation ou d'un changement d'expression, un
    nouvel ancrage est explicitement demandé.
    """

    after_utc = _as_utc(after)
    schedule = _schedule_contract(row)
    parsed = schedule.parsed()
    if isinstance(parsed, CronExpression):
        return next_cron_occurrence(parsed, after_utc, schedule.resolved_timezone())

    assert isinstance(parsed, IntervalSchedule)
    anchor = None if reset_interval_anchor else row.next_run_at
    if anchor is None:
        return parsed.next_occurrence(after_utc)
    anchor = _as_utc(anchor)
    if anchor > after_utc:
        return anchor
    elapsed = (after_utc - anchor).total_seconds()
    steps = int(elapsed // parsed.seconds) + 1
    return anchor + timedelta(seconds=steps * parsed.seconds)


def create_automation(
    db: Session,
    *,
    project_id: str,
    body: AutomationCreate,
    principal_id: str,
    idempotency_key: str,
    allowed_agent_ids: set[str],
) -> ServiceResult[AutomationModel]:
    request_fingerprint = _canonical_fingerprint(
        {"command": "create", "payload": body.model_dump(mode="json")}
    )
    # La lecture et l'insertion doivent appartenir à la même section critique sur
    # SQLite. Sur PostgreSQL, l'index unique reste l'arbitre final si deux
    # transactions ne voient encore aucune ligne.
    _ensure_sqlite_write_transaction(db)
    replay = (
        db.query(AutomationModel)
        .filter_by(
            project_id=project_id,
            created_by_user_id=principal_id,
            create_idempotency_key=idempotency_key,
        )
        .populate_existing()
        .one_or_none()
    )
    if replay is not None:
        if replay.create_request_fingerprint != request_fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key déjà utilisée avec un autre payload"
            )
        db.commit()
        return ServiceResult(replay, replayed=True)

    project = _project(db, project_id)
    _validate_assignment(
        db, body.mission_template, project, allowed_agent_ids=allowed_agent_ids
    )
    row = AutomationModel(
        project_id=project_id,
        name=body.name,
        description=body.description,
        schedule_kind=body.schedule.kind,
        schedule_expression=body.schedule.expression,
        timezone=body.schedule.timezone,
        mission_template=body.mission_template.model_dump(mode="json"),
        enabled=0,
        catchup_policy=body.catchup_policy,
        max_concurrent_runs=body.max_concurrent_runs,
        next_run_at=None,
        created_by_user_id=principal_id,
        create_idempotency_key=idempotency_key,
        create_request_fingerprint=request_fingerprint,
        webhook_enabled=0,
        webhook_secret_hash=None,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(AutomationModel)
            .filter_by(
                project_id=project_id,
                created_by_user_id=principal_id,
                create_idempotency_key=idempotency_key,
            )
            .populate_existing()
            .one_or_none()
        )
        if replay is None:
            raise exc
        if replay.create_request_fingerprint != request_fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key déjà utilisée avec un autre payload"
            ) from exc
        return ServiceResult(replay, replayed=True)
    event = _event_for(
        db,
        row,
        "automation.created",
        payload={"automation_id": row.id, "name": row.name, "enabled": False},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(row, (event,))


def update_automation(
    db: Session,
    row: AutomationModel,
    *,
    body: AutomationUpdate,
    principal_id: str,
    idempotency_key: str,
    allowed_agent_ids: set[str],
    now: datetime | None = None,
) -> ServiceResult[AutomationModel]:
    row = _locked_automation(db, row.id)
    changes = body.model_dump(exclude_unset=True)
    request_fingerprint = _mutation_fingerprint(
        "update", body.model_dump(mode="json", exclude_unset=True)
    )
    replay = _replayed_mutation_command(
        db,
        row,
        command="update",
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        db.commit()
        return ServiceResult(row, replayed=True)
    changed_fields: set[str] = set()
    if "mission_template" in changes:
        template = body.mission_template
        assert template is not None
        _validate_assignment(
            db,
            template,
            _project(db, row.project_id),
            allowed_agent_ids=allowed_agent_ids,
        )
        template_payload = template.model_dump(mode="json")
        if row.mission_template != template_payload:
            row.mission_template = template_payload
            changed_fields.add("mission_template")
    if "name" in changes and row.name != body.name:
        row.name = body.name  # type: ignore[assignment]
        changed_fields.add("name")
    if "description" in changes and row.description != body.description:
        row.description = body.description  # type: ignore[assignment]
        changed_fields.add("description")
    if "catchup_policy" in changes and row.catchup_policy != body.catchup_policy:
        row.catchup_policy = body.catchup_policy  # type: ignore[assignment]
        changed_fields.add("catchup_policy")
    if (
        "max_concurrent_runs" in changes
        and row.max_concurrent_runs != body.max_concurrent_runs
    ):
        row.max_concurrent_runs = body.max_concurrent_runs  # type: ignore[assignment]
        changed_fields.add("max_concurrent_runs")
    schedule = body.schedule if "schedule" in changes else None
    schedule_changed = schedule is not None and (
        row.schedule_kind != schedule.kind
        or row.schedule_expression != schedule.expression
        or row.timezone != schedule.timezone
    )
    if schedule_changed:
        row.schedule_kind = schedule.kind
        row.schedule_expression = schedule.expression
        row.timezone = schedule.timezone
        changed_fields.add("schedule")
    if bool(row.enabled) and schedule_changed:
        row.next_run_at = next_run_after(
            row, now or utcnow(), reset_interval_anchor=True
        )
    if not changed_fields:
        _record_mutation_command(
            db,
            row,
            command="update",
            principal_id=principal_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            postcondition_fields=set(changes),
        )
        db.commit()
        return ServiceResult(row, replayed=True)
    _record_mutation_command(
        db,
        row,
        command="update",
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        postcondition_fields=set(changes),
    )
    event = _event_for(
        db,
        row,
        "automation.updated",
        payload={"automation_id": row.id, "fields": sorted(changed_fields)},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(row, (event,))


def set_automation_enabled(
    db: Session,
    row: AutomationModel,
    *,
    enabled: bool,
    principal_id: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> ServiceResult[AutomationModel]:
    row = _locked_automation(db, row.id)
    command: AutomationCommandType = "enable" if enabled else "disable"
    request_fingerprint = _mutation_fingerprint(command, {})
    replay = _replayed_mutation_command(
        db,
        row,
        command=command,
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        db.commit()
        return ServiceResult(row, replayed=True)
    target = int(enabled)
    if row.enabled == target:
        _record_mutation_command(
            db,
            row,
            command=command,
            principal_id=principal_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            postcondition_fields={"enabled"},
        )
        db.commit()
        return ServiceResult(row, replayed=True)
    row.enabled = target
    row.next_run_at = (
        next_run_after(row, now or utcnow(), reset_interval_anchor=True)
        if enabled
        else None
    )
    _record_mutation_command(
        db,
        row,
        command=command,
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        postcondition_fields={"enabled"},
    )
    event = _event_for(
        db,
        row,
        "automation.enabled" if enabled else "automation.disabled",
        payload={"automation_id": row.id, "enabled": enabled},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(row, (event,))


def rotate_webhook(
    db: Session,
    row: AutomationModel,
    *,
    body: AutomationWebhookRotationRequest,
    principal_id: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> ServiceResult[AutomationWebhookSecret]:
    row = _locked_automation(db, row.id)
    request_fingerprint = _canonical_fingerprint(
        {"command": "webhook.rotate", "payload": body.model_dump(mode="json")}
    )
    hashed_secret = _secret_hash(body.secret)
    replay = (
        db.query(AutomationWebhookRotationModel)
        .filter_by(
            automation_id=row.id,
            principal_id=principal_id,
            idempotency_key=idempotency_key,
        )
        .populate_existing()
        .one_or_none()
    )
    if replay is not None:
        if replay.request_fingerprint != request_fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key déjà utilisée avec un autre secret"
            )
        if (
            not row.webhook_enabled
            or row.webhook_rotation_number != replay.rotation_number
            or not hmac.compare_digest(
                row.webhook_secret_hash or "0" * 64, replay.secret_hash
            )
        ):
            raise IdempotencyConflict(
                "Cette rotation a été remplacée ou le webhook a été désactivé"
            )
        db.commit()
        status = webhook_status_contract(row)
        return ServiceResult(
            AutomationWebhookSecret(**status.model_dump(), secret=body.secret),
            replayed=True,
        )

    rotated_at = _as_utc(now or utcnow())
    rotation_number = row.webhook_rotation_number + 1
    row.webhook_secret_hash = hashed_secret
    row.webhook_enabled = 1
    row.webhook_rotated_at = rotated_at
    row.webhook_rotation_number = rotation_number
    row.mutation_revision += 1
    db.add(
        AutomationWebhookRotationModel(
            automation_id=row.id,
            principal_id=principal_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            secret_hash=hashed_secret,
            rotation_number=rotation_number,
            rotated_at=rotated_at,
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        current = automation_or_error(db, row.id)
        replay = (
            db.query(AutomationWebhookRotationModel)
            .filter_by(
                automation_id=row.id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
            )
            .populate_existing()
            .one_or_none()
        )
        if replay is None:
            raise exc
        if replay.request_fingerprint != request_fingerprint:
            raise IdempotencyConflict(
                "Idempotency-Key déjà utilisée avec un autre secret"
            ) from exc
        if (
            not current.webhook_enabled
            or current.webhook_rotation_number != replay.rotation_number
            or not hmac.compare_digest(
                current.webhook_secret_hash or "0" * 64, replay.secret_hash
            )
        ):
            raise IdempotencyConflict(
                "Cette rotation a été remplacée ou le webhook a été désactivé"
            ) from exc
        status = webhook_status_contract(current)
        return ServiceResult(
            AutomationWebhookSecret(**status.model_dump(), secret=body.secret),
            replayed=True,
        )
    status = webhook_status_contract(row)
    response = AutomationWebhookSecret(**status.model_dump(), secret=body.secret)
    event = _event_for(
        db,
        row,
        "automation.webhook_rotated",
        payload={"automation_id": row.id, "enabled": True},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(response, (event,))


def disable_webhook(
    db: Session,
    row: AutomationModel,
    *,
    principal_id: str,
    idempotency_key: str,
) -> ServiceResult[AutomationWebhookStatus]:
    row = _locked_automation(db, row.id)
    request_fingerprint = _mutation_fingerprint("webhook.disable", {})
    replay = _replayed_mutation_command(
        db,
        row,
        command="webhook.disable",
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        db.commit()
        return ServiceResult(webhook_status_contract(row), replayed=True)
    if not row.webhook_enabled and row.webhook_secret_hash is None:
        _record_mutation_command(
            db,
            row,
            command="webhook.disable",
            principal_id=principal_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            postcondition_fields={
                "webhook_enabled",
                "webhook_secret_configured",
                "webhook_rotation_number",
            },
        )
        db.commit()
        return ServiceResult(webhook_status_contract(row), replayed=True)
    row.webhook_enabled = 0
    row.webhook_secret_hash = None
    _record_mutation_command(
        db,
        row,
        command="webhook.disable",
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        postcondition_fields={
            "webhook_enabled",
            "webhook_secret_configured",
            "webhook_rotation_number",
        },
    )
    response = webhook_status_contract(row)
    event = _event_for(
        db,
        row,
        "automation.webhook_disabled",
        payload={"automation_id": row.id, "enabled": False},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(response, (event,))


def _webhook_credentials_valid(
    row: AutomationModel | None, bearer_secret: str | None
) -> bool:
    supplied_hash = hashlib.sha256((bearer_secret or "").encode("utf-8")).hexdigest()
    expected = row.webhook_secret_hash if row is not None else "0" * 64
    valid = hmac.compare_digest(supplied_hash, expected or "0" * 64)
    return bool(
        row is not None
        and row.webhook_enabled
        and row.webhook_secret_hash is not None
        and valid
    )


def authenticate_webhook(
    db: Session, automation_id: str, bearer_secret: str | None
) -> AutomationModel:
    """Authentifie sous le verrou conservé jusqu'à la matérialisation.

    Rotation et désactivation prennent le même verrou. Elles sont donc ordonnées
    avant l'authentification (l'ancien secret est refusé) ou après le commit du
    déclenchement (le déclenchement était déjà autorisé), jamais entre les deux.
    """

    # Une requête manifestement invalide ne doit jamais prendre le verrou global
    # d'écriture SQLite. Après cette prélecture sans effet, la transaction est
    # close puis la même preuve est revérifiée sous le verrou décisionnel.
    candidate = db.get(AutomationModel, automation_id)
    if not _webhook_credentials_valid(candidate, bearer_secret):
        raise WebhookAuthenticationFailed("webhook non authentifié")
    db.rollback()
    try:
        row = _locked_automation(db, automation_id)
    except AutomationNotFound as exc:
        db.rollback()
        raise WebhookAuthenticationFailed("webhook non authentifié") from exc
    if not _webhook_credentials_valid(row, bearer_secret):
        db.rollback()
        raise WebhookAuthenticationFailed("webhook non authentifié")
    return row


def _external_fire_key(
    automation_id: str,
    trigger_kind: Literal["manual", "webhook"],
    identity: str,
    *,
    principal_id: str | None = None,
) -> str:
    if trigger_kind == "manual" and not principal_id:
        raise ValueError("un principal est requis pour un déclenchement manuel")
    # Une clé manuelle appartient à l'utilisateur authentifié. L'identité webhook
    # reste au contraire globale à la routine, car elle vient de l'émetteur externe.
    scope = principal_id if trigger_kind == "manual" else None
    encoded = json.dumps(
        [automation_id, trigger_kind, scope, identity],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _active_automation_run_count(db: Session, automation_id: str) -> int:
    statement = (
        select(func.count(distinct(TaskModel.id)))
        .select_from(AutomationRunModel)
        .join(TaskModel, TaskModel.id == AutomationRunModel.task_id)
        .join(TaskRunModel, TaskRunModel.task_id == TaskModel.id)
        .where(
            AutomationRunModel.automation_id == automation_id,
            AutomationRunModel.outcome == "launched",
            TaskRunModel.status.in_(ACTIVE_RUN_STATES),
        )
    )
    return int(db.execute(statement).scalar_one())


def _materialization_event(
    db: Session,
    automation: AutomationModel,
    run: AutomationRunModel,
    *,
    task: TaskModel | None = None,
    task_run: TaskRunModel | None = None,
) -> Event:
    # Ni clé d'idempotence, ni event_id, ni payload du webhook ne sont journalisés.
    return _event_for(
        db,
        automation,
        "automation.run_materialized",
        task=task,
        task_run=task_run,
        payload={
            "automation_id": automation.id,
            "automation_run_id": run.id,
            "trigger_kind": run.trigger_kind,
            "outcome": run.outcome,
        },
    )


def _advance_due_schedule(
    automation: AutomationModel, *, nominal: datetime, key: str
) -> None:
    """Avance le curseur seulement quand cette occurrence est encore la courante.

    Un import historique ou un appel retardé ne doit jamais faire régresser un
    ``next_run_at`` déjà plus récent. Pour une occurrence due, l'avancement vit
    dans la même transaction que son verdict, y compris en cas de saturation.
    """

    if not automation.enabled:
        return
    current = (
        _database_utc(automation.next_run_at)
        if automation.next_run_at is not None
        else None
    )
    if current is not None and current > nominal:
        return
    automation.last_fire_key = key
    automation.next_run_at = next_run_after(automation, nominal)


def materialize_occurrence(
    db: Session,
    *,
    automation_id: str,
    trigger_kind: AutomationTriggerKind,
    scheduled_for: datetime,
    identity: str | None = None,
    principal_id: str | None = None,
    now: datetime | None = None,
) -> ServiceResult[AutomationRunModel]:
    """Matérialise une occurrence, quel que soit son déclencheur.

    Le verrou logique sur la ligne parente sérialise le contrôle de concurrence
    sous PostgreSQL et prend un verrou d'écriture anticipé sous SQLite. L'unicité
    ``(automation_id, fire_key)`` reste néanmoins l'arbitre définitif : un rejet de
    la base est relu comme un replay, jamais rejoué en deuxième mission.
    """

    nominal = _as_utc(scheduled_for)
    fired_at = _as_utc(now or utcnow())
    if trigger_kind == "schedule":
        key = schedule_fire_key(automation_id, nominal)
    elif trigger_kind in {"manual", "webhook"} and identity:
        key = _external_fire_key(
            automation_id,
            trigger_kind,
            identity,
            principal_id=principal_id,
        )
    else:
        raise ValueError("une identité stable est requise pour ce déclencheur")

    replay = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation_id, fire_key=key)
        .populate_existing()
        .first()
    )
    if replay is not None:
        return ServiceResult(replay, replayed=True)

    # Le verrou parent sérialise le quota de concurrence et recharge explicitement
    # la ligne : une session réutilisée après commit ne doit jamais décider à partir
    # d'un objet resté dans son identity-map.
    automation = _locked_automation(db, automation_id)

    replay = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation_id, fire_key=key)
        .populate_existing()
        .first()
    )
    if replay is not None:
        db.rollback()
        return ServiceResult(replay, replayed=True)

    run = AutomationRunModel(
        automation_id=automation_id,
        fire_key=key,
        scheduled_for=nominal,
        fired_at=fired_at,
        schedule_timezone=automation.timezone,
        trigger_kind=trigger_kind,
        outcome="failed",
        detail="matérialisation interrompue",
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, fire_key=key)
            .populate_existing()
            .first()
        )
        if replay is None:
            raise exc
        return ServiceResult(replay, replayed=True)

    if not automation.enabled and trigger_kind != "manual":
        run.outcome = "skipped_disabled"
        run.detail = "automatisation désactivée"
        event = _materialization_event(db, automation, run)
        _store_events(db, [event])
        db.commit()
        return ServiceResult(run, (event,))

    if _active_automation_run_count(db, automation_id) >= automation.max_concurrent_runs:
        run.outcome = "skipped_concurrency"
        run.detail = "limite de concurrence atteinte"
        if trigger_kind == "schedule":
            _advance_due_schedule(automation, nominal=nominal, key=key)
        event = _materialization_event(db, automation, run)
        _store_events(db, [event])
        db.commit()
        return ServiceResult(run, (event,))

    template = AutomationMissionTemplate.model_validate(automation.mission_template or {})
    mission = template.to_mission_create(automation.project_id)
    _validate_assignment(
        db, template, _project(db, automation.project_id), allowed_agent_ids=None
    )
    try:
        enforce_project_mission_capacity(db, automation.project_id)
    except BudgetServiceError as exc:
        # La clé de tir reste consommée : rejouer le même événement après qu'une
        # place se libère créerait un effet différé inattendu et casserait
        # l'idempotence du webhook. Une nouvelle demande emploie une nouvelle clé.
        run.outcome = "skipped_concurrency"
        run.detail = exc.detail[:500]
        if trigger_kind == "schedule":
            _advance_due_schedule(automation, nominal=nominal, key=key)
        event = _materialization_event(db, automation, run)
        _store_events(db, [event])
        db.commit()
        return ServiceResult(run, (event,))
    task = TaskModel(
        project_id=automation.project_id,
        team_id=mission.team_id,
        agent_instance_id=mission.agent_instance_id,
        title=mission.title,
        description=mission.objective,
        status="queued",
        priority=mission.priority,
        meta={
            "mission": True,
            "execution_mode": "real",
            "required_capabilities": mission.required_capabilities,
            "execution": mission.execution.model_dump(mode="json") if mission.execution else None,
            "automation": {
                "automation_id": automation.id,
                "automation_run_id": run.id,
                "trigger_kind": trigger_kind,
            },
        },
        is_mission=1,
        objective=mission.objective,
        expected_outcome=mission.expected_outcome,
        acceptance_criteria=mission.acceptance_criteria,
        autonomy=mission.autonomy.model_dump(mode="json"),
        resources=[item.model_dump(mode="json") for item in mission.resources],
        budget=mission.budget.model_dump(mode="json"),
        duration_seconds=mission.duration_seconds,
        created_by_user_id=principal_id or automation.created_by_user_id,
        attempt_counter=1,
    )
    db.add(task)
    db.flush()
    task.meta = {
        **task.meta,
        "extensions": resolve_project_extensions(
            db, automation.project_id
        ).model_dump(mode="json"),
    }
    task_run = TaskRunModel(
        task_id=task.id,
        agent_instance_id=mission.agent_instance_id,
        status="queued",
        attempt_number=1,
        fencing_token=1,
        plan={
            "mission_snapshot": mission.model_dump(mode="json"),
            "automation_snapshot": {
                "id": automation.id,
                "name": automation.name,
                "schedule": _schedule_contract(automation).model_dump(mode="json"),
                "trigger_kind": trigger_kind,
            },
        },
        technical_validation={"status": "pending"},
        user_acceptance={"status": "pending"},
    )
    db.add(task_run)
    db.flush()
    task.active_run_id = task_run.id
    run.task_id = task.id
    run.outcome = "launched"
    run.detail = "mission créée"
    if trigger_kind == "schedule":
        _advance_due_schedule(automation, nominal=nominal, key=key)

    event = _materialization_event(
        db, automation, run, task=task, task_run=task_run
    )
    mission_event = _event_for(
        db,
        automation,
        "mission.created",
        task=task,
        task_run=task_run,
        payload={
            "title": task.title,
            "attempt_number": 1,
            "status": "queued",
            "source": "automation",
            "automation_id": automation.id,
        },
    )
    events = [event, mission_event]
    _store_events(db, events)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation_id, fire_key=key)
            .first()
        )
        if replay is None:
            raise exc
        return ServiceResult(replay, replayed=True)
    return ServiceResult(run, tuple(events))


def list_calendar(
    db: Session,
    automations: list[AutomationModel],
    *,
    start: datetime,
    end: datetime,
    now: datetime | None = None,
    limit: int = CALENDAR_MAX_ENTRIES,
) -> list[CalendarEntry]:
    start_utc = _as_utc(start)
    end_utc = _as_utc(end)
    current = _as_utc(now or utcnow())
    if end_utc <= start_utc:
        raise ValueError("la fin du calendrier doit suivre son début")
    if end_utc - start_utc > timedelta(days=CALENDAR_MAX_DAYS):
        raise ValueError(f"le calendrier est borné à {CALENDAR_MAX_DAYS} jours")
    if not 1 <= limit <= CALENDAR_MAX_ENTRIES:
        raise ValueError(f"le calendrier est borné à {CALENDAR_MAX_ENTRIES} entrées")
    if not automations:
        return []

    by_id = {row.id: row for row in automations}
    materialized = (
        db.query(AutomationRunModel)
        .filter(
            AutomationRunModel.automation_id.in_(by_id),
            AutomationRunModel.scheduled_for >= start_utc,
            AutomationRunModel.scheduled_for < end_utc,
        )
        .order_by(AutomationRunModel.scheduled_for, AutomationRunModel.id)
        .limit(CALENDAR_MAX_ENTRIES)
        .all()
    )
    entries: list[CalendarEntry] = []
    seen: set[tuple[str, datetime]] = set()
    # L'historique n'est jamais reconstruit : seules les occurrences réellement
    # matérialisées ont le droit d'apparaître dans le passé.
    for run in materialized:
        automation = by_id[run.automation_id]
        instant = _as_utc(run.scheduled_for)
        seen.add((automation.id, instant))
        entries.append(
            CalendarEntry.from_occurrence(
                occurs_at_utc=instant,
                automation_id=automation.id,
                automation_name=automation.name,
                state="past" if instant <= current else "planned",
                timezone=run.schedule_timezone or automation.timezone,
                task_id=run.task_id,
                outcome=run.outcome,
            )
        )

    lower = max(start_utc, current)
    schedules: dict[
        str,
        tuple[
            AutomationModel,
            AutomationSchedule,
            CronExpression | IntervalSchedule,
        ],
    ] = {}
    candidates: list[tuple[datetime, str]] = []
    for automation in automations:
        if not automation.enabled:
            continue
        schedule = _schedule_contract(automation)
        parsed = schedule.parsed()
        if isinstance(parsed, CronExpression):
            candidate = next_cron_occurrence(
                parsed,
                lower - timedelta(microseconds=1),
                schedule.resolved_timezone(),
            )
        else:
            assert isinstance(parsed, IntervalSchedule)
            candidate = next_run_after(automation, lower - timedelta(microseconds=1))
        schedules[automation.id] = (automation, schedule, parsed)
        if candidate is not None and candidate < end_utc:
            heapq.heappush(candidates, (candidate, automation.id))

    # Fusion k-way : on produit les occurrences globalement dans l'ordre. Parcourir
    # chaque routine jusqu'à 500 avant de passer à la suivante privilégierait la
    # première routine et pourrait masquer une occurrence plus proche d'une autre.
    generated = 0
    while candidates and generated < limit:
        candidate, automation_id = heapq.heappop(candidates)
        automation, schedule, parsed = schedules[automation_id]
        if (automation.id, candidate) not in seen:
            entries.append(
                CalendarEntry.from_occurrence(
                    occurs_at_utc=candidate,
                    automation_id=automation.id,
                    automation_name=automation.name,
                    state="planned",
                    timezone=automation.timezone,
                )
            )
            generated += 1
        if isinstance(parsed, CronExpression):
            following = next_cron_occurrence(
                parsed, candidate, schedule.resolved_timezone()
            )
        else:
            following = candidate + timedelta(seconds=parsed.seconds)
        if following is not None and following < end_utc:
            heapq.heappush(candidates, (following, automation.id))

    entries.sort(key=lambda item: (item.occurs_at_utc, item.automation_id))
    return entries[:limit]
