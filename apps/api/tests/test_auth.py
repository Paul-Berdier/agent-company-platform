"""Tests du bootstrap propriétaire et des sessions web révocables."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.security import hash_token, utcnow, verify_password
from acp_database.models import UserModel, UserSessionModel
from acp_database.testing import make_test_engine

BOOTSTRAP_TOKEN = "test-bootstrap-token-with-enough-entropy"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def auth_client(monkeypatch, tmp_path):
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
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close()


def _bootstrap(client: TestClient, *, login: str = "Owner"):
    return client.post(
        "/auth/bootstrap",
        headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
        json={
            "login": login,
            "display_name": "Propriétaire",
            "password": PASSWORD,
        },
    )


def test_bootstrap_is_token_protected_unique_and_stores_only_hashes(auth_client):
    client, session_factory = auth_client
    status_response = client.get("/auth/status")
    assert status_response.status_code == 200
    assert status_response.json() == {"bootstrap_required": True}
    assert status_response.headers["cache-control"] == "no-store"

    missing = client.post(
        "/auth/bootstrap",
        json={
            "login": "owner",
            "display_name": "Propriétaire",
            "password": PASSWORD,
        },
    )
    wrong = client.post(
        "/auth/bootstrap",
        headers={"X-ACP-Bootstrap-Token": "incorrect"},
        json={
            "login": "owner",
            "display_name": "Propriétaire",
            "password": PASSWORD,
        },
    )
    assert missing.status_code == wrong.status_code == 403
    assert missing.json() == wrong.json()
    assert wrong.headers["cache-control"] == "no-store"

    created = _bootstrap(client)
    assert created.status_code == 201
    payload = created.json()
    assert payload["user"]["login"] == "owner"
    assert payload["user"]["role"] == "owner"
    assert "password" not in created.text.lower()
    assert "acp_session" not in payload
    cookie_header = created.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    session_token = client.cookies.get("acp_session")
    assert session_token

    with session_factory() as db:
        user = db.query(UserModel).one()
        session = db.query(UserSessionModel).one()
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != PASSWORD
        assert verify_password(PASSWORD, user.password_hash)
        assert session.token_hash == hash_token(session_token)
        assert session.token_hash != session_token
        assert session.csrf_token_hash == hash_token(payload["csrf_token"])

    replay = _bootstrap(client, login="another-owner")
    assert replay.status_code == 409
    assert client.get("/auth/status").json() == {"bootstrap_required": False}


def test_login_has_generic_errors_and_creates_a_new_opaque_session(auth_client):
    client, session_factory = auth_client
    assert _bootstrap(client).status_code == 201
    client.cookies.clear()

    unknown = client.post(
        "/auth/login", json={"login": "unknown", "password": "wrong-password"}
    )
    wrong = client.post(
        "/auth/login", json={"login": "OWNER", "password": "wrong-password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Identifiants invalides"}

    logged_in = client.post(
        "/auth/login", json={"login": " OWNER ", "password": PASSWORD}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["login"] == "owner"
    assert client.cookies.get("acp_session")
    with session_factory() as db:
        assert db.query(UserSessionModel).count() == 2
        assert db.query(UserModel).one().last_login_at is not None


def test_session_reload_rotates_csrf_and_logout_revokes_server_side(auth_client):
    client, session_factory = auth_client
    created = _bootstrap(client)
    first_csrf = created.json()["csrf_token"]

    reloaded = client.get("/auth/session")
    assert reloaded.status_code == 200
    second_csrf = reloaded.json()["csrf_token"]
    assert second_csrf != first_csrf
    assert reloaded.headers["cache-control"] == "no-store"

    assert client.post("/auth/logout").status_code == 403
    assert (
        client.post(
            "/auth/logout", headers={"X-CSRF-Token": first_csrf}
        ).status_code
        == 403
    )
    logged_out = client.post(
        "/auth/logout", headers={"X-CSRF-Token": second_csrf}
    )
    assert logged_out.status_code == 200
    assert logged_out.json() == {"status": "signed_out"}
    assert client.cookies.get("acp_session") is None
    assert client.get("/auth/session").status_code == 401
    with session_factory() as db:
        assert db.query(UserSessionModel).one().revoked_at is not None


def test_expired_session_and_spoofed_user_header_do_not_authenticate(auth_client):
    client, session_factory = auth_client
    created = _bootstrap(client)
    session_token = client.cookies.get("acp_session")
    assert session_token
    with session_factory() as db:
        session = db.query(UserSessionModel).filter_by(
            token_hash=hash_token(session_token)
        ).one()
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/auth/session").status_code == 401

    client.cookies.clear()
    spoofed = client.post(
        "/tasks",
        headers={
            "X-User-Id": created.json()["user"]["id"],
            "X-CSRF-Token": created.json()["csrf_token"],
        },
        json={"project_id": "missing", "title": "Ne doit pas être créée"},
    )
    assert spoofed.status_code == 401


def test_mutation_authenticated_by_cookie_requires_current_csrf(auth_client):
    client, _ = auth_client
    created = _bootstrap(client)
    csrf_token = created.json()["csrf_token"]

    without_csrf = client.post(
        "/tasks", json={"project_id": "missing", "title": "Refusée"}
    )
    assert without_csrf.status_code == 403

    accepted_by_auth_layer = client.post(
        "/tasks",
        headers={"X-CSRF-Token": csrf_token},
        json={"project_id": "missing", "title": "Projet absent"},
    )
    assert accepted_by_auth_layer.status_code == 404
