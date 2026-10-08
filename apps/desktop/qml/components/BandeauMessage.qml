// Résultat d'un geste du propriétaire, tel que le serveur l'a rendu : réussite (message de
// la station) ou refus (message du greffon ou de Hermes, rendu tel quel).
//
// La forme ne dépend pas de la seule couleur : un refus est préfixé « Refusé : » et annoncé
// comme une alerte aux technologies d'assistance. Un geste accepté SANS effet (`alerte` : carte
// non relancée, non reprise) est préfixé « Attention : », annoncé comme une alerte, et jamais
// présenté comme une réussite.

import QtQuick
import QtQuick.Layouts
import Acp.Design

Rectangle {
    id: bandeau

    property string message: ""
    property string erreur: ""
    property bool alerte: false

    readonly property bool enErreur: bandeau.erreur.length > 0
    readonly property bool enAlerte: !bandeau.enErreur && bandeau.alerte && bandeau.message.length > 0
    readonly property string texte: bandeau.enErreur ? qsTr("Refusé : %1").arg(bandeau.erreur)
                                  : bandeau.enAlerte ? qsTr("Attention : %1").arg(bandeau.message)
                                                     : bandeau.message

    visible: bandeau.texte.length > 0
    implicitHeight: visible ? libelle.implicitHeight + Space.space4 * 2 : 0
    radius: Radius.radiusSm
    color: bandeau.enErreur ? Status.statusFailedTint
         : bandeau.enAlerte ? Status.statusDegradedTint
                            : Status.statusSucceededTint
    border.width: Space.layoutBorderWidth
    border.color: bandeau.enErreur ? Status.statusFailedBorder
                : bandeau.enAlerte ? Status.statusDegradedBorder
                                   : Status.statusSucceededBorder

    Text {
        id: libelle
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: Space.space5
        text: bandeau.texte
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: bandeau.enErreur ? Status.statusFailedForeground
             : bandeau.enAlerte ? Status.statusDegradedForeground
                                : Status.statusSucceededForeground
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    Accessible.role: bandeau.enErreur || bandeau.enAlerte ? Accessible.AlertMessage : Accessible.StaticText
    Accessible.name: bandeau.texte
}
