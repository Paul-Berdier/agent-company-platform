"""Bibliothèque de livrables (``/artifacts``) et liens signés.

Un contenu produit par un test est traité comme non fiable : téléchargement forcé,
``nosniff``, CSP restrictive, jamais d'exécution dans l'origine de la plateforme.

Trois règles portent la sécurité de ce routeur :

1. **Le type servi vient d'une allowlist serveur** (§7), croisée entre le type déclaré
   et l'extension du nom d'origine. Aucun reniflage du contenu, et ``text/html``,
   ``image/svg+xml`` et les archives ne sont jamais servis en ligne.
2. **Aucun nom fourni par le client n'entre dans un chemin** : la clé de stockage est
   un sha256 calculé côté serveur, le nom d'origine ne sort que dans un
   ``Content-Disposition`` assaini.
3. **Un lien signé n'ouvre jamais un projet** : il porte un artefact et un
   utilisateur, expire, se révoque, et les droits du titulaire sont revérifiés à
   chaque téléchargement.

Le routeur est déclaré sans préfixe : chaque route porte son chemin complet.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from acp_contracts import ArtifactLink, ArtifactPage, ArtifactSummary
from acp_database.models import (
    ArtifactLinkModel,
    ArtifactModel,
    TaskModel,
    TaskRunModel,
    WorkerLeaseModel,
    WorkerModel,
)

from ..artifacts_storage import (
    ArtifactKeyInvalid,
    ArtifactNotFound,
    ArtifactStorage,
    ArtifactStorageError,
    ArtifactStorageFull,
    ArtifactStorageUnavailable,
    ArtifactTooLarge,
    LocalArtifactStorage,
    artifact_max_bytes,
    artifact_max_bytes_per_run,
    local_artifact_storage,
    storage_error_from_oserror,
)
from ..alerts_service import open_or_escalate_alert
from ..deps import accessible_project_ids, ensure_access, get_db, get_principal
from ..security import authenticate_session
from ..signing import (
    DEFAULT_LINK_TTL_SECONDS,
    MAX_LINK_TTL_SECONDS,
    TOKEN_MAX_CHARS,
    ArtifactSigningNotConfigured,
    ArtifactTokenExpired,
    ArtifactTokenInvalid,
    load_signing_keys,
    sign_artifact_token,
    token_hash,
    verify_artifact_token,
)
from .workers import expire_task_leases

router = APIRouter(tags=["artifacts"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
STREAM_CHUNK_BYTES = 64 * 1024
FILE_NAME_MAX_CHARS = 100

#: Bornes du lecteur multipart. Elles protègent l'analyse elle-même : un émetteur
#: hostile ne doit pas pouvoir faire grossir un tampon en envoyant un préambule, des
#: en-têtes de partie ou un champ texte sans fin.
MULTIPART_PREAMBLE_MAX_BYTES = 4096
MULTIPART_HEADERS_MAX_BYTES = 8192
MULTIPART_FIELD_MAX_BYTES = 8192
MULTIPART_MAX_PARTS = 16
MULTIPART_SPOOL_MAX_BYTES = 1024 * 1024
#: Marge acceptée entre ``Content-Length`` et la taille utile (bornes et en-têtes
#: des parties) pour refuser un corps manifestement trop gros avant de le lire.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
FILE_FIELD_NAME = "file"

#: Origine séparée servant les aperçus signés ; vide, les liens pointent vers l'API.
ARTIFACT_PUBLIC_ORIGIN_ENV = "ACP_ARTIFACT_PUBLIC_ORIGIN"

CONTENT_SECURITY_POLICY = "default-src 'none'; sandbox"

#: Types dont l'aperçu en ligne est autorisé (§7). Toute autre valeur est servie en
#: ``application/octet-stream`` avec téléchargement forcé.
PREVIEWABLE_CONTENT_TYPES: dict[str, str] = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
    "video/webm": "video/webm",
    "video/mp4": "video/mp4",
    # Le texte et le JSON sont servis en texte brut : jamais interprétés.
    "text/plain": "text/plain; charset=utf-8",
    "application/json": "text/plain; charset=utf-8",
}

#: Types connus mais jamais servis en ligne, quelle que soit la déclaration.
NEVER_INLINE_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "application/zip",
        "application/x-zip-compressed",
        "application/gzip",
        "application/x-tar",
        "application/javascript",
        "text/javascript",
        "text/css",
        "application/xml",
        "text/xml",
        "application/pdf",
    }
)

#: Extension → type de référence. Sert à détecter un désaccord avec le type déclaré.
EXTENSION_CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".webm": "video/webm",
    ".mp4": "video/mp4",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/plain",
    ".json": "application/json",
    ".ndjson": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "application/xhtml+xml",
    ".svg": "image/svg+xml",
    ".zip": "application/zip",
    ".gz": "application/gzip",
    ".tar": "application/x-tar",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".xml": "application/xml",
    ".pdf": "application/pdf",
}

OCTET_STREAM = "application/octet-stream"

#: Les deux bornes sont limitées à 19 chiffres (au-delà de 2^63, donc de toute taille
#: de fichier concevable). Sans cette limite, CPython refuse de convertir une chaîne
#: de plus de 4300 chiffres et le ``int()`` levait un ``ValueError`` non intercepté :
#: un simple en-tête ``Range`` suffisait à provoquer un 500. La RFC 9110 demande
#: d'ignorer un ``Range`` illisible ; le motif ne correspond plus, donc ``_parse_range``
#: rend ``None`` et la représentation entière est servie.
_RANGE_PATTERN = re.compile(r"^bytes=(\d{0,19})-(\d{0,19})$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_NAME_CHARACTERS = re.compile(r'["\\/]')


# --- Types et en-têtes (§7) -----------------------------------------------------


def safe_content_type(declared: str, original_name: str) -> tuple[str, bool]:
    """Type réellement servi et autorisation d'aperçu, depuis l'allowlist serveur.

    Un type de la liste « jamais en ligne » est écarté d'emblée : aucun nom d'origine
    ne réhabilite ``text/html``, ``image/svg+xml`` ou une archive (§7).

    Le type déclaré et l'extension du nom d'origine doivent ensuite concorder : un
    fichier ``piege.html`` annoncé ``image/png`` est un piège, pas une image. En cas
    de désaccord — ou de type inconnu — le contenu est servi en
    ``application/octet-stream`` et téléchargé.
    """

    normalized = (declared or "").split(";", 1)[0].strip().lower()
    if normalized in NEVER_INLINE_CONTENT_TYPES:
        return OCTET_STREAM, False
    suffix = PurePosixPath((original_name or "").replace("\\", "/")).suffix.lower()
    from_extension = EXTENSION_CONTENT_TYPES.get(suffix)

    if (
        from_extension is not None
        and normalized in PREVIEWABLE_CONTENT_TYPES
        and normalized != from_extension
    ):
        candidate = None
    elif from_extension is not None:
        candidate = from_extension
    else:
        candidate = normalized

    if candidate in NEVER_INLINE_CONTENT_TYPES:
        return OCTET_STREAM, False
    served = PREVIEWABLE_CONTENT_TYPES.get(candidate or "")
    if served is None:
        return OCTET_STREAM, False
    return served, True


def safe_file_name(original_name: str, artifact_id: str) -> str:
    """Nom de téléchargement assaini : jamais un chemin, jamais un en-tête injecté."""

    candidate = PurePosixPath((original_name or "").replace("\\", "/")).name
    candidate = _CONTROL_CHARACTERS.sub("", candidate)
    candidate = _UNSAFE_NAME_CHARACTERS.sub("", candidate)
    candidate = candidate.strip().strip(".")
    candidate = candidate[:FILE_NAME_MAX_CHARS].strip()
    return candidate or f"livrable-{artifact_id}"


def content_disposition(*, inline: bool, original_name: str, artifact_id: str) -> str:
    """En-tête ``Content-Disposition`` (RFC 6266) avec repli ASCII et forme UTF-8."""

    name = safe_file_name(original_name, artifact_id)
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_name:
        ascii_name = f"livrable-{artifact_id}"
    encoded = quote(name, safe="")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def content_headers(
    *, artifact: ArtifactModel, served_type: str, inline: bool
) -> dict[str, str]:
    """En-têtes de sécurité exigés par §6 et §7, identiques en 200 et en 206."""

    return {
        "Content-Type": served_type,
        "Content-Disposition": content_disposition(
            inline=inline,
            original_name=artifact.original_name or "",
            artifact_id=artifact.id,
        ),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
    }


# --- Stockage et pagination -----------------------------------------------------


def artifact_storage() -> LocalArtifactStorage:
    """Stockage courant, relu à chaque requête pour suivre la configuration."""

    return local_artifact_storage(os.environ)


def _summary(artifact: ArtifactModel) -> ArtifactSummary:
    return ArtifactSummary(
        id=artifact.id,
        project_id=artifact.project_id,
        task_run_id=artifact.task_run_id,
        kind=artifact.kind,
        stream_kind=artifact.stream_kind or "",
        original_name=artifact.original_name or "",
        content_type=artifact.content_type or OCTET_STREAM,
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        source=artifact.source or "worker",
        has_content=bool(artifact.storage_key) and artifact.deleted_at is None,
        created_at=artifact.created_at,
    )


def _encode_cursor(artifact: ArtifactModel) -> str:
    raw = f"{artifact.created_at.isoformat()}|{artifact.id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        moment, _, identifier = raw.partition("|")
        return datetime.fromisoformat(moment), identifier
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Curseur de pagination illisible : reprenez la liste au début.",
        ) from exc


# --- Lecture --------------------------------------------------------------------


@router.get("/artifacts", response_model=ArtifactPage)
def list_artifacts(
    project_id: str | None = None,
    task_run_id: str | None = None,
    stream_kind: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> ArtifactPage:
    """Bibliothèque paginée ; un filtre client ne peut que restreindre la portée."""

    query = db.query(ArtifactModel).filter(
        ArtifactModel.project_id.in_(accessible_project_ids(db, principal))
    )
    if project_id:
        query = query.filter(ArtifactModel.project_id == project_id)
    if task_run_id:
        query = query.filter(ArtifactModel.task_run_id == task_run_id)
    if stream_kind:
        query = query.filter(ArtifactModel.stream_kind == stream_kind)
    if cursor:
        moment, identifier = _decode_cursor(cursor)
        query = query.filter(
            or_(
                ArtifactModel.created_at < moment,
                and_(
                    ArtifactModel.created_at == moment,
                    ArtifactModel.id < identifier,
                ),
            )
        )
    rows = (
        query.order_by(ArtifactModel.created_at.desc(), ArtifactModel.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return ArtifactPage(
        items=[_summary(row) for row in page],
        next_cursor=_encode_cursor(page[-1]) if has_more and page else None,
    )


def _readable_artifact(db: Session, principal: str, artifact_id: str) -> ArtifactModel:
    """Livrable visible par ce principal ; l'absence de droit se lit « introuvable ».

    Un 403 distinguerait un identifiant existant d'un identifiant inconnu : la
    bibliothèque d'un autre projet ne doit pas être énumérable.
    """

    artifact = db.get(ArtifactModel, artifact_id)
    if artifact is None or artifact.project_id not in accessible_project_ids(
        db, principal
    ):
        raise HTTPException(status_code=404, detail="Livrable introuvable")
    return artifact


@router.get("/artifacts/{artifact_id}", response_model=ArtifactSummary)
def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> ArtifactSummary:
    """Métadonnées d'un livrable ; ni la clé de stockage ni le chemin ne sortent."""

    return _summary(_readable_artifact(db, principal, artifact_id))


