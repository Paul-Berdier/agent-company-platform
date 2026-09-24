"""Ligne d'état Claude Code livrée avec le poste (``python -m acp_poste.claude_statusline``).

Le module est exercé comme Claude Code le lance : un vrai processus Python qui reçoit
le JSON de session sur son entrée standard. L'entrée de référence reprend la forme
documentée par Claude Code (https://code.claude.com/docs/en/statusline), y compris
des champs que le relevé ne doit jamais recopier (session, transcription, coût,
limite de dépense d'une passerelle).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

import acp_poste
from acp_poste import claude_statusline as statusline
from acp_poste.subscription_quotas import SubscriptionQuotaConfig, probe_claude_code

WORKER_SOURCES = Path(acp_poste.__file__).resolve().parents[1]
PYTHON = str(Path(sys.executable).resolve())
FIVE_HOUR_RESETS_AT = 1_790_000_000
SEVEN_DAY_RESETS_AT = 1_790_400_000


def session(**overrides) -> dict:
    """JSON de session tel que Claude Code le transmet à la ligne d'état."""

    payload = {
        "cwd": "C:/Users/titulaire/projets/plateforme",
        "session_id": "session-secrete-0f3a",
        "transcript_path": "C:/Users/titulaire/.claude/projects/x/transcript.jsonl",
        "model": {"id": "claude-opus-5-5", "display_name": "Opus"},
        "workspace": {
            "current_dir": "C:/Users/titulaire/projets/plateforme",
            "project_dir": "C:/Users/titulaire/projets/plateforme",
        },
        "version": "2.1.278",
        "cost": {"total_cost_usd": 0.01234, "total_duration_ms": 45000},
        "context_window": {"used_percentage": 8, "remaining_percentage": 92},
        "rate_limits": {
            "five_hour": {"used_percentage": 23.5, "resets_at": FIVE_HOUR_RESETS_AT},
            "seven_day": {"used_percentage": 41.2, "resets_at": SEVEN_DAY_RESETS_AT},
            "spend_limit": {"used_percentage": 162.8, "resets_at": 1_790_800_000},
        },
    }
    payload.update(overrides)
    return payload


def run_statusline(
    stdin: bytes | str | dict,
    snapshot: Path | None,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if isinstance(stdin, dict):
        stdin = json.dumps(stdin)
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in {statusline.SNAPSHOT_ENV, "PYTHONPATH"}
    }
    env["PYTHONPATH"] = str(WORKER_SOURCES)
    if snapshot is not None:
        env[statusline.SNAPSHOT_ENV] = str(snapshot)
    env.update(environment or {})
    return subprocess.run(
        [PYTHON, "-m", "acp_poste.claude_statusline", *arguments],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def test_the_status_line_records_only_the_subscription_windows(tmp_path: Path):
    snapshot = tmp_path / "quotas" / "claude-code.json"
    before = datetime.now(UTC).replace(microsecond=0)
    completed = run_statusline(session(), snapshot)
    after = datetime.now(UTC)

    assert completed.returncode == 0, completed.stderr
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    assert set(document) == {"source", "observed_at", "windows"}
    assert document["source"] == "claude-code-statusline"
    assert before <= datetime.fromisoformat(document["observed_at"]) <= after
    assert document["windows"] == {
        "five_hour": {"used_percentage": 23.5, "resets_at": FIVE_HOUR_RESETS_AT},
        "seven_day": {"used_percentage": 41.2, "resets_at": SEVEN_DAY_RESETS_AT},
    }
    raw = snapshot.read_text(encoding="utf-8")
    for secret in ("session-secrete", "transcript", "titulaire", "cost", "spend_limit", "Opus"):
        assert secret not in raw
    assert [path.name for path in snapshot.parent.iterdir()] == ["claude-code.json"]

    line = completed.stdout.decode("utf-8")
    assert "\n" not in line.strip()
    assert "Opus" in line and "plateforme" in line
    assert "5 h : 23,5 % utilisés" in line
    assert "7 j : 41,2 % utilisés" in line


def test_the_default_location_is_the_one_the_worker_reads(tmp_path: Path):
    assert statusline.default_snapshot_path() == Path.home() / ".acp" / "quotas" / "claude-code.json"
    assert SubscriptionQuotaConfig().claude_snapshot_path == statusline.default_snapshot_path()
    completed = run_statusline(
        session(), None, environment={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)}
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / ".acp" / "quotas" / "claude-code.json").is_file()


