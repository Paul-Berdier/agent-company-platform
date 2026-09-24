import asyncio
import hashlib
import json
import os
import signal
import sys
from pathlib import Path

import pytest

import acp_poste.local_runner as local_runner_module
from acp_poste.local_runner import (
    EVIDENCE_FILENAME,
    EVIDENCE_SCHEMA,
    REQUEST_SCHEMA,
    LocalRunnerConfig,
    LocalRunRequest,
    RunnerConfigurationError,
    RunnerRequestError,
    restricted_run_environment,
    run_local_program,
)


def runner_config(
    tmp_path: Path,
    code: str,
    *,
    timeout: float = 5.0,
    output_limit: int = 1024,
    environment_allowlist: tuple[str, ...] = (),
    extra_args: tuple[str, ...] = (),
) -> LocalRunnerConfig:
    return LocalRunnerConfig(
        argv=(sys.executable, "-I", "-c", code, *extra_args),
        run_root=tmp_path / "runs",
        timeout_seconds=timeout,
        max_output_bytes=output_limit,
        environment_allowlist=environment_allowlist,
        terminate_grace_seconds=0.05,
    )


def request(
    *,
    run_id: str = "run-1",
    attempt_id: str = "attempt-1",
    timeout_seconds: float | None = None,
) -> LocalRunRequest:
    return LocalRunRequest(
        run_id=run_id,
        attempt_id=attempt_id,
        attempt_number=1,
        fencing_token=7,
        payload={"schema": REQUEST_SCHEMA, "value": "déterministe"},
        timeout_seconds=timeout_seconds,
    )


