"""Sauvegarde et restauration sur PostgreSQL (base de test ``ACP_TEST_DATABASE_URL``).

Les binaires ``pg_dump``/``pg_restore`` sont pris, dans cet ordre :

- **natifs**, s'ils sont sur le PATH (exécuteur GitHub Ubuntu, binaires PostgreSQL
  installés sur le poste) : les commandes par défaut du module de sauvegarde, sur
  l'adresse même de la base ;
- sinon **dans le conteneur Docker** du serveur (``ACP_TEST_DOCKER_CONTAINER``,
  défaut ``acp-pg``) par ``ACP_BACKUP_PG_DUMP_COMMAND``,
  ``ACP_BACKUP_PG_RESTORE_COMMAND`` et ``ACP_BACKUP_DATABASE_URL_FOR_TOOLS``
  (adresse du serveur vue depuis le conteneur).

``ACP_TEST_PG_TOOLS=native`` ou ``docker`` impose l'un des deux. Sans outil, la suite
est ignorée ; elle échoue si ``ACP_TEST_DATABASE_REQUIRED=1``.

La base du lot est la source ; la restauration vise une seconde base
``<base>_restore`` créée à la demande, car restaurer sur la source est refusé.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from acp_api.artifacts_storage import LocalArtifactStorage
from acp_api.backup import EXIT_OK, EXIT_REFUSED, MANIFEST_NAME, main, url_fingerprint
from acp_api.secrets_vault import SecretsVault, key_id
from acp_database.engine import make_engine
from acp_database.migrate import run_upgrade
from acp_database.models import (
    ArtifactModel,
    Base,
    OrganizationModel,
    ProjectModel,
    SecretModel,
    TaskModel,
    TaskRunModel,
    UserModel,
    WorkerModel,
    WorkspaceModel,
)
from acp_database.schema_state import (
    VERSION_TABLE,
    autogenerate_options,
    check_schema_current,
    head_revision,
)
from acp_database.testing import (
    TEST_REQUIRED_ENV,
    reset_public_schema,
    schema_inventory,
    skip_or_fail_without_postgresql,
)

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
CONTAINER_ENV = "ACP_TEST_DOCKER_CONTAINER"
DEFAULT_CONTAINER = "acp-pg"
CONTAINER_PORT = 5432
TOOLS_ENV = "ACP_TEST_PG_TOOLS"


def _normalize(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return repr(value)


def table_fingerprints(url: str) -> dict[str, str]:
    """Empreinte du contenu de chaque table (lignes triées, hors table de version)."""

    engine = make_engine(url, maintenance=True)
    try:
        preparer = engine.dialect.identifier_preparer
        fingerprints: dict[str, str] = {}
        with engine.connect() as connection:
            for table in sorted(inspect(engine).get_table_names()):
                if table == VERSION_TABLE:
                    continue
                rows = connection.execute(
                    text(f"SELECT * FROM {preparer.quote(table)}")
                ).mappings()
                rendered = sorted(
                    json.dumps({k: _normalize(v) for k, v in row.items()}, sort_keys=True)
                    for row in rows
                )
                fingerprints[table] = hashlib.sha256("\n".join(rendered).encode()).hexdigest()
        return fingerprints
    finally:
        engine.dispose()


def _compare(url: str):
    engine = make_engine(url, maintenance=True)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"version_table": VERSION_TABLE, **autogenerate_options()}
            )
            return compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()


def _canonical_dumped_check(expression):
    """Normalise seulement les tableaux de littéraux varchar convertis en text.

    pg_dump peut déplacer le cast ``::text[]`` du tableau vers chacun de ses
    éléments. Les autres casts, les littéraux et la structure AND/OR restent
    strictement inchangés.
    """
    if not isinstance(expression, tuple):
        return expression
    if any(isinstance(item, tuple) for item in expression):
        return tuple(_canonical_dumped_check(item) for item in expression)

    varchar_cast = (":", ":", "character", "varying")
    text_cast = (":", ":", "text")
    normalized = []
    index = 0
    while index < len(expression):
        if expression[index:index + 2] == ("array", "["):
            try:
                end = expression.index("]", index + 2)
            except ValueError:
                end = index
            elements = [[]]
            for token in expression[index + 2:end]:
                if token == ",":
                    elements.append([])
                else:
                    elements[-1].append(token)
            literal_varchars = all(
                element and element[0].startswith("'")
                and tuple(element[1:]) in (varchar_cast, varchar_cast + text_cast)
                for element in elements
            )
            array_cast = expression[end + 1:end + 6] == text_cast + ("[", "]")
            element_casts = all(tuple(element[1:]) == varchar_cast + text_cast for element in elements)
            if literal_varchars and (array_cast or element_casts):
                normalized.extend(("array", "["))
                for number, element in enumerate(elements):
                    if number:
                        normalized.append(",")
                    normalized.extend((element[0], *text_cast))
                normalized.append("]")
                index = end + (6 if array_cast else 1)
                continue
        normalized.append(expression[index])
        index += 1
    return tuple(normalized)


def _comparable_inventory(url: str) -> dict:
    """Inventaire structurel dont les CHECK sont ramenés à une forme canonique.

    Un ``CHECK (x IN ('a', 'b'))`` est stocké par PostgreSQL comme
    ``x::text = ANY (ARRAY['a'::character varying, …]::text[])`` ; relu par
    ``pg_dump`` puis re-parsé par ``pg_restore``, il ressort en
    ``ANY (ARRAY['a'::character varying::text, …])``. Les deux formes sont
    équivalentes ; seul le rendu textuel du catalogue diffère.
    """

    engine = make_engine(url, maintenance=True)
    try:
        inventory = schema_inventory(engine)
    finally:
        engine.dispose()
    for table in inventory.values():
        table["checks"] = {
            (
                name,
                _canonical_dumped_check(expression),
            )
            for name, expression in table["checks"]
        }
    return inventory


@pytest.mark.parametrize("suffix", ["", " OR a IS NULL", " AND (a IS NULL OR b IS NULL)"])
def test_check_inventory_normalizes_dump_casts_without_flattening(suffix):
    from acp_database.testing import _normalized_expression

    source = "state::text = ANY (ARRAY['A B'::character varying, 'x,y'::character varying]::text[])"
    restored = "state::text = ANY (ARRAY['A B'::character varying::text, 'x,y'::character varying::text])"
    assert _canonical_dumped_check(_normalized_expression(source + suffix)) == (
        _canonical_dumped_check(_normalized_expression(restored + suffix))
    )


@pytest.mark.parametrize("first,second", [
    ("(a OR b) AND c", "a OR (b AND c)"),
    ("(x + y) * z > 0", "x + (y * z) > 0"),
    ("state = 'A B'", "state = 'a b'"),
    ("state = ']::text[]'", "state = ']'"),
    ("state = '::character varying::text'", "state = '::character varying'"),
    ("value = ANY (ARRAY[1, 2]::text[])", "value = ANY (ARRAY[1, 2])"),
    ("value = ANY (ARRAY['ab'::character varying(1)]::text[])",
     "value = ANY (ARRAY['ab'::character varying]::text[])"),
])
def test_check_inventory_preserves_other_semantic_differences(first, second):
    from acp_database.testing import _normalized_expression

    first_structure = _normalized_expression(first)
    assert _canonical_dumped_check(first_structure) == first_structure
    assert _canonical_dumped_check(first_structure) != (
        _canonical_dumped_check(_normalized_expression(second))
    )


def _ensure_database(admin_url: str, name: str) -> None:
    """Crée la base ``name`` si elle manque (connexion d'administration en autocommit)."""

    engine = create_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()


class PgTools:
    """Commandes ``pg_dump``/``pg_restore`` et adresse de la base telle qu'elles la voient."""

    def __init__(self, mode: str, commands: dict[str, str]) -> None:
        self.mode = mode
        self.commands = commands

    def url_for(self, url: str) -> str:
        parsed = make_url(url).set(drivername="postgresql")
        if self.mode == "docker":
            # Depuis le conteneur, le serveur écoute sur son port interne.
            parsed = parsed.set(host="127.0.0.1", port=CONTAINER_PORT)
        return parsed.render_as_string(hide_password=False)


def _tools_unavailable(reason: str):
    if os.environ.get(TEST_REQUIRED_ENV, "").strip() == "1":
        pytest.fail(f"{TEST_REQUIRED_ENV}=1 mais {reason}")
    pytest.skip(reason)


@pytest.fixture
def pg_tools() -> PgTools:
    """Outils natifs si présents, sinon exécutés dans le conteneur ; voir la docstring."""

    wanted = (os.environ.get(TOOLS_ENV) or "").strip().lower()
    if wanted not in {"", "native", "docker"}:
        pytest.fail(f"{TOOLS_ENV} : « native » ou « docker » attendu, « {wanted} » lu")
    native = shutil.which("pg_dump") is not None and shutil.which("pg_restore") is not None
    if wanted == "native" or (not wanted and native):
        if not native:
            _tools_unavailable("pg_dump/pg_restore absents du PATH")
        return PgTools("native", {})
    if shutil.which("docker") is None:
        _tools_unavailable("ni pg_dump/pg_restore sur le PATH, ni docker pour les exécuter")
    container = (os.environ.get(CONTAINER_ENV) or "").strip() or DEFAULT_CONTAINER
    return PgTools(
        "docker",
        {
            "ACP_BACKUP_PG_DUMP_COMMAND": json.dumps(
                [
                    "docker", "exec", container, "pg_dump", "--format=custom",
                    "--no-owner", "--no-privileges", "--dbname", "{url}",
                ]
            ),
            "ACP_BACKUP_PG_RESTORE_COMMAND": json.dumps(
                [
                    "docker", "exec", "-i", container, "pg_restore", "--no-owner",
                    "--no-privileges", "--exit-on-error", "--single-transaction",
                    "--dbname", "{url}",
                ]
            ),
        },
    )


def _drop_other_schemas(url: str) -> None:
    """Retire de la base cible tout schéma autre que ``public`` et ceux du système.

    ``pg_dump`` exporte tous les schémas de la source, y compris les schémas
    éphémères ``t_<hex>`` qu'un lot interrompu y aurait laissés ; une cible qui les
    aurait déjà reçus d'une restauration précédente ferait échouer ``pg_restore``
    (« schema already exists »). La cible ``<base>_restore`` n'appartient qu'à ce
    fichier de tests.
    """

    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            names = connection.execute(
                text(
                    "SELECT nspname FROM pg_namespace WHERE nspname <> 'public' "
                    "AND nspname <> 'information_schema' AND nspname NOT LIKE 'pg\\_%'"
                )
            ).scalars().all()
            for name in names:
                quoted = connection.dialect.identifier_preparer.quote(name)
                connection.execute(text(f"DROP SCHEMA {quoted} CASCADE"))
    finally:
        engine.dispose()


@pytest.fixture
def databases(pg_tools):
    """Source (base du lot, migrée puis peuplée) et cible ``<base>_restore`` vide."""

    source_url = skip_or_fail_without_postgresql()
    parsed = make_url(source_url)
    target_name = f"{parsed.database}_restore"
    _ensure_database(source_url, target_name)
    target_url = parsed.set(database=target_name).render_as_string(hide_password=False)
    reset_public_schema(source_url)
    reset_public_schema(target_url)
    _drop_other_schemas(target_url)
    engine = make_engine(source_url, maintenance=True)
    try:
        run_upgrade(engine)
    finally:
        engine.dispose()
    return {"source": source_url, "target": target_url}


class World:
    """Répertoires de fichiers, clé de coffre et données insérées dans une base."""

    def __init__(self, root: Path, suffix: str) -> None:
        self.artifacts_dir = root / f"artifacts-{suffix}"
        self.skills_dir = root / f"skills-{suffix}"
        self.vault_key = Fernet.generate_key().decode("ascii")
        self.key_id = key_id(self.vault_key.encode("ascii"))
        self.storage_keys: list[str] = []

    def environ(self, url: str, tools: PgTools) -> dict[str, str]:
        return {
            **tools.commands,
            "ACP_DATABASE_URL": url,
            "ACP_BACKUP_DATABASE_URL_FOR_TOOLS": tools.url_for(url),
            "ACP_ARTIFACT_STORAGE_DIR": str(self.artifacts_dir),
            "ACP_SKILLS_STORAGE_DIR": str(self.skills_dir),
            "ACP_SECRETS_KEYS": self.vault_key,
        }

    def populate(self, url: str) -> "World":
        storage = LocalArtifactStorage(self.artifacts_dir)
        engine = make_engine(url, maintenance=True)
        try:
            with Session(engine) as db:
                user = UserModel(
                    login_normalized=f"owner-{uuid4().hex}",
                    display_name="Propriétaire",
                    password_hash="x" * 60,
                )
                db.add(user)
                organization = OrganizationModel(name="Org")
                db.add(organization)
                db.flush()
                workspace = WorkspaceModel(organization_id=organization.id, name="Ws")
                db.add(workspace)
                db.flush()
                project = ProjectModel(workspace_id=workspace.id, name="Projet")
                db.add(project)
                db.flush()
                task = TaskModel(project_id=project.id, title="Mission", is_mission=1)
                db.add(task)
                db.flush()
                run = TaskRunModel(task_id=task.id, status="succeeded")
                db.add(run)
                worker = WorkerModel(
                    name=f"worker-{uuid4().hex}",
                    token_hash="y" * 64,
                    token_prefix="prefix",
                    token_expires_at=NOW + timedelta(days=1),
                )
                db.add(worker)
                db.flush()
                for payload in (b"rapport un", b"rapport deux", b"rapport trois"):
                    blob = storage.write(io.BytesIO(payload), max_bytes=1_000_000)
                    db.add(
                        ArtifactModel(
                            project_id=project.id,
                            task_run_id=run.id,
                            worker_id=worker.id,
                            kind="report",
                            path="",
                            checksum=blob.sha256,
                            size_bytes=blob.size,
                            storage_key=blob.key,
                            metadata_json={"accents": "éàü", "n": 1},
                        )
                    )
                    self.storage_keys.append(blob.key)
                vault = SecretsVault([self.vault_key.encode("ascii")])
                used_key_id, token = vault.encrypt("valeur")
                db.add(
                    SecretModel(
                        name="API_TOKEN",
                        scope_type="platform",
                        key_id=used_key_id,
                        ciphertext=token,
                        created_by_user_id=user.id,
                    )
                )
                db.commit()
        finally:
            engine.dispose()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        return self


def run(argv, environ):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, environ=environ, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _restore_args(backup_dir: Path, url: str, world: World, *extra: str) -> list[str]:
    return [
        "restore", str(backup_dir), "--into", url,
        "--artifacts-dir", str(world.artifacts_dir),
        "--skills-dir", str(world.skills_dir),
        *extra,
    ]


def test_round_trip_through_pg_dump_and_pg_restore(databases, pg_tools, tmp_path):
    source, target = databases["source"], databases["target"]
    world = World(tmp_path, "a").populate(source)
    before = table_fingerprints(source)
    assert before["artifacts"] and before["secrets"]
    output = tmp_path / "sauvegarde"

    code, out, err = run(
        ["create", "--output", str(output), "--label", "pg"], world.environ(source, pg_tools)
    )
    assert (code, err) == (EXIT_OK, ""), out + err
    manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["database"]["dialect"] == "postgresql"
    assert manifest["database"]["file"] == "database.pgdump"
    assert manifest["database"]["alembic_current"] == head_revision()
    assert manifest["database"]["row_counts"]["artifacts"] == 3
    assert manifest["secrets_key_ids"] == [world.key_id]
    assert manifest["artifact_storage_keys_referenced"] == sorted(world.storage_keys)
    assert manifest["source_url_fingerprint"] == url_fingerprint(source)
    assert manifest["warnings"] == []
    assert (output / "database.pgdump").read_bytes().startswith(b"PGDMP")
    assert make_url(source).password not in json.dumps(manifest)

    code, out, err = run(["verify", str(output)], world.environ(source, pg_tools))
    assert (code, err) == (EXIT_OK, ""), out + err

    # Restaurer sur la source est refusé ; la cible est la base voisine vide.
    code, _out, err = run(_restore_args(output, source, world), world.environ(source, pg_tools))
    assert code == EXIT_REFUSED and "base d'origine" in err

    restored = World(tmp_path, "b")
    restored.vault_key, restored.key_id = world.vault_key, world.key_id
    code, out, err = run(
        _restore_args(output, target, restored), restored.environ(target, pg_tools)
    )
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Contrôles post-restauration conformes" in out
    assert "Avertissement" not in out

    assert table_fingerprints(target) == before
    assert _compare(target) == []
    assert _comparable_inventory(target) == _comparable_inventory(source)
    state = check_schema_current(make_engine(target, maintenance=True))
    assert state.ok is True and state.current == head_revision()
    assert sorted(
        p.relative_to(restored.artifacts_dir).as_posix()
        for p in restored.artifacts_dir.rglob("*")
        if p.is_file()
    ) == sorted(world.storage_keys)


def test_replace_backs_up_the_postgresql_target_then_restores(databases, pg_tools, tmp_path):
    source, target = databases["source"], databases["target"]
    world = World(tmp_path, "a").populate(source)
    source_fingerprints = table_fingerprints(source)
    output = tmp_path / "sauvegarde"
    code, out, err = run(["create", "--output", str(output)], world.environ(source, pg_tools))
    assert (code, err) == (EXIT_OK, ""), out + err

    # La cible est elle-même une base ACP migrée et peuplée différemment.
    engine = make_engine(target, maintenance=True)
    try:
        run_upgrade(engine)
    finally:
        engine.dispose()
    occupant = World(tmp_path, "b").populate(target)
    occupant_fingerprints = table_fingerprints(target)
    assert occupant_fingerprints != source_fingerprints

    code, _out, err = run(_restore_args(output, target, occupant), occupant.environ(target, pg_tools))
    assert code == EXIT_REFUSED and "Cible non vide" in err
    assert table_fingerprints(target) == occupant_fingerprints

    pre_restore = tmp_path / "avant"
    code, out, err = run(
        _restore_args(output, target, occupant, "--replace", "--pre-restore-backup", str(pre_restore)),
        occupant.environ(target, pg_tools),
    )
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Schéma public de la cible vidé" in out
    assert "Répertoire mis à l'écart" in out
    pre_manifest = json.loads((pre_restore / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert pre_manifest["source_url_fingerprint"] == url_fingerprint(target)
    assert pre_manifest["artifact_storage_keys_referenced"] == sorted(occupant.storage_keys)
    code, _out, err = run(["verify", str(pre_restore)], occupant.environ(target, pg_tools))
    assert (code, err) == (EXIT_OK, "")

    assert table_fingerprints(target) == source_fingerprints
    assert _compare(target) == []
    assert check_schema_current(make_engine(target, maintenance=True)).ok is True
    warnings = [line for line in out.splitlines() if line.startswith("Avertissement")]
    assert any("clés de secrets absentes" in line and world.key_id in line for line in warnings), (
        "la cible garde la clé de coffre de l'occupant : la clé de la source manque"
    )
