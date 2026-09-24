"""Proxy MCP de mission : autorisation vivante et réservation durable avant effet.

Le CLI ne reçoit ni URL amont ni secret du coffre. Une réponse d'outil perdue reste
indéterminée : aucun nouvel appel aval ne remplace cette preuve manquante.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from acp_contracts import BudgetPermitRequest, BudgetUsageDelta, McpServerConfig
from acp_contracts.redaction import redact_data, redaction_values
from acp_database.models import (
    McpBindingModel, McpExecutionCallModel, McpExecutionGrantModel,
    McpServerModel, McpServerRevisionModel, WorkerModel,
)

from ..budget_service import (
    BudgetContext, BudgetServiceError, begin_budget_write, load_worker_budget_context,
    record_usage, reserve_budget,
)
from ..outbound import OutboundPolicyError, PinnedHttpClient
from ..routers.workers import _as_utc, authenticate_worker, utcnow
from ..secrets_vault import VaultNotConfigured, get_vault
from .client import DEFAULT_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS, _McpSession
from .service import (
    canonical_fingerprint, ensure_transmittable_headers, foreign_project_secrets,
    resolve_secret_values, HeaderNotTransmittable, SecretResolutionError,
)

MAX_BODY_BYTES = 128_000
MAX_RESULT_BYTES = 1_000_000
_ACTIVE = {"preparing", "running"}


def canonical(value) -> str:
    """JSON déterministe, fini et stockable ; le contenu machine reste intact."""
    def check(item, depth=0):
        if depth > 64:
            raise ValueError("JSON trop profond")
        if isinstance(item, str) and "\0" in item:
            raise ValueError("NUL interdit")
        if isinstance(item, dict):
            for key, child in item.items():
                check(key, depth + 1)
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
    check(value)
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    result.encode("utf-8")
    return result


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _context(db, worker, run_id, fence) -> BudgetContext:
    try:
        context = load_worker_budget_context(db, worker=worker, run_id=run_id, fencing_token=fence)
    except BudgetServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    # Les verrous run/lease peuvent attendre ; les droits chargés avant cette
    # attente ne prouvent plus l'état courant du worker.
    db.refresh(worker)
    if (worker.status == "revoked" or worker.simulation
            or _as_utc(worker.token_expires_at) <= utcnow()
            or not (worker.global_access == 1 or worker.project_id == context.project.id)
            or not context.task.is_mission
            or context.task.active_run_id != context.run.id
            or context.run.status not in _ACTIVE or context.run.stop_requested_at is not None):
        raise HTTPException(409, "Cette tentative ne peut plus appeler d'outil MCP.")
    return context


def _extension(db, task, server_id, *, revision_id=None, granted_tools=None):
    entries = ((task.meta or {}).get("extensions") or {}).get("mcp", [])
    entry = next((item for item in entries if item.get("server_id") == server_id), None)
    server = db.get(McpServerModel, server_id)
    binding = db.query(McpBindingModel).filter_by(
        server_id=server_id, project_id=task.project_id, enabled=1, revoked_at=None,
    ).populate_existing().first()
    revision = None if binding is None else db.get(McpServerRevisionModel, binding.revision_id)
    if (entry is None or server is None or server.status != "active" or server.revoked_at is not None
            or binding is None or revision is None or revision.server_id != server.id
            or revision.number != entry.get("revision_number")
            or (revision_id is not None and revision.id != revision_id)):
        raise HTTPException(409, "La liaison MCP ou sa révision épinglée n'est plus autorisée.")
    config = McpServerConfig.model_validate(revision.config)
    if config.transport != "http" or server.transport != "http":
        raise HTTPException(409, "L'exécution MCP stdio protégée n'est pas disponible ; utiliser Streamable HTTP.")
    if (canonical_fingerprint(config) != revision.fingerprint
            or revision.discovery_fingerprint != revision.fingerprint or revision.discovered_at is None):
        raise HTTPException(409, "La découverte MCP ne correspond plus à la configuration approuvée.")
    if foreign_project_secrets(db, revision.config, task.project_id):
        raise HTTPException(403, "Cette configuration MCP référence le secret d'un autre projet.")
    allowed = set(entry.get("allowed_tools") or []) & set(binding.allowed_tools or [])
    if granted_tools is not None:
        allowed &= set(granted_tools)
    discovered = (revision.discovery or {}).get("tools") or []
    tools = [tool for tool in discovered if tool.get("name") in allowed]
    if len({tool.get("name") for tool in tools}) != len(tools):
        raise HTTPException(409, "La découverte MCP contient des outils ambigus.")
    return server, revision, config, tools


def issue_grants(db: Session, *, worker_id, run_id, authorization, fence, step_id, ttl_seconds):
    authenticate_worker(db, worker_id, authorization)
    begin_budget_write(db)
    worker = authenticate_worker(db, worker_id, authorization)
    context = _context(db, worker, run_id, fence)
    # _context a relu le worker après les verrous, y compris une rotation de clé.
    authenticate_worker(db, worker_id, authorization)
    entries = ((context.task.meta or {}).get("extensions") or {}).get("mcp", [])
    servers = []
    for entry in entries:
        server, revision, _, tools = _extension(db, context.task, entry.get("server_id"))
        token = secrets.token_urlsafe(32)
        grant = McpExecutionGrantModel(
            token_hash=_digest(token), worker_id=worker.id, worker_token_hash=worker.token_hash,
            task_run_id=run_id, fencing_token=fence, step_id=step_id, server_id=server.id,
            revision_id=revision.id, allowed_tools=[tool["name"] for tool in tools],
            expires_at=min(utcnow() + timedelta(seconds=ttl_seconds), _as_utc(worker.token_expires_at)),
        )
        db.add(grant)
        db.flush()
        servers.append({"server_id": server.id, "name": server.name, "revision_number": revision.number,
                        "allowed_tools": grant.allowed_tools, "url_path": f"/mcp/execution/{grant.id}",
                        "token": token, "expires_at": _as_utc(grant.expires_at).isoformat()})
    db.commit()
    return {"servers": servers}


def _check_grant(grant, token):
    if (grant is None or not token or len(token) > 256 or not hmac.compare_digest(grant.token_hash, _digest(token))
            or grant.revoked_at is not None or _as_utc(grant.expires_at) <= utcnow()):
        raise HTTPException(401, "Délégation MCP absente, expirée ou révoquée.")


def _check_grant_worker(grant, worker):
    if worker is None or not hmac.compare_digest(worker.token_hash, grant.worker_token_hash):
        raise HTTPException(401, "La délégation MCP ne correspond plus au worker courant.")


def authorize_grant(db: Session, grant_id: str, authorization: str | None):
    # Un commit sans expiration (workers/tests) ne doit pas conserver un état
    # antérieur à une révocation intervenue pendant un aller-retour réseau.
    db.expire_all()
    token = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    grant = db.get(McpExecutionGrantModel, grant_id)
    _check_grant(grant, token)
    worker = db.get(WorkerModel, grant.worker_id)
    _check_grant_worker(grant, worker)
    context = _context(db, worker, grant.task_run_id, grant.fencing_token)
    # Revalider après toute attente SQL, avant la moindre exécution distante.
    # _context vient aussi de rafraîchir et de valider l'état du worker.
    db.refresh(grant)
    _check_grant(grant, token)
    _check_grant_worker(grant, worker)
    server, revision, config, tools = _extension(
        db, context.task, grant.server_id, revision_id=grant.revision_id, granted_tools=grant.allowed_tools,
    )
    return grant, context, server, revision, config, tools


def _headers(db, config):
    refs = config.http.header_secrets
    if refs:
        try:
            vault = get_vault()
        except VaultNotConfigured:
            raise HTTPException(503, "Coffre MCP non configuré.") from None
        try:
            values = resolve_secret_values(db, vault, refs, purpose="mcp_execution")
        except SecretResolutionError:
            raise HTTPException(409, "Un secret MCP a été révoqué ou n'est plus accessible.") from None
    else:
        values = {}
    headers = {**config.http.headers, **values}
    try:
        ensure_transmittable_headers(headers)
    except HeaderNotTransmittable:
        raise HTTPException(409, "Un en-tête MCP n'est pas transmissible.") from None
    return headers, redaction_values(values)


def _replayed(call, request_hash):
    if call["request_hash"] != request_hash:
        raise HTTPException(409, "Cet identifiant RPC désigne déjà un autre appel MCP.")
    if call["status"] == "succeeded" and call["result"] is not None:
        return call["result"]
    if call["status"] == "denied":
        raise HTTPException(409, "Cet appel MCP a été refusé avant exécution.")
    raise HTTPException(409, "Résultat MCP indéterminé ou encore en cours ; aucun effet ne sera rejoué.")


async def call_tool(db, *, grant_id, authorization, rpc_id, name, arguments, policy, resolver, transport):
    # Authentifier avant d'acquérir le verrou d'écriture SQLite, puis tout relire.
    authorize_grant(db, grant_id, authorization)
    begin_budget_write(db)
    grant, context, server, revision, config, tools = authorize_grant(db, grant_id, authorization)
    if name not in {tool["name"] for tool in tools}:
        raise HTTPException(403, "Cet outil MCP n'est pas autorisé pour cette tentative.")
    call_key = _digest(canonical([context.run.id, grant.fencing_token, grant.step_id, server.id, rpc_id]))
    request_hash = _digest(canonical([revision.id, name, arguments]))
    existing = db.query(McpExecutionCallModel).filter_by(call_key=call_key).first()
    if existing is not None:
        cached = {"request_hash": existing.request_hash, "status": existing.status, "result": existing.result}
        # Libérer le verrou AVANT les refus409 ; le cleanup HTTP ne doit pas
        # devenir responsable de débloquer une autre requête en cours.
        db.commit()
        return _replayed(cached, request_hash)
    headers, redactions = _headers(db, config)
    try:
        policy.validate_url(config.http.url)
    except OutboundPolicyError:
        raise HTTPException(403, "L'origine MCP est refusée par la politique de sortie.") from None
    call = McpExecutionCallModel(
        call_key=call_key, task_run_id=context.run.id, server_id=server.id,
        revision_id=revision.id, step_id=grant.step_id, request_hash=request_hash,
        tool_name=name, status="pending",
    )
    db.add(call)
    # reserve_budget valide la réservation d'appel dans sa transaction : un crash
    # suivant laisse une preuve pending et une unité réservée, jamais un replay.
    permit_id = f"mcp-{call_key}"
    provider = f"mcp:{server.id}"
    try:
        decision = reserve_budget(db, context, BudgetPermitRequest(
            permit_id=permit_id, provider=provider, phase="tool", tool_calls=1,
        ))
    except BudgetServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    if not decision.permit_allowed:
        call.status, call.finished_at = "denied", utcnow()
        db.commit()
        raise HTTPException(409, "Le budget refuse l'appel MCP (borne dépassée ou consommation inconnue).")
    call_id = call.id
    try:
        # Une unité consommée avant dispatch reste comptée même si l'effet distant
        # ou son rapport est perdu. Aucune estimation monétaire n'est inventée.
        begin_budget_write(db)
        _, context, _, _, config, _ = authorize_grant(db, grant_id, authorization)
        record_usage(db, context, BudgetUsageDelta(
            report_id=f"mcp-used-{call_key}", permit_id=permit_id, provider=provider,
            phase="tool", source="platform", tool_calls=1,
        ))
        pinned = PinnedHttpClient(policy, resolver, transport=transport, max_redirects=0,
                                  max_body_bytes=MAX_RESULT_BYTES, timeout=float(config.http.timeout_seconds))
        session = _McpSession(pinned, config.http.url, headers, DEFAULT_PROTOCOL_VERSION)
        try:
            initialized = await session.call(1, "initialize", {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "agent-company-platform-execution", "version": "1"},
            })
            version = initialized.get("protocolVersion")
            if version not in SUPPORTED_PROTOCOL_VERSIONS:
                raise ValueError("Protocole MCP non supporté")
            session.negotiated_protocol_version = version
            await session.notify("notifications/initialized")
            # Le handshake peut durer : stop, bail, révision et secrets sont relus
            # juste avant le seul appel d'outil aval, sans transaction réseau.
            db.rollback()
            _, _, _, _, current_config, current_tools = authorize_grant(db, grant_id, authorization)
            if name not in {tool["name"] for tool in current_tools}:
                raise HTTPException(403, "Outil MCP révoqué pendant la négociation.")
            session.base_headers, latest_redactions = _headers(db, current_config)
            redactions = tuple(sorted(set(redactions) | set(latest_redactions), key=len, reverse=True))
            db.commit()
            result = await session.call(2, "tools/call", {"name": name, "arguments": arguments})
            if not isinstance(result.get("content"), list) or ("isError" in result and type(result["isError"]) is not bool):
                raise ValueError("Résultat tools/call invalide")
            result = redact_data(result, redactions)
            if len(canonical(result).encode("utf-8")) > MAX_RESULT_BYTES:
                raise ValueError("Résultat MCP trop volumineux")
        finally:
            await session.close()
        db.rollback()
        call = db.get(McpExecutionCallModel, call_id)
        call.status, call.result, call.finished_at = "succeeded", result, utcnow()
        db.commit()
        authorize_grant(db, grant_id, authorization)
        db.commit()
        return result
    except (Exception, asyncio.CancelledError):
        db.rollback()
        call = db.get(McpExecutionCallModel, call_id)
        if call is not None and call.status == "pending":
            call.status, call.finished_at = "unknown", utcnow()
            db.commit()
        # Aucun détail transport, URL ou texte amont non expurgé ne traverse le proxy.
        raise HTTPException(409, "L'appel MCP n'a pas de résultat confirmé ; aucun effet ne sera rejoué.") from None


def call_tool_sync(db, **kwargs):
    """Exécution dans le pool HTTP : les verrous SQL ne bloquent pas la boucle ASGI."""
    return asyncio.run(call_tool(db, **kwargs))
