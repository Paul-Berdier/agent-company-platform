#!/usr/bin/env python3
"""Génère les singletons QML de la station de travail depuis ``design/tokens/*.json``.

Ce script est l'unique source des couleurs, des tailles et des durées employées par
l'interface QML : aucune valeur de jeton n'est recopiée à la main dans un fichier QML.
La sortie est versionnée dans ``apps/desktop/qml/theme/generated/`` afin qu'un poste
sans Python puisse quand même configurer le projet ; le mode ``--check`` permet à
l'intégration continue de refuser une sortie périmée.

Conventions respectées, telles que les fichiers de jetons les décrivent eux-mêmes dans
leur bloc ``$qml`` :

- un nom de jeton pointé devient une propriété camelCase (``surface.panelRaised`` donne
  ``surfacePanelRaised``, ``space.3`` donne ``space3``) ;
- un fichier ``$themed: true`` produit un objet par thème plus des accesseurs plats qui
  lisent le thème actif ; la sélection du thème est faite à l'exécution, pas ici ;
- les couleurs sont opaques et hexadécimales à six chiffres, directement affectables à
  une propriété ``color`` ;
- les valeurs à canal alpha vivent uniquement dans ``elevation.json``, sous la forme
  d'une couleur opaque et d'une opacité séparée ;
- les courbes d'accélération sont complétées par ``1, 1`` pour être passées telles
  quelles à ``easing.bezierCurve``.

Usage :
    python generate_design_tokens.py --tokens <dir> --out <dir> [--check]

Le code de sortie vaut 0 si tout est cohérent, 1 en cas de refus explicite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Association fichier de jetons -> nom du singleton QML attendu. Toute divergence avec
#: le bloc ``$qml.singleton`` du fichier lu est un refus, pas une correction silencieuse.
EXPECTED_SINGLETONS = {
    # Pas « Palette » : QtQuick exporte déjà un type Palette, qui masque un singleton
    # homonyme dans tout fichier important QtQuick. Constaté au premier passage réel
    # des tests QML : Palette.dark valait undefined.
    "colors": "Colors",
    "semantic-status": "Status",
    "typography": "Type",
    "spacing": "Space",
    "radius": "Radius",
    "elevation": "Elevation",
    "motion": "Motion",
}

#: URI du module QML qui héberge les singletons générés.
EXPECTED_MODULE = "Acp.Design"

#: Capitalisations de police acceptées, projetées vers l'énumération Qt correspondante.
FONT_CAPITALIZATION = {
    "MixedCase": "Font.MixedCase",
    "AllUppercase": "Font.AllUppercase",
    "AllLowercase": "Font.AllLowercase",
    "SmallCaps": "Font.SmallCaps",
    "Capitalize": "Font.Capitalize",
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class GenerationError(RuntimeError):
    """Refus explicite : un jeton est hors contrat et rien ne sera écrit."""


# --- Projection des noms ------------------------------------------------------


def camel_case(dotted: str) -> str:
    """``surface.panelRaised`` -> ``surfacePanelRaised`` ; ``space.3`` -> ``space3``."""

    segments = [segment for segment in dotted.split(".") if segment]
    if not segments:
        raise GenerationError(f"nom de jeton vide : {dotted!r}")
    head, *tail = segments
    parts = [head[0].lower() + head[1:]]
    for segment in tail:
        parts.append(segment[0].upper() + segment[1:])
    name = "".join(parts)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        raise GenerationError(
            f"le jeton {dotted!r} produit l'identifiant QML invalide {name!r}"
        )
    return name


# --- Rendu des valeurs --------------------------------------------------------


def qml_color(value: object, token: str) -> str:
    if not isinstance(value, str) or not _HEX_COLOR.match(value):
        raise GenerationError(
            f"{token} : couleur attendue en hexadécimal opaque à six chiffres, reçu {value!r}"
        )
    return f'"{value.lower()}"'


def qml_number(value: object, token: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationError(f"{token} : nombre attendu, reçu {value!r}")
    return repr(float(value)) if isinstance(value, float) else str(value)


def qml_string_list(values: object, token: str) -> str:
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise GenerationError(f"{token} : liste de chaînes attendue, reçu {values!r}")
    inner = ", ".join(json.dumps(item, ensure_ascii=False) for item in values)
    return f"[{inner}]"


def qml_bezier(values: object, token: str) -> str:
    """Complète les quatre points de contrôle par ``1, 1`` pour ``easing.bezierCurve``."""

    if not isinstance(values, list) or len(values) != 4:
        raise GenerationError(
            f"{token} : quatre points de contrôle attendus pour une Bézier cubique, reçu {values!r}"
        )
    numbers = ", ".join(qml_number(item, token) for item in values)
    return f"[{numbers}, 1, 1]"


# --- Lecture des fichiers de jetons -------------------------------------------


def load_tokens(tokens_dir: Path, stem: str) -> dict:
    path = tokens_dir / f"{stem}.json"
    if not path.is_file():
        raise GenerationError(f"fichier de jetons introuvable : {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GenerationError(f"{path} : JSON invalide ({error})") from error
    if not isinstance(document, dict):
        raise GenerationError(f"{path} : objet JSON attendu à la racine")
    qml_block = document.get("$qml")
    if not isinstance(qml_block, dict):
        raise GenerationError(f"{path} : bloc $qml manquant")
    singleton = qml_block.get("singleton")
    if singleton != EXPECTED_SINGLETONS[stem]:
        raise GenerationError(
            f"{path} : singleton {singleton!r} déclaré, {EXPECTED_SINGLETONS[stem]!r} attendu"
        )
    module = qml_block.get("module")
    if module != EXPECTED_MODULE:
        raise GenerationError(
            f"{path} : module {module!r} déclaré, {EXPECTED_MODULE!r} attendu"
        )
    if not isinstance(document.get("tokens"), dict):
        raise GenerationError(f"{path} : objet 'tokens' manquant")
    return document


def public_tokens(document: dict) -> dict:
    """Écarte les clés de métadonnées préfixées par ``$``."""

    return {
        name: payload
        for name, payload in document["tokens"].items()
        if not name.startswith("$")
    }


# --- Squelette de fichier -----------------------------------------------------


def header(stem: str, document: dict) -> list[str]:
    return [
        "// Fichier généré — NE PAS MODIFIER À LA MAIN.",
        f"// Source    : design/tokens/{stem}.json (version {document.get('$version', 'inconnue')})",
        "// Générateur : apps/desktop/cmake/generate_design_tokens.py",
        "// Toute correction se fait dans le fichier de jetons, puis par régénération.",
        "",
        "pragma Singleton",
        "",
        "import QtQuick",
        "",
    ]


_THEME_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def theme_object_name(theme: str) -> str:
    """``atelier-nuit`` -> ``atelierNuit`` : nom de l'objet QML qui porte un thème."""

    head, *tail = theme.split("-")
    return head + "".join(part[0].upper() + part[1:] for part in tail)


