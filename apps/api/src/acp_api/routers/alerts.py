"""Boîte d'alertes in-app et préférences personnelles par projet."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from acp_contracts import (
    AlertAcknowledge,
    AlertSummary,
    NotificationPreferences,
    NotificationPreferencesSummary,
)
from acp_database.models import AlertModel

from ..alerts_service import (
    acknowledge_alert,
    alert_summary,
    get_or_create_notification_preferences,
    notification_preferences_summary,
    replace_notification_preferences,
)
from ..deps import accessible_project_ids, ensure_access, get_auth_context, get_db, require_csrf
from ..security import AuthContext

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertSummary])
def list_alerts(
    project_id: str | None = None,
    open_state: bool | None = Query(default=None, alias="open"),
    severity: Literal["info", "warning", "critical"] | None = None,
    kind: str | None = Query(default=None, min_length=1, max_length=50),
    limit: int = Query(default=100, ge=1, le=200),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AlertSummary]:
    """Liste stable, toujours bornée aux projets visibles du demandeur."""

    visible = accessible_project_ids(db, context.user.id)
    if project_id is not None:
        visible.intersection_update({project_id})
    if not visible:
        return []

    query = db.query(AlertModel).filter(AlertModel.project_id.in_(visible))
    if open_state is True:
        query = query.filter(AlertModel.acknowledged_at.is_(None))
    elif open_state is False:
        query = query.filter(AlertModel.acknowledged_at.is_not(None))
    if severity is not None:
        query = query.filter(AlertModel.severity == severity)
    if kind is not None:
        query = query.filter(AlertModel.kind == kind)
    rows = (
        query.order_by(AlertModel.created_at.desc(), AlertModel.id.desc())
        .limit(limit)
        .all()
    )
    return [alert_summary(row) for row in rows]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertSummary)
def acknowledge(
    alert_id: str,
    body: AlertAcknowledge,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AlertSummary:
    """Acquitte une cause une seule fois ; une répétition reste sans nouvel effet."""

    visible = accessible_project_ids(db, context.user.id)
    alert = (
        db.query(AlertModel)
        .filter(AlertModel.id == alert_id, AlertModel.project_id.in_(visible))
        .first()
    )
    if alert is None:
        # Même réponse pour un identifiant absent et une autre organisation.
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    ensure_access(
        db,
        context.user.id,
        project_id=alert.project_id,
        minimum_role="member",
    )
    alert, _replayed = acknowledge_alert(
        db,
        alert,
        user_id=context.user.id,
        comment=body.comment,
    )
    db.commit()
    return alert_summary(alert)


@router.get(
    "/projects/{project_id}/notification-preferences",
    response_model=NotificationPreferencesSummary,
)
def read_notification_preferences(
    project_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> NotificationPreferencesSummary:
    """Retourne les préférences effectives de l'utilisateur courant."""

    ensure_access(
        db,
        context.user.id,
        project_id=project_id,
        minimum_role="viewer",
    )
    row = get_or_create_notification_preferences(
        db,
        project_id=project_id,
        user_id=context.user.id,
    )
    db.commit()
    return notification_preferences_summary(row)


@router.put(
    "/projects/{project_id}/notification-preferences",
    response_model=NotificationPreferencesSummary,
)
def update_notification_preferences(
    project_id: str,
    body: NotificationPreferences,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> NotificationPreferencesSummary:
    """Remplace uniquement les réglages in-app du demandeur, jamais ceux d'autrui."""

    ensure_access(
        db,
        context.user.id,
        project_id=project_id,
        minimum_role="viewer",
    )
    row = get_or_create_notification_preferences(
        db,
        project_id=project_id,
        user_id=context.user.id,
    )
    replace_notification_preferences(row, body)
    db.commit()
    return notification_preferences_summary(row)
