"""Écriture du journal durable, allocation de séquence et réveil des flux locaux.

Le journal est la **source de vérité** : le hub ne transporte que des numéros de
séquence et sert uniquement à réveiller un flux SSE plus tôt que son interrogation
périodique. Une coupure du hub ne perd donc aucun événement, elle ajoute au pire la
latence d'une interrogation.

Le journal porte **deux** compteurs, alloués dans la transaction métier et protégés
chacun par un index unique partiel ; en cas de collision concurrente, l'insertion est
rejouée dans un point de sauvegarde, au plus ``SEQUENCE_ALLOCATION_ATTEMPTS`` fois :

- ``sequence`` est monotone **par tentative** (``task_run_id``) et sert de curseur de
  reprise à la portée tentative (``Last-Event-ID``, ``after_seq``) ; index
  ``uq_event_run_sequence`` ;
- ``journal_seq`` est monotone **à l'échelle du journal** et sert de curseur à la
  portée projet ; index ``uq_events_journal_seq``. Une horloge ne peut pas tenir ce
  rôle : sa granularité réelle (environ 1,5 ms sous Windows) rend les égalités
  courantes, alors qu'un curseur de pagination exige un ordre **total**.

Tout événement reçoit un ``journal_seq``, avec ou sans tentative : c'est ce qui le
rend lisible dans la portée projet. L'allocation vit donc dans ``store_event``, le
point d'écriture unique, et pas seulement dans ``publish``.

Aucun média ne transite dans un événement (§0.2 de la spécification) : un événement
de média ne porte qu'une référence d'artefact (``media_reference_payload``). Quatre
contrôles, tous *refus explicites* à l'écriture — jamais un abandon silencieux :

1. taille : une charge utile sérialisée au-delà de ``PAYLOAD_MAX_BYTES`` est refusée,
   quel que soit le nom de ses clés — c'est ce contrôle-là, et non une liste de noms,
   qui arrête un média encodé en ligne dont personne n'avait prévu la clé ;
2. profondeur : au-delà de ``PAYLOAD_MAX_DEPTH`` niveaux, la charge utile est refusée
   parce qu'elle n'est plus inspectable ;
3. clés de contenu : les noms de ``INLINE_CONTENT_KEYS`` sont refusés à toute
   profondeur inspectée — un filet complémentaire, qui donne un message parlant ;
4. référence d'artefact : toute table portant ``artifact_id`` ne peut contenir que
   ``MEDIA_PAYLOAD_KEYS`` ; aucune clé étrangère ne voyage à côté d'une référence.

Ce que ces contrôles ne prétendent pas faire : reconnaître un petit fragment binaire
logé dans une clé quelconque. La garantie tenue est « rien d'assez gros, d'assez
profond ou d'assez mal nommé pour être un média », pas « aucun octet encodé ».
"""

from __future__ import annotations

import asyncio
import json
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
    "MEDIA_REFERENCE_KEY",
    "PAYLOAD_MAX_BYTES",
    "PAYLOAD_MAX_DEPTH",
    "SEQUENCE_ALLOCATION_ATTEMPTS",
    "EventHub",
    "MediaPayloadRefused",
    "SequenceAllocationError",
    "allocate_journal_seq",
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

MEDIA_REFERENCE_KEY = "artifact_id"
"""Clé qui identifie une référence d'artefact, à quelque profondeur qu'elle soit."""

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

PAYLOAD_MAX_BYTES = 64 * 1024
"""Taille maximale d'une charge utile sérialisée (§0.2).

Ce n'est pas une borne de conception mais une borne **anti-média** : un événement
métier tient très largement dedans, un média encodé en ligne n'y tient jamais. Elle
attrape ce qu'aucune liste de noms de clés ne peut attraper.
"""

_ALLOCATION_COLLISION_MARKERS = (
    # PostgreSQL nomme les index uniques partiels…
    "uq_event_run_sequence",
    "uq_events_journal_seq",
    # …SQLite nomme les colonnes de l'index.
    "events.task_run_id, events.sequence",
    "events.journal_seq",
)

_HUB_QUEUE_MAXSIZE = 64

_pending_forwards: set[asyncio.Task] = set()
"""Références fortes des relais en vol : sans elles, ``asyncio`` peut les ramasser."""


class SequenceAllocationError(RuntimeError):
    """Aucun numéro libre après ``SEQUENCE_ALLOCATION_ATTEMPTS`` essais.

    Vaut pour la séquence de tentative comme pour le compteur de journal : les deux
    suivent la même discipline d'allocation.
    """


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


