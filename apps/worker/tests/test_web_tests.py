"""Tests de l'exécution de tests web (Playwright) par le worker.

Aucun navigateur, aucun réseau : l'API est simulée par ``httpx.MockTransport`` et
le runner est un vrai processus local déterministe
(``fake_playwright_runner.py``) lancé par ``sys.executable``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

from acp_contracts import EvidenceCreate, TestIngestRequest
from acp_worker.capabilities import detect_capabilities
from acp_worker.config import WorkerConfig
from acp_worker.local_log import WorkerLogger
from acp_worker.local_runner import LocalRunnerConfig
from acp_worker.main import process
from acp_worker.state import WorkerCredentials
from acp_worker.web_tests import (
    DEFAULT_MAX_ARTIFACT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    REPORT_FILENAME,
    AttachmentRefused,
    WebTestConfig,
    WebTestConfigurationError,
    WebTestLease,
    WorkerTestApi,
    mission_requests_web_tests,
    resolve_attachment,
    run_web_tests,
    web_tests_available,
)


PYTHON = str(Path(sys.executable).resolve())
FAKE_RUNNER = str(Path(__file__).with_name("fake_playwright_runner.py").resolve())
SECRET = "MOT-DE-PASSE-E2E-ULTRA-SECRET"


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------


def process_is_running(process_id: int) -> bool:
    """Vrai tant que le PID désigne un processus vivant et non zombie."""

    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            return bool(
                kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ) and (exit_code.value == 259)
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


def symlinks_supported(tmp_path: Path) -> bool:
    probe = tmp_path / "sonde-lien"
    cible = tmp_path / "sonde-cible"
    cible.write_text("x", encoding="utf-8")
    try:
        os.symlink(cible, probe)
    except (OSError, NotImplementedError, AttributeError):
        return False
    probe.unlink()
    return True


def web_test_config(
    tmp_path: Path,
    *,
    mode: str = "full",
    extra: str | None = None,
    enabled: bool = True,
    timeout_seconds: float = 30.0,
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
    environment_allowlist: tuple[str, ...] = (),
) -> WebTestConfig:
    cwd = tmp_path / "projet"
    cwd.mkdir(parents=True, exist_ok=True)
    argv = [PYTHON, "-I", FAKE_RUNNER, mode]
    if extra is not None:
        argv.append(extra)
    return WebTestConfig(
        enabled=enabled,
        argv=tuple(argv),
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_artifact_bytes=max_artifact_bytes,
        environment_allowlist=environment_allowlist,
    )


def web_test_lease(tmp_path: Path, *, attempt_number: int = 1) -> WebTestLease:
    return WebTestLease(
        worker_id="worker-1",
        task_run_id="run-1",
        attempt_number=attempt_number,
        fencing_token=9,
        project_id="project-1",
        output_root=tmp_path / "runs",
    )


class RecordingApi:
    """Transport API réel (``WorkerTestApi``) branché sur un MockTransport."""

    def __init__(self, *, quota_error: bool = False) -> None:
        self.uploads: list[dict] = []
        self.ingested: list[dict] = []
        self.quota_error = quota_error
        self._next_artifact = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/workers/worker-1/artifacts/content":
            assert request.headers["x-attempt-fencing-token"] == "9"
            body = request.content
            self.uploads.append(
                {
                    "size": len(body),
                    "content": body,
                    "content_type": request.headers.get("content-type", ""),
                }
            )
            if self.quota_error:
                return httpx.Response(413, json={"detail": "quota du run dépassé"})
            self._next_artifact += 1
            return httpx.Response(
                201,
                json={
                    "id": f"artifact-{self._next_artifact}",
                    "project_id": "project-1",
                    "task_run_id": "run-1",
                    "kind": "test_attachment",
                    "stream_kind": "screenshot",
                    "original_name": "piece.png",
                    "content_type": "application/octet-stream",
                    "size_bytes": len(body),
                    "checksum": "0" * 64,
                    "source": "playwright",
                    "has_content": True,
                    "created_at": "2026-09-12T08:00:00Z",
                },
            )
        if path == "/workers/worker-1/test-runs":
            assert request.headers["x-attempt-fencing-token"] == "9"
            body = json.loads(request.content.decode("utf-8"))
            self.ingested.append(body)
            return httpx.Response(
                201,
                json={
                    "id": "test-run-1",
                    "task_run_id": "run-1",
                    "project_id": "project-1",
                    "worker_id": "worker-1",
                    "runner": "playwright",
                    "runner_version": body.get("runner_version", ""),
                    "status": "completed",
                    "started_at": "2026-09-12T08:00:00Z",
                    "finished_at": "2026-09-12T08:00:42Z",
                    "duration_ms": 42000,
                    "totals": {},
                    "exit_code": body.get("exit_code"),
                    "config": {},
                    "case_count": len(
                        [
                            event
                            for event in body["events"]
                            if event["kind"] == "test_end"
                        ]
                    ),
                    "cases": [],
                    "report_artifact": None,
                },
            )
        raise AssertionError(f"route API inattendue: {path}")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            headers={"Authorization": "Bearer worker-token", "X-Worker-Id": "worker-1"},
        )


async def execute(
    tmp_path: Path,
    *,
    config: WebTestConfig,
    api: RecordingApi | None = None,
    lease: WebTestLease | None = None,
    mission: dict | None = None,
):
    recorder = api or RecordingApi()
    async with recorder.client() as client:
        return await run_web_tests(
            mission,
            config,
            api=WorkerTestApi(client, "https://api.test", "worker-1"),
            lease=lease or web_test_lease(tmp_path),
        )


def mission_with_web_tests() -> dict:
    return {
        "id": "task-1",
        "objective": "Vérifier le parcours d'achat",
        "expected_outcome": "La suite Playwright passe",
        "acceptance_criteria": ["suite verte"],
        "autonomy": {
            "mode": "supervised",
            "allowed_actions": [],
            "forbidden_actions": [],
            "approval_required_actions": [],
        },
        "resources": [
            {
                "kind": "web_test_suite",
                "identifier": "tests/panier.spec.ts",
                "access": "read",
                "description": "Suite Playwright du panier",
            }
        ],
        "budget": {
            "max_cost": 0,
            "currency": "EUR",
            "max_tokens": None,
            "max_tool_calls": 1,
        },
        "duration_seconds": 120,
    }


# --------------------------------------------------------------------------
# Frontières structurelles
# --------------------------------------------------------------------------


def test_the_module_only_spawns_through_the_runner_fence():
    """Règle non négociable : jamais de shell, jamais de spawn hors clôture."""

    import acp_worker.web_tests as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "create_subprocess_exec" not in source
    assert "create_subprocess_shell" not in source
    assert "shell=True" not in source
    assert "subprocess.run" not in source
    assert "os.system" not in source
    assert "spawn_fenced_process" in source
    assert "terminate_process_tree" in source


def test_the_test_process_never_receives_a_platform_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from acp_worker.web_tests import web_test_environment

    monkeypatch.setenv("ACP_GATEWAY_SERVICE_TOKEN", "secret-gateway")
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", "secret-enrolement")
    monkeypatch.setenv("HERMES_API_KEY", "secret-hermes")
    output = tmp_path / "sortie"

    environment, injected = web_test_environment(web_test_config(tmp_path), output)

    assert injected == {}
    for name in (
        "ACP_GATEWAY_SERVICE_TOKEN",
        "ACP_WORKER_REGISTRATION_TOKEN",
        "HERMES_API_KEY",
    ):
        assert name not in environment
    assert "secret-" not in json.dumps(environment, ensure_ascii=False)
    assert environment["ACP_REPORT_FILE"] == str(output / REPORT_FILENAME)
    assert environment["PLAYWRIGHT_HTML_OPEN"] == "never"


def test_a_platform_secret_can_never_be_allowlisted(tmp_path: Path):
    with pytest.raises(WebTestConfigurationError, match="interdit"):
        web_test_config(
            tmp_path, environment_allowlist=("HERMES_SERVICE_TOKEN",)
        )


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_web_test_configuration_is_disabled_by_default():
    config = WebTestConfig.from_environ({})

    assert config.enabled is False
    assert config.argv == ()
    assert config.cwd is None
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.max_artifact_bytes == DEFAULT_MAX_ARTIFACT_BYTES
    assert config.status() == "disabled"
    assert config.configured is False


def test_web_test_configuration_reads_the_documented_variables(tmp_path: Path):
    cwd = tmp_path / "projet"
    cwd.mkdir()
    config = WebTestConfig.from_environ(
        {
            "ACP_WORKER_WEBTEST_ENABLED": "1",
            "ACP_WORKER_WEBTEST_ARGV_JSON": json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"]),
            "ACP_WORKER_WEBTEST_CWD": str(cwd),
            "ACP_WORKER_WEBTEST_TIMEOUT_SECONDS": "120",
            "ACP_WORKER_WEBTEST_MAX_ARTIFACT_BYTES": "1024",
            "ACP_WORKER_WEBTEST_ENV_ALLOWLIST": "E2E_USER, E2E_PASSWORD ,E2E_USER",
        }
    )

    assert config.enabled is True
    assert config.argv[0] == PYTHON
    assert config.cwd == cwd.resolve()
    assert config.timeout_seconds == 120
    assert config.max_artifact_bytes == 1024
    assert config.environment_allowlist == ("E2E_USER", "E2E_PASSWORD")
    assert config.configured is True
    assert config.status() == "enabled"


@pytest.mark.parametrize(
    "environ, message",
    [
        ({"ACP_WORKER_WEBTEST_ENABLED": "oui"}, "0 ou 1"),
        (
            {"ACP_WORKER_WEBTEST_ENABLED": "1"},
            "ACP_WORKER_WEBTEST_ARGV_JSON",
        ),
        (
            {
                "ACP_WORKER_WEBTEST_ENABLED": "1",
                "ACP_WORKER_WEBTEST_ARGV_JSON": "pas du json",
                "ACP_WORKER_WEBTEST_CWD": "/tmp",
            },
            "JSON",
        ),
        (
            {
                "ACP_WORKER_WEBTEST_ENABLED": "1",
                "ACP_WORKER_WEBTEST_ARGV_JSON": json.dumps(["node", "cli.js"]),
                "ACP_WORKER_WEBTEST_CWD": "/tmp",
            },
            "absolu",
        ),
        (
            {
                "ACP_WORKER_WEBTEST_ENABLED": "1",
                "ACP_WORKER_WEBTEST_ARGV_JSON": json.dumps([PYTHON]),
                "ACP_WORKER_WEBTEST_CWD": "chemin/relatif",
            },
            "absolu",
        ),
    ],
)
def test_web_test_configuration_refuses_incomplete_or_unsafe_settings(environ, message):
    with pytest.raises(WebTestConfigurationError, match=message):
        WebTestConfig.from_environ(environ)


def test_web_test_timeout_is_bounded(tmp_path: Path):
    cwd = tmp_path / "projet"
    cwd.mkdir()
    base = {
        "ACP_WORKER_WEBTEST_ENABLED": "1",
        "ACP_WORKER_WEBTEST_ARGV_JSON": json.dumps([PYTHON]),
        "ACP_WORKER_WEBTEST_CWD": str(cwd),
    }

    with pytest.raises(WebTestConfigurationError):
        WebTestConfig.from_environ({**base, "ACP_WORKER_WEBTEST_TIMEOUT_SECONDS": "0"})
    with pytest.raises(WebTestConfigurationError):
        WebTestConfig.from_environ(
            {
                **base,
                "ACP_WORKER_WEBTEST_TIMEOUT_SECONDS": str(MAX_TIMEOUT_SECONDS + 1),
            }
        )
    accepted = WebTestConfig.from_environ(
        {**base, "ACP_WORKER_WEBTEST_TIMEOUT_SECONDS": str(MAX_TIMEOUT_SECONDS)}
    )
    assert accepted.timeout_seconds == MAX_TIMEOUT_SECONDS


def test_web_test_environment_allowlist_refuses_platform_secrets(tmp_path: Path):
    cwd = tmp_path / "projet"
    cwd.mkdir()

    with pytest.raises(WebTestConfigurationError, match="interdit"):
        WebTestConfig.from_environ(
            {
                "ACP_WORKER_WEBTEST_ENABLED": "1",
                "ACP_WORKER_WEBTEST_ARGV_JSON": json.dumps([PYTHON]),
                "ACP_WORKER_WEBTEST_CWD": str(cwd),
                "ACP_WORKER_WEBTEST_ENV_ALLOWLIST": "ACP_GATEWAY_SERVICE_TOKEN",
            }
        )


def test_worker_config_exposes_the_web_test_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cwd = tmp_path / "projet"
    cwd.mkdir()
    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "1")
    monkeypatch.setenv(
        "ACP_WORKER_WEBTEST_ARGV_JSON", json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"])
    )
    monkeypatch.setenv("ACP_WORKER_WEBTEST_CWD", str(cwd))

    config = WorkerConfig.from_env()

    assert config.web_tests.enabled is True
    assert config.web_tests.cwd == cwd.resolve()


# --------------------------------------------------------------------------
# Capacité, doctor et routage
# --------------------------------------------------------------------------


def test_capability_requires_a_complete_configuration_and_real_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cwd = tmp_path / "projet"
    cwd.mkdir()
    monkeypatch.delenv("ACP_WORKER_WEBTEST_ENABLED", raising=False)
    monkeypatch.delenv("ACP_WORKER_WEBTEST_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_WEBTEST_CWD", raising=False)
    monkeypatch.setenv("ACP_WORKER_SIMULATION", "0")
    assert "web_tests" not in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "1")
    monkeypatch.setenv(
        "ACP_WORKER_WEBTEST_ARGV_JSON", json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"])
    )
    assert "web_tests" not in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_WEBTEST_CWD", str(cwd))
    assert "web_tests" in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_SIMULATION", "1")
    assert "web_tests" not in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_SIMULATION", "0")
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "0")
    assert "web_tests" not in detect_capabilities()


def test_doctor_reports_the_web_test_capability(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from acp_worker.cli import main as cli_main

    cwd = tmp_path / "projet"
    cwd.mkdir()
    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "1")
    monkeypatch.setenv(
        "ACP_WORKER_WEBTEST_ARGV_JSON", json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"])
    )
    monkeypatch.setenv("ACP_WORKER_WEBTEST_CWD", str(cwd))
    monkeypatch.setenv("ACP_WORKER_WEBTEST_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENV_ALLOWLIST", "E2E_USER,E2E_PASSWORD")
    # Le mode effectif fait partie du diagnostic : « enabled » ne peut être
    # publié que dans le mode où la capacité est réellement annoncée.
    monkeypatch.setenv("ACP_WORKER_SIMULATION", "0")
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("hors ligne")),
    )
    monkeypatch.setattr(
        "acp_worker.cli.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("hors ligne")),
    )

    assert cli_main(["doctor"]) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["web_tests"] == "enabled"
    # Un état « enabled » que l'enregistrement n'annoncerait pas serait un faux
    # diagnostic : les deux champs disent la même chose ou aucun.
    assert "web_tests" in report["capabilities"]
    assert report["web_tests_argv"] == [PYTHON, "-I", FAKE_RUNNER, "green"]
    assert report["web_tests_cwd"] == str(cwd.resolve())
    assert report["web_tests_timeout_seconds"] == 600
    # Les noms allowlistés peuvent désigner un secret : seul le compte est publié.
    assert report["web_tests_env_allowlist"] == 2

    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "0")
    assert cli_main(["doctor"]) == 1
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["web_tests"] == "disabled"
    assert "web_tests_argv" not in disabled


def test_doctor_never_claims_a_capability_it_would_not_announce(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Configuration complète mais mode simulé : l'état le dit, sans mentir."""

    from acp_worker.cli import main as cli_main

    cwd = tmp_path / "projet"
    cwd.mkdir()
    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "1")
    monkeypatch.setenv(
        "ACP_WORKER_WEBTEST_ARGV_JSON", json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"])
    )
    monkeypatch.setenv("ACP_WORKER_WEBTEST_CWD", str(cwd))
    monkeypatch.setenv("ACP_WORKER_SIMULATION", "1")
    monkeypatch.setattr(
        "acp_worker.cli.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("hors ligne")),
    )

    assert cli_main(["doctor"]) == 1
    report = json.loads(capsys.readouterr().out)

    assert "web_tests" not in report["capabilities"]
    assert report["web_tests"] == "enabled_not_announced"


