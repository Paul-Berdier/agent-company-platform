"""Flux d'événements SSE servi par l'API métier (``GET /streams/...``).

L'API détient la base, les sessions et le RBAC : le flux utilisateur est servi ici,
jamais par ``apps/event-service`` qui reste un relais interne sans accès aux données.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
``Last-Event-ID`` est prioritaire sur ``?after_seq=`` pour que la reprise automatique
d'``EventSource`` fasse autorité.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..deps import ensure_access, get_auth_context, get_db
from ..security import SESSION_COOKIE_NAME, AuthContext
from ..streams import (
    SSE_HEADERS,
    SSE_MEDIA_TYPE,
    project_event_stream,
    resolve_run_project,
    resume_cursor,
    run_event_stream,
    session_factory_from,
    stream_connections,
    stream_policy,
)

router = APIRouter(tags=["streams"])

_AFTER_SEQ = Query(
    default=0,
    ge=0,
    description="Curseur de reprise ; ``Last-Event-ID`` est prioritaire.",
)


async def _released_when_closed(
    chunks: AsyncIterator[bytes], user_id: str
) -> AsyncIterator[bytes]:
    """Rend son jeton de connexion quoi qu'il arrive : fin propre, erreur ou coupure."""

    try:
        async for chunk in chunks:
            yield chunk
    finally:
        stream_connections.release(user_id)


def _streaming_response(chunks: AsyncIterator[bytes], user_id: str) -> StreamingResponse:
    return StreamingResponse(
        _released_when_closed(chunks, user_id),
        media_type=SSE_MEDIA_TYPE,
        headers=dict(SSE_HEADERS),
    )


def _acquire_slot(user_id: str, limit: int) -> None:
    if not stream_connections.acquire(user_id, limit):
        raise HTTPException(
            status_code=429,
            detail="Trop de flux simultanés pour cet utilisateur ; fermez un onglet ouvert.",
            headers={"Retry-After": "5"},
        )


@router.get("/streams/runs/{run_id}")
async def stream_run_events(
    run_id: str,
    request: Request,
    after_seq: int = _AFTER_SEQ,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    """Flux SSE d'une tentative ; le projet est résolu côté serveur."""

    project_id = resolve_run_project(db, run_id)
    user_id = context.user.id
    ensure_access(db, user_id, project_id=project_id, minimum_role="viewer")
    policy = stream_policy(
        user_id=user_id,
        session_token=request.cookies.get(SESSION_COOKIE_NAME) or "",
        project_id=project_id,
        run_id=run_id,
    )
    cursor = resume_cursor(request.headers.get("Last-Event-ID"), after_seq)
    _acquire_slot(user_id, policy.max_connections_per_user)
    db_factory = session_factory_from(db)
    return _streaming_response(
        run_event_stream(db_factory, run_id, cursor, policy), user_id
    )


@router.get("/streams/projects/{project_id}")
async def stream_project_events(
    project_id: str,
    request: Request,
    after_seq: int = _AFTER_SEQ,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    """Flux SSE d'un projet, toutes tentatives confondues."""

    user_id = context.user.id
    ensure_access(db, user_id, project_id=project_id, minimum_role="viewer")
    policy = stream_policy(
        user_id=user_id,
        session_token=request.cookies.get(SESSION_COOKIE_NAME) or "",
        project_id=project_id,
    )
    cursor = resume_cursor(request.headers.get("Last-Event-ID"), after_seq)
    _acquire_slot(user_id, policy.max_connections_per_user)
    db_factory = session_factory_from(db)
    return _streaming_response(
        project_event_stream(db_factory, project_id, cursor, policy), user_id
    )
