import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4
        RowLayout {
            Layout.fillWidth: true
            Label { textFormat: Text.PlainText; text: qsTr("Studio en direct"); font.pixelSize: Type.pageTitle.pixelSize; color: Colors.textPrimary }
            Item { Layout.fillWidth: true }
            AcpButton { label: qsTr("Choisir une mission"); onTriggered: Navigation.setCurrentRoute("missions") }
            AcpButton { label: qsTr("Livrables"); manualEnabled: Workspace.projectId.length > 0; onTriggered: Navigation.setCurrentRoute("library") }
        }
        Label {
            textFormat: Text.PlainText
            visible: Missions.selectedRunId.length === 0
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Colors.textSecondary
            text: qsTr("Ouvrez une mission pour suivre sa tentative, ses événements, ses tests et ses preuves. Le worker et les événements sont ceux rapportés par l’API.")
        }
        Label {
            visible: Missions.selectedRunId.length > 0
            text: qsTr("Worker : %1 · Fournisseur : %2").arg(Missions.run.worker_id || qsTr("Inconnu")).arg(Missions.run.provider || qsTr("Inconnu"))
            textFormat: Text.PlainText
            color: Colors.textSecondary
        }
        RunPage { Layout.fillWidth: true; Layout.fillHeight: true }
    }
}
