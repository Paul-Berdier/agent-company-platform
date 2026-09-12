"""Routes de la bibliothèque de skills (``/skills``) et des extensions de projet.

``GET /projects/{project_id}/extensions`` ne peut pas vivre sous le préfixe ``/skills`` :
il se déclare sur ``extensions_router`` (sans préfixe), dans ce même fichier comme
l'exige la spécification.

Règles d'accès : lecture ouverte à tout utilisateur authentifié ; import, révision,
approbation, activation, désactivation, révocation et retour arrière réservés au
propriétaire de la plateforme ; rattachements réservés aux membres du projet visé.
Les mutations exigent en outre un jeton CSRF valide (``get_principal``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from acp_contracts import (
    ProjectExtensions,
    SkillApproveRequest,
    SkillBinding,
    SkillBindingCreate,
    SkillCatalogEntry,
    SkillDetail,
    SkillFile,
    SkillFileContent,
    SkillImportRequest,
    SkillRevisionCreate,
    SkillRevokeRequest,
    SkillRollbackRequest,
    SkillSearchResult,
    SkillSummary,
)
from acp_database.models import ProjectModel, SkillBindingModel, SkillModel

from ..deps import (
    accessible_project_ids,
    ensure_access,
    get_db,
    get_principal,
    require_platform_role,
)
from ..extensions import resolve_project_extensions
from ..skills import SkillError
from ..skills import service as skills_service

router = APIRouter(prefix="/skills", tags=["skills"])
extensions_router = APIRouter(tags=["extensions"])


def _refuse(exc: SkillError) -> HTTPException:
    """Convertit un refus métier en réponse HTTP explicite (jamais un faux succès)."""

    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _skill_or_404(db: Session, skill_id: str) -> SkillModel:
    skill = db.get(SkillModel, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill introuvable")
    return skill


def _owner(db: Session, principal: str) -> None:
    require_platform_role(db, principal, "owner")


def _detail(db: Session, skill: SkillModel, principal: str) -> SkillDetail:
    """Détail filtré : les rattachements exposés sont ceux des projets accessibles à l'appelant."""

    return skills_service.skill_detail(
        db, skill, visible_project_ids=accessible_project_ids(db, principal)
    )


# --- Catalogue et recherche --------------------------------------------------


