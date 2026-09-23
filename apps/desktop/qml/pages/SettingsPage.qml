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
        Label { text: qsTr("Réglages"); color: Colors.textPrimary; font.pixelSize: Type.pageTitle.pixelSize }
        Label { text: qsTr("Serveur et session"); color: Colors.textPrimary; font.bold: true }
        AcpTextField { id: server; Layout.fillWidth: true; text: Shell.serverUrl; placeholder: qsTr("Adresse HTTPS de l’API ACP") }
        CheckBox { id: loopback; text: qsTr("Autoriser HTTP uniquement sur cette machine (développement)"); checked: Shell.allowsInsecureLoopback }
        AcpButton { label: qsTr("Changer de serveur"); onTriggered: changeServer.open() }
        Label { id: serverError; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Status.statusFailedForeground }
        CheckBox {
            text: qsTr("Mémoriser la session dans le coffre Windows")
            checked: SessionStorage.rememberSession
            onToggled: SessionStorage.rememberSession = checked
        }
        Label { text: SessionStorage.error || SessionStorage.status; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary }
        AcpButton { label: qsTr("Se déconnecter"); commandId: "session.logout" }
        AcpButton { label: qsTr("Reprendre la session"); commandId: "session.resume" }
        Label { text: qsTr("Apparence"); color: Colors.textPrimary; font.bold: true }
        RowLayout {
            Label { text: qsTr("Thème"); color: Colors.textSecondary }
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
        Label { text: qsTr("Mises à jour · version %1").arg(Updates.currentVersion); color: Colors.textPrimary; font.bold: true }
        Label {
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
        Label { visible: Updates.updateAvailable; text: qsTr("Vérifiez SHA256SUMS.txt et la signature du paquet avant installation. Les paquets de développement peuvent être non signés."); color: Colors.textSecondary; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        TextArea { visible: Updates.notes.length > 0; text: Updates.notes; textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Colors.textPrimary; Layout.fillWidth: true }
        Item { Layout.preferredHeight: Space.space8 }
    }
    Dialog {
        id: changeServer
        anchors.centerIn: parent
        title: qsTr("Changer de serveur ?")
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: qsTr("La session courante sera oubliée sur ce poste. Vous devrez vous reconnecter.") }
        onAccepted: serverError.text = Shell.applyServerUrl(server.text, loopback.checked)
    }
}
