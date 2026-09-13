"""Coffre de secrets via l'API : statut, création, rotation, révocation et RBAC.

Aucune valeur de secret ne doit apparaître dans une réponse ni dans la table ``events``.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.secrets_vault import SecretsVault, generate_key
from acp_api.security import create_user_session, hash_password, utcnow
from acp_database.models import Base, EventModel, SecretModel, UserModel

BOOTSTRAP_TOKEN = "secrets-bootstrap-token-with-enough-entropy"
PASSWORD = "correct horse battery staple"
SECRET_VALUE = "valeur-ultra-confidentielle-9f8e7d"


@pytest.fixture
def secrets_client(monkeypatch):
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.delenv("ACP_SECRETS_KEYS", raising=False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": BOOTSTRAP_TOKEN},
                json={
                    "login": "owner",
                    "display_name": "Propriétaire",
                    "password": PASSWORD,
                },
            )
            assert response.status_code == 201
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _create_user_session(session_factory, login: str, platform_role: str):
    with session_factory() as db:
        user = UserModel(
            login_normalized=f"{login}-{uuid4().hex[:8]}",
            display_name=login.title(),
            password_hash=hash_password(PASSWORD),
            platform_role=platform_role,
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
        return user.id, session_token, csrf_token


def _authenticate(client: TestClient, session_token: str, csrf_token: str) -> None:
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _create_project(client: TestClient, suffix: str) -> dict[str, str]:
    organization = client.post("/organizations", json={"name": f"Org {suffix}"}).json()
    workspace = client.post(
        "/workspaces", json={"organization_id": organization["id"], "name": f"Ws {suffix}"}
    ).json()
    project = client.post(
        "/projects", json={"workspace_id": workspace["id"], "name": f"Project {suffix}"}
    ).json()
    return {"workspace_id": workspace["id"], "project_id": project["id"]}


def _all_events(session_factory) -> list[EventModel]:
    with session_factory() as db:
        return db.query(EventModel).all()


def _assert_no_secret_leak(payload: object) -> None:
    assert SECRET_VALUE not in str(payload)


# --- coffre non configuré -------------------------------------------------------------


def test_unconfigured_vault_is_explicit_without_false_success(secrets_client):
    client, _ = secrets_client
    status = client.get("/secrets/status")
    assert status.status_code == 200
    body = status.json()
    assert body["configured"] is False
    assert body["primary_key_id"] is None and body["key_count"] == 0
    assert "ACP_SECRETS_KEYS" in body["message"]

    created = client.post(
        "/secrets", json={"name": "GITHUB_TOKEN", "value": SECRET_VALUE}
    )
    assert created.status_code == 503
    assert created.json()["detail"].startswith("Coffre de secrets non configuré")
    _assert_no_secret_leak(created.json())
    assert client.get("/secrets").json() == []


def test_status_requires_a_session(secrets_client):
    client, _ = secrets_client
    client.cookies.clear()
    assert client.get("/secrets/status").status_code == 401
    assert client.get("/secrets").status_code == 401


# --- cycle de vie -----------------------------------------------------------------------


def test_create_rotate_and_revoke_without_leaking_the_value(secrets_client, monkeypatch):
    client, session_factory = secrets_client
    first_key = generate_key()
    monkeypatch.setenv("ACP_SECRETS_KEYS", first_key)

    status = client.get("/secrets/status").json()
    assert status["configured"] is True and status["key_count"] == 1
    first_key_id = status["primary_key_id"]

    created = client.post(
        "/secrets",
        json={
            "name": "GITHUB_TOKEN",
            "value": SECRET_VALUE,
            "description": "Jeton GitHub de la plateforme",
        },
    )
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["name"] == "GITHUB_TOKEN"
    assert summary["scope_type"] == "platform"
    assert summary["project_id"] is None
    assert summary["key_id"] == first_key_id
    assert summary["rotated_at"] is None and summary["revoked_at"] is None
    assert summary["referenced_by_mcp_servers"] == []
    assert "value" not in summary and "ciphertext" not in summary
    _assert_no_secret_leak(summary)
    secret_id = summary["id"]

    duplicate = client.post("/secrets", json={"name": "GITHUB_TOKEN", "value": "autre"})
    assert duplicate.status_code == 409

    listed = client.get("/secrets")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [secret_id]
    _assert_no_secret_leak(listed.json())

    with session_factory() as db:
        row = db.get(SecretModel, secret_id)
        assert row.ciphertext != SECRET_VALUE and SECRET_VALUE not in row.ciphertext
        assert SecretsVault([first_key.encode()]).decrypt(row.ciphertext) == SECRET_VALUE

    # Rotation avec une nouvelle clé primaire : l'ancienne clé reste connue pour déchiffrer.
    second_key = generate_key()
    monkeypatch.setenv("ACP_SECRETS_KEYS", f"{second_key},{first_key}")
    rotated = client.post(f"/secrets/{secret_id}/rotate", json={"value": "nouvelle-valeur-2"})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["key_id"] != first_key_id
    assert rotated.json()["rotated_at"] is not None
    _assert_no_secret_leak(rotated.json())
    assert "nouvelle-valeur-2" not in rotated.text

    with session_factory() as db:
        row = db.get(SecretModel, secret_id)
        vault = SecretsVault([second_key.encode(), first_key.encode()])
        assert vault.decrypt(row.ciphertext) == "nouvelle-valeur-2"
        # Un jeton chiffré avec l'ancienne clé reste déchiffrable après la rotation de clés.
        _, old_token = SecretsVault([first_key.encode()]).encrypt("ancien")
        assert vault.decrypt(old_token) == "ancien"

    revoked = client.delete(f"/secrets/{secret_id}")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"] is not None
    assert client.delete(f"/secrets/{secret_id}").status_code == 409
    assert client.post(f"/secrets/{secret_id}/rotate", json={"value": "x"}).status_code == 409

    events = _all_events(session_factory)
    types = [event.type for event in events]
    assert types.count("secret.created") == 1
    assert types.count("secret.rotated") == 1
    assert types.count("secret.revoked") == 1
    for event in events:
        _assert_no_secret_leak(event.payload)
        assert "nouvelle-valeur-2" not in str(event.payload)
        assert "value" not in event.payload


def test_missing_secret_returns_404(secrets_client, monkeypatch):
    client, _ = secrets_client
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    assert client.post("/secrets/unknown/rotate", json={"value": "x"}).status_code == 404
    assert client.delete("/secrets/unknown").status_code == 404


def test_invalid_names_and_scopes_are_rejected(secrets_client, monkeypatch):
    client, _ = secrets_client
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    assert client.post("/secrets", json={"name": "lowercase", "value": "x"}).status_code == 422
    assert client.post("/secrets", json={"name": "OK_NAME", "value": ""}).status_code == 422
    assert (
        client.post(
            "/secrets", json={"name": "OK_NAME", "value": "x", "scope_type": "project"}
        ).status_code
        == 422
    )
    missing_project = client.post(
        "/secrets",
        json={"name": "OK_NAME", "value": "x", "scope_type": "project", "project_id": "nope"},
    )
    assert missing_project.status_code == 404


# --- RBAC ---------------------------------------------------------------------------------


def test_viewer_and_member_rules(secrets_client, monkeypatch):
    client, session_factory = secrets_client
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    first = _create_project(client, "A")
    second = _create_project(client, "B")

    platform_secret = client.post("/secrets", json={"name": "PLATFORM_KEY", "value": "p"})
    assert platform_secret.status_code == 201
    project_b_secret = client.post(
        "/secrets",
        json={
            "name": "PROJECT_B_KEY",
            "value": "b",
            "scope_type": "project",
            "project_id": second["project_id"],
        },
    )
    assert project_b_secret.status_code == 201

    viewer_id, viewer_session, viewer_csrf = _create_user_session(
        session_factory, "viewer", "viewer"
    )
    member_id, member_session, member_csrf = _create_user_session(
        session_factory, "member", "operator"
    )
    for user_id, role in ((viewer_id, "viewer"), (member_id, "member")):
        membership = client.post(
            "/memberships",
            json={
                "user_id": user_id,
                "scope_type": "project",
                "scope_id": first["project_id"],
                "role": role,
            },
        )
        assert membership.status_code == 200

    # Lecteur : aucune mutation, ni platform ni projet.
    _authenticate(client, viewer_session, viewer_csrf)
    assert client.post("/secrets", json={"name": "VIEWER_KEY", "value": "v"}).status_code == 403
    assert (
        client.post(
            "/secrets",
            json={
                "name": "VIEWER_KEY",
                "value": "v",
                "scope_type": "project",
                "project_id": first["project_id"],
            },
        ).status_code
        == 403
    )
    assert (
        client.post(f"/secrets/{platform_secret.json()['id']}/rotate", json={"value": "v"}).status_code
        == 403
    )
    assert client.delete(f"/secrets/{platform_secret.json()['id']}").status_code == 403
    assert client.get("/secrets").json() == []

    # Membre du projet A : secret de projet A autorisé, projet B et platform refusés.
    _authenticate(client, member_session, member_csrf)
    assert client.post("/secrets", json={"name": "MEMBER_KEY", "value": "m"}).status_code == 403
    assert (
        client.post(
            "/secrets",
            json={
                "name": "MEMBER_KEY",
                "value": "m",
                "scope_type": "project",
                "project_id": second["project_id"],
            },
        ).status_code
        == 403
    )
    own = client.post(
        "/secrets",
        json={
            "name": "MEMBER_KEY",
            "value": "m",
            "scope_type": "project",
            "project_id": first["project_id"],
        },
    )
    assert own.status_code == 201, own.text
    assert [row["id"] for row in client.get("/secrets").json()] == [own.json()["id"]]
    assert client.delete(f"/secrets/{project_b_secret.json()['id']}").status_code == 403
    assert client.post(f"/secrets/{own.json()['id']}/rotate", json={"value": "m2"}).status_code == 200

    # CSRF exigé sur les mutations.
    client.headers.pop("X-CSRF-Token")

    assert (
        client.post(
            "/secrets",
            json={
                "name": "NO_CSRF",
                "value": "m",
                "scope_type": "project",
                "project_id": first["project_id"],
            },
        ).status_code
        == 403
    )


# --- journal d'audit ------------------------------------------------------------------


def test_the_audit_trail_of_the_vault_is_readable_in_the_project_journal(
    secrets_client, monkeypatch
):
    """Un événement d'audit du coffre doit entrer dans le curseur du journal projet.

    Écrit sans numéro de journal, il resterait invisible de
    ``GET /projects/{id}/events`` pour toute la vie du processus, puis ressortirait
    hors d'ordre après un redémarrage : une trace d'audit muette n'est pas une trace
    d'audit.
    """

    client, session_factory = secrets_client
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    scope = _create_project(client, "Journal")
    project_id = scope["project_id"]
    baseline = client.get(f"/projects/{project_id}/events").json()
    cursor = baseline["next_cursor"] or 0

    created = client.post(
        "/secrets",
        json={
            "name": "API_TOKEN_JOURNAL",
            "value": SECRET_VALUE,
            "scope_type": "project",
            "project_id": project_id,
        },
    )
    assert created.status_code == 201, created.text

    page = client.get(
        f"/projects/{project_id}/events", params={"after_seq": cursor}
    ).json()
    assert [event["type"] for event in page["events"]] == ["secret.created"]
    assert page["next_cursor"] is not None and page["next_cursor"] > cursor
    _assert_no_secret_leak(page)

    rows = [event for event in _all_events(session_factory) if event.type == "secret.created"]
    assert rows and all(row.journal_seq is not None for row in rows)
