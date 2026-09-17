"""Outillage de test partagé par tous les arbres de tests du dépôt.

Sans ``ACP_TEST_DATABASE_URL``, les moteurs rendus sont exactement ceux que les
suites construisaient à la main jusqu'ici (SQLite en mémoire sur ``StaticPool``,
ou fichier temporaire sur ``QueuePool`` pour les tests concurrents). Avec la
variable, chaque test reçoit un schéma PostgreSQL éphémère ``t_<hex12>`` détruit
à la fermeture : les tests d'un même lot peuvent tourner en parallèle sur une
seule base sans se voir.

Doctrine : un test PostgreSQL non configuré est **ignoré** avec une raison
explicite ; il **échoue** si ``ACP_TEST_DATABASE_REQUIRED=1`` et que la base est
injoignable, pour qu'une CI PostgreSQL ne puisse jamais passer au vert par
absence de base.
"""

from __future__ import annotations

import os
import secrets
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from . import engine as engine_module
from .models import Base
from .schema_state import VERSION_TABLE, literal_default_text

TEST_URL_ENV = "ACP_TEST_DATABASE_URL"
TEST_REQUIRED_ENV = "ACP_TEST_DATABASE_REQUIRED"
POSTGRESQL_DRIVER = "postgresql+psycopg"
SKIP_REASON = f"PostgreSQL non configuré ({TEST_URL_ENV} absent)"


def _test_url() -> str:
    return os.environ.get(TEST_URL_ENV, "").strip()


def database_backend() -> str:
    """``'sqlite'`` sans ``ACP_TEST_DATABASE_URL``, ``'postgresql'`` avec.

    Toute autre URL est refusée : la suite n'a que deux cibles, et une variable
    mal renseignée doit se voir tout de suite plutôt que produire des tests
    ignorés en silence.
    """

    url = _test_url()
    if not url:
        return "sqlite"
    try:
        driver = make_url(url).drivername
    except Exception as exc:  # ArgumentError et consorts
        raise RuntimeError(f"{TEST_URL_ENV} invalide : {exc}") from exc
    if driver != POSTGRESQL_DRIVER:
        raise RuntimeError(
            f"{TEST_URL_ENV} invalide : seule une URL {POSTGRESQL_DRIVER}:// est "
            f"acceptée (reçu « {driver} »)"
        )
    return "postgresql"


def _admin_engine(url: str):
    """Moteur d'administration en autocommit, sans pool ni délais applicatifs."""

    return create_engine(
        url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "application_name": "acp-tests-admin"},
    )


@contextmanager
def ephemeral_postgresql_schema(url: str) -> Iterator[str]:
    """Crée un schéma ``t_<hex12>`` sur une connexion d'administration, puis le détruit.

    Le ``DROP SCHEMA … CASCADE`` final tourne dans un ``finally`` : un test qui
    échoue ne laisse pas de schéma orphelin derrière lui.
    """

    schema = f"t_{secrets.token_hex(6)}"
    admin = _admin_engine(url)
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        try:
            yield schema
        finally:
            with admin.connect() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        admin.dispose()


def reset_public_schema(url: str) -> None:
    """Vide entièrement le schéma ``public`` (tests Alembic et sauvegarde).

    Destructif et réservé aux bases de test : chaque lot reçoit la sienne.
    """

    admin = _admin_engine(url)
    try:
        with admin.connect() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        admin.dispose()


