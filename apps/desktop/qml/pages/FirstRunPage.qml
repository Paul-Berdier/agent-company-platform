// Écran de connexion.
//
// Il sert à la première ouverture ET à chaque retour sans session. Deux étapes :
//   1. l'adresse du serveur Hermes, saisie ; aucune valeur par défaut n'est proposée ;
//   2. le test du lien, qui montre l'état réel mesuré par `/api/health`.
//
// La connexion elle-même passe par le navigateur système (RFC 8252) : aucun mot de passe
// n'est jamais saisi dans la station. Ce geste n'est pas encore branché dans cette version
// de la station : l'écran le dit, et n'offre aucun bouton qui ferait semblant.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Rectangle {
    id: page

    color: Colors.surfaceCanvas

    property string urlError: ""

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight + Space.space10 * 2
        clip: true

        ColumnLayout {
            id: column
            x: Math.max(Space.space8, (page.width - width) / 2)
            y: Space.space10
            width: Math.min(page.width - Space.space8 * 2, Type.measureProse)
            spacing: Space.space8

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: qsTr("Station de travail")
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
                font.letterSpacing: Type.pageTitle.letterSpacing
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Shell.firstRun
                    ? qsTr("Aucune adresse de serveur n'est configurée. La station ne "
                           + "propose aucune adresse par défaut : saisissez celle de votre "
                           + "Hermes.")
                    : qsTr("Aucune session n'est ouverte sur ce poste.")
                color: Colors.textSecondary
                lineHeight: Type.prose.lineHeight
                lineHeightMode: Text.FixedHeight
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            // --- Étape 1 : adresse ------------------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("1. Adresse de Hermes")
                subtitle: qsTr("HTTPS est imposé. Le HTTP en clair n'est accepté que sur une "
                               + "adresse de bouclage, et seulement si vous l'autorisez "
                               + "explicitement ci-dessous.")
            }

            AcpTextField {
                id: urlField
                Layout.fillWidth: true
                placeholder: "https://exemple.invalid"
                accessibleName: qsTr("Adresse du serveur")
                text: Shell.serverUrl
                helperText: qsTr("Exemple de forme attendue ; ce n'est pas une adresse réelle.")
                errorText: page.urlError
                onAccepted: page.submitUrl()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4

                CheckBox {
                    id: loopbackBox
                    text: qsTr("Autoriser HTTP en clair sur une adresse de bouclage")
                    checked: Shell.allowsInsecureLoopback
                    contentItem: Text {
                        textFormat: Text.PlainText
                        text: loopbackBox.text
                        leftPadding: loopbackBox.indicator.width + Space.space3
                        verticalAlignment: Text.AlignVCenter
                        color: Colors.textSecondary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                }

                Item { Layout.fillWidth: true }

                AcpButton {
                    label: qsTr("Enregistrer et tester")
                    primary: true
                    manualEnabled: urlField.text.length > 0
                    onTriggered: page.submitUrl()
                }
            }

            // --- Étape 2 : test du lien -------------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("2. Test du lien")
                subtitle: qsTr("Les valeurs ci-dessous sont mesurées. Tant qu'aucune mesure "
                               + "n'a eu lieu, elles affichent « Inconnu ».")
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("État du lien")
                    value: Health.linkStatusLabel
                    known: Health.linkStatus !== LinkStatus.Unknown
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Version de Hermes")
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
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Détail")
                    value: Health.detail.length > 0 ? Health.detail : qsTr("Aucun")
                    known: Health.detail.length > 0
                }
            }

            // --- Étape 3 : connexion ----------------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("3. Connexion")
                subtitle: qsTr("La connexion passera par le navigateur du système, sur la page "
                               + "de connexion de Hermes. Elle n'est pas encore disponible dans "
                               + "cette version de la station.")
            }
        }
    }

    function submitUrl() {
        page.urlError = Shell.applyServerUrl(urlField.text, loopbackBox.checked);
    }
}
