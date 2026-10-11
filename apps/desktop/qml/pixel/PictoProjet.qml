// Pictogramme décoratif d'un projet ou d'une mission (12 × 12). Il est choisi par la station
// d'après l'identifiant (EspaceTravailViewModel.pictogramme) et ne porte aucune donnée.

import QtQuick
import Acp.Design

SpritePixel {
    id: picto

    property string motif: "cristal"
    property string teinte: "lavande"

    readonly property var motifs: ["fusee", "cristal", "feuille", "livre", "eclair", "planete", "engrenage"]

    planche: "pictogrammes"
    sequence: picto.teinte
    image: Math.max(0, picto.motifs.indexOf(picto.motif))
    echelle: 2
    Accessible.ignored: true
}
