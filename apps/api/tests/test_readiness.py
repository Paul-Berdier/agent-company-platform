"""Readiness (``/ready``), démarrage fermé, erreurs base traduites et seed gardé.

Les tests SQLite pointent le moteur global sur un fichier temporaire, comme le
ferait un déploiement local ; les tests ``postgres`` remettent le schéma
``public`` de la base du lot à zéro et prouvent le refus sur base vide, puis la
readiness après ``run_upgrade``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from acp_api import db_errors, readiness
from acp_api import seed as seed_module
from acp_api.main import app
from acp_api.preview import create_preview_app
from acp_database import engine as engine_module
from acp_database import get_engine, init_db
from acp_database.migrate import run_upgrade
from acp_database.models import (
    EventModel,
    EventOutboxModel,
    OrganizationModel,
    ProviderModel,
)
from acp_database.schema_state import (
    VERSION_TABLE,
    SchemaOutOfDateError,
    head_revision,
)
from acp_database.testing import (
    make_test_engine,
    point_global_engine_at,
    reset_public_schema,
    skip_or_fail_without_postgresql,
)

READINESS_ENV = (
    "ACP_ARTIFACT_STORAGE_DIR",
    "ACP_SKILLS_STORAGE_DIR",
    "ACP_EVENT_RELAY_ENABLED",
    "ACP_READY_MIGRATION_CACHE_SECONDS",
    "ACP_ALLOW_SEED",
)
CHECK_NAMES = {"database", "migrations", "artifact_storage", "skills_storage", "outbox"}


@pytest.fixture
def clean_environ(monkeypatch):
    for name in READINESS_ENV:
        monkeypatch.delenv(name, raising=False)
    readiness.clear_migration_cache()
    yield
    readiness.clear_migration_cache()


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch, clean_environ):
    """Moteur global sur un fichier SQLite du test ; l'URL contient ``tmp_path``."""

    url = f"sqlite:///{(tmp_path / 'ready.db').as_posix()}"
    point_global_engine_at(monkeypatch, url)
    return url


@pytest.fixture
def client(sqlite_url):
    with TestClient(app) as api_client:
        yield api_client


def _assert_no_leak(body: str, tmp_path, url: str) -> None:
    assert str(tmp_path) not in body
    assert tmp_path.as_posix() not in body
    assert url not in body
    assert "sqlite:///" not in body


# --- /ready sous SQLite ------------------------------------------------------


def test_ready_reports_every_check_and_never_caches(client, tmp_path, sqlite_url):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "api"
    checks = body["checks"]
    assert set(checks) == CHECK_NAMES
    for check in checks.values():
        assert check["ok"] is True
        assert isinstance(check["reason"], str) and check["reason"]
    assert checks["database"]["dialect"] == "sqlite"
    assert isinstance(checks["database"]["latency_ms"], (int, float))
    assert checks["migrations"]["current"] == head_revision()
    assert checks["migrations"]["head"] == head_revision()
    # La sonde de démarrage a déjà vérifié le schéma : la première requête sert
    # ce verdict mémorisé.
    assert checks["migrations"]["cached"] is True
    assert checks["artifact_storage"] == {
        "ok": True,
        "reason": "non configuré : repli sur ./acp-data, non persistant hors poste de "
        "développement",
        "configured": False,
    }
    assert checks["skills_storage"]["configured"] is False
    assert checks["outbox"]["enabled"] is False
    _assert_no_leak(response.text, tmp_path, sqlite_url)