# --- Téléchargement -------------------------------------------------------------


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Interprète un ``Range`` simple ; ``None`` signifie « servir tout le contenu ».

    Une plage illisible ou une unité inconnue n'est pas une erreur : la RFC 9110
    demande d'ignorer l'en-tête et de servir la représentation entière.
    """

    if not header:
        return None
    match = _RANGE_PATTERN.match(header.strip())
    if match is None:
        return None
    first, last = match.group(1), match.group(2)
    if not first and not last:
        return None
    if not first:
        length = int(last)
        if length == 0:
            raise _range_not_satisfiable(size)
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
    if start >= size or end < start:
        raise _range_not_satisfiable(size)
    return start, min(end, size - 1)


def _range_not_satisfiable(size: int) -> HTTPException:
    return HTTPException(
        status_code=416,
        detail="Plage demandée hors du contenu.",
        headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
    )


def _blob_stream(handle: BinaryIO, start: int, length: int) -> Iterator[bytes]:
    """Diffuse ``length`` octets depuis ``start`` ; le descripteur est toujours fermé."""

    try:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(STREAM_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        handle.close()


def _open_content(
    storage: ArtifactStorage, artifact: ArtifactModel
) -> tuple[BinaryIO, int]:
    if artifact.deleted_at is not None:
        raise HTTPException(
            status_code=410,
            detail="Contenu supprimé par la rétention ; seules les métadonnées subsistent.",
        )
    if not artifact.storage_key:
        raise HTTPException(
            status_code=404,
            detail="Ce livrable n'a pas de contenu téléversé.",
        )
    try:
        handle = storage.open(artifact.storage_key)
    except (ArtifactNotFound, ArtifactKeyInvalid) as exc:
        # Une clé hors de l'adressage par contenu — ligne corrompue, migration
        # bâclée — ne doit pas devenir une erreur serveur : le stockage a déjà
        # refusé d'y toucher, la route répond « pas de contenu ».
        raise HTTPException(
            status_code=404,
            detail="Ce livrable n'a pas de contenu téléversé.",
        ) from exc
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    return handle, size


def _content_response(
    *, artifact: ArtifactModel, storage: ArtifactStorage, range_header: str | None
) -> Response:
    handle, size = _open_content(storage, artifact)
    try:
        window = _parse_range(range_header, size)
    except HTTPException:
        handle.close()
        raise
    served_type, inline = safe_content_type(
        artifact.content_type or "", artifact.original_name or ""
    )
    headers = content_headers(artifact=artifact, served_type=served_type, inline=inline)
    if window is None:
        start, end = 0, size - 1
        status_code = 200
    else:
        start, end = window
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    length = 0 if size == 0 else end - start + 1
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        _blob_stream(handle, start, length),
        status_code=status_code,
        headers=headers,
        media_type=served_type,
    )


@router.get("/artifacts/{artifact_id}/content")
def download_artifact_content(
    artifact_id: str,
    request: Request,
    token: str | None = Query(default=None, max_length=TOKEN_MAX_CHARS),
    db: Session = Depends(get_db),
) -> Response:
    """Contenu d'un livrable, par session ou par lien signé, toujours en flux."""

    if token:
        principal = _link_principal(db, artifact_id, token)
    else:
        principal = _session_principal(request, db)
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentification requise")
    artifact = _readable_artifact(db, principal, artifact_id)
    return _content_response(
        artifact=artifact,
        storage=artifact_storage(),
        range_header=request.headers.get("range"),
    )


