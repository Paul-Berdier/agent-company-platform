import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    function known(value) { return value === undefined || value === null ? qsTr("Inconnu") : String(value); }
    function limit(value) { return value === undefined || value === null ? qsTr("Non défini") : String(value); }
    function counter(totals, metric) {
        const value = totals[metric];
        if (value === undefined || value === null) return qsTr("Inconnu");
        return (totals.saturated_metrics || []).indexOf(metric) >= 0
            ? qsTr("au moins %1 (compteur saturé)").arg(String(value)) : String(value);
    }
    function cost(totals) {
        if (typeof totals.cost !== "number" || !isFinite(totals.cost)
            || typeof totals.currency !== "string" || !/^[A-Za-z]{3}$/.test(totals.currency))
            return qsTr("Inconnu");
        return String(totals.cost) + " " + totals.currency;
    }
    function consumption(totals) {
        return qsTr("Coût : %1\nJetons entrants : %2\nJetons sortants : %3\nAppels d’outils : %4\nRapports : %5 · Réservations en attente : %6")
            .arg(cost(totals)).arg(counter(totals, "tokens_input")).arg(counter(totals, "tokens_output"))
            .arg(counter(totals, "tool_calls")).arg(counter(totals, "reports")).arg(counter(totals, "pending_reservations"));
    }
    component Copy: Label {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Colors.textPrimary
    }
    Connections {
        target: Operations
        function onContextReset() {
            confirmation.close(); comment.text = "";
        }
    }
    Dialog {
        id: confirmation
        property string action: ""
        property string recordId: ""
        property string recordTitle: ""
        property bool enableValue: false
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(560, parent.width - 32)
        modal: true
        title: action === "APPROVED" ? qsTr("Confirmer l’autorisation")
             : action === "REJECTED" ? qsTr("Confirmer le refus")
             : action === "alert" ? qsTr("Acquitter l’alerte")
             : enableValue ? qsTr("Activer l’automation") : qsTr("Mettre l’automation en pause")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: ColumnLayout {
            Copy { text: confirmation.recordTitle }
            Copy {
                text: confirmation.action === "APPROVED"
                    ? qsTr("La demande autorise l’effet et la portée décrits. La décision sera enregistrée.")
                    : confirmation.action === "automation" && confirmation.enableValue
                        ? qsTr("Les prochaines échéances pourront créer des missions supervisées selon les limites affichées.")
                        : qsTr("Cette action sera enregistrée sur le serveur.")
            }
            TextArea {
                id: comment
                Layout.fillWidth: true
                visible: confirmation.action !== "automation"
                placeholderText: confirmation.action === "alert" ? qsTr("Commentaire — 500 caractères maximum") : qsTr("Commentaire — 2 000 caractères maximum")
                textFormat: Text.PlainText
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                Accessible.name: qsTr("Commentaire de la décision")
            }
        }
        onAccepted: {
            if (action === "alert") Operations.acknowledgeAlert(recordId, comment.text);
            else if (action === "automation") Operations.setAutomationEnabled(recordId, enableValue);
            else Operations.decideApproval(recordId, action, comment.text);
        }
    }
    function confirm(action, id, title, enable) {
        confirmation.action = action; confirmation.recordId = id;
        confirmation.recordTitle = title; confirmation.enableValue = !!enable;
        comment.text = ""; confirmation.open();
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space3
        RowLayout {
            Layout.fillWidth: true
            Copy { text: qsTr("Opérations"); font.pixelSize: 24; font.bold: true }
            BusyIndicator { running: Operations.busy; visible: running }
            AcpButton {
                label: qsTr("Actualiser")
                manualEnabled: Operations.projectId.length > 0 && !Operations.busy && !Operations.mutating
                onTriggered: Operations.refresh()
            }
        }
        Copy { visible: Operations.projectId.length === 0; text: qsTr("Sélectionnez un projet.") }
        Copy { visible: Operations.error.length > 0; text: Operations.error; Accessible.role: Accessible.AlertMessage }
        Copy { visible: Operations.notice.length > 0; text: Operations.notice }
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: qsTr("Approbations") }
            TabButton { text: qsTr("Alertes") }
            TabButton { text: qsTr("Budgets") }
            TabButton { text: qsTr("Automations") }
        }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                Copy { text: Operations.statuses.approvals || qsTr("Approbations non chargées.") }
                Copy { text: qsTr("Les décisions nécessitent le rôle propriétaire du projet, de l’espace ou de la plateforme.") }
                ListView {
                    id: approvalsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: Operations.approvals
                    clip: true
                    spacing: 8
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Frame {
                        id: approval
                        required property var item
                        width: approvalsList.width - 16
                        implicitHeight: approvalContent.implicitHeight + 24
                        ColumnLayout {
                            id: approvalContent
                            width: parent.width
                            Copy { text: String(approval.item.action) + " · " + String(approval.item.target || ""); font.bold: true }
                            Copy { text: page.known(approval.item.reason) }
                            Copy { text: qsTr("Conséquences : %1").arg((approval.item.consequences || []).join("\n")) }
                            Copy { text: qsTr("Expiration : %1\nDemandée par : %2").arg(page.known(approval.item.expires_at)).arg(page.known(approval.item.requested_by)) }
                            Copy { text: qsTr("Portée :\n%1\nEmpreinte :\n%2").arg(Operations.describe(approval.item.scope)).arg(Operations.describe(approval.item.footprint)) }
                            RowLayout {
                                AcpButton {
                                    label: qsTr("Autoriser…"); manualEnabled: Operations.canDecide
                                    onTriggered: page.confirm("APPROVED", String(approval.item.id), String(approval.item.action) + " : " + String(approval.item.target || ""), false)
                                }
                                AcpButton {
                                    label: qsTr("Refuser…"); manualEnabled: Operations.canDecide
                                    onTriggered: page.confirm("REJECTED", String(approval.item.id), String(approval.item.action) + " : " + String(approval.item.target || ""), false)
                                }
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Copy { text: Operations.statuses.alerts || qsTr("Alertes non chargées.") }
                Copy { text: qsTr("Alertes ouvertes de votre boîte personnelle, selon vos préférences serveur. Acquittement : rôle membre minimum.") }
                ListView {
                    id: alertsList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: Operations.alerts
                    clip: true
                    spacing: 8
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Frame {
                        id: alert
                        required property var item
                        width: alertsList.width - 16
                        implicitHeight: alertContent.implicitHeight + 24
                        ColumnLayout {
                            id: alertContent
                            width: parent.width
                            Copy { text: page.known(alert.item.title); font.bold: true }
                            Copy { text: page.known(alert.item.severity) + " · " + page.known(alert.item.kind) + " · " + page.known(alert.item.created_at) }
                            Copy { text: page.known(alert.item.detail) }
                            AcpButton {
                                label: qsTr("Acquitter…"); manualEnabled: Operations.canManage
                                onTriggered: page.confirm("alert", String(alert.item.id), String(alert.item.title), false)
                            }
                        }
                    }
                }
            }

            ScrollView {
                id: budgetScroll
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: budgetScroll.availableWidth
                    spacing: Space.space4
                    Copy { text: Operations.statuses.usage || qsTr("Consommation non chargée."); font.bold: true }
                    Copy {
                        property var totals: Operations.budgetUsage.totals || ({})
                        text: page.consumption(totals)
                    }
                    Copy {
                        property var totals: Operations.budgetUsage.totals || ({})
                        text: totals.estimated === true ? qsTr("Cette consommation contient des estimations.") : qsTr("Une mesure absente reste inconnue ; elle n’est pas affichée comme zéro.")
                    }
                    Copy { text: qsTr("Ces totaux incluent les réservations en attente. Aucune conversion de devise n’est effectuée ; un coût global mêlant plusieurs devises reste inconnu.") }
                    Repeater {
                        model: Operations.budgetUsage.providers || []
                        delegate: ColumnLayout {
                            id: providerUsage
                            required property var modelData
                            readonly property var totals: modelData.totals || ({})
                            Layout.fillWidth: true
                            Copy { text: qsTr("Consommation · %1").arg(page.known(providerUsage.modelData.provider)); font.bold: true }
                            Copy { text: page.consumption(providerUsage.totals) }
                            Copy { visible: providerUsage.totals.estimated === true; text: qsTr("Cette consommation contient des estimations.") }
                        }
                    }
                    Copy { text: Operations.statuses.policy || qsTr("Politique non chargée."); font.bold: true }
                    Copy {
                        property var daily: Operations.budgetPolicy.daily_budget
                        text: !Operations.budgetPolicy.project_id ? qsTr("Plafonds indisponibles.")
                            : !daily ? qsTr("Aucun plafond journalier de projet défini.")
                            : qsTr("Plafond journalier : coût %1 %2 · jetons %3 · outils %4")
                                .arg(page.limit(daily.max_cost)).arg(page.known(daily.currency)).arg(page.limit(daily.max_tokens)).arg(page.limit(daily.max_tool_calls))
                    }
                    Copy { text: qsTr("Fuseau comptable : %1").arg(page.known(Operations.budgetPolicy.timezone)) }
                    Repeater {
                        model: Operations.budgetPolicy.provider_budgets || []
                        delegate: Copy {
                            required property var modelData
                            text: qsTr("Fournisseur %1 : coût %2 %3 · jetons %4 · outils %5")
                                .arg(modelData.provider).arg(page.limit(modelData.budget.max_cost)).arg(page.known(modelData.budget.currency))
                                .arg(page.limit(modelData.budget.max_tokens)).arg(page.limit(modelData.budget.max_tool_calls))
                        }
                    }
                    Copy { text: qsTr("Modifier les limites opérationnelles. Les plafonds journaliers, fournisseurs et le fuseau restent ceux lus sur le serveur.") }
                    RowLayout {
                        Copy { text: qsTr("Missions simultanées (1–100)") }
                        SpinBox { id: maxConcurrent; from: 1; to: 100; value: Operations.budgetPolicy.max_concurrent_missions || 1; editable: true; enabled: !!Operations.budgetPolicy.project_id }
                    }
                    RowLayout {
                        Copy { text: qsTr("Relances par mission (0–20)") }
                        SpinBox { id: maxRetries; from: 0; to: 20; value: Operations.budgetPolicy.max_retries_per_mission === undefined ? 0 : Operations.budgetPolicy.max_retries_per_mission; editable: true; enabled: !!Operations.budgetPolicy.project_id }
                    }
                    RowLayout {
                        Copy { text: qsTr("Agents créés par tentative (1–32)") }
                        SpinBox { id: maxAgents; from: 1; to: 32; value: Operations.budgetPolicy.max_spawned_agents_per_run || 1; editable: true; enabled: !!Operations.budgetPolicy.project_id }
                    }
                    AcpButton {
                        label: qsTr("Enregistrer les limites")
                        manualEnabled: Operations.canManage && !!Operations.budgetPolicy.project_id
                        onTriggered: Operations.saveBudgetPolicy(maxConcurrent.value, maxRetries.value, maxAgents.value)
                    }
                }
            }

            ScrollView {
                id: automationScroll
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: automationScroll.availableWidth
                    spacing: Space.space4
                    Copy { text: Operations.statuses.automations || qsTr("Automations non chargées.") }
                    Repeater {
                        model: Operations.automations
                        delegate: Frame {
                            id: routine
                            required property var item
                            Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width
                                Copy { text: page.known(routine.item.name) + (routine.item.enabled ? qsTr(" · Active") : qsTr(" · En pause")); font.bold: true }
                                Copy { text: routine.item.schedule ? String(routine.item.schedule.kind) + " " + String(routine.item.schedule.expression) + " · " + String(routine.item.schedule.timezone) : qsTr("Calendrier inconnu") }
                                Copy { text: qsTr("Prochaine échéance : %1").arg(page.known(routine.item.next_run_at)) }
                                RowLayout {
                                    AcpButton {
                                        label: routine.item.enabled ? qsTr("Mettre en pause…") : qsTr("Activer…")
                                        manualEnabled: Operations.canManage
                                        onTriggered: page.confirm("automation", String(routine.item.id), String(routine.item.name), !routine.item.enabled)
                                    }
                                    AcpButton {
                                        label: qsTr("Dernières exécutions")
                                        manualEnabled: !Operations.busy && !Operations.mutating
                                        onTriggered: Operations.selectAutomation(String(routine.item.id))
                                    }
                                }
                            }
                        }
                    }
                    Copy { visible: !!Operations.selectedAutomation.id; text: qsTr("Exécutions · %1").arg(page.known(Operations.selectedAutomation.name)); font.bold: true }
                    Copy { visible: !!Operations.selectedAutomation.id; text: Operations.statuses.runs || qsTr("Historique non chargé.") }
                    Repeater {
                        model: Operations.automationRuns
                        delegate: Copy {
                            required property var item
                            text: page.known(item.scheduled_for) + " · " + page.known(item.outcome)
                                + " · " + (item.completion_status ? String(item.completion_status) : qsTr("Achèvement non renseigné"))
                                + "\n" + String(item.detail || "")
                        }
                    }
                    Copy { text: qsTr("Créer une automation en pause"); font.pixelSize: 18; font.bold: true }
                    Copy { text: qsTr("Mission supervisée, sans affectation imposée, une exécution simultanée, sans rattrapage. Le coût et les jetons n’ont pas de plafond ici ; le plafond d’outils et la durée sont obligatoires.") }
                    TextField { id: routineName; Layout.fillWidth: true; placeholderText: qsTr("Nom de l’automation"); maximumLength: 200; Accessible.name: placeholderText }
                    TextArea { id: objective; Layout.fillWidth: true; placeholderText: qsTr("Objectif de la mission"); textFormat: Text.PlainText; wrapMode: TextEdit.Wrap; Accessible.name: placeholderText }
                    TextArea { id: expected; Layout.fillWidth: true; placeholderText: qsTr("Résultat attendu"); textFormat: Text.PlainText; wrapMode: TextEdit.Wrap; Accessible.name: placeholderText }
                    TextArea { id: criteria; Layout.fillWidth: true; placeholderText: qsTr("Critères d’acceptation — un par ligne"); textFormat: Text.PlainText; wrapMode: TextEdit.Wrap; Accessible.name: placeholderText }
                    RowLayout {
                        ComboBox { id: scheduleKind; model: [qsTr("Intervalle en minutes"), qsTr("Cron — cinq champs")]; Layout.preferredWidth: 220 }
                        TextField { id: expression; Layout.fillWidth: true; text: "60"; placeholderText: scheduleKind.currentIndex === 0 ? qsTr("Exemple : 60") : qsTr("Exemple : 0 9 * * 1-5"); Accessible.name: qsTr("Expression de planification") }
                    }
                    TextField { id: timezone; Layout.fillWidth: true; text: "Europe/Paris"; placeholderText: qsTr("Fuseau IANA"); Accessible.name: qsTr("Fuseau de planification") }
                    RowLayout {
                        Copy { text: qsTr("Durée maximale (secondes)") }
                        SpinBox { id: duration; from: 1; to: 31536000; value: 900; editable: true }
                    }
                    RowLayout {
                        Copy { text: qsTr("Appels d’outils maximum (0 interdit tout appel)") }
                        SpinBox { id: toolsLimit; from: 0; to: 1000000; value: 30; editable: true }
                    }
                    AcpButton {
                        label: qsTr("Créer en pause")
                        manualEnabled: Operations.canManage
                        onTriggered: Operations.createAutomation({name: routineName.text, objective: objective.text,
                            expectedOutcome: expected.text, criteria: criteria.text,
                            scheduleKind: scheduleKind.currentIndex === 0 ? "interval" : "cron",
                            expression: expression.text, timezone: timezone.text,
                            durationSeconds: duration.value, maxToolCalls: toolsLimit.value})
                    }
                }
            }
        }
    }
}