def test_health_stays_a_pure_liveness(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_ready_degrades_when_a_storage_root_is_a_file(
    client, tmp_path, monkeypatch, sqlite_url
):
    blocked = tmp_path / "artifacts-as-file"
    blocked.write_text("pas un répertoire", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setenv("ACP_ARTIFACT_STORAGE_DIR", str(blocked))
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(skills))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "degraded"
    artifact = body["checks"]["artifact_storage"]
    assert artifact["ok"] is False
    assert artifact["configured"] is True
    assert "non inscriptible" in artifact["reason"]
    assert body["checks"]["skills_storage"]["ok"] is True
    assert not list(skills.glob(".acp-ready-*"))
    assert blocked.read_text(encoding="utf-8") == "pas un répertoire"
    _assert_no_leak(response.text, tmp_path, sqlite_url)


def test_ready_never_recreates_a_root_that_disappeared(
    client, tmp_path, monkeypatch, sqlite_url
):
    # Avant 0.9.1, la sonde créait la racine manquante : un volume démonté passait
    # pour sain, et les livrables suivants partaient sur la couche éphémère.
    missing = tmp_path / "volume" / "artifacts"
    monkeypatch.setenv("ACP_ARTIFACT_STORAGE_DIR", str(missing))

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    artifact = body["checks"]["artifact_storage"]
    assert artifact == {
        "ok": False,
        "reason": "racine absente : volume démonté ou répertoire supprimé depuis le "
        "démarrage",
        "configured": True,
    }
    assert not missing.exists()
    assert not missing.parent.exists()
    _assert_no_leak(response.text, tmp_path, sqlite_url)


def test_startup_initialises_the_configured_roots(sqlite_url, tmp_path, monkeypatch):
    artifacts = tmp_path / "donnees" / "artifacts"
    skills = tmp_path / "donnees" / "skills"
    monkeypatch.setenv("ACP_ARTIFACT_STORAGE_DIR", str(artifacts))
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(skills))

    with TestClient(app) as api_client:
        assert artifacts.is_dir() and skills.is_dir()
        response = api_client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["artifact_storage"]["reason"] == "racine inscriptible"
    assert not list(artifacts.glob(".acp-ready-*"))


def test_ready_degrades_when_alembic_version_is_missing(client, monkeypatch):
    monkeypatch.setenv("ACP_READY_MIGRATION_CACHE_SECONDS", "0")
    assert client.get("/ready").status_code == 200

    with get_engine().begin() as connection:
        connection.execute(text(f"DROP TABLE {VERSION_TABLE}"))

    response = client.get("/ready")

    assert response.status_code == 503
    migrations = response.json()["checks"]["migrations"]
    assert migrations["ok"] is False
    assert migrations["current"] is None
    assert migrations["head"] == head_revision()
    assert "migrate upgrade" in migrations["reason"]
    assert response.json()["checks"]["database"]["ok"] is True


def test_ready_caches_only_a_current_schema_verdict(client):
    readiness.clear_migration_cache()
    first = client.get("/ready").json()["checks"]["migrations"]
    assert first["cached"] is False

    with get_engine().begin() as connection:
        connection.execute(text(f"DROP TABLE {VERSION_TABLE}"))

    cached = client.get("/ready")
    assert cached.status_code == 200
    assert cached.json()["checks"]["migrations"]["cached"] is True

    readiness.clear_migration_cache()
    degraded = client.get("/ready")
    assert degraded.status_code == 503
    assert degraded.json()["checks"]["migrations"]["cached"] is False

    # Un verdict négatif n'est pas mémorisé : la sonde suivante revérifie.
    assert client.get("/ready").status_code == 503


def test_ready_outbox_counts_are_informational(client, monkeypatch):
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        pending_event = EventModel(type="readiness.pending")
        dead_event = EventModel(type="readiness.dead")
        db.add_all([pending_event, dead_event])
        db.flush()
        db.add_all(
            [
                EventOutboxModel(
                    event_id=pending_event.id, journal_seq=1, next_attempt_at=now
                ),
                EventOutboxModel(
                    event_id=dead_event.id,
                    journal_seq=2,
                    next_attempt_at=now,
                    dead_at=now,
                    last_error="abandon",
                ),
            ]
        )
        db.commit()

    response = client.get("/ready")

    assert response.status_code == 200
    outbox = response.json()["checks"]["outbox"]
    assert outbox == {
        "ok": True,
        "reason": "1 événement(s) en attente, 1 en lettre morte",
        "enabled": True,
        "pending": 1,
        "dead": 1,
    }


