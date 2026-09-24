// État réel de connexion ; les détails techniques restent accessibles aux diagnostics.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime

Rectangle {
    id: statusBar
    color: Colors.surfaceSidebar
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Space.space5
        anchors.rightMargin: Space.space5
        spacing: Space.space4
        Rectangle {
            width: 5; height: 5; radius: 3
            color: Health.linkStatus === LinkStatus.Online && Session.state === SessionStatus.Connected
                ? Colors.accentPrimary : Colors.textMuted
        }
        Text {
            text: Session.state === SessionStatus.Offline ? Session.stateLabel : Health.linkStatusLabel
            textFormat: Text.PlainText
            color: Colors.textSecondary
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
        Text {
            Layout.maximumWidth: statusBar.width * 0.24
            text: Shell.serverUrlLabel
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
        Text {
            Layout.fillWidth: true
            text: Shell.lastNotice
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: Colors.textSecondary
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
            HoverHandler { id: noticeHover }
            ToolTip {
                id: noticeTip
                visible: noticeHover.hovered && Shell.lastNotice.length > 0
                text: Shell.lastNotice
                contentItem: Text { text: noticeTip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
            }
        }
        Text {
            text: Session.userDisplayName || Session.stateLabel
            textFormat: Text.PlainText
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
            elide: Text.ElideRight
            Layout.maximumWidth: statusBar.width * 0.18
            HoverHandler { id: stateHover }
            ToolTip {
                id: stateTip
                visible: stateHover.hovered
                text: Shell.statusSummary
                contentItem: Text { text: stateTip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
            }
        }
    }
}
