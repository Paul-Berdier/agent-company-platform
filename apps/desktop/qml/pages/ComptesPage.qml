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
    function donneesCompte(moteur) {
        const liste = Comptes.comptes
        for (let i = 0; i < liste.length; ++i) if (liste[i].moteur === moteur) return liste[i]
        return { moteur: moteur, nom: "", implementation: "non_implemente", etat: "inconnu", libelle: "", message: "", modeles: [], aliasDocumentes: [], observation: "", quotasRapportes: 0 }
    }
    function montrer(debut, fin) {
        // ScrollView possède un Flickable interne : suivre les parents réels du formulaire.
        let vue = fin.parent
        while (vue && (vue.contentY === undefined || vue.contentHeight === undefined)) vue = vue.parent
        if (!vue || !fin.visible || vue.height <= 0) return
        const haut = debut.mapToItem(vue.contentItem, 0, 0).y
        const bas = fin.mapToItem(vue.contentItem, 0, fin.height).y
        let position = vue.contentY
        if (bas + Space.space4 > position + vue.height) position = bas + Space.space4 - vue.height
        if (haut - Space.space4 < position) position = haut - Space.space4
        vue.contentY = Math.max(0, Math.min(position, Math.max(0, vue.contentHeight - vue.height)))
    }
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
                // Identités fixes : un GET ne détruit jamais le champ ni son focus.
                model: ["codex", "claude_code", "mistral_vibe"]
                delegate: Carte {
                    id: compte
                    required property string modelData
                    readonly property var donnees: page.donneesCompte(modelData)
                    readonly property bool procedure: Comptes.connexion.moteur === modelData && (Comptes.connexion.id || "").length > 0
                    visible: donnees.nom.length > 0
                    Layout.fillWidth: true
                    objectName: "compte-" + modelData
                    titre: donnees.nom
                    cle: donnees.etat === "inconnu" ? "unknown" : donnees.compteConnecte === true ? "succeeded" : donnees.etat === "connexion_en_attente" ? "pending" : "notConfigured"
                    libelleEtat: donnees.implementation === "non_implemente" ? qsTr("Non pris en charge dans cette version") : donnees.libelle
                    sousTitre: donnees.message
                    ColumnLayout {
                        id: panneauConnexion
                        visible: compte.procedure
                        readonly property string defi: compte.procedure ? Comptes.connexion.defiId || "" : ""
                        function montrerDefi() {
                            if (visible && Comptes.attente) page.montrer(retourCode.visible ? retourCode : panneauConnexion, actionsConnexion)
                        }
                        onVisibleChanged: if (visible && Comptes.attente) Qt.callLater(montrerDefi)
                        onDefiChanged: if (defi.length > 0) Qt.callLater(montrerDefi)
                        Layout.fillWidth: true
                        spacing: Space.space3
                        Paragraphe { objectName: "comptes-connexion-etat" + (compte.modelData === "codex" ? "" : "-" + compte.modelData); text: Comptes.connexion.libelle || ""; color: Colors.textPrimary; font.weight: Font.DemiBold }
                        Paragraphe { text: Comptes.connexion.message || "" }
                        Paragraphe { visible: Comptes.attente; text: qsTr("Vous pouvez terminer cette procédure jusqu’à %1. ACP suit sa confirmation automatiquement.").arg(Comptes.connexion.limite || qsTr("une heure inconnue")) }
                        TextArea {
                            objectName: "comptes-code"
                            visible: compte.donnees.moteur === "codex" && (Comptes.connexion.code || "").length > 0
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
                        Paragraphe {
                            visible: compte.donnees.moteur === "claude_code" && (Comptes.connexion.receptionCodeEtat || "").length > 0
                            text: Comptes.connexion.receptionCodeEtat === "en_attente" ? qsTr("Code reçu, remise à Claude en attente…")
                                : Comptes.connexion.receptionCodeEtat === "transmis" ? qsTr("Code transmis. La connexion reste à confirmer.")
                                : Comptes.connexion.receptionCodeEtat === "non_recue" ? qsTr("Le code n’a pas été reçu. Vous pouvez le coller de nouveau pour réessayer.")
                                : qsTr("La remise du code n’est plus confirmable après une interruption. Attendez la vérification du compte, ou annulez cette procédure puis recommencez la connexion.")
                            Accessible.role: Accessible.StaticText
                            Accessible.name: text
                        }
                        AcpTextField {
                            id: retourCode
                            objectName: compte.modelData === "claude_code" ? "comptes-code-claude" : ""
                            Layout.fillWidth: true
                            visible: compte.donnees.moteur === "claude_code" && panneauConnexion.defi.length > 0 && Comptes.attente
                            enabled: Comptes.peutSaisirCode
                            activeFocusOnTab: true
                            KeyNavigation.tab: validerCode
                            onVisibleChanged: if (!visible) text = ""
                            onEnabledChanged: if (!enabled) text = ""
                            masked: true
                            placeholder: qsTr("Code temporaire affiché par Anthropic")
                            accessibleName: qsTr("Code temporaire de connexion Claude")
                            helperText: qsTr("Collez uniquement le code de cette autorisation. Ce champ est effacé dès l’envoi.")
                            function envoyer() {
                                if (!Comptes.peutSaisirCode || text.length === 0) return
                                const code = text
                                text = ""
                                Comptes.soumettreCode(code)
                            }
                            onAccepted: envoyer()
                            Connections {
                                target: Comptes
                                function onEffacerCodeTemporaire() { retourCode.text = "" }
                            }
                        }
                        Flow {
                            id: actionsConnexion
                            Layout.fillWidth: true
                            spacing: Space.space3
                            AcpButton {
                                KeyNavigation.tab: compte.modelData === "claude_code" ? retourCode : null
                                objectName: "comptes-ouvrir-autorisation" + (compte.modelData === "codex" ? "" : "-" + compte.modelData)
                                visible: panneauConnexion.defi.length > 0
                                manualEnabled: Comptes.peutOuvrirVerification
                                label: compte.donnees.moteur === "claude_code" ? qsTr("Ouvrir Anthropic dans le navigateur") : qsTr("Ouvrir OpenAI dans le navigateur")
                                primary: true
                                onTriggered: Comptes.ouvrirVerification()
                            }
                            AcpButton {
                                id: validerCode
                                objectName: compte.modelData === "claude_code" ? "comptes-envoyer-code-claude" : ""
                                visible: compte.donnees.moteur === "claude_code" && panneauConnexion.defi.length > 0
                                manualEnabled: Comptes.peutSaisirCode && retourCode.text.length > 0
                                label: qsTr("Valider le code")
                                primary: true
                                onTriggered: retourCode.envoyer()
                            }
                            AcpButton {
                                objectName: "comptes-annuler" + (compte.modelData === "codex" ? "" : "-" + compte.modelData)
                                visible: Comptes.attente
                                manualEnabled: !Comptes.gesteEnCours && Comptes.connexion.etat !== "annulation_demandee"
                                label: qsTr("Annuler la connexion")
                                onTriggered: Comptes.annulerConnexion()
                            }
                        }
                    }
                    RowLayout {
                        visible: compte.donnees.implementation === "disponible"
                        Layout.fillWidth: true
                        spacing: Space.space5
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Version distante"); value: compte.donnees.version || qsTr("Inconnue") }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Inférence"); value: compte.donnees.inferenceVerifiee ? qsTr("Vérifiée") : qsTr("Non vérifiée") }
                    }
                    Paragraphe {
                        visible: compte.donnees.implementation === "disponible"
                        text: compte.donnees.modeles.length > 0
                            ? qsTr("Modèles rapportés par le moteur : %1").arg(compte.donnees.modeles.join(", "))
                            : qsTr("Aucun modèle autorisé confirmé par ce parcours. Un compte connecté ne garantit ni le quota ni la possibilité d’exécuter une tâche.")
                    }
                    Paragraphe {
                        visible: compte.donnees.implementation === "disponible"
                        text: compte.donnees.observation
                    }
                    Paragraphe {
                        visible: compte.donnees.implementation === "disponible" && compte.donnees.quotasRapportes > 0
                        text: qsTr("%1 compteurs de quota rapportés. Détail dans Quotas et budgets.").arg(compte.donnees.quotasRapportes)
                    }
                    Paragraphe {
                        visible: (compte.donnees.aliasDocumentes || []).length > 0
                        text: qsTr("Alias Claude documentés : %1. Leur disponibilité pour votre compte reste à vérifier.").arg((compte.donnees.aliasDocumentes || []).join(", "))
                    }
                    AcpButton {
                        objectName: compte.modelData === "claude_code" ? "comptes-connecter-claude" : ""
                        visible: compte.donnees.moteur === "claude_code" && compte.donnees.implementation === "disponible" && !Comptes.attente
                        label: compte.donnees.compteConnecte === true ? qsTr("Reconnecter Claude") : qsTr("Connecter Claude")
                        primary: true
                        manualEnabled: Comptes.peutConnecterClaude
                        onTriggered: Comptes.connecterClaude()
                    }
                    AcpButton {
                        objectName: compte.modelData === "codex" ? "comptes-connecter-codex" : ""
                        visible: compte.donnees.moteur === "codex" && !Comptes.attente
                        label: compte.donnees.compteConnecte === true ? qsTr("Reconnecter Codex") : qsTr("Connecter Codex")
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
