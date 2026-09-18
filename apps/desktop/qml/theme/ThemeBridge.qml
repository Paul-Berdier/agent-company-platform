// Branche les singletons de design sur la préférence d'apparence de la station.
//
// Les fichiers générés déclarent une propriété `theme` (et `profile` pour Motion) qu'ils
// n'alimentent pas eux-mêmes : « la sélection de thème est faite à l'exécution par la
// couche QML, pas par le générateur ». C'est ici, et nulle part ailleurs, que cette
// sélection a lieu. Aucun composant ne choisit son thème.

import QtQuick
import Acp.Design
import Acp.Runtime

QtObject {
    id: bridge

    readonly property string activeTheme: Appearance.activeTheme
    readonly property string activeMotionProfile: Appearance.activeMotionProfile

    function applyTheme() {
        Palette.theme = bridge.activeTheme;
        Status.theme = bridge.activeTheme;
        Elevation.theme = bridge.activeTheme;
        Motion.profile = bridge.activeMotionProfile;
    }

    onActiveThemeChanged: bridge.applyTheme()
    onActiveMotionProfileChanged: bridge.applyTheme()
    Component.onCompleted: bridge.applyTheme()
}
