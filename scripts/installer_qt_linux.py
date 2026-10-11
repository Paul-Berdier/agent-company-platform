#!/usr/bin/env python3
"""Installe Qt 6.8.3 de conda-forge hors du dépôt, pour construire et tester la station sous Linux.

Outil de l'agent de développement (outillage A, ``docs/refonte/atelier-outillage.md``). Il ne sert ni en
intégration continue, ni pour le poste Windows : la référence reste ``packaging/windows/toolchain.json``
et la preuve qui fait foi reste le workflow « Desktop CI » (windows-2022, MSVC). Aucun workflow ne
l'appelle.

Ce qu'il installe
-----------------
Depuis le canal conda-forge, dans un préfixe donné (par défaut ``/opt/acp-outils/qt683``) :

- ``qt6-main`` 6.8.3, build ``hb82b983_5`` épinglé, archive vérifiée par son condensat SHA-256 ;
- ``libgl-devel``, ``libegl-devel`` et ``fontconfig`` (en-têtes OpenGL/EGL et polices pour CMake et le
  rendu hors écran).

Seul ``qt6-main`` est épinglé. Les compagnons et les dépendances suivent conda-forge au jour de
l'installation : deux installations à des dates différentes peuvent différer sur ces paquets.

Prérequis
---------
- Linux x86_64 (refus explicite sur tout autre système ou toute autre architecture) ;
- Python 3.10 ou plus récent, avec le module ``venv`` (paquet ``python3.X-venv`` sous Debian ou
  Ubuntu), seulement si py-rattler doit être installé ;
- accès HTTPS à pypi.org et files.pythonhosted.org (py-rattler, seulement s'il manque) et à
  conda.anaconda.org (paquets) ;
- droit d'écriture sur le préfixe et sur le dossier de l'environnement virtuel.

Effets
------
1. Inspecte ``<préfixe>/conda-meta`` sans rien télécharger. Si ``qt6-main`` 6.8.3 y figure avec le
   build et le condensat épinglés, et les trois compagnons avec lui, le script le dit (« déjà
   installé »), affiche les commandes CMake et sort en 0. Tout autre préfixe non vide est refusé (autre
   version, autre build, autre condensat, compagnon manquant, dossier non conda) : il n'est jamais
   complété ni écrasé.
2. Si py-rattler 0.27.1 manque à l'interpréteur courant, crée au besoin l'environnement virtuel
   ``<parent du préfixe>/rattler-venv`` (option ``--venv``), y installe ``py-rattler==0.27.1`` par pip
   (roue manylinux x86_64 vérifiée par son condensat, ``--require-hashes``), puis se relance sous cet
   interpréteur. Un environnement existant qui porte une autre version est refusé.
3. Résout les paquets, vérifie version, build et condensat de ``qt6-main``, puis installe dans le
   préfixe. Le cache de téléchargement est celui de rattler (``~/.cache/rattler``).
4. Relit ``conda-meta`` et affiche les commandes CMake à utiliser.

Rien d'autre n'est modifié : ni le dépôt, ni le système, ni Docker.

Usage
-----
::

    python3 scripts/installer_qt_linux.py                  # préfixe par défaut
    python3 scripts/installer_qt_linux.py /chemin/qt683     # autre préfixe
    python3 scripts/installer_qt_linux.py --verifier        # constate seulement, ne télécharge rien
    python3 scripts/installer_qt_linux.py --simuler         # résout, n'installe rien dans le préfixe

Codes de sortie : 0 en cas de succès ; 1 en cas d'échec ou de refus, avec un message en français sur
la sortie d'erreur.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, NoReturn, Optional, Sequence

QT_NOM = "qt6-main"
QT_VERSION = "6.8.3"
QT_BUILD = "hb82b983_5"
#: Condensat de l'archive conda-forge linux-64/qt6-main-6.8.3-hb82b983_5.conda (relevé dans conda-meta).
QT_SHA256 = "9e410da286149f4b560da7b8a299caa96ff495b5b8ddf01b8e6680598331e691"
COMPAGNONS = ("libgl-devel", "libegl-devel", "fontconfig")
# Forme stricte acceptée par le solveur de rattler (« nom ==version build »).
SPECS = (f"{QT_NOM} =={QT_VERSION} {QT_BUILD}",) + COMPAGNONS
CANAL = "conda-forge"

RATTLER_VERSION = "0.27.1"
#: Roue py_rattler-0.27.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (PyPI).
RATTLER_SHA256 = "c83bccfd63643fb13ae0a4507a5251fb871571db31716d74dc25bd85cb7bf38b"

PREFIXE_DEFAUT = Path("/opt/acp-outils/qt683")
NOM_VENV = "rattler-venv"
VARIABLE_RELANCE = "ACP_INSTALLER_QT_RELANCE"


class Refus(Exception):
    """Échec ou refus explicite : message en français, code de sortie 1."""


@dataclass
class EtatPrefixe:
    existe: bool = False
    vide: bool = True
    conda: bool = False
    qt_version: Optional[str] = None
    qt_build: Optional[str] = None
    qt_sha256: Optional[str] = None
    paquets: List[str] = field(default_factory=list)

    @property
    def compagnons_manquants(self) -> List[str]:
        return [nom for nom in COMPAGNONS if nom not in self.paquets]


def sortir_en_echec(message: str) -> NoReturn:
    print(f"Échec : {message}", file=sys.stderr)
    sys.exit(1)


def verifier_plateforme() -> None:
    if not sys.platform.startswith("linux"):
        raise Refus(f"ce script ne s'exécute que sous Linux (système détecté : {sys.platform}). "
                    "Pour Windows, suivez packaging/windows/toolchain.json et scripts/setup-desktop.ps1.")
    machine = platform.machine()
    if machine != "x86_64":
        raise Refus(f"architecture {machine or 'inconnue'} non prise en charge : seul Linux x86_64 l'est "
                    f"(build {QT_BUILD} de linux-64).")


def lire_prefixe(prefixe: Path) -> EtatPrefixe:
    """Lit l'état du préfixe sans rien télécharger (bibliothèque standard seulement)."""
    etat = EtatPrefixe()
    if not prefixe.exists():
        return etat
    if not prefixe.is_dir():
        raise Refus(f"{prefixe} existe et n'est pas un dossier.")
    etat.existe = True
    etat.vide = not any(prefixe.iterdir())
    meta = prefixe / "conda-meta"
    if not meta.is_dir():
        return etat
    etat.conda = True
    for fichier in sorted(meta.glob("*.json")):
        # Nom de fichier conda : <nom>-<version>-<build>.json ; ni la version ni le build ne contiennent « - ».
        morceaux = fichier.stem.rsplit("-", 2)
        if len(morceaux) == 3:
            etat.paquets.append(morceaux[0])
    fiches = sorted(meta.glob(f"{QT_NOM}-*.json"))
    fiches = [f for f in fiches if f.stem.rsplit("-", 2)[0] == QT_NOM]
    if len(fiches) > 1:
        raise Refus(f"{meta} contient plusieurs fiches {QT_NOM} : préfixe incohérent, à vérifier à la main.")
    if fiches:
        try:
            donnees = json.loads(fiches[0].read_text(encoding="utf-8"))
        except (OSError, ValueError) as erreur:
            raise Refus(f"fiche illisible {fiches[0]} : {erreur}") from erreur
        etat.qt_version = str(donnees.get("version") or "") or None
        etat.qt_build = str(donnees.get("build") or "") or None
        etat.qt_sha256 = str(donnees.get("sha256") or "") or None
    return etat


