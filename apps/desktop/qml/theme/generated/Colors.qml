// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/colors.json (version 1.0.0)
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
        readonly property color surfaceCanvas: "#0e1417"
        readonly property color surfaceSidebar: "#111a1e"
        readonly property color surfacePanel: "#172126"
        readonly property color surfacePanelRaised: "#1c292f"
        readonly property color surfaceSunken: "#0a1013"
        readonly property color surfaceOverlay: "#1f2c32"
        readonly property color surfaceScrimless: "#060a0c"
        readonly property color textPrimary: "#edf4f4"
        readonly property color textSecondary: "#a8b7bb"
        readonly property color textMuted: "#8b9ca1"
        readonly property color textOnAccent: "#04221f"
        readonly property color accentPrimary: "#38b9b0"
        readonly property color accentHover: "#63d7ce"
        readonly property color accentPressed: "#2aa39b"
        readonly property color accentMuted: "#1c3639"
        readonly property color borderSubtle: "#232f34"
        readonly property color borderDefault: "#2d3c42"
        readonly property color borderInteractive: "#5c7178"
        readonly property color borderFocus: "#8be9e1"
        readonly property color stateHover: "#242e32"
        readonly property color statePressed: "#2f383d"
        readonly property color stateSelected: "#214f4f"
        readonly property color stateDisabled: "#1a2328"
    }

    readonly property QtObject light: QtObject {
        readonly property color surfaceCanvas: "#eef3f2"
        readonly property color surfaceSidebar: "#f8fbfa"
        readonly property color surfacePanel: "#ffffff"
        readonly property color surfacePanelRaised: "#f4f8f7"
        readonly property color surfaceSunken: "#e4ebe9"
        readonly property color surfaceOverlay: "#ffffff"
        readonly property color surfaceScrimless: "#c4cfcd"
        readonly property color textPrimary: "#152326"
        readonly property color textSecondary: "#4d5f62"
        readonly property color textMuted: "#57696d"
        readonly property color textOnAccent: "#ffffff"
        readonly property color accentPrimary: "#0a6d68"
        readonly property color accentHover: "#075550"
        readonly property color accentPressed: "#05423e"
        readonly property color accentMuted: "#e6f0f0"
        readonly property color borderSubtle: "#dfe7e5"
        readonly property color borderDefault: "#ccd9d7"
        readonly property color borderInteractive: "#7c8f8c"
        readonly property color borderFocus: "#075e5a"
        readonly property color stateHover: "#f3f4f4"
        readonly property color statePressed: "#e8e9e9"
        readonly property color stateSelected: "#cee2e1"
        readonly property color stateDisabled: "#eaefee"
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
