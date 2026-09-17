"""Vérification de bout en bout du parcours d'automatisation du Lot F.

Ce script lance successivement l'API en portée d'enrôlement globale puis projet,
sur la même base SQLite et avec les mêmes secrets éphémères, puis exerce les
vraies routes HTTP du lot : création et rejeu idempotents, conflit de corps,
activation, calendrier, tick du planificateur, déclenchements manuel et webhook,
historique, permis/usage de budget et alerte.

Le tick est rendu déterministe sans attente : après l'activation, le script ne
modifie que le curseur ``next_run_at`` de sa propre base pour simuler une
occurrence devenue due. L'acquisition du bail, le fencing et la matérialisation
restent exécutés par les routes de production.

Base de données : sans option, une base SQLite temporaire est créée dans le
répertoire de vérification et supprimée à la fin. ``--database-url`` accepte une
URL ``postgresql+psycopg://`` : le schéma est alors migré par
``python -m acp_database.migrate upgrade`` avant le démarrage de l'API, et remis à
zéro à la fin (``DROP SCHEMA public CASCADE; CREATE SCHEMA public``) par SQLAlchemy,
jamais par un binaire ``psql``. Toute autre URL est refusée avant tout lancement.
Le dialecte réellement constaté sur la base est imprimé dans le verdict.

Il n'effectue aucun appel Internet et ne dépense rien.

Usage, depuis la racine du dépôt, avec l'environnement installé par
``scripts/setup`` :

```
.venv/Scripts/python.exe scripts/verify_automation_journey.py                  # Windows
.venv/bin/python scripts/verify_automation_journey.py                          # Linux/macOS
.venv/bin/python scripts/verify_automation_journey.py \
    --database-url postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_h7        # PostgreSQL
```

Sortie : une ligne par étape, puis un VERDICT. Code de retour 0 si toutes les
étapes passent, 1 sinon.
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import httpx
from sqlalchemy import DateTime, bindparam, create_engine, text
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

# Les sorties redirigées de Python utilisent encore parfois la page de codes locale
# sous Windows, alors que la CI et les terminaux modernes attendent UTF-8. Fixer
# explicitement l'encodage garde les libellés français lisibles dans les journaux.
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
    # Ne jamais hériter d'un editable install ou d'un PYTHONPATH pointant vers un
    # autre checkout : le parcours doit prouver exactement l'arbre qui contient
    # ce script. L'ordre correspond aux sources installées par ``scripts/setup``.
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
        Path(line.strip()).resolve()
        for line in probe.stdout.splitlines()
        if line.strip()
    ]
    if len(imported) != 3 or any(
        not path.is_relative_to(WORKTREE) for path in imported
    ):
        rendered = ", ".join(str(path) for path in imported) or "aucun chemin"
        raise RuntimeError(
            "Le parcours importerait des paquets hors du worktree courant : " + rendered
        )


def _vault_key(env: dict[str, str]) -> str:
    command = [
        str(PYTHON),
        "-c",
        "from acp_api.secrets_vault import generate_key; print(generate_key())",
    ]
    return subprocess.run(
        command,
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


# --- Base de données ------------------------------------------------------------


def check_database_argument(argument: str | None) -> None:
    """Refuse toute URL autre que PostgreSQL via psycopg, avant tout lancement.

    Sans option, le script crée lui-même sa base SQLite temporaire : une URL SQLite
    explicite est donc inutile et refusée comme les autres, pour ne jamais pointer
    par erreur le parcours sur une base persistante du poste. Le refus est une
    étape en échec, donc un verdict 0/1 et un code de retour 1.
    """

    if argument is None:
        return
    if argument.startswith(POSTGRES_URL_PREFIX):
        try:
            make_url(argument)
        except Exception as exc:  # noqa: BLE001 - toute URL illisible est refusée
            step("URL de base acceptée", False, f"URL PostgreSQL illisible : {exc}")
            raise JourneyStopped("url de base refusée") from exc
        return
    step(
        "URL de base acceptée",
        False,
        f"seule une URL {POSTGRES_URL_PREFIX} est acceptée ; sans option, une base "
        "SQLite temporaire est créée puis supprimée",
    )
    raise JourneyStopped("url de base refusée")


def database_url_for(argument: str | None, verify_dir: Path) -> str:
    """URL réellement utilisée : SQLite temporaire par défaut, PostgreSQL sur demande."""

    if argument is None:
        return f"sqlite:///{(verify_dir / 'verify-automations.db').as_posix()}"
    return argument


def redacted_url(database_url: str) -> str:
    """URL sans mot de passe : le verdict est un journal, jamais un secret."""

    return make_url(database_url).render_as_string(hide_password=True)


def is_postgres_url(database_url: str) -> bool:
    """Seul PostgreSQL déclenche la migration préalable et la remise à zéro finale."""

    return database_url.startswith(POSTGRES_URL_PREFIX)


def migrate_schema(env: dict[str, str], database_url: str) -> None:
    """Applique les migrations Alembic du dépôt avant de démarrer l'API.

    L'API ne doit jamais créer un schéma PostgreSQL par ``create_all`` : la chaîne
    de migration est la seule source du schéma hébergé. Une commande absente ou en
    échec arrête le parcours, sans repli silencieux vers ``init_db``.
    """

    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "acp_database.migrate",
            "upgrade",
            "--database-url",
            database_url,
        ],
        cwd=WORKTREE,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    require(
        "Schéma migré par acp_database.migrate upgrade",
        result.returncode == 0,
        output[-800:] or f"code {result.returncode}",
    )


def observed_dialect(database_url: str) -> str:
    """Dialecte et version réellement servis par la base, lus par SQLAlchemy."""

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
    """Remet le schéma ``public`` à zéro pour que le prochain parcours reparte de rien."""

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


# --- Processus ------------------------------------------------------------------


def start_api(
    verify_dir: Path,
    *,
    port: int,
    database_url: str,
    bootstrap_token: str,
    worker_registration_token: str,
    worker_token_pepper: str,
    vault_key: str,
    registration_project_id: str | None = None,
    registration_global_access: bool = False,
) -> subprocess.Popen[str]:
    has_project_scope = registration_project_id not in {None, ""}
    if registration_global_access == has_project_scope:
        raise ValueError("exactement une portée d'enrôlement worker est requise")
    env = _isolated_subprocess_environment()
    _assert_subprocess_provenance(env)
    env.update(
        {
            "ACP_DATABASE_URL": database_url,
            "ACP_BOOTSTRAP_TOKEN": bootstrap_token,
            "ACP_PLUGINS_DIR": str(verify_dir / "plugins"),
            "ACP_PROVIDER_GATEWAY_URL": "http://127.0.0.1:9",
            "ACP_SESSION_COOKIE_SECURE": "0",
            "ACP_SECRETS_KEYS": vault_key,
            "ACP_SKILLS_STORAGE_DIR": str(verify_dir / "skills"),
            "ACP_WORKER_REGISTRATION_TOKEN": worker_registration_token,
            "ACP_WORKER_TOKEN_PEPPER": worker_token_pepper,
            "PYTHONUNBUFFERED": "1",
        }
    )
    if registration_global_access:
        env["ACP_WORKER_REGISTRATION_GLOBAL_ACCESS"] = "1"
    else:
        env["ACP_WORKER_REGISTRATION_PROJECT_ID"] = registration_project_id or ""
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
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        ),
    )


def wait_for_api(process: subprocess.Popen[str], api_url: str) -> bool:
    for _ in range(120):
        if process.poll() is not None:
            return False
        try:
            response = httpx.get(
                f"{api_url}/health", timeout=1.0, trust_env=False
            )
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    return False


def _force_due(database_url: str, automation_id: str) -> datetime:
    """Prépare uniquement la donnée temporelle de la base du script.

    L'écriture passe par SQLAlchemy sur l'URL réellement servie à l'API, avec un
    instant conscient du fuseau en UTC. ``AutomationModel.next_run_at`` est un
    ``UtcDateTime``, c'est-à-dire un ``DateTime(timezone=True)`` normalisé en UTC :
    lier ici ce même type de colonne fait stocker à SQLite comme à PostgreSQL
    exactement ce que la colonne relira, sans chaîne ISO fabriquée à la main.
    """

    due = datetime.now(UTC) - timedelta(seconds=65)
    statement = text(
        "UPDATE automations SET next_run_at = :due WHERE id = :id AND enabled = 1"
    ).bindparams(bindparam("due", type_=DateTime(timezone=True)))
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            updated = connection.execute(
                statement, {"due": due.astimezone(UTC), "id": automation_id}
            ).rowcount
    finally:
        engine.dispose()
    if updated != 1:
        step(
            "Occurrence rendue due dans la base éphémère",
            False,
            f"ligne mise à jour={updated}",
        )
        raise JourneyStopped("curseur scheduler introuvable")
    return due


def _automation_payload(agent_id: str) -> dict:
    return {
        "name": "Routine de vérification Lot F",
        "description": "Parcours API local, déterministe et sans dépense",
        "schedule": {
            "kind": "interval",
            "expression": "60",
            "timezone": "Europe/Paris",
        },
        "mission_template": {
            "title": "Mission automatique de vérification",
            "objective": "Matérialiser une mission traçable sans effet externe",
            "expected_outcome": "Un parcours Lot F observable dans l'historique",
            "acceptance_criteria": ["le parcours est idempotent"],
            "autonomy": {
                "mode": "bounded",
                "allowed_actions": ["read"],
                "forbidden_actions": ["deploy"],
                "approval_required_actions": ["git_publish"],
            },
            "resources": [],
            "budget": {"max_tool_calls": 2, "currency": "EUR"},
            "duration_seconds": 600,
            "agent_instance_id": agent_id,
            "required_capabilities": [],
        },
        "catchup_policy": "run_once",
        "max_concurrent_runs": 4,
    }


def _abort_with_api_output(
    process: subprocess.Popen[str], label: str
) -> NoReturn:
    _stop_process(process)
    output = process.stdout.read() if process.stdout else ""
    step(label, False, output[-1500:].strip() or "aucune sortie du processus")
    raise JourneyStopped(label)


def run_global_phase(
    client: httpx.Client,
    *,
    database_url: str,
    bootstrap_token: str,
    worker_registration_token: str,
) -> str:
    owner_login = f"verification-{secrets.token_hex(12)}"
    owner_password = secrets.token_urlsafe(32)
    bootstrap = require_http(
        "Bootstrap du propriétaire",
        client.post(
            "/auth/bootstrap",
            headers={"X-ACP-Bootstrap-Token": bootstrap_token},
            json={
                "login": owner_login,
                "display_name": "Vérification automatisations",
                "password": owner_password,
            },
        ),
        201,
    )
    client.headers["X-CSRF-Token"] = bootstrap["csrf_token"]

    organization = require_http(
        "Organisation créée",
        client.post("/organizations", json={"name": "Org vérification Lot F"}),
    )
    workspace = require_http(
        "Workspace créé",
        client.post(
            "/workspaces",
            json={
                "organization_id": organization["id"],
                "name": "Workspace vérification Lot F",
            },
        ),
    )
    project = require_http(
        "Projet créé",
        client.post(
            "/projects",
            json={
                "workspace_id": workspace["id"],
                "name": "Projet vérification Lot F",
            },
        ),
    )
    project_id = project["id"]
    agent = require_http(
        "Agent local créé",
        client.post(
            "/agents",
            json={
                "workspace_id": workspace["id"],
                "name": "Agent vérification Lot F",
                "role_id": "developer",
                "capabilities": [],
            },
        ),
    )

    policy = require_http(
        "Politique de budget enregistrée",
        client.put(
            f"/projects/{project_id}/budget-policy",
            json={
                "timezone": "Europe/Paris",
                "daily_budget": {"max_tool_calls": 2, "currency": "EUR"},
                "provider_budgets": [
                    {
                        "provider": "mock",
                        "budget": {"max_tool_calls": 2, "currency": "EUR"},
                    }
                ],
                "max_concurrent_missions": 10,
                "max_retries_per_mission": 2,
                "max_spawned_agents_per_run": 4,
            },
        ),
    )
    require(
        "Politique relue sans perte",
        policy.get("daily_budget", {}).get("max_tool_calls") == 2
        and policy.get("provider_budgets", [{}])[0].get("provider") == "mock",
    )

    automation_endpoint = f"/projects/{project_id}/automations"
    create_key = "lot-f-create-stable-key"
    payload = _automation_payload(agent["id"])
    created = require_http(
        "Automatisation créée avec Idempotency-Key",
        client.post(
            automation_endpoint,
            headers={"Idempotency-Key": create_key},
            json=payload,
        ),
        201,
    )
    automation_id = created["id"]
    replay = require_http(
        "Création rejouée",
        client.post(
            automation_endpoint,
            headers={"Idempotency-Key": create_key},
            json=payload,
        ),
        201,
    )
    require(
        "Le rejeu renvoie la même automatisation",
        replay.get("id") == automation_id,
        f"id={automation_id}",
    )
    conflict_payload = {**payload, "name": "Corps différent"}
    conflict = client.post(
        automation_endpoint,
        headers={"Idempotency-Key": create_key},
        json=conflict_payload,
    )
    require(
        "Même clé avec un autre corps refusée",
        conflict.status_code == 409,
        f"HTTP {conflict.status_code}",
    )
    automations = client.get("/automations", params={"project_id": project_id})
    require(
        "Aucun doublon de ressource",
        automations.status_code == 200
        and isinstance(automations.json(), list)
        and [item["id"] for item in automations.json()] == [automation_id],
        f"HTTP {automations.status_code}",
    )

    enable_key = "lot-f-enable-command-a"
    enabled = require_http(
        "Automatisation activée",
        client.post(
            f"/automations/{automation_id}/enable",
            headers={"Idempotency-Key": enable_key},
        ),
    )
    require(
        "Prochaine occurrence persistée",
        enabled.get("enabled") is True and enabled.get("next_run_at") is not None,
    )
    enabled_replay = require_http(
        "Activation rejouée avec la même clé",
        client.post(
            f"/automations/{automation_id}/enable",
            headers={"Idempotency-Key": enable_key},
        ),
    )
    require(
        "Le rejeu d'activation conserve sa postcondition",
        enabled_replay.get("enabled") is True
        and enabled_replay.get("next_run_at") == enabled.get("next_run_at"),
    )
    disabled = require_http(
        "Mutation opposée validée après l'activation",
        client.post(
            f"/automations/{automation_id}/disable",
            headers={"Idempotency-Key": "lot-f-disable-command-b"},
        ),
    )
    require(
        "La mutation opposée suspend effectivement la routine",
        disabled.get("enabled") is False and disabled.get("next_run_at") is None,
    )
    stale_enable = client.post(
        f"/automations/{automation_id}/enable",
        headers={"Idempotency-Key": enable_key},
    )
    require(
        "Une activation périmée n'est jamais réappliquée",
        stale_enable.status_code == 409,
        f"HTTP {stale_enable.status_code}",
    )
    enabled = require_http(
        "Routine réactivée par une nouvelle intention",
        client.post(
            f"/automations/{automation_id}/enable",
            headers={"Idempotency-Key": "lot-f-enable-command-c"},
        ),
    )
    next_run = datetime.fromisoformat(enabled["next_run_at"])
    calendar = client.get(
        "/automations/calendar",
        params={
            "automation_id": automation_id,
            "start": (next_run - timedelta(seconds=1)).isoformat(),
            "end": (next_run + timedelta(seconds=121)).isoformat(),
        },
    )
    calendar_rows = calendar.json() if calendar.status_code == 200 else []
    require(
        "Calendrier calculé sans déplacer son ancre",
        calendar.status_code == 200
        and len(calendar_rows) >= 2
        and all(item["automation_id"] == automation_id for item in calendar_rows)
        and all(item["state"] == "planned" for item in calendar_rows),
        f"HTTP {calendar.status_code}, entrées={len(calendar_rows)}",
    )

    scheduler_worker = require_http(
        "Worker global du planificateur enregistré",
        client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": worker_registration_token},
            json={
                "name": f"verify-automation-scheduler-{secrets.token_hex(8)}",
                "capabilities": [],
                "max_concurrency": 1,
                "simulation": False,
                "global_access": True,
                "metadata": {"purpose": "lot-f-scheduler-verification"},
            },
        ),
        201,
    )
    scheduler_worker_id = scheduler_worker["worker_id"]
    scheduler_worker_headers = {
        "Authorization": f"Bearer {scheduler_worker['token']}"
    }
    holder_id = secrets.token_hex(16)
    lease = require_http(
        "Bail singleton du planificateur acquis",
        client.post(
            f"/workers/{scheduler_worker_id}/automation-scheduler/lease",
            headers=scheduler_worker_headers,
            json={"holder_id": holder_id},
        ),
    )
    require(
        "Fence du planificateur attribué",
        lease.get("acquired") is True
        and isinstance(lease.get("fencing_token"), int)
        and lease["fencing_token"] >= 1,
    )

    due = _force_due(database_url, automation_id)
    step(
        "Occurrence rendue due dans la base éphémère",
        True,
        due.isoformat(timespec="seconds"),
    )
    scheduler_headers = {
        **scheduler_worker_headers,
        "X-Scheduler-Fencing-Token": str(lease["fencing_token"]),
    }
    tick = require_http(
        "Tick planificateur exécuté via l'API",
        client.post(
            f"/workers/{scheduler_worker_id}/automation-scheduler/tick",
            headers=scheduler_headers,
            json={"holder_id": holder_id, "limit": 10},
        ),
    )
    require(
        "Le scheduler matérialise exactement un rattrapage",
        tick.get("launched") == 1
        and tick.get("examined") == 1
        and tick.get("failed") == 0,
        f"launched={tick.get('launched')} examined={tick.get('examined')}",
    )
    require_http(
        "Bail du planificateur libéré",
        client.post(
            f"/workers/{scheduler_worker_id}/automation-scheduler/lease/release",
            headers=scheduler_headers,
            json={"holder_id": holder_id},
        ),
        204,
    )

    manual_key = "lot-f-manual-stable-key"
    manual = require_http(
        "Déclenchement manuel créé",
        client.post(
            f"/automations/{automation_id}/trigger",
            headers={"Idempotency-Key": manual_key},
        ),
        201,
    )
    manual_replay = require_http(
        "Déclenchement manuel rejoué",
        client.post(
            f"/automations/{automation_id}/trigger",
            headers={"Idempotency-Key": manual_key},
        ),
        201,
    )
    require(
        "Le manuel est exactement une fois",
        manual.get("outcome") == "launched"
        and manual.get("id") == manual_replay.get("id"),
        f"run={manual.get('id')}",
    )

    webhook_status = require_http(
        "Statut webhook initial consulté",
        client.get(f"/automations/{automation_id}/webhook"),
    )
    require(
        "Aucun secret n'est exposé par le statut",
        webhook_status.get("enabled") is False and "secret" not in webhook_status,
    )
    webhook_secret = secrets.token_urlsafe(32)
    rotation_key = "lot-f-webhook-rotation-key"
    rotated = require_http(
        "Webhook activé avec un secret fourni par le client",
        client.post(
            f"/automations/{automation_id}/webhook",
            headers={"Idempotency-Key": rotation_key},
            json={"secret": webhook_secret},
        ),
        201,
    )
    require(
        "La rotation confirme uniquement le secret fourni",
        rotated.get("enabled") is True and rotated.get("secret") == webhook_secret,
    )
    rotation_replay = require_http(
        "Rotation webhook rejouée après réponse incertaine",
        client.post(
            f"/automations/{automation_id}/webhook",
            headers={"Idempotency-Key": rotation_key},
            json={"secret": webhook_secret},
        ),
        201,
    )
    require(
        "La rotation rejouée est récupérable sans nouveau secret",
        rotation_replay == rotated,
    )
    status_after_rotation = require_http(
        "Statut webhook relu après rotation",
        client.get(f"/automations/{automation_id}/webhook"),
    )
    require(
        "Le statut public masque toujours le secret",
        status_after_rotation.get("secret_configured") is True
        and "secret" not in status_after_rotation,
    )

    event = {
        "event_id": "lot-f-external-event-001",
        "payload": {"probe": "local-verification"},
    }
    with httpx.Client(
        base_url=str(client.base_url), timeout=30.0, trust_env=False
    ) as webhook_client:
        webhook = require_http(
            "Événement webhook authentifié",
            webhook_client.post(
                f"/automations/{automation_id}/webhook/trigger",
                headers={"Authorization": f"Bearer {webhook_secret}"},
                json=event,
            ),
            201,
        )
        webhook_replay = require_http(
            "Événement webhook rejoué",
            webhook_client.post(
                f"/automations/{automation_id}/webhook/trigger",
                headers={"Authorization": f"Bearer {webhook_secret}"},
                json=event,
            ),
            201,
        )
    require(
        "L'événement webhook est dédoublonné",
        webhook.get("outcome") == "launched"
        and webhook.get("id") == webhook_replay.get("id"),
        f"run={webhook.get('id')}",
    )

    webhook_disable_key = "lot-f-webhook-disable-command-a"
    webhook_disabled = client.delete(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": webhook_disable_key},
    )
    webhook_disable_replay = client.delete(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": webhook_disable_key},
    )
    replacement_secret = secrets.token_urlsafe(32)
    replacement_rotation = client.post(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": "lot-f-webhook-rotation-command-b"},
        json={"secret": replacement_secret},
    )
    stale_webhook_disable = client.delete(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": webhook_disable_key},
    )
    replacement_status = client.get(f"/automations/{automation_id}/webhook")
    cleanup_webhook = client.delete(
        f"/automations/{automation_id}/webhook",
        headers={"Idempotency-Key": "lot-f-webhook-disable-command-c"},
    )
    require(
        "La révocation webhook est rejouable mais jamais réappliquée après rotation",
        webhook_disabled.status_code == 200
        and webhook_disabled.json().get("enabled") is False
        and webhook_disable_replay.status_code == 200
        and webhook_disable_replay.json() == webhook_disabled.json()
        and replacement_rotation.status_code == 201
        and replacement_rotation.json().get("secret") == replacement_secret
        and stale_webhook_disable.status_code == 409
        and replacement_status.status_code == 200
        and replacement_status.json().get("enabled") is True
        and cleanup_webhook.status_code == 200
        and cleanup_webhook.json().get("enabled") is False,
        "disable/replay/rotation/stale="
        f"{webhook_disabled.status_code}/{webhook_disable_replay.status_code}/"
        f"{replacement_rotation.status_code}/{stale_webhook_disable.status_code}",
    )

    history_response = client.get(f"/automations/{automation_id}/runs")
    history = history_response.json() if history_response.status_code == 200 else []
    require(
        "Historique des trois modes de déclenchement",
        history_response.status_code == 200
        and len(history) == 3
        and {item["trigger_kind"] for item in history}
        == {"schedule", "manual", "webhook"},
        f"HTTP {history_response.status_code}, runs={len(history)}",
    )

    return project_id


def run_project_phase(
    client: httpx.Client,
    *,
    project_id: str,
    worker_registration_token: str,
) -> None:

    worker = require_http(
        "Worker d'exécution limité au projet enregistré",
        client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": worker_registration_token},
            json={
                "name": f"verify-automation-executor-{secrets.token_hex(8)}",
                "capabilities": [],
                "max_concurrency": 4,
                "simulation": False,
                "project_id": project_id,
                "global_access": False,
                "metadata": {"purpose": "lot-f-execution-verification"},
            },
        ),
        201,
    )
    worker_id = worker["worker_id"]
    worker_headers = {"Authorization": f"Bearer {worker['token']}"}

    claim = require_http(
        "Une mission automatisée est attribuée au worker",
        client.post(
            f"/workers/{worker_id}/claim",
            headers=worker_headers,
            json={"provider_id": "mock"},
        ),
    )
    require(
        "Le claim porte le gabarit et un fence",
        claim.get("task") is not None
        and claim.get("mission", {}).get("budget", {}).get("max_tool_calls") == 2
        and isinstance(claim.get("fencing_token"), int),
        "task="
        f"{claim.get('task') is not None}, budget={claim.get('mission', {}).get('budget')}, "
        f"fence={claim.get('fencing_token')!r}",
    )
    task_id = claim["task"]["id"]
    run_id = claim["attempt_id"]
    attempt_fence = claim["fencing_token"]
    budget_headers = {
        **worker_headers,
        "X-Attempt-Fencing-Token": str(attempt_fence),
    }
    budget_root = f"/work/workers/{worker_id}/runs/{run_id}/budget"
    permit_body = {
        "permit_id": "lot-f-budget-permit-001",
        "provider": "mock",
        "phase": "tool",
        "tool_calls": 2,
    }
    permit = require_http(
        "Permis de budget obtenu avant l'effet",
        client.post(
            f"{budget_root}/permit", headers=budget_headers, json=permit_body
        ),
    )
    require(
        "La borne exacte est autorisée et signalée",
        permit.get("accepted") is True
        and permit.get("permit_allowed") is True
        and permit.get("verdict", {}).get("state") == "warning",
    )
    permit_replay = require_http(
        "Permis de budget rejoué",
        client.post(
            f"{budget_root}/permit", headers=budget_headers, json=permit_body
        ),
    )
    require(
        "Le permis est exactement une fois",
        permit_replay.get("idempotent") is True
        and permit_replay.get("verdict") == permit.get("verdict"),
    )

    usage_body = {
        "report_id": "lot-f-budget-usage-001",
        "permit_id": permit_body["permit_id"],
        "provider": "mock",
        "phase": "tool",
        "source": "platform",
        "tool_calls": 2,
    }
    usage = require_http(
        "Usage réel rapproché du permis",
        client.post(
            f"{budget_root}/usage", headers=budget_headers, json=usage_body
        ),
    )
    require(
        "Le rapport de consommation est accepté",
        usage.get("accepted") is True and usage.get("idempotent") is False,
    )
    usage_replay = require_http(
        "Rapport de consommation rejoué",
        client.post(
            f"{budget_root}/usage", headers=budget_headers, json=usage_body
        ),
    )
    require(
        "Le rapport de consommation est exactement une fois",
        usage_replay.get("idempotent") is True
        and usage_replay.get("verdict") == usage.get("verdict"),
    )
    usage_summary = require_http(
        "Consommation de budget relue côté utilisateur",
        client.get(f"/projects/{project_id}/budget-usage"),
    )
    require(
        "Le ledger agrège la mesure sans double compte",
        usage_summary.get("totals", {}).get("reports") == 1
        and usage_summary.get("totals", {}).get("tool_calls") == 2
        and any(
            mission.get("mission_id") == task_id
            for mission in usage_summary.get("missions", [])
        )
        and any(
            provider.get("provider") == "mock"
            for provider in usage_summary.get("providers", [])
        ),
    )

    alerts_response = client.get(
        "/alerts", params={"project_id": project_id, "open": True}
    )
    alerts = alerts_response.json() if alerts_response.status_code == 200 else []
    budget_alerts = [item for item in alerts if item.get("kind") == "budget.guard"]
    require(
        "Alerte de budget visible et dédupliquée",
        alerts_response.status_code == 200
        and len(budget_alerts) == 1
        and budget_alerts[0].get("severity") == "warning",
        f"HTTP {alerts_response.status_code}, alertes budget={len(budget_alerts)}",
    )
    acknowledged = require_http(
        "Alerte acquittée",
        client.post(
            f"/alerts/{budget_alerts[0]['id']}/acknowledge",
            json={"comment": "Parcours local vérifié"},
        ),
    )
    require(
        "L'acquittement est historisé",
        acknowledged.get("acknowledged_at") is not None
        and acknowledged.get("acknowledgement_comment")
        == "Parcours local vérifié",
    )
    remaining = client.get(
        "/alerts", params={"project_id": project_id, "open": True}
    )
    require(
        "Aucune alerte ouverte ne subsiste",
        remaining.status_code == 200 and remaining.json() == [],
        f"HTTP {remaining.status_code}",
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # terminate() maps to TerminateProcess on Windows and skips the ASGI
        # lifespan shutdown, leaving SQLite handles open. CTRL_BREAK lets
        # Uvicorn dispose the engine before the temporary directory is removed.
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
            # Le lanceur d'un environnement virtuel peut avoir créé le vrai
            # Python en enfant. /T cible uniquement cet arbre de PID connu.
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
            raise RuntimeError(
                f"le processus API {process.pid} ne s'est pas arrêté"
            ) from exc


def _remove_verify_directory(directory: Path) -> None:
    """Supprime le répertoire après libération asynchrone des handles Windows."""

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


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rejoue le parcours d'automatisation du Lot F contre une API réellement "
            "démarrée sur le bouclage."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "URL postgresql+psycopg:// d'une base dédiée au parcours (migrée avant "
            "l'API, remise à zéro à la fin). Sans option : SQLite temporaire."
        ),
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
    database_url: str | None = None
    dialect = "inconnu"

    try:
        check_database_argument(arguments.database_url)
        verify_dir = Path(tempfile.mkdtemp(prefix="acp-automations-e2e-"))
        database_url = database_url_for(arguments.database_url, verify_dir)
        subprocess_env = _isolated_subprocess_environment()
        vault_key = _vault_key(subprocess_env)
        if is_postgres_url(database_url):
            migrate_schema(subprocess_env, database_url)
        try:
            process = start_api(
                verify_dir,
                port=port,
                database_url=database_url,
                bootstrap_token=bootstrap_token,
                worker_registration_token=worker_registration_token,
                worker_token_pepper=worker_token_pepper,
                vault_key=vault_key,
                registration_global_access=True,
            )
            if not wait_for_api(process, api_url):
                _abort_with_api_output(process, "API démarrée")
            step("API démarrée", True, api_url)
            # Lu sans étape supplémentaire : le décompte des 62 étapes SQLite
            # reste celui documenté, et le dialecte figure dans le verdict.
            dialect = observed_dialect(database_url)
            with httpx.Client(
                base_url=api_url,
                timeout=30.0,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                project_id = run_global_phase(
                    client,
                    database_url=database_url,
                    bootstrap_token=bootstrap_token,
                    worker_registration_token=worker_registration_token,
                )
                session_cookies = dict(client.cookies)
                csrf_token = client.headers.get("X-CSRF-Token")

            # La portée d'enrôlement est une décision de déploiement immuable pour
            # un processus API. Le même parcours redémarre donc proprement sur la
            # même base et avec les mêmes secrets avant d'enrôler l'exécuteur du
            # projet, au lieu de relâcher cette garantie pour les besoins du test.
            _stop_process(process)
            process = None
            process = start_api(
                verify_dir,
                port=port,
                database_url=database_url,
                bootstrap_token=bootstrap_token,
                worker_registration_token=worker_registration_token,
                worker_token_pepper=worker_token_pepper,
                vault_key=vault_key,
                registration_project_id=project_id,
            )
            if not wait_for_api(process, api_url):
                _abort_with_api_output(process, "API redémarrée en portée projet")
            with httpx.Client(
                base_url=api_url,
                timeout=30.0,
                trust_env=False,
                follow_redirects=False,
                cookies=session_cookies,
                headers={"X-CSRF-Token": csrf_token or ""},
            ) as client:
                run_project_phase(
                    client,
                    project_id=project_id,
                    worker_registration_token=worker_registration_token,
                )
        finally:
            if process is not None:
                _stop_process(process)
                process = None
    except JourneyStopped:
        pass
    except Exception as exc:
        step("Parcours sans erreur inattendue", False, f"{type(exc).__name__}: {exc}")
    finally:
        if process is not None:
            _stop_process(process)
        if database_url is not None and is_postgres_url(database_url):
            try:
                reset_postgres_schema(database_url)
                step("Schéma PostgreSQL remis à zéro", True, redacted_url(database_url))
            except Exception as exc:  # noqa: BLE001 - le nettoyage est une étape comptée
                step(
                    "Schéma PostgreSQL remis à zéro",
                    False,
                    f"{type(exc).__name__}: {exc}",
                )
        if verify_dir is not None:
            try:
                _remove_verify_directory(verify_dir)
            except Exception as exc:
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
    raise SystemExit(main())