def deja_installe(prefixe: Path, etat: EtatPrefixe) -> bool:
    """Vrai si l'installation attendue est présente ; lève Refus si le préfixe est occupé autrement."""
    if not etat.existe or etat.vide:
        return False
    if not etat.conda:
        raise Refus(f"{prefixe} n'est pas vide et ne contient pas de conda-meta : préfixe refusé, il ne "
                    "sera ni complété ni écrasé. Choisissez un préfixe vide ou absent.")
    if etat.qt_version is None:
        raise Refus(f"{prefixe} contient un environnement conda sans {QT_NOM} : préfixe refusé. "
                    "Choisissez un préfixe vide ou absent.")
    if etat.qt_version != QT_VERSION:
        raise Refus(f"{prefixe} contient {QT_NOM} {etat.qt_version}, pas {QT_VERSION} : préfixe refusé. "
                    "Supprimez-le vous-même ou choisissez un autre préfixe.")
    if etat.qt_build != QT_BUILD or etat.qt_sha256 != QT_SHA256:
        raise Refus(f"{prefixe} contient {QT_NOM} {QT_VERSION} de build {etat.qt_build or 'inconnu'} et de "
                    f"condensat {etat.qt_sha256 or 'inconnu'}, pas l'épingle {QT_BUILD} ({QT_SHA256}) : "
                    "préfixe refusé. Supprimez-le vous-même ou choisissez un autre préfixe.")
    manquants = etat.compagnons_manquants
    if manquants:
        raise Refus(f"{prefixe} contient {QT_NOM} {QT_VERSION} mais pas {', '.join(manquants)} : "
                    "installation incomplète, refusée. Supprimez ce préfixe vous-même, puis relancez.")
    return True


