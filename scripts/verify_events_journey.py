"""Vérification de bout en bout du parcours d'événements du Lot E (scénario 12).

Le script démarre l'API métier (``acp_api.main:app``) et le service d'aperçu
(``acp_api.preview:app``) sur deux ports de bouclage distincts, initialise une
base par les seules routes publiques, puis rejoue la chaîne complète du Lot E :
mission mise en file, enrôlement d'un worker limité au projet, claim fencé,
téléversement d'une pièce par la route worker, ingestion d'un rapport de tests
déterministe, flux SSE de la tentative puis du projet avec fermeture volontaire et
reprise par ``Last-Event-ID`` (ni doublon ni trou, comparé aux pages ``GET``),
clôture terminale par le worker, journal paginé, liens signés de téléchargement et
d'aperçu sur leurs origines respectives, révocation, puis arrêt propre.

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
.venv/Scripts/python.exe scripts/verify_events_journey.py                      # Windows
.venv/bin/python scripts/verify_events_journey.py                              # Linux/macOS
.venv/bin/python scripts/verify_events_journey.py \
    --database-url postgresql+psycopg://acp:acp@127.0.0.1:55432/acp_h7        # PostgreSQL
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
import signal
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import httpx
from sqlalchemy import create_engine, text
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
SSE_EVENT_NAME = "acp.event"
STREAM_READ_SECONDS = 20.0
FIRST_STREAM_FRAMES = 3

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


def _generated_secret(env: dict[str, str], command: list[str]) -> str:
    """Fait générer un secret éphémère par le code du worktree, jamais en dur ici."""

    return subprocess.run(
        [str(PYTHON), *command],
        cwd=WORKTREE,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def _vault_key(env: dict[str, str]) -> str:
    return _generated_secret(
        env,
        ["-c", "from acp_api.secrets_vault import generate_key; print(generate_key())"],
    )


def _signing_key(env: dict[str, str]) -> str:
    return _generated_secret(env, ["-m", "acp_api.signing", "generate-key"])


# --- Base de données ------------------------------------------------------------


def check_database_argument(argument: str | None) -> None:
    """Refuse toute URL autre que PostgreSQL via psycopg, avant tout lancement.

    Sans option, le script crée lui-même sa base SQLite temporaire : une URL SQLite
    explicite est donc inutile et refusée comme les autres, pour ne jamais pointer
    par erreur le parcours sur une base persistante du poste.
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
        return f"sqlite:///{(verify_dir / 'verify-events.db').as_posix()}"
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


