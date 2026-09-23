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
            : (tap.pressed ? Colors.statePressed
                : (hover.hovered ? Colors.stateHover : "transparent"))
    }

    Text {
        textFormat: Text.PlainText
        anchors.centerIn: parent
        text: control.glyph
        color: control.manualEnabled ? Colors.textSecondary : Colors.textMuted
        font.family: Type.tableCell.family
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
        border.color: Colors.borderFocus
    }

    // Un glyphe n'est pas un nom : l'infobulle sert de nom accessible.
    Accessible.role: Accessible.Button
    Accessible.name: control.tooltip
    Accessible.focusable: true
    Accessible.onPressAction: if (control.manualEnabled) control.triggered()

    ToolTip {
        id: plainTip
        visible: hover.hovered && control.tooltip.length > 0
        text: control.tooltip
        contentItem: Text { text: plainTip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
        delay: 400
    }

    Keys.onReturnPressed: if (control.manualEnabled) control.triggered()
    Keys.onSpacePressed: if (control.manualEnabled) control.triggered()
}
