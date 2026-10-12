import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Controls

Carte {
    id: carte
    required property var preparation
    objectName: "hermes-connexion"
    titre: qsTr("Hermes · coordinateur")
    sousTitre: qsTr("Retrouver votre configuration serveur ou connecter le compte ChatGPT utilisé par Hermes.")
    cle: preparation.etat === "pret" ? "succeeded"
        : preparation.etat === "erreur" ? "degraded"
        : preparation.occupe ? "running" : "pending"
    libelleEtat: preparation.libelle
    lecture: preparation.lecture

    Text {
        Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText
        text: carte.preparation.detail
        color: Colors.textSecondary
        font.family: Type.prose.family; font.pixelSize: Type.prose.pixelSize
    }
    Text {
        visible: carte.preparation.modele.length > 0
        Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText
        text: carte.preparation.fournisseur + " · " + carte.preparation.modele
        color: Colors.textPrimary
        font.family: Type.prose.family; font.pixelSize: Type.prose.pixelSize
        font.weight: Font.DemiBold
    }
    Text {
        Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText
        text: carte.preparation.prochaineAction
        color: Colors.textPrimary
        font.family: Type.prose.family; font.pixelSize: Type.prose.pixelSize
    }
    ColumnLayout {
        visible: carte.preparation.defiActif
        Layout.fillWidth: true
        Text {
            text: qsTr("Code à saisir sur auth.openai.com")
            textFormat: Text.PlainText; color: Colors.textSecondary
            font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize
        }
        Text {
            objectName: "hermes-code-appareil"
            text: carte.preparation.codeAppareil
            textFormat: Text.PlainText; color: Colors.textPrimary
            font.family: Type.identifier.family; font.pixelSize: 24; font.weight: Font.DemiBold
            Accessible.name: qsTr("Code d'appareil : %1").arg(text)
        }
        Text {
            text: qsTr("Expire dans %1 s").arg(carte.preparation.secondesRestantes)
            textFormat: Text.PlainText; color: Colors.textSecondary
            font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize
        }
        Flow {
            Layout.fillWidth: true; spacing: Space.space3
            AcpButton {
                objectName: "hermes-ouvrir-autorisation"
                label: qsTr("Ouvrir OpenAI"); primary: true
                onTriggered: carte.preparation.ouvrirVerification()
            }
            AcpButton {
                objectName: "hermes-copier-code"
                label: qsTr("Copier le code")
                onTriggered: carte.preparation.copierCode()
            }
        }
    }
    Flow {
        Layout.fillWidth: true; spacing: Space.space3
        AcpButton {
            objectName: "hermes-verifier"
            label: qsTr("Vérifier Hermes")
            manualEnabled: carte.preparation.peutVerifier
            visible: !carte.preparation.defiActif
            onTriggered: carte.preparation.verifier()
        }
        AcpButton {
            objectName: "hermes-connecter"
            label: carte.preparation.etat === "pret" && carte.preparation.fournisseur === "openai-codex" ? qsTr("Reconnecter ChatGPT") : qsTr("Connecter ChatGPT à Hermes")
            primary: carte.preparation.etat === "manquant"
            manualEnabled: carte.preparation.peutConnecter
            visible: !carte.preparation.occupe
            onTriggered: carte.preparation.connecter()
        }
        AcpButton {
            objectName: "hermes-annuler"
            label: qsTr("Annuler")
            visible: carte.preparation.etat === "demarrage" || carte.preparation.defiActif
            onTriggered: carte.preparation.annuler()
        }
        AcpButton {
            objectName: "hermes-tableau-de-bord"
            label: qsTr("Ouvrir le tableau de bord")
            visible: !carte.preparation.occupe
            onTriggered: carte.preparation.ouvrirTableauDeBord()
        }
    }
}