// Une ligne de la barre des projets : un projet (dépôt), ses missions archivées repliées, ou
// une mission. La sélection ouvre la mission au centre ; elle n'envoie rien au serveur.
import QtQuick
import QtQuick.Controls.Basic
import Acp.Design
import Acp.Runtime
import Acp.Pixel
import Acp.Controls
import Acp.Components

Item {
    id: ligneArbre
    property var ligne: ({})
    readonly property string type: ligneArbre.ligne.type || ""
    readonly property bool estMission: ligneArbre.type === "mission"
    // Marquée seulement quand la mission est affichée au centre (pas sous l'Accueil ni les Réglages).
    readonly property bool selectionnee: ligneArbre.estMission && ligneArbre.ligne.selectionnee === true
                                         && Navigation.currentRoute === "projects"
    implicitHeight: ligneArbre.type === "groupe" ? Math.max(Space.densityHitTargetMinimum, Space.rowHeight + Space.space2)
        : Math.max(Space.densityHitTargetMinimum, Space.rowHeight)
    activeFocusOnTab: true

    function activer() {
        if (ligneArbre.estMission)
            Espace.selectionnerMission(ligneArbre.ligne.id)
        else
            Espace.basculer(ligneArbre.ligne.cle)
    }

    FondPixel {
        anchors.fill: parent
        anchors.leftMargin: Space.space2
        anchors.rightMargin: Space.space2
        couleur: ligneArbre.selectionnee ? Colors.accentMuted : survol.hovered ? Colors.stateHover : "transparent"
        bordure: Colors.borderFocus
        epaisseur: ligneArbre.activeFocus ? Space.layoutFocusRingWidth : 0
        rayon: Radius.radiusSm
    }
    Rectangle {
        visible: ligneArbre.selectionnee
        anchors.left: parent.left
        anchors.leftMargin: Space.space2
        anchors.verticalCenter: parent.verticalCenter
        width: Space.layoutPixelUnit; height: 14
        color: Colors.accentPrimary
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: Space.space5 + (ligneArbre.ligne.niveau || 0) * Space.space6
        anchors.right: badges.left
        anchors.rightMargin: Space.space3
        anchors.verticalCenter: parent.verticalCenter
        spacing: Space.space3
        AcpIcon {
            visible: !ligneArbre.estMission
            anchors.verticalCenter: parent.verticalCenter
            name: ligneArbre.ligne.deplie ? "chevronDown" : "chevronRight"
            size: 14
            color: Colors.textMuted
        }
        PictoProjet {
            visible: ligneArbre.type !== "archives"
            anchors.verticalCenter: parent.verticalCenter
            motif: ligneArbre.ligne.motif || "cristal"
            teinte: ligneArbre.ligne.teinte || "lavande"
            echelle: ligneArbre.type === "groupe" ? 2 : 1
            opacity: ligneArbre.ligne.archivee === true ? 0.55 : 1
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x
            text: ligneArbre.ligne.libelle || ""
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: ligneArbre.ligne.archivee === true || ligneArbre.type === "archives" ? Colors.textMuted : Colors.textPrimary
            font.family: ligneArbre.type === "groupe" ? Type.identifier.family : Type.tableCell.family
            font.pixelSize: Type.tableCell.pixelSize
            font.weight: ligneArbre.type === "groupe" || ligneArbre.selectionnee ? Type.tableCellEmphasis.weight : Type.tableCell.weight
        }
    }

    Row {
        id: badges
        anchors.right: parent.right
        anchors.rightMargin: Space.space4
        anchors.verticalCenter: parent.verticalCenter
        spacing: Space.space2
        // Décision attendue : la seule pastille pleine (elle mène à « À traiter »).
        PastilleCompteur {
            anchors.verticalCenter: parent.verticalCenter
            nombre: ligneArbre.ligne.questions || 0
            description: qsTr("questions ouvertes")
        }
        Rectangle {
            // Échec ou blocage observé : un carré d'alerte, doublé du nom accessible.
            visible: (ligneArbre.ligne.bloquees || 0) > 0
            anchors.verticalCenter: parent.verticalCenter
            width: Space.layoutPixelUnit * 3; height: width
            color: Status.statusBlockedForeground
        }
        Text {
            visible: ligneArbre.estMission && (ligneArbre.ligne.progression || "").length > 0 && ligneArbre.width > 220
            anchors.verticalCenter: parent.verticalCenter
            text: ligneArbre.ligne.progression || ""
            textFormat: Text.PlainText
            color: Colors.textMuted
            font.family: Type.identifier.family
            font.pixelSize: Type.metadata.pixelSize
        }
        Text {
            visible: ligneArbre.type === "groupe"
            anchors.verticalCenter: parent.verticalCenter
            text: ligneArbre.ligne.missions || 0
            textFormat: Text.PlainText
            color: Colors.textMuted
            font.family: Type.identifier.family
            font.pixelSize: Type.metadata.pixelSize
        }
        AcpButton {
            visible: ligneArbre.type === "groupe" && (survol.hovered || ligneArbre.activeFocus)
            anchors.verticalCenter: parent.verticalCenter
            label: ""
            iconName: "plus"
            implicitWidth: Space.densityControlHeightSmall + Space.space3
            implicitHeight: Space.densityControlHeightSmall
            Accessible.name: qsTr("Nouvelle mission dans %1").arg(ligneArbre.ligne.libelle || "")
            onTriggered: Espace.nouvelleMission(ligneArbre.ligne.depot || "")
        }
    }

    HoverHandler { id: survol; cursorShape: Qt.PointingHandCursor }
    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: ligneArbre.activer() }
    Keys.onReturnPressed: ligneArbre.activer()
    Keys.onSpacePressed: ligneArbre.activer()
    Keys.onRightPressed: if (!ligneArbre.estMission && !ligneArbre.ligne.deplie) Espace.basculer(ligneArbre.ligne.cle)
    Keys.onLeftPressed: if (!ligneArbre.estMission && ligneArbre.ligne.deplie) Espace.basculer(ligneArbre.ligne.cle)

    Accessible.role: ligneArbre.estMission ? Accessible.Button : Accessible.TreeItem
    Accessible.name: ligneArbre.estMission
        ? qsTr("Mission %1, %2").arg(ligneArbre.ligne.libelle || "").arg(ligneArbre.ligne.etatLibelle || "")
            + ((ligneArbre.ligne.questions || 0) > 0 ? qsTr(", %1 questions ouvertes").arg(ligneArbre.ligne.questions) : "")
            + ((ligneArbre.ligne.bloquees || 0) > 0 ? qsTr(", %1 tâches bloquées").arg(ligneArbre.ligne.bloquees) : "")
        : (ligneArbre.ligne.libelle || "") + (ligneArbre.ligne.deplie ? qsTr(", déplié") : qsTr(", replié"))
    Accessible.focusable: true
    Accessible.onPressAction: ligneArbre.activer()

    ToolTip {
        id: info
        visible: survol.hovered && ligneArbre.estMission
        delay: 500
        text: (ligneArbre.ligne.libelle || "") + "\n" + (ligneArbre.ligne.etatLibelle || "")
        contentItem: Text { text: info.text; textFormat: Text.PlainText; color: Colors.textPrimary; wrapMode: Text.Wrap }
    }
}
