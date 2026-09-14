"""Planificateur transactionnel des automatisations.

Le worker appelle ce service exclusivement via le routeur authentifié.  La base
reste l'arbitre de toutes les décisions importantes : singleton du leader, fence,
curseur ``next_run_at`` et unicité de l'occurrence matérialisée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from acp_contracts import Event
from acp_contracts.schedule import ScheduleError, fire_key as schedule_fire_key
from acp_database.models import (
    AutomationModel,
    AutomationRunModel,
    SchedulerLeaseModel,
    TaskModel,
    TaskRunModel,
)

from .alerts_service import open_or_escalate_alert
from .automation_service import (
    AssignmentInvalid,
    materialize_occurrence,
    next_run_after,
)
from .events_bus import publish

SCHEDULER_KEY = "automation-scheduler"
SCHEDULER_LEASE_ID = "automation-scheduler"
SCHEDULER_LEASE_SECONDS = 45
MAX_TICK_AUTOMATIONS = 100
CATCHUP_GRACE_SECONDS = 30
INVALID_CONFIGURATION_RETRY_SECONDS = 300

TERMINAL_RUN_STATES = frozenset(
    {"blocked", "succeeded", "failed", "cancelled", "interrupted"}
)
FAILURE_RUN_STATES = frozenset({"blocked", "failed", "interrupted"})
ORDERED_STREAK_OUTCOMES = frozenset({"launched", "failed"})
ROUTINE_CONFIGURATION_ERRORS = (ValidationError, ScheduleError, AssignmentInvalid)


class SchedulerServiceError(RuntimeError):
    """Erreur de protocole sûre à traduire par le routeur."""


class SchedulerLeaseBusy(SchedulerServiceError):
    """Un autre processus détient encore le bail singleton."""


class SchedulerFenceRejected(SchedulerServiceError):
    """Le détenteur, le fence ou l'expiration ne correspondent plus."""


@dataclass(frozen=True)
class SchedulerLease:
    worker_id: str
    holder_id: str
    fencing_token: int
    lease_expires_at: datetime
    acquired: bool


@dataclass
class SchedulerTick:
    reconciled: int = 0
    disabled_after_failures: int = 0
    examined: int = 0
    launched: int = 0
    replayed: int = 0
    skipped_concurrency: int = 0
    skipped_disabled: int = 0
    catchup_skipped: int = 0
    failed: int = 0


def utcnow() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("un instant conscient du fuseau est requis")
    return value.astimezone(UTC)


def _stored_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_holder_id(holder_id: str) -> None:
    if (
        not isinstance(holder_id, str)
        or not 16 <= len(holder_id) <= 64
        or not holder_id.isascii()
        or not holder_id.isalnum()
    ):
        raise ValueError("holder_id ASCII alphanumérique invalide")