def test_registering_in_real_mode_announces_the_web_test_capability(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """``register --real`` enregistre ``simulation=False`` : l'annonce suit.

    Lire ``ACP_WORKER_SIMULATION`` au lieu du mode effectivement enregistré
    produisait un worker déclaré réel qui n'annonçait jamais ``web_tests`` : ses
    missions ``web_test_suite`` repartaient silencieusement vers le programme
    local du Lot C.
    """

    import argparse

    from acp_worker.cli import _register

    cwd = tmp_path / "projet"
    cwd.mkdir()
    monkeypatch.setenv("ACP_WORKER_WEBTEST_ENABLED", "1")
    monkeypatch.setenv(
        "ACP_WORKER_WEBTEST_ARGV_JSON", json.dumps([PYTHON, "-I", FAKE_RUNNER, "green"])
    )
    monkeypatch.setenv("ACP_WORKER_WEBTEST_CWD", str(cwd))
    monkeypatch.setenv("ACP_WORKER_SIMULATION", "1")

    sent: dict = {}

    class _Response:
        status_code = 201

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "worker_id": "worker-1",
                "token": "worker-token",
                "token_expires_at": "2026-09-13T08:00:00Z",
                "heartbeat_interval_seconds": 30,
            }

    def _post(url, **kwargs):
        sent.update(kwargs["json"])
        return _Response()

    monkeypatch.setattr("acp_worker.cli.httpx.post", _post)

    config = WorkerConfig(
        api_url="https://api.example",
        gateway_url="https://gateway.example",
        gateway_service_token=None,
        provider_id="hermes",
        poll_interval=2.0,
        step_seconds=0.0,
        state_dir=tmp_path / "state",
        name="test-worker",
        max_concurrency=1,
        simulation=True,
        registration_token="registration-secret",
        local_runner=LocalRunnerConfig(
            argv=(PYTHON, "-V"), run_root=tmp_path / "runs"
        ),
    )
    args = argparse.Namespace(
        name=None, capabilities=None, max_concurrency=None, real=True
    )

    assert _register(config, args) == 0
    assert sent["simulation"] is False
    assert "web_tests" in sent["capabilities"]


