// Carte d'un écran de pilotage : un titre, une pastille facultative, un contenu, et l'état de
// la lecture qui l'alimente (« Lu à HH:MM:SS », ou l'erreur de la dernière lecture).
//
// Composant de présentation pur : il ne lit aucun service. Une erreur de lecture ne vide
// jamais le contenu : la dernière valeur reste affichée, datée, avec l'erreur à côté.

import QtQuick
import QtQuick.Layouts
import Acp.Design

Rectangle {
    id: carte

    property string titre: ""
    property string sousTitre: ""
    //! Clé de pastille d'état (StatusChip) ; vide = aucune pastille.
    property string cle: ""
    property string libelleEtat: ""
    property string lecture: ""
    property string erreurLecture: ""

    default property alias contenu: corps.data

    implicitHeight: colonne.implicitHeight + Space.space6 * 2
    color: Colors.surfacePanel
    radius: Radius.radiusMd
    border.width: Space.layoutBorderWidth
    border.color: Colors.borderDefault

    Accessible.role: Accessible.Grouping
    Accessible.name: carte.titre

    ColumnLayout {
        id: colonne
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space4
            Text {
                Layout.fillWidth: true
                text: carte.titre
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textPrimary
                font.family: Type.panelTitle.family
                font.pixelSize: Type.panelTitle.pixelSize
                font.weight: Type.panelTitle.weight
            }
            StatusChip {
                visible: carte.cle.length > 0
                statusKey: carte.cle.length > 0 ? carte.cle : "unknown"
                label: carte.libelleEtat
            }
        }

        Text {
            Layout.fillWidth: true
            visible: carte.sousTitre.length > 0
            text: carte.sousTitre
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        ColumnLayout {
            id: corps
            Layout.fillWidth: true
            spacing: Space.space2
        }

        EtatLecture {
            Layout.fillWidth: true
            lecture: carte.lecture
            erreur: carte.erreurLecture
        }
    }
}
