// Fond d'un panneau ou d'un contrôle : coins crantés en Pixel Atelier, arrondis en Studio.
//
// Aucun Canvas : deux rectangles croisés dessinent la surface, quatre traits et quatre pixels
// de coin dessinent le contour en marches. Le graphe de scène les regroupe ; rien n'est
// redessiné quand le thème change, seules les couleurs suivent leurs liaisons.

import QtQuick
import Acp.Design

Item {
    id: fond

    property color couleur: "transparent"
    property color bordure: "transparent"
    property real epaisseur: 0
    //! Taille du cran des coins ; 0 : rectangle arrondi (`rayon`).
    property real cran: Colors.family === "atelier" ? Space.layoutPixelUnit : 0
    property real rayon: Radius.radiusMd

    Rectangle {
        visible: fond.cran <= 0
        anchors.fill: parent
        color: fond.couleur
        radius: fond.rayon
        border.width: fond.epaisseur
        border.color: fond.bordure
    }

    Item {
        visible: fond.cran > 0
        anchors.fill: parent
        readonly property real c: fond.cran
        readonly property real e: fond.epaisseur

        Rectangle { x: parent.c; width: parent.width - 2 * parent.c; height: parent.height; color: fond.couleur }
        Rectangle { y: parent.c; width: parent.width; height: parent.height - 2 * parent.c; color: fond.couleur }

        Rectangle { visible: parent.e > 0; x: parent.c; width: parent.width - 2 * parent.c; height: parent.e; color: fond.bordure }
        Rectangle { visible: parent.e > 0; x: parent.c; y: parent.height - parent.e; width: parent.width - 2 * parent.c; height: parent.e; color: fond.bordure }
        Rectangle { visible: parent.e > 0; y: parent.c; width: parent.e; height: parent.height - 2 * parent.c; color: fond.bordure }
        Rectangle { visible: parent.e > 0; x: parent.width - parent.e; y: parent.c; width: parent.e; height: parent.height - 2 * parent.c; color: fond.bordure }

        Rectangle { visible: parent.e > 0; x: parent.c - parent.e; y: parent.c - parent.e; width: parent.e; height: parent.e; color: fond.bordure }
        Rectangle { visible: parent.e > 0; x: parent.width - parent.c; y: parent.c - parent.e; width: parent.e; height: parent.e; color: fond.bordure }
        Rectangle { visible: parent.e > 0; x: parent.c - parent.e; y: parent.height - parent.c; width: parent.e; height: parent.e; color: fond.bordure }
        Rectangle { visible: parent.e > 0; x: parent.width - parent.c; y: parent.height - parent.c; width: parent.e; height: parent.e; color: fond.bordure }
    }
}