def test_a_mission_declares_web_tests_only_through_a_web_test_suite_resource():
    assert mission_requests_web_tests(mission_with_web_tests()) is True
    assert mission_requests_web_tests(None) is False
    assert mission_requests_web_tests({"resources": []}) is False
    assert (
        mission_requests_web_tests(
            {"resources": [{"kind": "repository", "identifier": "x"}]}
        )
        is False
    )


def test_web_tests_available_needs_the_capability_and_the_configuration(tmp_path: Path):
    config = web_test_config(tmp_path)

    assert web_tests_available(config, ["web_tests"], simulation=False) is True
    assert web_tests_available(config, ["git"], simulation=False) is False
    assert web_tests_available(config, ["web_tests"], simulation=True) is False
    assert (
        web_tests_available(WebTestConfig.disabled(), ["web_tests"], simulation=False)
        is False
    )


# --------------------------------------------------------------------------
# Résolution des pièces jointes
# --------------------------------------------------------------------------


def test_an_attachment_is_accepted_only_under_the_output_directory(tmp_path: Path):
    output = tmp_path / "sortie"
    (output / "attachments").mkdir(parents=True)
    good = output / "attachments" / "capture.png"
    good.write_bytes(b"png")

    assert resolve_attachment(output, "attachments/capture.png") == good.resolve()


