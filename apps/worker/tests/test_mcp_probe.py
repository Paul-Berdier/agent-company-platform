"""Tests de la sonde MCP stdio du worker.

Aucun accès réseau : l'API est simulée par ``httpx.MockTransport`` et le serveur
MCP est un vrai processus local déterministe (``fake_mcp_server.py``).
"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import httpx
import pytest

from acp_worker.capabilities import detect_capabilities
from acp_worker.config import WorkerConfig
from acp_worker.local_log import WorkerLogger
from acp_worker.local_runner import LocalRunnerConfig
from acp_worker.main import _probe_loop, run_forever
from acp_worker.mcp_probe import (
    CLIENT_NAME,
    INHERITED_ENVIRONMENT_NAMES,
    PROTOCOL_VERSION,
    REDACTED_PLACEHOLDER as REDACTED,
    STDERR_TAIL_MAX_CHARS,
    McpProbeConfigurationError,
    McpStdioProbeConfig,
    run_stdio_probe,
)
from acp_worker.state import WorkerCredentials


FAKE_SERVER = str(Path(__file__).with_name("fake_mcp_server.py").resolve())
PYTHON = str(Path(sys.executable).resolve())


def probe_config(
    *,
    enabled: bool = True,
    allowed: tuple[str, ...] = (PYTHON,),
    timeout: int = 20,
) -> McpStdioProbeConfig:
    return McpStdioProbeConfig(
        enabled=enabled, allowed_executables=allowed, timeout_seconds=timeout
    )


def probe_request(
    *,
    mode: str = "ok",
    extra_arg: str | None = None,
    command: str = PYTHON,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout_seconds: int | None = None,
) -> dict:
    args = ["-I", FAKE_SERVER, mode]
    if extra_arg is not None:
        args.append(extra_arg)
    request: dict = {
        "id": "probe-1",
        "server_id": "server-1",
        "revision_id": "revision-1",
        "command": command,
        "args": args,
        "env": env or {},
        "cwd": cwd,
        "timeout_seconds": timeout_seconds if timeout_seconds is not None else 20,
        "lease_expires_at": "2030-01-01T00:00:00Z",
    }
    return request


def process_is_running(process_id: int) -> bool:
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


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_probe_configuration_is_disabled_by_default():
    config = McpStdioProbeConfig.from_environ({})

    assert config.enabled is False
    assert config.allowed_executables == ()
    assert config.timeout_seconds == 20


def test_enabled_probe_requires_a_non_empty_absolute_allowlist():
    with pytest.raises(McpProbeConfigurationError, match="au moins un exécutable"):
        McpStdioProbeConfig.from_environ({"ACP_WORKER_MCP_STDIO_ENABLED": "1"})
    with pytest.raises(McpProbeConfigurationError, match="chemins absolus"):
        McpStdioProbeConfig.from_environ(
            {
                "ACP_WORKER_MCP_STDIO_ENABLED": "1",
                "ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES": "python.exe",
            }
        )


@pytest.mark.parametrize("value", ["0", "120"])
def test_probe_timeout_is_bounded(value: str):
    with pytest.raises(McpProbeConfigurationError, match="entre 1 et 120"):
        McpStdioProbeConfig.from_environ(
            {
                "ACP_WORKER_MCP_STDIO_ENABLED": "1",
                "ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES": PYTHON,
                "ACP_WORKER_MCP_STDIO_TIMEOUT_SECONDS": (
                    "0" if value == "0" else "121"
                ),
            }
        )


def test_probe_enabled_flag_accepts_only_zero_or_one():
    with pytest.raises(McpProbeConfigurationError, match="0 ou 1"):
        McpStdioProbeConfig.from_environ({"ACP_WORKER_MCP_STDIO_ENABLED": "oui"})


def test_probe_configuration_reads_the_full_environment():
    config = McpStdioProbeConfig.from_environ(
        {
            "ACP_WORKER_MCP_STDIO_ENABLED": "1",
            "ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES": os.pathsep.join(
                [PYTHON, str(Path(sys.executable).parent.resolve())]
            ),
            "ACP_WORKER_MCP_STDIO_TIMEOUT_SECONDS": "30",
        }
    )

    assert config.enabled is True
    assert config.timeout_seconds == 30
    assert PYTHON in config.allowed_executables


def test_worker_config_exposes_the_probe_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)
    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ENABLED", "1")
    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES", PYTHON)

    config = WorkerConfig.from_env()

    assert config.mcp_probe.enabled is True
    assert config.mcp_probe.allowed_executables == (PYTHON,)


# --------------------------------------------------------------------------
# Capacité et doctor
# --------------------------------------------------------------------------


def test_capability_requires_both_the_flag_and_the_allowlist(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ACP_WORKER_MCP_STDIO_ENABLED", raising=False)
    monkeypatch.delenv("ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES", raising=False)
    assert "mcp_stdio_probe" not in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ENABLED", "1")
    assert "mcp_stdio_probe" not in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES", PYTHON)
    assert "mcp_stdio_probe" in detect_capabilities()

    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ENABLED", "0")
    assert "mcp_stdio_probe" not in detect_capabilities()


def test_doctor_reports_the_stdio_probe_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from acp_worker.cli import main as cli_main

    monkeypatch.setenv("ACP_API_URL", "https://api.example")
    monkeypatch.setenv("ACP_PROVIDER_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("ACP_WORKER_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("ACP_WORKER_RUNNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("ACP_WORKER_RUN_ROOT", raising=False)
    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ENABLED", "1")
    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ALLOWED_EXECUTABLES", PYTHON)
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

    assert report["mcp_stdio_probe"] == "enabled"
    assert report["mcp_stdio_allowed_executables"] == 1

    monkeypatch.setenv("ACP_WORKER_MCP_STDIO_ENABLED", "0")
    assert cli_main(["doctor"]) == 1
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["mcp_stdio_probe"] == "disabled"
    assert "mcp_stdio_allowed_executables" not in disabled


# --------------------------------------------------------------------------
# Refus sans lancement
# --------------------------------------------------------------------------


async def test_command_outside_the_allowlist_never_spawns(tmp_path: Path):
    witness = tmp_path / "temoin.txt"
    config = probe_config(allowed=(str(tmp_path / "autre-programme.exe"),))

    result = await run_stdio_probe(
        probe_request(mode="witness", extra_arg=str(witness)), config
    )

    assert result["status"] == "failed"
    assert result["error"] == "not_allowed"
    assert result["exit_code"] is None
    assert result["tools"] == []
    await asyncio.sleep(0.2)
    assert not witness.exists()


async def test_disabled_probe_never_spawns(tmp_path: Path):
    witness = tmp_path / "temoin-desactive.txt"
    config = McpStdioProbeConfig(
        enabled=False, allowed_executables=(PYTHON,), timeout_seconds=20
    )

    result = await run_stdio_probe(
        probe_request(mode="witness", extra_arg=str(witness)), config
    )

    assert result["status"] == "failed"
    assert result["error"] == "disabled"
    await asyncio.sleep(0.2)
    assert not witness.exists()


async def test_relative_command_never_spawns(tmp_path: Path):
    witness = tmp_path / "temoin-relatif.txt"
    request = probe_request(mode="witness", extra_arg=str(witness), command="python")

    result = await run_stdio_probe(request, probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "not_allowed"
    await asyncio.sleep(0.2)
    assert not witness.exists()


async def test_allowlist_is_compared_after_resolution():
    """``..`` et casse ne contournent pas l'allowlist et ne la durcissent pas."""

    parent = Path(PYTHON).parent
    detoured = str(parent / ".." / Path(parent).name / Path(PYTHON).name)

    result = await run_stdio_probe(
        probe_request(command=detoured), probe_config(allowed=(PYTHON,))
    )

    assert result["status"] == "succeeded", result["error"]


