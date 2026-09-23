"""Démarre Hermes isolé et lit santé/capacités, sans soumettre de Run.

Le profil neuf sous .test-tmp n'hérite d'aucun compte ou configuration utilisateur.
Ce contrôle ne prouve jamais la disponibilité d'un modèle ni une génération.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from uuid import uuid4

import httpx

from check_hermes_profile import check_profile

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "acp-data/tools/hermes-v2026.9.7")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    python = source / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    if not python.is_file():
        parser.error("Exécuter setup-hermes.ps1 auparavant.")
    directory = ROOT / ".test-tmp" / f"hermes-local-{uuid4().hex}"
    profile = directory / "profile"
    profile.mkdir(parents=True)
    check_profile(source, profile, managed=Path("/etc/hermes"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # Ni .env utilisateur, ni clés de modèle, ni profil CLI personnel.
    environment = {key: value for key, value in os.environ.items() if key in {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP", "LANG",
    }}
    token = secrets.token_urlsafe(32)
    environment.update({
        "HOME": str(profile), "USERPROFILE": str(profile),
        "APPDATA": str(profile / "appdata"), "LOCALAPPDATA": str(profile / "local"),
        "HERMES_HOME": str(profile), "CODEX_HOME": str(profile / "codex"),
        "CLAUDE_CONFIG_DIR": str(profile / "claude"), "PYTHONUTF8": "1",
        "API_SERVER_ENABLED": "true", "API_SERVER_HOST": "127.0.0.1",
        "API_SERVER_PORT": str(port), "API_SERVER_KEY": token,
        "HERMES_GATEWAY_NO_SUPERVISE": "1",
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "PYTHON_DOTENV_DISABLED": "1",
    })
    result = {"status": "not_started", "directory": str(directory),
              "run_submissions": 0, "isolated_profile": True}
    log_path = directory / "gateway.log"
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(python), "-m", "hermes_cli.main", "gateway", "run", "--no-supervise"],
                cwd=source, env=environment, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 90
                with httpx.Client(base_url=f"http://127.0.0.1:{port}",
                                  headers={"Authorization": f"Bearer {token}"},
                                  timeout=2, trust_env=False) as client:
                    while process.poll() is None and time.monotonic() < deadline:
                        try:
                            health = client.get("/health/detailed")
                            capabilities = client.get("/v1/capabilities")
                            if health.status_code in {200, 503} and capabilities.status_code == 200:
                                result.update(status="server_reachable", health=health.json(),
                                              capabilities=capabilities.json())
                                break
                        except (httpx.HTTPError, ValueError):
                            pass
                        time.sleep(0.5)
                if result["status"] == "not_started":
                    result.update(status="startup_failed" if process.poll() is not None else "startup_timeout",
                                  exit_code=process.poll())
            finally:
                # --no-supervise : seul l'arbre lancé ici est concerné.
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    finally:
        if log_path.exists():
            log_path.write_text(log_path.read_text(encoding="utf-8", errors="replace").replace(token, "[REDACTED]"),
                                encoding="utf-8")
        encoded = json.dumps(result, ensure_ascii=False, indent=2).replace(token, "[REDACTED]")
        (directory / "result.json").write_text(encoded, encoding="utf-8")
    print(json.dumps({"status": result["status"], "directory": str(directory), "run_submissions": 0}))
    return 0 if result["status"] == "server_reachable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
