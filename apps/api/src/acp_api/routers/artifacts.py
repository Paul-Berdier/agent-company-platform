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
import json
import os
import re
import struct
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import BinaryIO, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from acp_contracts import (
    ArtifactLink,
    ArtifactPage,
    ArtifactSummary,
    ServiceOriginError,
    normalize_service_origin,
)
from acp_database.models import (
    ArtifactLinkModel,
    ArtifactModel,
    TaskModel,
    TaskRunModel,
    WorkerModel,
)

from ..attempt_fencing import require_active_worker_attempt
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
router = APIRouter(tags=["artifacts"])
preview_router = APIRouter(tags=["artifact-preview"])

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

#: Origine séparée servant les aperçus signés ; vide, toute demande d'aperçu échoue
#: explicitement avant la création du jeton. Les téléchargements restent sur l'API.
ARTIFACT_PUBLIC_ORIGIN_ENV = "ACP_ARTIFACT_PUBLIC_ORIGIN"

CONTENT_SECURITY_POLICY = "default-src 'none'; sandbox"

GLB_CONTENT_TYPE = "model/gltf-binary"
GLTF_JSON_CONTENT_TYPE = "model/gltf+json"
GLB_EXTENSION = ".glb"
GLTF_EXTENSION = ".gltf"
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
GLB_HEADER_BYTES = 12
GLB_CHUNK_HEADER_BYTES = 8
GLB_JSON_MAX_BYTES = 4 * 1024 * 1024
GLB_MAX_RESOURCE_ENTRIES = 65_536
GLB_MAX_DECODED_ACCESSOR_BYTES = 128 * 1024 * 1024
GLB_MIN_DECODED_ACCESSOR_BUDGET = 1024 * 1024
GLB_MAX_DECODED_AMPLIFICATION = 8
GLB_MAX_BUFFER_VIEW_BYTES = 128 * 1024 * 1024
GLB_MAX_PHYSICAL_ACCESSOR_BYTES = 128 * 1024 * 1024
GLB_MAX_EMBEDDED_RESOURCE_BYTES = 128 * 1024 * 1024
GLB_MAX_COMPRESSED_IMAGE_BYTES = 32 * 1024 * 1024
GLB_MAX_IMAGE_DIMENSION = 8192
GLB_MAX_IMAGE_BASE_PIXELS = 32 * 1024 * 1024
GLB_MAX_IMAGE_RGBA_MIP_BYTES = 128 * 1024 * 1024
GLB_JSON_CHUNK_TYPE = b"JSON"
GLB_BINARY_CHUNK_TYPE = b"BIN\x00"
GLB_BUFFER_MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/gltf-buffer", "application/octet-stream"}
)
GLB_IMAGE_MEDIA_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
GLB_DATA_URI_MEDIA_TYPES: frozenset[str] = frozenset(
    GLB_BUFFER_MEDIA_TYPES | GLB_IMAGE_MEDIA_TYPES
)
GLB_EXTERNAL_DECODER_EXTENSIONS: frozenset[str] = frozenset(
    {
        "KHR_draco_mesh_compression",
        "EXT_meshopt_compression",
        "KHR_texture_basisu",
    }
)
# Marqueur exclusivement écrit par ce routeur après validation du spool. Sa valeur
# est l'empreinte du contenu validé : une ligne historique ou des métadonnées forgées
# ne peuvent donc pas rendre un ancien blob affichable par simple changement de type.
GLB_VALIDATION_METADATA_KEY = "_acp_glb_preview_sha256_v1"

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
    # Un GLB n'est réellement promu qu'après concordance stricte type + extension
    # dans ``safe_content_type`` et validation structurelle lors du téléversement.
    GLB_CONTENT_TYPE: GLB_CONTENT_TYPE,
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
        # Le JSON glTF peut référencer des ressources externes. Le premier aperçu 3D
        # accepte uniquement son conteneur binaire GLB auto-contenu.
        GLTF_JSON_CONTENT_TYPE,
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
    GLB_EXTENSION: GLB_CONTENT_TYPE,
    GLTF_EXTENSION: GLTF_JSON_CONTENT_TYPE,
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

    # Contrairement aux images historiques, ni le nom ni la déclaration seuls ne
    # suffisent pour un modèle 3D. Cette concordance est la première moitié de la
    # décision ; le contenu doit aussi porter le sceau de validation lié au sha256.
    if normalized == GLB_CONTENT_TYPE or suffix == GLB_EXTENSION:
        if normalized == GLB_CONTENT_TYPE and suffix == GLB_EXTENSION:
            return GLB_CONTENT_TYPE, True
        return OCTET_STREAM, False
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


def _glb_error(detail: str, *, status_code: int = 422) -> HTTPException:
    """Erreur stable et explicite pour un modèle annoncé comme affichable."""

    return HTTPException(status_code=status_code, detail=f"GLB refusé : {detail}")


