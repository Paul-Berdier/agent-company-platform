// Barre latérale de l'espace de travail (D167) : recherche, nouvelle mission, accès global
// « À traiter », conversations avec Hermes, puis les projets et leurs missions. Les réglages
// et les pages techniques vivent en bas, sous « Réglages ».
//
// Un « projet » de cette barre est un dépôt autorisé ; ses lignes sont les missions servies
// par le greffon (D166). Rien n'y est inventé : une barre vide le dit.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Rectangle {
    id: navigation
    color: Colors.surfaceSidebar
    readonly property bool collapsed: width <= Space.layoutSidebarCollapsedWidth + 8

    // La barre est toujours affichée en session : elle lit la liste des missions.
    Component.onCompleted: Espace.pageVisible = true
    Component.onDestruction: Espace.pageVisible = false

    component NavEntry: Item {
        id: entry
        property string label: ""
        property string iconName: "chat"
        property string explanation: ""
        property bool selected: false
        property bool actionable: true
        //! Compteur affiché à droite ; 0 ou inconnu (négatif) : rien.
        property int compteur: 0
        property string compteurDescription: ""
        signal activated()
        implicitHeight: Math.max(Space.densityHitTargetMinimum, Space.rowHeight)
        activeFocusOnTab: visible
        FondPixel {
            anchors.fill: parent
            anchors.leftMargin: Space.space2
            anchors.rightMargin: Space.space2
            couleur: entry.selected ? Colors.accentMuted
                : hover.hovered && entry.actionable ? Colors.stateHover : "transparent"
            bordure: Colors.borderFocus
            epaisseur: entry.activeFocus ? Space.layoutFocusRingWidth : 0
            rayon: Radius.radiusMd
        }
        AcpIcon {
            id: icon
            anchors.left: parent.left
            anchors.leftMargin: Space.space5
            anchors.verticalCenter: parent.verticalCenter
            name: entry.iconName
            size: 17
            color: entry.selected ? Colors.accentPrimary : entry.actionable ? Colors.textSecondary : Colors.textMuted
        }
        Text {
            anchors.left: icon.right
            anchors.leftMargin: Space.space4
            anchors.right: compteurEntree.visible ? compteurEntree.left : parent.right
            anchors.rightMargin: Space.space3
            anchors.verticalCenter: parent.verticalCenter
            visible: !navigation.collapsed
            text: entry.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: entry.actionable ? Colors.textPrimary : Colors.textMuted
            font.family: Type.tableCell.family
            font.pixelSize: Type.tableCell.pixelSize
            font.weight: entry.selected ? Type.tableCellEmphasis.weight : Type.tableCell.weight
        }
        PastilleCompteur {
            id: compteurEntree
            anchors.right: parent.right
            anchors.rightMargin: Space.space4
            anchors.verticalCenter: parent.verticalCenter
            nombre: navigation.collapsed ? 0 : entry.compteur
            description: entry.compteurDescription
        }
        Rectangle {
            visible: entry.selected
            anchors.left: parent.left
            anchors.leftMargin: Space.space2
            anchors.verticalCenter: parent.verticalCenter
            width: Space.layoutPixelUnit; height: 14
            color: Colors.accentPrimary
        }
        HoverHandler { id: hover; cursorShape: entry.actionable ? Qt.PointingHandCursor : Qt.ArrowCursor }
        TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: if (entry.actionable) entry.activated() }
        Keys.onReturnPressed: if (entry.actionable) entry.activated()
        Keys.onSpacePressed: if (entry.actionable) entry.activated()
        Accessible.role: Accessible.Button
        Accessible.name: entry.compteur > 0 && entry.compteurDescription.length > 0
            ? entry.label + " (" + entry.compteur + " " + entry.compteurDescription + ")" : entry.label
        Accessible.description: entry.explanation
        Accessible.focusable: true
        Accessible.onPressAction: if (entry.actionable) entry.activated()
        ToolTip {
            id: tip
            visible: hover.hovered && (navigation.collapsed || entry.explanation.length > 0)
            delay: 400
            text: entry.label + (entry.explanation ? "\n" + entry.explanation : "")
            contentItem: Text { text: tip.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Space.space4
        anchors.bottomMargin: Space.space3
        spacing: Space.space2

        // Identité : l'emblème et le nom, en police pixel (libellé court).
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: navigation.collapsed ? Space.space3 : Space.space5
            Layout.rightMargin: Space.space4
            spacing: Space.space4
            Embleme { taille: 24 }
            TextePixel {
                visible: !navigation.collapsed
                text: "ACP"
                couleur: "accent"
                echelle: 2
            }
            Item { Layout.fillWidth: true }
            AcpButton {
                objectName: "navigation-nouvelle-mission"
                visible: !navigation.collapsed
                label: ""
                iconName: "plus"
                commandId: "projects.new"
                Accessible.name: qsTr("Nouvelle mission · Ctrl+N")
            }
        }

        AcpTextField {
            id: recherche
            objectName: "navigation-recherche"
            Layout.fillWidth: true
            Layout.leftMargin: Space.space4
            Layout.rightMargin: Space.space4
            visible: !navigation.collapsed
            placeholder: qsTr("Rechercher une mission")
            accessibleName: qsTr("Rechercher une mission ou un projet")
            // Le texte saisi pilote la recherche ; elle est oubliée avec la session, et le champ avec elle.
            Component.onCompleted: text = Espace.recherche
            onTextChanged: Espace.recherche = text
            Connections {
                target: Espace
                function onArbreChange() {
                    if (recherche.text !== Espace.recherche) recherche.text = Espace.recherche
                }
            }
        }

        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-home"
            label: qsTr("Accueil"); iconName: "grid"
            selected: Navigation.currentRoute === "home"
            onActivated: Navigation.setCurrentRoute("home")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-questions"
            label: qsTr("À traiter"); iconName: "check"
            selected: Navigation.currentRoute === "questions"
            compteur: Streams.aTraiter
            // Le nom accessible dit ce que le total compte : discussions comprises quand elles sont lues.
            compteurDescription: Streams.descriptionATraiter
            onActivated: Navigation.setCurrentRoute("questions")
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-chat"
            label: qsTr("Conversations avec Hermes"); iconName: "chat"
            selected: Navigation.currentRoute === "chat"
            onActivated: Navigation.setCurrentRoute("chat")
        }

        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.rightMargin: Space.space5
            Layout.topMargin: Space.space2
            height: Space.layoutBorderWidth; color: Colors.borderSubtle
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Space.space5
            Layout.rightMargin: Space.space4
            visible: !navigation.collapsed
            TextePixel {
                text: qsTr("PROJETS")
                couleur: "attenue"
                echelle: 1
            }
            Item { Layout.fillWidth: true }
            Text {
                objectName: "navigation-compte-missions"
                text: Espace.listeLue
                    ? qsTr("%1 · %2").arg(Espace.nombreProjets === 1 ? qsTr("1 projet") : qsTr("%1 projets").arg(Espace.nombreProjets))
                                      .arg(Espace.nombreMissions === 1 ? qsTr("1 mission") : qsTr("%1 missions").arg(Espace.nombreMissions))
                    : ""
                textFormat: Text.PlainText
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }

        ListView {
            id: arbre
            objectName: "navigation-arbre"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !navigation.collapsed
            clip: true
            model: Espace.arbre
            reuseItems: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: LigneArbre {
                required property var item
                width: arbre.width
                ligne: item
            }
            Text {
                anchors.fill: parent
                anchors.margins: Space.space5
                visible: arbre.count === 0
                text: !Session.connectee ? qsTr("Connectez-vous pour voir vos projets.")
                    : Espace.erreur.length > 0 ? qsTr("Liste des missions illisible : %1").arg(Espace.erreur)
                    : !Espace.listeLue ? qsTr("Lecture des missions…")
                    : Espace.recherche.length > 0 ? qsTr("Aucune mission ne correspond à « %1 ».").arg(Espace.recherche)
                    : qsTr("Aucune mission pour l'instant. « Nouvelle mission » lance la première sur un dépôt autorisé.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Colors.textMuted
                font.family: Type.metadata.family
                font.pixelSize: Type.metadata.pixelSize
            }
        }
        Item { Layout.fillHeight: true; visible: navigation.collapsed }

        Rectangle {
            Layout.fillWidth: true; Layout.leftMargin: Space.space5; Layout.rightMargin: Space.space5
            height: Space.layoutBorderWidth; color: Colors.borderSubtle
        }
        NavEntry {
            Layout.fillWidth: true
            objectName: "navigation-settings"
            label: qsTr("Réglages"); iconName: "settings"
            explanation: qsTr("Apparence, comptes, exécutants, modèles et budgets, sauvegarde, diagnostics")
            selected: ["settings", "station", "quotas", "routing", "backup", "diagnostics"].indexOf(Navigation.currentRoute) >= 0
            onActivated: Navigation.setCurrentRoute("settings")
        }
    }
}
