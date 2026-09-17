"""Sauvegarde, vérification et restauration avec manifeste, sur SQLite fichier.

Chaque test part d'une base réelle (fichier temporaire estampillé à la tête
Alembic) peuplée d'un projet, d'une tentative, de livrables adressés par contenu,
d'une révision de skill sur disque et d'un secret chiffré avec une clé Fernet
connue. Les preuves sont des empreintes de lignes par table, calculées avant et
après l'aller-retour : une restauration « réussie » qui aurait perdu une ligne se
verrait.

Les refus font partie du contrat : manifeste altéré, cible non vide, source comme
cible, dialecte différent, clé de secret manquante, chemin hostile dans une
archive. Chacun est prouvé par son code de sortie et son message.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from acp_api import backup
from acp_api.artifacts_storage import LocalArtifactStorage
from acp_api.backup import (
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    FORMAT_VERSION,
    MANIFEST_NAME,
    main,
    product_version,
    url_fingerprint,
)
from acp_api.secrets_vault import SecretsVault, key_id
from acp_database.engine import make_engine
from acp_database.migrate import run_stamp
from acp_database.models import (
    ArtifactModel,
    Base,
    EventModel,
    OrganizationModel,
    ProjectModel,
    SecretModel,
    SkillModel,
    SkillRevisionModel,
    TaskModel,
    TaskRunModel,
    UserModel,
    WorkerModel,
    WorkspaceModel,
)
from acp_database.schema_state import VERSION_TABLE, check_schema_current, stamp_head

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[3]


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


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


def _files_of(root: Path) -> dict[str, str]:
    """Contenu d'un répertoire : chemin relatif → sha256 (fichiers seulement)."""

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class World:
    """Base SQLite fichier, répertoires de livrables et de skills, clé de coffre."""

    def __init__(self, root: Path, *, suffix: str = "a") -> None:
        self.root = root
        self.database = root / f"base-{suffix}.db"
        self.url = _sqlite_url(self.database)
        self.artifacts_dir = root / f"artifacts-{suffix}"
        self.skills_dir = root / f"skills-{suffix}"
        self.vault_key = Fernet.generate_key().decode("ascii")
        self.key_id = key_id(self.vault_key.encode("ascii"))
        self.storage_keys: list[str] = []
        self.deleted_storage_key: str | None = None
        self.skill_id = ""

    @property
    def environ(self) -> dict[str, str]:
        return {
            "ACP_DATABASE_URL": self.url,
            "ACP_ARTIFACT_STORAGE_DIR": str(self.artifacts_dir),
            "ACP_SKILLS_STORAGE_DIR": str(self.skills_dir),
            "ACP_SECRETS_KEYS": self.vault_key,
        }

    def populate(self, *, stamp: str = "head") -> "World":
        engine = make_engine(self.url)
        try:
            # Une seule transaction pour tout le DDL : un fichier SQLite sous Windows
            # paie une synchronisation disque par validation.
            with engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA synchronous=OFF")
                Base.metadata.create_all(connection)
            if stamp == "head":
                stamp_head(engine)
            else:
                run_stamp(engine, stamp)
            storage = LocalArtifactStorage(self.artifacts_dir)
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
                for index, payload in enumerate((b"rapport un", b"rapport deux")):
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
                            original_name=f"rapport-{index}.txt",
                        )
                    )
                    self.storage_keys.append(blob.key)
                purged = storage.write(io.BytesIO(b"purge"), max_bytes=1_000_000)
                storage.delete(purged.key)
                self.deleted_storage_key = purged.key
                db.add(
                    ArtifactModel(
                        project_id=project.id,
                        task_run_id=run.id,
                        worker_id=worker.id,
                        kind="report",
                        path="",
                        checksum=purged.sha256,
                        size_bytes=purged.size,
                        storage_key=purged.key,
                        deleted_at=NOW,
                    )
                )
                # Un fragment de téléversement et un fichier hors format ne doivent
                # jamais entrer dans l'archive.
                (self.artifacts_dir / "tmp").mkdir(parents=True, exist_ok=True)
                (self.artifacts_dir / "tmp" / "upload-abc.part").write_bytes(b"fragment")
                (self.artifacts_dir / "ab" ).mkdir(exist_ok=True)
                (self.artifacts_dir / "ab" / "en-cours.part").write_bytes(b"fragment")
                db.add(
                    EventModel(
                        type="task.completed",
                        occurred_at=NOW,
                        project_id=project.id,
                        task_run_id=run.id,
                        payload={"ok": True},
                    )
                )
                skill = SkillModel(
                    name=f"skill-{uuid4().hex[:8]}",
                    display_name="Skill",
                    kind="documentary",
                    source_kind="manual",
                    created_by_user_id=user.id,
                )
                db.add(skill)
                db.flush()
                self.skill_id = skill.id
                revision_dir = self.skills_dir / skill.id / "1"
                revision_dir.mkdir(parents=True)
                (revision_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
                db.add(
                    SkillRevisionModel(
                        skill_id=skill.id,
                        number=1,
                        fingerprint="f" * 64,
                        kind="documentary",
                        storage_path=str(revision_dir),
                        created_by_user_id=user.id,
                    )
                )
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
                db.add(
                    SecretModel(
                        name="ANCIEN",
                        scope_type="platform",
                        key_id="revoquee0000",
                        ciphertext=token,
                        created_by_user_id=user.id,
                        revoked_at=NOW,
                    )
                )
                db.commit()
        finally:
            engine.dispose()
        return self


@pytest.fixture
def world(tmp_path) -> World:
    return World(tmp_path, suffix="a").populate()


@pytest.fixture
def target(tmp_path) -> World:
    """Cible vide : fichier absent, répertoires absents."""

    return World(tmp_path, suffix="b")


def run(argv, environ, *, stdout=None, stderr=None):
    out = stdout if stdout is not None else io.StringIO()
    err = stderr if stderr is not None else io.StringIO()
    code = main(argv, environ=environ, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def create(world: World, output: Path, *, label: str = "test") -> dict:
    code, out, err = run(
        ["create", "--output", str(output), "--label", label], world.environ
    )
    assert (code, err) == (EXIT_OK, ""), out + err
    return json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))


