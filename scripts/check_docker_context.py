"""Calcule le contexte de build Docker effectif et refuse tout fichier interdit.

Les deux images (``docker/python.Dockerfile`` et ``docker/web.Dockerfile``) sont
construites depuis la racine du dépôt, filtrée par ``.dockerignore``. Un motif mal
écrit n'échoue jamais : le fichier entre simplement dans le contexte, puis dans
l'image si un ``COPY`` couvre son dossier. Ce script rejoue donc, sans lancer
Docker, la sélection que fait le démon, et refuse (code 1) tout fichier qui ne doit
jamais atteindre une image :

- les assets sous licence (LimeZu…) dont la redistribution est interdite ;
- les fichiers d'environnement ``.env*`` (hors modèle ``.env.example``), qui
  peuvent porter des secrets ou figer des variables ``VITE_*`` dans le bundle ;
- les bases SQLite, les données locales ``acp-data``, les environnements virtuels.

Sémantique reproduite : celle de ``moby/patternmatcher`` (``MatchesOrParentMatches``)
utilisée par ``docker build`` : chaque motif est nettoyé (``filepath.Clean``, barre
initiale retirée), comparé au chemin **relatif à la racine du contexte** en entier,
puis à chacun de ses dossiers parents ; ``*`` et ``?`` ne traversent pas ``/`` ;
``**`` et certaines classes de caractères peuvent traverser les niveaux ; un motif
``!`` réintègre ; le dernier motif qui s'applique l'emporte. Un motif sans ``**/``
ne vise donc que la racine, sauf ces classes qui traversent ``/``.

Usage :
    python scripts/check_docker_context.py            # vérifie l'arbre courant
    python scripts/check_docker_context.py --list     # affiche le contexte effectif
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE = ROOT / ".dockerignore"

# Noms de dossiers d'assets sous licence, à n'importe quelle profondeur. La liste
# reprend la section « Third-party licensed pixel-art assets » de .gitignore.
LICENSED_DIRECTORY_NAMES = frozenset(
    {"licensed", "licensed-assets", "local-assets", "vendor-assets", "Limzu", "LimeZu"}
)


@dataclass(frozen=True)
class Pattern:
    """Motif compilé d'un ``.dockerignore``."""

    source: str
    exclusion: bool
    regex: re.Pattern[str]
    literal_prefix: str

    def matches(self, path: str) -> bool:
        return self.regex.fullmatch(path) is not None

    def may_match_below(self, directory: str) -> bool:
        """Vrai si le motif peut viser un chemin situé sous ``directory``.

        Estimation prudente (jamais fausse dans le sens « non ») : seul un motif
        dont le préfixe littéral est incompatible avec ``directory`` est écarté.
        """

        below = directory + "/"
        prefix = self.literal_prefix
        return not prefix or below.startswith(prefix) or prefix.startswith(below)


def _clean(pattern: str) -> str:
    """Équivalent de ``filepath.Clean`` (séparateur ``/``) sur un motif."""

    absolute = pattern.startswith("/")
    parts: list[str] = []
    for part in pattern.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            elif not absolute:
                parts.append(part)
            continue
        parts.append(part)
    cleaned = "/".join(parts)
    if absolute:
        cleaned = "/" + cleaned
    return cleaned or "."


def _character_class(pattern: str, index: int) -> tuple[str, int]:
    """Lit une classe Docker : négation ``^``, plages et caractères échappés.

    Échapper la classe entière transformerait ``[a-z]`` en trois caractères
    littéraux et ``[^a]`` en inclusion de ``a``. Moby conserve ces classes dans
    sa regex : une classe négative peut donc franchir le séparateur de chemin.
    Les classes invalides ou ambiguës (``?``/``*`` non échappés) sont refusées.
    """

    index += 1
    negated = index < len(pattern) and pattern[index] == "^"
    if negated:
        index += 1
    fragments: list[str] = []

    def character(position: int) -> tuple[str, int]:
        if position >= len(pattern) or pattern[position] in "]-":
            raise ValueError("caractère ou borne de classe absent")
        if pattern[position] in "?*":
            # Moby développe ces jokers avant de traiter les crochets ; leur
            # compilation n'est donc pas celle d'une classe littérale.
            raise ValueError("joker non échappé dans une classe non pris en charge")
        if pattern[position] == "\\":
            position += 1
            if position >= len(pattern):
                raise ValueError("échappement de classe incomplet")
        return pattern[position], position + 1

    while index < len(pattern) and pattern[index] != "]":
        first, index = character(index)
        if index < len(pattern) and pattern[index] == "-":
            last, index = character(index + 1)
            if ord(first) > ord(last):
                raise ValueError("plage de classe inversée")
            fragments.append(re.escape(first) + "-" + re.escape(last))
        else:
            fragments.append(re.escape(first))
    if index >= len(pattern) or not fragments:
        raise ValueError("classe vide ou non terminée")
    return "[" + ("^" if negated else "") + "".join(fragments) + "]", index + 1


def _translate(pattern: str) -> str:
    """Traduit un motif en expression régulière, comme ``patternmatcher.compile``."""

    regex = ""
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    index += 1
                if index >= len(pattern):
                    regex += ".*"
                else:
                    regex += "(.*/)?"
                continue
            regex += "[^/]*"
        elif char == "?":
            regex += "[^/]"
        elif char == "\\" and index + 1 < len(pattern):
            index += 1
            regex += re.escape(pattern[index])
        elif char == "[":
            character_class, index = _character_class(pattern, index)
            regex += character_class
            continue
        else:
            regex += re.escape(char)
        index += 1
    return regex


