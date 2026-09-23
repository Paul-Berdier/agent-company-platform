// État vide.
//
// Il dit TROIS choses : ce qui serait affiché ici, pourquoi ce n'est pas affiché, et
// quelle action est possible. Il ne dit jamais « tout va bien » et ne convertit jamais
// une absence en réussite.

import QtQuick
import QtQuick.Layouts
import Acp.Design
import Acp.Controls

Item {
    id: state

    property string title: ""
    property string body: ""
    property string actionLabel: ""
    property string actionCommandId: ""

    signal actionTriggered()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - Space.space10 * 2, Type.measureProse)
        spacing: Space.space5

        Text {
            Layout.fillWidth: true
            text: state.title
            textFormat: Text.PlainText
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            color: Colors.textPrimary
            font.family: Type.emptyStateTitle.family
            font.pixelSize: Type.emptyStateTitle.pixelSize
            font.weight: Type.emptyStateTitle.weight
            font.letterSpacing: Type.emptyStateTitle.letterSpacing
        }

        Text {
            Layout.fillWidth: true
            visible: state.body.length > 0
            text: state.body
            textFormat: Text.PlainText
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            lineHeight: Type.prose.lineHeight
            lineHeightMode: Text.FixedHeight
            color: Colors.textSecondary
            font.family: Type.prose.family
            font.pixelSize: Type.prose.pixelSize
        }

        AcpButton {
            Layout.alignment: Qt.AlignHCenter
            visible: state.actionLabel.length > 0
            label: state.actionLabel
            commandId: state.actionCommandId
            onTriggered: state.actionTriggered()
        }
    }
}
