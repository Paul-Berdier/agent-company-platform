"""Toute décision citée par son numéro (« D8 », « décision D12 ») dans la documentation, le journal ou
le verrou du catalogue est définie dans docs/refonte/plan.md § 1 (relecture de P3 : 13 citations,
aucune définition dans le dépôt). Une définition dit si le choix est confirmé par le propriétaire."""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CITATION = re.compile(r"\bD(\d{1,2})\b")
DEFINITION = re.compile(r"^\| D(\d{1,2}) \|", re.M)


def _sources():
    yield from sorted((RACINE / "docs" / "refonte").glob("*.md"))
    yield RACINE / "docs" / "reprise-poste.md"
    yield RACINE / "CHANGELOG.md"
    yield RACINE / "hermes" / "catalogue" / "catalogue.lock.json"


def test_chaque_decision_citee_est_definie_dans_le_plan():
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    definies = {int(n) for n in DEFINITION.findall(plan)}
    assert definies, "aucune décision D<n> définie dans docs/refonte/plan.md"
    manquantes = []
    for chemin in _sources():
        for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
            for n in CITATION.findall(ligne):
                if int(n) not in definies:
                    manquantes.append(f"{chemin.relative_to(RACINE).as_posix()}:{numero} cite D{n}")
    assert manquantes == [], "\n".join(manquantes)


def test_les_choix_de_p3_se_disent_non_confirmes():
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    debut = plan.index("### Étape P3 : choix par défaut D1 à D20")
    bloc = plan[debut:plan.index("\n### ", debut + 1)]
    assert "à confirmer par le propriétaire" in bloc and "ne font pas\nfoi" in bloc
    assert sorted(int(n) for n in DEFINITION.findall(bloc)) == list(range(1, 21))


def test_les_choix_de_p4_se_disent_non_confirmes():
    """Étape P4 : D21 à D47, choix par défaut appliqués pour avancer, jamais présentés comme confirmés. Depuis
    la relecture de P4 : une priorité de confirmation (comme P3), et pour chaque choix l'autre option et sa
    conséquence pour le propriétaire (colonne dédiée, jamais vide)."""
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    debut = plan.index("### Étape P4 : choix par défaut D21 à D47")
    bloc = plan[debut:plan.index("\n### ", debut + 1)]
    assert "à confirmer par le propriétaire" in bloc and "ne font pas foi" in bloc
    assert "Aucun de ces choix n'a été confirmé par le propriétaire" in bloc
    assert sorted(int(n) for n in DEFINITION.findall(bloc)) == list(range(21, 48))
    assert "À confirmer en priorité" in bloc and "**D25, D31, D39, D40 et D41**" in bloc
    entete = "| N° | Question | Choix appliqué en P4 | Autre option et conséquence pour vous | Écart au plan ou remarque |"
    assert entete in bloc
    for ligne in bloc.splitlines():
        if DEFINITION.match(ligne):
            cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
            assert len(cellules) == 5 and cellules[3] not in ("", "—"), ligne[:60]
