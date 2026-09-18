"""Fixtures communes de l'API : base du ``lifespan`` et adaptation du test Pixel legacy.

Le ``lifespan`` de ``acp_api.main:app`` appelle ``init_db()`` sur le moteur global
(``ACP_DATABASE_URL``) à chaque ``TestClient(app)``. Sans réglage, ce moteur
pointerait sur ``./acp.db``, la base de travail du poste : une suite de tests ne
doit jamais la toucher. La fixture de session ci-dessous lui donne une base à lui :

- sans ``ACP_TEST_DATABASE_URL`` : un fichier SQLite de ``tmp_path_factory`` ;
- avec la variable : un schéma PostgreSQL éphémère de session (``t_<hex12>``,
  détruit à la fin), migré par Alembic, distinct du schéma ``public`` que les tests
  marqués ``postgres`` remettent à zéro à leur guise.

Sous PostgreSQL, le moteur global ne connaît pas ce schéma : ``make_engine`` fixe
lui-même l'option ``options`` de la connexion, qui écraserait un ``search_path``
passé dans l'URL. Le ``search_path`` est donc posé à l'ouverture de chaque
connexion du moteur global, et un test qui reconstruit ce moteur
(``point_global_engine_at``, ``cache_clear``) le retrouve armé au test suivant.
"""

from __future__ import annotations

import os
import weakref
from uuid import uuid4

import pytest
from sqlalchemy import event

from acp_database import engine as engine_module
from acp_database.migrate import run_upgrade
from acp_database.testing import database_backend, make_test_engine

# Moteurs armés par la session : clé faible, un moteur disposé n'y laisse rien.
_ARMED: "weakref.WeakKeyDictionary[object, str]" = weakref.WeakKeyDictionary()


class LifespanDatabase:
    """Base réservée au moteur global de l'application pendant la session."""

    def __init__(self, url: str, schema: str | None) -> None:
        self.url = url
        self.schema = schema

    def _bind_search_path(self, engine) -> None:
        schema = self.schema
        if schema is None:
            return

        @event.listens_for(engine, "connect")
        def _search_path(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f'SET search_path TO "{schema}"')
            finally:
                cursor.close()
            # ``SET`` est transactionnel : sans validation, le retour au pool
            # (``rollback``) le défait et la connexion retomberait sur ``public``.
            dbapi_connection.commit()

    def arm(self) -> None:
        """Garantit que ``get_engine()`` rend un moteur de cette base, prêt à l'emploi.

        Un moteur étranger encore en cache (test qui a pointé le moteur global
        ailleurs sans le rendre) est disposé et remplacé ; un moteur déjà armé est
        conservé avec son pool.
        """

        if os.environ.get("ACP_DATABASE_URL") != self.url:
            raise RuntimeError(
                "ACP_DATABASE_URL a été modifiée hors monkeypatch : la base du "
                "lifespan des tests n'est plus celle de la session"
            )
        if engine_module.get_engine.cache_info().currsize:
            cached = engine_module.get_engine()
            if _ARMED.get(cached) == self.url:
                return
            cached.dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()
        engine = engine_module.get_engine()
        self._bind_search_path(engine)
        _ARMED[engine] = self.url

    def release(self) -> None:
        if engine_module.get_engine.cache_info().currsize:
            engine_module.get_engine().dispose()
        engine_module.get_engine.cache_clear()
        engine_module.get_session_factory.cache_clear()


@pytest.fixture(scope="session")
def lifespan_database(tmp_path_factory) -> LifespanDatabase:
    """Pose ``ACP_DATABASE_URL`` pour toute la session et prépare la base visée."""

    monkeypatch = pytest.MonkeyPatch()
    backend = database_backend()
    if backend == "sqlite":
        root = tmp_path_factory.mktemp("lifespan")
        url = f"sqlite:///{(root / 'lifespan.db').as_posix()}"
        monkeypatch.setenv("ACP_DATABASE_URL", url)
        database = LifespanDatabase(url, None)
        try:
            database.arm()
            yield database
        finally:
            database.release()
            monkeypatch.undo()
        return

    # PostgreSQL : schéma éphémère de session, migré par la chaîne Alembic (le
    # ``init_db()`` du lifespan refuse toute base hors version et ne crée rien).
    with make_test_engine(
        tmp_path_factory.mktemp("lifespan"), concurrent=True, create_schema=False
    ) as test_database:
        run_upgrade(test_database.engine)
        test_database.engine.dispose()
        monkeypatch.setenv("ACP_DATABASE_URL", test_database.url)
        database = LifespanDatabase(test_database.url, test_database.schema)
        try:
            database.arm()
            yield database
        finally:
            database.release()
            monkeypatch.undo()


@pytest.fixture(autouse=True)
def _lifespan_engine(lifespan_database: LifespanDatabase) -> LifespanDatabase:
    """Réarme le moteur global avant chaque test de l'API.

    Un test qui a pointé le moteur ailleurs (``point_global_engine_at``) l'a rendu
    au teardown de son ``monkeypatch`` ; le suivant repart d'un moteur de la base de
    session, jamais d'un moteur périmé ni de ``./acp.db``.
    """

    lifespan_database.arm()
    return lifespan_database


@pytest.fixture(autouse=True)
def authenticate_legacy_office_test(request, _lifespan_engine):
    """Injecte un owner uniquement dans l'ancien test Pixel déjà présent.

    Les suites auth/RBAC utilisent les vraies sessions. Cette adaptation isolée
    évite de modifier le fichier Pixel localement enrichi par l'utilisateur. Le
    propriétaire est écrit dans la base du lifespan, celle que ``TestClient(app)``
    initialise et que ses routes servent sans surcharge de ``get_db``.
    """

    if request.node.path.name != "test_office_config.py":
        yield
        return

    from acp_api.deps import get_principal
    from acp_api.main import app
    from acp_api.security import hash_password
    from acp_database import get_session_factory, init_db
    from acp_database.models import UserModel

    init_db()
    with get_session_factory()() as db:
        owner = UserModel(
            login_normalized=f"legacy-office-{uuid4().hex}",
            display_name="Test office legacy",
            password_hash=hash_password("legacy office test password"),
            platform_role="owner",
        )
        db.add(owner)
        db.commit()
        owner_id = owner.id

    app.dependency_overrides[get_principal] = lambda: owner_id
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_principal, None)
