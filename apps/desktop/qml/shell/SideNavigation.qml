// Pages de pilotage de Hermes, puis diagnostics et réglages. Une page non livrée reste
// visible, désactivée, avec sa raison : jamais un écran simulé.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls
import Acp.Components

Rectangle {
    id: navigation
    color: Colors.surfaceSidebar
    readonly property bool collapsed: width <= Space.layoutSidebarCollapsedWidth + 8

    component NavEntry: Item {
        id: entry
        property string label: ""
        property string iconName: "chat"
        property string explanation: ""
        property bool selected: false
        property bool actionable: true
        //! Compteur affiché à droite (questions ouvertes) ; 0 ou inconnu (négatif) : rien.
        property int compteur: 0
        property string compteurDescription: ""
        signal activated()
        implicitHeight: Math.max(Space.densityHitTargetMinimum, Space.densityRowHeightComfortable)
        activeFocusOnTab: visible
        Rectangle {
            anchors.fill: parent
            anchors.leftMargin: Space.space2
            anchors.rightMargin: Space.space2
            radius: Radius.radiusMd
            color: entry.selected ? Colors.accentMuted
                : hover.hovered && entry.actionable ? Colors.stateHover : "transparent"
            border.width: entry.activeFocus ? Space.layoutFocusRingWidth : 0
            border.color: Colors.borderFocus
            AcpIcon {
                id: icon
                anchors.left: parent.left
                anchors.leftMargin: Space.space4
                anchors.verticalCenter: parent.verticalCenter
                name: entry.iconName
                size: 17
                color: entry.actionable ? Colors.textSecondary : Colors.textMuted
            }
            Text {
                anchors.left: icon.right
                anchors.leftMargin: Space.space4
                anchors.right: compteurEntree.visible ? compteurEntree.left : parent.right
                anchors.rightMargin: Space.space3
                anchors.verticalCenter: parent.verticalCenter
                visible: !navigation.collapsed
                text: entry.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: entry.actionable ? Colors.textPrimary : Colors.textMuted
                font.family: Type.tableCell.family
                font.pixelSize: Type.tableCell.pixelSize
                font.weight: entry.selected ? Type.tableCellEmphasis.weight : Type.tableCell.weight
            }
            PastilleCompteur {
                id: compteurEntree
                anchors.right: parent.right
                anchors.rightMargin: Space.space3
                anchors.verticalCenter: parent.verticalCenter
                nombre: navigation.collapsed ? 0 : entry.compteur
                description: entry.compteurDescription
            }
            Rectangle {
                visible: entry.selected
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: 2; height: 14; radius: 1
                color: Colors.accentPrimary
            }
        }
        HoverHandler { id: hover; cursorShape: entry.actionable ? Qt.PointingHandCursor : Qt.ArrowCursor }
        TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: if (entry.actionable) entry.activated() }
        Keys.onReturnPressed: if (entry.actionable) entry.activated()
        Keys.onSpacePressed: if (entry.actionable) entry.activated()
        Accessible.role: Accessible.Button
        Accessible.name: entry.compteur > 0 && entry.compteurDescription.length > 0
            ? entry.label + " (" + entry.compteur + " " + entry.compteurDescription + ")" : entry.label
        Accessible.description: entry.explanation
        Accessible.focusable: true
        Accessible.onPressAction: if (entry.actionable) entry.activated()
        ToolTip {
            id: tip
            visible: hover.hovered && (navigation.collapsed || entry.explanation.length > 0)
            delay: 400
            text: entry.label + (entry.explanation ? "\n" + entry.explanation : "")
            contentItem: Text { text: tip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
        }
    }
    component SectionLabel: Text {
        visible: !navigation.collapsed
        // Une hauteur issue du jeton évite la boucle Text.elide/implicitHeight
        // lorsque la navigation se replie et que la largeur disponible change.
        height: visible ? Space.densityRowHeightRegular : 0
        leftPadding: Space.space5
        topPadding: Space.space3
        textFormat: Text.PlainText
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
        elide: Text.ElideRight
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Space.space5; anchors.bottomMargin: Space.space4
        spacing: Space.space2
        RowLayout {
            Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.bottomMargin: Space.space5
            AtelierMark { Layout.preferredWidth: 36; Layout.preferredHeight: 28 }
            ColumnLayout {
                visible: !navigation.collapsed; spacing: 1
                Text { text: "ACP"; color: Colors.textPrimary; font.family: Type.panelTitle.family; font.pixelSize: 18; font.weight: Font.DemiBold }
                Text { text: qsTr("Votre atelier de développement"); color: Colors.textMuted; font.family: Type.metadata.family; font.pixelSize: 11 }
            }
        }
        NavEntry {
            Layout.fillWidth: true; label: qsTr("Rechercher"); iconName: "search"
            explanation: qsTr("Commandes et navigation · Ctrl+K")
            onActivated: Commands.execute("palette.open")
        }
        NavEntry {
            objectName: "navigation-new-project"; Layout.fillWidth: true
            label: qsTr("Nouveau projet"); iconName: "plus"
            onActivated: { Projets.afficherNouveau(); Navigation.setCurrentRoute("projects"); }
        }
        Rectangle { Layout.fillWidth: true; Layout.margins: Space.space4; implicitHeight: 1; color: Colors.borderSubtle }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-home"
            label: qsTr("Mon atelier"); iconName: "grid"; selected: Navigation.currentRoute === "home"
            onActivated: Navigation.setCurrentRoute("home")
        }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-questions"
            label: qsTr("À traiter"); iconName: "activity"; selected: Navigation.currentRoute === "questions"
            compteur: Streams.aTraiter; compteurDescription: Streams.descriptionATraiter
            onActivated: Navigation.setCurrentRoute("questions")
        }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-chat"
            label: qsTr("Discussions"); iconName: "chat"; selected: Navigation.currentRoute === "chat"
            onActivated: Navigation.setCurrentRoute("chat")
        }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-tools"
            label: qsTr("Outils et compétences"); iconName: "command"
            selected: Navigation.currentRoute === "tools"
            onActivated: Navigation.setCurrentRoute("tools")
        }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-vault"
            label: qsTr("Coffre ACP"); iconName: "folder"
            selected: Navigation.currentRoute === "vault"
            onActivated: Navigation.setCurrentRoute("vault")
        }
        SectionLabel { Layout.fillWidth: true; text: qsTr("PROJETS") }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-projects"
            label: qsTr("Tous les projets"); iconName: "folder"
            selected: Navigation.currentRoute === "projects" && Projets.vue === "liste"
            onActivated: { Projets.afficherListe(); Navigation.setCurrentRoute("projects"); }
        }
        ListView {
            id: projectList
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            model: Projets.listeLue ? Projets.projets : Accueil.projetsEnCours; spacing: Space.space1
            ScrollBar.vertical: ScrollBar {}
            delegate: NavEntry {
                required property var item
                width: projectList.width; label: item.titre; iconName: "folder"; explanation: item.etatLibelle
                selected: Navigation.currentRoute === "projects" && Projets.projetOuvert === item.id && Projets.vue === "detail"
                onActivated: { Projets.ouvrirProjet(item.id); Navigation.setCurrentRoute("projects"); }
            }
            Text {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Space.space5
                visible: !navigation.collapsed && projectList.count === 0
                text: Projets.listeLue ? qsTr("Vos projets apparaîtront ici.") : qsTr("Ouvrez vos projets pour les retrouver ici.")
                color: Colors.textMuted; font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize; wrapMode: Text.WordWrap
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.rightMargin: Space.space5; implicitHeight: 1; color: Colors.borderSubtle }
        NavEntry {
            Layout.fillWidth: true; objectName: "navigation-settings"
            label: qsTr("Réglages"); iconName: "settings"
            selected: ["settings", "station", "quotas", "routing", "backup", "diagnostics"].indexOf(Navigation.currentRoute) >= 0
            onActivated: Navigation.setCurrentRoute("settings")
        }
        Text {
            Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.rightMargin: Space.space4
            visible: !navigation.collapsed
            text: Colors.variantLabel
            color: Colors.textMuted; font.family: Type.metadata.family; font.pixelSize: 11; elide: Text.ElideRight
        }
    }
}
