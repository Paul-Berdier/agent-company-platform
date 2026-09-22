"""Logique métier de la bibliothèque de skills.

Cycle de vie d'un skill : import (révision 1, statut ``draft``) → approbation → activation
→ rattachement à un projet (binding) → révisions successives → retour arrière → révocation
irréversible. Une révision est immuable : toute modification crée une nouvelle révision.

Trois invariants gouvernent ce module :

1. **Aucun faux succès.** Une source illisible, un dossier non autorisé, une intégration
   non configurée ou une limite dépassée produisent un refus explicite, jamais un skill
   partiellement importé.
2. **Le contenu importé est une donnée.** Les chemins lus proviennent toujours du manifeste
   stocké en base, jamais de l'URL ; le contenu est renvoyé comme texte brut, jamais rendu ;
   un ``native_plugin`` est étiqueté mais jamais chargé par la plateforme.
3. **Les changements sensibles exigent une relecture.** Première révision, script ajouté,
   nouvel indicateur réseau, nouvelle permission, changement de nature ou constat ``danger``
   ⇒ approbation par un propriétaire avant activation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from acp_contracts import (
    Event,
    SkillBinding,
    SkillCatalogEntry,
    SkillDependencies,
    SkillDetail,
    SkillFile,
    SkillFileContent,
    SkillRevision,
    SkillRevisionDiff,
    SkillScanFinding,
    SkillSearchResult,
    SkillSummary,
    validate_slug,
)
from acp_contracts.skills import SKILL_FILE_CONTENT_MAX_CHARS
from acp_database.models import (
    SkillBindingModel,
    SkillModel,
    SkillRevisionModel,
)

from . import SkillError
from . import scan as scan_module
from . import sources as sources_module
from ..events_bus import store_event
from ..transactions import end_read_transaction
from ..outbound import OutboundPolicy, PinnedHttpClient

FRONTMATTER_MAX_CHARS = 65_536
LICENSE_MAX_CHARS = 120
GITHUB_MAX_BODY_BYTES = 25 * 1024 * 1024
GITHUB_IMPORT_PURPOSE = "skills.github_import"
DEFAULT_STORAGE_DIR = "./acp-data/skills"

CATALOG_PATH = Path(__file__).with_name("catalog.json")

NATIVE_PLUGIN_NOTE = (
    "Skill de type « native_plugin » : jamais chargé ni exécuté par la plateforme. "
    "Il est uniquement étiqueté et listé pour information."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Configuration -----------------------------------------------------------


def storage_directory(environ: Mapping[str, str] = os.environ) -> Path:
    """Racine de stockage des révisions (``ACP_SKILLS_STORAGE_DIR``)."""

    raw = (environ.get("ACP_SKILLS_STORAGE_DIR") or "").strip() or DEFAULT_STORAGE_DIR
    return Path(raw).expanduser()


def github_client_factory() -> PinnedHttpClient:
    """Client HTTP contrôlé utilisé pour télécharger un tarball GitHub.

    Remplacé par un transport simulé dans les tests : aucun accès réseau réel n'est requis
    pour vérifier l'épinglage, l'en-tête ``Authorization`` et les refus de la politique.
    """

    return PinnedHttpClient(
        OutboundPolicy.from_environ(os.environ),
        max_body_bytes=GITHUB_MAX_BODY_BYTES,
    )


# --- Fonctions pures ---------------------------------------------------------


def parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    """Sépare le frontmatter YAML (entre ``---``) du corps du document.

    Absence de frontmatter ⇒ ``({}, texte)``. Frontmatter illisible, trop volumineux ou qui
    n'est pas un dictionnaire ⇒ ``SkillError`` (jamais un import silencieusement dégradé).
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return {}, text
    raw_frontmatter = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :])
    if len(raw_frontmatter) > FRONTMATTER_MAX_CHARS:
        raise SkillError(
            f"Frontmatter refusé : plus de {FRONTMATTER_MAX_CHARS} caractères dans SKILL.md."
        )
    try:
        parsed = yaml.safe_load(raw_frontmatter)
    except yaml.YAMLError as exc:
        raise SkillError(f"Frontmatter YAML invalide dans SKILL.md : {exc}.") from exc
    if parsed is None:
        return {}, body
    if not isinstance(parsed, dict):
        raise SkillError(
            "Frontmatter invalide dans SKILL.md : un dictionnaire de métadonnées est attendu."
        )
    return parsed, body


def classify_kind(files: Sequence[tuple[str, bytes]], frontmatter: Mapping[str, Any]) -> str:
    """``native_plugin`` (manifeste de plugin), ``scripted`` (scripts présents) ou ``documentary``."""

    metadata = frontmatter.get("metadata") if isinstance(frontmatter, Mapping) else None
    hermes = metadata.get("hermes") if isinstance(metadata, Mapping) else None
    if isinstance(hermes, Mapping) and hermes.get("plugin"):
        return "native_plugin"
    if scan_module._plugin_manifest(files):
        return "native_plugin"
    if scan_module.script_paths(files):
        return "scripted"
    return "documentary"


