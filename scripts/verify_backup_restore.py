"""Vérification de bout en bout de la sauvegarde et de la restauration (Lot H).

Le script démarre l'API sur une base A et des répertoires temporaires, crée des
données par les seules routes HTTP (bootstrap, organisation, projet, mission,
secret, worker global, pièce téléversée, clôture de la tentative), relit chaque
objet, arrête l'API, puis enchaîne ``python -m acp_api.backup create``,
``verify`` et ``restore`` vers une base B et des répertoires neufs. L'API est
redémarrée sur B, le propriétaire se reconnecte par mot de passe, et chaque
relecture ``GET`` doit être identique à celle faite sur A (le contenu de la pièce
compris). Une seconde restauration vers B, désormais occupée, doit être refusée.

Base de données : sans option, deux fichiers SQLite temporaires jouent A et B.
``--database-url`` et ``--restore-database-url`` (ensemble) acceptent deux URL
``postgresql+psycopg://`` distinctes : A est migrée par
``python -m acp_database.migrate upgrade`` avant l'API, B doit être vide (aucune
table) au départ, et les deux schémas ``public`` sont remis à zéro à la fin par
SQLAlchemy. Les binaires ``pg_dump``/``pg_restore`` proviennent des variables
``ACP_BACKUP_PG_DUMP_COMMAND`` et ``ACP_BACKUP_PG_RESTORE_COMMAND`` de
l'environnement appelant (transmises telles quelles) ; si
``ACP_BACKUP_DATABASE_URL_FOR_TOOLS`` est posée, elle sert de **modèle** dont le nom
de base est remplacé par celui de A ou de B pour chaque commande.

Il n'effectue aucun appel Internet et ne dépense rien.

Usage, depuis la racine du dépôt, avec l'environnement installé par
``scripts/setup`` :

```
.venv/Scripts/python.exe scripts/verify_backup_restore.py                      # Windows
.venv/bin/python scripts/verify_backup_restore.py                              # Linux/macOS
ACP_BACKUP_PG_DUMP_COMMAND='["docker","exec","acp-pg","pg_dump","--format=custom","--no-owner","--no-privileges","--dbname","{url}"]' \
ACP_BACKUP_PG_RESTORE_COMMAND='["docker","exec","-i","acp-pg","pg_restore","--no-owner","--no-privileges","--exit-on-error","--single-transaction","--dbname","{url}"]' \
ACP_BACKUP_DATABASE_URL_FOR_TOOLS='postgresql://acp:acp@127.0.0.1:5432/acp_h4' \
.venv/bin/python scripts/verify_backup_restore.py \
    --database-url postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_h4 \
    --restore-database-url postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_h4_restore
```

Sortie : une ligne par étape, puis un VERDICT. Code de retour 0 si toutes les
étapes passent, 1 sinon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


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

POSTGRES_URL_PREFIX = "postgresql+psycopg://"
BACKUP_ENV_PASSTHROUGH = (
    "ACP_BACKUP_PG_DUMP_COMMAND",
    "ACP_BACKUP_PG_RESTORE_COMMAND",
)
TOOLS_URL_ENV = "ACP_BACKUP_DATABASE_URL_FOR_TOOLS"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

steps: list[tuple[str, bool, str]] = []


class JourneyStopped(RuntimeError):
    """Arrêt contrôlé après une étape indispensable en échec."""


def step(label: str, ok: bool, detail: str = "") -> None:
    steps.append((label, ok, detail))
    mark = "OK   " if ok else "ECHEC"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""), flush=True)


def require(label: str, condition: bool, detail: str = "") -> None:
    step(label, condition, detail)
    if not condition:
        raise JourneyStopped(label)


def require_http(
    label: str,
    response: httpx.Response,
    expected: int | tuple[int, ...] = 200,
) -> dict:
    statuses = (expected,) if isinstance(expected, int) else expected
    require(
        label,
        response.status_code in statuses,
        f"HTTP {response.status_code} (attendu {', '.join(map(str, statuses))})",
    )
    if response.status_code == 204:
        return {}
    try:
        payload = response.json()
    except ValueError as exc:
        step(f"{label} : réponse JSON", False, "corps JSON invalide")
        raise JourneyStopped(label) from exc
    if not isinstance(payload, dict):
        step(f"{label} : réponse objet", False, "objet JSON attendu")
        raise JourneyStopped(label)
    return payload


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _isolated_subprocess_environment() -> dict[str, str]:
    """Conserve uniquement le runtime nécessaire, jamais les secrets du poste."""

    allowed = {
        "PATH",
        "PYTHONHOME",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "VIRTUAL_ENV",
        "WINDIR",
    }
    env = {name: value for name, value in os.environ.items() if name.upper() in allowed}
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in SOURCE_ROOTS)
    # Les enfants écrivent en UTF-8 quelle que soit la console : leur sortie est
    # relue en UTF-8 par ce script, et une console cp1252 rendrait les accents
    # illisibles ou ferait échouer une étape sur un simple message.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _assert_subprocess_provenance(env: dict[str, str]) -> None:
    """Refuse de tester silencieusement les paquets d'un autre checkout."""

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
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    imported = [
        Path(line.strip()).resolve() for line in probe.stdout.splitlines() if line.strip()
    ]
    if len(imported) != 3 or any(not path.is_relative_to(WORKTREE) for path in imported):
        rendered = ", ".join(str(path) for path in imported) or "aucun chemin"
        raise RuntimeError(
            "Le parcours importerait des paquets hors du worktree courant : " + rendered
        )