async def test_real_program_success_is_deterministic_and_proven(tmp_path: Path):
    config = runner_config(
        tmp_path,
        "import json,os,sys; data=json.load(open(sys.argv[-1],encoding='utf-8')); "
        "print(json.dumps({'cwd':os.getcwd(),'data':data},sort_keys=True))",
    )
    run_request = request()

    result = await run_local_program(config, run_request)

    assert result.succeeded is True
    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert result.termination_reason == "exit"
    decoded = json.loads(result.stdout.text)
    assert Path(decoded["cwd"]) == result.run_directory
    assert decoded["data"] == run_request.payload
    expected_request = json.dumps(
        run_request.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert result.request_sha256 == hashlib.sha256(expected_request).hexdigest()
    assert (result.run_directory / "request.json").read_bytes() == expected_request

    evidence = result.evidence(run_request)
    assert evidence["schema"] == EVIDENCE_SCHEMA
    assert evidence["kind"] == "local_process"
    assert evidence["attempt_id"] == "attempt-1"
    assert evidence["fencing_token"] == 7
    assert evidence["status"] == "succeeded"
    assert evidence["exit_code"] == 0
    assert evidence["stdout"]["truncated"] is False
    assert len(evidence["request_sha256"]) == 64
    assert len(evidence["command_sha256"]) == 64
    assert json.loads(
        (result.run_directory / EVIDENCE_FILENAME).read_text(encoding="utf-8")
    ) == evidence


async def test_non_zero_exit_is_a_real_failure_with_stderr(tmp_path: Path):
    config = runner_config(
        tmp_path,
        "import sys; sys.stderr.write('real failure\\n'); raise SystemExit(7)",
    )

    result = await run_local_program(config, request())

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.exit_code == 7
    assert result.termination_reason == "exit"
    assert result.stderr.text.splitlines() == ["real failure"]


async def test_success_fails_closed_when_process_tree_cleanup_is_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def cleanup_unconfirmed(
        process: asyncio.subprocess.Process, grace_seconds: float
    ) -> bool:
        assert process.returncode == 0
        assert grace_seconds == 0
        return False

    monkeypatch.setattr(
        local_runner_module,
        "_terminate_process",
        cleanup_unconfirmed,
    )
    result = await run_local_program(
        runner_config(tmp_path, "raise SystemExit(0)"),
        request(),
    )

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.termination_reason == "exit_process_tree_cleanup_failed"


async def test_timeout_terminates_the_real_process(tmp_path: Path):
    config = runner_config(
        tmp_path,
        "import time; time.sleep(30)",
        timeout=0.15,
    )

    result = await asyncio.wait_for(run_local_program(config, request()), timeout=3)

    assert result.succeeded is False
    assert result.status == "timed_out"
    assert result.termination_reason == "timeout"
    assert result.exit_code not in (None, 0)
    assert result.duration_ms < 2500


async def test_request_duration_can_only_reduce_the_local_timeout(tmp_path: Path):
    config = runner_config(tmp_path, "import time; time.sleep(30)", timeout=5)

    result = await asyncio.wait_for(
        run_local_program(config, request(timeout_seconds=0.15)), timeout=3
    )

    assert result.status == "timed_out"
    assert result.timeout_seconds == 0.15
    assert result.evidence(request(timeout_seconds=0.15))["limits"][
        "timeout_seconds"
    ] == 0.15


async def test_stop_event_terminates_the_real_process(tmp_path: Path):
    config = runner_config(tmp_path, "import time; time.sleep(30)", timeout=10)
    stop = asyncio.Event()

    async def request_stop() -> None:
        await asyncio.sleep(0.15)
        stop.set()

    stopper = asyncio.create_task(request_stop())
    result = await asyncio.wait_for(
        run_local_program(config, request(), stop_event=stop), timeout=3
    )
    await stopper

    assert result.succeeded is False
    assert result.status == "cancelled"
    assert result.termination_reason == "stop_requested"
    assert result.exit_code not in (None, 0)
    assert result.duration_ms < 2500


async def test_preexisting_stop_is_persisted_without_spawning(tmp_path: Path):
    marker = tmp_path / "must-not-spawn"
    config = runner_config(
        tmp_path,
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('spawned')",
        extra_args=(str(marker),),
    )
    stop = asyncio.Event()
    stop.set()

    result = await run_local_program(config, request(), stop_event=stop)

    assert result.status == "cancelled"
    assert result.exit_code is None
    assert not marker.exists()
    evidence = json.loads(
        (result.run_directory / EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert evidence["status"] == "cancelled"
    assert evidence["termination_reason"] == "stop_requested"


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


async def terminate_test_process(process_id: int) -> None:
    """Nettoie un enfant de test même si l'assertion principale a échoué."""

    if process_is_running(process_id):
        try:
            os.kill(process_id, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(200):
        if not process_is_running(process_id):
            return
        await asyncio.sleep(0.01)
    if hasattr(signal, "SIGKILL"):
        try:
            os.kill(process_id, signal.SIGKILL)
        except OSError:
            pass
        for _ in range(200):
            if not process_is_running(process_id):
                return
            await asyncio.sleep(0.01)


def read_test_process_id(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None


async def test_stop_terminates_a_spawned_child_process(tmp_path: Path):
    child_pid_file = tmp_path / "child.pid"
    child_code = (
        "import signal,time; "
        "signal.signal(signal.SIGBREAK, signal.SIG_IGN) "
        "if hasattr(signal, 'SIGBREAK') else None; "
        "time.sleep(30)"
    )
    code = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-I','-c',{child_code!r}]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
    )
    config = runner_config(
        tmp_path,
        code,
        timeout=10,
        extra_args=(str(child_pid_file),),
    )
    stop = asyncio.Event()

    async def stop_after_child_started() -> None:
        for _ in range(300):
            if read_test_process_id(child_pid_file) is not None:
                stop.set()
                return
            await asyncio.sleep(0.01)
        raise AssertionError("le processus enfant n'a pas démarré")

    stopper = asyncio.create_task(stop_after_child_started())
    child_pid: int | None = None
    try:
        result = await asyncio.wait_for(
            run_local_program(config, request(), stop_event=stop), timeout=5
        )
        await stopper
        child_pid = read_test_process_id(child_pid_file)
        assert child_pid is not None
        for _ in range(200):
            if not process_is_running(child_pid):
                break
            await asyncio.sleep(0.01)
        assert result.status == "cancelled"
        assert result.termination_reason == "stop_requested"
        assert not process_is_running(child_pid)
    finally:
        stopper.cancel()
        await asyncio.gather(stopper, return_exceptions=True)
        if child_pid is None:
            child_pid = read_test_process_id(child_pid_file)
        if child_pid is not None:
            await terminate_test_process(child_pid)


async def test_normal_parent_exit_cannot_leave_a_background_child(tmp_path: Path):
    child_pid_file = tmp_path / "background-child.pid"
    child_code = (
        "import signal,time; "
        "signal.signal(signal.SIGBREAK, signal.SIG_IGN) "
        "if hasattr(signal, 'SIGBREAK') else None; "
        "time.sleep(30)"
    )
    code = (
        "import pathlib,subprocess,sys; "
        f"child=subprocess.Popen([sys.executable,'-I','-c',{child_code!r}]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
    )
    config = runner_config(tmp_path, code, extra_args=(str(child_pid_file),))
    child_pid: int | None = None
    try:
        result = await asyncio.wait_for(run_local_program(config, request()), timeout=5)
        child_pid = read_test_process_id(child_pid_file)
        assert child_pid is not None
        for _ in range(200):
            if not process_is_running(child_pid):
                break
            await asyncio.sleep(0.01)
        assert result.succeeded
        assert not process_is_running(child_pid)
    finally:
        if child_pid is None:
            child_pid = read_test_process_id(child_pid_file)
        if child_pid is not None:
            await terminate_test_process(child_pid)


async def test_asyncio_cancellation_terminates_the_process_tree(tmp_path: Path):
    child_pid_file = tmp_path / "cancelled-child.pid"
    code = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)']); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)"
    )
    config = runner_config(
        tmp_path,
        code,
        timeout=10,
        extra_args=(str(child_pid_file),),
    )
    execution = asyncio.create_task(run_local_program(config, request()))
    child_pid: int | None = None
    try:
        for _ in range(300):
            if child_pid_file.exists():
                break
            await asyncio.sleep(0.01)
        child_pid = int(child_pid_file.read_text(encoding="ascii"))
        execution.cancel()
        result = await execution
        for _ in range(200):
            if not process_is_running(child_pid):
                break
            await asyncio.sleep(0.01)
        assert result.status == "cancelled"
        assert result.termination_reason == "task_cancelled"
        assert (result.run_directory / EVIDENCE_FILENAME).exists()
        assert not process_is_running(child_pid)
    finally:
        if not execution.done():
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        if child_pid is not None and process_is_running(child_pid):
            os.kill(child_pid, signal.SIGTERM)


async def test_orphaned_grandchild_is_terminated_when_parent_exits_normally(
    tmp_path: Path,
):
    """Le parent lance un intermédiaire qui lance le petit-fils puis sort aussitôt.

    La filiation est rompue avant même la sortie du parent : seule une clôture
    attachée au spawn (session POSIX, Job Object Windows) peut retrouver le
    petit-fils. Le résultat doit rester ``succeeded`` et le petit-fils mort.
    """

    grandchild_pid_file = tmp_path / "orphan-grandchild.pid"
    grandchild_code = (
        "import signal,time; "
        "signal.signal(signal.SIGBREAK, signal.SIG_IGN) "
        "if hasattr(signal, 'SIGBREAK') else None; "
        "time.sleep(30)"
    )
    intermediate_code = (
        "import pathlib,subprocess,sys; "
        f"child=subprocess.Popen([sys.executable,'-I','-c',{grandchild_code!r}]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
    )
    parent_code = (
        "import subprocess,sys; "
        "raise SystemExit(subprocess.call("
        f"[sys.executable,'-I','-c',{intermediate_code!r},sys.argv[1]]))"
    )
    config = runner_config(
        tmp_path, parent_code, extra_args=(str(grandchild_pid_file),)
    )
    grandchild_pid: int | None = None
    try:
        result = await asyncio.wait_for(run_local_program(config, request()), timeout=10)
        grandchild_pid = read_test_process_id(grandchild_pid_file)
        assert grandchild_pid is not None
        for _ in range(200):
            if not process_is_running(grandchild_pid):
                break
            await asyncio.sleep(0.01)
        assert result.status == "succeeded"
        assert result.termination_reason == "exit"
        assert result.succeeded
        assert not process_is_running(grandchild_pid)
    finally:
        if grandchild_pid is None:
            grandchild_pid = read_test_process_id(grandchild_pid_file)
        if grandchild_pid is not None:
            await terminate_test_process(grandchild_pid)


@pytest.mark.skipif(os.name != "nt", reason="Job Object Windows uniquement")
async def test_job_assignment_failure_is_spawn_failed_and_never_runs_the_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "must-not-run"

    def assignment_refused(job_handle: int, process_id: int) -> None:
        assert isinstance(job_handle, int) and job_handle
        assert isinstance(process_id, int) and process_id > 0
        raise OSError(5, "affectation au job refusée (simulation)")

    monkeypatch.setattr(
        local_runner_module,
        "_windows_assign_process_to_job",
        assignment_refused,
    )
    config = runner_config(
        tmp_path,
        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')",
        extra_args=(str(marker),),
    )

    result = await asyncio.wait_for(run_local_program(config, request()), timeout=10)

    assert result.succeeded is False
    assert result.status == "spawn_failed"
    assert result.termination_reason == "job_assignment_failed"
    assert result.exit_code is None
    assert result.evidence(request())["termination_reason"] == "job_assignment_failed"
    await asyncio.sleep(0.2)
    assert not marker.exists()


@pytest.mark.parametrize(
    ("run_id", "attempt_id"),
    [
        ("../escape", "attempt-1"),
        ("run-1", "..\\escape"),
        ("/absolute", "attempt-1"),
        ("run.with.dot", "attempt-1"),
        ("run-1", ""),
    ],
)
def test_run_directory_components_reject_traversal(run_id: str, attempt_id: str):
    with pytest.raises(RunnerRequestError, match="sans séparateur"):
        request(run_id=run_id, attempt_id=attempt_id)


async def test_shell_metacharacters_are_literal_arguments(tmp_path: Path):
    marker = tmp_path / "must-not-exist"
    literal = f"; echo unsafe > {marker}"
    config = runner_config(
        tmp_path,
        "import json,sys; print(json.dumps(sys.argv[1:-1]))",
        extra_args=(literal,),
    )

    result = await run_local_program(config, request())

    assert result.succeeded
    assert json.loads(result.stdout.text) == [literal]
    assert not marker.exists()


async def test_environment_is_minimal_allowlisted_and_has_no_worker_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAFE_TEST_VALUE", "visible")
    monkeypatch.setenv("ACP_WORKER_REGISTRATION_TOKEN", "worker-secret")
    monkeypatch.setenv("ACP_GATEWAY_SERVICE_TOKEN", "gateway-secret")
    monkeypatch.setenv("CODEX_API_KEY", "codex-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    config = runner_config(
        tmp_path,
        "import json,os; print(json.dumps({"
        "'safe':os.environ.get('SAFE_TEST_VALUE'),"
        "'worker':'ACP_WORKER_REGISTRATION_TOKEN' in os.environ,"
        "'gateway':'ACP_GATEWAY_SERVICE_TOKEN' in os.environ,"
        "'codex':'CODEX_API_KEY' in os.environ,"
        "'anthropic':'ANTHROPIC_API_KEY' in os.environ,"
        "'path':'PATH' in os.environ}))",
        environment_allowlist=("SAFE_TEST_VALUE",),
    )

    result = await run_local_program(config, request())
    environment_seen = json.loads(result.stdout.text)

    assert environment_seen == {
        "safe": "visible",
        "worker": False,
        "gateway": False,
        "codex": False,
        "anthropic": False,
        "path": False,
    }


def test_reserved_environment_variables_cannot_be_overridden(tmp_path: Path):
    with pytest.raises(RunnerConfigurationError, match="réservée"):
        runner_config(
            tmp_path,
            "pass",
            environment_allowlist=("ACP_RUN_REQUEST_PATH",),
        )
    with pytest.raises(RunnerConfigurationError, match="secret de contrôle interdit"):
        runner_config(
            tmp_path,
            "pass",
            environment_allowlist=("ACP_GATEWAY_SERVICE_TOKEN",),
        )

    config = runner_config(tmp_path, "pass")
    run_request = request()
    request_path = tmp_path / "request.json"
    environment = restricted_run_environment(
        config,
        run_request,
        request_path,
        source={"ACP_RUN_REQUEST_PATH": "attacker-value"},
    )
    assert environment["ACP_RUN_REQUEST_PATH"] == str(request_path)


async def test_stdout_and_stderr_capture_is_bounded_but_hashes_full_streams(
    tmp_path: Path,
):
    config = runner_config(
        tmp_path,
        "import sys; sys.stdout.buffer.write(b'x'*4096); "
        "sys.stderr.buffer.write(b'y'*3072)",
        output_limit=64,
    )

    result = await run_local_program(config, request())

    assert result.succeeded
    assert result.stdout.text == "x" * 64
    assert result.stdout.captured_bytes == 64
    assert result.stdout.total_bytes == 4096
    assert result.stdout.truncated is True
    assert result.stdout.sha256 == hashlib.sha256(b"x" * 4096).hexdigest()
    assert result.stderr.text == "y" * 64
    assert result.stderr.captured_bytes == 64
    assert result.stderr.total_bytes == 3072
    assert result.stderr.truncated is True
    assert result.stderr.sha256 == hashlib.sha256(b"y" * 3072).hexdigest()


async def test_duplicate_attempt_directory_is_rejected(tmp_path: Path):
    config = runner_config(tmp_path, "print('ok')")
    run_request = request()
    first = await run_local_program(config, run_request)
    assert first.succeeded

    with pytest.raises(RunnerRequestError, match="rejeu implicite refusé"):
        await run_local_program(config, run_request)


async def test_spawn_failure_is_structured_and_never_success(tmp_path: Path):
    fake_executable = tmp_path / "configured-but-not-executable.bin"
    fake_executable.write_text("not an executable", encoding="utf-8")
    config = LocalRunnerConfig(
        argv=(str(fake_executable.resolve()),),
        run_root=tmp_path / "runs",
        timeout_seconds=1,
        max_output_bytes=64,
    )

    result = await run_local_program(config, request())

    assert result.succeeded is False
    assert result.status == "spawn_failed"
    assert result.exit_code is None
    assert result.termination_reason == "spawn_error"
    assert result.evidence(request())["status"] == "spawn_failed"


def test_configuration_is_fail_closed_and_requires_absolute_existing_program(
    tmp_path: Path,
):
    assert LocalRunnerConfig.from_environment({}) is None
    with pytest.raises(RunnerConfigurationError, match="requis ensemble"):
        LocalRunnerConfig.from_environment(
            {"ACP_WORKER_RUNNER_ARGV_JSON": json.dumps([sys.executable])}
        )
    with pytest.raises(RunnerConfigurationError, match="chemin absolu"):
        LocalRunnerConfig(
            argv=("python", "-V"),
            run_root=tmp_path / "runs",
        )
    with pytest.raises(RunnerConfigurationError, match="introuvable"):
        LocalRunnerConfig(
            argv=(str((tmp_path / "missing.exe").resolve()),),
            run_root=tmp_path / "runs",
        )
    writable_runner = tmp_path / "runs" / "mutable-runner.bin"
    writable_runner.parent.mkdir()
    writable_runner.write_text("mutable", encoding="utf-8")
    with pytest.raises(RunnerConfigurationError, match="racine inscriptible"):
        LocalRunnerConfig(
            argv=(str(writable_runner.resolve()),),
            run_root=tmp_path / "runs",
        )


def test_configuration_parses_only_an_argv_json_not_a_shell_string(tmp_path: Path):
    environment = {
        "ACP_WORKER_RUNNER_ARGV_JSON": json.dumps(
            [sys.executable, "-I", "-c", "print('ok')"]
        ),
        "ACP_WORKER_RUN_ROOT": str(tmp_path / "runs"),
        "ACP_WORKER_RUN_TIMEOUT_SECONDS": "12.5",
        "ACP_WORKER_RUN_MAX_OUTPUT_BYTES": "512",
        "ACP_WORKER_RUN_ENV_ALLOWLIST": "SAFE_ONE, SAFE_TWO",
    }

    config = LocalRunnerConfig.from_environment(environment)

    assert config is not None
    assert config.argv[0] == str(Path(sys.executable).resolve())
    assert config.timeout_seconds == 12.5
    assert config.max_output_bytes == 512
    assert config.environment_allowlist == ("SAFE_ONE", "SAFE_TWO")

    environment["ACP_WORKER_RUNNER_ARGV_JSON"] = f"{sys.executable} -c print('bad')"
    with pytest.raises(RunnerConfigurationError, match="JSON valide"):
        LocalRunnerConfig.from_environment(environment)
