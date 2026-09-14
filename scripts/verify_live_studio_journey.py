"""Preuve locale opt-in du shell et du Studio dans un vrai navigateur.

Sans ``ACP_E2E=1``, le script s'arrête explicitement avec ``SKIPPED``. Avec
l'opt-in, il démarre une API et Vite sur deux ports de bouclage, initialise une
base SQLite temporaire par les routes publiques, puis exécute le paquet E2E
Playwright contre ces vrais services. Aucun fournisseur IA ni service payant
n'est contacté.
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NoReturn

import httpx


WORKTREE = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable).resolve()
SOURCE_ROOTS = (
    WORKTREE / "packages" / "contracts" / "src",
    WORKTREE / "packages" / "database" / "src",
    WORKTREE / "packages" / "agent-sdk" / "src",
    WORKTREE / "packages" / "event-sdk" / "src",
    WORKTREE / "packages" / "provider-sdk" / "src",
    WORKTREE / "apps" / "api" / "src",
    WORKTREE / "apps" / "worker" / "src",
    WORKTREE / "apps" / "cli" / "src",
    WORKTREE / "apps" / "event-service" / "src",
    WORKTREE / "services" / "provider-gateway" / "src",
)
SAFE_PARENT_ENVIRONMENT = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)


class JourneyError(RuntimeError):
    """Échec contrôlé d'une preuve indispensable."""


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _base_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in SAFE_PARENT_ENVIRONMENT
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def _python_environment() -> dict[str, str]:
    environment = _base_environment()
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in SOURCE_ROOTS)
    return environment


