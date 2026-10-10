import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

ScrollView {
    id: page
    clip: true
    ColumnLayout {
        width: page.availableWidth - 2 * Space.space6
        x: Space.space6
        y: Space.space6
        spacing: Space.space5
        Label { textFormat: Text.PlainText; text: qsTr("Réglages"); color: Colors.textPrimary; font.pixelSize: Type.pageTitle.pixelSize }
        Label { textFormat: Text.PlainText; text: qsTr("Serveur"); color: Colors.textPrimary; font.bold: true }
        AcpTextField { id: server; Layout.fillWidth: true; text: Shell.serverUrl; placeholder: qsTr("Adresse HTTPS de Hermes") }
        CheckBox { id: loopback; text: qsTr("Autoriser HTTP uniquement sur cette machine (développement)"); checked: Shell.allowsInsecureLoopback }
        AcpButton { objectName: "reglages-changer-serveur"; label: qsTr("Changer de serveur"); onTriggered: changeServer.open() }
        Label { id: serverError; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Status.statusFailedForeground }
        Label { textFormat: Text.PlainText; text: qsTr("Session"); color: Colors.textPrimary; font.bold: true }
        Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Colors.textSecondary
            text: Session.connectee
                ? qsTr("Connecté en tant que %1 (%2), fournisseur %3. Jeton d'accès valable jusqu'au %4.")
                      .arg(Session.nomAffiche).arg(Session.courriel).arg(Session.fournisseur).arg(Session.expiration)
                : qsTr("État : %1.").arg(Session.libelleEtat)
        }
        CheckBox {
            objectName: "reglages-memoriser"
            text: qsTr("Mémoriser la connexion sur ce poste (coffre Windows)")
            checked: Session.memoriser
            onToggled: Session.memoriser = checked
        }
        Label {
            visible: text.length > 0
            text: Session.avisCoffre
            textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary
        }
        Label {
            visible: text.length > 0
            text: Session.bilanDeconnexion
            textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary
        }
        RowLayout {
            AcpButton { objectName: "reglages-se-deconnecter"; label: qsTr("Se déconnecter"); commandId: "session.logout" }
            AcpButton { label: qsTr("Retenter le renouvellement"); commandId: "session.retry" }
        }
        Label { textFormat: Text.PlainText; text: qsTr("Apparence"); color: Colors.textPrimary; font.bold: true }
        RowLayout {
            Label { textFormat: Text.PlainText; text: qsTr("Thème"); color: Colors.textSecondary }
            ComboBox {
                model: [qsTr("Suivre Windows"), qsTr("Clair"), qsTr("Sombre")]
                currentIndex: ["system", "light", "dark"].indexOf(Appearance.themePreference)
                Accessible.name: qsTr("Thème")
                onActivated: Appearance.themePreference = ["system", "light", "dark"][currentIndex]
            }
            CheckBox {
                text: qsTr("Réduire les animations")
                checked: Appearance.motionPreference === "reduced"
                onToggled: Appearance.motionPreference = checked ? "reduced" : "standard"
            }
        }
        Label { textFormat: Text.PlainText; text: qsTr("Mises à jour · version %1").arg(Updates.currentVersion); color: Colors.textPrimary; font.bold: true }
        Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary
            text: qsTr("La vérification contacte GitHub à votre demande. Vous choisissez ensuite le paquet dans la publication ; rien n’est téléchargé ni installé automatiquement.")
        }
        CheckBox {
            text: qsTr("Inclure les préversions pour cette vérification")
            enabled: !Updates.busy
            checked: Updates.includePrereleases
            onToggled: Updates.includePrereleases = checked
        }
        RowLayout {
            AcpButton { label: qsTr("Vérifier les mises à jour"); manualEnabled: !Updates.busy; onTriggered: Updates.check() }
            AcpButton { label: qsTr("Ouvrir la publication GitHub"); visible: Updates.updateAvailable; onTriggered: Updates.openRelease() }
            BusyIndicator { running: Updates.busy; visible: running; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
        }
        Label { text: Updates.status; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary }
        Label { visible: Updates.latestVersion.length > 0; text: qsTr("Publication vérifiée : %1").arg(Updates.latestVersion); textFormat: Text.PlainText; color: Colors.textPrimary }
        Label { objectName: "reglages-avertissement-paquet"; textFormat: Text.PlainText; visible: Updates.updateAvailable; text: qsTr("Vérifiez l'empreinte du paquet dans SHA256SUMS.txt avant installation. Un paquet n'est signé que si les notes de sa publication le disent."); color: Colors.textSecondary; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        TextArea { visible: Updates.notes.length > 0; text: Updates.notes; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Colors.textPrimary; Layout.fillWidth: true }
        Item { Layout.preferredHeight: Space.space8 }
    }
    // Boutons explicites, en français (les boutons standard de Qt s'afficheraient en anglais :
    // aucun traducteur Qt n'est chargé), comme les autres confirmations de la station.
    Dialog {
        id: changeServer
        objectName: "reglages-changer-serveur-confirmation"
        anchors.centerIn: parent
        title: qsTr("Changer de serveur ?")
        modal: true
        width: Math.min(page.width - Space.space8 * 2, 520)
        contentItem: ColumnLayout {
            spacing: Space.space4
            Label {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                text: qsTr("La session courante sera oubliée sur ce poste. Vous devrez vous reconnecter.")
            }
            RowLayout {
                spacing: Space.space4
                AcpButton {
                    objectName: "reglages-changer-serveur-confirmer"
                    primary: true
                    label: qsTr("Changer de serveur")
                    onTriggered: {
                        changeServer.close();
                        serverError.text = Shell.applyServerUrl(server.text, loopback.checked);
                    }
                }
                AcpButton {
                    objectName: "reglages-changer-serveur-annuler"
                    label: qsTr("Annuler")
                    onTriggered: changeServer.close()
                }
            }
        }
    }
}
