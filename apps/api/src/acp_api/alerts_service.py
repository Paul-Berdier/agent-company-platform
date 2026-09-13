"""Transactional alert lifecycle for budgets, automations and storage.

Alerts are durable product state.  They are not an e-mail/webhook delivery queue:
the only channel implemented in Lot F is the authenticated in-app inbox.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    AlertSummary,
    Event,
    NotificationPreferences,
    NotificationPreferencesSummary,
)
from acp_database.models import AlertModel, NotificationPreferencesModel

from .events_bus import publish

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
_ALERT_KIND_MAX = 50
_ALERT_TITLE_MAX = 300
_ALERT_DETAIL_MAX = 10_000


def _ensure_sqlite_write_transaction(db: Session) -> None:
    """Ouvre la vraie transaction avant un SAVEPOINT sous ``pysqlite``.

    Sans ce ``BEGIN IMMEDIATE``, libérer le premier point de sauvegarde peut
    valider l'alerte à l'insu de l'appelant. Le verrou d'écriture sérialise aussi
    les deux créations concurrentes avant que la contrainte unique les arbitre.
    """

    connection = db.connection()
    if connection.dialect.name != "sqlite":
        return
    driver_connection = getattr(connection.connection, "driver_connection", None)
    if driver_connection is None or getattr(driver_connection, "in_transaction", False):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def alert_dedupe_key(
    kind: str, dimensions: Mapping[str, str | None] | None = None
) -> str:
    """Hash canonical, stable and safe to persist for one open cause.

    Titles, exception messages and paths are deliberately excluded by the API: a
    caller supplies only identity dimensions such as automation/provider/limit.
    """

    if not kind or len(kind) > _ALERT_KIND_MAX:
        raise ValueError("le type d'alerte doit contenir entre 1 et 50 caractères")
    normalized_dimensions: dict[str, str] = {}
    for key, value in sorted((dimensions or {}).items()):
        if not isinstance(key, str) or not key:
            raise ValueError("une dimension d'alerte doit avoir un nom non vide")
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError("une dimension d'alerte doit être textuelle")
        normalized_dimensions[key] = value

    identity = {
        "kind": kind,
        "dimensions": normalized_dimensions,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def alert_summary(alert: AlertModel) -> AlertSummary:
    created_at = _utc(alert.created_at)
    assert created_at is not None
    return AlertSummary(
        id=alert.id,
        project_id=alert.project_id,
        kind=alert.kind,
        severity=alert.severity,
        title=alert.title,
        detail=alert.detail or "",
        task_id=alert.task_id,
        automation_id=alert.automation_id,
        acknowledged_at=_utc(alert.acknowledged_at),
        acknowledged_by_user_id=alert.acknowledged_by_user_id,
        acknowledgement_comment=alert.acknowledgement_comment or "",
        created_at=created_at,
    )


def _event(
    db: Session,
    event_type: str,
    alert: AlertModel,
    *,
    has_comment: bool = False,
) -> None:
    publish(
        db,
        Event(
            type=event_type,
            project_id=alert.project_id,
            task_id=alert.task_id,
            payload={
                "alert_id": alert.id,
                "kind": alert.kind,
                "severity": alert.severity,
                "automation_id": alert.automation_id,
                "has_comment": has_comment,
            },
        ),
        commit=False,
        forward=False,
    )


def open_or_escalate_alert(
    db: Session,
    *,
    project_id: str,
    kind: str,
    severity: str,
    title: str,
    detail: str = "",
    task_id: str | None = None,
    automation_id: str | None = None,
    dimensions: Mapping[str, str | None] | None = None,
) -> tuple[AlertModel, str]:
    """Open one cause or monotonically escalate its existing open alert.

    Returns ``(alert, transition)`` where transition is ``opened``, ``escalated``
    or ``unchanged``.  The caller owns the outer commit.
    """

    if severity not in _SEVERITY_RANK:
        raise ValueError("sévérité d'alerte inconnue")
    if not title or len(title) > _ALERT_TITLE_MAX:
        raise ValueError("le titre d'alerte doit contenir entre 1 et 300 caractères")
    if len(detail) > _ALERT_DETAIL_MAX:
        raise ValueError("le détail d'alerte dépasse 10 000 caractères")
    dedupe_key = alert_dedupe_key(kind, dimensions)
    _ensure_sqlite_write_transaction(db)
    alert = (
        db.query(AlertModel)
        .filter_by(project_id=project_id, dedupe_key_active=dedupe_key)
        .with_for_update()
        .first()
    )
    if alert is not None:
        if _SEVERITY_RANK[severity] <= _SEVERITY_RANK[alert.severity]:
            return alert, "unchanged"
        alert.severity = severity
        alert.title = title
        alert.detail = detail
        alert.task_id = task_id or alert.task_id
        alert.automation_id = automation_id or alert.automation_id
        db.flush()
        _event(db, "alert.escalated", alert)
        return alert, "escalated"

    candidate = AlertModel(
        project_id=project_id,
        kind=kind,
        severity=severity,
        title=title,
        detail=detail,
        task_id=task_id,
        automation_id=automation_id,
        acknowledgement_comment="",
        dedupe_key=dedupe_key,
        dedupe_key_active=dedupe_key,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        # Another transaction opened the same cause.  The unique index is the
        # arbiter; the savepoint preserves the surrounding business transaction.
        alert = (
            db.query(AlertModel)
            .filter_by(project_id=project_id, dedupe_key_active=dedupe_key)
            .with_for_update()
            .one()
        )
        if _SEVERITY_RANK[severity] > _SEVERITY_RANK[alert.severity]:
            alert.severity = severity
            alert.title = title
            alert.detail = detail
            alert.task_id = task_id or alert.task_id
            alert.automation_id = automation_id or alert.automation_id
            db.flush()
            _event(db, "alert.escalated", alert)
            return alert, "escalated"
        return alert, "unchanged"
    _event(db, "alert.opened", candidate)
    return candidate, "opened"


def acknowledge_alert(
    db: Session,
    alert: AlertModel,
    *,
    user_id: str,
    comment: str,
) -> tuple[AlertModel, bool]:
    """Acknowledge by compare-and-set; replay emits no second event."""

    now = datetime.now(UTC)
    changed = (
        db.query(AlertModel)
        .filter(AlertModel.id == alert.id, AlertModel.acknowledged_at.is_(None))
        .update(
            {
                AlertModel.acknowledged_at: now,
                AlertModel.acknowledged_by_user_id: user_id,
                AlertModel.acknowledgement_comment: comment,
                AlertModel.dedupe_key_active: None,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    db.expire(alert)
    if not changed:
        return alert, True
    _event(db, "alert.acknowledged", alert, has_comment=bool(comment))
    return alert, False


def notification_preferences_summary(
    row: NotificationPreferencesModel,
) -> NotificationPreferencesSummary:
    updated_at = _utc(row.updated_at)
    assert updated_at is not None
    return NotificationPreferencesSummary(
        project_id=row.project_id,
        channel="in_app",
        enabled=bool(row.enabled),
        minimum_severity=row.minimum_severity,
        budget_alerts=bool(row.budget_alerts),
        automation_failures=bool(row.automation_failures),
        storage_alerts=bool(row.storage_alerts),
        updated_at=updated_at,
    )


def get_or_create_notification_preferences(
    db: Session,
    *,
    project_id: str,
    user_id: str,
) -> NotificationPreferencesModel:
    """Materialise les préférences par défaut, sans doublon concurrent.

    Le point de sauvegarde laisse l'appelant propriétaire de la transaction. La
    contrainte ``(project_id, user_id)`` reste l'arbitre si deux premières lectures
    arrivent ensemble.
    """

    row = (
        db.query(NotificationPreferencesModel)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    if row is not None:
        return row

    _ensure_sqlite_write_transaction(db)
    # Une transaction concurrente peut avoir créé la ligne pendant l'attente du
    # verrou SQLite : relire évite de provoquer une collision devenue certaine.
    row = (
        db.query(NotificationPreferencesModel)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    if row is not None:
        return row

    candidate = NotificationPreferencesModel(
        project_id=project_id,
        user_id=user_id,
        channel="in_app",
        enabled=1,
        minimum_severity="warning",
        budget_alerts=1,
        automation_failures=1,
        storage_alerts=1,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
    except IntegrityError:
        return (
            db.query(NotificationPreferencesModel)
            .filter_by(project_id=project_id, user_id=user_id)
            .one()
        )
    return candidate


def replace_notification_preferences(
    row: NotificationPreferencesModel,
    preferences: NotificationPreferences,
) -> NotificationPreferencesModel:
    """Remplace les préférences de l'utilisateur par le contrat JSON validé."""

    # ``channel`` ne peut être que ``in_app`` dans le contrat et dans la base.
    row.channel = preferences.channel
    row.enabled = int(preferences.enabled)
    row.minimum_severity = preferences.minimum_severity
    row.budget_alerts = int(preferences.budget_alerts)
    row.automation_failures = int(preferences.automation_failures)
    row.storage_alerts = int(preferences.storage_alerts)
    return row
