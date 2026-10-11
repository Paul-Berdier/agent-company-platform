// Emblème d'ACP : noyau carré, deux ailes en pixels, trois agents. Identique dans tous les
// thèmes (l'icône système ne varie pas). L'image retenue est la plus petite taille dessinée
// qui couvre la taille demandée au facteur d'échelle de l'écran : jamais lissée.

import QtQuick
import Acp.Design

Item {
    id: embleme

    property int taille: 32

    readonly property real facteur: Screen.devicePixelRatio > 0 ? Screen.devicePixelRatio : 1
    readonly property int source: {
        const voulu = embleme.taille * embleme.facteur;
        const tailles = PlanchesPixel.embleme.tailles;
        for (let i = 0; i < tailles.length; ++i) {
            if (tailles[i] >= voulu)
                return tailles[i];
        }
        return tailles[tailles.length - 1];
    }

    implicitWidth: embleme.taille
    implicitHeight: embleme.taille

    Image {
        anchors.fill: parent
        source: Qt.resolvedUrl("assets/embleme-" + embleme.source + ".png")
        sourceSize.width: embleme.source
        sourceSize.height: embleme.source
        smooth: false
        mipmap: false
    }

    Accessible.role: Accessible.Graphic
    Accessible.name: qsTr("Emblème d'ACP")
}