# --------------------------------------------------------------------------
# Découverte
# --------------------------------------------------------------------------


async def test_successful_discovery_returns_protocol_tools_and_exit_code():
    result = await run_stdio_probe(probe_request(), probe_config())

    assert result["status"] == "succeeded"
    assert result["error"] is None
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert result["server_info"]["name"] == "faux-serveur-mcp"
    assert [tool["name"] for tool in result["tools"]] == ["outil-1", "outil-2"]
    assert result["tools"][0]["input_schema"]["required"] == ["chemin"]
    assert result["exit_code"] == 0
    assert isinstance(result["duration_ms"], int) and result["duration_ms"] >= 0
    assert "faux serveur prêt" in result["stderr_tail"]


async def test_tool_descriptions_are_bounded():
    result = await run_stdio_probe(probe_request(), probe_config())

    assert len(result["tools"][1]["description"]) == 2000


async def test_paginated_tools_are_all_collected():
    result = await run_stdio_probe(probe_request(mode="paged"), probe_config())

    assert result["status"] == "succeeded"
    assert [tool["name"] for tool in result["tools"]] == [
        "outil-1",
        "outil-2",
        "outil-3",
    ]


async def test_unbounded_pagination_is_refused_instead_of_truncated():
    result = await run_stdio_probe(probe_request(mode="endless"), probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "too_many_tools"


async def test_a_single_oversized_page_is_refused_instead_of_truncated():
    """Sans ``nextCursor``, rien ne signalerait la troncature : elle est refusée."""

    result = await run_stdio_probe(probe_request(mode="oversized"), probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "too_many_tools"
    assert result["tools"] == []


async def test_environment_is_minimal_and_carries_no_worker_secret(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", "secret-worker")
    monkeypatch.setenv("HERMES_SERVICE_TOKEN", "secret-hermes")

    result = await run_stdio_probe(
        probe_request(env={"MCP_SERVER_TOKEN": "valeur-injectée"}), probe_config()
    )

    assert result["status"] == "succeeded", result["error"]
    # CPython pose lui-même ``LC_CTYPE`` dans son propre environnement quand il coerce
    # une locale POSIX héritée (PEP 538), ce qui arrive sur les runners Linux dont la
    # locale est `C`. Cette variable est créée par l'interpréteur enfant : elle ne
    # provient pas de l'environnement du worker et ne peut donc pas transporter un
    # secret. L'exclure garde l'égalité stricte sur ce que le worker transmet vraiment.
    interpreter_injected = {"LC_CTYPE"}
    visible = set(result["server_info"]["environmentNames"]) - interpreter_injected
    expected = {
        name for name in INHERITED_ENVIRONMENT_NAMES if name in os.environ
    } | {"MCP_SERVER_TOKEN"}

    assert visible == expected
    assert "ACP_WORKER_REGISTRATION_TOKEN" not in visible
    assert "HERMES_SERVICE_TOKEN" not in visible


async def test_injected_environment_values_never_reach_the_result():
    """Un serveur bavard ne doit pas faire ressortir un secret du coffre."""

    secret = "VALEUR-DE-COFFRE-ULTRA-SECRETE-42"

    result = await run_stdio_probe(
        probe_request(
            mode="echo-env",
            extra_arg="MCP_TOKEN",
            env={"MCP_TOKEN": secret},
        ),
        probe_config(),
    )

    assert result["status"] == "succeeded", result["error"]
    assert secret not in json.dumps(result, ensure_ascii=False)
    assert result["server_info"]["echoedEnvironment"]["MCP_TOKEN"] == REDACTED
    assert REDACTED in result["stderr_tail"]
    assert REDACTED in result["tools"][0]["description"]
    # Le nom reste visible : seul le secret est masqué.
    assert "MCP_TOKEN" in result["server_info"]["environmentNames"]


async def test_short_environment_values_are_redacted_too():
    """``SecretCreate.value`` autorise une valeur d'un caractère : elle est un secret aussi."""

    result = await run_stdio_probe(
        probe_request(mode="echo-env", extra_arg="MCP_TOKEN", env={"MCP_TOKEN": "ok"}),
        probe_config(),
    )

    assert result["status"] == "succeeded", result["error"]
    assert result["server_info"]["echoedEnvironment"]["MCP_TOKEN"] == REDACTED


async def test_probe_runs_in_a_fresh_directory_when_no_cwd_is_given(tmp_path: Path):
    result = await run_stdio_probe(
        probe_request(cwd=str(tmp_path)), probe_config()
    )

    assert result["status"] == "succeeded", result["error"]


# --------------------------------------------------------------------------
# Échecs d'exécution
# --------------------------------------------------------------------------


async def test_non_json_output_is_a_protocol_error():
    result = await run_stdio_probe(probe_request(mode="garbage"), probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "protocol"
    assert result["tools"] == []
    assert result["protocol_version"] is None


@pytest.mark.parametrize(
    "mode", ["empty-initialize", "no-protocol-version", "no-server-info"]
)
async def test_malformed_initialize_is_never_reported_as_a_success(mode: str):
    """Aucun faux succès : ``protocolVersion`` et ``serverInfo`` sont obligatoires.

    Le contrat ``McpDiscovery.protocol_version`` est un ``str`` requis côté API :
    un succès à ``protocol_version: null`` serait ininstanciable.
    """

    result = await run_stdio_probe(probe_request(mode=mode), probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "protocol"
    assert result["protocol_version"] is None
    assert result["tools"] == []


async def test_timeout_terminates_the_process_tree(tmp_path: Path):
    pid_file = tmp_path / "hang.pid"
    request = probe_request(mode="hang", extra_arg=str(pid_file), timeout_seconds=1)

    result = await asyncio.wait_for(
        run_stdio_probe(request, probe_config(timeout=1)), timeout=30
    )

    assert result["status"] == "failed"
    assert result["error"] == "timeout"
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


async def test_stderr_tail_is_bounded():
    result = await run_stdio_probe(probe_request(mode="noisy"), probe_config())

    assert result["status"] == "succeeded", result["error"]
    assert len(result["stderr_tail"]) == STDERR_TAIL_MAX_CHARS


async def test_request_timeout_can_only_reduce_the_configured_timeout(tmp_path: Path):
    pid_file = tmp_path / "hang-reduced.pid"
    request = probe_request(mode="hang", extra_arg=str(pid_file), timeout_seconds=1)

    result = await asyncio.wait_for(
        run_stdio_probe(request, probe_config(timeout=120)), timeout=30
    )

    assert result["error"] == "timeout"
    assert result["duration_ms"] < 20_000
    server_pid = int(pid_file.read_text(encoding="ascii"))
    for _ in range(200):
        if not process_is_running(server_pid):
            break
        await asyncio.sleep(0.01)
    if process_is_running(server_pid):
        os.kill(server_pid, signal.SIGTERM)


async def test_malformed_request_is_refused_without_spawning(tmp_path: Path):
    result = await run_stdio_probe({"id": "probe-1"}, probe_config())

    assert result["status"] == "failed"
    assert result["error"] == "invalid_request"


# --------------------------------------------------------------------------
# Boucle de sonde
# --------------------------------------------------------------------------


def loop_config(tmp_path: Path, *, enabled: bool = True) -> WorkerConfig:
    runner = LocalRunnerConfig(
        argv=(PYTHON, "-I", "-c", "raise SystemExit(0)"),
        run_root=tmp_path / "runs",
    )
    return WorkerConfig(
        api_url="https://api.test",
        gateway_url="https://gateway.test",
        gateway_service_token="gateway-secret",
        provider_id="hermes",
        poll_interval=0.01,
        step_seconds=0,
        state_dir=tmp_path / "state",
        name="probe-test-worker",
        max_concurrency=1,
        simulation=False,
        registration_token=None,
        local_runner=runner,
        mcp_probe=probe_config(enabled=enabled),
    )


def loop_credentials(*, capabilities: list[str] | None = None) -> WorkerCredentials:
    return WorkerCredentials(
        worker_id="worker-1",
        token="worker-token",
        api_origin="https://api.test",
        name="probe-test-worker",
        capabilities=(
            capabilities if capabilities is not None else ["mcp_stdio_probe"]
        ),
        max_concurrency=1,
        simulation=False,
        token_expires_at="2030-01-01T00:00:00Z",
    )


async def test_probe_loop_does_nothing_when_no_probe_is_claimed(tmp_path: Path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"probe": None})

    stop = asyncio.Event()
    logger = WorkerLogger(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            _probe_loop(client, loop_config(tmp_path), loop_credentials(), stop, logger)
        )
        for _ in range(300):
            if calls:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert calls
    assert all(url.endswith("/mcp/worker/probes/claim") for url in calls)


async def test_probe_loop_runs_the_probe_and_posts_the_result(tmp_path: Path):
    posted: list[dict] = []
    claimed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal claimed
        if request.url.path == "/mcp/worker/probes/claim":
            if claimed:
                return httpx.Response(200, json={"probe": None})
            claimed = True
            return httpx.Response(
                200,
                json={
                    "probe": {
                        **probe_request(),
                        "id": "probe-42",
                    }
                },
            )
        assert request.url.path == "/mcp/worker/probes/probe-42/result"
        posted.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"id": "probe-42", "status": "succeeded"})

    stop = asyncio.Event()
    logger = WorkerLogger(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            _probe_loop(client, loop_config(tmp_path), loop_credentials(), stop, logger)
        )
        for _ in range(1000):
            if posted:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    assert len(posted) == 1
    body = posted[0]
    assert body["status"] == "succeeded"
    assert body["protocol_version"] == PROTOCOL_VERSION
    assert [tool["name"] for tool in body["tools"]] == ["outil-1", "outil-2"]
    assert body["exit_code"] == 0
    assert set(body) == {
        "status",
        "protocol_version",
        "server_info",
        "tools",
        "exit_code",
        "stderr_tail",
        "duration_ms",
        "error",
    }


async def test_probe_loop_never_logs_environment_values(tmp_path: Path):
    """Règle non négociable : aucune valeur de secret dans le journal local."""

    secret = "VALEUR-ULTRA-SECRETE-42"
    posted: list[dict] = []
    claimed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal claimed
        if request.url.path == "/mcp/worker/probes/claim":
            if claimed:
                return httpx.Response(200, json={"probe": None})
            claimed = True
            probe = {**probe_request(env={"MCP_TOKEN": secret}), "id": "probe-7"}
            return httpx.Response(200, json={"probe": probe})
        posted.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"id": "probe-7"})

    stop = asyncio.Event()
    state_dir = tmp_path / "state"
    logger = WorkerLogger(state_dir)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            _probe_loop(client, loop_config(tmp_path), loop_credentials(), stop, logger)
        )
        for _ in range(1000):
            if posted:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    assert posted and posted[0]["status"] == "succeeded"
    assert "MCP_TOKEN" in posted[0]["server_info"]["environmentNames"]
    journal = (state_dir / "worker.log.jsonl").read_text(encoding="utf-8")
    assert "probe-7" in journal
    assert secret not in journal


