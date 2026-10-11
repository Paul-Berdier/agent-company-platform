// Libellé court en police pixel (capitales 5 × 7, accents français) : emblème, titres de
// section, pastilles. Jamais un paragraphe : la lecture courante reste en police système.
//
// Les glyphes viennent de la planche « police », une rangée par thème et par couleur
// (texte, atténué, accent), générée depuis les jetons : aucune couleur recopiée ici.

import QtQuick
import Acp.Design

Row {
    id: texte

    property string text: ""
    //! « texte », « attenue » ou « accent ».
    property string couleur: "texte"
    property int echelle: 2

    readonly property var police: PlanchesPixel.police
    readonly property string sequenceVoulue: Colors.theme + "." + texte.couleur
    readonly property var seq: texte.police.sequences[texte.sequenceVoulue] !== undefined
        ? texte.police.sequences[texte.sequenceVoulue]
        : texte.police.sequences["atelier-nuit." + texte.couleur]
    readonly property var caracteres: texte.text.toLocaleUpperCase(Qt.locale("fr_FR")).split("")

    spacing: texte.echelle

    Accessible.role: Accessible.StaticText
    Accessible.name: texte.text

    Repeater {
        model: texte.caracteres
        delegate: Image {
            required property string modelData
            readonly property int colonne: texte.police.glyphes[modelData] !== undefined
                ? texte.police.glyphes[modelData] : texte.police.glyphes["?"]
            width: texte.police.case[0] * texte.echelle
            height: texte.police.case[1] * texte.echelle
            source: Qt.resolvedUrl("assets/" + texte.police.fichier)
            sourceClipRect: Qt.rect(colonne * texte.police.case[0], (texte.seq ? texte.seq.rang : 0) * texte.police.case[1],
                                    texte.police.case[0], texte.police.case[1])
            smooth: false
            Accessible.ignored: true
        }
    }
}
