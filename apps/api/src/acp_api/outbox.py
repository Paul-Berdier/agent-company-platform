"""Boîte d'envoi transactionnelle des événements et relais avec reprise (Lot H3).

Le relais direct du Lot C (``forward_event`` : un POST « best effort » après la
réponse HTTP) perd un événement dès que le service temps réel est indisponible au
moment précis de la publication. La boîte d'envoi remplace ce pari par une ligne
``event_outbox`` écrite dans la **même** transaction que la ligne ``events`` : si le
métier est validé, la livraison est due ; si le métier est annulé, rien n'est dû.

Sémantique tenue, et seulement celle-là :

- **au-moins-une-fois** : une ligne n'est marquée livrée qu'après un 2xx du
  consommateur ; un incident entre le 2xx et le commit du relais renvoie
  l'événement, que le consommateur doit reconnaître (``DeliveryLedger`` du service
  d'événements) ;
- **ordre du journal par relais** : un relais livre ses lignes par ``journal_seq``
  croissant et s'arrête à la première erreur de transport, pour ne jamais livrer
  ``n+1`` avant ``n`` de son propre lot ; deux relais parallèles ne livrent jamais
  la même ligne (``SKIP LOCKED`` à la réclamation de chaque ligne), mais l'ordre
  **entre** relais n'est pas garanti — d'où une seule réplique par consommateur ;
- jamais **exactement-une-fois** : personne ne peut le promettre au-dessus d'un
  transport HTTP sans transaction distribuée, et ce module ne le prétend pas.

Le remplissage n'est actif que si ``ACP_EVENT_RELAY_ENABLED`` vaut exactement ``1`` :
sans la variable, ``store_event`` n'écrit aucune ligne d'outbox et le relais direct
historique reste en place. Avec elle, ``forward_event`` se tait et le relais
(``python -m acp_api.outbox_relay``) devient l'unique chemin vers le service
d'événements.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from acp_contracts import Event, ServiceOriginError, normalize_service_origin
from acp_database.locking import write_lock
from acp_database.models import EventModel, EventOutboxModel

__all__ = [
    "BACKOFF_CAP_SECONDS",
    "DEFAULT_CONSUMER",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "HTTP_TIMEOUT_ENV",
    "LAST_ERROR_MAX_LENGTH",
    "MAX_ATTEMPTS_ENV",
    "OUTBOX_LOCK_KEY",
    "RELAY_ENABLED_ENV",
    "HttpxTransport",
    "OutboxConfigurationError",
    "OutboxTransport",
    "RelayReport",
    "enqueue",
    "event_from_model",
    "list_dead",
    "max_attempts",
    "relay_enabled",
    "relay_once",
    "requeue_dead",
    "undelivered_filter",
]

RELAY_ENABLED_ENV = "ACP_EVENT_RELAY_ENABLED"
"""Vaut exactement ``1`` pour activer l'outbox et couper le relais direct."""

MAX_ATTEMPTS_ENV = "ACP_OUTBOX_MAX_ATTEMPTS"
HTTP_TIMEOUT_ENV = "ACP_OUTBOX_HTTP_TIMEOUT_SECONDS"

DEFAULT_CONSUMER = "event-service"
DEFAULT_MAX_ATTEMPTS = 8
DEFAULT_HTTP_TIMEOUT_SECONDS = 3.0

BACKOFF_CAP_SECONDS = 300
"""Plafond du recul exponentiel : ``min(2^attempts, 300)`` secondes."""

LAST_ERROR_MAX_LENGTH = 500
"""Largeur de la colonne ``last_error`` : le message est tronqué, jamais refusé."""

OUTBOX_LOCK_KEY = "events.outbox"
"""Clé du verrou d'écriture du relais, distincte de celle du journal."""

EVENT_ID_HEADER = "X-ACP-Event-Id"
JOURNAL_SEQ_HEADER = "X-ACP-Journal-Seq"
DELIVERY_ATTEMPT_HEADER = "X-ACP-Delivery-Attempt"


class OutboxConfigurationError(ValueError):
    """Le relais ne peut pas démarrer : jeton absent, origine invalide ou borne absurde."""


