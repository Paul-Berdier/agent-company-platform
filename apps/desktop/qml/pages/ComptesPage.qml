import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    property bool identitesOuvertes: false
    Component.onCompleted: Comptes.pageVisible = visible
    onVisibleChanged: Comptes.pageVisible = visible
    Component.onDestruction: Comptes.pageVisible = false

    component Paragraphe: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textSecondary
        font.family: Type.prose.family
        font.pixelSize: Type.prose.pixelSize
    }
    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: Math.max(0, Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth))
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space5
            Item { Layout.preferredHeight: Space.space4 }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Comptes et modèles")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton { objectName: "comptes-actualiser"; label: qsTr("Actualiser"); manualEnabled: !Comptes.chargement && !Comptes.gesteEnCours; onTriggered: Comptes.actualiser() }
            }
            Paragraphe {
                text: qsTr("Connectez les moteurs qui réalisent vos projets sur le serveur. Votre PC affiche le travail ; il n’exécute aucun agent.")
            }
            Carte {
                Layout.fillWidth: true
                titre: qsTr("Exécution distante")
                cle: !Comptes.lue ? "unknown" : Comptes.serveur.disponible ? "succeeded" : "notConfigured"
                libelleEtat: !Comptes.lue ? qsTr("État non lu") : Comptes.serveur.disponible ? qsTr("Serveur joignable") : qsTr("Serveur indisponible")
                sousTitre: Comptes.serveur.nom || qsTr("Le serveur d’exécution est choisi par Hermes.")
                Paragraphe { visible: (Comptes.serveur.raison || "").length > 0; text: Comptes.serveur.raison || "" }
            }
            BandeauMessage { Layout.fillWidth: true; message: Comptes.messageGeste; erreur: Comptes.erreurGeste; alerte: Comptes.alerteGeste }
            Paragraphe {
                objectName: "comptes-erreur"
                visible: Comptes.erreur.length > 0
                text: Comptes.erreur
                color: Status.statusFailedForeground
                Accessible.role: Accessible.AlertMessage
                Accessible.name: text
            }
            Paragraphe { visible: !Comptes.lue && Comptes.erreur.length === 0; text: qsTr("Lecture des comptes du serveur…") }
            Repeater {
                model: Comptes.comptes
                delegate: Carte {
                    id: compte
                    required property var modelData
                    Layout.fillWidth: true
                    objectName: "compte-" + modelData.moteur
                    titre: modelData.nom
                    cle: modelData.etat === "inconnu" ? "unknown" : modelData.compteConnecte === true ? "succeeded" : modelData.etat === "connexion_en_attente" ? "pending" : "notConfigured"
                    libelleEtat: modelData.implementation === "non_implemente" ? qsTr("Non pris en charge dans cette version") : modelData.libelle
                    sousTitre: modelData.message
                    RowLayout {
                        visible: compte.modelData.implementation === "disponible"
                        Layout.fillWidth: true
                        spacing: Space.space5
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Version distante"); value: compte.modelData.version || qsTr("Inconnue") }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Inférence"); value: compte.modelData.inferenceVerifiee ? qsTr("Vérifiée") : qsTr("Non vérifiée") }
                    }
                    Paragraphe {
                        visible: compte.modelData.implementation === "disponible"
                        text: compte.modelData.modeles.length > 0
                            ? qsTr("Modèles rapportés par le moteur : %1").arg(compte.modelData.modeles.join(", "))
                            : qsTr("Aucun modèle autorisé confirmé par ce parcours. Un compte connecté ne garantit ni le quota ni la possibilité d’exécuter une tâche.")
                    }
                    Paragraphe {
                        visible: compte.modelData.implementation === "disponible"
                        text: compte.modelData.observation
                    }
                    Paragraphe {
                        visible: compte.modelData.implementation === "disponible" && compte.modelData.quotasRapportes > 0
                        text: qsTr("%1 compteurs de quota rapportés. Détail dans Quotas et budgets.").arg(compte.modelData.quotasRapportes)
                    }
                    ColumnLayout {
                        visible: compte.modelData.moteur === "codex" && (Comptes.connexion.id || "").length > 0
                        Layout.fillWidth: true
                        spacing: Space.space3
                        Paragraphe { objectName: "comptes-connexion-etat"; text: Comptes.connexion.libelle || ""; color: Colors.textPrimary; font.weight: Font.DemiBold }
                        Paragraphe { text: Comptes.connexion.message || "" }
                        Paragraphe { visible: Comptes.attente; text: qsTr("Limite d’attente ACP : %1. Le serveur suit la confirmation automatiquement.").arg(Comptes.connexion.limite || qsTr("Inconnue")) }
                        TextArea {
                            objectName: "comptes-code"
                            visible: (Comptes.connexion.code || "").length > 0
                            Layout.fillWidth: true
                            readOnly: true; selectByMouse: true
                            text: Comptes.connexion.code || ""
                            textFormat: TextEdit.PlainText
                            color: Colors.textPrimary
                            font.family: Type.identifier.family
                            font.pixelSize: 26
                            Accessible.name: qsTr("Code temporaire de connexion Codex")
                        }
                        Paragraphe { visible: (Comptes.connexion.url || "").length > 0; text: Comptes.connexion.url || "" }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Space.space3
                            AcpButton {
                                objectName: "comptes-ouvrir-autorisation"
                                visible: (Comptes.connexion.url || "").length > 0
                                label: qsTr("Ouvrir OpenAI dans le navigateur")
                                primary: true
                                onTriggered: Comptes.ouvrirVerification()
                            }
                            AcpButton {
                                objectName: "comptes-annuler"
                                visible: Comptes.attente
                                manualEnabled: !Comptes.gesteEnCours && Comptes.connexion.etat !== "annulation_demandee"
                                label: qsTr("Annuler la connexion")
                                onTriggered: Comptes.annulerConnexion()
                            }
                        }
                    }
                    AcpButton {
                        objectName: "comptes-connecter-codex"
                        visible: compte.modelData.moteur === "codex" && !Comptes.attente
                        label: compte.modelData.compteConnecte === true ? qsTr("Reconnecter Codex") : qsTr("Connecter Codex")
                        primary: true
                        manualEnabled: Comptes.peutConnecter
                        onTriggered: Comptes.connecterCodex()
                    }
                }
            }
            Paragraphe {
                text: qsTr("La déconnexion d’un compte moteur depuis cette interface n’est pas encore disponible.")
            }
            Flow {
                Layout.fillWidth: true; spacing: Space.space3
                AcpButton { label: qsTr("Modèles d’exécution"); onTriggered: Navigation.setCurrentRoute("routing") }
                AcpButton { label: qsTr("Quotas et budgets"); onTriggered: Navigation.setCurrentRoute("quotas") }
            }
            AcpButton {
                objectName: "comptes-identites"
                label: page.identitesOuvertes ? qsTr("Masquer l’accès ACP et le coordinateur") : qsTr("Mon accès ACP et le coordinateur Hermes")
                onTriggered: page.identitesOuvertes = !page.identitesOuvertes
            }
            GridLayout {
                visible: page.identitesOuvertes
                Layout.fillWidth: true
                columns: page.width >= 1100 ? 2 : 1
                columnSpacing: Space.space5; rowSpacing: Space.space5
                Carte {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    titre: qsTr("Mon accès ACP")
                    cle: Session.connectee ? "succeeded" : "notConfigured"
                    libelleEtat: Session.libelleEtat
                    sousTitre: qsTr("Cette session vous donne accès à vos projets. Elle est distincte des comptes Codex et Claude Code.")
                    Paragraphe { text: Session.nomAffiche || qsTr("Identité non confirmée") }
                    AcpButton { label: qsTr("Gérer ma session ACP"); onTriggered: Navigation.setCurrentRoute("settings") }
                }
                HermesConnectionCard {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                    preparation: PreparationHermes
                    sousTitre: qsTr("Le compte de coordination permet à Hermes de planifier. Sa connexion n’authentifie pas les moteurs qui exécutent les tâches.")
                }
            }
            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
