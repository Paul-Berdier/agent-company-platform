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

    // Raccourcis globaux. Ils exécutent des COMMANDES du registre, jamais une action
    // câblée directement : la disponibilité est ainsi calculée au même endroit que pour
    // un bouton ou pour la palette.
    Shortcut {
        sequence: "Ctrl+K"
        onActivated: Commands.execute("palette.open")
    }
    Shortcut {
        sequence: "Ctrl+1"
        onActivated: Commands.execute("navigation.home")
    }
    Shortcut {
        sequence: "Ctrl+2"
        onActivated: Commands.execute("navigation.diagnostics")
    }
    Shortcut {
        sequence: "Ctrl+R"
        onActivated: Commands.execute("connection.probe")
    }
    Shortcut {
        sequence: "Escape"
        enabled: Shell.commandPaletteOpen
        onActivated: Shell.commandPaletteOpen = false
    }
}
