// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/motion.json (version 1.0.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Profil actif. Écrit par la couche C++ d'après la préférence système,
    // ou forcé par la préférence applicative. Jamais deviné en QML.
    property string profile: "standard"
    readonly property bool reduced: profile === "reduced"

    readonly property int durationInstant: 0
    readonly property int durationMicro: 80
    readonly property int durationFast: 120
    readonly property int durationBase: 180
    readonly property int durationSlow: 240
    readonly property int durationPulse: 1600
    readonly property var easingStandard: [0.2, 0, 0, 1, 1, 1]
    readonly property var easingEnter: [0.05, 0.7, 0.1, 1, 1, 1]
    readonly property var easingExit: [0.3, 0, 0.8, 0.15, 1, 1]
    readonly property var easingLinear: [0, 0, 1, 1, 1, 1]
    readonly property real distanceEnter: 4
    readonly property real distancePanelSlide: 12
    readonly property real opacityEnterFrom: 0
    readonly property real opacityPulseMin: 0.45

    readonly property QtObject standardProfile: QtObject {
        readonly property QtObject hover: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject press: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject focusRing: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject statusChange: QtObject {
            readonly property int duration: root.durationFast
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject overlayEnter: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingEnter
            readonly property real distance: root.distanceEnter
        }
        readonly property QtObject overlayExit: QtObject {
            readonly property int duration: root.durationFast
            readonly property var easing: root.easingExit
        }
        readonly property QtObject panelResize: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject listInsert: QtObject {
            readonly property int duration: root.durationFast
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject activityPulse: QtObject {
            readonly property int duration: root.durationPulse
            readonly property var easing: root.easingLinear
        }
    }

    readonly property QtObject reducedProfile: QtObject {
        readonly property QtObject hover: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject press: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject focusRing: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject statusChange: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingLinear
        }
        readonly property QtObject overlayEnter: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingLinear
            readonly property real distance: 0
        }
        readonly property QtObject overlayExit: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject panelResize: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject listInsert: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject activityPulse: QtObject {
            readonly property int duration: root.durationInstant
        }
    }

    // Profil réellement appliqué par les composants.
    readonly property QtObject active: root.reduced ? root.reducedProfile : root.standardProfile
}