@dataclass
class TestDatabase:
    """Moteur de test et sa ressource sous-jacente, à fermer explicitement.

    Utilisable comme gestionnaire de contexte ; ``close()`` dispose le moteur puis,
    sous PostgreSQL, détruit le schéma éphémère.
    """

    engine: object
    backend: str
    url: str
    schema: str | None = None
    _stack: ExitStack = field(default_factory=ExitStack, repr=False)

    def close(self) -> None:
        self.engine.dispose()
        self._stack.close()

    def __enter__(self) -> "TestDatabase":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def make_test_engine(
    tmp_path, *, concurrent: bool = False, create_schema: bool = True
) -> TestDatabase:
    """Moteur de test selon le backend configuré.

    - SQLite, ``concurrent=False`` : base mémoire partagée (``StaticPool``,
      ``check_same_thread=False``), la forme historique des tests unitaires ;
    - SQLite, ``concurrent=True`` : fichier ``tmp_path/test.db`` sur ``QueuePool``
      avec ``timeout=30``, la forme historique des tests multi-threads ;
    - PostgreSQL : schéma éphémère et moteur ``pool_size=8, max_overflow=8``
      dont le ``search_path`` est fixé au schéma, fuseau UTC, ``lock_timeout``
      10 s et ``statement_timeout`` 30 s.

    ``create_schema=False`` rend le moteur nu, pour les tests qui construisent
    eux-mêmes une base historique.
    """

    backend = database_backend()
    if backend == "sqlite":
        if concurrent:
            database_path = tmp_path / "test.db"
            url = f"sqlite+pysqlite:///{database_path.as_posix()}"
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False, "timeout": 30},
                poolclass=QueuePool,
            )
        else:
            url = "sqlite://"
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        database = TestDatabase(engine=engine, backend=backend, url=url)
    else:
        url = _test_url()
        stack = ExitStack()
        schema = stack.enter_context(ephemeral_postgresql_schema(url))
        engine = create_engine(
            url,
            pool_size=8,
            max_overflow=8,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": 5,
                "application_name": "acp-tests",
                "options": (
                    f"-csearch_path={schema} -c timezone=UTC "
                    "-c lock_timeout=10000 -c statement_timeout=30000"
                ),
            },
        )
        database = TestDatabase(
            engine=engine, backend=backend, url=url, schema=schema, _stack=stack
        )
    if create_schema:
        Base.metadata.create_all(database.engine)
    return database


def _reset_global_engine() -> None:
    if engine_module.get_engine.cache_info().currsize:
        engine_module.get_engine().dispose()
    engine_module.get_engine.cache_clear()
    engine_module.get_session_factory.cache_clear()


class _GlobalEngineTeardown:
    """Support dont l'attribut « armed », retiré par ``MonkeyPatch.undo()``, libère le moteur.

    ``monkeypatch`` n'offre pas de finaliseur ; il supprime en revanche, au
    teardown, tout attribut qu'il a créé. C'est ce retrait qui déclenche ici la
    remise à zéro du moteur global.
    """

    def __delattr__(self, name: str) -> None:
        if name == "armed":
            _reset_global_engine()
        object.__delattr__(self, name)


def point_global_engine_at(monkeypatch, url: str) -> None:
    """Fait pointer ``get_engine()`` sur ``url`` le temps du test.

    Pose ``ACP_DATABASE_URL``, vide les caches ``get_engine`` et
    ``get_session_factory``, puis, au teardown du ``monkeypatch``, dispose le
    moteur créé pendant le test, vide à nouveau les caches et laisse
    ``monkeypatch`` restaurer la variable.
    """

    _reset_global_engine()
    monkeypatch.setenv("ACP_DATABASE_URL", url)
    monkeypatch.setattr(_GlobalEngineTeardown(), "armed", True, raising=False)


def postgresql_available() -> bool:
    """Vrai si ``ACP_TEST_DATABASE_URL`` est posée et que la base répond."""

    if database_backend() != "postgresql":
        return False
    admin = _admin_engine(_test_url())
    try:
        with admin.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        admin.dispose()


