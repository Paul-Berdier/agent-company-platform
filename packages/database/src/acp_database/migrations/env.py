"""Environnement Alembic : la connexion vient d'``acp_database``, jamais d'un ini.

Trois chemins d'exécution :

- ``acp_database.migrate`` fournit une connexion déjà verrouillée dans
  ``config.attributes["connection"]`` ;
- la commande ``alembic`` native lit ``ACP_DATABASE_URL`` et construit un moteur
  de maintenance (sans ``statement_timeout``, car un ``CREATE INDEX`` sur une
  grosse table dépasse légitimement le délai des requêtes applicatives) ;
- le mode hors ligne (``--sql``) rend le DDL sans se connecter.
"""

from __future__ import annotations

import os

from alembic import context

from acp_database.engine import make_engine
from acp_database.models import Base
from acp_database.schema_state import VERSION_TABLE, autogenerate_options

config = context.config
target_metadata = Base.metadata


def _resolve_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get(
        "ACP_DATABASE_URL", ""
    )
    if not url:
        raise RuntimeError(
            "Aucune URL de base : renseignez ACP_DATABASE_URL, ou passez "
            "--database-url à « python -m acp_database.migrate »."
        )
    return url


def _configure(*, connection=None, url: str | None = None, dialect_name: str) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        transaction_per_migration=True,
        # Seul SQLite exige le mode « batch » (recréation de table) pour ALTER.
        render_as_batch=dialect_name == "sqlite",
        literal_binds=connection is None,
        **autogenerate_options(),
    )


def run_migrations_offline() -> None:
    """Rend le DDL sur la sortie standard, sans connexion."""

    url = _resolve_url()
    dialect_name = url.split(":", 1)[0].split("+", 1)[0]
    _configure(url=url, dialect_name=dialect_name)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    _configure(connection=connection, dialect_name=connection.dialect.name)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécute les révisions sur la connexion fournie ou sur un moteur dédié."""

    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(_resolve_url(), maintenance=True)
    try:
        with engine.connect() as owned_connection:
            _run(owned_connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