def _session_principal(request: Request, db: Session) -> str | None:
    """Identité de session, ou ``None`` : cette route accepte aussi un lien signé."""

    context = authenticate_session(db, request.cookies.get("acp_session"))
    return context.user.id if context is not None else None


# --- Liens signés (§5.3, §6) ----------------------------------------------------


class ArtifactLinkCreated(ArtifactLink):
    """``ArtifactLink`` augmenté de l'identifiant nécessaire à la révocation.

    Le contrat partagé ne porte pas d'identifiant (le jeton, lui, ne doit pas servir
    de clé de révocation : il circule dans une URL). La réponse est donc un
    sur-ensemble strict du contrat, sans en modifier un seul champ.
    """

    id: str


def _refused_link(detail: str) -> HTTPException:
    """Toutes les raisons de refus d'un lien répondent 403, sans détail exploitable."""

    return HTTPException(status_code=403, detail=detail)


def _link_principal(db: Session, artifact_id: str, token: str) -> str:
    """Titulaire d'un lien valide pour cet artefact, ou refus explicite.

    Le jeton ne porte pas d'utilisateur : le titulaire vient de la ligne
    ``artifact_links`` retrouvée par empreinte, et la signature doit correspondre à
    ce couple. Les droits du titulaire sont revérifiés à chaque téléchargement :
    une perte d'accès ferme le lien sans avoir à le révoquer.
    """

    link = (
        db.query(ArtifactLinkModel).filter_by(token_hash=token_hash(token)).first()
    )
    if link is None or link.artifact_id != artifact_id:
        raise _refused_link("Lien invalide ou inconnu.")
    if link.revoked_at is not None:
        raise _refused_link("Lien révoqué.")
    now = datetime.now(timezone.utc)
    try:
        keys = load_signing_keys(os.environ)
        verify_artifact_token(
            token,
            keys,
            artifact_id=artifact_id,
            user_id=link.user_id,
            now=now,
        )
    except ArtifactTokenExpired as exc:
        raise _refused_link("Lien expiré : demandez-en un nouveau.") from exc
    except ArtifactTokenInvalid as exc:
        raise _refused_link("Lien invalide ou inconnu.") from exc
    except ArtifactSigningNotConfigured as exc:
        # La configuration du serveur ne se déduit pas d'une requête non authentifiée.
        raise _refused_link("Lien invalide ou inconnu.") from exc
    if _as_utc(link.expires_at) <= now:
        raise _refused_link("Lien expiré : demandez-en un nouveau.")
    artifact = db.get(ArtifactModel, artifact_id)
    if artifact is None:
        raise _refused_link("Lien invalide ou inconnu.")
    try:
        allowed = accessible_project_ids(db, link.user_id)
    except HTTPException as exc:
        # Compte désactivé ou supprimé : le lien meurt avec lui, et le refus reste
        # un refus de lien — pas une invitation à s'authentifier.
        raise _refused_link(
            "Le titulaire de ce lien n'a plus accès à ce livrable."
        ) from exc
    if artifact.project_id not in allowed:
        raise _refused_link("Le titulaire de ce lien n'a plus accès à ce livrable.")
    link.used_count = (link.used_count or 0) + 1
    db.commit()
    return link.user_id


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _link_url(artifact_id: str, token: str) -> str:
    """URL du lien : origine d'aperçu dédiée si elle existe, sinon celle de l'API.

    L'origine n'est jamais déduite de l'en-tête ``Host`` : un en-tête falsifié
    fabriquerait sinon un lien pointant vers un domaine tiers, avec un jeton valide
    dans la chaîne de requête.
    """

    origin = (os.environ.get(ARTIFACT_PUBLIC_ORIGIN_ENV) or "").strip().rstrip("/")
    if not origin:
        origin = (os.environ.get("ACP_API_URL") or "").strip().rstrip("/")
    path = (
        f"/artifacts/{quote(artifact_id, safe='')}/content"
        f"?token={quote(token, safe='')}"
    )
    return f"{origin}{path}" if origin else path


