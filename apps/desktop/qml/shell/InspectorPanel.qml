// Métadonnées d'une sélection réelle. Les valeurs restent du texte brut copiable.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Rectangle {
    id: inspector
    property string heading: qsTr("Détails")
    property var fields: []
    property string actionLabel: ""
    property string actionRoute: ""
    color: Colors.surfacePanel
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space6
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: inspector.heading
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.panelTitle.family
                font.pixelSize: Type.panelTitle.pixelSize
                font.weight: Type.panelTitle.weight
                elide: Text.ElideRight
            }
            AcpButton {
                objectName: "shell-close-inspector"
                label: ""; iconName: "close"
                Accessible.name: qsTr("Fermer les détails")
                onTriggered: Shell.inspectorVisible = false
            }
        }
        ScrollView {
            id: fieldScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: fieldScroll.availableWidth
                spacing: Space.space6
                Repeater {
                    model: inspector.fields
                    delegate: Column {
                        required property var modelData
                        width: parent.width
                        spacing: Space.space2
                        Text {
                            width: parent.width
                            text: modelData.label
                            textFormat: Text.PlainText
                            color: Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                        TextEdit {
                            width: parent.width
                            text: String(modelData.value === undefined || modelData.value === null || modelData.value === ""
                                ? qsTr("Non renseigné") : modelData.value)
                            textFormat: TextEdit.PlainText
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            color: Colors.textPrimary
                            selectionColor: Colors.accentMuted
                            font.family: Type.tableCell.family
                            font.pixelSize: Type.tableCell.pixelSize
                            Accessible.name: modelData.label
                        }
                    }
                }
            }
        }
        AcpButton {
            Layout.fillWidth: true
            visible: inspector.actionRoute.length > 0
            label: inspector.actionLabel
            onTriggered: Navigation.setCurrentRoute(inspector.actionRoute)
        }
    }
}
