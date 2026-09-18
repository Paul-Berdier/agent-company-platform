"""Commande du relais d'outbox (Lot H3).

Le relais est un processus **à part** de l'API : il lit ``event_outbox``, livre au
service d'événements dans l'ordre du journal et valide ligne par ligne. Une seule
réplique tourne à la fois (``deploy/railway/relay``), non par verrou global mais parce
que l'ordre **entre** relais n'est pas garanti ; le ``SKIP LOCKED`` de ``relay_once``
empêche seulement deux relais de livrer la même ligne.

Usage :

```text
python -m acp_api.outbox_relay --once            # un lot, puis sortie (0, ou 3 si interrompu)
python -m acp_api.outbox_relay --follow          # boucle jusqu'à SIGTERM/SIGINT
python -m acp_api.outbox_relay --list-dead       # lettres mortes, sans rien changer
python -m acp_api.outbox_relay --requeue-dead    # remet les lettres mortes en attente
```

Options : ``--batch-size`` (100), ``--poll-interval-ms`` (500), ``--consumer``
(``event-service``). Codes de sortie : ``0`` succès, ``2`` usage ou configuration
invalide (schéma hors version, jeton absent, origine refusée), ``3`` lot ``--once``
interrompu par une erreur de transport — les lignes restantes seront rejouées.

La commande démarre par ``init_db()`` : sous PostgreSQL, un schéma qui n'est pas à
la révision de tête refuse le démarrage plutôt que de lire une table incomplète.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, TextIO

from .outbox import (
    DEFAULT_CONSUMER,
    OutboxConfigurationError,
    OutboxTransport,
    RelayReport,
    list_dead,
    relay_once,
    requeue_dead,
)

__all__ = [
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_USAGE",
    "FOLLOW_BACKOFF_MAX_SECONDS",
    "FOLLOW_BACKOFF_MIN_SECONDS",
    "follow",
    "main",
]

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INTERRUPTED = 3

FOLLOW_BACKOFF_MIN_SECONDS = 1.0
FOLLOW_BACKOFF_MAX_SECONDS = 60.0

DEFAULT_BATCH_SIZE = 100
DEFAULT_POLL_INTERVAL_MS = 500


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m acp_api.outbox_relay",
        description=(
            "Relaie les événements de la boîte d'envoi vers le service d'événements, "
            "dans l'ordre du journal. Sans option, un seul lot est traité."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once", action="store_true", help="Traite un lot puis s'arrête (défaut)."
    )
    mode.add_argument(
        "--follow",
        action="store_true",
        help="Boucle jusqu'à SIGTERM/SIGINT, avec recul exponentiel après erreur.",
    )
    mode.add_argument(
        "--list-dead",
        action="store_true",
        help="Affiche les lettres mortes du consommateur, sans rien modifier.",
    )
    mode.add_argument(
        "--requeue-dead",
        action="store_true",
        help="Remet les lettres mortes en attente de livraison.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Lignes par lot (défaut {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--poll-interval-ms",
        type=int,
        default=DEFAULT_POLL_INTERVAL_MS,
        help=f"Attente entre deux lots vides en --follow (défaut {DEFAULT_POLL_INTERVAL_MS}).",
    )
    parser.add_argument(
        "--consumer",
        default=DEFAULT_CONSUMER,
        help=f"Consommateur servi (défaut « {DEFAULT_CONSUMER} »).",
    )
    return parser


class _StopSignal:
    """Drapeau d'arrêt armé par SIGTERM/SIGINT, ou par le test qui l'injecte."""

    def __init__(self, stop: threading.Event | None = None) -> None:
        self.event = stop or threading.Event()

    def install(self) -> None:
        """Pose les gestionnaires de signal si le fil courant le permet.

        ``signal.signal`` refuse hors du fil principal ; un relais lancé depuis un
        test ou un fil secondaire garde alors son drapeau injecté.
        """

        def _handler(_signum: int, _frame: Any) -> None:
            self.event.set()

        for name in ("SIGTERM", "SIGINT"):
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                signal.signal(signum, _handler)
            except ValueError:
                return

    def wait(self, seconds: float) -> bool:
        """Attend ``seconds`` ou l'arrêt ; vrai si l'arrêt a été demandé."""

        return self.event.wait(max(0.0, seconds))


def follow(
    session_factory: Callable[[], Any],
    transport: OutboxTransport | None,
    *,
    consumer: str,
    batch_size: int,
    poll_interval_seconds: float,
    clock: Callable[[], datetime] | None,
    stop: _StopSignal,
    out: TextIO,
    err: TextIO,
) -> int:
    """Boucle de relais : lot après lot, recul exponentiel 1 s → 60 s après erreur.

    Un lot plein enchaîne sans attendre ; un lot vide attend ``poll_interval`` ; un
    lot interrompu (transport) ou une exception (base) attend le recul courant, qui
    double à chaque échec consécutif et retombe à 1 s au premier succès. L'arrêt
    par signal est honoré entre deux lots : la ligne en cours est validée ou non,
    jamais à moitié.
    """

    backoff = FOLLOW_BACKOFF_MIN_SECONDS
    while not stop.event.is_set():
        try:
            report = relay_once(
                session_factory,
                transport,
                consumer=consumer,
                batch_size=batch_size,
                now=clock() if clock is not None else None,
            )
        except OutboxConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 — journalisé, puis recul
            print(
                f"Relais interrompu par une erreur : {type(exc).__name__}: {exc} ; "
                f"nouvel essai dans {backoff:g} s.",
                file=err,
            )
            if stop.wait(backoff):
                break
            backoff = min(backoff * 2, FOLLOW_BACKOFF_MAX_SECONDS)
            continue
        if report.interrupted:
            print(f"{report.summary()} Nouvel essai dans {backoff:g} s.", file=err)
            if stop.wait(backoff):
                break
            backoff = min(backoff * 2, FOLLOW_BACKOFF_MAX_SECONDS)
            continue
        backoff = FOLLOW_BACKOFF_MIN_SECONDS
        if report.delivered:
            print(report.summary(), file=out)
            continue
        if stop.wait(poll_interval_seconds):
            break
    print("Relais arrêté proprement.", file=out)
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Any] | None = None,
    transport: OutboxTransport | None = None,
    clock: Callable[[], datetime] | None = None,
    stop: threading.Event | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Point d'entrée ; renvoie 0, 2 (usage/configuration) ou 3 (lot interrompu).

    ``session_factory``, ``transport``, ``clock`` et ``stop`` sont injectables pour
    les tests ; en production, ``init_db()`` est appelé d'abord et refuse un schéma
    hors version.
    """

    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = _parser()
    try:
        arguments = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit:  # pragma: no cover - argparse a déjà expliqué
        return EXIT_USAGE
    if arguments.batch_size < 1:
        print("--batch-size : au moins une ligne par lot est nécessaire.", file=err)
        return EXIT_USAGE
    if arguments.poll_interval_ms < 1:
        print("--poll-interval-ms : un délai strictement positif est attendu.", file=err)
        return EXIT_USAGE

    if session_factory is None:  # pragma: no cover - chemin de production
        from acp_database import get_session_factory, init_db
        from acp_database.schema_state import SchemaOutOfDateError

        try:
            init_db()
        except (SchemaOutOfDateError, RuntimeError) as exc:
            print(f"Démarrage refusé : {exc}", file=err)
            return EXIT_USAGE
        session_factory = get_session_factory()

    try:
        if arguments.list_dead:
            with session_factory() as db:
                rows = list_dead(db, consumer=arguments.consumer)
            if not rows:
                print(
                    f"Aucune lettre morte pour le consommateur « {arguments.consumer} ».",
                    file=out,
                )
                return EXIT_OK
            print(
                f"{len(rows)} lettre(s) morte(s) pour « {arguments.consumer} » :",
                file=out,
            )
            for row in rows:
                print(
                    f"  journal {row.journal_seq} — événement {row.event_id} — "
                    f"{row.attempts} essai(s) — {row.last_error or 'sans message'}",
                    file=out,
                )
            return EXIT_OK
        if arguments.requeue_dead:
            with session_factory() as db:
                count = requeue_dead(
                    db,
                    consumer=arguments.consumer,
                    now=clock() if clock is not None else None,
                )
            print(f"{count} lettre(s) morte(s) remise(s) en attente.", file=out)
            return EXIT_OK
        if arguments.follow:
            stop_signal = _StopSignal(stop)
            stop_signal.install()
            return follow(
                session_factory,
                transport,
                consumer=arguments.consumer,
                batch_size=arguments.batch_size,
                poll_interval_seconds=arguments.poll_interval_ms / 1000,
                clock=clock,
                stop=stop_signal,
                out=out,
                err=err,
            )
        report: RelayReport = relay_once(
            session_factory,
            transport,
            consumer=arguments.consumer,
            batch_size=arguments.batch_size,
            now=clock() if clock is not None else None,
        )
    except OutboxConfigurationError as exc:
        print(str(exc), file=err)
        return EXIT_USAGE
    print(report.summary(), file=out)
    if report.interrupted:
        print(
            "Le lot a été interrompu : les lignes restantes seront rejouées au "
            "prochain passage.",
            file=err,
        )
        return EXIT_INTERRUPTED
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - utilitaire de console
    raise SystemExit(main(sys.argv[1:]))
