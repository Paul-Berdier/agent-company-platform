// Jauge de quota : part RESTANTE d'une fenêtre d'abonnement.
//
// Dessinée en Qt Quick pur : Qt Charts est exclu pour raison de licence (voir
// apps/desktop/CMakeLists.txt). Une part inconnue n'est jamais dessinée comme zéro : la
// piste reste vide et le texte dit « Inconnu ». La couleur accompagne toujours un texte,
// elle ne porte jamais seule l'information.

import QtQuick
import Acp.Design

Item {
    id: gauge

    property string label: ""
    //! Part restante, de 0 à 100 ; `null` quand la source ne la donne pas.
    property var remainingPercent: null
    property string remainingText: "Inconnu"
    property string usedText: "Inconnu"
    property string resetText: "Inconnu"
    //! « dans 3 h 57 », « déjà passée » ou vide quand l'heure est inconnue.
    property string countdownText: ""
    //! « normal », « warning », « critical » ou « unknown ».
    property string level: "unknown"

    readonly property bool known: typeof gauge.remainingPercent === "number"
        && isFinite(gauge.remainingPercent)
    readonly property real ratio: gauge.known
        ? Math.max(0, Math.min(100, gauge.remainingPercent)) / 100
        : 0
    readonly property color fillColor: gauge.level === "critical" ? Status.statusFailedForeground
        : gauge.level === "warning" ? Status.statusDegradedForeground
        : Status.statusSucceededForeground
    readonly property string resetLine: gauge.resetText
        + (gauge.countdownText.length > 0 ? " (" + gauge.countdownText + ")" : "")
    readonly property string summary: gauge.label + " : "
        + (gauge.known ? qsTr("%1 restant, %2 utilisé").arg(gauge.remainingText).arg(gauge.usedText)
                       : qsTr("reste Inconnu"))
        + qsTr(", remise à zéro %1").arg(gauge.resetLine)

    implicitWidth: 240
    implicitHeight: column.implicitHeight

    Accessible.role: Accessible.ProgressBar
    Accessible.name: gauge.summary

    Column {
        id: column
        width: parent.width
        spacing: Space.space2

        Item {
            width: parent.width
            height: Math.max(labelText.implicitHeight, valueText.implicitHeight)
            Text {
                id: labelText
                anchors.left: parent.left
                anchors.right: valueText.left
                anchors.rightMargin: Space.space4
                text: gauge.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: Colors.textPrimary
                font.family: Type.tableCellEmphasis.family
                font.pixelSize: Type.tableCellEmphasis.pixelSize
                font.weight: Type.tableCellEmphasis.weight
            }
            Text {
                id: valueText
                anchors.right: parent.right
                text: gauge.known
                    ? qsTr("%1 restant · %2 utilisé").arg(gauge.remainingText).arg(gauge.usedText)
                    : qsTr("Restant : Inconnu")
                textFormat: Text.PlainText
                color: gauge.known ? Colors.textPrimary : Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }
        }

        Rectangle {
            id: track
            objectName: "quotaGaugeTrack"
            width: parent.width
            height: 8
            radius: height / 2
            color: Colors.surfaceSunken
            border.width: Space.layoutBorderWidth
            border.color: Colors.borderSubtle

            Rectangle {
                objectName: "quotaGaugeFill"
                visible: gauge.known && gauge.ratio > 0
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: parent.width * gauge.ratio
                radius: track.radius
                color: gauge.fillColor
            }
        }

        Text {
            width: parent.width
            text: qsTr("Remise à zéro : %1").arg(gauge.resetLine)
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
    }
}
