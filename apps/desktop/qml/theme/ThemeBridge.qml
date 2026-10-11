// Branche les singletons de design sur les préférences d'apparence de la station.
//
// Les fichiers générés déclarent les propriétés de sélection (`theme`, `profile`,
// `concentration`, `density`, `textScale`) qu'ils n'alimentent pas eux-mêmes : « la sélection
// de thème est faite à l'exécution par la couche QML, pas par le générateur ». C'est ici, et
// nulle part ailleurs, que cette sélection a lieu. Aucun composant ne choisit son thème.
//
// Changement à chaud (D165) : seules des propriétés changent ; aucun écran, aucune session
// ni aucun modèle n'est recréé.

import QtQuick
import Acp.Design
import Acp.Runtime

QtObject {
    id: bridge

    readonly property string activeTheme: Appearance.activeTheme
    readonly property string activeMotionProfile: Appearance.activeMotionProfile
    readonly property bool concentration: Appearance.concentration
    readonly property string density: Appearance.density
    readonly property int textScale: Appearance.textScale

    function applyTheme() {
        Colors.theme = bridge.activeTheme;
        Status.theme = bridge.activeTheme;
        Elevation.theme = bridge.activeTheme;
    }

    function applyMotion() {
        Motion.profile = bridge.activeMotionProfile;
        Motion.concentration = bridge.concentration;
    }

    function applyReading() {
        Space.density = bridge.density;
        Type.textScale = bridge.textScale;
    }

    onActiveThemeChanged: bridge.applyTheme()
    onActiveMotionProfileChanged: bridge.applyMotion()
    onConcentrationChanged: bridge.applyMotion()
    onDensityChanged: bridge.applyReading()
    onTextScaleChanged: bridge.applyReading()
    Component.onCompleted: {
        bridge.applyTheme();
        bridge.applyMotion();
        bridge.applyReading();
    }
}
