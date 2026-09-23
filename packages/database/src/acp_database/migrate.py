"""Migration du schéma : API Python et commande ``python -m acp_database.migrate``.

Codes de sortie de la commande :

- ``0`` succès ;
- ``1`` échec d'exécution (base injoignable, révision inconnue, erreur SQL) ;
- ``2`` erreur d'usage (option manquante ou invalide, URL absente) ;
- ``3`` refus explicite (verrou occupé, base hors version, dérive du schéma,
  pilote interdit, opération de migration sur SQLite).

Sous SQLite, ``upgrade`` et ``downgrade`` sont refusés : SQLite est migré par
``init_db()`` ; Alembic n'y fait qu'estampiller. Sous PostgreSQL, toute écriture
de la table de version se fait sous le verrou consultatif de session
``acp_database.migrate`` et sur un moteur en mode maintenance.
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
from contextlib import nullcontext
from typing import Callable, Sequence, TextIO

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.exc import SQLAlchemyError

from .engine import make_engine
from .locking import LockUnavailableError, advisory_session_lock
from .models import Base
from .schema_state import (
    VERSION_TABLE,
    SchemaOutOfDateError,
    SchemaState,
    alembic_config,
    autogenerate_options,
    check_schema_current,
    head_revision,
    script_directory,
)

MIGRATION_LOCK_KEY = "acp_database.migrate"
DEFAULT_LOCK_TIMEOUT_SECONDS = 60.0
SQLITE_REFUSAL = (
    "SQLite est migré par init_db() ; Alembic n'y fait qu'estampiller "
    "(commandes current, check, history et stamp seulement)."
)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


class _UsageError(Exception):
    """Erreur d'usage de la ligne de commande (code 2)."""


class _Refusal(RuntimeError):
    """Refus explicite (code 3)."""


def _with_migration_lock(
    engine, action: Callable[[object], None], *, lock_timeout_seconds: float
) -> None:
    """Exécute une commande Alembic sur une connexion verrouillée du moteur.

    La connexion est transmise à ``env.py`` via ``config.attributes`` : Alembic
    ouvre alors une transaction par révision sur cette connexion, sans jamais
    construire de moteur de son côté. Sous SQLite le verrou est un no-op.
    """

    config = alembic_config()
    with engine.connect() as connection:
        with advisory_session_lock(
            connection, MIGRATION_LOCK_KEY, timeout_seconds=lock_timeout_seconds
        ):
            config.attributes["connection"] = connection
            action(config)
            if connection.in_transaction():
                connection.commit()