async def test_the_written_file_is_read_back_by_the_worker_probe(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    assert run_statusline(session(), snapshot).returncode == 0
    report = await probe_claude_code(
        SubscriptionQuotaConfig(enabled=True, codex_home=tmp_path, claude_snapshot_path=snapshot)
    )
    assert (report.status, report.limit_id) == ("ok", "default")
    assert [(w.key, w.used_percent, w.window_minutes, w.resets_at) for w in report.windows] == [
        ("five_hour", 23.5, 300, datetime.fromtimestamp(FIVE_HOUR_RESETS_AT, UTC)),
        ("seven_day", 41.2, 10080, datetime.fromtimestamp(SEVEN_DAY_RESETS_AT, UTC)),
    ]


def test_nothing_is_written_before_claude_code_sends_rate_limits(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    snapshot.write_text('{"ancien": true}', encoding="utf-8")
    without = session()
    del without["rate_limits"]
    for payload in (without, session(rate_limits={}), session(rate_limits={"spend_limit": {}})):
        completed = run_statusline(payload, snapshot)
        assert completed.returncode == 0, completed.stderr
        assert "quotas d'abonnement non transmis par Claude Code" in completed.stdout.decode("utf-8")
    assert snapshot.read_text(encoding="utf-8") == '{"ancien": true}'


def test_a_missing_or_unreadable_value_stays_unknown(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    limits = {
        "five_hour": {"used_percentage": 140, "resets_at": "demain"},
        "seven_day": {"used_percentage": True, "resets_at": 1e30},
    }
    completed = run_statusline(session(rate_limits=limits), snapshot)
    assert completed.returncode == 0, completed.stderr
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    assert document["windows"] == {
        "five_hour": {"used_percentage": None, "resets_at": None},
        "seven_day": {"used_percentage": None, "resets_at": None},
    }
    assert "5 h : Inconnu" in completed.stdout.decode("utf-8")

    only_five_hours = {"five_hour": {"used_percentage": 12, "resets_at": None}}
    assert run_statusline(session(rate_limits=only_five_hours), snapshot).returncode == 0
    assert json.loads(snapshot.read_text(encoding="utf-8"))["windows"] == {
        "five_hour": {"used_percentage": 12, "resets_at": None}
    }


@pytest.mark.parametrize("stdin", [b"", b"{pas du json", b"[1, 2]", b"\xff\xfe"])
def test_an_unreadable_input_never_breaks_the_status_line(tmp_path: Path, stdin: bytes):
    snapshot = tmp_path / "claude-code.json"
    completed = run_statusline(stdin, snapshot)
    assert completed.returncode == 0
    assert completed.stdout
    assert not snapshot.exists()


def test_an_existing_status_line_keeps_its_display(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    existing = (
        "import sys; data = sys.stdin.buffer.read(); "
        "sys.stdout.write('ma ligne ' + str(len(data)))"
    )
    payload = json.dumps(session()).encode("utf-8")
    completed = run_statusline(payload, snapshot, "--", PYTHON, "-c", existing)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.decode("utf-8") == f"ma ligne {len(payload)}"
    assert json.loads(snapshot.read_text(encoding="utf-8"))["windows"]["five_hour"] == {
        "used_percentage": 23.5,
        "resets_at": FIVE_HOUR_RESETS_AT,
    }


def test_a_failing_existing_status_line_is_reported_not_hidden(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    missing = str(tmp_path / "absente" / "statusline.exe")
    completed = run_statusline(session(), snapshot, "--", missing)
    assert completed.returncode == 0
    line = completed.stdout.decode("utf-8")
    assert "5 h : 23,5 % utilisés" in line
    assert "ligne d'état existante en échec" in line
    assert snapshot.is_file()


def test_an_unexpected_argument_is_refused_in_french(tmp_path: Path):
    completed = run_statusline(session(), tmp_path / "claude-code.json", "--aide")
    assert completed.returncode == 0
    assert "argument refusé" in completed.stdout.decode("utf-8")


def test_a_relative_snapshot_setting_is_refused_without_writing(tmp_path: Path):
    completed = run_statusline(
        session(),
        None,
        environment={statusline.SNAPSHOT_ENV: "quotas/claude-code.json"},
    )
    assert completed.returncode == 0
    assert statusline.SNAPSHOT_ENV in completed.stdout.decode("utf-8")
    assert "relevé non enregistré" in completed.stdout.decode("utf-8")


# --------------------------------------------------------------------------
# Écriture atomique
# --------------------------------------------------------------------------


def _snapshot(used: float) -> dict:
    return {
        "source": statusline.SNAPSHOT_SOURCE,
        "observed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "windows": {"five_hour": {"used_percentage": used, "resets_at": None}},
    }


def test_a_failed_replacement_keeps_the_previous_file_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "claude-code.json"
    assert statusline.write_snapshot(target, _snapshot(10))
    previous = target.read_bytes()

    def refuse(*_args, **_kwargs):
        raise PermissionError("fichier ouvert par un lecteur")

    monkeypatch.setattr(statusline.os, "replace", refuse)
    monkeypatch.setattr(statusline, "REPLACE_RETRY_SECONDS", 0.0)
    assert statusline.write_snapshot(target, _snapshot(90)) is False
    assert target.read_bytes() == previous
    assert [path.name for path in tmp_path.iterdir()] == ["claude-code.json"]


def test_temporary_files_left_by_an_interrupted_run_are_removed(tmp_path: Path):
    target = tmp_path / "claude-code.json"
    old = tmp_path / ".claude-code.json.abandonne.tmp"
    recent = tmp_path / ".claude-code.json.en-cours.tmp"
    unrelated = tmp_path / "autre.tmp"
    for path in (old, recent, unrelated):
        path.write_text("{", encoding="utf-8")
    ancient = time.time() - statusline.STALE_TEMPORARY_SECONDS - 60
    os.utime(old, (ancient, ancient))

    assert statusline.write_snapshot(target, _snapshot(33))
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        ["claude-code.json", recent.name, unrelated.name]
    )
