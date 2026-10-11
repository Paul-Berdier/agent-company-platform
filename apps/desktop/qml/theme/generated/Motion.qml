// Fichier généré — NE PAS MODIFIER À LA MAIN.
// Source    : design/tokens/motion.json (version 2.0.0)
// Générateur : apps/desktop/cmake/generate_design_tokens.py
// Toute correction se fait dans le fichier de jetons, puis par régénération.

pragma Singleton

import QtQuick

QtObject {
    id: root

    // Profil actif. Écrit par ThemeBridge d'après la préférence de l'opérateur (couche
    // C++). Jamais deviné en QML ; un nom inconnu retombe sur le profil par défaut.
    property string profile: "complet"
    readonly property var profiles: ["complet", "discret", "reduit"]
    readonly property bool knownProfile: root.profiles.indexOf(root.profile) >= 0
    readonly property bool reduced: root.profile === "reduit"
    // Mode Concentration : coupe l'ambiance quel que soit le profil (préférence distincte).
    property bool concentration: false
    readonly property var profileLabels: ({"complet": "Complet", "discret": "Discret", "reduit": "Réduit"})

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
    readonly property int durationSpriteFrame: 240
    readonly property int durationAmbiance: 2600

    readonly property QtObject completProfile: QtObject {
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
            readonly property int loops: Animation.Infinite
        }
        readonly property QtObject panelToggle: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject attention: QtObject {
            readonly property int duration: root.durationSlow
            readonly property var easing: root.easingStandard
            readonly property int loops: 2
        }
        readonly property QtObject completion: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingEnter
        }
        readonly property QtObject paletteTransition: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject spriteActivity: QtObject {
            readonly property int duration: root.durationSpriteFrame
            readonly property int loops: Animation.Infinite
        }
        readonly property QtObject ambiance: QtObject {
            readonly property int duration: root.durationAmbiance
            readonly property int loops: Animation.Infinite
        }
    }

    readonly property QtObject discretProfile: QtObject {
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
            readonly property int loops: Animation.Infinite
        }
        readonly property QtObject panelToggle: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject attention: QtObject {
            readonly property int duration: root.durationSlow
            readonly property var easing: root.easingStandard
            readonly property int loops: 2
        }
        readonly property QtObject completion: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingEnter
        }
        readonly property QtObject paletteTransition: QtObject {
            readonly property int duration: root.durationBase
            readonly property var easing: root.easingStandard
        }
        readonly property QtObject spriteActivity: QtObject {
            readonly property int duration: root.durationSpriteFrame
            readonly property int loops: Animation.Infinite
        }
        readonly property QtObject ambiance: QtObject {
            readonly property int duration: root.durationInstant
            readonly property int loops: 0
        }
    }

    readonly property QtObject reduitProfile: QtObject {
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
            readonly property int loops: 0
        }
        readonly property QtObject panelToggle: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject attention: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingLinear
            readonly property int loops: 1
        }
        readonly property QtObject completion: QtObject {
            readonly property int duration: root.durationMicro
            readonly property var easing: root.easingLinear
        }
        readonly property QtObject paletteTransition: QtObject {
            readonly property int duration: root.durationInstant
        }
        readonly property QtObject spriteActivity: QtObject {
            readonly property int duration: root.durationInstant
            readonly property int loops: 0
        }
        readonly property QtObject ambiance: QtObject {
            readonly property int duration: root.durationInstant
            readonly property int loops: 0
        }
    }

    // Profil réellement appliqué par les composants.
    readonly property QtObject active: root.profile === "discret" ? root.discretProfile : root.profile === "reduit" ? root.reduitProfile : root.completProfile
    // L'ambiance (sprites et scènes décoratifs) ne tourne que si le profil l'admet et
    // hors mode Concentration ; la vue la suspend en plus hors écran.
    readonly property bool ambianceActive: !root.concentration && root.active.ambiance.duration > 0
    readonly property bool spriteActivityActive: root.active.spriteActivity.duration > 0
}
