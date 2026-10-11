// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/typography.json (version 1.1.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Taille du texte choisie par l'opérateur, en pour cent ; écrite par ThemeBridge.
    property int textScale: 100
    readonly property var textScales: [100, 112, 125, 140]
    readonly property real scale: root.textScale / 100

    readonly property var familyInterface: ["Inter", "Inter Variable", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Noto Sans", "DejaVu Sans"]
    readonly property string familyInterfaceResolved: root.firstInstalled(familyInterface)
    readonly property var familyMono: ["Cascadia Code", "Cascadia Mono", "JetBrains Mono", "SF Mono", "SFMono-Regular", "Consolas", "DejaVu Sans Mono"]
    readonly property string familyMonoResolved: root.firstInstalled(familyMono)
    readonly property real sizeMicro: 11
    readonly property real sizeSmall: 12
    readonly property real sizeBody: 14
    readonly property real sizeSubtitle: 14
    readonly property real sizeTitle: 16
    readonly property real sizeSectionTitle: 20
    readonly property real sizeDisplay: 26
    readonly property real sizeMonoSmall: 11
    readonly property real sizeMono: 12
    readonly property real lineHeightMicro: 14
    readonly property real lineHeightSmall: 16
    readonly property real lineHeightBody: 20
    readonly property real lineHeightSubtitle: 20
    readonly property real lineHeightTitle: 22
    readonly property real lineHeightSectionTitle: 26
    readonly property real lineHeightDisplay: 32
    readonly property real lineHeightMono: 17
    readonly property real lineHeightProse: 24
    readonly property real weightRegular: 400
    readonly property real weightMedium: 500
    readonly property real weightSemibold: 600
    readonly property real weightBold: 700
    readonly property real letterSpacingTight: -0.2
    readonly property real letterSpacingNormal: 0
    readonly property real letterSpacingWide: 0.4
    readonly property real measureProse: 680

    function firstInstalled(stack) {
        var installed = Qt.fontFamilies();
        for (var i = 0; i < stack.length; ++i) {
            if (installed.indexOf(stack[i]) >= 0)
                return stack[i];
        }
        return "";
    }

    // Rôles prêts à l'emploi : un écran consomme un rôle, il n'en compose pas.
    // La taille et la hauteur de ligne suivent textScale, à chaud.
    readonly property QtObject pageTitle: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeSectionTitle * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightSectionTitle * root.scale)
        readonly property int weight: root.weightBold
        readonly property real letterSpacing: root.letterSpacingTight
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject panelTitle: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeSubtitle * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightSubtitle * root.scale)
        readonly property int weight: root.weightSemibold
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject objectTitle: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeTitle * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightTitle * root.scale)
        readonly property int weight: root.weightSemibold
        readonly property real letterSpacing: root.letterSpacingTight
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject columnHeader: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeMicro * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightMicro * root.scale)
        readonly property int weight: root.weightSemibold
        readonly property real letterSpacing: root.letterSpacingWide
        readonly property int capitalization: Font.AllUppercase
    }
    readonly property QtObject tableCell: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeBody * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightBody * root.scale)
        readonly property int weight: root.weightRegular
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject tableCellEmphasis: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeBody * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightBody * root.scale)
        readonly property int weight: root.weightMedium
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject metadata: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeSmall * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightSmall * root.scale)
        readonly property int weight: root.weightRegular
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject statusChip: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeMicro * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightMicro * root.scale)
        readonly property int weight: root.weightSemibold
        readonly property real letterSpacing: root.letterSpacingWide
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject buttonLabel: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeBody * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightBody * root.scale)
        readonly property int weight: root.weightMedium
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject prose: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeBody * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightProse * root.scale)
        readonly property int weight: root.weightRegular
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject identifier: QtObject {
        readonly property string family: root.familyMonoResolved
        readonly property int pixelSize: Math.round(root.sizeMono * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightMono * root.scale)
        readonly property int weight: root.weightRegular
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject logLine: QtObject {
        readonly property string family: root.familyMonoResolved
        readonly property int pixelSize: Math.round(root.sizeMonoSmall * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightMono * root.scale)
        readonly property int weight: root.weightRegular
        readonly property real letterSpacing: root.letterSpacingNormal
        readonly property int capitalization: Font.MixedCase
    }
    readonly property QtObject emptyStateTitle: QtObject {
        readonly property string family: root.familyInterfaceResolved
        readonly property int pixelSize: Math.round(root.sizeDisplay * root.scale)
        readonly property real lineHeight: Math.round(root.lineHeightDisplay * root.scale)
        readonly property int weight: root.weightSemibold
        readonly property real letterSpacing: root.letterSpacingTight
        readonly property int capitalization: Font.MixedCase
    }
}
