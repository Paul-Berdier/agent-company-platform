// Message natif : Markdown contrôlé pour Hermes, texte brut pour les autres rôles,
// code copiable sans exécution. Aucun média externe n’est chargé par le rendu.

import QtQuick
import QtQuick.Layouts
import Acp.Design
import QtQuick.Controls.Basic

Rectangle {
    id: bulle

    property string auteur: ""
    property string texte: ""
    //! « utilisateur », « assistant », « outil », « systeme » ou « autre ».
    property string role: "autre"
    property bool enCours: false
    property string statut: ""
    property string avertissement: ""
    property string heure: ""
    property bool outilDeveloppe: false
    property var blocsMessage: []
    signal copierDemande(string contenu)
    signal lienDemande(string lien)

    component BoutonMessage: Button {
        id: bouton
        property string label: ""
        signal triggered()
        text: label
        implicitHeight: Space.densityControlHeightRegular
        horizontalPadding: Space.space3
        onClicked: triggered()
        background: Rectangle {
            radius: Radius.radiusSm
            color: bouton.down ? Colors.statePressed : bouton.hovered ? Colors.stateHover : "transparent"
            border.width: bouton.activeFocus ? 2 : 1
            border.color: bouton.activeFocus ? Colors.borderFocus : Colors.borderSubtle
        }
        contentItem: Text {
            text: bouton.text
            textFormat: Text.PlainText
            color: Colors.textSecondary
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Accessible.name: label
    }

    readonly property bool deVous: bulle.role === "utilisateur"
    readonly property string indication: bulle.enCours
        ? (bulle.role === "outil" ? qsTr("en cours") : qsTr("Hermes écrit…"))
        : ""

    implicitHeight: colonne.implicitHeight + Space.space4 * 2
    radius: Radius.radiusMd
    color: bulle.deVous ? Colors.accentMuted
        : bulle.role === "outil" || bulle.role === "systeme" ? Colors.surfaceSunken : "transparent"
    border.width: bulle.deVous ? Space.layoutBorderWidth : 0
    border.color: Colors.borderSubtle

    Accessible.role: Accessible.StaticText
    Accessible.name: bulle.auteur + " : " + bulle.texte + (bulle.statut.length > 0 ? " (" + bulle.statut + ")" : "")

    // Largeur déterminée avant la hauteur du texte : des Layouts imbriqués
    // donnaient une hauteur transitoire et déplaçaient l’historique à la molette.
    Column {
        id: colonne
        x: Space.space4; y: Space.space4
        width: Math.max(0, bulle.width - Space.space4 * 2)
        spacing: Space.space2

        RowLayout {
            width: colonne.width
            spacing: Space.space3
            AtelierMark { visible: bulle.role === "assistant"; Layout.preferredWidth: 24; Layout.preferredHeight: 20 }
            Text {
                text: bulle.auteur
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.family: Type.tableCellEmphasis.family
                font.pixelSize: Type.tableCellEmphasis.pixelSize
                font.weight: Type.tableCellEmphasis.weight
            }
            Text {
                visible: bulle.heure.length > 0
                text: bulle.heure
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
            Item { Layout.fillWidth: true }
            BoutonMessage {
                objectName: "bulle-copier"
                visible: bulle.texte.length > 0
                label: qsTr("Copier")
                onTriggered: bulle.copierDemande(bulle.texte)
            }
            BoutonMessage {
                visible: bulle.role === "outil" && bulle.texte.length > 0
                label: bulle.outilDeveloppe ? qsTr("Réduire") : qsTr("Détails")
                onTriggered: bulle.outilDeveloppe = !bulle.outilDeveloppe
            }
            Text {
                objectName: "bulle-indication"
                visible: bulle.indication.length > 0
                text: bulle.indication
                textFormat: Text.PlainText
                color: Status.statusRunningForeground
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }

        TextEdit {
            objectName: "bulle-texte"
            width: colonne.width
            visible: text.length > 0 && bulle.blocsMessage.length === 0 && (bulle.role !== "outil" || bulle.outilDeveloppe)
            readOnly: true
            selectByMouse: true
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.Wrap
            text: bulle.texte
            color: bulle.role === "outil" ? Colors.textSecondary : Colors.textPrimary
            selectionColor: Colors.stateSelected
            selectedTextColor: Colors.textPrimary
            font.family: bulle.role === "outil" ? Type.identifier.family : Type.prose.family
            font.pixelSize: bulle.role === "outil" ? Type.identifier.pixelSize : Type.prose.pixelSize
        }

        Repeater {
            model: bulle.blocsMessage
            delegate: Rectangle {
                id: bloc
                required property var modelData
                width: colonne.width
                readonly property bool code: modelData.genre === "code"
                implicitHeight: contenuBloc.implicitHeight + (code ? Space.space4 * 2 : 0)
                color: code ? Colors.surfaceSunken : "transparent"
                radius: Radius.radiusSm
                border.width: code ? 1 : 0
                border.color: Colors.borderSubtle
                Column {
                    id: contenuBloc
                    x: bloc.code ? Space.space4 : 0
                    y: x
                    width: Math.max(0, bloc.width - x * 2)
                    spacing: Space.space2
                    RowLayout {
                        visible: bloc.code
                        width: contenuBloc.width
                        Text {
                            text: bloc.modelData.langue || qsTr("Code")
                            textFormat: Text.PlainText
                            color: Colors.textMuted
                            font.family: Type.identifier.family
                            font.pixelSize: Type.identifier.pixelSize
                        }
                        Item { Layout.fillWidth: true }
                        BoutonMessage {
                            objectName: bloc.code ? "bulle-copier-code" : ""
                            label: qsTr("Copier le code")
                            onTriggered: bulle.copierDemande(bloc.modelData.texte)
                        }
                    }
                    TextEdit {
                        objectName: bloc.code ? "bulle-code" : "bulle-markdown"
                        width: contenuBloc.width
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        textFormat: bloc.modelData.genre === "prose" ? TextEdit.RichText : TextEdit.PlainText
                        text: bloc.modelData.genre === "prose" ? bloc.modelData.html : bloc.modelData.texte
                        color: Colors.textPrimary
                        selectionColor: Colors.stateSelected
                        selectedTextColor: Colors.textPrimary
                        font.family: bloc.code ? Type.identifier.family : Type.prose.family
                        font.pixelSize: bloc.code ? Type.identifier.pixelSize : Type.prose.pixelSize
                        onLinkActivated: function(lien) {
                            bulle.lienDemande(lien);
                        }
                        Accessible.name: bloc.modelData.texte
                    }
                }
            }
        }

        Text {
            objectName: "bulle-statut"
            width: colonne.width
            visible: bulle.statut.length > 0
            text: bulle.statut
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: bulle.statut === qsTr("Envoi…") ? Colors.textMuted : Status.statusFailedForeground
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }

        Text {
            objectName: "bulle-avertissement"
            width: colonne.width
            visible: bulle.avertissement.length > 0
            text: qsTr("Avertissement : %1").arg(bulle.avertissement)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Status.statusDegradedForeground
            font.family: Type.metadata.family
            font.pixelSize: Type.metadata.pixelSize
        }
    }
}