def parse_dockerignore(text: str) -> list[Pattern]:
    """Lit un ``.dockerignore`` comme ``moby/patternmatcher/ignorefile.ReadAll``."""

    patterns: list[Pattern] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        exclusion = line.startswith("!")
        if exclusion:
            line = line[1:].strip()
            if not line:
                continue
        cleaned = _clean(line)
        if len(cleaned) > 1 and cleaned.startswith("/"):
            cleaned = cleaned[1:]
        literal = re.split(r"[*?\[\\]", cleaned, maxsplit=1)[0]
        try:
            regex = re.compile(_translate(cleaned))
        except (ValueError, re.error) as exc:
            raise ValueError(f"Motif .dockerignore invalide « {raw.strip()} » : {exc}") from exc
        patterns.append(Pattern(raw.strip(), exclusion, regex, literal))
    return patterns


def is_excluded(path: str, patterns: list[Pattern]) -> bool:
    """Vrai si ``path`` (relatif, séparateur ``/``) est exclu du contexte.

    Reproduit ``PatternMatcher.MatchesOrParentMatches`` : un motif s'applique au
    chemin lui-même ou à l'un de ses dossiers parents ; les motifs sont évalués
    dans l'ordre et le dernier qui s'applique décide.
    """

    posix = PurePosixPath(path)
    parents = [str(parent) for parent in reversed(posix.parents) if str(parent) != "."]
    matched = False
    for pattern in patterns:
        if pattern.exclusion != matched:
            continue
        hit = pattern.matches(str(posix))
        if not hit:
            hit = any(pattern.matches(parent) for parent in parents)
        if hit:
            matched = not pattern.exclusion
    return matched


def effective_context(root: Path, patterns: list[Pattern]) -> list[str]:
    """Fichiers de ``root`` que ``docker build`` enverrait au démon, triés."""

    exceptions = [pattern for pattern in patterns if pattern.exclusion]
    kept: list[str] = []
    for directory, subdirectories, files in os.walk(root):
        relative_directory = Path(directory).relative_to(root).as_posix()
        prefix = "" if relative_directory == "." else relative_directory + "/"
        # Élagage sûr : un dossier exclu dont aucun motif ``!`` ne peut réintégrer
        # le contenu n'est pas parcouru (``.git``, ``node_modules``…).
        subdirectories[:] = [
            name
            for name in subdirectories
            if not is_excluded(prefix + name, patterns)
            or any(pattern.may_match_below(prefix + name) for pattern in exceptions)
        ]
        for name in files:
            path = prefix + name
            if not is_excluded(path, patterns):
                kept.append(path)
    return sorted(kept)


def forbidden_reason(path: str) -> str | None:
    """Motif de refus d'un fichier du contexte, ou ``None`` s'il est admis."""

    parts = PurePosixPath(path).parts
    name = parts[-1]
    directories = parts[:-1]
    if any(part in LICENSED_DIRECTORY_NAMES for part in directories):
        return "asset sous licence (redistribution interdite)"
    if name.endswith(".aseprite"):
        return "source Aseprite sous licence"
    # Les modèles versionnés (``.env.example``, ``.env.compose.example``) ne portent
    # aucun secret ; tout autre ``.env*`` peut en porter.
    if name.startswith(".env") and not name.endswith(".example"):
        return "fichier d'environnement (secrets ou variables VITE_* figées)"
    if name.endswith((".db", ".sqlite", ".sqlite3")) or any(
        extension + "-" in name for extension in (".db", ".sqlite", ".sqlite3")
    ):
        return "base SQLite locale"
    if "acp-data" in directories:
        return "données locales de la plateforme (acp-data)"
    if any(part.startswith(".venv") or part in {"venv", "node_modules"} for part in directories):
        return "environnement local (venv ou node_modules)"
    if ".git" in directories or ".claude" in directories:
        return "métadonnées locales (.git ou .claude)"
    return None


def check(root: Path, dockerignore: Path) -> list[str]:
    """Écarts du contexte effectif de ``root`` (vide si conforme)."""

    if not dockerignore.is_file():
        return [f"{dockerignore.name} introuvable : tout le dépôt entrerait dans le contexte"]
    try:
        patterns = parse_dockerignore(dockerignore.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]
    errors: list[str] = []
    # BuildKit préfère <Dockerfile>.dockerignore au .dockerignore de la racine : un
    # tel fichier rendrait ce contrôle (et le .dockerignore versionné) sans effet.
    for directory in (root, root / "docker"):
        if directory.is_dir():
            for candidate in sorted(directory.glob("*Dockerfile.dockerignore")):
                errors.append(
                    f"{candidate.relative_to(root).as_posix()} : remplacerait .dockerignore "
                    "pour ce Dockerfile, sans le contrôle de ce script"
                )
    for path in effective_context(root, patterns):
        reason = forbidden_reason(path)
        if reason is not None:
            errors.append(f"{path} : {reason}")
    return errors


def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : code 0 si le contexte est sain, 1 sinon."""

    _force_utf8_streams()
    parser = argparse.ArgumentParser(description="Vérifie le contexte de build Docker effectif")
    parser.add_argument("--root", type=Path, default=ROOT, help="racine du contexte (défaut : dépôt)")
    parser.add_argument("--dockerignore", type=Path, default=None, help="défaut : <root>/.dockerignore")
    parser.add_argument("--list", action="store_true", help="affiche les fichiers du contexte effectif")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    dockerignore = args.dockerignore or root / ".dockerignore"
    if args.list and dockerignore.is_file():
        try:
            patterns = parse_dockerignore(dockerignore.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"Contexte de build Docker refusé : {exc}", file=sys.stderr)
            return 1
        for path in effective_context(root, patterns):
            print(path)
    errors = check(root, dockerignore)
    if errors:
        print("Contexte de build Docker refusé :", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Contexte de build Docker conforme ({root}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