def theme_ids(stem: str, document: dict) -> list[str]:
    """Liste des thèmes déclarés par un fichier à thème ; refus si elle est mal formée."""

    themes = document.get("$themes")
    if (not isinstance(themes, list) or not themes
            or not all(isinstance(theme, str) and _THEME_ID.match(theme) for theme in themes)
            or len(set(themes)) != len(themes)):
        raise GenerationError(f"{stem} : $themes doit être une liste non vide d'identifiants distincts")
    default = document.get("$defaultTheme")
    if default not in themes:
        raise GenerationError(f"{stem} : $defaultTheme {default!r} absent de $themes")
    return list(themes)


def theme_metadata(document: dict) -> dict[str, dict]:
    """Famille et luminosité de chaque thème, lues dans ``$themeFamilies`` de colors.json."""

    themes = theme_ids("colors", document)
    families = document.get("$themeFamilies")
    if not isinstance(families, dict):
        raise GenerationError("colors : bloc $themeFamilies manquant")
    meta: dict[str, dict] = {}
    for family, entry in families.items():
        if family.startswith("$"):
            continue
        if not isinstance(entry, dict) or not entry.get("label"):
            raise GenerationError(f"colors : famille {family!r} sans libellé")
        for variant, dark in (("sombre", True), ("clair", False)):
            theme = entry.get(variant)
            if theme not in themes:
                raise GenerationError(f"colors : famille {family!r}, variante {variant} : thème {theme!r} inconnu")
            if theme in meta:
                raise GenerationError(f"colors : le thème {theme!r} appartient à deux familles")
            meta[theme] = {"family": family, "isDark": dark}
    missing = [theme for theme in themes if theme not in meta]
    if missing:
        raise GenerationError(f"colors : thèmes sans famille : {missing}")
    return meta


def theme_preamble(themes: list[str], default: str) -> list[str]:
    """Sélection du thème actif. Un nom inconnu retombe sur le thème par défaut, et ``known`` le dit."""

    chain = " : ".join(
        f'root.theme === "{theme}" ? root.{theme_object_name(theme)}'
        for theme in themes if theme != default
    )
    selection = f"{chain} : root.{theme_object_name(default)}" if chain else f"root.{theme_object_name(default)}"
    return [
        "    // Thème actif. Écrit par ThemeBridge (Acp.Theme) d'après la préférence lue par la",
        "    // couche C++ (SystemAppearance) ; jamais deviné par un composant.",
        f'    property string theme: "{default}"',
        f"    readonly property var themes: {qml_string_list(themes, 'themes')}",
        "    // Faux si `theme` n'est pas un thème généré : le thème par défaut s'applique alors.",
        "    readonly property bool known: root.themes.indexOf(root.theme) >= 0",
        f"    readonly property QtObject current: {selection}",
        "    readonly property bool isDark: root.current.isDark",
        "    readonly property string family: root.current.family",
        "",
    ]