def afficher_installation(prefixe: Path, etat: EtatPrefixe) -> None:
    print(f"{QT_NOM} {etat.qt_version} (build {etat.qt_build}, condensat de l'épingle) présent dans {prefixe}.")
    print(f"Compagnons présents : {', '.join(COMPAGNONS)} ; {len(etat.paquets)} paquets dans conda-meta.")


def afficher_commandes(prefixe: Path) -> None:
    print()
    print("Commandes à utiliser depuis la racine du dépôt (CMake 3.24 ou plus récent et Ninja exigés par")
    print("apps/desktop/CMakePresets.json) :")
    print()
    print(f"  export QT_ROOT_DIR={prefixe}")
    print("  export QT_QPA_PLATFORM=offscreen")
    print(f"  export QT_QPA_FONTDIR={prefixe / 'fonts'}")
    print("  cd apps/desktop")
    print("  cmake --preset linux-gcc-debug")
    print("  cmake --build --preset linux-gcc-debug")
    print("  ctest --preset linux-gcc-debug")
    print()
    manquants = [outil for outil in ("cmake", "ninja") if shutil.which(outil) is None]
    if manquants:
        print(f"Avertissement : introuvable dans le PATH : {', '.join(manquants)}.")
    print("Ce préréglage Linux éprouve la logique ; la preuve qui fait foi reste la Desktop CI Windows.")


# --- py-rattler -------------------------------------------------------------------------------------


def version_rattler_courante() -> Optional[str]:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("py-rattler")
    except PackageNotFoundError:
        return None


def version_rattler_venv(python_venv: Path) -> Optional[str]:
    code = ("from importlib.metadata import version, PackageNotFoundError\n"
            "try:\n    print(version('py-rattler'))\nexcept PackageNotFoundError:\n    pass\n")
    resultat = subprocess.run([str(python_venv), "-I", "-c", code], capture_output=True, text=True,
                              check=False)
    if resultat.returncode != 0:
        raise Refus(f"l'interpréteur {python_venv} ne répond pas : {resultat.stderr.strip() or 'sans message'}")
    return resultat.stdout.strip() or None