@pytest.mark.parametrize(
    "candidate",
    [
        "../evasion.txt",
        "attachments/../../evasion.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "//serveur/partage/fichier.txt",
        "",
        "attachments",
        "attachments/absent.png",
    ],
)
def test_an_attachment_outside_the_output_directory_is_refused(
    tmp_path: Path, candidate: str
):
    output = tmp_path / "sortie"
    (output / "attachments").mkdir(parents=True)
    (tmp_path / "evasion.txt").write_bytes(b"secret")

    with pytest.raises(AttachmentRefused):
        resolve_attachment(output, candidate)


def test_a_symbolic_link_is_refused_even_when_its_path_looks_relative(tmp_path: Path):
    if not symlinks_supported(tmp_path):
        pytest.skip("liens symboliques indisponibles sur cette machine")
    output = tmp_path / "sortie"
    (output / "attachments").mkdir(parents=True)
    cible = tmp_path / "cible.txt"
    cible.write_bytes(b"contenu externe")
    os.symlink(cible, output / "attachments" / "lien.txt")

    with pytest.raises(AttachmentRefused, match="lien"):
        resolve_attachment(output, "attachments/lien.txt")


def test_a_link_component_is_refused_without_symlink_privileges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """La branche « lien » est vérifiée même là où les liens sont interdits.

    Sous Windows sans mode développeur, ``os.symlink`` exige un privilège ; la
    règle de refus doit rester couverte sur cette machine aussi.
    """

    output = tmp_path / "sortie"
    (output / "attachments").mkdir(parents=True)
    piege = (output / "attachments" / "capture.png").resolve()
    piege.write_bytes(b"png")
    reelle = Path.is_symlink

    def is_symlink(self: Path) -> bool:
        return self == piege or reelle(self)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(AttachmentRefused, match="lien"):
        resolve_attachment(output, "attachments/capture.png")


def test_a_link_inside_the_output_directory_is_refused_as_well(tmp_path: Path):
    """Un lien reste refusé même s'il pointe à l'intérieur : aucune exception."""

    if not symlinks_supported(tmp_path):
        pytest.skip("liens symboliques indisponibles sur cette machine")
    output = tmp_path / "sortie"
    (output / "attachments").mkdir(parents=True)
    reelle = output / "attachments" / "capture.png"
    reelle.write_bytes(b"png")
    os.symlink(reelle, output / "attachments" / "alias.png")

    with pytest.raises(AttachmentRefused, match="lien"):
        resolve_attachment(output, "attachments/alias.png")


