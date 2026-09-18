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
                return Palette.stateDisabled;
            if (control.primary)
                return tap.pressed ? Palette.accentPressed
                    : (hover.hovered ? Palette.accentHover : Palette.accentPrimary);
            return tap.pressed ? Palette.statePressed
                : (hover.hovered ? Palette.stateHover : "transparent");
        }
        border.width: control.primary ? 0 : Space.layoutBorderWidth
        border.color: control.effectiveEnabled
            ? Palette.borderInteractive
            : Palette.borderSubtle

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
            color: {
                if (!control.effectiveEnabled)
                    return Palette.textMuted;
                return control.primary ? Palette.textOnAccent : Palette.textPrimary;
            }
            font.families: Type.buttonLabel.family
            font.pixelSize: Type.buttonLabel.pixelSize
            font.weight: Type.buttonLabel.weight
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            visible: control.shortcutHint.length > 0
            text: control.shortcutHint
            color: Palette.textMuted
            font.families: Type.identifier.family
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
        border.color: Palette.borderFocus
    }

    ToolTip.visible: hover.hovered && control.unavailableReason.length > 0
    ToolTip.text: control.unavailableReason
    ToolTip.delay: 300

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
