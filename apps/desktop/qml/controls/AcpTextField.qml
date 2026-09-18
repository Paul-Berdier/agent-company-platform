// Champ de saisie.
//
// `masked` bascule en saisie masquée ET coupe la prédiction et l'auto-complétion du
// système : un mot de passe ou un jeton d'amorçage ne doit pas entrer dans un
// dictionnaire d'apprentissage. La valeur n'est jamais journalisée, jamais mise en cache
// et jamais copiée dans une propriété exposée.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design

Item {
    id: field

    property alias text: input.text
    property string placeholder: ""
    property string helperText: ""
    property string errorText: ""
    property bool masked: false

    signal accepted()

    implicitHeight: Space.densityControlHeightRegular
        + (helper.visible ? helper.implicitHeight + Space.space2 : 0)
    implicitWidth: 240

    Rectangle {
        id: box
        width: parent.width
        height: Space.densityControlHeightRegular
        radius: Radius.radiusSm
        color: field.enabled ? Palette.surfacePanelRaised : Palette.stateDisabled
        border.width: Space.layoutBorderWidth
        border.color: field.errorText.length > 0
            ? Status.statusFailedBorder
            : (input.activeFocus ? Palette.borderFocus : Palette.borderInteractive)

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: Space.space5
            anchors.rightMargin: Space.space5
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            enabled: field.enabled
            color: field.enabled ? Palette.textPrimary : Palette.textMuted
            selectionColor: Palette.stateSelected
            selectedTextColor: Palette.textPrimary
            font.families: field.masked ? Type.identifier.family : Type.tableCell.family
            font.pixelSize: Type.tableCell.pixelSize
            echoMode: field.masked ? TextInput.Password : TextInput.Normal
            // Ni prédiction, ni correction, ni complétion sur une saisie masquée.
            inputMethodHints: field.masked
                ? (Qt.ImhHiddenText | Qt.ImhSensitiveData | Qt.ImhNoAutoUppercase
                   | Qt.ImhNoPredictiveText)
                : Qt.ImhNone
            onAccepted: field.accepted()

            Text {
                anchors.fill: parent
                verticalAlignment: Text.AlignVCenter
                visible: input.text.length === 0
                text: field.placeholder
                color: Palette.textMuted
                font: input.font
                elide: Text.ElideRight
            }
        }
    }

    Text {
        id: helper
        anchors.top: box.bottom
        anchors.topMargin: Space.space2
        width: parent.width
        visible: field.errorText.length > 0 || field.helperText.length > 0
        wrapMode: Text.WordWrap
        text: field.errorText.length > 0 ? field.errorText : field.helperText
        color: field.errorText.length > 0 ? Status.statusFailedForeground : Palette.textMuted
        font.families: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }
}