def detect_license(files: Sequence[tuple[str, bytes]], frontmatter: Mapping[str, Any]) -> str | None:
    """Licence déclarée dans le frontmatter, sinon première ligne d'un fichier ``LICENSE*``."""

    declared = frontmatter.get("license") if isinstance(frontmatter, Mapping) else None
    if isinstance(declared, str) and declared.strip():
        return declared.strip()[:LICENSE_MAX_CHARS]
    for path, data in files:
        base = scan_module.relative_name(path).lower()
        if base != "license" and not base.startswith("license."):
            continue
        text = scan_module.decode_text(data)
        if text is None:
            return None
        for line in text.splitlines():
            if line.strip():
                return line.strip()[:LICENSE_MAX_CHARS]
        return None
    return None


def extract_dependencies(
    frontmatter: Mapping[str, Any],
    files: Sequence[tuple[str, bytes]],
    scan: Sequence[SkillScanFinding] | None = None,
) -> SkillDependencies:
    """Dépendances déclarées (frontmatter Hermes) et observées (scripts, URL réseau)."""

    hermes: Mapping[str, Any] = {}
    metadata = frontmatter.get("metadata") if isinstance(frontmatter, Mapping) else None
    if isinstance(metadata, Mapping) and isinstance(metadata.get("hermes"), Mapping):
        hermes = metadata["hermes"]

    def declared(key: str) -> list[Any]:
        value = frontmatter.get(key) if isinstance(frontmatter, Mapping) else None
        if value is None:
            value = hermes.get(key)
        return scan_module._as_list(value)

    environment: list[dict[str, Any]] = []
    for entry in declared("required_environment_variables"):
        if isinstance(entry, str) and entry.strip():
            environment.append({"name": entry.strip()})
        elif isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
            environment.append(dict(entry))
    return SkillDependencies(
        required_environment_variables=environment,
        requires_toolsets=[str(item) for item in declared("requires_toolsets") if item],
        requires_tools=[str(item) for item in declared("requires_tools") if item],
        scripts=scan_module.script_paths(files),
        network_indicators=scan_module.collect_network_indicators(files),
        platforms=[str(item) for item in declared("platforms") if item],
    )


