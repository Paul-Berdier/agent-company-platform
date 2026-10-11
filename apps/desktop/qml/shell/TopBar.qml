// Barre supérieure : navigation, contexte (projet › mission), palette et volets. Le titre
// décrit ce qui est visible, jamais un ancien projet sélectionné.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Rectangle {
    id: bar
    property bool navigationCompact: false
    property bool missionOuverte: false
    signal toggleNavigation()
    color: Colors.surfaceCanvas
    readonly property string contextLabel: bar.missionOuverte && (Espace.mission.depot || "").length > 0
        ? Espace.mission.depot : ""
    readonly property string contextTitle: bar.missionOuverte && (Espace.mission.titre || "").length > 0
        ? Espace.mission.titre : Navigation.currentTitle

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: Space.layoutBorderWidth
        color: Colors.borderSubtle
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Space.space4
        anchors.rightMargin: Space.space4
        spacing: Space.space3
        AcpButton {
            objectName: "shell-toggle-navigation"
            label: ""; iconName: "sidebar"
            Accessible.name: bar.navigationCompact ? qsTr("Déplier la barre des projets · Ctrl+B") : qsTr("Replier la barre des projets · Ctrl+B")
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
            Layout.maximumWidth: bar.width * 0.24
            visible: bar.contextLabel.length > 0
            text: bar.contextLabel
            textFormat: Text.PlainText
            color: Colors.textMuted
            elide: Text.ElideRight
            font.family: Type.identifier.family
            font.pixelSize: Type.identifier.pixelSize
        }
        Text {
            visible: bar.contextLabel.length > 0
            text: "›"; textFormat: Text.PlainText; color: Colors.borderInteractive
            Accessible.ignored: true
        }
        Text {
            objectName: "shell-context-title"
            Layout.fillWidth: true
            text: bar.contextTitle
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
            objectName: "shell-toggle-volet"
            visible: bar.missionOuverte
            label: ""
            iconName: "activity"
            primary: Shell.bottomDrawerVisible
            commandId: "shell.toggleDrawer"
            Accessible.name: Shell.bottomDrawerVisible ? qsTr("Masquer le volet Activité · Ctrl+J") : qsTr("Afficher le volet Activité · Ctrl+J")
        }
        AcpButton {
            objectName: "shell-toggle-agents"
            visible: bar.missionOuverte
            label: bar.width > 1050 ? qsTr("Agents") : ""
            iconName: "grid"
            primary: Shell.agentsPanelVisible
            commandId: "shell.toggleAgents"
            Accessible.name: Shell.agentsPanelVisible ? qsTr("Masquer le panneau des agents · Ctrl+Alt+B") : qsTr("Afficher le panneau des agents · Ctrl+Alt+B")
        }
    }
}
