"""Tests des vérificateurs de déploiement du Lot H5.

``scripts/check_railway_config.py`` et ``scripts/check_lock.py`` sont les garde-fous
des fichiers que Railway et les images lisent sans jamais se plaindre d'une clé
inconnue ou d'une version divergente : ces tests prouvent que les fichiers versionnés
passent et, surtout, que chaque altération attendue est refusée avec un code 1.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
RAILWAY_DIR = ROOT / "deploy" / "railway"
LOCK = ROOT / "requirements" / "python-3.12.lock.txt"
CONSTRAINTS = ROOT / "requirements" / "constraints.txt"
SOURCE = ROOT / "requirements" / "python-3.12.in"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def railway():
    return _load("check_railway_config")


@pytest.fixture(scope="module")
def lock():
    return _load("check_lock")


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )


def _copy_railway(tmp_path: Path) -> Path:
    target = tmp_path / "railway"
    shutil.copytree(RAILWAY_DIR, target)
    return target


def _rewrite(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- Railway


def test_railway_files_versionnes_sont_conformes(railway):
    assert railway.check_directory() == {}
    for service in railway.SERVICES:
        data = json.loads((RAILWAY_DIR / service / "railway.json").read_text(encoding="utf-8"))
        assert data["build"]["builder"] == "DOCKERFILE"
        assert (ROOT / data["build"]["dockerfilePath"]).is_file()
        assert set(data) <= railway.TOP_LEVEL_KEYS
        assert set(data["build"]) <= railway.BUILD_KEYS
        assert set(data["deploy"]) <= railway.DEPLOY_KEYS


def test_railway_migration_exclusive_a_api(railway):
    for service in railway.SERVICES:
        data = json.loads((RAILWAY_DIR / service / "railway.json").read_text(encoding="utf-8"))
        has_pre_deploy = "preDeployCommand" in data["deploy"]
        assert has_pre_deploy is (service == "api"), service


def test_railway_readiness_et_repliques_attendues(railway):
    expected_paths = {
        "api": "/ready",
        "artifact-preview": "/ready",
        "provider-gateway": "/health",
        "event-service": "/health",
        "web": "/",
    }
    for service, path in expected_paths.items():
        data = json.loads((RAILWAY_DIR / service / "railway.json").read_text(encoding="utf-8"))
        assert data["deploy"]["healthcheckPath"] == path
    relay = json.loads((RAILWAY_DIR / "relay" / "railway.json").read_text(encoding="utf-8"))
    assert "healthcheckPath" not in relay["deploy"]
    for service in ("api", "artifact-preview", "relay"):
        data = json.loads((RAILWAY_DIR / service / "railway.json").read_text(encoding="utf-8"))
        assert data["deploy"]["numReplicas"] == 1


def test_railway_cli_accepte_les_fichiers_versionnes():
    result = _run("check_railway_config.py")
    assert result.returncode == 0, result.stderr
    assert "conforme" in result.stdout


def test_railway_cle_inconnue_refusee(railway, tmp_path):
    target = _copy_railway(tmp_path)
    _rewrite(target / "api" / "railway.json", lambda d: d["deploy"].__setitem__("healthCheckPath", "/ready"))
    report = railway.check_directory(target)
    assert list(report) == ["api"]
    assert any("clé inconnue du schéma Railway : deploy.healthCheckPath" in e for e in report["api"])


def test_railway_pre_deploy_hors_api_refuse(railway, tmp_path):
    target = _copy_railway(tmp_path)
    _rewrite(
        target / "relay" / "railway.json",
        lambda d: d["deploy"].__setitem__("preDeployCommand", "/app/docker/entrypoint.sh migrate"),
    )
    report = railway.check_directory(target)
    assert list(report) == ["relay"]
    assert any("interdit sur relay" in e for e in report["relay"])


def test_railway_api_sans_migration_refuse(railway, tmp_path):
    target = _copy_railway(tmp_path)
    _rewrite(target / "api" / "railway.json", lambda d: d["deploy"].pop("preDeployCommand"))
    report = railway.check_directory(target)
    assert any("preDeployCommand" in e for e in report["api"])


def test_railway_constructeur_readiness_et_repliques_refuses(railway, tmp_path):
    target = _copy_railway(tmp_path)

    def mutate(d):
        d["build"]["builder"] = "RAILPACK"
        d["deploy"]["healthcheckPath"] = "/health"
        d["deploy"]["numReplicas"] = 2
        d["deploy"]["restartPolicyType"] = "ALWAYS"

    _rewrite(target / "api" / "railway.json", mutate)
    errors = railway.check_directory(target)["api"]
    joined = "\n".join(errors)
    assert "build.builder doit être DOCKERFILE" in joined
    assert "deploy.healthcheckPath doit valoir /ready" in joined
    assert "deploy.numReplicas doit valoir 1" in joined
    assert "restartPolicyType doit valoir ON_FAILURE" in joined


def test_railway_dockerfile_introuvable_et_json_illisible(railway, tmp_path):
    target = _copy_railway(tmp_path)
    _rewrite(target / "web" / "railway.json", lambda d: d["build"].__setitem__("dockerfilePath", "docker/absent.Dockerfile"))
    (target / "event-service" / "railway.json").write_text("{not json", encoding="utf-8")
    shutil.rmtree(target / "relay")
    report = railway.check_directory(target)
    assert any("introuvable dans le dépôt" in e for e in report["web"])
    assert any("JSON illisible" in e for e in report["event-service"])
    assert any("fichier introuvable" in e for e in report["relay"])


def test_railway_cli_refuse_un_fichier_altere(tmp_path):
    target = _copy_railway(tmp_path)
    _rewrite(target / "artifact-preview" / "railway.json", lambda d: d["deploy"].__setitem__("preDeployCommand", "x"))
    result = _run("check_railway_config.py", "--config-dir", str(target))
    assert result.returncode == 1
    assert "artifact-preview" in result.stderr
    assert "interdit" in result.stderr


# --------------------------------------------------------------------------- Lock


def test_lock_versionne_est_coherent(lock):
    errors = lock.check(
        LOCK.read_text(encoding="utf-8"),
        CONSTRAINTS.read_text(encoding="utf-8"),
        SOURCE.read_text(encoding="utf-8"),
    )
    assert errors == []
    pins = lock.parse_pins(LOCK.read_text(encoding="utf-8"))
    assert pins["alembic"] == "1.20.0"
    assert pins["psycopg"] == "3.3.5"
    assert pins["psycopg-binary"] == "3.3.5"
    assert pins["sqlalchemy"] == "2.0.51"
    assert "--hash=sha256:" in LOCK.read_text(encoding="utf-8")
    assert "--hash" not in CONSTRAINTS.read_text(encoding="utf-8").replace("Les hachés", "")


def test_lock_constraints_est_derive_du_verrou(lock):
    rendered = lock.render_constraints(LOCK.read_text(encoding="utf-8"))
    assert rendered == CONSTRAINTS.read_text(encoding="utf-8")


def test_lock_cli_accepte_les_fichiers_versionnes():
    result = _run("check_lock.py")
    assert result.returncode == 0, result.stderr
    assert "cohérents" in result.stdout


def test_lock_divergence_de_version_refusee(lock):
    lock_text = LOCK.read_text(encoding="utf-8")
    constraints = CONSTRAINTS.read_text(encoding="utf-8").replace("sqlalchemy==2.0.51", "sqlalchemy==2.0.50")
    errors = lock.check(lock_text, constraints)
    assert any("sqlalchemy diverge" in e for e in errors)


def test_lock_pilote_non_epingle_refuse(lock):
    lock_text = LOCK.read_text(encoding="utf-8").replace("alembic==1.20.0", "alembic==1.19.0")
    constraints = CONSTRAINTS.read_text(encoding="utf-8").replace("alembic==1.20.0", "alembic==1.19.0")
    errors = lock.check(lock_text, constraints)
    assert any("alembic doit être épinglé à 1.20.0" in e for e in errors)


def test_lock_epingle_manquante_ou_sans_hache_refusee(lock):
    lock_text = LOCK.read_text(encoding="utf-8")
    constraints = CONSTRAINTS.read_text(encoding="utf-8") + "paquet-fantome==1.0\n"
    errors = lock.check(lock_text, constraints)
    assert any("paquet-fantome==1.0 figure dans les contraintes mais pas dans le verrou" in e for e in errors)

    no_hash = "\n".join(line for line in lock_text.splitlines() if "--hash" not in line)
    errors = lock.check(no_hash.replace(" \\", ""), CONSTRAINTS.read_text(encoding="utf-8"))
    assert any("aucun haché" in e for e in errors)

    source = SOURCE.read_text(encoding="utf-8") + "\npaquet-inconnu>=1\n"
    errors = lock.check(lock_text, CONSTRAINTS.read_text(encoding="utf-8"), source)
    assert any("paquet-inconnu est demandé par python-3.12.in" in e for e in errors)


def test_lock_cli_refuse_des_contraintes_alterees(tmp_path):
    altered = tmp_path / "constraints.txt"
    altered.write_text(
        CONSTRAINTS.read_text(encoding="utf-8").replace("psycopg==3.3.5", "psycopg==3.2.0"),
        encoding="utf-8",
    )
    result = _run("check_lock.py", "--constraints", str(altered))
    assert result.returncode == 1
    assert "psycopg diverge" in result.stderr


def test_lock_cli_regenere_les_contraintes(tmp_path):
    target = tmp_path / "constraints.txt"
    result = _run("check_lock.py", "--write-constraints", "--constraints", str(target))
    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == CONSTRAINTS.read_text(encoding="utf-8")


def test_lock_refuse_une_dependance_pyproject_oubliee_dans_la_source(lock):
    errors = lock.check(
        "httpx==0.28.1 --hash=sha256:abc\n",
        "httpx==0.28.1\n",
        "",
        required_pins={},
        project_files={
            "apps/api/pyproject.toml":
                '[project]\nname="acp-api"\ndependencies=["httpx>=0.27"]\n',
        },
    )
    assert any("httpx" in error and "python-3.12.in" in error for error in errors)


def test_lock_cli_refuse_une_nouvelle_dependance_non_verrouillee(lock, tmp_path, monkeypatch):
    project = tmp_path / "apps" / "api" / "pyproject.toml"
    project.parent.mkdir(parents=True)
    project.write_text(
        '[project]\nname="acp-api"\ndependencies=["paquet-oublie>=1"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(lock, "ROOT", tmp_path)
    assert lock.main([
        "--lock", str(LOCK), "--constraints", str(CONSTRAINTS), "--source", str(SOURCE),
    ]) == 1


def test_lock_verifie_aussi_extras_construction_et_autres_plateformes(lock):
    errors = lock.check(
        "httpx==0.28.1 --hash=sha256:abc\n",
        "httpx==0.28.1\n",
        "httpx>=0.27\n",
        required_pins={},
        project_files={
            "apps/api/pyproject.toml": '''
[project]
name = "acp-api"
dependencies = ["httpx>=0.27", "tzdata; platform_system == 'Windows'"]
[project.optional-dependencies]
test = ["pytest>=8"]
[build-system]
requires = ["setuptools>=68"]
''',
        },
    )
    for name in ("tzdata", "pytest", "setuptools"):
        assert any(name in error and "python-3.12.in" in error for error in errors)
        assert any(name in error and "absent du verrou" in error for error in errors)


def test_lock_refuse_version_incompatible_et_extra_oublie(lock):
    errors = lock.check(
        "uvicorn==0.29.0 --hash=sha256:abc\n",
        "uvicorn==0.29.0\n",
        "uvicorn>=0.29\n",
        required_pins={},
        project_files={
            "apps/api/pyproject.toml":
                '[project]\nname="acp-api"\ndependencies=["uvicorn[standard]>=0.30"]\n',
        },
    )
    assert any("standard" in error and "python-3.12.in" in error for error in errors)
    assert any("0.29.0" in error and ">=0.30" in error for error in errors)


def test_lock_exempte_seulement_les_distributions_locales_reelles(lock):
    errors = lock.check(
        "httpx==0.28.1 --hash=sha256:abc\n",
        "httpx==0.28.1\n",
        "httpx>=0.27\n",
        required_pins={},
        project_files={
            "apps/api/pyproject.toml":
                '[project]\nname="acp-api"\ndependencies=["ACP_contracts", "acp-inconnu"]\n',
            "packages/contracts/pyproject.toml":
                '[project]\nname="acp-contracts"\ndependencies=["httpx>=0.27"]\n',
        },
    )
    assert not any("ACP_contracts" in error or "acp-contracts" in error for error in errors)
    assert any("acp-inconnu" in error for error in errors)


def test_lock_refuse_un_specificateur_source_incompatible_avec_le_verrou(lock):
    errors = lock.check(
        "fastapi==0.141.1 --hash=sha256:abc\n",
        "fastapi==0.141.1\n",
        "fastapi>=99\n",
        required_pins={},
        project_files={
            "apps/api/pyproject.toml":
                '[project]\nname="acp-api"\ndependencies=["fastapi>=0.111"]\n',
        },
    )
    assert any("python-3.12.in" in error and ">=99" in error for error in errors)


# --------------------------------------------------------------------------- Fichiers Docker


def test_entrypoint_et_dockerfiles_en_lf_et_commandes_fixees():
    entrypoint = (ROOT / "docker" / "entrypoint.sh").read_bytes()
    assert b"\r" not in entrypoint
    text = entrypoint.decode("utf-8")
    for command in (
        "python -m acp_database.migrate upgrade",
        "python -m acp_api.outbox_relay --follow",
        "python -m acp_api.backup",
        "acp_api.main:app",
        "acp_api.preview:app",
        "acp_provider_gateway.main:app",
        "acp_event_service.main:app",
    ):
        assert command in text
    assert "chown" not in text.replace("aucun chown", "").replace("un ``chown``", "").replace("aucun ``chown``", "")
    assert "exit 3" in text

    python_dockerfile = (ROOT / "docker" / "python.Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes" in python_dockerfile
    assert "python:3.12-slim-bookworm@sha256:" in python_dockerfile
    assert "10001" in python_dockerfile
    assert 'ENTRYPOINT ["/app/docker/entrypoint.sh"]' in python_dockerfile
    assert 'CMD ["api"]' in python_dockerfile

    # Avant 0.9.1, ce test vérifiait la seule présence des lignes « .env* », « *.db »…
    # sans voir qu'elles ne visaient que la racine du contexte. Le contexte effectif
    # est désormais rejoué par apps/api/tests/test_docker_context.py ; ici, seuls les
    # motifs récursifs attendus sont exigés.
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("**/.venv*", "**/node_modules", "**/acp-data", "**/*.db", "**/.env*", "**/licensed", "e2e", ".git"):
        assert pattern in ignored
