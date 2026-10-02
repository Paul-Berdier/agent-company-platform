// Accueil de la station (cahier P8 § 7.1).
//
// Des cartes de faits : Hermes (compatibilité lue dans /v1/meta), projets, questions, poste,
// quotas, pause générale et discussions récentes. Chaque carte dit quand elle a été lue et,
// si la dernière lecture a échoué, l'erreur à côté de la valeur gardée. Une valeur absente
// vaut « Inconnu » ; aucune n'est inventée.

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
                text: qsTr("État de votre agent Hermes et de la plateforme ACP, relu toutes les 15 secondes "
                           + "tant que cette page est affichée.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textSecondary
                font.family: Type.prose.family
                font.pixelSize: Type.prose.pixelSize
            }

            BandeauMessage {
                Layout.fillWidth: true
                message: Accueil.messageGeste
                erreur: Accueil.erreurGeste
            }

            GridLayout {
                Layout.fillWidth: true
                columns: width > 820 ? 2 : 1
                columnSpacing: Space.space6
                rowSpacing: Space.space6

                // --- Hermes ---------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-hermes"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Hermes")
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

                // --- Projets ----------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-projets"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Projets")
                    lecture: Accueil.lectureProjets
                    erreurLecture: Accueil.erreurProjets
                    Text {
                        Layout.fillWidth: true
                        visible: Accueil.carteProjets.aucunProjet
                        text: qsTr("Aucun projet pour l'instant. Lancez-en un depuis la page Projets, ou "
                                   + "demandez-le à Hermes dans la discussion.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textSecondary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Projets actifs")
                        value: Accueil.carteProjets.actifs
                        known: Accueil.carteProjets.lisible
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("En pause")
                        value: Accueil.carteProjets.enPause
                        known: Accueil.carteProjets.lisible
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Cartes faites")
                        value: Accueil.carteProjets.cartesFaites
                        known: Accueil.carteProjets.cartesFaites !== qsTr("Inconnu")
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Cartes en attente du poste")
                        value: Accueil.carteProjets.attentePoste
                        known: Accueil.carteProjets.attentePoste !== qsTr("Inconnu")
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: Accueil.carteProjets.lisible && !Accueil.carteProjets.aucunProjet
                        libelle: Accueil.carteProjets.derniereNoteProjet.length > 0
                            ? qsTr("Dernière note (projet « %1 »)").arg(Accueil.carteProjets.derniereNoteProjet)
                            : qsTr("Dernière note")
                        texte: Accueil.carteProjets.derniereNote
                            + (Accueil.carteProjets.derniereNoteTronquee ? qsTr(" […] (extrait)") : "")
                        vide: qsTr("Aucune carte finie pour l'instant.")
                    }
                    AcpButton {
                        label: qsTr("Ouvrir les projets")
                        commandId: "navigation.projects"
                    }
                }

                // --- Questions ----------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-questions"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Questions")
                    cle: !Accueil.carteQuestions.connu ? "unknown"
                        : Accueil.carteQuestions.attente ? "approvalRequired" : "succeeded"
                    libelleEtat: Accueil.carteQuestions.nombre
                    lecture: Accueil.lectureProjets
                    erreurLecture: Accueil.erreurProjets
                    Text {
                        Layout.fillWidth: true
                        text: Accueil.carteQuestions.libelle
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Accueil.carteQuestions.connu ? Colors.textPrimary : Colors.textMuted
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    AcpButton {
                        label: qsTr("Ouvrir les questions")
                        commandId: "navigation.questions"
                    }
                }

                // --- Poste ----------------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-poste"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Poste Windows")
                    cle: Accueil.cartePoste.cle
                    libelleEtat: Accueil.cartePoste.etat
                    lecture: Accueil.lectureProjets
                    erreurLecture: Accueil.erreurProjets
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Machine")
                        value: Accueil.cartePoste.machine
                        known: Accueil.cartePoste.machine !== qsTr("Inconnu")
                        monospace: true
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Vu pour la dernière fois")
                        value: Accueil.cartePoste.vuA
                        known: Accueil.cartePoste.vuA !== qsTr("Inconnu")
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        visible: Accueil.cartePoste.horsLigneDepuis.length > 0
                        label: qsTr("Hors ligne depuis")
                        value: Accueil.cartePoste.horsLigneDepuis
                    }
                    KeyValueRow {
                        Layout.fillWidth: true
                        label: qsTr("Cartes du poste en attente")
                        value: Accueil.cartePoste.cartesEnAttente
                        known: Accueil.cartePoste.cartesEnAttente !== qsTr("Inconnu")
                    }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: Accueil.cartePoste.message.length > 0
                        texte: Accueil.cartePoste.message
                    }
                }

                // --- Quotas -------------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-quotas"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Quotas (voie la plus entamée)")
                    cle: Accueil.carteQuotas.cle
                    libelleEtat: Accueil.carteQuotas.etat
                    lecture: Accueil.lectureQuotas
                    erreurLecture: Accueil.erreurQuotas
                    Text {
                        Layout.fillWidth: true
                        text: Accueil.carteQuotas.libelle
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Accueil.carteQuotas.connu ? Colors.textPrimary : Colors.textMuted
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: [Accueil.carteQuotas.remise, Accueil.carteQuotas.detail].filter(t => t.length > 0).join(" · ")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: Colors.textMuted
                        font.family: Type.metadata.family
                        font.pixelSize: Type.metadata.pixelSize
                    }
                }

                // --- Pause générale ---------------------------------------------------------------
                Carte {
                    objectName: "accueil-carte-pause"
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    titre: qsTr("Pause générale")
                    cle: Accueil.cartePause.etat === 1 ? "degraded" : Accueil.cartePause.etat === 0 ? "succeeded" : "unknown"
                    libelleEtat: Accueil.cartePause.libelle
                    lecture: Accueil.lectureProjets
                    erreurLecture: Accueil.erreurProjets
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

                // --- Discussions récentes ------------------------------------------------------------
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
                        delegate: KeyValueRow {
                            required property var item
                            Layout.fillWidth: true
                            label: item.titre
                            value: qsTr("%1 · %2 messages · %3").arg(item.actifA).arg(item.messages).arg(item.source)
                        }
                    }
                }
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
