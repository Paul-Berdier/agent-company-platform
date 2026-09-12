"""Lecture par curseur et génération du flux SSE durable (spécification §5.2).

Le flux « tail » la base par curseur : interrogation bornée (``ACP_STREAM_POLL_INTERVAL_MS``)
réveillée plus tôt par le hub local. La base reste la seule source de vérité, donc une
reconnexion ne duplique ni ne perd d'événement, et plusieurs processus d'API peuvent
servir le même run.

Deux portées, deux curseurs :

- **tentative** (``/streams/runs/{id}``) — le curseur est la séquence monotone du run ;
- **projet** (``/streams/projects/{id}``) — les séquences étant propres à chaque run, le
  curseur est la date de création de la ligne exprimée en microsecondes depuis l'époque
  Unix, avec un ordre total ``(created_at, id)``.

Le RBAC résolu à l'ouverture est **revérifié à chaque page** : une révocation de session
ou une perte de membership ferme la connexion au plus tard à l'interrogation suivante.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic

from fastapi import HTTPException
from sqlalchemy.orm import Session

from acp_contracts import EVENT_SCHEMA_VERSION, EventPage, StreamEvent
from acp_database.models import EventModel, TaskModel, TaskRunModel

from .deps import ensure_access
from .events_bus import event_hub, project_channel, run_channel
from .security import authenticate_session

__all__ = [
    "DEFAULT_EVENT_PAGE_LIMIT",
    "DEFAULT_EVENT_RETENTION_DAYS",
    "MAX_EVENT_PAGE_LIMIT",
    "SSE_CLOSED_EVENT",
    "SSE_EVENT_NAME",
    "SSE_HEADERS",
    "SSE_MEDIA_TYPE",
    "SSE_ROTATE_EVENT",
    "StreamConnectionLimiter",
    "StreamPolicy",
    "event_retention_days",
    "project_cursor",
    "project_event_stream",
    "read_project_page",
    "read_run_page",
    "resolve_run_project",
    "resume_cursor",
    "run_event_stream",
    "session_factory_from",
    "stream_connections",
    "stream_policy",
    "to_stream_event",
]

SSE_MEDIA_TYPE = "text/event-stream"
SSE_EVENT_NAME = "acp.event"
SSE_ROTATE_EVENT = "acp.stream.rotate"
SSE_CLOSED_EVENT = "acp.stream.closed"
SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

DEFAULT_EVENT_PAGE_LIMIT = 200
MAX_EVENT_PAGE_LIMIT = 500
DEFAULT_EVENT_RETENTION_DAYS = 90

DEFAULT_POLL_INTERVAL_MS = 400
DEFAULT_KEEPALIVE_SECONDS = 15.0
DEFAULT_MAX_SECONDS = 900.0
DEFAULT_MAX_CONNECTIONS_PER_USER = 4
DEFAULT_STREAM_BATCH = 200

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECONDS_PER_DAY = 86_400_000_000


# --- Configuration ------------------------------------------------------------


def _positive_number(
    environ: Mapping[str, str], name: str, default: float, *, minimum: float
) -> float:
    raw_value = str(environ.get(name, "")).strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    if value < minimum:
        return minimum
    return value


def _positive_int(
    environ: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int
) -> int:
    raw_value = str(environ.get(name, "")).strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def event_retention_days(environ: Mapping[str, str] | None = None) -> int:
    """Fenêtre de conservation annoncée aux lecteurs (``0`` = illimitée)."""

    environ = os.environ if environ is None else environ
    raw_value = str(environ.get("ACP_EVENT_RETENTION_DAYS", "")).strip()
    if not raw_value:
        return DEFAULT_EVENT_RETENTION_DAYS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_EVENT_RETENTION_DAYS
    return max(0, value)


@dataclass(frozen=True, slots=True)
class StreamPolicy:
    """Identité, portée et bornes temporelles d'une connexion SSE."""

    user_id: str
    session_token: str
    project_id: str
    run_id: str | None = None
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_MS / 1000
    keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS
    max_seconds: float = DEFAULT_MAX_SECONDS
    batch: int = DEFAULT_STREAM_BATCH
    max_connections_per_user: int = DEFAULT_MAX_CONNECTIONS_PER_USER


