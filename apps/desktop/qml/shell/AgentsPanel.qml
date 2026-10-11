// Panneau des agents de la mission ouverte (D166) : Hermes coordonne, chaque tâche (carte
// kanban) est exécutée par un agent, une relecture est rangée sous la tâche qu'elle relit.
//
// Ce que le serveur ne remonte pas n'est pas montré : sessions des CLI, outils en cours et
// sous-agents natifs sont dits « non observés ». Un portrait ne s'anime « au travail » que
// sur l'état « Exécute » servi par le kanban.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Rectangle {
    id: panneau
    color: Colors.surfacePanel

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space5
        spacing: Space.space4

        RowLayout {
            Layout.fillWidth: true
            spacing: Space.space3
            TextePixel { text: qsTr("AGENTS"); couleur: "attenue"; echelle: 1 }
            Item { Layout.fillWidth: true }
            Text {
                text: Espace.agents.count > 1 ? qsTr("%1 tâches").arg(Espace.agents.count - 1) : ""
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
            AcpButton {
                objectName: "agents-masquer"
                label: ""
                iconName: "close"
                commandId: "shell.toggleAgents"
                Accessible.name: qsTr("Masquer le panneau des agents · Ctrl+Alt+B")
            }
        }

        ListView {
            id: arbre
            objectName: "agents-arbre"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: panneau.height * 0.5
            clip: true
            model: Espace.agents
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Item {
                id: ligneAgent
                required property var item
                readonly property bool choisi: Espace.agentSelectionne === ligneAgent.item.cle
                width: arbre.width
                implicitHeight: Math.max(Space.densityHitTargetMinimum, contenu.implicitHeight + Space.space3 * 2)
                activeFocusOnTab: true
                FondPixel {
                    anchors.fill: parent
                    couleur: ligneAgent.choisi ? Colors.accentMuted : survolAgent.hovered ? Colors.stateHover : "transparent"
                    bordure: Colors.borderFocus
                    epaisseur: ligneAgent.activeFocus ? Space.layoutFocusRingWidth : 0
                    rayon: Radius.radiusSm
                }
                // Trait de rattachement : la profondeur se lit sans la couleur.
                Rectangle {
                    visible: (ligneAgent.item.niveau || 0) > 0
                    x: Space.space4 + ((ligneAgent.item.niveau || 0) - 1) * Space.space7 + Space.space5
                    width: Space.layoutBorderWidth
                    height: parent.height
                    color: Colors.borderDefault
                }
                RowLayout {
                    id: contenu
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Space.space3 + (ligneAgent.item.niveau || 0) * Space.space7
                    anchors.rightMargin: Space.space3
                    spacing: Space.space4
                    PortraitAgent {
                        role: ligneAgent.item.portrait || "inconnu"
                        etat: ligneAgent.item.sprite || "repos"
                        echelle: (ligneAgent.item.niveau || 0) === 0 ? 3 : 2
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Space.space1
                        Text {
                            Layout.fillWidth: true
                            text: ligneAgent.item.titre || ""
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: Colors.textPrimary
                            font.family: Type.tableCell.family
                            font.pixelSize: Type.tableCell.pixelSize
                            font.weight: Type.tableCellEmphasis.weight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: [ligneAgent.item.roleLibelle, ligneAgent.item.voieLibelle].filter(x => (x || "").length > 0).join(" · ")
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: Colors.textMuted
                            font.family: Type.metadata.family
                            font.pixelSize: Type.metadata.pixelSize
                        }
                        // L'état sous le titre : le titre garde toute la largeur du panneau.
                        StatusChip {
                            Layout.maximumWidth: parent.width
                            statusKey: ligneAgent.item.statusKey || "unknown"
                            label: ligneAgent.item.etatLibelle || ""
                        }
                    }
                }
                HoverHandler { id: survolAgent; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: Espace.agentSelectionne = ligneAgent.item.cle }
                Keys.onReturnPressed: Espace.agentSelectionne = ligneAgent.item.cle
                Keys.onSpacePressed: Espace.agentSelectionne = ligneAgent.item.cle
                Accessible.role: Accessible.TreeItem
                Accessible.name: (ligneAgent.item.titre || "") + ", " + (ligneAgent.item.etatLibelle || "")
                Accessible.focusable: true
                Accessible.onPressAction: Espace.agentSelectionne = ligneAgent.item.cle
            }
            Text {
                anchors.fill: parent
                visible: arbre.count === 0
                text: Projets.detailLu ? qsTr("Aucune tâche servie pour cette mission.") : qsTr("Lecture de la mission…")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }

        Rectangle { Layout.fillWidth: true; height: Space.layoutBorderWidth; color: Colors.borderSubtle }

        // Détail de la sélection : rien n'est inventé ; un champ absent du serveur se dit.
        ScrollView {
            id: detail
            objectName: "agents-detail"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            readonly property var a: Espace.agent
            readonly property bool choisi: (detail.a.cle || "").length > 0
            ColumnLayout {
                width: detail.availableWidth
                spacing: Space.space3
                Text {
                    Layout.fillWidth: true
                    visible: !detail.choisi
                    text: qsTr("Choisissez un agent pour voir son rôle, son modèle, la source du choix de routage et son dernier résumé.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textMuted
                    font.family: Type.metadata.family
                    font.pixelSize: Type.metadata.pixelSize
                }
                Text {
                    Layout.fillWidth: true
                    visible: detail.choisi
                    text: detail.a.titre || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textPrimary
                    font.family: Type.panelTitle.family
                    font.pixelSize: Type.panelTitle.pixelSize
                    font.weight: Type.panelTitle.weight
                }
                Repeater {
                    model: detail.choisi ? [
                        { "label": qsTr("Rôle"), "valeur": detail.a.roleLibelle },
                        { "label": qsTr("État"), "valeur": detail.a.etatLibelle },
                        { "label": qsTr("Exécutant"), "valeur": detail.a.voieLibelle },
                        { "label": qsTr("Modèle demandé"), "valeur": detail.a.modele },
                        { "label": qsTr("Modèle servi"), "valeur": detail.a.modeleServi },
                        { "label": qsTr("Effort"), "valeur": detail.a.effort },
                        { "label": qsTr("Choix du routage"), "valeur": detail.a.sourceRoutage },
                        { "label": qsTr("Mention"), "valeur": detail.a.mention },
                        { "label": qsTr("Tour"), "valeur": detail.a.tour },
                        { "label": qsTr("Carte"), "valeur": detail.a.carte }
                    ].filter(l => (l.valeur || "").length > 0) : []
                    delegate: KeyValueRow {
                        required property var modelData
                        Layout.fillWidth: true
                        label: modelData.label
                        value: modelData.valeur
                        aLaLigne: true
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: detail.choisi
                    text: qsTr("Session de la CLI, outils en cours et sous-agents : non remontés par l'exécutant (non observés).")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: Colors.textMuted
                    font.family: Type.metadata.family
                    font.pixelSize: Type.metadata.pixelSize
                }
                BlocTexte {
                    Layout.fillWidth: true
                    visible: detail.choisi && (detail.a.resume || "").length > 0
                    texte: detail.a.resume || ""
                }
            }
        }
    }
}
