// État de la dernière lecture d'une source : « Lu à HH:MM:SS », et, si la dernière lecture a
// échoué, l'erreur À CÔTÉ de la valeur gardée (jamais une page vidée, jamais un succès feint).

import QtQuick
import QtQuick.Layouts
import Acp.Design

ColumnLayout {
    id: etat

    property string lecture: ""
    property string erreur: ""

    readonly property bool enErreur: etat.erreur.length > 0

    spacing: Space.space1
    visible: etat.lecture.length > 0 || etat.enErreur

    Text {
        objectName: "etat-lecture"
        Layout.fillWidth: true
        visible: etat.lecture.length > 0
        text: etat.lecture
        textFormat: Text.PlainText
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    Text {
        objectName: "etat-lecture-erreur"
        Layout.fillWidth: true
        visible: etat.enErreur
        text: qsTr("Dernière lecture impossible : %1").arg(etat.erreur)
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Status.statusFailedForeground
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }
}
