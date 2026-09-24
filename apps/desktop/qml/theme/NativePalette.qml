// Les contrôles Qt Basic héritent de la même palette que les composants de la station.
import QtQuick
import Acp.Design

Palette {
    window: Colors.surfaceCanvas
    windowText: Colors.textPrimary
    base: Colors.surfacePanel
    alternateBase: Colors.surfacePanelRaised
    text: Colors.textPrimary
    button: Colors.surfacePanelRaised
    buttonText: Colors.textPrimary
    light: Colors.stateSelected
    midlight: Colors.stateHover
    mid: Colors.borderDefault
    dark: Colors.borderInteractive
    highlight: Colors.accentPrimary
    highlightedText: Colors.textOnAccent
    toolTipBase: Colors.surfaceOverlay
    toolTipText: Colors.textPrimary
    placeholderText: Colors.textMuted
    disabled.text: Colors.textMuted
    disabled.windowText: Colors.textMuted
    disabled.buttonText: Colors.textMuted
    disabled.button: Colors.stateDisabled
}
