"""Lecture paginée du journal d'événements (``GET /runs/{id}/events``, ``/projects/...``).

Ces lectures réconcilient l'interface après une coupure de flux : une reconnexion
ne relance jamais une mission et ne duplique aucun événement, elle relit par curseur.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
Le projet d'une tentative est **toujours** résolu côté serveur : un ``project_id``
fourni par le client n'élargit jamais la portée.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from acp_contracts import EventPage

from ..deps import ensure_access, get_db, get_principal
from ..streams import (
    DEFAULT_EVENT_PAGE_LIMIT,
    MAX_EVENT_PAGE_LIMIT,
    read_project_page,
    read_run_page,
    resolve_run_project,
)

router = APIRouter(tags=["events"])

_AFTER_SEQ = Query(
    default=0,
    ge=0,
    description="Curseur exclusif : seuls les événements strictement postérieurs sont rendus.",
)
_LIMIT = Query(
    default=DEFAULT_EVENT_PAGE_LIMIT,
    ge=1,
    le=MAX_EVENT_PAGE_LIMIT,
    description="Nombre maximal d'événements rendus par page.",
)


@router.get("/runs/{run_id}/events", response_model=EventPage)
def read_run_events(
    run_id: str,
    after_seq: int = _AFTER_SEQ,
    limit: int = _LIMIT,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> EventPage:
    """Page du journal d'une tentative, par séquence croissante."""

    project_id = resolve_run_project(db, run_id)
    ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
    return read_run_page(db, run_id, after_seq=after_seq, limit=limit)


@router.get("/projects/{project_id}/events", response_model=EventPage)
def read_project_events(
    project_id: str,
    after_seq: int = _AFTER_SEQ,
    limit: int = _LIMIT,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> EventPage:
    """Page du journal d'un projet, toutes tentatives confondues."""

    ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
    return read_project_page(db, project_id, after_seq=after_seq, limit=limit)
