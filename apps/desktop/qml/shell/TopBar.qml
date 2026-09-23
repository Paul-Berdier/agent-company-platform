// Le titre décrit le contexte visible, jamais un ancien projet sélectionné.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Rectangle {
    id: bar
    property bool inspectorAvailable: false
    property bool navigationCompact: false
    signal toggleNavigation()
    color: Colors.surfaceCanvas
    readonly property bool conversation: Navigation.currentRoute === "conversations"
    readonly property string contextLabel: conversation
        ? (Conversations.projectId.length === 0 ? qsTr("Conversation générale")
            : (Conversations.projectId === Workspace.projectId ? Workspace.projectName : qsTr("Conversation de projet")))
        : (["missions", "studio", "library", "approvals", "platform", "extensions"].indexOf(Navigation.currentRoute) >= 0
            ? Workspace.projectName || qsTr("Aucun projet sélectionné") : "")
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Space.space4
        anchors.rightMargin: Space.space4
        spacing: Space.space3
        AcpButton {
            objectName: "shell-toggle-navigation"
            label: ""; iconName: bar.navigationCompact ? "chevronRight" : "chevronLeft"
            Accessible.name: bar.navigationCompact ? qsTr("Déplier la navigation") : qsTr("Replier la navigation")
            onTriggered: bar.toggleNavigation()
        }
        AcpButton {
            objectName: "shell-back"
            label: ""; iconName: "chevronLeft"
            Accessible.name: qsTr("Écran précédent · Alt+gauche")
            manualEnabled: Navigation.canGoBack
            onTriggered: Commands.execute("navigation.back")
        }
        AcpButton {
            objectName: "shell-forward"
            label: ""; iconName: "chevronRight"
            Accessible.name: qsTr("Écran suivant · Alt+droite")
            manualEnabled: Navigation.canGoForward
            onTriggered: Commands.execute("navigation.forward")
        }
        Text {
            objectName: "shell-context-label"
            Layout.maximumWidth: bar.width * 0.28
            visible: bar.contextLabel.length > 0
            text: bar.contextLabel
            textFormat: Text.PlainText
            color: Colors.textMuted
            elide: Text.ElideRight
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
        Text {
            visible: bar.contextLabel.length > 0
            text: "/"; textFormat: Text.PlainText; color: Colors.borderInteractive
        }
        Text {
            objectName: "shell-context-title"
            Layout.fillWidth: true
            text: bar.conversation ? Conversations.currentTitle || qsTr("Conversations") : Navigation.currentTitle
            textFormat: Text.PlainText
            color: Colors.textPrimary
            elide: Text.ElideRight
            font.family: Type.tableCellEmphasis.family
            font.pixelSize: Type.tableCellEmphasis.pixelSize
            font.weight: Type.tableCellEmphasis.weight
        }
        AcpButton {
            objectName: "shell-command-palette"
            label: bar.width > 1050 ? qsTr("Rechercher une commande") : ""
            iconName: "search"
            shortcutHint: bar.width > 1050 ? "Ctrl+K" : ""
            commandId: "palette.open"
            Accessible.name: qsTr("Rechercher une commande · Ctrl+K")
        }
        AcpButton {
            objectName: "shell-inspect"
            visible: bar.inspectorAvailable
            label: qsTr("Détails")
            iconName: "more"
            onTriggered: Shell.inspectorVisible = !Shell.inspectorVisible
        }
    }
}
