"""Instantanés physiques (``acp_database.snapshot``) : SQLite, commandes d'outils, refus.

Les cas PostgreSQL réels vivent dans ``apps/api/tests/test_backup_restore_postgresql.py``
; ici, les commandes ``pg_dump``/``pg_restore`` sont remplacées par de petits
programmes Python pour prouver, sans serveur, la capture de la sortie standard,
l'alimentation par l'entrée standard, la substitution du jeton ``{url}`` et
l'absence de tout mot de passe dans les messages.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from acp_database import snapshot
from acp_database.snapshot import (
    DEFAULT_PG_DUMP_COMMAND,
    DEFAULT_PG_RESTORE_COMMAND,
    PG_DUMP_COMMAND_ENV,
    PG_RESTORE_COMMAND_ENV,
    TOOLS_URL_ENV,
    SnapshotError,
    SnapshotToolMissing,
    dump_postgresql,
    dump_sqlite,
    redacted_url,
    render_command,
    restore_postgresql,
    restore_sqlite,
    schema_wipe_postgresql,
    sqlite_database_path,
    tool_command,
    tool_url,
)

PASSWORD = "motdepasse-tres-secret"
PG_URL = f"postgresql+psycopg://acp:{PASSWORD}@127.0.0.1:55432/acp_h4"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _seed(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (x INTEGER)")
    connection.execute("INSERT INTO t VALUES (1)")
    connection.commit()
    connection.close()


def _rows(path: Path) -> list[int]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT x FROM t ORDER BY x")]
    finally:
        connection.close()


# --- SQLite ----------------------------------------------------------------------


def test_dump_sqlite_is_consistent_while_a_write_is_open(tmp_path):
    source = tmp_path / "source.db"
    _seed(source)
    writer = sqlite3.connect(source, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO t VALUES (2)")
    try:
        copy = dump_sqlite(_sqlite_url(source), tmp_path / "out" / "copy.sqlite")
    finally:
        writer.execute("COMMIT")
        writer.close()
    assert copy == tmp_path / "out" / "copy.sqlite"
    assert _rows(copy) == [1], "la transaction non validée ne doit pas figurer dans la copie"
    assert _rows(source) == [1, 2]
    assert copy.read_bytes().startswith(snapshot.SQLITE_HEADER)
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["copy.sqlite"]


def test_dump_sqlite_refuses_memory_and_missing_databases(tmp_path):
    with pytest.raises(SnapshotError, match="mémoire"):
        dump_sqlite("sqlite://", tmp_path / "copy.sqlite")
    with pytest.raises(SnapshotError, match="mémoire"):
        sqlite_database_path("sqlite:///:memory:")
    with pytest.raises(SnapshotError, match="introuvable"):
        dump_sqlite(_sqlite_url(tmp_path / "absente.db"), tmp_path / "copy.sqlite")
    with pytest.raises(SnapshotError, match="SQLite attendue"):
        sqlite_database_path(PG_URL)
    assert not (tmp_path / "copy.sqlite").exists()


def test_restore_sqlite_replaces_atomically_and_drops_sidecars(tmp_path):
    source = tmp_path / "source.db"
    _seed(source)
    copy = dump_sqlite(_sqlite_url(source), tmp_path / "copy.sqlite")
    target = tmp_path / "cible" / "acp.db"
    target.parent.mkdir()
    connection = sqlite3.connect(target)
    connection.execute("CREATE TABLE autre (y INTEGER)")
    connection.commit()
    connection.close()
    stale_wal = Path(str(target) + "-wal")
    stale_wal.write_bytes(b"journal perime")
    Path(str(target) + "-shm").write_bytes(b"")

    assert restore_sqlite(copy, _sqlite_url(target)) == target.resolve()
    assert _rows(target) == [1]
    assert not stale_wal.exists()
    assert not Path(str(target) + "-shm").exists()
    assert sorted(p.name for p in target.parent.iterdir()) == ["acp.db"]


def test_restore_sqlite_refuses_files_that_are_not_databases(tmp_path):
    fake = tmp_path / "faux.sqlite"
    fake.write_bytes(b"pas une base")
    target = tmp_path / "cible.db"
    with pytest.raises(SnapshotError, match="n'est pas une base SQLite"):
        restore_sqlite(fake, _sqlite_url(target))
    assert not target.exists()
    with pytest.raises(SnapshotError, match="introuvable"):
        restore_sqlite(tmp_path / "absent.sqlite", _sqlite_url(target))


# --- Commandes d'outils ------------------------------------------------------------


def test_tool_command_defaults_then_accepts_a_json_argv():
    assert tool_command(PG_DUMP_COMMAND_ENV, DEFAULT_PG_DUMP_COMMAND, {}) == list(
        DEFAULT_PG_DUMP_COMMAND
    )
    docker = ["docker", "exec", "acp-pg", "pg_dump", "--dbname", "{url}"]
    environ = {PG_DUMP_COMMAND_ENV: json.dumps(docker)}
    assert tool_command(PG_DUMP_COMMAND_ENV, DEFAULT_PG_DUMP_COMMAND, environ) == docker


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("pg_dump --dbname {url}", "tableau JSON"),
        ("[]", "non vide"),
        ('["pg_dump", 3]', "chaînes non vides"),
        ('["pg_dump", "--dbname", "acp"]', "jeton {url}"),
    ],
)
def test_tool_command_refuses_malformed_overrides(raw, expected):
    with pytest.raises(SnapshotError, match=expected):
        tool_command(PG_DUMP_COMMAND_ENV, DEFAULT_PG_DUMP_COMMAND, {PG_DUMP_COMMAND_ENV: raw})


def test_tool_url_strips_the_sqlalchemy_driver_and_honours_the_override():
    assert tool_url(PG_URL, {}) == f"postgresql://acp:{PASSWORD}@127.0.0.1:55432/acp_h4"
    container = "postgresql://acp:acp@127.0.0.1:5432/acp_h4"
    assert tool_url(PG_URL, {TOOLS_URL_ENV: container}) == container
    with pytest.raises(SnapshotError, match="PostgreSQL attendue"):
        tool_url("sqlite:///acp.db", {})
    assert render_command(["x", "--dbname", "{url}", "{url}-bis"], "U") == [
        "x",
        "--dbname",
        "U",
        "U-bis",
    ]


def test_redacted_url_never_shows_the_password():
    assert PASSWORD not in redacted_url(PG_URL)
    assert redacted_url(PG_URL).startswith("postgresql+psycopg://acp:***@")


def test_dump_postgresql_refuses_a_missing_binary_citing_docker(tmp_path):
    environ = {
        PG_DUMP_COMMAND_ENV: json.dumps(
            ["binaire-pg-dump-inexistant-h4", "--dbname", "{url}"]
        )
    }
    with pytest.raises(SnapshotToolMissing) as excinfo:
        dump_postgresql(PG_URL, tmp_path / "db.pgdump", environ)
    message = str(excinfo.value)
    assert "introuvable" in message
    assert "docker" in message and PG_DUMP_COMMAND_ENV in message
    assert PASSWORD not in message
    assert not (tmp_path / "db.pgdump").exists()
    assert list(tmp_path.iterdir()) == []


def test_dump_postgresql_failure_message_is_scrubbed(tmp_path):
    program = "import sys; print('echec sur', sys.argv[1], file=sys.stderr); sys.exit(4)"
    environ = {PG_DUMP_COMMAND_ENV: json.dumps([sys.executable, "-c", program, "{url}"])}
    with pytest.raises(SnapshotError) as excinfo:
        dump_postgresql(PG_URL, tmp_path / "db.pgdump", environ)
    message = str(excinfo.value)
    assert "code 4" in message and "echec sur" in message
    assert PASSWORD not in message and "***" in message
    assert not (tmp_path / "db.pgdump").exists()


def test_dump_postgresql_captures_stdout_and_checks_the_custom_header(tmp_path):
    program = (
        "import sys; sys.stdout.buffer.write(b'PGDMP' + sys.argv[1].encode()); "
        "sys.stdout.flush()"
    )
    container = "postgresql://acp:acp@127.0.0.1:5432/acp_h4"
    environ = {
        PG_DUMP_COMMAND_ENV: json.dumps([sys.executable, "-c", program, "{url}"]),
        TOOLS_URL_ENV: container,
    }
    destination = dump_postgresql(PG_URL, tmp_path / "db.pgdump", environ)
    assert destination.read_bytes() == b"PGDMP" + container.encode()
    assert [p.name for p in tmp_path.iterdir()] == ["db.pgdump"]

    text_only = {
        PG_DUMP_COMMAND_ENV: json.dumps(
            [sys.executable, "-c", "print('pas un dump')", "{url}"]
        )
    }
    with pytest.raises(SnapshotError, match="PGDMP"):
        dump_postgresql(PG_URL, tmp_path / "autre.pgdump", text_only)
    assert not (tmp_path / "autre.pgdump").exists()


def test_restore_postgresql_feeds_stdin_and_substitutes_the_url(tmp_path):
    source = tmp_path / "db.pgdump"
    payload = b"PGDMP" + bytes(range(256)) * 3
    source.write_bytes(payload)
    captured = tmp_path / "recu.bin"
    seen_url = tmp_path / "url.txt"
    program = (
        "import sys, pathlib; "
        "pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read()); "
        "pathlib.Path(sys.argv[2]).write_text(sys.argv[3], encoding='utf-8')"
    )
    environ = {
        PG_RESTORE_COMMAND_ENV: json.dumps(
            [sys.executable, "-c", program, str(captured), str(seen_url), "{url}"]
        )
    }
    restore_postgresql(source, PG_URL, environ)
    assert captured.read_bytes() == payload
    assert seen_url.read_text(encoding="utf-8") == f"postgresql://acp:{PASSWORD}@127.0.0.1:55432/acp_h4"

    failing = {
        PG_RESTORE_COMMAND_ENV: json.dumps(
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read(); sys.exit(1)", "{url}"]
        )
    }
    with pytest.raises(SnapshotError) as excinfo:
        restore_postgresql(source, PG_URL, failing)
    assert "pg_restore a échoué (code 1)" in str(excinfo.value)
    assert PASSWORD not in str(excinfo.value)

    not_a_dump = tmp_path / "texte.pgdump"
    not_a_dump.write_bytes(b"bonjour")
    with pytest.raises(SnapshotError, match="format custom"):
        restore_postgresql(not_a_dump, PG_URL, environ)
    assert tool_command(PG_RESTORE_COMMAND_ENV, DEFAULT_PG_RESTORE_COMMAND, {})[0] == "pg_restore"


def test_schema_wipe_refuses_a_sqlite_url(tmp_path):
    source = tmp_path / "source.db"
    _seed(source)
    with pytest.raises(SnapshotError, match="exige une URL PostgreSQL"):
        schema_wipe_postgresql(_sqlite_url(source))
    assert _rows(source) == [1]