def _strict_json_object(raw: bytes) -> dict[str, object]:
    """Décode le chunk JSON sans extensions permissives du parseur Python."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"clé JSON dupliquée : {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"constante JSON interdite : {value}")

    try:
        text = raw.decode("utf-8", errors="strict")
        document = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise _glb_error("le chunk JSON n'est pas un document UTF-8 valide.") from exc
    if not isinstance(document, dict):
        raise _glb_error("la racine du chunk JSON doit être un objet.")
    asset = document.get("asset")
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise _glb_error("le document doit déclarer asset.version égal à « 2.0 ».")
    return document


def _validate_self_contained_glb_uris(
    document: dict[str, object], *, total_size: int
) -> None:
    """Refuse toute ressource susceptible de provoquer une requête hors du GLB.

    Les URI glTF standard apparaissent dans les propriétés ``uri`` (buffers et
    images). Les extensions sont parcourues elles aussi. Une ``data:`` reste incluse
    dans le fichier et sa somme est bornée par la taille déjà admise pour le spool.
    """

    data_uri_bytes = 0
    pending: list[object] = [document]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key.casefold() == "uri":
                    if not isinstance(value, str):
                        raise _glb_error("une propriété uri doit être une chaîne.")
                    if not value.casefold().startswith("data:"):
                        raise _glb_error(
                            "une URI externe est interdite dans un aperçu auto-contenu."
                        )
                    if "," not in value[5:]:
                        raise _glb_error("une data URI du document est mal formée.")
                    metadata, _separator, payload = value[5:].partition(",")
                    metadata_parts = metadata.casefold().split(";")
                    if (
                        len(metadata_parts) != 2
                        or metadata_parts[0] not in GLB_DATA_URI_MEDIA_TYPES
                        or metadata_parts[1] != "base64"
                    ):
                        raise _glb_error(
                            "une data URI doit utiliser un type binaire autorisé et base64."
                        )
                    if any(
                        ord(character) < 0x20 or ord(character) == 0x7F
                        for character in value
                    ):
                        raise _glb_error("une data URI contient un caractère de contrôle.")
                    encoded_size = len(value.encode("utf-8"))
                    data_uri_bytes += encoded_size
                    max_encoded_size = 4 * (
                        (GLB_MAX_EMBEDDED_RESOURCE_BYTES + 2) // 3
                    )
                    if (
                        encoded_size > total_size
                        or data_uri_bytes > total_size
                        or len(payload) > max_encoded_size
                    ):
                        raise _glb_error(
                            "les data URI dépassent la taille globale bornée du GLB."
                        )
                    try:
                        decoded = base64.b64decode(
                            payload.encode("ascii", errors="strict"), validate=True
                        )
                    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                        raise _glb_error(
                            "le payload base64 d'une data URI est invalide."
                        ) from exc
                    if len(decoded) > GLB_MAX_EMBEDDED_RESOURCE_BYTES:
                        raise _glb_error(
                            "une ressource embarquée dépasse la borne autorisée."
                        )
                pending.append(value)
        elif isinstance(node, list):
            pending.extend(node)


def _validate_glb_extensions(document: dict[str, object]) -> None:
    """Refuse les extensions qui peuvent charger un décodeur hors de l'application."""

    declared: dict[str, set[str]] = {}
    for field in ("extensionsUsed", "extensionsRequired"):
        raw = document.get(field, [])
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise _glb_error(f"{field} doit être une liste de noms d'extensions.")
        values = set(raw)
        declared[field] = values
        blocked = values & GLB_EXTERNAL_DECODER_EXTENSIONS
        if blocked:
            names = ", ".join(sorted(blocked))
            raise _glb_error(
                f"l'extension « {names} » exige un décodeur externe interdit."
            )
    if not declared["extensionsRequired"].issubset(declared["extensionsUsed"]):
        raise _glb_error(
            "extensionsRequired doit être un sous-ensemble de extensionsUsed."
        )

    # Un document incohérent pourrait omettre ``extensionsUsed`` tout en portant le
    # bloc d'extension. Le parseur du visualiseur, pas cette déclaration, décide alors
    # de son comportement : rechercher également les clés ferme ce contournement.
    blocked_casefold = {
        extension.casefold() for extension in GLB_EXTERNAL_DECODER_EXTENSIONS
    }
    pending: list[object] = [document]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key.casefold() in blocked_casefold:
                    raise _glb_error(
                        f"l'extension « {key} » exige un décodeur externe interdit."
                    )
                pending.append(value)
        elif isinstance(node, list):
            pending.extend(node)


