"""Quotas réels d'abonnement : enregistrement monotone des relevés et vue du propriétaire.

Les relevés arrivent d'un worker authentifié, qui les a lus à la source officielle
(app-server Codex, ligne d'état Claude Code). Le service ne calcule rien d'autre que
la part restante (100 − part utilisée) et la fraîcheur : aucune valeur n'est estimée.

Une lecture en échec porte l'identifiant réservé ``probe`` (contrat
``SubscriptionQuotaReport``) : elle n'a jamais l'identité d'un compteur réussi.
Règles d'écriture, appliquées sous le verrou de la ligne du worker :

- un relevé plus ancien que celui déjà stocké pour le même compteur est ignoré, et
  compté comme tel dans le bilan ;
- un relevé au moins aussi récent remplace le précédent (un rejeu à l'identique
  est donc sans effet sur les valeurs) ;
- une lecture réussie fait foi pour la liste des compteurs de son fournisseur : si
  le lot contient des relevés ``ok`` pour ce fournisseur, les compteurs du même
  worker et du même fournisseur qu'il ne rapporte plus, et qui sont plus anciens que
  lui, sont retirés ;
- la même lecture réussie retire l'état d'échec (``probe``) de ce fournisseur, quelle
  que soit sa date d'observation : il a été reçu avant elle (l'écriture est
  sérialisée par worker), et l'instant d'un fichier de ligne d'état Claude Code,
  daté de son écriture, précède souvent celui de l'échec qu'il suit ;
- un échec de lecture ne retire rien : les derniers relevés réussis restent visibles
  avec leur date, à côté de l'échec qui explique pourquoi ils ne sont plus relus, et
  deviennent « Périmé » avec le temps.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from acp_contracts import (
    DEFAULT_QUOTA_STALE_SECONDS,
    QUOTA_SOURCE_BY_PROVIDER,
    QUOTA_STALE_SECONDS_MAX,
    QUOTA_STALE_SECONDS_MIN,
    QuotaCredits,
    QuotaWindow,
    QuotaWindowView,
    SubscriptionQuotaBatch,
    SubscriptionQuotaIngestResult,
    SubscriptionQuotaList,
    SubscriptionQuotaReport,
    SubscriptionQuotaView,
)
from acp_database.models import SubscriptionQuotaSnapshotModel, WorkerModel

STALE_SECONDS_ENV = "ACP_SUBSCRIPTION_QUOTA_STALE_SECONDS"
OWNER_ONLY_DETAIL = (
    "Quotas d'abonnement réservés au propriétaire de la plateforme : l'usage d'un "
    "abonnement est personnel à son titulaire."
)
UNREADABLE_SNAPSHOT_DETAIL = (
    "Relevé enregistré illisible : il sera remplacé au prochain passage du worker."
)
_DIGITS = re.compile(r"[0-9]{1,9}")


def stale_after_seconds(environ: Mapping[str, str] | None = None) -> int:
    """Seuil de fraîcheur des relevés, en secondes ; une valeur invalide est refusée (503)."""

    raw = (os.environ if environ is None else environ).get(STALE_SECONDS_ENV)
    if raw is None:
        return DEFAULT_QUOTA_STALE_SECONDS
    text = raw.strip()
    value = int(text) if _DIGITS.fullmatch(text) else None
    if value is None or not QUOTA_STALE_SECONDS_MIN <= value <= QUOTA_STALE_SECONDS_MAX:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Configuration {STALE_SECONDS_ENV} invalide : entier de "
                f"{QUOTA_STALE_SECONDS_MIN} à {QUOTA_STALE_SECONDS_MAX} secondes attendu"
            ),
        )
    return value


def _stored_values(report: SubscriptionQuotaReport, received_at: datetime) -> dict:
    return {
        "status": report.status,
        "source": report.source,
        "plan": report.plan,
        "windows": [window.model_dump(mode="json") for window in report.windows],
        "credits": None if report.credits is None else report.credits.model_dump(mode="json"),
        "limit_reached": None if report.limit_reached is None else int(report.limit_reached),
        "reached_type": report.reached_type,
        "detail": report.detail,
        "observed_at": report.observed_at,
        "received_at": received_at,
    }


def ingest_reports(
    db: Session,
    worker: WorkerModel,
    batch: SubscriptionQuotaBatch,
    *,
    now: datetime,
) -> SubscriptionQuotaIngestResult:
    """Enregistre un lot sous le verrou du worker ; l'appelant a authentifié ce worker."""

    existing = {
        (row.provider, row.limit_id): row
        for row in db.scalars(
            select(SubscriptionQuotaSnapshotModel).where(
                SubscriptionQuotaSnapshotModel.worker_id == worker.id
            )
        )
    }
    stored = ignored_older = removed = 0
    for report in batch.reports:
        identity = (report.provider, report.limit_id)
        row = existing.get(identity)
        if row is not None and row.observed_at > report.observed_at:
            ignored_older += 1
            continue
        values = _stored_values(report, now)
        if row is None:
            row = SubscriptionQuotaSnapshotModel(
                worker_id=worker.id,
                provider=report.provider,
                limit_id=report.limit_id,
                **values,
            )
            db.add(row)
            existing[identity] = row
        else:
            for name, value in values.items():
                setattr(row, name, value)
        stored += 1

    for provider in sorted({report.provider for report in batch.reports}):
        provider_reports = [report for report in batch.reports if report.provider == provider]
        if not any(report.status == "ok" for report in provider_reports):
            continue
        reported = {report.limit_id for report in provider_reports}
        newest = max(report.observed_at for report in provider_reports)
        for (row_provider, limit_id), row in sorted(existing.items()):
            if row_provider != provider or limit_id in reported:
                continue
            if row.status != "ok" or row.observed_at < newest:
                db.delete(row)
                removed += 1
    db.commit()
    return SubscriptionQuotaIngestResult(
        stored=stored, ignored_older=ignored_older, removed=removed
    )