def compute_fingerprint(manifest: Sequence[Mapping[str, Any]]) -> str:
    """sha256 de la liste canonique ``[{path, sha256}]`` triée par chemin."""

    canonical = [
        {"path": entry["path"], "sha256": entry["sha256"]}
        for entry in sorted(manifest, key=lambda item: item["path"])
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest(files: Sequence[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """Manifeste d'une révision : chemin, taille, empreinte et nature textuelle de chaque fichier."""

    return [
        {
            "path": path,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "text": scan_module.decode_text(data) is not None,
        }
        for path, data in sorted(files)
    ]


@dataclass(frozen=True)
class RevisionContent:
    """Contenu analysé d'une révision, avant écriture en base."""

    files: list[tuple[str, bytes]]
    manifest: list[dict[str, Any]]
    fingerprint: str
    skill_md: str
    frontmatter: dict[str, Any]
    license: str | None
    dependencies: SkillDependencies
    scan: list[SkillScanFinding]
    kind: str
    source_kind: str
    origin: str
    source_ref: str


def analyse(materialized: sources_module.MaterializedSource) -> RevisionContent:
    """Analyse les fichiers matérialisés ; exige un ``SKILL.md`` exploitable à la racine."""

    files = list(materialized.files)
    skill_md_bytes = next((data for path, data in files if path == "SKILL.md"), None)
    if skill_md_bytes is None:
        raise SkillError(
            "Import refusé : aucun fichier SKILL.md à la racine de la source."
        )
    skill_md = scan_module.decode_text(skill_md_bytes)
    if skill_md is None:
        raise SkillError("Import refusé : SKILL.md n'est pas un texte UTF-8 valide.")
    frontmatter, _ = parse_skill_md(skill_md)
    kind = classify_kind(files, frontmatter)
    license_value = detect_license(files, frontmatter)
    findings = scan_module.scan_files(
        files, frontmatter=frontmatter, license=license_value, kind=kind
    )
    dependencies = extract_dependencies(frontmatter, files, findings)
    manifest = build_manifest(files)
    return RevisionContent(
        files=files,
        manifest=manifest,
        fingerprint=compute_fingerprint(manifest),
        skill_md=skill_md,
        frontmatter=frontmatter,
        license=license_value,
        dependencies=dependencies,
        scan=findings,
        kind=kind,
        source_kind=materialized.source_kind,
        origin=materialized.origin,
        source_ref=materialized.source_ref,
    )


def compute_revision_diff(
    previous: SkillRevisionModel | None, new: RevisionContent
) -> SkillRevisionDiff:
    """Différence entre la révision courante et la nouvelle, et besoin d'approbation associé."""

    previous_files: dict[str, str] = {}
    previous_dependencies = SkillDependencies()
    if previous is not None:
        previous_files = {
            entry["path"]: entry["sha256"] for entry in (previous.files or []) if "path" in entry
        }
        previous_dependencies = SkillDependencies.model_validate(previous.dependencies or {})
    new_files = {entry["path"]: entry["sha256"] for entry in new.manifest}

    files_added = sorted(set(new_files) - set(previous_files))
    files_removed = sorted(set(previous_files) - set(new_files))
    files_changed = sorted(
        path for path in set(new_files) & set(previous_files)
        if new_files[path] != previous_files[path]
    )
    scripts_added = sorted(
        path for path in set(files_added) | set(files_changed) if scan_module.is_script(path)
    )
    network_added = sorted(
        set(new.dependencies.network_indicators) - set(previous_dependencies.network_indicators)
    )
    permissions_added = sorted(
        (
            {
                str(item.get("name"))
                for item in new.dependencies.required_environment_variables
                if item.get("name")
            }
            | set(new.dependencies.requires_toolsets)
        )
        - (
            {
                str(item.get("name"))
                for item in previous_dependencies.required_environment_variables
                if item.get("name")
            }
            | set(previous_dependencies.requires_toolsets)
        )
    )
    kind_changed = previous is not None and previous.kind != new.kind
    has_danger = scan_module.has_danger(new.scan)

    reasons: list[str] = []
    if previous is None:
        reasons.append("première révision : approbation initiale requise avant activation")
    if scripts_added:
        reasons.append("scripts ajoutés ou modifiés : " + ", ".join(scripts_added))
    if network_added:
        reasons.append("nouveaux indicateurs de sortie réseau : " + ", ".join(network_added))
    if permissions_added:
        reasons.append("nouvelles permissions demandées : " + ", ".join(permissions_added))
    if kind_changed:
        reasons.append(f"changement de nature du skill : {previous.kind} → {new.kind}")
    if has_danger:
        reasons.append("constats de niveau danger relevés par le contrôle automatique")

    return SkillRevisionDiff(
        previous_number=previous.number if previous is not None else None,
        files_added=files_added,
        files_removed=files_removed,
        files_changed=files_changed,
        scripts_added=scripts_added,
        network_indicators_added=network_added,
        permissions_added=permissions_added,
        kind_changed=kind_changed,
        requires_approval=bool(reasons),
        reasons=reasons,
    )


# --- Stockage ----------------------------------------------------------------


def store_revision(
    storage_dir: Path, skill_id: str, number: int, files: Sequence[tuple[str, bytes]]
) -> str:
    """Écrit les fichiers sous ``<storage_dir>/<skill_id>/<number>/`` et retourne ce chemin.

    Aucune écriture n'a lieu hors de ce répertoire : chaque chemin est déjà normalisé et la
    cible résolue est revérifiée avant l'écriture.
    """

    root = (Path(storage_dir) / skill_id / str(number)).expanduser()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    anchor = root.resolve()
    for path, data in files:
        target = root.joinpath(*path.split("/"))
        if anchor not in target.resolve().parents:
            raise SkillError(f"Écriture refusée hors du stockage de la révision : « {path} ».")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return str(root)


def revision_storage_path(skill_id: str, number: int) -> str:
    """Chemin de stockage mémorisé pour une révision : ``<skill_id>/<numéro>``, relatif.

    La base ne connaît pas la racine : elle vient de ``ACP_SKILLS_STORAGE_DIR`` au
    moment de la lecture. Un déploiement peut ainsi déplacer son volume ou changer
    d'hôte (Docker, Railway) sans réécrire les lignes de révision.
    """

    return f"{skill_id}/{number}"


def revision_root(revision: SkillRevisionModel) -> Path:
    """Répertoire des fichiers d'une révision, résolu contre la racine configurée.

    L'emplacement est toujours ``<racine>/<skill_id>/<numéro>``. Les anciennes
    lignes incluent parfois la racine dans ``storage_path`` (relative au processus
    ou absolue) : ne pas la préfixer à nouveau et ne pas la suivre hors du volume
    configuré. Un volume déplacé reste lisible sans migration des lignes.
    """

    anchor = storage_directory().resolve()
    canonical = (anchor / revision.skill_id / str(revision.number)).resolve()
    if not canonical.is_relative_to(anchor):
        raise SkillError(
            "Lecture refusée hors de la racine ACP_SKILLS_STORAGE_DIR.", status_code=409
        )
    if canonical.is_dir():
        return canonical

    # Si le volume attendu est absent, une ancienne adresse ne doit pas servir de
    # repli vers un autre volume. Une adresse relative moderne se résout sous la
    # racine ; une adresse héritée incluait déjà cette racine dans son préfixe.
    stored = Path(revision.storage_path).expanduser()
    if stored == Path(revision_storage_path(revision.skill_id, revision.number)):
        stored = anchor / stored
    if not stored.resolve().is_relative_to(anchor):
        raise SkillError(
            "Lecture refusée hors de la racine ACP_SKILLS_STORAGE_DIR ; "
            "la révision est absente du volume configuré.",
            status_code=409,
        )
    return canonical


def read_file(revision: SkillRevisionModel, path: str) -> SkillFileContent:
    """Lit un fichier **du manifeste** de la révision ; un chemin absent du manifeste est 404."""

    entry = next(
        (item for item in (revision.files or []) if item.get("path") == path), None
    )
    if entry is None:
        raise SkillError(
            f"Fichier « {path} » absent du manifeste de cette révision.", status_code=404
        )
    if not entry.get("text"):
        return SkillFileContent(
            path=entry["path"],
            text=False,
            content=None,
            truncated=False,
            size=int(entry.get("size", 0)),
            sha256=str(entry.get("sha256", "")),
        )
    root = revision_root(revision)
    target = root.joinpath(*str(entry["path"]).split("/"))
    anchor = root.resolve()
    if anchor not in target.resolve().parents:
        raise SkillError("Lecture refusée hors du stockage de la révision.", status_code=404)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise SkillError(
            f"Fichier « {path} » illisible dans le stockage de la révision ({exc}).",
            status_code=404,
        ) from exc
    text = scan_module.decode_text(data)
    if text is None:
        return SkillFileContent(
            path=entry["path"],
            text=False,
            content=None,
            truncated=False,
            size=int(entry.get("size", 0)),
            sha256=str(entry.get("sha256", "")),
        )
    truncated = len(text) > SKILL_FILE_CONTENT_MAX_CHARS
    return SkillFileContent(
        path=entry["path"],
        text=True,
        content=text[:SKILL_FILE_CONTENT_MAX_CHARS],
        truncated=truncated,
        size=int(entry.get("size", 0)),
        sha256=str(entry.get("sha256", "")),
    )


# --- Catalogue et recherche --------------------------------------------------


@lru_cache(maxsize=1)
def catalog_entries() -> tuple[SkillCatalogEntry, ...]:
    """Catalogue statique de dépôts de skills cités par la documentation Hermes."""

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return tuple(SkillCatalogEntry.model_validate(entry) for entry in raw)


def search(db: Session, query: str | None = None) -> SkillSearchResult:
    """Recherche dans les skills installés (nom, description, catégorie) et dans le catalogue."""

    needle = (query or "").strip().lower()
    installed = []
    for skill in db.query(SkillModel).order_by(SkillModel.name).all():
        haystack = " ".join(
            [skill.name, skill.display_name or "", skill.description or "", skill.category or ""]
        ).lower()
        if not needle or needle in haystack:
            installed.append(skill_summary(db, skill))
    catalog = [
        entry
        for entry in catalog_entries()
        if not needle
        or needle
        in " ".join([entry.id, entry.display_name, entry.description, entry.repository, entry.path]).lower()
    ]
    return SkillSearchResult(installed=installed, catalog=catalog)


# --- Sérialisation -----------------------------------------------------------


def revision_contract(revision: SkillRevisionModel) -> SkillRevision:
    return SkillRevision(
        id=revision.id,
        skill_id=revision.skill_id,
        number=revision.number,
        fingerprint=revision.fingerprint,
        files=[SkillFile.model_validate(entry) for entry in (revision.files or [])],
        frontmatter=revision.frontmatter or {},
        license=revision.license,
        dependencies=SkillDependencies.model_validate(revision.dependencies or {}),
        scan=[SkillScanFinding.model_validate(entry) for entry in (revision.scan or [])],
        kind=revision.kind,
        change_summary=SkillRevisionDiff.model_validate(revision.change_summary or {}),
        requires_approval=bool(revision.requires_approval),
        approved=revision.approved_at is not None,
        approved_at=revision.approved_at,
        source_ref=revision.source_ref or "",
        note=revision.note or "",
        created_at=revision.created_at,
        superseded_at=revision.superseded_at,
    )


def binding_contract(binding: SkillBindingModel, skill: SkillModel, number: int) -> SkillBinding:
    return SkillBinding(
        id=binding.id,
        skill_id=binding.skill_id,
        skill_name=skill.name,
        project_id=binding.project_id,
        revision_id=binding.revision_id,
        revision_number=number,
        enabled=bool(binding.enabled),
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        revoked_at=binding.revoked_at,
    )


def _revisions_of(db: Session, skill_id: str) -> list[SkillRevisionModel]:
    return (
        db.query(SkillRevisionModel)
        .filter_by(skill_id=skill_id)
        .order_by(SkillRevisionModel.number)
        .all()
    )


def _bindings_of(db: Session, skill_id: str) -> list[SkillBindingModel]:
    return (
        db.query(SkillBindingModel)
        .filter_by(skill_id=skill_id)
        .order_by(SkillBindingModel.created_at, SkillBindingModel.id)
        .all()
    )


def _current_revision(db: Session, skill: SkillModel) -> SkillRevisionModel | None:
    if not skill.current_revision_id:
        return None
    return db.get(SkillRevisionModel, skill.current_revision_id)


def _requires_approval(revision: SkillRevisionModel | None) -> bool:
    return bool(revision is not None and revision.requires_approval and revision.approved_at is None)


def skill_summary(db: Session, skill: SkillModel) -> SkillSummary:
    current = _current_revision(db, skill)
    active = [
        binding
        for binding in _bindings_of(db, skill.id)
        if binding.revoked_at is None and binding.enabled
    ]
    return SkillSummary(
        id=skill.id,
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description or "",
        category=skill.category or "general",
        kind=skill.kind,
        source_kind=skill.source_kind,
        origin=skill.origin or "",
        status=skill.status,
        current_revision_number=current.number if current is not None else None,
        binding_count=len(active),
        requires_approval=_requires_approval(current),
        created_at=skill.created_at,
        updated_at=skill.updated_at,
        revoked_at=skill.revoked_at,
    )


def skill_detail(
    db: Session, skill: SkillModel, *, visible_project_ids: set[str] | None = None
) -> SkillDetail:
    """Détail d'un skill ; ``visible_project_ids`` filtre les rattachements exposés.

    Les rattachements révèlent quels projets utilisent quel skill : ils sont restreints aux
    projets réellement accessibles à l'appelant, comme ``GET /skills/bindings``. Le compteur
    ``binding_count`` reste global (nombre de rattachements actifs, sans nommer les projets).
    """

    revisions = _revisions_of(db, skill.id)
    numbers = {revision.id: revision.number for revision in revisions}
    current = _current_revision(db, skill)
    notes: list[str] = []
    if skill.kind == "native_plugin":
        notes.append(NATIVE_PLUGIN_NOTE)
    if _requires_approval(current):
        notes.append(
            f"La révision {current.number} exige une approbation par un propriétaire "
            "de la plateforme avant activation."
        )
    if current is not None and any(
        entry.get("level") == "danger" for entry in (current.scan or [])
    ):
        notes.append(
            "Le contrôle automatique signale des constats de niveau « danger » : "
            "relisez les fichiers concernés avant d'approuver."
        )
    if skill.status == "revoked":
        notes.append(
            "Skill révoqué : les rattachements sont retirés et l'historique reste lisible."
        )
    summary = skill_summary(db, skill)
    return SkillDetail(
        **summary.model_dump(),
        current_revision=revision_contract(current) if current is not None else None,
        revisions=[revision_contract(revision) for revision in revisions],
        bindings=[
            binding_contract(binding, skill, numbers.get(binding.revision_id, 0))
            for binding in _bindings_of(db, skill.id)
            if visible_project_ids is None or binding.project_id in visible_project_ids
        ],
        apply_notes=notes,
    )


# --- Événements --------------------------------------------------------------


def record_event(
    db: Session, event_type: str, payload: dict[str, Any], *, project_id: str | None = None
) -> None:
    """Trace d'audit durable, sans secret ni contenu de fichier.

    ``store_event`` alloue le numéro de journal : une ligne écrite sans lui sort de
    la page projet jusqu'au prochain redémarrage, puis y remonte hors d'ordre.
    ``commit=False`` laisse la transaction à l'appelant, comme avant.
    """

    store_event(
        db,
        Event(type=event_type, project_id=project_id, payload=payload),
        commit=False,
    )


# --- Opérations --------------------------------------------------------------


def materialize_source(db: Session, source: Any) -> sources_module.MaterializedSource:
    """Matérialise une source en appliquant la configuration d'environnement courante.

    Si le téléchargement GitHub atteint une adresse privée explicitement allowlistée
    (``ACP_OUTBOUND_PRIVATE_ALLOWLIST``), l'usage est journalisé par l'appelant comme
    l'exige la spécification : ``outbound.private_allowlist_used`` avec ``purpose``.
    """

    # Téléchargement possible jusqu'à 25 Mio : les lectures de contrôle de la route ne
    # gardent pas leur transaction pendant ce temps (acp_api.transactions).
    end_read_transaction(db)
    enabled = sources_module.github_enabled(os.environ)
    client = None
    allowlist_used: set[tuple[str, str]] = set()
    if getattr(source, "kind", "") == "github" and enabled:
        client = github_client_factory()
        client.on_private_allowlist_used = lambda host, address: allowlist_used.add(
            (host, address)
        )
    try:
        return sources_module.materialize(
            source,
            allowed_dirs=sources_module.allowed_directories(os.environ),
            github_enabled=enabled,
            github_token=sources_module.github_token(os.environ),
            pinned_client=client,
        )
    finally:
        for host, address in sorted(allowlist_used):
            record_event(
                db,
                "outbound.private_allowlist_used",
                {"host": host, "address": address, "purpose": GITHUB_IMPORT_PURPOSE},
            )


def _resolve_name(content: RevisionContent, requested: str | None) -> str:
    if requested:
        return requested
    candidate = content.frontmatter.get("name")
    if isinstance(candidate, str) and candidate.strip():
        try:
            return validate_slug(candidate.strip())
        except ValueError as exc:
            raise SkillError(
                f"Nom de skill invalide dans le frontmatter : {exc}. Fournissez « name » dans la requête."
            ) from exc
    raise SkillError(
        "Nom de skill absent : ajoutez « name » au frontmatter de SKILL.md ou au corps de la requête."
    )


def _display_name(content: RevisionContent, name: str) -> str:
    for key in ("display_name", "title"):
        value = content.frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    return name[:120]


def _category(content: RevisionContent) -> str:
    metadata = content.frontmatter.get("metadata")
    hermes = metadata.get("hermes") if isinstance(metadata, Mapping) else None
    for holder, key in ((hermes, "category"), (content.frontmatter, "category")):
        if isinstance(holder, Mapping):
            value = holder.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:64]
    return "general"


def _description(content: RevisionContent) -> str:
    value = content.frontmatter.get("description")
    return value.strip() if isinstance(value, str) else ""


def import_skill(
    db: Session, *, source: Any, name: str | None, note: str, principal: str
) -> SkillModel:
    """Crée un skill et sa révision 1 (statut ``draft``)."""

    content = analyse(materialize_source(db, source))
    resolved = _resolve_name(content, name)
    if db.query(SkillModel).filter_by(name=resolved).first() is not None:
        raise SkillError(
            f"Un skill nommé « {resolved} » existe déjà.", status_code=409
        )
    skill = SkillModel(
        name=resolved,
        display_name=_display_name(content, resolved),
        description=_description(content),
        category=_category(content),
        kind=content.kind,
        source_kind=content.source_kind,
        origin=content.origin,
        status="draft",
        created_by_user_id=principal,
    )
    db.add(skill)
    db.flush()
    revision = _add_revision(db, skill, content, number=1, note=note, principal=principal)
    skill.current_revision_id = revision.id
    record_event(
        db,
        "skill.imported",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "kind": skill.kind,
            "source_kind": skill.source_kind,
            "revision_number": revision.number,
        },
    )
    return skill


def _add_revision(
    db: Session,
    skill: SkillModel,
    content: RevisionContent,
    *,
    number: int,
    note: str,
    principal: str,
    previous: SkillRevisionModel | None = None,
) -> SkillRevisionModel:
    """Écrit les fichiers puis la ligne de révision ; l'approbation est reportée si déjà acquise."""

    diff = compute_revision_diff(previous, content)
    store_revision(storage_directory(), skill.id, number, content.files)
    storage_path = revision_storage_path(skill.id, number)
    revision = SkillRevisionModel(
        skill_id=skill.id,
        number=number,
        fingerprint=content.fingerprint,
        files=content.manifest,
        skill_md=content.skill_md,
        frontmatter=content.frontmatter,
        license=content.license,
        dependencies=content.dependencies.model_dump(mode="json"),
        scan=[finding.model_dump(mode="json") for finding in content.scan],
        kind=content.kind,
        storage_path=storage_path,
        change_summary=diff.model_dump(mode="json"),
        requires_approval=1 if diff.requires_approval else 0,
        created_by_user_id=principal,
        note=note,
        source_ref=content.source_ref,
    )
    inherited = _inherit_approval(db, skill, revision)
    if not inherited and previous is not None and _requires_approval(previous):
        # Le contenu repris n'a jamais été relu : une révision « neutre » (retour arrière,
        # simple édition documentaire) ne doit pas rendre activable ce qui attendait une
        # approbation. Sans cette règle, un rollback blanchirait n'importe quel contenu.
        diff.requires_approval = True
        diff.reasons.append(
            f"contenu jamais approuvé : la révision {previous.number} attend toujours "
            "une approbation"
        )
        revision.change_summary = diff.model_dump(mode="json")
        revision.requires_approval = 1
    db.add(revision)
    db.flush()
    return revision


def _inherit_approval(db: Session, skill: SkillModel, revision: SkillRevisionModel) -> bool:
    """Une empreinte déjà approuvée reste approuvée (retour arrière sans nouvelle relecture)."""

    approved = (
        db.query(SkillRevisionModel)
        .filter_by(skill_id=skill.id, approval_fingerprint=revision.fingerprint)
        .filter(SkillRevisionModel.approved_at.is_not(None))
        .order_by(SkillRevisionModel.number.desc())
        .first()
    )
    if approved is None:
        return False
    revision.approved_by_user_id = approved.approved_by_user_id
    revision.approved_at = approved.approved_at
    revision.approval_fingerprint = approved.approval_fingerprint
    return True


def _ensure_not_revoked(skill: SkillModel, action: str) -> None:
    if skill.status == "revoked":
        raise SkillError(
            f"Skill révoqué : {action} impossible. La révocation est irréversible.",
            status_code=409,
        )


def create_revision(
    db: Session, skill: SkillModel, *, source: Any, note: str, principal: str
) -> SkillModel:
    """Ajoute une révision ; les bindings restent sur leur révision jusqu'à ``activate``."""

    _ensure_not_revoked(skill, "création d'une révision")
    content = analyse(materialize_source(db, source))
    previous = _current_revision(db, skill)
    number = (
        db.query(SkillRevisionModel)
        .filter_by(skill_id=skill.id)
        .order_by(SkillRevisionModel.number.desc())
        .first()
    )
    next_number = (number.number if number is not None else 0) + 1
    revision = _add_revision(
        db, skill, content, number=next_number, note=note, principal=principal, previous=previous
    )
    if previous is not None:
        previous.superseded_at = utcnow()
    skill.current_revision_id = revision.id
    skill.kind = content.kind
    skill.description = _description(content) or skill.description
    skill.category = _category(content)
    skill.updated_at = utcnow()
    record_event(
        db,
        "skill.revision_created",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "revision_number": revision.number,
            "requires_approval": bool(revision.requires_approval),
        },
    )
    return skill


