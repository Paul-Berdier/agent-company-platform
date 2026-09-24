"""Sondes des quotas réels d'abonnement du poste (Codex CLI, Claude Code).

Aucun accès réseau et aucun compte réel : Codex est simulé par un vrai processus
local déterministe (``fake_codex_app_server.py``), dont les réponses sont validées
contre les schémas publiés par Codex CLI 0.156.1 (``fixtures/codex_app_server_0_156_1``).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import signal
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from acp_poste_contrat import SubscriptionQuotaBatch, SubscriptionQuotaReport
from acp_poste import subscription_quotas as quotas
from acp_poste.cli import main as cli_main
from acp_poste.config import PosteConfig, PosteConfigurationError
from acp_poste.executors import ExecutorConfig, ExecutorSpec
from acp_poste.subscription_quotas import (
    API_KEY_VARIABLES,
    SubscriptionQuotaConfig,
    SubscriptionQuotaConfigurationError,
    codex_environment,
    collect_reports,
    probe_claude_code,
    probe_codex,
)

HERE = Path(__file__).resolve().parent
FAKE_SERVER = str(HERE / "fake_codex_app_server.py")
SCHEMAS = HERE / "fixtures" / "codex_app_server_0_156_1"
PYTHON = str(Path(sys.executable).resolve())


def _fake_module():
    spec = importlib.util.spec_from_file_location("fake_codex_app_server", FAKE_SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FAKE = _fake_module()


def quota_config(
    tmp_path: Path,
    mode: str = "ok",
    *,
    extra: str | None = None,
    timeout: float = 20.0,
    command: tuple[str, ...] | None = None,
    home: Path | None = None,
    snapshot: Path | None = None,
    enabled: bool = True,
) -> SubscriptionQuotaConfig:
    profile = home if home is not None else tmp_path / "codex-home"
    profile.mkdir(parents=True, exist_ok=True)
    fake = (PYTHON, "-I", FAKE_SERVER, mode) + ((extra,) if extra is not None else ())
    return SubscriptionQuotaConfig(
        enabled=enabled,
        codex_command=command if command is not None else fake,
        codex_home=profile,
        claude_snapshot_path=snapshot if snapshot is not None else tmp_path / "claude-code.json",
        probe_timeout_seconds=timeout,
    )


def process_is_running(process_id: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
                exit_code.value == 259
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{process_id}/stat")
    if stat.exists() and ") Z " in stat.read_text(encoding="ascii", errors="ignore"):
        return False
    return True


# --------------------------------------------------------------------------
# Sous-ensemble de JSON Schema draft-07 (suffisant pour les schémas copiés)
# --------------------------------------------------------------------------

_JSON_TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: type(value) is int,
    "number": lambda value: type(value) in (int, float),
    "boolean": lambda value: type(value) is bool,
    "null": lambda value: value is None,
}


def schema_errors(value, schema, root=None, path="$") -> list[str]:
    root = schema if root is None else root
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [f"{path} : aucune valeur admise"]
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return schema_errors(value, target, root, path)
    errors: list[str] = []
    if "allOf" in schema:
        for branch in schema["allOf"]:
            errors += schema_errors(value, branch, root, path)
    if "anyOf" in schema:
        branches = [schema_errors(value, branch, root, path) for branch in schema["anyOf"]]
        if all(branches):
            detail = "; ".join(branches[0])
            errors.append(f"{path} : aucune branche anyOf ne correspond ({detail})")
    if "oneOf" in schema:
        matching = [branch for branch in schema["oneOf"] if not schema_errors(value, branch, root, path)]
        if len(matching) != 1:
            errors.append(f"{path} : {len(matching)} branches oneOf correspondent")
    if "type" in schema:
        expected = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_JSON_TYPES[name](value) for name in expected):
            return errors + [f"{path} : type {expected} attendu"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} : valeur hors énumération")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name} : champ requis absent")
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                errors += schema_errors(item, properties[name], root, f"{path}.{name}")
            elif "additionalProperties" in schema:
                errors += schema_errors(item, schema["additionalProperties"], root, f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors += schema_errors(item, schema["items"], root, f"{path}[{index}]")
    return errors


def load_schema(relative: str) -> dict:
    return json.loads((SCHEMAS / relative).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Contrat du faux app-server face aux schémas officiels
# --------------------------------------------------------------------------


def test_the_schema_subset_validator_rejects_what_it_should():
    schema = load_schema("v2/GetAccountRateLimitsResponse.json")
    assert schema_errors({"rateLimits": {}}, schema) == []
    assert schema_errors({}, schema) != []
    broken = FAKE.rate_limits_result("malformed")
    assert any("usedPercent" in error for error in schema_errors(broken, schema))


@pytest.mark.parametrize("mode", ["ok", "single", "legacy", "out-of-range", "notifications"])
def test_fake_rate_limit_responses_follow_the_codex_0_156_1_schema(mode):
    assert schema_errors(FAKE.rate_limits_result(mode), load_schema("v2/GetAccountRateLimitsResponse.json")) == []


@pytest.mark.parametrize("mode", ["ok", "not-signed-in", "api-key"])
def test_fake_account_responses_follow_the_codex_0_156_1_schema(mode):
    assert schema_errors(FAKE.account_result(mode), load_schema("v2/GetAccountResponse.json")) == []


def test_fake_initialize_response_and_envelopes_follow_the_schema():
    assert schema_errors(FAKE.initialize_result(), load_schema("v1/InitializeResponse.json")) == []
    response = {"id": 1, "result": FAKE.initialize_result()}
    assert schema_errors(response, load_schema("JSONRPCResponse.json")) == []
    error = {"id": 3, "error": {"code": -32600, "message": "refusé"}}
    assert schema_errors(error, load_schema("JSONRPCError.json")) == []


def test_the_fields_read_by_the_probe_exist_in_the_official_schema():
    rate_limits = load_schema("v2/GetAccountRateLimitsResponse.json")
    definitions = rate_limits["definitions"]
    assert {"rateLimits", "rateLimitsByLimitId"} <= set(rate_limits["properties"])
    assert {
        "limitId",
        "primary",
        "secondary",
        "credits",
        "planType",
        "rateLimitReachedType",
    } <= set(definitions["RateLimitSnapshot"]["properties"])
    window = definitions["RateLimitWindow"]
    assert window["properties"]["usedPercent"]["type"] == "integer"
    assert window["properties"]["windowDurationMins"]["type"] == ["integer", "null"]
    assert window["properties"]["resetsAt"]["type"] == ["integer", "null"]
    assert set(definitions["CreditsSnapshot"]["properties"]) == {"hasCredits", "unlimited", "balance"}
    assert "prolite" in definitions["PlanType"]["enum"]
    account = load_schema("v2/GetAccountResponse.json")
    chatgpt = next(
        branch
        for branch in account["definitions"]["Account"]["oneOf"]
        if branch["properties"]["type"]["enum"] == ["chatgpt"]
    )
    assert {"planType", "email"} <= set(chatgpt["properties"])


async def test_requests_sent_by_the_probe_follow_the_schema(tmp_path: Path):
    record = tmp_path / "requests.jsonl"
    reports = await probe_codex(quota_config(tmp_path, "record", extra=str(record)))
    assert [report.status for report in reports] == ["ok", "ok"]

    messages = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
    assert [message["method"] for message in messages] == [
        "initialize",
        "initialized",
        "account/read",
        "account/rateLimits/read",
    ]
    initialize, initialized, account, limits = messages
    assert schema_errors(initialize, load_schema("JSONRPCRequest.json")) == []
    assert schema_errors(initialize["params"], load_schema("v1/InitializeParams.json")) == []
    assert schema_errors(initialized, load_schema("ClientNotification.json")) == []
    assert "id" not in initialized
    assert schema_errors(account["params"], load_schema("v2/GetAccountParams.json")) == []
    assert account["params"] == {}
    assert schema_errors(limits, load_schema("JSONRPCRequest.json")) == []
    assert "params" not in limits
    assert all("jsonrpc" not in message for message in messages)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_quotas_are_disabled_by_default_and_use_the_dedicated_locations(tmp_path: Path):
    config = SubscriptionQuotaConfig.from_environ({})
    assert config.enabled is False
    assert config.status() == "disabled"
    assert config.codex_command is None
    assert config.codex_home == Path.home() / ".acp" / "codex-home"
    assert config.claude_snapshot_path == Path.home() / ".acp" / "quotas" / "claude-code.json"


def test_quota_settings_are_read_from_the_environment(tmp_path: Path):
    executable = tmp_path / "codex.exe"
    config = SubscriptionQuotaConfig.from_environ(
        {
            "ACP_WORKER_SUBSCRIPTION_QUOTAS": "1",
            "ACP_WORKER_QUOTA_CODEX_EXECUTABLE": str(executable),
            "ACP_WORKER_QUOTA_CODEX_HOME": str(tmp_path / "profil"),
            "ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT": str(tmp_path / "claude.json"),
        }
    )
    assert config.enabled is True
    assert config.status() == "enabled"
    assert config.codex_command == (str(executable),)
    assert config.codex_home == tmp_path / "profil"
    assert config.claude_snapshot_path == tmp_path / "claude.json"


@pytest.mark.parametrize(
    "setting,value",
    [
        ("ACP_WORKER_SUBSCRIPTION_QUOTAS", "oui"),
        ("ACP_WORKER_SUBSCRIPTION_QUOTAS", "true"),
        ("ACP_WORKER_QUOTA_CODEX_HOME", "profil-relatif"),
        ("ACP_WORKER_QUOTA_CODEX_EXECUTABLE", "codex"),
        ("ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT", "claude.json"),
    ],
)
def test_invalid_quota_settings_are_refused_in_french(setting: str, value: str):
    with pytest.raises(SubscriptionQuotaConfigurationError) as caught:
        SubscriptionQuotaConfig.from_environ({setting: value})
    assert setting in str(caught.value)


def _executor_config(tmp_path: Path) -> ExecutorConfig:
    executable = tmp_path / "tools" / "codex.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"")
    profile = tmp_path / "executor-codex-home"
    profile.mkdir()
    project = tmp_path / "projet"
    project.mkdir()
    return ExecutorConfig(
        codex=ExecutorSpec(executable=executable, auth_directory=profile),
        project_roots={"projet-1": project},
    )


def test_the_codex_executor_profile_is_reused_when_it_exists(tmp_path: Path):
    executors = _executor_config(tmp_path)
    config = SubscriptionQuotaConfig.from_environ(
        {"ACP_WORKER_SUBSCRIPTION_QUOTAS": "1"}, executors=executors
    )
    assert config.codex_command == (str(executors.codex.executable),)
    assert config.codex_home == executors.codex.auth_directory

    with pytest.raises(SubscriptionQuotaConfigurationError, match="ACP_WORKER_CODEX_HOME"):
        SubscriptionQuotaConfig.from_environ(
            {"ACP_WORKER_QUOTA_CODEX_HOME": str(tmp_path / "autre")}, executors=executors
        )


def _clean_poste_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("ACP_"):
            monkeypatch.delenv(name, raising=False)


def test_poste_config_carries_the_quota_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _clean_poste_environment(monkeypatch, tmp_path)
    assert PosteConfig.from_env().subscription_quotas.enabled is False
    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "1")
    assert PosteConfig.from_env().subscription_quotas.enabled is True

    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "2")
    with pytest.raises(PosteConfigurationError, match="ACP_WORKER_SUBSCRIPTION_QUOTAS"):
        PosteConfig.from_env()


def test_the_diagnostic_reports_the_quota_state_without_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _clean_poste_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "1")
    monkeypatch.setenv("ACP_WORKER_CLAUDE_QUOTA_SNAPSHOT", str(tmp_path / "secret-path.json"))

    assert cli_main(["diagnostic"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    # Seul l'accord du relevé est annoncé : aucun réglage qui ne gouverne rien.
    assert report["subscription_quotas"] == "enabled"
    assert "subscription_quota_interval_seconds" not in report
    assert "secret-path" not in output

    monkeypatch.setenv("ACP_WORKER_SUBSCRIPTION_QUOTAS", "0")
    assert cli_main(["diagnostic"]) == 0
    assert json.loads(capsys.readouterr().out)["subscription_quotas"] == "disabled"


def test_the_codex_environment_carries_no_api_key_and_points_to_the_profile(tmp_path: Path):
    source = {
        "PATH": "C:\\outils",
        "SYSTEMROOT": "C:\\Windows",
        "OPENAI_API_KEY": "sk-secret",
        "CODEX_API_KEY": "cx-secret",
        "CODEX_ACCESS_TOKEN": "jeton",
        "ACP_WORKER_REGISTRATION_TOKEN": "enrolement",
        "ACP_GATEWAY_SERVICE_TOKEN": "passerelle",
        "CODEX_HOME": "C:\\profil-personnel",
    }
    environment = codex_environment(tmp_path / "profil", source=source)
    assert set(API_KEY_VARIABLES) == {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"}
    assert not set(API_KEY_VARIABLES) & set(environment)
    assert not any(name.startswith("ACP_") for name in environment)
    assert environment["CODEX_HOME"] == str(tmp_path / "profil")
    assert environment["PATH"] == "C:\\outils"
    assert "secret" not in json.dumps(environment)


# --------------------------------------------------------------------------
# Sonde Codex (vrai processus, faux app-server)
# --------------------------------------------------------------------------


async def test_a_signed_in_profile_gives_one_report_per_counter(tmp_path: Path):
    before = datetime.now(UTC)
    reports = await probe_codex(quota_config(tmp_path, "ok"))
    after = datetime.now(UTC)

    assert [report.limit_id for report in reports] == ["codex", "codex_other"]
    codex, other = reports
    assert codex.status == "ok"
    assert codex.source == "codex_app_server"
    assert codex.plan == "prolite"
    assert [
        (window.key, window.used_percent, window.window_minutes, window.resets_at)
        for window in codex.windows
    ] == [
        ("primary", 42, 300, datetime.fromtimestamp(FAKE.PRIMARY_RESETS_AT, UTC)),
        ("secondary", 7, 10080, datetime.fromtimestamp(FAKE.SECONDARY_RESETS_AT, UTC)),
    ]
    assert codex.credits is not None and codex.credits.model_dump() == {
        "has_credits": False,
        "unlimited": False,
        "balance": None,
    }
    assert (codex.limit_reached, codex.reached_type) == (False, None)
    assert (other.limit_reached, other.reached_type) == (True, "rate_limit_reached")
    assert other.windows[0].used_percent == 100
    assert before <= codex.observed_at <= after
    assert FAKE.EMAIL not in json.dumps([report.model_dump(mode="json") for report in reports])


async def test_the_single_bucket_view_is_used_when_the_multi_bucket_view_is_absent(tmp_path: Path):
    reports = await probe_codex(quota_config(tmp_path, "single"))
    assert [(report.status, report.limit_id) for report in reports] == [("ok", "codex")]


async def test_a_legacy_counter_keeps_its_unknowns_unknown(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "legacy"))
    assert report.status == "ok"
    assert [(w.key, w.used_percent, w.window_minutes, w.resets_at) for w in report.windows] == [
        ("primary", 12, None, None)
    ]
    assert report.credits is None
    assert report.limit_reached is None


async def test_notifications_and_foreign_messages_are_ignored(tmp_path: Path):
    reports = await probe_codex(quota_config(tmp_path, "notifications"))
    assert [report.status for report in reports] == ["ok", "ok"]


async def test_an_unsigned_profile_is_reported_as_not_signed_in(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "not-signed-in"))
    assert report.status == "not_signed_in"
    assert report.limit_id == "probe"
    assert report.windows == []
    assert "codex login" in report.detail
    assert "non connecté" in report.detail


async def test_an_api_key_profile_has_no_subscription_quota(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "api-key"))
    assert report.status == "not_signed_in"
    assert "clé d'API" in report.detail


async def test_a_missing_dedicated_profile_is_not_signed_in_without_spawning(tmp_path: Path):
    witness = tmp_path / "requests.jsonl"
    config = quota_config(tmp_path, "record", extra=str(witness))
    config = SubscriptionQuotaConfig(
        **{**config.__dict__, "codex_home": tmp_path / "profil-absent"}
    )
    (report,) = await probe_codex(config)
    assert report.status == "not_signed_in"
    assert "absent" in report.detail
    assert not witness.exists()


async def test_a_too_old_cli_is_reported_with_its_version(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "old"))
    assert report.status == "cli_too_old"
    assert "0.99.0" in report.detail
    assert "0.100.0" in report.detail


async def test_an_unreadable_version_is_unavailable(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "garbled-version"))
    assert report.status == "unavailable"
    assert "version" in report.detail.lower()


async def test_a_missing_executable_is_cli_missing(tmp_path: Path):
    config = quota_config(tmp_path, command=(str(tmp_path / "absent" / "codex.exe"),))
    (report,) = await probe_codex(config)
    assert report.status == "cli_missing"
    assert "introuvable" in report.detail


async def test_a_cli_absent_from_the_path_is_cli_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    empty = tmp_path / "vide"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    config = SubscriptionQuotaConfig(
        enabled=True, codex_home=tmp_path, claude_snapshot_path=tmp_path / "c.json"
    )
    (report,) = await probe_codex(config)
    assert report.status == "cli_missing"


@pytest.mark.parametrize("mode", ["malformed", "garbage", "crash"])
async def test_a_malformed_exchange_is_unavailable(tmp_path: Path, mode: str):
    (report,) = await probe_codex(quota_config(tmp_path, mode))
    assert report.status == "unavailable"
    assert report.windows == []
    assert "app-server" in report.detail


async def test_an_out_of_range_counter_is_unavailable_without_inventing_a_value(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "out-of-range"))
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert report.windows == []
    assert "used_percent" in report.detail
    assert "« codex »" in report.detail


def test_one_counter_outside_the_contract_fails_the_whole_reading():
    """Aucun compteur transmis à moitié : les derniers relevés réussis restent affichés."""

    valid = FAKE.snapshot("codex", "Codex", 10, 20)
    beyond = FAKE.snapshot("codex_other", "GPT-6 Astra", 140, 20)
    reports = quotas.codex_reports_from_rate_limits(
        {"rateLimits": valid, "rateLimitsByLimitId": {"codex": valid, "codex_other": beyond}},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert [(report.status, report.limit_id, report.plan) for report in reports] == [
        ("unavailable", "probe", "prolite")
    ]
    assert "« codex_other »" in reports[0].detail
    assert "used_percent" in reports[0].detail
    SubscriptionQuotaBatch.model_validate({"reports": [report.model_dump(mode="json") for report in reports]})


def test_too_many_counters_are_refused_rather_than_truncated():
    many = {f"compteur_{index:02d}": FAKE.snapshot(f"compteur_{index:02d}", "C", 1, 1) for index in range(16)}
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": many["compteur_00"], "rateLimitsByLimitId": many},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert (report.status, report.limit_id, report.plan) == ("unavailable", "probe", "prolite")
    assert "16 compteurs" in report.detail

    fifteen = dict(list(many.items())[:15])
    reports = quotas.codex_reports_from_rate_limits(
        {"rateLimits": many["compteur_00"], "rateLimitsByLimitId": fifteen},
        account_plan="prolite",
        observed_at=datetime.now(UTC),
    )
    assert [report.status for report in reports] == ["ok"] * 15


def test_the_unknown_plan_of_the_source_stays_unknown():
    """``PlanType`` de Codex vaut « unknown » quand le serveur ignore l'offre."""

    counter = FAKE.snapshot("codex", "Codex", 10, 20)
    counter["planType"] = "unknown"
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": counter}, account_plan=None, observed_at=datetime.now(UTC)
    )
    assert (report.status, report.plan) == ("ok", None)
    # Comme une offre absente du compteur : celle lue par « account/read » s'applique.
    (from_account,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": counter}, account_plan="prolite", observed_at=datetime.now(UTC)
    )
    assert from_account.plan == "prolite"
    assert quotas._account_plan({"account": {"type": "chatgpt", "planType": "unknown"}}) == (
        None,
        None,
    )
    without_plan = FAKE.snapshot("codex", "Codex", 10, 20)
    del without_plan["planType"]
    (inherited,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": without_plan}, account_plan="unknown", observed_at=datetime.now(UTC)
    )
    assert inherited.plan is None