# --------------------------------------------------------------------------
# Ingestion complète
# --------------------------------------------------------------------------


async def test_a_realistic_report_is_ingested_with_every_status_kept_distinct(
    tmp_path: Path,
):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="full"), api=api
    )

    assert outcome.status == "failed"
    assert outcome.exit_code == 1
    assert outcome.succeeded is False
    assert outcome.error is None
    assert outcome.corrupt_lines == 0
    assert outcome.test_run_id == "test-run-1"
    assert outcome.case_count == 6
    assert outcome.totals == {
        "expected": 2,
        "unexpected": 3,
        "flaky": 1,
        "skipped": 1,
        "interrupted": 1,
        "timedOut": 1,
    }

    assert len(api.ingested) == 1
    body = api.ingested[0]
    TestIngestRequest.model_validate(body)
    assert body["task_run_id"] == "run-1"
    assert body["fencing_token"] == 9
    assert body["runner"] == "playwright"
    assert body["runner_version"] == "1.44.2"
    assert body["exit_code"] == 1
    cases = [event for event in body["events"] if event["kind"] == "test_end"]
    assert [case["status"] for case in cases] == [
        "passed",
        "failed",
        "timedOut",
        "skipped",
        "interrupted",
        "passed",
    ]
    assert [case["outcome"] for case in cases] == [
        "expected",
        "unexpected",
        "unexpected",
        "skipped",
        "unexpected",
        "flaky",
    ]
    assert cases[5]["attempt"] == 2
    # Trois pièces jointes de cas + le rapport HTML annoncé par ``run_end``.
    assert len(api.uploads) == 4
    uploaded = [
        attachment
        for case in cases
        for attachment in case["attachments"]
    ]
    assert len(uploaded) == 3
    assert all(len(attachment["sha256"]) == 64 for attachment in uploaded)
    assert all(attachment["size_bytes"] > 0 for attachment in uploaded)
    assert outcome.report_artifact_id is not None


async def test_a_green_suite_is_the_only_shape_that_can_succeed(tmp_path: Path):
    outcome = await execute(tmp_path, config=web_test_config(tmp_path, mode="green"))

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert outcome.case_count == 2
    assert outcome.succeeded is True


async def test_the_mission_evidence_summarises_totals_and_is_never_an_image(
    tmp_path: Path,
):
    outcome = await execute(tmp_path, config=web_test_config(tmp_path, mode="full"))
    evidence = outcome.evidence()

    EvidenceCreate.model_validate(evidence)
    assert evidence["kind"] == "web_tests"
    assert evidence["exit_code"] == 1
    assert evidence["data"]["test_run_id"] == "test-run-1"
    assert evidence["data"]["totals"]["unexpected"] == 3
    assert "inattendus 3" in evidence["summary"]
    assert set(evidence["data"]) >= {
        "status",
        "exit_code",
        "totals",
        "case_count",
        "test_run_id",
        "corrupt_lines",
        "refused_attachments",
    }
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "image/png" not in serialized
    assert "base64" not in serialized


# --------------------------------------------------------------------------
# Refus explicites
# --------------------------------------------------------------------------


async def test_an_attachment_outside_the_output_directory_is_never_uploaded(
    tmp_path: Path,
):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="escape"), api=api
    )

    assert outcome.succeeded is False
    # Le reste du rapport survit : le cas voisin et ``run_end`` sont ingérés.
    assert len(api.ingested) == 1
    body = api.ingested[0]
    cases = [event for event in body["events"] if event["kind"] == "test_end"]
    assert [case["test_id"] for case in cases] == ["evasion-voisin"]
    assert outcome.corrupt_lines == 1
    assert api.uploads == []
    assert not any(b"hors du repertoire" in upload["content"] for upload in api.uploads)


async def test_a_symlinked_attachment_is_refused_without_losing_the_report(
    tmp_path: Path,
):
    if not symlinks_supported(tmp_path):
        pytest.skip("liens symboliques indisponibles sur cette machine")
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="symlink"), api=api
    )

    assert api.uploads == []
    assert outcome.refused_attachments
    assert outcome.refused_attachments[0]["reason"] == "lien"
    assert len(api.ingested) == 1
    cases = [
        event for event in api.ingested[0]["events"] if event["kind"] == "test_end"
    ]
    assert cases[0]["test_id"] == "lien"
    assert cases[0]["attachments"] == []
    assert outcome.succeeded is False


async def test_an_announced_but_missing_attachment_is_refused_and_signalled(
    tmp_path: Path,
):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="ghost"), api=api
    )

    assert api.uploads == []
    assert outcome.refused_attachments[0]["reason"] == "absent"
    assert outcome.refused_attachments[0]["path"] == "attachments/fantome.png"
    assert len(api.ingested) == 1
    cases = [
        event for event in api.ingested[0]["events"] if event["kind"] == "test_end"
    ]
    assert cases[0]["attachments"] == []
    assert outcome.succeeded is False
    assert "1 pièce(s) jointe(s) refusée(s)" in outcome.evidence()["summary"]


async def test_a_partially_corrupt_report_is_counted_and_never_a_success(
    tmp_path: Path,
):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="corrupt"), api=api
    )

    assert outcome.corrupt_lines == 3
    assert outcome.succeeded is False
    assert len(api.ingested) == 1
    cases = [
        event for event in api.ingested[0]["events"] if event["kind"] == "test_end"
    ]
    assert [case["test_id"] for case in cases] == ["corrompu-avant", "corrompu-apres"]
    assert outcome.evidence()["data"]["corrupt_lines"] == 3
    assert "3 ligne" in outcome.evidence()["summary"]


