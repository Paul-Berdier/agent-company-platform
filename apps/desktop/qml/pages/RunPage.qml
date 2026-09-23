import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    readonly property var details: Missions.run
    readonly property var mission: Missions.mission
    property string previousRunId: ""

    ColumnLayout {
        anchors.fill: parent
        spacing: Space.space3
        Text {
            Layout.fillWidth: true
            text: page.mission.title || qsTr("Sélectionnez une mission")
            textFormat: Text.PlainText
            color: Colors.textPrimary
            font.family: Type.panelTitle.family
            font.pixelSize: Type.panelTitle.pixelSize
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            visible: Missions.selectedMissionId.length > 0
            ComboBox {
                id: attempts
                Layout.fillWidth: true
                model: Missions.runs
                textRole: "item"
                displayText: Missions.selectedRunId.length > 0
                    ? qsTr("Tentative %1 — %2").arg(page.details.attempt_number || "?").arg(page.details.status || qsTr("Inconnu"))
                    : qsTr("Tentatives")
                Accessible.name: qsTr("Tentative sélectionnée")
                contentItem: Text {
                    text: attempts.displayText
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                delegate: ItemDelegate {
                    id: attemptChoice
                    required property var item
                    required property int index
                    width: attempts.width
                    text: qsTr("Tentative %1 — %2").arg(item.attempt_number).arg(item.status)
                    contentItem: Text {
                        text: attemptChoice.text
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        elide: Text.ElideRight
                    }
                    onClicked: { Missions.selectRun(item.id); attempts.popup.close(); }
                }
                onActivated: function(index) { Missions.selectRun(Missions.runs.get(index).id); }
            }
            AcpButton {
                label: qsTr("Relire")
                manualEnabled: !Missions.busy
                onTriggered: Missions.refreshDetail()
            }
        }
        Text {
            Layout.fillWidth: true
            visible: Missions.selectedRunId.length > 0
            text: Missions.streamStatus + " · " + qsTr("Validation technique : %1 · Acceptation : %2")
                .arg(page.details.technical_validation ? page.details.technical_validation.status : qsTr("Inconnue"))
                .arg(page.details.user_acceptance ? page.details.user_acceptance.status : qsTr("Inconnue"))
            textFormat: Text.PlainText
            color: Colors.textMuted
            wrapMode: Text.WordWrap
        }
        RowLayout {
            visible: Missions.selectedRunId.length > 0
            AcpButton { label: qsTr("Demander l’arrêt"); manualEnabled: Missions.canStop; onTriggered: stopDialog.open() }
            AcpButton { label: qsTr("Relancer"); manualEnabled: Missions.canRetry; onTriggered: retryDialog.open() }
            AcpButton { label: qsTr("Accepter"); manualEnabled: Missions.canAccept; onTriggered: { acceptanceDialog.decision = "accepted"; acceptanceDialog.open(); } }
            AcpButton { label: qsTr("Rejeter"); manualEnabled: Missions.canAccept; onTriggered: { acceptanceDialog.decision = "rejected"; acceptanceDialog.open(); } }
        }
        Text {
            Layout.fillWidth: true
            visible: Missions.error.length > 0 || Missions.notice.length > 0
            text: Missions.error.length > 0 ? Missions.error : Missions.notice
            textFormat: Text.PlainText
            color: Missions.error.length > 0 ? Status.statusFailedForeground : Colors.textPrimary
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: Missions.selectedRunId.length > 0
            text: qsTr("Arrêt et relance concernent la tentative courante. L’acceptation exige une réussite technique ; une réussite doit être rejetée avant relance.")
            color: Colors.textMuted
            wrapMode: Text.WordWrap
        }
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: qsTr("Détail") }
            TabButton { text: qsTr("Journal") }
            TabButton { text: qsTr("Preuves") }
            TabButton { text: qsTr("Tests") }
            TabButton { text: qsTr("Commentaires") }
        }
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabs.currentIndex
            ScrollView {
                clip: true
                TextArea {
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    color: Colors.textPrimary
                    text: Missions.selectedRunId.length === 0 ? qsTr("Aucune tentative sélectionnée.")
                        : qsTr("Objectif\n") + (page.mission.objective || "")
                          + qsTr("\n\nRésultat attendu\n") + (page.mission.expected_outcome || "")
                          + qsTr("\n\nCritères\n") + (page.mission.acceptance_criteria || []).join("\n")
                          + qsTr("\n\nPlan\n") + Missions.displayJson(page.details.plan)
                          + qsTr("\nRésultat\n") + Missions.displayJson(page.details.result)
                          + qsTr("\nLogs de la tentative\n") + Missions.displayJson(page.details.logs)
                }
            }
            ColumnLayout {
                Text {
                    text: qsTr("Derniers 1 000 événements reçus. Reprise et repli par interrogation sont assurés par le service de flux.")
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: Colors.textMuted
                }
                ListView {
                    id: journal
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: Missions.events
                    clip: true
                    ScrollBar.vertical: ScrollBar {}
                    delegate: TextArea {
                        required property var item
                        width: journal.width
                        readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText; color: Colors.textPrimary
                        text: (item.type || qsTr("Événement")) + " · " + (item.occurred_at || "") + "\n" + Missions.displayJson(item.payload)
                    }
                }
            }
            ListView {
                id: proofs
                model: Missions.evidence
                clip: true
                ScrollBar.vertical: ScrollBar {}
                delegate: TextArea {
                    required property var item
                    width: proofs.width
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText; color: Colors.textPrimary
                    text: (item.kind || "") + " · " + (item.summary || "") + "\n" + Missions.displayJson(item)
                }
                Text { visible: proofs.count === 0; text: qsTr("Aucune preuve reçue pour cette tentative."); color: Colors.textMuted; wrapMode: Text.WordWrap; width: parent.width }
            }
            ColumnLayout {
                Text { text: Missions.testsStatus; textFormat: Text.PlainText; color: Colors.textMuted; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                Text {
                    text: Missions.testReport.totals ? Missions.displayJson(Missions.testReport.totals) : ""
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
                ListView {
                    id: cases
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: Missions.testCases; clip: true
                    ScrollBar.vertical: ScrollBar {}
                    delegate: TextArea {
                        required property var item
                        width: cases.width
                        readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText; color: Colors.textPrimary
                        text: (item.title || "") + " · " + (item.status || "") + " · " + (item.outcome || "")
                            + "\n" + Missions.displayJson(item)
                    }
                }
            }
            ColumnLayout {
                ListView {
                    id: comments
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: Missions.comments; clip: true
                    ScrollBar.vertical: ScrollBar {}
                    delegate: TextArea {
                        required property var item
                        width: comments.width
                        readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText; color: Colors.textPrimary
                        text: (item.created_at || "") + " · " + (item.author_user_id || "") + "\n" + (item.body || "")
                    }
                }
                TextArea {
                    id: commentField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 70
                    placeholderText: qsTr("Commentaire pour la tentative sélectionnée")
                    textFormat: TextEdit.PlainText
                    Accessible.name: placeholderText
                    color: Colors.textPrimary
                    wrapMode: TextEdit.Wrap
                }
                AcpButton { label: qsTr("Envoyer le commentaire"); manualEnabled: Missions.canWrite && Missions.selectedRunId.length > 0 && commentField.text.trim().length > 0; onTriggered: Missions.addComment(commentField.text) }
            }
        }
    }
    Dialog {
        id: stopDialog
        property string runId: ""
        onOpened: runId = Missions.selectedRunId
        anchors.centerIn: parent
        modal: true
        title: qsTr("Arrêter la tentative courante ?")
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: qsTr("L’arrêt est une demande au worker ; il peut prendre du temps.") }
        onAccepted: { if (runId === Missions.selectedRunId) Missions.stopMission(); }
    }
    Dialog {
        id: retryDialog
        property string runId: ""
        onOpened: runId = Missions.selectedRunId
        anchors.centerIn: parent
        modal: true
        width: Math.min(440, page.width)
        title: qsTr("Créer une nouvelle tentative")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: TextArea { id: retryReason; placeholderText: qsTr("Motif obligatoire"); textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; Accessible.name: placeholderText }
        onAccepted: { if (runId === Missions.selectedRunId) Missions.retryMission(retryReason.text); }
    }
    Dialog {
        id: acceptanceDialog
        property string decision: ""
        property string runId: ""
        onOpened: runId = Missions.selectedRunId
        anchors.centerIn: parent
        modal: true
        width: Math.min(440, page.width)
        title: decision === "accepted" ? qsTr("Accepter le résultat") : qsTr("Rejeter le résultat")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: TextArea { id: acceptanceComment; placeholderText: qsTr("Commentaire de décision, facultatif"); textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; Accessible.name: placeholderText }
        onAccepted: { if (runId === Missions.selectedRunId) Missions.decideAcceptance(decision, acceptanceComment.text); }
    }
    Connections {
        target: Missions
        function onChanged() {
            if (page.previousRunId !== Missions.selectedRunId) {
                page.previousRunId = Missions.selectedRunId;
                commentField.text = ""; retryReason.text = ""; acceptanceComment.text = "";
            }
            if (stopDialog.opened && stopDialog.runId !== Missions.selectedRunId) stopDialog.close();
            if (retryDialog.opened && retryDialog.runId !== Missions.selectedRunId) retryDialog.close();
            if (acceptanceDialog.opened && acceptanceDialog.runId !== Missions.selectedRunId) acceptanceDialog.close();
        }
    }
}
