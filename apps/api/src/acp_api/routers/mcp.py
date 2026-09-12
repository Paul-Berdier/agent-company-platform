"""Routes du centre MCP (``/mcp``) : catalogue, serveurs, révisions, probes, bindings, export.

Aucune route utilisateur ne renvoie une valeur de secret. Seule la route de claim, réservée
à un runner authentifié doté de la capacité ``mcp_stdio_probe`` et non simulé, reçoit les
valeurs résolues, avec ``Cache-Control: no-store``.

Les routes d'import (``/mcp/import/*``) sont déclarées en fin de module et s'appuient sur
``mcp.importers`` : le contenu importé est une donnée non fiable, son aperçu ne renvoie que des
candidats de secrets masqués et rien n'est créé sans choix explicite.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from acp_contracts import (
    McpBinding,
    McpBindingCreate,
    McpBindingPatch,
    McpCatalogEntry,
    McpExport,
    McpExportFormat,
    McpImportApplyRequest,
    McpImportApplyResult,
    McpImportPreview,
    McpImportPreviewRequest,
    McpProbe,
    McpProbeDecision,
    McpProbeResult,
    McpRevokeRequest,
    McpRollbackRequest,
    McpServerCreate,
    McpServerDetail,
    McpServerRevisionCreate,
    McpServerSummary,
)
from acp_database.models import (
    McpBindingModel,
    McpProbeModel,
    McpServerModel,
    McpServerRevisionModel,
    ProjectModel,
    SecretModel,
    WorkerModel,
)

from ..deps import (
    accessible_project_ids,
    ensure_access,
    get_db,
    get_principal,
    require_platform_role,
)
from ..mcp import importers, service
from ..mcp.service import ConfigRefused, SecretResolutionError
from ..outbound import OutboundPolicy
from ..secrets_vault import SecretsVault, VaultNotConfigured, get_vault
from .workers import authenticate_worker

router = APIRouter(prefix="/mcp", tags=["mcp"])

CATALOG_PATH = Path(__file__).resolve().parent.parent / "mcp" / "catalog.json"


# --- dépendances injectables (aucun réseau réel dans les tests) --------------------------------


def get_dns_resolver() -> Callable[..., object]:
    """Résolveur DNS utilisé par la politique de sortie ; remplacé dans les tests."""

    return socket.getaddrinfo


def get_http_transport() -> httpx.BaseTransport | None:
    """Transport httpx du probe HTTP ; remplacé par un ``MockTransport`` dans les tests."""

    return None


@lru_cache(maxsize=1)
def _catalog_payload() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _policy() -> OutboundPolicy:
    """Politique de sortie relue à chaque requête (l'allowlist peut changer à chaud)."""

    try:
        return OutboundPolicy.from_environ(os.environ)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Politique de sortie invalide : {exc}") from exc


def _vault_or_503() -> SecretsVault:
    try:
        return get_vault(os.environ)
    except VaultNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _optional_vault() -> SecretsVault | None:
    try:
        return get_vault(os.environ)
    except VaultNotConfigured:
        return None


# --- helpers -------------------------------------------------------------------------------------


def _server_or_404(db: Session, server_id: str) -> McpServerModel:
    server = db.get(McpServerModel, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Serveur MCP introuvable")
    return server


def _mutable_server(db: Session, server_id: str) -> McpServerModel:
    """Un serveur révoqué est définitif : toute mutation est refusée, l'historique reste lisible."""

    server = _server_or_404(db, server_id)
    if server.status == "revoked":
        raise HTTPException(
            status_code=409,
            detail="Serveur révoqué : la révocation est irréversible, créez un nouveau serveur.",
        )
    return server


def _current_revision_or_409(db: Session, server: McpServerModel) -> McpServerRevisionModel:
    revision = service.current_revision(db, server)
    if revision is None:
        raise HTTPException(status_code=409, detail="Serveur sans révision courante")
    return revision


def _check_secret_references(db: Session, config) -> None:
    """Les références de secrets doivent exister ; aucune valeur n'est lue ici."""

    for secret_id in sorted(service.secret_ids_in_config(config.model_dump(mode="json"))):
        if db.get(SecretModel, secret_id) is None:
            raise HTTPException(
                status_code=422,
                detail=f"Référence invalide : le secret {secret_id!r} n'existe pas dans le coffre.",
            )


def _validated_config(db: Session, config):
    """Contrôle politique + références ; lève une 422 au message explicite."""

    try:
        flags = service.validate_config(config, _policy())
    except ConfigRefused as exc:
        raise HTTPException(
            status_code=422, detail=f"Configuration refusée ({exc.code}) : {exc}"
        ) from exc
    _check_secret_references(db, config)
    return flags


def _check_target_worker(db: Session, config, target_worker_id: str | None) -> None:
    if config.transport != "stdio":
        return
    if target_worker_id is None:
        return
    if db.get(WorkerModel, target_worker_id) is None:
        raise HTTPException(status_code=404, detail="Runner désigné introuvable")


def _binding_or_404(db: Session, binding_id: str) -> McpBindingModel:
    binding = db.get(McpBindingModel, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Binding introuvable")
    return binding


def _project_or_404(db: Session, project_id: str) -> ProjectModel:
    project = db.get(ProjectModel, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return project


def _check_project_scoped_secrets(db: Session, revision: McpServerRevisionModel, project_id: str) -> None:
    """Un secret de portée projet ne peut servir qu'au projet auquel il appartient."""

    foreign = service.foreign_project_secrets(db, revision.config or {}, project_id)
    if foreign:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Le secret « {foreign[0]} » appartient à un autre projet : "
                "créez un secret propre à ce projet ou utilisez un secret de plateforme."
            ),
        )


def _validate_tools(revision: McpServerRevisionModel, tools: list[str]) -> list[str]:
    known = service.discovered_tool_names(revision)
    unknown = [tool for tool in tools if tool not in known]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Outils inconnus pour la révision courante : {', '.join(unknown)}. "
                f"Outils découverts : {', '.join(known) or 'aucun'}."
            ),
        )
    seen: list[str] = []
    for tool in tools:
        if tool not in seen:
            seen.append(tool)
    return seen