async def test_a_missing_report_is_an_explicit_failure(tmp_path: Path):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="missing"), api=api
    )

    assert outcome.succeeded is False
    assert outcome.status == "failed"
    assert outcome.error == "no_test_results"
    assert outcome.case_count == 0
    assert api.ingested == []
    assert "aucun résultat de test produit" in outcome.evidence()["summary"]


async def test_an_empty_report_is_an_explicit_failure(tmp_path: Path):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="empty"), api=api
    )

    assert outcome.succeeded is False
    assert outcome.error == "no_test_results"
    assert api.ingested == []


async def test_an_oversized_attachment_is_refused_without_losing_the_report(
    tmp_path: Path,
):
    api = RecordingApi()
    outcome = await execute(
        tmp_path,
        config=web_test_config(
            tmp_path, mode="huge", extra="4096", max_artifact_bytes=1024
        ),
        api=api,
    )

    assert outcome.refused_attachments
    assert outcome.refused_attachments[0]["reason"] == "quota"
    assert outcome.refused_attachments[0]["size_bytes"] == 4096
    # La petite pièce jointe passe encore : le refus est ciblé, pas global.
    assert len(api.uploads) == 1
    assert len(api.ingested) == 1
    cases = [
        event for event in api.ingested[0]["events"] if event["kind"] == "test_end"
    ]
    assert [attachment["name"] for attachment in cases[0]["attachments"]] == [
        "screenshot"
    ]
    assert outcome.succeeded is False


async def test_an_api_refusal_on_upload_never_loses_the_report(tmp_path: Path):
    api = RecordingApi(quota_error=True)
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, mode="green"), api=api
    )

    assert outcome.refused_attachments[0]["reason"] == "api"
    assert len(api.ingested) == 1
    assert outcome.succeeded is False


# --------------------------------------------------------------------------
# Arrêt d'arbre et timeout
# --------------------------------------------------------------------------


async def test_a_timeout_stops_the_whole_tree_and_reports_timed_out(tmp_path: Path):
    api = RecordingApi()
    outcome = await execute(
        tmp_path,
        config=web_test_config(tmp_path, mode="hang", timeout_seconds=2.0),
        api=api,
    )

    assert outcome.status == "timed_out"
    assert outcome.succeeded is False
    assert outcome.error in {"timeout", "no_test_results"}
    pids = json.loads(
        (outcome.output_directory / "pids.json").read_text(encoding="utf-8")
    )
    await asyncio.sleep(0.5)
    assert process_is_running(pids["parent"]) is False
    assert process_is_running(pids["child"]) is False


def test_the_mission_budget_can_only_shorten_the_local_timeout(tmp_path: Path):
    from acp_worker.web_tests import _effective_timeout

    config = web_test_config(tmp_path, timeout_seconds=600.0)

    assert _effective_timeout(None, config) == 600.0
    assert _effective_timeout({"duration_seconds": 120}, config) == 120.0
    # Une mission plus généreuse ne dépasse jamais la limite de l'opérateur.
    assert _effective_timeout({"duration_seconds": 9999}, config) == 600.0
    # Le reste du budget global borne encore davantage.
    assert _effective_timeout({"duration_seconds": 120}, config, 30.0) == 30.0
    assert _effective_timeout(None, config, 0.0) == 1.0


async def test_a_lease_stop_interrupts_the_suite_and_stops_the_tree(tmp_path: Path):
    stop = asyncio.Event()
    api = RecordingApi()
    config = web_test_config(tmp_path, mode="hang", timeout_seconds=30.0)

    async def stop_soon() -> None:
        await asyncio.sleep(1.0)
        stop.set()

    async with api.client() as client:
        waiter = asyncio.create_task(stop_soon())
        outcome = await run_web_tests(
            None,
            config,
            api=WorkerTestApi(client, "https://api.test", "worker-1"),
            lease=web_test_lease(tmp_path),
            stop_event=stop,
        )
        await waiter

    assert outcome.status == "interrupted"
    assert outcome.error == "stopped"
    assert outcome.succeeded is False
    pids = json.loads(
        (outcome.output_directory / "pids.json").read_text(encoding="utf-8")
    )
    await asyncio.sleep(0.5)
    assert process_is_running(pids["parent"]) is False
    assert process_is_running(pids["child"]) is False


async def test_an_unproven_tree_stop_can_never_be_a_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def never_proven(process, grace_seconds):
        return False

    monkeypatch.setattr("acp_worker.web_tests.terminate_process_tree", never_proven)
    outcome = await execute(tmp_path, config=web_test_config(tmp_path, mode="green"))

    assert outcome.succeeded is False
    assert outcome.error == "process_tree_cleanup_failed"


async def test_a_spawn_failure_is_a_structured_failure(tmp_path: Path):
    """Un fichier existant mais non exécutable reste un échec structuré."""

    config = web_test_config(tmp_path, mode="green")
    faux = tmp_path / "pas-un-programme.txt"
    faux.write_text("ceci n'est pas un exécutable", encoding="utf-8")

    outcome = await execute(
        tmp_path,
        config=WebTestConfig(
            enabled=True,
            argv=(str(faux),),
            cwd=config.cwd,
            timeout_seconds=5.0,
        ),
    )

    assert outcome.succeeded is False
    assert outcome.error in {"spawn_error", "job_assignment_failed"}
    assert outcome.status == "failed"


def test_a_missing_project_root_is_refused_before_any_launch(tmp_path: Path):
    """Racine de projet inexistante : refus à la configuration, jamais au spawn."""

    config = web_test_config(tmp_path, mode="green")

    with pytest.raises(WebTestConfigurationError, match="répertoire de projet"):
        WebTestConfig(
            enabled=True,
            argv=config.argv,
            cwd=config.cwd / "sous-dossier-absent",
        )


