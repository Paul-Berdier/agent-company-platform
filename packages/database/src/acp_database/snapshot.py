"""Instantanés physiques d'une base : copie SQLite cohérente, ``pg_dump`` et ``pg_restore``.

Ce module ne connaît ni le manifeste ni les répertoires de fichiers : il ne
produit et ne rejoue que l'image d'une base, dans le format natif de chaque
dialecte.

- **SQLite** : ``VACUUM INTO`` écrit une copie compacte et transactionnellement
  cohérente depuis une connexion ``sqlite3`` dédiée, même si l'application écrit
  au même moment (la copie voit l'état validé au début de sa lecture, jamais une
  transaction en cours). La restauration remplace le fichier de façon atomique.
- **PostgreSQL** : ``pg_dump --format=custom`` et ``pg_restore`` sont exécutés
  comme des commandes externes dont la sortie standard (ou l'entrée standard)
  est le fichier d'instantané. Aucune option ``-f`` n'est jamais utilisée : la
  commande peut ainsi tourner dans un conteneur (``docker exec``) qui ne voit
  pas le système de fichiers de l'opérateur.

Les messages d'erreur ne contiennent jamais de mot de passe : les URL sont
rendues masquées et la sortie des outils est expurgée avant d'être citée.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .engine import make_engine

PG_DUMP_COMMAND_ENV = "ACP_BACKUP_PG_DUMP_COMMAND"
PG_RESTORE_COMMAND_ENV = "ACP_BACKUP_PG_RESTORE_COMMAND"
TOOLS_URL_ENV = "ACP_BACKUP_DATABASE_URL_FOR_TOOLS"

#: Jeton remplacé par l'URL libpq de la base dans les commandes d'outils.
URL_TOKEN = "{url}"

DEFAULT_PG_DUMP_COMMAND: tuple[str, ...] = (
    "pg_dump",
    "--format=custom",
    "--no-owner",
    "--no-privileges",
    "--dbname",
    URL_TOKEN,
)
DEFAULT_PG_RESTORE_COMMAND: tuple[str, ...] = (
    "pg_restore",
    "--no-owner",
    "--no-privileges",
    "--exit-on-error",
    "--single-transaction",
    "--dbname",
    URL_TOKEN,
)

#: Exemples cités dans les refus quand le binaire manque sur le poste.
DOCKER_PG_DUMP_EXAMPLE = json.dumps(
    ["docker", "exec", "acp-pg", *DEFAULT_PG_DUMP_COMMAND], ensure_ascii=False
)
DOCKER_PG_RESTORE_EXAMPLE = json.dumps(
    ["docker", "exec", "-i", "acp-pg", *DEFAULT_PG_RESTORE_COMMAND], ensure_ascii=False
)

SQLITE_HEADER = b"SQLite format 3\x00"
PG_CUSTOM_HEADER = b"PGDMP"

#: Fichiers annexes qu'un remplacement de base SQLite doit retirer : un journal
#: ou un WAL de l'ancienne base appliqué au nouveau fichier le corromprait.
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

_OUTPUT_TAIL_CHARS = 1500


class SnapshotError(RuntimeError):
    """Instantané impossible ; le message est en français et sans mot de passe."""


class SnapshotToolMissing(SnapshotError):
    """Le binaire ``pg_dump``/``pg_restore`` est introuvable sur ce poste."""


# --- URL --------------------------------------------------------------------------


def redacted_url(url: str) -> str:
    """URL sans mot de passe, la seule forme admise dans un message ou un journal."""

    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return "<URL illisible>"


def _password_of(url: str) -> str | None:
    try:
        return make_url(url).password
    except ArgumentError:
        return None


def _scrub(output: str, secrets: Sequence[str | None]) -> str:
    """Expurge chaque secret connu d'une sortie d'outil avant de la citer."""

    scrubbed = output
    for secret in secrets:
        if secret:
            scrubbed = scrubbed.replace(secret, "***")
    return scrubbed


def sqlite_database_path(url: str) -> Path:
    """Chemin du fichier d'une URL SQLite ; une base mémoire est refusée.

    Une base ``sqlite://`` ou ``:memory:`` ne survit pas au processus qui la
    porte : la sauvegarder n'aurait aucun sens et la « restaurer » écrirait dans le
    vide.
    """

    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise SnapshotError(f"URL SQLite invalide : {exc}") from exc
    if not parsed.drivername.startswith("sqlite"):
        raise SnapshotError(
            f"URL SQLite attendue, reçu le dialecte « {parsed.drivername} »"
        )
    database = (parsed.database or "").strip()
    if not database or database == ":memory:" or database.startswith("file:"):
        raise SnapshotError(
            "Une base SQLite en mémoire ou en URI ne peut pas être sauvegardée : "
            "seule une base fichier est prise en charge"
        )
    return Path(database).expanduser().resolve()


def tool_url(url: str, environ: Mapping[str, str] = os.environ) -> str:
    """URL libpq passée aux outils PostgreSQL, ou sa substitution d'environnement.

    ``pg_dump`` ne comprend pas le pilote ``+psycopg`` de SQLAlchemy : il est
    retiré. Quand l'outil tourne dans un conteneur, l'adresse du serveur vue
    depuis ce conteneur n'est pas celle de l'opérateur (``127.0.0.1:5432`` au lieu
    de ``127.0.0.1:55432``) : ``ACP_BACKUP_DATABASE_URL_FOR_TOOLS`` remplace alors
    entièrement l'URL substituée au jeton ``{url}``.
    """

    override = (environ.get(TOOLS_URL_ENV) or "").strip()
    if override:
        return override
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise SnapshotError(f"URL PostgreSQL invalide : {exc}") from exc
    if not parsed.drivername.startswith("postgresql"):
        raise SnapshotError(
            f"URL PostgreSQL attendue, reçu le dialecte « {parsed.drivername} »"
        )
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


# --- Commandes externes ---------------------------------------------------------


def tool_command(
    env_name: str,
    default: Sequence[str],
    environ: Mapping[str, str] = os.environ,
) -> list[str]:
    """Commande d'outil : la valeur par défaut, ou un argv JSON d'environnement.

    La surcharge est un tableau JSON de chaînes (jamais une ligne de shell : rien
    n'est interprété, aucun caractère n'est à échapper) qui doit contenir le jeton
    ``{url}``, faute de quoi l'outil ne saurait pas quelle base viser.
    """

    raw = (environ.get(env_name) or "").strip()
    if not raw:
        return list(default)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SnapshotError(
            f"{env_name} invalide : un tableau JSON de chaînes est attendu ({exc})"
        ) from exc
    if (
        not isinstance(parsed, list)
        or not parsed
        or not all(isinstance(item, str) and item for item in parsed)
    ):
        raise SnapshotError(
            f"{env_name} invalide : un tableau JSON non vide de chaînes non vides "
            "est attendu"
        )
    if not any(URL_TOKEN in item for item in parsed):
        raise SnapshotError(
            f"{env_name} invalide : la commande doit contenir le jeton {URL_TOKEN}"
        )
    return list(parsed)


def render_command(argv: Sequence[str], url: str) -> list[str]:
    """Substitue le jeton ``{url}`` dans chaque argument de la commande."""

    return [item.replace(URL_TOKEN, url) for item in argv]


def _tool_missing(argv: Sequence[str], env_name: str, example: str) -> SnapshotToolMissing:
    return SnapshotToolMissing(
        f"Commande « {argv[0]} » introuvable sur ce poste. Installez les outils "
        f"client PostgreSQL ou exécutez-les dans le conteneur en posant "
        f"{env_name}='{example}'"
    )


def _run_tool(
    argv: Sequence[str],
    *,
    env_name: str,
    example: str,
    secrets: Sequence[str | None],
    stdin=None,
    stdout=None,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            list(argv),
            stdin=stdin,
            stdout=stdout if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise _tool_missing(argv, env_name, example) from exc
    except OSError as exc:
        raise SnapshotError(
            f"Commande « {argv[0]} » impossible à lancer : "
            f"{_scrub(str(exc), secrets)}"
        ) from exc


def _output_tail(process: subprocess.CompletedProcess, secrets: Sequence[str | None]) -> str:
    parts = []
    for stream in (process.stdout, process.stderr):
        if isinstance(stream, bytes) and stream:
            parts.append(stream.decode("utf-8", errors="replace"))
    tail = "\n".join(parts).strip()[-_OUTPUT_TAIL_CHARS:]
    return _scrub(tail, secrets) or "aucune sortie"


# --- SQLite -----------------------------------------------------------------------


def _quick_check(path: Path) -> None:
    """Refuse toute copie ou source que SQLite lui-même ne juge pas saine."""

    try:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, isolation_level=None
        )
    except sqlite3.Error as exc:
        raise SnapshotError(f"Fichier SQLite illisible « {path.name} » : {exc}") from exc
    try:
        verdict = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise SnapshotError(f"Fichier SQLite invalide « {path.name} » : {exc}") from exc
    finally:
        connection.close()
    if not verdict or verdict[0] != "ok":
        raise SnapshotError(
            f"Fichier SQLite corrompu « {path.name} » : quick_check renvoie "
            f"{verdict[0] if verdict else 'rien'}"
        )


def _require_sqlite_header(path: Path) -> None:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(SQLITE_HEADER))
    except OSError as exc:
        raise SnapshotError(f"Fichier « {path.name} » illisible : {exc}") from exc
    if header != SQLITE_HEADER:
        raise SnapshotError(
            f"Fichier « {path.name} » : ce n'est pas une base SQLite (en-tête absent)"
        )


def dump_sqlite(url: str, destination: Path) -> Path:
    """Copie cohérente de la base SQLite de ``url`` dans ``destination``.

    La copie est produite par ``VACUUM INTO`` sur une connexion ``sqlite3`` dédiée
    : elle est compacte, ne contient aucune transaction en cours et reste
    cohérente même si l'API écrit pendant la sauvegarde (une transaction non
    validée à l'ouverture de la lecture n'y figure pas). Elle est écrite dans un
    fichier temporaire du même répertoire, contrôlée par ``quick_check`` puis
    renommée atomiquement : un lecteur ne voit jamais une copie partielle.

    Ce module n'arrête ni ne libère le moteur global de l'application : il ouvre sa
    propre connexion et la referme. C'est à l'exploitant d'arrêter l'API s'il veut
    figer aussi les fichiers de livrables au même instant que la base.
    """

    source = sqlite_database_path(url)
    if not source.is_file():
        raise SnapshotError(f"Base SQLite introuvable : {source}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        connection = sqlite3.connect(str(source), timeout=30, isolation_level=None)
    except sqlite3.Error as exc:
        raise SnapshotError(f"Base SQLite inaccessible : {exc}") from exc
    try:
        connection.execute("VACUUM INTO ?", (str(temporary),))
    except sqlite3.Error as exc:
        temporary.unlink(missing_ok=True)
        raise SnapshotError(f"VACUUM INTO a échoué : {exc}") from exc
    finally:
        connection.close()
    try:
        _quick_check(temporary)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def restore_sqlite(source: Path, url: str) -> Path:
    """Remplace atomiquement la base SQLite de ``url`` par la copie ``source``.

    La copie est d'abord contrôlée (en-tête et ``quick_check``), recopiée dans un
    fichier temporaire du répertoire cible, puis ``os.replace`` la met en place :
    la base est soit l'ancienne, soit la nouvelle, jamais un mélange. Les fichiers
    annexes de l'ancienne base (``-wal``, ``-shm``, ``-journal``) sont retirés
    avant, car SQLite les appliquerait au nouveau fichier.

    Sous Windows, un fichier ouvert par l'API ne peut pas être remplacé : le refus
    demande d'arrêter le service plutôt que d'échouer à moitié.
    """

    source = Path(source)
    if not source.is_file():
        raise SnapshotError(f"Instantané SQLite introuvable : {source}")
    _require_sqlite_header(source)
    _quick_check(source)
    target = sqlite_database_path(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.restore-{os.getpid()}")
    try:
        shutil.copyfile(source, temporary)
        for suffix in SQLITE_SIDECAR_SUFFIXES:
            Path(str(target) + suffix).unlink(missing_ok=True)
        os.replace(temporary, target)
    except PermissionError as exc:
        temporary.unlink(missing_ok=True)
        raise SnapshotError(
            f"Remplacement de {target.name} refusé par le système : le fichier est "
            "probablement ouvert par l'API. Arrêtez le service avant de restaurer"
        ) from exc
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise SnapshotError(f"Remplacement de {target.name} impossible : {exc}") from exc
    return target


# --- PostgreSQL -------------------------------------------------------------------


def dump_postgresql(
    url: str, destination: Path, environ: Mapping[str, str] = os.environ
) -> Path:
    """Instantané ``pg_dump --format=custom`` de ``url`` dans ``destination``.

    La sortie standard de la commande est capturée dans un fichier temporaire du
    répertoire cible, puis renommée atomiquement après contrôle de l'en-tête du
    format ``custom`` : un fichier vide ou un texte d'erreur ne passe jamais pour
    une sauvegarde. Un binaire absent est un refus explicite qui cite la commande
    Docker équivalente.
    """

    libpq_url = tool_url(url, environ)
    argv = render_command(
        tool_command(PG_DUMP_COMMAND_ENV, DEFAULT_PG_DUMP_COMMAND, environ), libpq_url
    )
    secrets = (_password_of(url), _password_of(libpq_url))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            process = _run_tool(
                argv,
                env_name=PG_DUMP_COMMAND_ENV,
                example=DOCKER_PG_DUMP_EXAMPLE,
                secrets=secrets,
                stdout=handle,
            )
        if process.returncode != 0:
            raise SnapshotError(
                f"pg_dump a échoué (code {process.returncode}) sur "
                f"{redacted_url(url)} : {_output_tail(process, secrets)}"
            )
        with temporary.open("rb") as handle:
            header = handle.read(len(PG_CUSTOM_HEADER))
        if header != PG_CUSTOM_HEADER:
            raise SnapshotError(
                "pg_dump n'a pas produit un fichier au format custom (en-tête PGDMP "
                "absent) : vérifiez la commande configurée"
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_postgresql(
    source: Path, url: str, environ: Mapping[str, str] = os.environ
) -> None:
    """Rejoue l'instantané ``source`` dans la base ``url`` par ``pg_restore``.

    ``--single-transaction --exit-on-error`` : la restauration est tout ou rien,
    une base cible qui n'était pas vide ou un dump altéré laissent la base telle
    quelle. Le fichier est fourni sur l'entrée standard pour qu'un ``docker exec
    -i`` le transmette au conteneur.
    """

    source = Path(source)
    if not source.is_file():
        raise SnapshotError(f"Instantané PostgreSQL introuvable : {source}")
    with source.open("rb") as handle:
        header = handle.read(len(PG_CUSTOM_HEADER))
    if header != PG_CUSTOM_HEADER:
        raise SnapshotError(
            f"Fichier « {source.name} » : ce n'est pas un instantané pg_dump au "
            "format custom"
        )
    libpq_url = tool_url(url, environ)
    argv = render_command(
        tool_command(PG_RESTORE_COMMAND_ENV, DEFAULT_PG_RESTORE_COMMAND, environ),
        libpq_url,
    )
    secrets = (_password_of(url), _password_of(libpq_url))
    with source.open("rb") as handle:
        process = _run_tool(
            argv,
            env_name=PG_RESTORE_COMMAND_ENV,
            example=DOCKER_PG_RESTORE_EXAMPLE,
            secrets=secrets,
            stdin=handle,
        )
    if process.returncode != 0:
        raise SnapshotError(
            f"pg_restore a échoué (code {process.returncode}) sur "
            f"{redacted_url(url)} : {_output_tail(process, secrets)}"
        )


def schema_wipe_postgresql(url: str) -> None:
    """Vide le schéma ``public`` de ``url`` (``DROP SCHEMA … CASCADE`` puis recréation).

    Destructif et réservé à une restauration explicitement demandée avec
    remplacement ; passe par SQLAlchemy sur un moteur de maintenance, jamais par
    un binaire ``psql`` que le poste peut ne pas avoir.
    """

    engine = make_engine(url, maintenance=True)
    try:
        if engine.dialect.name != "postgresql":
            raise SnapshotError(
                f"schema_wipe_postgresql exige une URL PostgreSQL, reçu "
                f"« {engine.dialect.name} »"
            )
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()