async def test_probe_loop_never_posts_environment_values(tmp_path: Path):
    """Règle non négociable : aucune valeur de secret dans la réponse API.

    ``GET /mcp/probes/{id}`` est lisible par tout utilisateur authentifié : un
    serveur MCP bavard ne doit jamais y publier une valeur du coffre.
    """

    secret = "VALEUR-DE-COFFRE-ULTRA-SECRETE-99"
    bodies: list[str] = []
    claimed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal claimed
        if request.url.path == "/mcp/worker/probes/claim":
            if claimed:
                return httpx.Response(200, json={"probe": None})
            claimed = True
            probe = {
                **probe_request(
                    mode="echo-env",
                    extra_arg="MCP_TOKEN",
                    env={"MCP_TOKEN": secret},
                ),
                "id": "probe-9",
            }
            return httpx.Response(200, json={"probe": probe})
        bodies.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "probe-9"})

    stop = asyncio.Event()
    logger = WorkerLogger(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            _probe_loop(client, loop_config(tmp_path), loop_credentials(), stop, logger)
        )
        for _ in range(1000):
            if bodies:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    assert bodies
    posted = json.loads(bodies[0])
    assert posted["status"] == "succeeded", posted["error"]
    assert secret not in bodies[0]
    assert secret.encode("unicode_escape").decode("ascii") not in bodies[0]
    assert posted["server_info"]["echoedEnvironment"]["MCP_TOKEN"] == REDACTED
    assert REDACTED in posted["stderr_tail"]


