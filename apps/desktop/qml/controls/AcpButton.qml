// Bouton de la station.
//
// Règle appliquée : un bouton relié à une commande NE PEUT PAS faire semblant. Sa
// disponibilité vient du registre, son libellé d'indisponibilité aussi, et il reste
// LISIBLE une fois désactivé (texte en text.muted, jamais plus pâle).

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design
import Acp.Runtime

Item {
    id: control

    property string label: ""
    property string shortcutHint: ""
    property bool primary: false

    //! Identifiant de commande. Quand il est renseigné, la disponibilité et l'exécution
    //! viennent du registre ; `enabled` et `onTriggered` ne sont plus consultés.
    property string commandId: ""

    //! Utilisé seulement quand commandId est vide.
    property bool manualEnabled: true

    //! Raison d'indisponibilité affichée en infobulle.
    readonly property string unavailableReason: control.commandId.length > 0
        ? Commands.availabilityReasonOf(control.commandId)
        : ""

    readonly property bool effectiveEnabled: control.commandId.length > 0
        ? control.unavailableReason.length === 0
        : control.manualEnabled

    signal triggered()

    implicitWidth: content.implicitWidth + Space.space5 * 2
    implicitHeight: Space.densityControlHeightRegular
    activeFocusOnTab: true

    Rectangle {
        id: background
        anchors.fill: parent
        radius: Radius.radiusSm
        color: {
            if (!control.effectiveEnabled)
                return Colors.stateDisabled;
            if (control.primary)
                return tap.pressed ? Colors.accentPressed
                    : (hover.hovered ? Colors.accentHover : Colors.accentPrimary);
            return tap.pressed ? Colors.statePressed
                : (hover.hovered ? Colors.stateHover : "transparent");
        }
        border.width: control.primary ? 0 : Space.layoutBorderWidth
        border.color: control.effectiveEnabled
            ? Colors.borderInteractive
            : Colors.borderSubtle

        Behavior on color {
            enabled: Motion.active.press.duration > 0
            ColorAnimation {
                duration: Motion.active.press.duration
                easing.type: Easing.Bezier
                easing.bezierCurve: Motion.easingStandard
            }
        }
    }

    Row {
        id: content
        anchors.centerIn: parent
        spacing: Space.space3

        Text {
            text: control.label
            textFormat: Text.PlainText
            color: {
                if (!control.effectiveEnabled)
                    return Colors.textMuted;
                return control.primary ? Colors.textOnAccent : Colors.textPrimary;
            }
            font.family: Type.buttonLabel.family
            font.pixelSize: Type.buttonLabel.pixelSize
            font.weight: Type.buttonLabel.weight
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            textFormat: Text.PlainText
            visible: control.shortcutHint.length > 0
            text: control.shortcutHint
            color: Colors.textMuted
            font.family: Type.identifier.family
            font.pixelSize: Type.identifier.pixelSize
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    // Cible cliquable d'au moins 32 px, obtenue par une zone transparente : le contrôle
    // visible reste à 28 px.
    Item {
        anchors.centerIn: parent
        width: Math.max(control.width, Space.densityHitTargetMinimum)
        height: Math.max(control.height, Space.densityHitTargetMinimum)

        HoverHandler {
            id: hover
            cursorShape: control.effectiveEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        }
        TapHandler {
            id: tap
            onTapped: control.activate()
        }
    }

    Rectangle {
        visible: control.activeFocus
        anchors.fill: parent
        anchors.margins: -Space.layoutFocusRingOffset
        color: "transparent"
        radius: Radius.radiusSm
        border.width: Space.layoutFocusRingWidth
        border.color: Colors.borderFocus
    }

    // Rôle, nom et action exposés aux technologies d'assistance (UI Automation sous
    // Windows) : sans eux, un lecteur d'écran ne voit pas ce bouton du tout.
    // https://doc.qt.io/qt-6.8/qml-qtquick-accessible.html — consulté le 18 septembre 2026.
    Accessible.role: Accessible.Button
    Accessible.name: control.label
    Accessible.description: control.unavailableReason
    Accessible.focusable: true
    Accessible.onPressAction: control.activate()

    ToolTip {
        id: plainTip
        visible: hover.hovered && control.unavailableReason.length > 0
        text: control.unavailableReason
        contentItem: Text { text: plainTip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
        delay: 300
    }

    Keys.onReturnPressed: control.activate()
    Keys.onSpacePressed: control.activate()

    function activate() {
        if (control.commandId.length > 0) {
            // Même quand le bouton est désactivé, l'exécution passe par le registre :
            // c'est lui qui refuse et qui fournit le message affiché.
            Commands.execute(control.commandId);
            return;
        }
        if (control.manualEnabled)
            control.triggered();
    }
}
