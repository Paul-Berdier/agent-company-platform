"""Toute décision citée par son numéro (« D8 », « décision D12 ») dans la documentation, le journal ou
le verrou du catalogue est définie dans docs/refonte/plan.md § 1 (relecture de P3 : 13 citations,
aucune définition dans le dépôt). Une définition dit si le choix est confirmé par le propriétaire."""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
# Étapes P7 et P9 (même motif, élargi de chaque côté) : les numéros dépassent 99 (P7 : D93 à D121) ; un motif à
# deux chiffres ne voyait ni « D100 » cité, ni sa définition (décision P9-11).
CITATION = re.compile(r"\bD(\d{1,3})\b")
DEFINITION = re.compile(r"^\| D(\d{1,3}) \|", re.M)


def _sources():
    yield from sorted((RACINE / "docs" / "refonte").glob("*.md"))
    yield RACINE / "docs" / "reprise-poste.md"
    yield RACINE / "CHANGELOG.md"
    yield RACINE / "hermes" / "catalogue" / "catalogue.lock.json"
    # Étape P9 : manuel d'exploitation du propriétaire (écrit en part D de P9 ; contrôlé dès qu'il existe).
    exploitation = RACINE / "docs" / "exploitation.md"
    if exploitation.is_file():
        yield exploitation


def _citations_non_definies(plan: str, sources):
    """``sources`` : couples (nom, texte). Rend « nom:ligne cite Dn » pour chaque citation sans définition."""
    definies = {int(n) for n in DEFINITION.findall(plan)}
    manquantes = []
    for nom, texte in sources:
        for numero, ligne in enumerate(texte.splitlines(), 1):
            for n in CITATION.findall(ligne):
                if int(n) not in definies:
                    manquantes.append(f"{nom}:{numero} cite D{n}")
    return manquantes


def test_chaque_decision_citee_est_definie_dans_le_plan():
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    assert DEFINITION.findall(plan), "aucune décision D<n> définie dans docs/refonte/plan.md"
    sources = ((c.relative_to(RACINE).as_posix(), c.read_text(encoding="utf-8")) for c in _sources())
    manquantes = _citations_non_definies(plan, sources)
    assert manquantes == [], "\n".join(manquantes)


def test_une_decision_a_trois_chiffres_est_controlee_comme_les_autres():
    """Étape P9 (décision P9-11) : le plan s'arrêtait à D92 avant P7, et P7 puis P9 numérotent à la suite ; avec
    « \\d{1,2} », une citation D100 non définie passait sans bruit et une définition « | D100 | » n'était pas
    reconnue."""
    plan_sans_d100 = "| D7 | choix |\n| D99 | choix |\n"
    citation = [("docs/exemple.md", "Voir D7, D99 et D100, puis D101.")]
    assert _citations_non_definies(plan_sans_d100, citation) == [
        "docs/exemple.md:1 cite D100", "docs/exemple.md:1 cite D101"]
    plan_avec_d100 = plan_sans_d100 + "| D100 | choix |\n| D101 | choix |\n"
    assert _citations_non_definies(plan_avec_d100, citation) == []
    # Quatre chiffres ou un identifiant collé ne sont pas des décisions (« D1000 », « ID100 », « D100a »).
    assert _citations_non_definies(plan_sans_d100, [("x", "D1000 ID100 D100a")]) == []


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


def test_les_choix_de_p5_se_disent_non_confirmes():
    """Étape P5 : D48 à D66 (numérotés 40 à 58 dans le cahier de P5, déjà pris par P4), choix par défaut appliqués
    pour avancer, jamais présentés comme confirmés ; même forme que P4 (priorité, autre option et sa conséquence)."""
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    debut = plan.index("### Étape P5 : choix par défaut D48 à D66")
    bloc = plan[debut:plan.index("\n### ", debut + 1)]
    assert "à confirmer par le propriétaire" in bloc and "ne font pas foi" in bloc
    assert "Aucun de ces choix n'a été confirmé par le propriétaire" in bloc
    assert sorted(int(n) for n in DEFINITION.findall(bloc)) == list(range(48, 67))
    assert "À confirmer en" in bloc and "**D48, D49, D51, D52, D58 et D60**" in bloc
    entete = "| N° | Question | Choix appliqué en P5 | Autre option et conséquence pour vous | Écart au plan ou remarque |"
    assert entete in bloc
    for ligne in bloc.splitlines():
        if DEFINITION.match(ligne):
            cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
            assert len(cellules) == 5 and cellules[3] not in ("", "—"), ligne[:60]


