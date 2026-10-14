// Journal conservé côté serveur : la visibilité ne commande que sa lecture.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Acp.Design
import Acp.Runtime
import Acp.Components
import Acp.Controls

ColumnLayout {
    id: panneau
    property bool execution: true
    spacing: Space.space4
    function synchroniser() {
        JournalExecution.pageVisible = false;
        JournalExecution.choisirProjet(Projets.vue === "detail" ? Projets.projetOuvert : "");
        JournalExecution.pageVisible = visible && execution && Projets.vue === "detail";
    }
    Component.onCompleted: synchroniser()
    onVisibleChanged: synchroniser()
    onExecutionChanged: synchroniser()
    Component.onDestruction: JournalExecution.pageVisible = false
    Connections {
        target: Projets
        function onVueChange() { panneau.synchroniser(); }
    }
    component Legende: Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Colors.textMuted
        font.family: Type.metadata.family
        font.pixelSize: Type.metadata.pixelSize
    }
    RowLayout {
        Layout.fillWidth: true
        AcpButton {
            objectName: "journal-execution"
            label: qsTr("Exécution des agents")
            manualEnabled: !panneau.execution
            onTriggered: panneau.execution = true
        }
        AcpButton {
            objectName: "journal-decisions"
            label: qsTr("Décisions du projet")
            manualEnabled: panneau.execution
            onTriggered: panneau.execution = false
        }
        Item { Layout.fillWidth: true }
        AcpButton {
            objectName: "journal-actualiser"
            visible: panneau.execution
            label: JournalExecution.chargement ? qsTr("Lecture…") : qsTr("Actualiser")
            manualEnabled: JournalExecution.actif && !JournalExecution.chargement
            onTriggered: JournalExecution.actualiser()
        }
    }
    Legende {
        text: panneau.execution
            ? qsTr("Événements d’exécution conservés sur le serveur. La lecture reprend sans relancer les agents.")
            : qsTr("Décisions et changements d’état rapportés par Hermes.")
    }
    Legende {
        visible: panneau.execution && JournalExecution.erreur.length > 0
        text: JournalExecution.erreur
        color: Status.statusDegradedForeground
        Accessible.role: Accessible.AlertMessage
    }
    Legende {
        visible: panneau.execution && JournalExecution.historiqueBorne
        text: qsTr("Les 5 000 derniers événements chargés sont affichés. Les précédents restent conservés sur le serveur.")
    }
    Legende {
        visible: panneau.execution ? JournalExecution.evenements.count === 0 : Projets.journal.count === 0
        text: panneau.execution && JournalExecution.chargement ? qsTr("Chargement du journal distant…") : qsTr("Aucun événement disponible pour l’instant.")
    }
    ListView {
        id: liste
        objectName: "journal-evenements"
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: Space.space4
        model: panneau.execution ? JournalExecution.evenements : Projets.journal
        ScrollBar.vertical: ScrollBar {}
        delegate: ColumnLayout {
            id: evenement
            required property var item
            property bool details: false
            width: Math.max(0, liste.width - Space.space5)
            spacing: Space.space2
            Legende {
                text: panneau.execution
                    ? [evenement.item.quand, evenement.item.agent || evenement.item.moteur, evenement.item.genre === "termine" ? qsTr("Tour moteur terminé") : evenement.item.genre, evenement.item.outil].filter(t => t && t.length > 0).join(" · ")
                    : evenement.item.quand + " · " + evenement.item.acteur
            }
            BlocTexte {
                Layout.fillWidth: true
                libelle: panneau.execution
                    ? [evenement.item.carte, evenement.item.modele_demande ? qsTr("Modèle demandé : ") + evenement.item.modele_demande : "", evenement.item.modele_servi ? qsTr("Modèle servi : ") + evenement.item.modele_servi : qsTr("Modèle servi non rapporté")].filter(t => t && t.length > 0).join(" · ")
                    : [evenement.item.action, evenement.item.cible].filter(t => t && t.length > 0).join(" · ")
                texte: panneau.execution ? evenement.item.texte : evenement.item.detail
            }
            AcpButton {
                visible: panneau.execution
                label: evenement.details ? qsTr("Masquer les identifiants") : qsTr("Identifiants et filiation")
                onTriggered: evenement.details = !evenement.details
            }
            BlocTexte {
                Layout.fillWidth: true
                visible: panneau.execution && evenement.details
                monospace: true
                texte: !panneau.execution ? "" : [
                    qsTr("Événement : ") + evenement.item.id,
                    qsTr("Projet : ") + evenement.item.projet_id,
                    qsTr("Exécution : ") + (evenement.item.run_id || qsTr("Non rapportée")),
                    qsTr("Tentative : ") + (evenement.item.tentative_id || qsTr("Non rapportée")),
                    qsTr("Session native : ") + (evenement.item.session_native || qsTr("Non rapportée")),
                    qsTr("Serveur : ") + (evenement.item.machine_id || qsTr("Non rapporté")),
                    qsTr("Parent natif : ") + (evenement.item.parent_natif || qsTr("Non rapporté")),
                    qsTr("Parents : ") + (evenement.item.parents || qsTr("Aucun rapporté"))
                ].join("\n")
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: Colors.borderSubtle
            }
        }
    }
}
