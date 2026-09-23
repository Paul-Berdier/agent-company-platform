// Conversations et projets d'abord ; outils secondaires, données API uniquement.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Controls

Rectangle {
    id: navigation
    color: Colors.surfaceSidebar
    readonly property bool collapsed: width <= Space.layoutSidebarCollapsedWidth + 8
    readonly property bool contextLocked: Conversations.busy || Conversations.pendingSubmission

    component NavEntry: Item {
        id: entry
        property string label: ""
        property string iconName: "chat"
        property string explanation: ""
        property bool selected: false
        property bool actionable: true
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
                anchors.right: parent.right
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
        Accessible.name: entry.label
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
            label: qsTr("Agent Company"); iconName: "grid"
            selected: Navigation.currentRoute === "home"
            onActivated: Navigation.setCurrentRoute("home")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "shell-new-conversation"
            label: qsTr("Nouvelle conversation"); iconName: "plus"
            actionable: Shell.authenticated && !navigation.contextLocked
            explanation: navigation.contextLocked ? qsTr("Terminez ou résolvez l'envoi en cours.") : "Ctrl+N"
            onActivated: Commands.execute("conversation.new")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-conversations"
            label: qsTr("Conversations"); iconName: "chat"
            selected: Navigation.currentRoute === "conversations"
            onActivated: Navigation.setCurrentRoute("conversations")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-projects"
            label: qsTr("Projets"); iconName: "folder"
            selected: Navigation.currentRoute === "projects"
            explanation: "Ctrl+P"
            onActivated: Navigation.setCurrentRoute("projects")
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
                SectionLabel { width: parent.width; text: qsTr("PROJETS") }
                ListView {
                    id: projectList
                    width: parent.width
                    height: navigation.collapsed ? 0 : Math.min(count, 5) * Space.densityRowHeightComfortable
                    visible: !navigation.collapsed
                    interactive: false; clip: true; cacheBuffer: 0
                    model: Workspace.projects
                    delegate: NavEntry {
                        required property var item
                        width: projectList.width
                        height: Space.densityRowHeightComfortable
                        label: item.name || qsTr("Projet sans nom"); iconName: "folder"
                        selected: Workspace.projectId === item.id && Navigation.currentRoute !== "conversations"
                        actionable: !navigation.contextLocked
                        explanation: navigation.contextLocked ? qsTr("Résolvez d'abord l'envoi en cours.") : ""
                        onActivated: { Workspace.selectProject(item.id); Navigation.setCurrentRoute("projects") }
                    }
                }
                Text {
                    width: parent.width - Space.space5 * 2; x: Space.space5
                    visible: !navigation.collapsed && projectList.count === 0
                    text: Workspace.busy ? qsTr("Chargement…") : qsTr("Vos projets apparaîtront ici.")
                    textFormat: Text.PlainText; color: Colors.textMuted; wrapMode: Text.Wrap
                    font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize
                }
                NavEntry {
                    width: parent.width
                    visible: !navigation.collapsed; height: visible ? implicitHeight : 0
                    label: qsTr("Nouveau projet"); iconName: "plus"
                    actionable: Workspace.canCreateProject && !navigation.contextLocked
                    explanation: !Workspace.canCreateProject ? qsTr("Un droit de création dans l'espace est requis.") : "Ctrl+Shift+N"
                    onActivated: Commands.execute("project.new")
                }
                SectionLabel {
                    width: parent.width
                    text: Conversations.projectId.length === 0 ? qsTr("HISTORIQUE · GÉNÉRAL") : qsTr("HISTORIQUE · PROJET")
                }
                ListView {
                    id: historyList
                    objectName: "shell-conversation-history"
                    width: parent.width
                    height: navigation.collapsed ? 0 : Math.min(count, 6) * Space.densityRowHeightComfortable
                    visible: !navigation.collapsed
                    interactive: false; clip: true; cacheBuffer: 0
                    model: Conversations.conversations
                    delegate: NavEntry {
                        required property var item
                        width: historyList.width; height: Space.densityRowHeightComfortable
                        label: item.title || qsTr("Conversation")
                        iconName: item.status === "archived" ? "archive" : "chat"
                        selected: Navigation.currentRoute === "conversations" && Conversations.currentId === item.id
                        actionable: !navigation.contextLocked && Conversations.available
                        explanation: navigation.contextLocked ? qsTr("Résolvez d'abord l'envoi en cours.") : ""
                        onActivated: if (Conversations.openConversation(item.id)) Navigation.setCurrentRoute("conversations")
                    }
                }
                Text {
                    width: parent.width - Space.space5 * 2; x: Space.space5
                    visible: !navigation.collapsed && historyList.count === 0
                    text: Conversations.loading ? qsTr("Chargement…") : qsTr("Ouvrez Conversations pour retrouver vos fils.")
                    textFormat: Text.PlainText; color: Colors.textMuted; wrapMode: Text.Wrap
                    font.family: Type.metadata.family; font.pixelSize: Type.metadata.pixelSize
                }
                NavEntry {
                    width: parent.width
                    visible: !navigation.collapsed && historyList.count > 6; height: visible ? implicitHeight : 0
                    label: qsTr("Tout l'historique"); iconName: "archive"
                    onActivated: Navigation.setCurrentRoute("conversations")
                }
                SectionLabel { width: parent.width; text: qsTr("OUTILS DU PROJET") }
                Repeater {
                    model: [
                        {route: "missions", label: qsTr("Missions"), icon: "check"},
                        {route: "studio", label: qsTr("Studio en direct"), icon: "code"},
                        {route: "library", label: qsTr("Livrables"), icon: "archive"},
                        {route: "approvals", label: qsTr("Opérations"), icon: "activity"},
                        {route: "platform", label: qsTr("Agents et workers"), icon: "grid"},
                        {route: "extensions", label: qsTr("Extensions"), icon: "code"},
                        {route: "office", label: qsTr("Bureau de département"), icon: "grid"}
                    ]
                    delegate: NavEntry {
                        required property var modelData
                        width: parent.width
                        objectName: "navigation-" + modelData.route
                        label: modelData.label; iconName: modelData.icon
                        selected: Navigation.currentRoute === modelData.route
                        actionable: Navigation.isNavigable(modelData.route)
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
