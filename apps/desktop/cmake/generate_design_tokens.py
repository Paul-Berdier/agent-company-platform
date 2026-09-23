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


def theme_preamble() -> list[str]:
    return [
        "    // Thème actif. Écrit par la couche C++ (ThemeController) au démarrage et à",
        "    // chaque changement de préférence ; jamais deviné par un composant.",
        '    property string theme: "dark"',
        '    readonly property bool isDark: theme !== "light"',
        "",
    ]


# --- Générateurs par fichier --------------------------------------------------


def generate_flat_themed(stem: str, document: dict) -> str:
    """colors.json : un objet par thème, plus des accesseurs plats de type ``color``."""

    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(theme_preamble())

    for theme in ("dark", "light"):
        lines.append(f"    readonly property QtObject {theme}: QtObject {{")
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
        lines.append(
            f"    readonly property color {name}: (root.isDark ? root.dark : root.light).{name}"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_status(stem: str, document: dict) -> str:
    """semantic-status.json : couleurs par thème, métadonnées, priorité et résolution."""

    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(theme_preamble())

    for theme in ("dark", "light"):
        lines.append(f"    readonly property QtObject {theme}: QtObject {{")
        for token, payload in tokens.items():
            if theme not in payload:
                raise GenerationError(f"{stem}.{token} : valeur {theme!r} manquante")
            lines.append(
                f"        readonly property color {camel_case(token)}: "
                f"{qml_color(payload[theme], f'{stem}.{token}')}"
            )
        lines.append("    }")
        lines.append("")

    for token in tokens:
        name = camel_case(token)
        lines.append(
            f"    readonly property color {name}: (root.isDark ? root.dark : root.light).{name}"
        )
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


def generate_typography(stem: str, document: dict) -> str:
    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
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


def generate_scalar(stem: str, document: dict) -> str:
    """spacing.json et radius.json : uniquement des dimensions, un seul thème."""

    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
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
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_motion(stem: str, document: dict) -> str:
    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.append("    // Profil actif. Écrit par la couche C++ d'après la préférence système,")
    lines.append("    // ou forcé par la préférence applicative. Jamais deviné en QML.")
    lines.append('    property string profile: "standard"')
    lines.append('    readonly property bool reduced: profile === "reduced"')
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

    profiles = document.get("$profiles", {})
    for profile_name in ("standard", "reduced"):
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            raise GenerationError(f"{stem} : profil {profile_name!r} manquant")
        lines.append(f"    readonly property QtObject {profile_name}Profile: QtObject {{")
        for entry_name, entry in profile.items():
            if entry_name.startswith("$") or not isinstance(entry, dict):
                continue
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
            lines.append("        }")
        lines.append("    }")
        lines.append("")

    lines.append("    // Profil réellement appliqué par les composants.")
    lines.append("    readonly property QtObject active: root.reduced ? root.reducedProfile : root.standardProfile")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_elevation(stem: str, document: dict) -> str:
    tokens = public_tokens(document)
    lines = header(stem, document)
    lines.append("QtObject {")
    lines.append("    id: root")
    lines.append("")
    lines.extend(theme_preamble())

    for token, payload in tokens.items():
        name = camel_case(token)
        reference = f"{stem}.{token}"
        token_type = payload.get("$type")
        if token_type not in ("elevation", "scrim"):
            raise GenerationError(f"{reference} : type {token_type!r} non pris en charge")
        lines.append(f"    readonly property QtObject {name}: QtObject {{")
        for theme in ("dark", "light"):
            values = payload.get(theme)
            if not isinstance(values, dict):
                raise GenerationError(f"{reference} : valeurs {theme!r} manquantes")
        for field, kind in (
            ("offsetX", "real"),
            ("offsetY", "real"),
            ("blur", "real"),
            ("opacity", "real"),
        ):
            if field not in payload["dark"]:
                continue
            dark_value = qml_number(payload["dark"][field], reference)
            light_value = qml_number(payload["light"][field], reference)
            lines.append(
                f"        readonly property {kind} {field}: "
                f"root.isDark ? {dark_value} : {light_value}"
            )
        # Nommé shadowColor et non color : une propriété QML nommée comme son type est
        # légale mais illisible, et le nom retenu est celui de MultiEffect.
        dark_color = qml_color(payload["dark"]["color"], reference)
        light_color = qml_color(payload["light"]["color"], reference)
        lines.append(
            f"        readonly property color shadowColor: root.isDark ? {dark_color} : {light_color}"
        )
        # Les champs surface et border citent un jeton de colors.json : le générateur ne
        # les résout pas ici pour ne pas créer de dépendance circulaire entre singletons.
        # Le composant consommateur les lit comme des noms et interroge Colors.
        for field in ("surface", "border"):
            if field in payload["dark"]:
                dark_name = json.dumps(payload["dark"][field], ensure_ascii=False)
                light_name = json.dumps(payload["light"][field], ensure_ascii=False)
                lines.append(
                    f"        readonly property string {field}Token: "
                    f"root.isDark ? {dark_name} : {light_name}"
                )
        lines.append("    }")
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
    rendered: dict[str, str] = {}
    for stem, singleton in EXPECTED_SINGLETONS.items():
        document = load_tokens(tokens_dir, stem)
        rendered[f"{singleton}.qml"] = GENERATORS[stem](stem, document)
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
