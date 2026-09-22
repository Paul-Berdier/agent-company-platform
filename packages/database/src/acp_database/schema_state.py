"""État de version du schéma : lecture, comparaison et estampillage Alembic.

Ce module est la seule source des réglages Alembic du projet (emplacement des
révisions, nom de la table de version, options de comparaison) : ``env.py``,
``acp_database.migrate`` et ``init_db()`` le consomment tous, afin qu'un
``check`` en ligne de commande et le contrôle de démarrage disent la même chose.
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

VERSION_TABLE = "alembic_version"
MIGRATIONS_PATH = Path(__file__).resolve().parent / "migrations"
UPGRADE_COMMAND = "python -m acp_database.migrate upgrade"


@dataclass(frozen=True)
class SchemaState:
    """Photographie de la version d'une base face à la chaîne de révisions.

    ``current`` vaut ``None`` quand la base ne porte pas de table
    ``alembic_version`` (base vide ou jamais estampillée) ; ``ok`` n'est vrai que
    si la révision courante est exactement la tête de la chaîne.
    """

    current: str | None
    head: str
    ok: bool
    unknown_revision: bool = False
    missing_tables: tuple[str, ...] = ()


class SchemaOutOfDateError(RuntimeError):
    """Refus de démarrage : la base n'est pas à la révision attendue.

    Le message cite la révision courante et la révision attendue ainsi que la
    commande à exécuter : l'opérateur sait exactement quoi faire, et rien n'est
    tenté à sa place, car une migration implicite au démarrage d'un processus
    parmi plusieurs serait une course dont personne ne voit le résultat.
    """

    def __init__(self, state: SchemaState) -> None:
        self.state = state
        current = state.current or "aucune (table alembic_version absente)"
        if getattr(state, "unknown_revision", False):
            message = (
                "Base migrée par une version plus récente ou une chaîne inconnue : "
                f"révision courante {current}, tête de ce code {state.head}. "
                "Utilisez le code compatible avec cette base ; tout retour arrière "
                "doit être préparé avec cette version et une sauvegarde vérifiée."
            )
        elif getattr(state, "missing_tables", ()):
            message = "Schéma incomplet malgré son estampille : tables absentes : " + ", ".join(state.missing_tables)
        else:
            message = (
                "Schéma de base hors version : révision courante "
                f"{current}, révision attendue {state.head}. "
                f"Exécutez « {UPGRADE_COMMAND} » avant de démarrer."
            )
        super().__init__(message)


def alembic_config(url: str | None = None) -> Config:
    """Configuration Alembic programmatique, sans dépendre d'un ``alembic.ini``.

    L'emplacement des révisions est celui du paquet installé : la commande
    fonctionne depuis n'importe quel répertoire courant. L'URL n'est posée que si
    l'appelant la fournit ; ``env.py`` lit sinon ``ACP_DATABASE_URL``.
    """

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    if url is not None:
        # configparser interprète ``%`` : on l'échappe pour les mots de passe.
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@lru_cache(maxsize=1)
def script_directory() -> ScriptDirectory:
    """Chaîne de révisions chargée une seule fois par processus.

    ``init_db()`` estampille chaque base SQLite qu'il ouvre ; relire les fichiers
    de révision à chaque appel pèserait sur la suite de tests sans rien apporter.
    """

    return ScriptDirectory.from_config(alembic_config())


def head_revision() -> str:
    """Révision de tête attendue par le code en cours d'exécution.

    Une chaîne à plusieurs têtes est refusée : elle signifierait deux branches de
    migration concurrentes, ce que le projet n'autorise pas.
    """

    heads = script_directory().get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "La chaîne Alembic doit avoir exactement une tête ; trouvé "
            f"{list(heads)!r}"
        )
    return heads[0]


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Écarte la table de version d'Alembic de toute comparaison de schéma."""

    if type_ == "table" and name == VERSION_TABLE:
        return False
    return True


_CAST_SUFFIX = re.compile(r"::[A-Za-z_][A-Za-z0-9_ ]*(\([^)]*\))?(\[\])*$")


def literal_default_text(rendered: str | None) -> str | None:
    """Ramène un ``DEFAULT`` relu du catalogue à son littéral nu.

    Vérifié empiriquement avec Alembic 1.20 sur les deux dialectes du projet :

    - SQLite renvoie ``''`` pour ``server_default=""`` alors qu'Alembic rend le
      modèle par la chaîne vide, d'où un faux ``modify_default`` sur les trois
      colonnes vides du modèle ;
    - PostgreSQL décore les littéraux d'un transtypage (``'EUR'::character
      varying``, ``'{}'::json``) puis, faute d'égalité textuelle, exécute une
      égalité SQL que le type ``json`` ne définit pas (``json = unknown``).

    Le modèle ne déclare que des littéraux : les comparer nus est donc exact, et
    le test de parité relit en plus le catalogue pour prouver la valeur stockée.
    """

    if rendered is None:
        return None
    value = rendered.strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    value = _CAST_SUFFIX.sub("", value).strip()
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def compare_server_default(
    context,
    inspected_column,
    metadata_column,
    inspected_default,
    metadata_default,
    rendered_metadata_default,
):
    """Comparateur de ``server_default`` limité aux littéraux du modèle.

    Retourne ``None`` (comparaison Alembic native) dès que le modèle porte autre
    chose qu'un littéral texte : seul le cas documenté dans
    :func:`literal_default_text` est pris en charge ici.
    """

    arg = getattr(metadata_default, "arg", None)
    if not isinstance(arg, str):
        return None
    if inspected_default is None:
        return True
    return literal_default_text(inspected_default) != arg


def autogenerate_options() -> dict:
    """Options de comparaison communes à ``env.py`` et à ``check_drift``."""

    return {
        "compare_type": True,
        "compare_server_default": compare_server_default,
        "include_object": include_object,
    }


def check_schema_current(engine, *, connection=None) -> SchemaState:
    """Lit la révision estampillée et la confronte à la tête de la chaîne.

    Une base sans table ``alembic_version`` donne ``current=None`` et ``ok=False``
    : c'est le cas d'une base PostgreSQL neuve, qui doit passer par
    ``acp_database.migrate upgrade`` et jamais par ``create_all``.
    """

    head = head_revision()
    missing: tuple[str, ...] = ()
    with (nullcontext(connection) if connection is not None else engine.connect()) as connection:
        context = MigrationContext.configure(
            connection, opts={"version_table": VERSION_TABLE}
        )
        heads = tuple(context.get_current_heads())
        if heads == (head,):
            from .models import Base
            missing = tuple(sorted(set(Base.metadata.tables) - set(inspect(connection).get_table_names())))
    if not heads:
        current: str | None = None
    elif len(heads) == 1:
        current = heads[0]
    else:
        current = ",".join(sorted(heads))
    known = {revision.revision for revision in script_directory().walk_revisions()}
    unknown = any(revision not in known for revision in heads)
    return SchemaState(
        current=current, head=head, ok=current == head and not missing,
        unknown_revision=unknown, missing_tables=missing,
    )


def stamp_head(engine) -> None:
    """Enregistre la tête de chaîne dans ``alembic_version`` sans autre DDL.

    Réservé à ``init_db()`` sous SQLite, où ``create_all`` et la mise à niveau ad
    hoc produisent déjà le schéma de tête : l'estampille dit simplement à Alembic
    qu'il n'a rien à rejouer. La table de version est créée si elle manque.
    """

    with engine.begin() as connection:
        context = MigrationContext.configure(
            connection, opts={"version_table": VERSION_TABLE}
        )
        context.stamp(script_directory(), "head")
