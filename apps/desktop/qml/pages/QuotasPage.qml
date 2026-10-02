// Page Quotas (cahier P8 § 7.6) : quotas relevés par le poste, par voie et par compteur,
// jamais estimés. Une jauge n'est pleine que d'une part rendue par le serveur ; une part
// absente reste « Inconnu ».

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Quotas.pageVisible = true
    Component.onDestruction: Quotas.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth)
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space5

            Item { Layout.preferredHeight: Space.space4 }

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Quotas")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "quotas-relever"
                    label: qsTr("Relever maintenant")
                    manualEnabled: !Quotas.gesteEnCours
                    onTriggered: Quotas.relever()
                }
                AcpButton {
                    objectName: "quotas-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Quotas.actualiser()
                }
            }

            Discret {
                text: qsTr("Quotas relevés par le poste, jamais estimés. Au-delà du seuil, le routage écarte la voie. "
                           + "Page relue toutes les 60 secondes tant qu'elle est affichée.")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Quotas.lecture
                erreur: Quotas.erreur
            }
            BandeauMessage {
                Layout.fillWidth: true
                message: Quotas.messageGeste
                erreur: Quotas.erreurGeste
            }
            Text {
                visible: !Quotas.lue && Quotas.erreur.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            Repeater {
                model: Quotas.voies
                delegate: Carte {
                    id: voie
                    required property var item
                    objectName: "quotas-" + voie.item.voie
                    Layout.fillWidth: true
                    titre: voie.item.titre
                    cle: voie.item.etatCle
                    libelleEtat: voie.item.etatLibelle
                    KeyValueRow { Layout.fillWidth: true; visible: voie.item.releveLe.length > 0; label: qsTr("Relevé"); value: voie.item.releveLe }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Seuil du routage"); value: voie.item.seuil }
                    Discret { visible: voie.item.source.length > 0; text: voie.item.source }
                    BlocTexte { Layout.fillWidth: true; visible: voie.item.detail.length > 0; texte: voie.item.detail }
                    Discret { visible: voie.item.compteurs.length === 0; text: qsTr("Aucun compteur relevé.") }
                    Repeater {
                        model: voie.item.compteurs
                        delegate: ColumnLayout {
                            id: compteur
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Space.space2
                            RowLayout {
                                Layout.fillWidth: true
                                KeyValueRow { Layout.fillWidth: true; label: qsTr("Compteur"); value: compteur.modelData.compteur; monospace: true }
                                StatusChip {
                                    visible: compteur.modelData.limiteAtteinte
                                    statusKey: "failed"
                                    label: qsTr("Limite atteinte")
                                }
                            }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Offre"); value: compteur.modelData.offre; monospace: true }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Relevé"); value: compteur.modelData.releveLe }
                            BlocTexte { Layout.fillWidth: true; visible: compteur.modelData.detail.length > 0; texte: compteur.modelData.detail }
                            Repeater {
                                model: compteur.modelData.fenetres
                                delegate: ColumnLayout {
                                    id: fenetre
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: Space.space1
                                    QuotaGauge {
                                        Layout.fillWidth: true
                                        label: fenetre.modelData.libelle
                                        usedPercent: fenetre.modelData.utilisePct
                                        thresholdPercent: fenetre.modelData.seuilPct
                                        remainingText: fenetre.modelData.restant
                                        usedText: fenetre.modelData.utilise
                                        resetText: fenetre.modelData.remise
                                        level: fenetre.modelData.niveau
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        visible: fenetre.modelData.seuilAtteint
                                        text: qsTr("Seuil du routage atteint : la voie est écartée.")
                                        textFormat: Text.PlainText
                                        wrapMode: Text.WordWrap
                                        color: Status.statusFailedForeground
                                        font.family: Type.metadata.family
                                        font.pixelSize: Type.metadata.pixelSize
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Carte {
                objectName: "quotas-hermes"
                Layout.fillWidth: true
                visible: Quotas.lue
                titre: qsTr("Hermes (cerveau)")
                BlocTexte { Layout.fillWidth: true; texte: Quotas.hermes }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
