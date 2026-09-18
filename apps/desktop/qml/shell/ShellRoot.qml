// Coquille : barre supérieure, navigation, zone de travail, inspecteur, barre basse.
//
// Disposition : un SplitView horizontal redimensionnable entre la navigation, le contenu
// et l'inspecteur optionnel. Les volets sont repliables ; le redimensionnement est
// instantané, conformément au profil de mouvement (`panelResize: duration.instant`).

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime

Item {
    id: shell

    // En dessous du seuil « narrow », l'inspecteur passe en surcouche et la navigation se
    // réduit aux glyphes : la station est souvent utilisée en demi-écran.
    readonly property bool narrow: shell.width < Space.breakpointRegular

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TopBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutTopBarHeight
        }

        SplitView {
            id: split
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            handle: Rectangle {
                implicitWidth: Space.layoutPaneGap + 4
                color: SplitHandle.pressed || SplitHandle.hovered
                    ? Palette.borderInteractive
                    : Palette.borderSubtle
            }

            SideNavigation {
                SplitView.preferredWidth: Shell.sidebarCollapsed
                    ? Space.layoutSidebarCollapsedWidth
                    : Space.layoutSidebarWidth
                SplitView.minimumWidth: Space.layoutSidebarCollapsedWidth
                SplitView.maximumWidth: Space.layoutSidebarWidth * 1.5
            }

            WorkArea {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 320
            }

            InspectorPanel {
                visible: Shell.inspectorVisible && !shell.narrow
                SplitView.preferredWidth: Space.layoutInspectorWidthDefault
                SplitView.minimumWidth: Space.layoutInspectorWidthMin
            }
        }

        StatusBar {
            Layout.fillWidth: true
            Layout.preferredHeight: Space.layoutStatusBarHeight
        }
    }

    // En largeur réduite, l'inspecteur devient une surcouche plutôt que de comprimer le
    // contenu jusqu'à l'illisible.
    Rectangle {
        visible: Shell.inspectorVisible && shell.narrow
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: Space.layoutTopBarHeight
        anchors.bottomMargin: Space.layoutStatusBarHeight
        width: Math.min(Space.layoutInspectorWidthDefault, shell.width * 0.8)
        color: Palette.surfacePanel
        border.width: Space.layoutBorderWidth
        border.color: Palette.borderDefault

        InspectorPanel {
            anchors.fill: parent
        }
    }
}