def stream_policy(
    *,
    user_id: str,
    session_token: str,
    project_id: str,
    run_id: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> StreamPolicy:
    """Lit les bornes du flux dans l'environnement, en corrigeant les valeurs absurdes."""

    environ = os.environ if environ is None else environ
    poll_ms = _positive_number(
        environ, "ACP_STREAM_POLL_INTERVAL_MS", DEFAULT_POLL_INTERVAL_MS, minimum=10
    )
    return StreamPolicy(
        user_id=user_id,
        session_token=session_token,
        project_id=project_id,
        run_id=run_id,
        poll_interval_seconds=poll_ms / 1000,
        keepalive_seconds=_positive_number(
            environ, "ACP_STREAM_KEEPALIVE_SECONDS", DEFAULT_KEEPALIVE_SECONDS, minimum=0.05
        ),
        max_seconds=_positive_number(
            environ, "ACP_STREAM_MAX_SECONDS", DEFAULT_MAX_SECONDS, minimum=0.1
        ),
        batch=_positive_int(
            environ, "ACP_STREAM_BATCH", DEFAULT_STREAM_BATCH, minimum=1, maximum=MAX_EVENT_PAGE_LIMIT
        ),
        max_connections_per_user=_positive_int(
            environ,
            "ACP_STREAM_MAX_CONNECTIONS_PER_USER",
            DEFAULT_MAX_CONNECTIONS_PER_USER,
            minimum=1,
            maximum=64,
        ),
    )


# --- Limite de connexions simultanées ----------------------------------------


class StreamConnectionLimiter:
    """Compte les flux SSE ouverts par utilisateur dans ce processus."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, user_id: str, limit: int) -> bool:
        with self._lock:
            current = self._counts.get(user_id, 0)
            if current >= max(1, limit):
                return False
            self._counts[user_id] = current + 1
            return True

    def release(self, user_id: str) -> None:
        with self._lock:
            current = self._counts.get(user_id, 0)
            if current <= 1:
                self._counts.pop(user_id, None)
                return
            self._counts[user_id] = current - 1

    def count(self, user_id: str) -> int:
        with self._lock:
            return self._counts.get(user_id, 0)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


stream_connections = StreamConnectionLimiter()
"""Compteur du processus, partagé par les deux routes de flux."""


# --- Curseurs et lecture ------------------------------------------------------


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def project_cursor(model: EventModel) -> int:
    """Curseur projet : microsecondes depuis l'époque Unix, en arithmétique entière.

    Les séquences étant propres à chaque tentative, elles ne peuvent pas ordonner un
    projet entier : l'ordre d'écriture le peut, et il tient dans l'entier attendu par
    ``after_seq`` / ``Last-Event-ID``.
    """

    delta = _as_utc(model.created_at) - _EPOCH
    return delta.days * _MICROSECONDS_PER_DAY + delta.seconds * 1_000_000 + delta.microseconds


def _cursor_datetime(cursor: int) -> datetime:
    return _EPOCH + timedelta(microseconds=cursor)


def to_stream_event(model: EventModel) -> StreamEvent:
    """Projette une ligne du journal sur le contrat public du flux."""

    return StreamEvent(
        schema_version=model.schema_version or EVENT_SCHEMA_VERSION,
        id=model.id,
        sequence=model.sequence,
        type=model.type,
        occurred_at=_as_utc(model.occurred_at),
        project_id=model.project_id,
        conversation_id=model.conversation_id,
        task_id=model.task_id,
        task_run_id=model.task_run_id,
        step_id=model.step_id,
        executor=model.executor,
        emitted_by=model.emitted_by,
        payload=model.payload or {},
    )


def resolve_run_project(db: Session, run_id: str) -> str:
    """Résout le projet d'une tentative **côté serveur** : le client ne le fournit jamais."""

    run = db.get(TaskRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Tentative introuvable")
    task = db.get(TaskModel, run.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tâche de la tentative introuvable")
    return task.project_id


def _read_run_rows(
    db: Session, run_id: str, cursor: int, limit: int
) -> tuple[list[tuple[StreamEvent, int]], bool]:
    rows = (
        db.query(EventModel)
        .filter(
            EventModel.task_run_id == run_id,
            EventModel.sequence.is_not(None),
            EventModel.sequence > cursor,
        )
        .order_by(EventModel.sequence.asc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return [(to_stream_event(row), int(row.sequence)) for row in rows], has_more


def _read_project_rows(
    db: Session, project_id: str, cursor: int, limit: int
) -> tuple[list[tuple[StreamEvent, int]], bool]:
    query = db.query(EventModel).filter(EventModel.project_id == project_id)
    if cursor > 0:
        query = query.filter(EventModel.created_at > _cursor_datetime(cursor))
    rows = (
        query.order_by(EventModel.created_at.asc(), EventModel.id.asc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    if has_more and rows:
        # Ne jamais couper au milieu d'un groupe de lignes partageant la même
        # microseconde : la page suivante reprend en « strictement après ».
        boundary = project_cursor(rows[-1])
        trimmed = [row for row in rows if project_cursor(row) < boundary]
        if trimmed:
            rows = trimmed
    return [(to_stream_event(row), project_cursor(row)) for row in rows], has_more


def _page(
    rows: list[tuple[StreamEvent, int]],
    *,
    has_more: bool,
    cursor: int,
    environ: Mapping[str, str] | None = None,
) -> EventPage:
    next_cursor = rows[-1][1] if rows else (cursor or None)
    return EventPage(
        events=[event for event, _ in rows],
        next_cursor=next_cursor,
        has_more=has_more,
        retention_days=event_retention_days(environ),
    )


def read_run_page(
    db: Session, run_id: str, *, after_seq: int = 0, limit: int = DEFAULT_EVENT_PAGE_LIMIT
) -> EventPage:
    """Page du journal d'une tentative, ordonnée par séquence croissante."""

    rows, has_more = _read_run_rows(db, run_id, max(0, after_seq), limit)
    return _page(rows, has_more=has_more, cursor=max(0, after_seq))


def read_project_page(
    db: Session,
    project_id: str,
    *,
    after_seq: int = 0,
    limit: int = DEFAULT_EVENT_PAGE_LIMIT,
) -> EventPage:
    """Page du journal d'un projet, ordonnée par date d'écriture croissante."""

    rows, has_more = _read_project_rows(db, project_id, max(0, after_seq), limit)
    return _page(rows, has_more=has_more, cursor=max(0, after_seq))


def resume_cursor(last_event_id: str | None, after_seq: int) -> int:
    """``Last-Event-ID`` est prioritaire sur ``?after_seq=`` ; illisible, il est ignoré."""

    if last_event_id is not None:
        candidate = last_event_id.strip()
        if candidate.isdigit():
            return int(candidate)
    return max(0, after_seq)


def session_factory_from(db: Session) -> Callable[[], Session]:
    """Fabrique de sessions adossée au même moteur que la requête.

    Le générateur SSE vit plus longtemps que la session de la requête : il ouvre et
    referme sa propre session à chaque page, sans jamais garder de transaction ouverte.
    """

    bind = db.get_bind()
    return lambda: Session(bind=bind, expire_on_commit=False)


# --- Trames SSE ---------------------------------------------------------------


def _frame_event(cursor: int, event: StreamEvent) -> bytes:
    return (
        f"id: {cursor}\n"
        f"event: {SSE_EVENT_NAME}\n"
        f"data: {event.model_dump_json()}\n\n"
    ).encode("utf-8")


def _frame_rotate(cursor: int) -> bytes:
    payload = json.dumps(
        {"cursor": cursor, "reason": "max_seconds"}, ensure_ascii=False, separators=(",", ":")
    )
    prefix = f"id: {cursor}\n" if cursor > 0 else ""
    return f"{prefix}event: {SSE_ROTATE_EVENT}\ndata: {payload}\n\n".encode("utf-8")


def _frame_closed(reason: str) -> bytes:
    payload = json.dumps({"reason": reason}, ensure_ascii=False, separators=(",", ":"))
    return f"event: {SSE_CLOSED_EVENT}\ndata: {payload}\n\n".encode("utf-8")


_KEEPALIVE_FRAME = b": ping\n\n"


# --- Générateur -------------------------------------------------------------


def _still_authorized(db_factory: Callable[[], Session], policy: StreamPolicy) -> bool:
    """Revalide session **et** membership : l'autorisation d'ouverture ne se périme pas seule."""

    with closing(db_factory()) as db:
        context = authenticate_session(db, policy.session_token)
        if context is None or context.user.id != policy.user_id:
            return False
        try:
            ensure_access(db, policy.user_id, project_id=policy.project_id, minimum_role="viewer")
        except HTTPException:
            return False
        return True


def _read_rows(
    db_factory: Callable[[], Session],
    *,
    scope: str,
    scope_id: str,
    cursor: int,
    limit: int,
) -> list[tuple[StreamEvent, int]]:
    with closing(db_factory()) as db:
        if scope == "run":
            rows, _ = _read_run_rows(db, scope_id, cursor, limit)
        else:
            rows, _ = _read_project_rows(db, scope_id, cursor, limit)
    return rows


async def _event_stream(
    db_factory: Callable[[], Session],
    *,
    scope: str,
    scope_id: str,
    after_seq: int,
    policy: StreamPolicy,
) -> AsyncIterator[bytes]:
    channel = run_channel(scope_id) if scope == "run" else project_channel(scope_id)
    queue = event_hub.subscribe(channel)
    cursor = max(0, after_seq)
    started = monotonic()
    last_keepalive = started
    try:
        # Ouvrir par un commentaire : les proxys voient la réponse démarrer sans
        # attendre le premier événement. Il est émis **dans** le ``try`` pour qu'une
        # fermeture immédiate désabonne quand même le flux du hub.
        yield _KEEPALIVE_FRAME
        while True:
            if not await asyncio.to_thread(_still_authorized, db_factory, policy):
                yield _frame_closed("unauthorized")
                return
            rows = await asyncio.to_thread(
                _read_rows,
                db_factory,
                scope=scope,
                scope_id=scope_id,
                cursor=cursor,
                limit=policy.batch,
            )
            for event, row_cursor in rows:
                cursor = row_cursor
                yield _frame_event(row_cursor, event)
            if rows:
                # Rattrapage : vider le retard avant de repasser en attente.
                continue
            now = monotonic()
            if now - started >= policy.max_seconds:
                yield _frame_rotate(cursor)
                return
            if now - last_keepalive >= policy.keepalive_seconds:
                yield _KEEPALIVE_FRAME
                last_keepalive = now
            remaining = policy.max_seconds - (now - started)
            timeout = max(0.01, min(policy.poll_interval_seconds, remaining))
            try:
                await asyncio.wait_for(queue.get(), timeout=timeout)
            except (TimeoutError, asyncio.TimeoutError):
                pass
    finally:
        event_hub.unsubscribe(channel, queue)


def run_event_stream(
    db_factory: Callable[[], Session],
    run_id: str,
    after_seq: int,
    policy: StreamPolicy,
) -> AsyncIterator[bytes]:
    """Flux SSE d'une tentative, curseur = séquence du run."""

    return _event_stream(
        db_factory, scope="run", scope_id=run_id, after_seq=after_seq, policy=policy
    )


def project_event_stream(
    db_factory: Callable[[], Session],
    project_id: str,
    after_seq: int,
    policy: StreamPolicy,
) -> AsyncIterator[bytes]:
    """Flux SSE d'un projet, curseur = microsecondes d'écriture."""

    return _event_stream(
        db_factory,
        scope="project",
        scope_id=project_id,
        after_seq=after_seq,
        policy=policy,
    )
