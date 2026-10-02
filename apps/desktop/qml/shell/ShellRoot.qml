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
    // Aucune page livrée n'a encore d'objet à inspecter : le panneau de détails reste
    // fermé et son bouton absent, plutôt que d'afficher des champs vides.
    readonly property string inspectionKind: ""
    readonly property bool inspectorAvailable: inspectionKind.length > 0
    readonly property string inspectionTitle: ""
    readonly property var inspectionFields: []
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
        }
    }
}
