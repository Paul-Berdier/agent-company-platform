// Écran de connexion.
//
// Il sert à la première ouverture ET à chaque retour sans session. Trois étapes :
//   1. l'adresse du serveur Hermes, saisie ; aucune valeur par défaut n'est proposée ;
//   2. le test du lien, qui montre l'état réel mesuré par `/api/health` ;
//   3. la connexion par le navigateur du système (RFC 8252) : Hermes mène la connexion chez
//      son fournisseur d'identité, puis renvoie le navigateur vers la station. Aucun mot de
//      passe n'est jamais saisi dans la station, et aucun jeton n'atteint cet écran.

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

    readonly property bool lienUtilisable: Health.linkStatus === LinkStatus.Online
        || Health.linkStatus === LinkStatus.Degraded
    readonly property bool enAttente: Session.etat === SessionStatus.AttenteNavigateur
        || Session.etat === SessionStatus.Echange

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
                enabled: !page.enAttente
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
                    enabled: !page.enAttente
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
                    primary: Shell.firstRun
                    manualEnabled: urlField.text.length > 0 && !page.enAttente
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
                subtitle: qsTr("La connexion s'ouvre dans votre navigateur, sur la page de "
                               + "connexion de Hermes (mot de passe, clé d'accès, consentement). "
                               + "Aucun mot de passe n'est saisi dans la station.")
            }

            CheckBox {
                id: memoriserBox
                objectName: "connexion-memoriser"
                text: qsTr("Mémoriser la connexion sur ce poste (coffre Windows)")
                checked: Session.memoriser
                enabled: !page.enAttente
                onToggled: Session.memoriser = checked
                contentItem: Text {
                    textFormat: Text.PlainText
                    text: memoriserBox.text
                    leftPadding: memoriserBox.indicator.width + Space.space3
                    verticalAlignment: Text.AlignVCenter
                    color: Colors.textSecondary
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                }
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: qsTr("Mémorisée, la connexion reprend au prochain lancement sans repasser "
                           + "par le navigateur, jusqu'à son expiration chez le fournisseur "
                           + "d'identité. Seul le jeton de renouvellement est gardé, dans le "
                           + "Gestionnaire d'identification de Windows.")
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4

                StatusChip {
                    statusKey: {
                        switch (Session.etat) {
                        case SessionStatus.Connectee: return "succeeded";
                        case SessionStatus.AttenteNavigateur:
                        case SessionStatus.Echange:
                        case SessionStatus.Rafraichissement: return "running";
                        case SessionStatus.Expiree:
                        case SessionStatus.Refusee: return "failed";
                        case SessionStatus.HorsLigne:
                        case SessionStatus.FournisseurInjoignable: return "offline";
                        default: return "unknown";
                        }
                    }
                    label: Session.libelleEtat
                    detail: Session.derniereErreur
                }

                Item { Layout.fillWidth: true }

                AcpButton {
                    objectName: "connexion-annuler"
                    visible: page.enAttente
                    label: qsTr("Annuler")
                    onTriggered: Session.annulerConnexion()
                }

                AcpButton {
                    objectName: "connexion-se-connecter"
                    label: qsTr("Se connecter avec le navigateur")
                    primary: true
                    commandId: "session.signIn"
                }
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                visible: page.enAttente
                text: Session.etat === SessionStatus.Echange
                    ? qsTr("Réponse reçue du navigateur : vérification de la connexion auprès de Hermes.")
                    : qsTr("En attente de la connexion dans le navigateur — %1 s restantes. Vous "
                           + "pouvez revenir ici une fois la page « Connexion transmise à la "
                           + "station » affichée.").arg(Session.secondesRestantes)
                color: Colors.textSecondary
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            RowLayout {
                Layout.fillWidth: true
                visible: Session.etat === SessionStatus.AttenteNavigateur
                spacing: Space.space4

                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: Session.navigateurNonOuvert
                        ? qsTr("Le navigateur ne s'est pas ouvert : copiez le lien et ouvrez-le "
                               + "vous-même dans un navigateur de ce poste.")
                        : qsTr("Le navigateur ne s'est pas affiché ? Copiez le lien et ouvrez-le "
                               + "vous-même. Il ne contient ni mot de passe ni jeton.")
                    color: Session.navigateurNonOuvert ? Status.statusFailedForeground : Colors.textMuted
                    font.family: Type.metadata.family
                    font.pixelSize: Type.metadata.pixelSize
                }

                AcpButton {
                    objectName: "connexion-copier-lien"
                    label: qsTr("Copier le lien")
                    onTriggered: Shell.notify(Session.copierLienConnexion()
                        ? qsTr("Lien de connexion copié dans le presse-papiers.")
                        : qsTr("Le lien n'a pas pu être copié."))
                }
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                visible: Session.derniereErreur.length > 0 && !page.enAttente
                text: Session.derniereErreur
                color: Status.statusFailedForeground
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                visible: Session.avertissement.length > 0
                text: Session.avertissement
                color: Colors.textSecondary
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }

            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                visible: Session.avisCoffre.length > 0
                text: Session.avisCoffre
                color: Colors.textSecondary
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }

            Item { Layout.preferredHeight: Space.space4 }
        }
    }

    function submitUrl() {
        page.urlError = Shell.applyServerUrl(urlField.text, loopbackBox.checked);
    }
}
