// Discussion avec Hermes (cahier P8 § 7.4), par la passerelle JSON-RPC `/api/ws`.
//
// À gauche, les sessions de Hermes ; à droite, la session ouverte : transcription en texte
// brut, réponse qui s'écrit au fil du flux, lignes d'outils sans arguments bruts, demandes
// d'autorisation ou de précision de l'agent, et la zone d'envoi. Rien n'est affiché qui ne
// vienne de Hermes ; l'état de la passerelle est toujours dit.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page

    Component.onCompleted: Discussion.pageVisible = true
    Component.onDestruction: Discussion.pageVisible = false

    readonly property bool coupee: Compatibility.etat !== CompatibilityStatus.NonVerifiee
        && Compatibility.etat !== CompatibilityStatus.Verification
        && Compatibility.etat !== CompatibilityStatus.Injoignable
        && !Compatibility.discussionDisponible

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    EmptyState {
        anchors.fill: parent
        visible: page.coupee
        title: qsTr("Discussion coupée")
        body: Compatibility.explication
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space6
        visible: !page.coupee

        // --- Sessions ------------------------------------------------------------------------------
        ColumnLayout {
            Layout.preferredWidth: 300
            Layout.maximumWidth: 340
            Layout.fillHeight: true
            spacing: Space.space4

            Text {
                text: qsTr("Discussions")
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.pageTitle.family
                font.pixelSize: Type.pageTitle.pixelSize
                font.weight: Type.pageTitle.weight
            }
            RowLayout {
                spacing: Space.space3
                AcpButton {
                    objectName: "discussion-nouvelle"
                    primary: true
                    label: qsTr("Nouvelle discussion")
                    manualEnabled: Discussion.passerellePrete && !Discussion.ouverture
                    onTriggered: Discussion.nouvelle()
                }
                AcpButton {
                    objectName: "discussion-actualiser"
                    label: qsTr("Actualiser")
                    onTriggered: Discussion.actualiserSessions()
                }
            }
            Discret { text: qsTr("Passerelle : %1").arg(Discussion.etatPasserelle) }
            Discret {
                visible: Discussion.erreurSessions.length > 0
                text: Discussion.erreurSessions
                color: Status.statusFailedForeground
            }
            Discret {
                visible: Discussion.sessionsLues && Discussion.sessions.count === 0
                text: qsTr("Aucune discussion pour l'instant.")
            }
            // Comme la liste du navigateur (seconde relecture de P8b, constat desktop-11) : sans état d'attente lu,
            // l'absence de la marque « En attente d'une réponse » ne prouve rien, et c'est dit.
            Discret {
                objectName: "discussion-attente-inconnue"
                visible: Discussion.attenteInconnue.length > 0
                text: Discussion.attenteInconnue
                color: Colors.textSecondary
            }
            ListView {
                id: listeSessions
                objectName: "discussion-sessions"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: Space.space2
                model: Discussion.sessions
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: ligneSession
                    required property var item
                    width: listeSessions.width - Space.space3
                    implicitHeight: contenuSession.implicitHeight + Space.space4 * 2
                    radius: Radius.radiusSm
                    color: ligneSession.item.id === Discussion.sessionOuverte ? Colors.accentMuted
                        : survol.hovered ? Colors.stateHover : Colors.surfacePanel
                    border.width: Space.layoutBorderWidth
                    border.color: Colors.borderSubtle
                    ColumnLayout {
                        id: contenuSession
                        anchors.fill: parent
                        anchors.margins: Space.space4
                        spacing: Space.space1
                        Text {
                            Layout.fillWidth: true
                            text: ligneSession.item.titre
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: Colors.textPrimary
                            font.family: Type.tableCellEmphasis.family
                            font.pixelSize: Type.tableCellEmphasis.pixelSize
                            font.weight: Type.tableCellEmphasis.weight
                        }
                        StatusChip {
                            objectName: "discussion-en-attente-" + ligneSession.item.id
                            visible: ligneSession.item.enAttente === true
                            statusKey: "approvalRequired"
                            label: qsTr("En attente d'une réponse")
                        }
                        Discret {
                            visible: ligneSession.item.apercu.length > 0
                            text: ligneSession.item.apercu
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                        Discret {
                            text: qsTr("%1 · %2 messages · %3").arg(ligneSession.item.date).arg(ligneSession.item.messages)
                                .arg(ligneSession.item.source)
                        }
                    }
                    HoverHandler { id: survol; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Discussion.ouvrir(ligneSession.item.id) }
                    Accessible.role: Accessible.Button
                    Accessible.name: ligneSession.item.enAttente === true
                        ? qsTr("Ouvrir la discussion « %1 », en attente d'une réponse").arg(ligneSession.item.titre)
                        : qsTr("Ouvrir la discussion « %1 »").arg(ligneSession.item.titre)
                    Accessible.onPressAction: Discussion.ouvrir(ligneSession.item.id)
                }
            }
        }

        Rectangle {
            Layout.fillHeight: true
            width: Space.layoutBorderWidth
            color: Colors.borderSubtle
        }

        // --- Session ouverte ----------------------------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Space.space4

            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space4
                Text {
                    Layout.fillWidth: true
                    text: Discussion.sessionVivante.length === 0 ? qsTr("Aucune discussion ouverte")
                        : Discussion.titreSession.length > 0 ? Discussion.titreSession : qsTr("Discussion sans titre")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Colors.textPrimary
                    font.family: Type.panelTitle.family
                    font.pixelSize: Type.panelTitle.pixelSize
                    font.weight: Type.panelTitle.weight
                }
                StatusChip {
                    statusKey: Discussion.passerellePrete ? (Discussion.tourEnCours ? "running" : "succeeded") : "offline"
                    label: Discussion.passerellePrete ? (Discussion.tourEnCours ? qsTr("Hermes travaille") : qsTr("Passerelle prête"))
                                                      : qsTr("Passerelle indisponible")
                }
                AcpButton {
                    objectName: "discussion-arreter"
                    visible: Discussion.tourEnCours
                    label: qsTr("Arrêter")
                    onTriggered: Discussion.arreter()
                }
                AcpButton {
                    objectName: "discussion-quitter"
                    visible: Discussion.sessionVivante.length > 0
                    label: qsTr("Quitter la discussion")
                    onTriggered: Discussion.quitter()
                }
            }

            BandeauMessage {
                Layout.fillWidth: true
                message: Discussion.messageGeste
                erreur: Discussion.erreurGeste
            }
            BandeauMessage {
                Layout.fillWidth: true
                erreur: Discussion.erreurSession
            }
            Discret { visible: Discussion.avis.length > 0; text: Discussion.avis; color: Colors.textSecondary }
            Discret { visible: Discussion.ouverture; text: qsTr("Ouverture de la discussion…") }

            // Demandes de l'agent pour cette session.
            Repeater {
                model: Demandes.demandes
                delegate: CarteDemande {
                    required property var item
                    Layout.fillWidth: true
                    visible: item.sessionId === Discussion.sessionVivante
                    demande: item
                }
            }

            EmptyState {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: Discussion.sessionVivante.length === 0 && !Discussion.ouverture
                title: qsTr("Choisissez une discussion")
                body: qsTr("Ouvrez une discussion de la liste, ou commencez-en une nouvelle. Hermes répond avec le "
                           + "modèle par défaut de son profil.")
            }

            ListView {
                id: transcription
                objectName: "discussion-transcription"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: Discussion.sessionVivante.length > 0
                clip: true
                spacing: Space.space3
                model: Discussion.transcription
                ScrollBar.vertical: ScrollBar {}
                onCountChanged: Qt.callLater(transcription.positionViewAtEnd)
                delegate: BulleMessage {
                    required property var item
                    width: transcription.width - Space.space4
                    auteur: item.auteur
                    texte: item.texte
                    role: item.role
                    enCours: item.enCours
                    statut: item.statut
                    avertissement: item.avertissement
                    heure: item.heure
                    onTexteChanged: if (transcription.atYEnd) Qt.callLater(transcription.positionViewAtEnd)
                }
            }

            Discret {
                objectName: "discussion-ligne-etat"
                visible: Discussion.ligneEtat.length > 0
                text: Discussion.ligneEtat
                color: Status.statusRunningForeground
            }

            RowLayout {
                Layout.fillWidth: true
                visible: Discussion.sessionVivante.length > 0
                spacing: Space.space4
                TextArea {
                    id: saisie
                    objectName: "discussion-saisie"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 84
                    wrapMode: TextEdit.Wrap
                    textFormat: TextEdit.PlainText
                    placeholderText: qsTr("Écrivez à Hermes (Ctrl+Entrée pour envoyer)")
                    color: Colors.textPrimary
                    font.family: Type.prose.family
                    font.pixelSize: Type.prose.pixelSize
                    background: Rectangle {
                        color: Colors.surfacePanelRaised
                        radius: Radius.radiusSm
                        border.width: Space.layoutBorderWidth
                        border.color: saisie.activeFocus ? Colors.borderFocus : Colors.borderInteractive
                    }
                    Accessible.name: qsTr("Message à Hermes")
                    Keys.onPressed: function(evenement) {
                        if ((evenement.key === Qt.Key_Return || evenement.key === Qt.Key_Enter)
                                && (evenement.modifiers & Qt.ControlModifier)) {
                            envoyer.activate();
                            evenement.accepted = true;
                        }
                    }
                }
                AcpButton {
                    id: envoyer
                    objectName: "discussion-envoyer"
                    primary: true
                    label: qsTr("Envoyer")
                    manualEnabled: Discussion.passerellePrete && saisie.text.trim().length > 0
                    onTriggered: {
                        // Le texte n'est effacé que s'il est parti : un refus local le garde.
                        if (Discussion.envoyer(saisie.text))
                            saisie.text = "";
                    }
                }
            }
        }
    }
}
