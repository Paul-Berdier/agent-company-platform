// Compteur d'une entrée de navigation (questions ouvertes…). Invisible à zéro ou quand le
// nombre est inconnu (négatif) : un compteur inconnu n'est jamais affiché « 0 ». Au-delà de
// 99, « 99+ ». Le nombre exact reste dans le nom accessible.

import QtQuick
import Acp.Design

Rectangle {
    id: pastille

    property int nombre: 0
    //! Ce que compte la pastille, au pluriel (« questions ouvertes »), pour le nom accessible.
    property string description: ""

    readonly property string texte: pastille.nombre > 99 ? "99+" : String(pastille.nombre)

    visible: pastille.nombre > 0
    implicitWidth: Math.max(implicitHeight, libelle.implicitWidth + Space.space3 * 2)
    implicitHeight: Space.densityControlHeightSmall - Space.space2
    radius: Radius.radiusPill
    color: Status.statusApprovalRequiredTint
    border.width: Space.layoutBorderWidth
    border.color: Status.statusApprovalRequiredBorder

    Text {
        id: libelle
        anchors.centerIn: parent
        text: pastille.texte
        textFormat: Text.PlainText
        color: Status.statusApprovalRequiredForeground
        font.family: Type.statusChip.family
        font.pixelSize: Type.statusChip.pixelSize
        font.weight: Type.statusChip.weight
    }

    Accessible.role: Accessible.StaticText
    Accessible.name: pastille.description.length > 0 ? pastille.nombre + " " + pastille.description : String(pastille.nombre)
}
