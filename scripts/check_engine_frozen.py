"""Prouve que le moteur Pixel Office est gelé sur l'étiquette d'archive.

Refonte « Hermes au centre » : ``packages/pixel-office-engine`` reste STRICTEMENT
identique, octet pour octet, à l'étiquette ``archive/acp-0.10.0-avant-hermes``, avec
tout ce dont il dépend. Ce script échoue (code 1, motifs en français) dès qu'un de ces
éléments s'en écarte :

1. les chemins gelés — le moteur, ``apps/web/public/assets`` (ses données) et
   ``plugins`` (les salles lues par ``tools/room-preview.mjs`` et
   ``tools/tiled-to-template.mjs``) — comparés à l'étiquette par
   ``git diff --exit-code``, arbre de travail compris, et sans fichier non suivi ;
2. le bloc de règles ``.gitignore`` des assets sous licence, lu par
   ``tests/limezu-pipeline.test.ts`` et par ``tools/import-limezu.mjs`` ;
3. l'entrée de workspace npm du moteur et le script ``test:engine`` ;
4. dans ``package-lock.json``, l'entrée du moteur et la version, l'URL et l'empreinte
   d'intégrité de chaque paquet de sa fermeture de dépendances. Un paquet ajouté par un
   autre workspace n'est pas concerné ; un paquet du moteur remonté, déplacé par le
   hissage ou retiré l'est.

Une intégration du travail moteur non commité passe par une PR dédiée qui modifie
aussi cette garde (docs/refonte/plan.md).

Usage : ``python scripts/check_engine_frozen.py`` depuis n'importe quel dossier du
dépôt. La CI doit disposer de l'historique et des étiquettes (``fetch-depth: 0``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_TAG = "archive/acp-0.10.0-avant-hermes"
FROZEN_PATHS = ("packages/pixel-office-engine", "apps/web/public/assets", "plugins")
ENGINE_WORKSPACE = "packages/pixel-office-engine"
ENGINE_TEST_SCRIPT = ("test:engine", "npm test --workspace @acp/pixel-office-engine")
GITIGNORE_BLOCK_HEADER = "# Third-party licensed pixel-art assets"


class GelRompu(Exception):
    """Le gel du moteur ne peut pas être vérifié ou n'est pas respecté."""


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and process.returncode != 0:
        raise GelRompu(
            f"git {' '.join(arguments)} a échoué (code {process.returncode}) : "
            f"{process.stderr.strip()}"
        )
    return process


def archived_file(relative: str) -> str:
    return git("show", f"{ARCHIVE_TAG}:{relative}").stdout


# --- Bloc .gitignore -------------------------------------------------------------


def gitignore_block(text: str) -> list[str]:
    """Bloc de règles qui commence à l'en-tête des assets sous licence.

    Il s'étend jusqu'à la première ligne vide ou au prochain commentaire d'en-tête.
    """

    lines = [line.rstrip("\r") for line in text.splitlines()]
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(GITIGNORE_BLOCK_HEADER))
    except StopIteration:
        return []
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.strip() or line.startswith("#"):
            break
        block.append(line)
    return block


def contains_block(text: str, block: list[str]) -> bool:
    lines = [line.rstrip("\r") for line in text.splitlines()]
    size = len(block)
    return any(lines[i : i + size] == block for i in range(len(lines) - size + 1))


# --- Fermeture de dépendances du moteur dans le verrou npm -------------------------


def _package_name(path: str) -> str:
    return path.rsplit("node_modules/", 1)[-1]


def _lookup_dirs(from_path: str) -> list[str]:
    """Dossiers ``node_modules`` visités par la résolution de Node depuis ``from_path``."""

    parts = [part for part in from_path.split("/") if part]
    candidates: list[str] = []
    for end in range(len(parts), -1, -1):
        if end and parts[end - 1] == "node_modules":
            continue
        prefix = "/".join(parts[:end])
        candidates.append(f"{prefix}/node_modules" if prefix else "node_modules")
    return candidates


def resolve(packages: dict, from_path: str, name: str) -> str | None:
    for directory in _lookup_dirs(from_path):
        candidate = f"{directory}/{name}"
        if candidate in packages:
            entry = packages[candidate]
            if entry.get("link"):
                return entry.get("resolved")
            return candidate
    return None


