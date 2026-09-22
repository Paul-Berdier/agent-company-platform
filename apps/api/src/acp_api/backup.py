"""Sauvegarde, vérification et restauration avec manifeste.

Une sauvegarde est un répertoire : l'instantané de la base (copie SQLite ou
``pg_dump`` au format custom), une archive ``tar`` par répertoire de fichiers
(livrables adressés par contenu, révisions de skills) et un ``manifest.json`` qui
décrit tout ce que le répertoire contient — empreintes, tailles, révision Alembic,
comptages par table, clés de stockage citées, identifiants de clés de secrets —
sans jamais contenir de secret.

Quatre décisions structurent ce module :

1. **La base d'abord, les fichiers ensuite.** L'API écrit un blob avant la ligne
   qui le cite ; sauvegarder la base puis les fichiers garantit que tout blob cité
   par une ligne de l'instantané existe déjà dans l'archive. L'ordre inverse
   pourrait archiver un état des fichiers antérieur à une ligne de la base.
2. **Une restauration se refuse plutôt que de deviner.** Dialecte différent,
   cible qui est la source, base ou répertoires non vides : refus explicite. Le
   remplacement n'est possible qu'avec ``--replace --pre-restore-backup DIR2``,
   qui sauvegarde et vérifie d'abord la cible.
3. **Rien n'est cru sur parole.** ``verify`` recalcule les empreintes ; ``restore``
   commence par ``verify`` et finit par des contrôles de cohérence (révision,
   comptages, blobs cités, dossiers de révisions, clés de secrets) dont chaque
   écart est listé et rend le code 3.
4. **Aucune migration implicite.** Une base restaurée à une révision antérieure à
   la tête du code reste telle quelle ; le message dit quoi exécuter.

Codes de sortie : ``0`` succès, ``1`` échec d'exécution (outil en échec, base
injoignable), ``2`` usage, ``3`` refus ou écart constaté.

Usage :

```text
python -m acp_api.backup create --output DIR [--database-url URL] [--label TXT]
python -m acp_api.backup verify DIR
python -m acp_api.backup inspect DIR
python -m acp_api.backup restore DIR --into URL [--artifacts-dir D] [--skills-dir D]
    [--replace --pre-restore-backup DIR2] [--require-secret-keys]
```
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import sys
import tarfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, TextIO

from alembic.script.revision import ResolutionError
from alembic.util.exc import CommandError
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from acp_database import snapshot
from acp_database.engine import make_engine
from acp_database.schema_state import (
    VERSION_TABLE,
    check_schema_current,
    head_revision,
    script_directory,
)
from acp_database.snapshot import SnapshotError, redacted_url

from .artifacts_storage import (
    ARTIFACT_STORAGE_DIR_ENV,
    TEMP_DIRECTORY_NAME,
    storage_directory as artifacts_storage_directory,
)
from .secrets_vault import VaultNotConfigured, key_id, load_keys

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3

FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_FILES = {"sqlite": "database.sqlite", "postgresql": "database.pgdump"}
SKILLS_STORAGE_DIR_ENV = "ACP_SKILLS_STORAGE_DIR"
ARTIFACTS_DIRECTORY = "artifacts"
SKILLS_DIRECTORY = "skills"
DIRECTORY_ARCHIVES = {ARTIFACTS_DIRECTORY: "artifacts.tar", SKILLS_DIRECTORY: "skills.tar"}
UPGRADE_HINT_POSTGRESQL = "exécutez « python -m acp_database.migrate upgrade »"
UPGRADE_HINT_SQLITE = (
    "init_db() mettra le schéma à niveau au prochain démarrage de l'API "
    "(« python -m acp_database.migrate upgrade » est refusé sous SQLite)"
)

_CHUNK_BYTES = 1024 * 1024
_BLOB_DIR_PATTERN = re.compile(r"^[0-9a-f]{2}$")
_BLOB_FILE_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class BackupError(Exception):
    """Base des erreurs de ce module ; le message est destiné à l'opérateur."""


class UsageError(BackupError):
    """Erreur d'usage de la ligne de commande (code 2)."""


class Refusal(BackupError):
    """Refus explicite ou écart constaté (code 3)."""


# --- Outils --------------------------------------------------------------------


def product_version() -> str:
    """Version du produit lue dans le fichier ``VERSION`` du dépôt.

    Le manifeste la porte pour qu'un opérateur sache quel code a produit la
    sauvegarde ; hors dépôt (paquet installé seul), la valeur est ``inconnue``
    plutôt qu'inventée.
    """

    for candidate in (Path(__file__).resolve().parents[3] / "VERSION", Path.cwd() / "VERSION"):
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "inconnue"


def dialect_of(url: str) -> str:
    """``sqlite`` ou ``postgresql`` ; tout autre dialecte est un refus."""

    try:
        driver = make_url(url).drivername
    except ArgumentError as exc:
        raise Refusal(f"URL de base invalide : {exc}") from exc
    if driver.startswith("sqlite"):
        return "sqlite"
    if driver.startswith("postgresql"):
        return "postgresql"
    raise Refusal(
        f"Dialecte « {driver} » non pris en charge : sqlite ou postgresql attendu"
    )


