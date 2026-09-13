"""Service métier des automatisations, indépendant de FastAPI.

Les routes authentifient et autorisent les appels. Ce module possède la mutation
transactionnelle : une occurrence, sa mission, sa première tentative et ses
événements durables sont validés ensemble, ou pas du tout.
"""

from __future__ import annotations

import hashlib
import heapq
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Generic, Literal, TypeVar

from sqlalchemy import distinct, func, select, update
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
    AutomationModel,
    AutomationRunModel,
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


def _project(db: Session, project_id: str) -> ProjectModel:
    row = db.get(ProjectModel, project_id)
    if row is None:
        raise ProjectNotFound(project_id)
    return row


def automation_or_error(db: Session, automation_id: str) -> AutomationModel:
    row = db.get(AutomationModel, automation_id)
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
    allowed_agent_ids: set[str],
) -> ServiceResult[AutomationModel]:
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
        webhook_enabled=0,
        webhook_secret_hash=None,
    )
    db.add(row)
    db.flush()
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
    allowed_agent_ids: set[str],
    now: datetime | None = None,
) -> ServiceResult[AutomationModel]:
    changes = body.model_dump(exclude_unset=True)
    if "mission_template" in changes:
        template = body.mission_template
        assert template is not None
        _validate_assignment(
            db,
            template,
            _project(db, row.project_id),
            allowed_agent_ids=allowed_agent_ids,
        )
        row.mission_template = template.model_dump(mode="json")
    if "name" in changes:
        row.name = body.name  # type: ignore[assignment]
    if "description" in changes:
        row.description = body.description  # type: ignore[assignment]
    if "catchup_policy" in changes:
        row.catchup_policy = body.catchup_policy  # type: ignore[assignment]
    if "max_concurrent_runs" in changes:
        row.max_concurrent_runs = body.max_concurrent_runs  # type: ignore[assignment]
    schedule_changed = "schedule" in changes
    if schedule_changed:
        schedule = body.schedule
        assert schedule is not None
        row.schedule_kind = schedule.kind
        row.schedule_expression = schedule.expression
        row.timezone = schedule.timezone
    if bool(row.enabled) and schedule_changed:
        row.next_run_at = next_run_after(
            row, now or utcnow(), reset_interval_anchor=True
        )
    db.flush()
    event = _event_for(
        db,
        row,
        "automation.updated",
        payload={"automation_id": row.id, "fields": sorted(changes)},
    )
    _store_events(db, [event])
    db.commit()
    return ServiceResult(row, (event,))


def set_automation_enabled(
    db: Session,
    row: AutomationModel,
    *,
    enabled: bool,
    now: datetime | None = None,
) -> ServiceResult[AutomationModel]:
    target = int(enabled)
    if row.enabled == target:
        return ServiceResult(row, replayed=True)
    row.enabled = target
    row.next_run_at = (
        next_run_after(row, now or utcnow(), reset_interval_anchor=True)
        if enabled
        else None
    )
    db.flush()
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
    db: Session, row: AutomationModel, *, now: datetime | None = None
) -> ServiceResult[AutomationWebhookSecret]:
    raw_secret = secrets.token_urlsafe(32)
    rotated_at = _as_utc(now or utcnow())
    row.webhook_secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    row.webhook_enabled = 1
    row.webhook_rotated_at = rotated_at
    db.flush()
    status = webhook_status_contract(row)
    response = AutomationWebhookSecret(**status.model_dump(), secret=raw_secret)
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
    db: Session, row: AutomationModel
) -> ServiceResult[AutomationWebhookStatus]:
    if not row.webhook_enabled and row.webhook_secret_hash is None:
        return ServiceResult(webhook_status_contract(row), replayed=True)
    row.webhook_enabled = 0
    row.webhook_secret_hash = None
    db.flush()
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


def authenticate_webhook(
    db: Session, automation_id: str, bearer_secret: str | None
) -> AutomationModel:
    """Authentifie sans révéler si l'identifiant ou le secret est fautif."""

    row = db.get(AutomationModel, automation_id)
    supplied_hash = hashlib.sha256((bearer_secret or "").encode("utf-8")).hexdigest()
    expected = row.webhook_secret_hash if row is not None else "0" * 64
    valid = hmac.compare_digest(supplied_hash, expected or "0" * 64)
    if (
        row is None
        or not row.webhook_enabled
        or row.webhook_secret_hash is None
        or not valid
    ):
        raise WebhookAuthenticationFailed("webhook non authentifié")
    return row


def _external_fire_key(
    automation_id: str,
    trigger_kind: Literal["manual", "webhook"],
    identity: str,
) -> str:
    encoded = f"{automation_id}:{trigger_kind}:{identity}".encode("utf-8")
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
        key = _external_fire_key(automation_id, trigger_kind, identity)
    else:
        raise ValueError("une identité stable est requise pour ce déclencheur")

    replay = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation_id, fire_key=key)
        .first()
    )
    if replay is not None:
        return ServiceResult(replay, replayed=True)

    # UPDATE sans changement : verrou de sérialisation portable. Sous SQLite il
    # transforme aussi la transaction différée en transaction d'écriture avant les
    # lectures de concurrence et les SAVEPOINT du journal durable.
    locked = db.execute(
        update(AutomationModel)
        .where(AutomationModel.id == automation_id)
        .values(last_fire_key=AutomationModel.last_fire_key)
    ).rowcount
    if not locked:
        db.rollback()
        raise AutomationNotFound(automation_id)
    automation = automation_or_error(db, automation_id)

    replay = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation_id, fire_key=key)
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
                timezone=automation.timezone,
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