def _start_uvicorn(app: str, *, port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            app,
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


def start_api(
    verify_dir: Path,
    *,
    port: int,
    api_url: str,
    preview_origin: str,
    database_url: str,
    bootstrap_token: str,
    worker_registration_token: str,
    worker_token_pepper: str,
    vault_key: str,
    signing_key: str,
    registration_project_id: str | None = None,
) -> subprocess.Popen[str]:
    """Démarre l'API métier ; sans projet, l'enrôlement worker reste indisponible.

    La portée d'enrôlement est une décision de déploiement immuable pour un
    processus API. Le projet n'existant pas encore au premier démarrage, la
    première phase ne configure aucune portée (la route d'enrôlement répondrait
    503 et n'est pas appelée) ; la seconde phase redémarre l'API avec le projet.
    """

    env = _isolated_subprocess_environment()
    _assert_subprocess_provenance(env)
    env.update(
        {
            "ACP_API_URL": api_url,
            "ACP_ARTIFACT_PUBLIC_ORIGIN": preview_origin,
            "ACP_ARTIFACT_SIGNING_KEYS": signing_key,
            "ACP_ARTIFACT_STORAGE_DIR": str(verify_dir / "artifacts"),
            "ACP_BOOTSTRAP_TOKEN": bootstrap_token,
            "ACP_DATABASE_URL": database_url,
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
    if registration_project_id is not None:
        env["ACP_WORKER_REGISTRATION_PROJECT_ID"] = registration_project_id
    return _start_uvicorn("acp_api.main:app", port=port, env=env)


def start_preview(
    verify_dir: Path,
    *,
    port: int,
    api_url: str,
    preview_origin: str,
    database_url: str,
    signing_key: str,
) -> subprocess.Popen[str]:
    """Démarre le service d'aperçu avec le strict nécessaire : base, blobs, clés."""

    env = _isolated_subprocess_environment()
    _assert_subprocess_provenance(env)
    env.update(
        {
            "ACP_API_URL": api_url,
            "ACP_ARTIFACT_PUBLIC_ORIGIN": preview_origin,
            "ACP_ARTIFACT_SIGNING_KEYS": signing_key,
            "ACP_ARTIFACT_STORAGE_DIR": str(verify_dir / "artifacts"),
            "ACP_DATABASE_URL": database_url,
            "PYTHONUNBUFFERED": "1",
        }
    )
    return _start_uvicorn("acp_api.preview:app", port=port, env=env)


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


def _abort_with_process_output(
    process: subprocess.Popen[str], label: str
) -> NoReturn:
    _stop_process(process)
    output = process.stdout.read() if process.stdout else ""
    step(label, False, output[-1500:].strip() or "aucune sortie du processus")
    raise JourneyStopped(label)


def _stop_process(process: subprocess.Popen[str]) -> bool:
    """Arrête un processus par le signal gracieux ; ``True`` s'il l'a honoré seul.

    ``False`` signale qu'un arrêt forcé a été nécessaire : le processus est bien
    terminé, mais son extinction n'a pas été propre et l'étape correspondante ne
    doit pas le prétendre.
    """

    if process.poll() is not None:
        return True
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
        return True
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
                f"le processus {process.pid} ne s'est pas arrêté"
            ) from exc
        return False


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


# --- Données déterministes ------------------------------------------------------


def _png_bytes() -> bytes:
    """Image PNG 1×1 réellement décodable : la pièce jointe n'est pas un faux fichier."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scanline = b"\x00\xff\x00\x00"  # filtre « none » puis un pixel RVB rouge
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanline))
        + chunk(b"IEND", b"")
    )


def _reporter_events(screenshot_sha256: str) -> list[dict]:
    """Rapport NDJSON normalisé : 2 réussites, 1 échec avec capture, toujours identique."""

    def test_end(test_id: str, title: str, **overrides: object) -> dict:
        event = {
            "kind": "test_end",
            "test_id": test_id,
            "title": title,
            "suite_path": ["lot-e", "journal"],
            "location": {"file": "tests/journal.spec.ts", "line": 1, "column": 1},
            "project_name": "chromium",
            "attempt": 1,
            "expected_status": "passed",
            "status": "passed",
            "outcome": "expected",
            "duration_ms": 120,
        }
        event.update(overrides)
        return event

    return [
        {
            "kind": "run_begin",
            "started_at": "2026-09-17T08:00:00Z",
            "runner_version": "1.63.0",
            "config": {"projects": ["chromium"], "workers": 1},
        },
        test_end("journal.spec.ts:1:1", "la page de journal se charge"),
        test_end("journal.spec.ts:2:1", "la reprise par curseur ne duplique rien"),
        test_end(
            "journal.spec.ts:3:1",
            "la capture accompagne l'échec",
            status="failed",
            outcome="unexpected",
            duration_ms=340,
            error_message="expect(received).toBe(expected) — attendu 3, reçu 2",
            attachments=[
                {
                    "name": "screenshot",
                    "content_type": "image/png",
                    "path": "test-results/journal/echec-1.png",
                    "sha256": screenshot_sha256,
                    "size_bytes": len(_png_bytes()),
                }
            ],
        ),
        {
            "kind": "run_end",
            "finished_at": "2026-09-17T08:00:02Z",
            "totals": {
                "expected": 2,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "interrupted": 0,
                "timedOut": 0,
            },
            "run_status": "failed",
            "exit_code": 1,
        },
    ]


def _mission_payload(project_id: str, agent_id: str) -> dict:
    return {
        "project_id": project_id,
        "agent_instance_id": agent_id,
        "title": "Mission de vérification du journal Lot E",
        "objective": "Produire un journal d'événements, un rapport de tests et une pièce",
        "expected_outcome": "Un flux SSE reprenable sans doublon ni trou",
        "acceptance_criteria": ["le journal est contigu", "les liens signés sont révocables"],
        "autonomy": {
            "mode": "bounded",
            "allowed_actions": ["read"],
            "forbidden_actions": ["deploy", "purchase"],
            "approval_required_actions": [],
        },
        "resources": [],
        "budget": {"currency": "EUR", "max_tool_calls": 1},
        "duration_seconds": 600,
        "required_capabilities": ["web_tests"],
    }


# --- Flux SSE -------------------------------------------------------------------


def _read_stream(
    client: httpx.Client,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    enough: Callable[[list[dict[str, str]]], bool],
) -> tuple[int, list[dict[str, str]]]:
    """Lit un flux SSE trame par trame, puis ferme volontairement la connexion.

    La sortie du bloc ``with`` ferme la réponse : c'est la coupure côté client que
    la reprise par ``Last-Event-ID`` doit ensuite rattraper. Un flux qui n'apporte
    plus rien est abandonné après ``STREAM_READ_SECONDS`` plutôt qu'attendu sans fin.
    """

    frames: list[dict[str, str]] = []
    current: dict[str, str] = {}
    started = time.monotonic()
    try:
        with client.stream(
            "GET",
            path,
            headers=headers or {},
            timeout=httpx.Timeout(10.0, read=5.0),
        ) as response:
            if response.status_code != 200:
                return response.status_code, frames
            for raw in response.iter_lines():
                line = raw.rstrip("\r")
                if line == "":
                    if current:
                        frames.append(current)
                        current = {}
                    if enough(frames):
                        break
                elif not line.startswith(":"):
                    field, _, value = line.partition(":")
                    current[field] = value[1:] if value.startswith(" ") else value
                if time.monotonic() - started > STREAM_READ_SECONDS:
                    break
            return response.status_code, frames
    except httpx.ReadTimeout:
        return 200, frames


def _event_frames(frames: list[dict[str, str]]) -> list[dict[str, str]]:
    return [frame for frame in frames if frame.get("event") == SSE_EVENT_NAME]


def _frame_cursors(frames: list[dict[str, str]]) -> list[int]:
    return [int(frame["id"]) for frame in _event_frames(frames)]


def _frame_event_ids(frames: list[dict[str, str]]) -> list[str]:
    return [json.loads(frame["data"])["id"] for frame in _event_frames(frames)]


def _at_least(count: int) -> Callable[[list[dict[str, str]]], bool]:
    return lambda frames: len(_event_frames(frames)) >= count


def _collect_pages(client: httpx.Client, path: str, *, limit: int) -> list[dict]:
    """Suit ``next_cursor``/``has_more`` jusqu'au bout, sans jamais tourner en rond."""

    events: list[dict] = []
    cursor = 0
    for _ in range(50):
        response = client.get(path, params={"after_seq": cursor, "limit": limit})
        page = require_http(f"Page du journal après le curseur {cursor}", response)
        events.extend(page["events"])
        if not page["has_more"]:
            return events
        require(
            "Le curseur de page avance",
            page["next_cursor"] is not None and page["next_cursor"] > cursor,
            f"next_cursor={page['next_cursor']}",
        )
        cursor = page["next_cursor"]
    raise JourneyStopped("pagination non convergente")


def _contiguous(values: list[int]) -> bool:
    return values == list(range(values[0], values[0] + len(values))) if values else True


def verify_resumable_stream(
    client: httpx.Client,
    *,
    scope_label: str,
    stream_path: str,
    reference_ids: list[str],
    reference_cursors: list[int] | None,
) -> None:
    """Prouve qu'une coupure puis une reprise ne perdent ni ne dupliquent rien.

    ``reference_ids`` sont les identifiants d'événements rendus par la page ``GET``
    de la même portée ; ``reference_cursors`` les séquences attendues lorsqu'elles
    sont connues (portée tentative), ``None`` lorsqu'elles ne sont pas exposées par
    la page (portée projet, où seul l'ordre strict des ``journal_seq`` est prouvable).
    """

    total = len(reference_ids)
    require(
        f"{scope_label} : assez d'événements pour couper puis reprendre",
        total > FIRST_STREAM_FRAMES,
        f"{total} événement(s) dans la page, {FIRST_STREAM_FRAMES} lus avant coupure",
    )
    status, first = _read_stream(client, stream_path, enough=_at_least(FIRST_STREAM_FRAMES))
    first_cursors = _frame_cursors(first)
    require(
        f"{scope_label} : {FIRST_STREAM_FRAMES} trames lues puis fermeture volontaire",
        status == 200 and len(first_cursors) == FIRST_STREAM_FRAMES,
        f"HTTP {status}, curseurs={first_cursors}",
    )
    last_seen = first_cursors[-1]
    status, resumed = _read_stream(
        client,
        stream_path,
        headers={"Last-Event-ID": str(last_seen)},
        enough=_at_least(total - FIRST_STREAM_FRAMES),
    )
    resumed_cursors = _frame_cursors(resumed)
    require(
        f"{scope_label} : reprise avec Last-Event-ID={last_seen}",
        status == 200 and len(resumed_cursors) == total - FIRST_STREAM_FRAMES,
        f"HTTP {status}, curseurs={resumed_cursors}",
    )
    require(
        f"{scope_label} : uniquement des trames strictement postérieures au curseur",
        all(cursor > last_seen for cursor in resumed_cursors),
        f"curseurs={resumed_cursors}",
    )
    merged_cursors = first_cursors + resumed_cursors
    merged_ids = _frame_event_ids(first) + _frame_event_ids(resumed)
    require(
        f"{scope_label} : aucun doublon entre les deux lectures",
        len(set(merged_ids)) == len(merged_ids)
        and merged_cursors == sorted(merged_cursors)
        and len(set(merged_cursors)) == len(merged_cursors),
        f"{len(merged_ids)} identifiant(s) distinct(s)",
    )
    require(
        f"{scope_label} : aucun trou par rapport à la page GET",
        merged_ids == reference_ids,
        f"flux={len(merged_ids)} page={len(reference_ids)}",
    )
    if reference_cursors is not None:
        require(
            f"{scope_label} : séquences contiguës et identiques à la page",
            merged_cursors == reference_cursors and _contiguous(merged_cursors),
            f"séquences={merged_cursors}",
        )
    else:
        require(
            f"{scope_label} : curseurs de journal strictement croissants",
            all(later > earlier for earlier, later in zip(merged_cursors, merged_cursors[1:])),
            f"curseurs={merged_cursors}",
        )


def run_outbox_relay_steps(client: httpx.Client, *, run_id: str) -> None:
    """Point d'extension réservé au relais outbox (lot H3).

    Aucune étape n'est comptée ici tant que le relais n'existe pas : le parcours ne
    doit jamais afficher un succès pour une capacité absente. H3 remplacera ce corps
    par les étapes de relais (drainage, accusé, rejeu) sans changer la signature.
    """

    del client, run_id


# --- Phases -----------------------------------------------------------------------


def run_setup_phase(
    api_url: str,
    *,
    preview_url: str,
    bootstrap_token: str,
) -> tuple[dict[str, str], str, dict[str, str]]:
    """Bootstrap, login et hiérarchie ; rend les cookies, le CSRF et les identifiants."""

    owner_login = f"verification-{secrets.token_hex(12)}"
    owner_password = secrets.token_urlsafe(32)
    with httpx.Client(
        base_url=api_url, timeout=30.0, trust_env=False, follow_redirects=False
    ) as bootstrap_client:
        require_http("Santé de l'API", bootstrap_client.get("/health"))
        require_http(
            "Santé du service d'aperçu",
            httpx.get(f"{preview_url}/health", timeout=5.0, trust_env=False),
        )
        require_http(
            "Bootstrap du propriétaire",
            bootstrap_client.post(
                "/auth/bootstrap",
                headers={"X-ACP-Bootstrap-Token": bootstrap_token},
                json={
                    "login": owner_login,
                    "display_name": "Vérification journal Lot E",
                    "password": owner_password,
                },
            ),
            201,
        )

    client = httpx.Client(
        base_url=api_url, timeout=30.0, trust_env=False, follow_redirects=False
    )
    with client:
        login = require_http(
            "Connexion par mot de passe",
            client.post(
                "/auth/login", json={"login": owner_login, "password": owner_password}
            ),
        )
        require(
            "Cookie de session et jeton CSRF reçus",
            "acp_session" in client.cookies and bool(login.get("csrf_token")),
        )
        client.headers["X-CSRF-Token"] = login["csrf_token"]

        organization = require_http(
            "Organisation créée",
            client.post("/organizations", json={"name": "Org vérification Lot E"}),
        )
        workspace = require_http(
            "Workspace créé",
            client.post(
                "/workspaces",
                json={
                    "organization_id": organization["id"],
                    "name": "Workspace vérification Lot E",
                },
            ),
        )
        department = require_http(
            "Département créé",
            client.post(
                "/departments",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Département vérification Lot E",
                    "department_type": "engineering",
                },
            ),
        )
        project = require_http(
            "Projet créé",
            client.post(
                "/projects",
                json={
                    "workspace_id": workspace["id"],
                    "department_id": department["id"],
                    "name": "Projet vérification Lot E",
                },
            ),
        )
        agent = require_http(
            "Agent créé",
            client.post(
                "/agents",
                json={
                    "workspace_id": workspace["id"],
                    "name": "Agent vérification Lot E",
                    "role_id": "tester",
                    "capabilities": ["web_tests"],
                },
            ),
        )
        mission = require_http(
            "Mission mise en file",
            client.post(
                "/missions",
                headers={"Idempotency-Key": "lot-e-events-journey-create"},
                json=_mission_payload(project["id"], agent["id"]),
            ),
            201,
        )
        current_run = mission.get("current_run") or {}
        require(
            "Première tentative créée en file",
            isinstance(current_run.get("id"), str) and current_run.get("status") == "queued",
            f"status={current_run.get('status')}",
        )
        identifiers = {
            "project_id": project["id"],
            "mission_id": mission["id"],
            "run_id": current_run["id"],
        }
        return dict(client.cookies), login["csrf_token"], identifiers


def run_worker_phase(
    client: httpx.Client,
    *,
    api_url: str,
    preview_origin: str,
    identifiers: dict[str, str],
    worker_registration_token: str,
) -> None:
    project_id = identifiers["project_id"]
    expected_run_id = identifiers["run_id"]

    worker = require_http(
        "Worker enrôlé en portée projet",
        client.post(
            "/workers/register",
            headers={"X-Worker-Registration-Token": worker_registration_token},
            json={
                "name": f"verify-events-worker-{secrets.token_hex(8)}",
                "capabilities": ["web_tests"],
                "max_concurrency": 1,
                "simulation": False,
                "project_id": project_id,
                "global_access": False,
                "metadata": {"purpose": "lot-e-events-verification"},
            },
        ),
        201,
    )
    worker_id = worker["worker_id"]
    worker_headers = {"Authorization": f"Bearer {worker['token']}"}

    claim = require_http(
        "Tentative attribuée au worker (claim)",
        client.post(
            f"/workers/{worker_id}/claim",
            headers=worker_headers,
            json={"provider_id": "mock"},
        ),
    )
    require(
        "Le claim porte la tentative active et un jeton de fencing",
        claim.get("attempt_id") == expected_run_id
        and isinstance(claim.get("fencing_token"), int)
        and claim["fencing_token"] >= 1
        and claim.get("task_run", {}).get("status") == "preparing",
        f"attempt={claim.get('attempt_id')}, fence={claim.get('fencing_token')!r}",
    )
    run_id = claim["attempt_id"]
    fencing_token = claim["fencing_token"]
    fenced_headers = {
        **worker_headers,
        "X-Worker-Id": worker_id,
        "X-Attempt-Fencing-Token": str(fencing_token),
    }

    heartbeat = require_http(
        "Heartbeat du worker",
        client.post(f"/workers/{worker_id}/heartbeat", headers=worker_headers, json={}),
    )
    require(
        "Le heartbeat reflète la tentative active",
        heartbeat.get("active_runs") == 1 and heartbeat.get("status") == "busy",
        f"status={heartbeat.get('status')}, active_runs={heartbeat.get('active_runs')}",
    )
    require_http(
        "Bail de tentative renouvelé avec le fence",
        client.post(f"/workers/{worker_id}/leases/{run_id}/renew", headers=fenced_headers),
    )

    png = _png_bytes()
    png_sha256 = hashlib.sha256(png).hexdigest()
    upload = require_http(
        "Pièce téléversée par la route worker fencée",
        client.post(
            f"/workers/{worker_id}/artifacts/content",
            headers=fenced_headers,
            files={"file": ("echec-1.png", png, "image/png")},
            data={
                "kind": "screenshot",
                "stream_kind": "screenshot",
                "task_run_id": run_id,
                "project_id": project_id,
            },
        ),
        201,
    )
    require(
        "La pièce est adressée par son sha256",
        upload.get("checksum") == png_sha256
        and upload.get("has_content") is True
        and upload.get("size_bytes") == len(png),
        f"checksum={str(upload.get('checksum'))[:12]}…",
    )
    artifact_id = upload["id"]

    ingested = require_http(
        "Exécution de tests ingérée (2 réussites, 1 échec avec pièce)",
        client.post(
            f"/workers/{worker_id}/test-runs",
            headers=fenced_headers,
            json={
                "task_run_id": run_id,
                "fencing_token": fencing_token,
                "runner": "playwright",
                "runner_version": "1.63.0",
                "config": {"base_url": "http://127.0.0.1:4173"},
                "exit_code": 1,
                "events": _reporter_events(png_sha256),
            },
        ),
    )
    failed_cases = [case for case in ingested.get("cases", []) if case["status"] == "failed"]
    require(
        "Statuts distincts conservés et pièce rattachée par sha256",
        ingested.get("status") == "failed"
        and ingested.get("case_count") == 3
        and ingested.get("totals", {}).get("expected") == 2
        and ingested.get("totals", {}).get("unexpected") == 1
        and len(failed_cases) == 1
        and [item["id"] for item in failed_cases[0]["attachments"]] == [artifact_id],
        f"status={ingested.get('status')}, cas={ingested.get('case_count')}",
    )
    test_run = require_http(
        "Exécution de tests relue par la tentative",
        client.get(f"/runs/{run_id}/test-run"),
    )
    require(
        "Statut et totaux identiques à l'ingestion",
        test_run.get("id") == ingested.get("id")
        and test_run.get("status") == "failed"
        and test_run.get("totals") == ingested.get("totals")
        and test_run.get("exit_code") == 1,
        f"totals={test_run.get('totals')}",
    )
    mission = require_http(
        "Mission relue par sa tentative",
        client.get(f"/missions/by-run/{run_id}"),
    )
    require(
        "Validation technique dérivée : failed, jamais succeeded",
        (mission.get("current_run") or {}).get("technical_validation", {}).get("status")
        == "failed",
        f"technical_validation={(mission.get('current_run') or {}).get('technical_validation')}",
    )

    run_page = require_http(
        "Journal de la tentative lu en une page",
        client.get(f"/runs/{run_id}/events", params={"limit": 500}),
    )
    run_events = run_page["events"]
    run_types = [event["type"] for event in run_events]
    require(
        "Le journal contient la mission et les événements de tests",
        run_types[:1] == ["mission.created"]
        and run_types.count("test.case.finished") == 3
        and "test.run.started" in run_types
        and "test.run.finished" in run_types
        and run_page["has_more"] is False,
        f"types={run_types}",
    )
    verify_resumable_stream(
        client,
        scope_label="Flux de la tentative",
        stream_path=f"/streams/runs/{run_id}",
        reference_ids=[event["id"] for event in run_events],
        reference_cursors=[event["sequence"] for event in run_events],
    )

    project_events = _collect_pages(client, f"/projects/{project_id}/events", limit=500)
    require(
        "Journal du projet lu par curseur journal_seq",
        len(project_events) >= len(run_events)
        and {event["id"] for event in run_events}
        <= {event["id"] for event in project_events},
        f"{len(project_events)} événement(s) projet",
    )
    verify_resumable_stream(
        client,
        scope_label="Flux du projet",
        stream_path=f"/streams/projects/{project_id}",
        reference_ids=[event["id"] for event in project_events],
        reference_cursors=None,
    )

    run_outbox_relay_steps(client, run_id=run_id)

    closed = require_http(
        "Clôture terminale de la tentative par le worker",
        client.patch(
            f"/task-runs/{run_id}",
            headers=fenced_headers,
            json={
                "status": "failed",
                "append_logs": [
                    {"level": "error", "message": "1 cas inattendu : tentative close"}
                ],
            },
        ),
    )
    require(
        "La tentative est close et datée",
        closed.get("status") == "failed" and closed.get("finished_at") is not None,
        f"status={closed.get('status')}",
    )
    paginated = _collect_pages(client, f"/runs/{run_id}/events", limit=2)
    sequences = [event["sequence"] for event in paginated]
    require(
        "Journal paginé contigu jusqu'à l'événement terminal",
        sequences == list(range(1, len(paginated) + 1))
        and len(paginated) == len(run_events) + 1
        and paginated[-1]["type"] == "task.failed",
        f"séquences={sequences}, dernier={paginated[-1]['type'] if paginated else None}",
    )

    with httpx.Client(timeout=30.0, trust_env=False, follow_redirects=False) as anonymous:
        refused = anonymous.get(f"{api_url}/runs/{run_id}/events")
        require(
            "Journal refusé sans cookie de session",
            refused.status_code == 401,
            f"HTTP {refused.status_code}",
        )
        refused_content = anonymous.get(f"{api_url}/artifacts/{artifact_id}/content")
        require(
            "Contenu refusé sans session ni jeton",
            refused_content.status_code == 401,
            f"HTTP {refused_content.status_code}",
        )

        download_link = require_http(
            "Lien signé de téléchargement créé",
            client.post(f"/artifacts/{artifact_id}/link", params={"purpose": "download"}),
            201,
        )
        require(
            "Le lien de téléchargement pointe l'API de contrôle",
            str(download_link.get("url", "")).startswith(f"{api_url}/artifacts/"),
            download_link.get("url", "")[:60],
        )
        downloaded = anonymous.get(download_link["url"])
        require(
            "Téléchargement par lien signé : 200, attachment, nosniff",
            downloaded.status_code == 200
            and downloaded.headers.get("content-disposition", "").startswith("attachment")
            and downloaded.headers.get("x-content-type-options") == "nosniff"
            and downloaded.content == png,
            f"HTTP {downloaded.status_code}, "
            f"disposition={downloaded.headers.get('content-disposition', '')[:20]}",
        )

        preview_link = require_http(
            "Lien signé d'aperçu créé (origine d'aperçu configurée)",
            client.post(f"/artifacts/{artifact_id}/link", params={"purpose": "preview"}),
            201,
        )
        require(
            "Le lien d'aperçu pointe l'origine d'aperçu",
            str(preview_link.get("url", "")).startswith(f"{preview_origin}/artifacts/"),
            preview_link.get("url", "")[:60],
        )
        previewed = anonymous.get(preview_link["url"])
        require(
            "Aperçu servi en ligne sur l'origine d'aperçu",
            previewed.status_code == 200
            and previewed.headers.get("content-disposition", "").startswith("inline")
            and previewed.headers.get("content-type", "").startswith("image/png")
            and previewed.headers.get("x-content-type-options") == "nosniff"
            and previewed.content == png,
            f"HTTP {previewed.status_code}, "
            f"disposition={previewed.headers.get('content-disposition', '')[:20]}",
        )
        preview_token = preview_link["url"].split("?token=", 1)[1]
        replayed = anonymous.get(
            f"{api_url}/artifacts/{artifact_id}/content", params={"token": preview_token}
        )
        require(
            "Jeton d'aperçu refusé sur l'origine de l'API",
            replayed.status_code == 403,
            f"HTTP {replayed.status_code}",
        )
        download_token = download_link["url"].split("?token=", 1)[1]
        crossed = anonymous.get(
            f"{preview_origin}/artifacts/{artifact_id}/content",
            params={"token": download_token},
        )
        require(
            "Jeton de téléchargement refusé sur l'origine d'aperçu",
            crossed.status_code == 403,
            f"HTTP {crossed.status_code}",
        )

        require_http(
            "Lien de téléchargement révoqué",
            client.delete(f"/artifacts/links/{download_link['id']}"),
            204,
        )
        after_revocation = anonymous.get(download_link["url"])
        require(
            "Lien révoqué refusé au téléchargement",
            after_revocation.status_code == 403,
            f"HTTP {after_revocation.status_code}",
        )
        require_http(
            "Lien d'aperçu révoqué",
            client.delete(f"/artifacts/links/{preview_link['id']}"),
            204,
        )
        preview_after_revocation = anonymous.get(preview_link["url"])
        require(
            "Lien d'aperçu révoqué refusé",
            preview_after_revocation.status_code == 403,
            f"HTTP {preview_after_revocation.status_code}",
        )


# --- Point d'entrée ----------------------------------------------------------------


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rejoue le parcours d'événements du Lot E contre une API et un service "
            "d'aperçu réellement démarrés sur le bouclage."
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
    api_port = _free_loopback_port()
    preview_port = _free_loopback_port()
    api_url = f"http://127.0.0.1:{api_port}"
    preview_origin = f"http://127.0.0.1:{preview_port}"
    bootstrap_token = secrets.token_urlsafe(32)
    worker_registration_token = secrets.token_urlsafe(32)
    worker_token_pepper = secrets.token_urlsafe(32)
    api_process: subprocess.Popen[str] | None = None
    preview_process: subprocess.Popen[str] | None = None
    verify_dir: Path | None = None
    database_url: str | None = None
    dialect = "inconnu"

    try:
        check_database_argument(arguments.database_url)
        verify_dir = Path(tempfile.mkdtemp(prefix="acp-events-e2e-"))
        database_url = database_url_for(arguments.database_url, verify_dir)
        subprocess_env = _isolated_subprocess_environment()
        vault_key = _vault_key(subprocess_env)
        signing_key = _signing_key(subprocess_env)
        if is_postgres_url(database_url):
            migrate_schema(subprocess_env, database_url)
        api_settings = {
            "port": api_port,
            "api_url": api_url,
            "preview_origin": preview_origin,
            "database_url": database_url,
            "bootstrap_token": bootstrap_token,
            "worker_registration_token": worker_registration_token,
            "worker_token_pepper": worker_token_pepper,
            "vault_key": vault_key,
            "signing_key": signing_key,
        }
        try:
            api_process = start_api(verify_dir, **api_settings)
            if not wait_for_api(api_process, api_url):
                _abort_with_process_output(api_process, "API démarrée")
            step("API démarrée", True, api_url)
            dialect = observed_dialect(database_url)
            step("Dialecte constaté sur la base", True, dialect)
            # Le service d'aperçu partage la base : il démarre après l'API pour que
            # deux ``init_db`` ne se disputent pas la création des tables.
            preview_process = start_preview(
                verify_dir,
                port=preview_port,
                api_url=api_url,
                preview_origin=preview_origin,
                database_url=database_url,
                signing_key=signing_key,
            )
            if not wait_for_api(preview_process, preview_origin):
                _abort_with_process_output(preview_process, "Service d'aperçu démarré")
            step("Service d'aperçu démarré", True, preview_origin)

            session_cookies, csrf_token, identifiers = run_setup_phase(
                api_url, preview_url=preview_origin, bootstrap_token=bootstrap_token
            )

            # La portée d'enrôlement est une décision de déploiement immuable pour
            # un processus API : le projet maintenant connu, l'API redémarre sur la
            # même base et avec les mêmes secrets pour n'enrôler que ses workers.
            _stop_process(api_process)
            api_process = None
            api_process = start_api(
                verify_dir,
                **api_settings,
                registration_project_id=identifiers["project_id"],
            )
            if not wait_for_api(api_process, api_url):
                _abort_with_process_output(api_process, "API redémarrée en portée projet")
            step("API redémarrée en portée projet", True, identifiers["project_id"])
            with httpx.Client(
                base_url=api_url,
                timeout=30.0,
                trust_env=False,
                follow_redirects=False,
                cookies=session_cookies,
                headers={"X-CSRF-Token": csrf_token},
            ) as client:
                run_worker_phase(
                    client,
                    api_url=api_url,
                    preview_origin=preview_origin,
                    identifiers=identifiers,
                    worker_registration_token=worker_registration_token,
                )

            graceful = _stop_process(preview_process)
            step(
                "Service d'aperçu arrêté proprement",
                graceful,
                f"signal d'arrêt {'honoré' if graceful else 'ignoré, arrêt forcé'}, "
                f"code {preview_process.returncode}",
            )
            preview_process = None
            graceful = _stop_process(api_process)
            step(
                "API arrêtée proprement",
                graceful,
                f"signal d'arrêt {'honoré' if graceful else 'ignoré, arrêt forcé'}, "
                f"code {api_process.returncode}",
            )
            api_process = None
        finally:
            for process in (preview_process, api_process):
                if process is not None:
                    _stop_process(process)
            preview_process = None
            api_process = None
    except JourneyStopped:
        pass
    except Exception as exc:  # noqa: BLE001 - toute erreur inattendue est une étape en échec
        step("Parcours sans erreur inattendue", False, f"{type(exc).__name__}: {exc}")
    finally:
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
            except Exception as exc:  # noqa: BLE001 - le nettoyage est une étape comptée
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