def url_fingerprint(url: str) -> str:
    """Empreinte d'une URL sans mot de passe, stable pour une même base.

    Une URL SQLite est ramenée à son chemin absolu : ``sqlite:///./acp.db`` et
    sa forme absolue désignent la même base et doivent donner la même empreinte,
    car c'est elle qui interdit de restaurer une sauvegarde sur sa propre source.
    """

    if dialect_of(url) == "sqlite":
        canonical = f"sqlite:///{snapshot.sqlite_database_path(url).as_posix()}"
    else:
        canonical = redacted_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _open_engine(url: str):
    """Moteur de maintenance (sans délais applicatifs) sur ``url``."""

    try:
        return make_engine(url, maintenance=True)
    except RuntimeError as exc:
        raise Refusal(str(exc)) from exc


def _table_names(engine) -> list[str]:
    return sorted(name for name in inspect(engine).get_table_names() if name != VERSION_TABLE)


def _row_counts(engine) -> dict[str, int]:
    """Nombre de lignes de chaque table (hors table de version), par ordre de nom."""

    preparer = engine.dialect.identifier_preparer
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in _table_names(engine):
            counts[table] = int(
                connection.execute(
                    text(f"SELECT COUNT(*) FROM {preparer.quote(table)}")
                ).scalar_one()
            )
    return counts


def _referenced_storage_keys(engine) -> list[str]:
    """Clés de stockage citées par un livrable non supprimé."""

    if not inspect(engine).has_table("artifacts"):
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT DISTINCT storage_key FROM artifacts "
                "WHERE storage_key IS NOT NULL AND deleted_at IS NULL"
            )
        ).scalars()
        return sorted(key for key in rows if key)


def _secret_key_ids(engine) -> list[str]:
    """Identifiants (jamais les clés) des clés ayant chiffré un secret non révoqué."""

    if not inspect(engine).has_table("secrets"):
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT DISTINCT key_id FROM secrets WHERE revoked_at IS NULL")
        ).scalars()
        return sorted(value for value in rows if value)


def _skill_revisions(engine) -> list[tuple[str, int, str]]:
    if not inspect(engine).has_table("skill_revisions"):
        return []
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT skill_id, number, storage_path FROM skill_revisions")
        ).all()
    return [(str(row[0]), int(row[1]), str(row[2] or "")) for row in rows]


def _configured_secret_key_ids(environ: Mapping[str, str]) -> set[str] | None:
    """Identifiants dérivés de ``ACP_SECRETS_KEYS`` ; ``None`` si le coffre est absent."""

    try:
        return {key_id(key) for key in load_keys(environ)}
    except VaultNotConfigured:
        return None


def skills_storage_directory(environ: Mapping[str, str]) -> Path:
    """Racine des révisions de skills, telle que ``acp_api.skills.service`` la lit."""

    from .skills.service import storage_directory

    return storage_directory(environ)


# --- Archives ------------------------------------------------------------------


def _member_problem(name: str) -> str | None:
    """Raison de refuser un membre d'archive, ou ``None`` s'il reste sous la racine."""

    if not name or name in (".", "./"):
        return "nom vide"
    if "\\" in name:
        return "séparateur Windows interdit"
    if name.startswith("/") or _WINDOWS_DRIVE.match(name):
        return "chemin absolu"
    parts = PurePosixPath(name).parts
    if any(part in ("..", "") for part in parts):
        return "remonte au-dessus de la racine"
    return None


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Membres réguliers d'une archive ; tout membre hostile est un refus.

    Liens symboliques, liens durs, périphériques et tubes sont refusés : une
    archive de sauvegarde ne contient que des fichiers et des répertoires, et un
    lien pourrait faire écrire hors de la racine cible lors de l'extraction.
    """

    members = []
    for member in archive.getmembers():
        problem = _member_problem(member.name)
        if problem is not None:
            raise Refusal(
                f"Archive {Path(archive.name or '').name} : membre « {member.name} » "
                f"refusé ({problem})"
            )
        if member.isdir():
            members.append(member)
            continue
        if not member.isfile():
            raise Refusal(
                f"Archive {Path(archive.name or '').name} : membre « {member.name} » "
                "refusé (seuls des fichiers et des répertoires sont admis)"
            )
        members.append(member)
    return members


def _archive_entries(archive_path: Path) -> int:
    """Nombre de fichiers réguliers d'une archive dont chaque membre est sûr."""

    try:
        with tarfile.open(archive_path, "r:") as archive:
            return sum(1 for member in _safe_members(archive) if member.isfile())
    except tarfile.TarError as exc:
        raise Refusal(f"Archive {archive_path.name} illisible : {exc}") from exc


