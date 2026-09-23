"""Effets MCP simulés : aucun réseau réel, aucune base utilisateur."""

import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from acp_api.deps import get_db
from acp_api.mcp.service import canonical_fingerprint
from acp_api.routers import mcp_execution
from acp_api.routers.mcp import get_dns_resolver, get_http_transport
from acp_api.routers.workers import _token_hash
from acp_api.secrets_vault import get_vault
from acp_contracts import McpServerConfig
from acp_database.models import (
    BudgetUsageReportModel, McpBindingModel, McpExecutionCallModel, McpExecutionGrantModel,
    McpServerModel, McpServerRevisionModel, OrganizationModel, ProjectModel, SecretModel,
    TaskModel, TaskRunModel, UserModel, WorkerLeaseModel, WorkerModel, WorkspaceModel,
)
from acp_database.testing import make_test_engine


@pytest.fixture
def proxy(tmp_path, monkeypatch):
    database = make_test_engine(tmp_path, concurrent=True)
    factory = sessionmaker(bind=database.engine, expire_on_commit=False)
    token = "synthetic-worker-mcp-token"
    injected = "synthetic-upstream-only-secret"
    monkeypatch.setenv("ACP_SECRETS_KEYS", Fernet.generate_key().decode())
    monkeypatch.setenv("ACP_EVENT_RELAY_ENABLED", "1")
    with factory() as db:
        user = UserModel(login_normalized="proxy-owner", display_name="Test", password_hash="test")
        org = OrganizationModel(name="MCP test")
        db.add_all([user, org]); db.flush()
        workspace = WorkspaceModel(name="MCP", organization_id=org.id)
        db.add(workspace); db.flush()
        project = ProjectModel(name="MCP", workspace_id=workspace.id)
        db.add(project); db.flush()
        worker = WorkerModel(name="MCP worker", token_hash=_token_hash(token), token_prefix="test",
                             token_expires_at=datetime.now(UTC) + timedelta(days=1), project_id=project.id,
                             global_access=0, status="online", simulation=0)
        db.add(worker); db.flush()
        task = TaskModel(title="Mission", project_id=project.id, is_mission=1,
                         budget={"max_tool_calls": 10, "currency": "EUR"}, duration_seconds=3600,
                         status="in_progress")
        db.add(task); db.flush()
        run = TaskRunModel(task_id=task.id, status="running", fencing_token=3)
        db.add(run); db.flush(); task.active_run_id = run.id
        lease = WorkerLeaseModel(worker_id=worker.id, task_id=task.id, task_run_id=run.id,
                                 status="active", lease_expires_at=datetime.now(UTC) + timedelta(hours=1))
        db.add(lease)
        key_id, encrypted = get_vault().encrypt(injected)
        secret = SecretModel(name="test-key", scope_type="project", project_id=project.id,
                             key_id=key_id, ciphertext=encrypted, created_by_user_id=user.id)
        db.add(secret); db.flush()
        config = McpServerConfig.model_validate({"transport": "http", "http": {
            "url": "https://mcp.example/tools", "header_secrets": {"X-Test-Secret": {"secret_id": secret.id}},
        }})
        server = McpServerModel(name="notes", display_name="Notes", transport="http",
                                execution_location="platform", source_kind="manual", status="active",
                                created_by_user_id=user.id)
        db.add(server); db.flush()
        fingerprint = canonical_fingerprint(config)
        revision = McpServerRevisionModel(server_id=server.id, number=1, config=config.model_dump(mode="json"),
            fingerprint=fingerprint, discovery_fingerprint=fingerprint, discovered_at=datetime.now(UTC),
            discovery={"tools": [{"name": "read_note", "description": "Lire", "input_schema": {"type": "object"}},
                                 {"name": "delete_note", "input_schema": {"type": "object"}}]},
            created_by_user_id=user.id)
        db.add(revision); db.flush(); server.current_revision_id = revision.id
        binding = McpBindingModel(server_id=server.id, project_id=project.id, revision_id=revision.id,
                                  allowed_tools=["read_note"], created_by_user_id=user.id)
        db.add(binding)
        task.meta = {"extensions": {"mcp": [{"server_id": server.id, "revision_number": 1,
                                               "allowed_tools": ["read_note"]}]}}
        db.commit()
        ids = {"worker": worker.id, "run": run.id, "task": task.id, "server": server.id,
               "revision": revision.id, "binding": binding.id, "lease": lease.id, "secret": secret.id}
    calls = []
    behavior = {"fail": False, "handshake": None, "redirect": False, "tool_gate": None, "result": None}
    def handler(request):
        assert request.url.host == "8.8.8.8"
        assert request.headers["Host"] == "mcp.example"
        assert request.headers["X-Test-Secret"] == injected
        if request.method == "DELETE":
            return httpx.Response(204)
        message = json.loads(request.content)
        calls.append(message)
        if message["method"] == "initialize":
            if behavior["handshake"]:
                behavior["handshake"]()
            return httpx.Response(200, headers={"Mcp-Session-Id": "test-session"},
                json={"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}})
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert message["method"] == "tools/call"
        # Le ledger prouve la consommation AVANT le premier effet externe.
        with factory() as db:
            assert db.query(BudgetUsageReportModel).filter_by(kind="usage", phase="tool").count() >= 1
        if behavior["tool_gate"]:
            behavior["tool_gate"]()
        if behavior["fail"]:
            raise httpx.ReadError("perte après effet " + injected, request=request)
        if behavior["redirect"]:
            return httpx.Response(307, headers={"Location": "https://other.example/tools"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": behavior["result"] or {
            "content": [{"type": "text", "text": "note " + injected}], "isError": False}})
    app = FastAPI(); app.include_router(mcp_execution.router)
    def db_dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    app.dependency_overrides[get_dns_resolver] = lambda: lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    with TestClient(app) as client:
        yield {"app": app, "client": client, "factory": factory, "ids": ids, "calls": calls,
               "behavior": behavior, "worker_token": token, "upstream_secret": injected}
    database.close()


def _grant(proxy, *, step="step-1"):
    ids = proxy["ids"]
    result = proxy["client"].post(f"/work/workers/{ids['worker']}/runs/{ids['run']}/mcp/grants",
        headers={"Authorization": "Bearer " + proxy["worker_token"], "X-Attempt-Fencing-Token": "3"},
        json={"step_id": step})
    assert result.status_code == 200, result.text
    assert result.headers["Cache-Control"] == "no-store"
    assert datetime.fromisoformat(result.json()["servers"][0]["expires_at"]).utcoffset() == timedelta(0)
    return result.json()["servers"][0]


def _rpc(proxy, grant, method="tools/call", *, rpc_id=5, name="read_note", arguments=None):
    params = {"name": name, "arguments": arguments or {}} if method == "tools/call" else {}
    return proxy["client"].post(grant["url_path"], headers={"Authorization": "Bearer " + grant["token"]},
                                json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})


