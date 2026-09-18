// Barre inférieure permanente : runs, connexion, alertes.
//
// Le hors ligne vit ici, en permanence, avec l'horodatage du dernier échange réussi.
// Aucune donnée de démonstration ne comble un trou : un compteur sans échantillon affiche
// « Inconnu ».

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime

Rectangle {
    id: statusBar

    color: Palette.surfaceSidebar

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: Space.layoutBorderWidth
        color: Palette.borderDefault
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Space.space4
        anchors.rightMargin: Space.space4
        spacing: Space.space5

        Text {
            // Runs actifs : aucune route consommée ici ne les compte. On l'écrit.
            text: qsTr("Runs actifs : Inconnu")
            color: Palette.textMuted
            font.families: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        Text {
            text: qsTr("Alertes : Inconnu")
            color: Palette.textMuted
            font.families: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        Item { Layout.fillWidth: true }

        Text {
            Layout.maximumWidth: statusBar.width * 0.45
            text: Shell.lastNotice
            visible: Shell.lastNotice.length > 0
            elide: Text.ElideRight
            color: Palette.textSecondary
            font.families: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize

            ToolTip.visible: noticeHover.hovered && Shell.lastNotice.length > 0
            ToolTip.text: Shell.lastNotice
            HoverHandler { id: noticeHover }
        }

        Text {
            text: Shell.statusSummary
            color: Palette.textMuted
            font.families: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
            elide: Text.ElideLeft
            Layout.maximumWidth: statusBar.width * 0.5
        }
    }
}