def preparer_venv(venv: Path) -> Path:
    """Rend l'interpréteur d'un environnement virtuel qui porte py-rattler à la version épinglée."""
    python_venv = venv / "bin" / "python"
    if venv.exists() and not python_venv.exists():
        raise Refus(f"{venv} existe mais n'est pas un environnement virtuel Python ({python_venv} absent). "
                    "Indiquez un autre --venv ou supprimez ce dossier vous-même.")
    if not venv.exists():
        if sys.version_info < (3, 10):
            raise Refus(f"py-rattler {RATTLER_VERSION} exige Python 3.10 ou plus récent "
                        f"(interpréteur courant : {platform.python_version()}).")
        print(f"Création de l'environnement virtuel {venv}…")
        resultat = subprocess.run([sys.executable, "-m", "venv", str(venv)], check=False)
        if resultat.returncode != 0 or not python_venv.exists():
            raise Refus(f"création de {venv} impossible (module venv absent ? sous Debian ou Ubuntu : paquet "
                        f"python{sys.version_info.major}.{sys.version_info.minor}-venv).")
    installee = version_rattler_venv(python_venv)
    if installee == RATTLER_VERSION:
        return python_venv
    if installee is not None:
        raise Refus(f"{venv} porte py-rattler {installee}, pas {RATTLER_VERSION} : environnement refusé. "
                    "Indiquez un autre --venv ou supprimez celui-ci vous-même.")
    print(f"Installation de py-rattler {RATTLER_VERSION} dans {venv} (roue vérifiée par condensat)…")
    with tempfile.TemporaryDirectory(prefix="acp-rattler-") as dossier:
        exigences = Path(dossier) / "exigences.txt"
        exigences.write_text(f"py-rattler=={RATTLER_VERSION} --hash=sha256:{RATTLER_SHA256}\n", encoding="utf-8")
        resultat = subprocess.run(
            [str(python_venv), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
             "--only-binary=:all:", "--require-hashes", "-r", str(exigences)],
            check=False)
    if resultat.returncode != 0:
        raise Refus(f"pip n'a pas pu installer py-rattler {RATTLER_VERSION} dans {venv} "
                    f"(code {resultat.returncode}) ; voir le message de pip ci-dessus.")
    if version_rattler_venv(python_venv) != RATTLER_VERSION:
        raise Refus(f"py-rattler {RATTLER_VERSION} reste introuvable dans {venv} après installation.")
    return python_venv


def relancer_sous(python_venv: Path) -> NoReturn:
    if os.environ.get(VARIABLE_RELANCE) == "1":
        raise Refus(f"relance déjà faite et py-rattler {RATTLER_VERSION} toujours absent : arrêt.")
    environnement = dict(os.environ)
    environnement[VARIABLE_RELANCE] = "1"
    sys.stdout.flush()
    sys.stderr.flush()
    argv = [str(python_venv), "-I", str(Path(__file__).resolve()), *sys.argv[1:]]
    os.execve(str(python_venv), argv, environnement)


async def resoudre() -> list:
    from rattler import Platform, VirtualPackage, solve  # importé seulement sous py-rattler épinglé

    return await solve(sources=[CANAL], specs=list(SPECS), virtual_packages=VirtualPackage.detect(),
                       platforms=[Platform("linux-64"), Platform("noarch")])


def controler_resolution(paquets: Sequence) -> None:
    qt = [p for p in paquets if p.name.normalized == QT_NOM]
    if len(qt) != 1:
        raise Refus(f"résolution inattendue : {len(qt)} paquet(s) {QT_NOM}.")
    enregistrement = qt[0]
    condensat = enregistrement.sha256.hex() if isinstance(enregistrement.sha256, (bytes, bytearray)) else None
    if str(enregistrement.version) != QT_VERSION or enregistrement.build != QT_BUILD:
        raise Refus(f"résolution inattendue : {QT_NOM} {enregistrement.version} {enregistrement.build}, "
                    f"attendu {QT_VERSION} {QT_BUILD}.")
    if condensat != QT_SHA256:
        raise Refus(f"condensat de {QT_NOM} inattendu : {condensat or 'absent'}, attendu {QT_SHA256}.")
    noms = {p.name.normalized for p in paquets}
    manquants = [nom for nom in COMPAGNONS if nom not in noms]
    if manquants:
        raise Refus(f"résolution incomplète : {', '.join(manquants)} absent(s).")
    print(f"Résolu : {QT_NOM} {enregistrement.version} {enregistrement.build} (condensat vérifié), "
          f"{len(paquets)} paquets au total.")


async def installer(paquets: list, prefixe: Path) -> None:
    from rattler import install

    await install(paquets, target_prefix=str(prefixe))


# --- Programme principal ----------------------------------------------------------------------------


class Formateur(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):  # type: ignore[override]
        return super().add_usage(usage, actions, groups, prefix="Usage : ")

    def _split_lines(self, text, width):  # type: ignore[override]
        # Ne jamais couper un chemin sur son trait d'union (« /opt/acp-outils »).
        return textwrap.wrap(" ".join(text.split()), width, break_on_hyphens=False)


