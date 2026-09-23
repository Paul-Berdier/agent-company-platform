"""Contexte de build Docker effectif (``.dockerignore`` et ``scripts/check_docker_context.py``).

Docker compare chaque motif de ``.dockerignore`` au chemin relatif à la racine du
contexte : un motif sans ``**/`` ne vise que la racine. Avant 0.9.1, les assets sous
licence installés dans ``apps/web/public/assets/licensed`` (ignorés par Git) et tout
``.env`` imbriqué entraient donc dans le contexte, puis dans l'image web servie par
nginx. Ces tests rejouent la sélection de Docker sans lancer Docker : sur un arbre
synthétique qui contient ce qu'un poste de développement peut contenir, et sur les
fichiers versionnés que les Dockerfiles copient.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check_docker_context.py"
DOCKERIGNORE = ROOT / ".dockerignore"


def _load():
    spec = importlib.util.spec_from_file_location("check_docker_context", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Les dataclasses résolvent leurs annotations via sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def context():
    return _load()


def _excluded(context, patterns_text: str, path: str) -> bool:
    return context.is_excluded(path, context.parse_dockerignore(patterns_text))


# --- sémantique de Docker ------------------------------------------------------


def test_the_matcher_follows_docker_semantics(context):
    # Un motif sans « ** » ne vise que la racine du contexte (et ses descendants).
    assert _excluded(context, "LimeZu\n", "LimeZu/tiles.png")
    assert not _excluded(context, "LimeZu\n", "apps/web/LimeZu/tiles.png")
    assert not _excluded(context, "*.db\n", "apps/api/acp.db")
    assert _excluded(context, "*.db\n", "acp.db")
    # « **/ » traverse les niveaux, et vise aussi la racine.
    assert _excluded(context, "**/LimeZu\n", "apps/web/LimeZu/tiles.png")
    assert _excluded(context, "**/LimeZu\n", "LimeZu/tiles.png")
    assert _excluded(context, "**/*.db\n", "apps/api/acp.db")
    # « * » ne traverse pas « / » ; un motif ancré vise ce chemin et son contenu.
    assert not _excluded(context, "apps/*.db\n", "apps/api/acp.db")
    assert _excluded(context, "apps/web/public/assets/licensed\n", "apps/web/public/assets/licensed/a/b.png")
    assert _excluded(context, "/docs/**\n", "docs/assets/a.png")
    # Le dernier motif applicable l'emporte ; « ! » réintègre.
    assert not _excluded(context, "**/.env*\n!**/.env.example\n", "apps/web/.env.example")
    assert _excluded(context, "**/.env*\n!**/.env.example\n", "apps/web/.env.local")
    assert _excluded(context, "!**/.env.example\n**/.env*\n", "apps/web/.env.example")
    # Commentaires et lignes vides sont ignorés.
    assert not _excluded(context, "# LimeZu\n\n", "LimeZu/a.png")


def test_character_classes_keep_docker_ranges_and_negation(context, tmp_path):
    assert _excluded(context, "[a-z].db", "m.db")
    assert not _excluded(context, "[a-z].db", "-.db")
    assert not _excluded(context, "[^a].db", "a.db")
    assert _excluded(context, "[^a].db", "b.db")
    assert _excluded(context, "a[^b]c.db", "a/c.db")
    assert _excluded(context, r"[a\-z].db", "-.db")
    assert not _excluded(context, r"[a\-z].db", "m.db")
    assert _excluded(context, r"[\]a].db", "].db")
    assert _excluded(context, r"[\?a].db", "a.db")
    assert _excluded(context, r"[\*a].db", "a.db")
    dockerignore = tmp_path / ".dockerignore"
    dockerignore.write_text("[^a].db\n", encoding="utf-8")
    (tmp_path / "a.db").write_bytes(b"base locale")
    assert any("a.db" in error for error in context.check(tmp_path, dockerignore))

    # Moby conserve les classes dans sa regex : une classe négative peut donc
    # franchir « / » et réintégrer une base initialement exclue par « **/*.db ».
    dockerignore.write_text("**/*.db\n!a[^x]b.db\n", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.db").write_bytes(b"base locale")
    assert any("a/b.db" in error for error in context.check(tmp_path, dockerignore))


@pytest.mark.parametrize("pattern", ["[", "[]", "[^]", "[z-a]", "[a-]", "[?a].db", "[*a].db"])
def test_invalid_character_classes_are_explicitly_refused(context, tmp_path, pattern):
    dockerignore = tmp_path / ".dockerignore"
    dockerignore.write_text(pattern + "\n", encoding="utf-8")
    errors = context.check(tmp_path, dockerignore)
    assert len(errors) == 1
    assert "motif" in errors[0].lower() and "invalide" in errors[0].lower()


@pytest.mark.parametrize("extension", ["db", "sqlite", "sqlite3"])
@pytest.mark.parametrize("sidecar", ["wal", "shm", "journal"])
def test_all_sqlite_sidecars_are_excluded_and_recognized(context, extension, sidecar):
    path = f"apps/api/client.{extension}-{sidecar}"
    patterns = context.parse_dockerignore(DOCKERIGNORE.read_text(encoding="utf-8"))
    assert context.is_excluded(path, patterns)
    assert "SQLite" in context.forbidden_reason(path)


# --- arbre de poste de développement -------------------------------------------

SENSITIVE_FILES = (
    ".test-tmp/proof.txt",
    "apps/web/public/assets/licensed/limezu/characters/manifest.json",
    "apps/web/public/assets/licensed/limezu/office/inventory-source/LICENSE.txt",
    "apps/web/public/assets/licensed/limezu/office/inventory-source/Modern_Office_32x32.png",
    "packages/pixel-office-engine/assets/licensed/limezu/atlas.png",
    "apps/web/art/LimeZu/tiles.png",
    "apps/web/art/Limzu/tiles.png",
    "packages/ui/local-assets/sprite.png",
    "packages/ui/licensed-assets/sprite.png",
    "packages/ui/vendor-assets/sprite.png",
    "apps/web/src/sprites/office.aseprite",
    "apps/web/.env",
    "apps/web/.env.local",
    "apps/web/.env.production",
    "apps/web/.env.production.local",
    "apps/api/.env",
    "docker/.env.compose",
    ".env",
    "acp.db",
    "apps/api/acp.db",
    "apps/api/visual-validation.sqlite3",
    "apps/api/acp-data/artifacts/ab/blob",
    "acp-data/skills/rev/SKILL.md",
    "packages/database/.venv/pyvenv.cfg",
    "apps/web/node_modules/vite/package.json",
)

BUILD_INPUTS = (
    "package.json",
    "package-lock.json",
    "VERSION",
    "requirements/python-3.12.lock.txt",
    "docker/entrypoint.sh",
    "docker/web.nginx.conf",
    "apps/web/package.json",
    "apps/web/index.html",
    "apps/web/public/assets/packs.json",
    "apps/web/public/assets/core/manifest.json",
    "apps/api/pyproject.toml",
    "apps/api/src/acp_api/main.py",
    "packages/pixel-office-engine/src/index.ts",
    "packages/pixel-office-engine/tools/limezu-mapping.json",
    "plugins/research/rooms/library-v1.json",
)


def _tree(tmp_path: Path, files) -> Path:
    root = tmp_path / "contexte"
    for relative in files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    shutil.copyfile(DOCKERIGNORE, root / ".dockerignore")
    return root


def test_sensitive_files_never_enter_the_build_context(context, tmp_path):
    root = _tree(tmp_path, SENSITIVE_FILES + BUILD_INPUTS)
    patterns = context.parse_dockerignore(DOCKERIGNORE.read_text(encoding="utf-8"))

    sent = set(context.effective_context(root, patterns))

    leaked = sorted(set(SENSITIVE_FILES) & sent)
    assert leaked == [], f"entreraient dans le contexte de build : {leaked}"
    missing = sorted(set(BUILD_INPUTS) - sent)
    assert missing == [], f"entrées de build exclues à tort : {missing}"
    assert context.check(root, root / ".dockerignore") == []


def test_versioned_templates_are_not_secrets_but_every_other_env_file_is(context):
    assert context.forbidden_reason("docker/.env.compose.example") is None
    assert context.forbidden_reason(".env.example") is None
    for path in ("apps/web/.env.production.local", "docker/.env.compose", ".env"):
        assert "environnement" in context.forbidden_reason(path)


def test_every_licensed_pattern_of_gitignore_is_excluded_at_any_depth(context):
    """Parité : ce que Git refuse de versionner au titre des licences, Docker ne
    l'embarque pas non plus, qu'il soit à la racine ou imbriqué."""

    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if "licensed" in line.lower() and line.startswith("#"))
    section = []
    for line in lines[start + 1 :]:
        if not line.strip() or line.startswith("#"):
            break
        section.append(line.strip())
    assert section, "section des assets sous licence introuvable dans .gitignore"
    patterns = context.parse_dockerignore(DOCKERIGNORE.read_text(encoding="utf-8"))

    samples: list[str] = []
    for pattern in section:
        name = pattern.rstrip("/")
        if name.startswith("*."):
            samples += [f"x{name[1:]}", f"apps/web/src/deep/x{name[1:]}"]
        elif "/" in name:
            samples.append(f"{name}/pack/manifest.json")
        else:
            samples += [f"{name}/a.png", f"apps/web/public/{name}/a.png", f"packages/ui/deep/{name}/a.png"]

    kept = [sample for sample in samples if not context.is_excluded(sample, patterns)]
    assert kept == [], f"motifs de .gitignore sans équivalent récursif dans .dockerignore : {kept}"


def _copy_sources() -> list[str]:
    sources: list[str] = []
    for dockerfile in ("docker/python.Dockerfile", "docker/web.Dockerfile"):
        for line in (ROOT / dockerfile).read_text(encoding="utf-8").splitlines():
            words = line.split()
            if not words or words[0] != "COPY" or any(w.startswith("--from") for w in words):
                continue
            sources += [w for w in words[1:-1] if not w.startswith("--")]
    return sources


def test_tracked_build_inputs_copied_by_the_dockerfiles_stay_in_the_context(context):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git absent : fichiers versionnés inconnus")
    tracked = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8").split("\0")
    tracked = [path for path in tracked if path]
    patterns = context.parse_dockerignore(DOCKERIGNORE.read_text(encoding="utf-8"))
    sources = _copy_sources()
    assert "apps/web" in sources and "packages/contracts" in sources

    for source in sources:
        under = [path for path in tracked if path == source or path.startswith(source.rstrip("/") + "/")]
        assert under, f"source COPY sans fichier versionné : {source}"
        excluded = [path for path in under if context.is_excluded(path, patterns)]
        assert excluded == [], f"{source} : fichiers versionnés exclus du contexte : {excluded[:5]}"
    forbidden = [
        path
        for path in tracked
        if context.forbidden_reason(path) and not context.is_excluded(path, patterns)
    ]
    assert forbidden == [], f"fichiers versionnés interdits dans le contexte : {forbidden}"


def test_a_dockerfile_specific_ignore_file_is_refused(context, tmp_path):
    root = _tree(tmp_path, BUILD_INPUTS)
    (root / "docker").mkdir(exist_ok=True)
    (root / "docker" / "web.Dockerfile.dockerignore").write_text("node_modules\n", encoding="utf-8")

    errors = context.check(root, root / ".dockerignore")

    assert any("web.Dockerfile.dockerignore" in error for error in errors)


def test_the_cli_refuses_a_leaking_context_and_accepts_the_repository(tmp_path):
    root = _tree(tmp_path, BUILD_INPUTS)
    (root / ".dockerignore").write_text("node_modules\n", encoding="utf-8")
    (root / "apps/web/public/assets/licensed/limezu").mkdir(parents=True)
    (root / "apps/web/public/assets/licensed/limezu/manifest.json").write_text("{}", encoding="utf-8")

    leaking = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    repository = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert leaking.returncode == 1
    assert "apps/web/public/assets/licensed/limezu/manifest.json" in leaking.stderr
    assert "sous licence" in leaking.stderr
    assert repository.returncode == 0, repository.stderr
    assert "conforme" in repository.stdout


def test_the_web_image_refuses_licensed_assets_before_building():
    """Défense en profondeur : même si le filtrage régressait, le build web refuse
    un dossier ``licensed`` au lieu de le recopier dans ``dist`` puis dans nginx."""

    dockerfile = (ROOT / "docker" / "web.Dockerfile").read_text(encoding="utf-8")
    guard = dockerfile.index("-name licensed")
    assert guard < dockerfile.index("npm run build:web")
    assert "Build refusé" in dockerfile[guard - 400 : guard + 400]
