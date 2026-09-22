"""Écriture du journal durable, allocation de séquence et réveil des flux locaux.

Le journal est la **source de vérité** : le hub ne transporte que des numéros de
séquence et sert uniquement à réveiller un flux SSE plus tôt que son interrogation
périodique. Une coupure du hub ne perd donc aucun événement, elle ajoute au pire la
latence d'une interrogation.

Le journal porte **deux** compteurs, attribués au commit de la transaction métier et
protégés chacun par un index unique partiel ; en cas de collision, l'attribution est
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

Verrou et boîte d'envoi (Lot H3, revu en 0.9.1). Les numéros sont attribués **au
commit** (``_number_pending_events``), sous ``write_lock(db, 'events.journal')``, puis
dans le même ordre (journal, puis tentative). Sous PostgreSQL c'est un verrou
consultatif tenu jusqu'au commit, ce qui rend ``journal_seq`` contigu **et ordonné par
commit** ; pris au commit, il est le **dernier** verrou de la transaction et ne peut
plus former de cycle avec un verrou de ligne. Sous SQLite, ``store_event`` conserve le
``BEGIN IMMEDIATE`` historique dès le premier événement. Quand
``ACP_EVENT_RELAY_ENABLED`` vaut ``1``, la ligne ``event_outbox`` est ajoutée au commit,
dans la même transaction, et ``forward_event`` se tait : le relais
(``acp_api.outbox_relay``) devient l'unique chemin vers le service d'événements.
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
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    EVENT_SCHEMA_VERSION,
    Event,
    ServiceOriginError,
    normalize_service_origin,
)
from acp_database.locking import write_lock
from acp_database.models import EventModel

from .outbox import enqueue as _enqueue_outbox
from .outbox import relay_enabled

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "INLINE_CONTENT_KEYS",
    "JOURNAL_LOCK_KEY",
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

JOURNAL_LOCK_KEY = "events.journal"
"""Clé du verrou d'écriture pris avant toute allocation de numéro."""

_ALLOCATION_INDEX_NAMES = frozenset({"uq_event_run_sequence", "uq_events_journal_seq"})
"""Index uniques dont la violation signe une collision d'allocation (psycopg)."""