class Analyseur(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sortir_en_echec(f"arguments invalides ({message}).")


def analyser(argv: Sequence[str]) -> argparse.Namespace:
    analyseur = Analyseur(
        prog="installer_qt_linux.py", add_help=False, formatter_class=Formateur,
        description=(f"Installe {QT_NOM} {QT_VERSION} (build {QT_BUILD}) et {', '.join(COMPAGNONS)}\n"
                     f"depuis {CANAL}, hors du dépôt, au moyen de py-rattler {RATTLER_VERSION}.\n"
                     "Outil de l'agent de développement sous Linux x86_64 : jamais en CI,\n"
                     "jamais pour le poste Windows."),
        epilog="Codes de sortie : 0 succès ; 1 échec ou refus. Voir docs/refonte/atelier-outillage.md.")
    analyseur._positionals.title = "arguments positionnels"
    analyseur._optionals.title = "options"
    analyseur.add_argument("prefixe", nargs="?", default=str(PREFIXE_DEFAUT), metavar="PREFIXE",
                           help=f"dossier d'installation (par défaut : {PREFIXE_DEFAUT})")
    analyseur.add_argument("--venv", metavar="DOSSIER",
                           help=f"environnement virtuel de py-rattler (par défaut : <parent du préfixe>/{NOM_VENV})")
    mode = analyseur.add_mutually_exclusive_group()
    mode.add_argument("--verifier", action="store_true",
                      help="constate l'état du préfixe sans rien télécharger ; code 1 si Qt n'y est pas")
    mode.add_argument("--simuler", action="store_true",
                      help="résout les paquets et contrôle l'épingle, sans rien installer dans le "
                           "préfixe (py-rattler peut l'être dans son environnement virtuel s'il manque)")
    analyseur.add_argument("-h", "--aide", "--help", action="help", help="affiche cette aide et sort")
    return analyseur.parse_args(argv)


def principal(argv: Sequence[str]) -> int:
    arguments = analyser(argv)
    verifier_plateforme()
    prefixe = Path(arguments.prefixe).expanduser().resolve()
    venv = Path(arguments.venv).expanduser().resolve() if arguments.venv else prefixe.parent / NOM_VENV

    etat = lire_prefixe(prefixe)
    if deja_installe(prefixe, etat):
        print(f"Qt {QT_VERSION} déjà installé dans {prefixe} : rien à faire, rien n'a été téléchargé.")
        afficher_installation(prefixe, etat)
        afficher_commandes(prefixe)
        return 0
    if arguments.verifier:
        raise Refus(f"{QT_NOM} {QT_VERSION} absent de {prefixe} (préfixe {'vide' if etat.existe else 'absent'}).")

    if version_rattler_courante() != RATTLER_VERSION:
        relancer_sous(preparer_venv(venv))

    print(f"Résolution de {', '.join(SPECS)} sur {CANAL}…")
    try:
        paquets = asyncio.run(resoudre())
    except Exception as erreur:  # toute erreur de rattler devient un refus explicite
        raise Refus(f"résolution impossible : {erreur}") from erreur
    controler_resolution(paquets)
    if arguments.simuler:
        print(f"Simulation : rien n'a été installé dans {prefixe}.")
        return 0

    print(f"Installation de {len(paquets)} paquets dans {prefixe}…")
    try:
        asyncio.run(installer(paquets, prefixe))
    except Exception as erreur:  # idem : refus explicite, jamais de trace brute
        raise Refus(f"installation interrompue : {erreur}. Le préfixe {prefixe} peut être partiellement "
                    "rempli : supprimez-le vous-même avant de relancer.") from erreur

    etat = lire_prefixe(prefixe)
    if not deja_installe(prefixe, etat):
        raise Refus(f"{QT_NOM} {QT_VERSION} introuvable dans {prefixe}/conda-meta après installation.")
    print(f"Qt {QT_VERSION} installé dans {prefixe}.")
    afficher_installation(prefixe, etat)
    afficher_commandes(prefixe)
    return 0


def main() -> None:
    try:
        sys.exit(principal(sys.argv[1:]))
    except Refus as refus:
        sortir_en_echec(str(refus))
    except KeyboardInterrupt:
        sortir_en_echec("interrompu par l'utilisateur.")
    except OSError as erreur:  # droits, disque plein, interpréteur introuvable : jamais de trace brute
        sortir_en_echec(f"erreur du système : {erreur}.")


if __name__ == "__main__":
    main()