def _archive_directory(
    root: Path,
    destination: Path,
    *,
    excluded_top_level: frozenset[str] = frozenset(),
    excluded_suffixes: tuple[str, ...] = (),
    warnings: list[str],
) -> tuple[str, int, int]:
    """Archive les fichiers réguliers de ``root`` ; retourne (sha256, octets, entrées).

    Un répertoire absent donne une archive vide et un avertissement : une
    installation neuve n'a encore aucun livrable, ce n'est pas une erreur. Les
    liens symboliques sont ignorés avec avertissement plutôt que suivis.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    label = destination.stem
    with tarfile.open(destination, "w", format=tarfile.PAX_FORMAT) as archive:
        if not root.is_dir():
            warnings.append(
                f"répertoire {label} absent ({root}) : archive vide"
            )
        else:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if relative.parts and relative.parts[0] in excluded_top_level:
                    continue
                if path.is_symlink():
                    warnings.append(
                        f"lien symbolique ignoré dans {label} : {relative.as_posix()}"
                    )
                    continue
                if path.is_dir():
                    archive.add(path, arcname=relative.as_posix(), recursive=False)
                    continue
                if not path.is_file() or path.name.endswith(excluded_suffixes):
                    continue
                archive.add(path, arcname=relative.as_posix(), recursive=False)
                entries += 1
    sha256, size = _sha256_of(destination)
    return sha256, size, entries


def _extract_archive(archive_path: Path, target: Path) -> int:
    """Extrait une archive vérifiée sous ``target`` ; retourne le nombre de fichiers.

    Chaque membre a déjà été contrôlé par :func:`_safe_members` ; le filtre
    ``data`` de :mod:`tarfile` ajoute une seconde barrière du côté de la
    bibliothèque standard.
    """

    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:") as archive:
        members = _safe_members(archive)
        archive.extractall(path=target, members=members, filter="data")
    return sum(1 for member in members if member.isfile())


# --- Manifeste -----------------------------------------------------------------


def _write_manifest(directory: Path, manifest: dict[str, Any]) -> Path:
    path = directory / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_manifest(directory: Path) -> dict[str, Any]:
    """Lit et valide la structure d'un manifeste ; toute lacune est un refus."""

    path = Path(directory) / MANIFEST_NAME
    if not path.is_file():
        raise Refusal(f"Manifeste introuvable : {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal(f"Manifeste illisible ({path.name}) : {exc}") from exc
    if not isinstance(manifest, dict):
        raise Refusal("Manifeste invalide : un objet JSON est attendu")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise Refusal(
            f"Manifeste de format {manifest.get('format_version')!r} : seul le "
            f"format {FORMAT_VERSION} est pris en charge"
        )
    database = manifest.get("database")
    if not isinstance(database, dict):
        raise Refusal("Manifeste invalide : section « database » absente")
    for key in ("dialect", "file", "sha256", "bytes", "row_counts"):
        if key not in database:
            raise Refusal(f"Manifeste invalide : « database.{key} » absent")
    if database["dialect"] not in DATABASE_FILES:
        raise Refusal(
            f"Manifeste invalide : dialecte « {database['dialect']} » inconnu"
        )
    if not isinstance(database["row_counts"], dict):
        raise Refusal("Manifeste invalide : « database.row_counts » doit être un objet")
    directories = manifest.get("directories")
    if not isinstance(directories, list):
        raise Refusal("Manifeste invalide : section « directories » absente")
    for entry in directories:
        if not isinstance(entry, dict) or not all(
            key in entry for key in ("name", "archive", "sha256", "bytes", "entries")
        ):
            raise Refusal("Manifeste invalide : entrée de « directories » incomplète")
    for key in (
        "created_at",
        "product_version",
        "source_url_fingerprint",
        "artifact_storage_keys_referenced",
        "secrets_key_ids",
        "warnings",
    ):
        if key not in manifest:
            raise Refusal(f"Manifeste invalide : « {key} » absent")
    return manifest


# --- Création ------------------------------------------------------------------


def _require_empty_output(directory: Path, *, what: str) -> None:
    if directory.exists():
        if not directory.is_dir():
            raise Refusal(f"{what} : {directory} existe et n'est pas un répertoire")
        if any(directory.iterdir()):
            raise Refusal(
                f"{what} : {directory} n'est pas vide ; une sauvegarde n'écrase "
                "jamais un répertoire existant"
            )


def create_backup(
    *,
    database_url: str,
    output: Path,
    artifacts_dir: Path,
    skills_dir: Path,
    label: str = "",
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO | None = None,
) -> dict[str, Any]:
    """Produit une sauvegarde complète dans ``output`` et retourne son manifeste.

    Ordre imposé : instantané de la base, puis archive des livrables, puis archive
    des skills (voir la docstring du module). Sous SQLite, révision, comptages et
    références sont lus **dans la copie** produite : le manifeste décrit
    exactement le fichier livré. Sous PostgreSQL, ils sont lus sur la base après
    ``pg_dump`` ; un comptage qui aurait bougé entre le début et la fin de
    l'instantané est signalé dans ``warnings`` (l'API écrivait pendant la
    sauvegarde) plutôt que présenté comme exact.
    """

    out = stdout or sys.stdout
    output = Path(output)
    _require_empty_output(output, what="Répertoire de sortie")
    dialect = dialect_of(database_url)
    warnings: list[str] = []
    output.mkdir(parents=True, exist_ok=True)
    database_file = output / DATABASE_FILES[dialect]

    if dialect == "sqlite":
        snapshot.dump_sqlite(database_url, database_file)
        engine = _open_engine(f"sqlite:///{database_file.as_posix()}")
        counts_before = None
    else:
        live = _open_engine(database_url)
        try:
            counts_before = _row_counts(live)
        finally:
            live.dispose()
        snapshot.dump_postgresql(database_url, database_file, environ)
        engine = _open_engine(database_url)
    try:
        state = check_schema_current(engine)
        row_counts = _row_counts(engine)
        storage_keys = _referenced_storage_keys(engine)
        secret_key_ids = _secret_key_ids(engine)
    finally:
        engine.dispose()
    if state.current is None and row_counts:
        raise Refusal(
            "La base contient des tables mais aucune révision Alembic : démarrez "
            "l'API (SQLite) ou exécutez « python -m acp_database.migrate upgrade » "
            "(PostgreSQL) avant de la sauvegarder"
        )
    if state.current is None:
        warnings.append("base vide : aucune table ni révision Alembic")
    if counts_before is not None and counts_before != row_counts:
        changed = sorted(
            table
            for table in set(counts_before) | set(row_counts)
            if counts_before.get(table) != row_counts.get(table)
        )
        warnings.append(
            "la base a été modifiée pendant l'instantané (tables : "
            + ", ".join(changed)
            + ") ; les comptages décrivent l'état après pg_dump, pas l'instantané"
        )
    sha256, size = _sha256_of(database_file)
    print(
        f"Base {dialect} sauvegardée : {database_file.name} ({size} octets, "
        f"révision {state.current or 'aucune'}, {sum(row_counts.values())} lignes)",
        file=out,
    )

    directories = []
    for name, root, exclusions in (
        (
            ARTIFACTS_DIRECTORY,
            Path(artifacts_dir),
            {
                "excluded_top_level": frozenset({TEMP_DIRECTORY_NAME}),
                "excluded_suffixes": (".part",),
            },
        ),
        (SKILLS_DIRECTORY, Path(skills_dir), {}),
    ):
        archive = output / DIRECTORY_ARCHIVES[name]
        archive_sha256, archive_size, entries = _archive_directory(
            root, archive, warnings=warnings, **exclusions
        )
        directories.append(
            {
                "name": name,
                "archive": archive.name,
                "sha256": archive_sha256,
                "bytes": archive_size,
                "entries": entries,
            }
        )
        print(
            f"Répertoire {name} archivé : {archive.name} ({entries} fichiers, "
            f"{archive_size} octets)",
            file=out,
        )

    manifest = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_version": product_version(),
        "label": label or "",
        "database": {
            "dialect": dialect,
            "alembic_current": state.current,
            "file": database_file.name,
            "sha256": sha256,
            "bytes": size,
            "row_counts": row_counts,
        },
        "directories": directories,
        "artifact_storage_keys_referenced": storage_keys,
        "secrets_key_ids": secret_key_ids,
        "source_url_fingerprint": url_fingerprint(database_url),
        "warnings": warnings,
    }
    _write_manifest(output, manifest)
    for warning in warnings:
        print(f"Avertissement : {warning}", file=out)
    print(f"Manifeste écrit : {output / MANIFEST_NAME}", file=out)
    return manifest


