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
    property string shownConversationId: ""
    property bool followTail: true
    property real savedHistoryY: 0
    property bool unreadResponse: false
    property string copyNotice: ""
    readonly property bool mutableContext: Conversations.available && !Conversations.busy && !Conversations.pendingSubmission

    Component.onCompleted: Conversations.active = true
    Component.onDestruction: Conversations.active = false

    function turnLabel(status) {
        switch (status) {
        case "submitting": return qsTr("Envoi enregistré");
        case "running": return qsTr("Réponse en cours…");
        case "waiting_for_approval": return qsTr("Approbation attendue dans Hermes");
        case "stopping": return qsTr("Arrêt demandé, confirmation attendue");
        case "completed": return qsTr("Terminé");
        case "failed": return qsTr("Échec");
        case "interrupted": return qsTr("Interrompu");
        default: return qsTr("Inconnu");
        }
    }
    function copyText(value) {
        clipboardText.text = value;
        clipboardText.selectAll(); clipboardText.copy(); clipboardText.deselect();
        clipboardText.text = "";
        page.copyNotice = qsTr("Copié dans le presse-papiers");
        copyTimer.restart();
    }
    function submit() {
        if (!Conversations.canSend || composer.inputMethodComposing) return;
        page.followTail = true;
        Conversations.sendMessage();
    }
    function scrollToLatest() {
        history.positionViewAtEnd();
        page.followTail = true;
        page.unreadResponse = false;
    }
    function newChat() {
        if (Conversations.startConversation(Conversations.projectId)) historyDrawer.close();
    }
    function restoreComposerFocus() {
        // Une réponse réseau ou un changement de contexte ne vole jamais le focus
        // à une fenêtre modale (historique, renommage ou export).
        if (!historyDrawer.visible && !renameDialog.visible && !exportDialog.visible
                && Conversations.currentId.length > 0 && Conversations.active)
            composer.forceActiveFocus();
    }

    TextEdit { id: clipboardText; visible: false; textFormat: TextEdit.PlainText }
    Timer { id: copyTimer; interval: 1800; onTriggered: page.copyNotice = "" }
    Connections {
        target: Conversations
        function onHistoryAboutToChange() {
            page.followTail = history.atYEnd || history.count === 0;
            page.savedHistoryY = history.contentY;
        }
        function onHistoryChanged() {
            Qt.callLater(function() {
                if (page.followTail) page.scrollToLatest();
                else {
                    history.contentY = Math.max(history.originY, Math.min(page.savedHistoryY,
                        history.originY + history.contentHeight - history.height));
                    page.unreadResponse = true;
                }
            });
        }
        function onChanged() {
            if (Conversations.currentId !== page.shownConversationId) {
                page.shownConversationId = Conversations.currentId;
                page.followTail = true;
                page.unreadResponse = false;
                Qt.callLater(function() { page.scrollToLatest(); page.restoreComposerFocus(); });
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

    // Les délégués n'interprètent jamais HTML, URL ou images. Les clôtures de code
    // produisent seulement un encadré monospace et une copie explicite.
    component MessageBody: Column {
        id: messageBody
        property string content: ""
        signal copyRequested(string value)
        spacing: Space.space4
        Repeater {
            model: Conversations.messageBlocks(messageBody.content)
            delegate: Rectangle {
                id: block
                required property var modelData
                readonly property bool code: modelData.kind === "code"
                width: messageBody.width
                implicitHeight: blockColumn.implicitHeight + (code ? Space.space4 * 2 : 0)
                color: code ? Colors.surfaceSunken : "transparent"
                radius: Radius.radiusMd
                border.width: code ? 1 : 0
                border.color: Colors.borderSubtle
                Column {
                    id: blockColumn
                    x: block.code ? Space.space4 : 0
                    y: block.code ? Space.space4 : 0
                    width: parent.width - x * 2
                    spacing: Space.space3
                    RowLayout {
                        width: parent.width
                        visible: block.code
                        Text {
                            Layout.fillWidth: true
                            text: block.modelData.language || qsTr("Code")
                            textFormat: Text.PlainText
                            color: Colors.textSecondary
                            font.family: Type.identifier.family
                            font.pixelSize: Type.identifier.pixelSize
                        }
                        AcpButton {
                            objectName: block.code ? "conversationCopyCodeButton" : ""
                            label: qsTr("Copier le code")
                            onTriggered: messageBody.copyRequested(block.modelData.text)
                        }
                    }
                    TextEdit {
                        objectName: block.code ? "conversationCodeText" : "conversationMessageText"
                        width: parent.width
                        text: block.modelData.text
                        textFormat: TextEdit.PlainText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        color: Colors.textPrimary
                        font.family: block.code ? Type.identifier.family : Type.prose.family
                        font.pixelSize: block.code ? Type.identifier.pixelSize : Type.prose.pixelSize
                        Accessible.name: block.code ? qsTr("Bloc de code, texte inerte") : qsTr("Texte du message")
                    }
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space5
        spacing: Space.space3
        RowLayout {
            Layout.fillWidth: true
            AcpButton {
                objectName: "conversationHistoryButton"
                label: qsTr("Historique")
                iconName: "search"
                onTriggered: historyDrawer.open()
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: Conversations.currentTitle || (Conversations.projectId.length > 0 ? qsTr("Chat du projet") : qsTr("Chat général"))
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Colors.textPrimary
                    font.family: Type.objectTitle.family
                    font.pixelSize: Type.objectTitle.pixelSize
                    font.weight: Type.objectTitle.weight
                }
                Text {
                    Layout.fillWidth: true
                    text: Conversations.projectId.length === 0 ? qsTr("Discussion libre · Hermes")
                        : qsTr("%1 · Hermes").arg(Workspace.projectId === Conversations.projectId && Workspace.projectName
                            ? Workspace.projectName : qsTr("Conversation de projet"))
                    textFormat: Text.PlainText
                    color: Colors.textMuted
                    elide: Text.ElideRight
                    font.pixelSize: Type.metadata.pixelSize
                }
            }
            BusyIndicator {
                running: Conversations.loading || Conversations.busy
                visible: running
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                Accessible.name: qsTr("Chargement du chat")
            }
            AcpButton {
                objectName: "conversationNewButton"
                iconName: "plus"
                label: qsTr("Nouveau chat")
                manualEnabled: page.mutableContext
                onTriggered: page.newChat()
            }
            AcpButton {
                objectName: "conversationActionsButton"
                label: qsTr("Actions")
                iconName: "more"
                onTriggered: actionsMenu.popup()
                Menu {
                    id: actionsMenu
                    MenuItem { text: qsTr("Actualiser"); enabled: Conversations.available && !Conversations.busy && !Conversations.loading; onTriggered: Conversations.refresh() }
                    MenuItem { text: qsTr("Renommer…"); enabled: page.mutableContext && Conversations.currentId.length > 0 && !Conversations.loading; onTriggered: { renameTitle.text = Conversations.currentTitle; renameDialog.open(); } }
                    MenuItem { text: qsTr("Exporter en JSON…"); enabled: page.mutableContext && Conversations.currentId.length > 0 && !Conversations.loading; onTriggered: Conversations.exportConversation() }
                    MenuSeparator {}
                    MenuItem { text: Conversations.archived ? qsTr("Réactiver le chat") : qsTr("Archiver le chat"); enabled: page.mutableContext && Conversations.currentId.length > 0 && !Conversations.loading; onTriggered: Conversations.setArchived(!Conversations.archived) }
                }
            }
        }
        Label {
            Layout.fillWidth: true
            visible: Conversations.error.length > 0
            text: Conversations.error
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Status.statusFailedForeground
        }
        Label {
            Layout.fillWidth: true
            visible: Conversations.notice.length > 0 || page.copyNotice.length > 0
            text: page.copyNotice || Conversations.notice
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textSecondary
            font.pixelSize: Type.metadata.pixelSize
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - Space.space6 * 2, Type.measureProse)
                spacing: Space.space5
                visible: Conversations.currentId.length === 0 && !Conversations.loading && !Conversations.busy
                AcpIcon { Layout.alignment: Qt.AlignHCenter; name: Conversations.projectId.length ? "folder" : "chat"; size: 36; color: Colors.accentPrimary }
                Label {
                    Layout.fillWidth: true
                    text: Conversations.projectId.length ? qsTr("Un espace pour avancer sur votre projet") : qsTr("De quoi voulez-vous parler ?")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.pixelSize: Type.emptyStateTitle.pixelSize
                    font.weight: Type.emptyStateTitle.weight
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                }
                Label {
                    Layout.fillWidth: true
                    text: Conversations.available ? (Conversations.projectId.length
                        ? qsTr("Clarifiez une idée ou préparez une demande. Les exécutions de code et les livrables se pilotent ensuite dans les missions du projet.")
                        : qsTr("Échangez librement, sans créer de projet. Retrouvez vos discussions dans l’historique."))
                        : qsTr("Connectez-vous au serveur pour retrouver vos chats et commencer une discussion.")
                    textFormat: Text.PlainText
                    color: Colors.textSecondary
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    font.pixelSize: Type.prose.pixelSize
                }
                AcpButton {
                    objectName: "conversationEmptyNewButton"
                    Layout.alignment: Qt.AlignHCenter
                    label: qsTr("Commencer un chat")
                    iconName: "plus"
                    primary: true
                    manualEnabled: page.mutableContext
                    onTriggered: page.newChat()
                }
            }
            ListView {
                id: history
                objectName: "conversationHistory"
                anchors.fill: parent
                visible: Conversations.currentId.length > 0
                model: Conversations.turns
                clip: true
                spacing: Space.space7
                topMargin: Space.space5
                bottomMargin: Space.space5
                ScrollBar.vertical: ScrollBar {}
                onMovementEnded: { page.followTail = atYEnd; if (atYEnd) page.unreadResponse = false; }
                delegate: Item {
                    required property var item
                    width: history.width
                    implicitHeight: turnColumn.implicitHeight
                    Column {
                        id: turnColumn
                        width: Math.min(parent.width - Space.space5 * 2, Type.measureProse)
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: Space.space4
                        Rectangle {
                            width: parent.width
                            implicitHeight: userColumn.implicitHeight + Space.space5 * 2
                            radius: Radius.radiusLg
                            color: Colors.surfacePanelRaised
                            Column {
                                id: userColumn
                                x: Space.space5; y: Space.space5
                                width: parent.width - Space.space5 * 2
                                spacing: Space.space3
                                Text { text: qsTr("Vous"); textFormat: Text.PlainText; color: Colors.textSecondary; font.weight: Font.DemiBold }
                                MessageBody { width: parent.width; content: item.user_content; onCopyRequested: value => page.copyText(value) }
                            }
                        }
                        RowLayout {
                            width: parent.width
                            AcpIcon { name: "chat"; size: 18; color: Colors.accentPrimary }
                            Text { text: "Hermes"; textFormat: Text.PlainText; color: Colors.textPrimary; font.weight: Font.DemiBold }
                            Item { Layout.fillWidth: true }
                            Text { text: page.turnLabel(item.status); textFormat: Text.PlainText; color: Colors.textMuted; font.pixelSize: Type.metadata.pixelSize }
                        }
                        MessageBody {
                            width: parent.width
                            content: item.assistant_content || ""
                            visible: content.length > 0
                            onCopyRequested: value => page.copyText(value)
                        }
                        Text {
                            width: parent.width
                            visible: !!item.error
                            text: item.error || ""
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Status.statusFailedForeground
                        }
                        RowLayout {
                            width: parent.width
                            AcpButton { label: qsTr("Copier le message"); onTriggered: page.copyText(item.user_content) }
                            AcpButton { objectName: "conversationCopyAnswerButton"; visible: !!item.assistant_content; label: qsTr("Copier la réponse"); onTriggered: page.copyText(item.assistant_content) }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - Space.space5 * 2, Type.measureProse)
                    spacing: Space.space4
                    visible: history.count === 0 && !Conversations.loading
                    Text {
                        width: parent.width
                        text: qsTr("Votre conversation commence ici")
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        font.pixelSize: Type.emptyStateTitle.pixelSize
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }
                    Text {
                        width: parent.width
                        text: Conversations.projectId.length ? qsTr("Posez votre question sur le projet ou préparez votre prochaine mission.") : qsTr("Une question, une idée, quelque chose à explorer…")
                        textFormat: Text.PlainText
                        color: Colors.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }
                }
            }
            AcpButton {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                visible: page.unreadResponse && !history.atYEnd
                label: qsTr("Voir la dernière réponse")
                primary: true
                onTriggered: page.scrollToLatest()
            }
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: composerLayout.implicitHeight
            visible: Conversations.currentId.length > 0
            ColumnLayout {
                id: composerLayout
                objectName: "conversationComposerContainer"
                width: Math.min(parent.width, Type.measureProse)
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Space.space2
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: composerColumn.implicitHeight + Space.space4 * 2
                    color: Colors.surfacePanelRaised
                    border.color: composer.activeFocus ? Colors.borderFocus : Colors.borderDefault
                    radius: Radius.radiusLg
                    ColumnLayout {
                        id: composerColumn
                        x: Space.space4; y: Space.space4
                        width: parent.width - Space.space4 * 2
                        spacing: Space.space3
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(160, Math.max(54, composer.contentHeight + composer.topPadding + composer.bottomPadding))
                            clip: true
                            TextArea {
                                id: composer
                                objectName: "conversationComposer"
                                text: Conversations.draft
                                onTextChanged: Conversations.draft = text
                                readOnly: Conversations.pendingSubmission || Conversations.busy || Conversations.archived
                                textFormat: TextEdit.PlainText
                                wrapMode: TextEdit.Wrap
                                placeholderText: Conversations.archived ? qsTr("Réactivez le chat pour écrire.") : qsTr("Écrivez votre message…")
                                color: Colors.textPrimary
                                selectionColor: Colors.stateSelected
                                font.family: Type.prose.family
                                font.pixelSize: Type.prose.pixelSize
                                background: null
                                Accessible.name: qsTr("Message à Hermes")
                                Accessible.description: qsTr("Entrée pour envoyer. Majuscule et Entrée pour une nouvelle ligne.")
                                Keys.priority: Keys.BeforeItem
                                Keys.onPressed: event => {
                                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                                            && event.modifiers === Qt.NoModifier && !inputMethodComposing) {
                                        event.accepted = true;
                                        if (!event.isAutoRepeat) page.submit();
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                Layout.fillWidth: true
                                text: Conversations.pendingSubmission ? qsTr("Envoi incertain · texte conservé")
                                    : Conversations.archived ? qsTr("Chat archivé")
                                    : Conversations.draft.length > 95000 ? qsTr("%1 / 100 000 caractères").arg(Conversations.draft.length)
                                    : qsTr("Maj + Entrée pour une nouvelle ligne")
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                color: Colors.textMuted
                                font.pixelSize: Type.metadata.pixelSize
                            }
                            AcpButton {
                                visible: Conversations.pendingSubmission
                                label: qsTr("Réessayer le même envoi")
                                manualEnabled: !Conversations.busy && !Conversations.loading && !Conversations.archived && Conversations.available
                                onTriggered: Conversations.retryPendingMessage()
                            }
                            AcpButton {
                                objectName: "conversationStopTurnButton"
                                visible: Conversations.canStopTurn
                                label: qsTr("Arrêter")
                                manualEnabled: Conversations.canStopTurn
                                onTriggered: Conversations.stopTurn()
                            }
                            AcpButton {
                                objectName: "conversationSendButton"
                                visible: !Conversations.canStopTurn && !Conversations.pendingSubmission
                                label: qsTr("Envoyer")
                                iconName: "arrowUp"
                                primary: true
                                manualEnabled: Conversations.canSend
                                onTriggered: page.submit()
                            }
                        }
                    }
                }
                Label {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: Conversations.projectId.length ? qsTr("Chat du projet · les missions pilotent les exécutions et les livrables.")
                        : qsTr("Chat général · vos messages sont envoyés au Hermes configuré sur le serveur.")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    color: Colors.textMuted
                    font.pixelSize: Type.metadata.pixelSize
                }
            }
        }
    }

    Drawer {
        id: historyDrawer
        objectName: "conversationHistoryDrawer"
        parent: Overlay.overlay
        width: Math.min(360, parent ? parent.width : 360)
        height: parent ? parent.height : page.height
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: historySearch.forceActiveFocus()
        onClosed: page.restoreComposerFocus()
        background: Rectangle { color: Colors.surfaceSidebar; border.color: Colors.borderSubtle }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Space.space5
            spacing: Space.space4
            Label { text: qsTr("Vos chats"); textFormat: Text.PlainText; color: Colors.textPrimary; font.pixelSize: Type.pageTitle.pixelSize; font.weight: Font.DemiBold }
            RowLayout {
                Layout.fillWidth: true
                AcpButton { objectName: "generalConversationsButton"; label: qsTr("Général"); primary: Conversations.projectId.length === 0; manualEnabled: page.mutableContext; onTriggered: Conversations.projectId = "" }
                AcpButton { objectName: "projectConversationsButton"; label: qsTr("Projet sélectionné"); primary: Conversations.projectId.length > 0; manualEnabled: page.mutableContext && Workspace.projectId.length > 0; onTriggered: Conversations.projectId = Workspace.projectId }
            }
            AcpTextField {
                id: historySearch
                objectName: "conversationSearchField"
                Layout.fillWidth: true
                text: Conversations.searchText
                onTextChanged: Conversations.searchText = text
                placeholder: qsTr("Rechercher dans les titres…")
                accessibleName: qsTr("Rechercher les chats par titre")
            }
            CheckBox { text: qsTr("Inclure les chats archivés"); checked: Conversations.showArchived; onToggled: Conversations.showArchived = checked; palette.windowText: Colors.textSecondary }
            ListView {
                id: conversationList
                objectName: "conversationThreadList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: Conversations.conversations
                clip: true
                spacing: Space.space2
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    required property var item
                    objectName: "conversation-thread-" + item.id
                    width: conversationList.width
                    enabled: page.mutableContext
                    Accessible.name: item.title + (item.status === "archived" ? qsTr(", archivé") : "")
                    contentItem: Column {
                        spacing: Space.space2
                        Text { width: parent.width; text: item.title; textFormat: Text.PlainText; color: Colors.textPrimary; elide: Text.ElideRight; font.pixelSize: Type.tableCell.pixelSize }
                        Text { width: parent.width; text: (item.status === "archived" ? qsTr("Archivé · ") : "") + new Date(item.updated_at).toLocaleDateString(Qt.locale(), Locale.ShortFormat); textFormat: Text.PlainText; color: Colors.textMuted; font.pixelSize: Type.metadata.pixelSize }
                    }
                    background: Rectangle { radius: Radius.radiusSm; color: item.id === Conversations.currentId ? Colors.stateSelected : "transparent" }
                    onClicked: { Conversations.selectConversation(item.id); historyDrawer.close(); }
                }
                Label {
                    anchors.centerIn: parent
                    width: parent.width
                    visible: conversationList.count === 0 && !Conversations.loading
                    text: Conversations.searchText.length ? qsTr("Aucun titre correspondant.") : qsTr("Aucun chat dans ce contexte.")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    color: Colors.textMuted
                }
            }
            AcpButton { Layout.fillWidth: true; label: qsTr("Nouveau chat"); iconName: "plus"; primary: true; manualEnabled: page.mutableContext; onTriggered: page.newChat() }
            AcpButton { Layout.fillWidth: true; label: qsTr("Fermer l’historique"); onTriggered: historyDrawer.close() }
        }
    }
    Dialog {
        id: renameDialog
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(page.width - Space.space5 * 2, 460)
        modal: true
        title: qsTr("Renommer le chat")
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: renameTitle.forceActiveFocus()
        onAccepted: Conversations.renameConversation(renameTitle.text)
        contentItem: AcpTextField { id: renameTitle; accessibleName: qsTr("Nouveau titre du chat"); onAccepted: renameDialog.accept() }
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
            AcpButton { label: qsTr("Copier l’export"); onTriggered: page.copyText(Conversations.exportText) }
        }
    }
}
