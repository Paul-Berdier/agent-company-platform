// Discussion avec Hermes (cahier P8 § 7.4), par la passerelle JSON-RPC `/api/ws`.
//
// À gauche, les sessions de Hermes ; à droite, la session ouverte : Markdown contrôlé,
// code copiable, réponse au fil du flux, lignes d’outils sans arguments bruts, demandes
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
    property bool sessionsExpanded: false
    readonly property var usageSession: Discussion.infosSession.usage || ({})
    readonly property string modeleEffectif: Discussion.infosSession.model || qsTr("Modèle non relevé")

    Component.onCompleted: Discussion.pageVisible = visible
    onVisibleChanged: {
        Discussion.pageVisible = visible;
        if (!visible) { renommage.close(); modeles.close(); }
    }
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
            visible: page.width > 860 || page.sessionsExpanded || Discussion.sessionVivante.length === 0
            Layout.preferredWidth: page.width > 860 ? 240 : 200
            Layout.maximumWidth: 280
            Layout.fillHeight: true
            spacing: Space.space4

            Text {
                text: qsTr("Vos discussions")
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
                    label: qsTr("Nouvelle"); iconName: "plus"
                    manualEnabled: Discussion.passerellePrete && !Discussion.ouverture
                    onTriggered: Discussion.nouvelle()
                }
                AcpButton {
                    objectName: "discussion-actualiser"
                    label: ""; iconName: "activity"; Accessible.name: qsTr("Actualiser les discussions")
                    onTriggered: Discussion.actualiserSessions()
                }
            }
            Discret { visible: !Discussion.passerellePrete; text: qsTr("Passerelle : %1").arg(Discussion.etatPasserelle) }
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
            AcpTextField {
                objectName: "discussion-recherche"
                Layout.fillWidth: true
                placeholder: qsTr("Rechercher une discussion…")
                text: Discussion.rechercheSessions
                onTextChanged: if (Discussion.rechercheSessions !== text) Discussion.rechercheSessions = text
            }
            Discret {
                visible: Discussion.sessionsLues
                text: qsTr("%1 discussions chargées").arg(Discussion.sessionsChargees)
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
                    objectName: "discussion-session-" + ligneSession.item.id
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
            AcpButton {
                objectName: "discussion-charger-plus"
                Layout.fillWidth: true
                visible: Discussion.peutChargerPlus
                label: Discussion.chargementSessions ? qsTr("Chargement…") : qsTr("Charger plus de discussions")
                manualEnabled: !Discussion.chargementSessions && Discussion.passerellePrete
                onTriggered: Discussion.chargerPlusSessions()
            }
        }

        Rectangle {
            visible: page.width > 860 || page.sessionsExpanded || Discussion.sessionVivante.length === 0
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
                AcpButton {
                    visible: page.width <= 860 && Discussion.sessionVivante.length > 0
                    label: ""; iconName: "chat"; Accessible.name: qsTr("Afficher les discussions")
                    onTriggered: page.sessionsExpanded = !page.sessionsExpanded
                }
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

            Flow {
                Layout.fillWidth: true
                spacing: Space.space2
                visible: Discussion.sessionVivante.length > 0
                AcpButton {
                    objectName: "discussion-renommer"
                    label: qsTr("Renommer")
                    manualEnabled: Discussion.passerellePrete && !Discussion.gesteEnCours
                    onTriggered: { nomDiscussion.text = Discussion.titreSession; renommage.open(); }
                }
                AcpButton {
                    objectName: "discussion-dupliquer"
                    label: qsTr("Dupliquer")
                    manualEnabled: Discussion.passerellePrete && !Discussion.tourEnCours && !Discussion.ouverture && !Discussion.gesteEnCours
                    onTriggered: Discussion.dupliquer()
                }
                AcpButton {
                    objectName: "discussion-choisir-modele"
                    label: qsTr("Changer de modèle")
                    manualEnabled: Discussion.passerellePrete && !Discussion.tourEnCours && !Discussion.gesteEnCours
                    onTriggered: { Discussion.actualiserModeles(); modeles.open(); }
                }
                AcpButton {
                    objectName: "discussion-outils"
                    label: qsTr("Outils et compétences")
                    onTriggered: Navigation.setCurrentRoute("tools")
                }
            }
            Discret {
                visible: Discussion.sessionVivante.length > 0
                text: page.modeleEffectif + (Discussion.infosSession.provider ? " · " + Discussion.infosSession.provider : "")
                    + (Discussion.infosSession.reasoning_effort ? " · " + Discussion.infosSession.reasoning_effort : "")
            }
            RowLayout {
                Layout.fillWidth: true
                visible: typeof page.usageSession.context_percent === "number"
                ProgressBar {
                    Layout.preferredWidth: 100
                    from: 0; to: 100
                    value: typeof page.usageSession.context_percent === "number" ? page.usageSession.context_percent : 0
                }
                Discret {
                    text: qsTr("Contexte utilisé : %1 %").arg(Math.round(page.usageSession.context_percent || 0))
                        + (page.usageSession.context_estimated ? qsTr(" · estimation") : "")
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
                property bool following: true
                function suivreLaFin() {
                    // Une mise en page différée ne doit pas annuler un geste commencé
                    // depuis sa programmation (molette, glissement ou défilement tactile).
                    if (following && !moving) positionViewAtEnd();
                }
                readonly property string sessionIdentity: Discussion.sessionOuverte || Discussion.sessionVivante
                // Une nouvelle discussion s'ouvre sur sa fin. Une relecture de la même
                // session conserve le choix de lire plus haut dans son historique.
                onSessionIdentityChanged: {
                    following = true;
                    Qt.callLater(transcription.suivreLaFin);
                }
                onMovementStarted: following = false
                onMovementEnded: following = atYEnd
                onCountChanged: if (following) Qt.callLater(transcription.suivreLaFin)
                delegate: BulleMessage {
                    required property var item
                    width: Math.min(transcription.width - Space.space4, 960)
                    x: Math.max(0, (transcription.width - width) / 2)
                    auteur: item.auteur
                    texte: item.texte
                    role: item.role
                    blocsMessage: item.role === "assistant" ? TexteDiscussion.blocs(item.texte) : []
                    onCopierDemande: function(contenu) {
                        Shell.notify(TexteDiscussion.copier(contenu) ? qsTr("Texte copié.") : qsTr("Copie indisponible."));
                    }
                    onLienDemande: function(lien) {
                        if (!TexteDiscussion.ouvrirLien(lien)) Shell.notify(qsTr("Ce lien ne peut pas être ouvert."));
                    }
                    enCours: item.enCours
                    statut: item.statut
                    avertissement: item.avertissement
                    heure: item.heure
                    onTexteChanged: if (transcription.following) Qt.callLater(transcription.suivreLaFin)
                }
            }

            Discret {
                objectName: "discussion-ligne-etat"
                visible: Discussion.ligneEtat.length > 0
                text: Discussion.ligneEtat
                color: Status.statusRunningForeground
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 158
                visible: Discussion.sessionVivante.length > 0
                radius: 8; color: Colors.surfacePanelRaised
                border.width: 1; border.color: saisie.activeFocus ? Colors.borderFocus : Colors.borderInteractive
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: Space.space4; spacing: Space.space3
                    TextArea {
                        id: saisie; objectName: "discussion-saisie"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; selectByMouse: true
                        placeholderText: qsTr("Donnez une consigne, posez une question…")
                        text: Discussion.brouillon
                        onTextChanged: if (Discussion.brouillon !== text) Discussion.brouillon = text
                        color: Colors.textPrimary; placeholderTextColor: Colors.textMuted
                        font.family: Type.prose.family; font.pixelSize: 15
                        background: Item {}
                        Accessible.name: qsTr("Message à Hermes")
                        Keys.onPressed: function(event) {
                            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                                envoyer.activate(); event.accepted = true;
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Space.space3
                        AtelierMark { Layout.preferredWidth: 24; Layout.preferredHeight: 20 }
                        Text { text: page.modeleEffectif; elide: Text.ElideRight; Layout.maximumWidth: 260; color: Colors.textSecondary; font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize }
                        Item { Layout.fillWidth: true }
                        Text { visible: page.width > 900; text: "Ctrl+Entrée"; color: Colors.textMuted; font.family: Type.identifier.family; font.pixelSize: 11 }
                        AcpButton {
                            id: envoyer; objectName: "discussion-envoyer"
                            primary: true; label: qsTr("Envoyer"); iconName: "arrowUp"
                            manualEnabled: Discussion.passerellePrete && !Discussion.ouverture && saisie.text.trim().length > 0
                            onTriggered: Discussion.envoyer(saisie.text)
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: renommage
        objectName: "discussion-renommage"
        modal: true; focus: true
        width: Math.min(page.width - 32, 460)
        x: (page.width - width) / 2; y: Math.max(16, (page.height - height) / 2)
        padding: Space.space6
        background: Rectangle { color: Colors.surfacePanel; radius: Radius.radiusMd; border.color: Colors.borderDefault; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: Space.space4
            Text { text: qsTr("Renommer la discussion"); color: Colors.textPrimary; font.family: Type.panelTitle.family; font.pixelSize: Type.panelTitle.pixelSize }
            AcpTextField { id: nomDiscussion; objectName: "discussion-nouveau-titre"; Layout.fillWidth: true; placeholder: qsTr("Titre de la discussion") }
            RowLayout {
                Item { Layout.fillWidth: true }
                AcpButton { label: qsTr("Annuler"); onTriggered: renommage.close() }
                AcpButton {
                    objectName: "discussion-confirmer-titre"; primary: true; label: qsTr("Renommer")
                    manualEnabled: nomDiscussion.text.trim().length > 0 && Discussion.passerellePrete
                    onTriggered: { Discussion.renommer(nomDiscussion.text); renommage.close(); }
                }
            }
        }
    }
    Popup {
        id: modeles
        objectName: "discussion-modeles"
        modal: true; focus: true
        width: Math.min(page.width - 32, 640)
        height: Math.min(page.height - 32, 500)
        x: (page.width - width) / 2; y: (page.height - height) / 2
        padding: Space.space6
        background: Rectangle { color: Colors.surfacePanel; radius: Radius.radiusMd; border.color: Colors.borderDefault; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: Space.space4
            RowLayout {
                Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: qsTr("Modèle de cette discussion"); color: Colors.textPrimary; font.family: Type.panelTitle.family; font.pixelSize: Type.panelTitle.pixelSize }
                AcpButton { label: qsTr("Fermer"); onTriggered: modeles.close() }
            }
            Discret { text: qsTr("Le choix s’applique à cette session. Le modèle par défaut du serveur est conservé.") }
            Discret { visible: Discussion.chargementModeles; text: qsTr("Lecture des modèles disponibles…") }
            BandeauMessage { Layout.fillWidth: true; erreur: Discussion.erreurModeles }
            AcpTextField { id: rechercheModele; objectName: "discussion-recherche-modele"; Layout.fillWidth: true; placeholder: qsTr("Filtrer les modèles…") }
            ListView {
                id: listeModeles
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: Discussion.modelesSession
                spacing: 0
                ScrollBar.vertical: ScrollBar {}
                delegate: AcpButton {
                    required property var item
                    objectName: "discussion-modele-" + item.fournisseur + "-" + item.modele
                    width: listeModeles.width
                    visible: (item.libelle + " " + item.fournisseur + " " + item.modele).toLowerCase().indexOf(rechercheModele.text.toLowerCase()) >= 0
                    height: visible ? implicitHeight : 0
                    readonly property int caracteresVisibles: Math.max(18, Math.floor(width / 9) - 6)
                    label: item.libelle.length > caracteresVisibles ? item.libelle.slice(0, caracteresVisibles - 1) + "…" : item.libelle
                    Accessible.name: item.libelle
                    manualEnabled: Discussion.passerellePrete && !Discussion.gesteEnCours
                    onTriggered: { Discussion.choisirModele(item.fournisseur, item.modele); modeles.close(); }
                    HoverHandler { id: survolModele }
                    ToolTip.visible: survolModele.hovered
                    ToolTip.text: item.libelle + (item.avertissement ? "\n" + item.avertissement : "")
                }
            }
            Discret { visible: Discussion.modelesCharges && Discussion.modelesSession.count === 0; text: qsTr("Aucun modèle disponible n’a été renvoyé par Hermes.") }
        }
    }
    Popup {
        id: confirmationModele
        objectName: "discussion-confirmation-modele"
        visible: page.visible && Discussion.confirmationModele.length > 0
        modal: true; focus: true
        width: Math.min(page.width - 32, 480)
        x: (page.width - width) / 2; y: Math.max(16, (page.height - height) / 2)
        padding: Space.space6
        closePolicy: Popup.NoAutoClose
        background: Rectangle { color: Colors.surfacePanel; radius: Radius.radiusMd; border.color: Colors.borderDefault; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: Space.space4
            Discret { text: Discussion.confirmationModele; color: Colors.textPrimary }
            RowLayout {
                Item { Layout.fillWidth: true }
                AcpButton { objectName: "discussion-annuler-modele"; label: qsTr("Annuler"); onTriggered: Discussion.annulerChoixModele() }
                AcpButton { objectName: "discussion-confirmer-modele"; primary: true; label: qsTr("Confirmer ce modèle"); onTriggered: Discussion.confirmerModele() }
            }
        }
    }
}