def skip_or_fail_without_postgresql() -> str:
    """Ignore le test sans PostgreSQL configuré ; échoue si la base est exigée.

    Retourne l'URL de test. ``pytest.fail`` quand ``ACP_TEST_DATABASE_REQUIRED=1``
    et que la base est injoignable : la CI PostgreSQL ne doit pas pouvoir passer
    parce que son service n'a pas démarré.
    """

    if database_backend() != "postgresql":
        if os.environ.get(TEST_REQUIRED_ENV, "").strip() == "1":
            pytest.fail(
                f"{TEST_REQUIRED_ENV}=1 mais {TEST_URL_ENV} n'est pas une URL "
                "postgresql+psycopg"
            )
        pytest.skip(SKIP_REASON)
    url = _test_url()
    if not postgresql_available():
        message = f"PostgreSQL injoignable à l'URL de {TEST_URL_ENV}"
        if os.environ.get(TEST_REQUIRED_ENV, "").strip() == "1":
            pytest.fail(message)
        pytest.skip(message)
    return url


def _normalized_expression(value) -> str:
    """Compare des expressions SQL sans parenthèses, espaces ni casse.

    PostgreSQL renvoie ``((a IS NOT NULL) AND (b IS NOT NULL))`` là où le modèle
    écrit ``a IS NOT NULL AND b IS NOT NULL`` ; seule la structure compte ici.
    """

    rendered = "" if value is None else str(value)
    return "".join(rendered.lower().replace("(", "").replace(")", "").split())


def schema_inventory(engine, *, schema: str | None = None) -> dict:
    """Inventaire structurel normalisé d'une base, indépendant de l'origine du DDL.

    Tables (hors ``alembic_version``), colonnes (type compilé, nullabilité,
    valeur par défaut littérale), clé primaire, index (colonnes, unicité,
    prédicat partiel), contraintes uniques, CHECK et clés étrangères. Deux bases
    dont l'inventaire est égal se comportent de la même façon, quelle que soit la
    voie (``create_all`` ou Alembic) qui les a produites.
    """

    inspector = inspect(engine)
    dialect = engine.dialect
    where_key = f"{dialect.name}_where"
    # Les lectures groupées (``get_multi_*``) évitent une rafale de requêtes par
    # table, sensible sur un PostgreSQL distant.
    tables = sorted(
        name for name in inspector.get_table_names(schema=schema) if name != VERSION_TABLE
    )
    multi = {"schema": schema, "filter_names": tables}
    all_columns = inspector.get_multi_columns(**multi)
    all_primary_keys = inspector.get_multi_pk_constraint(**multi)
    all_indexes = inspector.get_multi_indexes(**multi)
    all_uniques = inspector.get_multi_unique_constraints(**multi)
    all_checks = inspector.get_multi_check_constraints(**multi)
    all_foreign_keys = inspector.get_multi_foreign_keys(**multi)
    inventory: dict = {}
    for table in tables:
        key = (schema, table)
        columns = {}
        for column in all_columns.get(key, ()):
            columns[column["name"]] = {
                "type": "".join(str(column["type"].compile(dialect=dialect)).upper().split()),
                "nullable": bool(column.get("nullable")),
                "default": literal_default_text(column.get("default")),
            }
        primary_key = tuple(
            (all_primary_keys.get(key) or {}).get("constrained_columns") or ()
        )
        indexes = {}
        for index in all_indexes.get(key, ()):
            options = index.get("dialect_options") or {}
            indexes[index["name"]] = {
                "columns": tuple(index.get("column_names") or ()),
                "unique": bool(index.get("unique")),
                "where": _normalized_expression(options.get(where_key)),
            }
        uniques = {
            (
                constraint.get("name"),
                tuple(constraint.get("column_names") or ()),
            )
            for constraint in all_uniques.get(key, ())
        }
        checks = {
            (constraint.get("name"), _normalized_expression(constraint.get("sqltext")))
            for constraint in all_checks.get(key, ())
        }
        foreign_keys = {
            (
                tuple(constraint.get("constrained_columns") or ()),
                constraint.get("referred_table"),
                tuple(constraint.get("referred_columns") or ()),
                tuple(sorted((constraint.get("options") or {}).items())),
            )
            for constraint in all_foreign_keys.get(key, ())
        }
        inventory[table] = {
            "columns": columns,
            "primary_key": primary_key,
            "indexes": indexes,
            "uniques": uniques,
            "checks": checks,
            "foreign_keys": foreign_keys,
        }
    return inventory
