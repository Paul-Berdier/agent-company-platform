// Volet bas de la mission ouverte : Activité, Changements, Tests, Sorties, Services.
//
// Chaque onglet montre ce que le greffon sert déjà, rien de plus : le journal de la mission,
// la vérification rapportée à la fin de chaque tâche, les résumés des tâches. Le diff et les
// sorties brutes restent sur l'exécutant ; l'onglet le dit au lieu de les simuler.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Rectangle {
    id: volet
    color: Colors.surfaceSunken

    readonly property var onglets: [
        { "cle": "activite", "libelle": qsTr("Activité") },
        { "cle": "changements", "libelle": qsTr("Changements") },
        { "cle": "tests", "libelle": qsTr("Tests") },
        { "cle": "sorties", "libelle": qsTr("Sorties") },
        { "cle": "services", "libelle": qsTr("Services") }
    ]
    readonly property int rang: Math.max(0, Shell.bottomDrawerTabs.indexOf(Shell.bottomDrawerTab))

    component Vide: Text {
        Layout.fillWidth: true
        Layout.margins: Space.space5
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Space.space4
            Layout.rightMargin: Space.space4
            Layout.topMargin: Space.space2
            Layout.bottomMargin: Space.space2
            spacing: Space.space2
            Repeater {
                model: volet.onglets
                delegate: AcpButton {
                    required property var modelData
                    required property int index
                    objectName: "volet-onglet-" + modelData.cle
                    label: modelData.libelle
                    primary: volet.rang === index
                    onTriggered: Shell.bottomDrawerTab = modelData.cle
                    Accessible.role: Accessible.PageTab
                }
            }
            Item { Layout.fillWidth: true }
            AcpButton {
                objectName: "volet-masquer"
                label: ""
                iconName: "close"
                commandId: "shell.toggleDrawer"
                Accessible.name: qsTr("Masquer le volet · Ctrl+J")
            }
        }
        Rectangle { Layout.fillWidth: true; height: Space.layoutBorderWidth; color: Colors.borderSubtle }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: volet.rang

            // Activité : journal de la mission (les 100 dernières lignes servies, du plus récent au plus ancien).
            ListView {
                id: journal
                // Marges du contenu : les lignes ne collent pas au bord du volet.
                leftMargin: Space.space5
                rightMargin: Space.space5
                topMargin: Space.space3
                bottomMargin: Space.space3
                objectName: "volet-activite"
                clip: true
                model: Projets.journal
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: RowLayout {
                    required property var item
                    width: journal.width - journal.leftMargin - journal.rightMargin
                    spacing: Space.space4
                    Text {
                        text: item.quand || ""
                        textFormat: Text.PlainText
                        color: Colors.textMuted
                        font.family: Type.logLine.family
                        font.pixelSize: Type.logLine.pixelSize
                    }
                    Text {
                        text: item.acteur || ""
                        textFormat: Text.PlainText
                        color: Colors.accentSecondary
                        font.family: Type.logLine.family
                        font.pixelSize: Type.logLine.pixelSize
                    }
                    Text {
                        Layout.fillWidth: true
                        text: [item.action, item.cible, item.detail].filter(x => (x || "").length > 0).join(" · ")
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        color: Colors.textSecondary
                        font.family: Type.logLine.family
                        font.pixelSize: Type.logLine.pixelSize
                    }
                }
                Vide {
                    anchors.fill: parent
                    visible: journal.count === 0
                    text: qsTr("Aucune ligne de journal servie pour cette mission.")
                }
            }

            ColumnLayout {
                objectName: "volet-changements"
                Vide {
                    text: qsTr("Changements : le diff reste sur l'exécutant, qui ne pousse jamais. Ce serveur ne sert pas "
                               + "encore le résumé des changements par tâche (prévu au lot D : diffstat et branche servis "
                               + "avec chaque tâche). La récupération du travail passe par la commande indiquée dans "
                               + "l'onglet Pilotage.")
                }
                Item { Layout.fillHeight: true }
            }

            ListView {
                id: essais
                // Marges du contenu : les lignes ne collent pas au bord du volet.
                leftMargin: Space.space5
                rightMargin: Space.space5
                topMargin: Space.space3
                bottomMargin: Space.space3
                objectName: "volet-tests"
                clip: true
                model: Espace.essais
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: RowLayout {
                    required property var item
                    width: essais.width - essais.leftMargin - essais.rightMargin
                    height: Space.rowHeight
                    spacing: Space.space4
                    StatusChip { statusKey: item.statusKey || "unknown"; label: item.libelle || "" }
                    Text {
                        Layout.fillWidth: true
                        text: item.titre || ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        color: Colors.textPrimary
                        font.family: Type.tableCell.family
                        font.pixelSize: Type.tableCell.pixelSize
                    }
                    Text {
                        text: item.quand || ""
                        textFormat: Text.PlainText
                        color: Colors.textMuted
                        font.family: Type.identifier.family
                        font.pixelSize: Type.metadata.pixelSize
                    }
                }
                Vide {
                    anchors.fill: parent
                    visible: essais.count === 0
                    text: qsTr("Aucune vérification rapportée : elles arrivent avec la fin de chaque tâche (état seulement ; "
                               + "le détail des commandes reste sur l'exécutant).")
                }
            }

            ListView {
                id: sorties
                // Marges du contenu : les lignes ne collent pas au bord du volet.
                leftMargin: Space.space5
                rightMargin: Space.space5
                topMargin: Space.space3
                bottomMargin: Space.space3
                objectName: "volet-sorties"
                clip: true
                model: Espace.sorties
                spacing: Space.space4
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: BlocTexte {
                    required property var item
                    width: sorties.width - sorties.leftMargin - sorties.rightMargin
                    libelle: (item.titre || "") + (item.tronque ? qsTr(" (résumé tronqué, %1 caractères en tout)").arg(item.longueur) : "")
                    texte: item.resume || ""
                }
                Vide {
                    anchors.fill: parent
                    visible: sorties.count === 0
                    text: qsTr("Aucun résumé de tâche pour l'instant. Les sorties brutes des CLI ne sont pas remontées.")
                }
            }

            ColumnLayout {
                objectName: "volet-services"
                spacing: Space.space3
                Vide {
                    text: Streams.libelleResume.length > 0
                        ? qsTr("Exécutant et file : %1").arg(Streams.libelleResume)
                        : qsTr("État de l'exécutant : Inconnu (aucun relevé lu dans cette session).")
                }
                Vide {
                    text: qsTr("Aucun service de développement n'est géré par ACP dans cette version : un service se "
                               + "déclarera avec son état, son propriétaire, ses journaux et son arrêt (backlog).")
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
