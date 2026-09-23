// Barre supérieure : espace de travail, recherche, commandes, état, utilisateur.
//
// Chaque zone affiche un FAIT. « Non configuré » et « Non connecté » sont des valeurs
// légitimes ; aucune n'est remplacée par un libellé rassurant.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Rectangle {
    id: bar

    color: Colors.surfaceSidebar

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: Space.layoutBorderWidth
        color: Colors.borderDefault
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Space.space4
        anchors.rightMargin: Space.space4
        spacing: Space.space5

        AcpIconButton {
            glyph: Shell.sidebarCollapsed ? "»" : "«"
            tooltip: Shell.sidebarCollapsed
                ? qsTr("Déplier la navigation")
                : qsTr("Replier la navigation")
            onTriggered: Shell.sidebarCollapsed = !Shell.sidebarCollapsed
        }

        AcpButton {
            label: Workspace.projectName || qsTr("Choisir un projet")
            Layout.maximumWidth: 260
            onTriggered: Navigation.setCurrentRoute("projects")
        }

        Text {
            textFormat: Text.PlainText
            text: Shell.serverUrlLabel
            color: Shell.serverUrl.length === 0
                ? Status.statusNotConfiguredForeground
                : Colors.textMuted
            font.family: Type.identifier.family
            font.pixelSize: Type.identifier.pixelSize
            elide: Text.ElideMiddle
            Layout.maximumWidth: 320
        }

        Item { Layout.fillWidth: true }

        AcpButton {
            label: qsTr("Commandes")
            shortcutHint: "Ctrl+K"
            commandId: "palette.open"
        }

        StatusChip {
            statusKey: Health.linkStatus === LinkStatus.Online ? "succeeded"
                : Health.linkStatus === LinkStatus.Degraded ? "degraded"
                : Health.linkStatus === LinkStatus.Offline ? "offline"
                : Health.linkStatus === LinkStatus.Probing ? "running"
                : "unknown"
            label: Health.linkStatusLabel
            detail: Health.detail
        }

        Text {
            textFormat: Text.PlainText
            text: Session.userDisplayName.length > 0
                ? Session.userDisplayName
                : qsTr("Non connecté")
            color: Colors.textSecondary
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
    }
}
