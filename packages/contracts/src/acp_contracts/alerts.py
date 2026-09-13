"""Contrats des alertes : ce qu'un humain doit voir sans aller lire un journal.

Une alerte est une cause ouverte, pas une notification. La plateforme ne livre
**aucun** canal sortant — ni courriel, ni webhook : une alerte se lit dans
l'atelier et s'acquitte à la main. La déduplication d'une cause encore ouverte
appartient à la base ; ce module ne décrit que ce qui circule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AlertSeverity = Literal["info", "warning", "critical"]
NotificationChannel = Literal["in_app"]

ALERT_ACKNOWLEDGE_COMMENT_MAX = 500
"""Un acquittement se commente en une phrase ; l'analyse va dans la mission."""


class _AlertContract(BaseModel):
    """Frontière JSON stricte commune aux alertes du Lot F."""

    model_config = ConfigDict(extra="forbid", strict=True)


class AlertSummary(_AlertContract):
    """Alerte d'un projet, telle qu'elle est listée et comptée.

    ``acknowledged_at`` à ``None`` signifie « encore ouverte » : c'est ce que
    compte la pastille de l'atelier. ``task_id`` et ``automation_id`` sont
    facultatifs parce que toutes les causes ne viennent pas d'une exécution —
    la saturation du stockage n'appartient à aucune mission.
    """

    id: str
    project_id: str
    kind: str = Field(min_length=1, max_length=50)
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=300)
    detail: str = Field(max_length=10_000)
    task_id: str | None
    automation_id: str | None
    acknowledged_at: datetime | None
    acknowledged_by_user_id: str | None
    acknowledgement_comment: str = Field(max_length=ALERT_ACKNOWLEDGE_COMMENT_MAX)
    created_at: datetime

    @field_validator("acknowledged_at", "created_at")
    @classmethod
    def normalise_utc_instants(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("un instant d'alerte doit porter son fuseau")
        return value.astimezone(UTC)


class AlertAcknowledge(_AlertContract):
    """Acquittement d'une alerte, avec au plus un commentaire court."""

    comment: str = Field(default="", max_length=ALERT_ACKNOWLEDGE_COMMENT_MAX)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str) -> str:
        return value.strip()


class NotificationPreferences(_AlertContract):
    """Préférences du canal réellement disponible : les alertes dans l'atelier.

    Aucun canal externe n'est annoncé tant qu'un connecteur authentifié n'est pas
    installé. Cela évite un réglage courriel/webhook qui n'enverrait rien.
    """

    channel: NotificationChannel = "in_app"
    enabled: bool = True
    minimum_severity: AlertSeverity = "warning"
    budget_alerts: bool = True
    automation_failures: bool = True
    storage_alerts: bool = True


class NotificationPreferencesSummary(NotificationPreferences):
    """Préférences persistées d'un utilisateur pour un projet."""

    project_id: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalise_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("« updated_at » doit porter son fuseau")
        return value.astimezone(UTC)