def _tool_calls(proxy):
    return [message for message in proxy["calls"] if message["method"] == "tools/call"]


def test_proxy_descriptors_budget_redaction_and_regrant_dedup(proxy):
    grant = _grant(proxy)
    assert proxy["upstream_secret"] not in json.dumps(grant)
    assert "mcp.example" not in json.dumps(grant)
    with proxy["factory"]() as db:
        row = db.query(McpExecutionGrantModel).one()
        assert row.token_hash != grant["token"]
    assert _rpc(proxy, grant, "initialize").json()["result"]["protocolVersion"] == "2025-06-18"
    listed = _rpc(proxy, grant, "tools/list").json()["result"]["tools"]
    assert [tool["name"] for tool in listed] == ["read_note"]
    assert proxy["calls"] == []
    result = _rpc(proxy, grant)
    assert result.status_code == 200, result.text
    assert result.json()["result"]["content"][0]["text"] == "note ***"
    assert proxy["upstream_secret"] not in result.text
    # Nouveau jeton après redémarrage du client : même scope d'appel durable.
    replay = _rpc(proxy, _grant(proxy))
    assert replay.json() == result.json()
    assert len(_tool_calls(proxy)) == 1
    with proxy["factory"]() as db:
        call = db.query(McpExecutionCallModel).one()
        assert call.status == "succeeded"
        assert proxy["upstream_secret"] not in json.dumps(call.result)
        usage = db.query(BudgetUsageReportModel).filter_by(kind="usage").all()
        assert len(usage) == 1 and usage[0].tool_calls == 1


