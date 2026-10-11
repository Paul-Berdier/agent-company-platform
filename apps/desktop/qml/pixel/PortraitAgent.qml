// Portrait d'un agent : son rôle se lit à l'accessoire, son état réel à la bulle.
//
// Aucune activité n'est inventée : l'image « au travail » ne s'anime que si l'état observé
// est « travail » ET que la télémétrie est présente (`observe`) ET que Motion l'admet ; le
// clignement au repos est de l'ambiance (profil complet, hors Concentration). Sans
// télémétrie, le portrait reste fixe et le texte voisin le dit.

import QtQuick
import Acp.Design

Item {
    id: portrait

    //! coordinateur, developpeur, relecteur, explorateur, testeur ou inconnu.
    property string role: "inconnu"
    //! repos, travail, attente, echec, termine ou arrete.
    property string etat: "repos"
    property int echelle: 3
    property bool observe: true
    property string description: ""

    readonly property string sequenceVoulue: portrait.role + "." + portrait.etat
    readonly property string sequenceRetenue: PlanchesPixel.portraits.sequences[portrait.sequenceVoulue] !== undefined
        ? portrait.sequenceVoulue
        : (PlanchesPixel.portraits.sequences["inconnu." + portrait.etat] !== undefined ? "inconnu." + portrait.etat
                                                                                       : "inconnu.repos")
    readonly property bool anime: portrait.etat === "travail"
        ? (portrait.observe && Motion.spriteActivityActive)
        : (portrait.etat === "repos" && Motion.ambianceActive)

    implicitWidth: sprite.implicitWidth
    implicitHeight: sprite.implicitHeight

    SpritePixel {
        id: sprite
        anchors.fill: parent
        planche: "portraits"
        sequence: portrait.sequenceRetenue
        echelle: portrait.echelle
        animer: portrait.anime
    }

    Accessible.role: Accessible.Graphic
    Accessible.name: portrait.description
    Accessible.ignored: portrait.description.length === 0
}
