// Ligne « libellé : valeur » d'un écran de diagnostics.
//
// Une valeur jamais mesurée est affichée en text.muted et accompagnée d'une pastille
// « Inconnu » : elle n'est jamais présentée comme un fait.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design

Item {
    id: row

    property string label: ""
    property string value: ""
    property bool known: true
    property bool monospace: false

    implicitHeight: Space.densityRowHeightRegular

    Rectangle {
        anchors.fill: parent
        color: hover.hovered ? Colors.stateHover : "transparent"
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: Space.layoutBorderWidth
        color: Colors.borderSubtle
    }

    Text {
        id: labelText
        anchors.left: parent.left
        anchors.leftMargin: Space.space4
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(row.width * 0.4, 320)
        text: row.label
        elide: Text.ElideRight
        color: Colors.textSecondary
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    Text {
        anchors.left: labelText.right
        anchors.leftMargin: Space.space5
        anchors.right: parent.right
        anchors.rightMargin: Space.space4
        anchors.verticalCenter: parent.verticalCenter
        text: row.value
        elide: Text.ElideRight
        color: row.known ? Colors.textPrimary : Colors.textMuted
        // Chasse fixe obligatoire pour tout identifiant, chemin, durée, version : c'est
        // ce qui rend une valeur copiable et comparable du regard.
        font.family: row.monospace ? Type.identifier.family : Type.tableCell.family
        font.pixelSize: row.monospace ? Type.identifier.pixelSize : Type.tableCell.pixelSize

        ToolTip.visible: hover.hovered && row.value.length > 60
        ToolTip.text: row.value
        ToolTip.delay: 500
    }

    HoverHandler { id: hover }
}
