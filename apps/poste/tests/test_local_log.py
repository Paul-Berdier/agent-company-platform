"""Journal JSONL local gardé pour P5 : aucun écrivain ni lecteur ne l'utilise encore.

La commande ``acp-poste journal`` a été retirée tant qu'aucun composant du poste
n'écrit ce journal ; ces tests couvrent le module seul, que le plan garde.
"""

import json
from pathlib import Path

import pytest

from acp_poste.local_log import LOG_FILENAME, PosteLogger, tail_logs


def test_the_logger_appends_one_json_record_per_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    logger = PosteLogger(tmp_path / "etat")
    logger.write("info", "démarrage", tentative=1)
    logger.write("error", "arrêt")

    lines = (tmp_path / "etat" / LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [(record["level"], record["message"]) for record in records] == [
        ("info", "démarrage"),
        ("error", "arrêt"),
    ]
    assert records[0]["tentative"] == 1
    assert all(record["timestamp"].endswith("+00:00") for record in records)
    assert "démarrage" in lines[0]
    assert capsys.readouterr().out.splitlines() == ["[info] démarrage", "[error] arrêt"]


def test_the_tail_returns_the_last_lines_only(tmp_path: Path):
    logger = PosteLogger(tmp_path)
    for index in range(3):
        logger.write("info", f"message {index}")

    assert [json.loads(line)["message"] for line in tail_logs(tmp_path, 2)] == [
        "message 1",
        "message 2",
    ]