def _is_container(value: Any) -> bool:
    return isinstance(value, (list, tuple)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _refuse_foreign_media_keys(mapping: Mapping[Any, Any], path: str) -> None:
    """Une référence d'artefact ne porte **que** ses clés : rien ne voyage à côté.

    Contrôle *positif* : la liste des clés admises fait foi, au lieu d'espérer qu'un
    média se dénonce par le nom de sa clé.
    """

    foreign = sorted(str(key) for key in mapping if str(key) not in MEDIA_PAYLOAD_KEYS)
    if foreign:
        raise MediaPayloadRefused(
            "Une référence d'artefact ne contient que "
            f"{', '.join(MEDIA_PAYLOAD_KEYS)} : « {path} » ajoute {', '.join(foreign)}."
        )


def _refuse_unsafe_payload(value: Any, depth: int = 0, path: str = "payload") -> None:
    """Refuse toute charge utile qui pourrait transporter un média (§0.2).

    Trois refus, tous explicites : une clé de contenu encodé en ligne, une référence
    d'artefact alourdie d'une clé étrangère, et une imbrication trop profonde pour
    être inspectée — cette dernière était auparavant **ignorée** en silence.
    """

    if depth > PAYLOAD_MAX_DEPTH:
        raise MediaPayloadRefused(
            f"Charge utile trop imbriquée pour être contrôlée (« {path} », au-delà de "
            f"{PAYLOAD_MAX_DEPTH} niveaux) : un événement reste plat et sans média."
        )
    if isinstance(value, Mapping):
        for key in value:
            if isinstance(key, str) and key.strip().lower() in INLINE_CONTENT_KEYS:
                raise MediaPayloadRefused(
                    "Un événement ne transporte jamais de média : "
                    f"la clé « {key} » doit être remplacée par une référence d'artefact."
                )
        if any(str(key) == MEDIA_REFERENCE_KEY for key in value):
            _refuse_foreign_media_keys(value, path)
        for key, nested in value.items():
            _refuse_unsafe_payload(nested, depth + 1, f"{path}.{key}")
        return
    if _is_container(value):
        for index, nested in enumerate(value):
            _refuse_unsafe_payload(nested, depth + 1, f"{path}[{index}]")


def _refuse_oversized_payload(payload: Any) -> None:
    """Borne la charge utile sérialisée : aucun média n'entre dans ``PAYLOAD_MAX_BYTES``."""

    if not payload:
        return
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    if len(encoded) > PAYLOAD_MAX_BYTES:
        raise MediaPayloadRefused(
            f"Charge utile de {len(encoded)} octets : au-delà de {PAYLOAD_MAX_BYTES}, "
            "un événement cite une référence d'artefact au lieu de porter le contenu."
        )


def _refuse_media_payload(payload: Any) -> None:
    """Point d'entrée unique du contrôle « aucun média dans un événement »."""

    _refuse_oversized_payload(payload)
    _refuse_unsafe_payload(payload)


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


def allocate_journal_seq(db: Session) -> int:
    """Retourne le prochain numéro libre du journal, toutes portées confondues.

    Même discipline que ``allocate_sequence`` : l'appel ne consomme rien, l'unicité
    est garantie par l'index ``uq_events_journal_seq``, et la collision concurrente
    est rattrapée par le réessai de l'écriture.

    Le maximum est lu par ``ORDER BY … LIMIT 1`` verrouillé plutôt que par un
    agrégat : ``FOR UPDATE`` est refusé sur un agrégat par PostgreSQL, et c'est bien
    la ligne la plus haute qu'il faut verrouiller.
    """

    statement = (
        select(func.coalesce(EventModel.journal_seq, 0))
        .where(EventModel.journal_seq.is_not(None))
        .order_by(EventModel.journal_seq.desc())
        .limit(1)
        .with_for_update()
    )
    highest = db.execute(statement).scalar()
    return int(highest or 0) + 1


def _is_allocation_collision(error: IntegrityError) -> bool:
    """Distingue la collision d'un compteur de toute autre violation d'unicité.

    Rejouer aveuglément masquerait le vrai défaut de l'appelant — une clé primaire en
    double, par exemple — derrière cinq essais inutiles et un message trompeur.
    """

    message = str(getattr(error, "orig", None) or error)
    return any(marker in message for marker in _ALLOCATION_COLLISION_MARKERS)


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
    journal_seq: int | None,
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
        journal_seq=journal_seq,
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
    journal_seq: int | None = None,
    commit: bool = True,
    schema_version: str = EVENT_SCHEMA_VERSION,
    conversation_id: str | None = None,
    step_id: str | None = None,
    executor: str | None = None,
    emitted_by: str | None = None,
) -> EventModel:
    """Persiste un événement, en lui garantissant ses deux numéros.

    ``commit=True`` (défaut) préserve le comportement du Lot C pour les appelants
    existants qui n'ouvrent pas de transaction explicite. Un appelant qui possède
    déjà sa transaction passe ``commit=False`` : rien n'est validé avant son propre
    ``commit()``.

    ``journal_seq`` n'est fourni que par ``publish``, qui mène déjà sa propre boucle
    d'allocation. Sans lui, l'allocation est faite ici : un appelant direct (les
    routeurs du Lot C) écrirait sinon une ligne sans numéro, donc invisible dans la
    portée projet — exactement la perte silencieuse que ce curseur doit empêcher.

    ``sequence`` suit la même règle : un événement qui porte une tentative reçoit
    ici sa séquence de tentative si l'appelant ne l'a pas déjà allouée. Sans elle,
    les événements terminaux du Lot C (``task.completed``, ``task.failed``,
    ``task.blocked``, ``task.cancelled``, ``task.interrupted``) et les événements de
    mission sortiraient de ``GET /runs/{id}/events`` et du flux de la tentative :
    le Studio ne verrait jamais une mission se clore.
    """

    _refuse_media_payload(event.payload)
    extra = {
        "schema_version": schema_version,
        "conversation_id": conversation_id,
        "step_id": step_id,
        "executor": executor,
        "emitted_by": emitted_by,
    }
    if journal_seq is None:
        return _store_numbered(db, event, sequence=sequence, commit=commit, **extra)
    model = _event_model(event, sequence=sequence, journal_seq=journal_seq, **extra)
    db.add(model)
    if commit:
        db.commit()
    return model


