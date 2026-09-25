#!/usr/bin/env python3
"""Balayage des secrets du dépôt par motifs, reproductible hors ligne (bibliothèque standard).

Deux portées, cumulables :

- ``--arbre`` (par défaut) : chaque fichier SUIVI par git (``git ls-files``), tel qu'il est dans
  l'arbre de travail ; les fichiers binaires (octet nul) sont ignorés ;
- ``--plage A..B`` : chaque ligne AJOUTÉE par les commits de la plage (``git log -p``), pour qu'un
  secret committé puis retiré soit trouvé aussi.

Motifs : clé privée PEM, clés d'API OpenAI, Anthropic et Google, jetons GitHub et Slack, clé d'accès
AWS, empreinte argon2id complète, jeton JWT. Code 1 et message en français au premier constat (tous
listés) ; l'extrait affiché est MASQUÉ (quatre premiers caractères), jamais le secret entier.

Ce n'est pas gitleaks (aucun outil tiers épinglé dans le dépôt) : un secret d'une autre forme
passerait. Relecture de P3 : la preuve « aucun secret » reposait sur un script du brouillon, hors
dépôt ; ce script la rend rejouable et la CI l'exécute (ci.yml, travail « moteur »).

Usage :
    python scripts/balayer_secrets.py [--arbre] [--plage origin/main..HEAD]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

RACINE = Path(__file__).resolve().parents[1]

MOTIFS = {
    # En-tête seul sur sa ligne (fichier PEM) ou suivi de la clé sur la même ligne (chaîne échappée) ;
    # l'en-tête cité dans une commande (grep de validation d'identite/acp-identite-entree) n'est pas
    # une clé.
    "clé privée PEM": re.compile(r"^\s*-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----\s*$"),
    "clé privée PEM en ligne": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----(?:\\[nr]|\s)+[A-Za-z0-9+/]{32,}"),
    "clé d'API Anthropic": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "clé d'API OpenAI": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9]{20,}"),
    "clé d'API Google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "jeton GitHub": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "clé d'accès AWS": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "jeton Slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "empreinte argon2id": re.compile(r"\$argon2id\$v=19\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]{16,}\$[A-Za-z0-9+/]{16,}"),
    "jeton JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}

Constat = Tuple[str, str, str]  # (emplacement, motif, extrait masqué)


def masquer(valeur: str) -> str:
    return valeur[:4] + "…" + f" ({len(valeur)} caractères)"


def chercher(texte: str) -> Iterator[Tuple[str, str]]:
    for nom, motif in MOTIFS.items():
        for trouve in motif.finditer(texte):
            yield nom, masquer(trouve.group(0))


def _git(*arguments: str, racine: Path) -> str:
    sortie = subprocess.run(["git", "-C", str(racine), *arguments], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if sortie.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} a échoué (code {sortie.returncode}) : {sortie.stderr.strip()}")
    return sortie.stdout


def balayer_arbre(racine: Path = RACINE) -> List[Constat]:
    constats: List[Constat] = []
    for relatif in _git("ls-files", "-z", racine=racine).split("\0"):
        if not relatif:
            continue
        chemin = racine / relatif
        if not chemin.is_file():  # fichier supprimé de l'arbre de travail, lien vers un dossier
            continue
        octets = chemin.read_bytes()
        if b"\0" in octets:
            continue
        for numero, ligne in enumerate(octets.decode("utf-8", errors="replace").splitlines(), 1):
            for nom, extrait in chercher(ligne):
                constats.append((f"{relatif}:{numero}", nom, extrait))
    return constats


def balayer_plage(plage: str, racine: Path = RACINE) -> List[Constat]:
    journal = _git("log", "-p", "--no-color", "--no-ext-diff", "--format=COMMIT %h", plage, racine=racine)
    constats: List[Constat] = []
    commit = fichier = ""
    for ligne in journal.splitlines():
        if ligne.startswith("COMMIT "):
            commit = ligne.split()[1]
        elif ligne.startswith("+++ "):
            fichier = ligne[6:] if ligne.startswith("+++ b/") else ligne[4:]
        elif ligne.startswith("+") and not ligne.startswith("+++"):
            for nom, extrait in chercher(ligne[1:]):
                constats.append((f"{commit} {fichier}", nom, extrait))
    return constats


def main(argv: Optional[Iterable[str]] = None) -> int:
    analyseur = argparse.ArgumentParser(description="Balaie le dépôt à la recherche de motifs de secrets.")
    analyseur.add_argument("--arbre", action="store_true", help="fichiers suivis de l'arbre de travail (défaut)")
    analyseur.add_argument("--plage", help="lignes ajoutées par les commits de la plage git (ex. origin/main..HEAD)")
    options = analyseur.parse_args(list(argv) if argv is not None else None)
    constats: List[Constat] = []
    portees: List[str] = []
    try:
        if options.arbre or not options.plage:
            constats += balayer_arbre(RACINE)
            portees.append("fichiers suivis")
        if options.plage:
            constats += balayer_plage(options.plage, RACINE)
            portees.append(f"lignes ajoutées par {options.plage}")
    except RuntimeError as exc:
        print(f"Balayage impossible : {exc}", file=sys.stderr)
        return 1
    if constats:
        print(f"Secrets possibles : {len(constats)} constat(s) ({', '.join(portees)}).", file=sys.stderr)
        for emplacement, nom, extrait in constats:
            print(f"  - {emplacement} : {nom} « {extrait} »", file=sys.stderr)
        return 1
    print(f"Aucun motif de secret ({', '.join(portees)} ; {len(MOTIFS)} motifs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
