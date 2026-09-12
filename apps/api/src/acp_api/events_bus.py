"""Écriture du journal durable, allocation de séquence et réveil des flux locaux.

Le journal est la **source de vérité** : le hub ne transporte que des numéros de
séquence et sert uniquement à réveiller un flux SSE plus tôt que son interrogation
périodique. Une coupure du hub ne perd donc aucun événement, elle ajoute au pire la
latence d'une interrogation.

La séquence est monotone **par tentative** (``task_run_id``) et sert de curseur de
reprise (``Last-Event-ID``, ``after_seq``). Elle est allouée dans la transaction
métier et protégée par l'index unique partiel ``uq_event_run_sequence`` : en cas de
collision concurrente, l'insertion est rejouée dans un point de sauvegarde, au plus
``SEQUENCE_ALLOCATION_ATTEMPTS`` fois.

Aucun média ne transite dans un événement (§0.2 de la spécification) : un événement
de média ne porte qu'une référence d'artefact (``media_reference_payload``), et toute
charge utile contenant du contenu encodé en ligne est refusée.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    EVENT_SCHEMA_VERSION,
    Event,
    ServiceOriginError,
    normalize_service_origin,
)
from acp_database.models import EventModel

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "INLINE_CONTENT_KEYS",
    "MEDIA_PAYLOAD_KEYS",
    "PAYLOAD_MAX_DEPTH",
    "SEQUENCE_ALLOCATION_ATTEMPTS",
    "EventHub",
    "MediaPayloadRefused",
    "SequenceAllocationError",
    "allocate_sequence",
    "event_hub",
    "forward_event",
    "media_reference_payload",
    "project_channel",
    "publish",
    "run_channel",
    "store_event",
]

SEQUENCE_ALLOCATION_ATTEMPTS = 5
"""Nombre maximal d'essais d'allocation avant d'abandonner (spécification §5.1)."""

MEDIA_PAYLOAD_KEYS: tuple[str, ...] = (
    "artifact_id",
    "content_type",
    "size_bytes",
    "sha256",
    "stream_kind",
)
"""Seules clés admises dans la charge utile d'un événement de média (§4.1)."""

INLINE_CONTENT_KEYS = frozenset(
    {
        "base64",
        "blob",
        "body_base64",
        "content_base64",
        "data_base64",
        "data_url",
        "file_base64",
        "image_base64",
        "screenshot_base64",
        "trace_base64",
        "video_base64",
    }
)
"""Clés qui signeraient un média embarqué : refusées à l'écriture, à toute profondeur."""

PAYLOAD_MAX_DEPTH = 6
"""Profondeur d'inspection de la charge utile : borne le coût du contrôle."""

_SEQUENCE_COLLISION_MARKERS = (
    # PostgreSQL nomme l'index unique partiel…
    "uq_event_run_sequence",
    # …SQLite nomme les colonnes de l'index.
    "events.task_run_id, events.sequence",
)

_HUB_QUEUE_MAXSIZE = 64

_pending_forwards: set[asyncio.Task] = set()
"""Références fortes des relais en vol : sans elles, ``asyncio`` peut les ramasser."""


class SequenceAllocationError(RuntimeError):
    """Aucune séquence libre après ``SEQUENCE_ALLOCATION_ATTEMPTS`` essais."""


class MediaPayloadRefused(ValueError):
    """La charge utile embarque un contenu binaire : le journal ne transporte pas de média."""


# --- Charge utile -------------------------------------------------------------


def media_reference_payload(
    *,
    artifact_id: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    stream_kind: str,
) -> dict[str, Any]:
    """Construit la référence d'artefact d'un événement de média.

    C'est la seule forme admise : ni octets, ni base64, ni chemin local.
    """

    return {
        "artifact_id": artifact_id,
        "content_type": content_type,
        "size_bytes": int(size_bytes),
        "sha256": sha256,
        "stream_kind": stream_kind,
    }


