// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/spacing.json (version 1.2.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root
    readonly property real space0: 0
    readonly property real space1: 2
    readonly property real space2: 4
    readonly property real space3: 6
    readonly property real space4: 8
    readonly property real space5: 12
    readonly property real space6: 16
    readonly property real space7: 20
    readonly property real space8: 24
    readonly property real space9: 32
    readonly property real space10: 48
    readonly property real densityRowHeightCompact: 24
    readonly property real densityRowHeightRegular: 28
    readonly property real densityRowHeightComfortable: 36
    readonly property real densityControlHeightSmall: 24
    readonly property real densityControlHeightRegular: 32
    readonly property real densityControlHeightLarge: 40
    readonly property real densityHitTargetMinimum: 32
    readonly property real densityIconSizeSmall: 14
    readonly property real densityIconSizeRegular: 16
    readonly property real densityIconSizeLarge: 20
    readonly property real layoutSidebarWidth: 256
    readonly property real layoutSidebarCollapsedWidth: 48
    readonly property real layoutInspectorWidthMin: 320
    readonly property real layoutInspectorWidthDefault: 380
    readonly property real layoutContentMaxWidth: 1080
    readonly property real layoutTopBarHeight: 52
    readonly property real layoutStatusBarHeight: 24
    readonly property real layoutWindowMinWidth: 960
    readonly property real layoutWindowMinHeight: 600
    readonly property real layoutPaneGap: 1
    readonly property real layoutFocusRingWidth: 2
    readonly property real layoutFocusRingOffset: 2
    readonly property real layoutBorderWidth: 1
    readonly property real layoutSidebarWidthMin: 220
    readonly property real layoutSidebarWidthMax: 420
    readonly property real layoutAgentsPanelWidthMin: 260
    readonly property real layoutAgentsPanelWidthDefault: 320
    readonly property real layoutAgentsPanelWidthMax: 560
    readonly property real layoutBottomDrawerHeightMin: 120
    readonly property real layoutBottomDrawerHeightDefault: 220
    readonly property real layoutBottomDrawerHeightMax: 520
    readonly property real layoutComposerHeightMin: 96
    readonly property real layoutComposerHeightMax: 320
    readonly property real layoutCenterMinWidth: 420
    readonly property real layoutPixelUnit: 2

    // Seuils de largeur de fenêtre, pas des tailles d'appareil.
    readonly property real breakpointNarrow: 960
    readonly property real breakpointRegular: 1280
    readonly property real breakpointWide: 1680

    // Densité choisie par l'opérateur ; écrite par ThemeBridge.
    property string density: "standard"
    readonly property var densities: ["compacte", "standard", "aeree"]
    readonly property var densityLabels: ({"compacte": "Compacte", "standard": "Standard", "aeree": "Aérée"})
    readonly property real rowHeight: root.density === "compacte" ? root.densityRowHeightCompact : root.density === "aeree" ? root.densityRowHeightComfortable : root.densityRowHeightRegular
    readonly property real controlHeight: root.density === "compacte" ? root.densityControlHeightRegular : root.density === "aeree" ? root.densityControlHeightLarge : root.densityControlHeightRegular
}
