"""Registre des livraisons vues : rend l'ingestion idempotente (Lot H3).

Le relais d'outbox livre **au-moins-une-fois** : un incident entre le 2xx du service
et le commit du relais renvoie le même événement. Sans registre, chaque renvoi
serait rediffusé aux clients WebSocket, qui verraient un événement en double.

État **en mémoire**, volontairement : un registre persistant ne changerait pas la
sémantique (au-moins-une-fois resterait vraie) et coûterait une écriture par
événement. Conséquence honnête : après un redémarrage du service, un lot renvoyé
par le relais peut être rediffusé au plus une fois — c'est la borne, pas une
promesse d'exactement-une-fois. La fenêtre est bornée par ``max_ids`` identifiants
(``ACP_EVENT_INGEST_DEDUPE_SIZE``, 10 000 par défaut) : au-delà, les plus anciens
sont oubliés en premier.
"""

from __future__ import annotations

import asyncio
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Mapping
from typing import Literal

__all__ = [
    "DEDUPE_SIZE_ENV",
    "DEFAULT_DEDUPE_SIZE",
    "DEFAULT_INFLIGHT_WAIT_SECONDS",
    "INFLIGHT_WAIT_ENV",
    "DeliveryLedger",
    "dedupe_size",
    "inflight_wait_seconds",
]

DEDUPE_SIZE_ENV = "ACP_EVENT_INGEST_DEDUPE_SIZE"
DEFAULT_DEDUPE_SIZE = 10_000

INFLIGHT_WAIT_ENV = "ACP_EVENT_INGEST_INFLIGHT_WAIT_SECONDS"
DEFAULT_INFLIGHT_WAIT_SECONDS = 2.0
"""Attente maximale d'un renvoi pendant que l'original est diffusé. Inférieure au délai
HTTP du relais (3 s par défaut, ``ACP_OUTBOX_HTTP_TIMEOUT_SECONDS``) : le renvoi reçoit
une réponse avant que le relais n'abandonne."""

Reservation = Literal["reserved", "seen", "in_flight"]


def inflight_wait_seconds(environ: Mapping[str, str] | None = None) -> float:
    """Attente d'un renvoi en vol ; une valeur illisible ou non positive refuse le démarrage."""

    environ = os.environ if environ is None else environ
    raw = (environ.get(INFLIGHT_WAIT_ENV) or "").strip()
    if not raw:
        return DEFAULT_INFLIGHT_WAIT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{INFLIGHT_WAIT_ENV} : un délai en secondes est attendu, « {raw} » a été lu."
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(
            f"{INFLIGHT_WAIT_ENV} : un délai strictement positif est attendu ({raw} lu)."
        )
    return value


def dedupe_size(environ: Mapping[str, str] | None = None) -> int:
    """Taille du registre ; une valeur illisible ou inférieure à 1 refuse le démarrage.

    Un registre de taille nulle ne dédoublonnerait rien tout en laissant croire
    l'inverse : mieux vaut un refus explicite au démarrage.
    """

    environ = os.environ if environ is None else environ
    raw = (environ.get(DEDUPE_SIZE_ENV) or "").strip()
    if not raw:
        return DEFAULT_DEDUPE_SIZE
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{DEDUPE_SIZE_ENV} : un nombre d'identifiants est attendu, « {raw} » a été lu."
        ) from exc
    if value < 1:
        raise RuntimeError(
            f"{DEDUPE_SIZE_ENV} : au moins un identifiant est nécessaire ({value} lu)."
        )
    return value


class DeliveryLedger:
    """Fenêtre glissante des identifiants d'événements déjà diffusés, et de ceux en vol.

    La route ne fait plus « vérifier, diffuser, mémoriser » en trois temps : entre le
    premier et le dernier, un renvoi voyait l'identifiant comme jamais vu et le
    rediffusait. ``reserve`` décide **sans rendre la main** : l'appelant diffuse
    (``reserved``), l'identifiant est déjà diffusé (``seen``), ou une autre livraison
    le diffuse en ce moment (``in_flight``, avec l'événement qui se lèvera à la fin).
    ``confirm`` mémorise après une diffusion réussie ; ``release`` libère après un
    échec, pour qu'un événement que personne n'a reçu ne soit jamais marqué comme vu.
    """

    def __init__(self, max_ids: int = DEFAULT_DEDUPE_SIZE) -> None:
        if max_ids < 1:
            raise ValueError("Un registre de livraisons garde au moins un identifiant.")
        self.max_ids = int(max_ids)
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._in_flight: dict[str, asyncio.Event] = {}
        self._lock = threading.Lock()

    def seen(self, event_id: str) -> bool:
        """Vrai si ``event_id`` a déjà été diffusé dans la fenêtre courante."""

        with self._lock:
            return event_id in self._ids

    def reserve(self, event_id: str) -> tuple[Reservation, asyncio.Event | None]:
        """Réserve ``event_id`` pour la diffusion, ou dit pourquoi ce n'est pas à l'appelant.

        À appeler depuis la boucle d'événements du service : l'événement rendu pour
        ``in_flight`` est un ``asyncio.Event`` de cette boucle.
        """

        with self._lock:
            if event_id in self._ids:
                return "seen", None
            waiter = self._in_flight.get(event_id)
            if waiter is not None:
                return "in_flight", waiter
            self._in_flight[event_id] = asyncio.Event()
            return "reserved", None

    def confirm(self, event_id: str) -> None:
        """Mémorise une diffusion réussie et réveille les renvois qui l'attendaient."""

        with self._lock:
            waiter = self._in_flight.pop(event_id, None)
            self._remember_locked(event_id)
        if waiter is not None:
            waiter.set()

    def release(self, event_id: str) -> None:
        """Libère une réservation après un échec, sans rien mémoriser."""

        with self._lock:
            waiter = self._in_flight.pop(event_id, None)
        if waiter is not None:
            waiter.set()

    def remember(self, event_id: str) -> None:
        """Mémorise ``event_id`` ; l'identifiant le plus ancien sort si la fenêtre est pleine."""

        with self._lock:
            self._remember_locked(event_id)

    def _remember_locked(self, event_id: str) -> None:
        if event_id in self._ids:
            self._ids.move_to_end(event_id)
            return
        self._ids[event_id] = None
        while len(self._ids) > self.max_ids:
            self._ids.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)

    def reset(self) -> None:
        """Oublie tout (utilisé entre deux tests)."""

        with self._lock:
            self._ids.clear()
            self._in_flight.clear()