def _refuse_inline_media(value: Any, depth: int = 0) -> None:
    """Refuse toute charge utile portant un contenu encodé en ligne."""

    if depth > PAYLOAD_MAX_DEPTH:
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.strip().lower() in INLINE_CONTENT_KEYS:
                raise MediaPayloadRefused(
                    "Un événement ne transporte jamais de média : "
                    f"la clé « {key} » doit être remplacée par une référence d'artefact."
                )
            _refuse_inline_media(nested, depth + 1)
        return
    if isinstance(value, (list, tuple)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    ):
        for nested in value:
            _refuse_inline_media(nested, depth + 1)


# --- Hub local ----------------------------------------------------------------


def run_channel(run_id: str) -> str:
    """Canal de réveil d'une tentative."""

    return f"run:{run_id}"


def project_channel(project_id: str) -> str:
    """Canal de réveil d'un projet (agrégation des tentatives)."""

    return f"project:{project_id}"


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop | None = None

    def push(self, sequence: int) -> None:
        """Dépose un réveil sans jamais bloquer ni faire échouer la publication."""

        loop = self.loop
        if loop is None:
            self._put(sequence)
            return
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            # Même boucle : déposer tout de suite, sans attendre un tour de boucle.
            self._put(sequence)
            return
        if loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._put, sequence)
        except RuntimeError:
            # Boucle arrêtée entre-temps : la lecture en base reste la source de vérité.
            return

    def _put(self, sequence: int) -> None:
        try:
            self.queue.put_nowait(sequence)
        except asyncio.QueueFull:
            # Le flux a du retard : il relira la base, aucun événement n'est perdu.
            return


