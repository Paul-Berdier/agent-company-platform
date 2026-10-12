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
    property bool showDetails: false
    property bool development: Shell.allowsInsecureLoopback
    readonly property bool wide: width >= 1050
    readonly property bool lienUtilisable: Health.linkStatus === LinkStatus.Online || Health.linkStatus === LinkStatus.Degraded
    readonly property bool enAttente: Session.etat === SessionStatus.AttenteNavigateur || Session.etat === SessionStatus.Echange

    Rectangle {
        visible: page.wide
        width: parent.width * 0.45; height: parent.height
        color: Colors.surfaceSidebar
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 56; spacing: Space.space6
            RowLayout {
                AtelierMark { Layout.preferredWidth: 44; Layout.preferredHeight: 36 }
                Text { textFormat: Text.PlainText; text: "ACP"; color: Colors.textPrimary; font.family: Type.pageTitle.family; font.pixelSize: 24; font.weight: Font.DemiBold }
            }
            Item { Layout.fillHeight: true }
            Text { textFormat: Text.PlainText; text: qsTr("L'atelier de\nvos prochaines idées."); Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textPrimary; font.family: Type.pageTitle.family; font.pixelSize: 36; font.weight: Font.DemiBold; lineHeight: 1.2; font.letterSpacing: -0.8 }
            Text { textFormat: Text.PlainText; text: qsTr("Vos projets, vos assistants, votre travail.\nUn espace pour construire et reprendre le fil."); Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary; font.family: Type.prose.family; font.pixelSize: 16; lineHeight: 1.5 }
            AtelierScene { Layout.fillWidth: true; Layout.preferredHeight: 240; visible: Appearance.themeFamily === "pixel" }
            Item { Layout.fillHeight: true }
            Text { textFormat: Text.PlainText; text: qsTr("PIXEL ATELIER  /  ACP"); color: Colors.textMuted; font.family: Type.identifier.family; font.pixelSize: 11; font.letterSpacing: 1.6 }
        }
    }
    Flickable {
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        width: page.wide ? parent.width * 0.55 : parent.width
        contentWidth: width; contentHeight: column.implicitHeight + 80; clip: true
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: column
            x: (parent.width - width) / 2; y: 40
            width: Math.min(parent.width - 64, 500); spacing: Space.space5
            RowLayout {
                Layout.fillWidth: true
                Text { textFormat: Text.PlainText; text: qsTr("BIENVENUE DANS VOTRE ATELIER"); color: Colors.accentPrimary; font.family: Type.metadata.family; font.pixelSize: 11; font.letterSpacing: 1.3; Layout.fillWidth: true }
                AcpButton { label: Appearance.activeTheme === "dark" ? qsTr("Jour") : qsTr("Nuit"); onTriggered: Appearance.themePreference = Appearance.activeTheme === "dark" ? "light" : "dark" }
            }
            Text { textFormat: Text.PlainText; text: qsTr("Retrouvons votre espace."); color: Colors.textPrimary; font.family: Type.pageTitle.family; font.pixelSize: 28; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { textFormat: Text.PlainText; text: qsTr("Connectez votre serveur Hermes, puis identifiez-vous dans votre navigateur."); color: Colors.textSecondary; font.family: Type.prose.family; font.pixelSize: 15; lineHeight: 1.4; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Colors.borderSubtle; Layout.topMargin: Space.space3; Layout.bottomMargin: Space.space3 }
            Text { textFormat: Text.PlainText; text: qsTr("01   Votre serveur"); color: Colors.textPrimary; font.family: Type.panelTitle.family; font.pixelSize: 15; font.weight: Font.DemiBold }
            AcpTextField {
                id: urlField; objectName: "connexion-adresse"; Layout.fillWidth: true
                placeholder: "https://votre-serveur.invalid"; accessibleName: qsTr("Adresse du serveur")
                text: Shell.serverUrl; enabled: !page.enAttente; errorText: page.urlError
                onAccepted: page.submitUrl()
            }
            RowLayout {
                Layout.fillWidth: true
                AcpButton { label: qsTr("Enregistrer et tester"); primary: Shell.firstRun; manualEnabled: urlField.text.length > 0 && !page.enAttente; onTriggered: page.submitUrl() }
                Item { Layout.fillWidth: true }
                AcpButton { label: qsTr("Développement"); onTriggered: page.development = !page.development }
            }
            CheckBox { id: loopbackBox; visible: page.development; text: qsTr("Autoriser HTTP uniquement sur cette machine"); checked: Shell.allowsInsecureLoopback; enabled: !page.enAttente; Accessible.name: text }
            RowLayout {
                Layout.fillWidth: true; visible: !Shell.firstRun
                StatusChip { statusKey: Health.linkStatus === LinkStatus.Online ? "succeeded" : Health.linkStatus === LinkStatus.Degraded ? "degraded" : Health.linkStatus === LinkStatus.Offline ? "offline" : "unknown"; label: Health.linkStatusLabel }
                Text { textFormat: Text.PlainText; text: Health.detail; color: Colors.textSecondary; font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Colors.borderSubtle; Layout.topMargin: Space.space3; Layout.bottomMargin: Space.space3 }
            Text { textFormat: Text.PlainText; text: qsTr("02   Votre connexion"); color: Colors.textPrimary; font.family: Type.panelTitle.family; font.pixelSize: 15; font.weight: Font.DemiBold }
            Text { textFormat: Text.PlainText; text: qsTr("Votre clé d'accès ou mot de passe reste dans le navigateur. ACP reçoit la confirmation de connexion."); color: Colors.textSecondary; font.family: Type.prose.family; font.pixelSize: 14; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            CheckBox {
                objectName: "connexion-memoriser"; text: qsTr("Retrouver ma session au prochain lancement")
                checked: Session.memoriser; enabled: !page.enAttente
                onToggled: Session.memoriser = checked
                Accessible.description: qsTr("Le jeton de renouvellement est protégé dans le coffre Windows.")
            }
            AcpButton { objectName: "connexion-se-connecter"; label: qsTr("Se connecter avec le navigateur"); iconName: "chevronRight"; primary: true; commandId: "session.signIn"; Layout.fillWidth: true }
            Text { textFormat: Text.PlainText;
                visible: page.enAttente; Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: Session.etat === SessionStatus.Echange ? qsTr("Connexion reçue, vérification…") : qsTr("Terminez la connexion dans votre navigateur · %1 s restantes.").arg(Session.secondesRestantes)
                color: Colors.accentPrimary; font.family: Type.prose.family; font.pixelSize: 14
            }
            RowLayout {
                visible: page.enAttente; spacing: Space.space4
                AcpButton { objectName: "connexion-annuler"; label: qsTr("Annuler"); onTriggered: Session.annulerConnexion() }
                AcpButton { objectName: "connexion-copier-lien"; visible: Session.etat === SessionStatus.AttenteNavigateur; label: qsTr("Copier le lien"); onTriggered: Shell.notify(Session.copierLienConnexion() ? qsTr("Lien de connexion copié.") : qsTr("Le lien n'a pas pu être copié.")) }
            }
            Text { textFormat: Text.PlainText; visible: Session.navigateurNonOuvert; text: qsTr("Le navigateur ne s'est pas ouvert. Copiez le lien et ouvrez-le dans un navigateur de ce poste."); Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Status.statusDegradedForeground; font.pixelSize: 14 }
            Text { textFormat: Text.PlainText; visible: Session.derniereErreur.length > 0; text: Session.derniereErreur; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Status.statusFailedForeground; font.pixelSize: 14; Accessible.role: Accessible.AlertMessage }
            Text { textFormat: Text.PlainText; visible: Session.avertissement.length > 0; text: Session.avertissement; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary; font.pixelSize: 13 }
            Text { textFormat: Text.PlainText; visible: Session.avisCoffre.length > 0; text: Session.avisCoffre; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Colors.textSecondary; font.pixelSize: 13 }
            AcpButton { label: page.showDetails ? qsTr("Masquer les détails") : qsTr("Détails de connexion"); onTriggered: page.showDetails = !page.showDetails }
            ColumnLayout {
                visible: page.showDetails; Layout.fillWidth: true
                KeyValueRow { Layout.fillWidth: true; label: qsTr("Version de Hermes"); value: Health.hermesVersion }
                KeyValueRow { Layout.fillWidth: true; label: qsTr("Dernier échange réussi"); value: Health.lastSuccessLabel }
                KeyValueRow { Layout.fillWidth: true; label: qsTr("Session"); value: Session.libelleEtat }
            }
        }
    }
    function submitUrl() { page.urlError = Shell.applyServerUrl(urlField.text, loopbackBox.checked); }
}
