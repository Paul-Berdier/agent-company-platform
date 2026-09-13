"""Routes du coffre de secrets (``/secrets``).

Aucune valeur de secret ne figure jamais dans une réponse de ce routeur ni dans un
événement : seules des métadonnées (``SecretSummary``) circulent. Les valeurs sont
chiffrées par le coffre (``secrets_vault``) avant d'atteindre la base.

Règles d'accès : un secret de portée ``platform`` est réservé au propriétaire de la
plateforme ; un secret de portée ``project`` est géré par les membres du projet.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import Event, SecretCreate, SecretRotate, SecretsStatus, SecretSummary
from acp_database.models import ProjectModel, SecretModel

from ..deps import (
    accessible_project_ids,
    ensure_access,
    get_db,
    get_principal,
    is_platform_owner,
    require_platform_role,
)
from ..events_bus import store_event
from ..mcp.service import referencing_server_ids
from ..secrets_vault import SecretsVault, VaultNotConfigured, get_vault, vault_status

router = APIRouter(prefix="/secrets", tags=["secrets"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _vault_or_503() -> SecretsVault:
    """Coffre prêt à chiffrer ; 503 explicite (jamais de faux succès) s'il n'est pas configuré."""

    try:
        return get_vault(os.environ)
    except VaultNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _secret_or_404(db: Session, secret_id: str) -> SecretModel:
    secret = db.get(SecretModel, secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret introuvable")
    return secret


def _ensure_scope_access(
    db: Session, principal: str, *, scope_type: str, project_id: str | None
) -> None:
    """Portée ``platform`` ⇒ propriétaire ; portée ``project`` ⇒ membre du projet."""

    if scope_type == "platform":
        require_platform_role(db, principal, "owner")
        return
    if db.get(ProjectModel, project_id) is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    ensure_access(db, principal, project_id=project_id, minimum_role="member")


def _record(db: Session, event_type: str, secret: SecretModel) -> None:
    """Événement d'audit sans valeur : uniquement des identifiants et la portée.

    L'écriture passe par ``store_event`` — et non par un ``EventModel`` ajouté à la
    main — parce que c'est lui qui alloue le numéro de journal : sans ce numéro, la
    trace d'audit du coffre resterait invisible de ``GET /projects/{id}/events``
    pour toute la vie du processus, puis ressortirait hors d'ordre après un
    redémarrage. ``commit=False`` laisse la transaction à la route appelante.
    """

    store_event(
        db,
        Event(
            type=event_type,
            project_id=secret.project_id,
            payload={
                "secret_id": secret.id,
                "name": secret.name,
                "scope_type": secret.scope_type,
                "project_id": secret.project_id,
                "key_id": secret.key_id,
            },
        ),
        commit=False,
    )


def secret_summary(db: Session, secret: SecretModel) -> SecretSummary:
    return SecretSummary(
        id=secret.id,
        name=secret.name,
        scope_type=secret.scope_type,
        project_id=secret.project_id,
        description=secret.description or "",
        key_id=secret.key_id,
        created_at=secret.created_at,
        rotated_at=secret.rotated_at,
        revoked_at=secret.revoked_at,
        last_used_at=secret.last_used_at,
        referenced_by_mcp_servers=referencing_server_ids(db, secret.id),
    )


@router.get("/status", response_model=SecretsStatus)
def secrets_status(principal: str = Depends(get_principal)):
    """Ne renvoie jamais 503 : ``configured=false`` porte le message et l'action à effectuer."""

    return vault_status(os.environ)


@router.post("", response_model=SecretSummary, status_code=201)
def create_secret(
    body: SecretCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _ensure_scope_access(
        db, principal, scope_type=body.scope_type, project_id=body.project_id
    )
    vault = _vault_or_503()
    duplicate = (
        db.query(SecretModel)
        .filter_by(name=body.name, scope_type=body.scope_type, project_id=body.project_id)
        .first()
    )
    if duplicate is not None:
        # SQLite considère les NULL distincts : l'unicité « platform » est appliquée ici.
        raise HTTPException(
            status_code=409,
            detail=f"Un secret nommé « {body.name} » existe déjà pour cette portée",
        )
    key_id, ciphertext = vault.encrypt(body.value)
    secret = SecretModel(
        name=body.name,
        scope_type=body.scope_type,
        project_id=body.project_id,
        description=body.description,
        key_id=key_id,
        ciphertext=ciphertext,
        created_by_user_id=principal,
    )
    db.add(secret)
    db.flush()
    _record(db, "secret.created", secret)
    db.commit()
    db.refresh(secret)
    return secret_summary(db, secret)


@router.get("", response_model=list[SecretSummary])
def list_secrets(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Propriétaire : tous les secrets ; sinon uniquement ceux des projets accessibles."""

    query = db.query(SecretModel)
    if not is_platform_owner(db, principal):
        visible = accessible_project_ids(db, principal)
        if not visible:
            return []
        query = query.filter(
            SecretModel.scope_type == "project", SecretModel.project_id.in_(visible)
        )
    if project_id:
        query = query.filter(SecretModel.project_id == project_id)
    rows = query.order_by(SecretModel.created_at, SecretModel.id).all()
    return [secret_summary(db, row) for row in rows]


@router.post("/{secret_id}/rotate", response_model=SecretSummary)
def rotate_secret(
    secret_id: str,
    body: SecretRotate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    secret = _secret_or_404(db, secret_id)
    _ensure_scope_access(
        db, principal, scope_type=secret.scope_type, project_id=secret.project_id
    )
    if secret.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Secret révoqué : rotation impossible")
    vault = _vault_or_503()
    key_id, ciphertext = vault.encrypt(body.value)
    now = _utcnow()
    secret.key_id = key_id
    secret.ciphertext = ciphertext
    secret.rotated_at = now
    secret.updated_at = now
    _record(db, "secret.rotated", secret)
    db.commit()
    db.refresh(secret)
    return secret_summary(db, secret)


@router.delete("/{secret_id}", response_model=SecretSummary)
def revoke_secret(
    secret_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Révocation irréversible ; la ligne est conservée pour l'historique (jamais supprimée)."""

    secret = _secret_or_404(db, secret_id)
    _ensure_scope_access(
        db, principal, scope_type=secret.scope_type, project_id=secret.project_id
    )
    if secret.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Secret déjà révoqué")
    active_servers = referencing_server_ids(db, secret.id, active_only=True)
    if active_servers:
        raise HTTPException(
            status_code=409,
            detail=(
                "Secret référencé par la révision courante d'un serveur MCP actif : "
                f"{', '.join(active_servers)}. Révisez ou désactivez ces serveurs d'abord."
            ),
        )
    now = _utcnow()
    secret.revoked_at = now
    secret.updated_at = now
    _record(db, "secret.revoked", secret)
    db.commit()
    db.refresh(secret)
    return secret_summary(db, secret)
