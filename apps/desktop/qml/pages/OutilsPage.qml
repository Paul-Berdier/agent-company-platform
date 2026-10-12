// Catalogue réel de Hermes et registre descriptif des intégrations étudiées.
// Préparer une consigne modifie le brouillon de Discussion, sans envoyer de prompt.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

Item {
    id: page
    objectName: "outils-page"
    readonly property var detail: Catalogue.selection
    readonly property bool selectionPresente: !!detail.id

    Component.onCompleted: Catalogue.pageVisible = visible
    onVisibleChanged: Catalogue.pageVisible = visible
    Component.onDestruction: Catalogue.pageVisible = false

    component Paragraphe: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.tableCell.family
        font.pixelSize: Type.tableCell.pixelSize
    }

    ScrollView {
        id: defilement
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: contenu
            width: Math.min(defilement.availableWidth - Space.space8 * 2, Space.layoutContentMaxWidth)
            x: Math.max(Space.space8, (defilement.availableWidth - width) / 2)
            spacing: Space.space5
            Item { Layout.preferredHeight: Space.space4 }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Outils")
                    textFormat: Text.PlainText
                    color: Colors.textPrimary
                    font.family: Type.pageTitle.family
                    font.pixelSize: Type.pageTitle.pixelSize
                    font.weight: Type.pageTitle.weight
                }
                AcpButton {
                    objectName: "outils-actualiser"
                    label: qsTr("Actualiser")
                    manualEnabled: Catalogue.actif && !Catalogue.chargement
                    onTriggered: Catalogue.actualiser()
                }
            }
            Paragraphe {
                text: qsTr("Retrouvez les compétences de Hermes et préparez les outils de votre projet. Les connexions sont confirmées uniquement par le serveur.")
            }
            EtatLecture { Layout.fillWidth: true; lecture: Catalogue.lecture; erreur: Catalogue.erreur }
            BandeauMessage { Layout.fillWidth: true; message: Catalogue.messageGeste; erreur: Catalogue.erreurGeste }
            Repeater {
                model: Catalogue.alertes
                delegate: Paragraphe { required property string modelData; text: modelData }
            }
            AcpTextField {
                objectName: "outils-recherche"
                Layout.fillWidth: true
                placeholder: qsTr("Rechercher une compétence, un outil ou un profil")
                text: Catalogue.recherche
                onTextChanged: Catalogue.recherche = text
            }
            Flow {
                Layout.fillWidth: true
                spacing: Space.space2
                Repeater {
                    model: [ { cle: "tous", nom: qsTr("Tout") }, { cle: "skills", nom: qsTr("Skills") },
                        { cle: "mcp", nom: qsTr("MCP") }, { cle: "integrations", nom: qsTr("Sources étudiées") } ]
                    delegate: AcpButton {
                        required property var modelData
                        objectName: "outils-filtre-" + modelData.cle
                        label: (Catalogue.typeFiltre === modelData.cle ? "• " : "") + modelData.nom
                        onTriggered: Catalogue.typeFiltre = modelData.cle
                    }
                }
            }
            Paragraphe {
                text: qsTr("%1 résultat(s). Une fiche de source ne signifie pas que son logiciel est installé.").arg(Catalogue.entrees.count)
            }
            GridLayout {
                Layout.fillWidth: true
                columns: contenu.width >= 950 ? 2 : 1
                columnSpacing: Space.space5
                rowSpacing: Space.space5
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 390
                    Layout.preferredHeight: contenu.width >= 950 ? 640 : 330
                    Layout.alignment: Qt.AlignTop
                    color: Colors.surfacePanel
                    radius: Radius.radiusMd
                    border.width: Space.layoutBorderWidth
                    border.color: Colors.borderDefault
                    ListView {
                        id: liste
                        objectName: "outils-liste"
                        anchors.fill: parent
                        anchors.margins: Space.space2
                        clip: true
                        spacing: Space.space2
                        model: Catalogue.entrees
                        ScrollBar.vertical: ScrollBar {}
                        delegate: ItemDelegate {
                            id: ligne
                            required property var item
                            width: liste.width
                            implicitHeight: resume.implicitHeight + Space.space5 * 2
                            padding: Space.space5
                            onClicked: Catalogue.selectionner(item.id)
                            Accessible.name: item.nom + ", " + item.genre + ", " + item.etatLibelle
                            background: Rectangle {
                                color: page.detail.id === ligne.item.id ? Colors.stateSelected
                                    : ligne.hovered ? Colors.surfacePanelRaised : "transparent"
                                radius: Radius.radiusSm
                                border.width: ligne.activeFocus ? 2 : 0
                                border.color: Colors.borderFocus
                            }
                            contentItem: ColumnLayout {
                                id: resume
                                spacing: Space.space2
                                Text {
                                    Layout.fillWidth: true
                                    text: ligne.item.nom
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WrapAnywhere
                                    color: Colors.textPrimary
                                    font.family: Type.panelTitle.family
                                    font.pixelSize: Type.panelTitle.pixelSize
                                }
                                Paragraphe { text: ligne.item.genre + " · " + ligne.item.etatLibelle }
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - Space.space6
                            visible: liste.count === 0
                            text: qsTr("Aucun résultat. Essayez un autre mot ou actualisez le catalogue.")
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            horizontalAlignment: Text.AlignHCenter
                            color: Colors.textMuted
                            font.family: Type.tableCell.family
                            font.pixelSize: Type.tableCell.pixelSize
                        }
                    }
                }
                Carte {
                    objectName: "outils-detail"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 560
                    Layout.alignment: Qt.AlignTop
                    titre: page.selectionPresente ? (page.detail.nom || "") : qsTr("Choisir un outil")
                    sousTitre: page.selectionPresente ? (page.detail.genre || "") : qsTr("Sélectionnez une entrée pour lire son périmètre et préparer la prochaine étape.")
                    Paragraphe {
                        visible: page.selectionPresente
                        text: page.detail.etatLibelle || ""
                        color: Colors.textPrimary
                    }
                    Paragraphe { text: page.detail.description || ""; visible: text.length > 0 }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Utilisation"); value: page.detail.cible || ""; visible: value.length > 0 }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Profils"); value: page.detail.profils || ""; visible: value.length > 0 }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Licence"); value: page.detail.licence || ""; visible: value.length > 0 }
                    KeyValueRow { Layout.fillWidth: true; label: qsTr("Version"); value: page.detail.version || ""; visible: value.length > 0 }
                    Paragraphe { text: page.detail.raison || ""; visible: text.length > 0 }
                    Paragraphe { text: page.detail.frontiere || ""; visible: text.length > 0 }
                    Paragraphe { text: page.detail.observation || ""; visible: text.length > 0 }
                    Paragraphe { text: page.detail.prerequis || ""; visible: text.length > 0 }
                    Flow {
                        Layout.fillWidth: true
                                spacing: Space.space2
                        AcpButton {
                            objectName: "outils-coffre"
                            visible: page.detail.id === "integration:obsidian"
                            label: qsTr("Ouvrir le coffre ACP")
                            onTriggered: Navigation.setCurrentRoute("vault")
                        }
                        AcpButton {
                            objectName: "outils-source"
                            visible: !!page.detail.url
                            label: qsTr("Voir la source")
                            onTriggered: Catalogue.ouvrirSource(page.detail.id)
                        }
                        AcpButton {
                            objectName: "outils-copier"
                            visible: !!page.detail.configuration
                            label: qsTr("Copier la fiche")
                            onTriggered: Catalogue.copierConfiguration(page.detail.id)
                        }
                        AcpButton {
                            objectName: "outils-preparer"
                            visible: !!page.detail.peutConsigne
                            label: qsTr("Préparer une consigne")
                            manualEnabled: page.detail.type !== "skills" || (Catalogue.lue && Catalogue.erreur.length === 0 && Catalogue.actif)
                            onTriggered: {
                                const texte = Catalogue.consignePour(page.detail.id)
                                if (texte.length > 0) {
                                    Discussion.preparerConsigne(texte)
                                    Navigation.setCurrentRoute("chat")
                                }
                            }
                        }
                    }
                    Paragraphe {
                        visible: !!page.detail.peutConsigne
                        text: qsTr("La consigne sera ajoutée au brouillon de Discussion. Vous pourrez la compléter avant de l’envoyer.")
                    }
                    BlocTexte { Layout.fillWidth: true; visible: !!page.detail.configuration; texte: page.detail.configuration || "" }
                    Paragraphe { text: page.detail.commit ? qsTr("Source épinglée : %1").arg(page.detail.commit) : ""; visible: text.length > 0; wrapMode: Text.WrapAnywhere }
                }
            }
            Paragraphe { text: Catalogue.cadence; visible: text.length > 0 }
            Item { Layout.preferredHeight: Space.space8 }
        }
    }
}
