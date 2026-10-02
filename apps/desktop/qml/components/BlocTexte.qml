// Texte long venu du serveur (objectif, résumé, question, note) : affiché EN TEXTE BRUT,
// sélectionnable et copiable, jamais interprété comme du balisage. Une valeur vide s'affiche
// avec le libellé de remplacement donné (par exemple « Aucune carte finie pour l'instant. »).

import QtQuick
import QtQuick.Layouts
import Acp.Design

ColumnLayout {
    id: bloc

    property string libelle: ""
    property string texte: ""
    property string vide: ""
    property bool monospace: false

    spacing: Space.space1

    Text {
        Layout.fillWidth: true
        visible: bloc.libelle.length > 0
        text: bloc.libelle
        textFormat: Text.PlainText
        color: Colors.textSecondary
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    TextEdit {
        objectName: "bloc-texte-valeur"
        Layout.fillWidth: true
        readOnly: true
        selectByMouse: true
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.Wrap
        text: bloc.texte.length > 0 ? bloc.texte : bloc.vide
        color: bloc.texte.length > 0 ? Colors.textPrimary : Colors.textMuted
        selectionColor: Colors.stateSelected
        selectedTextColor: Colors.textPrimary
        font.family: bloc.monospace ? Type.identifier.family : Type.prose.family
        font.pixelSize: bloc.monospace ? Type.identifier.pixelSize : Type.prose.pixelSize
        Accessible.role: Accessible.StaticText
        Accessible.name: bloc.libelle.length > 0 ? bloc.libelle + " : " + text : text
    }
}
