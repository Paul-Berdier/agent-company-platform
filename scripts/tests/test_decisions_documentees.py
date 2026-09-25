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