def test_call_id_reuse_with_other_body_is_rejected_but_distinct_steps_are_independent(proxy):
    grant = _grant(proxy)
    assert _rpc(proxy, grant).status_code == 200
    assert _rpc(proxy, grant, arguments={"different": True}).status_code == 409
    assert _rpc(proxy, _grant(proxy, step="step-2")).status_code == 200
    assert len(_tool_calls(proxy)) == 2


@pytest.mark.parametrize("failure", ["fail", "redirect"])
def test_ambiguous_tool_effect_is_never_replayed_or_redirected(proxy, failure):
    proxy["behavior"][failure] = True
    grant = _grant(proxy)
    first = _rpc(proxy, grant)
    assert first.status_code == 409
    assert proxy["upstream_secret"] not in first.text
    proxy["behavior"][failure] = False
    assert _rpc(proxy, _grant(proxy)).status_code == 409
    assert len(_tool_calls(proxy)) == 1
    with proxy["factory"]() as db:
        assert db.query(McpExecutionCallModel).one().status == "unknown"


@pytest.mark.parametrize("reason", ["stop", "lease", "fence", "worker", "scope", "rotation", "binding", "tools", "revision", "expiry", "secret"])
def test_revocation_is_live_for_each_call(proxy, reason):
    grant = _grant(proxy)
    with proxy["factory"]() as db:
        ids = proxy["ids"]
        if reason == "stop": db.get(TaskRunModel, ids["run"]).status = "stopping"
        if reason == "lease": db.get(WorkerLeaseModel, ids["lease"]).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if reason == "fence": db.get(TaskRunModel, ids["run"]).fencing_token = 4
        if reason == "worker": db.get(WorkerModel, ids["worker"]).status = "revoked"
        if reason == "scope": db.get(WorkerModel, ids["worker"]).project_id = None
        if reason == "rotation": db.get(WorkerModel, ids["worker"]).token_hash = "0" * 64
        if reason == "binding": db.get(McpBindingModel, ids["binding"]).enabled = 0
        if reason == "tools": db.get(McpBindingModel, ids["binding"]).allowed_tools = []
        if reason == "revision": db.get(McpServerRevisionModel, ids["revision"]).fingerprint = "0" * 64
        if reason == "expiry": db.query(McpExecutionGrantModel).one().expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if reason == "secret": db.get(SecretModel, ids["secret"]).revoked_at = datetime.now(UTC)
        db.commit()
    result = _rpc(proxy, grant)
    assert result.status_code in {401, 403, 409}, result.text
    assert _tool_calls(proxy) == []


@pytest.mark.parametrize("reason", ["stop", "secret", "tools"])
def test_revocation_during_handshake_prevents_tool_dispatch(proxy, reason):
    grant = _grant(proxy)
    def revoke():
        with proxy["factory"]() as db:
            if reason == "stop": db.get(TaskRunModel, proxy["ids"]["run"]).status = "stopping"
            if reason == "secret": db.get(SecretModel, proxy["ids"]["secret"]).revoked_at = datetime.now(UTC)
            if reason == "tools": db.get(McpBindingModel, proxy["ids"]["binding"]).allowed_tools = []
            db.commit()
    proxy["behavior"]["handshake"] = revoke
    assert _rpc(proxy, grant).status_code == 409
    assert _tool_calls(proxy) == []


