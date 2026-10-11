// Racine de l'application : volontairement mince.
//
// Elle ne fait que quatre choses : brancher les jetons de design sur la préférence
// d'apparence, choisir entre l'écran de première ouverture et la coquille, installer les
// raccourcis globaux, et porter la palette de commandes. Aucune logique métier, aucun
// appel réseau, aucune décision d'état.

import QtQuick
import QtQuick.Controls.Basic
import Acp.Design
import Acp.Runtime
import Acp.Theme
import Acp.Station
import Acp.Pages

ApplicationWindow {
    id: root

    width: 1280
    height: 800
    minimumWidth: Space.layoutWindowMinWidth
    minimumHeight: Space.layoutWindowMinHeight
    visible: true
    title: qsTr("Station de travail — Agent Company Platform")
    color: Colors.surfaceCanvas
    palette: NativePalette {}

    // Fenêtre réduite : les pages cessent de sonder Hermes (cahier P8 § 6.1). Le sondage
    // léger de la barre d'état, lui, continue.
    onVisibilityChanged: Streams.fenetreActive = root.visibility !== Window.Minimized
        && root.visibility !== Window.Hidden

    // Les singletons générés portent le thème actif. La sélection vient de la couche C++
    // (préférence de l'opérateur, puis thème système) et jamais d'une décision prise ici.
    ThemeBridge {}

    // L'écran de connexion REMPLACE la coquille tant qu'aucune adresse n'est acceptée ou
    // qu'aucune session n'est ouverte : toutes les données métier exigent une session, il
    // n'y a donc rien d'honnête à afficher avant.
    Loader {
        anchors.fill: parent
        sourceComponent: Shell.connectionRequired ? firstRunComponent : shellComponent
    }

    Component {
        id: firstRunComponent
        FirstRunPage {}
    }

    Component {
        id: shellComponent
        ShellRoot {}
    }

    CommandPalette {
        anchors.fill: parent
        visible: Shell.commandPaletteOpen
    }

    // Transition de palette (D165) : au changement de thème, l'ancienne couleur du canevas couvre
    // brièvement la fenêtre puis s'efface. Aucun écran n'est recréé ; aucun éclair clair au
    // démarrage, le thème étant posé avant la première image. Profil réduit : instantané.
    property color fondMemorise: "transparent"
    Component.onCompleted: root.fondMemorise = Colors.surfaceCanvas
    Connections {
        target: Colors
        function onThemeChanged() {
            if (Motion.active.paletteTransition.duration > 0) {
                voile.color = root.fondMemorise;
                fondu.restart();
            }
            root.fondMemorise = Colors.surfaceCanvas;
        }
    }
    Rectangle {
        id: voile
        anchors.fill: parent
        opacity: 0
        visible: opacity > 0
        Accessible.ignored: true
        OpacityAnimator {
            id: fondu
            target: voile
            from: 1
            to: 0
            duration: Motion.active.paletteTransition.duration
            easing.type: Easing.Bezier
            easing.bezierCurve: Motion.easingStandard
        }
    }

    // Raccourcis globaux. Ils exécutent des COMMANDES du registre, jamais une action
    // câblée directement : la disponibilité est ainsi calculée au même endroit que pour
    // un bouton ou pour la palette. Un Shortcut par raccourci DÉCLARÉ au registre : tout
    // raccourci que la palette affiche fonctionne (Ctrl+1 à Ctrl+9, Ctrl+K, Ctrl+R, Alt+←/→).
    Instantiator {
        model: Commands.raccourcis()
        delegate: Shortcut {
            required property string modelData
            sequence: modelData
            onActivated: Commands.execute(Commands.commandForShortcut(modelData))
        }
    }
    Shortcut {
        sequence: "Escape"
        enabled: Shell.commandPaletteOpen
        onActivated: Shell.commandPaletteOpen = false
    }
}
