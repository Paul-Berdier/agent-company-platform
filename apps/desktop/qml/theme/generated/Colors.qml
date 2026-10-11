// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/colors.json (version 2.0.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Thème actif. Écrit par ThemeBridge (Acp.Theme) d'après la préférence lue par la
    // couche C++ (SystemAppearance) ; jamais deviné par un composant.
    property string theme: "atelier-nuit"
    readonly property var themes: ["atelier-nuit", "atelier-jour", "studio-graphite", "studio-papier"]
    // Faux si `theme` n'est pas un thème généré : le thème par défaut s'applique alors.
    readonly property bool known: root.themes.indexOf(root.theme) >= 0
    readonly property QtObject current: root.theme === "atelier-jour" ? root.atelierJour : root.theme === "studio-graphite" ? root.studioGraphite : root.theme === "studio-papier" ? root.studioPapier : root.atelierNuit
    readonly property bool isDark: root.current.isDark
    readonly property string family: root.current.family

    readonly property QtObject atelierNuit: QtObject {
        readonly property bool isDark: true
        readonly property string family: "atelier"
        readonly property color surfaceCanvas: "#151923"
        readonly property color surfaceSidebar: "#10131b"
        readonly property color surfacePanel: "#1a1f2d"
        readonly property color surfacePanelRaised: "#222839"
        readonly property color surfaceSunken: "#0e1119"
        readonly property color surfaceOverlay: "#252b3e"
        readonly property color surfaceScrimless: "#07090e"
        readonly property color textPrimary: "#f2ede4"
        readonly property color textSecondary: "#c3bfd3"
        readonly property color textMuted: "#a6a2bd"
        readonly property color textOnAccent: "#16122c"
        readonly property color accentPrimary: "#a99aff"
        readonly property color accentHover: "#c0b4ff"
        readonly property color accentPressed: "#9584f5"
        readonly property color accentMuted: "#2c2a4c"
        readonly property color borderSubtle: "#252b3c"
        readonly property color borderDefault: "#333a52"
        readonly property color borderInteractive: "#7f82a8"
        readonly property color borderFocus: "#7adbc3"
        readonly property color stateHover: "#222839"
        readonly property color statePressed: "#2b3249"
        readonly property color stateSelected: "#302d58"
        readonly property color stateDisabled: "#1a1e2a"
        readonly property color accentSecondary: "#7adbc3"
        readonly property color accentSecondaryMuted: "#1c3a3a"
        readonly property color decorGrid: "#1a1f2b"
        readonly property color decorOutline: "#07090e"
    }

    readonly property QtObject atelierJour: QtObject {
        readonly property bool isDark: false
        readonly property string family: "atelier"
        readonly property color surfaceCanvas: "#f6f2ea"
        readonly property color surfaceSidebar: "#eee9f4"
        readonly property color surfacePanel: "#fffdf8"
        readonly property color surfacePanelRaised: "#f3eef8"
        readonly property color surfaceSunken: "#ebe6f0"
        readonly property color surfaceOverlay: "#fffefb"
        readonly property color surfaceScrimless: "#cfc8da"
        readonly property color textPrimary: "#1d1a2e"
        readonly property color textSecondary: "#4a4563"
        readonly property color textMuted: "#5a5676"
        readonly property color textOnAccent: "#ffffff"
        readonly property color accentPrimary: "#5b47d6"
        readonly property color accentHover: "#4a36c2"
        readonly property color accentPressed: "#3d2aa6"
        readonly property color accentMuted: "#e7e2fc"
        readonly property color borderSubtle: "#e4deeb"
        readonly property color borderDefault: "#d2cade"
        readonly property color borderInteractive: "#7b7499"
        readonly property color borderFocus: "#0d7660"
        readonly property color stateHover: "#eee9f4"
        readonly property color statePressed: "#e4ddef"
        readonly property color stateSelected: "#e6e0fc"
        readonly property color stateDisabled: "#ece9f0"
        readonly property color accentSecondary: "#0d7660"
        readonly property color accentSecondaryMuted: "#dcf1ea"
        readonly property color decorGrid: "#ece6dc"
        readonly property color decorOutline: "#2a2540"
    }

    readonly property QtObject studioGraphite: QtObject {
        readonly property bool isDark: true
        readonly property string family: "studio"
        readonly property color surfaceCanvas: "#191c1a"
        readonly property color surfaceSidebar: "#131714"
        readonly property color surfacePanel: "#1e2420"
        readonly property color surfacePanelRaised: "#272e29"
        readonly property color surfaceSunken: "#111612"
        readonly property color surfaceOverlay: "#282f2a"
        readonly property color surfaceScrimless: "#090d0a"
        readonly property color textPrimary: "#eef2e9"
        readonly property color textSecondary: "#b1bcb2"
        readonly property color textMuted: "#a3b2a5"
        readonly property color textOnAccent: "#07271c"
        readonly property color accentPrimary: "#65c6ae"
        readonly property color accentHover: "#86dcc5"
        readonly property color accentPressed: "#4eb298"
        readonly property color accentMuted: "#233e32"
        readonly property color borderSubtle: "#2b332d"
        readonly property color borderDefault: "#3a453c"
        readonly property color borderInteractive: "#7e8e80"
        readonly property color borderFocus: "#95e4c9"
        readonly property color stateHover: "#2b332d"
        readonly property color statePressed: "#343f36"
        readonly property color stateSelected: "#2b4435"
        readonly property color stateDisabled: "#202722"
        readonly property color accentSecondary: "#a9b9c6"
        readonly property color accentSecondaryMuted: "#26302f"
        readonly property color decorGrid: "#1c201d"
        readonly property color decorOutline: "#090d0a"
    }

    readonly property QtObject studioPapier: QtObject {
        readonly property bool isDark: false
        readonly property string family: "studio"
        readonly property color surfaceCanvas: "#f7f6f0"
        readonly property color surfaceSidebar: "#eeefe7"
        readonly property color surfacePanel: "#ffffff"
        readonly property color surfacePanelRaised: "#f2f3eb"
        readonly property color surfaceSunken: "#e8ebe2"
        readonly property color surfaceOverlay: "#fffef8"
        readonly property color surfaceScrimless: "#c9cfc3"
        readonly property color textPrimary: "#1f2b23"
        readonly property color textSecondary: "#506154"
        readonly property color textMuted: "#536657"
        readonly property color textOnAccent: "#ffffff"
        readonly property color accentPrimary: "#0a6d60"
        readonly property color accentHover: "#085748"
        readonly property color accentPressed: "#064637"
        readonly property color accentMuted: "#e0ede4"
        readonly property color borderSubtle: "#dfe3d7"
        readonly property color borderDefault: "#cdd5c7"
        readonly property color borderInteractive: "#748771"
        readonly property color borderFocus: "#0a6654"
        readonly property color stateHover: "#e6ebdf"
        readonly property color statePressed: "#dce4d4"
        readonly property color stateSelected: "#dceadb"
        readonly property color stateDisabled: "#e5e9df"
        readonly property color accentSecondary: "#3c5a70"
        readonly property color accentSecondaryMuted: "#e3e9ec"
        readonly property color decorGrid: "#efeee6"
        readonly property color decorOutline: "#1f2b23"
    }

    // Accesseurs plats : un composant ne choisit jamais son thème lui-même.
    readonly property color surfaceCanvas: root.current.surfaceCanvas
    readonly property color surfaceSidebar: root.current.surfaceSidebar
    readonly property color surfacePanel: root.current.surfacePanel
    readonly property color surfacePanelRaised: root.current.surfacePanelRaised
    readonly property color surfaceSunken: root.current.surfaceSunken
    readonly property color surfaceOverlay: root.current.surfaceOverlay
    readonly property color surfaceScrimless: root.current.surfaceScrimless
    readonly property color textPrimary: root.current.textPrimary
    readonly property color textSecondary: root.current.textSecondary
    readonly property color textMuted: root.current.textMuted
    readonly property color textOnAccent: root.current.textOnAccent
    readonly property color accentPrimary: root.current.accentPrimary
    readonly property color accentHover: root.current.accentHover
    readonly property color accentPressed: root.current.accentPressed
    readonly property color accentMuted: root.current.accentMuted
    readonly property color borderSubtle: root.current.borderSubtle
    readonly property color borderDefault: root.current.borderDefault
    readonly property color borderInteractive: root.current.borderInteractive
    readonly property color borderFocus: root.current.borderFocus
    readonly property color stateHover: root.current.stateHover
    readonly property color statePressed: root.current.statePressed
    readonly property color stateSelected: root.current.stateSelected
    readonly property color stateDisabled: root.current.stateDisabled
    readonly property color accentSecondary: root.current.accentSecondary
    readonly property color accentSecondaryMuted: root.current.accentSecondaryMuted
    readonly property color decorGrid: root.current.decorGrid
    readonly property color decorOutline: root.current.decorOutline

    // Libellés français des thèmes et des familles, pour les réglages et le diagnostic.
    readonly property var themeLabels: ({"atelier-nuit": "Pixel Atelier — Nuit", "atelier-jour": "Pixel Atelier — Jour", "studio-graphite": "Studio — Graphite", "studio-papier": "Studio — Papier"})
    readonly property var families: ({"atelier": {"label": "Pixel Atelier", "sombre": "atelier-nuit", "clair": "atelier-jour"}, "studio": {"label": "Studio", "sombre": "studio-graphite", "clair": "studio-papier"}})
}