def test_ready_reports_an_unreachable_database_once(tmp_path, clean_environ):
    engine = engine_module.make_engine(
        f"sqlite:///{(tmp_path / 'absent' / 'nested' / 'ready.db').as_posix()}"
    )
    try:
        report = readiness.build_report(
            engine=engine, environ={"ACP_EVENT_RELAY_ENABLED": "1"}
        )
    finally:
        engine.dispose()

    assert report.ready is False
    assert report.failed() == ["database", "migrations"]
    assert report.checks["database"].ok is False
    assert report.checks["migrations"].reason == "non vérifié : base injoignable"
    assert report.checks["outbox"].ok is True
    assert report.checks["outbox"].reason == "non vérifié : base injoignable"
    assert str(tmp_path) not in str(report.payload(service="api"))


def test_migration_cache_setting_is_validated():
    assert readiness.migration_cache_seconds({}) == 30
    assert readiness.migration_cache_seconds({"ACP_READY_MIGRATION_CACHE_SECONDS": "0"}) == 0
    with pytest.raises(RuntimeError, match="ACP_READY_MIGRATION_CACHE_SECONDS"):
        readiness.migration_cache_seconds({"ACP_READY_MIGRATION_CACHE_SECONDS": "abc"})
    with pytest.raises(RuntimeError, match="négatif"):
        readiness.migration_cache_seconds({"ACP_READY_MIGRATION_CACHE_SECONDS": "-1"})


# --- démarrage fermé ---------------------------------------------------------


def test_startup_refuses_an_unwritable_configured_storage(
    sqlite_url, tmp_path, monkeypatch
):
    blocked = tmp_path / "skills-as-file"
    blocked.write_text("occupé", encoding="utf-8")
    monkeypatch.setenv("ACP_SKILLS_STORAGE_DIR", str(blocked))

    with pytest.raises(RuntimeError, match="Démarrage refusé") as error:
        with TestClient(app):
            pass

    message = str(error.value)
    assert "skills_storage" in message
    assert "artifact_storage" not in message
    assert str(tmp_path) not in message


def test_startup_refuses_an_invalid_cache_setting(sqlite_url, monkeypatch):
    monkeypatch.setenv("ACP_READY_MIGRATION_CACHE_SECONDS", "trente")

    with pytest.raises(RuntimeError, match="ACP_READY_MIGRATION_CACHE_SECONDS"):
        with TestClient(app):
            pass


def test_startup_translates_a_driver_error_into_a_french_runtime_error(
    sqlite_url, monkeypatch
):
    def unreachable() -> None:
        raise OperationalError("SELECT secret", {}, Exception("hôte confidentiel"))

    monkeypatch.setattr(readiness, "init_db", unreachable)

    with pytest.raises(RuntimeError, match="injoignable") as error:
        with TestClient(app):
            pass

    assert "secret" not in str(error.value)
    assert "confidentiel" not in str(error.value)
    assert isinstance(error.value.__cause__, OperationalError)


def test_preview_app_serves_ready_with_its_own_service_name(sqlite_url, tmp_path):
    preview = create_preview_app({"ACP_CORS_ORIGINS": "https://app.example.test"})

    with TestClient(preview) as preview_client:
        response = preview_client.get("/ready")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["service"] == "artifact-preview"
    assert response.json()["status"] == "ready"
    assert str(tmp_path) not in response.text


# --- db_errors ---------------------------------------------------------------


