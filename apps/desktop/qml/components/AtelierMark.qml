import QtQuick
import Acp.Design
// Emblème original ACP : un noyau et deux ailes géométriques.
Item {
    id: mark
    property color ink: Colors.accentPrimary
    implicitWidth: 40
    implicitHeight: 32
    Accessible.ignored: true
    Repeater {
        model: [[0,1,2,1], [1,2,2,1], [2,3,2,1], [3,1,4,4], [6,3,2,1], [7,2,2,1], [8,1,2,1]]
        Rectangle {
            required property var modelData
            x: modelData[0] * mark.width / 10; y: modelData[1] * mark.height / 7
            width: modelData[2] * mark.width / 10; height: modelData[3] * mark.height / 7
            color: mark.ink
        }
    }
    Rectangle {
        x: mark.width * 0.4; y: mark.height * 2 / 7
        width: mark.width / 5; height: mark.height * 2 / 7
        color: Colors.surfaceCanvas
    }
}
