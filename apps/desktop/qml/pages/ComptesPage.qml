// Comptes et assistants : trois choses distinctes, jamais confondues.
//
// 1. Votre identité ACP : la session de la station auprès de Hermes (OIDC, Authelia).
// 2. Les assistants de code, PAR MACHINE : l'état que l'exécutant OBSERVE et publie dans son
//    inventaire (connexions Codex et Claude Code). Un compte connecté sur un poste ne l'est
//    pas sur l'exécutant Railway. La station ne collecte, ne copie ni ne transmet aucun jeton :
//    la connexion se fait par le binaire officiel, en console, par le propriétaire (D83, D84).
// 3. Le modèle de coordination de Hermes : configuré sur le serveur, pas par la station.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

ScrollView {
    id: page
    objectName: "page-comptes"
    clip: true
    contentWidth: availableWidth

    // Cette section est la seule vue affichée du modèle Poste : elle le dit lu.
    Component.onCompleted: Poste.pageVisible = true
    Component.onDestruction: Poste.pageVisible = false

    readonly property var inv: Poste.inventaire

    component Aide: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textSecondary
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }
    component Commande: TextEdit {
        Layout.fillWidth: true
        readOnly: true
        selectByMouse: true
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.Wrap
        color: Colors.textPrimary
        font.family: Type.identifier.family
        font.pixelSize: Type.identifier.pixelSize
        Accessible.role: Accessible.StaticText
        Accessible.name: text
    }

    ColumnLayout {
        width: Math.min(page.availableWidth - Space.space7 * 2, 960)
        x: Space.space7
        spacing: Space.space5

        TextePixel { Layout.topMargin: Space.space6; text: qsTr("COMPTES"); couleur: "accent"; echelle: 2 }

        Carte {
            objectName: "comptes-identite"
            Layout.fillWidth: true
            titre: qsTr("Votre identité ACP")
            cle: Session.connectee ? "succeeded" : "offline"
            libelleEtat: Session.connectee ? qsTr("Connecté") : Session.libelleEtat
            KeyValueRow { Layout.fillWidth: true; label: qsTr("Nom"); value: Session.nomAffiche; known: Session.nomAffiche.length > 0 }
            KeyValueRow { Layout.fillWidth: true; label: qsTr("Courriel"); value: Session.courriel; known: Session.courriel.length > 0 }
            KeyValueRow { Layout.fillWidth: true; label: qsTr("Fournisseur d'identité"); value: Session.fournisseur; known: Session.fournisseur.length > 0 }
            KeyValueRow { Layout.fillWidth: true; label: qsTr("Serveur Hermes"); value: Shell.serverUrlLabel; monospace: true }
            Aide { text: qsTr("La connexion et la déconnexion se règlent dans « Connexion et mises à jour ».") }
        }

        Carte {
            objectName: "comptes-assistants"
            Layout.fillWidth: true
            titre: qsTr("Assistants de code de l'exécutant")
            sousTitre: Poste.machine.nom ? qsTr("Machine : %1").arg(Poste.machine.nom) : qsTr("Machine : Inconnue")
            lecture: Poste.lecture
            erreurLecture: Poste.erreur
            Aide {
                visible: page.inv.present !== true
                text: qsTr("Aucun inventaire publié : l'état des comptes est Inconnu. Il apparaît après le premier relevé de l'exécutant.")
            }
            RowLayout {
                Layout.fillWidth: true
                visible: page.inv.present === true
                spacing: Space.space4
                PortraitAgent { role: "developpeur"; etat: "repos"; echelle: 3 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space2
                    RowLayout {
                        Text { text: qsTr("Codex"); textFormat: Text.PlainText; color: Colors.textPrimary; font.family: Type.tableCellEmphasis.family; font.pixelSize: Type.tableCellEmphasis.pixelSize; font.weight: Type.tableCellEmphasis.weight }
                        StatusChip { objectName: "comptes-codex"; statusKey: page.inv.codexCle || "unknown"; label: page.inv.codexLibelle || "" }
                    }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Offre observée"); value: page.inv.offre || ""; known: (page.inv.offre || "").length > 0 && page.inv.offre !== qsTr("Inconnu") }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Dernier relevé"); value: page.inv.releveLe || "" }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: page.inv.present === true
                spacing: Space.space4
                PortraitAgent { role: "relecteur"; etat: "repos"; echelle: 3 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space2
                    RowLayout {
                        Text { text: qsTr("Claude Code"); textFormat: Text.PlainText; color: Colors.textPrimary; font.family: Type.tableCellEmphasis.family; font.pixelSize: Type.tableCellEmphasis.pixelSize; font.weight: Type.tableCellEmphasis.weight }
                        StatusChip { objectName: "comptes-claude"; statusKey: page.inv.claudeCle || "unknown"; label: page.inv.claudeLibelle || "" }
                    }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Dernier relevé"); value: page.inv.releveLe || "" }
                }
            }
            RowLayout {
                AcpButton {
                    objectName: "comptes-relever"
                    label: qsTr("Demander un nouveau relevé")
                    manualEnabled: Poste.peutRelever && !Poste.gesteEnCours
                    onTriggered: Poste.relever()
                }
                Aide { text: Poste.peutRelever ? "" : qsTr("Relevé à la demande indisponible (aucune machine active ou geste en cours).") }
            }
        }

        Carte {
            objectName: "comptes-gestes"
            Layout.fillWidth: true
            titre: qsTr("Connecter ou reconnecter un assistant")
            sousTitre: qsTr("Geste du propriétaire, dans le terminal officiel ; jamais par un agent, jamais par la station.")
            Aide {
                text: qsTr("Dans une session « railway ssh » sur le service executant (clé dédiée, retirée après "
                           + "l'opération), suspendez les réclamations, connectez, puis reprenez. Codex : activez d'abord "
                           + "la connexion par code d'appareil dans les réglages de sécurité de votre compte ChatGPT ; le "
                           + "lien et le code s'affichent dans la session. Claude Code : le jeton vient de « claude "
                           + "setup-token » lancé sur votre PC, saisi masqué dans la session.")
            }
            Commande {
                objectName: "comptes-commandes"
                text: "acp-poste pause\nacp-poste connexion codex\nacp-poste connexion claude\nacp-poste reprise\nacp-poste diagnostic"
            }
            Aide {
                text: qsTr("Procédure complète et vérifications : docs/refonte/railway.md, § 13.5. Le code et le jeton ne "
                           + "transitent jamais par Hermes ni par la station. Après le geste, « Demander un nouveau relevé » "
                           + "ci-dessus montre l'état observé ; rien n'est déclaré connecté avant ce relevé.")
            }
        }

        Carte {
            objectName: "comptes-hermes"
            Layout.fillWidth: true
            titre: qsTr("Modèle de coordination de Hermes")
            cle: "unknown"
            libelleEtat: qsTr("Non communiqué")
            Aide {
                text: qsTr("Le fournisseur et le modèle qui font raisonner Hermes sont configurés sur le serveur (image et "
                           + "volume Railway, docs/refonte/image.md) ; ce serveur ne les communique pas à la station. Ils "
                           + "sont distincts des comptes des assistants de code : un catalogue de modèles d'un compte ne "
                           + "valide jamais un autre fournisseur.")
            }
        }
        Item { Layout.preferredHeight: Space.space8 }
    }
}