def engine_closure(lock: dict) -> dict[str, tuple[str | None, str | None, str | None]]:
    """Paquets de la fermeture du moteur : chemin → (version, URL, intégrité).

    Les dépendances de développement ne sont suivies que pour le moteur lui-même,
    comme npm les installe. Une dépendance facultative ou un pair facultatif absent
    du verrou est ignoré ; toute autre absence est une erreur.
    """

    packages = lock.get("packages", {})
    if ENGINE_WORKSPACE not in packages:
        raise GelRompu(f"package-lock.json ne déclare plus le workspace {ENGINE_WORKSPACE}")
    closure: dict[str, tuple[str | None, str | None, str | None]] = {}
    pending = [ENGINE_WORKSPACE]
    seen: set[str] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        entry = packages[path]
        if path != ENGINE_WORKSPACE:
            closure[path] = (entry.get("version"), entry.get("resolved"), entry.get("integrity"))
        required = dict(entry.get("dependencies", {}))
        if path == ENGINE_WORKSPACE:
            required.update(entry.get("devDependencies", {}))
        optional = set(entry.get("optionalDependencies", {}))
        peers_meta = entry.get("peerDependenciesMeta", {})
        for name in entry.get("peerDependencies", {}):
            if not peers_meta.get(name, {}).get("optional"):
                required.setdefault(name, "*")
            else:
                optional.add(name)
        for name in sorted(set(required) | optional):
            target = resolve(packages, path, name)
            if target is None:
                if name in optional:
                    continue
                raise GelRompu(f"{path} : dépendance {name} introuvable dans le verrou")
            pending.append(target)
    return closure


def closure_signature(lock: dict) -> set[tuple[str, str | None, str | None, str | None]]:
    """Signature indépendante du hissage : (nom, version, URL, intégrité)."""

    return {
        (_package_name(path), *values) for path, values in engine_closure(lock).items()
    }


# --- Contrôles --------------------------------------------------------------------


def check() -> list[str]:
    problems: list[str] = []

    commit = git("rev-parse", "--verify", "--quiet", f"{ARCHIVE_TAG}^{{commit}}", check=False)
    if commit.returncode != 0:
        raise GelRompu(
            f"étiquette {ARCHIVE_TAG} introuvable : récupérez l'historique et les "
            "étiquettes (git fetch --tags, ou fetch-depth: 0 en CI)"
        )

    diff = git("diff", "--exit-code", "--stat", ARCHIVE_TAG, "--", *FROZEN_PATHS, check=False)
    if diff.returncode == 1:
        problems.append(
            "chemins gelés modifiés par rapport à l'étiquette :\n" + diff.stdout.rstrip()
        )
    elif diff.returncode != 0:
        raise GelRompu(f"git diff a échoué : {diff.stderr.strip()}")

    untracked = git("ls-files", "--others", "--exclude-standard", "--", *FROZEN_PATHS).stdout
    if untracked.strip():
        problems.append("fichiers non suivis dans les chemins gelés :\n" + untracked.rstrip())

    block = gitignore_block(archived_file(".gitignore"))
    if not block:
        raise GelRompu("bloc des assets sous licence introuvable dans le .gitignore archivé")
    current_gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if not contains_block(current_gitignore, block):
        problems.append(
            "le bloc .gitignore des assets sous licence a changé ; attendu tel quel :\n"
            + "\n".join(block)
        )

    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if ENGINE_WORKSPACE not in package.get("workspaces", []):
        problems.append(f"package.json : le workspace {ENGINE_WORKSPACE} a disparu")
    script, command = ENGINE_TEST_SCRIPT
    if package.get("scripts", {}).get(script) != command:
        problems.append(f"package.json : le script {script} doit rester « {command} »")

    current_lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    archived_lock = json.loads(archived_file("package-lock.json"))
    if current_lock["packages"].get(ENGINE_WORKSPACE) != archived_lock["packages"].get(
        ENGINE_WORKSPACE
    ):
        problems.append(f"package-lock.json : l'entrée {ENGINE_WORKSPACE} a changé")
    expected = closure_signature(archived_lock)
    actual = closure_signature(current_lock)
    for name, version, resolved, integrity in sorted(expected - actual, key=str):
        problems.append(f"package-lock.json : {name}@{version} manque ou a changé ({resolved})")
    for name, version, resolved, integrity in sorted(actual - expected, key=str):
        problems.append(f"package-lock.json : {name}@{version} n'était pas dans le moteur archivé")

    return problems


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    try:
        problems = check()
    except GelRompu as exc:
        print(f"Gel du moteur invérifiable : {exc}", file=sys.stderr)
        return 1
    if problems:
        print(f"Gel du moteur rompu (référence : {ARCHIVE_TAG}) :", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(
        f"Moteur gelé : {', '.join(FROZEN_PATHS)}, bloc .gitignore, workspace npm et "
        f"dépendances verrouillées identiques à {ARCHIVE_TAG}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