async def test_a_disabled_configuration_never_spawns_anything(tmp_path: Path):
    api = RecordingApi()
    outcome = await execute(
        tmp_path, config=web_test_config(tmp_path, enabled=False), api=api
    )

    assert outcome.succeeded is False
    assert outcome.error == "disabled"
    assert api.uploads == []
    assert api.ingested == []


async def test_the_output_directory_is_new_for_each_attempt(tmp_path: Path):
    config = web_test_config(tmp_path, mode="green")
    first = await execute(
        tmp_path, config=config, lease=web_test_lease(tmp_path, attempt_number=1)
    )
    second = await execute(
        tmp_path, config=config, lease=web_test_lease(tmp_path, attempt_number=2)
    )

    assert first.output_directory != second.output_directory
    assert (first.output_directory / REPORT_FILENAME).exists()
    assert (second.output_directory / REPORT_FILENAME).exists()

    replay = await execute(
        tmp_path, config=config, lease=web_test_lease(tmp_path, attempt_number=1)
    )
    assert replay.error == "output_directory_exists"
    assert replay.succeeded is False


# --------------------------------------------------------------------------
# Expurgation
# --------------------------------------------------------------------------


async def test_an_injected_environment_value_is_redacted_before_reaching_the_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("E2E_PASSWORD", SECRET)
    api = RecordingApi()
    config = web_test_config(
        tmp_path, mode="secret", environment_allowlist=("E2E_PASSWORD",)
    )

    outcome = await execute(tmp_path, config=config, api=api)

    assert len(api.ingested) == 1
    body = json.dumps(api.ingested[0], ensure_ascii=False)
    assert SECRET not in body
    assert "***" in body
    # Le rapport local garde la valeur : seule la republication est expurgée.
    report = (outcome.output_directory / REPORT_FILENAME).read_text(encoding="utf-8")
    assert SECRET in report
    # La preuve de mission republie aussi des refus de pièces jointes dont le
    # chemin vient du reporter : ils sont expurgés au même titre.
    assert outcome.refused_attachments[0]["reason"] == "absent"
    assert "***" in outcome.refused_attachments[0]["path"]
    assert SECRET not in json.dumps(outcome.evidence(), ensure_ascii=False)


async def test_a_value_absent_from_the_allowlist_is_not_injected_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("E2E_PASSWORD", SECRET)
    api = RecordingApi()
    config = web_test_config(tmp_path, mode="secret", environment_allowlist=())

    await execute(tmp_path, config=config, api=api)

    body = json.dumps(api.ingested[0], ensure_ascii=False)
    # La variable n'atteint jamais le processus : rien à expurger côté worker.
    assert SECRET not in body


async def test_an_uploaded_attachment_name_never_republishes_an_injected_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Le nom d'origine part vers l'API : il s'expurge comme le rapport.

    Le mode ``secret`` n'écrit pas sa pièce jointe, donc rien n'est téléversé.
    Ici le fichier existe : son nom traverse le champ ``original_name`` **et** le
    nom de fichier multipart, deux surfaces persistées puis rendues dans les
    Livrables. Elles doivent dire la même chose que les événements ingérés.
    """

    monkeypatch.setenv("E2E_PASSWORD", SECRET)
    api = RecordingApi()
    config = web_test_config(
        tmp_path, mode="secret-upload", environment_allowlist=("E2E_PASSWORD",)
    )

    outcome = await execute(tmp_path, config=config, api=api)

    assert outcome.refused_attachments == ()
    assert len(api.uploads) == 1
    multipart = api.uploads[0]["content"].decode("utf-8", errors="replace")
    assert SECRET not in multipart
    assert "***" in multipart
    assert SECRET not in json.dumps(api.ingested[0], ensure_ascii=False)
    # Le fichier local garde son nom : seule la republication est expurgée.
    assert (
        outcome.output_directory / "attachments" / f"{SECRET}.png"
    ).is_file()


async def test_an_unreadable_attachment_never_publishes_a_filesystem_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Une ``OSError`` de lecture porte le chemin absolu : il ne sort pas d'ici.

    ``str(exc)`` d'une ``OSError`` CPython vaut ``[Errno 13] ... : '<chemin>'`` :
    recopié tel quel dans ``refused_attachments``, il publierait la racine
    d'exécution du worker **et** le nom injecté par le reporter dans un corps
    d'API lisible par tout membre du projet.
    """

    monkeypatch.setenv("E2E_PASSWORD", SECRET)
    api = RecordingApi()
    config = web_test_config(
        tmp_path, mode="secret-upload", environment_allowlist=("E2E_PASSWORD",)
    )

    def unreadable(path: Path, *, limit: int):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("acp_worker.web_tests._sha256_of", unreadable)

    outcome = await execute(tmp_path, config=config, api=api)

    assert api.uploads == []
    assert len(outcome.refused_attachments) == 1
    refusal = outcome.refused_attachments[0]
    assert refusal["reason"] == "absent"
    evidence = json.dumps(outcome.evidence(), ensure_ascii=False)
    assert SECRET not in evidence
    assert str(outcome.output_directory) not in evidence
    assert str(tmp_path) not in evidence
    assert SECRET not in json.dumps(api.ingested[0], ensure_ascii=False)


