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
                textFormat: Text.PlainText
                text: qsTr("Missions")
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
            }
            Item { Layout.fillWidth: true }
            AcpButton {
                objectName: "missionRefreshButton"
                label: qsTr("Actualiser")
                manualEnabled: Missions.projectId.length > 0 && !Missions.busy
                onTriggered: Missions.refresh()
            }
            AcpButton {
                objectName: "missionNewButton"
                label: page.creating ? qsTr("Fermer le formulaire") : qsTr("Nouvelle mission")
                manualEnabled: Missions.canWrite
                primary: true
                onTriggered: page.creating = !page.creating
            }
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: Missions.projectId.length === 0 ? qsTr("Sélectionnez un projet pour lire ses missions.")
                : qsTr("Jusqu’à 500 missions récentes. L’arrêt, la relance et l’acceptation restent vérifiés par le serveur.")
            color: Colors.textMuted
            wrapMode: Text.WordWrap
        }
        Text {
            textFormat: Text.PlainText
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
                AcpTextField { id: titleField; objectName: "missionTitleField"; Layout.fillWidth: true; placeholder: qsTr("Titre de la mission — 300 caractères maximum") }
                TextArea {
                    id: objectiveField
                    objectName: "missionObjectiveField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Objectif")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    color: Colors.textPrimary
                }
                TextArea {
                    id: outcomeField
                    objectName: "missionOutcomeField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Résultat attendu")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    color: Colors.textPrimary
                }
                TextArea {
                    id: criteriaField
                    objectName: "missionCriteriaField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 65
                    placeholderText: qsTr("Critères d’acceptation — un par ligne")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    color: Colors.textPrimary
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: qsTr("Exécuteur"); textFormat: Text.PlainText; color: Colors.textPrimary }
                    ComboBox {
                        id: executorField
                        objectName: "missionExecutorField"
                        Layout.fillWidth: true
                        model: [qsTr("Worker standard"), qsTr("Codex CLI"), qsTr("Claude Code"), qsTr("Équipe Claude + Codex")]
                        Accessible.name: qsTr("Exécuteur de la mission")
                        onActivated: {
                            if (currentIndex > 0) autonomyField.currentIndex = 0;
                            if (currentIndex === 2) workspaceAccess.currentIndex = 0;
                        }
                    }
                }
                RowLayout {
                    visible: executorField.currentIndex === 3
                    Label { text: qsTr("Tâches simultanées maximum"); textFormat: Text.PlainText; color: Colors.textPrimary }
                    SpinBox { id: agentConcurrency; objectName: "missionAgentConcurrencyField"; from: 1; to: 2; value: 2; editable: true }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: executorField.currentIndex > 0
                    Label { text: qsTr("Accès au projet"); textFormat: Text.PlainText; color: Colors.textPrimary }
                    ComboBox {
                        id: workspaceAccess
                        objectName: "missionWorkspaceAccessField"
                        model: executorField.currentIndex === 2 ? [qsTr("Lecture seule")] : [qsTr("Lecture seule"), qsTr("Lecture et écriture")]
                        Accessible.name: qsTr("Accès de l’exécuteur au projet")
                    }
                }
                Label {
                    Layout.fillWidth: true
                    visible: executorField.currentIndex > 0
                    text: executorField.currentIndex === 3
                        ? qsTr("L’équipe demande Claude et Codex en mode supervisé. L’accès en écriture concerne Codex ; Claude reste en lecture seule. Le worker doit annoncer les deux capacités et autoriser la racine de ce projet. Le serveur confirme les étapes et leur état réel.")
                        : qsTr("Une seule invocation de l’exécuteur, en mode supervisé. La ressource désigne le projet sélectionné ; sa racine doit être autorisée sur le worker. La disponibilité et les droits restent vérifiés par le serveur.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textMuted
                }
                CheckBox {
                    id: costLimited
                    objectName: "missionCostLimitedField"
                    checked: true
                    text: qsTr("Imposer un plafond de coût en EUR")
                }
                RowLayout {
                    Layout.fillWidth: true
                    AcpTextField { id: costField; objectName: "missionCostField"; Layout.fillWidth: true; enabled: costLimited.checked; text: "5"; placeholder: qsTr("Plafond EUR"); helperText: qsTr("Plafond de coût en EUR (point décimal)") }
                    AcpTextField { id: durationField; objectName: "missionDurationField"; Layout.fillWidth: true; text: "900"; placeholder: qsTr("Durée maximale en secondes"); helperText: qsTr("Durée maximale, en secondes") }
                    ComboBox {
                        id: autonomyField
                        objectName: "missionAutonomyField"
                        model: [qsTr("Supervisée"), qsTr("Bornée"), qsTr("Autonome")]
                        currentIndex: 1
                        enabled: executorField.currentIndex === 0
                        Accessible.name: qsTr("Autonomie")
                    }
                }
                RowLayout {
                    Label { text: qsTr("Appels d’outils maximum"); textFormat: Text.PlainText; color: Colors.textPrimary }
                    SpinBox {
                        id: toolLimit
                        objectName: "missionToolLimitField"
                        from: 0; to: 1000000; value: 10; editable: true
                        Accessible.name: qsTr("Nombre maximum d’appels d’outils")
                    }
                }
                Label {
                    Layout.fillWidth: true
                    text: costLimited.checked
                        ? qsTr("Le plafond monétaire est conservé. Un worker incapable de garantir ce plafond doit refuser l’exécution ; les CLI ne fournissent pas actuellement cette borne avant lancement.")
                        : qsTr("Aucun plafond monétaire n’est demandé pour cette mission. Le nombre d’appels d’outils et la durée restent bornés ; les politiques du projet continuent de s’appliquer.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textMuted
                }
                TextArea {
                    id: capabilitiesField
                    objectName: "missionCapabilitiesField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 50
                    placeholderText: qsTr("Autres capacités requises — une par ligne (ex. local_process)")
                    Accessible.name: placeholderText
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    color: Colors.textPrimary
                }
                Text {
                    objectName: "missionExtensionsPolicy"
                    Layout.fillWidth: true
                    text: executorField.currentIndex === 0
                        ? qsTr("La mission attendra un worker compatible avec les capacités demandées.")
                        : qsTr("L’exécuteur choisi est ajouté aux capacités. Les compétences approuvées et outils MCP HTTP sont limités aux liaisons du projet. Un serveur MCP stdio lié doit être désactivé pour cette mission.")
                    textFormat: Text.PlainText
                    color: Colors.textMuted
                    wrapMode: Text.WordWrap
                }
                AcpButton {
                    objectName: "missionCreateButton"
                    label: Missions.mutating ? qsTr("Création en cours…") : qsTr("Créer la mission")
                    primary: true
                    manualEnabled: Missions.canWrite
                    onTriggered: Missions.createMission({
                        title: titleField.text, objective: objectiveField.text,
                        expected_outcome: outcomeField.text, acceptance_criteria: criteriaField.text,
                        max_cost: costField.text, duration_seconds: durationField.text,
                        cost_limit_enabled: costLimited.checked, max_tool_calls: toolLimit.value,
                        executor: ["standard", "codex_cli", "claude_code", "multi_agent"][executorField.currentIndex],
                        max_concurrency: agentConcurrency.value,
                        workspace_access: workspaceAccess.currentIndex === 1 ? "write" : "read",
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
                    contentItem: Text {
                        text: (item.title || qsTr("Sans titre")) + "\n" + (item.status || qsTr("Inconnu"))
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textPrimary
                    }
                    highlighted: item.id === Missions.selectedMissionId
                    Accessible.name: item.title || qsTr("Sans titre")
                    onClicked: Missions.selectMission(item.id)
                }
                Text {
                    textFormat: Text.PlainText
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
            executorField.currentIndex = 0; workspaceAccess.currentIndex = 0;
            autonomyField.currentIndex = 1; costLimited.checked = true;
            costField.text = "5"; durationField.text = "900"; toolLimit.value = 10; agentConcurrency.value = 2;
        }
        function onChanged() {
            if (Missions.notice === qsTr("Mission créée par le serveur.")) page.creating = false;
        }
    }
}
