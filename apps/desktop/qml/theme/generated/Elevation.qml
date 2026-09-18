// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/elevation.json (version 1.0.0)
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

    readonly property QtObject elevationFlat: QtObject {
        readonly property real offsetX: root.isDark ? 0 : 0
        readonly property real offsetY: root.isDark ? 0 : 0
        readonly property real blur: root.isDark ? 0 : 0
        readonly property real opacity: root.isDark ? 0 : 0
        readonly property color shadowColor: root.isDark ? "#000000" : "#000000"
        readonly property string surfaceToken: root.isDark ? "surface.canvas" : "surface.canvas"
        readonly property string borderToken: root.isDark ? "none" : "none"
    }
    readonly property QtObject elevationPanel: QtObject {
        readonly property real offsetX: root.isDark ? 0 : 0
        readonly property real offsetY: root.isDark ? 0 : 0
        readonly property real blur: root.isDark ? 0 : 0
        readonly property real opacity: root.isDark ? 0 : 0
        readonly property color shadowColor: root.isDark ? "#000000" : "#000000"
        readonly property string surfaceToken: root.isDark ? "surface.panel" : "surface.panel"
        readonly property string borderToken: root.isDark ? "border.default" : "border.default"
    }
    readonly property QtObject elevationRaised: QtObject {
        readonly property real offsetX: root.isDark ? 0 : 0
        readonly property real offsetY: root.isDark ? 1 : 1
        readonly property real blur: root.isDark ? 3 : 3
        readonly property real opacity: root.isDark ? 0.32 : 0.08
        readonly property color shadowColor: root.isDark ? "#000000" : "#1b2c2f"
        readonly property string surfaceToken: root.isDark ? "surface.panelRaised" : "surface.panelRaised"
        readonly property string borderToken: root.isDark ? "border.default" : "border.default"
    }
    readonly property QtObject elevationOverlay: QtObject {
        readonly property real offsetX: root.isDark ? 0 : 0
        readonly property real offsetY: root.isDark ? 6 : 6
        readonly property real blur: root.isDark ? 18 : 18
        readonly property real opacity: root.isDark ? 0.52 : 0.16
        readonly property color shadowColor: root.isDark ? "#000000" : "#1b2c2f"
        readonly property string surfaceToken: root.isDark ? "surface.overlay" : "surface.overlay"
        readonly property string borderToken: root.isDark ? "border.interactive" : "border.default"
    }
    readonly property QtObject elevationDialog: QtObject {
        readonly property real offsetX: root.isDark ? 0 : 0
        readonly property real offsetY: root.isDark ? 14 : 14
        readonly property real blur: root.isDark ? 36 : 36
        readonly property real opacity: root.isDark ? 0.62 : 0.22
        readonly property color shadowColor: root.isDark ? "#000000" : "#1b2c2f"
        readonly property string surfaceToken: root.isDark ? "surface.overlay" : "surface.overlay"
        readonly property string borderToken: root.isDark ? "border.interactive" : "border.default"
    }
    readonly property QtObject scrimDialog: QtObject {
        readonly property real opacity: root.isDark ? 0.58 : 0.34
        readonly property color shadowColor: root.isDark ? "#05090b" : "#0d1a1c"
    }
    readonly property QtObject scrimInactiveWindow: QtObject {
        readonly property real opacity: root.isDark ? 0.12 : 0.06
        readonly property color shadowColor: root.isDark ? "#05090b" : "#0d1a1c"
    }
}