def revision_by_number(db: Session, skill: SkillModel, number: int) -> SkillRevisionModel:
    revision = (
        db.query(SkillRevisionModel).filter_by(skill_id=skill.id, number=number).first()
    )
    if revision is None:
        raise SkillError(
            f"Révision {number} introuvable pour ce skill.", status_code=404
        )
    return revision


def approve_revision(
    db: Session, skill: SkillModel, number: int, *, principal: str, comment: str
) -> SkillModel:
    _ensure_not_revoked(skill, "approbation d'une révision")
    revision = revision_by_number(db, skill, number)
    revision.approved_by_user_id = principal
    revision.approved_at = utcnow()
    revision.approval_fingerprint = revision.fingerprint
    skill.updated_at = utcnow()
    record_event(
        db,
        "skill.approved",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "revision_number": revision.number,
            "fingerprint": revision.fingerprint,
            "comment": comment,
        },
    )
    return skill


def activate_skill(db: Session, skill: SkillModel) -> SkillModel:
    """Active le skill et aligne les bindings actifs sur la révision courante."""

    _ensure_not_revoked(skill, "activation")
    current = _current_revision(db, skill)
    if current is None:
        raise SkillError("Aucune révision à activer pour ce skill.", status_code=409)
    if _requires_approval(current):
        raise SkillError(
            f"Activation impossible : la révision {current.number} exige une approbation "
            "par un propriétaire de la plateforme "
            f"(POST /skills/{skill.id}/revisions/{current.number}/approve).",
            status_code=409,
        )
    skill.status = "active"
    skill.updated_at = utcnow()
    for binding in _bindings_of(db, skill.id):
        if binding.revoked_at is None and binding.enabled:
            binding.revision_id = current.id
            binding.updated_at = utcnow()
    record_event(
        db,
        "skill.activated",
        {"skill_id": skill.id, "name": skill.name, "revision_number": current.number},
    )
    return skill


