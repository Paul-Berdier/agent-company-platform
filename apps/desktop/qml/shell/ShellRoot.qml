// Espace de travail (D167) : barre des projets à gauche, mission au centre avec son volet bas,
// panneau des agents à droite. Volets redimensionnables, largeurs mémorisées sans secret ;
// dans une fenêtre étroite, les panneaux se replient (jamais un texte compressé illisible).
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime

Item {
    id: shell
    readonly property bool narrow: width < Space.breakpointRegular
    readonly property bool tresEtroit: width < Space.breakpointNarrow + 120
    property bool expandedInNarrow: false
    readonly property bool navigationCompact: Shell.sidebarCollapsed || (tresEtroit && !expandedInNarrow)
    //! Le panneau des agents et le volet bas n'ont de sens que pour une mission ouverte.
    readonly property bool missionOuverte: Navigation.currentRoute === "projects" && Espace.missionSelectionnee.length > 0
        && Projets.vue === "detail"
    readonly property bool agentsVisibles: Shell.agentsPanelVisible && shell.missionOuverte
    readonly property bool agentsEnSurcouche: shell.agentsVisibles && shell.narrow
    readonly property bool voletVisible: Shell.bottomDrawerVisible && shell.missionOuverte

    function toggleNavigation() {
        if (navigationCompact) {
            Shell.sidebarCollapsed = false
            expandedInNarrow = tresEtroit
        } else {
            Shell.sidebarCollapsed = true
            expandedInNarrow = false
        }
    }
    function applyNavigationWidth() {
        sidebar.SplitView.preferredWidth = navigationCompact ? Space.layoutSidebarCollapsedWidth
            : Shell.sidebarWidth || Space.layoutSidebarWidth
    }
    function applyPanels() {
        agents.SplitView.preferredWidth = Shell.inspectorWidth || Space.layoutAgentsPanelWidthDefault
        volet.SplitView.preferredHeight = Shell.bottomDrawerHeight || Space.layoutBottomDrawerHeightDefault
    }
    onTresEtroitChanged: expandedInNarrow = false
    onNavigationCompactChanged: applyNavigationWidth()
    Component.onCompleted: { applyNavigationWidth(); applyPanels() }
    Connections {
        target: Shell
        function onPanelWidthsChanged() {
            if (!split.resizing) shell.applyNavigationWidth()
            if (!split.resizing && !centre.resizing) shell.applyPanels()
        }
        function onLayoutChanged() { if (!centre.resizing) shell.applyPanels() }
        function onSidebarCollapsedChanged() { shell.applyNavigationWidth() }
    }
    // Alt+←/→ sont déclarés au registre (App.qml) : un second Shortcut identique les rendrait ambigus.
    Shortcut {
        sequence: "Escape"
        enabled: shell.agentsEnSurcouche && !Shell.commandPaletteOpen
        onActivated: Shell.agentsPanelVisible = false
    }

    component Poignee: Rectangle {
        implicitWidth: Space.layoutPaneGap + 2
        implicitHeight: Space.layoutPaneGap + 2
        color: SplitHandle.pressed || SplitHandle.hovered ? Colors.borderInteractive : Colors.borderSubtle
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        TopBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutTopBarHeight
            navigationCompact: shell.navigationCompact
            missionOuverte: shell.missionOuverte
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
                    if (agents.visible) Shell.inspectorWidth = Math.round(agents.width)
                }
            }
            handle: Poignee {}
            SideNavigation {
                id: sidebar
                objectName: "shell-sidebar"
                SplitView.preferredWidth: Space.layoutSidebarWidth
                SplitView.minimumWidth: shell.navigationCompact ? Space.layoutSidebarCollapsedWidth : Space.layoutSidebarWidthMin
                SplitView.maximumWidth: shell.navigationCompact ? Space.layoutSidebarCollapsedWidth : Space.layoutSidebarWidthMax
            }
            SplitView {
                id: centre
                SplitView.fillWidth: true
                SplitView.minimumWidth: Space.layoutCenterMinWidth
                orientation: Qt.Vertical
                onResizingChanged: if (!resizing && volet.visible) Shell.bottomDrawerHeight = Math.round(volet.height)
                handle: Poignee {}
                WorkArea {
                    SplitView.fillHeight: true
                    SplitView.minimumHeight: 240
                }
                BottomDrawer {
                    id: volet
                    objectName: "shell-volet"
                    visible: shell.voletVisible
                    SplitView.preferredHeight: Space.layoutBottomDrawerHeightDefault
                    SplitView.minimumHeight: Space.layoutBottomDrawerHeightMin
                    SplitView.maximumHeight: Space.layoutBottomDrawerHeightMax
                }
            }
            AgentsPanel {
                id: agents
                objectName: "shell-agents"
                visible: shell.agentsVisibles && !shell.narrow
                SplitView.preferredWidth: Space.layoutAgentsPanelWidthDefault
                SplitView.minimumWidth: Space.layoutAgentsPanelWidthMin
                SplitView.maximumWidth: Space.layoutAgentsPanelWidthMax
            }
        }
        StatusBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutStatusBarHeight
        }
    }

    // Fenêtre étroite : le panneau des agents passe en surcouche à droite, refermable par Échap.
    Rectangle {
        visible: shell.agentsEnSurcouche
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: Space.layoutTopBarHeight
        anchors.bottomMargin: Space.layoutStatusBarHeight
        width: Math.min(Shell.inspectorWidth || Space.layoutAgentsPanelWidthDefault, shell.width * 0.72)
        color: Colors.surfacePanel
        border.width: Space.layoutBorderWidth
        border.color: Colors.borderDefault
        AgentsPanel {
            anchors.fill: parent
            anchors.margins: Space.layoutBorderWidth
        }
    }
}
