// Page Questions (cahier P8 § 7.3) : répondre aux questions des projets, décider des cartes en
// triage, voir les cartes bloquées. Les gestes de triage viennent de ce que le greffon offre
// pour chaque carte ; le résultat de chaque geste est celui que le serveur a rendu.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Questions.pageVisible = true
    Component.onDestruction: Questions.pageVisible = false

    function ouvrirProjet(identifiant) {
        Projets.ouvrirProjet(identifiant);
        Navigation.setCurrentRoute("projects");
    }

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    component ChampLong: TextArea {
        Layout.fillWidth: true
        Layout.preferredHeight: 84
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.PlainText
        color: Colors.textPrimary
        font.family: Type.prose.family
        font.pixelSize: Type.prose.pixelSize
        background: Rectangle {
            color: Colors.surfacePanelRaised
            radius: Radius.radiusSm
            border.width: Space.layoutBorderWidth
            border.color: parent.activeFocus ? Colors.borderFocus : Colors.borderInteractive
        }
    }

    component Separateur: Rectangle {
        Layout.fillWidth: true
        height: Space.layoutBorderWidth
        color: Colors.borderSubtle
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
                    text: qsTr("Questions")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "questions-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Questions.actualiser()
                }
            }

            Discret {
                text: qsTr("Les questions de vos projets et les cartes qui attendent votre décision. Page relue toutes "
                           + "les 15 secondes tant qu'elle est affichée.")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Questions.lecture
                erreur: Questions.erreur
            }
            BandeauMessage {
                Layout.fillWidth: true
                message: Questions.messageGeste
                erreur: Questions.erreurGeste
            }
            Text {
                visible: !Questions.lue && Questions.erreur.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            // --- Questions ouvertes -----------------------------------------------------------------
            Carte {
                objectName: "questions-ouvertes"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Questions ouvertes")
                Discret { visible: Questions.questions.count === 0; text: qsTr("Aucune question en attente.") }
                Repeater {
                    model: Questions.questions
                    delegate: ColumnLayout {
                        id: question
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        RowLayout {
                            Layout.fillWidth: true
                            BlocTexte { Layout.fillWidth: true; texte: question.item.texte }
                            StatusChip { statusKey: question.item.etatCle; label: question.item.etatLibelle }
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: question.item.projetTitre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Carte"); value: question.item.carte }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Posée"); value: question.item.poseeLe }
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: question.item.contexte.length > 0
                            libelle: qsTr("Contexte")
                            texte: question.item.contexte
                        }
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: question.item.motif.length > 0
                            libelle: qsTr("Motif")
                            texte: question.item.motif
                        }
                        Discret { visible: question.item.peutRepondre; text: qsTr("Votre réponse (4 000 caractères au plus)"); color: Colors.textSecondary }
                        ChampLong {
                            id: reponse
                            objectName: "questions-reponse-" + question.item.id
                            visible: question.item.peutRepondre
                            Accessible.name: qsTr("Votre réponse")
                        }
                        RowLayout {
                            spacing: Space.space4
                            AcpButton {
                                objectName: "questions-repondre-" + question.item.id
                                visible: question.item.peutRepondre
                                primary: true
                                label: qsTr("Répondre")
                                manualEnabled: reponse.text.trim().length > 0 && !Questions.gesteEnCours
                                onTriggered: Questions.repondre(question.item.id, reponse.text)
                            }
                            AcpButton {
                                visible: question.item.projet.length > 0
                                label: qsTr("Ouvrir le projet")
                                onTriggered: page.ouvrirProjet(question.item.projet)
                            }
                        }
                    }
                }
            }

            // --- Cartes en triage ---------------------------------------------------------------------
            Carte {
                objectName: "questions-triage"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Cartes en triage")
                Discret { visible: Questions.triage.count === 0; text: qsTr("Aucune carte en triage.") }
                Repeater {
                    model: Questions.triage
                    delegate: ColumnLayout {
                        id: triage
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        Text {
                            Layout.fillWidth: true
                            text: triage.item.titre
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: Colors.textPrimary
                            font.family: Type.tableCellEmphasis.family
                            font.pixelSize: Type.tableCellEmphasis.pixelSize
                            font.weight: Type.tableCellEmphasis.weight
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: triage.item.projetTitre }
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: triage.item.raison.length > 0
                            libelle: qsTr("Raison")
                            texte: triage.item.raison
                        }
                        Discret { visible: triage.item.aide.length > 0; text: triage.item.aide }
                        Discret { visible: triage.item.aideConclure.length > 0; text: triage.item.aideConclure }
                        Discret { visible: triage.item.gestesInconnus.length > 0; text: triage.item.gestesInconnus }
                        Discret { visible: triage.item.avecConsigne; text: qsTr("Consigne (facultative, 8 000 caractères au plus)"); color: Colors.textSecondary }
                        ChampLong {
                            id: consigne
                            visible: triage.item.avecConsigne
                            Accessible.name: qsTr("Consigne")
                        }
                        RowLayout {
                            spacing: Space.space4
                            AcpButton {
                                objectName: "questions-reprise-" + triage.item.carte
                                visible: triage.item.avecConsigne
                                primary: true
                                label: triage.item.libelleReprise
                                manualEnabled: !Questions.gesteEnCours
                                onTriggered: Questions.agirTriage(triage.item.tableau, triage.item.carte, "reprise", consigne.text)
                            }
                            AcpButton {
                                objectName: "questions-conclure-" + triage.item.carte
                                visible: triage.item.peutConclure
                                label: qsTr("Conclure le projet")
                                manualEnabled: !Questions.gesteEnCours
                                onTriggered: Questions.agirTriage(triage.item.tableau, triage.item.carte, "conclure", "")
                            }
                            AcpButton {
                                visible: triage.item.projet.length > 0
                                label: qsTr("Ouvrir le projet")
                                onTriggered: page.ouvrirProjet(triage.item.projet)
                            }
                        }
                    }
                }
            }

            // --- Cartes bloquées ou abandonnées ----------------------------------------------------------
            Carte {
                objectName: "questions-bloquees"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Cartes bloquées ou abandonnées")
                sousTitre: qsTr("Lecture seule : relancer une carte depuis la station arrivera à l'étape P7 ; en "
                                + "attendant, le kanban de Hermes le permet.")
                Discret { visible: Questions.bloquees.count === 0; text: qsTr("Aucune carte bloquée.") }
                Repeater {
                    model: Questions.bloquees
                    delegate: ColumnLayout {
                        id: bloquee
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: bloquee.item.titre
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                color: Colors.textPrimary
                                font.family: Type.tableCellEmphasis.family
                                font.pixelSize: Type.tableCellEmphasis.pixelSize
                                font.weight: Type.tableCellEmphasis.weight
                            }
                            StatusChip { statusKey: "blocked"; label: bloquee.item.etatLibelle }
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: bloquee.item.projetTitre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Assignée à"); value: bloquee.item.assigne; monospace: true }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Raison"); texte: bloquee.item.raison }
                    }
                }
            }

            // --- Revues des fichiers de pilotage (P6) ---------------------------------------------------
            Carte {
                objectName: "questions-revues"
                Layout.fillWidth: true
                visible: Questions.lue && Questions.revuesPresentes
                titre: qsTr("Revues des fichiers de pilotage")
                sousTitre: qsTr("Lecture seule dans la station : l'acceptation et le refus d'une revue se font dans le "
                                + "tableau de bord, tant que leur contrat n'est pas intégré à la station.")
                Discret { visible: Questions.revues.count === 0; text: qsTr("Aucune revue en attente.") }
                Repeater {
                    model: Questions.revues
                    delegate: ColumnLayout {
                        id: revue
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Carte"); value: revue.item.titre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: revue.item.projetTitre }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Fichiers de pilotage"); texte: revue.item.chemins; monospace: true }
                        BlocTexte { Layout.fillWidth: true; visible: revue.item.resume.length > 0; libelle: qsTr("Résumé"); texte: revue.item.resume }
                    }
                }
                AcpButton {
                    objectName: "questions-revues-navigateur"
                    label: qsTr("Traiter dans le navigateur")
                    onTriggered: Questions.traiterDansLeNavigateur()
                }
            }

            // --- Tableaux illisibles -----------------------------------------------------------------------
            Carte {
                Layout.fillWidth: true
                visible: Questions.tableauxIllisibles.length > 0
                titre: qsTr("Tableaux illisibles")
                sousTitre: qsTr("Le greffon n'a pas pu lire ces tableaux : leurs cartes ne figurent pas ci-dessus.")
                BlocTexte { Layout.fillWidth: true; texte: Questions.tableauxIllisibles.join("\n"); monospace: true }
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
