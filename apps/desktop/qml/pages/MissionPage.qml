// Mission ouverte (D166, D167) : en-tête de la mission, puis trois vues sur les MÊMES données
// servies par le greffon (GET /v1/projets/{id}) :
//
// - Fil : objectif, exploration, décisions attendues, résultat, puis le journal, du plus
//   récent au plus ancien ;
// - Plan : les tours et leurs tâches, avec l'exécutant, le modèle et la source du routage ;
// - Pilotage : la page Projets complète (gestes de la mission, cartes, revues, journal).
//
// Une seule instance de la page Projets vit ici (onglet Pilotage, ou plein écran pour la liste
// et le formulaire) : c'est elle qui dit au modèle de vue qu'il est affiché (`pageVisible` est
// un booléen, une seconde vue l'éteindrait en disparaissant).
//
// La saisie du bas prépare une NOUVELLE mission dans le même projet (même dépôt) ; elle ne
// modifie jamais la mission ouverte. Son brouillon vit en mémoire (oubli local).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Item {
    id: page

    readonly property bool detail: Projets.vue === "detail"
    readonly property var d: Projets.detail
    readonly property string contexteBrouillon: "mission-suivante:" + (Espace.mission.depot || "")
    property int onglet: 0

    component Section: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        color: Colors.textPrimary
        font.family: Type.panelTitle.family
        font.pixelSize: Type.panelTitle.pixelSize
        font.weight: Type.panelTitle.weight
    }
    component Meta: Text {
        textFormat: Text.PlainText
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // --- En-tête de la mission ----------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: entete.implicitHeight + Space.space5 * 2
            visible: page.detail
            color: Colors.surfaceCanvas
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: Space.layoutBorderWidth; color: Colors.borderSubtle }
            RowLayout {
                id: entete
                anchors.fill: parent
                anchors.leftMargin: Space.space6
                anchors.rightMargin: Space.space6
                spacing: Space.space5
                PictoProjet {
                    readonly property var p: Espace.pictogramme(Espace.missionSelectionnee)
                    motif: p.motif
                    teinte: p.teinte
                    echelle: 3
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Space.space1
                    Text {
                        objectName: "mission-titre"
                        Layout.fillWidth: true
                        text: Espace.mission.titre || (page.d.titre || "")
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        color: Colors.textPrimary
                        font.family: Type.pageTitle.family
                        font.pixelSize: Type.pageTitle.pixelSize
                        font.weight: Type.pageTitle.weight
                    }
                    RowLayout {
                        spacing: Space.space4
                        Meta { text: qsTr("Projet : %1").arg(Espace.mission.depot || qsTr("Inconnu")); font.family: Type.identifier.family }
                        Meta { text: "·"; Accessible.ignored: true }
                        Meta {
                            objectName: "mission-agents"
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            // L'état de l'exécutant et de la file vit dans la barre d'état et l'onglet Services du volet.
                            text: (Espace.mission.agents || 0) > 1
                                ? qsTr("%1 tâches, coordonnées par Hermes").arg(Espace.mission.agents - 1)
                                : qsTr("Coordonnée par Hermes")
                        }
                    }
                }
                StatusChip {
                    objectName: "mission-etat"
                    statusKey: Espace.mission.etatCle || "unknown"
                    label: Espace.mission.etatLibelle || ""
                }
            }
        }

        // --- Onglets ------------------------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Space.space6
            Layout.rightMargin: Space.space6
            Layout.topMargin: Space.space3
            Layout.bottomMargin: Space.space3
            visible: page.detail
            spacing: Space.space2
            Repeater {
                model: [qsTr("Fil"), qsTr("Plan"), qsTr("Pilotage")]
                delegate: AcpButton {
                    required property string modelData
                    required property int index
                    objectName: "mission-onglet-" + index
                    label: modelData
                    primary: page.onglet === index
                    onTriggered: page.onglet = index
                    Accessible.role: Accessible.PageTab
                }
            }
            Item { Layout.fillWidth: true }
            Meta { text: Projets.lectureDetail }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: page.detail ? page.onglet : 2

            // --- Fil ------------------------------------------------------------------------
            ScrollView {
                id: fil
                objectName: "mission-fil"
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: Math.min(fil.availableWidth - Space.space6 * 2, Type.measureProse + 240)
                    x: Space.space6
                    spacing: Space.space5
                    Item { Layout.preferredHeight: Space.space2 }

                    Section { text: qsTr("Objectif") }
                    BlocTexte {
                        Layout.fillWidth: true
                        texte: page.d.objectif || ""
                        vide: Projets.detailLu ? qsTr("Objectif non servi par ce serveur.") : qsTr("Lecture de la mission…")
                    }

                    Section { visible: (page.d.exploration || "").length > 0; text: qsTr("Exploration du dépôt") }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: (page.d.exploration || "").length > 0
                        texte: page.d.exploration || ""
                    }

                    Section { visible: Projets.questionsDuProjet.count > 0; text: qsTr("Décisions attendues") }
                    Repeater {
                        model: Projets.questionsDuProjet
                        delegate: Carte {
                            required property var item
                            Layout.fillWidth: true
                            titre: item.texte || ""
                            cle: item.etatCle || "approvalRequired"
                            libelleEtat: item.etatLibelle || qsTr("Votre réponse est attendue")
                            AcpButton {
                                label: qsTr("Répondre dans « À traiter »")
                                onTriggered: Navigation.setCurrentRoute("questions")
                            }
                        }
                    }

                    Section { visible: (page.d.resultat || "").length > 0; text: qsTr("Résultat de la mission") }
                    BlocTexte {
                        Layout.fillWidth: true
                        visible: (page.d.resultat || "").length > 0
                        libelle: page.d.resultatTronque ? qsTr("Synthèse du tour %1 (tronquée)").arg(page.d.resultatTour)
                                                        : qsTr("Synthèse du tour %1").arg(page.d.resultatTour)
                        texte: page.d.resultat || ""
                    }

                    Section { text: qsTr("Journal") }
                    Repeater {
                        model: Projets.journal
                        delegate: RowLayout {
                            required property var item
                            Layout.fillWidth: true
                            spacing: Space.space4
                            Rectangle {
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: Space.space3
                                width: Space.layoutPixelUnit * 2; height: width
                                color: Colors.accentSecondary
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: Space.space1
                                Text {
                                    Layout.fillWidth: true
                                    text: (item.action || "") + ((item.cible || "").length > 0 ? " · " + item.cible : "")
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WordWrap
                                    color: Colors.textPrimary
                                    font.family: Type.tableCell.family
                                    font.pixelSize: Type.tableCell.pixelSize
                                }
                                Meta {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    text: [item.quand, item.acteur, item.detail].filter(x => (x || "").length > 0).join(" · ")
                                }
                            }
                        }
                    }
                    Meta {
                        visible: Projets.journal.count === 0
                        text: Projets.detailLu ? qsTr("Aucune ligne de journal servie pour cette mission.") : qsTr("Lecture de la mission…")
                    }
                    Item { Layout.preferredHeight: Space.space6 }
                }
            }

            // --- Plan -----------------------------------------------------------------------
            ScrollView {
                id: plan
                objectName: "mission-plan"
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: plan.availableWidth - Space.space6 * 2
                    x: Space.space6
                    spacing: Space.space3
                    Item { Layout.preferredHeight: Space.space2 }
                    Meta {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: qsTr("Tours et tâches de la mission, dans l'ordre du greffon. Une dépendance entre tâches n'est "
                                   + "pas une relation entre agents : le panneau des agents montre qui relit qui.")
                    }
                    Repeater {
                        model: Espace.agents
                        delegate: Rectangle {
                            id: tache
                            required property var item
                            visible: (item.niveau || 0) > 0
                            Layout.fillWidth: true
                            Layout.leftMargin: (item.niveau || 0) > 1 ? Space.space8 : 0
                            implicitHeight: visible ? ligneTache.implicitHeight + Space.space4 * 2 : 0
                            color: Espace.agentSelectionne === item.cle ? Colors.stateSelected : Colors.surfacePanel
                            border.width: Space.layoutBorderWidth
                            border.color: Colors.borderSubtle
                            RowLayout {
                                id: ligneTache
                                anchors.fill: parent
                                anchors.margins: Space.space4
                                spacing: Space.space4
                                Meta { text: qsTr("Tour %1").arg(tache.item.tour); font.family: Type.identifier.family }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Space.space1
                                    Text {
                                        Layout.fillWidth: true
                                        text: tache.item.titre || ""
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        color: Colors.textPrimary
                                        font.family: Type.tableCell.family
                                        font.pixelSize: Type.tableCell.pixelSize
                                    }
                                    Meta {
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                        text: [tache.item.roleLibelle, tache.item.voieLibelle, tache.item.modele, tache.item.sourceRoutage]
                                            .filter(x => (x || "").length > 0).join(" · ")
                                    }
                                }
                                StatusChip { statusKey: tache.item.statusKey || "unknown"; label: tache.item.etatLibelle || "" }
                            }
                            TapHandler { onTapped: Espace.agentSelectionne = tache.item.cle }
                        }
                    }
                    Meta {
                        visible: Espace.agents.count <= 1
                        text: Projets.detailLu ? qsTr("Aucune tâche servie pour cette mission.") : qsTr("Lecture de la mission…")
                    }
                    Item { Layout.preferredHeight: Space.space6 }
                }
            }

            // --- Pilotage (et liste ou formulaire quand aucune mission n'est ouverte) ----------
            ProjectsPage {
                objectName: "mission-pilotage"
            }
        }

        // --- Saisie persistante : nouvelle mission dans le même projet -----------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: saisie.implicitHeight + Space.space4 * 2
            visible: page.detail
            color: Colors.surfaceCanvas
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: Space.layoutBorderWidth; color: Colors.borderSubtle }
            RowLayout {
                id: saisie
                anchors.fill: parent
                anchors.margins: Space.space4
                anchors.leftMargin: Space.space6
                anchors.rightMargin: Space.space6
                spacing: Space.space4
                FondPixel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(Math.max(Space.layoutComposerHeightMin, champ.implicitHeight + Space.space4),
                                                     Space.layoutComposerHeightMax)
                    couleur: Colors.surfacePanelRaised
                    bordure: champ.activeFocus ? Colors.borderFocus : Colors.borderInteractive
                    epaisseur: Space.layoutBorderWidth
                    rayon: Radius.radiusMd
                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: Space.space3
                        clip: true
                        TextArea {
                            id: champ
                            objectName: "mission-saisie"
                            wrapMode: TextEdit.Wrap
                            textFormat: TextEdit.PlainText
                            placeholderText: qsTr("Prochaine mission dans « %1 » : décrivez le résultat attendu…").arg(Espace.mission.depot || "")
                            placeholderTextColor: Colors.textMuted
                            color: Colors.textPrimary
                            font.family: Type.prose.family
                            font.pixelSize: Type.prose.pixelSize
                            background: null
                            Accessible.name: qsTr("Prochaine mission dans ce projet")
                            Component.onCompleted: text = Espace.brouillon(page.contexteBrouillon)
                            onTextChanged: Espace.noterBrouillon(page.contexteBrouillon, text)
                            Keys.onPressed: function(evenement) {
                                if ((evenement.key === Qt.Key_Return || evenement.key === Qt.Key_Enter)
                                        && (evenement.modifiers & Qt.ControlModifier)) {
                                    page.preparer();
                                    evenement.accepted = true;
                                }
                            }
                        }
                    }
                }
                ColumnLayout {
                    spacing: Space.space2
                    AcpButton {
                        objectName: "mission-preparer"
                        primary: true
                        label: qsTr("Préparer la mission")
                        shortcutHint: "Ctrl+Entrée"
                        manualEnabled: champ.text.trim().length > 0 && Session.connectee
                        onTriggered: page.preparer()
                    }
                    Meta { text: qsTr("Auto : routage du greffon") }
                }
            }
        }
    }

    // Le formulaire complet s'ouvre, objectif repris du brouillon et dépôt présélectionné :
    // le propriétaire relit les options (Auto ou manuel) avant tout envoi.
    function preparer() {
        const objectif = champ.text.trim();
        if (objectif.length === 0)
            return;
        Espace.noterBrouillon("nouvelle-mission:objectif", objectif);
        Espace.noterBrouillon("nouvelle-mission:titre", objectif.split("\n")[0].slice(0, 120));
        champ.text = "";
        Espace.nouvelleMission(Espace.mission.depot === qsTr("Sans dépôt") ? "" : (Espace.mission.depot || ""));
    }
}