def test_a_plan_outside_the_contract_is_never_forwarded():
    oversized = FAKE.snapshot("codex", "Codex", 10, 20)
    oversized["planType"] = "p" * 41
    (report,) = quotas.codex_reports_from_rate_limits(
        {"rateLimits": oversized}, account_plan=None, observed_at=datetime.now(UTC)
    )
    assert (report.status, report.limit_id, report.plan) == ("unavailable", "probe", None)
    assert "plan" in report.detail


async def test_a_json_rpc_error_is_unavailable_and_never_echoes_the_server_message(tmp_path: Path):
    (report,) = await probe_codex(quota_config(tmp_path, "rpc-error"))
    assert report.status == "unavailable"
    assert "-32600" in report.detail
    assert FAKE.EMAIL not in report.detail


async def test_a_hanging_app_server_times_out_and_its_process_tree_is_stopped(tmp_path: Path):
    pid_file = tmp_path / "hang.pid"
    started = asyncio.get_running_loop().time()
    (report,) = await asyncio.wait_for(
        probe_codex(quota_config(tmp_path, "hang", extra=str(pid_file), timeout=2)), timeout=30
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert report.status == "unavailable"
    assert "délai" in report.detail
    assert elapsed < 15
    server_pid = int(pid_file.read_text(encoding="ascii"))
    for _ in range(200):
        if not process_is_running(server_pid):
            break
        await asyncio.sleep(0.01)
    try:
        assert not process_is_running(server_pid)
    finally:
        if process_is_running(server_pid):
            os.kill(server_pid, signal.SIGTERM)


async def test_a_hanging_version_check_times_out(tmp_path: Path):
    (report,) = await asyncio.wait_for(
        probe_codex(quota_config(tmp_path, "version-hang", timeout=2)), timeout=30
    )
    assert report.status == "unavailable"
    assert "délai" in report.detail


async def test_the_app_server_runs_in_account_mode_on_the_dedicated_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    for name in API_KEY_VARIABLES:
        monkeypatch.setenv(name, f"secret-{name.lower()}")
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", "secret-enrolement")
    record = tmp_path / "env.json"
    config = quota_config(tmp_path, "env", extra=str(record))
    reports = await probe_codex(config)

    assert [report.status for report in reports] == ["ok", "ok"]
    seen = json.loads(record.read_text(encoding="utf-8"))
    names = {name.upper() for name in seen["names"]}
    assert not {name.upper() for name in API_KEY_VARIABLES} & names
    assert not any(name.startswith("ACP_") for name in names)
    assert seen["codex_home"] == str(config.codex_home)


# --------------------------------------------------------------------------
# Sonde Claude Code (fichier de la ligne d'état)
# --------------------------------------------------------------------------


def _write_snapshot(path: Path, **overrides) -> dict:
    document = {
        "source": "claude-code-statusline",
        "observed_at": (datetime.now(UTC) - timedelta(minutes=3)).replace(microsecond=0).isoformat(),
        "windows": {
            "five_hour": {"used_percentage": 23.5, "resets_at": 1_790_000_000},
            "seven_day": {"used_percentage": None, "resets_at": None},
        },
    }
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


async def test_the_status_line_snapshot_becomes_a_claude_code_report(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    document = _write_snapshot(snapshot)
    report = await probe_claude_code(quota_config(tmp_path, snapshot=snapshot))

    assert report.provider == "claude_code"
    assert report.source == "claude_code_statusline"
    assert report.status == "ok"
    assert report.limit_id == "default"
    assert report.observed_at == datetime.fromisoformat(document["observed_at"])
    assert [(w.key, w.used_percent, w.window_minutes, w.resets_at) for w in report.windows] == [
        ("five_hour", 23.5, 300, datetime.fromtimestamp(1_790_000_000, UTC)),
        ("seven_day", None, 10080, None),
    ]
    assert report.plan is None and report.credits is None and report.limit_reached is None


async def test_a_missing_status_line_snapshot_is_unavailable_with_an_explanation(tmp_path: Path):
    report = await probe_claude_code(quota_config(tmp_path, snapshot=tmp_path / "absent.json"))
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert report.windows == []
    assert "absent" in report.detail
    assert "ligne d'état" in report.detail


@pytest.mark.parametrize(
    "content",
    [
        "{pas du json",
        json.dumps([1, 2]),
        json.dumps({"source": "autre-chose", "observed_at": "2026-09-24T08:00:00+00:00", "windows": {}}),
        json.dumps({"source": "claude-code-statusline", "observed_at": 12, "windows": {}}),
        json.dumps(
            {
                "source": "claude-code-statusline",
                "observed_at": "2026-09-24T08:00:00+00:00",
                "windows": {"five_hour": {"used_percentage": "beaucoup", "resets_at": None}},
            }
        ),
        json.dumps(
            {
                "source": "claude-code-statusline",
                "observed_at": "2026-09-24T08:00:00+00:00",
                "windows": {"five_hour": {"used_percentage": 12, "resets_at": 1e30}},
            }
        ),
    ],
)
async def test_an_unreadable_snapshot_is_unavailable_and_never_raises(tmp_path: Path, content: str):
    snapshot = tmp_path / "claude-code.json"
    snapshot.write_text(content, encoding="utf-8")
    report = await probe_claude_code(quota_config(tmp_path, snapshot=snapshot))
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert report.windows == []


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"observed_at": "2026-09-24T08:00:00"}, "observed_at"),
        ({"observed_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat()}, "observed_at"),
        ({"windows": {"five_hour": {"used_percentage": 150, "resets_at": None}}}, "used_percent"),
    ],
)
async def test_a_snapshot_outside_the_contract_is_unavailable(tmp_path: Path, overrides, field):
    snapshot = tmp_path / "claude-code.json"
    _write_snapshot(snapshot, **overrides)
    report = await probe_claude_code(quota_config(tmp_path, snapshot=snapshot))
    assert (report.status, report.limit_id) == ("unavailable", "probe")
    assert field in report.detail


