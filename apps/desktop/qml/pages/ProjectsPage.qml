// Page Projets (cahier P8 § 7.2) : liste, détail et nouveau projet.
//
// Tout ce qui est affiché vient de ProjetsViewModel, déjà libellé en français. Les gestes
// (lancer, mettre en pause, reprendre) rendent la réponse du serveur telle quelle. Aucun
// profil, dépôt, exécutant, modèle ou effort n'est proposé s'il ne vient pas du serveur.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Projets.pageVisible = true
    Component.onDestruction: Projets.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    component Alerte: Text {
        Layout.fillWidth: true
        visible: text.length > 0
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Status.statusDegradedForeground
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space8
        spacing: Space.space5

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space4
            Text {
                Layout.fillWidth: true
                text: qsTr("Projets")
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
            }
            AcpButton {
                objectName: "projets-vue-liste"
                label: qsTr("Vos projets")
                primary: Projets.vue === "liste"
                onTriggered: Projets.afficherListe()
            }
            AcpButton {
                objectName: "projets-vue-nouveau"
                label: qsTr("Nouveau projet")
                primary: Projets.vue === "nouveau"
                onTriggered: Projets.afficherNouveau()
            }
            AcpButton {
                objectName: "projets-actualiser"
                label: qsTr("Actualiser")
                onTriggered: Projets.actualiser()
            }
        }

        BandeauMessage {
            objectName: "projets-bandeau"
            Layout.fillWidth: true
            message: Projets.messageGeste
            alerte: Projets.alerteGeste
            erreur: Projets.erreurGeste
        }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: Projets.vue === "detail" ? vueDetail : Projets.vue === "nouveau" ? vueNouveau : vueListe
        }
    }

    // --- Liste ----------------------------------------------------------------------------------
    Component {
        id: vueListe
        ColumnLayout {
            spacing: Space.space4

            Rectangle {
                Layout.fillWidth: true
                visible: Projets.pause.etat === 1
                implicitHeight: textePause.implicitHeight + Space.space5 * 2
                radius: Radius.radiusSm
                color: Status.statusDegradedTint
                border.width: Space.layoutBorderWidth
                border.color: Status.statusDegradedBorder
                Text {
                    id: textePause
                    anchors.fill: parent
                    anchors.margins: Space.space5
                    text: qsTr("Hermes est en pause générale (%1, depuis %2) : aucune nouvelle carte ne part. "
                               + "La reprise se fait depuis l'accueil.").arg(Projets.pause.raison).arg(Projets.pause.depuis)
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Status.statusDegradedForeground
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                }
            }

            Discret {
                text: qsTr("Les projets que vous confiez à Hermes : il les planifie, les fait avancer carte par carte "
                           + "et vous pose ses questions. Page relue toutes les 15 secondes tant qu'elle est affichée.")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Projets.lectureListe
                erreur: Projets.erreurListe
            }

            Text {
                Layout.fillWidth: true
                visible: !Projets.listeLue && Projets.erreurListe.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            EmptyState {
                Layout.fillWidth: true
                Layout.preferredHeight: 220
                visible: Projets.listeLue && Projets.projets.count === 0
                title: qsTr("Aucun projet pour l'instant")
                body: qsTr("Lancez-en un avec « Nouveau projet », ou demandez-le à Hermes dans la discussion.")
                actionLabel: qsTr("Nouveau projet")
                onActionTriggered: Projets.afficherNouveau()
            }

            ListView {
                id: listeProjets
                objectName: "projets-liste"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: Projets.projets.count > 0
                clip: true
                spacing: Space.space4
                model: Projets.projets
                ScrollBar.vertical: ScrollBar {}
                delegate: Carte {
                    id: ligne
                    required property var item
                    width: listeProjets.width - Space.space4
                    titre: item.titre
                    cle: item.etatCle
                    libelleEtat: item.etatLibelle
                    Discret {
                        text: qsTr("Type : %1 · Dépôt : %2 · %3 · Créé le %4")
                            .arg(ligne.item.profil).arg(ligne.item.depot).arg(ligne.item.tour).arg(ligne.item.creeLe)
                    }
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Cartes faites : %1 · en cours : %2 · en attente du poste : %3 · bloquées : %4 · en triage : %5")
                            .arg(ligne.item.cartes).arg(ligne.item.enCours).arg(ligne.item.attentePoste)
                            .arg(ligne.item.bloquees).arg(ligne.item.triage)
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textPrimary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: ligne.item.questionsEnAttente
                        text: qsTr("Questions en attente : %1").arg(ligne.item.questions)
                        textFormat: Text.PlainText
                        color: Status.statusApprovalRequiredForeground
                        font.family: Type.tableCellEmphasis.family
                        font.pixelSize: Type.tableCellEmphasis.pixelSize
                        font.weight: Type.tableCellEmphasis.weight
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        libelle: qsTr("Dernière note")
                        texte: ligne.item.derniereNote + (ligne.item.noteTronquee ? qsTr(" […] (extrait ; le détail donne les résumés en entier)") : "")
                        vide: qsTr("Aucune carte finie pour l'instant.")
                    }
                    AcpButton {
                        objectName: "projets-ouvrir-" + ligne.item.id
                        label: qsTr("Ouvrir le projet")
                        onTriggered: Projets.ouvrirProjet(ligne.item.id)
                    }
                }
            }
        }
    }

    // --- Détail ---------------------------------------------------------------------------------
    Component {
        id: vueDetail
        ScrollView {
            id: defilement
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: defilement.availableWidth - Space.space4
                spacing: Space.space5

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Space.space4
                    AcpButton {
                        objectName: "projets-retour"
                        label: qsTr("Retour aux projets")
                        onTriggered: Projets.afficherListe()
                    }
                    Item { Layout.fillWidth: true }
                    AcpButton {
                        objectName: "projets-pause"
                        visible: Projets.detail.peutMettreEnPause
                        label: qsTr("Mettre en pause")
                        manualEnabled: !Projets.gesteEnCours
                        onTriggered: Projets.mettreEnPause()
                    }
                    AcpButton {
                        objectName: "projets-reprise"
                        visible: Projets.detail.peutReprendre
                        primary: true
                        label: qsTr("Reprendre")
                        manualEnabled: !Projets.gesteEnCours
                        onTriggered: Projets.reprendre()
                    }
                    AcpButton {
                        objectName: "projets-kanban"
                        label: qsTr("Ouvrir le kanban dans le navigateur")
                        onTriggered: Projets.ouvrirKanban()
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: !Projets.detailLu && Projets.erreurDetail.length === 0
                    text: qsTr("Chargement…")
                    textFormat: Text.PlainText
                    color: Colors.textMuted
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                }

                Carte {
                    objectName: "projets-detail"
                    Layout.fillWidth: true
                    titre: Projets.detail.titre
                    cle: Projets.detail.etatCle
                    libelleEtat: Projets.detail.etatLibelle
                    lecture: Projets.lectureDetail
                    erreurLecture: Projets.erreurDetail
                    BlocTexte { Layout.fillWidth: true; libelle: qsTr("Objectif"); texte: Projets.detail.objectif }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Type de projet"); value: Projets.detail.profil }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Dépôt"); value: Projets.detail.depot; monospace: true }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Qui répond"); value: Projets.detail.reponses }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Origine"); value: Projets.detail.origine }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Tour"); value: Projets.detail.tour }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Cartes créées"); value: Projets.detail.cartesCreees }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Cartes faites"); value: Projets.detail.cartesFaites }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Corrections par étape au plus"); value: Projets.detail.corrections }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Restants"); value: Projets.detail.restants }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Créé"); value: Projets.detail.creeLe }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Projets.detail.termineLe.length > 0
                        label: qsTr("Terminé")
                        value: Projets.detail.termineLe
                    }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Tableau kanban"); value: Projets.detail.tableau; monospace: true }
                    Discret { objectName: "projets-veille"; text: Projets.etatVeille }

                    // --- « Changer qui répond » (étape P7) : rien ne change à l'écran avant la réponse du greffon.
                    Item {
                        id: reglage
                        property bool ouvert: false
                        Layout.fillWidth: true
                        implicitHeight: colonneReglage.implicitHeight
                        visible: Projets.detail.peutChangerReponses === true
                        Connections {
                            target: Projets
                            function onReglageReponsesEnregistre() { reglage.ouvert = false; }
                            function onVueChange() { reglage.ouvert = false; }
                        }
                        ColumnLayout {
                            id: colonneReglage
                            width: parent.width
                            spacing: Space.space2
                            AcpButton {
                                objectName: "projets-changer-reponses"
                                visible: !reglage.ouvert
                                label: qsTr("Changer qui répond")
                                onTriggered: {
                                    choixReponses.currentIndex = Projets.detail.reponsesCode === "proprietaire" ? 1 : 0;
                                    reglage.ouvert = true;
                                }
                            }
                            Discret { visible: reglage.ouvert; text: qsTr("Qui répond aux questions suivantes"); color: Colors.textSecondary }
                            ComboBox {
                                id: choixReponses
                                objectName: "projets-choix-reponses"
                                visible: reglage.ouvert
                                Layout.preferredWidth: 280
                                model: [qsTr("Hermes d'abord"), qsTr("Moi")]
                                Accessible.name: qsTr("Qui répond aux questions suivantes")
                            }
                            Discret {
                                visible: reglage.ouvert
                                text: qsTr("Le changement vaut pour les questions suivantes ; les questions déjà ouvertes gardent "
                                           + "leur traitement, et vous pouvez toujours y répondre vous-même.")
                            }
                            RowLayout {
                                visible: reglage.ouvert
                                spacing: Space.space4
                                AcpButton {
                                    objectName: "projets-enregistrer-reponses"
                                    primary: true
                                    label: qsTr("Enregistrer")
                                    manualEnabled: !Projets.gesteEnCours
                                    onTriggered: Projets.changerReponses(choixReponses.currentIndex === 1 ? "proprietaire" : "hermes_d_abord")
                                }
                                AcpButton {
                                    objectName: "projets-annuler-reponses"
                                    label: qsTr("Annuler")
                                    onTriggered: reglage.ouvert = false
                                }
                            }
                        }
                    }

                    // --- « Clore le projet » (étape P7) : la confirmation dit exactement ce que fait la clôture.
                    Item {
                        id: cloture
                        property bool confirmation: false
                        Layout.fillWidth: true
                        implicitHeight: colonneCloture.implicitHeight
                        visible: Projets.detail.peutClore === true
                        Connections {
                            target: Projets
                            function onClotureFaite() { cloture.confirmation = false; }
                            function onVueChange() { cloture.confirmation = false; }
                        }
                        ColumnLayout {
                            id: colonneCloture
                            width: parent.width
                            spacing: Space.space2
                            AcpButton {
                                objectName: "projets-clore"
                                visible: !cloture.confirmation
                                label: qsTr("Clore le projet")
                                onTriggered: cloture.confirmation = true
                            }
                            Text {
                                objectName: "projets-clore-question"
                                Layout.fillWidth: true
                                visible: cloture.confirmation
                                text: qsTr("Clore ce projet ?")
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                color: Colors.textPrimary
                                font.family: Type.tableCellEmphasis.family
                                font.pixelSize: Type.tableCellEmphasis.pixelSize
                                font.weight: Type.tableCellEmphasis.weight
                            }
                            Discret { visible: cloture.confirmation; text: qsTr("• Les cartes ouvertes du projet sont archivées ; un travail en cours est arrêté.") }
                            Discret { visible: cloture.confirmation; text: qsTr("• Ses questions ouvertes sont annulées.") }
                            Discret { visible: cloture.confirmation; text: qsTr("• Le projet passe « Terminé » si la synthèse du tour en cours est faite, sinon « Abandonné ».") }
                            Discret { visible: cloture.confirmation; text: qsTr("• Aucune notification n'est envoyée ; les branches déjà rapportées restent sur l'exécutant jusqu'à leur purge (7 jours).") }
                            RowLayout {
                                visible: cloture.confirmation
                                spacing: Space.space4
                                AcpButton {
                                    objectName: "projets-confirmer-clore"
                                    label: qsTr("Confirmer la clôture")
                                    manualEnabled: !Projets.gesteEnCours
                                    onTriggered: Projets.clore()
                                }
                                AcpButton {
                                    objectName: "projets-annuler-clore"
                                    label: qsTr("Annuler")
                                    onTriggered: cloture.confirmation = false
                                }
                            }
                        }
                    }
                }

                Carte {
                    Layout.fillWidth: true
                    visible: Projets.detail.resultat.length > 0
                    titre: qsTr("Résultat du projet")
                    sousTitre: qsTr("Synthèse du dernier tour fait (tour %1), en entier.").arg(Projets.detail.resultatTour)
                    BlocTexte { Layout.fillWidth: true; texte: Projets.detail.resultat }
                    Discret { visible: Projets.detail.resultatTronque; text: qsTr("Texte borné à 100 000 caractères par le greffon.") }
                }

                Carte {
                    Layout.fillWidth: true
                    visible: Projets.detail.exploration.length > 0
                    titre: qsTr("Exploration du dépôt")
                    BlocTexte { Layout.fillWidth: true; texte: Projets.detail.exploration }
                }

                Carte {
                    Layout.fillWidth: true
                    titre: qsTr("Questions ouvertes du projet")
                    Discret { visible: Projets.questionsDuProjet.count === 0; text: qsTr("Aucune question en attente.") }
                    Repeater {
                        model: Projets.questionsDuProjet
                        delegate: ColumnLayout {
                            required property var item
                            Layout.fillWidth: true
                            spacing: Space.space1
                            StatusChip { statusKey: item.etatCle; label: item.etatLibelle }
                            BlocTexte { Layout.fillWidth: true; texte: item.texte }
                        }
                    }
                }

                Carte {
                    Layout.fillWidth: true
                    titre: qsTr("Cartes")
                    Discret { visible: Projets.cartes.count === 0; text: qsTr("Aucune carte pour l'instant.") }
                    Repeater {
                        model: Projets.cartes
                        delegate: ColumnLayout {
                            id: carteLigne
                            required property var item
                            Layout.fillWidth: true
                            spacing: Space.space2
                            Rectangle { Layout.fillWidth: true; height: Space.layoutBorderWidth; color: Colors.borderSubtle }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Space.space4
                                Text {
                                    Layout.fillWidth: true
                                    text: carteLigne.item.groupe + " — " + carteLigne.item.titre
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WordWrap
                                    color: Colors.textPrimary
                                    font.family: Type.tableCellEmphasis.family
                                    font.pixelSize: Type.tableCellEmphasis.pixelSize
                                    font.weight: Type.tableCellEmphasis.weight
                                }
                                StatusChip { statusKey: carteLigne.item.statutCle; label: carteLigne.item.statutLibelle }
                            }
                            Discret {
                                text: qsTr("Exécutant : %1 · Modèle demandé : %2 · Effort : %3 · Palier : %4 · Modèle servi : %5 · Tour %6")
                                    .arg(carteLigne.item.voie).arg(carteLigne.item.modele).arg(carteLigne.item.effort)
                                    .arg(carteLigne.item.palier).arg(carteLigne.item.modeleServi).arg(carteLigne.item.tour)
                            }
                            Discret { visible: carteLigne.item.mention.length > 0; text: qsTr("Mention : %1").arg(carteLigne.item.mention) }
                            BlocTexte {
                                Layout.fillWidth: true
                                visible: carteLigne.item.resume.length > 0
                                libelle: carteLigne.item.resumeTronque
                                    ? qsTr("Résumé (extrait : %1 caractères sur %2)").arg(carteLigne.item.resume.length).arg(carteLigne.item.resumeLongueur)
                                    : qsTr("Résumé")
                                texte: carteLigne.item.resume
                            }
                            AcpButton {
                                visible: carteLigne.item.resumeTronque && carteLigne.item.carte.length > 0
                                label: qsTr("Lire le résumé en entier")
                                onTriggered: Projets.lireCarteEnEntier(carteLigne.item.carte)
                            }
                        }
                    }
                }

                Carte {
                    Layout.fillWidth: true
                    visible: Projets.tours.count > 0
                    titre: qsTr("Tours et décisions")
                    Repeater {
                        model: Projets.tours
                        delegate: BlocTexte {
                            required property var item
                            Layout.fillWidth: true
                            libelle: item.tour
                            texte: item.resume + (item.decisions.length > 0 ? "\n" + qsTr("Décisions :") + "\n" + item.decisions : "")
                        }
                    }
                }

                Carte {
                    Layout.fillWidth: true
                    titre: qsTr("Journal")
                    Discret { visible: Projets.journal.count === 0; text: qsTr("Journal vide.") }
                    Repeater {
                        model: Projets.journal
                        delegate: Discret {
                            required property var item
                            color: Colors.textSecondary
                            text: [item.quand, item.acteur, item.action, item.cible, item.detail].filter(t => t.length > 0).join(" · ")
                        }
                    }
                }

                Item { Layout.preferredHeight: Space.space6 }
            }
        }
    }

    // --- Nouveau projet -------------------------------------------------------------------------
    Component {
        id: vueNouveau
        ScrollView {
            id: defilementFormulaire
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                id: formulaire
                objectName: "projets-formulaire"
                width: Math.min(defilementFormulaire.availableWidth - Space.space4, Type.measureProse + 160)
                spacing: Space.space4

                readonly property var f: Projets.formulaire
                property string reponses: "hermes_d_abord"
                readonly property bool complet: titreChamp.text.trim().length > 0 && objectifChamp.text.trim().length > 0
                    && !formulaire.f.modeleExige

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Décrivez le résultat attendu : Hermes le découpe en étapes vérifiables et le fait avancer "
                               + "seul. Il ne pousse, ne fusionne et ne publie jamais sans votre accord.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textSecondary
                    font.family: Type.prose.family
                    font.pixelSize: Type.prose.pixelSize
                }
                Text {
                    visible: !formulaire.f.pret
                    text: qsTr("Chargement…")
                    textFormat: Text.PlainText
                    color: Colors.textMuted
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                }
                Alerte { text: formulaire.f.erreurPoste }
                Alerte { text: formulaire.f.erreurCatalogue }

                Discret { text: qsTr("Titre"); color: Colors.textSecondary }
                AcpTextField {
                    id: titreChamp
                    objectName: "projets-champ-titre"
                    Layout.fillWidth: true
                    placeholder: qsTr("Titre (120 caractères au plus)")
                    accessibleName: qsTr("Titre")
                }

                Discret { text: qsTr("Objectif"); color: Colors.textSecondary }
                TextArea {
                    id: objectifChamp
                    objectName: "projets-champ-objectif"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    placeholderText: qsTr("Ce qui doit exister à la fin, les contraintes et ce qui compte pour vous.")
                    color: Colors.textPrimary
                    font.family: Type.prose.family
                    font.pixelSize: Type.prose.pixelSize
                    background: Rectangle {
                        color: Colors.surfacePanelRaised
                        radius: Radius.radiusSm
                        border.width: Space.layoutBorderWidth
                        border.color: objectifChamp.activeFocus ? Colors.borderFocus : Colors.borderInteractive
                    }
                    Accessible.name: qsTr("Objectif")
                }

                Discret { text: qsTr("Type de projet"); color: Colors.textSecondary }
                ComboBox {
                    id: profilChoix
                    objectName: "projets-champ-profil"
                    Layout.fillWidth: true
                    model: formulaire.f.profils
                    textRole: "libelle"
                    valueRole: "valeur"
                    Accessible.name: qsTr("Type de projet")
                    Component.onCompleted: currentIndex = Math.max(0, indexOfValue(formulaire.f.profilDefaut))
                    onModelChanged: currentIndex = Math.max(0, indexOfValue(formulaire.f.profilDefaut))
                }

                Discret { text: qsTr("Dépôt"); color: Colors.textSecondary }
                ComboBox {
                    id: depotChoix
                    objectName: "projets-champ-depot"
                    Layout.fillWidth: true
                    enabled: formulaire.f.depotsConnus
                    model: [qsTr("Sans dépôt")].concat(formulaire.f.depots)
                    currentIndex: formulaire.f.depot.length > 0 ? formulaire.f.depots.indexOf(formulaire.f.depot) + 1 : 0
                    Accessible.name: qsTr("Dépôt")
                    onActivated: function(index) { Projets.choisirDepot(index === 0 ? "" : formulaire.f.depots[index - 1]) }
                }
                Discret { visible: formulaire.f.aideDepot.length > 0; text: formulaire.f.aideDepot }

                Discret { text: qsTr("Qui répond aux questions"); color: Colors.textSecondary }
                Discret {
                    visible: formulaire.f.reponsesSansObjet
                    text: qsTr("Sans objet sans dépôt : aucune question ne naît d'un projet sans dépôt ; s'il manque une "
                               + "information, Hermes bloque une carte avec sa raison (page Questions, cartes bloquées).")
                }
                RadioButton {
                    visible: !formulaire.f.reponsesSansObjet
                    text: qsTr("Hermes d'abord : il répond s'il le peut, sinon il vous transmet la question.")
                    checked: formulaire.reponses === "hermes_d_abord"
                    onToggled: if (checked) formulaire.reponses = "hermes_d_abord"
                }
                RadioButton {
                    visible: !formulaire.f.reponsesSansObjet
                    text: qsTr("Moi : chaque question vous est transmise directement.")
                    checked: formulaire.reponses === "proprietaire"
                    onToggled: if (checked) formulaire.reponses = "proprietaire"
                }

                Alerte {
                    text: formulaire.f.releveFactice ? qsTr("Relevé factice : ces modèles viennent d'un relevé de test, pas de votre poste.") : ""
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: formulaire.f.avecExploration
                    spacing: Space.space3
                    Text {
                        text: qsTr("Exploration du dépôt")
                        textFormat: Text.PlainText
                        color: Colors.textPrimary
                        font.family: Type.panelTitle.family
                        font.pixelSize: Type.panelTitle.pixelSize
                        font.weight: Type.panelTitle.weight
                    }
                    Discret { text: qsTr("Le poste lit le dépôt, sans rien y modifier, avant la planification.") }
                    Discret { text: qsTr("Exécutant"); color: Colors.textSecondary }
                    ComboBox {
                        id: voieChoix
                        objectName: "projets-champ-voie"
                        Layout.fillWidth: true
                        model: formulaire.f.voies
                        textRole: "libelle"
                        valueRole: "valeur"
                        currentIndex: Math.max(0, indexOfValue(formulaire.f.voie))
                        Accessible.name: qsTr("Exécutant")
                        onActivated: Projets.choisirVoie(currentValue)
                    }
                    Discret { text: qsTr("Modèle"); color: Colors.textSecondary }
                    ComboBox {
                        id: modeleChoix
                        objectName: "projets-champ-modele"
                        Layout.fillWidth: true
                        model: [formulaire.f.libelleModeleVide].concat(formulaire.f.modeles)
                        currentIndex: formulaire.f.modele.length > 0 ? formulaire.f.modeles.indexOf(formulaire.f.modele) + 1 : 0
                        Accessible.name: qsTr("Modèle")
                        onActivated: function(index) { Projets.choisirModele(index === 0 ? "" : formulaire.f.modeles[index - 1]) }
                    }
                    Discret { text: qsTr("Effort"); color: Colors.textSecondary }
                    ComboBox {
                        id: effortChoix
                        objectName: "projets-champ-effort"
                        Layout.fillWidth: true
                        model: [qsTr("Par défaut")].concat(formulaire.f.efforts)
                        Accessible.name: qsTr("Effort")
                        onModelChanged: currentIndex = 0
                    }
                    Discret { text: qsTr("Relevé du %1").arg(formulaire.f.releveDu) }
                    Alerte { text: formulaire.f.relevePerime ? qsTr("Relevé périmé : le poste doit publier un nouvel inventaire.") : "" }
                    Alerte {
                        text: formulaire.f.modeleExige
                            ? qsTr("Choisissez un modèle pour l'exploration : le relevé de cet exécutant n'en désigne aucun par défaut.")
                            : ""
                    }
                }

                // Une sélection refaite par le serveur (dépôt disparu, modèle absent du relevé) est
                // reportée dans les listes : elles montrent toujours ce qui sera envoyé.
                Connections {
                    target: Projets
                    function onFormulaireChange() {
                        depotChoix.currentIndex = formulaire.f.depot.length > 0 ? formulaire.f.depots.indexOf(formulaire.f.depot) + 1 : 0;
                        voieChoix.currentIndex = Math.max(0, voieChoix.indexOfValue(formulaire.f.voie));
                        modeleChoix.currentIndex = formulaire.f.modele.length > 0 ? formulaire.f.modeles.indexOf(formulaire.f.modele) + 1 : 0;
                    }
                }

                AcpButton {
                    objectName: "projets-lancer"
                    primary: true
                    label: Projets.gesteEnCours ? qsTr("Envoi…") : qsTr("Lancer le projet")
                    manualEnabled: formulaire.f.pret && formulaire.complet && !Projets.gesteEnCours
                    onTriggered: Projets.lancer(titreChamp.text, objectifChamp.text, profilChoix.currentValue,
                                                formulaire.reponses,
                                                effortChoix.currentIndex > 0 ? formulaire.f.efforts[effortChoix.currentIndex - 1] : "")
                }
                Item { Layout.preferredHeight: Space.space6 }
            }
        }
    }

    // --- Résumé d'une carte en entier -------------------------------------------------------------
    Connections {
        target: Projets
        function onCarteLueChange() {
            if ((Projets.carteLue.carte || "").length > 0)
                carteEntiere.open();
            else
                carteEntiere.close();
        }
    }

    Dialog {
        id: carteEntiere
        objectName: "projets-carte-entiere"
        anchors.centerIn: parent
        modal: true
        width: Math.min(page.width - Space.space8 * 2, 760)
        height: Math.min(page.height - Space.space8 * 2, 620)
        title: (Projets.carteLue.titre || "").length > 0 ? Projets.carteLue.titre : qsTr("Résumé de la carte")
        onClosed: Projets.fermerCarteLue()
        contentItem: ScrollView {
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: Space.space3
                Discret { visible: Projets.carteLue.chargement === true; text: qsTr("Chargement…") }
                Alerte { text: Projets.carteLue.erreur || "" }
                Discret {
                    visible: (Projets.carteLue.statut || "").length > 0
                    text: qsTr("Statut : %1 · %2 caractères").arg(Projets.carteLue.statut || "").arg(Projets.carteLue.longueur || "")
                }
                BlocTexte {
                    Layout.fillWidth: true
                    visible: Projets.carteLue.chargement === false && (Projets.carteLue.erreur || "").length === 0
                    texte: Projets.carteLue.resume || ""
                    vide: qsTr("Aucun résumé pour cette carte.")
                }
                Discret { visible: (Projets.carteLue.borne || "").length > 0; text: Projets.carteLue.borne || "" }
            }
        }
        footer: DialogButtonBox {
            Button {
                text: qsTr("Fermer")
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
        }
    }
}