def theme_header(meta: dict) -> list[str]:
    return [
        f"        readonly property bool isDark: {str(meta['isDark']).lower()}",
        f"        readonly property string family: {json.dumps(meta['family'])}",
    ]


# --- Contrastes ---------------------------------------------------------------


def relative_luminance(hex_color: str) -> float:
    channels = []
    for index in (1, 3, 5):
        value = int(hex_color[index:index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


#: Surfaces opaques sur lesquelles le texte courant doit rester lisible (sélection comprise).
TEXT_SURFACES = ("surface.canvas", "surface.sidebar", "surface.panel", "surface.panelRaised",
                 "surface.sunken", "surface.overlay", "state.hover", "state.selected", "accent.muted")
#: Surfaces sur lesquelles un contour interactif, le focus et un accent doivent se distinguer.
CONTROL_SURFACES = ("surface.canvas", "surface.sidebar", "surface.panel", "surface.panelRaised")
STATUS_SURFACES = ("surface.canvas", "surface.panel", "surface.panelRaised", "surface.sunken")


def measure_contrasts(colors: dict, status: dict) -> dict[str, dict[str, float]]:
    """Mesure, thème par thème, les paires que la doctrine exige ; refuse sous un seuil.

    Rend le minimum mesuré de chaque règle, par thème, pour qu'il soit relevé dans la
    documentation. Seuils : ``$contrast`` de colors.json et de semantic-status.json.
    """

    thresholds = colors.get("$contrast", {})
    status_thresholds = status.get("$contrast", {})
    tokens = public_tokens(colors)
    status_tokens = public_tokens(status)
    failures: list[str] = []
    report: dict[str, dict[str, float]] = {}

    for theme in theme_ids("colors", colors):
        minima: dict[str, float] = {}

        def require(rule: str, first: str, second: str, threshold: float, label: str) -> None:
            ratio = contrast_ratio(first, second)
            minima[rule] = min(minima.get(rule, 99.0), round(ratio, 2))
            if ratio < threshold:
                failures.append(f"{theme} : {label} = {ratio:.2f}:1 < {threshold}:1")

        def color(name: str) -> str:
            return tokens[name][theme]

        for text in ("text.primary", "text.secondary", "text.muted"):
            for surface in TEXT_SURFACES:
                require("texte", color(text), color(surface), float(thresholds.get("texte", 4.5)),
                        f"{text} sur {surface}")
        for surface in CONTROL_SURFACES:
            require("bordureInteractive", color("border.interactive"), color(surface),
                    float(thresholds.get("bordureInteractive", 3.0)), f"border.interactive sur {surface}")
            require("focus", color("border.focus"), color(surface), float(thresholds.get("focus", 3.0)),
                    f"border.focus sur {surface}")
            for accent in ("accent.primary", "accent.secondary"):
                require("accent", color(accent), color(surface), float(thresholds.get("accent", 3.0)),
                        f"{accent} sur {surface}")
        for accent in ("accent.primary", "accent.hover", "accent.pressed"):
            require("encreSurAccent", color("text.onAccent"), color(accent),
                    float(thresholds.get("encreSurAccent", 4.5)), f"text.onAccent sur {accent}")

        families = sorted({name.split(".")[1] for name in status_tokens})
        for family in families:
            foreground = status_tokens[f"status.{family}.foreground"][theme]
            tint = status_tokens[f"status.{family}.tint"][theme]
            border = status_tokens[f"status.{family}.border"][theme]
            for surface in STATUS_SURFACES:
                require("premierPlan", foreground, color(surface),
                        float(status_thresholds.get("premierPlan", 4.5)), f"status.{family}.foreground sur {surface}")
            require("premierPlanSurTeinte", foreground, tint,
                    float(status_thresholds.get("premierPlanSurTeinte", 4.5)), f"status.{family} sur sa teinte")
            require("bordureSurPanneau", border, color("surface.panel"),
                    float(status_thresholds.get("bordureSurPanneau", 3.0)), f"status.{family}.border sur surface.panel")
        report[theme] = minima

    if failures:
        raise GenerationError("contraste insuffisant :\n  - " + "\n  - ".join(failures))
    return report


# --- Générateurs par fichier --------------------------------------------------


def themed_color_objects(stem: str, document: dict, meta: dict[str, dict]) -> list[str]:
    """Un QtObject par thème, puis des accesseurs plats qui lisent le thème actif."""

    tokens = public_tokens(document)
    themes = theme_ids(stem, document)
    if themes != list(meta):
        raise GenerationError(f"{stem} : $themes {themes} diffère de celui de colors.json {list(meta)}")
    lines = theme_preamble(themes, document["$defaultTheme"])
    for theme in themes:
        lines.append(f"    readonly property QtObject {theme_object_name(theme)}: QtObject {{")
        lines.extend(theme_header(meta[theme]))
        for token, payload in tokens.items():
            if theme not in payload:
                raise GenerationError(f"{stem}.{token} : valeur {theme!r} manquante")
            lines.append(
                f"        readonly property color {camel_case(token)}: "
                f"{qml_color(payload[theme], f'{stem}.{token}')}"
            )
        lines.append("    }")
        lines.append("")
    lines.append("    // Accesseurs plats : un composant ne choisit jamais son thème lui-même.")
    for token in tokens:
        name = camel_case(token)
        lines.append(f"    readonly property color {name}: root.current.{name}")
    return lines


def generate_flat_themed(stem: str, document: dict, meta: dict[str, dict]) -> str:
    """colors.json : un objet par thème, plus des accesseurs plats de type ``color``."""

    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(themed_color_objects(stem, document, meta))
    labels = document.get("$themeLabels", {})
    families = {
        family: entry for family, entry in document.get("$themeFamilies", {}).items() if not family.startswith("$")
    }
    lines.append("")
    lines.append("    // Libellés français des thèmes et des familles, pour les réglages et le diagnostic.")
    lines.append(
        "    readonly property var themeLabels: ("
        + json.dumps({theme: labels.get(theme, theme) for theme in meta}, ensure_ascii=False)
        + ")"
    )
    lines.append(
        "    readonly property var families: ("
        + json.dumps(
            {family: {"label": entry["label"], "sombre": entry["sombre"], "clair": entry["clair"]}
             for family, entry in families.items()},
            ensure_ascii=False,
        )
        + ")"
    )
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_status(stem: str, document: dict, meta: dict[str, dict]) -> str:
    """semantic-status.json : couleurs par thème, métadonnées, priorité et résolution."""

    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(themed_color_objects(stem, document, meta))
    lines.append("")

    # Métadonnées non colorées : libellé français, nom de glyphe, repli ASCII.
    families: dict[str, dict] = {}
    for token, payload in tokens.items():
        segments = token.split(".")
        if len(segments) != 3 or segments[0] != "status":
            raise GenerationError(
                f"{stem}.{token} : forme attendue status.<état>.<rôle>"
            )
        family, role = segments[1], segments[2]
        entry = families.setdefault(family, {})
        if role == "foreground":
            entry["label"] = payload.get("$label")
            entry["glyphName"] = payload.get("$glyphName")
            entry["asciiFallback"] = payload.get("$asciiFallback")
        entry.setdefault("roles", set()).add(role)

    shape_rules = document.get("$shapeRules", {})
    dashed = set(shape_rules.get("dashedBorder", []))
    animated = set(shape_rules.get("animated", []))
    never_filled = set(shape_rules.get("neverFilled", []))

    lines.append("    // Métadonnées d'état : la couleur n'est jamais seule porteuse de sens.")
    lines.append("    readonly property QtObject meta: QtObject {")
    for family, entry in families.items():
        missing = {"foreground", "tint", "border"} - entry["roles"]
        if missing:
            raise GenerationError(
                f"{stem} : l'état {family!r} n'expose pas {sorted(missing)}"
            )
        if not entry.get("label"):
            raise GenerationError(f"{stem} : l'état {family!r} n'a pas de $label")
        lines.append(f"        readonly property QtObject {family}: QtObject {{")
        lines.append(f'            readonly property string key: "{family}"')
        lines.append(
            f"            readonly property string label: {json.dumps(entry['label'], ensure_ascii=False)}"
        )
        lines.append(
            f"            readonly property string glyphName: {json.dumps(entry['glyphName'] or '', ensure_ascii=False)}"
        )
        lines.append(
            f"            readonly property string asciiFallback: {json.dumps(entry['asciiFallback'] or '', ensure_ascii=False)}"
        )
        lines.append(
            f"            readonly property bool dashedBorder: {str(family in dashed).lower()}"
        )
        lines.append(
            f"            readonly property bool animated: {str(family in animated).lower()}"
        )
        lines.append(
            f"            readonly property bool neverFilled: {str(family in never_filled).lower()}"
        )
        lines.append(
            f"            readonly property color foreground: root.status{family[0].upper()}{family[1:]}Foreground"
        )
        lines.append(
            f"            readonly property color tint: root.status{family[0].upper()}{family[1:]}Tint"
        )
        lines.append(
            f"            readonly property color border: root.status{family[0].upper()}{family[1:]}Border"
        )
        lines.append("        }")
    lines.append("    }")
    lines.append("")

    priority = document.get("$priority", {}).get("order", [])
    unknown_priority = [family for family in priority if family not in families]
    if unknown_priority:
        raise GenerationError(
            f"{stem} : $priority cite des états sans jeton : {unknown_priority}"
        )
    lines.append("    // Ordre d'agrégation : une réussite ne masque jamais un échec du groupe.")
    lines.append(
        f"    readonly property var priorityOrder: {qml_string_list(priority, f'{stem}.$priority')}"
    )
    lines.append("")

    # Table de correspondance vers les identifiants réellement produits par l'API.
    mapping = document.get("$backendMapping", {})
    # Note QML : une liaison qui commence par « { » est lue comme un bloc JavaScript.
    # L'objet littéral est donc systématiquement entouré de parenthèses.
    lines.append("    // Correspondance relevée dans le backend ; voir $backendMapping.$sources.")
    lines.append("    readonly property var backendMapping: ({")
    mapping_entries: list[str] = []
    for family_name, table in mapping.items():
        if family_name.startswith("$") or not isinstance(table, dict):
            continue
        rows: list[str] = []
        for raw_state, payload in table.items():
            if raw_state.startswith("$") or not isinstance(payload, dict):
                continue
            token_name = payload.get("token")
            if token_name not in families:
                raise GenerationError(
                    f"{stem}.$backendMapping.{family_name}.{raw_state} : "
                    f"jeton {token_name!r} inconnu"
                )
            label = payload.get("label")
            if not label:
                raise GenerationError(
                    f"{stem}.$backendMapping.{family_name}.{raw_state} : libellé manquant"
                )
            rows.append(
                f'            {json.dumps(raw_state, ensure_ascii=False)}: '
                f'{{ "token": "{token_name}", "label": {json.dumps(label, ensure_ascii=False)} }}'
            )
        mapping_entries.append(
            f'        {json.dumps(family_name, ensure_ascii=False)}: {{\n'
            + ",\n".join(rows)
            + "\n        }"
        )
    lines.append(",\n".join(mapping_entries))
    lines.append("    })")
    lines.append("")

    lines.append("    /*!")
    lines.append("        Résout un identifiant d'état brut de l'API vers son jeu de jetons.")
    lines.append("        Un état inconnu du backend ne provoque ni plantage ni invention :")
    lines.append('        il retombe sur « Inconnu » en conservant l\'identifiant brut.')
    lines.append("    */")
    lines.append("    function resolve(family, rawState) {")
    lines.append("        var table = root.backendMapping[family];")
    lines.append("        if (table !== undefined && table[rawState] !== undefined) {")
    lines.append("            var row = table[rawState];")
    lines.append("            return {")
    lines.append('                "token": row.token,')
    lines.append('                "label": row.label,')
    lines.append('                "meta": root.meta[row.token],')
    lines.append('                "recognised": true')
    lines.append("            };")
    lines.append("        }")
    lines.append("        return {")
    lines.append('            "token": "unknown",')
    lines.append('            "label": root.meta.unknown.label,')
    lines.append('            "meta": root.meta.unknown,')
    lines.append('            "recognised": false')
    lines.append("        };")
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_typography(stem: str, document: dict, meta: dict[str, dict]) -> str:
    del meta
    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    scales = document.get("$textScales", {})
    values = scales.get("valeurs", [100])
    if (not isinstance(values, list) or not values
            or not all(isinstance(value, int) and 80 <= value <= 200 for value in values)):
        raise GenerationError(f"{stem} : $textScales.valeurs doit lister des pourcentages entiers de 80 à 200")
    default_scale = scales.get("$default", 100)
    if default_scale not in values:
        raise GenerationError(f"{stem} : $textScales.$default absent des valeurs")
    lines.append("    // Taille du texte choisie par l'opérateur, en pour cent ; écrite par ThemeBridge.")
    lines.append(f"    property int textScale: {default_scale}")
    lines.append(f"    readonly property var textScales: {json.dumps(values)}")
    lines.append("    readonly property real scale: root.textScale / 100")
    lines.append("")

    for token, payload in tokens.items():
        name = camel_case(token)
        token_type = payload.get("$type")
        value = payload.get("$value")
        reference = f"{stem}.{token}"
        if token_type == "fontFamilyStack":
            lines.append(
                f"    readonly property var {name}: {qml_string_list(value, reference)}"
            )
            # font.families (liste) n'existe pas en QML avec Qt 6.8 : seule font.family,
            # une chaîne, est disponible. La première famille de la pile réellement
            # installée sur le poste est donc résolue une fois, au chargement. Aucune ne
            # l'est : chaîne vide, et Qt applique sa police par défaut plutôt qu'un nom
            # inventé.
            lines.append(
                f"    readonly property string {name}Resolved: root.firstInstalled({name})"
            )
        elif token_type in ("dimension", "fontWeight", "number"):
            lines.append(
                f"    readonly property real {name}: {qml_number(value, reference)}"
            )
        else:
            raise GenerationError(f"{reference} : type {token_type!r} non pris en charge")
    lines.append("")
    lines.append("    function firstInstalled(stack) {")
    lines.append("        var installed = Qt.fontFamilies();")
    lines.append("        for (var i = 0; i < stack.length; ++i) {")
    lines.append("            if (installed.indexOf(stack[i]) >= 0)")
    lines.append("                return stack[i];")
    lines.append("        }")
    lines.append('        return "";')
    lines.append("    }")
    lines.append("")

    roles = document.get("$roles", {})
    lines.append("    // Rôles prêts à l'emploi : un écran consomme un rôle, il n'en compose pas.")
    lines.append("    // La taille et la hauteur de ligne suivent textScale, à chaud.")
    for role_name, role in roles.items():
        if role_name.startswith("$") or not isinstance(role, dict):
            continue
        lines.append(f"    readonly property QtObject {camel_case(role_name)}: QtObject {{")
        # Les types déclarés suivent ceux de QML : font.pixelSize et font.weight sont
        # des entiers, lineHeight et letterSpacing des réels, family une chaîne résolue.
        for field, declared, token_ref in (
            ("family", "string", role.get("family")),
            ("pixelSize", "int", role.get("size")),
            ("lineHeight", "real", role.get("lineHeight")),
            ("weight", "int", role.get("weight")),
            ("letterSpacing", "real", role.get("letterSpacing")),
        ):
            if token_ref is None:
                raise GenerationError(f"{stem}.$roles.{role_name} : champ {field} manquant")
            if token_ref not in tokens:
                raise GenerationError(
                    f"{stem}.$roles.{role_name}.{field} : jeton {token_ref!r} inconnu"
                )
            target = camel_case(token_ref)
            if field == "family":
                target += "Resolved"
            if field == "pixelSize":
                lines.append(f"        readonly property {declared} {field}: Math.round(root.{target} * root.scale)")
            elif field == "lineHeight":
                lines.append(f"        readonly property {declared} {field}: Math.round(root.{target} * root.scale)")
            else:
                lines.append(f"        readonly property {declared} {field}: root.{target}")
        capitalization = role.get("capitalization", "MixedCase")
        if capitalization not in FONT_CAPITALIZATION:
            raise GenerationError(
                f"{stem}.$roles.{role_name} : capitalisation {capitalization!r} inconnue"
            )
        lines.append(
            f"        readonly property int capitalization: {FONT_CAPITALIZATION[capitalization]}"
        )
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_scalar(stem: str, document: dict, meta: dict[str, dict]) -> str:
    """spacing.json et radius.json : uniquement des dimensions, un seul thème."""

    del meta
    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    for token, payload in tokens.items():
        reference = f"{stem}.{token}"
        if payload.get("$type") != "dimension":
            raise GenerationError(f"{reference} : type 'dimension' attendu")
        lines.append(
            f"    readonly property real {camel_case(token)}: "
            f"{qml_number(payload.get('$value'), reference)}"
        )

    breakpoints = document.get("$breakpoints", {})
    named = {
        name: payload
        for name, payload in breakpoints.items()
        if not name.startswith("$") and isinstance(payload, dict)
    }
    if named:
        lines.append("")
        lines.append("    // Seuils de largeur de fenêtre, pas des tailles d'appareil.")
        for name, payload in named.items():
            lines.append(
                f"    readonly property real breakpoint{name[0].upper()}{name[1:]}: "
                f"{qml_number(payload.get('$value'), f'{stem}.$breakpoints.{name}')}"
            )

    densities = {
        name: payload for name, payload in document.get("$densities", {}).items()
        if not name.startswith("$") and isinstance(payload, dict)
    }
    if densities:
        default = document["$densities"].get("$default")
        if default not in densities:
            raise GenerationError(f"{stem} : $densities.$default {default!r} inconnu")
        lines.append("")
        lines.append("    // Densité choisie par l'opérateur ; écrite par ThemeBridge.")
        lines.append(f'    property string density: "{default}"')
        lines.append(f"    readonly property var densities: {qml_string_list(list(densities), 'densities')}")
        lines.append(
            "    readonly property var densityLabels: ("
            + json.dumps({name: payload.get("label", name) for name, payload in densities.items()},
                         ensure_ascii=False)
            + ")"
        )
        for field in ("rowHeight", "controlHeight"):
            chain = []
            for name, payload in densities.items():
                reference = payload.get(field)
                if reference not in tokens:
                    raise GenerationError(f"{stem}.$densities.{name}.{field} : jeton {reference!r} inconnu")
                chain.append((name, camel_case(reference)))
            fallback = dict(chain)[default]
            expression = " : ".join(
                f'root.density === "{name}" ? root.{target}' for name, target in chain if name != default
            )
            expression = f"{expression} : root.{fallback}" if expression else f"root.{fallback}"
            lines.append(f"    readonly property real {field}: {expression}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_motion(stem: str, document: dict, meta: dict[str, dict]) -> str:
    del meta
    tokens = public_tokens(document)
    profiles = {
        name: payload for name, payload in document.get("$profiles", {}).items()
        if not name.startswith("$") and isinstance(payload, dict)
    }
    default = document.get("$defaultProfile")
    reduced = document.get("$reducedProfile")
    if default not in profiles or reduced not in profiles:
        raise GenerationError(f"{stem} : $defaultProfile et $reducedProfile doivent nommer des profils déclarés")
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.append("    // Profil actif. Écrit par ThemeBridge d'après la préférence de l'opérateur (couche")
    lines.append("    // C++). Jamais deviné en QML ; un nom inconnu retombe sur le profil par défaut.")
    lines.append(f'    property string profile: "{default}"')
    lines.append(f"    readonly property var profiles: {qml_string_list(list(profiles), 'profiles')}")
    lines.append("    readonly property bool knownProfile: root.profiles.indexOf(root.profile) >= 0")
    lines.append(f'    readonly property bool reduced: root.profile === "{reduced}"')
    lines.append("    // Mode Concentration : coupe l'ambiance quel que soit le profil (préférence distincte).")
    lines.append("    property bool concentration: false")
    lines.append(
        "    readonly property var profileLabels: ("
        + json.dumps({name: document.get("$profileLabels", {}).get(name, name) for name in profiles},
                     ensure_ascii=False)
        + ")"
    )
    lines.append("")

    for token, payload in tokens.items():
        name = camel_case(token)
        reference = f"{stem}.{token}"
        token_type = payload.get("$type")
        value = payload.get("$value")
        if token_type in ("duration", "dimension", "number"):
            declared = "int" if token_type == "duration" else "real"
            lines.append(
                f"    readonly property {declared} {name}: {qml_number(value, reference)}"
            )
        elif token_type == "cubicBezier":
            lines.append(f"    readonly property var {name}: {qml_bezier(value, reference)}")
        else:
            raise GenerationError(f"{reference} : type {token_type!r} non pris en charge")
    lines.append("")

    entries_by_profile: dict[str, set[str]] = {}
    for profile_name, profile in profiles.items():
        lines.append(f"    readonly property QtObject {camel_case(profile_name)}Profile: QtObject {{")
        entries_by_profile[profile_name] = set()
        for entry_name, entry in profile.items():
            if entry_name.startswith("$") or not isinstance(entry, dict):
                continue
            entries_by_profile[profile_name].add(entry_name)
            lines.append(f"        readonly property QtObject {entry_name}: QtObject {{")
            duration_ref = entry.get("duration")
            if duration_ref is not None:
                if duration_ref not in tokens:
                    raise GenerationError(
                        f"{stem}.$profiles.{profile_name}.{entry_name} : "
                        f"durée {duration_ref!r} inconnue"
                    )
                lines.append(
                    f"            readonly property int duration: root.{camel_case(duration_ref)}"
                )
            easing_ref = entry.get("easing")
            if easing_ref is not None:
                if easing_ref not in tokens:
                    raise GenerationError(
                        f"{stem}.$profiles.{profile_name}.{entry_name} : "
                        f"courbe {easing_ref!r} inconnue"
                    )
                lines.append(
                    f"            readonly property var easing: root.{camel_case(easing_ref)}"
                )
            distance = entry.get("distance")
            if isinstance(distance, str):
                if distance not in tokens:
                    raise GenerationError(
                        f"{stem}.$profiles.{profile_name}.{entry_name} : "
                        f"distance {distance!r} inconnue"
                    )
                lines.append(
                    f"            readonly property real distance: root.{camel_case(distance)}"
                )
            elif isinstance(distance, (int, float)):
                lines.append(
                    f"            readonly property real distance: "
                    f"{qml_number(distance, f'{stem}.$profiles.{profile_name}.{entry_name}')}"
                )
            loops = entry.get("loops")
            if loops is not None:
                if loops == "infini":
                    lines.append("            readonly property int loops: Animation.Infinite")
                elif isinstance(loops, int) and not isinstance(loops, bool) and loops >= 0:
                    lines.append(f"            readonly property int loops: {loops}")
                else:
                    raise GenerationError(
                        f"{stem}.$profiles.{profile_name}.{entry_name} : boucles {loops!r} invalides"
                    )
            lines.append("        }")
        lines.append("    }")
        lines.append("")

    reference_entries = entries_by_profile[default]
    for profile_name, entries in entries_by_profile.items():
        if entries != reference_entries:
            raise GenerationError(
                f"{stem} : le profil {profile_name!r} ne déclare pas les mêmes entrées que {default!r} "
                f"(écart : {sorted(entries ^ reference_entries)})"
            )

    chain = " : ".join(
        f'root.profile === "{name}" ? root.{camel_case(name)}Profile' for name in profiles if name != default
    )
    selection = f"{chain} : root.{camel_case(default)}Profile" if chain else f"root.{camel_case(default)}Profile"
    lines.append("    // Profil réellement appliqué par les composants.")
    lines.append(f"    readonly property QtObject active: {selection}")
    if "ambiance" in reference_entries:
        lines.append("    // L'ambiance (sprites et scènes décoratifs) ne tourne que si le profil l'admet et")
        lines.append("    // hors mode Concentration ; la vue la suspend en plus hors écran.")
        lines.append("    readonly property bool ambianceActive: !root.concentration && root.active.ambiance.duration > 0")
    if "spriteActivity" in reference_entries:
        lines.append("    readonly property bool spriteActivityActive: root.active.spriteActivity.duration > 0")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_elevation(stem: str, document: dict, meta: dict[str, dict]) -> str:
    tokens = public_tokens(document)
    themes = theme_ids(stem, document)
    if themes != list(meta):
        raise GenerationError(f"{stem} : $themes {themes} diffère de celui de colors.json {list(meta)}")
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(theme_preamble(themes, document["$defaultTheme"]))

    for theme in themes:
        lines.append(f"    readonly property QtObject {theme_object_name(theme)}: QtObject {{")
        lines.extend(theme_header(meta[theme]))
        for token, payload in tokens.items():
            name = camel_case(token)
            reference = f"{stem}.{token}"
            token_type = payload.get("$type")
            if token_type not in ("elevation", "scrim"):
                raise GenerationError(f"{reference} : type {token_type!r} non pris en charge")
            values = payload.get(theme)
            if not isinstance(values, dict):
                raise GenerationError(f"{reference} : valeurs {theme!r} manquantes")
            lines.append(f"        readonly property QtObject {name}: QtObject {{")
            for field in ("offsetX", "offsetY", "blur", "opacity"):
                if field in values:
                    lines.append(
                        f"            readonly property real {field}: {qml_number(values[field], reference)}"
                    )
            # Nommé shadowColor et non color : une propriété QML nommée comme son type est
            # légale mais illisible, et le nom retenu est celui de MultiEffect.
            lines.append(
                f"            readonly property color shadowColor: {qml_color(values.get('color'), reference)}"
            )
            # Les champs surface et border citent un jeton de colors.json : le générateur ne
            # les résout pas ici pour ne pas créer de dépendance circulaire entre singletons.
            # Le composant consommateur les lit comme des noms et interroge Colors.
            for field in ("surface", "border"):
                if field in values:
                    lines.append(
                        f"            readonly property string {field}Token: "
                        f"{json.dumps(values[field], ensure_ascii=False)}"
                    )
            lines.append("        }")
        lines.append("    }")
        lines.append("")
    lines.append("    // Accesseurs plats vers le thème actif.")
    for token in tokens:
        name = camel_case(token)
        lines.append(f"    readonly property QtObject {name}: root.current.{name}")
    lines.append("}")
    return "\n".join(lines) + "\n"


GENERATORS = {
    "colors": generate_flat_themed,
    "semantic-status": generate_status,
    "typography": generate_typography,
    "spacing": generate_scalar,
    "radius": generate_scalar,
    "elevation": generate_elevation,
    "motion": generate_motion,
}


def qmldir_contents() -> str:
    lines = [
        "# Fichier généré — NE PAS MODIFIER À LA MAIN.",
        "# Ce qmldir n'est pas consommé par CMake : qt_add_qml_module en produit un.",
        "# Il est conservé pour permettre une relecture du module hors configuration.",
        f"module {EXPECTED_MODULE}",
    ]
    for singleton in sorted(EXPECTED_SINGLETONS.values()):
        lines.append(f"singleton {singleton} 1.0 {singleton}.qml")
    return "\n".join(lines) + "\n"


def render_all(tokens_dir: Path) -> dict[str, str]:
    documents = {stem: load_tokens(tokens_dir, stem) for stem in EXPECTED_SINGLETONS}
    meta = theme_metadata(documents["colors"])
    rendered: dict[str, str] = {}
    for stem, singleton in EXPECTED_SINGLETONS.items():
        rendered[f"{singleton}.qml"] = GENERATORS[stem](stem, documents[stem], meta)
    # Après les générateurs : ils refusent en français une valeur absente ou mal formée, avant toute mesure.
    measure_contrasts(documents["colors"], documents["semantic-status"])
    rendered["qmldir"] = qmldir_contents()
    return rendered


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Génère les singletons QML de design depuis design/tokens/*.json."
    )
    parser.add_argument("--tokens", required=True, type=Path, help="dossier design/tokens")
    parser.add_argument("--out", required=True, type=Path, help="dossier de sortie QML")
    parser.add_argument(
        "--check",
        action="store_true",
        help="ne rien écrire ; échouer si la sortie versionnée est périmée",
    )
    arguments = parser.parse_args(argv)

    try:
        rendered = render_all(arguments.tokens)
    except GenerationError as error:
        print(f"REFUS : {error}", file=sys.stderr)
        return 1

    if arguments.check:
        stale: list[str] = []
        for name, content in rendered.items():
            path = arguments.out / name
            if not path.is_file():
                stale.append(f"{name} : absent")
                continue
            current = path.read_text(encoding="utf-8")
            if current != content:
                stale.append(f"{name} : contenu périmé")
        if stale:
            print(
                "REFUS : la sortie versionnée ne correspond plus aux jetons.",
                file=sys.stderr,
            )
            for item in stale:
                print(f"  - {item}", file=sys.stderr)
            print(
                "  Régénérez avec : python apps/desktop/cmake/generate_design_tokens.py "
                "--tokens design/tokens --out apps/desktop/qml/theme/generated",
                file=sys.stderr,
            )
            return 1
        print(f"{len(rendered)} fichiers générés à jour.")
        return 0

    arguments.out.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        (arguments.out / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"{len(rendered)} fichiers écrits dans {arguments.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
