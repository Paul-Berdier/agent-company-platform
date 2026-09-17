"""Verrous d'écriture et verrous consultatifs, par dialecte.

Sous SQLite, la sérialisation des écritures vient du verrou de fichier pris par
``BEGIN IMMEDIATE`` ; sous PostgreSQL, ``FOR UPDATE`` ne verrouille que les
lignes existantes et deux allocations concurrentes recalculent le même numéro.
Les verrous consultatifs (``pg_advisory_*``) donnent l'exclusion mutuelle que
les appelants attendaient implicitement de SQLite, sous un nom explicite.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

_SUPPORTED = ("sqlite", "postgresql")


class LockUnavailableError(RuntimeError):
    """Le verrou consultatif de session n'a pas pu être pris dans le délai."""


def write_lock(db: Session, key: str) -> None:
    """Prend le verrou d'écriture qui sérialise les publications concurrentes.

    Sous SQLite, ``key`` est sans objet : le verrou porte sur toute la base.
    Deux raisons, toutes deux propres à ``pysqlite``, imposent un ``BEGIN
    IMMEDIATE`` explicite avant tout point de sauvegarde :

    1. le pilote n'émet ``BEGIN`` que devant une écriture ; un ``SAVEPOINT`` posé
       en premier ouvrirait lui-même la transaction et son ``RELEASE`` la
       **validerait** — l'appelant qui a passé ``commit=False`` perdrait le
       contrôle de sa transaction ;
    2. une transaction *différée* prendrait un verrou partagé à la lecture puis
       tenterait de l'élever à l'écriture : deux publications simultanées se
       bloqueraient mutuellement (``database is locked``, sans attente possible).

    ``BEGIN IMMEDIATE`` règle les deux : le verrou d'écriture est pris d'emblée,
    les publications se sérialisent et l'appelant conserve sa transaction. Il
    n'est émis que si le pilote n'est pas déjà en transaction.

    Sous PostgreSQL, ``pg_advisory_xact_lock(hashtext(key))`` bloque jusqu'à
    obtention et se libère avec la transaction de la session (commit ou
    rollback) : aucune libération explicite n'est possible ni nécessaire.
    """

    connection = db.connection()
    dialect = connection.dialect.name
    if dialect == "sqlite":
        driver_connection = getattr(connection.connection, "driver_connection", None)
        if driver_connection is None or getattr(
            driver_connection, "in_transaction", False
        ):
            return
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        return
    if dialect == "postgresql":
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key}
        )
        return
    raise RuntimeError(
        f"write_lock : dialecte « {dialect} » non pris en charge "
        f"(attendu : {', '.join(_SUPPORTED)})"
    )


@contextmanager
def advisory_session_lock(
    connection: Connection, key: str, *, timeout_seconds: float
) -> Iterator[None]:
    """Verrou consultatif de **session**, pour les opérations hors transaction.

    Destiné aux opérations de maintenance (migration, sauvegarde, rétention) qui
    enchaînent plusieurs transactions : un verrou de transaction tomberait au
    premier commit. Sous PostgreSQL, ``pg_try_advisory_lock`` est tenté en boucle
    jusqu'à ``timeout_seconds`` puis :class:`LockUnavailableError` est levée ; le
    verrou est rendu par ``pg_advisory_unlock`` dans un ``finally``.

    La connexion ne doit porter aucune transaction en cours : les instructions de
    verrouillage sont validées immédiatement pour laisser l'appelant démarrer ses
    propres transactions (Alembic en ouvre une par révision). Une transaction
    encore ouverte à la sortie est annulée avant la libération, car un commit
    implicite ici validerait un travail que l'appelant n'a pas confirmé.

    Sous SQLite le gestionnaire ne fait rien : le fichier lui-même sérialise les
    écrivains. Tout autre dialecte est refusé.
    """

    dialect = connection.dialect.name
    if dialect == "sqlite":
        yield
        return
    if dialect != "postgresql":
        raise RuntimeError(
            f"advisory_session_lock : dialecte « {dialect} » non pris en charge "
            f"(attendu : {', '.join(_SUPPORTED)})"
        )
    if timeout_seconds < 0:
        raise RuntimeError("advisory_session_lock : délai négatif refusé")
    if connection.in_transaction():
        raise RuntimeError(
            "advisory_session_lock : la connexion porte déjà une transaction ; "
            "validez-la ou annulez-la avant de demander un verrou de session"
        )
    deadline = time.monotonic() + timeout_seconds
    while True:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": key}
        ).scalar_one()
        connection.commit()
        if acquired:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LockUnavailableError(
                f"Verrou « {key} » indisponible après {timeout_seconds:g} s : "
                "une autre session le détient (migration ou maintenance en cours)"
            )
        time.sleep(min(0.1, remaining))
    try:
        yield
    finally:
        if connection.in_transaction():
            connection.rollback()
        connection.execute(
            text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": key}
        )
        connection.commit()