def restore_args(backup_dir: Path, target: World, *extra: str) -> list[str]:
    return [
        "restore",
        str(backup_dir),
        "--into",
        target.url,
        "--artifacts-dir",
        str(target.artifacts_dir),
        "--skills-dir",
        str(target.skills_dir),
        *extra,
    ]


# --- Aller-retour ----------------------------------------------------------------


def test_create_writes_a_complete_manifest_in_database_then_files_order(world, tmp_path):
    output = tmp_path / "sauvegarde"
    manifest = create(world, output, label="nuit")

    assert manifest["format_version"] == FORMAT_VERSION
    assert manifest["label"] == "nuit"
    assert manifest["product_version"] == (ROOT / "VERSION").read_text().strip() == product_version()
    assert manifest["created_at"].endswith("+00:00")
    database = manifest["database"]
    assert database["dialect"] == "sqlite" and database["file"] == "database.sqlite"
    assert database["alembic_current"] == check_schema_current(
        make_engine(world.url)
    ).current
    assert database["row_counts"]["artifacts"] == 3
    assert database["row_counts"]["secrets"] == 2
    assert database["row_counts"]["skill_revisions"] == 1
    assert VERSION_TABLE not in database["row_counts"]
    assert database["sha256"] == hashlib.sha256((output / "database.sqlite").read_bytes()).hexdigest()
    assert database["bytes"] == (output / "database.sqlite").stat().st_size
    assert manifest["artifact_storage_keys_referenced"] == sorted(world.storage_keys)
    assert world.deleted_storage_key not in manifest["artifact_storage_keys_referenced"]
    assert manifest["secrets_key_ids"] == [world.key_id]
    assert world.vault_key not in json.dumps(manifest)
    assert manifest["source_url_fingerprint"] == url_fingerprint(world.url)
    assert manifest["warnings"] == []
    by_name = {entry["name"]: entry for entry in manifest["directories"]}
    assert by_name["artifacts"]["archive"] == "artifacts.tar"
    assert by_name["artifacts"]["entries"] == 2, "ni tmp/ ni *.part"
    assert by_name["skills"]["entries"] == 1
    with tarfile.open(output / "artifacts.tar") as archive:
        names = [member.name for member in archive.getmembers() if member.isfile()]
    assert sorted(names) == sorted(world.storage_keys)
    assert not any("tmp" in name or name.endswith(".part") for name in names)
    # La base est sauvegardée avant les fichiers : l'instantané est plus ancien que
    # les archives (ordre des écritures sur disque).
    assert (output / "database.sqlite").stat().st_mtime_ns <= (output / "artifacts.tar").stat().st_mtime_ns
    assert (output / "artifacts.tar").stat().st_mtime_ns <= (output / "skills.tar").stat().st_mtime_ns


