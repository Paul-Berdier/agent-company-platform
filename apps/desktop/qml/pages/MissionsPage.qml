import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    property bool creating: false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: qsTr("Missions")
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
            }
            Item { Layout.fillWidth: true }
            AcpButton {
                label: qsTr("Actualiser")
                manualEnabled: Missions.projectId.length > 0 && !Missions.busy
                onTriggered: Missions.refresh()
            }
            AcpButton {
                label: page.creating ? qsTr("Fermer le formulaire") : qsTr("Nouvelle mission")
                manualEnabled: Missions.canWrite
                primary: true
                onTriggered: page.creating = !page.creating
            }
        }
        Text {
            Layout.fillWidth: true
            text: Missions.projectId.length === 0 ? qsTr("Sélectionnez un projet pour lire ses missions.")
                : qsTr("Jusqu’à 500 missions récentes. L’arrêt, la relance et l’acceptation restent vérifiés par le serveur.")
            color: Colors.textMuted
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: !Missions.canWrite && Missions.projectId.length > 0 && !Missions.mutating && !Missions.pendingMutation
            text: qsTr("Lecture seule : droits d’écriture du projet absents ou encore inconnus.")
            color: Colors.textMuted
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: Missions.error.length > 0 || Missions.notice.length > 0
            text: Missions.error.length > 0 ? Missions.error : Missions.notice
            color: Missions.error.length > 0 ? Status.statusFailedForeground : Colors.textPrimary
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: Missions.pendingMutation
            Text {
                Layout.fillWidth: true
                text: Missions.mutating
                    ? qsTr("%1 : réponse du serveur en attente…").arg(Missions.pendingAction)
                    : qsTr("%1 : résultat incertain. La reprise conserve exactement la commande et sa clé. Aucune commande n’est rejouée hors ligne.").arg(Missions.pendingAction)
                textFormat: Text.PlainText
                color: Colors.textPrimary
                wrapMode: Text.WordWrap
            }
            RowLayout {
                AcpButton {
                    label: qsTr("Réessayer la même commande")
                    manualEnabled: Missions.canRetryPending
                    onTriggered: Missions.retryPending()
                }
                AcpButton {
                    label: qsTr("Abandonner le suivi…")
                    manualEnabled: !Missions.mutating
                    onTriggered: abandonDialog.open()
                }
            }
        }
        ScrollView {
            visible: page.creating
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(430, page.height * 0.65)
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: Space.space3
                AcpTextField { id: titleField; Layout.fillWidth: true; placeholder: qsTr("Titre de la mission — 300 caractères maximum") }
                TextArea {
                    id: objectiveField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Objectif")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    color: Colors.textPrimary
                }
                TextArea {
                    id: outcomeField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Résultat attendu")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    color: Colors.textPrimary
                }
                TextArea {
                    id: criteriaField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Critères d’acceptation — un par ligne")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    color: Colors.textPrimary
                }
                RowLayout {
                    Layout.fillWidth: true
                    AcpTextField { id: costField; Layout.fillWidth: true; text: "5"; placeholder: qsTr("Plafond EUR"); helperText: qsTr("Plafond de coût en EUR (point décimal)") }
                    AcpTextField { id: durationField; Layout.fillWidth: true; text: "900"; placeholder: qsTr("Durée maximale en secondes"); helperText: qsTr("Durée maximale, en secondes") }
                    ComboBox {
                        id: autonomyField
                        model: [qsTr("Supervisée"), qsTr("Bornée"), qsTr("Autonome")]
                        currentIndex: 1
                        Accessible.name: qsTr("Autonomie")
                    }
                }
                TextArea {
                    id: capabilitiesField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 50
                    placeholderText: qsTr("Capacités requises, facultatives — une par ligne (ex. local_process)")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    color: Colors.textPrimary
                }
                Text {
                    Layout.fillWidth: true
                    text: qsTr("La mission sera créée sans affectation ni ressource explicite. Elle attendra un worker compatible.")
                    color: Colors.textMuted
                    wrapMode: Text.WordWrap
                }
                AcpButton {
                    label: Missions.mutating ? qsTr("Création en cours…") : qsTr("Créer la mission")
                    primary: true
                    manualEnabled: Missions.canWrite
                    onTriggered: Missions.createMission({
                        title: titleField.text, objective: objectiveField.text,
                        expected_outcome: outcomeField.text, acceptance_criteria: criteriaField.text,
                        max_cost: costField.text, duration_seconds: durationField.text,
                        autonomy: ["supervised", "bounded", "autonomous"][autonomyField.currentIndex],
                        required_capabilities: capabilitiesField.text
                    })
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Space.space5
            ListView {
                id: missionList
                Layout.preferredWidth: Math.min(290, page.width * 0.3)
                Layout.fillHeight: true
                clip: true
                spacing: Space.space2
                model: Missions.missions
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    required property var item
                    width: missionList.width
                    text: (item.title || qsTr("Sans titre")) + "\n" + (item.status || qsTr("Inconnu"))
                    highlighted: item.id === Missions.selectedMissionId
                    Accessible.name: text
                    onClicked: Missions.selectMission(item.id)
                }
                Text {
                    anchors.fill: parent
                    anchors.margins: Space.space4
                    visible: missionList.count === 0
                    text: Missions.busy ? qsTr("Lecture des missions…") : qsTr("Aucune mission chargée.")
                    color: Colors.textMuted
                    wrapMode: Text.WordWrap
                }
            }
            RunPage { Layout.fillWidth: true; Layout.fillHeight: true }
        }
    }
    Dialog {
        id: abandonDialog
        anchors.centerIn: parent
        width: Math.min(500, page.width - 32)
        height: Math.min(280, page.height - 32)
        title: qsTr("Abandonner le suivi de la commande ?")
        modal: true
        standardButtons: Dialog.Cancel | Dialog.Ok
        contentItem: Text {
            text: qsTr("La commande a pu réussir sur le serveur. Abandonner le suivi ne l’annule pas et efface la clé conservée sur ce poste. Vérifiez les missions et tentatives avant une nouvelle action : vous risquez sinon un doublon.")
            textFormat: Text.PlainText
            color: Colors.textPrimary
            wrapMode: Text.WordWrap
        }
        onAccepted: Missions.abandonPending(true)
    }
    Connections {
        target: Missions
        function onContextReset() {
            page.creating = false;
            titleField.text = ""; objectiveField.text = ""; outcomeField.text = "";
            criteriaField.text = ""; capabilitiesField.text = "";
        }
        function onChanged() {
            if (Missions.notice === qsTr("Mission créée par le serveur.")) page.creating = false;
        }
    }
}