def test_les_decisions_de_p6_sont_appliquees():
    """Étape P6 : D74 à D92 (numérotées 71 à 89 dans le cahier de P6, D67 à D73 déjà prises par la relecture de P5),
    APPLIQUÉES sur décision du propriétaire (il fournit les comptes, Hermes gère) : jamais présentées « à confirmer » ;
    pour chaque décision l'autre option et sa conséquence, et le numéro du cahier."""
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    debut = plan.index("### Étape P6 : décisions D74 à D92, **appliquées**")
    bloc = plan[debut:plan.index("\n### ", debut + 1)]
    assert "**appliquées**, et non « à confirmer »" in bloc
    assert sorted(int(n) for n in DEFINITION.findall(bloc)) == list(range(74, 93))
    entete = "| N° | Question | Choix appliqué en P6 | Autre option et conséquence | Remarque (n° du cahier P6) |"
    assert entete in bloc
    for ligne in bloc.splitlines():
        if definition := DEFINITION.match(ligne):
            cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
            numero = int(definition.group(1))
            assert len(cellules) == 5 and cellules[3] not in ("", "—"), ligne[:60]
            assert cellules[4].startswith(f"n° {numero - 3} du cahier"), ligne[:60]


ORIGINE_P7 = re.compile(r"^P7-(?:(\d+) du cahier|E-(\d+) du journal|F-(\d+) du journal|"
                        r"R-(\d+) de la relecture finale)\b")


def test_les_decisions_de_p7_sont_appliquees():
    """Étape P7 : décisions du cahier (P7-1 à P7-13), puis celles prises en cours de route et consignées au journal de
    P7 (partie E : P7-E-n ; partie F : P7-F-n), puis celles de la relecture finale (P7-R-n, journal des corrections),
    numérotées À LA SUITE de D92, sans trou, dans cet ordre ; APPLIQUÉES
    (le propriétaire fournit les comptes, Hermes gère), jamais « à confirmer » ; pour chacune l'autre option et sa
    conséquence, et son origine (numéro du cahier ou du journal) en tête de la remarque."""
    plan = (RACINE / "docs" / "refonte" / "plan.md").read_text(encoding="utf-8")
    debut = plan.index("### Étape P7 : décisions D93 à D")
    bloc = plan[debut:plan.index("\n### ", debut + 1)]
    assert "**appliquées**, et non « à confirmer »" in bloc
    numeros = [int(n) for n in DEFINITION.findall(bloc)]
    assert numeros == list(range(93, 93 + len(numeros))) and len(numeros) >= 13
    assert bloc.splitlines()[0] == f"### Étape P7 : décisions D93 à D{numeros[-1]}, **appliquées**"
    entete = "| N° | Question | Choix appliqué en P7 | Autre option et conséquence | Remarque (origine) |"
    assert entete in bloc
    origines = []
    for ligne in bloc.splitlines():
        if DEFINITION.match(ligne):
            cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
            assert len(cellules) == 5 and cellules[2] and cellules[3] not in ("", "—"), ligne[:60]
            trouve = ORIGINE_P7.match(cellules[4])
            assert trouve, ligne[:60]
            origines.append(next((genre, int(n)) for genre, n in zip("CEFR", trouve.groups()) if n))
    # Le cahier d'abord (P7-1 à P7-13, dans l'ordre), puis la partie E (P7-E-1…), la partie F (P7-F-1…), puis la
    # relecture finale (P7-R-1…).
    attendu = [("C", n) for n in range(1, 14)]
    attendu += [("E", n) for n in range(1, sum(1 for g, _ in origines if g == "E") + 1)]
    attendu += [("F", n) for n in range(1, sum(1 for g, _ in origines if g == "F") + 1)]
    attendu += [("R", n) for n in range(1, sum(1 for g, _ in origines if g == "R") + 1)]
    assert origines == attendu
