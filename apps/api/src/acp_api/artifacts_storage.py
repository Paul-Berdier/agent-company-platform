"""Stockage des livrables, adressé par contenu.

Le contenu d'un livrable ne vit jamais dans la base : il est écrit sous
``ACP_ARTIFACT_STORAGE_DIR`` (défaut ``./acp-data/artifacts``) sous la clé
``<sha256[0:2]>/<sha256>``. Deux téléversements du même contenu partagent donc le
même fichier, ce qui rend l'ingestion idempotente sans dédoublonnage applicatif.

Trois règles portent la sécurité de ce module :

1. **Aucun nom fourni par le client n'entre dans un chemin.** Le nom d'origine reste
   une métadonnée (``artifacts.original_name``) ; la clé est entièrement dérivée du
   contenu.
2. **La borne de taille est appliquée pendant la lecture du flux**, jamais après
   avoir tout écrit : un émetteur hostile ne peut pas remplir le disque avant d'être
   refusé, et un refus ne laisse aucun fragment.
3. **L'écriture est atomique** : un fichier temporaire du même volume puis
   ``os.replace``. Un lecteur ne voit jamais un blob partiel.

L'interface ``ArtifactStorage`` est explicite pour accueillir un adaptateur objet
(S3) dans un lot ultérieur ; seul l'adaptateur local est livré ici.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

ARTIFACT_STORAGE_DIR_ENV = "ACP_ARTIFACT_STORAGE_DIR"
ARTIFACT_MAX_BYTES_ENV = "ACP_ARTIFACT_MAX_BYTES"
ARTIFACT_MAX_BYTES_PER_RUN_ENV = "ACP_ARTIFACT_MAX_BYTES_PER_RUN"

DEFAULT_ARTIFACT_STORAGE_DIR = "./acp-data/artifacts"
DEFAULT_ARTIFACT_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_ARTIFACT_MAX_BYTES_PER_RUN = 1024 * 1024 * 1024

CHUNK_BYTES = 1024 * 1024
TEMP_DIRECTORY_NAME = "tmp"

_KEY_PATTERN = re.compile(r"^([0-9a-f]{2})/([0-9a-f]{64})$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ArtifactStorageError(RuntimeError):
    """Le stockage n'a pas pu satisfaire la demande."""


class ArtifactTooLarge(ArtifactStorageError):
    """Le flux dépasse la taille autorisée ; rien n'est conservé."""


class ArtifactStorageFull(ArtifactStorageError):
    """Le volume ou le quota physique du stockage est saturé."""


class ArtifactStorageUnavailable(ArtifactStorageError):
    """Le stockage est inaccessible pour une autre raison opérationnelle."""


class ArtifactNotFound(ArtifactStorageError):
    """La clé demandée n'a aucun contenu dans ce stockage."""


class ArtifactKeyInvalid(ArtifactStorageError, ValueError):
    """La clé n'a pas la forme ``<sha256[0:2]>/<sha256>`` : rien n'est tenté."""


@dataclass(frozen=True, slots=True)
class StoredBlob:
    """Résultat d'une écriture : empreinte, taille réelle et clé de stockage."""

    sha256: str
    size: int
    key: str


def content_key(sha256: str) -> str:
    """Clé de stockage d'une empreinte connue (``<sha256[0:2]>/<sha256>``)."""

    digest = sha256.strip().lower()
    if not _SHA256_PATTERN.match(digest):
        raise ArtifactKeyInvalid(
            "Empreinte invalide : 64 caractères hexadécimaux minuscules attendus."
        )
    return f"{digest[:2]}/{digest}"


@runtime_checkable
class ArtifactStorage(Protocol):
    """Contrat minimal d'un stockage de livrables (local aujourd'hui, objet demain)."""

    def write(self, stream: BinaryIO, *, max_bytes: int) -> StoredBlob:
        """Écrit le flux et renvoie son empreinte, sa taille et sa clé."""

    def open(self, key: str) -> BinaryIO:
        """Ouvre le blob en lecture binaire (flux, jamais un chargement mémoire)."""

    def delete(self, key: str) -> None:
        """Supprime le blob ; l'absence n'est pas une erreur."""

    def exists(self, key: str) -> bool:
        """Indique si le blob est présent."""


