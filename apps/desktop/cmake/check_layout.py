#!/usr/bin/env python3
"""Vérifie la cohérence interne de ``apps/desktop`` SANS compiler quoi que ce soit.

Aucune chaîne d'outils native n'est disponible sur le poste de rédaction : ni Qt, ni
CMake, ni compilateur C++. Ce script couvre ce qui reste vérifiable localement, et rien
de plus. Il ne prouve PAS que le projet compile ; il prouve seulement qu'aucun chemin,
aucun nom de fichier et aucun URI de module ne se contredisent.

Contrôles effectués :

1. tout fichier déclaré dans un ``CMakeLists.txt`` existe sur le disque ;
2. tout fichier source ou QML présent sur le disque est déclaré quelque part ;
3. chaque module QML déclare un URI unique, et chaque ``import Acp.*`` d'un fichier QML
   désigne un URI réellement déclaré ;
4. les singletons QML portent à la fois ``pragma Singleton`` et la propriété de source
   ``QT_QML_SINGLETON_TYPE`` ;
5. les fichiers de jetons sont du JSON valide, et la sortie engendrée est à jour ;
6. aucun chemin absolu, aucun nom d'hôte codé en dur, aucun secret en clair ;
7. toutes les fins de ligne sont des LF, sans octet nul ni tabulation d'indentation.

Code de sortie : 0 si tout est cohérent, 1 s'il reste au moins un constat.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DESKTOP_ROOT.parents[1]
TOKENS_DIR = REPO_ROOT / "design" / "tokens"
GENERATED_DIR = DESKTOP_ROOT / "qml" / "theme" / "generated"

#: Extensions soumises au contrôle de fins de ligne et de contenu.
TEXT_SUFFIXES = {".cpp", ".h", ".qml", ".json", ".txt", ".cmake", ".py", ".in", ".md"}

#: Motifs qui ne doivent apparaître nulle part : un secret en clair, ou une origine
#: réseau codée en dur. Les adresses de bouclage sont tolérées dans les tests seulement.
FORBIDDEN_PATTERNS = [
    (re.compile(r"\bBEGIN (RSA |EC |OPENSSH )?PRIVATE KEY\b"), "clé privée en clair"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "identifiant AWS"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "jeton GitHub"),
    (re.compile(r"password\s*=\s*[\"'][^\"']+[\"']", re.IGNORECASE), "mot de passe littéral"),
]

#: Chemins absolus interdits dans les sources versionnées.
ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"[\"'][A-Za-z]:[\\/]"),
    re.compile(r"[\"']/(usr|home|opt|Users)/"),
]


#: Répertoires de sortie locale, ignorés par git (apps/desktop/.gitignore) : ils contiennent
#: des fichiers engendrés par CMake, avec des chemins absolus du poste, qui ne sont pas des
#: sources. Les inclure ferait échouer ce script sur tout poste qui a compilé.
EXCLUDED_DIRECTORIES = {"build"}


def desktop_files(pattern: str) -> list[Path]:
    """Fichiers de ``apps/desktop`` correspondant au motif, hors sorties de compilation."""

    return sorted(
        path
        for path in DESKTOP_ROOT.rglob(pattern)
        if not EXCLUDED_DIRECTORIES.intersection(path.relative_to(DESKTOP_ROOT).parts)
    )


class Findings:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def ok(self) -> bool:
        return not self.items


# --- Lecture des CMakeLists ---------------------------------------------------


def cmake_files() -> list[Path]:
    return desktop_files("CMakeLists.txt")


def cmake_body(cmake_file: Path) -> str:
    """Contenu d'un CMakeLists débarrassé de ses lignes de commentaire.

    Une note citant un fichier ou un URI ne doit pas compter comme une déclaration.
    """

    return "\n".join(
        line
        for line in cmake_file.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def declared_files(findings: Findings) -> set[Path]:
    """Chemins déclarés dans les CMakeLists, résolus par rapport à leur répertoire."""

    declared: set[Path] = set()
    # Les tokens sont lus mot à mot pour pouvoir écarter ceux qui désignent le répertoire
    # de construction : un fichier engendré n'existe pas encore dans l'arborescence source.
    token_pattern = re.compile(r"\$?\{?[A-Za-z0-9_${}]*\}?[A-Za-z0-9_./-]*\.(?:cpp|h|qml|in)\b")
    for cmake_file in cmake_files():
        base = cmake_file.parent
        body = cmake_body(cmake_file)

        for match in token_pattern.finditer(body):
            token = match.group(0)
            if "BINARY_DIR" in token:
                # Sortie de configuration : elle n'a pas à exister dans les sources.
                continue
            if re.fullmatch(r"\$\{[A-Za-z0-9_]+\}\.(?:cpp|h|qml|in)", token):
                # Chemin paramétré par une variable de fonction, par exemple
                # « cpp/${name}.cpp » : l'indirection est résolue plus bas, à partir des
                # appels à acp_add_cpp_test.
                continue
            # Les variables CMake sont retirées ; ce qui reste est relatif au CMakeLists.
            relative = re.sub(r"\$\{[A-Za-z0-9_]+\}", "", token).lstrip("/")
            if not relative:
                continue
            candidate = (base / relative).resolve()
            declared.add(candidate)
            if not candidate.exists():
                findings.add(
                    f"{cmake_file.relative_to(REPO_ROOT).as_posix()} déclare un fichier "
                    f"absent : {token}"
                )

        # Les tests C++ sont déclarés par leur nom via la fonction acp_add_cpp_test, qui
        # dérive le chemin « cpp/<nom>.cpp ». L'indirection est suivie ici.
        for name in re.findall(r"acp_add_cpp_test\(\s*([A-Za-z0-9_]+)\s*\)", body):
            candidate = (base / "cpp" / f"{name}.cpp").resolve()
            declared.add(candidate)
            if not candidate.exists():
                findings.add(
                    f"{cmake_file.relative_to(REPO_ROOT).as_posix()} déclare le test "
                    f"« {name} » mais cpp/{name}.cpp est absent"
                )
    return declared


def source_files_on_disk() -> set[Path]:
    found: set[Path] = set()
    for pattern in ("src/**/*.cpp", "src/**/*.h", "src/**/*.in", "qml/**/*.qml",
                    "tests/**/*.cpp"):
        for path in DESKTOP_ROOT.glob(pattern):
            found.add(path.resolve())
    return found


def check_every_file_is_declared(declared: set[Path], findings: Findings) -> None:
    # Les fichiers QML de test sont découverts par le harnais Qt Quick Test lui-même, à
    # partir de QUICK_TEST_SOURCE_DIR : ils n'ont pas à figurer dans un CMakeLists.
    for path in sorted(source_files_on_disk()):
        if path in declared:
            continue
        relative = path.relative_to(DESKTOP_ROOT)
        if relative.parts[0] == "tests" and relative.suffix == ".qml":
            continue
        findings.add(f"fichier présent mais déclaré nulle part : {relative.as_posix()}")


# --- Modules QML --------------------------------------------------------------


def declared_module_uris(findings: Findings) -> dict[str, Path]:
    uris: dict[str, Path] = {}
    pattern = re.compile(r"^\s*URI\s+([A-Za-z][A-Za-z0-9_.]*)\s*$", re.MULTILINE)
    for cmake_file in cmake_files():
        for match in pattern.finditer(cmake_body(cmake_file)):
            uri = match.group(1)
            if uri in uris:
                findings.add(f"URI de module QML déclaré deux fois : {uri}")
            uris[uri] = cmake_file
    return uris


def check_qml_imports(uris: dict[str, Path], findings: Findings) -> None:
    # Acp.Runtime n'est pas déclaré par CMake : il est enregistré impérativement en C++
    # depuis Application::registerQmlTypes(). C'est un choix documenté.
    known = set(uris) | {"Acp.Runtime"}
    import_pattern = re.compile(r"^\s*import\s+(Acp\.[A-Za-z0-9_.]*)", re.MULTILINE)
    for path in desktop_files("*.qml"):
        text = path.read_text(encoding="utf-8")
        for match in import_pattern.finditer(text):
            uri = match.group(1)
            if uri not in known:
                findings.add(
                    f"{path.relative_to(REPO_ROOT).as_posix()} importe « {uri} », "
                    "qui n'est déclaré par aucun module"
                )


def check_singletons(findings: Findings) -> None:
    marked: set[str] = set()
    for cmake_file in cmake_files():
        text = cmake_body(cmake_file)
        blocks = re.findall(r"acp_mark_qml_singletons\(([^)]*)\)", text, re.DOTALL)
        for block in blocks:
            for token in re.findall(r"[A-Za-z0-9_./-]+\.qml", block):
                marked.add(token)
        # Les listes passées par variable sont suivies : ACP_DESIGN_SINGLETONS est
        # déclarée puis réutilisée, il faut donc résoudre l'indirection.
        for name in re.findall(r"acp_mark_qml_singletons\(\$\{([A-Za-z0-9_]+)\}\)", text):
            assignment = re.search(rf"set\({name}\s*(.*?)\)", text, re.DOTALL)
            if assignment:
                for token in re.findall(r"[A-Za-z0-9_./-]+\.qml", assignment.group(1)):
                    marked.add(token)

    for path in desktop_files("*.qml"):
        text = path.read_text(encoding="utf-8")
        has_pragma = "pragma Singleton" in text
        is_marked = path.name in marked
        if has_pragma and not is_marked:
            findings.add(
                f"{path.relative_to(REPO_ROOT).as_posix()} porte « pragma Singleton » mais "
                "n'est pas marqué QT_QML_SINGLETON_TYPE : le type serait ordinaire à "
                "l'exécution"
            )
        if is_marked and not has_pragma:
            findings.add(
                f"{path.relative_to(REPO_ROOT).as_posix()} est marqué singleton par CMake "
                "mais ne porte pas « pragma Singleton »"
            )


# --- Jetons de design ---------------------------------------------------------


def check_tokens(findings: Findings) -> None:
    if not TOKENS_DIR.is_dir():
        findings.add(f"dossier de jetons introuvable : {TOKENS_DIR}")
        return
    for path in sorted(TOKENS_DIR.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            findings.add(f"{path.relative_to(REPO_ROOT).as_posix()} : JSON invalide ({error})")
            continue
        if "tokens" not in document:
            findings.add(
                f"{path.relative_to(REPO_ROOT).as_posix()} : objet « tokens » manquant"
            )

    generator = DESKTOP_ROOT / "cmake" / "generate_design_tokens.py"
    result = subprocess.run(
        [sys.executable, str(generator), "--tokens", str(TOKENS_DIR), "--out",
         str(GENERATED_DIR), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        findings.add(
            "les singletons QML engendrés sont périmés : "
            + (result.stderr or result.stdout).strip().replace("\n", " | ")
        )


# --- Contenu des fichiers -----------------------------------------------------


def check_file_contents(findings: Findings) -> None:
    for path in desktop_files("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        raw = path.read_bytes()

        if b"\r\n" in raw or b"\r" in raw.replace(b"\r\n", b""):
            findings.add(f"{relative} : fin de ligne autre que LF")
        if b"\x00" in raw:
            findings.add(f"{relative} : octet nul")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.add(f"{relative} : contenu non décodable en UTF-8")
            continue

        for pattern, label in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                findings.add(f"{relative} : motif interdit détecté ({label})")

        # Les chemins absolus sont refusés partout : ils rendent un projet inconfigurable
        # ailleurs que sur le poste qui les a écrits.
        for pattern in ABSOLUTE_PATH_PATTERNS:
            for match in pattern.finditer(text):
                findings.add(f"{relative} : chemin absolu littéral ({match.group(0)})")

        if path.suffix in {".cpp", ".h", ".qml"} and "\t" in text:
            findings.add(f"{relative} : tabulation dans un fichier source")

        if text and not text.endswith("\n"):
            findings.add(f"{relative} : le fichier ne se termine pas par un saut de ligne")


def check_no_hardcoded_origin(findings: Findings) -> None:
    """Aucune origine réseau réelle ne doit être codée en dur.

    Les seules URL tolérées sont celles des documentations citées en commentaire, les
    adresses de bouclage des tests, et le domaine réservé ``.invalid`` employé par les
    exemples — qui, par définition, ne résout jamais.
    """

    url_pattern = re.compile(r"https?://([A-Za-z0-9.-]+)")
    allowed_hosts = {
        "doc.qt.io",
        "learn.microsoft.com",
        "html.spec.whatwg.org",
        "www.qt.io",
        "localhost",
        "127.0.0.1",
    }
    for path in desktop_files("*"):
        if not path.is_file() or path.suffix not in {".cpp", ".h", ".qml", ".json", ".txt"}:
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for match in url_pattern.finditer(path.read_text(encoding="utf-8")):
            host = match.group(1)
            if host in allowed_hosts or host.endswith(".invalid"):
                continue
            findings.add(f"{relative} : origine réseau codée en dur ({host})")


# --- Point d'entrée -----------------------------------------------------------


def main() -> int:
    findings = Findings()

    declared = declared_files(findings)
    check_every_file_is_declared(declared, findings)

    uris = declared_module_uris(findings)
    check_qml_imports(uris, findings)
    check_singletons(findings)

    check_tokens(findings)
    check_file_contents(findings)
    check_no_hardcoded_origin(findings)

    print(f"Modules QML déclarés : {', '.join(sorted(uris)) or 'aucun'}")
    print(f"Fichiers déclarés par CMake : {len(declared)}")

    if findings.ok():
        print("Aucun constat. La cohérence interne est vérifiée.")
        print(
            "RAPPEL : ce script ne compile RIEN. Aucune preuve de compilation n'est "
            "produite ici ; elle ne peut venir que d'un job d'intégration continue Windows."
        )
        return 0

    print(f"\n{len(findings.items)} constat(s) :", file=sys.stderr)
    for item in findings.items:
        print(f"  - {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