_UNIQUE_VIOLATION_SQLSTATE = "23505"

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

    Deux reconnaissances, dans cet ordre : le diagnostic structuré de psycopg
    (``sqlstate`` 23505 et ``diag.constraint_name`` parmi les index d'allocation),
    qui ne dépend ni de la langue du serveur ni du libellé du message ; puis les
    marqueurs textuels, seuls disponibles sous SQLite.
    """

    original = getattr(error, "orig", None)
    if original is not None:
        sqlstate = getattr(original, "sqlstate", None)
        diagnostic = getattr(original, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", None)
        if sqlstate == _UNIQUE_VIOLATION_SQLSTATE and constraint in _ALLOCATION_INDEX_NAMES:
            return True
    message = str(original or error)
    return any(marker in message for marker in _ALLOCATION_COLLISION_MARKERS)


def _ensure_write_transaction(db: Session) -> None:
    """Prend le verrou d'écriture du journal.

    Délègue à ``acp_database.locking.write_lock`` : sous PostgreSQL, un verrou
    consultatif de transaction sur ``events.journal``, tenu jusqu'au commit ; sous
    SQLite, le ``BEGIN IMMEDIATE`` historique. Depuis 0.9.1, il n'est pris qu'au
    **commit**, par ``_number_pending_events`` : c'est le dernier verrou de la
    transaction, qui ne peut donc plus former de cycle avec un verrou de ligne. Le nom
    est conservé pour les appelants du Lot E.
    """

    write_lock(db, JOURNAL_LOCK_KEY)


def _begin_sqlite_write(db: Session) -> None:
    """Sous SQLite seulement : ouvre la transaction en écriture dès le premier événement.

    SQLite ne sait pas faire passer une transaction de lecture en écriture pendant
    qu'une autre écrit : les deux échoueraient en « database is locked ». Le
    ``BEGIN IMMEDIATE`` historique est donc conservé ici. Sous PostgreSQL, rien n'est
    verrouillé à ce stade : le verrou du journal attend le commit.
    """

    if db.get_bind().dialect.name == "sqlite":
        write_lock(db, JOURNAL_LOCK_KEY)


_PENDING_EVENTS_KEY = "acp.events_bus.pending"
"""Clé de ``Session.info`` : événements de la transaction en attente de numéros."""


def _add_event(db: Session, model: EventModel) -> None:
    """Ajoute la ligne du journal ; ses numéros et sa ligne d'outbox attendent le commit.

    Un événement dont les numéros sont déjà fournis part tel quel, avec sa ligne
    d'outbox si le relais est actif. Les autres sont numérotés au commit par
    ``_number_pending_events``, qui ajoute alors leur ligne d'outbox dans la même
    transaction : un rollback métier retire les deux, un commit rend la livraison due.
    """

    db.add(model)
    if model.journal_seq is None or (model.task_run_id and model.sequence is None):
        db.info.setdefault(_PENDING_EVENTS_KEY, []).append(model)
        return
    model._acp_numbers = (model.journal_seq, model.sequence)
    if relay_enabled():
        _enqueue_outbox(db, model)


def _still_in_transaction(session: Session, model: EventModel) -> bool:
    """Vrai si la ligne appartient encore à la transaction : un point de sauvegarde
    annulé ou un ``expunge`` la rendent transitoire, et elle n'est alors pas numérotée."""

    state = sqlalchemy_inspect(model)
    return state.session is session and not state.deleted and (state.persistent or state.pending)


@sqlalchemy_event.listens_for(Session, "before_commit")
def _number_pending_events(session: Session) -> None:
    """Numérote au commit les événements de la transaction, sous le verrou du journal.

    Le verrou ``events.journal`` est pris **ici, en dernier** : jusqu'en 0.9.0, il
    l'était à la publication, au milieu de la transaction métier, et une transaction
    qui verrouillait une ligne après avoir publié s'opposait à une autre qui publiait
    après avoir verrouillé cette ligne (interblocages planificateur contre routes
    d'automatisation, expiration de bail contre fin de tentative). Tenu jusqu'au
    commit, il garde ``journal_seq`` ordonné par commit, ce qu'exige le curseur de la
    portée projet.

    Les lignes sont d'abord insérées sans numéro, hors de tout point de sauvegarde ;
    l'attribution des numéros est rejouée dans un point de sauvegarde en cas de
    collision, au plus ``SEQUENCE_ALLOCATION_ATTEMPTS`` fois.

    SQLAlchemy émet aussi ``before_commit`` à la libération d'un point de sauvegarde :
    seul le commit de la transaction racine numérote, sans quoi le verrou du journal
    serait repris au milieu de la transaction.
    """

    if session.in_nested_transaction():
        return
    pending = session.info.pop(_PENDING_EVENTS_KEY, None)
    if not pending:
        return
    alive = [model for model in pending if _still_in_transaction(session, model)]
    if not alive:
        return
    session.flush()
    _ensure_write_transaction(session)
    last_error: IntegrityError | None = None
    for _ in range(SEQUENCE_ALLOCATION_ATTEMPTS):
        # Les numéros sont relus à chaque essai : une allocation périmée ne doit
        # jamais survivre à la reprise qui la corrige.
        journal_next = allocate_journal_seq(session)
        run_next: dict[str, int] = {}
        for model in alive:
            if model.task_run_id and model.sequence is None and model.task_run_id not in run_next:
                run_next[model.task_run_id] = allocate_sequence(session, model.task_run_id)
        try:
            with session.begin_nested():
                for model in alive:
                    if model.journal_seq is None:
                        model.journal_seq = journal_next
                        journal_next += 1
                    if model.task_run_id and model.sequence is None:
                        model.sequence = run_next[model.task_run_id]
                        run_next[model.task_run_id] += 1
                session.flush()
        except IntegrityError as exc:
            if not _is_allocation_collision(exc):
                raise
            last_error = exc
            continue
        break
    else:
        raise SequenceAllocationError(
            "Numéro d'événement indisponible après "
            f"{SEQUENCE_ALLOCATION_ATTEMPTS} essais au commit de "
            f"{len(alive)} événement(s)."
        ) from last_error
    relay = relay_enabled()
    for model in alive:
        # Mémorisés hors des attributs cartographiés : après le commit, les lire ne
        # doit pas rouvrir une transaction pour les recharger.
        model._acp_numbers = (model.journal_seq, model.sequence)
        if relay:
            _enqueue_outbox(session, model)


@sqlalchemy_event.listens_for(Session, "after_transaction_end")
def _forget_pending_events(session: Session, transaction: Any) -> None:
    """La fin de la transaction racine (rollback, fermeture) oublie ses événements.

    Après un commit, les numéros et les annonces ont déjà été traités par
    ``before_commit`` et ``after_commit`` ; après un rollback, rien n'est dû.

    Un point de sauvegarde annulé ne vide rien : les événements publiés avant lui
    restent dus, et ceux qu'il retire sont écartés au commit par
    ``_still_in_transaction``.
    """

    if transaction.parent is None:
        session.info.pop(_PENDING_EVENTS_KEY, None)
        session.info.pop(_PENDING_ANNOUNCEMENTS_KEY, None)


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
    """Persiste un événement ; ses deux numéros lui sont attribués au commit.

    ``commit=True`` (défaut) préserve le comportement du Lot C pour les appelants
    existants qui n'ouvrent pas de transaction explicite. Un appelant qui possède
    déjà sa transaction passe ``commit=False`` : rien n'est validé ni numéroté avant
    son propre ``commit()``, et l'événement part dans la même transaction que l'effet
    métier qu'il décrit — jamais un effet validé suivi d'un événement perdu.

    Tout événement reçoit un ``journal_seq`` au commit, et une ``sequence`` s'il porte
    une tentative : sans eux, il sortirait de la portée projet ou du flux de la
    tentative (les événements terminaux du Lot C, ceux des missions). Des numéros
    fournis explicitement ne sont jamais réattribués.
    """

    _refuse_media_payload(event.payload)
    extra = {
        "schema_version": schema_version,
        "conversation_id": conversation_id,
        "step_id": step_id,
        "executor": executor,
        "emitted_by": emitted_by,
    }
    _begin_sqlite_write(db)
    model = _event_model(event, sequence=sequence, journal_seq=journal_seq, **extra)
    _add_event(db, model)
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
    """Persiste l'événement puis, une fois validé, réveille les flux locaux et le relaie.

    Retourne la séquence de tentative attribuée au commit, ou ``None`` : événement sans
    tentative, ou ``commit=False`` (les numéros n'existent qu'au commit de
    l'appelant, depuis 0.9.1).

    ``background`` accepte les ``BackgroundTasks`` de FastAPI pour relayer
    l'événement au service temps réel après la réponse ; sans lui, le relais est
    programmé sur la boucle courante s'il y en a une. Le relais reste « best
    effort » : il n'échoue jamais la transaction métier. Avec ``commit=False``, réveil
    et relais attendent le commit de l'appelant : une transaction annulée n'annonce
    rien, et aucun relais ne part pour un événement absent du journal.
    """

    model = store_event(
        db,
        event,
        commit=commit,
        schema_version=schema_version,
        conversation_id=conversation_id,
        step_id=step_id,
        executor=executor,
        emitted_by=emitted_by,
    )
    announcement = _Announcement(event, model, background=background, forward=forward)
    if commit:
        announcement.run()
    else:
        db.info.setdefault(_PENDING_ANNOUNCEMENTS_KEY, []).append(announcement)
    numbers = getattr(model, "_acp_numbers", None) if commit else None
    return numbers[1] if numbers else None


_PENDING_ANNOUNCEMENTS_KEY = "acp.events_bus.announcements"
"""Clé de ``Session.info`` : réveils et relais en attente du commit de l'appelant."""


@dataclass
class _Announcement:
    """Ce qu'un événement validé déclenche hors de la base : réveil local et relais."""

    event: Event
    model: EventModel
    background: Any | None = None
    forward: bool = True

    def run(self) -> None:
        numbers = getattr(self.model, "_acp_numbers", None)
        if numbers is None:
            # Jamais numéroté : la transaction qui le portait a été annulée.
            return
        _wake(self.event, numbers)
        _schedule_forward(self.event, background=self.background, forward=self.forward)


@sqlalchemy_event.listens_for(Session, "after_commit")
def _announce_committed_events(session: Session) -> None:
    """Annonce les événements d'une transaction racine, une fois ses lignes visibles.

    ``after_commit`` est aussi émis à la libération d'un point de sauvegarde : rien
    n'est encore visible des autres connexions, l'annonce attend donc le commit racine.
    """

    if session.in_nested_transaction():
        return
    for announcement in session.info.pop(_PENDING_ANNOUNCEMENTS_KEY, None) or ():
        announcement.run()


def _wake(event: Event, numbers: tuple[int | None, int | None]) -> None:
    """Réveille les flux du run et du projet.

    La valeur transmise n'est qu'un jeton de réveil : la lecture en base reste la
    source de vérité, et un événement sans tentative réveille tout de même son projet.
    À défaut de réveil, l'interrogation périodique du flux prend le relais.
    """

    journal_seq, sequence = numbers
    wake_value = sequence if sequence is not None else journal_seq
    if event.task_run_id:
        event_hub.notify(run_channel(event.task_run_id), wake_value)
    if event.project_id:
        event_hub.notify(project_channel(event.project_id), wake_value)


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
    """Pousse l'événement vers le service temps réel ; jamais bloquant pour le métier.

    La porte du relais d'outbox est **ici**, et non dans ``_schedule_forward`` : les
    routeurs du Lot C (``work``, ``platform``, ``crud``, ``automations``) appellent
    ``forward_event`` directement via ``background.add_task``. Quand
    ``ACP_EVENT_RELAY_ENABLED`` vaut ``1``, aucune requête n'est émise : la ligne
    d'outbox écrite par ``store_event`` est le seul chemin, et un envoi direct en
    plus ferait recevoir chaque événement deux fois au service.
    """
    if relay_enabled():
        return
    service_token = os.environ.get("ACP_EVENT_SERVICE_TOKEN", "").strip()
    if not service_token:
        return
    try:
        event_service_url = normalize_service_origin(
            os.environ.get("ACP_EVENT_SERVICE_URL", "http://localhost:8001"),
            setting="ACP_EVENT_SERVICE_URL",
            internal_http_hosts=os.environ.get("ACP_INTERNAL_HTTP_HOSTS", ""),
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
