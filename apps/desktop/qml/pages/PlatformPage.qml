import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    Component.onCompleted: Platform.active = true
    Component.onDestruction: Platform.active = false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4
        RowLayout {
            Layout.fillWidth: true
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Agents et fournisseurs")
                subtitle: qsTr("Inventaire accessible à votre session · état déclaré par le serveur")
            }
            BusyIndicator { running: Platform.loading; visible: running; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
            AcpButton { label: qsTr("Actualiser"); manualEnabled: Platform.available && !Platform.loading && !Platform.busy; onTriggered: Platform.refresh() }
        }
        Label { Layout.fillWidth: true; text: Platform.error; visible: text.length > 0; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Status.statusFailedForeground }
        Label { Layout.fillWidth: true; text: qsTr("Connectez-vous pour consulter la plateforme."); visible: !Platform.available; textFormat: Text.PlainText; color: Colors.textMuted }
        Repeater {
            model: Platform.providers
            delegate: Rectangle {
                required property var item
                Layout.fillWidth: true
                implicitHeight: providerText.implicitHeight + 24
                color: Colors.surfacePanel
                border.color: Colors.borderDefault
                radius: Radius.radiusMd
                Label {
                    id: providerText
                    anchors.fill: parent
                    anchors.margins: 12
                    text: item.name + " — " + item.state + (item.checked_at ? "\n" + qsTr("Vérifié : ") + item.checked_at : "")
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    color: Colors.textPrimary
                }
            }
        }
        TabBar {
            id: inventoryTabs
            Layout.fillWidth: true
            TabButton { text: qsTr("Agents (%1)").arg(Platform.agents.count) }
            TabButton { text: qsTr("Workers (%1)").arg(Platform.workers.count) }
        }
        Label {
            Layout.fillWidth: true
            visible: inventoryTabs.currentIndex === 1 && Platform.workersNotice.length > 0
            text: Platform.workersNotice
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textMuted
        }
        ListView {
            id: inventory
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: inventoryTabs.currentIndex === 0 ? Platform.agents : Platform.workers
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var item
                width: inventory.width
                implicitHeight: row.implicitHeight + 24
                color: Colors.surfacePanel
                border.color: Colors.borderDefault
                radius: Radius.radiusMd
                ColumnLayout {
                    id: row
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    Label { Layout.fillWidth: true; text: item.name + " — " + (item.status || qsTr("Inconnu")); textFormat: Text.PlainText; wrapMode: Text.Wrap; font.bold: true; color: Colors.textPrimary }
                    Label {
                        Layout.fillWidth: true
                        text: inventoryTabs.currentIndex === 0
                            ? qsTr("Rôle : %1 · Module : %2\nEspace : %3 · Équipe : %4").arg(item.role_id || qsTr("Inconnu")).arg(item.module || qsTr("Inconnu")).arg(item.workspace_id || qsTr("Inconnu")).arg(item.team_id || qsTr("Aucune"))
                            : qsTr("Exécutions : %1 / %2 · %3\nDernier contact : %4").arg(item.active_runs === undefined ? "?" : item.active_runs).arg(item.max_concurrency === undefined ? "?" : item.max_concurrency).arg(item.simulation ? qsTr("Simulation") : qsTr("Exécution réelle déclarée")).arg(item.last_seen_at || qsTr("Inconnu"))
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Colors.textSecondary
                    }
                    Label { Layout.fillWidth: true; text: qsTr("Capacités : %1").arg(item.capabilities ? item.capabilities.join(", ") : qsTr("Inconnues")); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Colors.textMuted }
                }
            }
            Label {
                anchors.centerIn: parent
                visible: inventory.count === 0 && !Platform.loading
                text: qsTr("Aucun élément accessible dans cet inventaire.")
                textFormat: Text.PlainText
                color: Colors.textMuted
            }
        }
    }
}
