// Page Questions (cahier P8 § 7.3 ; file à cinq sections de l'étape P7) : les mêmes sections, dans
// le même ordre et avec les mêmes gestes que la page Questions du navigateur — à traiter par vous,
// questions, décisions, revues, cartes arrêtées, discussions en attente. Les gestes viennent de ce
// que le greffon offre pour chaque entrée ; le résultat de chaque geste est celui que le serveur a
// rendu.

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

    // Champ dont le texte est un brouillon gardé par la station (QuestionsViewModel) : il survit
    // aux relectures de la liste, à un envoi refusé et à un changement de page, et ne se vide
    // qu'après la réussite du geste.
    component ChampLong: TextArea {
        id: champ
        property string cleBrouillon: ""
        Component.onCompleted: text = Questions.brouillon(champ.cleBrouillon)
        onTextChanged: Questions.setBrouillon(champ.cleBrouillon, text)
        Connections {
            target: Questions
            function onBrouillonEfface(cle) {
                if (cle === champ.cleBrouillon) {
                    champ.text = "";
                }
            }
        }
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

    component TitreEntree: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textPrimary
        font.family: Type.tableCellEmphasis.family
        font.pixelSize: Type.tableCellEmphasis.pixelSize
        font.weight: Type.tableCellEmphasis.weight
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
                text: qsTr("Ce qui attend votre décision dans vos projets : la même file que la page Questions du "
                           + "navigateur. Page relue toutes les 15 secondes tant qu'elle est affichée.")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Questions.lecture
                erreur: Questions.erreur
            }
            BandeauMessage {
                objectName: "questions-bandeau"
                Layout.fillWidth: true
                message: Questions.messageGeste
                alerte: Questions.alerteGeste
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

            // --- À traiter par vous -------------------------------------------------------------------
            Carte {
                objectName: "questions-resume"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("À traiter")
                KeyValueRow {
                    objectName: "questions-a-traiter"
                    Layout.fillWidth: true
                    label: qsTr("À traiter par vous")
                    value: Questions.resume.total + (Questions.resume.mention.length > 0 ? " " + Questions.resume.mention : "")
                    known: Questions.resume.connu
                }
                KeyValueRow { Layout.fillWidth: true; label: qsTr("Chez Hermes"); value: Questions.resume.chezHermes }
            }

            // --- 1. Questions ------------------------------------------------------------------------------
            Carte {
                objectName: "questions-ouvertes"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Questions")
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
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Qui répond"); value: question.item.quiRepond }
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
                        Discret { visible: question.item.chezHermesAide.length > 0; text: question.item.chezHermesAide }
                        Discret { visible: question.item.peutRepondre; text: qsTr("Votre réponse (4 000 caractères au plus)"); color: Colors.textSecondary }
                        ChampLong {
                            id: reponse
                            objectName: "questions-reponse-" + question.item.id
                            cleBrouillon: "q:" + question.item.id
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

            // --- 2. Décisions (cartes en triage) -------------------------------------------------------
            Carte {
                objectName: "questions-triage"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Décisions")
                Discret { visible: Questions.triage.count === 0; text: qsTr("Aucune carte en triage.") }
                Repeater {
                    model: Questions.triage
                    delegate: ColumnLayout {
                        id: triage
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        TitreEntree { text: triage.item.titre }
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
                            objectName: "questions-consigne-" + triage.item.carte
                            cleBrouillon: "t:" + triage.item.tableau + "/" + triage.item.carte
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

            // --- 3. Revues des fichiers de pilotage (P6) -------------------------------------------------
            Carte {
                objectName: "questions-revues"
                Layout.fillWidth: true
                visible: Questions.lue && Questions.revuesPresentes
                titre: qsTr("Revues")
                sousTitre: qsTr("Une carte de l'exécutant a modifié des fichiers qui pilotent les agents (CLAUDE.md, "
                                + "AGENTS.md, .github…). Acceptez-la, ou refusez-la avec un motif : elle revient alors à "
                                + "l'exécutant, qui retire la modification.")
                Discret { visible: Questions.revues.count === 0; text: qsTr("Aucune carte en revue.") }
                Repeater {
                    model: Questions.revues
                    delegate: ColumnLayout {
                        id: revue
                        required property var item
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        TitreEntree { text: revue.item.titre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: revue.item.projetTitre }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Fichiers de pilotage touchés"); texte: revue.item.chemins; monospace: true }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Modification"); value: revue.item.modification }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Branche"); value: revue.item.branche; monospace: true }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Tête"); value: revue.item.tete; monospace: true }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Résumé"); texte: revue.item.resume }
                        Discret { visible: revue.item.diff.length > 0; text: revue.item.diff }
                        Discret { visible: revue.item.adressable; text: qsTr("Motif du refus (1 000 caractères au plus)"); color: Colors.textSecondary }
                        ChampLong {
                            id: motif
                            objectName: "questions-motif-" + revue.item.carte
                            cleBrouillon: "m:" + revue.item.tableau + "/" + revue.item.carte
                            visible: revue.item.adressable
                            Layout.preferredHeight: 56
                            Accessible.name: qsTr("Motif du refus")
                        }
                        RowLayout {
                            spacing: Space.space4
                            AcpButton {
                                objectName: "questions-accepter-" + revue.item.carte
                                visible: revue.item.adressable
                                primary: true
                                label: qsTr("Accepter")
                                manualEnabled: !Questions.gesteEnCours
                                onTriggered: Questions.accepterRevue(revue.item.tableau, revue.item.carte)
                            }
                            AcpButton {
                                objectName: "questions-refuser-" + revue.item.carte
                                visible: revue.item.adressable
                                label: qsTr("Refuser")
                                manualEnabled: motif.text.trim().length > 0 && !Questions.gesteEnCours
                                onTriggered: Questions.refuserRevue(revue.item.tableau, revue.item.carte, motif.text)
                            }
                            AcpButton {
                                visible: revue.item.projet.length > 0
                                label: qsTr("Ouvrir le projet")
                                onTriggered: page.ouvrirProjet(revue.item.projet)
                            }
                        }
                    }
                }
            }

            // --- 4. Cartes arrêtées (bloquées ou abandonnées) ---------------------------------------------
            Carte {
                objectName: "questions-bloquees"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Cartes arrêtées")
                sousTitre: qsTr("« Relancer » remet la carte en route, avec votre consigne si vous en donnez une. Une "
                                + "carte qui rebloque pour la même raison revient en décision.")
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
                            TitreEntree { text: bloquee.item.titre }
                            StatusChip { statusKey: "blocked"; label: bloquee.item.etatLibelle }
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Projet"); value: bloquee.item.projetTitre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Assignée à"); value: bloquee.item.assigne; monospace: true }
                        BlocTexte { Layout.fillWidth: true; libelle: qsTr("Raison"); texte: bloquee.item.raison }
                        Text {
                            Layout.fillWidth: true
                            visible: bloquee.item.aide.length > 0
                            text: bloquee.item.aide
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: bloquee.item.aideAlerte ? Status.statusDegradedForeground : Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                        Discret {
                            objectName: "questions-refus-relance-" + bloquee.item.carte
                            visible: !bloquee.item.peutRelancer
                            text: qsTr("Relance impossible : %1").arg(bloquee.item.refusRelance)
                        }
                        Discret { visible: bloquee.item.avecConsigne; text: qsTr("Consigne (facultative, 4 000 caractères au plus)"); color: Colors.textSecondary }
                        ChampLong {
                            id: consigneRelance
                            objectName: "questions-consigne-relance-" + bloquee.item.carte
                            cleBrouillon: "r:" + bloquee.item.tableau + "/" + bloquee.item.carte
                            visible: bloquee.item.avecConsigne
                            Accessible.name: qsTr("Consigne de relance")
                        }
                        RowLayout {
                            spacing: Space.space4
                            AcpButton {
                                objectName: "questions-relancer-" + bloquee.item.carte
                                visible: bloquee.item.peutRelancer
                                primary: true
                                label: qsTr("Relancer")
                                manualEnabled: !Questions.gesteEnCours
                                onTriggered: Questions.relancer(bloquee.item.tableau, bloquee.item.carte,
                                                                bloquee.item.avecConsigne ? consigneRelance.text : "")
                            }
                            AcpButton {
                                visible: bloquee.item.projet.length > 0
                                label: qsTr("Ouvrir le projet")
                                onTriggered: page.ouvrirProjet(bloquee.item.projet)
                            }
                        }
                    }
                }
            }

            // --- 5. Discussions en attente (lecture seule) --------------------------------------------------
            Carte {
                objectName: "questions-discussions"
                Layout.fillWidth: true
                visible: Questions.lue
                titre: qsTr("Discussions en attente")
                sousTitre: qsTr("Discussions du tableau de bord dont une demande attend votre réponse, en lecture seule.")
                Discret {
                    objectName: "questions-discussions-etat"
                    visible: text.length > 0
                    text: Questions.discussions.etat
                    color: Colors.textSecondary
                }
                // Étape P8b : lues par la passerelle (session.active_list), comme la page web ; « Ouvrir la
                // discussion » reprend la session dans la page Discussion, qui y rejoue la demande ouverte.
                Repeater {
                    model: Questions.discussions.sessions || []
                    delegate: ColumnLayout {
                        id: discussionAttente
                        required property var modelData
                        objectName: "questions-discussion-" + modelData.cle
                        Layout.fillWidth: true
                        spacing: Space.space2
                        Separateur {}
                        TitreEntree { text: discussionAttente.modelData.titre }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("État"); value: discussionAttente.modelData.etat }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Dernière activité"); value: discussionAttente.modelData.activite }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Aperçu"); value: discussionAttente.modelData.apercu }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Session"); value: discussionAttente.modelData.cle }
                        AcpButton {
                            objectName: "questions-ouvrir-discussion-" + discussionAttente.modelData.cle
                            primary: true
                            label: qsTr("Ouvrir la discussion")
                            onTriggered: {
                                Discussion.ouvrir(discussionAttente.modelData.cle);
                                Navigation.setCurrentRoute("chat");
                            }
                        }
                    }
                }
                Discret { visible: Questions.discussions.limite.length > 0; text: Questions.discussions.limite }
            }

            // --- Demandes de vos discussions (approval, clarify) ---------------------------------------
            Carte {
                objectName: "questions-demandes"
                Layout.fillWidth: true
                titre: qsTr("Demandes de vos discussions")
                sousTitre: qsTr("Autorisations et précisions demandées par Hermes dans les discussions ouvertes sur ce "
                                + "poste. Non durables : elles disparaissent si Hermes est redéployé.")
                BandeauMessage {
                    Layout.fillWidth: true
                    message: Demandes.message
                    erreur: Demandes.erreur
                }
                Discret { visible: Demandes.nombre === 0; text: qsTr("Aucune demande en attente.") }
                Repeater {
                    model: Demandes.demandes
                    delegate: CarteDemande {
                        required property var item
                        Layout.fillWidth: true
                        demande: item
                    }
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
