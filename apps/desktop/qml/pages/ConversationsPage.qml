import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    property string shownExport: ""
    property string shownTitle: ""
    property string shownConversationId: ""

    Component.onCompleted: Conversations.active = true
    Component.onDestruction: Conversations.active = false

    function turnLabel(status) {
        switch (status) {
        case "submitting": return qsTr("Envoi enregistré");
        case "running": return qsTr("Réponse en cours");
        case "completed": return qsTr("Terminé");
        case "failed": return qsTr("Échec");
        case "interrupted": return qsTr("Interrompu");
        default: return qsTr("Inconnu");
        }
    }

    Connections {
        target: Conversations
        function onChanged() {
            if (Conversations.currentId !== page.shownConversationId
                    || Conversations.currentTitle !== page.shownTitle) {
                page.shownConversationId = Conversations.currentId;
                page.shownTitle = Conversations.currentTitle;
                editTitle.text = Conversations.currentTitle;
            }
            if (Conversations.exportText.length > 0 && Conversations.exportText !== page.shownExport) {
                page.shownExport = Conversations.exportText;
                exportDialog.open();
            }
            if (Conversations.exportText.length === 0) {
                page.shownExport = "";
                exportDialog.close();
            }
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
                title: qsTr("Conversations")
                subtitle: Conversations.projectId.length > 0
                    ? qsTr("Historique du projet sélectionné · réponses fournies par Hermes")
                    : qsTr("Conversations générales · réponses fournies par Hermes")
            }
            BusyIndicator {
                running: Conversations.loading || Conversations.busy
                visible: running
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                Accessible.name: qsTr("Chargement des conversations")
            }
            AcpButton {
                label: qsTr("Actualiser")
                manualEnabled: Conversations.available && !Conversations.busy && !Conversations.loading
                onTriggered: Conversations.refresh()
            }
        }

        Label {
            Layout.fillWidth: true
            visible: Conversations.error.length > 0
            text: Conversations.error
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Status.statusFailedForeground
            Accessible.name: text
        }
        Label {
            Layout.fillWidth: true
            visible: Conversations.notice.length > 0
            text: Conversations.notice
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textSecondary
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 270
                SplitView.minimumWidth: 220
                color: Colors.surfacePanel
                border.color: Colors.borderDefault
                radius: Radius.radiusMd

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Space.space4
                    spacing: Space.space4
                    Label {
                        text: qsTr("Vos conversations")
                        color: Colors.textPrimary
                        font.bold: true
                    }
                    ListView {
                        id: conversationList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: Conversations.conversations
                        clip: true
                        spacing: Space.space2
                        ScrollBar.vertical: ScrollBar {}
                        delegate: ItemDelegate {
                            required property var item
                            width: conversationList.width
                            enabled: !Conversations.busy && !Conversations.pendingSubmission
                            Accessible.name: item.title + (item.status === "archived" ? qsTr(", archivée") : "")
                            contentItem: Column {
                                spacing: Space.space2
                                Text {
                                    width: parent.width
                                    text: item.title
                                    textFormat: Text.PlainText
                                    color: Colors.textPrimary
                                    wrapMode: Text.Wrap
                                    font.pixelSize: Type.tableCell.pixelSize
                                }
                                Text {
                                    width: parent.width
                                    text: item.status === "archived" ? qsTr("Archivée") : qsTr("Active")
                                    textFormat: Text.PlainText
                                    color: Colors.textSecondary
                                    font.pixelSize: Type.identifier.pixelSize
                                }
                            }
                            background: Rectangle {
                                radius: Radius.radiusSm
                                color: item.id === Conversations.currentId
                                    ? Colors.stateSelected : Colors.surfacePanel
                            }
                            onClicked: Conversations.selectConversation(item.id)
                        }
                        Label {
                            anchors.centerIn: parent
                            width: parent.width - Space.space4
                            visible: conversationList.count === 0 && !Conversations.loading
                            text: Conversations.available ? qsTr("Aucune conversation dans ce contexte.")
                                                          : qsTr("Connectez-vous pour lire les conversations.")
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            color: Colors.textMuted
                        }
                    }
                    AcpTextField {
                        id: newTitle
                        Layout.fillWidth: true
                        placeholder: qsTr("Titre de la conversation")
                        accessibleName: qsTr("Titre de la nouvelle conversation")
                        enabled: !Conversations.busy && Conversations.available
                    }
                    AcpButton {
                        Layout.fillWidth: true
                        label: qsTr("Nouvelle conversation")
                        primary: true
                        manualEnabled: Conversations.available && !Conversations.busy && !Conversations.loading
                            && !Conversations.pendingSubmission && newTitle.text.trim().length > 0
                        onTriggered: Conversations.createConversation(newTitle.text)
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 390
                color: Colors.surfaceCanvas

                EmptyState {
                    anchors.fill: parent
                    visible: Conversations.currentId.length === 0
                    title: qsTr("Ouvrez une conversation")
                    body: qsTr("Sélectionnez un historique ou créez une conversation dans le contexte courant.")
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Space.space5
                    visible: Conversations.currentId.length > 0
                    spacing: Space.space4

                    RowLayout {
                        Layout.fillWidth: true
                        AcpTextField {
                            id: editTitle
                            Layout.fillWidth: true
                            placeholder: qsTr("Titre")
                            accessibleName: qsTr("Renommer la conversation")
                            enabled: !Conversations.busy && !Conversations.loading
                        }
                        AcpButton {
                            label: qsTr("Renommer")
                            manualEnabled: !Conversations.busy && !Conversations.loading
                                && !Conversations.pendingSubmission
                                && editTitle.text.trim().length > 0
                                && editTitle.text !== Conversations.currentTitle
                            onTriggered: Conversations.renameConversation(editTitle.text)
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        StatusChip {
                            statusKey: Conversations.archived ? "unknown" : "succeeded"
                            label: Conversations.archived ? qsTr("Archivée") : qsTr("Active")
                        }
                        Label {
                            visible: Conversations.polling
                            text: qsTr("Suivi de la réponse…")
                            color: Colors.textSecondary
                        }
                        Item { Layout.fillWidth: true }
                        AcpButton {
                            label: qsTr("Exporter")
                            manualEnabled: !Conversations.busy && !Conversations.loading
                            onTriggered: Conversations.exportConversation()
                        }
                        AcpButton {
                            label: Conversations.archived ? qsTr("Réactiver") : qsTr("Archiver")
                            manualEnabled: !Conversations.busy && !Conversations.loading && !Conversations.pendingSubmission
                            onTriggered: Conversations.setArchived(!Conversations.archived)
                        }
                    }

                    ListView {
                        id: history
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: Conversations.turns
                        spacing: Space.space5
                        ScrollBar.vertical: ScrollBar {}
                        onCountChanged: Qt.callLater(function() { history.positionViewAtEnd(); })
                        delegate: Rectangle {
                            required property var item
                            width: history.width
                            implicitHeight: turnColumn.implicitHeight + Space.space5 * 2
                            color: Colors.surfacePanel
                            radius: Radius.radiusMd
                            border.color: Colors.borderDefault
                            Column {
                                id: turnColumn
                                anchors.fill: parent
                                anchors.margins: Space.space5
                                spacing: Space.space4
                                Text {
                                    text: qsTr("Vous")
                                    color: Colors.textSecondary
                                    font.bold: true
                                }
                                TextEdit {
                                    width: parent.width
                                    text: item.user_content
                                    textFormat: TextEdit.PlainText
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: Colors.textPrimary
                                    font.family: Type.prose.family
                                    font.pixelSize: Type.prose.pixelSize
                                    Accessible.name: qsTr("Message envoyé")
                                }
                                Text {
                                    text: qsTr("Hermes · %1").arg(page.turnLabel(item.status))
                                    textFormat: Text.PlainText
                                    color: Colors.textSecondary
                                    font.bold: true
                                }
                                TextEdit {
                                    width: parent.width
                                    visible: item.assistant_content !== null && item.assistant_content !== undefined
                                    text: item.assistant_content || ""
                                    textFormat: TextEdit.PlainText
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: Colors.textPrimary
                                    font.family: Type.prose.family
                                    font.pixelSize: Type.prose.pixelSize
                                    Accessible.name: qsTr("Réponse Hermes")
                                }
                                Text {
                                    width: parent.width
                                    visible: !!item.error
                                    text: item.error || ""
                                    textFormat: Text.PlainText
                                    wrapMode: Text.Wrap
                                    color: Status.statusFailedForeground
                                }
                            }
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: history.count === 0 && !Conversations.loading
                            text: qsTr("Aucun message. Écrivez le premier.")
                            color: Colors.textMuted
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 112
                        TextArea {
                            id: composer
                            text: Conversations.draft
                            onTextChanged: Conversations.draft = text
                            readOnly: Conversations.pendingSubmission || Conversations.busy || Conversations.archived
                            textFormat: TextEdit.PlainText
                            wrapMode: TextEdit.Wrap
                            placeholderText: Conversations.archived ? qsTr("Réactivez la conversation pour écrire.")
                                                                   : qsTr("Votre message…")
                            color: Colors.textPrimary
                            selectionColor: Colors.stateSelected
                            font.family: Type.prose.family
                            font.pixelSize: Type.prose.pixelSize
                            background: Rectangle {
                                color: Colors.surfacePanelRaised
                                border.color: Colors.borderInteractive
                                radius: Radius.radiusSm
                            }
                            Accessible.name: qsTr("Message à Hermes")
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: Conversations.pendingSubmission
                                ? qsTr("Envoi incertain : le texte et sa clé restent conservés.")
                                : qsTr("%1 / 100 000 caractères").arg(Conversations.draft.length)
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Colors.textSecondary
                        }
                        AcpButton {
                            visible: Conversations.pendingSubmission
                            label: qsTr("Réessayer le même envoi")
                            manualEnabled: !Conversations.busy && !Conversations.loading && !Conversations.archived
                            onTriggered: Conversations.retryPendingMessage()
                        }
                        AcpButton {
                            label: qsTr("Envoyer")
                            primary: true
                            manualEnabled: Conversations.canSend
                            onTriggered: Conversations.sendMessage()
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: exportDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(page.width, 850)
        height: Math.min(page.height, 650)
        modal: true
        title: qsTr("Export JSON de la conversation")
        standardButtons: Dialog.Close
        contentItem: ColumnLayout {
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                TextArea {
                    id: exportContent
                    text: Conversations.exportText
                    textFormat: TextEdit.PlainText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: Colors.textPrimary
                    font.family: Type.identifier.family
                    font.pixelSize: Type.identifier.pixelSize
                    Accessible.name: qsTr("Contenu JSON exporté")
                }
            }
            AcpButton {
                label: qsTr("Copier l'export")
                onTriggered: {
                    exportContent.selectAll();
                    exportContent.copy();
                    exportContent.deselect();
                }
            }
        }
    }
}
