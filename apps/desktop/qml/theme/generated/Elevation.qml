// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/elevation.json (version 2.0.0)
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
        readonly property QtObject elevationFlat: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.canvas"
            readonly property string borderToken: "none"
        }
        readonly property QtObject elevationPanel: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panel"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationRaised: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 1
            readonly property real blur: 3
            readonly property real opacity: 0.32
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panelRaised"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationOverlay: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 6
            readonly property real blur: 18
            readonly property real opacity: 0.52
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.interactive"
        }
        readonly property QtObject elevationDialog: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 14
            readonly property real blur: 36
            readonly property real opacity: 0.62
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.interactive"
        }
        readonly property QtObject scrimDialog: QtObject {
            readonly property real opacity: 0.58
            readonly property color shadowColor: "#05070c"
        }
        readonly property QtObject scrimInactiveWindow: QtObject {
            readonly property real opacity: 0.12
            readonly property color shadowColor: "#05070c"
        }
    }

    readonly property QtObject atelierJour: QtObject {
        readonly property bool isDark: false
        readonly property string family: "atelier"
        readonly property QtObject elevationFlat: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.canvas"
            readonly property string borderToken: "none"
        }
        readonly property QtObject elevationPanel: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panel"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationRaised: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 1
            readonly property real blur: 3
            readonly property real opacity: 0.08
            readonly property color shadowColor: "#2a2440"
            readonly property string surfaceToken: "surface.panelRaised"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationOverlay: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 6
            readonly property real blur: 18
            readonly property real opacity: 0.16
            readonly property color shadowColor: "#2a2440"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationDialog: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 14
            readonly property real blur: 36
            readonly property real opacity: 0.22
            readonly property color shadowColor: "#2a2440"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject scrimDialog: QtObject {
            readonly property real opacity: 0.34
            readonly property color shadowColor: "#1d1a2e"
        }
        readonly property QtObject scrimInactiveWindow: QtObject {
            readonly property real opacity: 0.06
            readonly property color shadowColor: "#1d1a2e"
        }
    }

    readonly property QtObject studioGraphite: QtObject {
        readonly property bool isDark: true
        readonly property string family: "studio"
        readonly property QtObject elevationFlat: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.canvas"
            readonly property string borderToken: "none"
        }
        readonly property QtObject elevationPanel: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panel"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationRaised: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 1
            readonly property real blur: 3
            readonly property real opacity: 0.32
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panelRaised"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationOverlay: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 6
            readonly property real blur: 18
            readonly property real opacity: 0.52
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.interactive"
        }
        readonly property QtObject elevationDialog: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 14
            readonly property real blur: 36
            readonly property real opacity: 0.62
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.interactive"
        }
        readonly property QtObject scrimDialog: QtObject {
            readonly property real opacity: 0.58
            readonly property color shadowColor: "#05090b"
        }
        readonly property QtObject scrimInactiveWindow: QtObject {
            readonly property real opacity: 0.12
            readonly property color shadowColor: "#05090b"
        }
    }

    readonly property QtObject studioPapier: QtObject {
        readonly property bool isDark: false
        readonly property string family: "studio"
        readonly property QtObject elevationFlat: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.canvas"
            readonly property string borderToken: "none"
        }
        readonly property QtObject elevationPanel: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 0
            readonly property real blur: 0
            readonly property real opacity: 0
            readonly property color shadowColor: "#000000"
            readonly property string surfaceToken: "surface.panel"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationRaised: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 1
            readonly property real blur: 3
            readonly property real opacity: 0.08
            readonly property color shadowColor: "#1b2c2f"
            readonly property string surfaceToken: "surface.panelRaised"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationOverlay: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 6
            readonly property real blur: 18
            readonly property real opacity: 0.16
            readonly property color shadowColor: "#1b2c2f"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject elevationDialog: QtObject {
            readonly property real offsetX: 0
            readonly property real offsetY: 14
            readonly property real blur: 36
            readonly property real opacity: 0.22
            readonly property color shadowColor: "#1b2c2f"
            readonly property string surfaceToken: "surface.overlay"
            readonly property string borderToken: "border.default"
        }
        readonly property QtObject scrimDialog: QtObject {
            readonly property real opacity: 0.34
            readonly property color shadowColor: "#0d1a1c"
        }
        readonly property QtObject scrimInactiveWindow: QtObject {
            readonly property real opacity: 0.06
            readonly property color shadowColor: "#0d1a1c"
        }
    }

    // Accesseurs plats vers le thème actif.
    readonly property QtObject elevationFlat: root.current.elevationFlat
    readonly property QtObject elevationPanel: root.current.elevationPanel
    readonly property QtObject elevationRaised: root.current.elevationRaised
    readonly property QtObject elevationOverlay: root.current.elevationOverlay
    readonly property QtObject elevationDialog: root.current.elevationDialog
    readonly property QtObject scrimDialog: root.current.scrimDialog
    readonly property QtObject scrimInactiveWindow: root.current.scrimInactiveWindow
}
