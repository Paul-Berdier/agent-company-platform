// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/colors.json (version 1.1.0)
// Palettes  : design/tokens/desktop-palettes.json
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Thème actif. Écrit par ThemeBridge au démarrage et à
    // chaque changement de préférence ; jamais deviné par un composant.
    property string theme: "dark"
    readonly property bool isDark: theme !== "light"

    property string family: "pixel"
    readonly property bool isPixel: family !== "studio"
    readonly property string familyLabel: root.isPixel ? "Pixel Atelier" : "Studio"
    readonly property string variantLabel: root.isPixel
        ? (root.isDark ? "Pixel Atelier Nuit" : "Pixel Atelier Jour")
        : (root.isDark ? "Studio Graphite" : "Studio Papier")

    readonly property QtObject pixelDark: QtObject {
        readonly property color surfaceCanvas: "#151923"
        readonly property color surfaceSidebar: "#11151e"
        readonly property color surfacePanel: "#1a202c"
        readonly property color surfacePanelRaised: "#232a39"
        readonly property color surfaceSunken: "#10141d"
        readonly property color surfaceOverlay: "#252d3c"
        readonly property color surfaceScrimless: "#0c0f16"
        readonly property color textPrimary: "#f3eee4"
        readonly property color textSecondary: "#c1c3d2"
        readonly property color textMuted: "#abb1c4"
        readonly property color textOnAccent: "#171327"
        readonly property color accentPrimary: "#a99aff"
        readonly property color accentHover: "#bcafff"
        readonly property color accentPressed: "#9d8cef"
        readonly property color accentMuted: "#2e2b48"
        readonly property color borderSubtle: "#2a3142"
        readonly property color borderDefault: "#3b4356"
        readonly property color borderInteractive: "#8791aa"
        readonly property color borderFocus: "#beb0ff"
        readonly property color stateHover: "#272e40"
        readonly property color statePressed: "#30384a"
        readonly property color stateSelected: "#343049"
        readonly property color stateDisabled: "#1f2634"
        readonly property color accentSecondary: "#7adbc3"
        readonly property color accentWarm: "#e5ba79"
        readonly property color textOnSecondary: "#122920"
        readonly property color surfaceCode: "#111620"
        readonly property color surfaceTitlebar: "#10141d"
        readonly property color surfaceActivity: "#171c28"
        readonly property color surfaceSelection: "#342f4a"
        readonly property color workspaceGrid: "#292f40"
    }

    readonly property QtObject pixelLight: QtObject {
        readonly property color surfaceCanvas: "#f7f5ef"
        readonly property color surfaceSidebar: "#efeee8"
        readonly property color surfacePanel: "#fffefa"
        readonly property color surfacePanelRaised: "#eeeff5"
        readonly property color surfaceSunken: "#e8e9f0"
        readonly property color surfaceOverlay: "#fffdf8"
        readonly property color surfaceScrimless: "#c5c5cf"
        readonly property color textPrimary: "#27283b"
        readonly property color textSecondary: "#55576b"
        readonly property color textMuted: "#595c70"
        readonly property color textOnAccent: "#ffffff"
        readonly property color accentPrimary: "#6654af"
        readonly property color accentHover: "#564398"
        readonly property color accentPressed: "#493582"
        readonly property color accentMuted: "#eae4f7"
        readonly property color borderSubtle: "#e0dee7"
        readonly property color borderDefault: "#c9c6d3"
        readonly property color borderInteractive: "#77748a"
        readonly property color borderFocus: "#6750a4"
        readonly property color stateHover: "#eae8f1"
        readonly property color statePressed: "#ddd9eb"
        readonly property color stateSelected: "#e7dff3"
        readonly property color stateDisabled: "#ebe9ef"
        readonly property color accentSecondary: "#286f61"
        readonly property color accentWarm: "#875923"
        readonly property color textOnSecondary: "#ffffff"
        readonly property color surfaceCode: "#f1f0ea"
        readonly property color surfaceTitlebar: "#f8f6f0"
        readonly property color surfaceActivity: "#f2f0ea"
        readonly property color surfaceSelection: "#e7dff3"
        readonly property color workspaceGrid: "#dedce5"
    }

    readonly property QtObject studioDark: QtObject {
        readonly property color surfaceCanvas: "#191c1a"
        readonly property color surfaceSidebar: "#131714"
        readonly property color surfacePanel: "#1e2420"
        readonly property color surfacePanelRaised: "#272e29"
        readonly property color surfaceSunken: "#111612"
        readonly property color surfaceOverlay: "#282f2a"
        readonly property color surfaceScrimless: "#090d0a"
        readonly property color textPrimary: "#eef2e9"
        readonly property color textSecondary: "#b1bcb2"
        readonly property color textMuted: "#a1afa3"
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
        readonly property color accentSecondary: "#b1b8dd"
        readonly property color accentWarm: "#dcb67d"
        readonly property color textOnSecondary: "#202333"
        readonly property color surfaceCode: "#111612"
        readonly property color surfaceTitlebar: "#101410"
        readonly property color surfaceActivity: "#191f1a"
        readonly property color surfaceSelection: "#2b4435"
        readonly property color workspaceGrid: "#2b332d"
    }

    readonly property QtObject studioLight: QtObject {
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
        readonly property color accentSecondary: "#566088"
        readonly property color accentWarm: "#805620"
        readonly property color textOnSecondary: "#ffffff"
        readonly property color surfaceCode: "#f0f0e9"
        readonly property color surfaceTitlebar: "#f8f7f1"
        readonly property color surfaceActivity: "#f0f1ea"
        readonly property color surfaceSelection: "#dceadb"
        readonly property color workspaceGrid: "#dde1d5"
    }

    readonly property QtObject dark: root.isPixel ? root.pixelDark : root.studioDark
    readonly property QtObject light: root.isPixel ? root.pixelLight : root.studioLight

    // Accesseurs plats : un composant ne choisit jamais son thème lui-même.
    readonly property color surfaceCanvas: (root.isDark ? root.dark : root.light).surfaceCanvas
    readonly property color surfaceSidebar: (root.isDark ? root.dark : root.light).surfaceSidebar
    readonly property color surfacePanel: (root.isDark ? root.dark : root.light).surfacePanel
    readonly property color surfacePanelRaised: (root.isDark ? root.dark : root.light).surfacePanelRaised
    readonly property color surfaceSunken: (root.isDark ? root.dark : root.light).surfaceSunken
    readonly property color surfaceOverlay: (root.isDark ? root.dark : root.light).surfaceOverlay
    readonly property color surfaceScrimless: (root.isDark ? root.dark : root.light).surfaceScrimless
    readonly property color textPrimary: (root.isDark ? root.dark : root.light).textPrimary
    readonly property color textSecondary: (root.isDark ? root.dark : root.light).textSecondary
    readonly property color textMuted: (root.isDark ? root.dark : root.light).textMuted
    readonly property color textOnAccent: (root.isDark ? root.dark : root.light).textOnAccent
    readonly property color accentPrimary: (root.isDark ? root.dark : root.light).accentPrimary
    readonly property color accentHover: (root.isDark ? root.dark : root.light).accentHover
    readonly property color accentPressed: (root.isDark ? root.dark : root.light).accentPressed
    readonly property color accentMuted: (root.isDark ? root.dark : root.light).accentMuted
    readonly property color borderSubtle: (root.isDark ? root.dark : root.light).borderSubtle
    readonly property color borderDefault: (root.isDark ? root.dark : root.light).borderDefault
    readonly property color borderInteractive: (root.isDark ? root.dark : root.light).borderInteractive
    readonly property color borderFocus: (root.isDark ? root.dark : root.light).borderFocus
    readonly property color stateHover: (root.isDark ? root.dark : root.light).stateHover
    readonly property color statePressed: (root.isDark ? root.dark : root.light).statePressed
    readonly property color stateSelected: (root.isDark ? root.dark : root.light).stateSelected
    readonly property color stateDisabled: (root.isDark ? root.dark : root.light).stateDisabled
    readonly property color accentSecondary: (root.isDark ? root.dark : root.light).accentSecondary
    readonly property color accentWarm: (root.isDark ? root.dark : root.light).accentWarm
    readonly property color textOnSecondary: (root.isDark ? root.dark : root.light).textOnSecondary
    readonly property color surfaceCode: (root.isDark ? root.dark : root.light).surfaceCode
    readonly property color surfaceTitlebar: (root.isDark ? root.dark : root.light).surfaceTitlebar
    readonly property color surfaceActivity: (root.isDark ? root.dark : root.light).surfaceActivity
    readonly property color surfaceSelection: (root.isDark ? root.dark : root.light).surfaceSelection
    readonly property color workspaceGrid: (root.isDark ? root.dark : root.light).workspaceGrid
}
