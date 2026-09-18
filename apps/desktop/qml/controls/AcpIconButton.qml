// Bouton compact à glyphe.
//
// Le jeu d'icônes n'est PAS choisi : les jetons de statut déclarent explicitement
// `$iconSet.resolved: false`. Ce contrôle affiche donc un caractère, pas une ressource
// graphique, et l'infobulle porte toujours le libellé — la forme seule ne suffit jamais.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design

Item {
    id: control

    property string glyph: "·"
    property string tooltip: ""
    property bool manualEnabled: true

    signal triggered()

    implicitWidth: Space.densityControlHeightRegular
    implicitHeight: Space.densityControlHeightRegular
    activeFocusOnTab: true

    Rectangle {
        anchors.fill: parent
        radius: Radius.radiusSm
        color: !control.manualEnabled
            ? "transparent"
            : (tap.pressed ? Palette.statePressed
                : (hover.hovered ? Palette.stateHover : "transparent"))
    }

    Text {
        anchors.centerIn: parent
        text: control.glyph
        color: control.manualEnabled ? Palette.textSecondary : Palette.textMuted
        font.families: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    Item {
        anchors.centerIn: parent
        width: Space.densityHitTargetMinimum
        height: Space.densityHitTargetMinimum

        HoverHandler {
            id: hover
            cursorShape: control.manualEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        }
        TapHandler {
            id: tap
            onTapped: if (control.manualEnabled) control.triggered()
        }
    }

    Rectangle {
        visible: control.activeFocus
        anchors.fill: parent
        anchors.margins: -Space.layoutFocusRingOffset
        color: "transparent"
        radius: Radius.radiusSm
        border.width: Space.layoutFocusRingWidth
        border.color: Palette.borderFocus
    }

    ToolTip.visible: hover.hovered && control.tooltip.length > 0
    ToolTip.text: control.tooltip
    ToolTip.delay: 400

    Keys.onReturnPressed: if (control.manualEnabled) control.triggered()
    Keys.onSpacePressed: if (control.manualEnabled) control.triggered()
}