class _FakeOrig(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("détail pilote confidentiel")
        self.sqlstate = sqlstate


def _failing_app(sqlstate: str | None) -> FastAPI:
    application = FastAPI()
    db_errors.install(application)

    @application.get("/boom")
    def boom() -> dict[str, str]:
        raise OperationalError(
            "SELECT * FROM secrets WHERE key = %(key)s",
            {"key": "valeur-privée"},
            _FakeOrig(sqlstate),
        )

    return application


@pytest.mark.parametrize(
    ("sqlstate", "message"),
    [
        ("55P03", "Ressource temporairement verrouillée, réessayez"),
        ("57014", "Requête interrompue par le délai maximal"),
    ],
)
def test_lock_and_timeout_errors_become_503_without_sql(sqlstate, message):
    with TestClient(_failing_app(sqlstate)) as failing:
        response = failing.get("/boom")

    assert response.status_code == 503
    assert response.json() == {"detail": message}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "1"
    assert "secrets" not in response.text
    assert "valeur-privée" not in response.text
    assert "confidentiel" not in response.text


@pytest.mark.parametrize("sqlstate", [None, "23505", "08006"])
def test_other_operational_errors_are_re_raised(sqlstate):
    with TestClient(_failing_app(sqlstate)) as failing:
        with pytest.raises(OperationalError):
            failing.get("/boom")


def test_sqlstate_extraction_ignores_missing_or_non_text_values():
    assert db_errors.sqlstate_of(OperationalError("x", {}, _FakeOrig("55P03"))) == "55P03"
    assert db_errors.sqlstate_of(OperationalError("x", {}, Exception("sans état"))) is None
    assert db_errors.sqlstate_of(OperationalError("x", {}, _FakeOrig(None))) is None
    assert db_errors.sqlstate_of(RuntimeError("pas une erreur base")) is None


def test_handlers_are_installed_on_both_applications():
    preview = create_preview_app({})
    assert OperationalError in app.exception_handlers
    assert OperationalError in preview.exception_handlers


# --- seed --------------------------------------------------------------------


def test_seed_is_idempotent_on_sqlite(sqlite_url, capsys):
    assert seed_module.seed() is True
    assert seed_module.seed() is False
    assert seed_module.main() == 0
    assert "déjà présent" in capsys.readouterr().out
    with Session(get_engine()) as db:
        organizations = db.scalars(select(OrganizationModel)).all()
        providers = db.scalars(select(ProviderModel)).all()
    assert [organization.name for organization in organizations] == ["Virtual Company"]
    assert len(providers) == len(seed_module.PROVIDERS)


def test_seed_refuses_a_non_sqlite_database_before_opening_a_session(
    monkeypatch, capsys, clean_environ
):
    monkeypatch.setattr(seed_module, "init_db", lambda: None)
    monkeypatch.setattr(
        seed_module,
        "get_engine",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(
        seed_module,
        "get_session_factory",
        lambda: (_ for _ in ()).throw(AssertionError("aucune session ne doit s'ouvrir")),
    )

    with pytest.raises(seed_module.SeedRefusedError, match="ACP_ALLOW_SEED=1"):
        seed_module.seed()
    with pytest.raises(seed_module.SeedRefusedError):
        seed_module.seed({"ACP_ALLOW_SEED": "0"})

    assert seed_module.main() == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Refus : Seed de démonstration refusé sur une base « postgresql »" in captured.err


def test_seed_cli_reports_a_schema_refusal_with_exit_code_3(monkeypatch, capsys):
    def out_of_date() -> None:
        raise SchemaOutOfDateError(
            SimpleNamespace(current=None, head="0002_event_outbox")
        )

    monkeypatch.setattr(seed_module, "init_db", out_of_date)

    assert seed_module.main() == 3
    assert "hors version" in capsys.readouterr().err


# --- PostgreSQL --------------------------------------------------------------


@pytest.fixture
def postgresql_url(clean_environ):
    """URL de la base du lot, schéma ``public`` vidé avant et après le test."""

    url = skip_or_fail_without_postgresql()
    reset_public_schema(url)
    yield url
    reset_public_schema(url)


@pytest.mark.postgres
def test_pg_empty_database_is_degraded_without_starting_an_app(postgresql_url):
    engine = engine_module.make_engine(postgresql_url)
    try:
        report = readiness.build_report(engine=engine, environ={})
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()

    assert report.ready is False
    assert report.failed() == ["migrations"]
    assert report.checks["database"].ok is True
    assert report.checks["database"].details["dialect"] == "postgresql"
    migrations = report.checks["migrations"]
    assert migrations.details["current"] is None
    assert migrations.details["head"] == head_revision()
    assert report.status_code == 503
    assert "acp:acp" not in str(report.payload(service="api"))


@pytest.mark.postgres
def test_pg_startup_refuses_an_unmigrated_database_without_creating_tables(
    postgresql_url, monkeypatch
):
    point_global_engine_at(monkeypatch, postgresql_url)

    with pytest.raises(SchemaOutOfDateError, match="hors version") as error:
        init_db()
    assert isinstance(error.value, RuntimeError)

    with pytest.raises(RuntimeError, match="révision attendue") as startup_error:
        with TestClient(app):
            pass
    assert not isinstance(startup_error.value, SystemExit)
    assert "acp:acp" not in str(startup_error.value)

    assert inspect(get_engine()).get_table_names() == []


@pytest.mark.postgres
def test_pg_ready_after_upgrade_and_seed_is_gated(postgresql_url, monkeypatch):
    maintenance = engine_module.make_engine(postgresql_url, maintenance=True)
    try:
        run_upgrade(maintenance)
    finally:
        maintenance.dispose()
    point_global_engine_at(monkeypatch, postgresql_url)

    with pytest.raises(seed_module.SeedRefusedError, match="postgresql"):
        seed_module.seed()
    monkeypatch.setenv("ACP_ALLOW_SEED", "1")
    assert seed_module.seed() is True
    assert seed_module.seed() is False
    monkeypatch.delenv("ACP_ALLOW_SEED")

    with TestClient(app) as api_client:
        response = api_client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["dialect"] == "postgresql"
    assert body["checks"]["migrations"]["current"] == head_revision()
    assert "acp:acp" not in response.text
    with Session(get_engine()) as db:
        assert db.scalar(select(OrganizationModel.name)) == "Virtual Company"


@pytest.mark.postgres
def test_pg_lock_timeout_and_statement_timeout_become_503(tmp_path, clean_environ):
    skip_or_fail_without_postgresql()
    with make_test_engine(tmp_path) as database:
        engine = database.engine
        with Session(engine) as db:
            db.add(OrganizationModel(name="verrouillée"))
            db.commit()
        application = FastAPI()
        db_errors.install(application)

        def get_db():
            with Session(engine) as db:
                yield db

        @application.get("/locked")
        def locked(db: Session = Depends(get_db)) -> dict[str, str]:
            db.execute(text("SET LOCAL lock_timeout = 100"))
            db.execute(
                select(OrganizationModel).where(
                    OrganizationModel.name == "verrouillée"
                ).with_for_update()
            ).scalar_one()
            return {"status": "impossible"}

        @application.get("/slow")
        def slow(db: Session = Depends(get_db)) -> dict[str, str]:
            db.execute(text("SET LOCAL statement_timeout = 100"))
            db.execute(text("SELECT pg_sleep(2)"))
            return {"status": "impossible"}

        holder = engine.connect()
        try:
            holder.begin()
            holder.execute(
                select(OrganizationModel)
                .where(OrganizationModel.name == "verrouillée")
                .with_for_update()
            ).scalar_one()
            with TestClient(application) as client:
                blocked = client.get("/locked")
                timed_out = client.get("/slow")
        finally:
            holder.rollback()
            holder.close()

    assert blocked.status_code == 503
    assert blocked.json() == {"detail": "Ressource temporairement verrouillée, réessayez"}
    assert "organizations" not in blocked.text
    assert timed_out.status_code == 503
    assert timed_out.json() == {"detail": "Requête interrompue par le délai maximal"}
    assert "pg_sleep" not in timed_out.text


@pytest.mark.postgres
def test_pg_readiness_probe_is_bounded_by_a_local_statement_timeout(
    tmp_path, clean_environ
):
    skip_or_fail_without_postgresql()
    statements: list[str] = []
    with make_test_engine(tmp_path, create_schema=False) as database:
        @event.listens_for(database.engine, "before_cursor_execute")
        def _capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        report = readiness.build_report(engine=database.engine, environ={})

    assert report.checks["database"].ok is True
    assert any("SET LOCAL statement_timeout = 2000" in s for s in statements)
    # Schéma éphémère vide : la base répond mais n'est pas migrée.
    assert report.checks["migrations"].ok is False
