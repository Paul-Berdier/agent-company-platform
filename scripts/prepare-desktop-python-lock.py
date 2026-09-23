"""Projette le verrou Linux haché pour le parcours desktop Windows, sans résolution.

Seul uvloop est retiré (il ne fonctionne pas sous Windows). Le complément Windows
ajoute colorama. Toutes les autres épingles et tous leurs hachés sont conservés.
Une syntaxe inconnue, un doublon ou un paquet inattendu dans le complément fait
échouer la projection plutôt que d'ouvrir une installation flottante.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LINUX_LOCK = ROOT / "requirements/python-3.12.lock.txt"
WINDOWS_OVERLAY = ROOT / "requirements/desktop-windows-overlay.lock.txt"
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.!+\-]*)\s*\\")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}(?:\s*\\)?")


def pinned_blocks(text: str) -> dict[str, str]:
    """Reconnaît seulement des épingles pip-compile suivies de hachés SHA-256."""
    blocks: dict[str, str] = {}
    name = ""
    lines: list[str] = []
    continuing = False
    hashes = 0

    def finish() -> None:
        if not name:
            return
        if continuing or hashes == 0:
            raise ValueError(f"Épingle sans haché complet : {name}")
        if name in blocks:
            raise ValueError(f"Distribution dupliquée : {name}")
        blocks[name] = "".join(lines)

    for number, line in enumerate(text.splitlines(keepends=True), 1):
        content = line.strip()
        if not content or content.startswith("#"):
            if name:
                lines.append(line)
            continue
        if HASH.fullmatch(content):
            if not name or not continuing:
                raise ValueError(f"Haché sans continuation à la ligne {number}")
            lines.append(line)
            hashes += 1
            continuing = content.endswith("\\")
            continue
        finish()
        match = PIN.fullmatch(content)
        if not match or line[0].isspace():
            raise ValueError(f"Syntaxe de verrou non prise en charge à la ligne {number}")
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        lines = [line]
        hashes = 0
        continuing = True
    finish()
    if not blocks:
        raise ValueError("Verrou vide")
    return blocks


def project_lock(linux: str, overlay: str, target_platform: str) -> str:
    if target_platform != "win32":
        raise ValueError("Cette projection est réservée à Windows (win32).")
    base = pinned_blocks(linux)
    extra = pinned_blocks(overlay)
    if "uvloop" not in base:
        raise ValueError("Le verrou de référence ne contient plus uvloop ; revoir la projection.")
    if set(extra) != {"colorama"}:
        raise ValueError("Le complément Windows doit contenir seulement colorama.")
    if set(base) & set(extra):
        raise ValueError("Le complément recouvre le verrou de référence ; revoir la projection.")
    header = (
        "# Généré pour Windows par scripts/prepare-desktop-python-lock.py.\n"
        "# Seul uvloop est écarté ; colorama vient du complément Windows haché.\n"
        f"# SHA256 référence : {hashlib.sha256(linux.encode('utf-8')).hexdigest()}\n"
        f"# SHA256 complément : {hashlib.sha256(overlay.encode('utf-8')).hexdigest()}\n"
    )
    kept = [block for name, block in base.items() if name != "uvloop"]
    kept.extend(extra.values())
    return header + "\n".join(block.rstrip("\r\n") for block in kept) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-platform", default=sys.platform,
                        help="Cible explicite pour une vérification depuis un autre système ; seul win32 est accepté.")
    parser.add_argument("--output", type=Path, default=ROOT / ".test-tmp/desktop-python-3.12.lock.txt")
    args = parser.parse_args()
    try:
        if args.output.resolve() in {LINUX_LOCK.resolve(), WINDOWS_OVERLAY.resolve()}:
            raise ValueError("La projection ne peut pas écraser ses verrous sources.")
        projected = project_lock(LINUX_LOCK.read_text(encoding="utf-8"),
                                 WINDOWS_OVERLAY.read_text(encoding="utf-8"), args.target_platform)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(projected, encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        print(f"Projection refusée : {exc}", file=sys.stderr)
        return 1
    print(f"Verrou Windows haché écrit : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