@router.get("/search", response_model=SkillSearchResult)
def search_skills(
    q: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    return skills_service.search(db, q)


@router.get("/catalog", response_model=list[SkillCatalogEntry])
def list_catalog(principal: str = Depends(get_principal)):
    """Catalogue statique : dépôts de confiance cités par la documentation Hermes, non audités."""

    return list(skills_service.catalog_entries())


# --- Import et consultation --------------------------------------------------


@router.post("/import", response_model=SkillDetail, status_code=201)
def import_skill(
    body: SkillImportRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    try:
        skill = skills_service.import_skill(
            db, source=body.source, name=body.name, note=body.note, principal=principal
        )
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.get("", response_model=list[SkillSummary])
def list_skills(
    status: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    query = db.query(SkillModel)
    if status:
        query = query.filter(SkillModel.status == status)
    return [
        skills_service.skill_summary(db, skill)
        for skill in query.order_by(SkillModel.name).all()
    ]


@router.get("/bindings", response_model=list[SkillBinding])
def list_bindings(
    project_id: str | None = None,
    skill_id: str | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Rattachements actifs, filtrés par les projets réellement accessibles à l'appelant."""

    visible = accessible_project_ids(db, principal)
    if project_id is not None:
        visible = visible & {project_id}
    if not visible:
        return []
    query = db.query(SkillBindingModel).filter(
        SkillBindingModel.project_id.in_(visible),
        SkillBindingModel.revoked_at.is_(None),
    )
    if skill_id is not None:
        query = query.filter(SkillBindingModel.skill_id == skill_id)
    rows = query.order_by(SkillBindingModel.created_at, SkillBindingModel.id).all()
    result: list[SkillBinding] = []
    for binding in rows:
        skill = db.get(SkillModel, binding.skill_id)
        if skill is None:
            continue
        result.append(
            skills_service.binding_contract(
                binding, skill, skills_service.revision_number_of(db, binding.revision_id)
            )
        )
    return result


@router.get("/{skill_id}", response_model=SkillDetail)
def get_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    return _detail(db, _skill_or_404(db, skill_id), principal)


@router.get("/{skill_id}/revisions/{number}/files", response_model=list[SkillFile])
def list_revision_files(
    skill_id: str,
    number: int,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    skill = _skill_or_404(db, skill_id)
    try:
        revision = skills_service.revision_by_number(db, skill, number)
    except SkillError as exc:
        raise _refuse(exc) from exc
    return [SkillFile.model_validate(entry) for entry in (revision.files or [])]


@router.get("/{skill_id}/revisions/{number}/files/{path:path}", response_model=SkillFileContent)
def read_revision_file(
    skill_id: str,
    number: int,
    path: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    """Le chemin lu provient du manifeste stocké : un chemin absent du manifeste est 404.

    Le contenu est renvoyé comme texte brut dans un champ JSON, jamais rendu ni servi avec
    un type MIME exécutable ; un fichier binaire renvoie ``content = null``.
    """

    skill = _skill_or_404(db, skill_id)
    try:
        revision = skills_service.revision_by_number(db, skill, number)
        return skills_service.read_file(revision, path)
    except SkillError as exc:
        raise _refuse(exc) from exc


# --- Cycle de vie ------------------------------------------------------------


@router.post("/{skill_id}/revisions", response_model=SkillDetail, status_code=201)
def create_revision(
    skill_id: str,
    body: SkillRevisionCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.create_revision(
            db, skill, source=body.source, note=body.note, principal=principal
        )
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.post("/{skill_id}/revisions/{number}/approve", response_model=SkillDetail)
def approve_revision(
    skill_id: str,
    number: int,
    body: SkillApproveRequest | None = None,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.approve_revision(
            db, skill, number, principal=principal, comment=(body.comment if body else "")
        )
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.post("/{skill_id}/activate", response_model=SkillDetail)
def activate_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.activate_skill(db, skill)
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.post("/{skill_id}/disable", response_model=SkillDetail)
def disable_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.disable_skill(db, skill)
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.post("/{skill_id}/revoke", response_model=SkillDetail)
def revoke_skill(
    skill_id: str,
    body: SkillRevokeRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.revoke_skill(db, skill, reason=body.reason)
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


@router.post("/{skill_id}/rollback", response_model=SkillDetail)
def rollback_skill(
    skill_id: str,
    body: SkillRollbackRequest,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    _owner(db, principal)
    skill = _skill_or_404(db, skill_id)
    try:
        skills_service.rollback_skill(
            db,
            skill,
            revision_number=body.revision_number,
            note=body.note,
            principal=principal,
        )
        detail = _detail(db, skill, principal)
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return detail


# --- Rattachements -----------------------------------------------------------


@router.post("/{skill_id}/bindings", response_model=SkillBinding, status_code=201)
def create_binding(
    skill_id: str,
    body: SkillBindingCreate,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    skill = _skill_or_404(db, skill_id)
    if db.get(ProjectModel, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    try:
        binding = skills_service.create_binding(
            db, skill, project_id=body.project_id, principal=principal
        )
        contract = skills_service.binding_contract(
            binding, skill, skills_service.revision_number_of(db, binding.revision_id)
        )
    except SkillError as exc:
        db.rollback()
        raise _refuse(exc) from exc
    db.commit()
    return contract


@router.delete("/bindings/{binding_id}", response_model=SkillBinding)
def delete_binding(
    binding_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    binding = db.get(SkillBindingModel, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Rattachement introuvable")
    ensure_access(db, principal, project_id=binding.project_id, minimum_role="member")
    skill = _skill_or_404(db, binding.skill_id)
    skills_service.revoke_binding(db, binding, skill)
    contract = skills_service.binding_contract(
        binding, skill, skills_service.revision_number_of(db, binding.revision_id)
    )
    db.commit()
    return contract


# --- Extensions de projet ----------------------------------------------------


@extensions_router.get("/projects/{project_id}/extensions", response_model=ProjectExtensions)
def get_project_extensions(
    project_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
):
    ensure_access(db, principal, project_id=project_id, minimum_role="viewer")
    if db.get(ProjectModel, project_id) is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return resolve_project_extensions(db, project_id)
