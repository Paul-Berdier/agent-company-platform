// Réglages (D167) : les pages techniques quittent la barre latérale et se regroupent ici.
// Les sections reliées à une route (Exécutants, Modèles et routage, Quotas et budgets, Sauvegarde,
// Diagnostics) la suivent : raccourcis, palette et historique restent valables. Les autres
// sections vivent sous la route « settings ».
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Item {
    id: hub

    property string sectionLocale: "apparence"
    readonly property var sections: [
        { "cle": "apparence", "libelle": qsTr("Apparence"), "route": "settings", "icone": "grid" },
        { "cle": "comptes", "libelle": qsTr("Comptes et assistants"), "route": "settings", "icone": "chat" },
        { "cle": "executants", "libelle": qsTr("Exécutants"), "route": "station", "icone": "activity" },
        { "cle": "modeles", "libelle": qsTr("Modèles et routage"), "route": "routing", "icone": "code" },
        { "cle": "quotas", "libelle": qsTr("Quotas et budgets"), "route": "quotas", "icone": "gauge" },
        { "cle": "outils", "libelle": qsTr("Outils et skills"), "route": "settings", "icone": "folder" },
        { "cle": "sauvegarde", "libelle": qsTr("Sauvegarde"), "route": "backup", "icone": "archive" },
        { "cle": "diagnostics", "libelle": qsTr("Diagnostics"), "route": "diagnostics", "icone": "activity" },
        { "cle": "connexion", "libelle": qsTr("Connexion et mises à jour"), "route": "settings", "icone": "settings" }
    ]
    readonly property string section: {
        switch (Navigation.currentRoute) {
        case "station": return "executants";
        case "routing": return "modeles";
        case "quotas": return "quotas";
        case "backup": return "sauvegarde";
        case "diagnostics": return "diagnostics";
        default: return hub.sectionLocale;
        }
    }

    function ouvrir(entree) {
        if (entree.route === "settings")
            hub.sectionLocale = entree.cle;
        Navigation.setCurrentRoute(entree.route);
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 236
            color: Colors.surfaceSidebar
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Space.space4
                spacing: Space.space1
                TextePixel { Layout.margins: Space.space3; text: qsTr("RÉGLAGES"); couleur: "attenue"; echelle: 1 }
                Repeater {
                    model: hub.sections
                    delegate: Item {
                        id: entree
                        required property var modelData
                        readonly property bool choisie: hub.section === modelData.cle
                        objectName: "reglages-section-" + modelData.cle
                        Layout.fillWidth: true
                        implicitHeight: Math.max(Space.densityHitTargetMinimum, Space.rowHeight)
                        activeFocusOnTab: true
                        FondPixel {
                            anchors.fill: parent
                            couleur: entree.choisie ? Colors.accentMuted : survol.hovered ? Colors.stateHover : "transparent"
                            bordure: Colors.borderFocus
                            epaisseur: entree.activeFocus ? Space.layoutFocusRingWidth : 0
                            rayon: Radius.radiusSm
                        }
                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: Space.space4
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Space.space4
                            AcpIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                name: entree.modelData.icone
                                size: 15
                                color: entree.choisie ? Colors.accentPrimary : Colors.textSecondary
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: entree.modelData.libelle
                                textFormat: Text.PlainText
                                color: Colors.textPrimary
                                font.family: Type.tableCell.family
                                font.pixelSize: Type.tableCell.pixelSize
                                font.weight: entree.choisie ? Type.tableCellEmphasis.weight : Type.tableCell.weight
                            }
                        }
                        HoverHandler { id: survol; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: hub.ouvrir(entree.modelData) }
                        Keys.onReturnPressed: hub.ouvrir(entree.modelData)
                        Keys.onSpacePressed: hub.ouvrir(entree.modelData)
                        Accessible.role: Accessible.PageTab
                        Accessible.name: entree.modelData.libelle
                        Accessible.focusable: true
                        Accessible.onPressAction: hub.ouvrir(entree.modelData)
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: Space.layoutBorderWidth; color: Colors.borderSubtle }

        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: {
                switch (hub.section) {
                case "comptes": return comptes;
                case "executants": return executants;
                case "modeles": return modeles;
                case "quotas": return quotas;
                case "outils": return outils;
                case "sauvegarde": return sauvegarde;
                case "diagnostics": return diagnostics;
                case "connexion": return connexion;
                default: return apparence;
                }
            }
        }
    }

    Component { id: apparence; ApparencePage {} }
    Component { id: comptes; ComptesPage {} }
    Component { id: executants; PostePage {} }
    Component { id: modeles; RoutagePage {} }
    Component { id: quotas; QuotasPage {} }
    Component { id: sauvegarde; SauvegardePage {} }
    Component { id: diagnostics; DiagnosticsPage {} }
    Component { id: connexion; SettingsPage {} }
    Component {
        id: outils
        EmptyState {
            objectName: "reglages-outils"
            title: qsTr("Outils et skills")
            body: qsTr("Le catalogue des skills et des connecteurs MCP autorisés est servi par Hermes (/v1/catalogue) "
                       + "et consultable dans son tableau de bord. Cette version de la station ne l'affiche pas encore : "
                       + "provenance, licence, périmètre et autorisation par projet arrivent au lot E. Rien n'est "
                       + "installé ni autorisé depuis la station.")
        }
    }
}
