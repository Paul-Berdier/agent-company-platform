"""Parcours Qt contre une vraie API locale, exclusivement sur SQLite jetable.

Exemple Windows (depuis le worktree) :
  python scripts/verify-desktop-journey.py --qt-bin C:/Qt/6.8.3/msvc2022_64/bin
Le binaire tst_api_journey doit déjà être compilé. --seed-only vérifie seulement
le démarrage et le décor API ; ce mode ne déclare jamais le parcours Qt validé.
Les journaux et la base synthétique restent sous .test-tmp/desktop-journey-*.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ("Livrable synthétique du parcours Qt natif.\n" * 4096).encode("utf-8")


def serve() -> None:
    """Processus enfant isolé : même app, simple marqueur de provenance HTTP."""
    import uvicorn
    from acp_api.main import app

    instance = os.environ["ACP_DESKTOP_TEST_INSTANCE"]

    @app.middleware("http")
    async def mark_test_instance(request, call_next):
        response = await call_next(request)
        response.headers["X-ACP-Desktop-Test-Instance"] = instance
        return response

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["ACP_DESKTOP_TEST_PORT"]),
                access_log=False, log_level="warning")


def seed_artifact(directory: Path, database_url: str, project: str, run: str) -> dict:
    # Ce décor n'imite pas un worker opérationnel : il écrit exclusivement la
    # base synthétique marquée, puis exerce les vrais endpoints de lecture.
    from sqlalchemy.orm import Session
    from acp_database.engine import make_engine
    from acp_database.models import ArtifactModel, WorkerModel
    from acp_api.artifacts_storage import LocalArtifactStorage

    if not (directory / "desktop-test-instance.json").is_file():
        raise RuntimeError("Marqueur du décor jetable absent")
    expected = f"sqlite:///{(directory / 'journey.db').as_posix()}"
    if database_url != expected:
        raise RuntimeError("Base hors du décor jetable refusée")
    blob = LocalArtifactStorage(directory / "artifacts").write(io.BytesIO(CONTENT), max_bytes=len(CONTENT))
    engine = make_engine(database_url)
    try:
        with Session(engine) as db:
            worker = WorkerModel(name=f"fixture-worker-{uuid4().hex}", token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                token_prefix="test-fixture", token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                project_id=project, capabilities=[], status="offline", simulation=1)
            db.add(worker)
            db.flush()
            artifact = ArtifactModel(project_id=project, task_run_id=run, worker_id=worker.id,
                kind="report", path="fixture-report.txt", original_name="fixture-report.txt", content_type="text/plain",
                size_bytes=blob.size, checksum=blob.sha256, storage_key=blob.key, source="worker", stream_kind="report")
            db.add(artifact)
            db.commit()
            return {"id": artifact.id, "sha256": blob.sha256, "size": blob.size}
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-test", type=Path, default=ROOT / "apps/desktop/build/windows-msvc-release/tst_api_journey.exe")
    parser.add_argument("--qt-bin", type=Path, default=None)
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument("--interactive-shell", action="store_true", help="Ouvre le shell de test pendant au plus dix minutes ; ne valide pas une recette automatiquement.")
    parser.add_argument("--shell-exe", type=Path, default=ROOT / "apps/desktop/build/windows-msvc-release/desktop_preview.exe")
    args = parser.parse_args()
    if args.seed_only and args.interactive_shell:
        parser.error("--seed-only et --interactive-shell sont exclusifs.")
    if args.interactive_shell and not args.shell_exe.resolve().is_file():
        parser.error("Compilez desktop_preview ou indiquez --shell-exe.")
    if not args.seed_only and not args.interactive_shell and not args.qt_test.resolve().is_file():
        parser.error("Compilez tst_api_journey ou indiquez --qt-test ; aucun build n'est lancé par ce script.")
    if args.qt_bin is not None and not args.qt_bin.resolve().is_dir():
        parser.error("Le dossier --qt-bin n'existe pas.")

    parent = ROOT / ".test-tmp"
    parent.mkdir(exist_ok=True)
    directory = parent / ("desktop-journey-" + uuid4().hex)
    directory.mkdir()  # Aucun nom réutilisé, aucun effacement d'une base existante.
    for name in ("artifacts", "skills", "plugins", "qt-temp"):
        (directory / name).mkdir()
    instance = uuid4().hex
    marker = {"kind": "acp-desktop-disposable-test", "instance": instance}
    (directory / "desktop-test-instance.json").write_text(json.dumps(marker), encoding="utf-8")
    database_url = f"sqlite:///{(directory / 'journey.db').as_posix()}"
    if (directory / "journey.db").exists():
        raise RuntimeError("La base jetable doit être absente avant le démarrage")

    # Écarte toute configuration ACP héritée et privilégie les sources du worktree
    # plutôt que les installations éditables éventuellement liées à une autre branche.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("ACP_")}
    sources = [ROOT / "apps/api/src", *sorted((ROOT / "packages").glob("*/src"))]
    env["PYTHONPATH"] = os.pathsep.join(str(source) for source in sources)
    env["PYTHONUTF8"] = "1"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    login, password, bootstrap = "desktop-journey", secrets.token_urlsafe(30), secrets.token_urlsafe(32)
    env.update({"ACP_DATABASE_URL": database_url, "ACP_ARTIFACT_STORAGE_DIR": str(directory / "artifacts"),
        "ACP_SKILLS_STORAGE_DIR": str(directory / "skills"), "ACP_PLUGINS_DIR": str(directory / "plugins"),
        "ACP_SESSION_COOKIE_SECURE": "0", "ACP_EVENT_RELAY_ENABLED": "0", "ACP_BOOTSTRAP_TOKEN": bootstrap,
        "ACP_PROVIDER_GATEWAY_URL": "http://127.0.0.1:9", "ACP_GATEWAY_SERVICE_TOKEN": "",
        "ACP_DESKTOP_TEST_INSTANCE": instance, "ACP_DESKTOP_TEST_PORT": str(port)})
    process = None
    report: dict = {"directory": str(directory), "status": "failed", "qt_executed": False}
    log_path = directory / "api.log"
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"], cwd=directory,
                env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        import httpx
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False, trust_env=False) as client:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise RuntimeError("L'API jetable s'est arrêtée ; consulter api.log")
                try:
                    ready = client.get("/ready")
                    if ready.headers.get("X-ACP-Desktop-Test-Instance") != instance:
                        raise RuntimeError("L'origine HTTP ne porte pas le marqueur de cette instance jetable")
                    if ready.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("L'API jetable n'est pas prête dans le délai")
                time.sleep(0.15)

            def post(path: str, payload: dict, *, key: bool = False) -> dict:
                headers = {"Idempotency-Key": uuid4().hex} if key else {}
                response = client.post(path, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()

            response = client.post("/auth/bootstrap", json={"login": login, "password": password,
                "display_name": "Compte synthétique Qt"}, headers={"X-ACP-Bootstrap-Token": bootstrap})
            response.raise_for_status()
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            organization = post("/organizations", {"name": "Décor synthétique Qt"})
            workspace = post("/workspaces", {"organization_id": organization["id"], "name": "Espace synthétique"})
            project = post("/projects", {"workspace_id": workspace["id"], "name": "Livrables de test", "description": "Données jetables"})
            mission = post("/missions", {"project_id": project["id"], "title": "Mission synthétique",
                "objective": "Vérifier la lecture des livrables", "expected_outcome": "Fichier identique",
                "acceptance_criteria": ["Empreinte exacte"], "autonomy": {"mode": "supervised"},
                "budget": {"max_tool_calls": 0}, "duration_seconds": 60}, key=True)

            # Seuls les imports du décor local héritent de cette configuration ;
            # le processus parent ne lit aucune base utilisateur.
            for key in tuple(os.environ):
                if key.upper().startswith("ACP_"):
                    del os.environ[key]
            os.environ.update({key: value for key, value in env.items() if key.startswith("ACP_")})
            sys.path[:0] = [str(source) for source in sources]
            import acp_api
            if not Path(acp_api.__file__).resolve().is_relative_to(ROOT / "apps/api/src"):
                raise RuntimeError("Les imports API ne proviennent pas du worktree courant")
            artifact = seed_artifact(directory, database_url, project["id"], mission["current_run"]["id"])
            content = client.get(f"/artifacts/{artifact['id']}/content")
            content.raise_for_status()
            if content.content != CONTENT:
                raise RuntimeError("Le contenu du décor ne correspond pas au contenu réellement servi")
            report.update({"seed_ready": True, "artifact_bytes": artifact["size"], "artifact_sha256": artifact["sha256"]})

        if args.seed_only:
            report["status"] = "seed_ready_only"
        else:
            qt_env = dict(env)
            qt_env.pop("ACP_BOOTSTRAP_TOKEN", None)
            qt_env.update({"ACP_DESKTOP_TEST_API_URL": base_url, "ACP_DESKTOP_TEST_DISPOSABLE": "1",
                "ACP_DESKTOP_TEST_LOGIN": login, "ACP_DESKTOP_TEST_PASSWORD": password,
                "ACP_DESKTOP_TEST_PROJECT_ID": project["id"], "ACP_DESKTOP_TEST_ARTIFACT_ID": artifact["id"],
                "ACP_DESKTOP_TEST_ARTIFACT_SHA256": artifact["sha256"], "ACP_DESKTOP_TEST_ARTIFACT_BYTES": str(artifact["size"]),
                "QT_QPA_PLATFORM": "offscreen", "TMP": str(directory / "qt-temp"), "TEMP": str(directory / "qt-temp")})
            if args.qt_bin:
                qt_env["PATH"] = str(args.qt_bin.resolve()) + os.pathsep + qt_env.get("PATH", "")
            if args.interactive_shell:
                qt_env["QT_QPA_PLATFORM"] = "windows" if os.name == "nt" else os.environ.get("QT_QPA_PLATFORM", "xcb")
                report["preview_executed"] = True
                print(json.dumps({"status": "preview_running", "directory": str(directory), "maximum_seconds": 600}, ensure_ascii=False), flush=True)
                with (directory / "desktop-preview.log").open("w", encoding="utf-8") as preview_log:
                    try:
                        preview = subprocess.run([str(args.shell_exe.resolve())], cwd=directory, env=qt_env,
                            stdout=preview_log, stderr=subprocess.STDOUT, timeout=600,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                        report["preview_exit_code"] = preview.returncode
                        report["status"] = "preview_closed" if preview.returncode == 0 else "preview_failed"
                    except subprocess.TimeoutExpired:
                        report["status"] = "preview_timeout"
                return 0 if report["status"] == "preview_closed" else 1
            result = subprocess.run([str(args.qt_test.resolve()), "-o", str(directory / "qt-journey.log") + ",txt",
                "-o", str(directory / "qt-journey.xml") + ",junitxml"], cwd=directory, env=qt_env,
                capture_output=True, text=True, timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            report["qt_executed"] = True
            report["qt_exit_code"] = result.returncode
            # Les preuves détaillées viennent de QtTest ; aucun secret d'environnement
            # ni corps de réponse d'authentification n'est copié dans le rapport.
            xml = directory / "qt-journey.xml"
            cases = ElementTree.parse(xml).getroot().iter("testcase") if xml.is_file() else []
            journey_cases = [case for case in cases if case.attrib.get("name") == "realApiJourney"]
            confirmed = len(journey_cases) == 1 and not any(
                child.tag in {"failure", "error", "skipped"} for child in journey_cases[0]
            )
            report["journey_test_confirmed"] = confirmed
            report["status"] = "passed" if result.returncode == 0 and confirmed else "failed"
            if result.stderr:
                (directory / "qt-stderr.log").write_text(result.stderr, encoding="utf-8")
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc).replace(password, "[secret]").replace(bootstrap, "[secret]")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        (directory / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] in {"passed", "seed_ready_only", "preview_closed"} else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--serve"]:
        serve()
    else:
        raise SystemExit(main())
