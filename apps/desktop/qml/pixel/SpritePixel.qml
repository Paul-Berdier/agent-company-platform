// Une case d'une planche pixel (design/pixel, générée par scripts/generer_assets_pixel.py).
//
// L'image est agrandie par multiple entier, sans lissage. Une séquence de plusieurs images
// ne tourne que si l'appelant le demande (`animer`, liée à un état OBSERVÉ ou à l'ambiance
// admise par Motion), si l'élément est visible et si la fenêtre n'est ni réduite ni cachée :
// hors de ces cas, la première image reste fixe et aucun minuteur ne tourne.

import QtQuick
import Acp.Design

Item {
    id: sprite

    //! Planche : « portraits », « pictogrammes » ou « police » (PlanchesPixel).
    property string planche: "portraits"
    property string sequence: ""
    //! Image affichée quand la séquence ne tourne pas.
    property int image: 0
    property int echelle: 2
    property bool animer: false

    readonly property var meta: PlanchesPixel[sprite.planche]
    readonly property var seq: sprite.meta && sprite.meta.sequences ? sprite.meta.sequences[sprite.sequence] : undefined
    readonly property bool connue: sprite.seq !== undefined
    readonly property int nombreImages: sprite.seq ? sprite.seq.durees.length : 0
    readonly property bool fenetreVisible: Window.visibility !== Window.Minimized && Window.visibility !== Window.Hidden
    readonly property bool tourne: sprite.animer && sprite.nombreImages > 1 && sprite.visible && sprite.fenetreVisible
    property int courante: 0

    implicitWidth: sprite.meta ? sprite.meta.case[0] * sprite.echelle : 0
    implicitHeight: sprite.meta ? sprite.meta.case[1] * sprite.echelle : 0

    onTourneChanged: if (!sprite.tourne) sprite.courante = 0

    Image {
        anchors.fill: parent
        visible: sprite.connue
        source: sprite.meta ? Qt.resolvedUrl("assets/" + sprite.meta.fichier) : ""
        sourceClipRect: sprite.connue
            ? Qt.rect(((sprite.tourne ? sprite.courante : sprite.image) % Math.max(1, sprite.meta.colonnes)) * sprite.meta.case[0],
                      sprite.seq.rang * sprite.meta.case[1], sprite.meta.case[0], sprite.meta.case[1])
            : Qt.rect(0, 0, 0, 0)
        smooth: false
        mipmap: false
        fillMode: Image.Stretch
    }

    Timer {
        running: sprite.tourne
        repeat: true
        interval: sprite.seq ? Math.max(60, sprite.seq.durees[sprite.courante] || 240) : 1000
        onTriggered: sprite.courante = (sprite.courante + 1) % sprite.nombreImages
    }
}
