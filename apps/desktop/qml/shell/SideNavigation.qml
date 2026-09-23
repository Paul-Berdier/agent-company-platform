// Navigation latérale.
//
// Les destinations non livrées RESTENT visibles, désactivées, avec leur explication en
// infobulle. Les masquer laisserait croire qu'elles n'existent pas ; les activer serait
// un bouton qui fait semblant.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design
import Acp.Runtime

Rectangle {
    id: navigation

    color: Colors.surfaceSidebar
    readonly property bool collapsed: width <= Space.layoutSidebarCollapsedWidth + 8

    Rectangle {
        anchors.right: parent.right
        height: parent.height
        width: Space.layoutBorderWidth
        color: Colors.borderDefault
    }

    ListView {
        id: list
        anchors.fill: parent
        anchors.topMargin: Space.space4
        anchors.bottomMargin: Space.space4
        clip: true
        model: Navigation
        currentIndex: -1
        keyNavigationEnabled: true
        activeFocusOnTab: true

        delegate: Item {
            id: entry
            required property string route
            required property string title
            required property string glyph
            required property string detail
            required property string readinessLabel
            required property bool navigable

            width: list.width
            height: Space.densityRowHeightComfortable
            activeFocusOnTab: true

            readonly property bool current: Navigation.currentRoute === entry.route

            Rectangle {
                id: background
                anchors.fill: parent
                anchors.leftMargin: Space.space2
                anchors.rightMargin: Space.space2
                radius: Radius.radiusSm
                color: entry.current
                    ? Colors.accentMuted
                    : (hover.hovered && entry.navigable ? Colors.stateHover : "transparent")

                // Marque de sélection : elle ne repose PAS sur la seule couleur.
                Rectangle {
                    visible: entry.current
                    width: 2
                    height: background.height - Space.space3 * 2
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    color: Colors.accentPrimary
                }

                Text {
                    id: glyphText
                    anchors.left: parent.left
                    anchors.leftMargin: Space.space5
                    anchors.verticalCenter: parent.verticalCenter
                    // Le jeu d'icônes n'est pas choisi : on affiche l'initiale du nom
                    // sémantique plutôt qu'une ressource graphique qui n'existe pas.
                    text: entry.glyph.length > 0 ? entry.glyph.charAt(0).toUpperCase() : "·"
                    color: entry.navigable ? Colors.textSecondary : Colors.textMuted
                    font.family: Type.identifier.family
                    font.pixelSize: Type.identifier.pixelSize
                }

                Text {
                    visible: !navigation.collapsed
                    anchors.left: glyphText.right
                    anchors.leftMargin: Space.space4
                    anchors.right: parent.right
                    anchors.rightMargin: Space.space4
                    anchors.verticalCenter: parent.verticalCenter
                    text: entry.title
                    elide: Text.ElideRight
                    color: entry.navigable ? Colors.textPrimary : Colors.textMuted
                    font.family: Type.tableCell.family
                    font.pixelSize: Type.tableCell.pixelSize
                    font.weight: entry.current
                        ? Type.tableCellEmphasis.weight
                        : Type.tableCell.weight
                }

                // Anneau de focus clavier : jamais supprimé, jamais remplacé par une
                // simple variation de fond.
                Rectangle {
                    visible: entry.activeFocus
                    anchors.fill: parent
                    anchors.margins: -Space.layoutFocusRingOffset
                    color: "transparent"
                    radius: Radius.radiusSm
                    border.width: Space.layoutFocusRingWidth
                    border.color: Colors.borderFocus
                }
            }

            HoverHandler {
                id: hover
                cursorShape: entry.navigable ? Qt.PointingHandCursor : Qt.ArrowCursor
            }

            ToolTip.visible: hover.hovered && (navigation.collapsed || !entry.navigable)
            ToolTip.text: entry.navigable
                ? entry.title
                : entry.title + " — " + entry.readinessLabel + "\n" + entry.detail
            ToolTip.delay: 400

            // Le clic passe TOUJOURS par le modèle : c'est lui qui refuse une destination
            // non livrée et qui fournit l'explication affichée dans la barre basse.
            TapHandler {
                onTapped: Navigation.currentRoute = entry.route
            }

            Keys.onReturnPressed: Navigation.currentRoute = entry.route
            Keys.onSpacePressed: Navigation.currentRoute = entry.route

            Accessible.role: Accessible.Button
            Accessible.name: entry.title
            Accessible.description: entry.navigable ? "" : entry.readinessLabel
            // Même chemin que le clic : le modèle refuse une destination non livrée.
            Accessible.onPressAction: Navigation.currentRoute = entry.route
        }
    }
}
