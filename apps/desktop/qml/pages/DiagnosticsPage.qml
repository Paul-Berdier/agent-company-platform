// Diagnostics : uniquement des valeurs réelles.
//
// Deux listes, toutes deux alimentées par des faits :
//   - les cinq contrôles de `/ready`, avec la raison française donnée par le serveur ;
//   - l'inventaire de la station, du lien, de la session, des flux et du stockage.
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
                label: qsTr("Copier le rapport")
                onTriggered: {
                    // Le rapport est expurgé par la couche C++ avant de sortir.
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
            title: qsTr("Contrôles de disponibilité du serveur")
            subtitle: Health.readinessChecks !== null
                ? qsTr("Rendus par /ready. Les raisons sont celles du serveur, affichées "
                       + "telles quelles.")
                : qsTr("Inconnu")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(Space.densityRowHeightRegular,
                                             readyList.contentHeight + Space.space4)
            Layout.maximumHeight: page.height * 0.28
            color: Colors.surfacePanel
            radius: Radius.radiusMd
            border.width: Space.layoutBorderWidth
            border.color: Colors.borderDefault
            clip: true

            ListView {
                id: readyList
                anchors.fill: parent
                anchors.margins: Space.space2
                model: Health.readinessChecks
                clip: true

                delegate: Item {
                    id: readyRow
                    required property string name
                    required property string status
                    required property string detail
                    required property bool healthy

                    width: readyList.width
                    implicitHeight: readyValueRow.implicitHeight
                    height: readyValueRow.implicitHeight

                    KeyValueRow {
                        id: readyValueRow
                        width: parent.width
                        label: readyRow.name
                        // La raison vient du serveur et est affichée telle quelle.
                        value: readyRow.detail.length > 0
                            ? readyRow.status + " — " + readyRow.detail
                            : readyRow.status
                        known: readyRow.status.length > 0
                    }
                }
            }

            EmptyState {
                anchors.fill: parent
                visible: readyList.count === 0
                title: qsTr("Aucun contrôle relevé")
                body: qsTr("Le serveur n'a pas encore été interrogé, ou il n'a détaillé aucun "
                           + "contrôle. Aucune ligne n'est inventée pour remplir cet espace.")
            }
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