# --- Vérification --------------------------------------------------------------


def verify_backup(
    directory: Path, *, stdout: TextIO | None = None
) -> dict[str, Any]:
    """Contrôle une sauvegarde sans rien restaurer ; retourne son manifeste.

    Recalcule empreintes et tailles, exige la présence de chaque fichier annoncé,
    contrôle l'en-tête du fichier de base, refuse tout membre d'archive qui
    sortirait de sa racine, et vérifie que la révision Alembic est connue de la
    chaîne du code courant (une révision inconnue rendrait la base restaurée
    impossible à migrer). Tous les écarts sont listés dans un seul refus.
    """

    out = stdout or sys.stdout
    directory = Path(directory)
    manifest = load_manifest(directory)
    problems: list[str] = []
    database = manifest["database"]

    database_file = directory / str(database["file"])
    if not database_file.is_file():
        problems.append(f"fichier de base absent : {database['file']}")
    else:
        sha256, size = _sha256_of(database_file)
        if sha256 != database["sha256"]:
            problems.append(f"empreinte de {database['file']} différente du manifeste")
        if size != database["bytes"]:
            problems.append(
                f"taille de {database['file']} : {size} octets, manifeste {database['bytes']}"
            )
        with database_file.open("rb") as handle:
            header = handle.read(16)
        expected = (
            snapshot.SQLITE_HEADER
            if database["dialect"] == "sqlite"
            else snapshot.PG_CUSTOM_HEADER
        )
        if not header.startswith(expected):
            problems.append(
                f"{database['file']} n'a pas l'en-tête d'un instantané {database['dialect']}"
            )

    revision = database.get("alembic_current")
    if revision is None:
        if database["row_counts"]:
            problems.append("révision Alembic absente alors que la base contient des tables")
    else:
        try:
            script_directory().get_revision(str(revision))
        except (ResolutionError, CommandError):
            problems.append(
                f"révision Alembic « {revision} » inconnue de la chaîne du code courant"
            )

    for entry in manifest["directories"]:
        archive_path = directory / str(entry["archive"])
        if not archive_path.is_file():
            problems.append(f"archive absente : {entry['archive']}")
            continue
        sha256, size = _sha256_of(archive_path)
        if sha256 != entry["sha256"]:
            problems.append(f"empreinte de {entry['archive']} différente du manifeste")
        if size != entry["bytes"]:
            problems.append(
                f"taille de {entry['archive']} : {size} octets, manifeste {entry['bytes']}"
            )
        try:
            entries = _archive_entries(archive_path)
        except Refusal as exc:
            problems.append(str(exc))
            continue
        if entries != entry["entries"]:
            problems.append(
                f"{entry['archive']} contient {entries} fichiers, manifeste {entry['entries']}"
            )

    if problems:
        raise Refusal(
            f"Sauvegarde {directory} refusée :\n  - " + "\n  - ".join(problems)
        )
    current = product_version()
    if manifest["product_version"] != current:
        print(
            f"Avertissement : sauvegarde produite par la version "
            f"{manifest['product_version']}, code courant {current}",
            file=out,
        )
    print(
        f"Sauvegarde vérifiée : {database['file']} et "
        f"{len(manifest['directories'])} archive(s) conformes au manifeste "
        f"(révision {revision or 'aucune'})",
        file=out,
    )
    return manifest


