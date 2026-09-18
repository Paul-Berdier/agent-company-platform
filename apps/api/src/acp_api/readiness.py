"""Contrôles de readiness partagés par l'API et l'aperçu (``GET /ready``).

``/health`` reste une liveness pure : elle dit seulement que le processus répond.
``/ready`` dit si le service peut rendre service **maintenant** : base joignable,
schéma à la révision attendue, racines de stockage inscriptibles quand elles sont
configurées et, à titre informatif seulement, l'état de la boîte d'envoi des
événements.

Le même rapport sert au démarrage (:func:`assert_ready_at_startup`) : un service
qui échouerait à sa propre sonde ne démarre pas, plutôt que d'être mis en ligne
puis retiré par l'orchestrateur après des requêtes déjà perdues.

Doctrine : chaque contrôle porte un ``ok`` et une ``reason`` courte en français ;
aucun chemin absolu, aucune URL de base ni aucun secret n'est publié, car
``/ready`` est public comme ``/health``.
"""

from __future__ import annotations

import os
import secrets
import time
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from acp_database import get_engine, init_db
from acp_database.models import EventOutboxModel
from acp_database.schema_state import SchemaState, check_schema_current

from .artifacts_storage import ARTIFACT_STORAGE_DIR_ENV

SKILLS_STORAGE_DIR_ENV = "ACP_SKILLS_STORAGE_DIR"
RELAY_ENABLED_ENV = "ACP_EVENT_RELAY_ENABLED"
MIGRATION_CACHE_ENV = "ACP_READY_MIGRATION_CACHE_SECONDS"
DEFAULT_MIGRATION_CACHE_SECONDS = 30
DATABASE_PROBE_TIMEOUT_MS = 2000
PROBE_PREFIX = ".acp-ready-"

# Contrôles dont l'échec rend le service « degraded » (503) et refuse le démarrage.
# ``outbox`` n'en fait pas partie : un arriéré de livraison est une information
# d'exploitation, pas une raison de retirer l'API du trafic.
BLOCKING_CHECKS = ("database", "migrations", "artifact_storage", "skills_storage")

STATUS_READY = "ready"
STATUS_DEGRADED = "degraded"


@dataclass(frozen=True)
class CheckResult:
    """Résultat d'un contrôle : verdict, raison courte et détails publiables."""

    ok: bool
    reason: str
    details: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"ok": self.ok, "reason": self.reason}
        payload.update(self.details)
        return payload


@dataclass(frozen=True)
class ReadinessReport:
    """Rapport complet ; ``ready`` ne dépend que des contrôles bloquants."""

    checks: Mapping[str, CheckResult]

    @property
    def ready(self) -> bool:
        return not self.failed()

    def failed(self) -> list[str]:
        """Noms des contrôles bloquants en échec, dans l'ordre de ``BLOCKING_CHECKS``."""

        return [
            name
            for name in BLOCKING_CHECKS
            if name in self.checks and not self.checks[name].ok
        ]

    def payload(self, *, service: str) -> dict[str, object]:
        """Corps JSON de ``/ready`` : statut global, service et détail des contrôles."""

        return {
            "status": STATUS_READY if self.ready else STATUS_DEGRADED,
            "service": service,
            "checks": {name: check.as_dict() for name, check in self.checks.items()},
        }

    @property
    def status_code(self) -> int:
        return 200 if self.ready else 503


# --- cache du contrôle de migrations -----------------------------------------

# Clé faible : un moteur remplacé (tests, ``get_engine.cache_clear``) emporte son
# entrée avec lui, sans qu'un identifiant réutilisé puisse resservir un verdict.
_migration_cache: "weakref.WeakKeyDictionary[object, tuple[float, SchemaState]]" = (
    weakref.WeakKeyDictionary()
)


def clear_migration_cache() -> None:
    """Oublie les verdicts de migration mémorisés (tests et outillage)."""

    _migration_cache.clear()


def migration_cache_seconds(environ: Mapping[str, str]) -> int:
    """Durée de validité d'un verdict « schéma à jour », en secondes.

    ``0`` désactive le cache. Une valeur non entière ou négative est refusée
    plutôt que remplacée par le défaut : l'opérateur qui l'a réglée doit voir son
    erreur, et :func:`assert_ready_at_startup` la lui montre avant tout trafic.
    """

    raw = environ.get(MIGRATION_CACHE_ENV, "")
    if not raw.strip():
        return DEFAULT_MIGRATION_CACHE_SECONDS
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(
            f"Variable {MIGRATION_CACHE_ENV} invalide : « {raw} » n'est pas un entier"
        ) from exc
    if value < 0:
        raise RuntimeError(
            f"Variable {MIGRATION_CACHE_ENV} invalide : {value} est négatif"
        )
    return value


# --- contrôles ---------------------------------------------------------------


