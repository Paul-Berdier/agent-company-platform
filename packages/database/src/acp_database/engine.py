import hashlib
import json
import os
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import (
    CheckConstraint,
    MetaData,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from .models import Base

DEFAULT_URL = "sqlite:///./acp.db"


@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("ACP_DATABASE_URL", DEFAULT_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()
    return engine


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def _sqlite_migration_connection(engine):
    """Isole une reconstruction SQLite sans laisser les FK désactivées.

    SQLite exige de couper temporairement leur application pour remplacer une
    table parente déjà référencée. La coupure est locale à cette connexion ; le
    ``foreign_key_check`` de l'appelant reste disponible avant le commit, puis le
    ``finally`` restaure l'application même si le préflight ou le DDL échoue.
    """

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
            connection.commit()
            if enabled != 1:
                raise RuntimeError(
                    "Migration SQLite interrompue : impossible de réactiver "
                    "les clés étrangères"
                )


def init_db() -> None:
    """Crée les tables manquantes (MVP ; une migration Alembic viendra ensuite)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _upgrade_sqlite_schema(engine)


def _backfill_mission_command_principals(connection) -> None:
    """Attribue les anciennes commandes seulement quand l'auteur est certain.

    Une commande sans auteur de mission, ou deux anciennes commandes qui se
    retrouveraient sous la même clé principal/commande, nécessitent une décision
    opérateur. Le démarrage est alors refusé plutôt que de rendre la déduplication
    ambiguë ou de rejouer un effet.
    """

    rows = connection.execute(
        text(
            "SELECT mc.id, mc.command, mc.idempotency_key, mc.principal_id, "
            "t.created_by_user_id "
            "FROM mission_commands AS mc "
            "LEFT JOIN tasks AS t ON t.id = mc.task_id"
        )
    ).mappings().all()
    groups: dict[tuple[str, str, str], list[dict]] = {}
    unattributed = []
    for row in rows:
        effective_principal = row["principal_id"] or row["created_by_user_id"]
        if effective_principal is None:
            if row["principal_id"] is None:
                unattributed.append(row["id"])
            continue
        groups.setdefault(
            (effective_principal, row["command"], row["idempotency_key"]), []
        ).append(row)
    ambiguous = [
        grouped
        for grouped in groups.values()
        if len(grouped) > 1 and any(row["principal_id"] is None for row in grouped)
    ]
    if unattributed or ambiguous:
        raise RuntimeError(
            "Migration mission_commands refusée: "
            f"{len(unattributed)} commande(s) sans principal et "
            f"{len(ambiguous)} groupe(s) de clés ambigu(s)"
        )
    for grouped in groups.values():
        row = grouped[0]
        if row["principal_id"] is None:
            connection.execute(
                text(
                    "UPDATE mission_commands SET principal_id = :principal_id "
                    "WHERE id = :command_id AND principal_id IS NULL"
                ),
                {
                    "principal_id": row["created_by_user_id"],
                    "command_id": row["id"],
                },
            )


def _replace_task_scoped_mission_command_constraint(connection) -> None:
    """Retire l'ancienne unicité par mission, non supprimable via ALTER SQLite."""

    constraints = inspect(connection).get_unique_constraints("mission_commands")
    legacy_columns = ("task_id", "command", "idempotency_key")
    if not any(
        tuple(constraint.get("column_names") or ()) == legacy_columns
        for constraint in constraints
    ):
        return
    replacement = "mission_commands_principal_scope_v2"
    if inspect(connection).has_table(replacement):
        raise RuntimeError(
            "Migration mission_commands refusée: table temporaire déjà présente"
        )
    connection.execute(
        text(
            f"CREATE TABLE {replacement} ("
            "task_id VARCHAR(36) NOT NULL, "
            "command VARCHAR(50) NOT NULL, "
            "idempotency_key VARCHAR(200) NOT NULL, "
            "principal_id VARCHAR(36), "
            "request_fingerprint VARCHAR(64) NOT NULL DEFAULT '', "
            "task_run_id VARCHAR(36), "
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "created_at DATETIME NOT NULL, "
            "FOREIGN KEY(task_id) REFERENCES tasks (id), "
            "FOREIGN KEY(principal_id) REFERENCES users (id), "
            "FOREIGN KEY(task_run_id) REFERENCES task_runs (id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {replacement} ("
            "task_id, command, idempotency_key, principal_id, "
            "request_fingerprint, task_run_id, id, created_at"
            ") SELECT task_id, command, idempotency_key, principal_id, "
            "request_fingerprint, task_run_id, id, created_at "
            "FROM mission_commands"
        )
    )
    connection.execute(text("DROP TABLE mission_commands"))
    connection.execute(
        text(f"ALTER TABLE {replacement} RENAME TO mission_commands")
    )


def _mission_comment_fingerprint(*, body: str, run_id: str | None) -> str:
    canonical = json.dumps(
        {"body": body, "run_id": run_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _backfill_mission_comment_fingerprints(connection) -> None:
    """Backfill only comments whose idempotency scope is unambiguous.

    A legacy keyed comment without an attempt cannot safely be attached to a
    principal/run scope: choosing the latest run could turn a delayed retry into
    a new effect.  Such a database therefore requires operator intervention.
    """

    rows = connection.execute(
        text(
            "SELECT c.id, c.task_id, c.task_run_id, c.author_user_id, c.body, "
            "c.idempotency_key, c.request_fingerprint, "
            "r.task_id AS run_task_id "
            "FROM mission_comments AS c "
            "LEFT JOIN task_runs AS r ON r.id = c.task_run_id"
        )
    ).mappings().all()
    invalid = []
    scopes: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        key = row["idempotency_key"]
        if key is not None:
            if (
                row["author_user_id"] is None
                or row["task_run_id"] is None
                or row["run_task_id"] != row["task_id"]
            ):
                invalid.append(row["id"])
                continue
            scopes.setdefault(
                (row["author_user_id"], row["task_run_id"], key), []
            ).append(row["id"])
        expected = _mission_comment_fingerprint(
            body=row["body"], run_id=row["task_run_id"]
        )
        stored = row["request_fingerprint"] or ""
        if stored and stored != expected:
            invalid.append(row["id"])
            continue
        if not stored:
            connection.execute(
                text(
                    "UPDATE mission_comments SET request_fingerprint = :fingerprint "
                    "WHERE id = :comment_id"
                ),
                {"fingerprint": expected, "comment_id": row["id"]},
            )
    ambiguous = [ids for ids in scopes.values() if len(ids) > 1]
    if invalid or ambiguous:
        raise RuntimeError(
            "Migration mission_comments refusée: "
            f"{len(invalid)} commentaire(s) sans portée fiable et "
            f"{len(ambiguous)} groupe(s) de clés ambigu(s)"
        )


def _replace_task_scoped_mission_comment_constraint(connection) -> None:
    """Remplace l'ancienne clé mission/key par la portée principal/run/key."""

    constraints = inspect(connection).get_unique_constraints("mission_comments")
    legacy_columns = ("task_id", "idempotency_key")
    if not any(
        tuple(constraint.get("column_names") or ()) == legacy_columns
        for constraint in constraints
    ):
        return
    replacement = "mission_comments_principal_run_scope_v2"
    if inspect(connection).has_table(replacement):
        raise RuntimeError(
            "Migration mission_comments refusée: table temporaire déjà présente"
        )
    connection.execute(
        text(
            f"CREATE TABLE {replacement} ("
            "task_id VARCHAR(36) NOT NULL, "
            "task_run_id VARCHAR(36), "
            "author_user_id VARCHAR(36) NOT NULL, "
            "body TEXT NOT NULL, "
            "idempotency_key VARCHAR(200), "
            "request_fingerprint VARCHAR(64) NOT NULL DEFAULT '', "
            "id VARCHAR(36) NOT NULL PRIMARY KEY, "
            "created_at DATETIME NOT NULL, "
            "CONSTRAINT uq_mission_comment_principal_run_key UNIQUE "
            "(author_user_id, task_run_id, idempotency_key), "
            "CONSTRAINT ck_mission_comment_key_requires_run CHECK "
            "(idempotency_key IS NULL OR task_run_id IS NOT NULL), "
            "FOREIGN KEY(task_id) REFERENCES tasks (id), "
            "FOREIGN KEY(task_run_id) REFERENCES task_runs (id), "
            "FOREIGN KEY(author_user_id) REFERENCES users (id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {replacement} ("
            "task_id, task_run_id, author_user_id, body, idempotency_key, "
            "request_fingerprint, id, created_at"
            ") SELECT task_id, task_run_id, author_user_id, body, "
            "idempotency_key, request_fingerprint, id, created_at "
            "FROM mission_comments"
        )
    )
    connection.execute(text("DROP TABLE mission_comments"))
    connection.execute(
        text(f"ALTER TABLE {replacement} RENAME TO mission_comments")
    )


def _backfill_event_journal_sequence(connection) -> None:
    """Numérote les lignes d'événements antérieures au compteur de journal.

    Sous SQLite le ``rowid`` est unique et croît dans l'ordre d'insertion : il donne
    donc exactement l'ordre d'écriture recherché, là où ``created_at`` ne le donne
    pas (granularité d'horloge d'environ 1,5 ms sous Windows, donc égalités
    courantes).

    Le décalage par le maximum déjà attribué garantit l'idempotence dans le seul cas
    délicat : une base **partiellement** numérotée, où un ``rowid`` nu pourrait
    heurter un numéro déjà pris. Sur une base jamais migrée ce maximum vaut zéro et
    la numérotation est exactement le ``rowid``. Il est lu puis passé en paramètre
    plutôt qu'écrit en sous-requête : la valeur doit être figée **avant** la mise à
    jour de la table qu'elle interroge.
    """

    pending = connection.execute(
        text("SELECT COUNT(*) FROM events WHERE journal_seq IS NULL")
    ).scalar()
    if not pending:
        return
    offset = (
        connection.execute(text("SELECT MAX(journal_seq) FROM events")).scalar() or 0
    )
    connection.execute(
        text(
            "UPDATE events SET journal_seq = rowid + :offset WHERE journal_seq IS NULL"
        ),
        {"offset": int(offset)},
    )


def _ensure_unique_index(
    connection, *, table: str, columns: tuple[str, ...], name: str
) -> None:
    """Repose une unicité absente d'une table déjà créée sans elle.

    ``create_all`` ne complète jamais une table existante : une base où la table
    aurait été créée sans sa contrainte perdrait la garantie **silencieusement**.
    Un index unique donne exactement la même garantie et se crée, lui, de façon
    additive. La création est omise si l'unicité est déjà déclarée, afin de ne pas
    doubler l'index automatique posé par ``create_all``.
    """

    inspector = inspect(connection)
    declared = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table)
    }
    declared |= {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(table)
        if index.get("unique")
    }
    if columns in declared:
        return
    column_list = ", ".join(f'"{column}"' for column in columns)
    connection.execute(
        text(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({column_list})')
    )


_AUTOMATIONS_CHECK_EXPRESSIONS = {
    "ck_automations_create_idempotency_complete": (
        "(create_idempotency_key IS NULL AND create_request_fingerprint IS NULL) "
        "OR (create_idempotency_key IS NOT NULL AND "
        "create_request_fingerprint IS NOT NULL AND created_by_user_id IS NOT NULL)"
    ),
    "ck_automations_consecutive_failures": "consecutive_failures >= 0",
    "ck_automations_failure_threshold": "failure_threshold >= 1",
    "ck_automations_webhook_rotation_number": "webhook_rotation_number >= 0",
    "ck_automations_mutation_revision": "mutation_revision >= 0",
}
_AUTOMATIONS_FOREIGN_KEYS = frozenset(
    {
        ("projects", ("project_id",), ("id",)),
        ("users", ("created_by_user_id",), ("id",)),
    }
)
_AUTOMATIONS_CREATE_KEY = (
    "project_id",
    "created_by_user_id",
    "create_idempotency_key",
)
_MANAGED_AUTOMATION_INDEXES = {
    "ix_automations_project_id": (("project_id",), False),
    "ix_automations_next_run_at": (("next_run_at",), False),
    "ix_automations_created_by_user_id": (("created_by_user_id",), False),
    "uq_automations_create_principal_key": (_AUTOMATIONS_CREATE_KEY, True),
}


def _normalized_sql_expression(value: str | None) -> str:
    return "".join((value or "").lower().split())


def _normalized_sqlite_default(value) -> str | None:
    """Normalise les littéraux ``DEFAULT`` renvoyés par l'inspecteur SQLite.

    SQLAlchemy rend par exemple le modèle ``server_default="0"`` sous la forme
    ``'0'`` dans ``PRAGMA table_info``. Les parenthèses extérieures sont également
    facultatives en SQLite. On retire uniquement ces différences syntaxiques : la
    casse et le contenu d'un littéral restent intacts, car ils changent la valeur
    réellement insérée.
    """

    if value is None:
        return None
    normalized = str(value).strip()
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        quote: str | None = None
        wraps_whole_expression = True
        index = 0
        while index < len(normalized):
            character = normalized[index]
            if quote is not None:
                if character == quote:
                    if (
                        index + 1 < len(normalized)
                        and normalized[index + 1] == quote
                    ):
                        index += 1
                    else:
                        quote = None
            elif character in {"'", '"'}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(normalized) - 1:
                    wraps_whole_expression = False
                    break
            index += 1
        if not wraps_whole_expression or depth != 0 or quote is not None:
            break
        normalized = normalized[1:-1].strip()
    if (
        len(normalized) >= 2
        and normalized.startswith("'")
        and normalized.endswith("'")
    ):
        normalized = normalized[1:-1].replace("''", "'")
    return normalized


def _automations_schema_has_constraints(connection) -> bool:
    """Vérifie la parité structurelle complète avec ``AutomationModel``.

    Le chemin spécial conserve les objets SQLite locaux et produit des erreurs de
    données explicites, mais sa définition de la parité reste celle du comparateur
    commun. En particulier, un index unique partiel ne satisfait jamais une
    unicité totale.
    """

    rebuild, unsupported = _lot_f_table_parity(connection, "automations")
    return not rebuild and not unsupported


def _unsupported_automation_constraints(connection) -> list[str]:
    """Détecte les contraintes locales qu'une reconstruction ferait disparaître."""

    inspector = inspect(connection)
    issues: list[str] = []
    for constraint in inspector.get_check_constraints("automations"):
        name = constraint.get("name")
        expected = _AUTOMATIONS_CHECK_EXPRESSIONS.get(name)
        if expected is None or _normalized_sql_expression(
            constraint.get("sqltext")
        ) != _normalized_sql_expression(expected):
            issues.append(f"CHECK {name or '<sans nom>'}")

    for foreign_key in inspector.get_foreign_keys("automations"):
        signature = (
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("constrained_columns") or ()),
            tuple(foreign_key.get("referred_columns") or ()),
        )
        if signature not in _AUTOMATIONS_FOREIGN_KEYS or foreign_key.get("options"):
            issues.append(f"FOREIGN KEY {signature}")

    for constraint in inspector.get_unique_constraints("automations"):
        columns = tuple(constraint.get("column_names") or ())
        if columns != _AUTOMATIONS_CREATE_KEY:
            issues.append(
                f"UNIQUE {constraint.get('name') or '<sans nom>'}{columns}"
            )
    for index in inspector.get_indexes("automations"):
        expected = _MANAGED_AUTOMATION_INDEXES.get(index.get("name"))
        if expected is None:
            continue
        actual = (
            tuple(index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        if actual != expected:
            issues.append(f"INDEX {index.get('name')}{actual}")
    return issues


def _automation_migration_issues(connection) -> list[str]:
    """Liste les données qu'une reconstruction contrainte ne peut pas copier."""

    predicates = (
        (
            "ligne(s) avec colonne obligatoire NULL",
            "id IS NULL OR created_at IS NULL OR project_id IS NULL OR "
            "name IS NULL OR description IS NULL OR schedule_kind IS NULL OR "
            "schedule_expression IS NULL OR timezone IS NULL OR "
            "mission_template IS NULL OR enabled IS NULL OR "
            "catchup_policy IS NULL OR max_concurrent_runs IS NULL OR "
            "webhook_enabled IS NULL OR webhook_rotation_number IS NULL OR "
            "consecutive_failures IS NULL OR failure_threshold IS NULL",
        ),
        (
            "ligne(s) avec commande de création incomplète",
            "NOT ((create_idempotency_key IS NULL AND "
            "create_request_fingerprint IS NULL) OR "
            "(create_idempotency_key IS NOT NULL AND "
            "create_request_fingerprint IS NOT NULL AND "
            "created_by_user_id IS NOT NULL))",
        ),
        (
            "ligne(s) avec compteur webhook négatif",
            "webhook_rotation_number < 0",
        ),
        (
            "ligne(s) avec compteur d'échecs négatif",
            "consecutive_failures < 0",
        ),
        (
            "ligne(s) avec seuil d'échec non positif",
            "failure_threshold < 1",
        ),
        (
            "ligne(s) avec projet orphelin",
            "NOT EXISTS (SELECT 1 FROM projects "
            "WHERE projects.id = automations.project_id)",
        ),
        (
            "ligne(s) avec créateur orphelin",
            "created_by_user_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM users WHERE users.id = automations.created_by_user_id)",
        ),
    )
    issues: list[str] = []
    for label, predicate in predicates:
        count = connection.execute(
            text(f"SELECT COUNT(*) FROM automations WHERE {predicate}")
        ).scalar_one()
        if count:
            issues.append(f"{count} {label}")
    duplicate_groups = connection.execute(
        text(
            "SELECT COUNT(*) FROM ("
            "SELECT 1 FROM automations "
            "WHERE create_idempotency_key IS NOT NULL "
            "GROUP BY project_id, created_by_user_id, create_idempotency_key "
            "HAVING COUNT(*) > 1)"
        )
    ).scalar_one()
    if duplicate_groups:
        issues.append(f"{duplicate_groups} groupe(s) de clé de création dupliquée")
    return issues


def _rebuild_automations_with_constraints(connection) -> None:
    """Reconstruit atomiquement une table Lot F additive mais non contrainte.

    SQLite ne sait ajouter ni CHECK ni FOREIGN KEY via ``ALTER TABLE``. Une copie
    vers le DDL généré depuis le modèle est donc la seule manière d'obtenir la
    même frontière qu'une base fraîche. Les colonnes ou données non copiables
    font refuser le démarrage avant le moindre ``DROP``.
    """

    if _automations_schema_has_constraints(connection):
        return

    source_table = Base.metadata.tables["automations"]
    expected_columns = tuple(column.name for column in source_table.columns)
    existing_columns = tuple(
        column["name"] for column in inspect(connection).get_columns("automations")
    )
    missing = sorted(set(expected_columns).difference(existing_columns))
    extra = sorted(set(existing_columns).difference(expected_columns))
    if missing or extra:
        raise RuntimeError(
            "Migration automations refusée : colonnes incompatibles "
            f"(manquantes={missing}, inconnues={extra})"
        )

    unsupported_constraints = _unsupported_automation_constraints(connection)
    if unsupported_constraints:
        raise RuntimeError(
            "Migration automations refusée : contraintes locales non "
            "reconstructibles ("
            + "; ".join(unsupported_constraints)
            + ")"
        )

    issues = _automation_migration_issues(connection)
    if issues:
        raise RuntimeError(
            "Migration automations refusée : données incompatibles ("
            + "; ".join(issues)
            + "). Corrigez ces lignes avant de redémarrer."
        )

    replacement_name = "automations_lot_f_constraints_v2"
    if inspect(connection).has_table(replacement_name):
        raise RuntimeError(
            "Migration automations refusée : table temporaire déjà présente"
        )

    preserved_objects = connection.execute(
        text(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = 'automations' "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        )
    ).mappings().all()
    preserved_sql = [
        row["sql"]
        for row in preserved_objects
        if row["type"] == "trigger" or row["name"] not in _MANAGED_AUTOMATION_INDEXES
    ]

    migration_metadata = MetaData()
    for dependency in ("projects", "users"):
        Base.metadata.tables[dependency].to_metadata(migration_metadata)
    replacement = source_table.to_metadata(
        migration_metadata,
        name=replacement_name,
    )
    connection.execute(CreateTable(replacement))
    quoted_columns = ", ".join(f'"{name}"' for name in expected_columns)
    connection.execute(
        text(
            f'INSERT INTO "{replacement_name}" ({quoted_columns}) '
            f'SELECT {quoted_columns} FROM "automations"'
        )
    )

    # Les enfants peuvent déjà référencer des routines. La connexion de migration
    # suspend leur application pendant le remplacement ; le ``foreign_key_check``
    # global exécuté avant commit prouve que chaque référence est redevenue valide.
    connection.execute(text('DROP TABLE "automations"'))
    connection.execute(
        text(f'ALTER TABLE "{replacement_name}" RENAME TO "automations"')
    )
    for index in sorted(source_table.indexes, key=lambda item: item.name):
        connection.execute(CreateIndex(index))
    for sql in preserved_sql:
        connection.exec_driver_sql(sql)

    if not _automations_schema_has_constraints(connection):
        raise RuntimeError(
            "Migration automations refusée : contraintes non restaurées"
        )


_LOT_F_MODEL_PARITY_TABLES = (
    "workers",
    "automation_webhook_rotations",
    "automation_commands",
    "automation_runs",
    "scheduler_leases",
    "budget_usage",
    "alerts",
    "notification_preferences",
    "project_budget_policies",
    "budget_usage_reports",
)

# Une ancienne version additive posait ce CHECK anonyme au moment d'ajouter
# ``workers.global_access``. Il est la conjonction exacte des deux CHECK nommés du
# modèle actuel : il peut donc être remplacé sans perdre une règle locale.
_COMPATIBLE_LEGACY_CHECKS = {
    "workers": {
        "global_accessin(0,1)and(global_access=0orproject_idisnull)",
    },
    # CHECK transitoire posé avant l'ajout du plafond NUMERIC explicite.
    "budget_usage": {"cost>=0"},
    # Même transition pour le ledger : le CHECK historique nomme déjà la
    # contrainte, mais ne bornait pas encore la capacité NUMERIC côté SQLite.
    "budget_usage_reports": {"costisnullorcost>=0"},
}


def _normalized_type(connection, value) -> str:
    compiled = value.compile(dialect=connection.dialect)
    return "".join(str(compiled).upper().split())


def _check_signatures_from_model(table) -> set[tuple[str | None, str]]:
    return {
        (constraint.name, _normalized_sql_expression(str(constraint.sqltext)))
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _check_signatures_from_database(inspector, table_name: str):
    return {
        (
            constraint.get("name"),
            _normalized_sql_expression(constraint.get("sqltext")),
        )
        for constraint in inspector.get_check_constraints(table_name)
    }


def _foreign_key_signatures_from_model(table):
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
            _index_options_signature(
                {
                    "onupdate": constraint.onupdate,
                    "ondelete": constraint.ondelete,
                    "deferrable": constraint.deferrable,
                    "initially": constraint.initially,
                    "match": constraint.match,
                }
            ),
        )
        for constraint in table.foreign_key_constraints
    }


def _foreign_key_signatures_from_database(inspector, table_name: str):
    signatures = set()
    for constraint in inspector.get_foreign_keys(table_name):
        options = constraint.get("options") or {}
        signatures.add(
            (
                tuple(constraint.get("constrained_columns") or ()),
                constraint.get("referred_table"),
                tuple(constraint.get("referred_columns") or ()),
                _index_options_signature(options),
            )
        )
    return signatures


def _index_options_signature(options) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                str(name),
                _normalized_sql_expression(str(value)),
            )
            for name, value in dict(options or {}).items()
            if value is not None
        )
    )


def _unique_signatures_from_model(table):
    signatures = {
        (tuple(column.name for column in constraint.columns), ())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    signatures |= {
        (
            tuple(expression.name for expression in index.expressions),
            _index_options_signature(index.dialect_kwargs),
        )
        for index in table.indexes
        if index.unique
    }
    return signatures


def _unique_signatures_from_database(inspector, table_name: str):
    signatures = {
        (tuple(constraint.get("column_names") or ()), ())
        for constraint in inspector.get_unique_constraints(table_name)
    }
    signatures |= {
        (
            tuple(index.get("column_names") or ()),
            _index_options_signature(index.get("dialect_options")),
        )
        for index in inspector.get_indexes(table_name)
        if index.get("unique")
    }
    return signatures


def _model_index_signatures(table):
    return {
        index.name: (
            tuple(expression.name for expression in index.expressions),
            bool(index.unique),
            _index_options_signature(index.dialect_kwargs),
        )
        for index in table.indexes
    }


def _database_index_signatures(inspector, table_name: str):
    return {
        index.get("name"): (
            tuple(index.get("column_names") or ()),
            bool(index.get("unique")),
            _index_options_signature(index.get("dialect_options")),
        )
        for index in inspector.get_indexes(table_name)
    }


def _lot_f_table_parity(connection, table_name: str) -> tuple[bool, list[str]]:
    """Compare une table SQLite existante à son DDL SQLAlchemy de référence.

    La valeur booléenne indique qu'une reconstruction est nécessaire. Les
    messages signalent au contraire les objets locaux qui empêchent une
    reconstruction sans perte et doivent faire refuser le démarrage.
    """

    inspector = inspect(connection)
    model = Base.metadata.tables[table_name]
    expected_columns = {column.name: column for column in model.columns}
    actual_columns = {
        column["name"]: column
        for column in inspector.get_columns(table_name)
    }
    missing = sorted(set(expected_columns).difference(actual_columns))
    extra = sorted(set(actual_columns).difference(expected_columns))
    if missing or extra:
        raise RuntimeError(
            f"Migration {table_name} refusée : colonnes incompatibles "
            f"(manquantes non ajoutables={missing}, inconnues={extra})"
        )

    rebuild = False
    for name, expected in expected_columns.items():
        actual = actual_columns[name]
        if _normalized_type(connection, actual["type"]) != _normalized_type(
            connection, expected.type
        ):
            rebuild = True
        if bool(actual.get("nullable")) != bool(expected.nullable):
            rebuild = True
        if bool(actual.get("primary_key")) != bool(expected.primary_key):
            rebuild = True
        expected_default = (
            expected.server_default.arg
            if expected.server_default is not None
            else None
        )
        if _normalized_sqlite_default(
            actual.get("default")
        ) != _normalized_sqlite_default(expected_default):
            rebuild = True

    expected_pk = tuple(column.name for column in model.primary_key.columns)
    actual_pk = tuple(
        inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    rebuild = rebuild or actual_pk != expected_pk

    expected_checks = _check_signatures_from_model(model)
    actual_checks = _check_signatures_from_database(inspector, table_name)
    allowed_legacy = _COMPATIBLE_LEGACY_CHECKS.get(table_name, set())
    unsupported_checks = sorted(
        f"CHECK {name or '<sans nom>'}"
        for name, expression in actual_checks.difference(expected_checks)
        if expression not in allowed_legacy
    )
    rebuild = rebuild or actual_checks != expected_checks

    expected_foreign_keys = _foreign_key_signatures_from_model(model)
    actual_foreign_keys = _foreign_key_signatures_from_database(
        inspector, table_name
    )
    unsupported_foreign_keys = sorted(
        f"FOREIGN KEY {signature}"
        for signature in actual_foreign_keys.difference(expected_foreign_keys)
    )
    rebuild = rebuild or actual_foreign_keys != expected_foreign_keys

    expected_uniques = _unique_signatures_from_model(model)
    actual_uniques = _unique_signatures_from_database(inspector, table_name)
    unsupported_uniques = sorted(
        f"UNIQUE {columns} options={options}"
        for columns, options in actual_uniques.difference(expected_uniques)
    )
    rebuild = rebuild or actual_uniques != expected_uniques

    expected_indexes = _model_index_signatures(model)
    actual_indexes = _database_index_signatures(inspector, table_name)
    incompatible_indexes = sorted(
        f"INDEX {name}"
        for name, signature in expected_indexes.items()
        if name in actual_indexes and actual_indexes[name] != signature
    )
    rebuild = rebuild or any(
        actual_indexes.get(name) != signature
        for name, signature in expected_indexes.items()
    )

    return rebuild, (
        unsupported_checks
        + unsupported_foreign_keys
        + unsupported_uniques
        + incompatible_indexes
    )


def _preserved_lot_f_objects(connection, table_name: str) -> list[str]:
    """Capture les index non uniques et triggers étrangers au modèle."""

    inspector = inspect(connection)
    model_index_names = set(_model_index_signatures(Base.metadata.tables[table_name]))
    actual_indexes = _database_index_signatures(inspector, table_name)
    objects = connection.execute(
        text(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = :table_name AND type IN ('index', 'trigger') "
            "AND sql IS NOT NULL ORDER BY type, name"
        ),
        {"table_name": table_name},
    ).mappings()
    preserved: list[str] = []
    for row in objects:
        if row["type"] == "trigger":
            preserved.append(row["sql"])
            continue
        signature = actual_indexes.get(row["name"])
        if (
            row["name"] not in model_index_names
            and signature is not None
            and not signature[1]
        ):
            preserved.append(row["sql"])
    return preserved


def _rebuild_lot_f_table_from_model(connection, table_name: str) -> None:
    rebuild, unsupported = _lot_f_table_parity(connection, table_name)
    if unsupported:
        raise RuntimeError(
            f"Migration {table_name} refusée : contraintes ou index locaux "
            "incompatibles (" + "; ".join(unsupported) + ")"
        )
    if not rebuild:
        return

    replacement_name = f"{table_name}_lot_f_model_parity_v3"
    if inspect(connection).has_table(replacement_name):
        raise RuntimeError(
            f"Migration {table_name} refusée : table temporaire déjà présente"
        )
    preserved_sql = _preserved_lot_f_objects(connection, table_name)
    source = Base.metadata.tables[table_name]
    migration_metadata = MetaData()
    for foreign_key in source.foreign_key_constraints:
        foreign_key.referred_table.to_metadata(migration_metadata)
    replacement = source.to_metadata(migration_metadata, name=replacement_name)
    connection.execute(CreateTable(replacement))

    columns = tuple(column.name for column in source.columns)
    quoted_columns = ", ".join(f'"{name}"' for name in columns)
    try:
        connection.execute(
            text(
                f'INSERT INTO "{replacement_name}" ({quoted_columns}) '
                f'SELECT {quoted_columns} FROM "{table_name}"'
            )
        )
    except IntegrityError as exc:
        raise RuntimeError(
            f"Migration {table_name} refusée : données incompatibles avec "
            f"le modèle ({exc.orig})"
        ) from exc

    connection.execute(text(f'DROP TABLE "{table_name}"'))
    connection.execute(
        text(f'ALTER TABLE "{replacement_name}" RENAME TO "{table_name}"')
    )
    for index in sorted(source.indexes, key=lambda item: item.name):
        connection.execute(CreateIndex(index))
    for sql in preserved_sql:
        connection.exec_driver_sql(sql)

    remaining, unsupported = _lot_f_table_parity(connection, table_name)
    if remaining or unsupported:
        raise RuntimeError(
            f"Migration {table_name} refusée : parité structurelle non restaurée"
        )


def _backfill_legacy_budget_reports(connection) -> None:
    """Complète le ledger historique sans inventer une décision budgétaire."""

    if not inspect(connection).has_table("budget_usage_reports"):
        return
    invalid_measure = connection.execute(
        text(
            "SELECT COUNT(*) FROM budget_usage_reports WHERE "
            "cost IS NULL AND tokens_input IS NULL AND tokens_output IS NULL "
            "AND tool_calls IS NULL"
        )
    ).scalar_one()
    invalid_currency = connection.execute(
        text(
            "SELECT COUNT(*) FROM budget_usage_reports WHERE "
            "(cost IS NULL AND currency IS NOT NULL) OR "
            "(cost IS NOT NULL AND currency IS NULL)"
        )
    ).scalar_one()
    if invalid_measure or invalid_currency:
        raise RuntimeError(
            "Migration budget_usage_reports refusée : ledger historique "
            f"incohérent (sans mesure={invalid_measure}, "
            f"paire coût/devise={invalid_currency})"
        )

    connection.execute(
        text(
            "UPDATE budget_usage_reports SET kind = 'usage' "
            "WHERE kind IS NULL OR kind = ''"
        )
    )
    connection.execute(
        text(
            "UPDATE budget_usage_reports SET permit_id = 'legacy:' || id "
            "WHERE permit_id IS NULL OR permit_id = ''"
        )
    )
    connection.execute(
        text(
            "UPDATE budget_usage_reports "
            "SET accounting_day = strftime('%Y-%m-%d', occurred_at) "
            "WHERE accounting_day IS NULL OR accounting_day = ''"
        )
    )
    invalid_day = connection.execute(
        text(
            "SELECT COUNT(*) FROM budget_usage_reports WHERE "
            "accounting_day IS NULL OR length(accounting_day) != 10"
        )
    ).scalar_one()
    if invalid_day:
        raise RuntimeError(
            "Migration budget_usage_reports refusée : "
            f"{invalid_day} date(s) UTC non interprétable(s)"
        )

    rows = connection.execute(
        text(
            "SELECT id, source, cost, currency, tokens_input, tokens_output, "
            "tool_calls, estimated FROM budget_usage_reports "
            "WHERE verdict_snapshot IS NULL "
            "OR trim(CAST(verdict_snapshot AS TEXT)) IN ('', '{}')"
        )
    ).mappings()
    for row in rows:
        estimated = bool(row["estimated"])
        provider_measure = any(
            row[name] is not None
            for name in ("cost", "tokens_input", "tokens_output")
        )
        snapshot = {
            "state": "unknown",
            "measured": not estimated,
            "limit_reached": None,
            "cost": float(row["cost"]) if row["cost"] is not None else None,
            "currency": (
                str(row["currency"]).upper()
                if row["currency"] is not None
                else "EUR"
            ),
            "tokens_input": row["tokens_input"],
            "tokens_output": row["tokens_output"],
            "tool_calls": row["tool_calls"],
            "usage_reported": (
                row["source"] == "provider" and provider_measure and not estimated
            ),
            "estimated": estimated,
        }
        connection.execute(
            text(
                "UPDATE budget_usage_reports SET verdict_snapshot = :snapshot "
                "WHERE id = :report_id"
            ),
            {
                "snapshot": json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "report_id": row["id"],
            },
        )


def _prepare_lot_f_rows_for_model_parity(
    connection, *, automation_run_timezone_was_missing: bool
) -> None:
    inspector = inspect(connection)
    if inspector.has_table("automation_runs"):
        if inspector.has_table("automations"):
            timezone_expression = (
                "COALESCE(NULLIF((SELECT timezone FROM automations "
                "WHERE automations.id = automation_runs.automation_id), ''), "
                "'Europe/Paris')"
            )
        else:
            timezone_expression = "'Europe/Paris'"
        predicate = (
            "1 = 1"
            if automation_run_timezone_was_missing
            else "schedule_timezone IS NULL OR schedule_timezone = ''"
        )
        connection.execute(
            text(
                "UPDATE automation_runs SET schedule_timezone = "
                f"{timezone_expression} WHERE {predicate}"
            )
        )
        connection.execute(
            text(
                "UPDATE automation_runs SET trigger_kind = 'schedule' "
                "WHERE trigger_kind IS NULL OR trigger_kind = ''"
            )
        )
    if inspector.has_table("budget_usage"):
        connection.execute(
            text(
                "UPDATE budget_usage SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
    if inspector.has_table("alerts"):
        connection.execute(
            text(
                "UPDATE alerts SET acknowledgement_comment = '' "
                "WHERE acknowledgement_comment IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE alerts SET dedupe_key_active = dedupe_key "
                "WHERE acknowledged_at IS NULL AND dedupe_key_active IS NULL"
            )
        )
    if inspector.has_table("notification_preferences"):
        connection.execute(
            text(
                "UPDATE notification_preferences SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
    if inspector.has_table("project_budget_policies"):
        connection.execute(
            text(
                "UPDATE project_budget_policies SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
    _backfill_legacy_budget_reports(connection)


def _rebuild_lot_f_tables_with_model_parity(connection) -> None:
    for table_name in _LOT_F_MODEL_PARITY_TABLES:
        if inspect(connection).has_table(table_name):
            _rebuild_lot_f_table_from_model(connection, table_name)


def _upgrade_sqlite_schema(engine) -> None:
    """Met à niveau les bases SQLite MVP déjà créées.

    ``create_all`` ne complète pas une table existante. Les colonnes compatibles
    sont d'abord ajoutées et backfillées, puis les tables du Lot F sont comparées
    au modèle et reconstruites atomiquement lorsqu'une contrainte ou un type
    manque. Une vraie chaîne Alembic remplacera ce mécanisme lorsque le projet
    sortira du mode SQLite local.
    """

    if engine.dialect.name != "sqlite":
        return
    additions = {
        "tasks": {
            "is_mission": "INTEGER NOT NULL DEFAULT 0",
            "objective": "TEXT NOT NULL DEFAULT ''",
            "expected_outcome": "TEXT NOT NULL DEFAULT ''",
            "acceptance_criteria": "JSON NOT NULL DEFAULT '[]'",
            "autonomy": "JSON NOT NULL DEFAULT '{}'",
            "resources": "JSON NOT NULL DEFAULT '[]'",
            "budget": "JSON NOT NULL DEFAULT '{}'",
            "duration_seconds": "INTEGER",
            "created_by_user_id": "VARCHAR(36)",
            "attempt_counter": "INTEGER NOT NULL DEFAULT 0",
            "active_run_id": "VARCHAR(36)",
        },
        "task_runs": {
            "attempt_number": "INTEGER NOT NULL DEFAULT 0",
            "fencing_token": "INTEGER NOT NULL DEFAULT 0",
            "stop_requested_at": "DATETIME",
            "stop_requested_by_user_id": "VARCHAR(36)",
            "technical_validation": "JSON NOT NULL DEFAULT '{}'",
            "user_acceptance": "JSON NOT NULL DEFAULT '{}'",
            "updated_at": "DATETIME",
        },
        "approvals": {
            "target": "VARCHAR(1000) NOT NULL DEFAULT ''",
            "consequences": "JSON NOT NULL DEFAULT '[]'",
            "scope": "JSON NOT NULL DEFAULT '{}'",
            "footprint": "JSON NOT NULL DEFAULT '{}'",
            "action_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
            "invalidated_at": "DATETIME",
            "invalidated_reason": "TEXT NOT NULL DEFAULT ''",
        },
        "mission_commands": {
            "principal_id": "VARCHAR(36)",
            "request_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
        },
        "mission_comments": {
            "request_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
        },
        "events": {
            "schema_version": "VARCHAR(10) NOT NULL DEFAULT '1.0'",
            "sequence": "INTEGER",
            "journal_seq": "INTEGER",
            "conversation_id": "VARCHAR(36)",
            "step_id": "VARCHAR(64)",
            "executor": "VARCHAR(64)",
            "emitted_by": "VARCHAR(64)",
        },
        "artifacts": {
            "storage_key": "VARCHAR(200)",
            "content_type": "VARCHAR(200) NOT NULL DEFAULT 'application/octet-stream'",
            "original_name": "VARCHAR(500) NOT NULL DEFAULT ''",
            "source": "VARCHAR(50) NOT NULL DEFAULT 'worker'",
            "stream_kind": "VARCHAR(50) NOT NULL DEFAULT ''",
            "deleted_at": "DATETIME",
        },
        "workers": {
            "project_id": "VARCHAR(36) REFERENCES projects(id)",
            "global_access": "INTEGER NOT NULL DEFAULT 0",
        },
        "automations": {
            "description": "TEXT NOT NULL DEFAULT ''",
            "timezone": "VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris'",
            "mission_template": "JSON NOT NULL DEFAULT '{}'",
            "enabled": "INTEGER NOT NULL DEFAULT 0",
            "catchup_policy": "VARCHAR(20) NOT NULL DEFAULT 'skip'",
            "max_concurrent_runs": "INTEGER NOT NULL DEFAULT 1",
            "next_run_at": "DATETIME",
            "last_fire_key": "VARCHAR(64)",
            "created_by_user_id": "VARCHAR(36)",
            "create_idempotency_key": "VARCHAR(200)",
            "create_request_fingerprint": "VARCHAR(64)",
            "webhook_enabled": "INTEGER NOT NULL DEFAULT 0",
            "webhook_secret_hash": "VARCHAR(64)",
            "webhook_rotated_at": "DATETIME",
            "webhook_rotation_number": "INTEGER NOT NULL DEFAULT 0",
            "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
            "failure_threshold": "INTEGER NOT NULL DEFAULT 3",
            "mutation_revision": "BIGINT NOT NULL DEFAULT 0",
        },
        "automation_runs": {
            "task_id": "VARCHAR(36)",
            "trigger_kind": "VARCHAR(20) NOT NULL DEFAULT 'schedule'",
            "schedule_timezone": "VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris'",
            "detail": "VARCHAR(500) NOT NULL DEFAULT ''",
            "completion_observed_at": "DATETIME",
            "completion_status": "VARCHAR(30)",
        },
        "automation_commands": {
            "principal_id": "VARCHAR(36)",
            "command": "VARCHAR(30)",
            "idempotency_key": "VARCHAR(200)",
            "request_fingerprint": "VARCHAR(64)",
            "postcondition": "JSON NOT NULL DEFAULT '{}'",
            "result_revision": "BIGINT NOT NULL DEFAULT 0",
        },
        "budget_usage": {
            "cost": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
            "currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'",
            "tokens_input": "BIGINT NOT NULL DEFAULT 0",
            "tokens_output": "BIGINT NOT NULL DEFAULT 0",
            "tool_calls": "BIGINT NOT NULL DEFAULT 0",
            "usage_reported": "INTEGER NOT NULL DEFAULT 0",
            "cost_reported": "INTEGER NOT NULL DEFAULT 0",
            "tokens_input_reported": "INTEGER NOT NULL DEFAULT 0",
            "tokens_output_reported": "INTEGER NOT NULL DEFAULT 0",
            "tool_calls_reported": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "DATETIME",
        },
        "alerts": {
            "detail": "TEXT NOT NULL DEFAULT ''",
            "task_id": "VARCHAR(36)",
            "automation_id": "VARCHAR(36)",
            "acknowledged_at": "DATETIME",
            "acknowledged_by_user_id": "VARCHAR(36)",
            "acknowledgement_comment": "TEXT NOT NULL DEFAULT ''",
            "dedupe_key_active": "VARCHAR(64)",
        },
        "notification_preferences": {
            "project_id": "VARCHAR(36)",
            "user_id": "VARCHAR(36)",
            "channel": "VARCHAR(20) NOT NULL DEFAULT 'in_app'",
            "enabled": "INTEGER NOT NULL DEFAULT 1",
            "minimum_severity": "VARCHAR(20) NOT NULL DEFAULT 'warning'",
            "budget_alerts": "INTEGER NOT NULL DEFAULT 1",
            "automation_failures": "INTEGER NOT NULL DEFAULT 1",
            "storage_alerts": "INTEGER NOT NULL DEFAULT 1",
            "updated_at": "DATETIME",
        },
        "project_budget_policies": {
            "project_id": "VARCHAR(36)",
            "timezone": "VARCHAR(64) NOT NULL DEFAULT 'Europe/Paris'",
            "policy": "JSON NOT NULL DEFAULT '{}'",
            "updated_at": "DATETIME",
        },
        "budget_usage_reports": {
            "task_run_id": "VARCHAR(36)",
            "report_id": "VARCHAR(128)",
            "permit_id": "VARCHAR(128)",
            "project_id": "VARCHAR(36)",
            "provider": "VARCHAR(100)",
            "kind": "VARCHAR(20) NOT NULL DEFAULT 'usage'",
            "source": "VARCHAR(20)",
            "phase": "VARCHAR(20)",
            "cost": "NUMERIC(18, 6)",
            "currency": "VARCHAR(3)",
            "tokens_input": "BIGINT",
            "tokens_output": "BIGINT",
            "tool_calls": "BIGINT",
            "estimated": "INTEGER NOT NULL DEFAULT 0",
            "allowed": "INTEGER NOT NULL DEFAULT 1",
            "reconciled_at": "DATETIME",
            "accounting_day": "VARCHAR(10)",
            "verdict_snapshot": "JSON",
            "occurred_at": "DATETIME",
        },
    }
    with _sqlite_migration_connection(engine) as connection:
        # SQLite ne démarre sinon réellement la transaction qu'à la première
        # écriture. Une migration qui ajoute plusieurs colonnes puis reconstruit
        # une table doit former un seul changement indivisible, y compris quand
        # le préflight refuse finalement les données historiques.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        inspector = inspect(connection)
        automation_run_timezone_was_missing = (
            inspector.has_table("automation_runs")
            and "schedule_timezone"
            not in {
                column["name"]
                for column in inspector.get_columns("automation_runs")
            }
        )
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, definition in columns.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN "{column_name}" {definition}'
                    )
                )
        if inspector.has_table("mission_commands"):
            _backfill_mission_command_principals(connection)
            _replace_task_scoped_mission_command_constraint(connection)
        if inspector.has_table("mission_comments"):
            _backfill_mission_comment_fingerprints(connection)
            _replace_task_scoped_mission_comment_constraint(connection)
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_is_mission ON tasks (is_mission)")
        )
        if inspect(connection).has_table("workers"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_workers_project_id "
                    "ON workers (project_id)"
                )
            )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_active_run_id ON tasks (active_run_id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_task_runs_attempt_number "
                "ON task_runs (attempt_number)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_mission_command_principal_key "
                "ON mission_commands (principal_id, command, idempotency_key) "
                "WHERE principal_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mission_commands_task_id "
                "ON mission_commands (task_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mission_commands_principal_id "
                "ON mission_commands (principal_id)"
            )
        )
        if inspect(connection).has_table("mission_comments"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_task_id "
                    "ON mission_comments (task_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_task_run_id "
                    "ON mission_comments (task_run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_mission_comments_author_user_id "
                    "ON mission_comments (author_user_id)"
                )
            )
        if inspect(connection).has_table("events"):
            # Unicité partielle : les événements historiques et ceux sans
            # tentative n'ont pas de séquence et ne doivent pas être refusés.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_event_run_sequence "
                    "ON events (task_run_id, sequence) "
                    "WHERE task_run_id IS NOT NULL AND sequence IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_task_run_sequence "
                    "ON events (task_run_id, sequence)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_conversation_id "
                    "ON events (conversation_id)"
                )
            )
            # Ordre total du journal : unicité partielle, car une ligne peut
            # rester non numérotée le temps d'un démarrage interrompu.
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_journal_seq "
                    "ON events (journal_seq) WHERE journal_seq IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_events_journal_seq "
                    "ON events (journal_seq)"
                )
            )
            _backfill_event_journal_sequence(connection)
        if inspect(connection).has_table("artifacts"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_artifacts_storage_key "
                    "ON artifacts (storage_key)"
                )
            )
        if inspect(connection).has_table("automations"):
            # Les valeurs NULL viennent uniquement de schémas intermédiaires qui
            # avaient ajouté les colonnes sans leurs DEFAULT/NOT NULL effectifs.
            # Une valeur non NULL invalide est au contraire refusée par le
            # préflight : la corriger silencieusement masquerait une corruption.
            connection.execute(
                text(
                    "UPDATE automations SET webhook_rotation_number = 0 "
                    "WHERE webhook_rotation_number IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE automations SET consecutive_failures = 0 "
                    "WHERE consecutive_failures IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE automations SET failure_threshold = 3 "
                    "WHERE failure_threshold IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE automations SET mutation_revision = 0 "
                    "WHERE mutation_revision IS NULL"
                )
            )
            _rebuild_automations_with_constraints(connection)
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_project_id "
                    "ON automations (project_id)"
                )
            )
            # Le planificateur ne pose qu'une question à chaque examen :
            # « quelles automatisations actives sont dues ? ». Sans cet index,
            # elle coûte une lecture complète de la table toutes les trente secondes.
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_next_run_at "
                    "ON automations (next_run_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automations_created_by_user_id "
                    "ON automations (created_by_user_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="automations",
                columns=(
                    "project_id",
                    "created_by_user_id",
                    "create_idempotency_key",
                ),
                name="uq_automations_create_principal_key",
            )
        _prepare_lot_f_rows_for_model_parity(
            connection,
            automation_run_timezone_was_missing=(
                automation_run_timezone_was_missing
            ),
        )
        _rebuild_lot_f_tables_with_model_parity(connection)
        if inspect(connection).has_table("automation_webhook_rotations"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_webhook_rotations_automation_id "
                    "ON automation_webhook_rotations (automation_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_webhook_rotations_principal_id "
                    "ON automation_webhook_rotations (principal_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="automation_webhook_rotations",
                columns=("automation_id", "principal_id", "idempotency_key"),
                name="uq_webhook_rotation_principal_key",
            )
            _ensure_unique_index(
                connection,
                table="automation_webhook_rotations",
                columns=("automation_id", "rotation_number"),
                name="uq_webhook_rotation_number",
            )
        if inspect(connection).has_table("automation_commands"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_commands_automation_id "
                    "ON automation_commands (automation_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_commands_principal_id "
                    "ON automation_commands (principal_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="automation_commands",
                columns=(
                    "automation_id",
                    "principal_id",
                    "command",
                    "idempotency_key",
                ),
                name="uq_automation_command_principal_key",
            )
        if inspect(connection).has_table("automation_runs"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_automation_runs_automation_id "
                    "ON automation_runs (automation_id)"
                )
            )
            reconcile_columns = (
                "automation_id",
                "completion_observed_at",
                "scheduled_for",
                "id",
                "outcome",
            )
            reconcile_index = next(
                (
                    index
                    for index in inspect(connection).get_indexes("automation_runs")
                    if index["name"] == "ix_automation_runs_reconcile_order"
                ),
                None,
            )
            if reconcile_index is not None and tuple(
                reconcile_index.get("column_names") or ()
            ) != reconcile_columns:
                connection.execute(
                    text("DROP INDEX ix_automation_runs_reconcile_order")
                )
        if inspect(connection).has_table("automation_runs"):
            if inspect(connection).has_table("automations"):
                timezone_expression = (
                    "COALESCE(NULLIF((SELECT timezone FROM automations "
                    "WHERE automations.id = automation_runs.automation_id), ''), "
                    "'Europe/Paris')"
                )
            else:
                timezone_expression = "'Europe/Paris'"
            predicate = (
                "1 = 1"
                if automation_run_timezone_was_missing
                else "schedule_timezone IS NULL OR schedule_timezone = ''"
            )
            connection.execute(
                text(
                    "UPDATE automation_runs SET schedule_timezone = "
                    f"{timezone_expression} WHERE {predicate}"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_runs_reconcile_order ON automation_runs ("
                    "automation_id, completion_observed_at, scheduled_for, "
                    "id, outcome)"
                )
            )
            # Unicité de l'occurrence nominale : c'est elle, et non une
            # vérification en mémoire, qui interdit deux missions pour un même
            # déclenchement planifié.
            _ensure_unique_index(
                connection,
                table="automation_runs",
                columns=("automation_id", "fire_key"),
                name="uq_automation_runs_fire_key",
            )
            connection.execute(
                text(
                    "UPDATE automation_runs SET trigger_kind = 'schedule' "
                    "WHERE trigger_kind IS NULL OR trigger_kind = ''"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_automation_runs_completion_observed_at "
                    "ON automation_runs (completion_observed_at)"
                )
            )
        if inspect(connection).has_table("scheduler_leases"):
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduler_leases_key "
                    "ON scheduler_leases (scheduler_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_scheduler_leases_owner_worker_id "
                    "ON scheduler_leases (owner_worker_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_scheduler_leases_lease_expires_at "
                    "ON scheduler_leases (lease_expires_at)"
                )
            )
        if inspect(connection).has_table("budget_usage"):
            # Une seule ligne de consommation par tentative : les incréments
            # concurrents portent alors tous sur la même ligne.
            _ensure_unique_index(
                connection,
                table="budget_usage",
                columns=("task_run_id",),
                name="ix_budget_usage_task_run_id",
            )
            connection.execute(
                text(
                    "UPDATE budget_usage SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("alerts"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_alerts_project_id "
                    "ON alerts (project_id)"
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_alerts_kind ON alerts (kind)")
            )
            # ``dedupe_key_active`` vaut ``NULL`` une fois l'alerte acquittée, et
            # ``NULL`` n'entre pas en conflit avec ``NULL`` : l'unicité ne porte donc
            # que sur les alertes **ouvertes**.
            _ensure_unique_index(
                connection,
                table="alerts",
                columns=("project_id", "dedupe_key_active"),
                name="uq_alerts_dedupe_active",
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_alerts_acknowledged_by_user_id "
                    "ON alerts (acknowledged_by_user_id)"
                )
            )
        if inspect(connection).has_table("notification_preferences"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_notification_preferences_project_id "
                    "ON notification_preferences (project_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_notification_preferences_user_id "
                    "ON notification_preferences (user_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="notification_preferences",
                columns=("project_id", "user_id"),
                name="uq_notification_preferences_project_user",
            )
            connection.execute(
                text(
                    "UPDATE notification_preferences SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("project_budget_policies"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_project_budget_policies_project_id "
                    "ON project_budget_policies (project_id)"
                )
            )
            _ensure_unique_index(
                connection,
                table="project_budget_policies",
                columns=("project_id",),
                name="uq_project_budget_policies_project",
            )
            connection.execute(
                text(
                    "UPDATE project_budget_policies SET updated_at = created_at "
                    "WHERE updated_at IS NULL"
                )
            )
        if inspect(connection).has_table("budget_usage_reports"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_task_run_id "
                    "ON budget_usage_reports (task_run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_project_id "
                    "ON budget_usage_reports (project_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_provider "
                    "ON budget_usage_reports (provider)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_occurred_at "
                    "ON budget_usage_reports (occurred_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_budget_usage_reports_accounting_day "
                    "ON budget_usage_reports (accounting_day)"
                )
            )
            _ensure_unique_index(
                connection,
                table="budget_usage_reports",
                columns=("task_run_id", "report_id"),
                name="uq_budget_usage_reports_run_report",
            )
            connection.execute(
                text(
                    "UPDATE budget_usage_reports SET kind = 'usage' "
                    "WHERE kind IS NULL OR kind = ''"
                )
            )
            # Une ancienne ligne ne connaissait pas le fuseau applicable. Le jour
            # UTC est le seul backfill honnête ; toutes les nouvelles écritures
            # figent le vrai jour local avant insertion.
            connection.execute(
                text(
                    "UPDATE budget_usage_reports "
                    "SET accounting_day = substr(occurred_at, 1, 10) "
                    "WHERE accounting_day IS NULL AND occurred_at IS NOT NULL"
                )
            )
        connection.execute(
            text(
                "UPDATE task_runs SET updated_at = created_at "
                "WHERE updated_at IS NULL"
            )
        )
        violations = connection.execute(text("PRAGMA foreign_key_check")).all()
        if violations:
            preview = ", ".join(
                f"{table}[rowid={rowid}]→{parent}"
                for table, rowid, parent, _constraint_index in violations[:10]
            )
            raise RuntimeError(
                "Migration SQLite refusée : clés étrangères orphelines détectées "
                f"({preview}). Corrigez ces lignes avant de redémarrer."
            )
