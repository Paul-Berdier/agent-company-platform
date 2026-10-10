// Diagnostics : uniquement des valeurs réelles.
//
// Une liste alimentée par des faits : l'inventaire de la station, du lien et du stockage.
//
// Une valeur jamais mesurée s'affiche en gris et porte « Inconnu ». Aucune ligne n'est
// fabriquée pour remplir l'écran.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    // Les compteurs (trames, refus -32601) et le contrôle des préférences n'émettent aucun
    // signal : ils sont relus à l'ouverture de la page, sur demande et avant chaque rapport.
    Component.onCompleted: Diagnostics.refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space8
        spacing: Space.space6

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space5

            Text {
                textFormat: Text.PlainText
                text: qsTr("Diagnostics")
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
                font.letterSpacing: Type.pageTitle.letterSpacing
            }

            Item { Layout.fillWidth: true }

            AcpButton {
                label: qsTr("Vérifier le serveur")
                commandId: "connection.probe"
            }

            AcpButton {
                objectName: "diagnostics-actualiser"
                label: qsTr("Actualiser")
                onTriggered: Diagnostics.refresh()
            }

            AcpButton {
                label: qsTr("Copier le rapport")
                onTriggered: {
                    // Le rapport est expurgé par la couche C++ avant de sortir.
                    Diagnostics.refresh();
                    reportField.text = Diagnostics.buildReport();
                    reportField.selectAll();
                    reportField.copy();
                    Shell.notify(qsTr("Rapport copié, valeurs sensibles expurgées."));
                }
            }
        }

        // Champ technique servant uniquement de relais vers le presse-papiers. Il n'est
        // pas visible : le rapport s'affiche déjà dans la liste ci-dessous.
        TextEdit {
            id: reportField
            visible: false
            width: 0
            height: 0
        }

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Inventaire de la station")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Colors.surfacePanel
            radius: Radius.radiusMd
            border.width: Space.layoutBorderWidth
            border.color: Colors.borderDefault
            clip: true

            ListView {
                id: inventory
                anchors.fill: parent
                anchors.margins: Space.space2
                model: Diagnostics
                clip: true
                section.property: "section"
                section.delegate: Rectangle {
                    id: sectionHeaderRow
                    required property string section

                    width: inventory.width
                    height: Space.densityRowHeightRegular
                    color: Colors.surfacePanelRaised

                    Text {
                        textFormat: Text.PlainText
                        anchors.left: parent.left
                        anchors.leftMargin: Space.space4
                        anchors.verticalCenter: parent.verticalCenter
                        text: sectionHeaderRow.section
                        color: Colors.textMuted
                        font.family: Type.columnHeader.family
                        font.pixelSize: Type.columnHeader.pixelSize
                        font.weight: Type.columnHeader.weight
                        font.letterSpacing: Type.columnHeader.letterSpacing
                        font.capitalization: Type.columnHeader.capitalization
                    }
                }

                // Le délégué enveloppe KeyValueRow plutôt que d'en hériter : les rôles du
                // modèle portent les mêmes noms que les propriétés du composant, et une
                // propriété requise ne peut pas redéclarer une propriété existante.
                delegate: Item {
                    id: inventoryRow
                    required property string label
                    required property string value
                    required property bool known
                    required property bool monospace

                    width: inventory.width
                    implicitHeight: valueRow.implicitHeight
                    height: valueRow.implicitHeight

                    KeyValueRow {
                        id: valueRow
                        width: parent.width
                        label: inventoryRow.label
                        value: inventoryRow.value
                        known: inventoryRow.known
                        monospace: inventoryRow.monospace
                    }
                }
            }
        }
    }
}