def run_upgrade(
    engine,
    revision: str = "head",
    *,
    lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> None:
    """Applique les révisions jusqu'à ``revision`` (tête par défaut).

    Idempotent : une base déjà à la révision demandée ne reçoit aucun DDL. Sous
    PostgreSQL une seconde migration simultanée est refusée par le verrou de
    session (:class:`~acp_database.locking.LockUnavailableError`) plutôt que
    mise en file : deux processus qui appliqueraient la même révision liraient
    la même table de version et écriraient le même DDL.
    """

    def upgrade(config):
        state = check_schema_current(engine, connection=config.attributes["connection"])
        if state.unknown_revision:
            raise _Refusal(str(SchemaOutOfDateError(state)))
        command.upgrade(config, revision)

    _with_migration_lock(engine, upgrade, lock_timeout_seconds=lock_timeout_seconds)


def run_downgrade(
    engine,
    revision: str,
    *,
    lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> None:
    """Redescend le schéma jusqu'à ``revision`` (``base`` pour tout retirer).

    Destructif par nature : l'API Python n'ajoute aucune confirmation, celle-ci
    appartient à la ligne de commande (``--yes-i-understand-data-loss``).
    """

    _with_migration_lock(
        engine,
        lambda config: command.downgrade(config, revision),
        lock_timeout_seconds=lock_timeout_seconds,
    )


def run_stamp(
    engine,
    revision: str,
    *,
    lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    allow_unverified_revision: bool = False,
) -> None:
    """Estampille une base conforme ; une adoption intermédiaire exige un accord explicite."""

    def stamp(config):
        if engine.dialect.name == "postgresql":
            targets = script_directory().get_revisions(revision)
            if head_revision() not in {target.revision for target in targets}:
                if not allow_unverified_revision:
                    raise _Refusal(
                        "estampillage intermédiaire refusé : exige --allow-unverified-revision "
                        "après vérification manuelle du schéma de cette révision"
                    )
            else:
                drift = check_drift(engine, connection=config.attributes["connection"])
                if drift:
                    raise _Refusal("estampillage refusé : schéma différent du modèle : " + "; ".join(drift))
        command.stamp(config, revision)

    _with_migration_lock(engine, stamp, lock_timeout_seconds=lock_timeout_seconds)


def current_revision(engine) -> str | None:
    """Révision estampillée, ou ``None`` si la base n'a pas de table de version."""

    return check_schema_current(engine).current


def _describe_diff(diff) -> str:
    """Rend lisible une entrée de ``compare_metadata``.

    Les entrées ``modify_*`` arrivent groupées dans une liste par colonne ; les
    autres sont des tuples dont le premier élément nomme l'opération que la base
    devrait subir pour rejoindre le modèle.
    """

    if isinstance(diff, list):
        return " ; ".join(_describe_diff(item) for item in diff)
    kind = diff[0]
    action = "à créer" if kind.startswith("add_") else "à supprimer"
    if kind in ("add_table", "remove_table"):
        return f"table {diff[1].name} {action}"
    if kind in ("add_column", "remove_column"):
        return f"colonne {diff[2]}.{diff[3].name} {action}"
    if kind in ("add_index", "remove_index"):
        index = diff[1]
        return f"index {index.name} sur {index.table.name} {action}"
    if kind in ("add_constraint", "remove_constraint", "add_fk", "remove_fk"):
        constraint = diff[1]
        return (
            f"contrainte {constraint.name or '<sans nom>'} sur "
            f"{constraint.table.name} {action}"
        )
    if kind.startswith("modify_"):
        _schema, table, column, _info, old, new = diff[1:7]
        return (
            f"colonne {table}.{column} : {kind.removeprefix('modify_')} "
            f"en base {old!r}, attendu {new!r}"
        )
    return repr(diff)


def _predicate_structure(expression):
    """Compare AND/OR avec leur groupement ; conserve les atomes SQL et leurs littéraux.

    Les prédicats du modèle n'utilisent que IS NULL/NOT NULL, AND et OR.
    Toute autre expression demeure textuelle : aucun effacement de parenthèses
    susceptible de rendre deux expressions différentes artificiellement égales.
    """
    import re
    tokens = re.findall(r"'(?:''|[^'])*'|[A-Za-z_][A-Za-z_0-9]*|[^\s]", str(expression) if expression is not None else "")
    tokens = [token if token.startswith("'") else token.lower() for token in tokens]

    def parse(items):
        while items and items[0] == "(" and items[-1] == ")":
            depth = 0
            for i, token in enumerate(items):
                depth += (token == "(") - (token == ")")
                if depth == 0:
                    break
            if i != len(items) - 1:
                break
            items = items[1:-1]
        for operator in ("or", "and"):
            depth, start, parts = 0, 0, []
            for i, token in enumerate(items):
                depth += (token == "(") - (token == ")")
                if depth == 0 and token == operator:
                    parts.append(parse(items[start:i]))
                    start = i + 1
            if parts:
                parts.append(parse(items[start:]))
                return (operator, tuple(parts))
        return tuple(items)
    return parse(tokens)


def check_drift(engine, *, connection=None) -> list[str]:
    """Écarts entre la base et ``Base.metadata``, rendus en français.

    Une liste vide signifie que les contrôles effectués ne trouvent pas de dérive :
    types, valeurs par défaut, index et prédicats, noms des CHECK. Les expressions
    SQL des CHECK ne sont pas comparées ; cette limite est affichée par la CLI.
    """

    with (nullcontext(connection) if connection is not None else engine.connect()) as connection:
        context = MigrationContext.configure(
            connection,
            opts={"version_table": VERSION_TABLE, **autogenerate_options()},
        )
        diffs = compare_metadata(context, Base.metadata)
        inspector = inspect(connection)
        extra = []
        tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            expected_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
            actual_checks = {c["name"] for c in inspector.get_check_constraints(table.name)}
            for name in sorted(expected_checks - actual_checks):
                extra.append(f"contrainte CHECK {name} sur {table.name} absente")
            for name in sorted(actual_checks - expected_checks, key=str):
                extra.append(f"contrainte CHECK {name} sur {table.name} inattendue")
            actual_indexes = {i["name"]: i for i in inspector.get_indexes(table.name)}
            dialect = connection.dialect.name
            for index in table.indexes:
                actual = actual_indexes.get(index.name)
                if actual is None:
                    continue
                expected_where = index.dialect_options[dialect].get("where")
                actual_where = actual.get("dialect_options", {}).get(f"{dialect}_where")
                if _predicate_structure(expected_where) != _predicate_structure(actual_where):
                    extra.append(f"prédicat de l'index {index.name} sur {table.name} différent")
    return [_describe_diff(diff) for diff in diffs] + extra


class _Parser(argparse.ArgumentParser):
    """Analyseur dont les erreurs d'usage sont capturées plutôt que fatales."""

    def __init__(self, *args, stdout: TextIO, stderr: TextIO, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stdout = stdout
        self._stderr = stderr

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)

    def _print_message(self, message: str, file=None) -> None:  # type: ignore[override]
        if message:
            (self._stderr if file is sys.stderr else self._stdout).write(message)


def _build_parser(stdout: TextIO, stderr: TextIO) -> _Parser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--database-url",
        dest="database_url",
        default=None,
        help="URL SQLAlchemy de la base (sinon ACP_DATABASE_URL)",
    )
    common.add_argument(
        "--lock-timeout-seconds",
        dest="lock_timeout_seconds",
        type=float,
        default=DEFAULT_LOCK_TIMEOUT_SECONDS,
        help="attente maximale du verrou de migration PostgreSQL (défaut : 60)",
    )
    parser = _Parser(
        prog="python -m acp_database.migrate",
        description="Migration versionnée du schéma acp_database.",
        stdout=stdout,
        stderr=stderr,
    )
    commands = parser.add_subparsers(
        dest="command",
        metavar="commande",
        parser_class=functools.partial(_Parser, stdout=stdout, stderr=stderr),
    )
    commands.required = True

    upgrade = commands.add_parser(
        "upgrade", parents=[common], help="applique les révisions manquantes"
    )
    upgrade.add_argument("--to", dest="revision", default="head")

    downgrade = commands.add_parser(
        "downgrade", parents=[common], help="redescend vers une révision"
    )
    downgrade.add_argument("--to", dest="revision", required=True)
    downgrade.add_argument(
        "--yes-i-understand-data-loss",
        dest="acknowledged",
        action="store_true",
        help="obligatoire : un downgrade détruit des tables et leurs données",
    )

    commands.add_parser("current", parents=[common], help="révision estampillée")
    commands.add_parser(
        "check", parents=[common], help="vérifie version et dérive du schéma"
    )
    commands.add_parser("history", parents=[common], help="liste les révisions")
    stamp = commands.add_parser(
        "stamp", parents=[common], help="estampille une révision sans DDL"
    )
    stamp.add_argument("revision")
    stamp.add_argument(
        "--allow-unverified-revision", action="store_true",
        help="adoption intermédiaire après vérification manuelle (ne contourne pas le contrôle de la tête)",
    )
    return parser


def _resolve_url(namespace) -> str:
    url = namespace.database_url or os.environ.get("ACP_DATABASE_URL", "")
    if not url:
        raise _UsageError(
            "aucune URL de base : passez --database-url ou renseignez "
            "ACP_DATABASE_URL"
        )
    return url


def _print_history(script: ScriptDirectory, stdout: TextIO) -> None:
    for revision in script.walk_revisions():
        previous = revision.down_revision or "<base>"
        summary = (revision.doc or "").strip().splitlines()[0:1]
        stdout.write(
            f"{revision.revision} <- {previous} : {summary[0] if summary else ''}\n"
        )


def _run(namespace, stdout: TextIO, stderr: TextIO) -> int:
    url = _resolve_url(namespace)
    if namespace.command == "history":
        _print_history(script_directory(), stdout)
        return EXIT_OK
    if namespace.command == "downgrade" and not namespace.acknowledged:
        raise _UsageError(
            "downgrade exige --yes-i-understand-data-loss : des tables et leurs "
            "données seront détruites"
        )
    try:
        engine = make_engine(url, maintenance=True)
    except RuntimeError as exc:
        raise _Refusal(str(exc)) from exc
    try:
        is_sqlite = engine.dialect.name == "sqlite"
        if namespace.command in ("upgrade", "downgrade") and is_sqlite:
            raise _Refusal(SQLITE_REFUSAL)
        timeout = namespace.lock_timeout_seconds
        if namespace.command == "current":
            state = check_schema_current(engine)
            stdout.write(_format_current(state) + "\n")
            return EXIT_OK
        if namespace.command == "check":
            state = check_schema_current(engine)
            if not state.ok:
                raise _Refusal(str(SchemaOutOfDateError(state)))
            drift = check_drift(engine)
            if drift:
                raise _Refusal(
                    "dérive du schéma face au modèle :\n  - " + "\n  - ".join(drift)
                )
            stdout.write(f"Schéma à jour ({state.head}) et conforme aux contrôles effectués.\n")
            stdout.write("Limite : les noms des CHECK sont comparés, pas leur expression SQL.\n")
            return EXIT_OK
        if namespace.command == "upgrade":
            before = check_schema_current(engine)
            run_upgrade(engine, namespace.revision, lock_timeout_seconds=timeout)
            after = check_schema_current(engine)
            if before.current == after.current:
                stdout.write(f"Schéma déjà à jour ({after.current}) : aucun DDL émis.\n")
            else:
                stdout.write(
                    f"Schéma migré de {before.current or 'aucune'} vers "
                    f"{after.current}.\n"
                )
            return EXIT_OK
        if namespace.command == "downgrade":
            run_downgrade(engine, namespace.revision, lock_timeout_seconds=timeout)
            after = check_schema_current(engine)
            stdout.write(
                f"Schéma redescendu vers {after.current or 'aucune (base vide)'}.\n"
            )
            return EXIT_OK
        if namespace.command == "stamp":
            run_stamp(engine, namespace.revision, lock_timeout_seconds=timeout,
                      allow_unverified_revision=namespace.allow_unverified_revision)
            after = check_schema_current(engine)
            stdout.write(f"Base estampillée à {after.current or 'aucune'}.\n")
            return EXIT_OK
        raise _UsageError(f"commande inconnue : {namespace.command}")
    finally:
        engine.dispose()


def _format_current(state: SchemaState) -> str:
    current = state.current or "aucune (table alembic_version absente)"
    verdict = "à jour" if state.ok else "hors version"
    return f"Révision courante : {current} ; tête attendue : {state.head} ({verdict})"


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Point d'entrée de la commande ; retourne le code de sortie sans quitter."""

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = _build_parser(out, err)
    try:
        namespace = parser.parse_args(list(argv) if argv is not None else None)
    except _UsageError as exc:
        err.write(f"Usage incorrect : {exc}\n")
        return EXIT_USAGE
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    try:
        return _run(namespace, out, err)
    except _UsageError as exc:
        err.write(f"Usage incorrect : {exc}\n")
        return EXIT_USAGE
    except LockUnavailableError as exc:
        err.write(f"Refus : {exc}\n")
        return EXIT_REFUSED
    except _Refusal as exc:
        err.write(f"Refus : {exc}\n")
        return EXIT_REFUSED
    except (SQLAlchemyError, CommandError, RuntimeError) as exc:
        err.write(f"Échec : {exc}\n")
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
