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

import os
import threading
from collections import OrderedDict
from collections.abc import Mapping

__all__ = [
    "DEDUPE_SIZE_ENV",
    "DEFAULT_DEDUPE_SIZE",
    "DeliveryLedger",
    "dedupe_size",
]

DEDUPE_SIZE_ENV = "ACP_EVENT_INGEST_DEDUPE_SIZE"
DEFAULT_DEDUPE_SIZE = 10_000


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
    """Fenêtre glissante des identifiants d'événements déjà diffusés.

    ``seen`` répond sans modifier ; ``remember`` enregistre **après** la diffusion,
    pour qu'un échec de diffusion ne marque jamais comme vu un événement que
    personne n'a reçu. Un identifiant revu est rafraîchi en tête de fenêtre.
    """

    def __init__(self, max_ids: int = DEFAULT_DEDUPE_SIZE) -> None:
        if max_ids < 1:
            raise ValueError("Un registre de livraisons garde au moins un identifiant.")
        self.max_ids = int(max_ids)
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()

    def seen(self, event_id: str) -> bool:
        """Vrai si ``event_id`` a déjà été diffusé dans la fenêtre courante."""

        with self._lock:
            return event_id in self._ids

    def remember(self, event_id: str) -> None:
        """Mémorise ``event_id`` ; l'identifiant le plus ancien sort si la fenêtre est pleine."""

        with self._lock:
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
