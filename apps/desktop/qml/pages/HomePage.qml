// Accueil de la station (cahier P8 § 7.1 ; Accueil agrégé de l'étape P7, cahier P7 § 8).
//
// Les cartes de l'Accueil du navigateur, dans le même ordre, lues de la même route agrégée
// (`GET /v1/accueil`) : à traiter par vous, projets en cours, exécutant, quotas, notifications,
// pause générale ; puis les discussions récentes et Hermes. Chaque carte dit quand elle a été lue
// et, si la dernière lecture a échoué, l'erreur à côté de la valeur gardée. Un bloc illisible le
// dit avec sa raison ; une valeur absente vaut « Inconnu » ; aucune n'est inventée.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Accueil.pageVisible = true
    Component.onDestruction: Accueil.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    component Illisible: Text {
        property string raison: ""
        Layout.fillWidth: true
        text: qsTr("Bloc illisible : %1").arg(raison)
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Status.statusDegradedForeground
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth)
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space6

            Item { Layout.preferredHeight: Space.space4 }

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space5
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Accueil")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "accueil-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Accueil.actualiser()
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Ce qui attend votre décision, vos projets, l'exécutant et Hermes : le même Accueil que dans "
                           + "le navigateur.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textSecondary
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            // Cadence RÉELLE (temps réel ou sondage), jamais écrite en dur (relecture de P8b, constat desktop-4).
            Discret {
                objectName: "accueil-cadence"
                Layout.fillWidth: true
                text: Accueil.cadence
            }

            EtatLecture {
                Layout.fillWidth: true
                lecture: Accueil.lectureAccueil
                erreur: Accueil.erreurAccueil
            }

            BandeauMessage {
                objectName: "accueil-bandeau"
                Layout.fillWidth: true
                message: Accueil.messageGeste
                alerte: Accueil.alerteGeste
                erreur: Accueil.erreurGeste
            }

            GridLayout {
                Layout.fillWidth: true
                columns: width > 820 ? 2 : 1
                columnSpacing: Space.space6
                rowSpacing: Space.space6

                // --- 1. À traiter par vous ------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-a-traiter"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("À traiter par vous")
                    cle: !Accueil.carteATraiter.lisible ? "unknown" : Accueil.carteATraiter.attente ? "approvalRequired" : "pending"
                    libelleEtat: Accueil.carteATraiter.total
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: !Accueil.carteATraiter.lisible; raison: Accueil.carteATraiter.raison || "" }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: Accueil.carteATraiter.lisible === true
                        spacing: Space.space2
                        KeyValueRow {
                            objectName: "accueil-a-traiter-total"
                            Layout.fillWidth: true
                            label: qsTr("Total")
                            value: (Accueil.carteATraiter.total || "") + " " + (Accueil.carteATraiter.mention || "")
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Questions"); value: Accueil.carteATraiter.questions || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Décisions"); value: Accueil.carteATraiter.decisions || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Revues"); value: Accueil.carteATraiter.revues || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Cartes arrêtées"); value: Accueil.carteATraiter.arretees || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Discussions en attente"); value: Accueil.carteATraiter.discussions || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Chez Hermes"); value: Accueil.carteATraiter.chezHermes || "" }
                        Repeater {
                            model: Accueil.carteATraiter.premieres || []
                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: modelData.genre + " " + modelData.titre + " · " + modelData.projet
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                color: Colors.textPrimary
                                font.family: Type.tableCell.family
                                font.pixelSize: Type.tableCell.pixelSize
                            }
                        }
                        // Seulement si les discussions en attente ont pu être lues : jamais zéro par défaut.
                        Text {
                            objectName: "accueil-rien-a-traiter"
                            Layout.fillWidth: true
                            visible: Accueil.carteATraiter.rien === true
                            text: qsTr("Rien n'attend votre décision.")
                            textFormat: Text.PlainText
                            color: Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                    }
                    AcpButton {
                        label: qsTr("Ouvrir la file Questions")
                        commandId: "navigation.questions"
                    }
                }

                // --- 2. Projets en cours ---------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-projets"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Projets en cours")
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: !Accueil.carteProjets.lisible; raison: Accueil.carteProjets.raison || "" }
                    KeyValueRow { Layout.fillWidth: true; visible: Accueil.carteProjets.lisible === true; label: qsTr("En cours"); value: Accueil.carteProjets.enCours || "" }
                    KeyValueRow { Layout.fillWidth: true; visible: Accueil.carteProjets.lisible === true; label: qsTr("En pause"); value: Accueil.carteProjets.enPause || "" }
                    KeyValueRow { Layout.fillWidth: true; visible: Accueil.carteProjets.lisible === true; label: qsTr("Terminés ces 7 derniers jours"); value: Accueil.carteProjets.termines7j || "" }
                    Discret { visible: Accueil.carteProjets.aucunOuvert === true; text: qsTr("Aucun projet ouvert.") }
                    Repeater {
                        model: Accueil.projetsEnCours
                        delegate: ColumnLayout {
                            id: projet
                            required property var item
                            Layout.fillWidth: true
                            spacing: Space.space1
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: projet.item.titre
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WordWrap
                                    color: Colors.textPrimary
                                    font.family: Type.tableCellEmphasis.family
                                    font.pixelSize: Type.tableCellEmphasis.pixelSize
                                    font.weight: Type.tableCellEmphasis.weight
                                }
                                StatusChip { statusKey: projet.item.etatCle; label: projet.item.etatLibelle }
                                AcpButton {
                                    label: qsTr("Ouvrir")
                                    onTriggered: {
                                        Projets.ouvrirProjet(projet.item.id);
                                        Navigation.setCurrentRoute("projects");
                                    }
                                }
                            }
                            Discret { text: projet.item.avancement }
                            Discret { visible: projet.item.note.length > 0; text: projet.item.note }
                        }
                    }
                    AcpButton {
                        label: qsTr("Ouvrir les projets")
                        commandId: "navigation.projects"
                    }
                }

                // --- 3. Exécutant ------------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-executant"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Exécutant")
                    cle: Accueil.carteExecutant.cle || "unknown"
                    libelleEtat: Accueil.carteExecutant.etat || ""
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: !Accueil.carteExecutant.lisible; raison: Accueil.carteExecutant.raison || "" }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: Accueil.carteExecutant.lisible === true
                        spacing: Space.space2
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Machine"); value: Accueil.carteExecutant.machine || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Plateforme"); value: Accueil.carteExecutant.plateforme || ""; monospace: true }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Vu pour la dernière fois"); value: Accueil.carteExecutant.derniereVue || "" }
                        KeyValueRow {
                            Layout.fillWidth: true
                            visible: (Accueil.carteExecutant.horsLigneDepuis || "").length > 0
                            label: qsTr("Hors ligne depuis")
                            value: Accueil.carteExecutant.horsLigneDepuis || ""
                        }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Carte en cours"); value: Accueil.carteExecutant.carteEnCours || "" }
                        KeyValueRow { Layout.fillWidth: true; label: qsTr("Cartes en attente"); value: Accueil.carteExecutant.cartesEnAttente || "" }
                        // Rien quand aucune voie n'est servie fermée (exécutant inconnu compris), comme la page web.
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: (Accueil.carteExecutant.voiesFermees || "").length > 0
                            libelle: qsTr("Voies fermées")
                            texte: Accueil.carteExecutant.voiesFermees || ""
                        }
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: (Accueil.carteExecutant.message || "").length > 0
                            texte: Accueil.carteExecutant.message || ""
                        }
                    }
                    AcpButton {
                        label: qsTr("Ouvrir la page Poste")
                        commandId: "navigation.station"
                    }
                }

                // --- 4. Quotas -----------------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-quotas"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Quotas")
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: !Accueil.carteQuotas.lisible; raison: Accueil.carteQuotas.raison || "" }
                    Repeater {
                        model: Accueil.carteQuotas.voies || []
                        delegate: ColumnLayout {
                            id: voieQuota
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: Space.space1
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: voieQuota.modelData.nom
                                    textFormat: Text.PlainText
                                    color: Colors.textPrimary
                                    font.family: Type.tableCellEmphasis.family
                                    font.pixelSize: Type.tableCellEmphasis.pixelSize
                                    font.weight: Type.tableCellEmphasis.weight
                                }
                                StatusChip { statusKey: voieQuota.modelData.cle; label: voieQuota.modelData.etat }
                            }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Utilisé"); value: voieQuota.modelData.utilise }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Remise à zéro"); value: voieQuota.modelData.remise }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Source"); value: voieQuota.modelData.source }
                            KeyValueRow { Layout.fillWidth: true; label: qsTr("Relevé le"); value: voieQuota.modelData.releveLe }
                        }
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Accueil.carteQuotas.lisible === true
                        label: qsTr("Hermes")
                        value: Accueil.carteQuotas.hermes || ""
                    }
                    AcpButton {
                        label: qsTr("Ouvrir les quotas")
                        commandId: "navigation.quotas"
                    }
                }

                // --- 5. Notifications ----------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-notifications"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Notifications")
                    cle: Accueil.carteNotifications.cle || "unknown"
                    libelleEtat: Accueil.carteNotifications.etat || ""
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: !Accueil.carteNotifications.lisible; raison: Accueil.carteNotifications.raison || "" }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Accueil.carteNotifications.lisible === true
                        label: qsTr("Canal")
                        value: Accueil.carteNotifications.canal || ""
                    }
                    Discret {
                        objectName: "accueil-notifications-note"
                        visible: (Accueil.carteNotifications.note || "").length > 0
                        text: Accueil.carteNotifications.note || ""
                    }
                    AcpButton {
                        objectName: "accueil-notification-test"
                        label: qsTr("Envoyer une notification de test")
                        manualEnabled: Accueil.carteNotifications.configure === true && !Accueil.gesteEnCours
                        onTriggered: Accueil.envoyerNotificationDeTest()
                    }
                }

                // --- 5 bis. Bilan quotidien (tâche cron NATIVE de Hermes, comme CarteBilan.tsx) ---------
                Carte {
                    objectName: "accueil-carte-bilan"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Bilan quotidien")
                    cle: Accueil.carteBilan.cle || "unknown"
                    libelleEtat: Accueil.carteBilan.lu === true ? Accueil.carteBilan.etat : ""
                    lecture: Accueil.lectureBilan
                    erreurLecture: Accueil.erreurBilan
                    Text {
                        objectName: "accueil-bilan-illisible"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: Accueil.carteBilan.illisible || ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Status.statusDegradedForeground
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Discret {
                        visible: (Accueil.carteBilan.explication || "").length > 0
                        text: Accueil.carteBilan.explication || ""
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: (Accueil.carteBilan.prochaine || "").length > 0
                        label: qsTr("Prochaine exécution")
                        value: Accueil.carteBilan.prochaine || ""
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: (Accueil.carteBilan.derniere || "").length > 0
                        label: qsTr("Dernière exécution")
                        value: Accueil.carteBilan.derniere || ""
                    }
                    Text {
                        objectName: "accueil-bilan-alerte"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: Accueil.carteBilan.alerte || ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Status.statusDegradedForeground
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                        Accessible.role: Accessible.AlertMessage
                        Accessible.name: text
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: (Accueil.carteBilan.statut || "").length > 0
                        label: qsTr("Issue de la dernière exécution (Hermes)")
                        value: Accueil.carteBilan.statut || ""
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: (Accueil.carteBilan.message || "").length > 0
                        label: qsTr("Message de Hermes")
                        value: Accueil.carteBilan.message || ""
                    }
                    Discret { visible: (Accueil.carteBilan.plusieurs || "").length > 0; text: Accueil.carteBilan.plusieurs || "" }
                    Discret {
                        objectName: "accueil-bilan-sans-canal"
                        visible: (Accueil.carteBilan.sansCanal || "").length > 0
                        text: Accueil.carteBilan.sansCanal || ""
                    }
                    RowLayout {
                        spacing: Space.space4
                        AcpButton {
                            objectName: "accueil-bilan-creer"
                            visible: Accueil.carteBilan.peutCreer === true
                            primary: true
                            label: qsTr("Créer le bilan quotidien (8 h)")
                            manualEnabled: !Accueil.gesteEnCours
                            onTriggered: Accueil.creerBilanQuotidien()
                        }
                        AcpButton {
                            objectName: "accueil-bilan-cron"
                            label: qsTr("Pause et suppression : page Cron")
                            onTriggered: Accueil.ouvrirCron()
                        }
                    }
                }

                // --- 6. Pause générale ---------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-pause"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    visible: Accueil.lue
                    titre: qsTr("Pause générale")
                    cle: Accueil.cartePause.etat === 1 ? "degraded" : Accueil.cartePause.etat === 0 ? "succeeded" : "unknown"
                    libelleEtat: Accueil.cartePause.libelle
                    lecture: Accueil.lectureAccueil
                    erreurLecture: Accueil.erreurAccueil
                    Illisible { visible: (Accueil.cartePause.raisonIllisible || "").length > 0; raison: Accueil.cartePause.raisonIllisible || "" }
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Arrête le travail autonome de Hermes : aucune nouvelle carte ne part, les cartes en "
                                   + "cours finissent. La discussion reste ouverte ; lancer un projet y est refusé.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textSecondary
                        font.family: Type.metadata.family
                        font.pixelSize: Type.metadata.pixelSize
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Accueil.cartePause.etat === 1
                        label: qsTr("Raison")
                        value: Accueil.cartePause.raison
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Accueil.cartePause.etat === 1
                        label: qsTr("Depuis")
                        value: Accueil.cartePause.depuis
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: Accueil.cartePause.crochets
                        texte: qsTr("Pause engagée par la veille des crochets shell : retirez la clé hooks du "
                                    + "config.yaml (et tout shell-hooks-allowlist.json) du volume de Hermes ; la "
                                    + "reprise est refusée tant qu'ils existent.")
                    }
                    RowLayout {
                        spacing: Space.space4
                        AcpButton {
                            objectName: "accueil-pause-engager"
                            visible: Accueil.cartePause.pausePossible
                            label: qsTr("Mettre Hermes en pause générale")
                            manualEnabled: !Accueil.gesteEnCours
                            onTriggered: confirmationPause.open()
                        }
                        AcpButton {
                            objectName: "accueil-pause-reprendre"
                            visible: Accueil.cartePause.reprisePossible
                            primary: true
                            label: qsTr("Reprendre")
                            manualEnabled: !Accueil.gesteEnCours
                            onTriggered: Accueil.basculerPause(false, "")
                        }
                    }
                }

                // --- 7. Discussions récentes -----------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-sessions"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Discussions récentes")
                    lecture: Accueil.lectureSessions
                    erreurLecture: Accueil.erreurSessions
                    Text {
                        Layout.fillWidth: true
                        visible: Accueil.sessionsLues && Accueil.sessions.count === 0
                        text: qsTr("Aucune session pour l'instant.")
                        textFormat: Text.PlainText
                        color: Colors.textSecondary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Repeater {
                        model: Accueil.sessions
                        delegate: RowLayout {
                            id: ligneSession
                            required property var item
                            Layout.fillWidth: true
                            KeyValueRow {
                                Layout.fillWidth: true
                                label: ligneSession.item.titre
                                value: qsTr("%1 · %2 messages · %3").arg(ligneSession.item.actifA).arg(ligneSession.item.messages)
                                    .arg(ligneSession.item.source)
                            }
                            AcpButton {
                                label: qsTr("Ouvrir")
                                onTriggered: {
                                    Discussion.ouvrir(ligneSession.item.id);
                                    Navigation.setCurrentRoute("chat");
                                }
                            }
                        }
                    }
                }

                // --- 8. Hermes ---------------------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-hermes"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Hermes")
                    lecture: Compatibility.lecture
                    erreurLecture: Compatibility.erreurLecture
                    cle: Compatibility.etat === CompatibilityStatus.Compatible ? "succeeded"
                        : Compatibility.etat === CompatibilityStatus.Avertissement ? "degraded"
                        : Compatibility.etat === CompatibilityStatus.Incompatible
                          || Compatibility.etat === CompatibilityStatus.GreffonAbsent ? "failed" : "unknown"
                    libelleEtat: Compatibility.libelle
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Version en service")
                        value: Compatibility.versionHermes
                        known: Compatibility.versionHermes !== qsTr("Inconnu")
                        monospace: true
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Version testée par la station")
                        value: Compatibility.versionTestee
                        monospace: true
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Alertes du greffon")
                        value: Compatibility.etat === CompatibilityStatus.NonVerifiee ? qsTr("Inconnu")
                            : Compatibility.alertes.length === 0 ? qsTr("Aucune") : String(Compatibility.alertes.length)
                        known: Compatibility.etat !== CompatibilityStatus.NonVerifiee
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Passerelle de discussion")
                        value: Gateway.libelleEtat
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: Compatibility.explication.length > 0
                        texte: Compatibility.explication
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                visible: !Accueil.lue && Accueil.erreurAccueil.length === 0
                text: qsTr("Chargement…")
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }

            Item { Layout.preferredHeight: Space.space8 }
        }
    }

    Dialog {
        id: confirmationPause
        objectName: "accueil-pause-confirmation"
        anchors.centerIn: parent
        modal: true
        title: qsTr("Mettre Hermes en pause générale ?")
        width: Math.min(page.width - Space.space8 * 2, 520)
        onOpened: raisonPause.text = ""
        contentItem: ColumnLayout {
            spacing: Space.space4
            Text {
                Layout.fillWidth: true
                text: qsTr("Aucune nouvelle carte ne partira tant que vous ne reprendrez pas.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textSecondary
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
            }
            AcpTextField {
                id: raisonPause
                Layout.fillWidth: true
                placeholder: qsTr("Raison (facultative, 200 caractères au plus)")
                accessibleName: qsTr("Raison de la pause générale")
            }
            RowLayout {
                spacing: Space.space4
                AcpButton {
                    objectName: "accueil-pause-confirmer"
                    primary: true
                    label: qsTr("Confirmer la pause générale")
                    onTriggered: {
                        Accueil.basculerPause(true, raisonPause.text);
                        confirmationPause.close();
                    }
                }
                AcpButton {
                    label: qsTr("Annuler")
                    onTriggered: confirmationPause.close()
                }
            }
        }
    }
}