async def test_an_oversized_or_directory_snapshot_is_unavailable(tmp_path: Path):
    large = tmp_path / "large.json"
    large.write_text(" " * (quotas.MAX_SNAPSHOT_BYTES + 1), encoding="ascii")
    assert (await probe_claude_code(quota_config(tmp_path, snapshot=large))).status == "unavailable"
    directory = tmp_path / "dossier.json"
    directory.mkdir()
    assert (await probe_claude_code(quota_config(tmp_path, snapshot=directory))).status == "unavailable"


# --------------------------------------------------------------------------
# Lot de relevés
# --------------------------------------------------------------------------


async def test_nothing_is_collected_without_the_owner_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    witness = tmp_path / "requests.jsonl"
    snapshot = tmp_path / "claude-code.json"
    _write_snapshot(snapshot)
    config = quota_config(tmp_path, "record", extra=str(witness), snapshot=snapshot, enabled=False)

    async def no_probe(_config: SubscriptionQuotaConfig):
        pytest.fail("aucune sonde sans l'accord du propriétaire")

    monkeypatch.setattr(quotas, "probe_codex", no_probe)
    monkeypatch.setattr(quotas, "probe_claude_code", no_probe)
    with pytest.raises(SubscriptionQuotaConfigurationError, match="ACP_WORKER_SUBSCRIPTION_QUOTAS=1"):
        await collect_reports(config)
    assert not witness.exists()


async def test_collected_reports_form_a_valid_batch(tmp_path: Path):
    snapshot = tmp_path / "claude-code.json"
    _write_snapshot(snapshot)
    reports = await collect_reports(quota_config(tmp_path, "ok", snapshot=snapshot))
    batch = SubscriptionQuotaBatch.model_validate({"reports": reports})
    assert [(report.provider, report.limit_id) for report in batch.reports] == [
        ("codex", "codex"),
        ("codex", "codex_other"),
        ("claude_code", "default"),
    ]
    for report in reports:
        SubscriptionQuotaReport.model_validate(report)
