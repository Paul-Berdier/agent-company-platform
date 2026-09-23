import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space5
        RowLayout {
            Layout.fillWidth: true
            Label { textFormat: Text.PlainText; text: qsTr("Projets"); color: Colors.textPrimary; font.pixelSize: Type.pageTitle.pixelSize }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: Workspace.busy; visible: running; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
            AcpButton { label: qsTr("Actualiser"); enabled: !Workspace.busy; onTriggered: Workspace.refresh() }
            AcpButton { objectName: "projectNewButton"; label: qsTr("Nouveau projet"); manualEnabled: Workspace.canCreateProject; onTriggered: createDialog.open() }
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
        AcpTextField { id: search; Layout.fillWidth: true; placeholder: qsTr("Rechercher un projet par nom ou description") }
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
                    required property var item
                    width: ListView.view.width
                    property bool matches: (String(item.name) + " " + String(item.description)).toLowerCase().indexOf(search.text.toLowerCase()) >= 0
                    height: matches ? 74 : 0
                    visible: matches
                    highlighted: Workspace.projectId === item.id
                    Accessible.name: item.name
                    onClicked: Workspace.selectProject(item.id)
                    contentItem: Column {
                        spacing: 5
                        Label { width: parent.width; text: item.name; textFormat: Text.PlainText; elide: Text.ElideRight; color: Colors.textPrimary; font.bold: true }
                        Label { width: parent.width; text: item.description || item.status; textFormat: Text.PlainText; elide: Text.ElideRight; color: Colors.textSecondary }
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
                    Label { Layout.fillWidth: true; text: Workspace.projectName || qsTr("Sélectionnez un projet"); textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Colors.textPrimary; font.pixelSize: Type.objectTitle.pixelSize }
                    Label { Layout.fillWidth: true; text: Workspace.project.description || ""; textFormat: Text.PlainText; wrapMode: Text.WordWrap; color: Colors.textSecondary }
                    Label { text: Workspace.projectId; textFormat: Text.PlainText; color: Colors.textMuted; font.family: Type.identifier.family }
                    Label { text: Workspace.project.status || ""; textFormat: Text.PlainText; color: Colors.textSecondary }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Space.space3
                        visible: Workspace.projectId.length > 0
                        AcpButton { label: qsTr("Conversations"); onTriggered: Navigation.setCurrentRoute("conversations") }
                        AcpButton { label: qsTr("Missions et runs"); onTriggered: Navigation.setCurrentRoute("missions") }
                        AcpButton { label: qsTr("Livrables"); onTriggered: Navigation.setCurrentRoute("library") }
                    }
                    Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        text: qsTr("Le projet sélectionné est partagé par les écrans de la station. Les droits sont vérifiés par le serveur à chaque opération.")
                        wrapMode: Text.WordWrap
                        color: Colors.textMuted
                    }
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