def _assert_source_provenance(environment: dict[str, str]) -> None:
    probe = subprocess.run(
        [
            str(PYTHON),
            "-c",
            (
                "from pathlib import Path; "
                "import acp_api, acp_contracts, acp_database; "
                "print(Path(acp_api.__file__).resolve()); "
                "print(Path(acp_contracts.__file__).resolve()); "
                "print(Path(acp_database.__file__).resolve())"
            ),
        ],
        cwd=WORKTREE,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    imported = [Path(line).resolve() for line in probe.stdout.splitlines() if line]
    if len(imported) != 3 or any(
        not path.is_relative_to(WORKTREE) for path in imported
    ):
        raise JourneyError("les imports Python ne proviennent pas du worktree courant")


def _vault_key(environment: dict[str, str]) -> str:
    result = subprocess.run(
        [
            str(PYTHON),
            "-c",
            "from acp_api.secrets_vault import generate_key; print(generate_key())",
        ],
        cwd=WORKTREE,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _start_process(command: list[str], environment: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=WORKTREE,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        else:
            process.kill()
        process.wait(timeout=10)


def _process_output(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        return ""
    return process.stdout.read()[-3000:].strip()


def _abort_process(process: subprocess.Popen[str], label: str) -> NoReturn:
    _stop_process(process)
    detail = _process_output(process)
    raise JourneyError(f"{label}: {detail or 'aucune sortie du processus'}")


def _wait_http(process: subprocess.Popen[str], url: str) -> bool:
    for _ in range(160):
        if process.poll() is not None:
            return False
        try:
            response = httpx.get(
                url,
                timeout=1.0,
                trust_env=False,
                follow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    return False


def _json_response(label: str, response: httpx.Response) -> dict:
    if response.status_code < 200 or response.status_code >= 300:
        raise JourneyError(f"{label}: HTTP {response.status_code} — {response.text[:500]}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise JourneyError(f"{label}: réponse JSON invalide") from exc
    if not isinstance(payload, dict):
        raise JourneyError(f"{label}: objet JSON attendu")
    return payload


def _seed_real_api(
    api_origin: str, bootstrap_token: str
) -> tuple[str, str, str]:
    login = f"e2e-{secrets.token_hex(8)}"
    password = secrets.token_urlsafe(32)
    with httpx.Client(
        base_url=api_origin,
        timeout=30.0,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        bootstrap = _json_response(
            "bootstrap",
            client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": login,
                    "display_name": "Preuve E2E locale",
                    "password": password,
                },
            ),
        )
        client.headers["X-CSRF-Token"] = str(bootstrap["csrf_token"])
        organization = _json_response(
            "organisation",
            client.post("/organizations", json={"name": "Preuve E2E locale"}),
        )
        workspace = _json_response(
            "workspace",
            client.post(
                "/workspaces",
                json={
                    "organization_id": organization["id"],
                    "name": "Studio Playwright",
                },
            ),
        )
        project = _json_response(
            "projet",
            client.post(
                "/projects",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Parcours navigateur réel",
                },
            ),
        )
        agent = _json_response(
            "agent",
            client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Agent E2E",
                    "role_id": "tester",
                    "capabilities": ["web_tests"],
                },
            ),
        )
        mission = _json_response(
            "mission",
            client.post(
                "/missions",
                headers={"Idempotency-Key": "lot-g-live-shell-studio-v1"},
                json={
                    "project_id": project["id"],
                    "agent_instance_id": agent["id"],
                    "title": "Preuve du Studio réel",
                    "objective": "Ouvrir une tentative réelle dans le Studio",
                    "expected_outcome": "Le shell charge la chronologie sans erreur",
                    "acceptance_criteria": [
                        "authentification réelle",
                        "mission et événements réellement relus",
                    ],
                    "autonomy": {
                        "mode": "bounded",
                        "allowed_actions": ["read"],
                        "forbidden_actions": ["deploy", "purchase"],
                        "approval_required_actions": [],
                    },
                    "resources": [],
                    "budget": {"currency": "EUR", "max_tool_calls": 1},
                    "duration_seconds": 120,
                    "required_capabilities": ["web_tests"],
                },
            ),
        )
    current_run = mission.get("current_run")
    if not isinstance(current_run, dict) or not isinstance(current_run.get("id"), str):
        raise JourneyError("mission: tentative courante absente")
    return login, password, current_run["id"]


def _remove_directory(path: Path) -> None:
    for attempt in range(10):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def main() -> int:
    opt_in = os.environ.get("ACP_E2E", "")
    if opt_in in {"", "0"}:
        print("[E2E SKIPPED] ACP_E2E=1 est requis pour lancer les services et le navigateur.")
        return 0
    if opt_in != "1":
        print("[E2E FAILED] ACP_E2E doit valoir exactement 1, 0 ou être absent.")
        return 2

    npm = shutil.which("npm.cmd") if os.name == "nt" else shutil.which("npm")
    npm = npm or shutil.which("npm")
    if npm is None:
        print("[E2E FAILED] npm est introuvable.")
        return 2
    if not (WORKTREE / "e2e" / "node_modules" / "@playwright" / "test").is_dir():
        print("[E2E FAILED] Exécutez d'abord `npm ci --prefix e2e`.")
        return 2

    api_port = _free_loopback_port()
    web_port = _free_loopback_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    web_origin = f"http://127.0.0.1:{web_port}"
    bootstrap_token = secrets.token_urlsafe(32)
    api_process: subprocess.Popen[str] | None = None
    web_process: subprocess.Popen[str] | None = None
    verify_dir: Path | None = None

    try:
        verify_dir = Path(tempfile.mkdtemp(prefix="acp-live-studio-"))
        python_environment = _python_environment()
        _assert_source_provenance(python_environment)
        api_environment = dict(python_environment)
        api_environment.update(
            {
                "ACP_API_URL": api_origin,
                "ACP_ARTIFACT_STORAGE_DIR": str(verify_dir / "artifacts"),
                "ACP_BOOTSTRAP_TOKEN": bootstrap_token,
                "ACP_CORS_ORIGINS": web_origin,
                "ACP_DATABASE_URL": f"sqlite:///{(verify_dir / 'journey.db').as_posix()}",
                "ACP_PLUGINS_DIR": str(verify_dir / "plugins"),
                "ACP_PROVIDER_GATEWAY_URL": "http://127.0.0.1:9",
                "ACP_SESSION_COOKIE_SECURE": "0",
                "ACP_SECRETS_KEYS": _vault_key(python_environment),
                "ACP_SKILLS_STORAGE_DIR": str(verify_dir / "skills"),
            }
        )
        api_process = _start_process(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "acp_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
                "--log-level",
                "warning",
            ],
            api_environment,
        )
        if not _wait_http(api_process, f"{api_origin}/health"):
            _abort_process(api_process, "API non démarrée")

        login, password, run_id = _seed_real_api(api_origin, bootstrap_token)

        web_environment = _base_environment()
        web_environment["VITE_ACP_API_URL"] = api_origin
        web_process = _start_process(
            [
                npm,
                "run",
                "dev",
                "--workspace",
                "@acp/web",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
                "--strictPort",
            ],
            web_environment,
        )
        if not _wait_http(web_process, web_origin):
            _abort_process(web_process, "interface Vite non démarrée")

        test_environment = _base_environment()
        test_environment.update(
            {
                "ACP_E2E": "1",
                "ACP_E2E_ALLOWED_ORIGIN": web_origin,
                "ACP_E2E_API_ORIGIN": api_origin,
                "ACP_E2E_BASE_URL": web_origin,
                "ACP_E2E_BROWSER_CHANNEL": os.environ.get(
                    "ACP_E2E_BROWSER_CHANNEL", "chromium"
                ),
                "ACP_E2E_LOGIN": login,
                "ACP_E2E_PASSWORD": password,
                "ACP_E2E_RUN_ID": run_id,
            }
        )
        result = subprocess.run(
            [npm, "run", "test:e2e"],
            cwd=WORKTREE,
            env=test_environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            raise JourneyError(f"Playwright a échoué (code {result.returncode}):\n{output[-6000:]}")
        print(result.stdout.strip())
        print(
            "[E2E PASSED] API, authentification, CORS, shell, mission, événements "
            "et Studio vérifiés dans un vrai navigateur."
        )
        return 0
    except (JourneyError, OSError, subprocess.SubprocessError, httpx.HTTPError) as exc:
        print(f"[E2E FAILED] {type(exc).__name__}: {exc}")
        return 1
    finally:
        if web_process is not None:
            _stop_process(web_process)
        if api_process is not None:
            _stop_process(api_process)
        if verify_dir is not None:
            try:
                _remove_directory(verify_dir)
            except OSError as exc:
                print(f"[E2E FAILED] nettoyage temporaire: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
