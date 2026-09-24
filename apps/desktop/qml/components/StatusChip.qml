// Pastille d'état.
//
// La couleur n'est JAMAIS seule porteuse d'information : la pastille affiche toujours un
// libellé français et un repli ASCII, et trois états — inconnu, non configuré, hors
// ligne — se distinguent en plus par une bordure pointillée. Seul « en cours » porte du
// mouvement, et seulement en profil standard.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design

Item {
    id: chip

    //! Clé de jeton d'état : « unknown », « notConfigured », « offline », « pending »,
    //! « running », « blocked », « failed », « succeeded », « degraded »,
    //! « approvalRequired ».
    property string statusKey: "unknown"

    //! Libellé affiché. Vide = libellé du jeton.
    property string label: ""

    //! Détail affiché en infobulle. Vide = pas d'infobulle.
    property string detail: ""

    readonly property var meta: Status.meta[chip.statusKey] !== undefined
        ? Status.meta[chip.statusKey]
        : Status.meta.unknown

    readonly property string effectiveLabel: chip.label.length > 0
        ? chip.label
        : chip.meta.label

    implicitHeight: Space.densityControlHeightSmall
    implicitWidth: row.implicitWidth + Space.space4 * 2

    Rectangle {
        id: background
        anchors.fill: parent
        radius: Radius.radiusXs
        // Le remplissage plein est réservé aux pastilles qui sont AUSSI une cible
        // d'action ; les états neverFilled restent sur la surface.
        color: chip.meta.neverFilled ? "transparent" : chip.meta.tint
        border.width: Space.layoutBorderWidth
        border.color: chip.meta.border
    }

    // Bordure pointillée pour les états sans mesure : dessinée par répétition de traits,
    // Qt Quick n'ayant pas de style de trait pointillé sur Rectangle.
    Row {
        visible: chip.meta.dashedBorder
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 3
        Repeater {
            model: Math.max(1, Math.floor(chip.width / 6))
            Rectangle {
                width: 3
                height: Space.layoutBorderWidth
                color: chip.meta.border
            }
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Space.space2

        Rectangle {
            id: dot
            width: 6
            height: 6
            radius: Radius.radiusPill
            color: chip.meta.foreground
            anchors.verticalCenter: parent.verticalCenter

            // Pulsation : seul mouvement en boucle autorisé, et uniquement en profil
            // standard. En profil réduit, l'activité est signalée par le libellé.
            SequentialAnimation on opacity {
                running: chip.meta.animated && !Motion.reduced
                loops: Animation.Infinite
                NumberAnimation {
                    to: Motion.opacityPulseMin
                    duration: Motion.durationPulse / 2
                    easing.type: Easing.Bezier
                    easing.bezierCurve: Motion.easingLinear
                }
                NumberAnimation {
                    to: 1.0
                    duration: Motion.durationPulse / 2
                    easing.type: Easing.Bezier
                    easing.bezierCurve: Motion.easingLinear
                }
            }
        }

        Text {
            textFormat: Text.PlainText
            text: chip.effectiveLabel
            color: chip.meta.foreground
            font.family: Type.statusChip.family
            font.pixelSize: Type.statusChip.pixelSize
            font.weight: Type.statusChip.weight
            font.letterSpacing: Type.statusChip.letterSpacing
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    HoverHandler { id: hover }
    ToolTip {
        id: plainTip
        visible: hover.hovered && chip.detail.length > 0
        text: chip.detail
        contentItem: Text { text: plainTip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
        delay: 400
    }

    // Accessibilité : le repli ASCII accompagne le libellé, pour les lecteurs d'écran et
    // pour toute sortie textuelle.
    Accessible.role: Accessible.StaticText
    Accessible.name: chip.meta.asciiFallback + " " + chip.effectiveLabel
    Accessible.description: chip.detail
}
