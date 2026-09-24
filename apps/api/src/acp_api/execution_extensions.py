"""Contenu épinglé des compétences livré uniquement au worker détenteur du bail."""

import hashlib

from fastapi import HTTPException
from sqlalchemy.orm import Session

from acp_database.models import SkillBindingModel, SkillModel, SkillRevisionModel, TaskModel

MAX_SKILL_CONTEXT_CHARS = 24_000


def execution_skills(db: Session, task: TaskModel) -> list[dict]:
    """Relit les droits courants sans migrer la révision figée à l'admission."""
    snapshot = (task.meta or {}).get("extensions") or {}
    result = []
    remaining = MAX_SKILL_CONTEXT_CHARS
    for entry in snapshot.get("skills", []):
        skill_id = entry.get("skill_id")
        skill = db.get(SkillModel, skill_id)
        binding = db.query(SkillBindingModel).filter_by(
            skill_id=skill_id, project_id=task.project_id, enabled=1,
            revoked_at=None,
        ).first()
        revision = db.query(SkillRevisionModel).filter_by(
            skill_id=skill_id, number=entry.get("revision_number"),
        ).first()
        if (skill is None or skill.status != "active" or binding is None or revision is None
                or binding.revision_id != revision.id):
            raise HTTPException(409, "Une compétence de la mission a été désactivée ou révoquée.")
        if revision.requires_approval and (
            revision.approved_at is None or revision.approval_fingerprint != revision.fingerprint
        ):
            raise HTTPException(409, "La révision de compétence exige une approbation valide.")
        content = revision.skill_md or ""
        manifest = next((item for item in revision.files or [] if item.get("path") == "SKILL.md"), None)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not content or manifest is None or manifest.get("sha256") != digest:
            raise HTTPException(409, "Le contenu de compétence ne correspond pas à son empreinte.")
        if len(content) > remaining:
            raise HTTPException(409, "Le contenu des compétences dépasse 24000 caractères ; réduire les liaisons.")
        remaining -= len(content)
        result.append({"skill_id": skill.id, "name": skill.name,
                       "revision_number": revision.number, "sha256": digest,
                       "content": content})
    return result