async def test_probe_loop_survives_an_api_failure(tmp_path: Path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(503, json={"detail": "indisponible"})

    stop = asyncio.Event()
    logger = WorkerLogger(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            _probe_loop(client, loop_config(tmp_path), loop_credentials(), stop, logger)
        )
        for _ in range(300):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert len(calls) >= 2


async def test_probe_loop_called_directly_refuses_without_the_capability(
    tmp_path: Path,
):
    """Défense en profondeur : la boucle ne réclame rien sans capacité annoncée."""

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"probe": None})

    stop = asyncio.Event()
    logger = WorkerLogger(tmp_path / "state")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await asyncio.wait_for(
            _probe_loop(
                client,
                loop_config(tmp_path),
                loop_credentials(capabilities=["shell_restricted"]),
                stop,
                logger,
            ),
            timeout=5,
        )
        await asyncio.wait_for(
            _probe_loop(
                client,
                WorkerConfig(
                    **{
                        **loop_config(tmp_path).__dict__,
                        "mcp_probe": probe_config(enabled=False),
                    }
                ),
                loop_credentials(),
                stop,
                logger,
            ),
            timeout=5,
        )

    assert calls == []


async def test_probe_loop_is_not_started_without_the_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths: list[str] = []
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"task": None})

        return real_async_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("acp_worker.main.httpx.AsyncClient", client_factory)
    config = loop_config(tmp_path)

    await run_forever(
        config, loop_credentials(capabilities=["shell_restricted"]), once=True
    )

    assert "/mcp/worker/probes/claim" not in paths