def disable_skill(db: Session, skill: SkillModel) -> SkillModel:
    """Désactivation réversible : les bindings sont conservés mais ne résolvent plus."""

    _ensure_not_revoked(skill, "désactivation")
    skill.status = "disabled"
    skill.updated_at = utcnow()
    record_event(db, "skill.disabled", {"skill_id": skill.id, "name": skill.name})
    return skill


def revoke_skill(db: Session, skill: SkillModel, *, reason: str) -> SkillModel:
    """Révocation irréversible : statut ``revoked`` et rattachements retirés."""

    _ensure_not_revoked(skill, "révocation")
    now = utcnow()
    skill.status = "revoked"
    skill.revoked_at = now
    skill.revoked_reason = reason
    skill.updated_at = now
    revoked: list[str] = []
    for binding in _bindings_of(db, skill.id):
        if binding.revoked_at is None:
            binding.revoked_at = now
            binding.enabled = 0
            binding.updated_at = now
            revoked.append(binding.id)
    record_event(
        db,
        "skill.revoked",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "reason": reason,
            "revoked_binding_ids": revoked,
        },
    )
    return skill


def rollback_skill(
    db: Session, skill: SkillModel, *, revision_number: int, note: str, principal: str
) -> SkillModel:
    """Crée une nouvelle révision reprenant le contenu d'une révision antérieure."""

    _ensure_not_revoked(skill, "retour arrière")
    target = revision_by_number(db, skill, revision_number)
    files = _files_of(target)
    materialized = sources_module.MaterializedSource(
        files=files,
        source_kind=skill.source_kind,
        origin=skill.origin,
        source_ref=target.source_ref or "",
    )
    content = analyse(materialized)
    previous = _current_revision(db, skill)
    last = (
        db.query(SkillRevisionModel)
        .filter_by(skill_id=skill.id)
        .order_by(SkillRevisionModel.number.desc())
        .first()
    )
    next_number = (last.number if last is not None else 0) + 1
    revision = _add_revision(
        db, skill, content, number=next_number, note=note, principal=principal, previous=previous
    )
    if previous is not None and previous.id != revision.id:
        previous.superseded_at = utcnow()
    skill.current_revision_id = revision.id
    skill.kind = content.kind
    skill.updated_at = utcnow()
    record_event(
        db,
        "skill.rolled_back",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "from_revision_number": target.number,
            "revision_number": revision.number,
        },
    )
    return skill


