// Entrée du poste ACP : conversation libre ou projet de travail, avec données réelles.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    function newChat() {
        if (Conversations.startConversation("")) Navigation.currentRoute = "conversations";
    }
    function newProject() {
        Workspace.requestProjectCreation();
        Navigation.currentRoute = "projects";
    }
    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: Math.min(page.width - Space.space8 * 2, 760)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Space.space8
            Item { Layout.preferredHeight: Math.max(Space.space8, page.height * 0.065) }
            RowLayout {
                spacing: Space.space4
                Rectangle { width: 24; height: 3; radius: 1; color: Colors.accentPrimary }
                Label {
                    text: qsTr("Agent Company Platform")
                    textFormat: Text.PlainText
                    color: Colors.textSecondary
                    font.family: Type.metadata.family
                    font.pixelSize: Type.metadata.pixelSize
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Space.space5
                Label {
                    Layout.fillWidth: true
                    text: qsTr("Une idée. Un échange. Un projet.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textPrimary
                    font.family: Type.emptyStateTitle.family
                    font.pixelSize: Type.emptyStateTitle.pixelSize
                    font.weight: Type.emptyStateTitle.weight
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("Échangez librement ou ouvrez un projet pour coder, organiser le travail et produire des livrables.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textSecondary
                    font.family: Type.prose.family
                    font.pixelSize: Type.prose.pixelSize
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: width < 550 ? 1 : 2
                columnSpacing: Space.space8
                rowSpacing: Space.space7
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space5
                    AcpIcon { name: "chat"; size: 24; color: Colors.accentPrimary }
                    Label {
                        text: qsTr("Simplement discuter")
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        font.family: Type.objectTitle.family
                        font.pixelSize: Type.objectTitle.pixelSize
                        font.weight: Type.objectTitle.weight
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 290
                        text: qsTr("Une question, une recherche, une idée à clarifier. Aucun projet à créer.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textSecondary
                        font.pixelSize: Type.prose.pixelSize
                    }
                    AcpButton {
                        objectName: "homeNewConversationButton"
                        label: qsTr("Nouvelle conversation")
                        iconName: "plus"
                        primary: true
                        Layout.preferredHeight: Space.densityControlHeightLarge
                        manualEnabled: Conversations.available && !Conversations.busy
                            && !Conversations.loading && !Conversations.pendingSubmission
                        onTriggered: page.newChat()
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space5
                    AcpIcon { name: "folder"; size: 24; color: Colors.textSecondary }
                    Label {
                        text: qsTr("Construire quelque chose")
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        font.family: Type.objectTitle.family
                        font.pixelSize: Type.objectTitle.pixelSize
                        font.weight: Type.objectTitle.weight
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 290
                        text: qsTr("Un contexte partagé, des conversations et des missions pour avancer avec vos agents.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textSecondary
                        font.pixelSize: Type.prose.pixelSize
                    }
                    AcpButton {
                        objectName: "homeNewProjectButton"
                        label: qsTr("Nouveau projet")
                        iconName: "plus"
                        Layout.preferredHeight: Space.densityControlHeightLarge
                        manualEnabled: Workspace.canCreateProject && !Conversations.busy && !Conversations.pendingSubmission
                        onTriggered: page.newProject()
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Colors.borderDefault }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Space.space4
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: qsTr("Reprendre un projet")
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        font.family: Type.panelTitle.family
                        font.pixelSize: Type.panelTitle.pixelSize
                        font.weight: Type.panelTitle.weight
                    }
                    Item { Layout.fillWidth: true }
                    AcpButton {
                        label: qsTr("Tous les projets")
                        iconName: "chevronRight"
                        commandId: "navigation.projects"
                    }
                }
                Repeater {
                    model: Workspace.projects
                    delegate: ItemDelegate {
                        required property var item
                        required property int index
                        enabled: !Conversations.busy && !Conversations.pendingSubmission
                        Layout.fillWidth: true
                        visible: index < 5
                        Layout.preferredHeight: visible ? 58 : 0
                        Accessible.name: qsTr("Reprendre le projet %1").arg(item.name)
                        onClicked: {
                            Workspace.selectProject(item.id);
                            Navigation.currentRoute = "projects";
                        }
                        contentItem: RowLayout {
                            spacing: Space.space5
                            AcpIcon { name: "folder"; size: 20 }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Space.space1
                                Label {
                                    Layout.fillWidth: true
                                    text: item.name
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: Colors.textPrimary
                                    font.pixelSize: Type.tableCell.pixelSize
                                    font.weight: Type.tableCellEmphasis.weight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: item.description || qsTr("Ouvrir les conversations et le travail du projet")
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: Colors.textSecondary
                                    font.pixelSize: Type.metadata.pixelSize
                                }
                            }
                            AcpIcon { name: "chevronRight"; size: 16 }
                        }
                        background: Rectangle {
                            radius: 0
                            color: parent.hovered ? Colors.stateHover : "transparent"
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Colors.borderSubtle }
                        }
                    }
                }
                Label {
                    Layout.fillWidth: true
                    visible: Workspace.projects.count === 0 && !Workspace.busy
                    text: Workspace.canCreateProject
                        ? qsTr("Vos projets apparaîtront ici. Créez-en un pour retrouver vos échanges et vos livrables au même endroit.")
                        : qsTr("Aucun projet accessible. Ouvrez les projets pour configurer un espace de travail ou consulter vos droits.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textSecondary
                    font.pixelSize: Type.prose.pixelSize
                }
                Label {
                    Layout.fillWidth: true
                    visible: Workspace.error.length > 0 || Conversations.error.length > 0
                    text: Workspace.error || Conversations.error
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Status.statusFailedForeground
                }
                BusyIndicator { running: Workspace.busy; visible: running; Layout.preferredHeight: 28 }
            }
            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
