import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    readonly property bool mcpMode: extensionTabs.currentIndex === 0
    readonly property var selection: mcpMode ? Platform.selectedMcp : Platform.selectedSkill
    readonly property var binding: selection.binding || ({})
    readonly property bool editable: Platform.available && !Platform.busy && !Platform.loading && !!selection.id
    property string confirmedAction: ""
    property string confirmationText: ""

    Component.onCompleted: Platform.active = true
    Component.onDestruction: Platform.active = false

    function confirm(action, text) {
        confirmedAction = action;
        confirmationText = text;
        confirmation.open();
    }
    Connections {
        target: Platform
        function onChanged() {
            if (!Platform.available || !page.selection.id)
                confirmation.close();
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4
        RowLayout {
            Layout.fillWidth: true
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Extensions")
                subtitle: qsTr("Serveurs MCP et compétences installées · versions et accès du projet")
            }
            BusyIndicator { running: Platform.loading || Platform.busy; visible: running; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
            AcpButton { label: qsTr("Actualiser"); manualEnabled: Platform.available && !Platform.loading && !Platform.busy; onTriggered: Platform.refresh() }
        }
        Label { Layout.fillWidth: true; text: Platform.error; visible: text.length > 0; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Status.statusFailedForeground }
        Label { Layout.fillWidth: true; text: Platform.notice; visible: text.length > 0; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textSecondary }
        Label {
            Layout.fillWidth: true
            text: Platform.projectId.length > 0 ? qsTr("Projet sélectionné : %1").arg(Platform.projectId) : qsTr("Sélectionnez un projet pour lier ses extensions.")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textMuted
        }
        TabBar {
            id: extensionTabs
            Layout.fillWidth: true
            TabButton { text: qsTr("MCP (%1)").arg(Platform.mcpServers.count) }
            TabButton { text: qsTr("Compétences (%1)").arg(Platform.skills.count) }
        }
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            ListView {
                id: extensionList
                SplitView.preferredWidth: 280
                SplitView.minimumWidth: 200
                clip: true
                spacing: 6
                model: page.mcpMode ? Platform.mcpServers : Platform.skills
                ScrollBar.vertical: ScrollBar { }
                delegate: ItemDelegate {
                    required property var item
                    width: extensionList.width
                    implicitHeight: listText.implicitHeight + 24
                    enabled: !Platform.busy
                    highlighted: item.id === page.selection.id
                    Accessible.name: item.display_name || item.name
                    contentItem: Label {
                        id: listText
                        text: (item.display_name || item.name) + "\n" + item.status + " · " + qsTr("Version %1").arg(item.current_revision_number || "?")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textPrimary
                    }
                    onClicked: page.mcpMode ? Platform.selectMcp(item.id) : Platform.selectSkill(item.id)
                }
                Label { anchors.centerIn: parent; visible: extensionList.count === 0 && !Platform.loading; text: qsTr("Aucune extension installée."); textFormat: Text.PlainText; color: Colors.textMuted }
            }
            ScrollView {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 330
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: Space.space4
                    Label { Layout.fillWidth: true; text: page.selection.display_name || page.selection.name || qsTr("Sélectionnez une extension"); textFormat: Text.PlainText; font.bold: true; font.pixelSize: 20; wrapMode: Text.Wrap; color: Colors.textPrimary }
                    Label { Layout.fillWidth: true; text: page.selection.description || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textSecondary }
                    Label {
                        Layout.fillWidth: true
                        visible: !!page.selection.id
                        text: qsTr("État : %1 · Version courante : %2").arg(page.selection.status || qsTr("Inconnu")).arg(page.selection.current_revision_number || "?")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textPrimary
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !!page.selection.id
                        text: page.binding.id
                            ? qsTr("Lié au projet · version épinglée %1 · %2").arg(page.binding.revision_number).arg(page.binding.enabled ? qsTr("Activé") : qsTr("Désactivé"))
                            : qsTr("Aucune liaison avec le projet sélectionné. Une nouvelle liaison utilise la version courante.")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textSecondary
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !!page.selection.id
                        text: qsTr("Versions disponibles : %1").arg(page.selection.versions ? page.selection.versions.map(function(v) { return v.number; }).join(", ") : "?")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textMuted
                    }
                    Label { Layout.fillWidth: true; visible: !page.mcpMode && !!page.selection.requires_approval; text: qsTr("Cette version nécessite une approbation avant activation."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textMuted }
                    Label { visible: page.mcpMode && !!page.selection.id; text: qsTr("Outils autorisés pour le projet"); textFormat: Text.PlainText; color: Colors.textPrimary; font.bold: true }
                    Label {
                        Layout.fillWidth: true
                        visible: Platform.bindingPermissionReason.length > 0
                        text: Platform.bindingPermissionReason
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textMuted
                    }
                    Repeater {
                        model: page.mcpMode ? Platform.mcpTools : null
                        delegate: CheckBox {
                            required property var item
                            Layout.fillWidth: true
                            checked: !!item.selected
                            enabled: page.editable && Platform.canManageProjectBindings
                            Accessible.name: item.name
                            contentItem: Label {
                                text: item.name + (item.description ? "\n" + item.description : "")
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                leftPadding: 32
                                color: Colors.textPrimary
                            }
                            onClicked: Platform.toggleTool(item.name, checked)
                        }
                    }
                    Label { Layout.fillWidth: true; visible: page.mcpMode && !!page.selection.id && Platform.mcpTools.count === 0; text: qsTr("Aucun outil découvert pour cette version. La liaison nécessite une découverte valide côté serveur."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textMuted }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        visible: !!page.selection.id
                        AcpButton {
                            label: page.mcpMode && page.binding.id ? qsTr("Enregistrer les outils") : qsTr("Lier au projet")
                            primary: true
                            manualEnabled: page.editable && Platform.canManageProjectBindings && (page.mcpMode || !page.binding.id)
                            onTriggered: page.mcpMode ? Platform.saveMcpBinding() : Platform.bindSkill()
                        }
                        AcpButton {
                            visible: page.mcpMode && !!page.binding.id
                            label: page.binding.enabled ? qsTr("Désactiver la liaison") : qsTr("Réactiver la liaison")
                            manualEnabled: page.editable && Platform.canManageProjectBindings
                            onTriggered: Platform.setMcpBindingEnabled(!page.binding.enabled)
                        }
                        AcpButton {
                            visible: !!page.binding.id
                            label: qsTr("Retirer du projet")
                            manualEnabled: page.editable && Platform.canManageProjectBindings
                            onTriggered: page.confirm(page.mcpMode ? "remove-mcp" : "remove-skill", qsTr("Retirer cette extension du projet sélectionné ?"))
                        }
                    }
                    Label { Layout.fillWidth: true; visible: Platform.isOwner && !!page.selection.id; text: qsTr("Administration globale — affecte tous les projets utilisant cette extension."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textMuted }
                    AcpButton {
                        visible: Platform.isOwner && !!page.selection.id
                        label: page.selection.status === "active" ? qsTr("Désactiver globalement") : qsTr("Activer globalement")
                        manualEnabled: page.editable && page.selection.status !== "revoked"
                        onTriggered: page.confirm((page.mcpMode ? "mcp-" : "skill-") + (page.selection.status === "active" ? "disable" : "activate"), qsTr("Changer l'état global de cette extension pour tous ses projets ? Le serveur vérifiera les prérequis."))
                    }
                }
            }
        }
    }
    Dialog {
        id: confirmation
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: qsTr("Confirmer la modification")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: Label { text: page.confirmationText; textFormat: Text.PlainText; wrapMode: Text.Wrap; width: 420; color: Colors.textPrimary }
        onAccepted: {
            if (page.confirmedAction === "remove-mcp") Platform.removeMcpBinding();
            else if (page.confirmedAction === "remove-skill") Platform.removeSkillBinding();
            else if (page.confirmedAction === "mcp-disable") Platform.setMcpActive(false);
            else if (page.confirmedAction === "mcp-activate") Platform.setMcpActive(true);
            else if (page.confirmedAction === "skill-disable") Platform.setSkillActive(false);
            else if (page.confirmedAction === "skill-activate") Platform.setSkillActive(true);
        }
    }
}
