"""Point d'entrée de compatibilité ``GET /meta`` et jeton CSRF dédié ``POST /auth/csrf``.

Ce que ces tests prouvent, et rien de plus :

- le corps publié dit la vérité du serveur au moment de l'appel — version lue du
  fichier ``VERSION``, bornes lues de leurs modules, capacités **recalculées** à chaque
  requête quand l'environnement change ;
- rien de secret ne sort : ni clé, ni chemin, ni nom de variable d'environnement ;
- l'appel est public, comme ``/health`` et ``/ready``, qui restent inchangés ;
- le refus d'un client trop ancien est fermé, en français, et ne se déclenche que sur
  une annonce explicite : aucun client existant ne le rencontre ;
- ``POST /auth/csrf`` ne fait pas tourner un jeton encore valide, et ``GET
  /auth/session`` garde exactement le comportement dont dépendent le web et le CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.routers import meta
from acp_api.secrets_vault import generate_key
from acp_database.testing import make_test_engine

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERSION_FILE = REPOSITORY_ROOT / "VERSION"

BOOTSTRAP_TOKEN = "test-bootstrap-token-with-enough-entropy"
PASSWORD = "correct horse battery staple"

#: Valeurs volontairement reconnaissables : si l'une d'elles apparaissait dans une
#: réponse publique, la fuite serait immédiatement visible dans l'assertion.
SIGNING_KEY = "cle-de-signature-de-test-suffisamment-longue-0123456789"

COMPATIBILITY_ENV = (
    "ACP_ARTIFACT_SIGNING_KEYS",
    "ACP_SECRETS_KEYS",
    "ACP_EVENT_RELAY_ENABLED",
    "ACP_ARTIFACT_PUBLIC_ORIGIN",
    "ACP_ALLOW_LEGACY_WORKER_CLAIM",
    "ACP_SESSION_COOKIE_SECURE",
    "ACP_SESSION_TTL_SECONDS",
    "ACP_STREAM_MAX_SECONDS",
    "ACP_STREAM_MAX_CONNECTIONS_PER_USER",
    "ACP_EVENT_RETENTION_DAYS",
    "ACP_MIN_CLIENT_VERSION_DESKTOP",
    "ACP_MIN_CLIENT_VERSION_CLI",
    "ACP_VERSION_FILE",
)


@pytest.fixture
def clean_environ(monkeypatch):
    """Serveur sans aucune bascule : les capacités partent toutes de « non configuré »."""

    for name in COMPATIBILITY_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def client(clean_environ):
    with TestClient(app) as api_client:
        yield api_client


@pytest.fixture
def session_client(monkeypatch, tmp_path):
    """Client porteur d'une vraie session : base dédiée, propriétaire amorcé."""

    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACP_SESSION_TTL_SECONDS", "3600")
    database = make_test_engine(tmp_path)
    session_factory = sessionmaker(bind=database.engine, expire_on_commit=False)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as api_client:
            created = api_client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={
                    "login": "owner",
                    "display_name": "Propriétaire",
                    "password": PASSWORD,
                },
            )
            assert created.status_code == 201
            yield api_client, created.json()["csrf_token"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close()


def _meta(client: TestClient, **kwargs) -> dict:
    response = client.get("/meta", **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


# --- Contenu du corps ---------------------------------------------------------


def test_meta_publishes_versions_capabilities_and_limits(client):
    response = client.get("/meta")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()

    assert body["service"] == "api"
    assert body["checked_at"]
    assert body["client_announcement"] is None

    versions = body["versions"]
    assert versions["product"] == VERSION_FILE.read_text(encoding="utf-8").strip()
    assert versions["product_source"] == "fichier VERSION du dépôt"
    # La version de contrat d'API est versionnée indépendamment du produit : elle est
    # publiée, et rien n'impose qu'elle suive VERSION.
    assert versions["api_contract"]
    assert versions["event_schema"]
    assert versions["contracts"]

    for name in (
        "artifact_signing",
        "secrets_vault",
        "event_relay",
        "artifact_preview",
        "legacy_worker_claim",
        "session_cookie_secure",
        "interactive_docs",
        "csrf_endpoint",
    ):
        capability = body["capabilities"][name]
        assert isinstance(capability["available"], bool)
        assert capability["detail"].strip()

    limits = body["limits"]
    assert limits["session_ttl_seconds"] == 43200
    assert limits["stream_max_seconds"] == 900.0
    assert limits["stream_keepalive_seconds"] == 15.0
    assert limits["stream_poll_interval_ms"] == 400.0
    assert limits["stream_batch"] == 200
    assert limits["stream_max_connections_per_user"] == 4
    # La borne de flux n'est globale que tant qu'il n'y a qu'une réplique : le document
    # le dit plutôt que de laisser le client la croire partagée.
    assert limits["stream_connection_limit_scope"] == "process"
    assert limits["event_page_default_limit"] == 200
    assert limits["event_page_max_limit"] == 500
    assert limits["event_retention_days"] == 90
    assert limits["mission_page_max_limit"] == 500
    assert limits["artifact_page_default_limit"] == 50
    assert limits["artifact_page_max_limit"] == 200
    assert limits["artifact_link_default_ttl_seconds"] == 300
    assert limits["artifact_link_max_ttl_seconds"] == 900
    assert limits["max_request_body_bytes"] == 1024 * 1024
    assert limits["skill_source_max_body_bytes"] == 32 * 1024 * 1024


def test_meta_version_follows_the_version_file(clean_environ, tmp_path):
    """La version vient du fichier, jamais d'une constante recopiée dans le code."""

    version_file = tmp_path / "VERSION"
    version_file.write_text("41.2.3\n", encoding="utf-8")
    clean_environ.setenv("ACP_VERSION_FILE", str(version_file))
    with TestClient(app) as api_client:
        body = _meta(api_client)
    assert body["versions"]["product"] == "41.2.3"
    assert body["versions"]["product_source"] == (
        "fichier VERSION désigné par la configuration"
    )
    # Le plancher par défaut suit la version servie, sans être écrit nulle part.
    assert body["clients"]["desktop"]["minimum_version"] == "41.2.3"
    assert body["clients"]["cli"]["minimum_version"] == "41.2.3"


def test_meta_ignores_an_unreadable_version_file_and_falls_back_to_the_repository(
    clean_environ, tmp_path
):
    """Un fichier illisible n'est pas interprété : la lecture passe à la source suivante."""

    version_file = tmp_path / "VERSION"
    version_file.write_text("version inconnue\n", encoding="utf-8")
    clean_environ.setenv("ACP_VERSION_FILE", str(version_file))
    with TestClient(app) as api_client:
        body = _meta(api_client)
    assert body["versions"]["product"] == VERSION_FILE.read_text(encoding="utf-8").strip()
    assert body["versions"]["product_source"] == "fichier VERSION du dépôt"


def test_product_version_refuses_rather_than_inventing(monkeypatch, tmp_path):
    """Sans aucune source lisible, la fonction refuse : aucune version par défaut."""

    monkeypatch.setattr(meta, "_repository_version", lambda: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        meta.importlib_metadata,
        "version",
        _raise_package_not_found,
    )
    with pytest.raises(meta.ProductVersionUnavailable) as refusal:
        meta.product_version({})
    assert "VERSION" in str(refusal.value)


def _raise_package_not_found(_name: str) -> str:
    raise meta.importlib_metadata.PackageNotFoundError("acp-api")


# --- Absence de secret --------------------------------------------------------


def test_meta_never_leaks_secrets_paths_or_configuration_names(clean_environ, tmp_path):
    vault_key = generate_key()
    clean_environ.setenv("ACP_ARTIFACT_SIGNING_KEYS", SIGNING_KEY)
    clean_environ.setenv("ACP_SECRETS_KEYS", vault_key)
    clean_environ.setenv("ACP_ARTIFACT_PUBLIC_ORIGIN", "https://preview.example.test")
    with TestClient(app) as api_client:
        response = api_client.get("/meta")
    assert response.status_code == 200
    body = response.text

    assert SIGNING_KEY not in body
    assert vault_key not in body
    # Aucun nom de variable d'environnement : un document public ne cartographie pas la
    # configuration du serveur.
    assert "ACP_" not in body
    # Ni chemin de poste, ni URL interne.
    assert str(tmp_path) not in body
    assert str(REPOSITORY_ROOT) not in body
    assert "preview.example.test" not in body


# --- Capacités calculées ------------------------------------------------------


@pytest.mark.parametrize(
    ("variable", "value", "capability", "expected"),
    [
        ("ACP_ARTIFACT_SIGNING_KEYS", SIGNING_KEY, "artifact_signing", True),
        # Clé trop courte : la configuration existe, la capacité n'existe pas. C'est
        # tout l'écart entre une capacité calculée et une capacité déclarée.
        ("ACP_ARTIFACT_SIGNING_KEYS", "trop-courte", "artifact_signing", False),
        ("ACP_EVENT_RELAY_ENABLED", "1", "event_relay", True),
        # Aucune tolérance : « true » n'active rien, et le document le montre.
        ("ACP_EVENT_RELAY_ENABLED", "true", "event_relay", False),
        (
            "ACP_ARTIFACT_PUBLIC_ORIGIN",
            "https://preview.example.test",
            "artifact_preview",
            True,
        ),
        ("ACP_ARTIFACT_PUBLIC_ORIGIN", "pas-une-origine", "artifact_preview", False),
        ("ACP_ALLOW_LEGACY_WORKER_CLAIM", "1", "legacy_worker_claim", True),
        ("ACP_ALLOW_LEGACY_WORKER_CLAIM", "0", "legacy_worker_claim", False),
        ("ACP_SESSION_COOKIE_SECURE", "1", "session_cookie_secure", True),
        ("ACP_SESSION_COOKIE_SECURE", "0", "session_cookie_secure", False),
    ],
)
def test_capabilities_follow_the_environment(
    clean_environ, variable, value, capability, expected
):
    with TestClient(app) as api_client:
        absent = _meta(api_client)["capabilities"][capability]["available"]
        clean_environ.setenv(variable, value)
        present = _meta(api_client)["capabilities"][capability]["available"]
        clean_environ.delenv(variable)
        removed = _meta(api_client)["capabilities"][capability]["available"]

    assert absent is False
    assert present is expected
    # La capacité suit réellement l'environnement au lieu d'être figée au démarrage.
    assert removed is False


def test_secrets_vault_capability_follows_a_real_key(clean_environ):
    with TestClient(app) as api_client:
        assert _meta(api_client)["capabilities"]["secrets_vault"]["available"] is False
        clean_environ.setenv("ACP_SECRETS_KEYS", generate_key())
        assert _meta(api_client)["capabilities"]["secrets_vault"]["available"] is True
        clean_environ.setenv("ACP_SECRETS_KEYS", "pas-une-cle-fernet")
        assert _meta(api_client)["capabilities"]["secrets_vault"]["available"] is False


def test_limits_follow_the_environment(clean_environ):
    with TestClient(app) as api_client:
        clean_environ.setenv("ACP_SESSION_TTL_SECONDS", "7200")
        clean_environ.setenv("ACP_STREAM_MAX_SECONDS", "120")
        clean_environ.setenv("ACP_STREAM_MAX_CONNECTIONS_PER_USER", "2")
        clean_environ.setenv("ACP_EVENT_RETENTION_DAYS", "0")
        limits = _meta(api_client)["limits"]

    assert limits["session_ttl_seconds"] == 7200
    assert limits["stream_max_seconds"] == 120.0
    assert limits["stream_max_connections_per_user"] == 2
    assert limits["event_retention_days"] == 0


# --- Accès public et non-régression -------------------------------------------


def test_meta_is_public_and_health_and_ready_are_unchanged(client):
    assert client.cookies.get("acp_session") is None
    assert client.get("/meta").status_code == 200

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "api"}

    ready = client.get("/ready")
    assert ready.status_code in (200, 503)
    payload = ready.json()
    assert payload["service"] == "api"
    assert set(payload["checks"]) == {
        "database",
        "migrations",
        "artifact_storage",
        "skills_storage",
        "outbox",
    }


# --- Refus fermé d'un client trop ancien --------------------------------------


def test_a_recent_client_is_accepted_and_echoed(clean_environ):
    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_DESKTOP", "0.9.0")
    with TestClient(app) as api_client:
        response = api_client.get("/meta", headers={"X-ACP-Client": "desktop/0.9.1"})
    assert response.status_code == 200
    announcement = response.json()["client_announcement"]
    assert announcement == {
        "client": "desktop",
        "version": "0.9.1",
        "known": True,
        "accepted": True,
        "minimum_version": "0.9.0",
        "detail": "Version acceptée par ce serveur.",
    }


def test_an_outdated_client_is_refused_with_426_in_french(clean_environ):
    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_DESKTOP", "0.9.0")
    with TestClient(app) as api_client:
        response = api_client.get("/meta", headers={"X-ACP-Client": "desktop/0.8.9"})
    assert response.status_code == 426
    body = response.json()
    assert "refusée" in body["detail"]
    assert "0.9.0" in body["detail"]
    # Le refus porte le document : le client affiche la version servie et l'exigence
    # au lieu d'un écran vide.
    assert body["versions"]["product"]
    assert body["client_announcement"]["accepted"] is False


def test_a_prerelease_does_not_satisfy_its_own_floor(clean_environ):
    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_CLI", "0.9.0")
    with TestClient(app) as api_client:
        refused = api_client.get("/meta", headers={"X-ACP-Client": "cli/0.9.0-rc1"})
        accepted = api_client.get("/meta", headers={"X-ACP-Client": "cli/0.9.0"})
    assert refused.status_code == 426
    assert accepted.status_code == 200


def test_an_unknown_client_is_neither_guaranteed_nor_refused(client):
    response = client.get("/meta", headers={"X-ACP-Client": "atelier/0.1.0"})
    assert response.status_code == 200
    announcement = response.json()["client_announcement"]
    assert announcement["known"] is False
    assert announcement["accepted"] is True
    assert announcement["minimum_version"] is None


def test_known_clients_env_and_contract_stay_aligned():
    """Les trois listes de clients connus ne peuvent pas diverger en silence."""

    from acp_contracts import ClientRequirements, KNOWN_CLIENTS

    assert set(KNOWN_CLIENTS) == set(meta.MINIMUM_CLIENT_VERSION_ENV)
    assert set(KNOWN_CLIENTS) == set(ClientRequirements.model_fields)


@pytest.mark.parametrize("client", ["json", "copy", "dict", "construct"])
def test_a_client_named_like_a_model_method_is_only_unknown(client):
    """Un nom de client homonyme d'une méthode de modèle reste « inconnu », jamais un 500."""

    with TestClient(app) as api_client:
        response = api_client.get("/meta", headers={"X-ACP-Client": f"{client}/1.0.0"})
    assert response.status_code == 200
    assert response.json()["client_announcement"]["known"] is False


@pytest.mark.parametrize(
    "header", ["desktop", "desktop/", "/0.9.0", "desktop/version", "DESKTOP/0.9.0"]
)
def test_a_malformed_announcement_is_refused_rather_than_guessed(client, header):
    response = client.get("/meta", headers={"X-ACP-Client": header})
    assert response.status_code == 400
    assert "X-ACP-Client" in response.json()["detail"]


def test_requests_without_the_header_are_never_refused(clean_environ):
    """Le web et le CLI n'annoncent rien : ils ne peuvent pas être refusés."""

    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_DESKTOP", "99.0.0")
    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_CLI", "99.0.0")
    with TestClient(app) as api_client:
        response = api_client.get("/meta")
    assert response.status_code == 200
    assert response.json()["client_announcement"] is None


def test_an_unreadable_floor_is_a_closed_refusal(clean_environ):
    clean_environ.setenv("ACP_MIN_CLIENT_VERSION_DESKTOP", "dernière")
    with TestClient(app) as api_client:
        response = api_client.get("/meta")
    assert response.status_code == 503
    assert "ACP_MIN_CLIENT_VERSION_DESKTOP" in response.json()["detail"]


# --- Jeton CSRF : point d'obtention dédié -------------------------------------


def test_csrf_endpoint_confirms_a_valid_token_without_rotating_it(session_client):
    api_client, csrf_token = session_client

    first = api_client.post("/auth/csrf", headers={"X-CSRF-Token": csrf_token})
    second = api_client.post("/auth/csrf", headers={"X-CSRF-Token": csrf_token})

    assert first.status_code == second.status_code == 200
    assert first.json()["rotated"] is False
    assert second.json()["rotated"] is False
    assert first.json()["csrf_token"] is None
    assert second.json()["csrf_token"] is None
    assert first.json()["expires_at"]

    # Le jeton initial reste valide après deux appels : c'est exactement la course que
    # GET /auth/session provoquait sur un client multi-thread.
    logout = api_client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 200


def test_csrf_endpoint_issues_a_token_when_none_is_presented(session_client):
    api_client, csrf_token = session_client

    issued = api_client.post("/auth/csrf")
    assert issued.status_code == 200
    payload = issued.json()
    assert payload["rotated"] is True
    assert payload["csrf_token"] and payload["csrf_token"] != csrf_token

    # L'ancien jeton est bien remplacé, et le nouveau autorise une mutation.
    assert api_client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token}).status_code == 403
    assert (
        api_client.post(
            "/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]}
        ).status_code
        == 200
    )


def test_csrf_endpoint_requires_a_session(client):
    assert client.post("/auth/csrf").status_code == 401


def test_auth_session_keeps_rotating_for_existing_clients(session_client):
    """Non-régression : le web et le CLI gardent le comportement qu'ils connaissent."""

    api_client, csrf_token = session_client

    first = api_client.get("/auth/session")
    second = api_client.get("/auth/session")
    assert first.status_code == second.status_code == 200
    first_token = first.json()["csrf_token"]
    second_token = second.json()["csrf_token"]
    assert len({csrf_token, first_token, second_token}) == 3

    assert api_client.post("/auth/logout", headers={"X-CSRF-Token": first_token}).status_code == 403
    assert api_client.post("/auth/logout", headers={"X-CSRF-Token": second_token}).status_code == 200