@pytest.mark.parametrize("reason", ["expiry", "grant_revoked", "worker_revoked", "worker_rotation"])
def test_authorization_is_rechecked_after_context_lock_wait(proxy, monkeypatch, reason):
    from acp_api.mcp import execution

    grant = _grant(proxy)
    with proxy["factory"]() as db:
        deadline = db.query(McpExecutionGrantModel).one().expires_at
    clock = {"now": execution.utcnow(), "post_handshake": False, "waited": False}
    original_context = execution.load_worker_budget_context

    def after_context_wait(db, **kwargs):
        context = original_context(db, **kwargs)
        if clock["post_handshake"] and not clock["waited"]:
            clock["waited"] = True
            # Simule une attente des verrous run/lease, après lecture du jeton
            # et du worker mais avant la remise du contexte au proxy.
            if reason == "expiry":
                clock["now"] = deadline + timedelta(seconds=1)
            else:
                # Une écriture SQL indépendante de l'identity map rend la
                # relecture obligatoire, sans modifier les objets déjà chargés.
                if reason == "grant_revoked":
                    db.query(McpExecutionGrantModel).filter_by(id=grant["url_path"].rsplit("/", 1)[1]).update(
                        {"revoked_at": clock["now"]}, synchronize_session=False)
                else:
                    field, value = ("status", "revoked") if reason == "worker_revoked" else ("token_hash", "0" * 64)
                    db.query(WorkerModel).filter_by(id=proxy["ids"]["worker"]).update(
                        {field: value}, synchronize_session=False)
        return context

    monkeypatch.setattr(execution, "load_worker_budget_context", after_context_wait)
    monkeypatch.setattr(execution, "utcnow", lambda: clock["now"])
    proxy["behavior"]["handshake"] = lambda: clock.update(post_handshake=True)
    assert _rpc(proxy, grant).status_code == 409
    assert clock["waited"]
    assert _tool_calls(proxy) == []
    with proxy["factory"]() as db:
        call = db.query(McpExecutionCallModel).one()
        assert call.status == "unknown" and call.result is None


def test_proxy_authorization_lock_wait_does_not_block_the_http_event_loop(proxy, monkeypatch):
    from acp_api.mcp import execution

    grant = _grant(proxy)
    entered, release = threading.Event(), threading.Event()
    original_authorize = execution.authorize_grant

    def waiting_authorize(*args, **kwargs):
        entered.set()
        assert release.wait(5), "L'attente SQL doit laisser la boucle HTTP disponible."
        return original_authorize(*args, **kwargs)

    @proxy["app"].get("/test-event-loop")
    async def event_loop_probe():
        return {"responsive": True}

    monkeypatch.setattr(execution, "authorize_grant", waiting_authorize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(_rpc, proxy, grant, "tools/list")
        assert entered.wait(5)
        try:
            probe = pool.submit(proxy["client"].get, "/test-event-loop").result(timeout=2)
            assert probe.status_code == 200 and probe.json() == {"responsive": True}
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200
    assert proxy["calls"] == []


@pytest.mark.parametrize("budget", [{"max_tool_calls": 0}, {"max_cost": 1, "currency": "EUR"}])
def test_budget_refuses_before_any_remote_call(proxy, budget):
    grant = _grant(proxy)
    with proxy["factory"]() as db:
        db.get(TaskModel, proxy["ids"]["task"]).budget = budget
        db.commit()
    response = _rpc(proxy, grant)
    assert response.status_code == 409, response.text
    assert proxy["calls"] == []


def test_concurrent_same_tool_call_has_one_remote_effect(proxy):
    grant = _grant(proxy)
    entered, release = threading.Event(), threading.Event()
    def keep_effect_in_flight():
        entered.set()
        assert release.wait(5), "L'appel concurrent doit pouvoir être refusé sans attendre le tiers."
    proxy["behavior"]["tool_gate"] = keep_effect_in_flight
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_rpc, proxy, grant)
        assert entered.wait(5)
        try:
            second = pool.submit(_rpc, proxy, grant).result(timeout=5)
            assert second.status_code == 409
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert len(_tool_calls(proxy)) == 1


