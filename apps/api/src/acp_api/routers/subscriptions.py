"""Routes des quotas réels d'abonnement : dépôt par un worker, lecture par le propriétaire.

``POST /work/workers/{worker_id}/subscription-quotas`` porte l'authentification des
autres routes worker (jeton porteur du worker) et reste interdite aux clients humains.
``GET /subscription-quotas`` exige une session du propriétaire de la plateforme :
l'usage d'un abonnement (ChatGPT, Claude) est personnel à son titulaire, aucun autre
rôle ne lit ces valeurs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from acp_contracts import (
    SubscriptionQuotaBatch,
    SubscriptionQuotaIngestResult,
    SubscriptionQuotaList,
)

from ..deps import get_db, get_principal, is_platform_owner
from ..subscription_quotas import (
    OWNER_ONLY_DETAIL,
    ingest_reports,
    list_views,
    stale_after_seconds,
)
from .workers import _lock_worker_row, authenticate_worker, utcnow

router = APIRouter(tags=["subscriptions"])
_PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "Pragma": "no-cache"}


def _begin_worker_write(db: Session, worker_id: str, authorization: str | None):
    """Authentifie, puis reprend l'identité dans la transaction qui écrit.

    SQLite : ``BEGIN IMMEDIATE`` prend le verrou d'écriture avant la lecture des
    relevés existants. PostgreSQL : la ligne du worker est verrouillée
    (``FOR UPDATE``), ce qui sérialise les lots concurrents d'un même worker.
    """

    authenticated = authenticate_worker(db, worker_id, authorization)
    authenticated_id = authenticated.id
    if db.in_transaction():
        db.rollback()
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    _lock_worker_row(db, authenticated_id)
    worker = authenticate_worker(db, worker_id, authorization)
    if worker.id != authenticated_id:
        raise HTTPException(status_code=401, detail="Identité worker instable")
    return worker


@router.post(
    "/work/workers/{worker_id}/subscription-quotas",
    response_model=SubscriptionQuotaIngestResult,
)
def ingest_subscription_quotas(
    worker_id: str,
    body: SubscriptionQuotaBatch,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    worker = _begin_worker_write(db, worker_id, authorization)
    return ingest_reports(db, worker, body, now=utcnow())


@router.get("/subscription-quotas", response_model=SubscriptionQuotaList)
def read_subscription_quotas(
    response: Response,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    if not is_platform_owner(db, principal):
        raise HTTPException(status_code=403, detail=OWNER_ONLY_DETAIL)
    listing = list_views(db, now=utcnow(), stale_seconds=stale_after_seconds())
    response.headers.update(_PRIVATE_HEADERS)
    return listing
