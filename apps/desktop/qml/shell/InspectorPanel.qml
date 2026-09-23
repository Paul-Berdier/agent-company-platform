// Inspecteur : panneau latéral optionnel.
//
// Cette fondation ne livre aucun objet inspectable : le panneau dit ce qu'il montrera,
// pourquoi il ne montre rien, et comment le refermer. Il n'affiche pas de données
// d'exemple.

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Rectangle {
    id: inspector

    color: Colors.surfacePanel

    Rectangle {
        anchors.left: parent.left
        height: parent.height
        width: Space.layoutBorderWidth
        color: Colors.borderDefault
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space6

        RowLayout {
            Layout.fillWidth: true
            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("Inspecteur")
            }
            AcpIconButton {
                glyph: "×"
                tooltip: qsTr("Fermer l'inspecteur")
                onTriggered: Shell.inspectorVisible = false
            }
        }

        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: qsTr("Aucun élément sélectionné")
            body: qsTr("L'inspecteur affichera le détail d'une mission, d'une tentative ou "
                       + "d'un livrable. Aucun de ces écrans n'est livré par cette fondation.")
        }
    }
}