def _store_numbered(
    db: Session, event: Event, *, sequence: int | None, commit: bool, **extra: Any
) -> EventModel:
    """Écrit en allouant les numéros manquants, avec la discipline de ``publish``.

    Les deux numéros sont relus à chaque essai : une allocation périmée ne doit
    jamais survivre à la reprise qui la corrige.
    """

    last_error: IntegrityError | None = None
    _ensure_write_transaction(db)
    for _ in range(SEQUENCE_ALLOCATION_ATTEMPTS):
        run_sequence = sequence
        if run_sequence is None and event.task_run_id:
            run_sequence = allocate_sequence(db, event.task_run_id)
        model = _event_model(
            event, sequence=run_sequence, journal_seq=allocate_journal_seq(db), **extra
        )
        try:
            with db.begin_nested():
                db.add(model)
                db.flush()
        except IntegrityError as exc:
            if not _is_allocation_collision(exc):
                raise
            last_error = exc
            continue
        if commit:
            db.commit()
        return model

    raise SequenceAllocationError(
        "Numéro de journal indisponible après "
        f"{SEQUENCE_ALLOCATION_ATTEMPTS} essais pour l'événement {event.id}."
    ) from last_error


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
    """Alloue les numéros, persiste, réveille les flux locaux puis relaie l'événement.

    Retourne la séquence de tentative allouée, ou ``None`` pour un événement sans
    tentative (l'unicité ``(task_run_id, sequence)`` est partielle : ces lignes
    restent valides, simplement hors du curseur de tentative). Le numéro de journal,
    lui, est alloué dans **tous** les cas : c'est le curseur de la portée projet.

    ``background`` accepte les ``BackgroundTasks`` de FastAPI pour relayer
    l'événement au service temps réel après la réponse ; sans lui, le relais est
    programmé sur la boucle courante s'il y en a une. Le relais reste « best
    effort » : il n'échoue jamais la transaction métier.
    """

    # Refuser un média avant de prendre le moindre verrou d'écriture.
    _refuse_media_payload(event.payload)
    extra = {
        "schema_version": schema_version,
        "conversation_id": conversation_id,
        "step_id": step_id,
        "executor": executor,
        "emitted_by": emitted_by,
    }
    last_error: IntegrityError | None = None
    _ensure_write_transaction(db)
    for _ in range(SEQUENCE_ALLOCATION_ATTEMPTS):
        # Les deux numéros sont relus à chaque essai : une allocation périmée ne
        # doit jamais survivre à la reprise qui la corrige.
        journal_seq = allocate_journal_seq(db)
        sequence = (
            allocate_sequence(db, event.task_run_id) if event.task_run_id else None
        )
        try:
            with db.begin_nested():
                store_event(
                    db,
                    event,
                    sequence=sequence,
                    journal_seq=journal_seq,
                    commit=False,
                    **extra,
                )
                db.flush()
        except IntegrityError as exc:
            if not _is_allocation_collision(exc):
                raise
            # Une autre transaction a pris ce numéro : l'index unique partiel est
            # le seul arbitre, on relit et on rejoue.
            last_error = exc
            continue
        if commit:
            db.commit()
        _notify(
            event,
            sequence if sequence is not None else journal_seq,
            committed=commit,
            db=db,
        )
        _schedule_forward(event, background=background, forward=forward)
        return sequence

    scope = (
        f"la tentative {event.task_run_id}" if event.task_run_id else "le journal"
    )
    raise SequenceAllocationError(
        "Numéro d'événement indisponible après "
        f"{SEQUENCE_ALLOCATION_ATTEMPTS} essais pour {scope}."
    ) from last_error


def _notify(event: Event, wake_value: int, *, committed: bool, db: Session) -> None:
    """Réveille les flux du run et du projet, une fois la ligne visible.

    ``wake_value`` n'est qu'un jeton de réveil : la lecture en base reste la source
    de vérité, et un événement sans tentative réveille tout de même son projet.
    """

    channels = []
    if event.task_run_id:
        channels.append(run_channel(event.task_run_id))
    if event.project_id:
        channels.append(project_channel(event.project_id))
    if not channels:
        return

    def wake() -> None:
        for channel in channels:
            event_hub.notify(channel, wake_value)

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
