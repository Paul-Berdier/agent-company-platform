import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import Acp.Design
import Acp.Runtime
import Acp.Controls

Item {
    id: page
    property string pendingExportId: ""

    function value(key) {
        const result = Artifacts.selected[key];
        return result === undefined || result === null || result === "" ? qsTr("Inconnu") : String(result);
    }

    FileDialog {
        id: saveDialog
        title: qsTr("Exporter le livrable")
        fileMode: FileDialog.SaveFile
        onAccepted: Artifacts.downloadSelected(selectedFile, page.pendingExportId)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Space.space6
        spacing: Space.space4

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Livrables")
                textFormat: Text.PlainText
                color: Colors.textPrimary
                font.pixelSize: 24
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: Artifacts.busy || Artifacts.detailBusy; visible: running }
            AcpButton {
                label: qsTr("Actualiser")
                manualEnabled: Artifacts.projectId.length > 0 && !Artifacts.busy
                onTriggered: Artifacts.reload()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            TextField {
                Layout.fillWidth: true
                placeholderText: qsTr("Type de flux — vide pour tous")
                Accessible.name: qsTr("Filtrer par type de flux")
                text: Artifacts.streamKind
                selectByMouse: true
                onEditingFinished: Artifacts.streamKind = text
            }
            TextField {
                Layout.fillWidth: true
                placeholderText: qsTr("Identifiant de tentative — vide pour toutes")
                Accessible.name: qsTr("Filtrer par tentative")
                text: Artifacts.runId
                selectByMouse: true
                onEditingFinished: Artifacts.runId = text
            }
        }

        Label {
            Layout.fillWidth: true
            visible: Artifacts.error.length > 0
            text: Artifacts.error
            textFormat: Text.PlainText
            color: Colors.textPrimary
            wrapMode: Text.Wrap
            Accessible.role: Accessible.AlertMessage
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            ColumnLayout {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 230
                spacing: Space.space3
                ListView {
                    id: entries
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: Artifacts.rows
                    clip: true
                    spacing: 2
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ItemDelegate {
                        id: row
                        required property var item
                        width: entries.width
                        highlighted: Artifacts.selected.id === item.id
                        Accessible.name: String(item.original_name || item.id)
                        onClicked: Artifacts.selectArtifact(String(item.id))
                        contentItem: Column {
                            spacing: 4
                            Label {
                                width: parent.width
                                text: String(row.item.original_name || row.item.id)
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.bold: true
                            }
                            Label {
                                width: parent.width
                                text: String(row.item.stream_kind || row.item.kind || "")
                                      + " · " + Number(row.item.size_bytes || 0).toLocaleString(Qt.locale()) + qsTr(" octets")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                            }
                        }
                    }
                    Label {
                        anchors.centerIn: parent
                        width: parent.width - 24
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                        visible: entries.count === 0 && !Artifacts.busy && Artifacts.error.length === 0
                        text: Artifacts.projectId.length === 0
                              ? qsTr("Sélectionnez un projet.") : (!Artifacts.available
                                  ? qsTr("Connectez-vous pour lire les livrables.") : qsTr("Aucun livrable pour ces filtres."))
                    }
                }
                AcpButton {
                    label: qsTr("Charger la suite")
                    visible: Artifacts.canLoadMore
                    manualEnabled: !Artifacts.busy
                    onTriggered: Artifacts.nextPage()
                }
            }

            ScrollView {
                SplitView.preferredWidth: 370
                SplitView.minimumWidth: 260
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: Space.space4
                    Label {
                        Layout.fillWidth: true
                        text: Artifacts.selected.id ? page.value("original_name") : qsTr("Sélectionnez un livrable")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        font.bold: true
                        font.pixelSize: 18
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !!Artifacts.selected.id
                        text: qsTr("Type : %1\nFlux : %2\nTaille : %3 octets\nTentative : %4\nCréation : %5\nSHA-256 : %6")
                            .arg(page.value("content_type")).arg(page.value("stream_kind"))
                            .arg(page.value("size_bytes")).arg(page.value("task_run_id"))
                            .arg(page.value("created_at")).arg(page.value("checksum"))
                        textFormat: Text.PlainText
                        wrapMode: Text.WrapAnywhere
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Export vers un fichier local, limité à 512 Mio. Aucun contenu actif n’est exécuté dans la station.")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !!Artifacts.selected.id && !Artifacts.selected.has_content
                        text: qsTr("Contenu absent ou purgé : export indisponible.")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                    }
                    AcpButton {
                        label: qsTr("Exporter le fichier…")
                        manualEnabled: !!Artifacts.selected.id && !!Artifacts.selected.has_content
                                       && Number(Artifacts.selected.size_bytes) <= 512 * 1024 * 1024
                                       && !Artifacts.downloader.busy && !Artifacts.detailBusy
                        onTriggered: {
                            page.pendingExportId = String(Artifacts.selected.id);
                            saveDialog.selectedFile = Artifacts.suggestedSaveUrl;
                            saveDialog.open();
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: !!Artifacts.selected.id && Number(Artifacts.selected.size_bytes) > 512 * 1024 * 1024
                        text: qsTr("Ce fichier dépasse la limite d’export de 512 Mio de la station.")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                    }
                    ProgressBar {
                        Layout.fillWidth: true
                        visible: Artifacts.downloader.busy
                        from: 0
                        to: Math.max(1, Artifacts.downloader.total)
                        value: Artifacts.downloader.received
                    }
                    Label {
                        visible: Artifacts.downloader.busy
                        text: qsTr("%1 / %2 octets reçus")
                            .arg(Artifacts.downloader.received).arg(Artifacts.downloader.total)
                        textFormat: Text.PlainText
                    }
                    AcpButton {
                        visible: Artifacts.downloader.busy
                        label: qsTr("Annuler le téléchargement")
                        onTriggered: Artifacts.cancelDownload()
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: Artifacts.downloader.error.length > 0
                        text: Artifacts.downloader.error
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: Artifacts.downloader.savedFile.toString().length > 0
                        text: qsTr("Fichier exporté : %1").arg(Artifacts.downloader.savedFile)
                        textFormat: Text.PlainText
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }
        }
    }
}