def test_unknown_tool_and_stdio_are_explicitly_refused(proxy):
    grant = _grant(proxy)
    assert _rpc(proxy, grant, name="delete_note").status_code == 403
    with proxy["factory"]() as db:
        db.get(McpServerModel, proxy["ids"]["server"]).transport = "stdio"
        db.commit()
    response = _rpc(proxy, grant)
    assert response.status_code == 409 and "stdio" in response.text
    assert proxy["calls"] == []


def test_rpc_size_shape_origin_and_closed_grant_are_guarded(proxy):
    grant = _grant(proxy)
    headers = {"Authorization": "Bearer " + grant["token"]}
    assert proxy["client"].post(grant["url_path"], headers={**headers, "Origin": "https://evil.test"}, json={}).status_code == 403
    assert proxy["client"].post(grant["url_path"], headers=headers, content=b"x" * 128001).status_code == 413
    for raw in [b'{"jsonrpc":"2.0","jsonrpc":"2.0"}', b'{"value":NaN}', b'[]']:
        assert proxy["client"].post(grant["url_path"], headers=headers, content=raw).status_code == 400
    assert proxy["client"].delete(grant["url_path"], headers=headers).status_code == 204
    assert _rpc(proxy, grant).status_code == 401
    assert proxy["calls"] == []


def test_dns_rebinding_is_blocked_before_any_request_to_the_server(proxy):
    grant = _grant(proxy)
    proxy["app"].dependency_overrides[get_dns_resolver] = lambda: lambda *args: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    assert _rpc(proxy, grant).status_code == 409
    assert proxy["calls"] == []


@pytest.mark.parametrize("result", [{"content": "not-a-list"},
    {"content": [], "isError": "false"}, {"content": [{"type": "text", "text": "bad\0value"}]}])
def test_invalid_machine_result_is_not_stored_or_returned_as_success(proxy, result):
    grant = _grant(proxy)
    proxy["behavior"]["result"] = result
    assert _rpc(proxy, grant).status_code == 409
    with proxy["factory"]() as db:
        call = db.query(McpExecutionCallModel).one()
        assert call.status == "unknown" and call.result is None
    assert _rpc(proxy, grant).status_code == 409
    assert len(_tool_calls(proxy)) == 1


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad", "X-Attempt-Fencing-Token": "3"},
    {"Authorization": "Bearer synthetic-worker-mcp-token", "X-Attempt-Fencing-Token": "4"}])
def test_only_authenticated_current_worker_can_delegate(proxy, headers):
    ids = proxy["ids"]
    response = proxy["client"].post(f"/work/workers/{ids['worker']}/runs/{ids['run']}/mcp/grants",
                                     headers=headers, json={"step_id": "step-1"})
    assert response.status_code in {401, 409}
    with proxy["factory"]() as db:
        assert db.query(McpExecutionGrantModel).count() == 0


def test_schema_rollback_keeps_active_attempt_call_identity(proxy):
    from acp_database.migrate import current_revision, run_downgrade, run_stamp, run_upgrade
    from acp_database.schema_state import head_revision
    from sqlalchemy import inspect

    engine = proxy["factory"].kw["bind"]
    run_stamp(engine, "head")
    assert _rpc(proxy, _grant(proxy)).status_code == 200
    with pytest.raises(RuntimeError, match="tentative active"):
        run_downgrade(engine, "0003")
    assert current_revision(engine) == head_revision()
    with proxy["factory"]() as db:
        assert db.query(McpExecutionCallModel).count() == 1
        db.get(TaskRunModel, proxy["ids"]["run"]).status = "succeeded"
        db.commit()
    run_downgrade(engine, "0003")
    assert not inspect(engine).has_table("mcp_execution_calls")
    run_upgrade(engine)
    assert inspect(engine).has_table("mcp_execution_calls")
