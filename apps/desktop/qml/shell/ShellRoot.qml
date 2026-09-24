// Cadre adaptatif : navigation, conversation/travail, détails de la sélection.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime

Item {
    id: shell
    readonly property bool narrow: width < Space.breakpointRegular
    property bool expandedInNarrow: false
    readonly property bool navigationCompact: Shell.sidebarCollapsed || (narrow && !expandedInNarrow)
    readonly property bool missionContext: Navigation.currentRoute === "missions" || Navigation.currentRoute === "studio"
    readonly property string inspectionKind: Navigation.currentRoute === "conversations" && Conversations.currentId.length > 0
        ? "conversation" : Navigation.currentRoute === "projects" && Workspace.projectId.length > 0
        ? "project" : missionContext && Missions.selectedMissionId.length > 0
        ? "mission" : Navigation.currentRoute === "library" && Artifacts.selected.id ? "artifact" : ""
    readonly property bool inspectorAvailable: inspectionKind.length > 0
    readonly property string inspectionTitle: inspectionKind === "conversation" ? qsTr("Conversation")
        : inspectionKind === "project" ? qsTr("Projet")
        : inspectionKind === "mission" ? qsTr("Mission et tentative")
        : qsTr("Livrable")
    readonly property var inspectionFields: {
        switch (inspectionKind) {
        case "conversation":
            return [
                {label: qsTr("Titre"), value: Conversations.currentTitle},
                {label: qsTr("Contexte"), value: Conversations.projectId.length === 0 ? qsTr("Général")
                    : Conversations.projectId === Workspace.projectId ? Workspace.projectName : Conversations.projectId},
                {label: qsTr("Identifiant du fil"), value: Conversations.currentId},
                {label: qsTr("État"), value: Conversations.archived ? qsTr("Archivée") : qsTr("Active")},
                {label: qsTr("Réponse en cours"), value: Conversations.polling ? qsTr("Oui") : qsTr("Non")}
            ];
        case "project":
            return [
                {label: qsTr("Nom"), value: Workspace.projectName},
                {label: qsTr("Description"), value: Workspace.project.description},
                {label: qsTr("Identifiant"), value: Workspace.projectId},
                {label: qsTr("Espace"), value: Workspace.project.workspace_id},
                {label: qsTr("État"), value: Workspace.project.status}
            ];
        case "mission":
            return [
                {label: qsTr("Titre"), value: Missions.mission.title},
                {label: qsTr("Identifiant de mission"), value: Missions.selectedMissionId},
                {label: qsTr("État de mission"), value: Missions.mission.status},
                {label: qsTr("Tentative"), value: Missions.run.attempt_number},
                {label: qsTr("Identifiant de tentative"), value: Missions.selectedRunId},
                {label: qsTr("État de tentative"), value: Missions.run.status},
                {label: qsTr("Validation technique"), value: Missions.run.technical_validation ? Missions.run.technical_validation.status : ""},
                {label: qsTr("Acceptation"), value: Missions.run.user_acceptance ? Missions.run.user_acceptance.status : ""},
                {label: qsTr("Flux"), value: Missions.streamStatus}
            ];
        case "artifact":
            return [
                {label: qsTr("Nom"), value: Artifacts.selected.original_name},
                {label: qsTr("Identifiant"), value: Artifacts.selected.id},
                {label: qsTr("Type"), value: Artifacts.selected.content_type},
                {label: qsTr("Taille (octets)"), value: Artifacts.selected.size_bytes},
                {label: qsTr("SHA-256"), value: Artifacts.selected.checksum},
                {label: qsTr("Contenu"), value: Artifacts.selected.has_content ? qsTr("Disponible") : qsTr("Non disponible")}
            ];
        default: return [];
        }
    }

    function toggleNavigation() {
        if (navigationCompact) {
            Shell.sidebarCollapsed = false
            expandedInNarrow = narrow
        } else {
            Shell.sidebarCollapsed = true
            expandedInNarrow = false
        }
    }
    function applyNavigationWidth() {
        sidebar.SplitView.preferredWidth = navigationCompact ? Space.layoutSidebarCollapsedWidth
            : Shell.sidebarWidth || Space.layoutSidebarWidth
    }
    onNarrowChanged: expandedInNarrow = false
    onNavigationCompactChanged: applyNavigationWidth()
    onInspectorAvailableChanged: if (!inspectorAvailable) Shell.inspectorVisible = false
    Component.onCompleted: applyNavigationWidth()
    Connections {
        target: Shell
        function onPanelWidthsChanged() { if (!split.resizing) shell.applyNavigationWidth() }
    }

    Shortcut { sequence: "Ctrl+N"; enabled: !Shell.commandPaletteOpen; onActivated: Commands.execute("conversation.new") }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: !Shell.commandPaletteOpen; onActivated: Commands.execute("project.new") }
    Shortcut { sequence: "Ctrl+P"; enabled: !Shell.commandPaletteOpen; onActivated: Commands.execute("navigation.projects") }
    Shortcut { sequence: "Alt+Left"; enabled: !Shell.commandPaletteOpen; onActivated: Commands.execute("navigation.back") }
    Shortcut { sequence: "Alt+Right"; enabled: !Shell.commandPaletteOpen; onActivated: Commands.execute("navigation.forward") }
    Shortcut { sequence: "Escape"; enabled: Shell.inspectorVisible && !Shell.commandPaletteOpen; onActivated: Shell.inspectorVisible = false }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        TopBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutTopBarHeight
            inspectorAvailable: shell.inspectorAvailable
            navigationCompact: shell.navigationCompact
            onToggleNavigation: shell.toggleNavigation()
        }
        SplitView {
            id: split
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            onResizingChanged: {
                if (!resizing) {
                    if (!shell.navigationCompact) Shell.sidebarWidth = Math.round(sidebar.width)
                    if (details.visible) Shell.inspectorWidth = Math.round(details.width)
                }
            }
            handle: Rectangle {
                implicitWidth: Space.layoutPaneGap + 2
                color: SplitHandle.pressed || SplitHandle.hovered ? Colors.borderInteractive : Colors.borderSubtle
            }
            SideNavigation {
                id: sidebar
                objectName: "shell-sidebar"
                SplitView.preferredWidth: Space.layoutSidebarWidth
                SplitView.minimumWidth: shell.navigationCompact ? Space.layoutSidebarCollapsedWidth : 200
                SplitView.maximumWidth: shell.navigationCompact ? Space.layoutSidebarCollapsedWidth : 360
            }
            WorkArea {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 320
            }
            InspectorPanel {
                id: details
                objectName: "shell-inspector"
                visible: shell.inspectorAvailable && Shell.inspectorVisible && !shell.narrow
                heading: shell.inspectionTitle
                fields: shell.inspectionFields
                actionRoute: shell.inspectionKind === "project" ? "missions" : ""
                actionLabel: qsTr("Ouvrir les missions")
                SplitView.preferredWidth: Shell.inspectorWidth || Space.layoutInspectorWidthDefault
                SplitView.minimumWidth: Space.layoutInspectorWidthMin
                SplitView.maximumWidth: 600
            }
        }
        StatusBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutStatusBarHeight
        }
    }
    Rectangle {
        visible: shell.inspectorAvailable && Shell.inspectorVisible && shell.narrow
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: Space.layoutTopBarHeight
        anchors.bottomMargin: Space.layoutStatusBarHeight
        width: Math.min(Shell.inspectorWidth || Space.layoutInspectorWidthDefault, shell.width * 0.72)
        color: Colors.surfacePanel
        border.width: Space.layoutBorderWidth
        border.color: Colors.borderDefault
        InspectorPanel {
            anchors.fill: parent
            anchors.margins: 1
            heading: shell.inspectionTitle
            fields: shell.inspectionFields
            actionRoute: shell.inspectionKind === "project" ? "missions" : ""
            actionLabel: qsTr("Ouvrir les missions")
        }
    }
}
