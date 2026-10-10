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
        anchors.topMargin: Space.space3
        anchors.bottomMargin: Space.space3
        spacing: Space.space1
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-home"
            label: qsTr("Accueil"); iconName: "grid"
            selected: Navigation.currentRoute === "home"
            onActivated: Navigation.setCurrentRoute("home")
        }
        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: scroll.availableWidth
                spacing: Space.space1
                SectionLabel { width: parent.width; text: qsTr("PILOTAGE") }
                Repeater {
                    model: [
                        {route: "projects", label: qsTr("Projets"), icon: "folder"},
                        {route: "questions", label: qsTr("Questions"), icon: "chat"},
                        {route: "chat", label: qsTr("Discussion"), icon: "chat"},
                        {route: "station", label: qsTr("Poste"), icon: "grid"},
                        {route: "quotas", label: qsTr("Quotas"), icon: "gauge"},
                        {route: "routing", label: qsTr("Routage"), icon: "code"},
                        {route: "backup", label: qsTr("Sauvegarde"), icon: "archive"},
                        {route: "office", label: qsTr("Bureau de département"), icon: "grid"}
                    ]
                    delegate: NavEntry {
                        required property var modelData
                        width: parent.width
                        objectName: "navigation-" + modelData.route
                        label: modelData.label; iconName: modelData.icon
                        selected: Navigation.currentRoute === modelData.route
                        actionable: Navigation.isNavigable(modelData.route)
                        compteur: modelData.route === "questions" ? Streams.aTraiter : 0
                        // Le nom accessible dit ce que le total compte : discussions comprises quand elles sont lues.
                        compteurDescription: modelData.route === "questions" ? Streams.descriptionATraiter : ""
                        explanation: actionable ? "" : Navigation.detailFor(modelData.route)
                        onActivated: Navigation.setCurrentRoute(modelData.route)
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.rightMargin: Space.space5
            height: 1; color: Colors.borderSubtle
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-diagnostics"
            label: qsTr("Diagnostics"); iconName: "activity"
            selected: Navigation.currentRoute === "diagnostics"
            onActivated: Navigation.setCurrentRoute("diagnostics")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-settings"
            label: qsTr("Réglages"); iconName: "settings"
            selected: Navigation.currentRoute === "settings"
            onActivated: Navigation.setCurrentRoute("settings")
        }
    }
}
