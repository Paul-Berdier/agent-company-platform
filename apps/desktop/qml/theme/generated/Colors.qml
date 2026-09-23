// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/colors.json (version 1.1.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Thème actif. Écrit par la couche C++ (ThemeController) au démarrage et à
    // chaque changement de préférence ; jamais deviné par un composant.
    property string theme: "dark"
    readonly property bool isDark: theme !== "light"

    readonly property QtObject dark: QtObject {
        readonly property color surfaceCanvas: "#191c1a"
        readonly property color surfaceSidebar: "#131714"
        readonly property color surfacePanel: "#1e2420"
        readonly property color surfacePanelRaised: "#272e29"
        readonly property color surfaceSunken: "#111612"
        readonly property color surfaceOverlay: "#282f2a"
        readonly property color surfaceScrimless: "#090d0a"
        readonly property color textPrimary: "#eef2e9"
        readonly property color textSecondary: "#b1bcb2"
        readonly property color textMuted: "#9aaa9d"
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
    }

    readonly property QtObject light: QtObject {
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
    }

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
}