async def test_probe_loop_is_started_when_the_capability_is_announced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths: list[str] = []
    claim_seen = asyncio.Event()
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            if request.url.path == "/mcp/worker/probes/claim":
                claim_seen.set()
                return httpx.Response(200, json={"probe": None})
            return httpx.Response(200, json={"task": None})

        return real_async_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("acp_worker.main.httpx.AsyncClient", client_factory)
    config = loop_config(tmp_path)

    worker = asyncio.create_task(run_forever(config, loop_credentials()))
    try:
        await asyncio.wait_for(claim_seen.wait(), timeout=10)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    assert "/mcp/worker/probes/claim" in paths


async def test_simulated_worker_never_starts_the_probe_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths: list[str] = []
    real_async_client = httpx.AsyncClient

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"task": None})

        return real_async_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("acp_worker.main.httpx.AsyncClient", client_factory)
    config = WorkerConfig(
        **{**loop_config(tmp_path).__dict__, "simulation": True}
    )
    credentials = WorkerCredentials(
        **{**loop_credentials().__dict__, "simulation": True}
    )

    await run_forever(config, credentials, once=True)

    assert "/mcp/worker/probes/claim" not in paths


def test_client_identity_is_the_platform_worker():
    assert CLIENT_NAME == "agent-company-platform-worker"
    assert PROTOCOL_VERSION == "2025-06-18"