def _authenticated_worker(
    db: Session, worker_id: str | None, authorization: str | None
) -> WorkerModel:
    if not worker_id:
        raise HTTPException(status_code=401, detail="Identifiant de worker manquant")
    return authenticate_worker(db, worker_id, authorization)


# --- catalogue --------------------------------------------------------------------------------


@router.get("/catalog", response_model=list[McpCatalogEntry])
def list_catalog(principal: str = Depends(get_principal)):
    """Catalogue statique documenté (aucune exécution n'a été faite pour le constituer)."""

    return [McpCatalogEntry.model_validate(entry) for entry in _catalog_payload()]


# --- serveurs ----------------------------------------------------------------------------------


@router.post("/servers", response_model=McpServerDetail, status_code=201)
def create_server(
    body: McpServerCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    if db.query(McpServerModel).filter_by(name=body.name).first() is not None:
        raise HTTPException(
            status_code=409, detail=f"Un serveur MCP nommé « {body.name} » existe déjà"
        )
    flags = _validated_config(db, body.config)
    _check_target_worker(db, body.config, body.target_worker_id)
    server = McpServerModel(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        source_kind=body.source_kind,
        origin=body.origin,
        transport=body.config.transport,
        execution_location=body.config.execution_location,
        status="draft",
        target_worker_id=body.target_worker_id if body.config.transport == "stdio" else None,
        created_by_user_id=principal,
    )
    db.add(server)
    db.flush()
    revision = service.create_revision(
        db, server, body.config, principal=principal, note=body.note, risk_flags=flags
    )
    service.record_event(
        db,
        "mcp.server.created",
        payload={
            "server_id": server.id,
            "server_name": server.name,
            "transport": server.transport,
            "execution_location": server.execution_location,
            "revision_id": revision.id,
            "risk_flags": [flag.code for flag in flags],
        },
    )
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server)