class LocalArtifactStorage:
    """Stockage sur disque local, adressé par contenu."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).expanduser()

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"LocalArtifactStorage(root={self._root!s})"

    @property
    def root(self) -> Path:
        return self._root

    # --- écriture -------------------------------------------------------------

    def write(self, stream: BinaryIO, *, max_bytes: int) -> StoredBlob:
        """Traduit les erreurs du système en états métier sans exposer de chemin."""

        try:
            return self._write(stream, max_bytes=max_bytes)
        except ArtifactStorageError:
            raise
        except OSError as exc:
            raise storage_error_from_oserror(exc) from exc

    def _write(self, stream: BinaryIO, *, max_bytes: int) -> StoredBlob:
        """Écrit ``stream`` de façon atomique en refusant tout dépassement en vol.

        Lève ``ArtifactTooLarge`` dès que le cumul dépasse ``max_bytes`` : le chunk
        fautif n'est pas écrit et le fichier temporaire est supprimé.
        """

        if max_bytes <= 0:
            raise ValueError(
                "La borne de taille d'un livrable doit être strictement positive."
            )
        temp_directory = self._root / TEMP_DIRECTORY_NAME
        temp_directory.mkdir(parents=True, exist_ok=True)
        _restrict(temp_directory, directory=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=temp_directory, prefix="upload-", suffix=".part"
        )
        temp_path = Path(temp_name)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(descriptor, "wb") as destination:
                while True:
                    chunk = stream.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray)):
                        raise ArtifactStorageError(
                            "Flux invalide : un flux binaire est attendu."
                        )
                    size += len(chunk)
                    if size > max_bytes:
                        raise ArtifactTooLarge(
                            "Livrable refusé : la taille dépasse "
                            f"{max_bytes} octets."
                        )
                    digest.update(chunk)
                    destination.write(chunk)
            sha256 = digest.hexdigest()
            key = content_key(sha256)
            target = self._root / sha256[:2] / sha256
            target.parent.mkdir(parents=True, exist_ok=True)
            _restrict(target.parent, directory=True)
            if target.exists():
                if self._matches(target, sha256=sha256, size=size):
                    return StoredBlob(sha256=sha256, size=size, key=key)
                # Une cible adressée par ce digest mais corrompue est remplacée
                # atomiquement. La renvoyer sur la seule foi de son nom ferait
                # d’un replay un faux succès.
                os.replace(temp_path, target)
                _restrict(target)
            else:
                try:
                    os.replace(temp_path, target)
                except OSError:
                    # Course entre deux téléversements du même contenu : sous
                    # Windows, remplacer un fichier ouvert en lecture échoue.
                    # L'adressage par contenu garantit que la cible porte déjà
                    # les mêmes octets ; sinon l'erreur reste une erreur.
                    if not target.is_file() or not self._matches(
                        target, sha256=sha256, size=size
                    ):
                        raise
                else:
                    _restrict(target)
            return StoredBlob(sha256=sha256, size=size, key=key)
        finally:
            # Refus, erreur de flux ou contenu déjà stocké : rien ne reste.
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                # Ne masque jamais la cause initiale. Le suffixe ``.part`` reste
                # exclu des lectures et pourra être nettoyé par la maintenance.
                pass

    @staticmethod
    def _matches(path: Path, *, sha256: str, size: int) -> bool:
        try:
            if path.stat().st_size != size:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_BYTES):
                    digest.update(chunk)
            return digest.hexdigest() == sha256
        except OSError:
            return False

    # --- lecture --------------------------------------------------------------

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return path.open("rb")
        except FileNotFoundError as exc:
            raise ArtifactNotFound(
                "Contenu introuvable : le livrable a été purgé ou n'a jamais été téléversé."
            ) from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    # --- interne --------------------------------------------------------------

    def _path(self, key: str) -> Path:
        match = _KEY_PATTERN.match(key or "")
        if match is None or not match.group(2).startswith(match.group(1)):
            raise ArtifactKeyInvalid(
                "Clé de livrable invalide : « <sha256[0:2]>/<sha256> » attendu."
            )
        return self._root / match.group(1) / match.group(2)


def _restrict(path: Path, *, directory: bool = False) -> None:
    """Restreint les permissions au service quand le système le permet.

    Windows ignore ``chmod`` au-delà du bit lecture seule : l'échec n'est jamais
    fatal, il est simplement sans effet.
    """

    try:
        path.chmod(0o700 if directory else 0o600)
    except (OSError, NotImplementedError):  # pragma: no cover - dépend du système
        pass


def _is_storage_full(error: OSError) -> bool:
    """Reconnaît ENOSPC/EDQUOT et l'équivalent Windows ERROR_DISK_FULL."""

    return error.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)} or getattr(
        error, "winerror", None
    ) == 112


def storage_error_from_oserror(error: OSError) -> ArtifactStorageError:
    """Convertit une erreur disque, y compris celle du spool multipart."""

    if _is_storage_full(error):
        return ArtifactStorageFull(
            "Stockage saturé : libérez de l'espace avant de réessayer."
        )
    return ArtifactStorageUnavailable(
        "Stockage indisponible : vérifiez le volume et ses permissions."
    )


# --- configuration ------------------------------------------------------------


def storage_directory(environ: Mapping[str, str] = os.environ) -> Path:
    """Racine du stockage des livrables (``ACP_ARTIFACT_STORAGE_DIR``)."""

    raw = (environ.get(ARTIFACT_STORAGE_DIR_ENV) or "").strip()
    return Path(raw or DEFAULT_ARTIFACT_STORAGE_DIR).expanduser()


def local_artifact_storage(
    environ: Mapping[str, str] = os.environ,
) -> LocalArtifactStorage:
    """Stockage local configuré par l'environnement."""

    return LocalArtifactStorage(storage_directory(environ))


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} : un nombre entier d'octets est attendu, « {raw} » a été lu."
        ) from exc
    if value <= 0:
        raise ValueError(f"{name} : la borne doit être strictement positive.")
    return value


def artifact_max_bytes(environ: Mapping[str, str] = os.environ) -> int:
    """Taille maximale d'un livrable (``ACP_ARTIFACT_MAX_BYTES``, défaut 200 Mio)."""

    return _positive_int(environ, ARTIFACT_MAX_BYTES_ENV, DEFAULT_ARTIFACT_MAX_BYTES)


def artifact_max_bytes_per_run(environ: Mapping[str, str] = os.environ) -> int:
    """Quota de livrables par tentative (``ACP_ARTIFACT_MAX_BYTES_PER_RUN``, défaut 1 Gio)."""

    return _positive_int(
        environ, ARTIFACT_MAX_BYTES_PER_RUN_ENV, DEFAULT_ARTIFACT_MAX_BYTES_PER_RUN
    )
