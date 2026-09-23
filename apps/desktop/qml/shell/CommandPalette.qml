// Palette de commandes.
//
// Elle affiche TOUTES les commandes enregistrées, y compris celles qui ne sont pas
// disponibles : celles-ci sont grisées et portent leur raison. Masquer une commande
// indisponible laisserait croire qu'elle n'existe pas.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: palette

    // Voile : il assombrit, il ne floute pas — le flou coûte du GPU en continu et cache
    // l'état du système que l'opérateur surveille.
    Rectangle {
        anchors.fill: parent
        color: Colors.surfaceScrimless
        opacity: 0.58

        TapHandler {
            onTapped: Shell.commandPaletteOpen = false
        }
    }

    Rectangle {
        id: panel
        width: Math.min(parent.width - Space.space8 * 2, 640)
        height: Math.min(parent.height - Space.space10 * 2, 420)
        anchors.horizontalCenter: parent.horizontalCenter
        y: Space.space10
        color: Colors.surfaceOverlay
        radius: Radius.radiusLg
        border.width: Space.layoutBorderWidth
        border.color: Colors.borderInteractive

        // Entrée : déplacement minuscule, on suggère l'origine, on ne fait pas voyager.
        opacity: palette.visible ? 1 : 0
        transform: Translate {
            y: palette.visible ? 0 : Motion.active.overlayEnter.distance
        }
        Behavior on opacity {
            NumberAnimation {
                duration: Motion.active.overlayEnter.duration
                easing.type: Easing.Bezier
                easing.bezierCurve: Motion.easingEnter
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Space.space6
            spacing: Space.space5

            AcpTextField {
                id: search
                Layout.fillWidth: true
                placeholder: qsTr("Rechercher une commande")
                focus: palette.visible
                onTextChanged: Commands.filter = text
            }

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: Commands
                currentIndex: 0
                keyNavigationEnabled: true

                delegate: Item {
                    id: row
                    // Dès qu'un délégué déclare une propriété requise, l'injection par
                    // propriétés remplace les propriétés de contexte : `index` doit donc
                    // être déclaré lui aussi.
                    required property int index
                    required property string commandId
                    required property string title
                    required property string category
                    required property string shortcut
                    required property bool available
                    required property string availabilityReason

                    width: list.width
                    height: Space.densityRowHeightComfortable

                    Rectangle {
                        anchors.fill: parent
                        radius: Radius.radiusSm
                        color: list.currentIndex === row.index
                            ? Colors.stateSelected
                            : (rowHover.hovered ? Colors.stateHover : "transparent")
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Space.space5
                        anchors.rightMargin: Space.space5
                        spacing: Space.space4

                        Text {
                            text: row.title
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            color: row.available ? Colors.textPrimary : Colors.textMuted
                            font.family: Type.tableCell.family
                            font.pixelSize: Type.tableCell.pixelSize
                        }

                        Text {
                            text: row.available ? row.category : row.availabilityReason
                            elide: Text.ElideRight
                            Layout.maximumWidth: list.width * 0.45
                            color: Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }

                        Text {
                            visible: row.shortcut.length > 0
                            text: row.shortcut
                            color: Colors.textMuted
                            font.family: Type.identifier.family
                            font.pixelSize: Type.identifier.pixelSize
                        }
                    }

                    HoverHandler { id: rowHover }
                    TapHandler {
                        onTapped: palette.run(row.commandId)
                    }

                    Accessible.role: Accessible.ListItem
                    Accessible.name: row.title
                    Accessible.description: row.available ? row.category : row.availabilityReason
                    Accessible.onPressAction: palette.run(row.commandId)
                }

                Keys.onReturnPressed: {
                    if (list.currentItem !== null)
                        palette.run(list.currentItem.commandId);
                }
            }

            Text {
                Layout.fillWidth: true
                visible: list.count === 0
                text: qsTr("Aucune commande ne correspond à « %1 ».").arg(Commands.filter)
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }
    }

    function run(commandId) {
        // Le registre décide : il exécute ou il refuse, et son message est affiché dans
        // la barre basse. La palette ne juge rien.
        Commands.execute(commandId);
        Shell.commandPaletteOpen = false;
    }
}