def describe_backup(directory: Path, *, stdout: TextIO | None = None) -> dict[str, Any]:
    """Résumé lisible d'une sauvegarde d'après son manifeste (sans recalcul)."""

    out = stdout or sys.stdout
    manifest = load_manifest(Path(directory))
    database = manifest["database"]
    row_counts = database["row_counts"]
    lines = [
        f"Sauvegarde : {Path(directory)}",
        f"Créée le : {manifest['created_at']} (version {manifest['product_version']})",
        f"Libellé : {manifest.get('label') or '(aucun)'}",
        f"Base : {database['dialect']}, fichier {database['file']} "
        f"({database['bytes']} octets), révision {database.get('alembic_current') or 'aucune'}",
        f"Tables : {len(row_counts)}, lignes : {sum(row_counts.values())}",
    ]
    for table in sorted(row_counts):
        lines.append(f"  - {table} : {row_counts[table]}")
    for entry in manifest["directories"]:
        lines.append(
            f"Répertoire {entry['name']} : {entry['archive']} "
            f"({entry['entries']} fichiers, {entry['bytes']} octets)"
        )
    lines.append(
        f"Clés de stockage citées : {len(manifest['artifact_storage_keys_referenced'])}"
    )
    lines.append(
        "Clés de secrets requises : "
        + (", ".join(manifest["secrets_key_ids"]) or "aucune")
    )
    lines.append(f"Empreinte de la source : {manifest['source_url_fingerprint']}")
    for warning in manifest["warnings"]:
        lines.append(f"Avertissement : {warning}")
    lines.append("Exécutez « verify » pour recalculer empreintes et tailles.")
    print("\n".join(lines), file=out)
    return manifest


# --- Restauration --------------------------------------------------------------


