// Titre de section d'un panneau.

import QtQuick
import Acp.Design

Item {
    id: header

    property string title: ""
    property string subtitle: ""

    implicitHeight: column.implicitHeight

    Column {
        id: column
        width: parent.width
        spacing: Space.space1

        Text {
            width: parent.width
            text: header.title
            elide: Text.ElideRight
            color: Colors.textPrimary
            font.family: Type.panelTitle.family
            font.pixelSize: Type.panelTitle.pixelSize
            font.weight: Type.panelTitle.weight
        }

        Text {
            width: parent.width
            visible: header.subtitle.length > 0
            text: header.subtitle
            wrapMode: Text.WordWrap
            color: Colors.textMuted
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
    }
}