def test_full_round_trip_preserves_every_table_and_file(world, target, tmp_path):
    output = tmp_path / "sauvegarde"
    before = table_fingerprints(world.url)
    create(world, output)

    code, out, err = run(["verify", str(output)], world.environ)
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Sauvegarde vérifiée" in out

    code, out, err = run(restore_args(output, target), world.environ)
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Contrôles post-restauration conformes" in out
    # Le chemin absolu stocké dans skill_revisions.storage_path n'est pas réécrit :
    # l'opérateur est prévenu, la restauration n'invente pas de relocalisation.
    warnings = [line for line in out.splitlines() if line.startswith("Avertissement")]
    assert len(warnings) == 1 and "non relocalisé" in warnings[0]
    assert str(world.skills_dir) in warnings[0] and str(target.skills_dir) in warnings[0]

    assert table_fingerprints(target.url) == before
    assert _files_of(target.artifacts_dir) == {
        key: key.split("/")[1] for key in world.storage_keys
    }
    assert _files_of(target.skills_dir) == _files_of(world.skills_dir)
    assert check_schema_current(make_engine(target.url)).ok is True
    assert not target.database.with_name(target.database.name + "-wal").exists()


def test_inspect_prints_a_readable_summary(world, tmp_path):
    output = tmp_path / "sauvegarde"
    create(world, output)
    code, out, err = run(["inspect", str(output)], world.environ)
    assert (code, err) == (EXIT_OK, "")
    assert "Base : sqlite" in out and "artifacts : 3" in out
    assert f"Clés de secrets requises : {world.key_id}" in out
    assert "Exécutez « verify »" in out


# --- Écarts et refus -------------------------------------------------------------


def test_missing_blob_is_reported_after_restore(world, target, tmp_path):
    (world.artifacts_dir / world.storage_keys[0]).unlink()
    output = tmp_path / "sauvegarde"
    create(world, output)
    code, out, err = run(restore_args(output, target), world.environ)
    assert code == EXIT_REFUSED
    assert "Restauration effectuée mais écarts constatés" in out
    assert f"livrable cité sans blob : {world.storage_keys[0]}" in out
    assert target.database.exists(), "la base a bien été restaurée, l'écart est signalé"


def test_orphan_blob_and_missing_skill_folder_are_reported(world, target, tmp_path):
    orphan = hashlib.sha256(b"orphelin").hexdigest()
    (world.artifacts_dir / orphan[:2]).mkdir(exist_ok=True)
    (world.artifacts_dir / orphan[:2] / orphan).write_bytes(b"orphelin")
    import shutil

    shutil.rmtree(world.skills_dir / world.skill_id)
    output = tmp_path / "sauvegarde"
    create(world, output)
    code, out, _err = run(restore_args(output, target), world.environ)
    assert code == EXIT_REFUSED
    assert f"blob sans ligne de livrable : {orphan[:2]}/{orphan}" in out
    assert f"révision de skill sans dossier : {world.skill_id}/1" in out