def _files_of(revision: SkillRevisionModel) -> list[tuple[str, bytes]]:
    """Relit les fichiers d'une révision depuis son stockage, en suivant son manifeste."""

    root = revision_root(revision)
    anchor = root.resolve()
    files: list[tuple[str, bytes]] = []
    for entry in revision.files or []:
        path = str(entry.get("path", ""))
        target = root.joinpath(*path.split("/"))
        if anchor not in target.resolve().parents:
            raise SkillError("Lecture refusée hors du stockage de la révision.", status_code=409)
        try:
            files.append((path, target.read_bytes()))
        except OSError as exc:
            raise SkillError(
                f"Retour arrière impossible : fichier « {path} » illisible ({exc}).",
                status_code=409,
            ) from exc
    return files


# --- Bindings ----------------------------------------------------------------


def create_binding(
    db: Session, skill: SkillModel, *, project_id: str, principal: str
) -> SkillBindingModel:
    """Rattache un skill actif à un projet ; un rattachement révoqué est réactivé."""

    if skill.status != "active":
        raise SkillError(
            f"Skill « {skill.name} » non actif (statut « {skill.status} ») : "
            "rattachement impossible.",
            status_code=409,
        )
    current = _current_revision(db, skill)
    if current is None:
        raise SkillError("Aucune révision courante : rattachement impossible.", status_code=409)
    if _requires_approval(current):
        # Sans ce contrôle, créer un rattachement contournerait la porte d'``activate`` :
        # le projet recevrait la révision courante, jamais relue, comme extension active.
        raise SkillError(
            f"Rattachement impossible : la révision {current.number} exige une approbation "
            "par un propriétaire de la plateforme "
            f"(POST /skills/{skill.id}/revisions/{current.number}/approve).",
            status_code=409,
        )
    existing = (
        db.query(SkillBindingModel).filter_by(skill_id=skill.id, project_id=project_id).first()
    )
    if existing is not None and existing.revoked_at is None and existing.enabled:
        raise SkillError(
            "Ce skill est déjà rattaché à ce projet.", status_code=409
        )
    if existing is not None:
        existing.revoked_at = None
        existing.enabled = 1
        existing.revision_id = current.id
        existing.updated_at = utcnow()
        binding = existing
    else:
        binding = SkillBindingModel(
            skill_id=skill.id,
            project_id=project_id,
            revision_id=current.id,
            enabled=1,
            created_by_user_id=principal,
        )
        db.add(binding)
        db.flush()
    record_event(
        db,
        "skill.binding_created",
        {
            "skill_id": skill.id,
            "name": skill.name,
            "binding_id": binding.id,
            "project_id": project_id,
            "revision_number": current.number,
        },
        project_id=project_id,
    )
    return binding


def revoke_binding(db: Session, binding: SkillBindingModel, skill: SkillModel) -> SkillBindingModel:
    """Révocation idempotente : un rattachement déjà révoqué est renvoyé tel quel."""

    if binding.revoked_at is not None:
        return binding
    now = utcnow()
    binding.revoked_at = now
    binding.enabled = 0
    binding.updated_at = now
    record_event(
        db,
        "skill.binding_revoked",
        {
            "skill_id": binding.skill_id,
            "name": skill.name,
            "binding_id": binding.id,
            "project_id": binding.project_id,
        },
        project_id=binding.project_id,
    )
    return binding


def revision_number_of(db: Session, revision_id: str) -> int:
    revision = db.get(SkillRevisionModel, revision_id)
    return revision.number if revision is not None else 0
