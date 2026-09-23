import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    function openPendingCreation() {
        if (Workspace.projectCreationPending) {
            Workspace.acknowledgeProjectCreation();
            if (Workspace.canCreateProject) createDialog.open();
        }
    }
    Component.onCompleted: openPendingCreation()
    Connections {
        target: Workspace
        function onChanged() { page.openPendingCreation(); }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space5
        RowLayout {
            Layout.fillWidth: true
            Label { textFormat: Text.PlainText; text: qsTr("Vos projets"); color: Colors.textPrimary; font.pixelSize: Type.pageTitle.pixelSize; font.weight: Type.pageTitle.weight }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: Workspace.busy; visible: running; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
            AcpButton { label: qsTr("Actualiser"); enabled: !Workspace.busy; onTriggered: Workspace.refresh() }
            AcpButton { objectName: "projectNewButton"; label: qsTr("Nouveau projet"); iconName: "plus"; primary: true; manualEnabled: Workspace.canCreateProject && !Conversations.busy && !Conversations.pendingSubmission; onTriggered: createDialog.open() }
        }
        Label {
            Layout.fillWidth: true
            visible: Workspace.error.length > 0 || Workspace.notice.length > 0
            text: Workspace.error || Workspace.notice
            textFormat: Text.PlainText
            color: Workspace.error ? Status.statusFailedForeground : Colors.textSecondary
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.StaticText
        }
        Label {
            Layout.fillWidth: true
            visible: !Workspace.busy && !Workspace.canCreateProject
            text: qsTr("Création de projet indisponible : le rôle membre minimum est requis dans l’espace de travail, ou propriétaire de la plateforme.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Colors.textMuted
        }
        Label {
            Layout.fillWidth: true
            text: qsTr("Retrouvez le contexte, les échanges et les résultats de chaque projet.")
            textFormat: Text.PlainText
            color: Colors.textSecondary
            font.pixelSize: Type.prose.pixelSize
            wrapMode: Text.WordWrap
        }
        AcpTextField { id: search; Layout.fillWidth: true; placeholder: qsTr("Rechercher un projet") }
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            ListView {
                id: projects
                SplitView.preferredWidth: 320
                SplitView.minimumWidth: 220
                clip: true
                model: Workspace.projects
                spacing: Space.space2
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    id: projectRow
                    required property var item
                    enabled: !Conversations.busy && !Conversations.pendingSubmission
                    width: ListView.view.width
                    property bool matches: (String(item.name) + " " + String(item.description)).toLowerCase().indexOf(search.text.toLowerCase()) >= 0
                    height: matches ? 64 : 0
                    visible: matches
                    highlighted: Workspace.projectId === item.id
                    Accessible.name: item.name
                    onClicked: Workspace.selectProject(item.id)
                    contentItem: RowLayout {
                        spacing: Space.space5
                        AcpIcon { name: "folder"; size: 20; color: projectRow.highlighted ? Colors.accentPrimary : Colors.textSecondary }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Space.space2
                            Label { Layout.fillWidth: true; text: item.name; textFormat: Text.PlainText; elide: Text.ElideRight; color: Colors.textPrimary; font.weight: Type.tableCellEmphasis.weight; font.pixelSize: Type.tableCell.pixelSize }
                            Label { Layout.fillWidth: true; text: item.description || qsTr("Projet de travail"); textFormat: Text.PlainText; elide: Text.ElideRight; color: Colors.textSecondary; font.pixelSize: Type.metadata.pixelSize }
                        }
                    }
                    background: Rectangle { color: parent.highlighted ? Colors.stateSelected : Colors.surfacePanel; radius: Radius.radiusSm }
                }
                Label {
                    textFormat: Text.PlainText
                    anchors.centerIn: parent
                    width: parent.width - 24
                    visible: !Workspace.busy && Workspace.projects.count === 0
                    text: qsTr("Aucun projet accessible. Créez un projet dans un espace de travail autorisé.")
                    wrapMode: Text.WordWrap
                    color: Colors.textSecondary
                }
            }
            ScrollView {
                SplitView.fillWidth: true
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: Space.space5
                    Item { Layout.preferredHeight: Space.space4 }
                    AcpIcon { name: "folder"; size: 28; color: Colors.accentPrimary; visible: Workspace.projectId.length > 0 }
                    Label { Layout.fillWidth: true; text: Workspace.projectName || qsTr("Sélectionnez un projet"); textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Colors.textPrimary; font.pixelSize: Type.objectTitle.pixelSize }
                    Label { Layout.fillWidth: true; text: Workspace.project.description || ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Colors.textSecondary }
                    Label {
                        Layout.fillWidth: true
                        text: Workspace.projectId.length > 0 ? qsTr("Que souhaitez-vous faire avancer ?") : qsTr("Choisissez un projet pour reprendre le travail, ou créez-en un nouveau.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textSecondary
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Space.space3
                        visible: Workspace.projectId.length > 0
                        AcpButton {
                            objectName: "projectOpenConversationsButton"
                            label: qsTr("Reprendre les échanges")
                            iconName: "chat"
                            primary: true
                            manualEnabled: !Conversations.busy && !Conversations.pendingSubmission
                            onTriggered: { Conversations.projectId = Workspace.projectId; Navigation.setCurrentRoute("conversations"); }
                        }
                        AcpButton { label: qsTr("Missions et code"); iconName: "code"; onTriggered: Navigation.setCurrentRoute("missions") }
                        AcpButton { label: qsTr("Livrables"); iconName: "archive"; onTriggered: Navigation.setCurrentRoute("library") }
                    }
                    AcpButton {
                        visible: Workspace.projectId.length > 0
                        label: qsTr("Nouvelle conversation dans ce projet")
                        iconName: "plus"
                        manualEnabled: Conversations.available && !Conversations.busy && !Conversations.loading && !Conversations.pendingSubmission
                        onTriggered: { if (Conversations.startConversation(Workspace.projectId)) Navigation.currentRoute = "conversations"; }
                    }
                    Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        text: qsTr("Les conversations conservent le contexte du projet. Les missions confient le travail à vos agents ; leurs résultats restent consultables dans les livrables.")
                        wrapMode: Text.WordWrap
                        color: Colors.textMuted
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Colors.borderSubtle; visible: Workspace.projectId.length > 0 }
                    Label { text: Workspace.projectId; textFormat: Text.PlainText; color: Colors.textMuted; font.family: Type.identifier.family; font.pixelSize: Type.identifier.pixelSize; visible: Workspace.projectId.length > 0 }
                }
            }
        }
        RowLayout {
            visible: Session.platformRole === "owner"
            Label { textFormat: Text.PlainText; text: qsTr("Administration des espaces"); color: Colors.textSecondary }
            AcpButton { objectName: "organizationNewButton"; label: qsTr("Créer une organisation"); manualEnabled: !Workspace.busy; onTriggered: organizationDialog.open() }
            AcpButton { objectName: "workspaceNewButton"; label: qsTr("Créer un espace"); manualEnabled: !Workspace.busy && Workspace.organizations.count > 0; onTriggered: workspaceDialog.open() }
        }
    }
    Dialog {
        id: createDialog
        objectName: "projectCreateDialog"
        title: qsTr("Nouveau projet")
        anchors.centerIn: parent
        width: Math.min(page.width - 32, 500)
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: {
            if (workspaceChoice.currentIndex < 0 && workspaceChoice.count > 0) workspaceChoice.currentIndex = 0;
            standardButton(Dialog.Ok).objectName = "projectCreateOk";
            standardButton(Dialog.Ok).enabled = Qt.binding(function() {
                return Workspace.canCreateProject && Workspace.canCreateInWorkspace(workspaceChoice.currentValue || "");
            });
        }
        onAccepted: Workspace.createProject(workspaceChoice.currentValue || "", projectName.text, description.text)
        ColumnLayout {
            width: parent.width
            ComboBox {
                id: workspaceChoice
                objectName: "projectWorkspaceChoice"
                Layout.fillWidth: true
                model: Workspace.workspaces
                textRole: "recordName"
                valueRole: "recordId"
                Accessible.name: qsTr("Espace de travail du nouveau projet")
                contentItem: Text { text: workspaceChoice.displayText; textFormat: Text.PlainText; color: Colors.textPrimary; verticalAlignment: Text.AlignVCenter }
                delegate: ItemDelegate {
                    required property string recordName
                    width: workspaceChoice.width
                    contentItem: Text { text: recordName; textFormat: Text.PlainText; color: Colors.textPrimary }
                }
            }
            Label {
                Layout.fillWidth: true
                visible: !Workspace.canCreateProject || !Workspace.canCreateInWorkspace(workspaceChoice.currentValue || "")
                text: qsTr("Cet espace n’autorise pas la création : rôle membre minimum requis dans l’espace.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            AcpTextField { id: projectName; objectName: "projectNameField"; Layout.fillWidth: true; placeholder: qsTr("Nom du projet") }
            AcpTextField { id: description; objectName: "projectDescriptionField"; Layout.fillWidth: true; placeholder: qsTr("Description") }
        }
    }
    Dialog {
        id: organizationDialog
        objectName: "organizationCreateDialog"
        title: qsTr("Nouvelle organisation")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: standardButton(Dialog.Ok).objectName = "organizationCreateOk"
        onAccepted: Workspace.createOrganization(organizationName.text)
        AcpTextField { id: organizationName; objectName: "organizationNameField"; placeholder: qsTr("Nom de l’organisation") }
    }
    Dialog {
        id: workspaceDialog
        objectName: "workspaceCreateDialog"
        title: qsTr("Nouvel espace de travail")
        anchors.centerIn: parent
        width: Math.min(page.width - 32, 500)
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: {
            if (organizationChoice.currentIndex < 0 && organizationChoice.count > 0) organizationChoice.currentIndex = 0;
            standardButton(Dialog.Ok).objectName = "workspaceCreateOk";
        }
        onAccepted: Workspace.createWorkspace(organizationChoice.currentIndex >= 0 ? Workspace.organizations.get(organizationChoice.currentIndex).id : "", workspaceName.text)
        ColumnLayout {
            width: parent.width
            ComboBox {
                id: organizationChoice
                Layout.fillWidth: true
                model: Workspace.organizations
                textRole: "recordName"
                valueRole: "recordId"
                Accessible.name: qsTr("Organisation du nouvel espace")
                contentItem: Text { text: organizationChoice.displayText; textFormat: Text.PlainText; color: Colors.textPrimary; verticalAlignment: Text.AlignVCenter }
                delegate: ItemDelegate {
                    required property string recordName
                    width: organizationChoice.width
                    contentItem: Text { text: recordName; textFormat: Text.PlainText; color: Colors.textPrimary }
                }
            }
            AcpTextField { id: workspaceName; objectName: "workspaceNameField"; Layout.fillWidth: true; placeholder: qsTr("Nom de l’espace") }
        }
    }
}