def _view(
    row: SubscriptionQuotaSnapshotModel, worker_name: str, *, threshold: datetime
) -> SubscriptionQuotaView:
    identity = {
        "provider": row.provider,
        "source": row.source,
        "limit_id": row.limit_id,
        "observed_at": row.observed_at,
        "worker_id": row.worker_id,
        "worker_name": worker_name,
        "received_at": row.received_at,
        "stale": row.observed_at < threshold,
    }
    try:
        return SubscriptionQuotaView(
            **identity,
            status=row.status,
            plan=row.plan,
            windows=[
                QuotaWindowView.from_window(QuotaWindow.model_validate(window))
                for window in row.windows or []
            ],
            credits=None if row.credits is None else QuotaCredits.model_validate(row.credits),
            limit_reached=None if row.limit_reached is None else bool(row.limit_reached),
            reached_type=row.reached_type,
            detail=row.detail,
        )
    except (ValidationError, TypeError, ValueError):
        # Aucune ligne ne doit empêcher la lecture des autres, ni s'afficher comme
        # valide : elle devient « indisponible », avec son identité réelle.
        if identity["source"] != QUOTA_SOURCE_BY_PROVIDER.get(identity["provider"]):
            raise
        return SubscriptionQuotaView(
            **identity, status="unavailable", detail=UNREADABLE_SNAPSHOT_DETAIL
        )


def list_views(db: Session, *, now: datetime, stale_seconds: int) -> SubscriptionQuotaList:
    """Tous les derniers relevés, dans un ordre stable indépendant du dialecte."""

    threshold = now - timedelta(seconds=stale_seconds)
    rows = db.execute(
        select(SubscriptionQuotaSnapshotModel, WorkerModel.name).join(
            WorkerModel, WorkerModel.id == SubscriptionQuotaSnapshotModel.worker_id
        )
    ).all()
    # Tri par points de code en Python : l'ordre d'un ORDER BY dépendrait de la
    # collation PostgreSQL (qui peut ignorer « _ » et « - »), pas de SQLite.
    rows = sorted(
        rows,
        key=lambda item: (item[0].provider, item[0].limit_id, item[1], item[0].worker_id),
    )
    return SubscriptionQuotaList(
        items=[_view(row, worker_name, threshold=threshold) for row, worker_name in rows],
        stale_after_seconds=stale_seconds,
        generated_at=now,
    )
