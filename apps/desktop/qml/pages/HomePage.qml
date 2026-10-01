// Accueil de la station.
//
// Seuls des faits mesurés y figurent : l'adresse de Hermes, l'état du lien et la version
// annoncée. Les cartes de pilotage (projets, questions, poste, quotas) arrivent avec leurs
// pages ; tant qu'elles ne sont pas livrées, l'accueil n'en simule aucune.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.min(page.width - Space.space8 * 2, 760)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Space.space7

            Item { Layout.preferredHeight: Space.space8 }

            Label {
                Layout.fillWidth: true
                text: qsTr("Agent Company Platform")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("La station pilote Hermes par ses API. Les pages de pilotage "
                           + "(projets, questions, discussion, poste, quotas, routage, "
                           + "sauvegarde) apparaissent dans la navigation dès qu'elles sont "
                           + "livrées ; elles y sont marquées « Indisponible pour l'instant » "
                           + "d'ici là.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textSecondary
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Hermes")
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Adresse")
                    value: Shell.serverUrlLabel
                    known: Shell.serverUrl.length > 0
                    monospace: true
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Lien")
                    value: Health.linkStatusLabel
                    known: Health.linkStatus !== LinkStatus.Unknown
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Version annoncée")
                    value: Health.hermesVersion
                    known: Health.hermesVersion !== qsTr("Inconnu")
                    monospace: true
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Dernier échange réussi")
                    value: Health.lastSuccessLabel
                    known: Health.lastSuccessLabel !== qsTr("Jamais")
                    monospace: true
                }
            }

            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Session et compatibilité")
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Connecté en tant que")
                    value: Session.nomAffiche
                    known: Session.nomAffiche !== qsTr("Inconnu")
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Session")
                    value: Session.libelleEtat
                    known: true
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Compatibilité")
                    value: Compatibility.libelle
                    known: Compatibility.etat !== CompatibilityStatus.NonVerifiee
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Détail")
                    value: Compatibility.explication.length > 0 ? Compatibility.explication : qsTr("Aucun")
                    known: Compatibility.explication.length > 0
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Passerelle de Hermes")
                    value: Health.gatewayLabel
                    known: Health.gatewayLabel !== qsTr("Inconnu")
                }
            }

            RowLayout {
                spacing: Space.space4
                AcpButton { label: qsTr("Vérifier le serveur"); commandId: "connection.probe" }
                AcpButton { label: qsTr("Revérifier la compatibilité"); commandId: "connection.compatibility" }
                AcpButton { label: qsTr("Ouvrir les diagnostics"); commandId: "navigation.diagnostics" }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
