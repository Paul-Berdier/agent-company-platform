"""CLI locale ``acp-poste`` : aucune connexion réseau, aucune commande simulée."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from acp_poste import subscription_quotas
from acp_poste.cli import main as cli_main


@pytest.fixture
def poste_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("ACP_"):
            monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("command", ["start", "register", "doctor", "journal"])
def test_the_cli_offers_no_claim_loop_api_enrolment_nor_unfed_journal(command: str):
    # « journal » lisait un fichier qu'aucun composant du poste n'écrit plus : la
    # commande reviendra en P5 avec son écrivain, pas avant.
    with pytest.raises(SystemExit) as refused:
        cli_main([command])
    assert refused.value.code == 2


def test_the_quota_command_reports_missing_sources_without_inventing_values(
    poste_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "1")
    monkeypatch.setenv("ACP_WORKER_QUOTA_CODEX_EXECUTABLE", str(tmp_path / "absent" / "codex.exe"))
    monkeypatch.setenv("ACP_WORKER_QUOTA_CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT", str(tmp_path / "absent.json"))

    assert cli_main(["quotas"]) == 0
    reports = json.loads(capsys.readouterr().out)

    assert [(report["provider"], report["status"]) for report in reports] == [
        ("codex", "cli_missing"),
        ("claude_code", "unavailable"),
    ]
    assert all(report["windows"] == [] for report in reports)


@pytest.mark.parametrize("agreement", [None, "0"])
def test_the_quota_command_is_refused_in_french_without_the_owner_agreement(
    poste_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    agreement: str | None,
):
    # Fermé par défaut : sans ACP_WORKER_SUBSCRIPTION_QUOTAS=1, ni Codex CLI (qui
    # interroge le serveur d'OpenAI) ni le fichier de la ligne d'état ne sont touchés.
    if agreement is not None:
        monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", agreement)

    async def no_probe(_config):
        pytest.fail("aucune sonde sans l'accord du propriétaire")

    monkeypatch.setattr(subscription_quotas, "probe_codex", no_probe)
    monkeypatch.setattr(subscription_quotas, "probe_claude_code", no_probe)

    assert cli_main(["quotas"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Relevé des quotas refusé" in captured.err
    assert "ACP_WORKER_SUBSCRIPTION_QUOTAS=1" in captured.err


def test_an_invalid_configuration_is_refused_in_french(
    poste_environment: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "oui")

    assert cli_main(["diagnostic"]) == 2
    assert "Configuration du poste refusée" in capsys.readouterr().err
