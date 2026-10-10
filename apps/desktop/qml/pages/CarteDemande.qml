// Une demande de l'agent (`approval` ou `clarify`) d'une session ouverte dans la station.
// Les boutons de choix viennent des choix OFFERTS par Hermes ; un lot de questions reçoit une
// réponse par question. La réponse part par le canal JSON-RPC (DemandesAgent), avec le même
// identifiant que la demande.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Rectangle {
    id: carte

    required property var demande

    readonly property bool approbation: carte.demande.methode === "approval"

    implicitHeight: colonne.implicitHeight + Space.space5 * 2
    radius: Radius.radiusMd
    color: Status.statusApprovalRequiredTint
    border.width: Space.layoutBorderWidth
    border.color: Status.statusApprovalRequiredBorder
    Accessible.role: Accessible.Grouping
    Accessible.name: carte.demande.titre

    component Libelle: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textSecondary
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    ColumnLayout {
        id: colonne
        anchors.fill: parent
        anchors.margins: Space.space5
        spacing: Space.space3

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: carte.demande.titre
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Status.statusApprovalRequiredForeground
                font.family: Type.panelTitle.family
                font.pixelSize: Type.panelTitle.pixelSize
                font.weight: Type.panelTitle.weight
            }
            StatusChip { statusKey: "approvalRequired"; label: qsTr("Votre décision est attendue") }
        }
        Libelle {
            visible: carte.demande.rejouee
            text: qsTr("Demande reproposée par Hermes après une reconnexion.")
        }

        // --- Autorisation ----------------------------------------------------------------------
        BlocTexte {
            Layout.fillWidth: true
            visible: carte.approbation && carte.demande.commande.length > 0
            libelle: qsTr("Commande (expurgée par Hermes)")
            texte: carte.demande.commande
            monospace: true
        }
        BlocTexte {
            Layout.fillWidth: true
            visible: carte.approbation && carte.demande.description.length > 0
            libelle: qsTr("Description")
            texte: carte.demande.description
        }
        Libelle {
            visible: carte.approbation && carte.demande.outil.length > 0
            text: qsTr("Outil : %1").arg(carte.demande.outil)
        }
        Libelle {
            visible: carte.demande.sansChoix && carte.approbation
            text: qsTr("Hermes n'offre aucun choix reconnu par la station : la demande expirera d'elle-même.")
        }
        Flow {
            Layout.fillWidth: true
            visible: carte.approbation
            spacing: Space.space3
            Repeater {
                model: carte.approbation ? carte.demande.choix : []
                delegate: AcpButton {
                    required property var modelData
                    objectName: "demande-" + carte.demande.id + "-" + modelData.valeur
                    label: modelData.libelle
                    primary: modelData.valeur === "once"
                    onTriggered: Demandes.approuver(carte.demande.id, modelData.valeur)
                }
            }
        }

        // --- Question simple ---------------------------------------------------------------------
        BlocTexte {
            Layout.fillWidth: true
            visible: !carte.approbation && !carte.demande.estLot
            texte: carte.demande.question
            vide: qsTr("Question sans texte.")
        }
        Flow {
            Layout.fillWidth: true
            visible: !carte.approbation && !carte.demande.estLot && !carte.demande.multiple
            spacing: Space.space3
            Repeater {
                model: !carte.approbation && !carte.demande.estLot && !carte.demande.multiple ? carte.demande.choix : []
                delegate: AcpButton {
                    required property var modelData
                    label: modelData.libelle
                    onTriggered: Demandes.clarifier(carte.demande.id, modelData.valeur)
                }
            }
        }
        ColumnLayout {
            id: selection
            Layout.fillWidth: true
            visible: !carte.approbation && !carte.demande.estLot && carte.demande.multiple
            property var retenus: []
            Repeater {
                model: !carte.approbation && !carte.demande.estLot && carte.demande.multiple ? carte.demande.choix : []
                delegate: CheckBox {
                    required property var modelData
                    text: modelData.libelle
                    onToggled: {
                        const autres = selection.retenus.filter(v => v !== modelData.valeur);
                        selection.retenus = checked ? autres.concat([modelData.valeur]) : autres;
                    }
                }
            }
            AcpButton {
                label: qsTr("Valider la sélection")
                manualEnabled: selection.retenus.length > 0
                onTriggered: Demandes.clarifierSelection(carte.demande.id, selection.retenus)
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: !carte.approbation && !carte.demande.estLot
            spacing: Space.space2
            Libelle { text: carte.demande.sansChoix ? qsTr("Votre réponse") : qsTr("Ou une autre réponse") }
            AcpTextField {
                id: reponseLibre
                Layout.fillWidth: true
                placeholder: qsTr("Votre réponse")
                accessibleName: qsTr("Votre réponse à Hermes")
            }
            RowLayout {
                spacing: Space.space3
                AcpButton {
                    primary: true
                    label: qsTr("Répondre")
                    manualEnabled: reponseLibre.text.trim().length > 0
                    onTriggered: Demandes.clarifier(carte.demande.id, reponseLibre.text)
                }
                AcpButton {
                    label: qsTr("Passer la question")
                    onTriggered: Demandes.clarifier(carte.demande.id, "")
                }
            }
        }

        // --- Lot de questions ----------------------------------------------------------------------
        ColumnLayout {
            id: lot
            Layout.fillWidth: true
            visible: !carte.approbation && carte.demande.estLot
            spacing: Space.space3
            property var reponses: ({})
            Repeater {
                model: !carte.approbation && carte.demande.estLot ? carte.demande.lot : []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Space.space1
                    BlocTexte { Layout.fillWidth: true; texte: modelData.question }
                    Libelle {
                        visible: modelData.choix.length > 0
                        text: qsTr("Choix proposés : %1").arg(modelData.choix.map(c => c.libelle).join(", "))
                    }
                    AcpTextField {
                        Layout.fillWidth: true
                        text: modelData.verrouillee
                        placeholder: qsTr("Votre réponse (vide pour passer)")
                        accessibleName: modelData.question
                        Component.onCompleted: {
                            const copie = Object.assign({}, lot.reponses);
                            copie[modelData.qid] = text;
                            lot.reponses = copie;
                        }
                        onTextChanged: {
                            const copie = Object.assign({}, lot.reponses);
                            copie[modelData.qid] = text;
                            lot.reponses = copie;
                        }
                    }
                }
            }
            AcpButton {
                primary: true
                label: qsTr("Envoyer les réponses")
                onTriggered: Demandes.clarifierLot(carte.demande.id, lot.reponses)
            }
        }
    }
}