def _ensure_write_transaction(db: Session) -> None:
    """Prend le verrou d'écriture avant toute lecture décisionnelle sous SQLite."""

    connection = db.connection()
    if connection.dialect.name != "sqlite":
        return
    driver = getattr(connection.connection, "driver_connection", None)
    if driver is None or getattr(driver, "in_transaction", False):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _locked_lease(db: Session, *, create: bool) -> SchedulerLeaseModel | None:
    _ensure_write_transaction(db)
    row = (
        db.query(SchedulerLeaseModel)
        .filter_by(scheduler_key=SCHEDULER_KEY)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if row is not None or not create:
        return row

    candidate = SchedulerLeaseModel(
        id=SCHEDULER_LEASE_ID,
        scheduler_key=SCHEDULER_KEY,
        fencing_token=0,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        # PostgreSQL peut voir deux créations initiales. La clé unique choisit et
        # le perdant relit la ligne gagnante sous verrou.
        return (
            db.query(SchedulerLeaseModel)
            .filter_by(scheduler_key=SCHEDULER_KEY)
            .with_for_update()
            .populate_existing()
            .one()
        )
    return candidate


def acquire_scheduler_lease(
    db: Session,
    *,
    worker_id: str,
    holder_id: str,
    now: datetime | None = None,
) -> SchedulerLease:
    """Acquiert ou renouvelle le singleton, sans jamais partager un fence."""

    _validate_holder_id(holder_id)
    row = _locked_lease(db, create=True)
    assert row is not None
    # L'horloge réelle est lue après le verrou. Une requête qui a attendu une
    # autre transaction ne doit pas renouveler avec son heure d'arrivée périmée.
    moment = _utc(now) if now is not None else utcnow()
    expiry = _stored_utc(row.lease_expires_at)
    active = expiry is not None and expiry > moment and row.released_at is None
    same_holder = row.owner_worker_id == worker_id and row.holder_id == holder_id
    if active and not same_holder:
        db.rollback()
        raise SchedulerLeaseBusy("planificateur déjà détenu")

    acquired = not active
    if acquired:
        row.fencing_token = int(row.fencing_token or 0) + 1
        row.owner_worker_id = worker_id
        row.holder_id = holder_id
    renewed_expiry = moment + timedelta(seconds=SCHEDULER_LEASE_SECONDS)
    previous_renewal = _stored_utc(row.last_renewed_at)
    row.last_renewed_at = (
        max(previous_renewal, moment)
        if active and previous_renewal is not None
        else moment
    )
    # Même avec une horloge injectée ou corrigée en arrière, le détenteur courant
    # ne raccourcit jamais son propre bail.
    row.lease_expires_at = (
        max(expiry, renewed_expiry) if active and expiry else renewed_expiry
    )
    row.released_at = None
    db.commit()
    result = SchedulerLease(
        worker_id=worker_id,
        holder_id=holder_id,
        fencing_token=row.fencing_token,
        lease_expires_at=_utc(row.lease_expires_at),
        acquired=acquired,
    )
    db.expire_all()
    return result


def _require_live_fence(
    db: Session,
    *,
    worker_id: str,
    holder_id: str,
    fencing_token: int,
    now: datetime | None = None,
) -> tuple[SchedulerLeaseModel, datetime]:
    _validate_holder_id(holder_id)
    if (
        not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 1
    ):
        raise SchedulerFenceRejected("fence planificateur invalide")
    row = _locked_lease(db, create=False)
    moment = _utc(now) if now is not None else utcnow()
    expiry = _stored_utc(row.lease_expires_at) if row is not None else None
    if (
        row is None
        or row.owner_worker_id != worker_id
        or row.holder_id != holder_id
        or row.fencing_token != fencing_token
        or row.released_at is not None
        or expiry is None
        or expiry <= moment
    ):
        db.rollback()
        raise SchedulerFenceRejected("bail planificateur absent, expiré ou remplacé")
    return row, moment


def release_scheduler_lease(
    db: Session,
    *,
    worker_id: str,
    holder_id: str,
    fencing_token: int,
    now: datetime | None = None,
) -> None:
    """Libère le bail courant; un ancien fence ne peut libérer son successeur."""

    row = _locked_lease(db, create=False)
    moment = _utc(now) if now is not None else utcnow()
    if (
        row is None
        or row.owner_worker_id != worker_id
        or row.holder_id != holder_id
        or row.fencing_token != fencing_token
        or row.released_at is not None
    ):
        db.rollback()
        raise SchedulerFenceRejected("bail planificateur déjà remplacé")
    row.released_at = moment
    row.lease_expires_at = moment
    db.commit()
    db.expire_all()


def _register_failure(
    db: Session,
    automation: AutomationModel,
    *,
    task_id: str | None = None,
    task_run_id: str | None = None,
) -> bool:
    """Incrémente le suffixe ordonné et alerte seulement au franchissement actif."""

    automation.consecutive_failures = int(automation.consecutive_failures or 0) + 1
    threshold = max(1, int(automation.failure_threshold or 3))
    if automation.consecutive_failures < threshold:
        return False

    was_enabled = bool(automation.enabled)
    if not was_enabled:
        return False
    automation.enabled = 0
    automation.next_run_at = None
    open_or_escalate_alert(
        db,
        project_id=automation.project_id,
        kind="automation.repeated_failures",
        severity="critical",
        title="Automatisation arrêtée après des échecs répétés",
        detail=(
            "Le seuil d'échecs consécutifs a été atteint; "
            "l'automatisation a été désactivée."
        ),
        task_id=task_id,
        automation_id=automation.id,
        dimensions={"automation_id": automation.id},
    )
    publish(
        db,
        Event(
            type="automation.disabled_after_failures",
            project_id=automation.project_id,
            task_id=task_id,
            task_run_id=task_run_id,
            payload={
                "automation_id": automation.id,
                "consecutive_failures": automation.consecutive_failures,
                "failure_threshold": threshold,
            },
        ),
        commit=False,
        forward=False,
    )
    return True


def _has_earlier_unobserved_streak_occurrence(
    db: Session, occurrence: AutomationRunModel
) -> bool:
    """Dit si un verdict antérieur doit encore être incorporé au suffixe.

    Les verdicts de configuration sans tâche participent au même ordre nominal
    que les exécutions lancées. Les ignorer ici permettrait à un échec immédiat
    de dépasser une tâche plus ancienne encore en cours.
    """

    earlier = aliased(AutomationRunModel)
    return bool(
        db.query(
            exists().where(
                and_(
                    earlier.automation_id == occurrence.automation_id,
                    earlier.outcome.in_(ORDERED_STREAK_OUTCOMES),
                    earlier.completion_observed_at.is_(None),
                    or_(
                        earlier.scheduled_for < occurrence.scheduled_for,
                        and_(
                            earlier.scheduled_for == occurrence.scheduled_for,
                            earlier.id < occurrence.id,
                        ),
                    ),
                )
            )
        ).scalar()
    )


def _reconcile_terminal_runs(
    db: Session, *, observed_at: datetime, limit: int = 500
) -> tuple[int, int]:
    """Incorpore chaque verdict dans l'ordre nominal, une seule fois.

    Une occurrence lancée est classée d'après sa tentative initiale, même si un
    retry manuel suit. Un échec de configuration est déjà terminal à sa création,
    mais attend lui aussi tout verdict nominalement antérieur.
    """

    initial_attempt_id = (
        select(TaskRunModel.id)
        .where(TaskRunModel.task_id == TaskModel.id)
        .order_by(
            TaskRunModel.attempt_number.asc(),
            TaskRunModel.created_at.asc(),
            TaskRunModel.id.asc(),
        )
        .limit(1)
        .correlate(TaskModel)
        .scalar_subquery()
    )
    reconciled = 0
    disabled = 0
    earlier = aliased(AutomationRunModel)
    while reconciled < limit:
        candidates = (
            db.query(AutomationRunModel, TaskModel, TaskRunModel)
            .outerjoin(TaskModel, TaskModel.id == AutomationRunModel.task_id)
            .outerjoin(TaskRunModel, TaskRunModel.id == initial_attempt_id)
            .filter(
                AutomationRunModel.completion_observed_at.is_(None),
                AutomationRunModel.outcome.in_(ORDERED_STREAK_OUTCOMES),
                or_(
                    AutomationRunModel.outcome == "failed",
                    and_(
                        AutomationRunModel.outcome == "launched",
                        TaskRunModel.status.in_(TERMINAL_RUN_STATES),
                    ),
                ),
                ~exists().where(
                    and_(
                        earlier.automation_id == AutomationRunModel.automation_id,
                        earlier.outcome.in_(ORDERED_STREAK_OUTCOMES),
                        earlier.completion_observed_at.is_(None),
                        or_(
                            earlier.scheduled_for
                            < AutomationRunModel.scheduled_for,
                            and_(
                                earlier.scheduled_for
                                == AutomationRunModel.scheduled_for,
                                earlier.id < AutomationRunModel.id,
                            ),
                        ),
                    )
                ),
            )
            .order_by(
                AutomationRunModel.scheduled_for,
                AutomationRunModel.id,
            )
            .limit(limit - reconciled)
            # PostgreSQL refuse ``FOR UPDATE`` sans cible sur le côté nullable
            # d'un ``LEFT OUTER JOIN``. Seule l'occurrence porte le verdict que
            # cette boucle arbitre ; les lignes Task/TaskRun sont des instantanés
            # de lecture et ne doivent donc pas être verrouillées ici.
            .with_for_update(of=AutomationRunModel)
            .populate_existing()
            .all()
        )
        if not candidates:
            break
        for occurrence, task, attempt in candidates:
            status = "failed" if occurrence.outcome == "failed" else attempt.status
            automation = (
                db.query(AutomationModel)
                .filter_by(id=occurrence.automation_id)
                .with_for_update()
                .populate_existing()
                .one_or_none()
            )
            if automation is None:
                occurrence.completion_observed_at = observed_at
                occurrence.completion_status = status
                reconciled += 1
                continue
            if status == "succeeded":
                automation.consecutive_failures = 0
            elif status in FAILURE_RUN_STATES:
                if _register_failure(
                    db,
                    automation,
                    task_id=task.id if task is not None else None,
                    task_run_id=attempt.id if attempt is not None else None,
                ):
                    disabled += 1
            occurrence.completion_observed_at = observed_at
            occurrence.completion_status = status
            reconciled += 1
        db.flush()
    return reconciled, disabled


def _safe_future_cursor(automation: AutomationModel, *, now: datetime) -> datetime:
    """Retourne un futur strict, même si le calendrier persistant est corrompu."""

    try:
        candidate = next_run_after(automation, now)
    except ROUTINE_CONFIGURATION_ERRORS:
        candidate = None
    if candidate is None or candidate <= now:
        return now + timedelta(seconds=INVALID_CONFIGURATION_RETRY_SECONDS)
    return candidate


def _persist_scheduler_outcome(
    db: Session,
    automation: AutomationModel,
    *,
    nominal: datetime,
    fired_at: datetime,
    outcome: str,
    detail: str,
    reason_code: str,
    next_run_at: datetime | None,
) -> tuple[AutomationRunModel, bool]:
    """Écrit un verdict sans mission; la clé SQL décide encore des replays."""

    key = schedule_fire_key(automation.id, nominal)
    existing = (
        db.query(AutomationRunModel)
        .filter_by(automation_id=automation.id, fire_key=key)
        .populate_existing()
        .first()
    )
    if existing is not None:
        cursor = _stored_utc(automation.next_run_at)
        if cursor is not None and cursor <= nominal:
            automation.last_fire_key = key
            automation.next_run_at = next_run_at
        return existing, True

    run = AutomationRunModel(
        automation_id=automation.id,
        fire_key=key,
        scheduled_for=nominal,
        fired_at=fired_at,
        schedule_timezone=automation.timezone,
        trigger_kind="schedule",
        outcome=outcome,
        detail=detail,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        replay = (
            db.query(AutomationRunModel)
            .filter_by(automation_id=automation.id, fire_key=key)
            .populate_existing()
            .one()
        )
        return replay, True

    automation.last_fire_key = key
    automation.next_run_at = next_run_at
    publish(
        db,
        Event(
            type="automation.run_materialized",
            project_id=automation.project_id,
            payload={
                "automation_id": automation.id,
                "automation_run_id": run.id,
                "trigger_kind": "schedule",
                "outcome": outcome,
                "reason_code": reason_code,
            },
        ),
        commit=False,
        forward=False,
    )
    return run, False


def _record_configuration_failure(
    db: Session,
    automation: AutomationModel,
    *,
    nominal: datetime,
    fired_at: datetime,
) -> tuple[AutomationRunModel, bool, bool]:
    """Transforme une configuration illisible en verdict durable et expurgé."""

    run, replayed = _persist_scheduler_outcome(
        db,
        automation,
        nominal=nominal,
        fired_at=fired_at,
        outcome="failed",
        detail="configuration de routine invalide",
        reason_code="invalid_configuration",
        next_run_at=_safe_future_cursor(automation, now=fired_at),
    )
    disabled = False
    if not replayed:
        run.completion_status = "failed"
        db.flush()
        if not _has_earlier_unobserved_streak_occurrence(db, run):
            disabled = _register_failure(db, automation)
            run.completion_observed_at = fired_at
    return run, replayed, disabled


def _due_automation(db: Session, *, now: datetime) -> AutomationModel | None:
    statement = (
        select(AutomationModel)
        .where(
            AutomationModel.enabled == 1,
            AutomationModel.next_run_at.is_not(None),
            AutomationModel.next_run_at <= now,
        )
        .order_by(AutomationModel.next_run_at, AutomationModel.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    return db.execute(statement).scalar_one_or_none()


def _locked_automation_by_id(
    db: Session, automation_id: str
) -> AutomationModel | None:
    return (
        db.query(AutomationModel)
        .filter_by(id=automation_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )


def _catchup_shape(
    automation: AutomationModel, *, nominal: datetime, now: datetime
) -> tuple[bool, bool, datetime | None]:
    """Retourne ``(hors_grâce, plusieurs_dues, premier_tir_futur)``."""

    following = next_run_after(automation, nominal)
    multiple_due = following is not None and following <= now
    missed = now - nominal > timedelta(seconds=CATCHUP_GRACE_SECONDS)
    return missed, multiple_due, next_run_after(automation, now)


def run_scheduler_tick(
    db: Session,
    *,
    worker_id: str,
    holder_id: str,
    fencing_token: int,
    limit: int = 25,
    now: datetime | None = None,
) -> SchedulerTick:
    """Réconcilie les fins puis matérialise au plus ``limit`` occurrences dues.

    Chaque occurrence est une transaction autonome parce que la primitive commune
    ``materialize_occurrence`` en possède le commit. Avant chaque transaction, le
    bail et son fence sont reverrouillés. Une reprise après réponse perdue rejoue la
    même clé nominale, que l'unicité SQL transforme en lecture sans deuxième tâche.
    """

    if not 1 <= limit <= MAX_TICK_AUTOMATIONS:
        raise ValueError("limit hors bornes")
    stats = SchedulerTick()
    first_iteration = True
    while stats.examined < limit:
        # ``expire_on_commit=False`` est volontaire ailleurs dans l'application.
        # Le scheduler traverse plusieurs transactions dans une même Session : il
        # doit donc expirer explicitement tout objet avant la décision suivante.
        db.expire_all()
        lease, moment = _require_live_fence(
            db,
            worker_id=worker_id,
            holder_id=holder_id,
            fencing_token=fencing_token,
            now=now,
        )
        lease.last_renewed_at = moment
        lease.lease_expires_at = moment + timedelta(seconds=SCHEDULER_LEASE_SECONDS)

        if first_iteration:
            stats.reconciled, stats.disabled_after_failures = _reconcile_terminal_runs(
                db, observed_at=moment
            )
            first_iteration = False
            db.commit()
            db.expire_all()
            continue

        automation = _due_automation(db, now=moment)
        if automation is None:
            db.commit()
            db.expire_all()
            return stats

        automation_id = automation.id
        nominal = _stored_utc(automation.next_run_at)
        assert nominal is not None
        stats.examined += 1
        try:
            missed, multiple_due, future = _catchup_shape(
                automation, nominal=nominal, now=moment
            )

            if missed and automation.catchup_policy == "skip":
                _, replayed = _persist_scheduler_outcome(
                    db,
                    automation,
                    nominal=nominal,
                    fired_at=moment,
                    outcome="skipped_catchup",
                    detail=(
                        "occurrence manquée; grâce de "
                        f"{CATCHUP_GRACE_SECONDS} secondes dépassée"
                    ),
                    reason_code="catchup_grace_exceeded",
                    next_run_at=future,
                )
                db.commit()
                db.expire_all()
                if replayed:
                    stats.replayed += 1
                else:
                    stats.catchup_skipped += 1
                continue

            if multiple_due and automation.catchup_policy == "run_once":
                # Ce déplacement précède la primitive commune mais partage son
                # commit : un crash ne peut relancer chaque tir manqué.
                automation.next_run_at = future

            result = materialize_occurrence(
                db,
                automation_id=automation.id,
                trigger_kind="schedule",
                scheduled_for=nominal,
                now=moment,
            )
        except ROUTINE_CONFIGURATION_ERRORS:
            # ``materialize_occurrence`` avait peut-être déjà flushé sa ligne
            # provisoire. Tout annuler évite de conserver un verdict partiel, puis
            # le même fence reprend un verrou propre pour écrire l'échec expurgé.
            db.rollback()
            db.expire_all()
            lease, failure_moment = _require_live_fence(
                db,
                worker_id=worker_id,
                holder_id=holder_id,
                fencing_token=fencing_token,
                now=now,
            )
            lease.last_renewed_at = failure_moment
            lease.lease_expires_at = failure_moment + timedelta(
                seconds=SCHEDULER_LEASE_SECONDS
            )
            current = _locked_automation_by_id(db, automation_id)
            current_cursor = (
                _stored_utc(current.next_run_at) if current is not None else None
            )
            if (
                current is not None
                and bool(current.enabled)
                and current_cursor == nominal
            ):
                _, replayed, disabled = _record_configuration_failure(
                    db,
                    current,
                    nominal=nominal,
                    fired_at=failure_moment,
                )
                stats.replayed += int(replayed)
                stats.failed += int(not replayed)
                stats.disabled_after_failures += int(disabled)
            db.commit()
            db.expire_all()
            continue

        if result.replayed:
            stats.replayed += 1
            # Défense de reprise pour une ancienne base qui contiendrait déjà la
            # clé de tir mais aurait conservé un curseur obsolète. Les écritures
            # modernes sont atomiques, toutefois ce rattrapage évite une boucle
            # infinie sur un état historique ou importé.
            current = _locked_automation_by_id(db, automation.id)
            if current is not None:
                cursor = _stored_utc(current.next_run_at)
                if cursor is not None and cursor <= nominal:
                    current.last_fire_key = result.value.fire_key
                    current.next_run_at = next_run_after(current, nominal)
            db.commit()
            db.expire_all()
        elif result.value.outcome == "launched":
            stats.launched += 1
        elif result.value.outcome == "skipped_concurrency":
            stats.skipped_concurrency += 1
        elif result.value.outcome == "skipped_disabled":
            stats.skipped_disabled += 1
    # Les matérialisations normales valident déjà leur transaction. Ce commit
    # couvre le cas défensif d'un replay ancien qui aurait laissé un curseur sale.
    db.commit()
    db.expire_all()
    return stats