@dataclass
class EventHub:
    """Réveille les flux SSE du processus ; ne transporte que des numéros de séquence.

    Volontairement local et sans persistance : la reprise et la durabilité reposent
    sur la base, pas sur ce hub. Un abonné lent voit son réveil abandonné plutôt que
    de ralentir la transaction métier.
    """

    queue_maxsize: int = _HUB_QUEUE_MAXSIZE
    _subscribers: dict[str, list[_Subscriber]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Ouvre une file de réveil pour ``channel`` (``run:<id>`` ou ``project:<id>``)."""

        queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_maxsize)
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        subscriber = _Subscriber(queue=queue, loop=loop)
        with self._lock:
            self._subscribers.setdefault(channel, []).append(subscriber)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(channel)
            if not subscribers:
                return
            self._subscribers[channel] = [
                subscriber for subscriber in subscribers if subscriber.queue is not queue
            ]
            if not self._subscribers[channel]:
                self._subscribers.pop(channel, None)

    def notify(self, channel: str, sequence: int) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(channel, ()))
        for subscriber in subscribers:
            subscriber.push(sequence)

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._subscribers.get(channel, ()))

    def reset(self) -> None:
        """Oublie tous les abonnés (utilisé entre deux tests)."""

        with self._lock:
            self._subscribers.clear()


event_hub = EventHub()
"""Hub du processus : partagé par les routes de flux et par les publications."""


# --- Écriture du journal ------------------------------------------------------


def allocate_sequence(db: Session, task_run_id: str) -> int:
    """Retourne le prochain numéro de séquence libre de la tentative.

    L'appel ne consomme rien : deux lectures successives sans écriture rendent le
    même numéro. L'unicité est garantie par l'index ``uq_event_run_sequence``, et la
    collision concurrente est rattrapée par le réessai de ``publish``.
    """

    if not task_run_id:
        raise ValueError("Une séquence n'existe que pour une tentative identifiée.")
    statement = (
        select(func.coalesce(EventModel.sequence, 0))
        .where(
            EventModel.task_run_id == task_run_id,
            EventModel.sequence.is_not(None),
        )
        .order_by(EventModel.sequence.desc())
        .limit(1)
        .with_for_update()
    )
    highest = db.execute(statement).scalar()
    return int(highest or 0) + 1


def _is_sequence_collision(error: IntegrityError) -> bool:
    """Distingue la collision de séquence de toute autre violation d'unicité.

    Rejouer aveuglément masquerait le vrai défaut de l'appelant — une clé primaire en
    double, par exemple — derrière cinq essais inutiles et un message trompeur.
    """

    message = str(getattr(error, "orig", None) or error)
    return any(marker in message for marker in _SEQUENCE_COLLISION_MARKERS)


def _ensure_write_transaction(db: Session) -> None:
    """Garantit une transaction réelle **avant** de poser un point de sauvegarde.

    Deux raisons, toutes deux propres à ``pysqlite`` :

    1. le pilote n'émet ``BEGIN`` que devant une écriture ; un ``SAVEPOINT`` posé en
       premier ouvrirait lui-même la transaction et son ``RELEASE`` la **validerait** —
       l'appelant qui a passé ``commit=False`` perdrait le contrôle de sa transaction ;
    2. une transaction *différée* prendrait un verrou partagé à la lecture puis tenterait
       de l'élever à l'écriture : deux publications simultanées se bloqueraient
       mutuellement (``database is locked``, sans attente possible).

    ``BEGIN IMMEDIATE`` règle les deux : le verrou d'écriture est pris d'emblée, les
    publications se sérialisent et ``ACP`` conserve la transaction de l'appelant.
    """

    connection = db.connection()
    if connection.dialect.name != "sqlite":
        return
    driver_connection = getattr(connection.connection, "driver_connection", None)
    if driver_connection is None or getattr(driver_connection, "in_transaction", False):
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _event_model(
    event: Event,
    *,
    sequence: int | None,
    schema_version: str,
    conversation_id: str | None,
    step_id: str | None,
    executor: str | None,
    emitted_by: str | None,
) -> EventModel:
    return EventModel(
        id=event.id,
        type=event.type,
        occurred_at=event.occurred_at,
        organization_id=event.organization_id,
        workspace_id=event.workspace_id,
        department_id=event.department_id,
        project_id=event.project_id,
        team_id=event.team_id,
        agent_instance_id=event.agent_instance_id,
        task_id=event.task_id,
        task_run_id=event.task_run_id,
        payload=event.payload,
        schema_version=schema_version,
        sequence=sequence,
        conversation_id=conversation_id,
        step_id=step_id,
        executor=executor,
        emitted_by=emitted_by,
    )


def store_event(
    db: Session,
    event: Event,
    *,
    sequence: int | None = None,
    commit: bool = True,
    schema_version: str = EVENT_SCHEMA_VERSION,
    conversation_id: str | None = None,
    step_id: str | None = None,
    executor: str | None = None,
    emitted_by: str | None = None,
) -> EventModel:
    """Persiste un événement.

    ``commit=True`` (défaut) préserve le comportement du Lot C pour les appelants
    existants qui n'ouvrent pas de transaction explicite. Un appelant qui possède
    déjà sa transaction passe ``commit=False`` : rien n'est validé avant son propre
    ``commit()``.
    """

    _refuse_inline_media(event.payload)
    model = _event_model(
        event,
        sequence=sequence,
        schema_version=schema_version,
        conversation_id=conversation_id,
        step_id=step_id,
        executor=executor,
        emitted_by=emitted_by,
    )
    db.add(model)
    if commit:
        db.commit()
    return model


def publish(
    db: Session,
    event: Event,
    *,
    commit: bool = True,
    background: Any | None = None,
    forward: bool = True,
    schema_version: str = EVENT_SCHEMA_VERSION,
    conversation_id: str | None = None,
    step_id: str | None = None,
    executor: str | None = None,
    emitted_by: str | None = None,
) -> int | None:
    """Alloue la séquence, persiste, réveille les flux locaux puis relaie l'événement.

    Retourne la séquence allouée, ou ``None`` pour un événement sans tentative
    (l'unicité ``(task_run_id, sequence)`` est partielle : ces lignes restent
    valides, simplement hors curseur).

    ``background`` accepte les ``BackgroundTasks`` de FastAPI pour relayer
    l'événement au service temps réel après la réponse ; sans lui, le relais est
    programmé sur la boucle courante s'il y en a une. Le relais reste « best
    effort » : il n'échoue jamais la transaction métier.
    """

    # Refuser un média avant de prendre le moindre verrou d'écriture.
    _refuse_inline_media(event.payload)
    extra = {
        "schema_version": schema_version,
        "conversation_id": conversation_id,
        "step_id": step_id,
        "executor": executor,
        "emitted_by": emitted_by,
    }
    if not event.task_run_id:
        store_event(db, event, sequence=None, commit=commit, **extra)
        _schedule_forward(event, background=background, forward=forward)
        return None

    last_error: IntegrityError | None = None
    _ensure_write_transaction(db)
    for _ in range(SEQUENCE_ALLOCATION_ATTEMPTS):
        sequence = allocate_sequence(db, event.task_run_id)
        try:
            with db.begin_nested():
                store_event(db, event, sequence=sequence, commit=False, **extra)
                db.flush()
        except IntegrityError as exc:
            if not _is_sequence_collision(exc):
                raise
            # Une autre transaction a pris ce numéro : l'index unique partiel est
            # le seul arbitre, on relit et on rejoue.
            last_error = exc
            continue
        if commit:
            db.commit()
        _notify(event, sequence, committed=commit, db=db)
        _schedule_forward(event, background=background, forward=forward)
        return sequence

    raise SequenceAllocationError(
        "Séquence d'événement indisponible après "
        f"{SEQUENCE_ALLOCATION_ATTEMPTS} essais pour la tentative {event.task_run_id}."
    ) from last_error


def _notify(event: Event, sequence: int, *, committed: bool, db: Session) -> None:
    """Réveille les flux du run et du projet, une fois la ligne visible."""

    channels = [run_channel(event.task_run_id or "")]
    if event.project_id:
        channels.append(project_channel(event.project_id))

    def wake() -> None:
        for channel in channels:
            event_hub.notify(channel, sequence)

    if committed:
        wake()
        return
    # L'appelant garde sa transaction : réveiller maintenant ferait lire une ligne
    # encore invisible. Le réveil est donc reporté à son ``commit()`` ; à défaut,
    # l'interrogation périodique du flux prend le relais.
    from sqlalchemy import event as sqlalchemy_event

    sqlalchemy_event.listen(db, "after_commit", lambda _session: wake(), once=True)


def _schedule_forward(event: Event, *, background: Any | None, forward: bool) -> None:
    if not forward:
        return
    if background is not None:
        background.add_task(forward_event, event)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Route synchrone hors boucle : le relais temps réel est optionnel, le
        # journal durable a déjà tout enregistré.
        return
    task = loop.create_task(forward_event(event))
    # Garder une référence forte : une tâche uniquement référencée par la boucle
    # peut être ramassée avant la fin (avertissement documenté d'``asyncio``).
    _pending_forwards.add(task)
    task.add_done_callback(_pending_forwards.discard)


async def forward_event(event: Event) -> None:
    """Pousse l'événement vers le service temps réel ; jamais bloquant pour le métier."""
    service_token = os.environ.get("ACP_EVENT_SERVICE_TOKEN", "").strip()
    if not service_token:
        return
    try:
        event_service_url = normalize_service_origin(
            os.environ.get("ACP_EVENT_SERVICE_URL", "http://localhost:8001"),
            setting="ACP_EVENT_SERVICE_URL",
        )
    except ServiceOriginError:
        return

    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            response = await client.post(
                f"{event_service_url}/internal/events",
                json=event.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {service_token}"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        pass
