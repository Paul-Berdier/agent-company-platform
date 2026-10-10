// Un message de la transcription d'une discussion : auteur, heure, texte BRUT (jamais
// interprété comme du balisage), état (« Envoi… », « Non envoyé », issue du tour) et
// avertissement. Une réponse en cours d'écriture le dit par le texte, pas seulement par la
// forme.

import QtQuick
import QtQuick.Layouts
import Acp.Design

Rectangle {
    id: bulle

    property string auteur: ""
    property string texte: ""
    //! « utilisateur », « assistant », « outil », « systeme » ou « autre ».
    property string role: "autre"
    property bool enCours: false
    property string statut: ""
    property string avertissement: ""
    property string heure: ""

    readonly property bool deVous: bulle.role === "utilisateur"
    readonly property string indication: bulle.enCours
        ? (bulle.role === "outil" ? qsTr("en cours") : qsTr("Hermes écrit…"))
        : ""

    implicitHeight: colonne.implicitHeight + Space.space4 * 2
    radius: Radius.radiusMd
    color: bulle.deVous ? Colors.accentMuted
        : bulle.role === "outil" || bulle.role === "systeme" ? Colors.surfaceSunken : Colors.surfacePanelRaised
    border.width: Space.layoutBorderWidth
    border.color: Colors.borderSubtle

    Accessible.role: Accessible.StaticText
    Accessible.name: bulle.auteur + " : " + bulle.texte + (bulle.statut.length > 0 ? " (" + bulle.statut + ")" : "")

    ColumnLayout {
        id: colonne
        anchors.fill: parent
        anchors.margins: Space.space4
        spacing: Space.space2

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space3
            Text {
                text: bulle.auteur
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.tableCellEmphasis.family
                font.pixelSize: Type.tableCellEmphasis.pixelSize
                font.weight: Type.tableCellEmphasis.weight
            }
            Text {
                visible: bulle.heure.length > 0
                text: bulle.heure
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
            Item { Layout.fillWidth: true }
            Text {
                objectName: "bulle-indication"
                visible: bulle.indication.length > 0
                text: bulle.indication
                textFormat: Text.PlainText
                color: Status.statusRunningForeground
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }

        TextEdit {
            objectName: "bulle-texte"
            Layout.fillWidth: true
            visible: text.length > 0
            readOnly: true
            selectByMouse: true
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.Wrap
            text: bulle.texte
            color: bulle.role === "outil" ? Colors.textSecondary : Colors.textPrimary
            selectionColor: Colors.stateSelected
            selectedTextColor: Colors.textPrimary
            font.family: bulle.role === "outil" ? Type.identifier.family : Type.prose.family
            font.pixelSize: bulle.role === "outil" ? Type.identifier.pixelSize : Type.prose.pixelSize
        }

        Text {
            objectName: "bulle-statut"
            Layout.fillWidth: true
            visible: bulle.statut.length > 0
            text: bulle.statut
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: bulle.statut === qsTr("Envoi…") ? Colors.textMuted : Status.statusFailedForeground
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        Text {
            objectName: "bulle-avertissement"
            Layout.fillWidth: true
            visible: bulle.avertissement.length > 0
            text: qsTr("Avertissement : %1").arg(bulle.avertissement)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Status.statusDegradedForeground
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
    }
}