def _database_check(engine) -> CheckResult:
    """``SELECT 1`` chronométré ; sous PostgreSQL, borné par un ``statement_timeout`` local.

    Le délai local est plus court que celui du moteur applicatif : une sonde ne
    doit pas rester suspendue sur une base saturée, sinon l'orchestrateur ne voit
    rien avant son propre délai et la dégradation reste invisible.
    """

    started = time.perf_counter()
    dialect = engine.dialect.name
    try:
        with engine.connect() as connection:
            if dialect == "postgresql":
                with connection.begin():
                    connection.execute(
                        text(f"SET LOCAL statement_timeout = {DATABASE_PROBE_TIMEOUT_MS}")
                    )
                    connection.execute(text("SELECT 1")).scalar_one()
            else:
                connection.execute(text("SELECT 1")).scalar_one()
    except (SQLAlchemyError, OSError) as exc:
        return CheckResult(
            False,
            "base injoignable ou sans réponse dans le délai de la sonde",
            {"dialect": dialect, "error": type(exc).__name__},
        )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return CheckResult(
        True, "base joignable", {"dialect": dialect, "latency_ms": latency_ms}
    )


def _migrations_check(
    engine, environ: Mapping[str, str], *, database_ok: bool
) -> CheckResult:
    """Compare la révision estampillée à la tête de chaîne, avec cache des verdicts positifs.

    Seul un verdict « à jour » est mémorisé : une base hors version est revérifiée
    à chaque sonde pour que le service redevienne prêt dès la migration appliquée,
    et non après expiration d'un cache. Sous SQLite le critère est le même
    (``alembic_version`` à la tête), puisque ``init_db()`` y estampille la tête.
    """

    if not database_ok:
        return CheckResult(
            False, "non vérifié : base injoignable", {"cached": False}
        )
    ttl = migration_cache_seconds(environ)
    now = time.monotonic()
    cached = _migration_cache.get(engine)
    if cached is not None and ttl > 0 and now - cached[0] < ttl:
        state, from_cache = cached[1], True
    else:
        try:
            state = check_schema_current(engine)
        except (SQLAlchemyError, OSError) as exc:
            return CheckResult(
                False,
                "version du schéma illisible",
                {"cached": False, "error": type(exc).__name__},
            )
        from_cache = False
        if state.ok:
            _migration_cache[engine] = (now, state)
    details = {"current": state.current, "head": state.head, "cached": from_cache}
    if state.ok:
        return CheckResult(True, "schéma à la révision attendue", details)
    return CheckResult(
        False,
        "schéma hors version : exécutez « python -m acp_database.migrate upgrade »",
        details,
    )


def _configured_root(environ: Mapping[str, str], name: str) -> Path | None:
    raw = environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else None


def _storage_check(root: Path | None, *, create_missing: bool) -> CheckResult:
    """Crée puis supprime un fichier sonde dans la racine configurée.

    ``create_missing`` n'est vrai qu'au démarrage : la racine est alors initialisée,
    comme le stockage le ferait à la première écriture, et des permissions
    insuffisantes se voient avant le premier livrable. La route ``/ready`` ne crée
    jamais rien : une racine disparue depuis le démarrage (volume démonté) la rend
    « dégradée » au lieu d'être recréée sur la couche éphémère du conteneur. Qu'un
    volume soit réellement monté ne se prouve pas ici mais dans l'entrypoint de
    l'image, qui refuse un répertoire de données non persistant.

    Une racine non configurée est « ok » : le stockage se replie alors sur
    ``./acp-data``, ce que le motif dit explicitement.
    """

    if root is None:
        return CheckResult(
            True,
            "non configuré : repli sur ./acp-data, non persistant hors poste de développement",
            {"configured": False},
        )
    if not create_missing and not root.exists():
        return CheckResult(
            False,
            "racine absente : volume démonté ou répertoire supprimé depuis le démarrage",
            {"configured": True},
        )
    probe = root / f"{PROBE_PREFIX}{secrets.token_hex(8)}"
    try:
        if create_missing:
            root.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ready")
        probe.unlink()
    except OSError as exc:
        return CheckResult(
            False,
            "racine non inscriptible (volume absent, permissions ou chemin "
            "occupé par un fichier)",
            {"configured": True, "error": type(exc).__name__},
        )
    return CheckResult(True, "racine inscriptible", {"configured": True})


