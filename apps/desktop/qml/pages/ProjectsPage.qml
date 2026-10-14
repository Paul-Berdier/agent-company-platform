// Espace projet : les objectifs, les étapes et les résultats rapportés par Hermes.
// Les gestes et les règles restent ceux de ProjetsViewModel.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    Component.onCompleted: Projets.pageVisible = visible
    onVisibleChanged: {
        Projets.pageVisible = visible;
        if (!visible)
            carteEntiere.close();
    }
    Component.onDestruction: Projets.pageVisible = false

    component Discret: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }
    component TitreSection: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textPrimary
        font.family: Type.panelTitle.family
        font.pixelSize: Type.panelTitle.pixelSize
        font.weight: Type.panelTitle.weight
    }
    component Alerte: Discret {
        visible: text.length > 0
        color: Status.statusDegradedForeground
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }
    component Onglet: Button {
        id: onglet
        property bool choisi: false
        implicitHeight: 40
        leftPadding: Space.space6
        rightPadding: Space.space6
        contentItem: Text {
            text: onglet.text
            textFormat: Text.PlainText
            color: onglet.choisi ? Colors.textPrimary : Colors.textMuted
            font.family: Type.buttonLabel.family
            font.pixelSize: Type.buttonLabel.pixelSize
            font.weight: onglet.choisi ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: onglet.hovered ? Colors.stateHover : "transparent"
            border.width: onglet.activeFocus ? Space.layoutFocusRingWidth : 0
            border.color: Colors.borderFocus
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 2
                color: onglet.choisi ? Colors.accentPrimary : "transparent"
            }
        }
        Accessible.name: text
        Accessible.role: Accessible.PageTab
        Accessible.selected: choisi
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.width < 760 ? Space.space6 : Space.space8
        spacing: Space.space5
        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space4
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Space.space1
                Text {
                    Layout.fillWidth: true
                    text: Projets.vue === "detail" ? qsTr("Espace projet") : Projets.vue === "nouveau" ? qsTr("Nouveau projet") : qsTr("Vos projets")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                Discret {
                    visible: Projets.vue === "liste"
                    text: qsTr("Vos projets s’exécutent sur le serveur distant. Fermer ce client ne les arrête pas.")
                }
            }
            AcpButton {
                objectName: "projets-vue-liste"
                visible: Projets.vue !== "liste"
                label: qsTr("Tous les projets")
                onTriggered: Projets.afficherListe()
            }
            AcpButton {
                objectName: "projets-actualiser"
                label: qsTr("Actualiser")
                onTriggered: Projets.actualiser()
            }
            AcpButton {
                objectName: "projets-vue-nouveau"
                visible: Projets.vue !== "nouveau"
                label: qsTr("Nouveau projet")
                primary: true
                onTriggered: Projets.afficherNouveau()
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

    Component {
        id: vueListe
        ColumnLayout {
            spacing: Space.space5
            Alerte {
                visible: Projets.pause.etat === 1
                text: qsTr("Hermes est en pause générale (%1, depuis %2). La reprise se fait depuis l'accueil.").arg(Projets.pause.raison).arg(Projets.pause.depuis)
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Projets.lectureListe
                erreur: Projets.erreurListe
            }
            Discret {
                visible: !Projets.listeLue && Projets.erreurListe.length === 0
                text: qsTr("Chargement des projets…")
            }
            EmptyState {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: Projets.listeLue && Projets.projets.count === 0
                title: qsTr("Votre prochain projet commence ici")
                body: qsTr("Donnez un objectif à Hermes. Vous retrouverez ici ses étapes, les questions et le résultat.")
                actionLabel: qsTr("Créer un projet")
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
                keyNavigationEnabled: true
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    id: ligne
                    required property var item
                    required property int index
                    objectName: "projets-ouvrir-" + item.id
                    width: listeProjets.width - Space.space5
                    height: contenuProjet.implicitHeight + Space.space6 * 2
                    padding: Space.space6
                    onClicked: Projets.ouvrirProjet(item.id)
                    Accessible.name: qsTr("Ouvrir %1, %2").arg(item.titre).arg(item.etatLibelle)
                    background: Rectangle {
                        radius: Radius.radiusSm
                        color: ligne.hovered ? Colors.stateHover : Colors.surfacePanel
                        border.width: ligne.activeFocus ? Space.layoutFocusRingWidth : Space.layoutBorderWidth
                        border.color: ligne.activeFocus ? Colors.borderFocus : Colors.borderSubtle
                    }
                    contentItem: ColumnLayout {
                        id: contenuProjet
                        spacing: Space.space4
                        RowLayout {
                            Layout.fillWidth: true
                            TitreSection {
                                text: ligne.item.titre
                            }
                            StatusChip {
                                statusKey: ligne.item.etatCle
                                label: ligne.item.etatLibelle
                            }
                            Text {
                                text: "›"
                                color: Colors.textMuted
                                font.pixelSize: 24
                                Accessible.ignored: true
                            }
                        }
                        Discret {
                            text: ligne.item.depot + "  ·  " + ligne.item.profil + "  ·  " + ligne.item.tour
                        }
                        Text {
                            Layout.fillWidth: true
                            text: ligne.item.derniereNote.length > 0 ? ligne.item.derniereNote + (ligne.item.noteTronquee ? "…" : "") : qsTr("Le résultat des premières étapes apparaîtra ici.")
                            textFormat: Text.PlainText
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            wrapMode: Text.WordWrap
                            color: Colors.textSecondary
                            font.family: Type.prose.family
                            font.pixelSize: Type.prose.pixelSize
                        }
                        Discret {
                            text: qsTr("%1 cartes faites · %2 en cours · %3 en attente · %4 bloquées · %5 en triage").arg(ligne.item.cartes).arg(ligne.item.enCours).arg(ligne.item.attentePoste).arg(ligne.item.bloquees).arg(ligne.item.triage)
                        }
                        Discret {
                            visible: ligne.item.questionsEnAttente
                            text: qsTr("%1 questions à traiter").arg(ligne.item.questions)
                            color: Status.statusApprovalRequiredForeground
                        }
                    }
                }
            }
            Discret {
                objectName: "projets-cadence"
                text: Projets.cadence
            }
        }
    }

    Component {
        id: vueDetail
        ColumnLayout {
            id: espace
            objectName: "projets-detail"
            spacing: Space.space4
            property int onglet: 0
            property string carteSelectionnee: ""
            property var carte: ({})
            readonly property bool inspecteurPresent: (carte.carte || "").length > 0

            function choisirCarte(index) {
                const ligne = Projets.cartes.get(index);
                carteSelectionnee = ligne.carte || "";
                carte = ligne;
            }
            // La sélection suit l'identifiant après une relecture du modèle.
            function synchroniserCarte() {
                for (let index = 0; index < Projets.cartes.count; ++index) {
                    if (Projets.cartes.get(index).carte === carteSelectionnee) {
                        listeCartes.currentIndex = index;
                        choisirCarte(index);
                        return;
                    }
                }
                listeCartes.currentIndex = Projets.cartes.count > 0 ? 0 : -1;
                choisirCarte(listeCartes.currentIndex);
            }
            Component.onCompleted: synchroniserCarte()
            Connections {
                target: Projets
                function onDetailChange() {
                    espace.synchroniserCarte();
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Space.space5
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space2
                    TitreSection {
                        text: Projets.detail.titre
                        font.pixelSize: 24
                    }
                    Discret {
                        text: Projets.detail.depot + "  ·  " + Projets.detail.profil
                    }
                }
                StatusChip {
                    statusKey: Projets.detail.etatCle
                    label: Projets.detail.etatLibelle
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: Space.space4
                AcpButton {
                    objectName: "projets-retour"
                    label: qsTr("Retour")
                    onTriggered: Projets.afficherListe()
                }
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
                    label: qsTr("Kanban dans le navigateur")
                    onTriggered: Projets.ouvrirKanban()
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: objectifProjet.implicitHeight + Space.space5 * 2
                color: Colors.surfacePanel
                radius: Radius.radiusSm
                border.color: Colors.borderSubtle
                Rectangle {
                    width: 3
                    height: parent.height
                    color: Colors.accentPrimary
                }
                ColumnLayout {
                    id: objectifProjet
                    anchors.fill: parent
                    anchors.margins: Space.space5
                    anchors.leftMargin: Space.space6
                    spacing: Space.space2
                    Discret {
                        text: qsTr("OBJECTIF")
                        color: Colors.accentPrimary
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: Projets.detail.objectif
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        color: Colors.textPrimary
                        font.family: Type.prose.family
                        font.pixelSize: Type.prose.pixelSize
                    }
                }
            }
            Rectangle {
                id: panneauChef
                objectName: "projets-boucle-chef"
                Layout.fillWidth: true
                implicitHeight: boucleChef.implicitHeight + Space.space3 * 2
                color: Colors.surfaceSunken
                radius: Radius.radiusSm
                property bool developpe: false
                ColumnLayout {
                    id: boucleChef
                    anchors.fill: parent
                    anchors.margins: Space.space3
                    spacing: Space.space2
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Boucle du chef · tour %1 · %2 cartes faites").arg(Projets.detail.tour || qsTr("Inconnu")).arg(Projets.detail.cartesFaites || qsTr("Inconnu"))
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: Colors.textPrimary
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                        AcpButton {
                            objectName: "projets-boucle-details"
                            label: panneauChef.developpe ? qsTr("Réduire") : qsTr("Fonctionnement")
                            onTriggered: panneauChef.developpe = !panneauChef.developpe
                        }
                    }
                    Discret {
                        visible: panneauChef.developpe
                        text: qsTr("Hermes planifie → délègue aux assistants → fait relire → rassemble les preuves. Les corrections repartent en revue ; la synthèse attend les étapes terminées.")
                    }
                    Discret {
                        visible: panneauChef.developpe
                        text: qsTr("Limites de ce projet : %1 corrections par étape ; reste %2. À la limite, une décision vous est demandée dans Questions.").arg(Projets.detail.corrections || qsTr("Inconnu")).arg(Projets.detail.restants || qsTr("Inconnu"))
                    }
                }
            }
            Discret {
                visible: !Projets.detailLu && Projets.erreurDetail.length === 0
                text: qsTr("Chargement du projet…")
            }
            EtatLecture {
                Layout.fillWidth: true
                lecture: Projets.lectureDetail
                erreur: Projets.erreurDetail
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 0
                Onglet {
                    objectName: "projets-onglet-travail"
                    text: qsTr("Travail")
                    choisi: espace.onglet === 0
                    onClicked: espace.onglet = 0
                }
                Onglet {
                    objectName: "projets-onglet-resultats"
                    text: qsTr("Résultats")
                    choisi: espace.onglet === 1
                    onClicked: espace.onglet = 1
                }
                Onglet {
                    objectName: "projets-onglet-journal"
                    text: qsTr("Journal")
                    choisi: espace.onglet === 2
                    onClicked: espace.onglet = 2
                }
                Onglet {
                    objectName: "projets-onglet-reglages"
                    text: qsTr("Réglages")
                    choisi: espace.onglet === 3
                    onClicked: espace.onglet = 3
                }
                Item {
                    Layout.fillWidth: true
                }
            }
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: espace.onglet
                SplitView {
                    id: travail
                    objectName: "projets-travail"
                    orientation: width < 760 ? Qt.Vertical : Qt.Horizontal
                    handle: Rectangle {
                        implicitWidth: 8
                        implicitHeight: 8
                        color: SplitHandle.hovered || SplitHandle.pressed ? Colors.borderFocus : "transparent"
                        Rectangle {
                            anchors.centerIn: parent
                            width: travail.orientation === Qt.Horizontal ? 1 : parent.width
                            height: travail.orientation === Qt.Horizontal ? parent.height : 1
                            color: Colors.borderSubtle
                        }
                    }
                    ColumnLayout {
                        SplitView.fillWidth: true
                        SplitView.fillHeight: true
                        SplitView.minimumWidth: travail.orientation === Qt.Horizontal ? 240 : 0
                        SplitView.minimumHeight: travail.orientation === Qt.Vertical ? 100 : 0
                        spacing: Space.space4
                        RowLayout {
                            Layout.fillWidth: true
                            TitreSection {
                                text: qsTr("Étapes du projet")
                            }
                            Discret {
                                Layout.fillWidth: false
                                text: qsTr("%1 cartes").arg(Projets.cartes.count)
                            }
                        }
                        Discret {
                            visible: Projets.cartes.count === 0
                            text: qsTr("Les étapes apparaîtront dès que Hermes aura planifié le projet.")
                        }
                        ListView {
                            id: listeCartes
                            objectName: "projets-cartes"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: Space.space3
                            model: Projets.cartes
                            keyNavigationEnabled: true
                            activeFocusOnTab: true
                            Keys.onUpPressed: {
                                currentIndex = Math.max(0, currentIndex - 1);
                                espace.choisirCarte(currentIndex);
                            }
                            Keys.onDownPressed: {
                                currentIndex = Math.min(count - 1, currentIndex + 1);
                                espace.choisirCarte(currentIndex);
                            }
                            ScrollBar.vertical: ScrollBar {}
                            delegate: ItemDelegate {
                                id: etape
                                required property var item
                                required property int index
                                width: listeCartes.width - Space.space5
                                height: contenuEtape.implicitHeight + Space.space5 * 2
                                padding: Space.space5
                                highlighted: espace.carteSelectionnee === item.carte
                                onClicked: {
                                    listeCartes.currentIndex = index;
                                    espace.choisirCarte(index);
                                }
                                Accessible.name: item.titre + ", " + item.statutLibelle
                                background: Rectangle {
                                    radius: Radius.radiusSm
                                    color: etape.highlighted ? Colors.stateSelected : etape.hovered ? Colors.stateHover : Colors.surfacePanel
                                    border.width: etape.activeFocus ? 2 : 1
                                    border.color: etape.activeFocus ? Colors.borderFocus : etape.highlighted ? Colors.accentPrimary : Colors.borderSubtle
                                }
                                contentItem: ColumnLayout {
                                    id: contenuEtape
                                    spacing: Space.space3
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Discret {
                                            text: etape.item.groupe
                                            color: Colors.accentPrimary
                                        }
                                        StatusChip {
                                            statusKey: etape.item.statutCle
                                            label: etape.item.statutLibelle
                                        }
                                    }
                                    TitreSection {
                                        text: etape.item.titre
                                        font.pixelSize: Type.tableCellEmphasis.pixelSize
                                    }
                                    Discret {
                                        text: etape.item.voie + "  ·  " + qsTr("Tour %1").arg(etape.item.tour)
                                    }
                                }
                            }
                        }
                    }
                    Rectangle {
                        SplitView.preferredWidth: 340
                        SplitView.minimumWidth: travail.orientation === Qt.Horizontal ? 280 : 0
                        SplitView.preferredHeight: 170
                        SplitView.minimumHeight: 100
                        color: Colors.surfacePanel
                        radius: Radius.radiusSm
                        border.color: Colors.borderSubtle
                        ScrollView {
                            id: defilementInspecteur
                            anchors.fill: parent
                            anchors.margins: Space.space6
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                width: defilementInspecteur.availableWidth
                                spacing: Space.space5
                                TitreSection {
                                    text: qsTr("Détail de l'étape")
                                }
                                Discret {
                                    visible: !espace.inspecteurPresent
                                    text: qsTr("Sélectionnez une carte pour lire son résumé et ses informations d'exécution.")
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: espace.inspecteurPresent
                                    spacing: Space.space5
                                    TitreSection {
                                        text: espace.carte.titre || ""
                                    }
                                    StatusChip {
                                        statusKey: espace.carte.statutCle || "unknown"
                                        label: espace.carte.statutLibelle || ""
                                    }
                                    BlocTexte {
                                        Layout.fillWidth: true
                                        libelle: espace.carte.resumeTronque ? qsTr("Résumé — extrait de %1 caractères sur %2").arg((espace.carte.resume || "").length).arg(espace.carte.resumeLongueur || "") : qsTr("Résumé")
                                        texte: espace.carte.resume || ""
                                        vide: qsTr("Aucun résumé reçu pour cette carte.")
                                    }
                                    AcpButton {
                                        visible: espace.carte.resumeTronque === true
                                        label: qsTr("Lire le résumé entier")
                                        onTriggered: Projets.lireCarteEnEntier(espace.carteSelectionnee)
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        height: 1
                                        color: Colors.borderSubtle
                                    }
                                    BlocTexte {
                                        Layout.fillWidth: true
                                        libelle: qsTr("Exécutant")
                                        texte: espace.carte.voie || ""
                                    }
                                    BlocTexte {
                                        Layout.fillWidth: true
                                        libelle: qsTr("Modèle demandé")
                                        texte: espace.carte.modele || ""
                                    }
                                    BlocTexte {
                                        Layout.fillWidth: true
                                        libelle: qsTr("Modèle observé")
                                        texte: espace.carte.modeleServi || ""
                                    }
                                    Discret {
                                        text: qsTr("Effort : %1 · Palier : %2").arg(espace.carte.effort || "").arg(espace.carte.palier || "")
                                    }
                                    Alerte {
                                        text: espace.carte.mention || ""
                                    }
                                    ExecutionDetails {
                                        Layout.fillWidth: true
                                        execution: espace.carte.execution || ({})
                                    }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Colors.borderSubtle
                                }
                                TitreSection {
                                    text: qsTr("Questions du projet")
                                }
                                Discret {
                                    visible: Projets.questionsDuProjet.count === 0
                                    text: qsTr("Aucune question en attente.")
                                }
                                Repeater {
                                    model: Projets.questionsDuProjet
                                    delegate: ColumnLayout {
                                        required property var item
                                        Layout.fillWidth: true
                                        spacing: Space.space3
                                        StatusChip {
                                            statusKey: item.etatCle
                                            label: item.etatLibelle
                                        }
                                        BlocTexte {
                                            Layout.fillWidth: true
                                            texte: item.texte
                                        }
                                    }
                                }
                                Discret {
                                    visible: Projets.questionsDuProjet.count > 0
                                    text: qsTr("Retrouvez ces demandes dans Questions pour y répondre.")
                                }
                            }
                        }
                    }
                }

                ScrollView {
                    id: defilementResultats
                    objectName: "projets-resultats"
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: Math.max(0, defilementResultats.availableWidth - Space.space5)
                        spacing: Space.space6
                        TitreSection {
                            text: qsTr("Résultat du projet")
                        }
                        BlocTexte {
                            Layout.fillWidth: true
                            texte: Projets.detail.resultat
                            vide: qsTr("Aucun résultat final pour le moment. Les résumés disponibles se trouvent dans les cartes de l'onglet Travail.")
                        }
                        Discret {
                            visible: Projets.detail.resultat.length > 0
                            text: qsTr("Synthèse du tour %1").arg(Projets.detail.resultatTour)
                        }
                        Alerte {
                            visible: Projets.detail.resultatTronque
                            text: qsTr("Texte borné à 100 000 caractères par le greffon.")
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: Colors.borderSubtle
                        }
                        TitreSection {
                            text: qsTr("Exploration du dépôt")
                            visible: Projets.detail.exploration.length > 0
                        }
                        BlocTexte {
                            Layout.fillWidth: true
                            visible: Projets.detail.exploration.length > 0
                            texte: Projets.detail.exploration
                        }
                        TitreSection {
                            text: qsTr("Tours et décisions")
                            visible: Projets.tours.count > 0
                        }
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
                }
                JournalProjet {}
                ScrollView {
                    id: defilementReglages
                    objectName: "projets-reglages"
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: Math.min(Math.max(0, defilementReglages.availableWidth - Space.space5), Type.measureProse + 160)
                        spacing: Space.space5
                        TitreSection {
                            text: qsTr("Réglages du projet")
                        }
                        // Seconde relecture de P8b (constat desktop-8) : sans l'annonce de l'étape P7 par /v1/meta, aucun
                        // bouton « Qui répond » ni « Clore » ; la raison est dite à leur place.
                        Discret {
                            objectName: "projet-gestes-p7"
                            visible: (Projets.detail.gestesP7 || "").length > 0
                            text: Projets.detail.gestesP7 || ""
                            color: Colors.textSecondary
                        }

                        // --- « Changer qui répond » (étape P7) : rien ne change à l'écran avant la réponse du greffon.
                        Item {
                            id: reglage
                            property bool ouvert: false
                            Layout.fillWidth: true
                            implicitHeight: colonneReglage.implicitHeight
                            visible: Projets.detail.peutChangerReponses === true
                            Connections {
                                target: Projets
                                function onReglageReponsesEnregistre() {
                                    reglage.ouvert = false;
                                }
                                function onVueChange() {
                                    reglage.ouvert = false;
                                }
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
                                Discret {
                                    visible: reglage.ouvert
                                    text: qsTr("Qui répond aux questions suivantes")
                                    color: Colors.textSecondary
                                }
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
                                    text: qsTr("Le changement vaut pour les questions suivantes ; les questions déjà ouvertes gardent " + "leur traitement, et vous pouvez toujours y répondre vous-même.")
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
                                function onClotureFaite() {
                                    cloture.confirmation = false;
                                }
                                function onVueChange() {
                                    cloture.confirmation = false;
                                }
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
                                Discret {
                                    visible: cloture.confirmation
                                    text: qsTr("• Les cartes ouvertes du projet sont archivées ; un travail en cours est arrêté.")
                                }
                                Discret {
                                    visible: cloture.confirmation
                                    text: qsTr("• Ses questions ouvertes sont annulées.")
                                }
                                Discret {
                                    visible: cloture.confirmation
                                    text: qsTr("• Le projet passe « Terminé » si la synthèse du tour en cours est faite, sinon « Abandonné ».")
                                }
                                Discret {
                                    visible: cloture.confirmation
                                    text: qsTr("• Aucune notification n'est envoyée ; les branches déjà rapportées restent sur l'exécutant jusqu'à leur purge (7 jours).")
                                }
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
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: Colors.borderSubtle
                        }
                        TitreSection {
                            text: qsTr("Contexte et limites")
                        }
                        BlocTexte {
                            Layout.fillWidth: true
                            libelle: qsTr("Objectif complet")
                            texte: Projets.detail.objectif
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Type de projet")
                            value: Projets.detail.profil
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Dépôt")
                            value: Projets.detail.depot
                            monospace: true
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Qui répond")
                            value: Projets.detail.reponses
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Origine")
                            value: Projets.detail.origine
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Tour")
                            value: Projets.detail.tour
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Cartes créées")
                            value: Projets.detail.cartesCreees
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Cartes faites")
                            value: Projets.detail.cartesFaites
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Corrections par étape au plus")
                            value: Projets.detail.corrections
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Restants")
                            value: Projets.detail.restants
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Créé")
                            value: Projets.detail.creeLe
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            visible: Projets.detail.termineLe.length > 0
                            label: qsTr("Terminé")
                            value: Projets.detail.termineLe
                        }
                        KeyValueRow {
                            Layout.fillWidth: true
                            label: qsTr("Tableau kanban")
                            value: Projets.detail.tableau
                            monospace: true
                        }
                        Discret {
                            objectName: "projets-veille"
                            text: Projets.etatVeille
                        }
                    }
                }
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
                width: Math.min(Math.max(0, defilementFormulaire.availableWidth - Space.space5), Type.measureProse + 160)
                spacing: Space.space4

                readonly property var f: Projets.formulaire
                property string reponses: "hermes_d_abord"
                property bool avance: false
                readonly property bool complet: titreChamp.text.trim().length > 0 && objectifChamp.text.trim().length > 0 && !formulaire.f.modeleExige

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Que voulez-vous réaliser ? Décrivez le résultat attendu. Le chef Hermes planifie, délègue, fait vérifier et reprend les corrections dans les limites du projet.")
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
                Alerte {
                    text: formulaire.f.erreurPoste
                }
                Alerte {
                    text: formulaire.f.erreurCatalogue
                }

                TitreSection {
                    text: qsTr("Le résultat que vous attendez")
                }
                TextArea {
                    id: objectifChamp
                    objectName: "projets-champ-objectif"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    padding: Space.space5
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

                Discret {
                    text: qsTr("Nom du projet")
                    color: Colors.textSecondary
                }
                AcpTextField {
                    id: titreChamp
                    objectName: "projets-champ-titre"
                    Layout.fillWidth: true
                    placeholder: qsTr("Titre (120 caractères au plus)")
                    accessibleName: qsTr("Titre")
                }

                Discret {
                    text: qsTr("Type de projet")
                    color: Colors.textSecondary
                }
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

                Discret {
                    text: qsTr("Dépôt")
                    color: Colors.textSecondary
                }
                ComboBox {
                    id: depotChoix
                    objectName: "projets-champ-depot"
                    Layout.fillWidth: true
                    enabled: formulaire.f.depotsConnus
                    model: [qsTr("Sans dépôt")].concat(formulaire.f.depots)
                    currentIndex: formulaire.f.depot.length > 0 ? formulaire.f.depots.indexOf(formulaire.f.depot) + 1 : 0
                    Accessible.name: qsTr("Dépôt")
                    onActivated: function (index) {
                        Projets.choisirDepot(index === 0 ? "" : formulaire.f.depots[index - 1]);
                    }
                }
                Discret {
                    objectName: "projets-aide-depot"
                    visible: formulaire.f.aideDepot.length > 0
                    text: formulaire.f.aideDepot
                }

                CheckBox {
                    objectName: "projets-routage-manuel"
                    Layout.fillWidth: true
                    text: qsTr("Choisir manuellement l'assistant, le modèle et l'effort")
                    checked: !formulaire.f.routageAutomatique
                    onToggled: {
                        Projets.choisirRoutageAutomatique(!checked);
                        if (checked) formulaire.avance = true;
                    }
                }
                Discret {
                    text: formulaire.f.routageAutomatique
                        ? qsTr("Auto choisit dans la table de routage autorisée et respecte vos verrous. Après connexion et relevé : Comptes et modèles → Modèles d'exécution, relisez et appliquez les suggestions souhaitées, puis Valider la table.")
                        : qsTr("Choix manuel : les paramètres d'exploration ci-dessous sont envoyés explicitement.")
                }

                AcpButton {
                    objectName: "projets-avance"
                    label: formulaire.avance ? qsTr("Masquer les options avancées") : qsTr("Options avancées")
                    onTriggered: formulaire.avance = !formulaire.avance
                }
                Alerte {
                    visible: !formulaire.avance && formulaire.f.modeleExige
                    text: qsTr("Un modèle doit être choisi dans les options avancées avant de lancer ce projet.")
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: formulaire.avance
                    spacing: Space.space4
                    Discret {
                        text: qsTr("Qui répond aux questions")
                        color: Colors.textSecondary
                    }
                    Discret {
                        visible: formulaire.f.reponsesSansObjet
                        text: qsTr("Sans objet sans dépôt : aucune question ne naît d'un projet sans dépôt ; s'il manque une " + "information, Hermes bloque une carte avec sa raison (page Questions, cartes bloquées).")
                    }
                    RadioButton {
                        visible: !formulaire.f.reponsesSansObjet
                        text: qsTr("Hermes d'abord : il répond s'il le peut, sinon il vous transmet la question.")
                        checked: formulaire.reponses === "hermes_d_abord"
                        onToggled: if (checked)
                            formulaire.reponses = "hermes_d_abord"
                    }
                    RadioButton {
                        visible: !formulaire.f.reponsesSansObjet
                        text: qsTr("Moi : chaque question vous est transmise directement.")
                        checked: formulaire.reponses === "proprietaire"
                        onToggled: if (checked)
                            formulaire.reponses = "proprietaire"
                    }

                    Alerte {
                        text: formulaire.f.releveFactice ? qsTr("Relevé factice : ces modèles viennent d'un relevé de test, pas de votre serveur.") : ""
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: formulaire.f.avecExploration && !formulaire.f.routageAutomatique
                        spacing: Space.space3
                        Text {
                            text: qsTr("Exploration du dépôt")
                            textFormat: Text.PlainText
                            color: Colors.textPrimary
                            font.family: Type.panelTitle.family
                            font.pixelSize: Type.panelTitle.pixelSize
                            font.weight: Type.panelTitle.weight
                        }
                        Discret {
                            text: qsTr("Le serveur distant lit le dépôt, sans rien y modifier, avant la planification.")
                        }
                        Discret {
                            text: qsTr("Exécutant")
                            color: Colors.textSecondary
                        }
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
                            // Étape P7 : un exécutant fermé pour le dépôt choisi est grisé, jamais choisissable.
                            delegate: ItemDelegate {
                                required property var modelData
                                required property int index
                                objectName: "projets-voie-option-" + modelData.valeur
                                width: voieChoix.width
                                text: modelData.libelle
                                enabled: !modelData.fermee
                                highlighted: voieChoix.highlightedIndex === index
                            }
                        }
                        Repeater {
                            model: formulaire.f.voiesFermees || []
                            delegate: Discret {
                                required property var modelData
                                objectName: "projets-voie-fermee"
                                text: modelData
                            }
                        }
                        Alerte {
                            objectName: "projets-aucune-voie-ouverte"
                            text: formulaire.f.aucuneVoieOuverte === true ? qsTr("Aucun exécutant ouvert pour ce dépôt. Le lancement sera refusé tant que ses prérequis ne sont pas réunis.") : ""
                        }
                        Discret {
                            text: qsTr("Modèle")
                            color: Colors.textSecondary
                        }
                        ComboBox {
                            id: modeleChoix
                            objectName: "projets-champ-modele"
                            Layout.fillWidth: true
                            model: [formulaire.f.libelleModeleVide].concat(formulaire.f.modeles)
                            currentIndex: formulaire.f.modele.length > 0 ? formulaire.f.modeles.indexOf(formulaire.f.modele) + 1 : 0
                            Accessible.name: qsTr("Modèle")
                            onActivated: function (index) {
                                Projets.choisirModele(index === 0 ? "" : formulaire.f.modeles[index - 1]);
                            }
                        }
                        Discret {
                            text: qsTr("Effort")
                            color: Colors.textSecondary
                        }
                        ComboBox {
                            id: effortChoix
                            objectName: "projets-champ-effort"
                            Layout.fillWidth: true
                            model: [qsTr("Par défaut")].concat(formulaire.f.efforts)
                            Accessible.name: qsTr("Effort")
                            onModelChanged: currentIndex = 0
                        }
                        Discret {
                            text: qsTr("Relevé du %1").arg(formulaire.f.releveDu)
                        }
                        Alerte {
                            text: formulaire.f.relevePerime ? qsTr("Relevé périmé : le serveur distant doit publier un nouvel inventaire.") : ""
                        }
                        Alerte {
                            text: formulaire.f.modeleExige ? qsTr("Choisissez un modèle pour l'exploration : le relevé de cet exécutant n'en désigne aucun par défaut.") : ""
                        }
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
                    label: Projets.gesteEnCours ? qsTr("Envoi…")
                        : formulaire.f.depot.length > 0 ? qsTr("Lancer le projet") : qsTr("Lancer avec Hermes (sans dépôt)")
                    manualEnabled: formulaire.f.pret && formulaire.complet && !Projets.gesteEnCours
                    onTriggered: Projets.lancer(titreChamp.text, objectifChamp.text, profilChoix.currentValue, formulaire.reponses, effortChoix.currentIndex > 0 ? formulaire.f.efforts[effortChoix.currentIndex - 1] : "")
                }
                Item {
                    Layout.preferredHeight: Space.space6
                }
            }
        }
    }

    // --- Résumé d'une carte en entier -------------------------------------------------------------
    Connections {
        target: Projets
        function onCarteLueChange() {
            if (page.visible && Projets.vue === "detail" && (Projets.carteLue.carte || "").length > 0)
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
                Discret {
                    visible: Projets.carteLue.chargement === true
                    text: qsTr("Chargement…")
                }
                Alerte {
                    text: Projets.carteLue.erreur || ""
                }
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
                Discret {
                    visible: (Projets.carteLue.borne || "").length > 0
                    text: Projets.carteLue.borne || ""
                }
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
