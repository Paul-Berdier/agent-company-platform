"""Vérifie la cohérence du verrou Python 3.12 et du fichier de contraintes local.

Le verrou ``requirements/python-3.12.lock.txt`` (hachés, compilé dans un conteneur
Linux) alimente les images ; ``requirements/constraints.txt`` (mêmes épingles, sans
hachés) sert au poste local en Python 3.13, où ``--require-hashes`` n'est pas
possible faute de roues identiques. Les deux fichiers doivent porter exactement les
mêmes versions, et les trois pilotes du Lot H (alembic, psycopg, sqlalchemy) doivent
rester aux valeurs imposées : une dérive silencieuse entre l'image et le poste est
précisément ce que ce script refuse.

Usage :
    python scripts/check_lock.py                      # vérifie, code 0 ou 1
    python scripts/check_lock.py --write-constraints  # régénère constraints.txt
                                                      # depuis le verrou, puis vérifie
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "requirements" / "python-3.12.lock.txt"
CONSTRAINTS_PATH = ROOT / "requirements" / "constraints.txt"
SOURCE_PATH = ROOT / "requirements" / "python-3.12.in"

# Épingles imposées par le Lot H : la migration (alembic), le pilote PostgreSQL
# (psycopg et sa roue binaire) et l'ORM (sqlalchemy) ne bougent qu'ensemble et
# explicitement.
REQUIRED_PINS: dict[str, str] = {
    "alembic": "1.20.0",
    "psycopg": "3.3.5",
    "psycopg-binary": "3.3.5",
    "sqlalchemy": "2.0.51",
}

CONSTRAINTS_HEADER = (
    "# Contraintes de versions pour le poste local (Python 3.13 compris).\n"
    "# Généré depuis requirements/python-3.12.lock.txt par\n"
    "#   python scripts/check_lock.py --write-constraints\n"
    "# Ne pas éditer à la main : scripts/check_lock.py refuse toute divergence avec\n"
    "# le verrou. Les hachés sont volontairement absents (les roues locales ne sont\n"
    "# pas celles de l'image Linux) ; les versions, elles, sont identiques.\n"
)

_PIN_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)")


def normalize_name(name: str) -> str:
    """Normalise un nom de distribution comme pip (casse, ``_``/``.`` → ``-``)."""

    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str) -> dict[str, str]:
    """Extrait les épingles ``nom==version`` d'un fichier requirements.

    Les commentaires, les lignes d'options (``--hash``, ``--index-url``…) et les
    continuations de ligne sont ignorés. Un nom présent deux fois avec des versions
    différentes est une erreur de fichier, signalée par une exception.
    """

    pins: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = _PIN_PATTERN.match(line)
        if match is None:
            continue
        name = normalize_name(match.group(1))
        version = match.group(2)
        if name in pins and pins[name] != version:
            raise ValueError(
                f"{name} est épinglé deux fois avec des versions différentes "
                f"({pins[name]} et {version})"
            )
        pins[name] = version
    return pins


def parse_source_names(text: str) -> set[str]:
    """Liste les distributions demandées par ``python-3.12.in`` (noms normalisés)."""

    names: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match is not None:
            names.add(normalize_name(match.group(1)))
    return names


def render_constraints(lock_text: str) -> str:
    """Produit le contenu de ``constraints.txt`` à partir du verrou (épingles triées)."""

    pins = parse_pins(lock_text)
    body = "".join(f"{name}=={version}\n" for name, version in sorted(pins.items()))
    return CONSTRAINTS_HEADER + body


def check(
    lock_text: str,
    constraints_text: str,
    source_text: str | None = None,
    required_pins: dict[str, str] | None = None,
) -> list[str]:
    """Retourne la liste des écarts (vide si verrou et contraintes sont cohérents)."""

    required = REQUIRED_PINS if required_pins is None else required_pins
    errors: list[str] = []
    try:
        lock = parse_pins(lock_text)
    except ValueError as exc:
        return [f"verrou illisible : {exc}"]
    try:
        constraints = parse_pins(constraints_text)
    except ValueError as exc:
        return [f"contraintes illisibles : {exc}"]

    if not lock:
        errors.append("le verrou ne contient aucune épingle")
    if "--hash=" not in lock_text:
        errors.append("le verrou ne contient aucun haché (--generate-hashes attendu)")

    for name, expected in sorted(required.items()):
        actual = lock.get(name)
        if actual != expected:
            errors.append(
                f"{name} doit être épinglé à {expected} dans le verrou "
                f"(trouvé : {actual or 'absent'})"
            )

    for name in sorted(set(lock) | set(constraints)):
        in_lock = lock.get(name)
        in_constraints = constraints.get(name)
        if in_lock is None:
            errors.append(f"{name}=={in_constraints} figure dans les contraintes mais pas dans le verrou")
        elif in_constraints is None:
            errors.append(f"{name}=={in_lock} figure dans le verrou mais pas dans les contraintes")
        elif in_lock != in_constraints:
            errors.append(
                f"{name} diverge : {in_lock} dans le verrou, {in_constraints} dans les contraintes"
            )

    if source_text is not None:
        for name in sorted(parse_source_names(source_text)):
            if name not in lock:
                errors.append(f"{name} est demandé par python-3.12.in mais absent du verrou")

    return errors


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : code 0 si tout est cohérent, 1 sinon (motifs sur stderr)."""

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--write-constraints",
        action="store_true",
        help="régénère requirements/constraints.txt depuis le verrou avant de vérifier",
    )
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--constraints", type=Path, default=CONSTRAINTS_PATH)
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    args = parser.parse_args(argv)

    if not args.lock.is_file():
        print(f"Verrou introuvable : {args.lock}", file=sys.stderr)
        return 1
    lock_text = args.lock.read_text(encoding="utf-8")

    if args.write_constraints:
        args.constraints.write_text(render_constraints(lock_text), encoding="utf-8", newline="\n")

    if not args.constraints.is_file():
        print(f"Fichier de contraintes introuvable : {args.constraints}", file=sys.stderr)
        return 1
    constraints_text = args.constraints.read_text(encoding="utf-8")
    source_text = args.source.read_text(encoding="utf-8") if args.source.is_file() else None

    errors = check(lock_text, constraints_text, source_text)
    if errors:
        print("Verrou Python incohérent :", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    count = len(parse_pins(lock_text))
    print(f"Verrou et contraintes cohérents ({count} épingles, pilotes du Lot H vérifiés).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
