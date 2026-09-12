"""Matérialisation d'une source de skill en une liste de fichiers contrôlés.

Quatre sources sont supportées : ``manual`` (fichiers fournis dans la requête), ``directory``
(dossier local explicitement autorisé), ``archive`` (zip ou tar.gz transmis en base64) et
``github`` (tarball d'un commit épinglé, téléchargé via ``PinnedHttpClient``).

Toutes les sources passent par les mêmes contrôles avant d'être acceptées :

- 500 fichiers, 20 Mio au total, 2 Mio par fichier ;
- chemins relatifs normalisés, sans ``..``, sans chemin absolu (POSIX ou lettre de lecteur),
  sans UNC, sans segment vide, sans octet nul, sans nom de périphérique réservé de Windows
  (``NUL``, ``CON``, ``COM1``…) ni segment terminé par un point ou une espace ;
- aucun lien symbolique, jonction Windows (point de reparse) ni fichier spécial
  (``tarfile.data_filter`` puis contrôle manuel) ;
- rien n'est écrit sur le disque : l'extraction est faite en mémoire, la seule écriture a
  lieu ensuite sous ``ACP_SKILLS_STORAGE_DIR`` et uniquement si la révision est acceptée.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import re
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Iterable, Mapping, Sequence

import httpx

from acp_contracts import (
    SkillSourceArchive,
    SkillSourceDirectory,
    SkillSourceGithub,
    SkillSourceManual,
)

from . import SkillError
from ..outbound import OutboundPolicyError, PinnedHttpClient

MAX_FILES = 500
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_GITHUB_BYTES = 25 * 1024 * 1024
MAX_UNWRAP_DEPTH = 5

GITHUB_USER_AGENT = "acp-platform/skills-import"
GITHUB_API_VERSION = "2022-11-28"

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_SKIPPED_DIRECTORIES = {".git"}

# Noms de périphériques réservés de Windows : un fichier « NUL » y serait écrit dans le
# périphérique nul (contenu perdu) alors que le manifeste annoncerait sa taille et son
# empreinte. Refusés sur toutes les plateformes pour que le manifeste reste portable.
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class MaterializedSource:
    """Fichiers matérialisés et provenance (aucun secret, aucune URL d'authentification)."""

    files: list[tuple[str, bytes]]
    source_kind: str
    origin: str = ""
    source_ref: str = ""
    notes: list[str] = field(default_factory=list)


# --- Contrôles communs -------------------------------------------------------


def normalize_member_path(raw: str) -> str:
    """Normalise un chemin d'entrée en chemin relatif POSIX ; refuse tout ce qui sort de la racine."""

    candidate = (raw or "").replace("\\", "/").strip()
    if not candidate:
        raise SkillError("Chemin de fichier refusé : nom vide.")
    if "\x00" in candidate:
        raise SkillError(f"Chemin de fichier refusé : « {raw} » (octet nul interdit).")
    if candidate.startswith("/") or candidate.startswith("//"):
        raise SkillError(f"Chemin de fichier refusé : « {raw} » (chemin absolu interdit).")
    if _DRIVE_PREFIX.match(candidate):
        raise SkillError(f"Chemin de fichier refusé : « {raw} » (chemin absolu interdit).")
    segments: list[str] = []
    for segment in candidate.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise SkillError(
                f"Chemin de fichier refusé : « {raw} » (remontée « .. » interdite)."
            )
        if segment[-1] in (".", " "):
            raise SkillError(
                f"Chemin de fichier refusé : « {raw} » (segment « {segment} » terminé par "
                "un point ou une espace : le nom écrit sur disque différerait du manifeste)."
            )
        if segment.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise SkillError(
                f"Chemin de fichier refusé : « {raw} » (segment « {segment} » : nom de "
                "périphérique réservé sous Windows, le contenu ne serait pas stocké)."
            )
        segments.append(segment)
    if not segments:
        raise SkillError(f"Chemin de fichier refusé : « {raw} » (nom vide après normalisation).")
    return "/".join(segments)


class _Collector:
    """Accumule les fichiers en appliquant les limites de nombre, de taille et de total."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._total = 0

    def add(self, raw_path: str, data: bytes, *, declared_size: int | None = None) -> None:
        path = normalize_member_path(raw_path)
        size = declared_size if declared_size is not None else len(data)
        if size > MAX_FILE_BYTES:
            raise SkillError(
                f"Fichier « {path} » refusé : {size} octets, limite {MAX_FILE_BYTES} octets par fichier.",
                status_code=413,
            )
        if len(data) > MAX_FILE_BYTES:
            raise SkillError(
                f"Fichier « {path} » refusé : contenu supérieur à {MAX_FILE_BYTES} octets.",
                status_code=413,
            )
        if path not in self._files and len(self._files) >= MAX_FILES:
            raise SkillError(
                f"Source refusée : plus de {MAX_FILES} fichiers.", status_code=413
            )
        self._total += len(data)
        if self._total > MAX_TOTAL_BYTES:
            raise SkillError(
                f"Source refusée : contenu total supérieur à {MAX_TOTAL_BYTES} octets.",
                status_code=413,
            )
        self._files[path] = data

    def result(self) -> list[tuple[str, bytes]]:
        if not self._files:
            raise SkillError("Source refusée : aucun fichier exploitable.")
        return sorted(self._files.items())


def unwrap_single_root(files: Sequence[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Retire le dossier racine unique d'une archive tant que ``SKILL.md`` n'est pas à la racine."""

    current = list(files)
    for _ in range(MAX_UNWRAP_DEPTH):
        paths = [path for path, _ in current]
        if any(path == "SKILL.md" for path in paths):
            return current
        if not paths or not all("/" in path for path in paths):
            return current
        roots = {path.split("/", 1)[0] for path in paths}
        if len(roots) != 1:
            return current
        current = [(path.split("/", 1)[1], data) for path, data in current]
    return current


def select_subtree(files: Sequence[tuple[str, bytes]], subpath: str) -> list[tuple[str, bytes]]:
    """Restreint l'arborescence à ``subpath`` et la re-enracine ; refuse un sous-dossier absent."""

    if not subpath:
        return list(files)
    prefix = normalize_member_path(subpath) + "/"
    selected = [(path[len(prefix) :], data) for path, data in files if path.startswith(prefix)]
    if not selected:
        raise SkillError(
            f"Sous-dossier « {subpath} » absent de l'archive téléchargée."
        )
    return selected


# --- Configuration -----------------------------------------------------------


def allowed_directories(environ: Mapping[str, str] = os.environ) -> list[Path]:
    """Dossiers d'import autorisés (``ACP_SKILLS_ALLOWED_DIRS``, séparés par ``os.pathsep``)."""

    raw = (environ.get("ACP_SKILLS_ALLOWED_DIRS") or "").strip()
    if not raw:
        return []
    directories: list[Path] = []
    for entry in raw.split(os.pathsep):
        entry = entry.strip()
        if not entry:
            continue
        directories.append(Path(entry).expanduser().resolve())
    return directories


def github_enabled(environ: Mapping[str, str] = os.environ) -> bool:
    """``ACP_SKILLS_GITHUB_ENABLED=1`` autorise le téléchargement d'un tarball GitHub."""

    return (environ.get("ACP_SKILLS_GITHUB_ENABLED") or "0").strip() == "1"


def github_token(environ: Mapping[str, str] = os.environ) -> str | None:
    value = (environ.get("ACP_GITHUB_TOKEN") or "").strip()
    return value or None


# --- Sources -----------------------------------------------------------------


def _from_manual(source: SkillSourceManual) -> MaterializedSource:
    collector = _Collector()
    for entry in source.files:
        collector.add(entry.path, entry.content.encode("utf-8"))
    return MaterializedSource(files=collector.result(), source_kind="manual")


def _from_directory(source: SkillSourceDirectory, allowed: Sequence[Path]) -> MaterializedSource:
    """Le dossier doit être contenu dans un dossier autorisé, après résolution des liens."""

    requested = Path(source.path).expanduser()
    logical = requested if requested.is_absolute() else Path.cwd() / requested
    candidate = Path(os.path.normpath(str(logical)))
    if not _is_inside_any(candidate, allowed):
        raise SkillError(
            "Import refusé : dossier non autorisé. Ajoutez ce chemin à ACP_SKILLS_ALLOWED_DIRS.",
            status_code=403,
        )
    if not candidate.exists():
        raise SkillError(f"Dossier introuvable : « {source.path} ».", status_code=404)
    if _is_reparse_point(candidate):
        raise SkillError(
            "Import refusé : dossier non autorisé (lien symbolique ou jonction).", status_code=403
        )
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise SkillError(f"Dossier introuvable : « {source.path} ».", status_code=404)
    if not _is_inside_any(resolved, allowed):
        raise SkillError(
            "Import refusé : dossier non autorisé après résolution des liens.", status_code=403
        )

    anchor = os.path.realpath(resolved)
    collector = _Collector()
    for root, directories, filenames in os.walk(resolved, followlinks=False):
        kept: list[str] = []
        for name in sorted(directories):
            if name in _SKIPPED_DIRECTORIES:
                continue
            _ensure_contained(Path(root, name), anchor)
            kept.append(name)
        directories[:] = kept
        for filename in sorted(filenames):
            entry = Path(root, filename)
            _ensure_contained(entry, anchor)
            if not entry.is_file():
                raise SkillError(
                    f"Import refusé : fichier spécial « {entry.name} » dans le dossier source.",
                    status_code=403,
                )
            relative = entry.relative_to(resolved).as_posix()
            size = entry.stat().st_size
            if size > MAX_FILE_BYTES:
                raise SkillError(
                    f"Fichier « {relative} » refusé : {size} octets, limite {MAX_FILE_BYTES} octets.",
                    status_code=413,
                )
            collector.add(relative, entry.read_bytes())
    return MaterializedSource(
        files=collector.result(),
        source_kind="directory",
        origin=str(resolved),
        source_ref=str(resolved),
    )


def _is_reparse_point(entry: Path) -> bool:
    """Lien symbolique **ou** point de reparse Windows (jonction ``mklink /J``).

    ``Path.is_symlink`` et ``os.walk(followlinks=False)`` ignorent les jonctions : elles
    sortiraient du dossier autorisé sans être détectées comme des liens.
    """

    try:
        status = entry.lstat()
    except OSError:
        # Entrée illisible : traitée comme suspecte, jamais ignorée silencieusement.
        return True
    if stat.S_ISLNK(status.st_mode):
        return True
    return bool(getattr(status, "st_file_attributes", 0) & _REPARSE_POINT)


def _ensure_contained(entry: Path, anchor: str) -> None:
    """Refuse une entrée qui est un lien/une jonction ou dont la cible réelle sort de ``anchor``.

    Le contrôle porte sur **chaque** entrée parcourue, pas seulement sur la racine : une
    jonction déposée dans un dossier autorisé exposerait sinon n'importe quel fichier de la
    machine.
    """

    if _is_reparse_point(entry):
        raise SkillError(
            f"Import refusé : « {entry.name} » est un lien symbolique ou une jonction "
            "dans le dossier source.",
            status_code=403,
        )
    real = os.path.realpath(entry)
    if os.path.normcase(real) != os.path.normcase(anchor) and not os.path.normcase(
        real
    ).startswith(os.path.normcase(os.path.join(anchor, ""))):
        raise SkillError(
            f"Import refusé : « {entry.name} » sort du dossier autorisé après résolution.",
            status_code=403,
        )


def _is_inside_any(candidate: Path, allowed: Iterable[Path]) -> bool:
    for root in allowed:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _from_archive(source: SkillSourceArchive) -> MaterializedSource:
    try:
        payload = base64.b64decode(source.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SkillError(f"Archive refusée : contenu base64 invalide ({exc}).") from exc
    if not payload:
        raise SkillError("Archive refusée : contenu vide.")
    if len(payload) > MAX_TOTAL_BYTES:
        raise SkillError(
            f"Archive refusée : {len(payload)} octets transmis, limite {MAX_TOTAL_BYTES} octets.",
            status_code=413,
        )
    digest = hashlib.sha256(payload).hexdigest()
    files = extract_archive(payload, source.filename)
    return MaterializedSource(
        files=unwrap_single_root(files),
        source_kind="archive",
        origin=source.filename,
        source_ref=f"sha256:{digest}",
    )


def extract_archive(payload: bytes, filename: str) -> list[tuple[str, bytes]]:
    """Extrait un zip ou un tar.gz en mémoire en appliquant tous les contrôles."""

    lowered = filename.lower()
    if lowered.endswith(".zip"):
        return _extract_zip(payload)
    if lowered.endswith((".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz")):
        return _extract_tar(payload)
    raise SkillError(
        f"Format d'archive non reconnu pour « {filename} » : utilisez .zip, .tar.gz ou .tgz."
    )


def _extract_zip(payload: bytes) -> list[tuple[str, bytes]]:
    collector = _Collector()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise SkillError(
                        f"Archive refusée : lien symbolique « {info.filename} » interdit."
                    )
                if info.file_size > MAX_FILE_BYTES:
                    raise SkillError(
                        f"Fichier « {info.filename} » refusé : {info.file_size} octets, "
                        f"limite {MAX_FILE_BYTES} octets par fichier.",
                        status_code=413,
                    )
                # Le chemin est contrôlé avant toute lecture du contenu.
                path = normalize_member_path(info.filename)
                with archive.open(info) as handle:
                    data = handle.read(MAX_FILE_BYTES + 1)
                collector.add(path, data, declared_size=info.file_size)
    except zipfile.BadZipFile as exc:
        raise SkillError(f"Archive zip illisible : {exc}.") from exc
    return collector.result()


def _extract_tar(payload: bytes) -> list[tuple[str, bytes]]:
    collector = _Collector()
    reference = os.path.realpath(os.getcwd())
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
            for member in archive:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise SkillError(
                        f"Archive refusée : entrée « {member.name} » non régulière "
                        "(lien symbolique ou fichier spécial)."
                    )
                try:
                    tarfile.data_filter(member, reference)
                except tarfile.FilterError as exc:
                    raise SkillError(f"Archive refusée : entrée « {member.name} » ({exc}).") from exc
                if member.size > MAX_FILE_BYTES:
                    raise SkillError(
                        f"Fichier « {member.name} » refusé : {member.size} octets, "
                        f"limite {MAX_FILE_BYTES} octets par fichier.",
                        status_code=413,
                    )
                path = normalize_member_path(member.name)
                handle = archive.extractfile(member)
                if handle is None:
                    raise SkillError(f"Archive refusée : entrée « {member.name} » illisible.")
                data = handle.read(MAX_FILE_BYTES + 1)
                collector.add(path, data, declared_size=member.size)
    except tarfile.TarError as exc:
        raise SkillError(f"Archive tar illisible : {exc}.") from exc
    return collector.result()


def _from_github(
    source: SkillSourceGithub,
    *,
    enabled: bool,
    token: str | None,
    pinned_client: PinnedHttpClient | None,
) -> MaterializedSource:
    if not enabled:
        raise SkillError(
            "Import GitHub non configuré : définissez ACP_SKILLS_GITHUB_ENABLED=1 pour "
            "autoriser le téléchargement d'un tarball épinglé.",
            status_code=503,
        )
    if pinned_client is None:
        raise SkillError(
            "Import GitHub non configuré : aucun client HTTP contrôlé disponible.",
            status_code=503,
        )
    owner, repository = source.repository.split("/", 1)
    if owner in (".", "..") or repository in (".", ".."):
        # « ../.. » satisfait le motif « owner/repo » mais viserait un autre chemin de l'API
        # après normalisation de l'URL par le client HTTP.
        raise SkillError(f"Dépôt GitHub invalide : « {source.repository} ».")
    url = f"https://api.github.com/repos/{owner}/{repository}/tarball/{source.ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": GITHUB_USER_AGENT,
    }
    if token:
        # Jamais réémis vers une autre origine : ``PinnedHttpClient`` retire les identifiants
        # lors de la redirection vers codeload.github.com.
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = pinned_client.request("GET", url, headers=headers)
    except OutboundPolicyError as exc:
        raise SkillError(
            f"Téléchargement GitHub refusé par la politique de sortie ({exc.code}) : {exc}",
            status_code=502,
        ) from exc
    except httpx.HTTPError as exc:
        raise SkillError(
            f"Téléchargement GitHub impossible : {type(exc).__name__} ({exc}).", status_code=502
        ) from exc
    if response.status_code != 200:
        raise SkillError(
            f"Téléchargement GitHub refusé : réponse HTTP {response.status_code} "
            f"pour {source.repository}@{source.ref}.",
            status_code=502,
        )
    payload = response.content
    if len(payload) > MAX_GITHUB_BYTES:
        raise SkillError(
            f"Archive GitHub refusée : {len(payload)} octets, limite {MAX_GITHUB_BYTES} octets.",
            status_code=413,
        )
    files = unwrap_single_root(_extract_tar(payload))
    files = select_subtree(files, source.path)
    reference = f"{source.repository}@{source.ref}"
    if source.path:
        reference = f"{reference}:{source.path}"
    return MaterializedSource(
        files=files,
        source_kind="github",
        origin=reference,
        source_ref=reference,
    )


def materialize(
    source: SkillSourceManual | SkillSourceDirectory | SkillSourceArchive | SkillSourceGithub,
    *,
    allowed_dirs: Sequence[Path] = (),
    github_enabled: bool = False,
    github_token: str | None = None,
    pinned_client: PinnedHttpClient | None = None,
    tmp_dir: Path | None = None,
) -> MaterializedSource:
    """Matérialise ``source`` en mémoire et retourne les fichiers contrôlés et leur provenance.

    ``tmp_dir`` est accepté pour la compatibilité de signature : l'extraction n'écrit jamais
    sur le disque, ce qui supprime toute fenêtre d'écriture hors du stockage des révisions.
    """

    if isinstance(source, SkillSourceManual):
        return _from_manual(source)
    if isinstance(source, SkillSourceDirectory):
        return _from_directory(source, allowed_dirs)
    if isinstance(source, SkillSourceArchive):
        return _from_archive(source)
    if isinstance(source, SkillSourceGithub):
        return _from_github(
            source, enabled=github_enabled, token=github_token, pinned_client=pinned_client
        )
    raise SkillError(f"Type de source inconnu : {type(source).__name__}.")
