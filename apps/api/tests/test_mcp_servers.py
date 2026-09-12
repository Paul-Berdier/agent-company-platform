"""Centre MCP : parcours HTTP et stdio complets, révocation, rollback, exports, RBAC (critère 7).

Aucun réseau réel : le probe HTTP passe par un ``httpx.MockTransport`` et un résolveur DNS
injectés via les dépendances du routeur ; le probe stdio est simulé par un worker de test
qui réclame l'autorisation et renvoie un résultat.
"""

from __future__ import annotations

import json
import socket
import tomllib
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from acp_contracts.redaction import REDACTED_PLACEHOLDER

from acp_api.deps import get_db
from acp_api.main import app
from acp_api.routers import mcp as mcp_router
from acp_api.routers.workers import utcnow
from acp_api.secrets_vault import generate_key
from acp_api.security import create_user_session, hash_password
from acp_database.models import (
    Base,
    EventModel,
    McpProbeModel,
    SecretModel,
    TaskModel,
    UserModel,
)

PUBLIC_IP = "93.184.216.34"
PASSWORD = "correct horse battery staple"
REDACTED = REDACTED_PLACEHOLDER
HTTP_SECRET_VALUE = "Bearer SECRET-VALUE-123"
STDIO_SECRET_VALUE = "stdio-secret-value-456"
ALL_SECRET_VALUES = (HTTP_SECRET_VALUE, STDIO_SECRET_VALUE)


def fake_resolver(table: dict[str, list[str]]):
    def resolve(host, port=None, *args, **kwargs):
        if host not in table:
            raise socket.gaierror(-2, "Name or service not known")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))
            for address in table[host]
        ]

    return resolve


class RouterFakeMcp:
    """Serveur MCP Streamable HTTP simulé (JSON) dont les outils changent entre deux probes.

    ``echo_header`` simule un serveur bavard : il réémet la valeur de l'en-tête reçu dans
    ``serverInfo``, dans les capacités, dans la description d'un outil et dans un message
    d'erreur JSON-RPC. C'est le comportement hostile que l'expurgation doit neutraliser.
    """

    def __init__(self) -> None:
        self.tools: list[dict] = [
            {"name": "search", "description": "Recherche", "inputSchema": {"type": "object"}},
            {"name": "fetch", "description": "Lecture", "inputSchema": {"type": "object"}},
        ]
        self.status_override: int | None = None
        self.echo_header: str | None = None
        self.echo_as_jsonrpc_error = False
        self.seen: list[httpx.Request] = []

    def _echoed(self, request: httpx.Request) -> str:
        if self.echo_header is None:
            return ""
        return request.headers.get(self.echo_header, "")

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if self.status_override is not None:
            return httpx.Response(self.status_override, text="panne")
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body.get("method")
        echoed = self._echoed(request)
        if method == "initialize":
            if self.echo_as_jsonrpc_error:
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": -32000, "message": f"jeton refusé : {echoed}"},
                    },
                )
            server_info = {"name": "router-fake", "version": "0.1"}
            capabilities: dict = {"tools": {}}
            if echoed:
                server_info["authenticated_as"] = echoed
                capabilities["echo"] = echoed
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "router-session"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": capabilities,
                        "serverInfo": server_info,
                    },
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            tools = [dict(tool) for tool in self.tools]
            if echoed:
                tools[0]["description"] = f"jeton reçu : {echoed}"
                tools[0]["inputSchema"] = {"type": "object", "title": echoed}
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": tools}}
            )
        return httpx.Response(400)