def _target_tables(url: str) -> list[str]:
    """Tables présentes dans la cible, sans jamais créer un fichier SQLite absent."""

    if dialect_of(url) == "sqlite":
        if not snapshot.sqlite_database_path(url).exists():
            return []
    engine = _open_engine(url)
    try:
        return sorted(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _directory_is_empty(path: Path) -> bool:
    return not path.exists() or (path.is_dir() and not any(path.iterdir()))


def _move_aside(path: Path, stamp: str) -> Path | None:
    if not path.exists():
        return None
    aside = path.with_name(f"{path.name}.pre-restore-{stamp}")
    if aside.exists():
        raise Refusal(f"Le répertoire de mise à l'écart existe déjà : {aside}")
    path.rename(aside)
    return aside


def _blob_keys_present(root: Path) -> set[str]:
    """Clés des blobs présents sous ``root`` (forme ``xx/<sha256>`` uniquement)."""

    keys: set[str] = set()
    if not root.is_dir():
        return keys
    for prefix_dir in root.iterdir():
        if not prefix_dir.is_dir() or not _BLOB_DIR_PATTERN.match(prefix_dir.name):
            continue
        for blob in prefix_dir.iterdir():
            if (
                blob.is_file()
                and _BLOB_FILE_PATTERN.match(blob.name)
                and blob.name.startswith(prefix_dir.name)
            ):
                keys.add(f"{prefix_dir.name}/{blob.name}")
    return keys


def _post_restore_checks(
    *,
    manifest: dict[str, Any],
    into_url: str,
    artifacts_dir: Path,
    skills_dir: Path,
    environ: Mapping[str, str],
    require_secret_keys: bool,
    stdout: TextIO,
) -> tuple[list[str], list[str], str | None]:
    """Compare la cible restaurée au manifeste ; retourne (écarts, avertissements, révision)."""

    problems: list[str] = []
    warnings: list[str] = []
    database = manifest["database"]
    engine = _open_engine(into_url)
    try:
        state = check_schema_current(engine)
        if state.current != database.get("alembic_current"):
            problems.append(
                f"révision Alembic restaurée {state.current or 'aucune'}, manifeste "
                f"{database.get('alembic_current') or 'aucune'}"
            )
        counts = _row_counts(engine)
        expected_counts = {str(k): int(v) for k, v in database["row_counts"].items()}
        for table in sorted(set(counts) | set(expected_counts)):
            if counts.get(table) != expected_counts.get(table):
                problems.append(
                    f"table {table} : {counts.get(table, 'absente')} ligne(s), "
                    f"manifeste {expected_counts.get(table, 'absente')}"
                )
        referenced = set(_referenced_storage_keys(engine))
        with engine.connect() as connection:
            all_keys = (
                set(
                    connection.execute(
                        text(
                            "SELECT DISTINCT storage_key FROM artifacts "
                            "WHERE storage_key IS NOT NULL"
                        )
                    ).scalars()
                )
                if inspect(engine).has_table("artifacts")
                else set()
            )
        revisions = _skill_revisions(engine)
        secret_key_ids = set(_secret_key_ids(engine))
    finally:
        engine.dispose()

    present = _blob_keys_present(artifacts_dir)
    for key in sorted(referenced - present):
        problems.append(f"livrable cité sans blob : {key}")
    for key in sorted(present - all_keys):
        problems.append(f"blob sans ligne de livrable : {key}")

    skills_anchor = skills_dir.resolve()
    for skill_id, number, _storage_path in sorted(revisions):
        # Même emplacement que le lecteur de skills : la colonne historique n'est
        # pas suivie et ne constitue donc pas un défaut de relocalisation.
        expected = (skills_anchor / skill_id / str(number)).resolve()
        if not expected.is_relative_to(skills_anchor):
            problems.append(f"révision de skill hors de la racine configurée : {skill_id}/{number}")
        elif not expected.is_dir():
            problems.append(
                f"révision de skill sans dossier : {skill_id}/{number} (attendu {expected})"
            )

    configured = _configured_secret_key_ids(environ)
    missing = sorted(secret_key_ids - (configured or set()))
    if missing:
        message = (
            "clés de secrets absentes de ACP_SECRETS_KEYS : "
            + ", ".join(missing)
            + " ; les secrets chiffrés avec elles seront indéchiffrables"
        )
        if require_secret_keys:
            problems.append(message)
        else:
            warnings.append(message)
    return problems, warnings, state.current


def restore_backup(
    directory: Path,
    *,
    into_url: str,
    artifacts_dir: Path,
    skills_dir: Path,
    replace: bool = False,
    pre_restore_backup: Path | None = None,
    require_secret_keys: bool = False,
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO | None = None,
) -> list[str]:
    """Restaure une sauvegarde vérifiée dans une cible vide ; retourne les écarts.

    Refus (avant toute écriture) : sauvegarde invalide, dialecte différent, cible
    identique à la source, cible non vide sans ``replace`` et ``pre_restore_backup``.
    Avec ces deux options, la cible est d'abord sauvegardée puis vérifiée dans
    ``pre_restore_backup`` ; rien n'est vidé si cette étape échoue. Les répertoires
    cibles ne sont jamais supprimés : ils sont mis à l'écart sous
    ``<dir>.pre-restore-<horodatage>``.

    La liste retournée contient les écarts des contrôles post-restauration ; elle
    est vide quand la cible correspond au manifeste. La restauration elle-même a
    alors eu lieu : un écart décrit un état à corriger, pas une restauration
    annulée (``pg_restore --single-transaction`` protège la base, pas les fichiers).
    """

    out = stdout or sys.stdout
    directory = Path(directory)
    artifacts_dir = Path(artifacts_dir)
    skills_dir = Path(skills_dir)
    if replace != (pre_restore_backup is not None):
        raise UsageError(
            "--replace et --pre-restore-backup vont ensemble : le remplacement exige "
            "une sauvegarde préalable de la cible, et cette sauvegarde n'a de sens "
            "qu'avec un remplacement"
        )
    manifest = verify_backup(directory, stdout=out)
    database = manifest["database"]
    target_dialect = dialect_of(into_url)
    if target_dialect != database["dialect"]:
        raise Refusal(
            f"Dialecte de la cible ({target_dialect}) différent de la sauvegarde "
            f"({database['dialect']}) : l'import d'un dialecte vers un autre n'est "
            "pas pris en charge"
        )
    if url_fingerprint(into_url) == manifest["source_url_fingerprint"]:
        raise Refusal(
            "La cible est la base d'origine de cette sauvegarde : restaurez dans "
            "une base voisine puis basculez la configuration, jamais sur la source"
        )

    tables = _target_tables(into_url)
    wiped = False
    occupied: list[str] = []
    if tables:
        occupied.append(f"base {redacted_url(into_url)} ({len(tables)} table(s))")
    for name, path in ((ARTIFACTS_DIRECTORY, artifacts_dir), (SKILLS_DIRECTORY, skills_dir)):
        if not _directory_is_empty(path):
            occupied.append(f"répertoire {name} {path}")
    if occupied:
        if not replace:
            raise Refusal(
                "Cible non vide : "
                + " ; ".join(occupied)
                + ". Relancez avec --replace --pre-restore-backup DIR2 pour "
                "sauvegarder la cible puis la remplacer"
            )
        assert pre_restore_backup is not None
        pre_restore_backup = Path(pre_restore_backup)
        if target_dialect == "sqlite" and not tables:
            print(
                "Base cible absente ou vide : aucune sauvegarde préalable de la "
                "base n'est possible ; les répertoires seront mis à l'écart",
                file=out,
            )
        else:
            print(f"Sauvegarde préalable de la cible dans {pre_restore_backup}", file=out)
            create_backup(
                database_url=into_url,
                output=pre_restore_backup,
                artifacts_dir=artifacts_dir,
                skills_dir=skills_dir,
                label="pre-restore",
                environ=environ,
                stdout=out,
            )
            verify_backup(pre_restore_backup, stdout=out)
        # Ordre imposé : les opérations réversibles d'abord, l'irréversible ensuite.
        # Vider le schéma avant de déplacer les répertoires laissait la cible vide
        # dès qu'un renommage échouait (fichier ouvert, répertoire de mise à
        # l'écart déjà présent), sans aucun retour possible.
        stamp = _utc_stamp()
        moved: list[tuple[Path, Path]] = []
        try:
            for path in (artifacts_dir, skills_dir):
                if _directory_is_empty(path):
                    continue
                aside = _move_aside(path, stamp)
                if aside is not None:
                    moved.append((aside, path))
                    print(f"Répertoire mis à l'écart : {aside}", file=out)
            if tables and target_dialect == "postgresql":
                snapshot.schema_wipe_postgresql(into_url)
                wiped = True
                print("Schéma public de la cible vidé", file=out)
        except BaseException:
            # Rien d'irréversible n'a encore eu lieu si le vidage n'a pas abouti :
            # les répertoires retrouvent leur place et la cible reste intacte.
            for aside, original in reversed(moved):
                try:
                    aside.rename(original)
                except OSError:
                    print(
                        f"Répertoire laissé à l'écart : {aside} (remise en place "
                        f"impossible vers {original})",
                        file=out,
                    )
            raise

    database_file = directory / str(database["file"])
    try:
        if target_dialect == "sqlite":
            snapshot.restore_sqlite(database_file, into_url)
        else:
            snapshot.restore_postgresql(database_file, into_url, environ)
    except BaseException:
        if wiped:
            # L'opérateur doit savoir que la cible est vide et où se trouve son
            # contenu précédent : un simple message d'échec le laisserait croire
            # que rien n'a bougé.
            print(
                f"État de la cible : base {redacted_url(into_url)} VIDÉE et non "
                "restaurée"
                + (
                    f" ; sauvegarde préalable vérifiée dans {pre_restore_backup}"
                    if pre_restore_backup is not None
                    else ""
                ),
                file=out,
            )
        raise
    print(f"Base restaurée dans {redacted_url(into_url)}", file=out)
    for entry in manifest["directories"]:
        target = artifacts_dir if entry["name"] == ARTIFACTS_DIRECTORY else skills_dir
        extracted = _extract_archive(directory / str(entry["archive"]), target)
        print(f"Répertoire {entry['name']} restauré dans {target} ({extracted} fichiers)", file=out)

    problems, warnings, current = _post_restore_checks(
        manifest=manifest,
        into_url=into_url,
        artifacts_dir=artifacts_dir,
        skills_dir=skills_dir,
        environ=environ,
        require_secret_keys=require_secret_keys,
        stdout=out,
    )
    for warning in warnings:
        print(f"Avertissement : {warning}", file=out)
    if problems:
        print(
            "Restauration effectuée mais écarts constatés :\n  - " + "\n  - ".join(problems),
            file=out,
        )
    else:
        print("Contrôles post-restauration conformes au manifeste", file=out)
    head = head_revision()
    if current != head:
        hint = UPGRADE_HINT_SQLITE if target_dialect == "sqlite" else UPGRADE_HINT_POSTGRESQL
        print(
            f"Révision restaurée {current or 'aucune'} antérieure à la tête {head} : "
            f"{hint}. Aucune migration n'est lancée automatiquement",
            file=out,
        )
    return problems


# --- Commande ------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """Analyseur dont les erreurs d'usage sont capturées plutôt que fatales."""

    def __init__(self, *args, stdout: TextIO, stderr: TextIO, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stdout = stdout
        self._stderr = stderr

    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message)

    def _print_message(self, message: str, file=None) -> None:  # type: ignore[override]
        if message:
            (self._stderr if file is sys.stderr else self._stdout).write(message)


def _build_parser(stdout: TextIO, stderr: TextIO) -> _Parser:
    parser = _Parser(
        prog="python -m acp_api.backup",
        description="Sauvegarde, vérification et restauration avec manifeste.",
        stdout=stdout,
        stderr=stderr,
    )
    commands = parser.add_subparsers(
        dest="command",
        metavar="commande",
        parser_class=functools.partial(_Parser, stdout=stdout, stderr=stderr),
    )
    commands.required = True

    create = commands.add_parser("create", help="produit une sauvegarde complète")
    create.add_argument("--output", required=True, help="répertoire de sortie (vide ou absent)")
    create.add_argument("--database-url", default=None, help="URL de la base (sinon ACP_DATABASE_URL)")
    create.add_argument("--artifacts-dir", default=None, help=f"racine des livrables (sinon {ARTIFACT_STORAGE_DIR_ENV})")
    create.add_argument("--skills-dir", default=None, help=f"racine des skills (sinon {SKILLS_STORAGE_DIR_ENV})")
    create.add_argument("--label", default="", help="libellé libre inscrit dans le manifeste")

    verify = commands.add_parser("verify", help="recalcule empreintes et présence des fichiers")
    verify.add_argument("directory")

    inspect_command = commands.add_parser("inspect", help="résumé lisible d'une sauvegarde")
    inspect_command.add_argument("directory")

    restore = commands.add_parser("restore", help="restaure dans une cible vide")
    restore.add_argument("directory")
    restore.add_argument("--into", required=True, help="URL de la base cible")
    restore.add_argument("--artifacts-dir", default=None, help=f"racine cible des livrables (sinon {ARTIFACT_STORAGE_DIR_ENV})")
    restore.add_argument("--skills-dir", default=None, help=f"racine cible des skills (sinon {SKILLS_STORAGE_DIR_ENV})")
    restore.add_argument("--replace", action="store_true", help="remplace une cible non vide (exige --pre-restore-backup)")
    restore.add_argument("--pre-restore-backup", default=None, help="répertoire où sauvegarder la cible avant remplacement")
    restore.add_argument("--require-secret-keys", action="store_true", help="refuse si une clé de secret manque dans ACP_SECRETS_KEYS")
    return parser


def _directories(namespace, environ: Mapping[str, str]) -> tuple[Path, Path]:
    """Racines des livrables et des skills : options explicites, sinon environnement."""

    artifacts_dir = (
        Path(namespace.artifacts_dir).expanduser()
        if namespace.artifacts_dir
        else artifacts_storage_directory(environ)
    )
    skills_dir = (
        Path(namespace.skills_dir).expanduser()
        if namespace.skills_dir
        else skills_storage_directory(environ)
    )
    return artifacts_dir, skills_dir


def _run(namespace, environ: Mapping[str, str], stdout: TextIO) -> int:
    if namespace.command in ("create", "restore"):
        artifacts_dir, skills_dir = _directories(namespace, environ)
    if namespace.command == "create":
        url = namespace.database_url or environ.get("ACP_DATABASE_URL", "")
        if not url:
            raise UsageError("aucune URL de base : passez --database-url ou renseignez ACP_DATABASE_URL")
        create_backup(
            database_url=url,
            output=Path(namespace.output).expanduser(),
            artifacts_dir=artifacts_dir,
            skills_dir=skills_dir,
            label=namespace.label,
            environ=environ,
            stdout=stdout,
        )
        return EXIT_OK
    if namespace.command == "verify":
        verify_backup(Path(namespace.directory).expanduser(), stdout=stdout)
        return EXIT_OK
    if namespace.command == "inspect":
        describe_backup(Path(namespace.directory).expanduser(), stdout=stdout)
        return EXIT_OK
    if namespace.command == "restore":
        problems = restore_backup(
            Path(namespace.directory).expanduser(),
            into_url=namespace.into,
            artifacts_dir=artifacts_dir,
            skills_dir=skills_dir,
            replace=namespace.replace,
            pre_restore_backup=(
                Path(namespace.pre_restore_backup).expanduser()
                if namespace.pre_restore_backup
                else None
            ),
            require_secret_keys=namespace.require_secret_keys,
            environ=environ,
            stdout=stdout,
        )
        return EXIT_REFUSED if problems else EXIT_OK
    raise UsageError(f"commande inconnue : {namespace.command}")


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Point d'entrée de la commande ; retourne le code de sortie sans quitter."""

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    env = environ if environ is not None else os.environ
    parser = _build_parser(out, err)
    try:
        namespace = parser.parse_args(list(argv) if argv is not None else None)
    except UsageError as exc:
        err.write(f"Usage incorrect : {exc}\n")
        return EXIT_USAGE
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    try:
        return _run(namespace, env, out)
    except UsageError as exc:
        err.write(f"Usage incorrect : {exc}\n")
        return EXIT_USAGE
    except Refusal as exc:
        err.write(f"Refus : {exc}\n")
        return EXIT_REFUSED
    except (SnapshotError, SQLAlchemyError, RuntimeError, OSError) as exc:
        err.write(f"Échec : {exc}\n")
        return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover - utilitaire de console
    sys.exit(main())