@router.post(
    "/artifacts/{artifact_id}/link",
    response_model=ArtifactLinkCreated,
    status_code=201,
)
def create_artifact_link(
    artifact_id: str,
    ttl_seconds: int = Query(
        default=DEFAULT_LINK_TTL_SECONDS, ge=1, le=MAX_LINK_TTL_SECONDS
    ),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> ArtifactLinkCreated:
    """Crée un lien signé, borné et révocable, lié à ce livrable et à ce demandeur."""

    artifact = _readable_artifact(db, principal, artifact_id)
    if not artifact.storage_key or artifact.deleted_at is not None:
        raise HTTPException(
            status_code=404, detail="Ce livrable n'a pas de contenu téléversé."
        )
    try:
        keys = load_signing_keys(os.environ)
    except ArtifactSigningNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    token = sign_artifact_token(artifact.id, principal, expires_at, keys[0])
    link = ArtifactLinkModel(
        artifact_id=artifact.id,
        user_id=principal,
        token_hash=token_hash(token),
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return ArtifactLinkCreated(
        id=link.id,
        artifact_id=artifact.id,
        url=_link_url(artifact.id, token),
        expires_at=expires_at,
    )


@router.delete("/artifacts/links/{link_id}", status_code=204)
def revoke_artifact_link(
    link_id: str,
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> Response:
    """Révoque un lien : son titulaire, ou un owner du projet du livrable."""

    link = db.get(ArtifactLinkModel, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Lien introuvable")
    if link.user_id != principal:
        artifact = db.get(ArtifactModel, link.artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Lien introuvable")
        try:
            ensure_access(
                db, principal, project_id=artifact.project_id, minimum_role="owner"
            )
        except HTTPException as exc:
            # Ni l'existence du lien ni celle du livrable ne sont énumérables.
            raise HTTPException(status_code=404, detail="Lien introuvable") from exc
    if link.revoked_at is None:
        link.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=204)


# --- Lecture multipart en flux --------------------------------------------------
#
# ``python-multipart`` n'est pas une dépendance de l'API, donc ``request.form()``
# n'est pas disponible. Ce lecteur est de toute façon préférable ici : l'analyseur
# de Starlette déverse la pièce entière dans un fichier temporaire **avant** que la
# route ne s'exécute, ce qui rendrait le plafond par fichier inapplicable « pendant
# le flux ». Ici, le premier morceau qui dépasse la borne interrompt la lecture.


class MultipartFormatError(ValueError):
    """Le corps n'est pas un ``multipart/form-data`` exploitable."""


class ContentTooLarge(ValueError):
    """Le flux dépasse la borne applicable ; rien n'est conservé."""


@dataclass
class UploadedFile:
    """Pièce reçue : nom d'origine, type déclaré et contenu spoolé sur disque."""

    file_name: str
    content_type: str
    handle: BinaryIO
    size: int


def _multipart_boundary(content_type: str | None) -> bytes:
    """Extrait la frontière d'un en-tête ``multipart/form-data``.

    Le découpage simple sur « ; » suffit ici : les caractères autorisés dans une
    frontière (RFC 2046 §5.1.1) excluent le point-virgule, contrairement à un nom de
    fichier — voir ``_disposition_parameters`` pour ce dernier.
    """

    raw = (content_type or "").strip()
    main, _, parameters = raw.partition(";")
    if main.strip().lower() != "multipart/form-data":
        raise HTTPException(
            status_code=415,
            detail="Un corps « multipart/form-data » est attendu pour un téléversement.",
        )
    for parameter in parameters.split(";"):
        name, _, value = parameter.partition("=")
        if name.strip().lower() != "boundary":
            continue
        boundary = value.strip().strip('"')
        if not boundary or len(boundary) > 200:
            break
        encoded = boundary.encode("ascii", "ignore")
        if not encoded:
            break
        return encoded
    raise HTTPException(
        status_code=400, detail="Téléversement invalide : frontière multipart absente."
    )


def _disposition_parameters(disposition: str) -> list[str]:
    """Découpe un en-tête en paramètres, chaînes citées comprises (RFC 2045 §5.1).

    Un « ; » à l'intérieur d'une chaîne citée appartient à la valeur. Le découper
    naïvement tronquerait ``filename="a;b.png"`` en ``a`` et, pire, laisserait un
    ``name=`` glissé dans le nom de fichier renommer la partie. Un guillemet non
    fermé n'est pas deviné : l'en-tête est déclaré illisible.
    """

    parameters: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for character in disposition:
        if escaped:
            escaped = False
            current.append(character)
            continue
        if quoted and character == "\\":
            escaped = True
            current.append(character)
            continue
        if character == '"':
            quoted = not quoted
            current.append(character)
            continue
        if character == ";" and not quoted:
            parameters.append("".join(current))
            current = []
            continue
        current.append(character)
    if quoted or escaped:
        raise MultipartFormatError(
            "Content-Disposition mal formé : guillemet non fermé."
        )
    parameters.append("".join(current))
    return parameters


def _unquote_parameter(value: str) -> str:
    """Valeur d'un paramètre : chaîne citée déséchappée, ou jeton tel quel."""

    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return re.sub(r"\\(.)", r"\1", value[1:-1])
    return value


def _part_field_name(headers: dict[str, str]) -> tuple[str, str]:
    """Nom du champ et nom de fichier déclarés dans ``Content-Disposition``."""

    disposition = headers.get("content-disposition", "")
    name = ""
    file_name = ""
    for parameter in _disposition_parameters(disposition)[1:]:
        key, separator, value = parameter.partition("=")
        if not separator:
            continue
        key = key.strip().lower()
        value = _unquote_parameter(value)
        if key == "name":
            name = value
        elif key == "filename":
            file_name = value
    if not name:
        raise MultipartFormatError("Partie multipart sans nom de champ.")
    return name, file_name


class _MultipartScanner:
    """Tampon glissant sur le corps de la requête, borné à chaque étape."""

    def __init__(self, stream, boundary: bytes) -> None:
        self._stream = stream.__aiter__()
        self._buffer = bytearray()
        self._eof = False
        self.delimiter = b"--" + boundary

    async def _fill(self) -> bool:
        """Ajoute au moins un octet au tampon ; ``False`` signale la fin du corps.

        Les morceaux vides ne comptent pas comme un progrès : un flux qui n'en
        émettrait que ne doit pas faire tourner la boucle d'appel indéfiniment.
        """

        while not self._eof:
            try:
                chunk = await self._stream.__anext__()
            except StopAsyncIteration:
                self._eof = True
                return False
            if chunk:
                self._buffer.extend(chunk)
                return True
        return False

    async def read_until(self, separator: bytes, limit: int) -> bytes:
        index = self._buffer.find(separator)
        while index == -1:
            if len(self._buffer) > limit + len(separator):
                raise MultipartFormatError("Partie multipart hors bornes.")
            if not await self._fill():
                raise MultipartFormatError("Corps multipart interrompu.")
            index = self._buffer.find(separator)
        value = bytes(self._buffer[:index])
        del self._buffer[: index + len(separator)]
        return value

    async def read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            if not await self._fill():
                raise MultipartFormatError("Corps multipart interrompu.")
        value = bytes(self._buffer[:count])
        del self._buffer[:count]
        return value

    async def iterate_body(self) -> AsyncIterator[bytes]:
        """Morceaux du corps d'une partie, jusqu'au délimiteur suivant (exclu)."""

        terminator = b"\r\n" + self.delimiter
        while True:
            index = self._buffer.find(terminator)
            if index != -1:
                chunk = bytes(self._buffer[:index])
                del self._buffer[: index + len(terminator)]
                if chunk:
                    yield chunk
                return
            keep = len(terminator) - 1
            if len(self._buffer) > keep:
                chunk = bytes(self._buffer[: len(self._buffer) - keep])
                del self._buffer[: len(chunk)]
                yield chunk
            if not await self._fill():
                raise MultipartFormatError("Corps multipart interrompu.")


async def read_upload(
    request: Request,
    *,
    max_file_bytes: int,
    prepare: Callable[[dict[str, str]], int] | None = None,
) -> tuple[dict[str, str], UploadedFile | None]:
    """Lit un ``multipart/form-data`` en flux : champs texte bornés, une pièce spoolée.

    ``prepare`` est appelé juste avant de lire le contenu du fichier, avec les champs
    déjà reçus : c'est là que l'appelant valide le lease et resserre le plafond au
    quota restant de la tentative. Le contenu n'est donc jamais lu avant d'avoir
    vérifié à qui il appartient.
    """

    boundary = _multipart_boundary(request.headers.get("content-type"))
    scanner = _MultipartScanner(request.stream(), boundary)
    fields: dict[str, str] = {}
    uploaded: UploadedFile | None = None
    cap = max_file_bytes
    prepared = False
    await scanner.read_until(scanner.delimiter, MULTIPART_PREAMBLE_MAX_BYTES)
    for _ in range(MULTIPART_MAX_PARTS):
        marker = await scanner.read_exactly(2)
        if marker == b"--":
            break
        if marker != b"\r\n":
            raise MultipartFormatError("Délimiteur multipart invalide.")
        raw_headers = await scanner.read_until(
            b"\r\n\r\n", MULTIPART_HEADERS_MAX_BYTES
        )
        headers: dict[str, str] = {}
        for line in raw_headers.decode("latin-1").split("\r\n"):
            key, _, value = line.partition(":")
            if key:
                headers[key.strip().lower()] = value.strip()
        if headers.get("content-transfer-encoding", "").lower() not in {"", "binary"}:
            raise MultipartFormatError("Encodage de partie non pris en charge.")
        name, file_name = _part_field_name(headers)
        if name != FILE_FIELD_NAME:
            value = bytearray()
            async for chunk in scanner.iterate_body():
                value.extend(chunk)
                if len(value) > MULTIPART_FIELD_MAX_BYTES:
                    raise MultipartFormatError(f"Champ « {name} » trop volumineux.")
            fields[name] = value.decode("utf-8", errors="replace")
            continue
        if uploaded is not None:
            raise MultipartFormatError("Une seule pièce « file » est acceptée.")
        if prepare is not None and not prepared:
            cap = min(cap, prepare(fields))
            prepared = True
        spooled = tempfile.SpooledTemporaryFile(max_size=MULTIPART_SPOOL_MAX_BYTES)
        size = 0
        try:
            async for chunk in scanner.iterate_body():
                size += len(chunk)
                if size > cap:
                    raise ContentTooLarge(str(cap))
                spooled.write(chunk)
        except BaseException:
            spooled.close()
            raise
        spooled.seek(0)
        uploaded = UploadedFile(
            file_name=file_name,
            content_type=headers.get("content-type", ""),
            handle=spooled,
            size=size,
        )
    else:
        raise MultipartFormatError("Trop de parties dans le téléversement.")
    if prepare is not None and not prepared:
        prepare(fields)
    return fields, uploaded


# --- Téléversement worker (§6) --------------------------------------------------


def _active_run_lease(db: Session, worker_id: str, run_id: str) -> WorkerLeaseModel:
    """Lease actif du worker sur cette tentative, sinon 409.

    Dupliqué depuis ``routers/operations.py`` pour garder les modules acycliques :
    c'est ``operations`` qui monte la route et importe ce module, jamais l'inverse.
    """

    expire_task_leases(db)
    lease = (
        db.query(WorkerLeaseModel)
        .filter_by(worker_id=worker_id, task_run_id=run_id, status="active")
        .first()
    )
    if lease is None:
        raise HTTPException(
            status_code=409, detail="Le worker ne possède pas ce run actif"
        )
    return lease


def _used_bytes_for_run(db: Session, run_id: str) -> int:
    """Volume déjà conservé pour cette tentative (livrables non purgés)."""

    total = (
        db.query(func.coalesce(func.sum(ArtifactModel.size_bytes), 0))
        .filter(
            ArtifactModel.task_run_id == run_id,
            ArtifactModel.deleted_at.is_(None),
            ArtifactModel.storage_key.is_not(None),
        )
        .scalar()
    )
    return int(total or 0)


def _uploaded_checksum(stream: BinaryIO) -> str:
    """Empreinte un spool sans le charger en mémoire et restaure son curseur."""

    digest = hashlib.sha256()
    stream.seek(0)
    while chunk := stream.read(STREAM_CHUNK_BYTES):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def _lock_artifact_quota(db: Session, run_id: str) -> None:
    """Sérialise la décision finale de quota pour une tentative.

    PostgreSQL verrouille la ligne du run. SQLite ignore ``FOR UPDATE`` : une mise
    à jour sans effet prend alors son verrou d'écriture avant le calcul du total.
    Le verrou reste détenu jusqu'au commit qui insère l'artefact.
    """

    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        db.execute(
            update(TaskRunModel)
            .where(TaskRunModel.id == run_id)
            .values(updated_at=TaskRunModel.updated_at)
        )
        return
    db.query(TaskRunModel).filter_by(id=run_id).with_for_update().one()


def _required_field(fields: dict[str, str], name: str) -> str:
    value = (fields.get(name) or "").strip()
    if not value:
        raise HTTPException(
            status_code=422, detail=f"Champ « {name} » obligatoire pour un téléversement."
        )
    return value


async def receive_worker_artifact_content(
    db: Session, worker: WorkerModel, request: Request
) -> ArtifactSummary:
    """Téléverse un contenu pour une tentative que ce worker détient réellement.

    L'empreinte est calculée par le serveur : un client ne choisit jamais le sha256
    ni la clé de stockage. Une réémission du même contenu sur la même tentative rend
    le livrable déjà enregistré au lieu d'en créer un doublon.
    """

    max_file = artifact_max_bytes(os.environ)
    quota = artifact_max_bytes_per_run(os.environ)
    alert_scope: tuple[str, str] | None = None
    declared_length = request.headers.get("content-length")
    if declared_length and declared_length.isdigit():
        if int(declared_length) > max_file + MULTIPART_OVERHEAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Livrable refusé : la taille annoncée dépasse le plafond de "
                    f"{max_file} octets."
                ),
            )

    def validate(fields: dict[str, str]) -> tuple[str, str, int]:
        """Propriété de la tentative et quota restant, sur les champs reçus."""

        nonlocal alert_scope
        run_id = _required_field(fields, "task_run_id")
        project_id = _required_field(fields, "project_id")
        lease = _active_run_lease(db, worker.id, run_id)
        task = db.get(TaskModel, lease.task_id)
        if task is None or task.project_id != project_id:
            raise HTTPException(
                status_code=400, detail="Artefact hors du projet du run"
            )
        alert_scope = (run_id, project_id)
        remaining = quota - _used_bytes_for_run(db, run_id)
        return run_id, project_id, remaining

    def prepare(fields: dict[str, str]) -> int:
        """Valide tôt le propriétaire sans sacrifier les replays idempotents.

        L'ordre des parties appartient au client : si la pièce précède les champs,
        seule la borne par fichier s'applique pendant la lecture. Même lorsque le
        quota paraît épuisé, le spool reste borné par fichier : son empreinte doit
        être calculée pour reconnaître le renvoi d'un livrable déjà enregistré.
        La décision de quota est sérialisée juste après, avant toute écriture.
        """

        if not (fields.get("task_run_id") or "").strip() or not (
            fields.get("project_id") or ""
        ).strip():
            return max_file
        validate(fields)
        return max_file

    try:
        fields, uploaded = await read_upload(
            request, max_file_bytes=max_file, prepare=prepare
        )
    except ContentTooLarge as exc:
        raise _too_large(int(str(exc)), max_file, quota) from exc
    except OSError as exc:
        _raise_storage_failure(db, storage_error_from_oserror(exc), alert_scope)
    except MultipartFormatError as exc:
        raise HTTPException(status_code=422, detail=f"Téléversement invalide : {exc}") from exc

    if uploaded is None:
        raise HTTPException(
            status_code=422, detail="Téléversement invalide : pièce « file » absente."
        )
    try:
        run_id, project_id, _remaining_before_lock = validate(fields)
        uploaded_checksum = _uploaded_checksum(uploaded.handle)
        _lock_artifact_quota(db, run_id)
        existing = (
            db.query(ArtifactModel)
            .filter(
                ArtifactModel.task_run_id == run_id,
                ArtifactModel.checksum == uploaded_checksum,
                ArtifactModel.deleted_at.is_(None),
            )
            .order_by(ArtifactModel.created_at)
            .first()
        )
        if existing is not None:
            return _summary(existing)
        remaining = quota - _used_bytes_for_run(db, run_id)
        if remaining <= 0 or uploaded.size > remaining:
            raise _too_large(max(remaining, 0), max_file, quota)
        cap = min(max_file, remaining)
        if uploaded.size > cap:
            raise _too_large(cap, max_file, quota)
        storage = artifact_storage()
        try:
            blob = storage.write(uploaded.handle, max_bytes=cap)
        except ArtifactTooLarge as exc:
            raise _too_large(cap, max_file, quota) from exc
        except (ArtifactStorageFull, ArtifactStorageUnavailable) as exc:
            _raise_storage_failure(db, exc, (run_id, project_id))
        if blob.sha256 != uploaded_checksum:
            _raise_storage_failure(
                db,
                ArtifactStorageUnavailable("empreinte de stockage incohérente"),
                (run_id, project_id),
            )
    finally:
        uploaded.handle.close()

    artifact = ArtifactModel(
        project_id=project_id,
        task_run_id=run_id,
        worker_id=worker.id,
        kind=(fields.get("kind") or "file").strip()[:100] or "file",
        # Aucun chemin fourni par le client : la clé vient du contenu.
        path="",
        checksum=blob.sha256,
        size_bytes=blob.size,
        metadata_json={},
        storage_key=blob.key,
        content_type=(fields.get("content_type") or uploaded.content_type or OCTET_STREAM)
        .strip()[:200]
        or OCTET_STREAM,
        original_name=(fields.get("original_name") or uploaded.file_name or "")[:500],
        source="worker",
        stream_kind=(fields.get("stream_kind") or "").strip()[:50],
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return _summary(artifact)


def _raise_storage_failure(
    db: Session,
    error: ArtifactStorageError,
    scope: tuple[str, str] | None,
) -> None:
    """Persiste une alerte sûre puis rend 507 (plein) ou 503 (indisponible)."""

    full = isinstance(error, ArtifactStorageFull)
    if scope is not None:
        run_id, project_id = scope
        run = db.get(TaskRunModel, run_id)
        task_id = run.task_id if run is not None else None
        open_or_escalate_alert(
            db,
            project_id=project_id,
            kind="storage.saturated" if full else "storage.unavailable",
            severity="critical",
            title="Stockage de livrables saturé" if full else "Stockage indisponible",
            detail=(
                "Libérez de l'espace avant de relancer le téléversement."
                if full
                else "Vérifiez le volume de livrables et ses permissions."
            ),
            task_id=task_id,
            dimensions={"storage": "artifacts"},
        )
        db.commit()
    raise HTTPException(
        status_code=507 if full else 503,
        detail=(
            "Stockage saturé : libérez de l'espace avant de réessayer."
            if full
            else "Stockage de livrables indisponible."
        ),
    )


def _too_large(applied: int, max_file: int, quota: int) -> HTTPException:
    """Message distinguant le plafond par fichier du quota de la tentative."""

    if applied < max_file:
        return HTTPException(
            status_code=413,
            detail=(
                "Livrable refusé : le quota de la tentative "
                f"({quota} octets) serait dépassé."
            ),
        )
    return HTTPException(
        status_code=413,
        detail=f"Livrable refusé : la taille dépasse {max_file} octets.",
    )
