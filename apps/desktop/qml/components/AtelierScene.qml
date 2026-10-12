import QtQuick
import QtQuick.Window
import Acp.Design
// Illustration d'ambiance, jamais une représentation de l'activité des agents.
Item {
    id: scene
    implicitWidth: 480
    implicitHeight: 240
    property url imageSource: "qrc:/atelier/atelier.png"
    Accessible.ignored: true
    // Respiration lumineuse discrète : aucun déplacement, aucun état métier.
    // La propriété visible de l'Item inclut la visibilité héritée de la page.
    readonly property bool ambientMotionAllowed: Colors.isPixel && !Motion.reduced
        && scene.visible && scene.opacity > 0 && scene.width > 0 && scene.height > 0
        && scene.Window.window !== null && scene.Window.window.visible
        && scene.Window.window.active && scene.Window.window.visibility !== Window.Minimized
    property real ambientOpacity: 1.0

    SequentialAnimation {
        running: scene.ambientMotionAllowed
        loops: Animation.Infinite
        onRunningChanged: if (!running) scene.ambientOpacity = 1.0
        NumberAnimation {
            target: scene; property: "ambientOpacity"
            from: 1.0; to: 0.97
            duration: Motion.durationPulse * 2.5
            easing.type: Easing.InOutSine
        }
        NumberAnimation {
            target: scene; property: "ambientOpacity"
            from: 0.97; to: 1.0
            duration: Motion.durationPulse * 2.5
            easing.type: Easing.InOutSine
        }
    }
    Image {
        id: illustration
        opacity: scene.ambientOpacity
        anchors.fill: parent
        source: scene.imageSource
        sourceSize: Qt.size(480, 240)
        fillMode: Image.PreserveAspectFit
        smooth: false; mipmap: false; asynchronous: true
    }
    Item {
        anchors.centerIn: parent
        width: Math.min(scene.width, 360); height: 180
        visible: illustration.status !== Image.Ready
        opacity: scene.ambientOpacity
        Rectangle { x: 12; y: 150; width: 336; height: 2; color: Colors.borderInteractive }
        Rectangle { x: 46; y: 113; width: 242; height: 12; color: Colors.accentPrimary }
        Rectangle { x: 60; y: 125; width: 9; height: 25; color: Colors.borderInteractive }
        Rectangle { x: 265; y: 125; width: 9; height: 25; color: Colors.borderInteractive }
        Rectangle {
            x: 115; y: 31; width: 120; height: 72; color: Colors.surfaceSunken
            border.color: Colors.borderInteractive; border.width: 4
            AtelierMark { anchors.centerIn: parent; width: 40; height: 32 }
        }
        Rectangle { x: 167; y: 103; width: 16; height: 10; color: Colors.borderInteractive }
        Rectangle { x: 299; y: 105; width: 24; height: 45; color: Colors.accentMuted }
        Rectangle { x: 307; y: 63; width: 8; height: 46; color: Colors.accentPrimary }
        Rectangle { x: 292; y: 69; width: 22; height: 12; color: Colors.accentPrimary }
        Rectangle { x: 313; y: 86; width: 24; height: 12; color: Colors.accentPrimary }
    }
}