def _outbox_check(
    engine, environ: Mapping[str, str], *, database_ok: bool
) -> CheckResult:
    """Compte les livraisons en attente et en lettre morte ; ne dégrade jamais.

    Actif seulement avec ``ACP_EVENT_RELAY_ENABLED=1``. Un arriéré signale un
    relais en panne ou en retard, ce que l'opérateur doit voir sur la sonde ; mais
    retirer l'API du trafic n'y changerait rien, d'où ``ok`` toujours vrai.
    """

    if environ.get(RELAY_ENABLED_ENV, "").strip() != "1":
        return CheckResult(True, "relais désactivé", {"enabled": False})
    if not database_ok:
        return CheckResult(True, "non vérifié : base injoignable", {"enabled": True})
    try:
        with engine.connect() as connection:
            pending = connection.execute(
                select(func.count())
                .select_from(EventOutboxModel)
                .where(
                    EventOutboxModel.delivered_at.is_(None),
                    EventOutboxModel.dead_at.is_(None),
                )
            ).scalar_one()
            dead = connection.execute(
                select(func.count())
                .select_from(EventOutboxModel)
                .where(EventOutboxModel.dead_at.is_not(None))
            ).scalar_one()
    except (SQLAlchemyError, OSError) as exc:
        return CheckResult(
            True,
            "boîte d'envoi illisible",
            {"enabled": True, "error": type(exc).__name__},
        )
    return CheckResult(
        True,
        f"{pending} événement(s) en attente, {dead} en lettre morte",
        {"enabled": True, "pending": pending, "dead": dead},
    )


def build_report(
    *, engine, environ: Mapping[str, str], create_storage_roots: bool = False
) -> ReadinessReport:
    """Exécute tous les contrôles contre ``engine`` avec la configuration ``environ``.

    Les contrôles dépendant de la base (migrations, boîte d'envoi) ne sont tentés
    que si la base répond : une base injoignable produit un seul diagnostic net
    plutôt que trois erreurs de connexion en cascade. ``create_storage_roots`` n'est
    posé que par le démarrage (voir :func:`_storage_check`).
    """

    database = _database_check(engine)
    checks = {
        "database": database,
        "migrations": _migrations_check(engine, environ, database_ok=database.ok),
        "artifact_storage": _storage_check(
            _configured_root(environ, ARTIFACT_STORAGE_DIR_ENV),
            create_missing=create_storage_roots,
        ),
        "skills_storage": _storage_check(
            _configured_root(environ, SKILLS_STORAGE_DIR_ENV),
            create_missing=create_storage_roots,
        ),
        "outbox": _outbox_check(engine, environ, database_ok=database.ok),
    }
    return ReadinessReport(checks=checks)


# --- démarrage ---------------------------------------------------------------


def assert_ready_at_startup(*, engine=None, environ: Mapping[str, str] | None = None) -> None:
    """Refuse le démarrage (``RuntimeError``) si un contrôle bloquant échoue.

    Les stockages ne sont vérifiés que s'ils sont configurés, et leurs racines sont
    initialisées ici, au démarrage seulement. Le message cite chaque contrôle en
    échec avec sa raison, jamais ``SystemExit`` : uvicorn journalise l'exception, ne
    sert aucune requête et laisse l'orchestrateur relancer ou alerter.
    """

    report = build_report(
        engine=engine if engine is not None else get_engine(),
        environ=os.environ if environ is None else environ,
        create_storage_roots=True,
    )
    failed = report.failed()
    if failed:
        details = "; ".join(f"{name} : {report.checks[name].reason}" for name in failed)
        raise RuntimeError(f"Démarrage refusé, service non prêt — {details}")


def prepare_service_at_startup() -> None:
    """Séquence de démarrage fermée : ``init_db()`` puis :func:`assert_ready_at_startup`.

    Sous PostgreSQL, ``init_db()`` ne crée rien et refuse une base hors version ;
    sous SQLite il complète le schéma puis l'estampille. Une base injoignable
    lève une erreur pilote (``OperationalError``) : elle est traduite en
    ``RuntimeError`` française, sans recopier le message du pilote qui peut
    contenir l'hôte ou le nom d'utilisateur ; la cause reste chaînée pour le
    journal.
    """

    try:
        init_db()
    except RuntimeError:
        raise
    except (SQLAlchemyError, OSError) as exc:
        raise RuntimeError(
            "Démarrage refusé : la base de données est injoignable ou a refusé "
            f"l'initialisation ({type(exc).__name__})"
        ) from exc
    assert_ready_at_startup()


# --- route -------------------------------------------------------------------


def mount(app: FastAPI, *, service: str) -> None:
    """Monte ``GET /ready`` sur ``app`` ; public, jamais mis en cache.

    La fonction de route est synchrone : FastAPI l'exécute dans son pool de
    threads, ce qui convient aux entrées-sorties bloquantes de la sonde. Le
    moteur et l'environnement sont lus à chaque appel, pas à l'import.
    """

    @app.get("/ready", name=f"ready_{service}")
    def ready() -> JSONResponse:
        report = build_report(engine=get_engine(), environ=os.environ)
        return JSONResponse(
            status_code=report.status_code,
            content=report.payload(service=service),
            headers={"Cache-Control": "no-store"},
        )