def _vault_key(env: dict[str, str]) -> str:
    return subprocess.run(
        [
            str(PYTHON),
            "-c",
            "from acp_api.secrets_vault import generate_key; print(generate_key())",
        ],
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


# --- Bases de données ----------------------------------------------------------------


def check_database_arguments(source: str | None, target: str | None) -> None:
    """Refuse toute configuration autre que « rien » ou « deux URL PostgreSQL distinctes »."""

    if source is None and target is None:
        return
    if source is None or target is None:
        step(
            "URL de base acceptées",
            False,
            "--database-url et --restore-database-url vont ensemble",
        )
        raise JourneyStopped("url de base refusée")
    for label, argument in (("A", source), ("B", target)):
        if not argument.startswith(POSTGRES_URL_PREFIX):
            step(
                "URL de base acceptées",
                False,
                f"base {label} : seule une URL {POSTGRES_URL_PREFIX} est acceptée ; sans "
                "option, deux bases SQLite temporaires sont créées puis supprimées",
            )
            raise JourneyStopped("url de base refusée")
        try:
            make_url(argument)
        except Exception as exc:  # noqa: BLE001 - toute URL illisible est refusée
            step("URL de base acceptées", False, f"base {label} illisible : {exc}")
            raise JourneyStopped("url de base refusée") from exc
    if make_url(source).database == make_url(target).database and make_url(
        source
    ).host == make_url(target).host:
        step("URL de base acceptées", False, "A et B doivent être deux bases distinctes")
        raise JourneyStopped("url de base refusée")
    step("URL de base acceptées", True, f"{redacted_url(source)} → {redacted_url(target)}")


def redacted_url(database_url: str) -> str:
    """URL sans mot de passe : le verdict est un journal, jamais un secret."""

    return make_url(database_url).render_as_string(hide_password=True)


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith(POSTGRES_URL_PREFIX)


def migrate_schema(env: dict[str, str], database_url: str) -> None:
    result = subprocess.run(
        [str(PYTHON), "-m", "acp_database.migrate", "upgrade", "--database-url", database_url],
        cwd=WORKTREE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=300,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    require(
        "Schéma A migré par acp_database.migrate upgrade",
        result.returncode == 0,
        output[-800:] or f"code {result.returncode}",
    )


def table_count(database_url: str) -> int:
    engine = create_engine(database_url)
    try:
        return len(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def observed_dialect(database_url: str) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            name = connection.dialect.name
            if name == "postgresql":
                version = connection.execute(text("SHOW server_version")).scalar_one()
            elif name == "sqlite":
                version = connection.execute(text("SELECT sqlite_version()")).scalar_one()
            else:
                version = "version inconnue"
            return f"{name} {version}"
    finally:
        engine.dispose()


def reset_postgres_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def backup_environment(base_env: dict[str, str], *, database_url: str, vault_key: str) -> dict[str, str]:
    """Environnement de ``acp_api.backup`` : outils transmis, URL d'outils dérivée."""

    env = dict(base_env)
    env["ACP_SECRETS_KEYS"] = vault_key
    for name in BACKUP_ENV_PASSTHROUGH:
        value = os.environ.get(name)
        if value:
            env[name] = value
    template = (os.environ.get(TOOLS_URL_ENV) or "").strip()
    if template and is_postgres_url(database_url):
        env[TOOLS_URL_ENV] = (
            make_url(template)
            .set(database=make_url(database_url).database)
            .render_as_string(hide_password=False)
        )
    return env


def run_backup(
    env: dict[str, str], label: str, *argv: str, expected_code: int = 0
) -> tuple[int, str]:
    result = subprocess.run(
        [str(PYTHON), "-m", "acp_api.backup", *argv],
        cwd=WORKTREE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    lines = [line for line in output.splitlines() if line.strip()]
    if result.returncode == expected_code:
        detail = f"code {result.returncode} : {lines[-1] if lines else 'aucune sortie'}"
    else:
        detail = f"code {result.returncode} (attendu {expected_code}) : {output[-600:]}"
    require(label, result.returncode == expected_code, detail)
    return result.returncode, output


# --- Processus -------------------------------------------------------------------------


def start_api(
    *,
    port: int,
    database_url: str,
    artifacts_dir: Path,
    skills_dir: Path,
    plugins_dir: Path,
    bootstrap_token: str,
    worker_registration_token: str,
    worker_token_pepper: str,
    vault_key: str,
) -> subprocess.Popen[str]:
    env = _isolated_subprocess_environment()
    _assert_subprocess_provenance(env)
    env.update(
        {
            "ACP_ARTIFACT_STORAGE_DIR": str(artifacts_dir),
            "ACP_BOOTSTRAP_TOKEN": bootstrap_token,
            "ACP_DATABASE_URL": database_url,
            "ACP_PLUGINS_DIR": str(plugins_dir),
            "ACP_PROVIDER_GATEWAY_URL": "http://127.0.0.1:9",
            "ACP_SESSION_COOKIE_SECURE": "0",
            "ACP_SECRETS_KEYS": vault_key,
            "ACP_SKILLS_STORAGE_DIR": str(skills_dir),
            "ACP_WORKER_REGISTRATION_GLOBAL_ACCESS": "1",
            "ACP_WORKER_REGISTRATION_TOKEN": worker_registration_token,
            "ACP_WORKER_TOKEN_PEPPER": worker_token_pepper,
            "PYTHONUNBUFFERED": "1",
        }
    )
    return subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "acp_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=WORKTREE,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )


def wait_for_api(process: subprocess.Popen[str], api_url: str) -> bool:
    for _ in range(120):
        if process.poll() is not None:
            return False
        try:
            response = httpx.get(f"{api_url}/health", timeout=1.0, trust_env=False)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    return False


def _abort_with_api_output(process: subprocess.Popen[str], label: str) -> NoReturn:
    _stop_process(process)
    output = process.stdout.read() if process.stdout else ""
    step(label, False, output[-1500:].strip() or "aucune sortie du processus")
    raise JourneyStopped(label)


def _stop_process(process: subprocess.Popen[str]) -> bool:
    """Arrête un processus par le signal gracieux ; ``True`` s'il l'a honoré seul."""

    if process.poll() is not None:
        return True
    if os.name == "nt":
        # terminate() saute le lifespan ASGI et laisse des handles SQLite ouverts ;
        # CTRL_BREAK laisse Uvicorn libérer le moteur avant le remplacement du fichier.
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
        return True
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        else:
            process.kill()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"le processus {process.pid} ne s'est pas arrêté") from exc
        return False


def _remove_verify_directory(directory: Path) -> None:
    last_error: PermissionError | None = None
    for attempt in range(20):
        try:
            shutil.rmtree(directory)
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(min(0.05 * (attempt + 1), 0.5))
    assert last_error is not None
    raise last_error


# --- Données ---------------------------------------------------------------------------


def _mission_payload(project_id: str, agent_id: str) -> dict:
    return {
        "project_id": project_id,
        "agent_instance_id": agent_id,
        "title": "Mission de vérification de la sauvegarde",
        "objective": "Produire une pièce puis survivre à une restauration",
        "expected_outcome": "Une relecture identique sur la base restaurée",
        "acceptance_criteria": ["chaque GET est identique après restauration"],
        "autonomy": {
            "mode": "bounded",
            "allowed_actions": ["read"],
            "forbidden_actions": ["deploy", "purchase"],
            "approval_required_actions": [],
        },
        "resources": [],
        "budget": {"currency": "EUR", "max_tool_calls": 1},
        "duration_seconds": 600,
        "required_capabilities": [],
    }


def _artifact_bytes() -> bytes:
    """Contenu binaire déterministe, non textuel, avec des octets nuls."""

    return b"ACP-H4\x00" + bytes(range(256)) * 4 + "rapport de sauvegarde é".encode("utf-8")


def snapshot_reads(client: httpx.Client, identifiers: dict[str, str], *, phase: str) -> dict:
    """Relit chaque objet créé ; le dictionnaire retourné est comparé entre A et B."""

    projects = client.get("/projects")
    project = next(
        (
            item
            for item in (projects.json() if projects.status_code == 200 else [])
            if isinstance(item, dict) and item.get("id") == identifiers["project_id"]
        ),
        None,
    )
    require(
        f"Projet relu ({phase})",
        project is not None,
        f"HTTP {projects.status_code}",
    )
    mission = require_http(
        f"Mission relue ({phase})", client.get(f"/missions/{identifiers['mission_id']}")
    )
    artifact = require_http(
        f"Pièce relue ({phase})", client.get(f"/artifacts/{identifiers['artifact_id']}")
    )
    content = client.get(f"/artifacts/{identifiers['artifact_id']}/content")
    require(
        f"Contenu de la pièce relu ({phase})",
        content.status_code == 200 and content.content == _artifact_bytes(),
        f"HTTP {content.status_code}, {len(content.content)} octets",
    )
    secrets_list = client.get("/secrets")
    require(
        f"Secrets relus ({phase})",
        secrets_list.status_code == 200 and isinstance(secrets_list.json(), list),
        f"HTTP {secrets_list.status_code}",
    )
    return {
        "project": project,
        "mission": mission,
        "artifact": artifact,
        "content_sha256": hashlib.sha256(content.content).hexdigest(),
        "secrets": secrets_list.json(),
    }


def run_setup_phase(
    client: httpx.Client,
    *,
    bootstrap_token: str,
    worker_registration_token: str,
) -> tuple[dict[str, str], dict]:
    owner_login = f"verification-{secrets.token_hex(12)}"
    owner_password = secrets.token_urlsafe(32)
    bootstrap = require_http(
        "Bootstrap du propriétaire",
        client.post(
            "/auth/bootstrap",
            headers={"X-ACP-Bootstrap-Token": bootstrap_token},
            json={
                "login": owner_login,
                "display_name": "Vérification sauvegarde",
                "password": owner_password,
            },
        ),
        201,
    )
    client.headers["X-CSRF-Token"] = bootstrap["csrf_token"]

    organization = require_http(
        "Organisation créée",
        client.post("/organizations", json={"name": "Org vérification sauvegarde"}),
    )
    workspace = require_http(
        "Workspace créé",
        client.post(
            "/workspaces",
            json={"organization_id": organization["id"], "name": "Workspace sauvegarde"},
        ),
    )
    project = require_http(
        "Projet créé",
        client.post(
            "/projects",
            json={"workspace_id": workspace["id"], "name": "Projet sauvegarde"},
        ),
    )
    agent = require_http(
        "Agent créé",
        client.post(
            "/agents",
            json={
                "workspace_id": workspace["id"],
                "name": "Agent sauvegarde",
                "role_id": "developer",
                "capabilities": [],
            },
        ),
    )
    mission = require_http(
        "Mission mise en file",
        client.post(
            "/missions",
            headers={"Idempotency-Key": "lot-h-backup-journey-create"},
            json=_mission_payload(project["id"], agent["id"]),
        ),
        201,
    )
    secret = require_http(
        "Secret chiffré créé",
        client.post(
            "/secrets",
            json={
                "name": "H4_JETON",
                "value": secrets.token_urlsafe(16),
                "scope_type": "platform",
                "description": "secret du parcours de sauvegarde",
            },
        ),
        201,
    )
    require(
        "Le secret expose l'identifiant de clé, jamais la valeur",
        bool(secret.get("key_id")) and "value" not in secret,
        f"key_id={secret.get('key_id')}",
    )

    worker = require_http(
        "Worker global enrôlé",
        client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": worker_registration_token},
            json={
                "name": f"verify-backup-worker-{secrets.token_hex(8)}",
                "capabilities": [],
                "max_concurrency": 1,
                "simulation": False,
                "global_access": True,
                "metadata": {"purpose": "lot-h-backup-verification"},
            },
        ),
        201,
    )
    worker_id = worker["worker_id"]
    worker_headers = {"Authorization": f"Bearer {worker['token']}"}
    claim = require_http(
        "Tentative attribuée au worker (claim)",
        client.post(
            f"/workers/{worker_id}/claim", headers=worker_headers, json={"provider_id": "mock"}
        ),
    )
    require(
        "Le claim porte la tentative et un jeton de fencing",
        claim.get("task") is not None and isinstance(claim.get("fencing_token"), int),
        f"attempt={claim.get('attempt_id')}",
    )
    run_id = claim["attempt_id"]
    fenced_headers = {
        **worker_headers,
        "X-Worker-Id": worker_id,
        "X-Attempt-Fencing-Token": str(claim["fencing_token"]),
    }
    payload = _artifact_bytes()
    upload = require_http(
        "Pièce téléversée par la route worker fencée",
        client.post(
            f"/workers/{worker_id}/artifacts/content",
            headers=fenced_headers,
            files={"file": ("rapport.bin", payload, "application/octet-stream")},
            data={
                "kind": "report",
                "stream_kind": "file",
                "task_run_id": run_id,
                "project_id": project["id"],
            },
        ),
        201,
    )
    require(
        "La pièce est adressée par son sha256",
        upload.get("checksum") == hashlib.sha256(payload).hexdigest()
        and upload.get("size_bytes") == len(payload),
        f"checksum={str(upload.get('checksum'))[:12]}…",
    )
    require_http(
        "Tentative passée en exécution par le worker",
        client.patch(
            f"/task-runs/{run_id}",
            headers=fenced_headers,
            json={"status": "running"},
        ),
    )
    closed = require_http(
        "Tentative close par le worker",
        client.patch(
            f"/task-runs/{run_id}",
            headers=fenced_headers,
            json={
                "status": "succeeded",
                "technical_validation": {
                    "status": "passed",
                    "summary": "pièce téléversée et adressée par son sha256",
                },
                "evidence": [
                    {
                        "kind": "artifact",
                        "summary": "rapport binaire livré",
                        "data": {"artifact_id": upload["id"]},
                        "checksum": upload.get("checksum"),
                    }
                ],
                "append_logs": [{"level": "info", "message": "pièce livrée"}],
            },
        ),
    )
    require(
        "La tentative est terminale et datée",
        closed.get("status") == "succeeded" and closed.get("finished_at") is not None,
        f"status={closed.get('status')}",
    )
    identifiers = {
        "project_id": project["id"],
        "mission_id": mission["id"],
        "artifact_id": upload["id"],
        "secret_id": secret["id"],
    }
    credentials = {"login": owner_login, "password": owner_password}
    return identifiers, credentials


def run_restored_phase(
    api_url: str, *, identifiers: dict[str, str], credentials: dict, before: dict
) -> None:
    with httpx.Client(
        base_url=api_url, timeout=30.0, trust_env=False, follow_redirects=False
    ) as client:
        login = require_http(
            "Connexion par mot de passe sur la base restaurée",
            client.post("/auth/login", json=credentials),
        )
        client.headers["X-CSRF-Token"] = login["csrf_token"]
        after = snapshot_reads(client, identifiers, phase="B")
    for key, label in (
        ("project", "Projet identique après restauration"),
        ("mission", "Mission identique après restauration"),
        ("artifact", "Pièce identique après restauration"),
        ("content_sha256", "Contenu de la pièce identique après restauration"),
        ("secrets", "Secrets identiques après restauration"),
    ):
        same = before[key] == after[key]
        detail = "" if same else f"A={json.dumps(before[key])[:200]} B={json.dumps(after[key])[:200]}"
        require(label, same, detail)


# --- Point d'entrée ----------------------------------------------------------------------


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rejoue le parcours sauvegarde → vérification → restauration contre une "
            "API réellement démarrée sur le bouclage."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL postgresql+psycopg:// de la base A (migrée avant l'API, remise à zéro à la fin)",
    )
    parser.add_argument(
        "--restore-database-url",
        default=None,
        help="URL postgresql+psycopg:// de la base B (vide au départ, remise à zéro à la fin)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    steps.clear()
    arguments = _parse_arguments(argv)
    port = _free_loopback_port()
    api_url = f"http://127.0.0.1:{port}"
    bootstrap_token = secrets.token_urlsafe(32)
    worker_registration_token = secrets.token_urlsafe(32)
    worker_token_pepper = secrets.token_urlsafe(32)
    process: subprocess.Popen[str] | None = None
    verify_dir: Path | None = None
    # Remplie une URL à la fois, et seulement après avoir prouvé que la base
    # correspondante était vide : un refus ne doit jamais effacer les données
    # d'une base que ce parcours vient précisément de refuser de toucher.
    postgres_urls: list[str] = []
    dialect = "inconnu"

    try:
        check_database_arguments(arguments.database_url, arguments.restore_database_url)
        verify_dir = Path(tempfile.mkdtemp(prefix="acp-backup-e2e-"))
        if arguments.database_url is None:
            url_a = f"sqlite:///{(verify_dir / 'base-a.db').as_posix()}"
            url_b = f"sqlite:///{(verify_dir / 'base-b.db').as_posix()}"
        else:
            url_a, url_b = arguments.database_url, arguments.restore_database_url
        dirs_a = {name: verify_dir / "a" / name for name in ("artifacts", "skills", "plugins")}
        dirs_b = {name: verify_dir / "b" / name for name in ("artifacts", "skills", "plugins")}
        subprocess_env = _isolated_subprocess_environment()
        vault_key = _vault_key(subprocess_env)
        if arguments.database_url is not None:
            # Chaque base est vérifiée vide AVANT d'entrer dans la liste de
            # nettoyage : ce parcours n'efface que ce qu'il a lui-même écrit.
            count_a = table_count(url_a)
            require(
                "Base A vide au départ",
                count_a == 0,
                f"{count_a} table(s) dans {redacted_url(url_a)} : ce parcours "
                "remet le schéma public à zéro et refuse une base déjà peuplée",
            )
            postgres_urls.append(url_a)
            count_b = table_count(url_b)
            require(
                "Base B vide au départ",
                count_b == 0,
                f"{count_b} table(s) dans {redacted_url(url_b)} : ce parcours "
                "remet le schéma public à zéro et refuse une base déjà peuplée",
            )
            postgres_urls.append(url_b)
            migrate_schema(subprocess_env, url_a)
        common = {
            "bootstrap_token": bootstrap_token,
            "worker_registration_token": worker_registration_token,
            "worker_token_pepper": worker_token_pepper,
            "vault_key": vault_key,
        }
        try:
            process = start_api(
                port=port,
                database_url=url_a,
                artifacts_dir=dirs_a["artifacts"],
                skills_dir=dirs_a["skills"],
                plugins_dir=dirs_a["plugins"],
                **common,
            )
            if not wait_for_api(process, api_url):
                _abort_with_api_output(process, "API démarrée sur la base A")
            step("API démarrée sur la base A", True, api_url)
            dialect = observed_dialect(url_a)
            with httpx.Client(
                base_url=api_url, timeout=30.0, trust_env=False, follow_redirects=False
            ) as client:
                identifiers, credentials = run_setup_phase(
                    client,
                    bootstrap_token=bootstrap_token,
                    worker_registration_token=worker_registration_token,
                )
                before = snapshot_reads(client, identifiers, phase="A")
            stopped = _stop_process(process)
            process = None
            step("API arrêtée proprement avant la sauvegarde", stopped)

            backup_dir = verify_dir / "sauvegarde"
            env_a = backup_environment(subprocess_env, database_url=url_a, vault_key=vault_key)
            run_backup(
                env_a,
                "Sauvegarde créée (base puis fichiers)",
                "create",
                "--output",
                str(backup_dir),
                "--database-url",
                url_a,
                "--artifacts-dir",
                str(dirs_a["artifacts"]),
                "--skills-dir",
                str(dirs_a["skills"]),
                "--label",
                "parcours-h4",
            )
            manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
            require(
                "Manifeste complet (révision, comptages, clé de secret, pièce citée)",
                manifest.get("format_version") == 1
                and manifest["database"].get("alembic_current")
                and manifest["database"]["row_counts"].get("artifacts", 0) >= 1
                and len(manifest.get("secrets_key_ids", [])) == 1
                and len(manifest.get("artifact_storage_keys_referenced", [])) == 1,
                f"révision={manifest['database'].get('alembic_current')}, "
                f"lignes={sum(manifest['database']['row_counts'].values())}",
            )
            run_backup(env_a, "Sauvegarde vérifiée", "verify", str(backup_dir))
            run_backup(env_a, "Sauvegarde inspectée", "inspect", str(backup_dir))

            env_b = backup_environment(subprocess_env, database_url=url_b, vault_key=vault_key)
            restore_argv = (
                "restore",
                str(backup_dir),
                "--into",
                url_b,
                "--artifacts-dir",
                str(dirs_b["artifacts"]),
                "--skills-dir",
                str(dirs_b["skills"]),
                "--require-secret-keys",
            )
            _code, output = run_backup(env_b, "Restauration dans la base B", *restore_argv)
            conformant = "Contrôles post-restauration conformes" in output
            require(
                "Contrôles post-restauration conformes au manifeste",
                conformant,
                "" if conformant else output[-300:],
            )
            run_backup(
                env_b,
                "Seconde restauration refusée : B n'est plus vide",
                *restore_argv,
                expected_code=3,
            )

            process = start_api(
                port=port,
                database_url=url_b,
                artifacts_dir=dirs_b["artifacts"],
                skills_dir=dirs_b["skills"],
                plugins_dir=dirs_b["plugins"],
                **common,
            )
            if not wait_for_api(process, api_url):
                _abort_with_api_output(process, "API redémarrée sur la base B")
            step("API redémarrée sur la base B", True, redacted_url(url_b))
            run_restored_phase(
                api_url, identifiers=identifiers, credentials=credentials, before=before
            )
        finally:
            if process is not None:
                _stop_process(process)
                process = None
    except JourneyStopped:
        pass
    except Exception as exc:  # noqa: BLE001 - toute erreur inattendue est une étape en échec
        step("Parcours sans erreur inattendue", False, f"{type(exc).__name__}: {exc}")
    finally:
        if process is not None:
            _stop_process(process)
        for database_url in postgres_urls:
            try:
                reset_postgres_schema(database_url)
                step("Schéma PostgreSQL remis à zéro", True, redacted_url(database_url))
            except Exception as exc:  # noqa: BLE001 - le nettoyage est une étape comptée
                step(
                    "Schéma PostgreSQL remis à zéro",
                    False,
                    f"{redacted_url(database_url)} : {type(exc).__name__}: {exc}",
                )
        if verify_dir is not None:
            try:
                _remove_verify_directory(verify_dir)
            except Exception as exc:  # noqa: BLE001
                step(
                    "Répertoire de vérification supprimé",
                    False,
                    f"{type(exc).__name__}: {exc}",
                )

    failures = [label for label, ok, _detail in steps if not ok]
    print()
    print(
        f"VERDICT : {len(steps) - len(failures)}/{len(steps)} étapes réussies "
        f"(dialecte : {dialect})"
    )
    if failures:
        print("Étapes en échec : " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