@pytest.fixture
def mcp_context(monkeypatch):
    bootstrap_token = f"bootstrap-{uuid4().hex}"
    registration_token = f"registration-{uuid4().hex}"
    monkeypatch.setenv("ACP_BOOTSTRAP_TOKEN", bootstrap_token)
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", registration_token)
    monkeypatch.setenv("ACP_SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    monkeypatch.delenv("ACP_OUTBOUND_PRIVATE_ALLOWLIST", raising=False)
    monkeypatch.delenv("ACP_OUTBOUND_ALLOW_LOOPBACK_HTTP", raising=False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    fake = RouterFakeMcp()
    resolver_table = {
        "mcp.example": [PUBLIC_IP],
        "other.example": [PUBLIC_IP],
        "intranet.example": ["10.1.2.3"],
        "private.example": ["10.9.9.9"],
    }

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[mcp_router.get_dns_resolver] = lambda: fake_resolver(resolver_table)
    app.dependency_overrides[mcp_router.get_http_transport] = lambda: httpx.MockTransport(fake.handle)
    try:
        with TestClient(app) as client:
            bootstrap = client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={"login": "owner", "display_name": "Propriétaire", "password": PASSWORD},
            )
            assert bootstrap.status_code == 201
            owner_csrf = bootstrap.json()["csrf_token"]
            owner_session = client.cookies.get("acp_session")
            client.headers["X-CSRF-Token"] = owner_csrf
            organization = client.post("/organizations", json={"name": "Org MCP"}).json()
            projects = {}
            for label in ("A", "B"):
                workspace = client.post(
                    "/workspaces", json={"organization_id": organization["id"], "name": f"Ws {label}"}
                ).json()
                project = client.post(
                    "/projects", json={"workspace_id": workspace["id"], "name": f"Projet {label}"}
                ).json()
                agent = client.post(
                    "/agents",
                    json={"workspace_id": workspace["id"], "name": f"Agent {label}", "role_id": "developer"},
                ).json()
                projects[label] = {
                    "workspace_id": workspace["id"],
                    "project_id": project["id"],
                    "agent_id": agent["id"],
                }

            def register(name: str, capabilities: list[str], simulation: bool) -> dict:
                response = client.post(
                    "/workers/register",
                    headers={"X-Worker-Registration-Token": registration_token},
                    json={
                        "name": f"{name}-{uuid4().hex[:6]}",
                        "capabilities": capabilities,
                        "max_concurrency": 1,
                        "simulation": simulation,
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()

            workers = {
                "real": register("probe-runner", ["mcp_stdio_probe", "git"], False),
                "no_capability": register("plain-runner", ["git"], False),
                "simulation": register("sim-runner", ["mcp_stdio_probe"], True),
            }
            yield {
                "client": client,
                "session_factory": session_factory,
                "fake": fake,
                "projects": projects,
                "workers": workers,
                "register_worker": register,
                "owner": (owner_session, owner_csrf),
            }
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(mcp_router.get_dns_resolver, None)
        app.dependency_overrides.pop(mcp_router.get_http_transport, None)
        engine.dispose()


# --- helpers ---------------------------------------------------------------------------------


def _authenticate(client: TestClient, session_token: str, csrf_token: str) -> None:
    client.cookies.clear()
    client.cookies.set("acp_session", session_token)
    client.headers["X-CSRF-Token"] = csrf_token


def _as_owner(context) -> None:
    _authenticate(context["client"], *context["owner"])


def _create_user(context, login: str, platform_role: str, memberships: list[tuple[str, str]]):
    """Crée un utilisateur avec ses memberships ``(project_label, role)`` ; retourne (session, csrf)."""

    with context["session_factory"]() as db:
        user = UserModel(
            login_normalized=f"{login}-{uuid4().hex[:8]}",
            display_name=login,
            password_hash=hash_password(PASSWORD),
            platform_role=platform_role,
            password_changed_at=utcnow(),
        )
        db.add(user)
        db.flush()
        _, session_token, csrf_token = create_user_session(db, user.id)
        db.commit()
        user_id = user.id
    _as_owner(context)
    for label, role in memberships:
        response = context["client"].post(
            "/memberships",
            json={
                "user_id": user_id,
                "scope_type": "project",
                "scope_id": context["projects"][label]["project_id"],
                "role": role,
            },
        )
        assert response.status_code == 200, response.text
    return session_token, csrf_token


def _create_secret(context, name: str, value: str, project_label: str | None = None) -> str:
    payload = {"name": name, "value": value}
    if project_label is not None:
        payload.update(scope_type="project", project_id=context["projects"][project_label]["project_id"])
    response = context["client"].post("/secrets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _http_payload(name: str, secret_id: str, url: str = "https://mcp.example/mcp") -> dict:
    return {
        "name": name,
        "display_name": f"Serveur {name}",
        "description": "Serveur de test",
        "config": {
            "transport": "http",
            "http": {
                "url": url,
                "headers": {"X-Client": "acp"},
                "header_secrets": {"Authorization": {"secret_id": secret_id}},
                "timeout_seconds": 5,
            },
        },
    }


def _http_payload_without_secret(name: str, url: str = "https://mcp.example/mcp") -> dict:
    """Serveur HTTP public : aucune référence de secret, donc aucun besoin de coffre."""

    return {
        "name": name,
        "display_name": f"Serveur {name}",
        "config": {
            "transport": "http",
            "http": {"url": url, "headers": {"X-Client": "acp"}, "timeout_seconds": 5},
        },
    }


def _stdio_payload(name: str, secret_id: str, worker_id: str | None, args: list[str] | None = None) -> dict:
    return {
        "name": name,
        "display_name": f"Serveur {name}",
        "config": {
            "transport": "stdio",
            "stdio": {
                "command": "/opt/mcp/bin/server",
                "args": args if args is not None else ["--root", "/data"],
                "env": {"LOG_LEVEL": "info"},
                "env_secrets": {"API_KEY": {"secret_id": secret_id}},
                "cwd": "/data",
                "timeout_seconds": 10,
            },
        },
        "target_worker_id": worker_id,
    }


def _worker_headers(worker: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {worker['token']}", "X-Worker-Id": worker["worker_id"]}


def _claim(context, worker: dict) -> httpx.Response:
    client = context["client"]
    saved_cookies = dict(client.cookies)
    client.cookies.clear()
    try:
        return client.post("/mcp/worker/probes/claim", headers=_worker_headers(worker))
    finally:
        for key, value in saved_cookies.items():
            client.cookies.set(key, value)


def _report(context, worker: dict, probe_id: str, result: dict) -> httpx.Response:
    client = context["client"]
    saved_cookies = dict(client.cookies)
    client.cookies.clear()
    try:
        return client.post(
            f"/mcp/worker/probes/{probe_id}/result", headers=_worker_headers(worker), json=result
        )
    finally:
        for key, value in saved_cookies.items():
            client.cookies.set(key, value)


def _assert_no_secret_value(text: str) -> None:
    for value in ALL_SECRET_VALUES:
        assert value not in text


def _events(context, event_type: str) -> list[EventModel]:
    with context["session_factory"]() as db:
        return db.query(EventModel).filter_by(type=event_type).all()


def _extensions(context, label: str):
    """Instantané des extensions du projet ; ``None`` tant que la route de l'agent B est absente."""

    response = context["client"].get(f"/projects/{context['projects'][label]['project_id']}/extensions")
    if response.status_code == 404 and response.json().get("detail") == "Not Found":
        return None
    assert response.status_code == 200, response.text
    return response.json()


def _stdio_result(tools: list[str]) -> dict:
    return {
        "protocol_version": "2025-06-18",
        "server_info": {"name": "stdio-fake", "version": "1.0"},
        "tools": [{"name": name, "description": "", "input_schema": {}} for name in tools],
        "exit_code": 0,
        "stderr_tail": "",
        "duration_ms": 42,
        "error": None,
    }


def _activate_stdio_server(context, name: str, secret_id: str, tools: list[str]) -> dict:
    """Parcours complet stdio (probe → approbation → claim → résultat → activation)."""

    client = context["client"]
    real = context["workers"]["real"]
    created = client.post("/mcp/servers", json=_stdio_payload(name, secret_id, real["worker_id"]))
    assert created.status_code == 201, created.text
    server_id = created.json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe")
    assert probe.status_code == 200, probe.text
    decided = client.post(f"/mcp/probes/{probe.json()['id']}/decision", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    claimed = _claim(context, real).json()["probe"]
    assert claimed is not None and claimed["id"] == probe.json()["id"]
    reported = _report(context, real, claimed["id"], _stdio_result(tools))
    assert reported.status_code == 200, reported.text
    activated = client.post(f"/mcp/servers/{server_id}/activate")
    assert activated.status_code == 200, activated.text
    return activated.json()


# --- catalogue -------------------------------------------------------------------------------


def test_catalog_lists_three_documented_entries(mcp_context):
    client = mcp_context["client"]
    response = client.get("/mcp/catalog")
    assert response.status_code == 200
    entries = {entry["id"]: entry for entry in response.json()}
    assert set(entries) == {"context7", "github-remote", "filesystem"}
    for entry in entries.values():
        assert entry["verified_at"] == "2026-09-11"
        assert "non exécuté" in entry["verification"]
        assert entry["documentation_url"].startswith("https://")
        config = entry["config"]
        if config["transport"] == "http":
            assert config["http"]["header_secrets"] == {}
        else:
            assert config["stdio"]["env_secrets"] == {}
    assert entries["context7"]["config"]["http"]["url"] == "https://mcp.context7.com/mcp"
    assert entries["context7"]["required_secrets"] == ["CONTEXT7_API_KEY"]
    assert entries["github-remote"]["config"]["http"]["url"] == "https://api.githubcopilot.com/mcp/"
    assert entries["github-remote"]["required_secrets"]
    assert entries["filesystem"]["transport"] == "stdio"
    assert "@modelcontextprotocol/server-filesystem@2025.8.21" in entries["filesystem"]["config"]["stdio"]["args"]
    assert entries["filesystem"]["risks"]
    client.cookies.clear()
    assert client.get("/mcp/catalog").status_code == 401


# --- parcours HTTP -------------------------------------------------------------------------


def test_http_server_lifecycle_probe_bind_activate_revise_revoke(mcp_context):
    client = mcp_context["client"]
    fake = mcp_context["fake"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    project_b = mcp_context["projects"]["B"]["project_id"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)

    # Création : secret en clair refusé, URL http refusée par la politique, référence acceptée.
    plaintext = _http_payload("github", secret_id)
    plaintext["config"]["http"]["headers"] = {"Authorization": "Bearer en-clair"}
    plaintext["config"]["http"]["header_secrets"] = {}
    refused = client.post("/mcp/servers", json=plaintext)
    assert refused.status_code == 422
    assert "référence de secret" in refused.json()["detail"]

    insecure = client.post("/mcp/servers", json=_http_payload("github", secret_id, "http://mcp.example/mcp"))
    assert insecure.status_code == 422
    assert "scheme_forbidden" in insecure.json()["detail"]

    forbidden_url = client.post(
        "/mcp/servers", json=_http_payload("github", secret_id, "https://user:pw@mcp.example/mcp")
    )
    assert forbidden_url.status_code == 422 and "userinfo_forbidden" in forbidden_url.json()["detail"]

    assert client.post("/mcp/servers", json={**_http_payload("Bad Name", secret_id)}).status_code == 422

    created = client.post("/mcp/servers", json=_http_payload("github", secret_id))
    assert created.status_code == 201, created.text
    detail = created.json()
    _assert_no_secret_value(created.text)
    server_id = detail["id"]
    assert detail["status"] == "draft"
    assert detail["transport"] == "http" and detail["execution_location"] == "platform"
    assert detail["source_kind"] == "manual"
    assert detail["current_revision_number"] == 1
    assert detail["discovery_current"] is False
    assert detail["tool_count"] == 0 and detail["binding_count"] == 0
    revision = detail["current_revision"]
    assert revision["number"] == 1 and revision["fingerprint"]
    assert revision["config"]["http"]["header_secrets"] == {"Authorization": {"secret_id": secret_id}}
    assert revision["change_summary"]["previous_number"] is None
    assert revision["requires_approval"] is False
    assert len(detail["revisions"]) == 1
    assert client.post("/mcp/servers", json=_http_payload("github", secret_id)).status_code == 409

    secret_summary = next(row for row in client.get("/secrets").json() if row["id"] == secret_id)
    assert secret_summary["referenced_by_mcp_servers"] == [server_id]

    listed = client.get("/mcp/servers").json()
    assert [row["id"] for row in listed] == [server_id]
    assert client.get("/mcp/servers", params={"status": "active"}).json() == []
    assert client.get(f"/mcp/servers/{server_id}").status_code == 200
    assert client.get("/mcp/servers/unknown").status_code == 404

    # Ni binding ni activation avant une découverte courante.
    early_binding = client.post(
        f"/mcp/servers/{server_id}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
    )
    assert early_binding.status_code == 409
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 409

    # Probe HTTP : exécuté côté API avec le secret injecté, jamais renvoyé.
    probe = client.post(f"/mcp/servers/{server_id}/probe")
    assert probe.status_code == 200, probe.text
    _assert_no_secret_value(probe.text)
    assert probe.json()["status"] == "succeeded"
    assert probe.json()["transport"] == "http"
    assert probe.json()["authorization"] is None
    assert [tool["name"] for tool in probe.json()["result"]["tools"]] == ["search", "fetch"]
    assert probe.json()["result"]["protocol_version"] == "2025-06-18"
    assert probe.json()["expires_at"]
    initialize = fake.seen[0]
    assert initialize.headers["authorization"] == HTTP_SECRET_VALUE
    assert initialize.headers["x-client"] == "acp"
    assert initialize.headers["host"] == "mcp.example" and initialize.url.host == PUBLIC_IP
    with mcp_context["session_factory"]() as db:
        assert db.get(SecretModel, secret_id).last_used_at is not None

    detail = client.get(f"/mcp/servers/{server_id}").json()
    assert detail["discovery_current"] is True and detail["tool_count"] == 2
    assert detail["last_probe_status"] == "succeeded" and detail["last_probe_at"]
    assert detail["current_revision"]["discovery"]["server_info"]["name"] == "router-fake"
    assert len(detail["probes"]) == 1
    assert client.get(f"/mcp/servers/{server_id}/probes").json()[0]["id"] == probe.json()["id"]
    assert client.get(f"/mcp/probes/{probe.json()['id']}").json()["status"] == "succeeded"
    assert client.get("/mcp/probes").json() == []  # défaut : non terminaux uniquement
    assert [row["id"] for row in client.get("/mcp/probes", params={"status": "succeeded"}).json()] == [
        probe.json()["id"]
    ]
    assert _events(mcp_context, "mcp.probe.succeeded")

    # Binding : serveur non actif ⇒ 409 ; puis activation ; outil inconnu ⇒ 422.
    assert (
        client.post(
            f"/mcp/servers/{server_id}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
        ).status_code
        == 409
    )
    activated = client.post(f"/mcp/servers/{server_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert _events(mcp_context, "mcp.server.activated")

    unknown_tool = client.post(
        f"/mcp/servers/{server_id}/bindings",
        json={"project_id": project_a, "allowed_tools": ["search", "nope"]},
    )
    assert unknown_tool.status_code == 422 and "nope" in unknown_tool.json()["detail"]
    assert (
        client.post(f"/mcp/servers/{server_id}/bindings", json={"project_id": project_a, "allowed_tools": []}).status_code
        == 422
    )
    assert (
        client.post(f"/mcp/servers/{server_id}/bindings", json={"project_id": "nope", "allowed_tools": ["search"]}).status_code
        == 404
    )
    binding = client.post(
        f"/mcp/servers/{server_id}/bindings",
        json={"project_id": project_a, "allowed_tools": ["search", "fetch"]},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]
    assert binding.json()["revision_number"] == 1
    assert binding.json()["server_name"] == "github"
    assert binding.json()["enabled"] is True and binding.json()["revoked_at"] is None
    assert (
        client.post(
            f"/mcp/servers/{server_id}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
        ).status_code
        == 409
    )
    assert client.get(f"/mcp/servers/{server_id}").json()["binding_count"] == 1
    assert [row["id"] for row in client.get("/mcp/bindings", params={"project_id": project_a}).json()] == [binding_id]
    assert client.get("/mcp/bindings", params={"project_id": project_b}).json() == []
    assert [row["id"] for row in client.get("/mcp/bindings", params={"server_id": server_id}).json()] == [binding_id]

    extensions_a = _extensions(mcp_context, "A")
    if extensions_a is not None:
        assert [item["server_id"] for item in extensions_a["mcp"]] == [server_id]
        assert extensions_a["mcp"][0]["allowed_tools"] == ["search", "fetch"]
        assert extensions_a["mcp"][0]["revision_number"] == 1
        assert _extensions(mcp_context, "B")["mcp"] == []

    # Révision qui change l'URL : découverte plus courante, activation refusée, binding inchangé.
    revised = client.post(
        f"/mcp/servers/{server_id}/revisions",
        json={"config": _http_payload("github", secret_id, "https://other.example/mcp")["config"], "note": "nouvel hôte"},
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["current_revision_number"] == 2
    assert revised.json()["discovery_current"] is False
    assert revised.json()["status"] == "active"
    summary = revised.json()["current_revision"]["change_summary"]
    assert summary["previous_number"] == 1 and summary["endpoint_changed"] is True
    assert "http.url" in summary["changed_fields"]
    assert revised.json()["revisions"][0]["superseded_at"] is not None
    assert client.get(f"/mcp/bindings/{binding_id}").json()["revision_number"] == 1
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 409

    # Nouveau probe : l'outil « fetch » a disparu ⇒ retiré du binding et listé dans apply_notes.
    fake.tools = [fake.tools[0]]
    assert client.post(f"/mcp/servers/{server_id}/probe").json()["status"] == "succeeded"
    reactivated = client.post(f"/mcp/servers/{server_id}/activate")
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["current_revision"]["change_summary"]["tools_removed"] == ["fetch"]
    assert any("fetch" in note for note in reactivated.json()["apply_notes"])
    binding_after = client.get(f"/mcp/bindings/{binding_id}").json()
    assert binding_after["revision_number"] == 2 and binding_after["allowed_tools"] == ["search"]

    # Export : placeholder, jamais la valeur ; restreint aux outils du projet.
    export = client.get("/mcp/export", params={"format": "hermes"})
    assert export.status_code == 200, export.text
    _assert_no_secret_value(export.text)
    assert "${ACP_SECRET_GITHUB_TOKEN}" in export.json()["content"]
    assert export.json()["placeholders"] == ["ACP_SECRET_GITHUB_TOKEN"]
    project_export = client.get("/mcp/export", params={"format": "hermes", "project_id": project_a})
    assert project_export.status_code == 200
    parsed = yaml.safe_load(project_export.json()["content"])
    assert parsed["mcp_servers"]["github"]["tools"]["include"] == ["search"]
    assert project_export.json()["partial_compatibility"]

    # Le secret est référencé par un serveur actif : révocation du secret refusée.
    assert client.delete(f"/secrets/{secret_id}").status_code == 409

    # Révocation : irréversible, bindings révoqués, historique conservé, export sans le serveur.
    assert client.post(f"/mcp/servers/{server_id}/revoke", json={"reason": ""}).status_code == 422
    revoked = client.post(f"/mcp/servers/{server_id}/revoke", json={"reason": "Fournisseur abandonné"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked" and revoked.json()["revoked_at"]
    assert revoked.json()["bindings"][0]["revoked_at"] is not None
    assert len(revoked.json()["revisions"]) == 2
    events = _events(mcp_context, "mcp.server.revoked")
    assert len(events) == 1 and events[0].payload["reason"] == "Fournisseur abandonné"
    assert events[0].payload["server_id"] == server_id
    assert "github" not in client.get("/mcp/export", params={"format": "hermes"}).json()["content"]
    assert client.get("/mcp/bindings", params={"project_id": project_a}).json()[0]["revoked_at"]
    if _extensions(mcp_context, "A") is not None:
        assert _extensions(mcp_context, "A")["mcp"] == []

    history = client.get(f"/mcp/servers/{server_id}")
    assert history.status_code == 200 and history.json()["status"] == "revoked"
    assert [row["id"] for row in client.get("/mcp/servers", params={"status": "revoked"}).json()] == [server_id]
    for path, body in (
        ("revisions", {"config": _http_payload("github", secret_id)["config"]}),
        ("probe", None),
        ("activate", None),
        ("disable", None),
        ("revoke", {"reason": "encore"}),
        ("rollback", {"revision_number": 1}),
    ):
        response = client.post(f"/mcp/servers/{server_id}/{path}", json=body)
        assert response.status_code == 409, (path, response.text)
    assert client.patch(f"/mcp/bindings/{binding_id}", json={"enabled": False}).status_code == 409
    assert client.delete(f"/secrets/{secret_id}").status_code == 200

    for event in _events(mcp_context, "mcp.probe.succeeded") + _events(mcp_context, "mcp.server.revoked"):
        _assert_no_secret_value(json.dumps(event.payload))


def test_http_probe_failures_are_explicit_and_allowlist_is_audited(mcp_context, monkeypatch):
    client = mcp_context["client"]
    fake = mcp_context["fake"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)

    # Cible résolue vers une adresse privée : probe échoué avec le code de la politique.
    private = client.post("/mcp/servers", json=_http_payload("private", secret_id, "https://private.example/mcp"))
    assert private.status_code == 201, private.text
    probe = client.post(f"/mcp/servers/{private.json()['id']}/probe")
    assert probe.status_code == 200
    assert probe.json()["status"] == "failed"
    assert "host_blocked" in probe.json()["error"]
    assert fake.seen == []
    assert client.get(f"/mcp/servers/{private.json()['id']}").json()["last_probe_status"] == "failed"
    assert _events(mcp_context, "mcp.probe.failed")

    # Réponse 500 du serveur : échec explicite.
    server = client.post("/mcp/servers", json=_http_payload("flaky", secret_id))
    fake.status_override = 500
    failed = client.post(f"/mcp/servers/{server.json()['id']}/probe").json()
    assert failed["status"] == "failed" and "500" in failed["error"]
    fake.status_override = None
    assert client.get(f"/mcp/servers/{server.json()['id']}").json()["discovery_current"] is False

    # Secret révoqué : le probe refuse d'injecter et échoue explicitement.
    other_secret = _create_secret(mcp_context, "OTHER_TOKEN", "Bearer other")
    revocable = client.post("/mcp/servers", json=_http_payload("revocable", other_secret))
    assert client.delete(f"/secrets/{other_secret}").status_code == 200
    failed = client.post(f"/mcp/servers/{revocable.json()['id']}/probe").json()
    assert failed["status"] == "failed" and "révoqué" in failed["error"]

    # Allowlist ciblée : la cible privée devient joignable et l'usage est journalisé.
    monkeypatch.setenv("ACP_OUTBOUND_PRIVATE_ALLOWLIST", "intranet.example")
    intranet = client.post("/mcp/servers", json=_http_payload("intranet", secret_id, "https://intranet.example/mcp"))
    assert intranet.status_code == 201, intranet.text
    assert client.post(f"/mcp/servers/{intranet.json()['id']}/probe").json()["status"] == "succeeded"
    audit = _events(mcp_context, "outbound.private_allowlist_used")
    assert len(audit) == 1
    assert audit[0].payload == {"host": "intranet.example", "address": "10.1.2.3", "purpose": "mcp_probe"}


def test_disable_is_reversible(mcp_context):
    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("toggle", secret_id)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").json()["status"] == "active"
    disabled = client.post(f"/mcp/servers/{server['id']}/disable")
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
    assert (
        client.post(
            f"/mcp/servers/{server['id']}/bindings",
            json={"project_id": mcp_context["projects"]["A"]["project_id"], "allowed_tools": ["search"]},
        ).status_code
        == 409
    )
    assert client.post(f"/mcp/servers/{server['id']}/activate").json()["status"] == "active"


# --- parcours stdio ------------------------------------------------------------------------


def test_stdio_creation_refusals(mcp_context):
    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    real = mcp_context["workers"]["real"]["worker_id"]

    relative = _stdio_payload("relative", secret_id, real)
    relative["config"]["stdio"]["command"] = "npx"
    response = client.post("/mcp/servers", json=relative)
    assert response.status_code == 422 and "relative_command" in response.json()["detail"]

    unpinned = _stdio_payload("unpinned", secret_id, real)
    unpinned["config"]["stdio"]["command"] = "/usr/local/bin/npx"
    unpinned["config"]["stdio"]["args"] = ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    response = client.post("/mcp/servers", json=unpinned)
    assert response.status_code == 422 and "unpinned_package" in response.json()["detail"]

    pinned = _stdio_payload("pinned", secret_id, real)
    pinned["config"]["stdio"]["command"] = "C:\\Program Files\\nodejs\\npx.cmd"
    pinned["config"]["stdio"]["args"] = ["-y", "@modelcontextprotocol/server-filesystem@2025.8.21", "C:\\data"]
    response = client.post("/mcp/servers", json=pinned)
    assert response.status_code == 201, response.text

    plaintext = _stdio_payload("plaintext", secret_id, real)
    plaintext["config"]["stdio"]["env"] = {"GITHUB_TOKEN": "ghp_en_clair"}
    response = client.post("/mcp/servers", json=plaintext)
    assert response.status_code == 422 and "référence de secret" in response.json()["detail"]

    unknown_worker = client.post("/mcp/servers", json=_stdio_payload("noworker", secret_id, "nope"))
    assert unknown_worker.status_code == 404

    unknown_secret = _stdio_payload("nosecret", "missing-secret", real)
    response = client.post("/mcp/servers", json=unknown_secret)
    assert response.status_code == 422 and "secret" in response.json()["detail"].lower()


def test_stdio_probe_requires_authorization_then_worker_claim_and_result(mcp_context):
    client = mcp_context["client"]
    workers = mcp_context["workers"]
    real = workers["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)

    created = client.post("/mcp/servers", json=_stdio_payload("stdio", secret_id, real["worker_id"]))
    assert created.status_code == 201, created.text
    _assert_no_secret_value(created.text)
    server_id = created.json()["id"]
    assert created.json()["execution_location"] == "runner"
    assert created.json()["target_worker_id"] == real["worker_id"]
    assert created.json()["current_revision"]["requires_approval"] is True
    fingerprint = created.json()["current_revision"]["fingerprint"]

    # Rien à réclamer tant qu'aucun probe n'est en file.
    idle = _claim(mcp_context, real)
    assert idle.status_code == 200 and idle.json() == {"probe": None}
    assert idle.headers["cache-control"] == "no-store"
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 409

    probe = client.post(f"/mcp/servers/{server_id}/probe")
    assert probe.status_code == 200, probe.text
    probe_id = probe.json()["id"]
    assert probe.json()["status"] == "pending_approval"
    authorization = probe.json()["authorization"]
    assert authorization["action"] == "mcp_stdio_launch"
    assert authorization["target"] == "/opt/mcp/bin/server --root /data"
    assert authorization["consequences"]
    assert authorization["scope"] == {"execution_location": "runner", "worker_id": real["worker_id"]}
    assert authorization["fingerprint"] == fingerprint
    assert authorization["expires_at"]
    _assert_no_secret_value(probe.text)
    assert client.post(f"/mcp/servers/{server_id}/probe").status_code == 409
    assert [row["id"] for row in client.get("/mcp/probes").json()] == [probe_id]
    assert _claim(mcp_context, real).json()["probe"] is None

    assert client.post(f"/mcp/probes/{probe_id}/decision", json={"decision": "maybe"}).status_code == 422
    decided = client.post(f"/mcp/probes/{probe_id}/decision", json={"decision": "approved", "comment": "ok"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "queued"
    assert decided.json()["decided_by_user_id"] and decided.json()["decided_at"]
    assert decided.json()["decision_comment"] == "ok"
    assert client.post(f"/mcp/probes/{probe_id}/decision", json={"decision": "rejected"}).status_code == 409

    # Seul un worker réel doté de la capacité peut réclamer ; la valeur n'est renvoyée qu'à lui.
    assert _claim(mcp_context, workers["no_capability"]).json()["probe"] is None
    assert _claim(mcp_context, workers["simulation"]).json()["probe"] is None
    unauthenticated = client.post(
        "/mcp/worker/probes/claim",
        headers={"Authorization": "Bearer wrong", "X-Worker-Id": real["worker_id"]},
    )
    assert unauthenticated.status_code == 401
    assert client.post("/mcp/worker/probes/claim").status_code == 401

    claimed = _claim(mcp_context, real)
    assert claimed.status_code == 200, claimed.text
    assert claimed.headers["cache-control"] == "no-store"
    payload = claimed.json()["probe"]
    assert payload["id"] == probe_id and payload["server_id"] == server_id
    assert payload["revision_id"] == created.json()["current_revision"]["id"]
    assert payload["command"] == "/opt/mcp/bin/server"
    assert payload["args"] == ["--root", "/data"]
    assert payload["env"] == {"LOG_LEVEL": "info", "API_KEY": STDIO_SECRET_VALUE}
    assert payload["cwd"] == "/data" and payload["timeout_seconds"] == 10
    assert payload["lease_expires_at"]
    assert _claim(mcp_context, real).json()["probe"] is None

    visible = client.get(f"/mcp/probes/{probe_id}")
    assert visible.json()["status"] == "claimed" and visible.json()["worker_id"] == real["worker_id"]
    _assert_no_secret_value(visible.text)
    _assert_no_secret_value(client.get(f"/mcp/servers/{server_id}").text)
    with mcp_context["session_factory"]() as db:
        assert db.get(SecretModel, secret_id).last_used_at is not None
        for event in db.query(EventModel).all():
            _assert_no_secret_value(json.dumps(event.payload))

    # Résultat : uniquement par le worker détenteur.
    assert _report(mcp_context, workers["no_capability"], probe_id, _stdio_result(["read_file"])).status_code == 409
    reported = _report(mcp_context, real, probe_id, _stdio_result(["read_file", "list_dir"]))
    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "succeeded"
    assert [tool["name"] for tool in reported.json()["result"]["tools"]] == ["read_file", "list_dir"]
    assert reported.json()["finished_at"]
    assert _report(mcp_context, real, probe_id, _stdio_result(["again"])).status_code == 409

    detail = client.get(f"/mcp/servers/{server_id}").json()
    assert detail["discovery_current"] is True and detail["tool_count"] == 2
    assert detail["last_probe_status"] == "succeeded"
    activated = client.post(f"/mcp/servers/{server_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    # Un résultat en échec ne produit jamais une découverte.
    failing_secret = _create_secret(mcp_context, "OTHER_KEY", "other-value")
    other = client.post("/mcp/servers", json=_stdio_payload("stdio-failing", failing_secret, real["worker_id"])).json()
    failing_probe = client.post(f"/mcp/servers/{other['id']}/probe").json()
    client.post(f"/mcp/probes/{failing_probe['id']}/decision", json={"decision": "approved"})
    assert _claim(mcp_context, real).json()["probe"]["id"] == failing_probe["id"]
    failure = _report(
        mcp_context, real, failing_probe["id"],
        {"protocol_version": None, "server_info": None, "tools": [], "exit_code": 1, "stderr_tail": "boom", "duration_ms": 5, "error": "timeout"},
    )
    assert failure.status_code == 200 and failure.json()["status"] == "failed"
    assert failure.json()["error"] == "timeout"
    assert client.get(f"/mcp/servers/{other['id']}").json()["discovery_current"] is False
    assert client.post(f"/mcp/servers/{other['id']}/activate").status_code == 409


def test_stdio_probe_rejection_invalidation_expiration_and_lost_lease(mcp_context):
    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post("/mcp/servers", json=_stdio_payload("stdio", secret_id, real["worker_id"])).json()["id"]

    # Refus explicite.
    rejected_probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    rejected = client.post(f"/mcp/probes/{rejected_probe['id']}/decision", json={"decision": "rejected", "comment": "non"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert rejected.json()["finished_at"]
    assert _claim(mcp_context, real).json()["probe"] is None

    # Révision modifiée avant décision ⇒ invalidé (l'empreinte autorisée ne correspond plus).
    pending = client.post(f"/mcp/servers/{server_id}/probe").json()
    revised = client.post(
        f"/mcp/servers/{server_id}/revisions",
        json={"config": _stdio_payload("stdio", secret_id, real["worker_id"], args=["--root", "/other"])["config"]},
    )
    assert revised.status_code == 201, revised.text
    assert revised.json()["current_revision"]["change_summary"]["changed_fields"] == ["stdio.args"]
    assert revised.json()["current_revision"]["requires_approval"] is True
    assert client.get(f"/mcp/probes/{pending['id']}").json()["status"] == "invalidated"
    assert client.post(f"/mcp/probes/{pending['id']}/decision", json={"decision": "approved"}).status_code == 409
    assert _claim(mcp_context, real).json()["probe"] is None

    # Approuvé puis révision modifiée avant claim ⇒ invalidé.
    queued = client.post(f"/mcp/servers/{server_id}/probe").json()
    assert client.post(f"/mcp/probes/{queued['id']}/decision", json={"decision": "approved"}).json()["status"] == "queued"
    client.post(
        f"/mcp/servers/{server_id}/revisions",
        json={"config": _stdio_payload("stdio", secret_id, real["worker_id"], args=["--root", "/third"])["config"]},
    )
    assert _claim(mcp_context, real).json()["probe"] is None
    assert client.get(f"/mcp/probes/{queued['id']}").json()["status"] == "invalidated"

    # Autorisation expirée ⇒ expiré, aucun claim.
    expiring = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{expiring['id']}/decision", json={"decision": "approved"})
    with mcp_context["session_factory"]() as db:
        row = db.get(McpProbeModel, expiring["id"])
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert _claim(mcp_context, real).json()["probe"] is None
    assert client.get(f"/mcp/probes/{expiring['id']}").json()["status"] == "expired"

    # Lease perdu ⇒ résultat refusé (409) et probe expiré.
    lost = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{lost['id']}/decision", json={"decision": "approved"})
    assert _claim(mcp_context, real).json()["probe"]["id"] == lost["id"]
    with mcp_context["session_factory"]() as db:
        row = db.get(McpProbeModel, lost["id"])
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert _report(mcp_context, real, lost["id"], _stdio_result(["x"])).status_code == 409
    assert client.get(f"/mcp/probes/{lost['id']}").json()["status"] == "expired"
    assert client.get(f"/mcp/servers/{server_id}").json()["discovery_current"] is False

    # Révocation : les probes non terminaux passent à « cancelled ».
    cancelled = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/servers/{server_id}/revoke", json={"reason": "fin"})
    assert client.get(f"/mcp/probes/{cancelled['id']}").json()["status"] == "cancelled"
    statuses = {row["status"] for row in client.get(f"/mcp/servers/{server_id}/probes").json()}
    assert statuses == {"rejected", "invalidated", "expired", "cancelled"}


# --- rollback ---------------------------------------------------------------------------------


def test_rollback_copies_config_and_discovery(mcp_context):
    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("roll", secret_id)).json()
    server_id = server["id"]
    first_fingerprint = server["current_revision"]["fingerprint"]
    client.post(f"/mcp/servers/{server_id}/probe")
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 200
    binding = client.post(
        f"/mcp/servers/{server_id}/bindings",
        json={"project_id": mcp_context["projects"]["A"]["project_id"], "allowed_tools": ["search"]},
    ).json()

    revised = client.post(
        f"/mcp/servers/{server_id}/revisions",
        json={"config": _http_payload("roll", secret_id, "https://other.example/mcp")["config"]},
    ).json()
    assert revised["current_revision_number"] == 2 and revised["discovery_current"] is False

    assert client.post(f"/mcp/servers/{server_id}/rollback", json={"revision_number": 9}).status_code == 404
    rolled = client.post(f"/mcp/servers/{server_id}/rollback", json={"revision_number": 1, "note": "retour"})
    assert rolled.status_code == 200, rolled.text
    current = rolled.json()["current_revision"]
    assert current["number"] == 3 and current["fingerprint"] == first_fingerprint
    assert current["config"]["http"]["url"] == "https://mcp.example/mcp"
    assert current["discovery_current"] is True
    assert current["discovery"]["tools"]
    assert current["change_summary"]["previous_number"] == 2
    assert current["note"] == "retour"
    assert rolled.json()["discovery_current"] is True
    assert client.get(f"/mcp/bindings/{binding['id']}").json()["revision_number"] == 1
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 200
    assert client.get(f"/mcp/bindings/{binding['id']}").json()["revision_number"] == 3
    assert _events(mcp_context, "mcp.server.rolled_back")


def test_stdio_rollback_reuses_an_accepted_authorization(mcp_context):
    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    activated = _activate_stdio_server(mcp_context, "stdio-roll", secret_id, ["read_file"])
    server_id = activated["id"]
    approved_fingerprint = activated["current_revision"]["fingerprint"]

    revised = client.post(
        f"/mcp/servers/{server_id}/revisions",
        json={"config": _stdio_payload("stdio-roll", secret_id, real["worker_id"], args=["--root", "/elsewhere"])["config"]},
    ).json()
    assert revised["current_revision"]["requires_approval"] is True
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 409

    rolled = client.post(f"/mcp/servers/{server_id}/rollback", json={"revision_number": 1}).json()
    assert rolled["current_revision"]["fingerprint"] == approved_fingerprint
    assert rolled["current_revision"]["requires_approval"] is False
    assert rolled["discovery_current"] is True
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 200

    # Retour sur la révision jamais autorisée : approbation exigée à nouveau.
    rolled_again = client.post(f"/mcp/servers/{server_id}/rollback", json={"revision_number": 2}).json()
    assert rolled_again["current_revision"]["requires_approval"] is True
    assert rolled_again["discovery_current"] is False


# --- exports ----------------------------------------------------------------------------------


def test_exports_use_placeholders_and_never_values(mcp_context):
    client = mcp_context["client"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    http_secret = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    stdio_secret = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)

    http_server = client.post("/mcp/servers", json=_http_payload("github", http_secret)).json()
    client.post(f"/mcp/servers/{http_server['id']}/probe")
    assert client.post(f"/mcp/servers/{http_server['id']}/activate").status_code == 200
    _activate_stdio_server(mcp_context, "files", stdio_secret, ["read_file", "write_file"])
    draft = client.post("/mcp/servers", json=_http_payload("draft-only", http_secret, "https://other.example/mcp"))
    assert draft.status_code == 201
    binding = client.post(
        f"/mcp/servers/{http_server['id']}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
    )
    assert binding.status_code == 201, binding.text

    assert client.get("/mcp/export", params={"format": "yaml"}).status_code == 422

    hermes = client.get("/mcp/export", params={"format": "hermes"})
    assert hermes.status_code == 200, hermes.text
    _assert_no_secret_value(hermes.text)
    body = hermes.json()
    assert body["format"] == "hermes" and body["project_id"] is None
    assert sorted(body["placeholders"]) == ["ACP_SECRET_API_KEY", "ACP_SECRET_GITHUB_TOKEN"]
    assert any("ACP_SECRET_" in note for note in body["apply_notes"])
    assert any("reload-mcp" in note for note in body["apply_notes"])
    parsed = yaml.safe_load(body["content"])
    assert set(parsed["mcp_servers"]) == {"github", "files"}
    assert parsed["mcp_servers"]["github"]["url"] == "https://mcp.example/mcp"
    assert parsed["mcp_servers"]["github"]["headers"] == {
        "X-Client": "acp",
        "Authorization": "${ACP_SECRET_GITHUB_TOKEN}",
    }
    assert parsed["mcp_servers"]["github"]["timeout"] == 5
    assert "tools" not in parsed["mcp_servers"]["github"]
    assert parsed["mcp_servers"]["files"]["command"] == "/opt/mcp/bin/server"
    assert parsed["mcp_servers"]["files"]["args"] == ["--root", "/data"]
    assert parsed["mcp_servers"]["files"]["env"] == {"LOG_LEVEL": "info", "API_KEY": "${ACP_SECRET_API_KEY}"}

    hermes_project = client.get("/mcp/export", params={"format": "hermes", "project_id": project_a}).json()
    parsed = yaml.safe_load(hermes_project["content"])
    assert set(parsed["mcp_servers"]) == {"github"}
    assert parsed["mcp_servers"]["github"]["tools"] == {"include": ["search"]}
    assert hermes_project["project_id"] == project_a
    assert any("tools.include" in note for note in hermes_project["partial_compatibility"])

    claude = client.get("/mcp/export", params={"format": "claude"})
    assert claude.status_code == 200
    _assert_no_secret_value(claude.text)
    parsed = json.loads(claude.json()["content"])
    assert parsed["mcpServers"]["github"] == {
        "type": "http",
        "url": "https://mcp.example/mcp",
        "headers": {"X-Client": "acp", "Authorization": "${ACP_SECRET_GITHUB_TOKEN}"},
    }
    assert parsed["mcpServers"]["files"]["type"] == "stdio"
    assert parsed["mcpServers"]["files"]["command"] == "/opt/mcp/bin/server"
    assert parsed["mcpServers"]["files"]["env"]["API_KEY"] == "${ACP_SECRET_API_KEY}"
    claude_project = client.get("/mcp/export", params={"format": "claude", "project_id": project_a}).json()
    assert claude_project["partial_compatibility"]

    codex = client.get("/mcp/export", params={"format": "codex"})
    assert codex.status_code == 200
    _assert_no_secret_value(codex.text)
    parsed = tomllib.loads(codex.json()["content"])
    assert parsed["mcp_servers"]["github"]["url"] == "https://mcp.example/mcp"
    assert parsed["mcp_servers"]["github"]["bearer_token_env_var"] == "ACP_SECRET_GITHUB_TOKEN"
    assert parsed["mcp_servers"]["github"]["http_headers"] == {"X-Client": "acp"}
    assert parsed["mcp_servers"]["files"]["command"] == "/opt/mcp/bin/server"
    assert parsed["mcp_servers"]["files"]["args"] == ["--root", "/data"]
    assert parsed["mcp_servers"]["files"]["env"] == {"LOG_LEVEL": "info"}
    assert parsed["mcp_servers"]["files"]["env_vars"] == ["ACP_SECRET_API_KEY"]
    codex_project = client.get("/mcp/export", params={"format": "codex", "project_id": project_a}).json()
    parsed = tomllib.loads(codex_project["content"])
    assert parsed["mcp_servers"]["github"]["enabled_tools"] == ["search"]
    assert "files" not in parsed["mcp_servers"]

    # Lecteur du projet A : export projet autorisé, export global et projet B refusés.
    viewer = _create_user(mcp_context, "viewer", "viewer", [("A", "viewer")])
    _authenticate(client, *viewer)
    assert client.get("/mcp/export", params={"format": "hermes", "project_id": project_a}).status_code == 200
    assert client.get("/mcp/export", params={"format": "hermes"}).status_code == 403
    assert (
        client.get(
            "/mcp/export", params={"format": "hermes", "project_id": mcp_context["projects"]["B"]["project_id"]}
        ).status_code
        == 403
    )


# --- instantané de mission --------------------------------------------------------------------


def test_mission_snapshot_is_frozen_after_a_later_revision(mcp_context):
    try:
        from acp_api.extensions import resolve_project_extensions
    except ImportError:
        pytest.skip("hook missions livré par l'agent B")
    client = mcp_context["client"]
    project = mcp_context["projects"]["A"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("frozen", secret_id)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200
    assert (
        client.post(
            f"/mcp/servers/{server['id']}/bindings",
            json={"project_id": project["project_id"], "allowed_tools": ["search"]},
        ).status_code
        == 201
    )

    mission = client.post(
        "/missions",
        headers={"Idempotency-Key": f"mcp-snapshot-{uuid4().hex}"},
        json={
            "project_id": project["project_id"],
            "agent_instance_id": project["agent_id"],
            "title": "Mission figée",
            "objective": "Vérifier l'instantané des extensions",
            "expected_outcome": "Un instantané figé",
            "acceptance_criteria": ["l'instantané ne change pas"],
            "autonomy": {
                "mode": "bounded",
                "allowed_actions": ["read"],
                "forbidden_actions": ["deploy"],
                "approval_required_actions": ["git_publish"],
            },
            "resources": [],
            "budget": {"max_tokens": 1000, "max_tool_calls": 10},
            "duration_seconds": 3600,
            "required_capabilities": ["git"],
        },
    )
    assert mission.status_code == 201, mission.text
    with mcp_context["session_factory"]() as db:
        snapshot = db.get(TaskModel, mission.json()["id"]).meta.get("extensions")
    if snapshot is None:
        pytest.skip("hook missions livré par l'agent B")
    assert [item["server_id"] for item in snapshot["mcp"]] == [server["id"]]
    assert snapshot["mcp"][0]["revision_number"] == 1

    client.post(
        f"/mcp/servers/{server['id']}/revisions",
        json={"config": _http_payload("frozen", secret_id, "https://other.example/mcp")["config"]},
    )
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200
    with mcp_context["session_factory"]() as db:
        assert db.get(TaskModel, mission.json()["id"]).meta["extensions"] == snapshot
        live = resolve_project_extensions(db, project["project_id"])
    assert live.mcp[0].revision_number == 2


# --- bindings et RBAC -------------------------------------------------------------------------


def test_binding_rules_and_project_scoped_secrets(mcp_context):
    client = mcp_context["client"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    project_b = mcp_context["projects"]["B"]["project_id"]
    secret_b = _create_secret(mcp_context, "PROJECT_B_TOKEN", HTTP_SECRET_VALUE, project_label="B")
    server = client.post("/mcp/servers", json=_http_payload("scoped", secret_b)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200

    other_project = client.post(
        f"/mcp/servers/{server['id']}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
    )
    assert other_project.status_code == 403
    binding = client.post(
        f"/mcp/servers/{server['id']}/bindings", json={"project_id": project_b, "allowed_tools": ["search"]}
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    assert client.patch(f"/mcp/bindings/{binding_id}", json={"allowed_tools": []}).status_code == 422
    assert client.patch(f"/mcp/bindings/{binding_id}", json={"allowed_tools": ["nope"]}).status_code == 422
    patched = client.patch(f"/mcp/bindings/{binding_id}", json={"allowed_tools": ["fetch"], "enabled": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["allowed_tools"] == ["fetch"] and patched.json()["enabled"] is False
    assert client.get(f"/mcp/bindings/{binding_id}").json()["enabled"] is False
    assert client.get("/mcp/bindings/unknown").status_code == 404

    removed = client.delete(f"/mcp/bindings/{binding_id}")
    assert removed.status_code == 200 and removed.json()["revoked_at"]
    assert client.delete(f"/mcp/bindings/{binding_id}").status_code == 409
    assert _events(mcp_context, "mcp.binding.revoked")
    # Un nouveau binding sur le même projet réutilise la ligne révoquée.
    again = client.post(
        f"/mcp/servers/{server['id']}/bindings", json={"project_id": project_b, "allowed_tools": ["search"]}
    )
    assert again.status_code == 201 and again.json()["id"] == binding_id
    assert again.json()["revoked_at"] is None and again.json()["enabled"] is True


def test_rbac_refusals(mcp_context):
    client = mcp_context["client"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("rbac", secret_id)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200
    stdio_secret = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    stdio = client.post(
        "/mcp/servers", json=_stdio_payload("rbac-stdio", stdio_secret, mcp_context["workers"]["real"]["worker_id"])
    ).json()
    pending = client.post(f"/mcp/servers/{stdio['id']}/probe").json()

    viewer = _create_user(mcp_context, "viewer", "viewer", [("A", "viewer")])
    member_a = _create_user(mcp_context, "member-a", "operator", [("A", "member")])
    member_b = _create_user(mcp_context, "member-b", "operator", [("B", "member")])

    mutations = [
        ("post", "/mcp/servers", _http_payload("viewer-server", secret_id)),
        ("post", f"/mcp/servers/{server['id']}/revisions", {"config": _http_payload("rbac", secret_id)["config"]}),
        ("post", f"/mcp/servers/{server['id']}/probe", None),
        ("post", f"/mcp/servers/{server['id']}/activate", None),
        ("post", f"/mcp/servers/{server['id']}/disable", None),
        ("post", f"/mcp/servers/{server['id']}/revoke", {"reason": "x"}),
        ("post", f"/mcp/servers/{server['id']}/rollback", {"revision_number": 1}),
        ("post", f"/mcp/probes/{pending['id']}/decision", {"decision": "approved"}),
        ("post", f"/mcp/servers/{server['id']}/bindings", {"project_id": project_a, "allowed_tools": ["search"]}),
    ]

    # Lecteur : lecture autorisée, toute mutation refusée.
    _authenticate(client, *viewer)
    assert client.get("/mcp/servers").status_code == 200
    assert client.get(f"/mcp/servers/{server['id']}").status_code == 200
    assert client.get("/mcp/probes").status_code == 200
    assert client.get("/mcp/bindings").status_code == 200
    for method, path, body in mutations:
        response = getattr(client, method)(path, json=body)
        assert response.status_code == 403, (path, response.text)

    # Membre du projet B : aucun binding sur le projet A, ni mutation propriétaire.
    _authenticate(client, *member_b)
    for method, path, body in mutations:
        response = getattr(client, method)(path, json=body)
        assert response.status_code == 403, (path, response.text)

    # Membre du projet A : bindings du projet A seulement.
    _authenticate(client, *member_a)
    for method, path, body in mutations[:-1]:
        response = getattr(client, method)(path, json=body)
        assert response.status_code == 403, (path, response.text)
    binding = client.post(
        f"/mcp/servers/{server['id']}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
    )
    assert binding.status_code == 201, binding.text
    assert client.patch(f"/mcp/bindings/{binding.json()['id']}", json={"enabled": False}).status_code == 200
    assert [row["id"] for row in client.get("/mcp/bindings").json()] == [binding.json()["id"]]

    _authenticate(client, *member_b)
    assert client.patch(f"/mcp/bindings/{binding.json()['id']}", json={"enabled": True}).status_code == 403
    assert client.delete(f"/mcp/bindings/{binding.json()['id']}").status_code == 403
    assert client.get("/mcp/bindings").json() == []
    assert client.get(f"/mcp/bindings/{binding.json()['id']}").status_code == 403

    _authenticate(client, *member_a)
    assert client.delete(f"/mcp/bindings/{binding.json()['id']}").status_code == 200

    # CSRF exigé ; session exigée.
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            f"/mcp/servers/{server['id']}/bindings", json={"project_id": project_a, "allowed_tools": ["search"]}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert client.get("/mcp/servers").status_code == 401
    assert client.get("/mcp/export", params={"format": "hermes"}).status_code == 401


# --- catalogue, risques et isolation du runner ---------------------------------------------------


def test_catalog_entries_are_accepted_by_the_creation_rules(mcp_context):
    """Une entrée du catalogue ne doit jamais proposer une configuration que la plateforme refuse."""

    client = mcp_context["client"]
    for entry in client.get("/mcp/catalog").json():
        created = client.post(
            "/mcp/servers",
            json={
                "name": entry["id"],
                "display_name": entry["display_name"],
                "source_kind": "catalog",
                "origin": entry["documentation_url"],
                "config": entry["config"],
            },
        )
        assert created.status_code == 201, (entry["id"], created.text)
        assert created.json()["source_kind"] == "catalog"
        for name in entry["required_secrets"]:
            # Le nom annoncé doit pouvoir être créé tel quel dans le coffre.
            assert client.post("/secrets", json={"name": name, "value": "x"}).status_code == 201


def test_http_without_tls_is_only_possible_through_the_allowlist_and_is_flagged(
    mcp_context, monkeypatch
):
    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    refused = client.post(
        "/mcp/servers", json=_http_payload("clair", secret_id, "http://intranet.example/mcp")
    )
    assert refused.status_code == 422 and "scheme_forbidden" in refused.json()["detail"]

    monkeypatch.setenv("ACP_OUTBOUND_PRIVATE_ALLOWLIST", "intranet.example")
    created = client.post(
        "/mcp/servers", json=_http_payload("clair", secret_id, "http://intranet.example/mcp")
    )
    assert created.status_code == 201, created.text
    flags = {flag["code"]: flag for flag in created.json()["current_revision"]["risk_flags"]}
    assert flags["http_without_tls"]["level"] == "danger"
    assert "clair" in flags["http_without_tls"]["message"]

    local = client.post(
        "/mcp/servers", json=_http_payload("local", secret_id, "https://localhost/mcp")
    )
    assert local.status_code == 201, local.text
    local_flags = {flag["code"] for flag in local.json()["current_revision"]["risk_flags"]}
    assert "localhost_target" in local_flags


def test_transport_cannot_change_across_revisions(mcp_context):
    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("stable", secret_id)).json()
    stdio_secret = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    swapped = client.post(
        f"/mcp/servers/{server['id']}/revisions",
        json={
            "config": _stdio_payload(
                "stable", stdio_secret, mcp_context["workers"]["real"]["worker_id"]
            )["config"]
        },
    )
    assert swapped.status_code == 422
    assert "transport" in swapped.json()["detail"]
    assert client.get(f"/mcp/servers/{server['id']}").json()["current_revision_number"] == 1


def test_a_probe_is_only_offered_to_the_designated_runner(mcp_context):
    client = mcp_context["client"]
    designated = mcp_context["workers"]["real"]
    other = mcp_context["register_worker"]("autre-runner", ["mcp_stdio_probe"], False)
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("cible", secret_id, designated["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    decision = client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})
    assert decision.status_code == 200, decision.text

    assert _claim(mcp_context, other).json()["probe"] is None
    assert client.get(f"/mcp/probes/{probe['id']}").json()["status"] == "queued"
    claimed = _claim(mcp_context, designated).json()["probe"]
    assert claimed is not None and claimed["id"] == probe["id"]


def test_claim_without_a_configured_vault_fails_the_probe_explicitly(mcp_context, monkeypatch):
    """Sans coffre, aucun lancement n'est proposé et le diagnostic est marqué en échec."""

    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("sans-coffre", secret_id, real["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})

    monkeypatch.delenv("ACP_SECRETS_KEYS", raising=False)
    claimed = _claim(mcp_context, real)
    assert claimed.status_code == 200 and claimed.json() == {"probe": None}
    failed = client.get(f"/mcp/probes/{probe['id']}").json()
    assert failed["status"] == "failed"
    assert "Coffre de secrets non configuré" in failed["error"]


def test_http_probe_without_a_configured_vault_fails_only_when_a_secret_is_referenced(
    mcp_context, monkeypatch
):
    """Sans référence de secret, le coffre n'est pas requis : le diagnostic reste possible."""

    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    with_secret = client.post("/mcp/servers", json=_http_payload("github", secret_id)).json()
    without_secret = client.post(
        "/mcp/servers", json=_http_payload_without_secret("sans-secret")
    )
    assert without_secret.status_code == 201, without_secret.text

    monkeypatch.delenv("ACP_SECRETS_KEYS", raising=False)

    refused = client.post(f"/mcp/servers/{with_secret['id']}/probe")
    assert refused.status_code == 200, refused.text
    assert refused.json()["status"] == "failed"
    assert "ACP_SECRETS_KEYS" in refused.json()["error"]
    assert mcp_context["fake"].seen == []

    # Aucun secret référencé : le diagnostic s'exécute et le serveur devient activable.
    probe = client.post(f"/mcp/servers/{without_secret.json()['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "succeeded", probe.json()["error"]
    assert mcp_context["fake"].seen
    assert client.post(f"/mcp/servers/{without_secret.json()['id']}/activate").status_code == 200


# --- expurgation des contenus renvoyés par un tiers ---------------------------------------------


def test_a_talkative_http_server_never_republishes_the_injected_secret(mcp_context):
    """Un serveur MCP qui réémet l'en-tête reçu ne doit rien publier de lisible (§0.3)."""

    client = mcp_context["client"]
    fake = mcp_context["fake"]
    fake.echo_header = "authorization"
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("bavard", secret_id)).json()

    probe = client.post(f"/mcp/servers/{server['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "succeeded", probe.json()["error"]
    # Le serveur a bien reçu la valeur : c'est ce qui rend la fuite possible sans expurgation.
    assert fake.seen[0].headers["authorization"] == HTTP_SECRET_VALUE
    _assert_no_secret_value(probe.text)
    assert probe.json()["result"]["server_info"]["authenticated_as"] == REDACTED

    detail = client.get(f"/mcp/servers/{server['id']}")
    assert detail.status_code == 200
    _assert_no_secret_value(detail.text)
    discovery = detail.json()["current_revision"]["discovery"]
    assert discovery["server_info"]["authenticated_as"] == REDACTED
    assert discovery["capabilities"]["echo"] == REDACTED
    tool = next(item for item in discovery["tools"] if item["name"] == "search")
    assert REDACTED in tool["description"] and HTTP_SECRET_VALUE not in tool["description"]
    assert tool["input_schema"]["title"] == REDACTED

    stored = client.get(f"/mcp/probes/{probe.json()['id']}")
    assert stored.status_code == 200
    _assert_no_secret_value(stored.text)

    # Un lecteur sans aucun accès projet lit les mêmes routes : rien ne doit y apparaître.
    reader = _create_user(mcp_context, "lecteur-bavard", "operator", [])
    _authenticate(client, *reader)
    _assert_no_secret_value(client.get(f"/mcp/servers/{server['id']}").text)
    _assert_no_secret_value(client.get(f"/mcp/probes/{probe.json()['id']}").text)


def test_an_error_message_quoting_the_secret_is_redacted(mcp_context):
    """Le message d'erreur d'un diagnostic échoué peut citer la réponse distante."""

    client = mcp_context["client"]
    fake = mcp_context["fake"]
    fake.echo_header = "authorization"
    fake.echo_as_jsonrpc_error = True
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("erreur", secret_id)).json()

    probe = client.post(f"/mcp/servers/{server['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "failed"
    assert REDACTED in probe.json()["error"]
    _assert_no_secret_value(probe.text)
    _assert_no_secret_value(client.get(f"/mcp/probes/{probe.json()['id']}").text)


def test_a_talkative_runner_result_is_redacted_by_the_server(mcp_context):
    """Le contrôle n'existe pas que dans le worker : l'API expurge ce que le runner poste."""

    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("runner-bavard", secret_id, real["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})
    claimed = _claim(mcp_context, real).json()["probe"]
    assert claimed["env"]["API_KEY"] == STDIO_SECRET_VALUE

    result = _stdio_result(["search"])
    result["server_info"] = {"name": "stdio-fake", "authenticated_as": STDIO_SECRET_VALUE}
    result["tools"][0]["description"] = f"jeton reçu : {STDIO_SECRET_VALUE}"
    result["stderr_tail"] = f"connexion avec {STDIO_SECRET_VALUE}"
    reported = _report(mcp_context, real, claimed["id"], result)

    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "succeeded"
    _assert_no_secret_value(reported.text)
    assert reported.json()["result"]["server_info"]["authenticated_as"] == REDACTED
    detail = client.get(f"/mcp/servers/{server_id}")
    _assert_no_secret_value(detail.text)
    assert REDACTED in detail.json()["current_revision"]["discovery"]["tools"][0]["description"]


def test_a_runner_result_is_refused_when_the_redaction_cannot_be_checked(
    mcp_context, monkeypatch
):
    """Coffre devenu illisible entre le claim et le résultat : échec explicite, rien d'écrit."""

    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("coffre-perdu", secret_id, real["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})
    claimed = _claim(mcp_context, real).json()["probe"]

    monkeypatch.delenv("ACP_SECRETS_KEYS", raising=False)
    result = _stdio_result(["search"])
    result["server_info"] = {"name": "stdio-fake", "authenticated_as": STDIO_SECRET_VALUE}
    reported = _report(mcp_context, real, claimed["id"], result)

    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "failed"
    assert "Coffre de secrets non configuré" in reported.json()["error"]
    _assert_no_secret_value(reported.text)
    detail = client.get(f"/mcp/servers/{server_id}")
    _assert_no_secret_value(detail.text)
    assert detail.json()["current_revision"]["discovery"] is None


def test_server_detail_only_exposes_bindings_of_accessible_projects(mcp_context):
    """Les rattachements nomment des projets : un utilisateur sans accès n'en voit aucun."""

    client = mcp_context["client"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("cloisonne", secret_id)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200
    binding = client.post(
        f"/mcp/servers/{server['id']}/bindings",
        json={"project_id": project_a, "allowed_tools": ["search"]},
    )
    assert binding.status_code == 201, binding.text

    owner_detail = client.get(f"/mcp/servers/{server['id']}").json()
    assert [row["project_id"] for row in owner_detail["bindings"]] == [project_a]
    assert owner_detail["binding_count"] == 1

    outsider = _create_user(mcp_context, "hors-projet", "operator", [])
    _authenticate(client, *outsider)
    assert client.get("/mcp/bindings").json() == []
    detail = client.get(f"/mcp/servers/{server['id']}")
    assert detail.status_code == 200
    assert detail.json()["bindings"] == []
    assert project_a not in detail.text
    # Le compteur reste global : l'existence d'un rattachement n'est pas cachée, seul le
    # projet concerné l'est.
    assert detail.json()["binding_count"] == 1

    member_a = _create_user(mcp_context, "membre-a", "operator", [("A", "member")])
    _authenticate(client, *member_a)
    assert [row["project_id"] for row in client.get(f"/mcp/servers/{server['id']}").json()["bindings"]] == [
        project_a
    ]


def test_http_probe_fails_explicitly_when_the_encryption_key_disappeared(mcp_context, monkeypatch):
    """Clé retirée de ACP_SECRETS_KEYS : le secret est illisible ⇒ échec explicite, jamais une 500."""

    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    server = client.post("/mcp/servers", json=_http_payload("cle-perdue", secret_id)).json()
    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())

    response = client.post(f"/mcp/servers/{server['id']}/probe")
    assert response.status_code == 200, response.text
    probe = response.json()
    assert probe["status"] == "failed"
    assert "GITHUB_TOKEN" in probe["error"] and "ACP_SECRETS_KEYS" in probe["error"]
    _assert_no_secret_value(probe["error"])
    assert mcp_context["fake"].seen == []
    # Le diagnostic est persisté : l'état reste consultable après coup.
    assert client.get(f"/mcp/probes/{probe['id']}").json()["status"] == "failed"


def test_claim_fails_the_probe_when_the_encryption_key_disappeared(mcp_context, monkeypatch):
    """Même règle côté runner : rien n'est distribué et le diagnostic ne reste pas « queued »."""

    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("cle-perdue", secret_id, real["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    approved = client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})
    assert approved.status_code == 200, approved.text

    monkeypatch.setenv("ACP_SECRETS_KEYS", generate_key())
    claimed = _claim(mcp_context, real)
    assert claimed.status_code == 200 and claimed.json() == {"probe": None}
    failed = client.get(f"/mcp/probes/{probe['id']}").json()
    assert failed["status"] == "failed"
    assert "API_KEY" in failed["error"] and "ACP_SECRETS_KEYS" in failed["error"]
    _assert_no_secret_value(failed["error"])


def test_activation_never_repoints_a_binding_onto_another_project_secret(mcp_context):
    """Le contrôle de portée vaut aussi à l'activation : une révision ne peut pas faire dériver un binding."""

    client = mcp_context["client"]
    project_a = mcp_context["projects"]["A"]["project_id"]
    platform_secret = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    secret_b = _create_secret(mcp_context, "PROJECT_B_TOKEN", HTTP_SECRET_VALUE, project_label="B")
    server = client.post("/mcp/servers", json=_http_payload("derive", platform_secret)).json()
    client.post(f"/mcp/servers/{server['id']}/probe")
    assert client.post(f"/mcp/servers/{server['id']}/activate").status_code == 200
    binding = client.post(
        f"/mcp/servers/{server['id']}/bindings",
        json={"project_id": project_a, "allowed_tools": ["search"]},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]
    assert binding.json()["revision_number"] == 1

    revised = client.post(
        f"/mcp/servers/{server['id']}/revisions",
        json={"config": _http_payload("derive", secret_b)["config"], "note": "bascule de secret"},
    )
    assert revised.status_code == 201, revised.text
    assert client.post(f"/mcp/servers/{server['id']}/probe").json()["status"] == "succeeded"
    activated = client.post(f"/mcp/servers/{server['id']}/activate")
    assert activated.status_code == 200, activated.text
    notes = activated.json()["apply_notes"]
    assert any("PROJECT_B_TOKEN" in note and project_a in note for note in notes)

    after = client.get(f"/mcp/bindings/{binding_id}").json()
    assert after["revision_number"] == 1, "le binding reste sur la révision qu'il a approuvée"
    assert after["enabled"] is False
    export = client.get("/mcp/export", params={"format": "hermes", "project_id": project_a}).json()
    assert export["placeholders"] == []
    assert "ACP_SECRET_PROJECT_B_TOKEN" not in export["content"]


def test_an_empty_runner_result_is_a_failure_not_a_discovery(mcp_context):
    """Un résultat sans version de protocole n'est pas une découverte : échec explicite."""

    client = mcp_context["client"]
    real = mcp_context["workers"]["real"]
    secret_id = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    server_id = client.post(
        "/mcp/servers", json=_stdio_payload("vide", secret_id, real["worker_id"])
    ).json()["id"]
    probe = client.post(f"/mcp/servers/{server_id}/probe").json()
    client.post(f"/mcp/probes/{probe['id']}/decision", json={"decision": "approved"})
    assert _claim(mcp_context, real).json()["probe"]["id"] == probe["id"]

    reported = _report(
        mcp_context,
        real,
        probe["id"],
        {
            "protocol_version": None,
            "server_info": None,
            "tools": [],
            "exit_code": 0,
            "stderr_tail": "",
            "duration_ms": 1,
            "error": None,
        },
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["status"] == "failed"
    assert "protocole" in reported.json()["error"]
    detail = client.get(f"/mcp/servers/{server_id}").json()
    assert detail["discovery_current"] is False and detail["tool_count"] == 0
    assert client.post(f"/mcp/servers/{server_id}/activate").status_code == 409


def test_hostile_header_and_env_names_are_refused(mcp_context):
    """Un en-tête ou une variable ne sont jamais construits à partir d'une saisie non contrôlée."""

    client = mcp_context["client"]
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    stdio_secret = _create_secret(mcp_context, "API_KEY", STDIO_SECRET_VALUE)
    real = mcp_context["workers"]["real"]["worker_id"]

    for headers, code in (
        ({"X-Bad\r\nInject": "1"}, "invalid_header_name"),
        ({"X Bad": "1"}, "invalid_header_name"),
        ({"X-Note": "ligne1\r\nX-Injected: 1"}, "invalid_header_value"),
        ({"X-Note": "valeur accentuée"}, "invalid_header_value"),
    ):
        payload = _http_payload("injection", secret_id)
        payload["config"]["http"]["headers"] = headers
        response = client.post("/mcp/servers", json=payload)
        assert response.status_code == 422, (headers, response.text)
        assert code in response.json()["detail"]

    for env, code in (
        ({"BAD=NAME": "1"}, "invalid_env_name"),
        ({"": "1"}, "invalid_env_name"),
        ({"LOG_LEVEL": "info\x00rm -rf"}, "invalid_env_value"),
    ):
        payload = _stdio_payload("injection", stdio_secret, real)
        payload["config"]["stdio"]["env"] = env
        response = client.post("/mcp/servers", json=payload)
        assert response.status_code == 422, (env, response.text)
        assert code in response.json()["detail"]


def test_a_non_ascii_secret_value_fails_the_probe_without_leaking_it(mcp_context):
    """Une valeur de secret inutilisable en en-tête HTTP produit un échec explicite, jamais un 500."""

    client = mcp_context["client"]
    value = "Bearer clé-accentuée"
    secret_id = _create_secret(mcp_context, "ACCENTED_TOKEN", value)
    server = client.post("/mcp/servers", json=_http_payload("accentue", secret_id)).json()
    probe = client.post(f"/mcp/servers/{server['id']}/probe")
    assert probe.status_code == 200, probe.text
    assert probe.json()["status"] == "failed"
    assert "Authorization" in probe.json()["error"]
    assert value not in probe.text and "accentuée" not in probe.json()["error"]
    assert mcp_context["fake"].seen == []


def test_exports_escape_hostile_header_values(mcp_context):
    """Une valeur d'en-tête est une donnée : elle ne doit jamais casser le fichier exporté."""

    client = mcp_context["client"]
    hostile = 'va"leur\\ avec # diese'
    secret_id = _create_secret(mcp_context, "GITHUB_TOKEN", HTTP_SECRET_VALUE)
    payload = _http_payload("hostile", secret_id)
    payload["config"]["http"]["headers"] = {"X-Note": hostile}
    created = client.post("/mcp/servers", json=payload)
    assert created.status_code == 201, created.text
    client.post(f"/mcp/servers/{created.json()['id']}/probe")
    assert client.post(f"/mcp/servers/{created.json()['id']}/activate").status_code == 200

    hermes = yaml.safe_load(client.get("/mcp/export", params={"format": "hermes"}).json()["content"])
    assert hermes["mcp_servers"]["hostile"]["headers"]["X-Note"] == hostile
    claude = json.loads(client.get("/mcp/export", params={"format": "claude"}).json()["content"])
    assert claude["mcpServers"]["hostile"]["headers"]["X-Note"] == hostile
    codex = tomllib.loads(client.get("/mcp/export", params={"format": "codex"}).json()["content"])
    assert codex["mcp_servers"]["hostile"]["http_headers"]["X-Note"] == hostile


@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("/usr/local/bin/npx", ["-y", "@scope/paquet@1.2.3", "/data"], None),
        ("/usr/local/bin/npx", ["-y", "@scope/paquet"], "@scope/paquet"),
        ("/usr/local/bin/uvx", ["mcp-server-git"], "mcp-server-git"),
        ("/usr/local/bin/uvx", ["mcp-server-git@0.6.0"], None),
        ("/usr/bin/pipx", ["run", "outil"], "outil"),
        ("/usr/bin/pipx", ["run", "outil==1.0"], None),
        ("/usr/bin/pipx", ["outil"], None),  # sans « run », pipx ne lance pas un paquet distant
        ("C:\\Program Files\\nodejs\\npx.cmd", ["-y", "paquet"], "paquet"),
        ("/opt/mcp/bin/server", ["--root", "/data"], None),
        # Une étiquette flottante n'est pas une version : elle autorise une mise à jour silencieuse.
        ("/usr/local/bin/npx", ["-y", "@scope/paquet@latest"], "@scope/paquet@latest"),
        ("/usr/local/bin/npx", ["-y", "paquet@next"], "paquet@next"),
        ("/usr/local/bin/npx", ["-y", "paquet@^1.0.0"], "paquet@^1.0.0"),
        ("/usr/local/bin/npx", ["-y", "paquet@~1.0.0"], "paquet@~1.0.0"),
        ("/usr/local/bin/npx", ["-y", "paquet@1.x"], "paquet@1.x"),
        ("/usr/local/bin/npx", ["-y", "paquet@"], "paquet@"),
        ("/usr/local/bin/uvx", ["mcp-server-git==latest"], "mcp-server-git==latest"),
        # Versions concrètes, y compris préversion et préfixe « v ».
        ("/usr/local/bin/npx", ["-y", "@scope/paquet@v2025.8.21"], None),
        ("/usr/local/bin/npx", ["-y", "paquet@1.0.0-rc.1"], None),
    ],
)
def test_unpinned_package_detection(command, args, expected):
    from acp_contracts import McpStdioConfig

    from acp_api.mcp.service import unpinned_package

    assert unpinned_package(McpStdioConfig(command=command, args=args)) == expected


@pytest.mark.parametrize(
    ("command", "absolute"),
    [
        ("/opt/mcp/bin/server", True),
        ("C:\\Program Files\\nodejs\\npx.cmd", True),
        ("\\\\serveur\\partage\\mcp.exe", True),
        ("npx", False),
        ("./server", False),
        ("", False),
    ],
)
def test_absolute_command_detection(command, absolute):
    from acp_api.mcp.service import is_absolute_command

    assert is_absolute_command(command) is absolute