@router.get("/servers", response_model=list[McpServerSummary])
def list_servers(
    status: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    query = db.query(McpServerModel)
    if status:
        query = query.filter(McpServerModel.status == status)
    rows = query.order_by(McpServerModel.created_at.asc(), McpServerModel.id.asc()).all()
    return [service.server_summary(db, row) for row in rows]


@router.get("/servers/{server_id}", response_model=McpServerDetail)
def get_server(
    server_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    return service.server_detail(db, _server_or_404(db, server_id))


@router.post("/servers/{server_id}/revisions", response_model=McpServerDetail, status_code=201)
def create_server_revision(
    server_id: str,
    body: McpServerRevisionCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    if body.config.transport != server.transport:
        raise HTTPException(
            status_code=422,
            detail=(
                "Le transport d'un serveur ne change pas au fil des révisions : "
                "créez un nouveau serveur."
            ),
        )
    flags = _validated_config(db, body.config)
    target_worker_id = body.target_worker_id or server.target_worker_id
    _check_target_worker(db, body.config, target_worker_id)
    revision = service.create_revision(
        db, server, body.config, principal=principal, note=body.note, risk_flags=flags
    )
    if body.config.transport == "stdio":
        server.target_worker_id = target_worker_id
    service.record_event(
        db,
        "mcp.server.revised",
        payload={
            "server_id": server.id,
            "server_name": server.name,
            "revision_id": revision.id,
            "revision_number": revision.number,
            "requires_approval": bool(revision.requires_approval),
        },
    )
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server)


@router.post("/servers/{server_id}/probe", response_model=McpProbe)
def start_probe(
    server_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
    resolver: Callable[..., object] = Depends(get_dns_resolver),
    transport: httpx.BaseTransport | None = Depends(get_http_transport),
):
    """HTTP : diagnostic exécuté immédiatement. stdio : demande d'autorisation de lancement."""

    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    revision = _current_revision_or_409(db, server)
    service.expire_probes(db)
    if server.transport == "http":
        probe = service.run_http_probe(
            db,
            server,
            revision,
            principal=principal,
            vault=_vault_or_503(),
            policy=_policy(),
            resolver=resolver,
            transport=transport,
        )
        db.commit()
        db.refresh(probe)
        return service.probe_contract(probe)
    pending = (
        db.query(McpProbeModel)
        .filter(
            McpProbeModel.revision_id == revision.id,
            McpProbeModel.status.in_(service.ACTIVE_PROBE_STATUSES),
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=409,
            detail="Un diagnostic est déjà en cours pour cette révision (autorisation ou exécution).",
        )
    probe = service.request_stdio_probe(db, server, revision, principal=principal)
    db.commit()
    db.refresh(probe)
    return service.probe_contract(probe)


@router.get("/servers/{server_id}/probes", response_model=list[McpProbe])
def list_server_probes(
    server_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    server = _server_or_404(db, server_id)
    service.expire_probes(db)
    db.commit()
    return [service.probe_contract(row) for row in service.probes_of(db, server)]


@router.post("/servers/{server_id}/activate", response_model=McpServerDetail)
def activate_server(
    server_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    _current_revision_or_409(db, server)
    try:
        notes = service.activate_server(db, server, principal=principal)
    except ConfigRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server, apply_notes=notes)


@router.post("/servers/{server_id}/disable", response_model=McpServerDetail)
def disable_server(
    server_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    service.disable_server(db, server)
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server)


@router.post("/servers/{server_id}/revoke", response_model=McpServerDetail)
def revoke_server(
    server_id: str,
    body: McpRevokeRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    service.revoke_server(db, server, reason=body.reason, principal=principal)
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server)


@router.post("/servers/{server_id}/rollback", response_model=McpServerDetail)
def rollback_server(
    server_id: str,
    body: McpRollbackRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    require_platform_role(db, principal, "owner")
    server = _mutable_server(db, server_id)
    target = (
        db.query(McpServerRevisionModel)
        .filter_by(server_id=server.id, number=body.revision_number)
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"Révision {body.revision_number} introuvable pour ce serveur"
        )
    service.rollback_server(db, server, target, principal=principal, note=body.note)
    db.commit()
    db.refresh(server)
    return service.server_detail(db, server)


# --- probes ------------------------------------------------------------------------------------


@router.get("/probes", response_model=list[McpProbe])
def list_probes(
    status: str | None = None,
    server_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Par défaut, seuls les diagnostics non terminés (à décider, en file, réclamés)."""

    service.expire_probes(db)
    db.commit()
    query = db.query(McpProbeModel)
    if status:
        query = query.filter(McpProbeModel.status == status)
    else:
        query = query.filter(McpProbeModel.status.in_(service.ACTIVE_PROBE_STATUSES))
    if server_id:
        query = query.filter(McpProbeModel.server_id == server_id)
    rows = query.order_by(McpProbeModel.created_at.asc(), McpProbeModel.id.asc()).all()
    return [service.probe_contract(row) for row in rows]


@router.get("/probes/{probe_id}", response_model=McpProbe)
def get_probe(
    probe_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    service.expire_probes(db)
    db.commit()
    probe = db.get(McpProbeModel, probe_id)
    if probe is None:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable")
    return service.probe_contract(probe)


@router.post("/probes/{probe_id}/decision", response_model=McpProbe)
def decide_probe(
    probe_id: str,
    body: McpProbeDecision,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Autorise ou refuse un lancement stdio : l'empreinte autorisée doit être la courante."""

    require_platform_role(db, principal, "owner")
    service.expire_probes(db)
    probe = db.get(McpProbeModel, probe_id)
    if probe is None:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable")
    if probe.status != "pending_approval":
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"Diagnostic dans l'état « {probe.status} » : aucune décision n'est possible.",
        )
    server = _server_or_404(db, probe.server_id)
    revision = service.current_revision(db, server)
    authorized_fingerprint = (probe.authorization or {}).get("fingerprint")
    if revision is None or revision.fingerprint != authorized_fingerprint:
        probe.status = "invalidated"
        probe.error = "Révision courante modifiée : l'autorisation ne correspond plus."
        probe.finished_at = service.utcnow()
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="La configuration a changé depuis la demande : relancez un diagnostic.",
        )
    now = service.utcnow()
    probe.decided_by_user_id = principal
    probe.decided_at = now
    probe.decision_comment = body.comment
    if body.decision == "approved":
        probe.status = "queued"
    else:
        probe.status = "rejected"
        probe.finished_at = now
        probe.error = "Lancement refusé par le propriétaire."
    service.record_event(
        db,
        "mcp.probe.decided",
        payload={
            "probe_id": probe.id,
            "server_id": server.id,
            "server_name": server.name,
            "decision": body.decision,
            "decided_by_user_id": principal,
        },
    )
    db.commit()
    db.refresh(probe)
    return service.probe_contract(probe)


# --- bindings ----------------------------------------------------------------------------------


@router.post("/servers/{server_id}/bindings", response_model=McpBinding, status_code=201)
def create_binding(
    server_id: str,
    body: McpBindingCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    server = _server_or_404(db, server_id)
    _project_or_404(db, body.project_id)
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    if server.status != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Serveur « {server.name} » non actif (état {server.status}) : activez-le d'abord.",
        )
    revision = _current_revision_or_409(db, server)
    _check_project_scoped_secrets(db, revision, body.project_id)
    tools = _validate_tools(revision, body.allowed_tools)
    existing = (
        db.query(McpBindingModel).filter_by(server_id=server.id, project_id=body.project_id).first()
    )
    now = service.utcnow()
    if existing is not None and existing.revoked_at is None:
        raise HTTPException(
            status_code=409, detail="Ce serveur est déjà lié à ce projet : modifiez le binding."
        )
    if existing is not None:
        binding = existing
        binding.revoked_at = None
        binding.enabled = 1
        binding.revision_id = revision.id
        binding.allowed_tools = tools
        binding.updated_at = now
    else:
        binding = McpBindingModel(
            server_id=server.id,
            project_id=body.project_id,
            revision_id=revision.id,
            allowed_tools=tools,
            enabled=1,
            created_by_user_id=principal,
        )
        db.add(binding)
        db.flush()
    service.record_event(
        db,
        "mcp.binding.created",
        project_id=body.project_id,
        payload={
            "binding_id": binding.id,
            "server_id": server.id,
            "server_name": server.name,
            "project_id": body.project_id,
            "allowed_tools": tools,
        },
    )
    db.commit()
    db.refresh(binding)
    return service.binding_contract(db, binding)


@router.get("/bindings", response_model=list[McpBinding])
def list_bindings(
    project_id: str | None = None,
    server_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    visible = accessible_project_ids(db, principal)
    if not visible:
        return []
    query = db.query(McpBindingModel).filter(McpBindingModel.project_id.in_(visible))
    if project_id:
        query = query.filter(McpBindingModel.project_id == project_id)
    if server_id:
        query = query.filter(McpBindingModel.server_id == server_id)
    rows = query.order_by(McpBindingModel.created_at.asc(), McpBindingModel.id.asc()).all()
    return [service.binding_contract(db, row) for row in rows]


@router.get("/bindings/{binding_id}", response_model=McpBinding)
def get_binding(
    binding_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    binding = _binding_or_404(db, binding_id)
    ensure_access(db, principal, project_id=binding.project_id, minimum_role="viewer")
    return service.binding_contract(db, binding)


@router.patch("/bindings/{binding_id}", response_model=McpBinding)
def patch_binding(
    binding_id: str,
    body: McpBindingPatch,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    binding = _binding_or_404(db, binding_id)
    ensure_access(db, principal, project_id=binding.project_id, minimum_role="member")
    if binding.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Binding révoqué : créez-en un nouveau.")
    server = _server_or_404(db, binding.server_id)
    if server.status == "revoked":
        raise HTTPException(status_code=409, detail="Serveur révoqué : binding figé.")
    revision = db.get(McpServerRevisionModel, binding.revision_id)
    if body.allowed_tools is not None:
        if revision is None:
            raise HTTPException(status_code=409, detail="Révision du binding introuvable")
        binding.allowed_tools = _validate_tools(revision, body.allowed_tools)
    if body.enabled is not None:
        binding.enabled = 1 if body.enabled else 0
    binding.updated_at = service.utcnow()
    service.record_event(
        db,
        "mcp.binding.updated",
        project_id=binding.project_id,
        payload={
            "binding_id": binding.id,
            "server_id": binding.server_id,
            "project_id": binding.project_id,
            "allowed_tools": list(binding.allowed_tools or []),
            "enabled": bool(binding.enabled),
        },
    )
    db.commit()
    db.refresh(binding)
    return service.binding_contract(db, binding)


@router.delete("/bindings/{binding_id}", response_model=McpBinding)
def revoke_binding(
    binding_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    binding = _binding_or_404(db, binding_id)
    ensure_access(db, principal, project_id=binding.project_id, minimum_role="member")
    if binding.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Binding déjà révoqué")
    now = service.utcnow()
    binding.revoked_at = now
    binding.enabled = 0
    binding.updated_at = now
    service.record_event(
        db,
        "mcp.binding.revoked",
        project_id=binding.project_id,
        payload={
            "binding_id": binding.id,
            "server_id": binding.server_id,
            "project_id": binding.project_id,
        },
    )
    db.commit()
    db.refresh(binding)
    return service.binding_contract(db, binding)


# --- export ---------------------------------------------------------------------------------------


@router.get("/export", response_model=McpExport)
def export_servers(
    format: McpExportFormat = "hermes",
    project_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Export global réservé au propriétaire ; export de projet ouvert aux lecteurs du projet."""

    if project_id is None:
        require_platform_role(db, principal, "owner")
    else:
        _project_or_404(db, project_id)
        ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
    return service.export_config(db, format, project_id)


# --- runner (worker authentifié) ---------------------------------------------------------------


@router.post("/worker/probes/claim")
def claim_stdio_probe(
    response: Response,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
):
    """Renvoie au runner autorisé le lancement à exécuter, avec les valeurs de secrets résolues."""

    response.headers["Cache-Control"] = "no-store"
    worker = _authenticated_worker(db, x_worker_id, authorization)
    if service.STDIO_PROBE_CAPABILITY not in (worker.capabilities or []) or bool(worker.simulation):
        # Refus silencieux : un runner sans la capacité (ou en simulation) ne doit rien recevoir.
        service.expire_probes(db)
        db.commit()
        return {"probe": None}
    claimed = service.claim_probe_for_worker(db, worker, _optional_vault())
    db.commit()
    if claimed is None:
        return {"probe": None}
    _, payload = claimed
    return {"probe": payload}


@router.post("/worker/probes/{probe_id}/result", response_model=McpProbe)
def report_stdio_probe(
    probe_id: str,
    body: McpProbeResult,
    response: Response,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_worker_id: str | None = Header(default=None, alias="X-Worker-Id"),
):
    """Seul le runner détenteur d'un lease valide peut rapporter un résultat."""

    response.headers["Cache-Control"] = "no-store"
    worker = _authenticated_worker(db, x_worker_id, authorization)
    service.expire_probes(db)
    probe = db.get(McpProbeModel, probe_id)
    if probe is None:
        db.commit()
        raise HTTPException(status_code=404, detail="Diagnostic introuvable")
    if probe.status != "claimed" or probe.worker_id != worker.id:
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "Lease invalide ou expiré : le résultat est refusé, aucun succès n'est supposé "
                f"(état actuel : {probe.status})."
            ),
        )
    service.complete_probe(db, probe, body)
    db.commit()
    db.refresh(probe)
    return service.probe_contract(probe)


# --- import ---------------------------------------------------------------------------------------
# Le contenu importé est une donnée non fiable : il est borné par le contrat (1 000 000 caractères,
# au-delà ⇒ 422), analysé sans exécution, et aucun secret n'en ressort — l'aperçu ne renvoie que des
# candidats masqués, reliés à un secret du coffre au moment de l'application.


def _existing_server_names(db: Session) -> set[str]:
    return {name for (name,) in db.query(McpServerModel.name).all()}


@router.post("/import/preview", response_model=McpImportPreview)
def preview_import(
    body: McpImportPreviewRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Aperçu normalisé d'une configuration Hermes / Claude Code / Codex (rien n'est écrit)."""

    require_platform_role(db, principal, "owner")
    return importers.parse_import(body.format, body.content, _existing_server_names(db))


@router.post("/import/apply", response_model=McpImportApplyResult)
def apply_import(
    body: McpImportApplyRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Crée en brouillon les entrées explicitement choisies ; le reste est ignoré et expliqué."""

    require_platform_role(db, principal, "owner")
    preview = importers.parse_import(body.format, body.content, _existing_server_names(db))
    if preview.errors and not preview.entries:
        # Contenu illisible : aucune écriture, l'erreur d'analyse est rendue telle quelle.
        return McpImportApplyResult(errors=list(preview.errors))
    result = importers.apply_import(db, principal, body, preview, policy=_policy())
    db.commit()
    return result