class OutboxTransport(Protocol):
    """Ce que le relais attend d'un transport : un ``post`` synchrone qui rend un statut.

    ``httpx.Client`` satisfait ce protocole ; les tests injectent un espion. Une
    erreur de transport se signale par ``httpx.HTTPError`` ou par un statut hors 2xx.
    """

    def post(
        self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float
    ) -> Any: ...


class HttpxTransport:
    """Transport de production : un ``httpx.Client`` sans mandataire d'environnement.

    ``trust_env=False`` pour la même raison que ``forward_event`` : un Bearer ne doit
    jamais transiter par un mandataire lu dans ``HTTP_PROXY``.
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    def post(
        self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float
    ) -> httpx.Response:
        if self._client is None:
            self._client = httpx.Client(trust_env=False)
        return self._client.post(url, json=json, headers=dict(headers), timeout=timeout)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


@dataclass(frozen=True, slots=True)
class RelayReport:
    """Ce qu'un passage de relais a fait ; ``error`` est vide si le lot est allé au bout."""

    delivered: int = 0
    failed: int = 0
    dead: int = 0
    cursor_hint: int | None = None
    error: str = ""

    @property
    def interrupted(self) -> bool:
        """Vrai si une erreur de transport a arrêté le lot avant sa fin."""

        return bool(self.error)

    def summary(self) -> str:
        """Compte rendu français, lisible dans un journal d'exploitation."""

        text = (
            f"Relais — livrés : {self.delivered}, échecs : {self.failed}, "
            f"lettres mortes : {self.dead}"
        )
        if self.cursor_hint is not None:
            text += f", dernier numéro de journal livré : {self.cursor_hint}"
        if self.error:
            text += f" ; lot interrompu : {self.error}"
        return text + "."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def relay_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Vrai si ``ACP_EVENT_RELAY_ENABLED`` vaut exactement ``1``.

    Aucune tolérance (« true », « yes ») : la variable bascule le chemin de
    livraison des événements, et une valeur approximative doit se voir comme un
    relais resté direct plutôt que comme une activation devinée.
    """

    environ = os.environ if environ is None else environ
    return environ.get(RELAY_ENABLED_ENV) == "1"


def max_attempts(environ: Mapping[str, str] | None = None) -> int:
    """Nombre d'essais avant lettre morte (``ACP_OUTBOX_MAX_ATTEMPTS``, 8 par défaut).

    Une valeur illisible ou inférieure à 1 est refusée : un relais qui abandonnerait
    au premier essai, ou jamais, ne serait pas celui que l'opérateur croit avoir.
    """

    environ = os.environ if environ is None else environ
    raw = (environ.get(MAX_ATTEMPTS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_ATTEMPTS
    try:
        value = int(raw)
    except ValueError as exc:
        raise OutboxConfigurationError(
            f"{MAX_ATTEMPTS_ENV} : un nombre d'essais est attendu, « {raw} » a été lu."
        ) from exc
    if value < 1:
        raise OutboxConfigurationError(
            f"{MAX_ATTEMPTS_ENV} : au moins un essai est nécessaire ({value} lu)."
        )
    return value


def _http_timeout(environ: Mapping[str, str]) -> float:
    raw = (environ.get(HTTP_TIMEOUT_ENV) or "").strip()
    if not raw:
        return DEFAULT_HTTP_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise OutboxConfigurationError(
            f"{HTTP_TIMEOUT_ENV} : un délai en secondes est attendu, « {raw} » a été lu."
        ) from exc
    if value <= 0:
        raise OutboxConfigurationError(
            f"{HTTP_TIMEOUT_ENV} : un délai strictement positif est attendu ({raw} lu)."
        )
    return value


def _destination(environ: Mapping[str, str]) -> tuple[str, str]:
    """Origine validée et jeton du service d'événements ; refus explicite sinon.

    Le relais direct se taisait sans jeton ; le relais d'outbox, lui, est le seul
    chemin de livraison et ne peut pas « réussir » en n'envoyant rien.
    """

    token = (environ.get("ACP_EVENT_SERVICE_TOKEN") or "").strip()
    if not token:
        raise OutboxConfigurationError(
            "ACP_EVENT_SERVICE_TOKEN est absent : le relais ne peut pas s'authentifier "
            "auprès du service d'événements."
        )
    try:
        origin = normalize_service_origin(
            environ.get("ACP_EVENT_SERVICE_URL", "http://localhost:8001"),
            setting="ACP_EVENT_SERVICE_URL",
        )
    except ServiceOriginError as exc:
        raise OutboxConfigurationError(str(exc)) from exc
    return f"{origin}/internal/events", token


# --- Écriture ------------------------------------------------------------------


def enqueue(
    db: Session,
    event_model: EventModel,
    *,
    consumer: str = DEFAULT_CONSUMER,
    now: datetime | None = None,
) -> EventOutboxModel:
    """Ajoute la ligne d'outbox d'un événement à la session, sans valider.

    À appeler juste après ``db.add(event_model)`` : la ligne part dans la même
    transaction et l'unité de travail insère ``events`` avant ``event_outbox``
    (clé étrangère). Un événement sans numéro de journal est refusé : le relais
    ordonne ses livraisons par ce numéro et ne saurait quoi faire d'une ligne sans lui.
    """

    if event_model.journal_seq is None:
        raise ValueError(
            "Une ligne d'outbox exige un numéro de journal : "
            f"l'événement {event_model.id} n'en porte pas."
        )
    row = EventOutboxModel(
        event_id=event_model.id,
        journal_seq=int(event_model.journal_seq),
        project_id=event_model.project_id,
        consumer=consumer,
        attempts=0,
        next_attempt_at=now or _utcnow(),
        last_error="",
    )
    db.add(row)
    return row


def event_from_model(model: EventModel) -> Event:
    """Reconstruit le contrat ``Event`` transporté au consommateur.

    Le corps envoyé est **inchangé** par rapport au relais direct : les clients web
    du service d'événements continuent de recevoir exactement le même document. Les
    métadonnées de livraison voyagent dans des en-têtes HTTP, pas dans le corps.
    """

    return Event(
        id=model.id,
        type=model.type,
        occurred_at=_as_utc(model.occurred_at),
        organization_id=model.organization_id,
        workspace_id=model.workspace_id,
        department_id=model.department_id,
        project_id=model.project_id,
        team_id=model.team_id,
        agent_instance_id=model.agent_instance_id,
        task_id=model.task_id,
        task_run_id=model.task_run_id,
        payload=model.payload or {},
    )


# --- Relais ----------------------------------------------------------------------


def _pending_filter(consumer: str):
    """Lignes encore à livrer : ni livrées, ni en lettre morte.

    L'échéance ``next_attempt_at`` n'est volontairement **pas** un filtre SQL : une
    ligne reculée après un échec doit continuer de retenir celles qui la suivent,
    sinon la ligne ``n+1`` doublerait la ligne ``n`` dès le passage suivant. La tête
    de file est donc lue, et l'échéance vérifiée sur elle (``relay_once``).
    """

    return (
        EventOutboxModel.consumer == consumer,
        EventOutboxModel.delivered_at.is_(None),
        EventOutboxModel.dead_at.is_(None),
    )


def _select_batch(
    db: Session, *, consumer: str, batch_size: int
) -> list[tuple[str, int]]:
    """Candidats du lot, par ``journal_seq`` croissant, **sans verrou**.

    Le verrou (``FOR UPDATE SKIP LOCKED`` sous PostgreSQL, verrou d'écriture sous
    SQLite) est pris ligne par ligne dans ``_claim`` : un ``FOR UPDATE`` posé ici sur
    tout le lot serait tenu jusqu'au premier commit et cacherait les cent lignes à
    un relais parallèle, qui repartirait les mains vides. Une candidate livrée ou
    prise entre-temps est simplement refusée par ``_claim``. Sous SQLite, une
    interrogation à vide toutes les 500 ms ne prend ainsi jamais le verrou de
    toute la base.
    """

    statement = (
        select(EventOutboxModel.event_id, EventOutboxModel.journal_seq)
        .where(*_pending_filter(consumer))
        .order_by(EventOutboxModel.journal_seq)
        .limit(batch_size)
    )
    return [(str(event_id), int(seq)) for event_id, seq in db.execute(statement).all()]


def _claim(db: Session, event_id: str, *, consumer: str) -> EventOutboxModel | None:
    """Verrouille une ligne encore à livrer, ou rend ``None`` si elle ne l'est plus.

    Le relais valide **par ligne** : chaque candidate est réclamée dans sa propre
    transaction juste avant son envoi. Sous PostgreSQL, une ligne tenue par un
    relais parallèle est sautée (``SKIP LOCKED``) ; sous SQLite, le verrou
    d'écriture sérialise les relais et la relecture voit une ligne déjà livrée.
    """

    statement = select(EventOutboxModel).where(
        EventOutboxModel.event_id == event_id, *_pending_filter(consumer)
    )
    if db.connection().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    else:
        write_lock(db, OUTBOX_LOCK_KEY)
    return db.execute(statement).scalar_one_or_none()


def _failure_message(response: Any | None, error: BaseException | None) -> str:
    if error is not None:
        return f"{type(error).__name__}: {error}"[:LAST_ERROR_MAX_LENGTH]
    body = ""
    if response is not None:
        body = (getattr(response, "text", "") or "").strip().replace("\n", " ")
    status = getattr(response, "status_code", "?")
    return f"HTTP {status}: {body}"[:LAST_ERROR_MAX_LENGTH]


def relay_once(
    session_factory: Callable[[], Session],
    transport: OutboxTransport | None = None,
    *,
    consumer: str = DEFAULT_CONSUMER,
    batch_size: int = 100,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> RelayReport:
    """Livre au plus ``batch_size`` lignes dues, dans l'ordre du journal.

    Chaque ligne est réclamée, envoyée (``POST {ACP_EVENT_SERVICE_URL}/internal/events``
    avec le Bearer ``ACP_EVENT_SERVICE_TOKEN`` et les en-têtes ``X-ACP-Event-Id``,
    ``X-ACP-Journal-Seq``, ``X-ACP-Delivery-Attempt``) puis validée **une par une**,
    pour qu'un arrêt brutal ne relivre que la ligne en cours. Un 2xx marque
    ``delivered_at`` ; tout autre statut ou une erreur ``httpx`` incrémente
    ``attempts``, recule ``next_attempt_at`` de ``min(2^attempts, 300)`` secondes,
    conserve le message dans ``last_error`` et **arrête le lot** : livrer la ligne
    suivante avant celle-ci violerait l'ordre du journal. Pour la même raison, une
    ligne reculée retient celles qui la suivent jusqu'à son échéance : le passage
    s'arrête sur la première ligne non encore due. Au-delà de
    ``ACP_OUTBOX_MAX_ATTEMPTS`` essais, la ligne passe en lettre morte (``dead_at``)
    et cesse de retenir la file — c'est à cela que sert la lettre morte.

    Une exception étrangère au transport (base injoignable, commit refusé) remonte
    telle quelle : la ligne reste due et sera renvoyée — c'est l'au-moins-une-fois.
    ``now`` et ``environ`` sont injectables ; sans transport, un ``httpx.Client`` sans
    mandataire est construit.
    """

    if batch_size < 1:
        raise OutboxConfigurationError(
            f"batch_size : au moins une ligne par lot est nécessaire ({batch_size} lu)."
        )
    environ = os.environ if environ is None else environ
    url, token = _destination(environ)
    limit = max_attempts(environ)
    timeout = _http_timeout(environ)
    moment = now or _utcnow()
    owned_transport = transport is None
    client: OutboxTransport = HttpxTransport() if transport is None else transport

    delivered = failed = dead = 0
    cursor_hint: int | None = None
    error = ""
    try:
        with session_factory() as db:
            candidates = _select_batch(db, consumer=consumer, batch_size=batch_size)
            # La lecture des candidats n'a rien modifié : rendre la transaction pour
            # que chaque ligne soit réclamée dans la sienne.
            db.rollback()
            for event_id, _journal_seq in candidates:
                row = _claim(db, event_id, consumer=consumer)
                if row is None:
                    # Livrée ou tenue par un autre relais entre-temps : rien à faire.
                    db.rollback()
                    continue
                if _as_utc(row.next_attempt_at) > moment:
                    # Tête de file reculée : rien de ce qui suit ne peut partir avant elle.
                    db.rollback()
                    break
                model = db.get(EventModel, row.event_id)
                if model is None:
                    # Impossible tant que la clé étrangère tient ; refus explicite
                    # plutôt qu'une ligne sautée en silence.
                    db.rollback()
                    raise RuntimeError(
                        f"Ligne d'outbox orpheline : l'événement {row.event_id} "
                        "n'existe plus dans le journal."
                    )
                attempt = int(row.attempts) + 1
                headers = {
                    "Authorization": f"Bearer {token}",
                    EVENT_ID_HEADER: model.id,
                    JOURNAL_SEQ_HEADER: str(row.journal_seq),
                    DELIVERY_ATTEMPT_HEADER: str(attempt),
                }
                response = None
                transport_error: BaseException | None = None
                try:
                    response = client.post(
                        url,
                        json=event_from_model(model).model_dump(mode="json"),
                        headers=headers,
                        timeout=timeout,
                    )
                except httpx.HTTPError as exc:
                    transport_error = exc
                status = getattr(response, "status_code", None)
                if transport_error is None and status is not None and 200 <= int(status) < 300:
                    row.delivered_at = moment
                    db.commit()
                    delivered += 1
                    cursor_hint = int(row.journal_seq)
                    continue
                error = _failure_message(response, transport_error)
                row.attempts = attempt
                row.last_error = error
                if attempt >= limit:
                    row.dead_at = moment
                    dead += 1
                else:
                    row.next_attempt_at = moment + timedelta(
                        seconds=min(2**attempt, BACKOFF_CAP_SECONDS)
                    )
                db.commit()
                failed += 1
                break
    finally:
        if owned_transport:
            client.close()  # type: ignore[attr-defined]
    return RelayReport(
        delivered=delivered,
        failed=failed,
        dead=dead,
        cursor_hint=cursor_hint,
        error=error,
    )


# --- Lettres mortes ------------------------------------------------------------


def list_dead(db: Session, *, consumer: str = DEFAULT_CONSUMER) -> list[EventOutboxModel]:
    """Lignes abandonnées après ``ACP_OUTBOX_MAX_ATTEMPTS`` essais, par numéro de journal."""

    statement = (
        select(EventOutboxModel)
        .where(
            EventOutboxModel.consumer == consumer,
            EventOutboxModel.dead_at.is_not(None),
        )
        .order_by(EventOutboxModel.journal_seq)
    )
    return list(db.execute(statement).scalars().all())


def requeue_dead(
    db: Session, *, consumer: str = DEFAULT_CONSUMER, now: datetime | None = None
) -> int:
    """Remet les lettres mortes en attente et valide ; renvoie leur nombre.

    Les essais repartent de zéro et la ligne redevient due immédiatement ; le dernier
    message d'erreur est conservé pour que l'opérateur sache pourquoi elle avait été
    abandonnée. Sous SQLite le verrou d'écriture est pris d'abord : un relais en cours
    ne doit pas voir une ligne changer d'état sous ses pieds.
    """

    moment = now or _utcnow()
    write_lock(db, OUTBOX_LOCK_KEY)
    rows = list_dead(db, consumer=consumer)
    for row in rows:
        row.dead_at = None
        row.attempts = 0
        row.next_attempt_at = moment
    db.commit()
    return len(rows)


def undelivered_filter():
    """Prédicat « livraison encore due ou abandonnée », partagé avec la rétention.

    Une lettre morte n'est pas livrée : la purger effacerait la seule trace d'un
    événement que le service temps réel n'a jamais reçu.
    """

    return or_(
        EventOutboxModel.delivered_at.is_(None),
        EventOutboxModel.dead_at.is_not(None),
    )