def test_a_refusal_message_is_redacted_like_its_path():
    """``message`` est aussi hostile que ``path`` : même traitement."""

    from acp_worker.web_tests import _refusal

    refusal = _refusal(
        path=f"attachments/{SECRET}.png",
        name=f"capture-{SECRET}",
        reason="absent",
        message=f"lecture refusée pour {SECRET}",
        size_bytes=3,
        redactions=(SECRET,),
    )

    assert SECRET not in json.dumps(refusal, ensure_ascii=False)


# --------------------------------------------------------------------------
# Routage depuis la boucle de mission
# --------------------------------------------------------------------------


def routing_claim(*, resources: list[dict]) -> dict:
    mission = mission_with_web_tests()
    mission["resources"] = resources
    return {
        "task": {
            "id": "task-1",
            "title": "Suite Playwright",
            "description": "Exécuter la suite web",
            "meta": {},
        },
        "task_run": {"id": "run-1"},
        "attempt_id": "run-1",
        "attempt_number": 1,
        "fencing_token": 9,
        "stop_requested": False,
        "session": {
            "session_id": "session-1",
            "organization_id": "organization-1",
            "workspace_id": "workspace-1",
            "project_id": "project-1",
            "team_id": None,
            "agent_instance_id": "agent-1",
            "provider_id": "hermes",
        },
        "agent": {"id": "agent-1", "name": "Agent", "role_id": "role-1"},
        "project": {"id": "project-1", "name": "Project", "project_type": "code"},
        "mission": mission,
        "required_capabilities": [],
    }


def routing_config(tmp_path: Path, web_tests: WebTestConfig) -> WorkerConfig:
    return WorkerConfig(
        api_url="https://api.test",
        gateway_url="https://gateway.test",
        gateway_service_token="gateway-secret",
        provider_id="hermes",
        poll_interval=0.01,
        step_seconds=0,
        state_dir=tmp_path / "state",
        name="web-test-worker",
        max_concurrency=1,
        simulation=False,
        registration_token=None,
        local_runner=LocalRunnerConfig(
            argv=(PYTHON, "-I", "-c", "print('processus local du lot C')"),
            run_root=tmp_path / "runs",
            timeout_seconds=10,
            max_output_bytes=4096,
        ),
        web_tests=web_tests,
    )


def routing_credentials(capabilities: list[str]) -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="worker-token",
        api_origin="https://api.test",
        name="web-test-worker",
        capabilities=capabilities,
        max_concurrency=1,
        simulation=False,
        token_expires_at="2030-01-01T00:00:00Z",
    )


async def run_routing(
    tmp_path: Path,
    *,
    capabilities: list[str],
    resources: list[dict],
    api: RecordingApi | None = None,
):
    api = api or RecordingApi()
    patches: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {
            "/workers/worker-1/artifacts/content",
            "/workers/worker-1/test-runs",
        }:
            return api.handler(request)
        if request.method == "PATCH":
            patches.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={})

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/plan"):
            return httpx.Response(
                200,
                json={
                    "plan_id": "plan-1",
                    "provider_id": "hermes",
                    "steps": [{"id": "step-1", "title": "Lancer la suite"}],
                },
            )
        return httpx.Response(200, json={"approved": True, "provider_id": "hermes"})

    config = routing_config(tmp_path, web_test_config(tmp_path, mode="green"))
    async with (
        httpx.AsyncClient(
            transport=httpx.MockTransport(api_handler),
            headers={"Authorization": "Bearer worker-token", "X-Worker-Id": "worker-1"},
        ) as api_client,
        httpx.AsyncClient(
            transport=httpx.MockTransport(gateway_handler)
        ) as gateway_client,
    ):
        await process(
            api_client,
            gateway_client,
            config,
            routing_credentials(capabilities),
            routing_claim(resources=resources),
            WorkerLogger(config.state_dir),
        )
    return patches, api


async def test_a_web_test_mission_is_routed_to_the_web_test_runner(tmp_path: Path):
    patches, api = await run_routing(
        tmp_path,
        capabilities=["web_tests"],
        resources=mission_with_web_tests()["resources"],
    )

    assert len(api.ingested) == 1
    terminal = patches[-1]
    assert terminal["result"]["execution_mode"] == "web_tests"
    assert terminal["evidence"][0]["kind"] == "web_tests"
    assert terminal["technical_validation"]["status"] == "passed"
    assert terminal["status"] == "succeeded"


async def test_a_writable_web_test_resource_is_refused_before_any_launch(
    tmp_path: Path,
):
    """La politique mission du Lot C garde son dernier mot sur les tests web."""

    from acp_worker.local_runner import RunnerRequestError

    resources = [
        {**mission_with_web_tests()["resources"][0], "access": "write"},
    ]
    recorder = RecordingApi()

    with pytest.raises(RunnerRequestError, match="écriture"):
        await run_routing(
            tmp_path,
            capabilities=["web_tests"],
            resources=resources,
            api=recorder,
        )

    assert recorder.ingested == []
    assert recorder.uploads == []


async def test_without_the_capability_the_mission_keeps_the_lot_c_behaviour(
    tmp_path: Path,
):
    patches, api = await run_routing(
        tmp_path,
        capabilities=["shell_restricted"],
        resources=mission_with_web_tests()["resources"],
    )

    assert api.ingested == []
    assert api.uploads == []
    terminal = patches[-1]
    assert terminal["result"]["execution_mode"] == "real_local_process"
    assert terminal["evidence"][0]["kind"] == "local_process"


async def test_without_a_web_test_resource_the_mission_keeps_the_lot_c_behaviour(
    tmp_path: Path,
):
    patches, api = await run_routing(
        tmp_path,
        capabilities=["web_tests"],
        resources=[],
    )

    assert api.ingested == []
    terminal = patches[-1]
    assert terminal["result"]["execution_mode"] == "real_local_process"
