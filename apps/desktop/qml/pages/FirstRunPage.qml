// Écran de première ouverture : point d'entrée, test de connexion, authentification.
//
// Trois étapes, dans cet ordre, et pas d'étape sautée :
//   1. l'adresse du serveur, saisie ; aucune valeur par défaut n'est proposée, parce que
//      le projet n'a décidé aucun domaine (audit, section 5.2) ;
//   2. le test de connexion, qui montre l'état réel du lien et de la compatibilité ;
//   3. l'authentification, disponible seulement une fois le serveur joignable.
//
// L'amorçage du propriétaire de plateforme est signalé quand `/auth/status` l'indique.
// Le jeton d'amorçage est saisi en champ masqué et n'est JAMAIS persisté.

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
                Layout.fillWidth: true
                text: qsTr("Station de travail")
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
                font.letterSpacing: Type.pageTitle.letterSpacing
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: qsTr("Aucune adresse de serveur n'est configurée. La station ne "
                           + "propose aucune adresse par défaut : aucun domaine n'a été "
                           + "décidé pour ce produit, et en inventer un ferait échouer la "
                           + "connexion sans le dire.")
                color: Colors.textSecondary
                lineHeight: Type.prose.lineHeight
                lineHeightMode: Text.FixedHeight
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            // --- Étape 1 : adresse ------------------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("1. Adresse du serveur")
                subtitle: qsTr("HTTPS est imposé. Le HTTP en clair n'est accepté que sur une "
                               + "adresse de bouclage, et seulement si vous l'autorisez "
                               + "explicitement ci-dessous.")
            }

            AcpTextField {
                id: urlField
                Layout.fillWidth: true
                placeholder: "https://exemple.invalid"
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
                    contentItem: Text {
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

            // --- Étape 2 : test de connexion --------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("2. Test de connexion")
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
                    label: qsTr("Dernier échange réussi")
                    value: Health.lastSuccessLabel
                    known: Health.lastSuccessAt !== undefined
                        && Health.lastSuccessLabel !== qsTr("Jamais")
                    monospace: true
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Compatibilité")
                    value: Compatibility.stateLabel
                    known: Compatibility.state !== CompatibilityStatus.NotChecked
                }
                KeyValueRow {
                    Layout.fillWidth: true
                    label: qsTr("Détail")
                    value: Compatibility.explanation.length > 0
                        ? Compatibility.explanation
                        : qsTr("Aucun")
                    known: Compatibility.explanation.length > 0
                }
            }

            // --- Étape 3 : authentification ---------------------------------
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("3. Authentification")
                subtitle: Session.bootstrapRequired
                    ? qsTr("Ce serveur n'a pas encore de propriétaire de plateforme. "
                           + "L'amorçage n'est pas livré par cette fondation : utilisez le "
                           + "client web ou la ligne de commande pour créer le premier "
                           + "compte.")
                    : qsTr("La session est portée par un cookie posé par le serveur. Aucun "
                           + "mot de passe n'est mémorisé sur ce poste par cette fondation.")
            }

            AcpTextField {
                id: emailField
                Layout.fillWidth: true
                enabled: Health.linkStatus === LinkStatus.Online
                    || Health.linkStatus === LinkStatus.Degraded
                placeholder: qsTr("Identifiant")
            }

            AcpTextField {
                id: passwordField
                Layout.fillWidth: true
                enabled: emailField.enabled
                masked: true
                placeholder: qsTr("Mot de passe")
                errorText: Session.state === SessionStatus.Disconnected
                    ? Session.lastError
                    : ""
                onAccepted: page.submitLogin()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4

                StatusChip {
                    statusKey: {
                        switch (Session.state) {
                        case SessionStatus.Connected: return "succeeded";
                        case SessionStatus.Connecting: return "running";
                        case SessionStatus.Expired:
                        case SessionStatus.Revoked: return "failed";
                        case SessionStatus.Offline: return "offline";
                        default: return "unknown";
                        }
                    }
                    label: Session.stateLabel
                    detail: Session.lastError
                }

                Item { Layout.fillWidth: true }

                AcpButton {
                    label: qsTr("Se connecter")
                    primary: true
                    manualEnabled: emailField.enabled && !Session.busy
                        && emailField.text.length > 0 && passwordField.text.length > 0
                    onTriggered: page.submitLogin()
                }
            }
        }
    }

    function submitUrl() {
        page.urlError = Shell.applyServerUrl(urlField.text, loopbackBox.checked);
    }

    function submitLogin() {
        Session.logIn(emailField.text, passwordField.text);
        // Le champ est vidé immédiatement après l'envoi : la valeur ne doit pas rester
        // dans la scène graphique plus longtemps que nécessaire.
        passwordField.text = "";
    }
}