def _glb_integer(
    value: object,
    *,
    label: str,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _glb_error(f"{label} doit être un entier supérieur ou égal à {minimum}.")
    if maximum is not None and value > maximum:
        raise _glb_error(f"{label} dépasse la borne autorisée.")
    return value


def _glb_array(document: dict[str, object], field: str) -> list[object]:
    value = document.get(field, [])
    if not isinstance(value, list):
        raise _glb_error(f"{field} doit être une liste.")
    if len(value) > GLB_MAX_RESOURCE_ENTRIES:
        raise _glb_error(f"{field} contient trop d'entrées.")
    return value


def _data_uri_payload(
    uri: str,
    *,
    expected_media: frozenset[str],
    max_decoded_bytes: int,
    kind: str,
) -> tuple[str, bytes]:
    if not uri.casefold().startswith("data:"):
        raise _glb_error(f"une URI de {kind} doit être une data URI.")
    metadata, separator, payload = uri[5:].partition(",")
    parts = metadata.casefold().split(";")
    if (
        not separator
        or len(parts) != 2
        or parts[0] not in expected_media
        or parts[1] != "base64"
    ):
        raise _glb_error(f"une data URI de {kind} est invalide.")
    if len(payload) > 4 * ((max_decoded_bytes + 2) // 3):
        raise _glb_error(f"une data URI de {kind} dépasse la borne autorisée.")
    try:
        decoded = base64.b64decode(
            payload.encode("ascii", errors="strict"), validate=True
        )
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise _glb_error(f"le payload base64 d'un {kind} est invalide.") from exc
    if len(decoded) > max_decoded_bytes:
        raise _glb_error(f"le contenu d'un {kind} dépasse la borne autorisée.")
    return parts[0], decoded


@dataclass(frozen=True)
class _GlbRangeReader:
    """Vue bornée d'une ressource, sans recopier un ``bufferView`` complet."""

    stream: BinaryIO | None
    payload: bytes | None
    absolute_offset: int
    length: int

    def read(self, offset: int, length: int) -> bytes | memoryview:
        if offset < 0 or length < 0 or offset > self.length - length:
            raise _glb_error("une lecture de ressource dépasse son bufferView.")
        start = self.absolute_offset + offset
        if self.payload is not None:
            return memoryview(self.payload)[start : start + length]
        if self.stream is None:
            raise _glb_error("les octets d'une ressource sont inaccessibles.")
        self.stream.seek(start)
        result = self.stream.read(length)
        if len(result) != length:
            raise _glb_error("les octets d'une ressource sont tronqués.")
        return result


@dataclass(frozen=True)
class _GlbBufferSource:
    length: int
    payload: bytes | None
    binary_absolute_offset: int | None

    def reader(
        self, stream: BinaryIO, *, byte_offset: int, byte_length: int
    ) -> _GlbRangeReader:
        if byte_offset < 0 or byte_length < 0 or byte_offset > self.length - byte_length:
            raise _glb_error("un bufferView dépasse son buffer.")
        if self.payload is not None:
            return _GlbRangeReader(
                stream=None,
                payload=self.payload,
                absolute_offset=byte_offset,
                length=byte_length,
            )
        if self.binary_absolute_offset is None:
            raise _glb_error("les octets du chunk BIN sont inaccessibles.")
        return _GlbRangeReader(
            stream=stream,
            payload=None,
            absolute_offset=self.binary_absolute_offset + byte_offset,
            length=byte_length,
        )


@dataclass(frozen=True)
class _GlbBufferView:
    buffer_index: int
    byte_offset: int
    byte_length: int
    byte_stride: int | None
    has_target: bool
    reader: _GlbRangeReader


def _reader_bytes(reader: _GlbRangeReader, offset: int, length: int) -> bytes:
    """Copie uniquement un petit en-tête explicitement demandé par un parseur."""

    return bytes(reader.read(offset, length))


def _png_dimensions(reader: _GlbRangeReader) -> tuple[int, int]:
    if reader.length < 57 or _reader_bytes(reader, 0, 8) != b"\x89PNG\r\n\x1a\n":
        raise _glb_error("la signature ou le conteneur PNG est incomplet.")
    if struct.unpack(">I", reader.read(8, 4))[0] != 13:
        raise _glb_error("le premier chunk PNG doit être IHDR.")
    if _reader_bytes(reader, 12, 4) != b"IHDR":
        raise _glb_error("le premier chunk PNG doit être IHDR.")
    ihdr = reader.read(16, 13)
    expected_crc = struct.unpack(">I", reader.read(29, 4))[0]
    actual_crc = binascii.crc32(b"IHDR")
    actual_crc = binascii.crc32(ihdr, actual_crc) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise _glb_error("l'en-tête IHDR du PNG porte un CRC invalide.")
    width, height = struct.unpack(">II", ihdr[:8])
    bit_depth, color_type, compression, filtering, interlace = ihdr[8:13]
    allowed_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if (
        width == 0
        or height == 0
        or color_type not in allowed_depths
        or bit_depth not in allowed_depths[color_type]
        or compression != 0
        or filtering != 0
        or interlace not in {0, 1}
    ):
        raise _glb_error("l'en-tête IHDR du PNG est invalide.")

    position = 8
    chunks = 0
    saw_idat = False
    saw_iend = False
    while position < reader.length:
        chunks += 1
        if chunks > GLB_MAX_RESOURCE_ENTRIES:
            raise _glb_error("une image PNG contient trop de chunks.")
        if reader.length - position < 12:
            raise _glb_error("un chunk PNG est tronqué.")
        chunk_length = struct.unpack(">I", reader.read(position, 4))[0]
        chunk_type = _reader_bytes(reader, position + 4, 4)
        chunk_end = position + 12 + chunk_length
        if chunk_end > reader.length:
            raise _glb_error("un chunk PNG dépasse le contenu de l'image.")
        if chunks == 1 and (chunk_type != b"IHDR" or chunk_length != 13):
            raise _glb_error("le premier chunk PNG doit être IHDR.")
        if chunk_type == b"IDAT":
            saw_idat = True
        if chunk_type == b"IEND":
            if chunk_length != 0 or chunk_end != reader.length:
                raise _glb_error("le chunk IEND du PNG est invalide.")
            saw_iend = True
            break
        position = chunk_end
    if not saw_idat or not saw_iend:
        raise _glb_error("le PNG doit contenir IDAT puis IEND.")
    return width, height


def _jpeg_dimensions(reader: _GlbRangeReader) -> tuple[int, int]:
    if (
        reader.length < 12
        or _reader_bytes(reader, 0, 2) != b"\xff\xd8"
        or _reader_bytes(reader, reader.length - 2, 2) != b"\xff\xd9"
    ):
        raise _glb_error("la signature ou le conteneur JPEG est incomplet.")

    position = 2
    marker_steps = 0
    dimensions: tuple[int, int] | None = None
    saw_scan = False
    supported_sof = {0xC0, 0xC1, 0xC2}
    standalone = {0x01, *range(0xD0, 0xD8)}
    while position < reader.length - 2:
        marker_steps += 1
        if marker_steps > GLB_MAX_RESOURCE_ENTRIES:
            raise _glb_error("une image JPEG contient trop de marqueurs.")
        if reader.read(position, 1)[0] != 0xFF:
            raise _glb_error("la table des segments JPEG est invalide.")
        while position < reader.length - 2 and reader.read(position, 1)[0] == 0xFF:
            position += 1
            marker_steps += 1
            if marker_steps > GLB_MAX_RESOURCE_ENTRIES:
                raise _glb_error("une image JPEG contient trop de remplissage.")
        if position >= reader.length - 2:
            break
        marker = reader.read(position, 1)[0]
        position += 1
        if marker == 0x00:
            raise _glb_error("un marqueur JPEG est invalide avant les données image.")
        if marker in standalone:
            continue
        if marker == 0xD9:
            break
        if reader.length - position < 2:
            raise _glb_error("un segment JPEG est tronqué.")
        segment_length = struct.unpack(">H", reader.read(position, 2))[0]
        if segment_length < 2 or segment_length > reader.length - position:
            raise _glb_error("la longueur d'un segment JPEG est invalide.")
        if marker in supported_sof:
            if dimensions is not None:
                raise _glb_error("une image JPEG ne peut contenir qu'un seul SOF.")
            if segment_length < 11:
                raise _glb_error("un segment SOF JPEG est tronqué.")
            header = reader.read(position + 2, 6)
            precision = header[0]
            height, width = struct.unpack(">HH", header[1:5])
            components = header[5]
            if (
                precision != 8
                or width == 0
                or height == 0
                or components not in {1, 3, 4}
                or segment_length != 8 + 3 * components
            ):
                raise _glb_error("le segment SOF du JPEG est invalide.")
            dimensions = (width, height)
        elif 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
            raise _glb_error("le type de codage JPEG n'est pas pris en charge.")
        if marker == 0xDA:
            saw_scan = True
            break
        position += segment_length
    if dimensions is None or not saw_scan:
        raise _glb_error("le JPEG doit contenir un SOF pris en charge puis un SOS.")
    return dimensions


def _webp_dimensions(reader: _GlbRangeReader) -> tuple[int, int]:
    if (
        reader.length < 20
        or _reader_bytes(reader, 0, 4) != b"RIFF"
        or _reader_bytes(reader, 8, 4) != b"WEBP"
    ):
        raise _glb_error("la signature ou le conteneur WebP est incomplet.")
    declared_length = struct.unpack("<I", reader.read(4, 4))[0] + 8
    if declared_length != reader.length:
        raise _glb_error("la longueur RIFF du WebP est incohérente.")

    position = 12
    chunks = 0
    canvas_dimensions: tuple[int, int] | None = None
    image_dimensions: tuple[int, int] | None = None
    while position < reader.length:
        chunks += 1
        if chunks > GLB_MAX_RESOURCE_ENTRIES:
            raise _glb_error("une image WebP contient trop de chunks.")
        if reader.length - position < 8:
            raise _glb_error("un chunk WebP est tronqué.")
        chunk_type = _reader_bytes(reader, position, 4)
        chunk_length = struct.unpack("<I", reader.read(position + 4, 4))[0]
        payload_offset = position + 8
        padded_length = chunk_length + (chunk_length & 1)
        if padded_length > reader.length - payload_offset:
            raise _glb_error("un chunk WebP dépasse le conteneur RIFF.")
        if chunk_type == b"VP8X":
            if canvas_dimensions is not None or image_dimensions is not None:
                raise _glb_error("l'ordre ou la multiplicité des chunks WebP est invalide.")
            if chunk_length != 10:
                raise _glb_error("le chunk VP8X porte une longueur invalide.")
            header = reader.read(payload_offset, 10)
            if header[0] & 0xC3 or any(header[1:4]):
                raise _glb_error("l'en-tête VP8X utilise des options interdites.")
            width = 1 + int.from_bytes(header[4:7], "little")
            height = 1 + int.from_bytes(header[7:10], "little")
            canvas_dimensions = (width, height)
        elif chunk_type == b"VP8 ":
            if image_dimensions is not None:
                raise _glb_error("un WebP ne peut contenir qu'une seule trame image.")
            if chunk_length < 10:
                raise _glb_error("le chunk VP8 est tronqué.")
            header = reader.read(payload_offset, 10)
            frame_tag = int.from_bytes(header[:3], "little")
            if frame_tag & 1 or bytes(header[3:6]) != b"\x9d\x01\x2a":
                raise _glb_error("l'en-tête de trame VP8 est invalide.")
            width = int.from_bytes(header[6:8], "little") & 0x3FFF
            height = int.from_bytes(header[8:10], "little") & 0x3FFF
            if width == 0 or height == 0:
                raise _glb_error("les dimensions VP8 doivent être positives.")
            image_dimensions = (width, height)
        elif chunk_type == b"VP8L":
            if image_dimensions is not None:
                raise _glb_error("un WebP ne peut contenir qu'une seule trame image.")
            if chunk_length < 5:
                raise _glb_error("le chunk VP8L est tronqué.")
            header = reader.read(payload_offset, 5)
            if header[0] != 0x2F:
                raise _glb_error("l'en-tête de trame VP8L est invalide.")
            packed = int.from_bytes(header[1:5], "little")
            width = 1 + (packed & 0x3FFF)
            height = 1 + ((packed >> 14) & 0x3FFF)
            image_dimensions = (width, height)
        elif chunk_type in {b"ANIM", b"ANMF"}:
            raise _glb_error("les images WebP animées ne sont pas prises en charge.")
        position = payload_offset + padded_length
    if position != reader.length or image_dimensions is None:
        raise _glb_error("le WebP ne contient aucune trame image prise en charge.")
    if canvas_dimensions is not None and canvas_dimensions != image_dimensions:
        raise _glb_error("les dimensions VP8X et celles de la trame divergent.")
    return image_dimensions


def _image_dimensions(reader: _GlbRangeReader, media_type: str) -> tuple[int, int]:
    if media_type == "image/png":
        return _png_dimensions(reader)
    if media_type == "image/jpeg":
        return _jpeg_dimensions(reader)
    if media_type == "image/webp":
        return _webp_dimensions(reader)
    raise _glb_error("le type MIME d'une image est interdit.")


def _rgba_mip_bytes(width: int, height: int) -> int:
    total_pixels = 0
    while True:
        total_pixels += width * height
        if width == 1 and height == 1:
            return total_pixels * 4
        width = max(1, width // 2)
        height = max(1, height // 2)


def _accessor_element_bytes(accessor_type: str, component_bytes: int) -> int:
    component_counts = {
        "SCALAR": 1,
        "VEC2": 2,
        "VEC3": 3,
        "VEC4": 4,
        "MAT2": 4,
        "MAT3": 9,
        "MAT4": 16,
    }
    try:
        components = component_counts[accessor_type]
    except KeyError as exc:
        raise _glb_error("un accessor porte un type inconnu.") from exc
    if not accessor_type.startswith("MAT"):
        return components * component_bytes
    dimension = int(accessor_type[-1])
    column_bytes = dimension * component_bytes
    aligned_column_bytes = (column_bytes + 3) // 4 * 4
    return dimension * aligned_column_bytes


def _validate_previewable_glb_resources(
    document: dict[str, object],
    *,
    stream: BinaryIO,
    binary_chunk_size: int,
    binary_chunk_offset: int | None,
    total_size: int,
) -> None:
    """Borne ressources et décodages avant leur remise au visualiseur WebGL."""

    raw_buffers = _glb_array(document, "buffers")
    buffers: list[_GlbBufferSource] = []
    embedded_buffer_bytes = 0
    binary_buffer_mapped = False
    for index, raw_buffer in enumerate(raw_buffers):
        if not isinstance(raw_buffer, dict):
            raise _glb_error("chaque buffer doit être un objet.")
        byte_length = _glb_integer(
            raw_buffer.get("byteLength"),
            label=f"buffers[{index}].byteLength",
            minimum=1,
            maximum=total_size,
        )
        uri = raw_buffer.get("uri")
        if uri is None:
            if index != 0:
                raise _glb_error("seul buffers[0] peut référencer le chunk BIN.")
            if binary_chunk_offset is None:
                raise _glb_error("buffers[0] référence un chunk BIN absent.")
            if binary_chunk_size < byte_length or binary_chunk_size > byte_length + 3:
                raise _glb_error(
                    "la longueur du buffer binaire ne correspond pas au chunk BIN."
                )
            binary_buffer_mapped = True
            source = _GlbBufferSource(
                length=byte_length,
                payload=None,
                binary_absolute_offset=binary_chunk_offset,
            )
        else:
            if not isinstance(uri, str) or not uri.casefold().startswith("data:"):
                raise _glb_error("un buffer doit être interne au GLB.")
            if byte_length > GLB_MAX_EMBEDDED_RESOURCE_BYTES:
                raise _glb_error("un buffer embarqué dépasse la borne autorisée.")
            _media_type, decoded = _data_uri_payload(
                uri,
                expected_media=GLB_BUFFER_MEDIA_TYPES,
                max_decoded_bytes=byte_length,
                kind="buffer",
            )
            if len(decoded) != byte_length:
                raise _glb_error(
                    "la longueur déclarée d'un buffer data URI est incohérente."
                )
            embedded_buffer_bytes += byte_length
            if embedded_buffer_bytes > GLB_MAX_EMBEDDED_RESOURCE_BYTES:
                raise _glb_error("les buffers embarqués dépassent la borne cumulée.")
            source = _GlbBufferSource(
                length=byte_length,
                payload=decoded,
                binary_absolute_offset=None,
            )
        buffers.append(source)
    if binary_chunk_offset is not None and not binary_buffer_mapped:
        raise _glb_error("le chunk BIN n'est pas référencé par buffers[0].")

    raw_views = _glb_array(document, "bufferViews")
    views: list[_GlbBufferView] = []
    buffer_view_bytes = 0
    for index, raw_view in enumerate(raw_views):
        if not isinstance(raw_view, dict):
            raise _glb_error("chaque bufferView doit être un objet.")
        buffer_index = _glb_integer(
            raw_view.get("buffer"), label=f"bufferViews[{index}].buffer"
        )
        if buffer_index >= len(buffers):
            raise _glb_error("un bufferView référence un buffer absent.")
        byte_offset = _glb_integer(
            raw_view.get("byteOffset", 0),
            label=f"bufferViews[{index}].byteOffset",
        )
        byte_length = _glb_integer(
            raw_view.get("byteLength"),
            label=f"bufferViews[{index}].byteLength",
            minimum=1,
            maximum=total_size,
        )
        if byte_offset + byte_length > buffers[buffer_index].length:
            raise _glb_error("un bufferView dépasse son buffer.")
        buffer_view_bytes += byte_length
        if buffer_view_bytes > GLB_MAX_BUFFER_VIEW_BYTES:
            raise _glb_error("les bufferViews dépassent leur budget cumulé.")
        raw_stride = raw_view.get("byteStride")
        byte_stride = None
        if raw_stride is not None:
            byte_stride = _glb_integer(
                raw_stride,
                label=f"bufferViews[{index}].byteStride",
                minimum=4,
                maximum=252,
            )
            if byte_stride % 4 or byte_stride > byte_length:
                raise _glb_error(
                    "le byteStride d'un bufferView doit être multiple de 4 et tenir dans la vue."
                )
        views.append(
            _GlbBufferView(
                buffer_index=buffer_index,
                byte_offset=byte_offset,
                byte_length=byte_length,
                byte_stride=byte_stride,
                has_target="target" in raw_view,
                reader=buffers[buffer_index].reader(
                    stream, byte_offset=byte_offset, byte_length=byte_length
                ),
            )
        )

    component_sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    decoded_budget = min(
        GLB_MAX_DECODED_ACCESSOR_BYTES,
        max(
            GLB_MIN_DECODED_ACCESSOR_BUDGET,
            total_size * GLB_MAX_DECODED_AMPLIFICATION,
        ),
    )
    decoded_total = 0
    physical_total = 0
    for index, raw_accessor in enumerate(_glb_array(document, "accessors")):
        if not isinstance(raw_accessor, dict):
            raise _glb_error("chaque accessor doit être un objet.")
        component_type = _glb_integer(
            raw_accessor.get("componentType"),
            label=f"accessors[{index}].componentType",
        )
        try:
            component_bytes = component_sizes[component_type]
        except KeyError as exc:
            raise _glb_error("un accessor porte un componentType inconnu.") from exc
        accessor_type = raw_accessor.get("type")
        if not isinstance(accessor_type, str):
            raise _glb_error("un accessor doit déclarer son type.")
        element_bytes = _accessor_element_bytes(accessor_type, component_bytes)
        count = _glb_integer(
            raw_accessor.get("count"),
            label=f"accessors[{index}].count",
            minimum=1,
        )
        if count > (decoded_budget - decoded_total) // element_bytes:
            raise _glb_error("les accessors dépassent le budget de décodage borné.")
        decoded_total += count * element_bytes

        byte_offset = _glb_integer(
            raw_accessor.get("byteOffset", 0),
            label=f"accessors[{index}].byteOffset",
        )
        raw_view_index = raw_accessor.get("bufferView")
        if raw_view_index is None:
            if "byteOffset" in raw_accessor:
                raise _glb_error("byteOffset exige un bufferView.")
        else:
            view_index = _glb_integer(
                raw_view_index, label=f"accessors[{index}].bufferView"
            )
            if view_index >= len(views):
                raise _glb_error("un accessor référence un bufferView absent.")
            view = views[view_index]
            stride = view.byte_stride or element_bytes
            if (
                stride < element_bytes
                or stride % component_bytes
                or (view.byte_stride is not None and stride % 4)
            ):
                raise _glb_error("le stride d'un accessor est incohérent.")
            if (view.byte_offset + byte_offset) % component_bytes:
                raise _glb_error("le décalage d'un accessor n'est pas aligné.")
            required = byte_offset + stride * (count - 1) + element_bytes
            if required > view.byte_length:
                raise _glb_error("un accessor dépasse son bufferView.")
            physical_span = stride * (count - 1) + element_bytes
            if physical_span > GLB_MAX_PHYSICAL_ACCESSOR_BYTES - physical_total:
                raise _glb_error(
                    "les accessors dépassent leur budget physique cumulé."
                )
            physical_total += physical_span

        sparse = raw_accessor.get("sparse")
        if sparse is not None:
            # Vérifier les valeurs impose de lire et trier chaque index. Le premier
            # aperçu choisit une politique plus sûre et stable : sparse est refusé.
            raise _glb_error("les accessors sparse ne sont pas pris en charge.")

    compressed_image_bytes = 0
    base_image_pixels = 0
    rgba_mip_bytes = 0
    for index, raw_image in enumerate(_glb_array(document, "images")):
        if not isinstance(raw_image, dict):
            raise _glb_error("chaque image doit être un objet.")
        has_uri = "uri" in raw_image
        has_view = "bufferView" in raw_image
        if has_uri == has_view:
            raise _glb_error("une image exige exactement uri ou bufferView.")

        declared_media = raw_image.get("mimeType")
        if declared_media is not None and (
            not isinstance(declared_media, str)
            or declared_media.casefold() not in GLB_IMAGE_MEDIA_TYPES
        ):
            raise _glb_error("le type MIME d'une image est interdit.")
        if has_uri:
            uri = raw_image.get("uri")
            if not isinstance(uri, str):
                raise _glb_error("l'URI d'une image doit être une chaîne.")
            media_type, payload = _data_uri_payload(
                uri,
                expected_media=GLB_IMAGE_MEDIA_TYPES,
                max_decoded_bytes=GLB_MAX_COMPRESSED_IMAGE_BYTES,
                kind="image",
            )
            if (
                isinstance(declared_media, str)
                and declared_media.casefold() != media_type
            ):
                raise _glb_error("le type MIME déclaré d'une image est incohérent.")
            reader = _GlbRangeReader(
                stream=None,
                payload=payload,
                absolute_offset=0,
                length=len(payload),
            )
        else:
            if not isinstance(declared_media, str):
                raise _glb_error("une image en bufferView doit déclarer mimeType.")
            media_type = declared_media.casefold()
            view_index = _glb_integer(
                raw_image.get("bufferView"), label=f"images[{index}].bufferView"
            )
            if view_index >= len(views):
                raise _glb_error("une image référence un bufferView absent.")
            reader = views[view_index].reader

        if reader.length > GLB_MAX_COMPRESSED_IMAGE_BYTES - compressed_image_bytes:
            raise _glb_error("les images dépassent leur budget compressé cumulé.")
        compressed_image_bytes += reader.length
        width, height = _image_dimensions(reader, media_type)
        if width > GLB_MAX_IMAGE_DIMENSION or height > GLB_MAX_IMAGE_DIMENSION:
            raise _glb_error("les dimensions d'une image dépassent la borne autorisée.")
        pixels = width * height
        if pixels > GLB_MAX_IMAGE_BASE_PIXELS - base_image_pixels:
            raise _glb_error("les images dépassent leur budget cumulé de pixels.")
        base_image_pixels += pixels
        mip_bytes = _rgba_mip_bytes(width, height)
        if mip_bytes > GLB_MAX_IMAGE_RGBA_MIP_BYTES - rgba_mip_bytes:
            raise _glb_error("les images dépassent leur budget RGBA avec mipmaps.")
        rgba_mip_bytes += mip_bytes


def _validate_previewable_glb(stream: BinaryIO, *, total_size: int) -> None:
    """Valide un GLB 2.0 strict et auto-contenu puis remet le spool au début.

    Le fichier peut contenir exactement un chunk JSON en premier, puis au plus un
    chunk BIN. Les chunks inconnus sont refusés : les ignorer rendrait la promesse
    d'un conteneur relisible et auto-contenu dépendante d'une extension future.
    """

    try:
        stream.seek(0, os.SEEK_END)
        actual_size = stream.tell()
        stream.seek(0)
        if actual_size != total_size:
            raise _glb_error("la taille du spool est incohérente.")

        magic = stream.read(len(GLB_MAGIC))
        if magic != GLB_MAGIC:
            raise _glb_error(
                "la signature binaire glTF est absente.", status_code=415
            )
        if total_size < GLB_HEADER_BYTES:
            raise _glb_error("l'en-tête de 12 octets est tronqué.")
        header_tail = stream.read(GLB_HEADER_BYTES - len(GLB_MAGIC))
        if len(header_tail) != GLB_HEADER_BYTES - len(GLB_MAGIC):
            raise _glb_error("l'en-tête de 12 octets est tronqué.")
        version, declared_size = struct.unpack("<II", header_tail)
        if version != GLB_VERSION:
            raise _glb_error("seule la version GLB 2 est acceptée.")
        if declared_size != total_size:
            raise _glb_error(
                "la longueur totale déclarée ne correspond pas au contenu reçu."
            )
        if declared_size < GLB_HEADER_BYTES + GLB_CHUNK_HEADER_BYTES:
            raise _glb_error("le chunk JSON obligatoire est absent.")

        json_seen = False
        binary_seen = False
        document: dict[str, object] | None = None
        binary_chunk_size = 0
        binary_chunk_offset: int | None = None
        chunk_index = 0
        while stream.tell() < declared_size:
            remaining = declared_size - stream.tell()
            if remaining < GLB_CHUNK_HEADER_BYTES:
                raise _glb_error("un en-tête de chunk est tronqué.")
            raw_chunk_header = stream.read(GLB_CHUNK_HEADER_BYTES)
            if len(raw_chunk_header) != GLB_CHUNK_HEADER_BYTES:
                raise _glb_error("un en-tête de chunk est tronqué.")
            chunk_size, chunk_type = struct.unpack("<I4s", raw_chunk_header)
            if chunk_size % 4:
                raise _glb_error("la longueur d'un chunk n'est pas alignée sur 4 octets.")
            if chunk_size > declared_size - stream.tell():
                raise _glb_error("un chunk dépasse la longueur totale déclarée.")

            if chunk_type == GLB_JSON_CHUNK_TYPE:
                if chunk_index != 0 or json_seen:
                    raise _glb_error("le chunk JSON doit être unique et placé en premier.")
                if chunk_size == 0:
                    raise _glb_error("le chunk JSON est vide.")
                if chunk_size > GLB_JSON_MAX_BYTES:
                    raise _glb_error("le chunk JSON dépasse 4 Mio.")
                raw_json = stream.read(chunk_size)
                if len(raw_json) != chunk_size:
                    raise _glb_error("le chunk JSON est tronqué.")
                document = _strict_json_object(raw_json)
                _validate_glb_extensions(document)
                _validate_self_contained_glb_uris(document, total_size=total_size)
                json_seen = True
            elif chunk_type == GLB_BINARY_CHUNK_TYPE:
                if not json_seen or binary_seen:
                    raise _glb_error(
                        "le chunk BIN doit être unique et suivre le chunk JSON."
                    )
                binary_chunk_offset = stream.tell()
                stream.seek(chunk_size, os.SEEK_CUR)
                binary_chunk_size = chunk_size
                binary_seen = True
            else:
                raise _glb_error("un type de chunk inconnu est présent.")
            chunk_index += 1

        if not json_seen:
            raise _glb_error("le chunk JSON obligatoire est absent.")
        if stream.tell() != declared_size:
            raise _glb_error("la table des chunks ne couvre pas exactement le fichier.")
        assert document is not None
        _validate_previewable_glb_resources(
            document,
            stream=stream,
            binary_chunk_size=binary_chunk_size,
            binary_chunk_offset=binary_chunk_offset,
            total_size=total_size,
        )
    finally:
        # Le calcul d'empreinte et le stockage qui suivent doivent toujours relire le
        # contenu entier, y compris après une validation réussie.
        stream.seek(0)


def _glb_preview_is_validated(artifact: ArtifactModel) -> bool:
    """Le contenu exact a été validé par ce routeur, pas seulement déclaré GLB."""

    metadata = artifact.metadata_json
    return (
        isinstance(metadata, dict)
        and isinstance(artifact.checksum, str)
        and metadata.get(GLB_VALIDATION_METADATA_KEY) == artifact.checksum
    )


def _metadata_with_glb_validation(
    metadata: object, *, checksum: str, validated: bool
) -> dict[str, object]:
    """Écrit ou retire le marqueur réservé sans perdre les métadonnées existantes."""

    result = dict(metadata) if isinstance(metadata, dict) else {}
    result.pop(GLB_VALIDATION_METADATA_KEY, None)
    if validated:
        result[GLB_VALIDATION_METADATA_KEY] = checksum
    return result


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
    exposed_content_type = artifact.content_type or OCTET_STREAM
    served_type, inline = safe_content_type(
        exposed_content_type, artifact.original_name or ""
    )
    if (
        served_type == GLB_CONTENT_TYPE
        and inline
        and not _glb_preview_is_validated(artifact)
    ):
        # Le web décide s'il propose un aperçu depuis ce contrat. Ne pas republier
        # le type GLB d'une ligne historique non scellée évite un bouton d'aperçu
        # que la route de contenu rétrograderait ensuite en téléchargement.
        exposed_content_type = OCTET_STREAM
    return ArtifactSummary(
        id=artifact.id,
        project_id=artifact.project_id,
        task_run_id=artifact.task_run_id,
        kind=artifact.kind,
        stream_kind=artifact.stream_kind or "",
        original_name=artifact.original_name or "",
        content_type=exposed_content_type,
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        source=artifact.source or "worker",
        has_content=bool(artifact.storage_key) and artifact.deleted_at is None,
        created_at=artifact.created_at,
    )


def _encode_cursor(artifact: ArtifactModel) -> str:
    """Curseur opaque ``(created_at UTC, id)`` ; même forme sur les deux dialectes.

    SQLite relit ses instants naïfs, PostgreSQL les relit en UTC : sans
    normalisation, un curseur émis par l'un serait décodé différemment par l'autre.
    """

    raw = f"{_as_utc(artifact.created_at).isoformat()}|{artifact.id}".encode("utf-8")
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
    try:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
    except BaseException:
        # ``storage.open`` a déjà transféré la propriété du descripteur à cette
        # fonction : même une erreur I/O inattendue pendant le dimensionnement doit
        # le restituer immédiatement.
        handle.close()
        raise
    return handle, size


def _content_response(
    *,
    artifact: ArtifactModel,
    storage: ArtifactStorage,
    range_header: str | None,
    force_download: bool,
    on_prepared: Callable[[], None] | None = None,
) -> Response:
    handle, size = _open_content(storage, artifact)
    try:
        served_type, inline = safe_content_type(
            artifact.content_type or "", artifact.original_name or ""
        )
        if (
            served_type == GLB_CONTENT_TYPE
            and inline
            and not _glb_preview_is_validated(artifact)
        ):
            # Les lignes créées avant le Lot G n'ont jamais traversé le validateur
            # GLB. Elles restent téléchargeables jusqu'à un re-téléversement validé.
            served_type, inline = OCTET_STREAM, False
        if force_download:
            # L'API de contrôle et les jetons de téléchargement ne rendent jamais le
            # contenu en ligne. Seul un jeton ``preview`` présenté sur l'origine
            # dédiée peut conserver la disposition inline calculée par l'allowlist.
            inline = False
        window = _parse_range(range_header, size)
        headers = content_headers(
            artifact=artifact, served_type=served_type, inline=inline
        )
        if window is None:
            start, end = 0, size - 1
            status_code = 200
        else:
            start, end = window
            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = 0 if size == 0 else end - start + 1
        headers["Content-Length"] = str(length)
        if on_prepared is not None:
            # Le compteur représente une réponse de contenu acceptée et préparée,
            # pas nécessairement un transfert réseau achevé par le client.
            on_prepared()
        return StreamingResponse(
            _blob_stream(handle, start, length),
            status_code=status_code,
            headers=headers,
            media_type=served_type,
        )
    except BaseException:
        handle.close()
        raise


@router.get("/artifacts/{artifact_id}/content")
def download_artifact_content(
    artifact_id: str,
    request: Request,
    token: str | None = Query(default=None, max_length=TOKEN_MAX_CHARS),
    db: Session = Depends(get_db),
) -> Response:
    """Contenu d'un livrable, par session ou par lien signé, toujours en flux."""

    force_download = True
    link_id: str | None = None
    if token:
        principal, purpose, link_id = _link_principal(
            db, artifact_id, token, request=request
        )
        force_download = purpose != "preview"
    else:
        principal = _session_principal(request, db)
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentification requise")
    artifact = _readable_artifact(db, principal, artifact_id)
    return _content_response(
        artifact=artifact,
        storage=artifact_storage(),
        range_header=request.headers.get("range"),
        force_download=force_download,
        on_prepared=(
            (lambda: _record_link_use(db, link_id)) if link_id is not None else None
        ),
    )


@preview_router.get("/artifacts/{artifact_id}/content")
def preview_artifact_content(
    artifact_id: str,
    request: Request,
    token: str = Query(min_length=1, max_length=TOKEN_MAX_CHARS),
    db: Session = Depends(get_db),
) -> Response:
    """Surface minimale : accepte uniquement un jeton d'aperçu signé.

    Cette route est montée par ``acp_api.preview`` sur une origine distincte. Elle
    ne consulte jamais une session et refuse les jetons de téléchargement afin que
    le service d'aperçu ne devienne pas une seconde API métier.
    """

    principal, purpose, link_id = _link_principal(
        db, artifact_id, token, request=request
    )
    if purpose != "preview":
        raise _refused_link("Ce lien n'autorise pas un aperçu.")
    artifact = _readable_artifact(db, principal, artifact_id)
    return _content_response(
        artifact=artifact,
        storage=artifact_storage(),
        range_header=request.headers.get("range"),
        force_download=False,
        on_prepared=lambda: _record_link_use(db, link_id),
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


def _link_principal(
    db: Session, artifact_id: str, token: str, *, request: Request
) -> tuple[str, Literal["download", "preview"], str]:
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
        claims = verify_artifact_token(
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
    if claims.purpose == "preview":
        # La vérification précède ce contrôle pour ne jamais laisser un Host forgé
        # devenir un oracle sur le contenu d'un jeton. Un refus d'origine ne compte
        # pas comme une utilisation réussie du lien.
        _require_preview_request_origin(request)
    return link.user_id, claims.purpose, link.id


def _record_link_use(db: Session, link_id: str) -> None:
    """Compte atomiquement une réponse préparée, si le lien est encore actif."""

    now = datetime.now(timezone.utc)
    result = db.execute(
        update(ArtifactLinkModel)
        .where(
            ArtifactLinkModel.id == link_id,
            ArtifactLinkModel.revoked_at.is_(None),
            ArtifactLinkModel.expires_at > now,
        )
        .values(used_count=func.coalesce(ArtifactLinkModel.used_count, 0) + 1)
    )
    if result.rowcount != 1:
        db.rollback()
        raise _refused_link("Lien expiré, révoqué ou inconnu.")
    db.commit()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _require_preview_request_origin(request: Request) -> None:
    """Refuse le rejeu d'un jeton preview sur l'origine API de contrôle."""

    try:
        expected = _configured_preview_origin(required=True)
        actual = normalize_service_origin(
            f"{request.url.scheme}://{request.url.netloc}",
            setting="origine de la requête d'aperçu",
        )
    except (HTTPException, ServiceOriginError) as exc:
        raise _refused_link("Lien d'aperçu indisponible sur cette origine.") from exc
    if actual != expected:
        raise _refused_link("Lien d'aperçu indisponible sur cette origine.")


def _configured_preview_origin(*, required: bool) -> str | None:
    """Origine d'aperçu déclarée, canonique et distincte de l'API de contrôle."""

    raw = (os.environ.get(ARTIFACT_PUBLIC_ORIGIN_ENV) or "").strip()
    if not raw:
        if required:
            raise HTTPException(
                status_code=424,
                detail=(
                    f"Aperçu désactivé : {ARTIFACT_PUBLIC_ORIGIN_ENV} doit désigner "
                    "une origine HTTPS distincte de l'API."
                ),
            )
        return None
    try:
        origin = normalize_service_origin(
            raw, setting=ARTIFACT_PUBLIC_ORIGIN_ENV
        )
    except ServiceOriginError as exc:
        raise HTTPException(
            status_code=424,
            detail=f"Aperçu désactivé : configuration {ARTIFACT_PUBLIC_ORIGIN_ENV} invalide.",
        ) from exc

    raw_api_origin = (os.environ.get("ACP_API_URL") or "").strip()
    if not raw_api_origin:
        raise HTTPException(
            status_code=424,
            detail=(
                "Aperçu désactivé : ACP_API_URL doit déclarer explicitement "
                "l'origine de l'API de contrôle."
            ),
        )
    try:
        api_origin = normalize_service_origin(raw_api_origin, setting="ACP_API_URL")
    except ServiceOriginError as exc:
        raise HTTPException(
            status_code=424,
            detail="Aperçu désactivé : configuration ACP_API_URL invalide.",
        ) from exc

    raw_browser_origins = os.environ.get(
        "ACP_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    browser_origins: set[str] = set()
    try:
        for index, raw_browser_origin in enumerate(raw_browser_origins.split(",")):
            browser_origins.add(
                normalize_service_origin(
                    raw_browser_origin.strip(),
                    setting=f"ACP_CORS_ORIGINS[{index}]",
                )
            )
    except ServiceOriginError as exc:
        raise HTTPException(
            status_code=424,
            detail="Aperçu désactivé : configuration ACP_CORS_ORIGINS invalide.",
        ) from exc

    if origin == api_origin or origin in browser_origins:
        raise HTTPException(
            status_code=424,
            detail=(
                f"Aperçu désactivé : {ARTIFACT_PUBLIC_ORIGIN_ENV} doit être distincte "
                "de l'application et de ACP_API_URL."
            ),
        )
    return origin


def _configured_download_origin() -> str:
    """Origine API canonique d'un téléchargement, ou URL relative en local."""

    raw = (os.environ.get("ACP_API_URL") or "").strip()
    if not raw:
        return ""
    try:
        return normalize_service_origin(raw, setting="ACP_API_URL")
    except ServiceOriginError as exc:
        raise HTTPException(
            status_code=424,
            detail="Lien de téléchargement désactivé : configuration ACP_API_URL invalide.",
        ) from exc


def _link_url(artifact_id: str, token: str, *, origin: str) -> str:
    """Construit l'URL après validation de son origine, avant signature/persistance.

    L'origine n'est jamais déduite de l'en-tête ``Host`` : un en-tête falsifié
    fabriquerait sinon un lien pointant vers un domaine tiers, avec un jeton valide
    dans la chaîne de requête.
    """

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
    purpose: Literal["download", "preview"] = Query(default="download"),
    db: Session = Depends(get_db),
    principal: str = Depends(get_principal),
) -> ArtifactLinkCreated:
    """Crée un lien signé, borné et révocable, lié à ce livrable et à ce demandeur."""

    artifact = _readable_artifact(db, principal, artifact_id)
    if not artifact.storage_key or artifact.deleted_at is not None:
        raise HTTPException(
            status_code=404, detail="Ce livrable n'a pas de contenu téléversé."
        )
    # Valider l'origine avant même la signature : une configuration refusée ne génère
    # aucun secret éphémère et ne laisse aucune ligne en base.
    origin = (
        _configured_preview_origin(required=True)
        if purpose == "preview"
        else _configured_download_origin()
    )
    try:
        keys = load_signing_keys(os.environ)
    except ArtifactSigningNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    token = sign_artifact_token(
        artifact.id, principal, expires_at, keys[0], purpose=purpose
    )
    url = _link_url(artifact.id, token, origin=origin)
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
        url=url,
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
        # Un transport ASGI peut livrer tout le segment et son séparateur dans
        # un unique message. Dans ce cas la boucle s'arrête aussitôt : la borne
        # doit porter sur la position trouvée, pas seulement sur les remplissages
        # où le séparateur manquait encore. ``limit`` reste une borne inclusive.
        if index > limit:
            raise MultipartFormatError("Partie multipart hors bornes.")
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
    locked = db.query(TaskRunModel).filter_by(id=run_id).with_for_update().one_or_none()
    if locked is None:
        # Une tentative disparue entre la validation des champs et le verrou est un
        # refus explicite, jamais une ``NoResultFound`` rendue en 500.
        raise HTTPException(status_code=404, detail="Tentative introuvable")


def _required_field(fields: dict[str, str], name: str) -> str:
    value = (fields.get(name) or "").strip()
    if not value:
        raise HTTPException(
            status_code=422, detail=f"Champ « {name} » obligatoire pour un téléversement."
        )
    return value


async def receive_worker_artifact_content(
    db: Session,
    worker: WorkerModel,
    request: Request,
    *,
    fencing_token: int,
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
        lease, _run = require_active_worker_attempt(
            db,
            worker_id=worker.id,
            run_id=run_id,
            fencing_token=fencing_token,
        )
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
        incoming_content_type = (
            fields.get("content_type") or uploaded.content_type or OCTET_STREAM
        ).strip()[:200] or OCTET_STREAM
        incoming_original_name = (
            fields.get("original_name") or uploaded.file_name or ""
        )[:500]
        incoming_served_type, incoming_inline = safe_content_type(
            incoming_content_type, incoming_original_name
        )
        incoming_glb_validated = (
            incoming_served_type == GLB_CONTENT_TYPE and incoming_inline
        )
        if incoming_glb_validated:
            _validate_previewable_glb(uploaded.handle, total_size=uploaded.size)
        uploaded_checksum = _uploaded_checksum(uploaded.handle)
        _lock_artifact_quota(db, run_id)
        # Le corps peut être long à recevoir. Le fence est donc revérifié sous le
        # même verrou d'écriture que la décision de quota et l'insertion : un
        # worker remplacé pendant le transfert ne peut pas publier tardivement.
        lease, _run = require_active_worker_attempt(
            db,
            worker_id=worker.id,
            run_id=run_id,
            fencing_token=fencing_token,
            lock=True,
            expire_leases=False,
        )
        task = db.get(TaskModel, lease.task_id)
        if task is None or task.project_id != project_id:
            raise HTTPException(
                status_code=400, detail="Artefact hors du projet du run"
            )
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
        storage = artifact_storage()
        if existing is not None:
            effective_content_type = existing.content_type or incoming_content_type
            effective_original_name = existing.original_name or incoming_original_name
            effective_served_type, effective_inline = safe_content_type(
                effective_content_type, effective_original_name
            )
            effective_glb_validated = (
                effective_served_type == GLB_CONTENT_TYPE and effective_inline
            )
            if effective_glb_validated and not incoming_glb_validated:
                _validate_previewable_glb(uploaded.handle, total_size=uploaded.size)
            # Une ligne seule ne prouve pas que le contenu existe. Réécrire via
            # l’adressage par contenu vérifie le blob et répare atomiquement une
            # ligne metadata-only ou un blob manquant/corrompu.
            if existing.storage_key is None:
                remaining = quota - _used_bytes_for_run(db, run_id)
                if remaining <= 0 or uploaded.size > remaining:
                    raise _too_large(max(remaining, 0), max_file, quota)
                cap = min(max_file, remaining)
            else:
                # Une ligne déjà comptée dans le quota garde le droit de réparer
                # son propre blob, y compris si le plafond a été abaissé depuis.
                cap = max_file
            try:
                repaired = storage.write(uploaded.handle, max_bytes=cap)
            except ArtifactTooLarge as exc:
                raise _too_large(cap, max_file, quota) from exc
            except (ArtifactStorageFull, ArtifactStorageUnavailable) as exc:
                _raise_storage_failure(db, exc, (run_id, project_id))
            if repaired.sha256 != uploaded_checksum:
                _raise_storage_failure(
                    db,
                    ArtifactStorageUnavailable("empreinte de stockage incohérente"),
                    (run_id, project_id),
                )
            existing.checksum = repaired.sha256
            existing.size_bytes = repaired.size
            existing.storage_key = repaired.key
            existing.worker_id = existing.worker_id or worker.id
            existing.content_type = effective_content_type
            existing.original_name = effective_original_name
            existing.source = existing.source or "worker"
            existing.stream_kind = existing.stream_kind or (
                fields.get("stream_kind") or ""
            ).strip()[:50]
            existing.metadata_json = _metadata_with_glb_validation(
                existing.metadata_json,
                checksum=repaired.sha256,
                validated=effective_glb_validated,
            )
            db.commit()
            db.refresh(existing)
            return _summary(existing)
        remaining = quota - _used_bytes_for_run(db, run_id)
        if remaining <= 0 or uploaded.size > remaining:
            raise _too_large(max(remaining, 0), max_file, quota)
        cap = min(max_file, remaining)
        if uploaded.size > cap:
            raise _too_large(cap, max_file, quota)
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
        metadata_json=_metadata_with_glb_validation(
            {}, checksum=blob.sha256, validated=incoming_glb_validated
        ),
        storage_key=blob.key,
        content_type=incoming_content_type,
        original_name=incoming_original_name,
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