@pytest.mark.parametrize("field", ["database", "artifacts", "revision"])
def test_tampered_backup_is_refused_by_verify_and_restore(world, target, tmp_path, field):
    output = tmp_path / "sauvegarde"
    manifest = create(world, output)
    if field == "database":
        with (output / "database.sqlite").open("ab") as handle:
            handle.write(b"\0")
        expected = "empreinte de database.sqlite"
    elif field == "artifacts":
        manifest["directories"][0]["sha256"] = "0" * 64
        expected = "empreinte de artifacts.tar"
    else:
        manifest["database"]["alembic_current"] = "ffffffffffff"
        expected = "révision Alembic « ffffffffffff » inconnue"
    (output / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    code, _out, err = run(["verify", str(output)], world.environ)
    assert code == EXIT_REFUSED and expected in err
    code, _out, err = run(restore_args(output, target), world.environ)
    assert code == EXIT_REFUSED and expected in err
    assert not target.database.exists() and not target.artifacts_dir.exists()


def test_missing_or_invalid_manifest_is_refused(tmp_path, world):
    empty = tmp_path / "vide"
    empty.mkdir()
    code, _out, err = run(["verify", str(empty)], world.environ)
    assert code == EXIT_REFUSED and "Manifeste introuvable" in err
    (empty / MANIFEST_NAME).write_text('{"format_version": 2}', encoding="utf-8")
    code, _out, err = run(["inspect", str(empty)], world.environ)
    assert code == EXIT_REFUSED and "format 2" in err


def test_restore_refuses_a_non_empty_target_without_replace(world, target, tmp_path):
    output = tmp_path / "sauvegarde"
    create(world, output)
    target.populate()
    before = table_fingerprints(target.url)

    code, _out, err = run(restore_args(output, target), world.environ)
    assert code == EXIT_REFUSED
    assert "Cible non vide" in err and "table(s)" in err and "répertoire artifacts" in err
    assert "--replace --pre-restore-backup" in err
    assert table_fingerprints(target.url) == before
    assert world.vault_key not in err

    code, _out, err = run(restore_args(output, target, "--replace"), world.environ)
    assert code == EXIT_USAGE and "--pre-restore-backup" in err
    code, _out, err = run(
        restore_args(output, target, "--pre-restore-backup", str(tmp_path / "avant")),
        world.environ,
    )
    assert code == EXIT_USAGE


def test_replace_backs_up_the_target_first_then_restores(world, target, tmp_path):
    output = tmp_path / "sauvegarde"
    source_fingerprints = table_fingerprints(world.url)
    create(world, output)
    target.populate()
    target_fingerprints = table_fingerprints(target.url)
    target_files = _files_of(target.artifacts_dir)
    pre_restore = tmp_path / "avant"

    code, out, err = run(
        restore_args(output, target, "--replace", "--pre-restore-backup", str(pre_restore)),
        world.environ,
    )
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Sauvegarde préalable de la cible" in out
    assert "Répertoire mis à l'écart" in out

    pre_manifest = json.loads((pre_restore / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert pre_manifest["label"] == "pre-restore"
    assert pre_manifest["source_url_fingerprint"] == url_fingerprint(target.url)
    assert pre_manifest["artifact_storage_keys_referenced"] == sorted(target.storage_keys)
    code, _out, err = run(["verify", str(pre_restore)], world.environ)
    assert (code, err) == (EXIT_OK, "")
    assert table_fingerprints(target.url) == source_fingerprints
    assert table_fingerprints(target.url) != target_fingerprints

    aside = [p for p in tmp_path.iterdir() if p.name.startswith("artifacts-b.pre-restore-")]
    assert len(aside) == 1 and _files_of(aside[0]) == target_files
    assert _files_of(target.artifacts_dir) == {
        key: key.split("/")[1] for key in world.storage_keys
    }

    # La sauvegarde préalable restaure à son tour l'ancien contenu de la cible.
    third = World(tmp_path, suffix="c")
    code, out, err = run(restore_args(pre_restore, third), target.environ)
    assert (code, err) == (EXIT_OK, ""), out + err
    assert table_fingerprints(third.url) == target_fingerprints


def test_replace_aborts_before_touching_the_target_if_the_pre_backup_fails(
    world, target, tmp_path
):
    output = tmp_path / "sauvegarde"
    create(world, output)
    target.populate()
    before = table_fingerprints(target.url)
    before_files = _files_of(target.artifacts_dir)
    occupied = tmp_path / "occupe"
    occupied.mkdir()
    (occupied / "deja-la.txt").write_text("x", encoding="utf-8")

    code, _out, err = run(
        restore_args(output, target, "--replace", "--pre-restore-backup", str(occupied)),
        world.environ,
    )
    assert code == EXIT_REFUSED and "n'est pas vide" in err
    assert table_fingerprints(target.url) == before
    assert _files_of(target.artifacts_dir) == before_files
    assert not [p for p in tmp_path.iterdir() if ".pre-restore-" in p.name]


def test_restore_refuses_the_source_and_another_dialect(world, tmp_path, monkeypatch):
    output = tmp_path / "sauvegarde"
    create(world, output)
    code, _out, err = run(
        ["restore", str(output), "--into", world.url], world.environ
    )
    assert code == EXIT_REFUSED and "base d'origine" in err
    # Une URL relative désignant le même fichier est la même source.
    monkeypatch.chdir(tmp_path)
    relative = f"sqlite:///./{world.database.name}"
    assert url_fingerprint(relative) == url_fingerprint(world.url)
    code, _out, err = run(
        ["restore", str(output), "--into", relative], world.environ
    )
    assert code == EXIT_REFUSED and "base d'origine" in err
    code, _out, err = run(
        [
            "restore",
            str(output),
            "--into",
            "postgresql+psycopg://acp:secret@127.0.0.1:55432/acp_h4",
            "--artifacts-dir",
            str(tmp_path / "x"),
            "--skills-dir",
            str(tmp_path / "y"),
        ],
        world.environ,
    )
    assert code == EXIT_REFUSED and "Dialecte de la cible (postgresql)" in err
    assert "secret" not in err


def test_secret_key_mismatch_warns_then_refuses_when_required(world, target, tmp_path):
    output = tmp_path / "sauvegarde"
    create(world, output)
    other_key = Fernet.generate_key().decode("ascii")
    environ = {**world.environ, "ACP_SECRETS_KEYS": other_key}

    code, out, err = run(restore_args(output, target), environ)
    assert (code, err) == (EXIT_OK, ""), out + err
    assert f"Avertissement : clés de secrets absentes de ACP_SECRETS_KEYS : {world.key_id}" in out
    assert "revoquee0000" not in out, "une clé révoquée n'est pas exigée"

    strict = World(tmp_path, suffix="strict")
    code, out, err = run(restore_args(output, strict, "--require-secret-keys"), environ)
    assert code == EXIT_REFUSED
    assert f"clés de secrets absentes de ACP_SECRETS_KEYS : {world.key_id}" in out

    unconfigured = World(tmp_path, suffix="sans-coffre")
    code, out, _err = run(
        restore_args(output, unconfigured, "--require-secret-keys"),
        {k: v for k, v in world.environ.items() if k != "ACP_SECRETS_KEYS"},
    )
    assert code == EXIT_REFUSED and world.key_id in out


def _rewrite_archive(output: Path, name: str, mutate) -> None:
    """Réécrit une archive puis aligne le manifeste sur elle (seul le contenu change)."""

    archive_path = output / name
    with tarfile.open(archive_path, "r:") as archive:
        members = [(m, archive.extractfile(m).read() if m.isfile() else None) for m in archive.getmembers()]
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
        for member, payload in members:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
        mutate(archive)
    manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    entry = next(item for item in manifest["directories"] if item["archive"] == name)
    entry["sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    entry["bytes"] = archive_path.stat().st_size
    with tarfile.open(archive_path, "r:") as archive:
        entry["entries"] = sum(1 for m in archive.getmembers() if m.isfile())
    (output / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    "hostile, expected",
    [
        ("../evasion.txt", "remonte au-dessus de la racine"),
        ("/etc/evasion.txt", "chemin absolu"),
        ("C:/evasion.txt", "chemin absolu"),
        ("dossier\\evasion.txt", "séparateur Windows"),
        ("lien", "seuls des fichiers et des répertoires"),
    ],
)
def test_hostile_archive_members_are_refused_before_any_write(
    world, target, tmp_path, hostile, expected
):
    output = tmp_path / "sauvegarde"
    create(world, output)

    def mutate(archive: tarfile.TarFile) -> None:
        if hostile == "lien":
            info = tarfile.TarInfo("lien")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../cible"
            archive.addfile(info)
        else:
            payload = b"evasion"
            info = tarfile.TarInfo(hostile)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    _rewrite_archive(output, "artifacts.tar", mutate)

    code, _out, err = run(["verify", str(output)], world.environ)
    assert code == EXIT_REFUSED and expected in err and "refusé" in err
    code, _out, err = run(restore_args(output, target), world.environ)
    assert code == EXIT_REFUSED and expected in err
    assert not target.database.exists()
    assert not target.artifacts_dir.exists()
    assert not (tmp_path / "evasion.txt").exists()


def test_stale_revision_is_reported_never_migrated(tmp_path):
    world = World(tmp_path, suffix="ancienne").populate(stamp="0001")
    target = World(tmp_path, suffix="b")
    output = tmp_path / "sauvegarde"
    create(world, output)
    code, out, err = run(restore_args(output, target), world.environ)
    assert (code, err) == (EXIT_OK, ""), out + err
    assert "Révision restaurée 0001 antérieure à la tête" in out
    assert "Aucune migration n'est lancée automatiquement" in out
    assert "init_db()" in out
    assert check_schema_current(make_engine(target.url)).current == "0001"


def test_create_refuses_unstamped_tables_non_empty_output_and_missing_url(tmp_path):
    world = World(tmp_path, suffix="brute")
    engine = make_engine(world.url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    output = tmp_path / "sauvegarde"
    code, _out, err = run(["create", "--output", str(output)], world.environ)
    assert code == EXIT_REFUSED and "aucune révision Alembic" in err

    occupied = tmp_path / "occupe"
    occupied.mkdir()
    (occupied / "x").write_text("x", encoding="utf-8")
    code, _out, err = run(["create", "--output", str(occupied)], world.environ)
    assert code == EXIT_REFUSED and "n'est pas vide" in err

    code, _out, err = run(["create", "--output", str(tmp_path / "autre")], {})
    assert code == EXIT_USAGE and "ACP_DATABASE_URL" in err

    code, _out, err = run(
        ["create", "--output", str(tmp_path / "autre")],
        {**world.environ, "ACP_DATABASE_URL": _sqlite_url(tmp_path / "absente.db")},
    )
    assert code == EXIT_FAILURE and "introuvable" in err


def test_usage_errors_exit_2(world):
    code, _out, err = run([], world.environ)
    assert code == EXIT_USAGE
    code, _out, err = run(["restore", "x"], world.environ)
    assert code == EXIT_USAGE and "--into" in err
    code, out, _err = run(["--help"], world.environ)
    assert code == 0 and "create" in out and "restore" in out


def test_unreachable_postgresql_is_a_failure_without_password(world, tmp_path):
    """Une base injoignable est un échec (code 1) dont le message ne cite aucun secret."""

    environ = {
        **world.environ,
        "ACP_BACKUP_PG_DUMP_COMMAND": json.dumps(["pg-dump-absent-h4", "--dbname", "{url}"]),
    }
    code, _out, err = run(
        [
            "create",
            "--output",
            str(tmp_path / "pg"),
            "--database-url",
            "postgresql+psycopg://acp:motdepasse-h4@127.0.0.1:1/acp",
        ],
        environ,
    )
    assert code == EXIT_FAILURE and err.startswith("Échec : ")
    assert "motdepasse-h4" not in err
    assert not (tmp_path / "pg" / "database.pgdump").exists()
    assert backup.snapshot.DOCKER_PG_DUMP_EXAMPLE.startswith('["docker", "exec", "acp-pg"')
